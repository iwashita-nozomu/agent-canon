//! Transactional ingestion of the host hook-event spool into the archive clone.

use super::{
    archive_blob_at, archive_runtime_root, canonical_compact_json, sha256_hex, ArchiveContext,
    ArchiveError, ArchivePublicationReceipt, PreparedArchiveTransaction,
};
use agent_canon::eval_archive_paths;
use agent_canon::runtime_boundary::{RuntimeArtifactBoundary, RuntimeSpoolBoundary};
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

const INDEX_SCHEMA: &str = "agent_canon.hook_spool_index.v1";
const CURSOR_SCHEMA: &str = "agent_canon.hook_spool_cursor.v1";
const CURSOR_NAME: &str = ".spool-cursor.json";
const ZERO_SHA256: &str = "0000000000000000000000000000000000000000000000000000000000000000";

#[derive(Clone)]
pub(super) struct EventSnapshot {
    pub path: PathBuf,
    pub size: u64,
    pub sha256: String,
}

pub(super) struct IngestResult {
    pub snapshot: Vec<EventSnapshot>,
    pub accepted: Vec<EventSnapshot>,
    pub duplicates: Vec<EventSnapshot>,
    pub index_path: PathBuf,
    pub index_sha256: String,
    pub cursor_sha256: String,
}

#[derive(Clone)]
struct IndexEntry {
    sha256: String,
    namespace: String,
    hook_name: String,
    projection: String,
}

fn error(code: &str) -> ArchiveError {
    ArchiveError::new(code, "")
}

fn hash(bytes: &[u8]) -> String {
    sha256_hex(bytes)
}

fn read(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    code: &str,
) -> Result<Option<Vec<u8>>, ArchiveError> {
    boundary
        .read_bytes(path)
        .map_err(|detail| ArchiveError::new(code, detail))
}

pub(super) fn snapshot(context: &ArchiveContext) -> Result<Vec<EventSnapshot>, ArchiveError> {
    let runtime_root = archive_runtime_root(context)?;
    let root = eval_archive_paths::hook_event_spool_root(&context.source_root, Some(&runtime_root))
        .map_err(|detail| ArchiveError::new("hook_spool_root_invalid", detail))?;
    let boundary =
        RuntimeSpoolBoundary::for_source(&context.source_root, Some(&runtime_root), false)
            .map_err(|detail| ArchiveError::new("hook_spool_root_invalid", detail))?;
    let root = boundary
        .resolve(root.strip_prefix(boundary.root()).unwrap_or(&root))
        .map_err(|detail| ArchiveError::new("hook_spool_root_invalid", detail))?;
    if !root.is_dir() {
        return Ok(Vec::new());
    }
    let mut files = Vec::new();
    for runtime in sorted_entries(&root)? {
        if !runtime
            .file_type()
            .map_err(|error| ArchiveError::new("hook_spool_snapshot_failed", error.to_string()))?
            .is_dir()
            || runtime
                .file_type()
                .map_err(|error| {
                    ArchiveError::new("hook_spool_snapshot_failed", error.to_string())
                })?
                .is_symlink()
        {
            continue;
        }
        for hook in sorted_entries(&runtime.path())? {
            let kind = hook.file_type().map_err(|error| {
                ArchiveError::new("hook_spool_snapshot_failed", error.to_string())
            })?;
            if !kind.is_dir() || kind.is_symlink() {
                continue;
            }
            for event in sorted_entries(&hook.path())? {
                let kind = event.file_type().map_err(|error| {
                    ArchiveError::new("hook_spool_snapshot_failed", error.to_string())
                })?;
                if kind.is_symlink()
                    || !kind.is_file()
                    || event.path().extension().is_none_or(|ext| ext != "json")
                {
                    continue;
                }
                files.push(event.path());
            }
        }
    }
    files.sort_by_key(|path| {
        path.strip_prefix(&root)
            .unwrap_or(path)
            .to_string_lossy()
            .replace('\\', "/")
    });
    let mut snapshot = Vec::with_capacity(files.len());
    for path in files {
        let relative = path
            .strip_prefix(boundary.root())
            .map_err(|_| error("hook_spool_event_invalid"))?;
        let bytes = boundary
            .read_bytes(relative)
            .map_err(|detail| ArchiveError::new("hook_spool_snapshot_changed", detail))?
            .ok_or_else(|| error("hook_spool_snapshot_changed"))?;
        let metadata = fs::symlink_metadata(&path).map_err(|detail| {
            ArchiveError::new("hook_spool_snapshot_changed", detail.to_string())
        })?;
        if !metadata.is_file()
            || metadata.file_type().is_symlink()
            || metadata.len() != bytes.len() as u64
        {
            return Err(error("hook_spool_snapshot_changed"));
        }
        snapshot.push(EventSnapshot {
            path,
            size: bytes.len() as u64,
            sha256: hash(&bytes),
        });
    }
    Ok(snapshot)
}

fn sorted_entries(path: &Path) -> Result<Vec<fs::DirEntry>, ArchiveError> {
    let mut entries = fs::read_dir(path)
        .map_err(|detail| ArchiveError::new("hook_spool_snapshot_failed", detail.to_string()))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|detail| ArchiveError::new("hook_spool_snapshot_failed", detail.to_string()))?;
    entries.sort_by_key(|entry| entry.file_name());
    Ok(entries)
}

fn valid_hex(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_oid(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_cursor(bytes: &[u8], repo_key: &str, index_bytes: &[u8]) -> Result<u64, ArchiveError> {
    let value: Value =
        serde_json::from_slice(bytes).map_err(|_| error("hook_spool_cursor_invalid"))?;
    let object = value
        .as_object()
        .ok_or_else(|| error("hook_spool_cursor_invalid_schema"))?;
    let expected = [
        "accepted_event_count",
        "archive_commit_oid",
        "cursor_body_sha256",
        "dedup_index_sha256",
        "duplicate_event_count",
        "failed_event_count",
        "generation",
        "prior_cursor_sha256",
        "repo_key",
        "schema",
        "schema_version",
        "source_event_count",
        "source_set_sha256",
        "transaction_id",
    ];
    if object.keys().map(String::as_str).ne(expected) {
        return Err(error("hook_spool_cursor_invalid_field_order"));
    }
    if canonical_compact_json(&value)? != bytes.strip_suffix(b"\n").unwrap_or(bytes) {
        return Err(error("hook_spool_cursor_invalid_canonical"));
    }
    if object.get("schema").and_then(Value::as_str) != Some(CURSOR_SCHEMA)
        || object.get("schema_version").and_then(Value::as_u64) != Some(1)
        || object.get("repo_key").and_then(Value::as_str) != Some(repo_key)
        || object.get("dedup_index_sha256").and_then(Value::as_str)
            != Some(hash(index_bytes).as_str())
    {
        return Err(error("hook_spool_checkpoint_inconsistent_certificate"));
    }
    let integers = [
        "accepted_event_count",
        "duplicate_event_count",
        "failed_event_count",
        "generation",
        "source_event_count",
    ];
    for field in integers {
        if object.get(field).and_then(Value::as_u64).is_none() {
            return Err(ArchiveError::new(
                "hook_spool_cursor_invalid_integer",
                field,
            ));
        }
    }
    let source_count = object["source_event_count"].as_u64().unwrap();
    let classified_count = object["accepted_event_count"].as_u64().unwrap()
        + object["duplicate_event_count"].as_u64().unwrap()
        + object["failed_event_count"].as_u64().unwrap();
    if source_count != classified_count {
        return Err(error("hook_spool_cursor_invalid_event_count"));
    }
    for field in [
        "cursor_body_sha256",
        "dedup_index_sha256",
        "prior_cursor_sha256",
        "source_set_sha256",
        "transaction_id",
    ] {
        if !object
            .get(field)
            .and_then(Value::as_str)
            .is_some_and(valid_hex)
        {
            return Err(ArchiveError::new("hook_spool_cursor_invalid_hash", field));
        }
    }
    let archive_oid = object["archive_commit_oid"]
        .as_str()
        .ok_or_else(|| error("hook_spool_cursor_invalid_archive_oid"))?;
    if !archive_oid.is_empty() && !valid_oid(archive_oid) {
        return Err(error("hook_spool_cursor_invalid_archive_oid"));
    }
    let body_hash = object["cursor_body_sha256"].as_str().unwrap();
    let mut body = value.clone();
    body.as_object_mut().unwrap().remove("cursor_body_sha256");
    if body_hash != hash(&canonical_compact_json(&body)?) {
        return Err(error("hook_spool_cursor_invalid_hash"));
    }
    object["generation"]
        .as_u64()
        .ok_or_else(|| error("hook_spool_cursor_invalid_generation"))
}

fn parse_event(bytes: &[u8]) -> Result<(Map<String, Value>, Vec<u8>), ArchiveError> {
    let value: Value =
        serde_json::from_slice(bytes).map_err(|_| error("hook_spool_event_invalid_json"))?;
    let Some(object) = value.as_object() else {
        return Err(error("hook_spool_event_invalid_schema"));
    };
    for field in [
        "hook_run_id",
        "timestamp",
        "payload_fingerprint",
        "status",
        "source_repo_key",
        "hook_log_namespace",
    ] {
        if !object
            .get(field)
            .and_then(Value::as_str)
            .is_some_and(|value| !value.trim().is_empty())
        {
            return Err(ArchiveError::new("hook_spool_event_invalid_field", field));
        }
    }
    let mut canonical = canonical_compact_json(&value)?;
    canonical.push(b'\n');
    if canonical != bytes {
        return Err(error("hook_spool_event_invalid_noncanonical"));
    }
    Ok((object.clone(), canonical))
}

fn parse_projection(bytes: &[u8]) -> Result<BTreeMap<String, String>, ArchiveError> {
    let mut identities = BTreeMap::new();
    for line in bytes.split_inclusive(|byte| *byte == b'\n') {
        if line.iter().all(u8::is_ascii_whitespace) {
            continue;
        }
        let (event, canonical) = parse_event(line)?;
        let id = event["hook_run_id"].as_str().unwrap_or_default().to_owned();
        let digest = hash(&canonical);
        if identities.get(&id).is_some_and(|prior| prior != &digest) {
            return Err(error("spool_conflict"));
        }
        identities.insert(id, digest);
    }
    Ok(identities)
}

fn parse_index(bytes: &[u8]) -> Result<BTreeMap<String, IndexEntry>, ArchiveError> {
    if !bytes.is_empty() && !bytes.ends_with(b"\n") {
        return Err(error("hook_spool_index_invalid_partial_row"));
    }
    let expected = [
        "event_id",
        "event_sha256",
        "hook_name",
        "projection_path",
        "runtime_namespace",
        "schema",
        "transaction_id",
    ];
    let mut entries = BTreeMap::new();
    for line in bytes
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
    {
        let value: Value =
            serde_json::from_slice(line).map_err(|_| error("hook_spool_index_invalid_json"))?;
        let Some(object) = value.as_object() else {
            return Err(error("hook_spool_index_invalid_schema"));
        };
        if object.keys().map(String::as_str).ne(expected) || canonical_compact_json(&value)? != line
        {
            return Err(error("hook_spool_index_invalid_canonical"));
        }
        if object.get("schema").and_then(Value::as_str) != Some(INDEX_SCHEMA) {
            return Err(error("hook_spool_index_invalid_schema"));
        }
        let string = |key: &str| {
            object
                .get(key)
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .map(str::to_owned)
                .ok_or_else(|| ArchiveError::new("hook_spool_index_invalid_field", key))
        };
        let id = string("event_id")?;
        let sha256 = string("event_sha256")?;
        if !valid_hex(&sha256) || entries.contains_key(&id) {
            return Err(error("hook_spool_index_invalid_identity"));
        }
        entries.insert(
            id,
            IndexEntry {
                sha256,
                namespace: string("runtime_namespace")?,
                hook_name: string("hook_name")?,
                projection: string("projection_path")?,
            },
        );
    }
    Ok(entries)
}

fn write_json_line(value: &Value) -> Result<Vec<u8>, ArchiveError> {
    let mut bytes = canonical_compact_json(value)?;
    bytes.push(b'\n');
    Ok(bytes)
}

pub(super) fn ingest(
    transaction: &PreparedArchiveTransaction,
    snapshot: Vec<EventSnapshot>,
) -> Result<IngestResult, ArchiveError> {
    let context = &transaction.context;
    let archive = RuntimeArtifactBoundary::for_source(
        &context.canon_root,
        Some(&context.archive_root),
        false,
    )
    .map_err(|detail| ArchiveError::new("archive_root_invalid", detail))?;
    let metadata_root = PathBuf::from("hook-runs").join(&context.repo_key);
    let index_relative = metadata_root.join(eval_archive_paths::HOOK_SPOOL_INDEX_NAME);
    let cursor_relative = metadata_root.join(CURSOR_NAME);
    let index_before =
        read(&archive, &index_relative, "hook_spool_index_invalid")?.unwrap_or_default();
    let index_present = archive
        .read_bytes(&index_relative)
        .map_err(|detail| ArchiveError::new("hook_spool_index_invalid", detail))?
        .is_some();
    let cursor_before =
        read(&archive, &cursor_relative, "hook_spool_cursor_invalid")?.unwrap_or_default();
    let index = parse_index(&index_before)?;
    if index_present != !cursor_before.is_empty() {
        return Err(error("hook_spool_checkpoint_inconsistent_index_cursor"));
    }
    let mut cursor_generation = 0_u64;
    if !cursor_before.is_empty() {
        cursor_generation = validate_cursor(&cursor_before, &context.repo_key, &index_before)?;
        for (id, row) in &index {
            let path = PathBuf::from(&row.projection);
            if path.is_absolute()
                || path
                    .components()
                    .any(|part| !matches!(part, std::path::Component::Normal(_)))
                || !path.starts_with(&metadata_root)
                || path.extension().is_none_or(|ext| ext != "jsonl")
            {
                return Err(error("hook_spool_checkpoint_inconsistent_projection_path"));
            }
            let bytes = read(
                &archive,
                &path,
                "hook_spool_checkpoint_inconsistent_projection_missing",
            )?
            .ok_or_else(|| error("hook_spool_checkpoint_inconsistent_projection_missing"))?;
            if parse_projection(&bytes)?.get(id) != Some(&row.sha256) {
                return Err(error(
                    "hook_spool_checkpoint_inconsistent_projection_mismatch",
                ));
            }
        }
    }

    let runtime_root = archive_runtime_root(context)?;
    let spool = RuntimeSpoolBoundary::for_source(&context.source_root, Some(&runtime_root), false)
        .map_err(|detail| ArchiveError::new("hook_spool_root_invalid", detail))?;
    let spool_root =
        eval_archive_paths::hook_event_spool_root(&context.source_root, Some(&runtime_root))
            .map_err(|detail| ArchiveError::new("hook_spool_root_invalid", detail))?;
    let head_key = eval_archive_paths::agent_canon_git_commit_key(&context.canon_root);
    let mut source_rows = Vec::new();
    let mut accepted = Vec::new();
    let mut duplicates = Vec::new();
    let mut pending = BTreeMap::<String, (String, String, String)>::new();
    let mut projection_bytes = BTreeMap::<PathBuf, Vec<u8>>::new();
    let mut projection_prior = BTreeMap::<PathBuf, Option<Vec<u8>>>::new();
    let mut projection_ids = BTreeMap::<PathBuf, BTreeMap<String, String>>::new();
    for event in &snapshot {
        let relative = event
            .path
            .strip_prefix(&spool_root)
            .map_err(|_| error("hook_spool_event_invalid_outside_root"))?;
        if relative.components().count() != 3
            || relative.extension().is_none_or(|ext| ext != "json")
        {
            return Err(error("hook_spool_event_invalid_path_shape"));
        }
        let mut components = relative.components();
        let namespace = components
            .next()
            .unwrap()
            .as_os_str()
            .to_string_lossy()
            .into_owned();
        let hook_name = components
            .next()
            .unwrap()
            .as_os_str()
            .to_string_lossy()
            .into_owned();
        let filename = components
            .next()
            .unwrap()
            .as_os_str()
            .to_string_lossy()
            .into_owned();
        let spool_relative = event
            .path
            .strip_prefix(spool.root())
            .map_err(|_| error("hook_spool_event_invalid_outside_root"))?;
        let payload = spool
            .read_bytes(spool_relative)
            .map_err(|detail| ArchiveError::new("hook_spool_snapshot_changed", detail))?
            .ok_or_else(|| error("hook_spool_snapshot_changed"))?;
        if payload.len() as u64 != event.size || hash(&payload) != event.sha256 {
            return Err(error("hook_spool_snapshot_changed"));
        }
        let (object, canonical) = parse_event(&payload)?;
        let id = object["hook_run_id"].as_str().unwrap().to_owned();
        let sha256 = hash(&canonical);
        if filename != format!("{id}.json") || sha256 != event.sha256 {
            return Err(error("hook_spool_event_invalid_identity"));
        }
        if object["source_repo_key"].as_str() != Some(context.repo_key.as_str()) {
            return Err(error("hook_spool_event_invalid_repo_key"));
        }
        if object["hook_log_namespace"].as_str() != Some(namespace.as_str()) {
            return Err(error("hook_spool_event_invalid_namespace"));
        }
        source_rows.push(json!([
            relative.to_string_lossy().replace('\\', "/"),
            sha256
        ]));
        if let Some(row) = index.get(&id) {
            if row.sha256 != sha256 || row.namespace != namespace || row.hook_name != hook_name {
                return Err(error("spool_conflict"));
            }
            duplicates.push(event.clone());
            continue;
        }
        if let Some(prior) = pending.get(&id) {
            if prior != &(sha256.clone(), namespace.clone(), hook_name.clone()) {
                return Err(error("spool_conflict"));
            }
            duplicates.push(event.clone());
            continue;
        }
        let projection = PathBuf::from("hook-runs")
            .join(&context.repo_key)
            .join(&namespace)
            .join(format!("{hook_name}-{head_key}.jsonl"));
        let ids = if let Some(ids) = projection_ids.get_mut(&projection) {
            ids
        } else {
            let prior = read(&archive, &projection, "hook_projection_invalid")?;
            let ids = parse_projection(prior.as_deref().unwrap_or_default())?;
            projection_prior.insert(projection.clone(), prior.clone());
            projection_bytes.insert(projection.clone(), prior.unwrap_or_default());
            projection_ids.insert(projection.clone(), ids);
            projection_ids.get_mut(&projection).unwrap()
        };
        if let Some(prior) = ids.get(&id) {
            if prior != &sha256 {
                return Err(error("spool_conflict"));
            }
        } else {
            projection_bytes
                .get_mut(&projection)
                .unwrap()
                .extend_from_slice(&canonical);
        }
        ids.insert(id.clone(), sha256.clone());
        pending.insert(id.clone(), (sha256, namespace.clone(), hook_name.clone()));
        accepted.push((event.clone(), id, namespace, hook_name, projection));
    }

    let source_set = canonical_compact_json(&Value::Array(source_rows))?;
    let source_set_sha256 = hash(&source_set);
    let prior_cursor_sha = if cursor_before.is_empty() {
        ZERO_SHA256.to_owned()
    } else {
        hash(&cursor_before)
    };
    let transaction_id = hash(&canonical_compact_json(&json!({
        "archive_head_before": transaction.archive_head_before,
        "prior_cursor_sha256": prior_cursor_sha,
        "repo_key": context.repo_key,
        "source_set_sha256": source_set_sha256,
    }))?);
    let mut index_after = index_before.clone();
    for (event, id, namespace, hook_name, projection) in &accepted {
        let relative = projection.to_string_lossy().replace('\\', "/");
        index_after.extend_from_slice(&write_json_line(&json!({
            "schema": INDEX_SCHEMA,
            "event_id": id,
            "event_sha256": event.sha256,
            "runtime_namespace": namespace,
            "hook_name": hook_name,
            "projection_path": relative,
            "transaction_id": transaction_id,
        }))?);
    }
    let index_sha256 = hash(&index_after);
    let mut cursor_after = cursor_before.clone();
    if !accepted.is_empty() {
        let mut cursor = json!({
            "schema": CURSOR_SCHEMA,
            "schema_version": 1,
            "repo_key": context.repo_key,
            "generation": cursor_generation + 1,
            "prior_cursor_sha256": prior_cursor_sha,
            "transaction_id": transaction_id,
            "source_event_count": snapshot.len(),
            "accepted_event_count": accepted.len(),
            "duplicate_event_count": duplicates.len(),
            "failed_event_count": 0,
            "source_set_sha256": source_set_sha256,
            "dedup_index_sha256": index_sha256,
            "archive_commit_oid": transaction.archive_head_before,
        });
        let body = canonical_compact_json(&cursor)?;
        cursor
            .as_object_mut()
            .unwrap()
            .insert("cursor_body_sha256".to_owned(), json!(hash(&body)));
        cursor_after = write_json_line(&cursor)?;
        let mut updates = projection_bytes;
        updates.insert(index_relative.clone(), index_after.clone());
        updates.insert(cursor_relative.clone(), cursor_after.clone());
        projection_prior.insert(
            index_relative.clone(),
            if index_present {
                Some(index_before.clone())
            } else {
                None
            },
        );
        projection_prior.insert(
            cursor_relative.clone(),
            if cursor_before.is_empty() {
                None
            } else {
                Some(cursor_before.clone())
            },
        );
        let mut touched = Vec::new();
        for (path, bytes) in updates {
            touched.push(path.clone());
            if let Err(detail) = archive.atomic_write_bytes(&path, &bytes, 0o600) {
                for changed in touched.into_iter().rev() {
                    let rollback = projection_prior.get(&changed).cloned().flatten();
                    let result = match rollback {
                        Some(prior) => archive
                            .atomic_write_bytes(&changed, &prior, 0o600)
                            .map(|_| ()),
                        None => archive.remove_file(&changed).map(|_| ()),
                    };
                    if result.is_err() {
                        return Err(error("hook_spool_recovery_failed"));
                    }
                }
                return Err(ArchiveError::new("hook_spool_ingest_failed", detail));
            }
        }
    }
    let observed_index = read(
        &archive,
        &index_relative,
        "hook_spool_checkpoint_inconsistent",
    )?
    .unwrap_or_default();
    let observed_cursor = read(
        &archive,
        &cursor_relative,
        "hook_spool_checkpoint_inconsistent",
    )?
    .unwrap_or_default();
    if observed_index != index_after || observed_cursor != cursor_after {
        return Err(error("hook_spool_checkpoint_inconsistent_write_readback"));
    }
    Ok(IngestResult {
        snapshot,
        accepted: accepted.into_iter().map(|item| item.0).collect(),
        duplicates,
        index_path: context.archive_root.join(index_relative),
        index_sha256,
        cursor_sha256: hash(&observed_cursor),
    })
}

pub(super) fn finalize(
    transaction: &PreparedArchiveTransaction,
    receipt: &ArchivePublicationReceipt,
    result: &IngestResult,
) -> Result<usize, ArchiveError> {
    if receipt.status != "committed" || !receipt.pushed {
        return Ok(0);
    }
    let covered = result
        .accepted
        .iter()
        .chain(&result.duplicates)
        .collect::<Vec<_>>();
    if covered.is_empty() {
        return Ok(0);
    }
    if receipt.archive_commit_oid.is_empty()
        || receipt.archive_tree_oid.is_empty()
        || receipt.dedup_index_sha256 != result.index_sha256
        || receipt.cursor_sha256 != result.cursor_sha256
    {
        return Err(error("archive_readback_mismatch"));
    }
    let context = &transaction.context;
    let index_relative = result
        .index_path
        .strip_prefix(&context.archive_root)
        .map_err(|_| error("archive_readback_mismatch"))?;
    let committed_index = archive_blob_at(context, &receipt.archive_commit_oid, index_relative)?;
    let entries = parse_index(&committed_index)?;
    let mut projection_cache = BTreeMap::<PathBuf, BTreeMap<String, String>>::new();
    for event in &covered {
        let event_id = event
            .path
            .file_stem()
            .and_then(|value| value.to_str())
            .ok_or_else(|| error("archive_readback_mismatch"))?;
        let indexed = entries
            .get(event_id)
            .ok_or_else(|| error("archive_readback_mismatch"))?;
        if indexed.sha256 != event.sha256 {
            return Err(error("archive_readback_mismatch"));
        }
        let projection = PathBuf::from(&indexed.projection);
        if !projection_cache.contains_key(&projection) {
            let bytes = archive_blob_at(context, &receipt.archive_commit_oid, &projection)?;
            projection_cache.insert(projection.clone(), parse_projection(&bytes)?);
        }
        if projection_cache
            .get(&projection)
            .and_then(|items| items.get(event_id))
            != Some(&event.sha256)
        {
            return Err(error("archive_readback_mismatch"));
        }
    }

    let runtime_root = archive_runtime_root(context)?;
    let spool = RuntimeSpoolBoundary::for_source(&context.source_root, Some(&runtime_root), false)
        .map_err(|detail| ArchiveError::new("hook_spool_root_invalid", detail))?;
    let mut removed = 0;
    for event in covered {
        let relative = event
            .path
            .strip_prefix(spool.root())
            .map_err(|_| error("hook_spool_event_invalid_outside_root"))?;
        let current = spool
            .read_bytes(relative)
            .map_err(|detail| ArchiveError::new("hook_spool_snapshot_changed", detail))?;
        let Some(current) = current else {
            continue;
        };
        if current.len() as u64 != event.size || hash(&current) != event.sha256 {
            continue;
        }
        if spool
            .remove_file(relative)
            .map_err(|detail| ArchiveError::new("hook_spool_finalize_failed", detail))?
        {
            removed += 1;
        }
    }
    Ok(removed)
}

#[cfg(test)]
mod tests {
    use super::{hash, parse_event, parse_index, parse_projection};
    use serde_json::json;

    #[test]
    fn hook_event_requires_canonical_jsonl_bytes_and_owned_fields() {
        let value = json!({
            "hook_run_id": "run-1",
            "timestamp": "2026-11-13T00:00:00Z",
            "payload_fingerprint": "fingerprint",
            "status": "pass",
            "source_repo_key": "repo-key",
            "hook_log_namespace": "test",
        });
        let mut bytes = serde_json::to_vec(&value).unwrap();
        bytes.push(b'\n');
        assert!(parse_event(&bytes).is_ok());
        assert!(parse_event(b"{\"hook_run_id\":\"run-1\"}").is_err());
        let mut noncanonical = serde_json::to_vec(&value).unwrap();
        noncanonical.extend_from_slice(b" \n");
        assert!(parse_event(&noncanonical).is_err());
    }

    #[test]
    fn projection_rejects_conflicting_event_id_and_index_requires_ordered_rows() {
        let event = |status: &str| {
            let value = json!({
                "hook_run_id": "run-1",
                "timestamp": "2026-11-13T00:00:00Z",
                "payload_fingerprint": "fingerprint",
                "status": status,
                "source_repo_key": "repo-key",
                "hook_log_namespace": "test",
            });
            let mut bytes = serde_json::to_vec(&value).unwrap();
            bytes.push(b'\n');
            bytes
        };
        let first = event("pass");
        assert!(parse_projection(&first).is_ok());
        let mut conflict = first.clone();
        conflict.extend_from_slice(&event("fail"));
        assert!(parse_projection(&conflict).is_err());
        assert_eq!(hash(&first).len(), 64);
        let index = json!({
            "event_id": "run-1",
            "event_sha256": "0".repeat(64),
            "hook_name": "SessionStart",
            "projection_path": "hook-runs/repo/test/SessionStart-head.jsonl",
            "runtime_namespace": "test",
            "schema": "agent_canon.hook_spool_index.v1",
            "transaction_id": "1".repeat(64),
        });
        let mut row = serde_json::to_vec(&index).unwrap();
        row.push(b'\n');
        assert_eq!(parse_index(&row).unwrap().len(), 1);
        assert!(parse_index(b"{}\n").is_err());
    }
}
