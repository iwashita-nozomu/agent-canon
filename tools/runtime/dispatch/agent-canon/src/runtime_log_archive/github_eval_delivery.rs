//! Bounded GitHub main-Eval artifact input for the existing host publisher.

use super::archive_runtime_root;
use super::{ArchiveContext, ArchiveError, CommandOptions, command_archive_eval};
use agent_canon::log_repository_identity::{normalize_remote, source_remote};
use agent_canon::runtime_boundary::{RuntimeArtifactBoundary, RuntimeSpoolBoundary};
use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt};
use cap_std::ambient_authority;
use cap_std::fs::{Dir, OpenOptions};
use flate2::read::DeflateDecoder;
use rawzip::{CompressionMethod, ZipArchive as RawZipArchive, ZipArchiveEntryWayfinder};
use serde_json::Value;
use sha2::Digest;
use std::collections::BTreeSet;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::OnceLock;

const WORKFLOW_PATH: &str = ".github/workflows/agent-canon-static-gates.yml";
const CHUNK_BYTES: usize = 64 * 1024;
const ZIP_MEMBER_METADATA_BYTES: u64 = 3 * (u16::MAX as u64) + 64;

#[derive(Clone, Copy)]
pub(super) struct EvalArtifactLimits {
    artifact_bytes: u64,
    entry_bytes: u64,
    runtime_bytes: u64,
    members: u64,
}

impl EvalArtifactLimits {
    pub(super) fn from_manifest(path: &Path) -> Result<Self, ArchiveError> {
        let bytes = super::read_file_nofollow(path)
            .map_err(|_| ArchiveError::new("github_eval_limits_invalid", ""))?;
        let text = std::str::from_utf8(&bytes)
            .map_err(|_| ArchiveError::new("github_eval_limits_invalid", ""))?;
        let manifest = text
            .parse::<toml_edit::DocumentMut>()
            .map_err(|_| ArchiveError::new("github_eval_limits_invalid", ""))?;
        let container = manifest
            .get("container")
            .and_then(toml_edit::Item::as_table)
            .ok_or_else(|| ArchiveError::new("github_eval_limits_invalid", ""))?;
        let archive = manifest
            .get("archive")
            .and_then(toml_edit::Item::as_table)
            .ok_or_else(|| ArchiveError::new("github_eval_limits_invalid", ""))?;
        Ok(Self {
            artifact_bytes: positive_limit(container, "task_state_quota_bytes")?,
            entry_bytes: positive_limit(container, "task_log_quota_bytes")?,
            runtime_bytes: positive_limit(container, "runtime_quota_bytes")?,
            members: positive_limit(archive, "main_eval_max_members")?,
        })
    }
}

fn positive_limit(table: &toml_edit::Table, key: &str) -> Result<u64, ArchiveError> {
    table
        .get(key)
        .and_then(toml_edit::Item::as_integer)
        .filter(|value| *value > 0)
        .map(|value| value as u64)
        .ok_or_else(|| ArchiveError::new("github_eval_limits_invalid", key))
}

fn github_error(code: &str) -> ArchiveError {
    ArchiveError::new(code, "")
}

fn github_json(endpoint: &str, source_root: &Path) -> Result<Value, ArchiveError> {
    let output = Command::new("gh")
        .args(["api", "--hostname", "github.com", endpoint])
        .current_dir(source_root)
        .output()
        .map_err(|_| github_error("github_eval_transport_unavailable"))?;
    if !output.status.success() {
        return Err(ArchiveError::new(
            "github_eval_metadata_unavailable",
            endpoint.to_owned(),
        ));
    }
    let value: Value = serde_json::from_slice(&output.stdout)
        .map_err(|_| github_error("github_eval_metadata_invalid"))?;
    if !value.is_object() {
        return Err(github_error("github_eval_json_object_required"));
    }
    Ok(value)
}

fn download(
    endpoint: &str,
    destination: &Path,
    source_root: &Path,
    maximum: u64,
    boundary: &RuntimeArtifactBoundary,
) -> Result<(), ArchiveError> {
    let destination = boundary
        .resolve(destination)
        .map_err(|error| ArchiveError::new("github_eval_download_unavailable", error))?;
    let parent = destination
        .parent()
        .ok_or_else(|| github_error("github_eval_download_unavailable"))?;
    let relative_parent = parent
        .strip_prefix(boundary.root())
        .map_err(|_| github_error("github_eval_download_unavailable"))?;
    let root = Dir::open_ambient_dir(boundary.root(), ambient_authority())
        .map_err(|_| github_error("github_eval_download_unavailable"))?;
    let mut directory = root;
    for component in relative_parent.components() {
        let Component::Normal(name) = component else {
            return Err(github_error("github_eval_download_unavailable"));
        };
        directory = directory
            .open_dir_nofollow(name)
            .map_err(|_| github_error("github_eval_download_unavailable"))?;
    }
    let filename = destination
        .file_name()
        .ok_or_else(|| github_error("github_eval_download_unavailable"))?;
    let mut options = OpenOptions::new();
    options
        .write(true)
        .create(true)
        .truncate(true)
        .follow(FollowSymlinks::No);
    #[cfg(unix)]
    {
        use cap_std::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut target = directory
        .open_with(filename, &options)
        .map_err(|_| github_error("github_eval_download_unavailable"))?;
    let mut child = Command::new("gh")
        .args(["api", "--hostname", "github.com", endpoint])
        .current_dir(source_root)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| github_error("github_eval_download_unavailable"))?;
    let mut total = 0_u64;
    let mut block = vec![0; CHUNK_BYTES];
    let mut result = Ok(());
    if let Some(mut stdout) = child.stdout.take() {
        loop {
            let count = match stdout.read(&mut block) {
                Ok(0) => break,
                Ok(count) => count,
                Err(_) => {
                    result = Err(github_error("github_eval_download_failed"));
                    break;
                }
            };
            total = total.saturating_add(count as u64);
            if total > maximum {
                result = Err(github_error("github_eval_download_quota_exceeded"));
                let _ = child.kill();
                break;
            }
            if target.write_all(&block[..count]).is_err() {
                result = Err(github_error("github_eval_download_failed"));
                let _ = child.kill();
                break;
            }
        }
    } else {
        result = Err(github_error("github_eval_download_unavailable"));
        let _ = child.kill();
    }
    let status = child
        .wait()
        .map_err(|_| github_error("github_eval_download_failed"))?;
    target
        .sync_all()
        .map_err(|_| github_error("github_eval_download_failed"))?;
    result?;
    if !status.success() {
        return Err(ArchiveError::new(
            "github_eval_download_failed",
            endpoint.to_owned(),
        ));
    }
    Ok(())
}

fn sha256_file(path: &Path, boundary: &RuntimeArtifactBoundary) -> Result<String, ArchiveError> {
    let path = boundary
        .resolve(path)
        .map_err(|_| github_error("github_eval_artifact_read_failed"))?;
    let mut file = super::open_file_nofollow(&path)
        .map_err(|_| github_error("github_eval_artifact_read_failed"))?;
    let mut digest = sha2::Sha256::new();
    let mut block = vec![0; CHUNK_BYTES];
    loop {
        let count = file
            .read(&mut block)
            .map_err(|_| github_error("github_eval_artifact_read_failed"))?;
        if count == 0 {
            break;
        }
        sha2::Digest::update(&mut digest, &block[..count]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn directory_bytes(path: &Path) -> Result<u64, ArchiveError> {
    let mut stack = vec![path.to_path_buf()];
    let mut total = 0_u64;
    while let Some(directory) = stack.pop() {
        let entries = match fs::read_dir(&directory) {
            Ok(entries) => entries,
            Err(error) if error.kind() == io::ErrorKind::NotFound => continue,
            Err(error) => {
                return Err(ArchiveError::new(
                    "github_eval_runtime_read_failed",
                    error.to_string(),
                ));
            }
        };
        for entry in entries {
            let entry = entry.map_err(|error| {
                ArchiveError::new("github_eval_runtime_read_failed", error.to_string())
            })?;
            let metadata = fs::symlink_metadata(entry.path()).map_err(|error| {
                ArchiveError::new("github_eval_runtime_read_failed", error.to_string())
            })?;
            if metadata.file_type().is_symlink() {
                continue;
            }
            if metadata.is_dir() {
                stack.push(entry.path());
            } else if metadata.is_file() {
                total = total.saturating_add(metadata.len());
            }
        }
    }
    Ok(total)
}

#[derive(Clone)]
struct ZipMember {
    wayfinder: ZipArchiveEntryWayfinder,
    name: String,
    header_name: String,
    is_directory: bool,
    size: u64,
    method: CompressionMethod,
    flags: u16,
    local_offset: u64,
    next_header_offset: u64,
}

fn normalized_member_path(name: &str) -> Result<(String, Vec<String>), ArchiveError> {
    if name.is_empty()
        || name.contains('\0')
        || name.contains('\\')
        || name.starts_with('/')
        || name.as_bytes().get(1) == Some(&b':') && name.as_bytes()[0].is_ascii_alphabetic()
    {
        return Err(github_error("github_eval_artifact_path_invalid"));
    }
    let mut parts = Vec::new();
    for part in name.split('/') {
        match part {
            "" | "." => {}
            ".." => return Err(github_error("github_eval_artifact_path_invalid")),
            part => parts.push(part.to_owned()),
        }
    }
    if parts.is_empty() {
        return Err(github_error("github_eval_artifact_path_invalid"));
    }
    let normalized = parts.join("/");
    if normalized != "collection.json"
        && !matches!(
            parts.first().map(String::as_str),
            Some("eval-results" | "producer-logs")
        )
    {
        return Err(github_error("github_eval_artifact_path_invalid"));
    }
    if normalized != "collection.json" && parts.len() < 2 && !name.ends_with('/') {
        return Err(github_error("github_eval_artifact_path_invalid"));
    }
    Ok((normalized, parts))
}

fn extract_archive(
    archive_path: &Path,
    destination: &Path,
    limits: EvalArtifactLimits,
    boundary: &RuntimeArtifactBoundary,
) -> Result<(), ArchiveError> {
    let archive_path = boundary
        .resolve(archive_path)
        .map_err(|_| github_error("github_eval_zip_invalid"))?;
    let metadata =
        fs::symlink_metadata(&archive_path).map_err(|_| github_error("github_eval_zip_invalid"))?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > limits.artifact_bytes
    {
        return Err(github_error("github_eval_archive_quota_exceeded"));
    }
    let file = super::open_file_nofollow(&archive_path)
        .map_err(|_| github_error("github_eval_zip_invalid"))?;
    let mut buffer = vec![0; rawzip::RECOMMENDED_BUFFER_SIZE];
    let archive = RawZipArchive::from_seekable(file, &mut buffer)
        .map_err(|_| github_error("github_eval_zip_invalid"))?;
    let directory_offset = archive.directory_offset();
    let metadata_limit = limits.entry_bytes.min(
        limits
            .members
            .saturating_add(1)
            .saturating_mul(ZIP_MEMBER_METADATA_BYTES),
    );
    if directory_offset > metadata.len() || metadata.len() - directory_offset > metadata_limit {
        return Err(github_error("github_eval_metadata_quota_exceeded"));
    }
    let mut entries = archive.entries(&mut buffer);
    let mut members = Vec::new();
    let mut names = BTreeSet::new();
    let mut expanded = 0_u64;
    let mut metadata_used = 0_u64;
    while let Some(entry) = entries
        .next_entry()
        .map_err(|_| github_error("github_eval_zip_invalid"))?
    {
        if members.len() as u64 >= limits.members {
            return Err(github_error("github_eval_member_quota_exceeded"));
        }
        let header_name = agent_canon::extract_docx::decode_zip_member_name(
            entry.file_path().as_ref(),
            entry.flags().is_utf8(),
        )
        .map_err(|_| github_error("github_eval_artifact_path_invalid"))?;
        let (name, _) = normalized_member_path(&header_name)?;
        if !names.insert(name.clone()) {
            return Err(github_error("github_eval_duplicate_member"));
        }
        metadata_used = metadata_used.saturating_add(header_name.len() as u64 + 64);
        if metadata_used > metadata_limit {
            return Err(github_error("github_eval_metadata_quota_exceeded"));
        }
        let mode = (entry.external_attributes() >> 16) & 0o170000;
        if mode == 0o120000 || (mode != 0 && !matches!(mode, 0o100000 | 0o040000)) {
            return Err(github_error("github_eval_artifact_type_invalid"));
        }
        if entry.flags().bits() & 1 != 0 {
            return Err(github_error("github_eval_encrypted_member"));
        }
        let method = entry.compression_method();
        if !matches!(
            method,
            CompressionMethod::STORE | CompressionMethod::DEFLATE
        ) {
            return Err(github_error("github_eval_unsupported_compression"));
        }
        let size = entry.uncompressed_size_hint();
        if size > limits.entry_bytes {
            return Err(github_error("github_eval_entry_quota_exceeded"));
        }
        expanded = expanded.saturating_add(size);
        if expanded > limits.artifact_bytes {
            return Err(github_error("github_eval_expansion_quota_exceeded"));
        }
        members.push(ZipMember {
            wayfinder: entry.wayfinder(),
            name: name.clone(),
            header_name,
            is_directory: entry.file_path().as_ref().last() == Some(&b'/'),
            size,
            method,
            flags: entry.flags().bits(),
            local_offset: entry.local_header_offset(),
            next_header_offset: directory_offset,
        });
    }
    let mut physical_order = (0..members.len()).collect::<Vec<_>>();
    physical_order.sort_by_key(|index| std::cmp::Reverse(members[*index].local_offset));
    let mut next_header_offset = directory_offset;
    for index in physical_order {
        members[index].next_header_offset = next_header_offset;
        next_header_offset = members[index].local_offset;
    }
    let files = members
        .iter()
        .filter(|member| !member.is_directory)
        .map(|member| member.name.clone())
        .collect::<BTreeSet<_>>();
    let destination = boundary
        .resolve(destination)
        .map_err(|_| github_error("github_eval_stage_invalid"))?;
    let spool_before = if destination.exists() {
        let mut pending = vec![destination.clone()];
        let mut existing = BTreeSet::new();
        while let Some(directory) = pending.pop() {
            let entries =
                fs::read_dir(&directory).map_err(|_| github_error("github_eval_stage_changed"))?;
            for entry in entries {
                let entry = entry.map_err(|_| github_error("github_eval_stage_changed"))?;
                let path = entry.path();
                let metadata = fs::symlink_metadata(&path)
                    .map_err(|_| github_error("github_eval_stage_changed"))?;
                if metadata.file_type().is_symlink() {
                    return Err(github_error("github_eval_artifact_type_invalid"));
                }
                if metadata.is_dir() {
                    pending.push(path);
                } else if metadata.is_file() {
                    let relative = path
                        .strip_prefix(&destination)
                        .map_err(|_| github_error("github_eval_stage_changed"))?
                        .to_str()
                        .ok_or_else(|| github_error("github_eval_artifact_path_invalid"))?
                        .replace('\\', "/");
                    if !files.contains(&relative) {
                        return Err(github_error("github_eval_stage_changed"));
                    }
                    existing.insert(relative);
                }
            }
        }
        existing
    } else {
        let relative = destination
            .strip_prefix(boundary.root())
            .map_err(|_| github_error("github_eval_stage_invalid"))?;
        boundary
            .ensure_directory(relative)
            .map_err(|_| github_error("github_eval_stage_invalid"))?;
        BTreeSet::new()
    };
    let temp_path = destination
        .parent()
        .unwrap_or(&destination)
        .join("entry.part");
    let temp_bytes = match fs::symlink_metadata(&temp_path) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
            return Err(github_error("github_eval_stage_changed"));
        }
        Ok(metadata) => metadata.len(),
        Err(error) if error.kind() == io::ErrorKind::NotFound => 0,
        Err(_) => return Err(github_error("github_eval_stage_changed")),
    };
    let used = directory_bytes(boundary.root())?;
    let existing_bytes = directory_bytes(&destination)?;
    let required = used
        .saturating_sub(existing_bytes)
        .saturating_sub(temp_bytes)
        .saturating_add(expanded);
    if required > limits.runtime_bytes && required > used {
        return Err(github_error("github_eval_runtime_quota_exceeded"));
    }
    for member in members {
        if member.is_directory {
            let path = destination.join(&member.name);
            let relative = path
                .strip_prefix(boundary.root())
                .map_err(|_| github_error("github_eval_stage_invalid"))?;
            boundary
                .ensure_directory(relative)
                .map_err(|_| github_error("github_eval_stage_invalid"))?;
            continue;
        }
        let target = destination.join(&member.name);
        let relative = target
            .strip_prefix(boundary.root())
            .map_err(|_| github_error("github_eval_stage_invalid"))?;
        let bytes = zip_member_bytes(&archive, &member, limits.entry_bytes)?;
        if spool_before.contains(&member.name) {
            let existing = boundary
                .read_bytes(relative)
                .map_err(|_| github_error("github_eval_stage_changed"))?
                .ok_or_else(|| github_error("github_eval_stage_changed"))?;
            if existing != bytes {
                return Err(github_error("github_eval_stage_changed"));
            }
            continue;
        }
        boundary
            .write_once_bytes(relative, &bytes)
            .map_err(|_| github_error("github_eval_stage_changed"))?;
    }
    Ok(())
}

fn zip_member_bytes(
    archive: &RawZipArchive<fs::File>,
    member: &ZipMember,
    maximum: u64,
) -> Result<Vec<u8>, ArchiveError> {
    let entry = archive
        .get_entry(member.wayfinder)
        .map_err(|_| github_error("github_eval_zip_invalid"))?;
    let mut local_header_buffer = vec![0; u16::MAX as usize * 2];
    let local_header = entry
        .local_header(&mut local_header_buffer)
        .map_err(|_| github_error("github_eval_zip_invalid"))?;
    let local_name = agent_canon::extract_docx::decode_zip_member_name(
        local_header.file_path().as_ref(),
        local_header.flags().is_utf8(),
    )
    .map_err(|_| github_error("github_eval_zip_invalid"))?;
    if local_name != member.header_name {
        return Err(github_error("github_eval_zip_invalid"));
    }
    let (compressed_start, compressed_end) = entry.compressed_data_range();
    if compressed_start < member.local_offset
        || compressed_end < compressed_start
        || compressed_end > member.next_header_offset
        || member.flags & 1 != 0
    {
        return Err(github_error("github_eval_zip_invalid"));
    }
    let decoder: Box<dyn Read> = match member.method {
        CompressionMethod::STORE => Box::new(entry.reader()),
        CompressionMethod::DEFLATE => Box::new(DeflateDecoder::new(entry.reader())),
        _ => return Err(github_error("github_eval_unsupported_compression")),
    };
    let mut reader = entry.verifying_reader(decoder);
    let mut output = Vec::with_capacity(member.size.min(maximum).min(1024 * 1024) as usize);
    let mut block = vec![0; CHUNK_BYTES];
    let mut total = 0_u64;
    loop {
        let count = reader
            .read(&mut block)
            .map_err(|_| github_error("github_eval_zip_invalid"))?;
        if count == 0 {
            break;
        }
        total = total.saturating_add(count as u64);
        if total > member.size || total > maximum {
            return Err(github_error("github_eval_entry_quota_exceeded"));
        }
        output.extend_from_slice(&block[..count]);
    }
    if total != member.size {
        return Err(github_error("github_eval_entry_size_mismatch"));
    }
    Ok(output)
}

fn collection_complete(
    spool: &Path,
    run_id: &str,
    head: &str,
    boundary: &RuntimeArtifactBoundary,
) -> Result<(), ArchiveError> {
    let bytes = super::read_boundary_file(
        boundary,
        &spool.join("collection.json"),
        "github_eval_collection_invalid",
    )?;
    let collection: Value = serde_json::from_slice(&bytes)
        .map_err(|_| github_error("github_eval_collection_invalid"))?;
    let tree_digest = collection
        .get("source_tree_digest_before")
        .and_then(Value::as_str);
    if collection.get("schema").and_then(Value::as_str) != Some("agent_canon.eval_collection.v1")
        || collection.get("run_id").and_then(Value::as_str) != Some(run_id)
        || collection.get("status").and_then(Value::as_str) != Some("collected")
        || collection
            .get("source_tree_unchanged")
            .and_then(Value::as_bool)
            != Some(true)
        || [
            "source_head_before",
            "source_head_after",
            "agent_canon_commit",
        ]
        .iter()
        .any(|key| collection.get(*key).and_then(Value::as_str) != Some(head))
        || ["source_git_status_before", "source_git_status_after"]
            .iter()
            .any(|key| collection.get(*key).and_then(Value::as_str) != Some(""))
        || tree_digest.is_none_or(|value| !is_hex(value, 64))
        || tree_digest
            != collection
                .get("source_tree_digest_after")
                .and_then(Value::as_str)
    {
        return Err(github_error("github_eval_collection_source_mismatch"));
    }
    let families = collection
        .get("family_status")
        .and_then(Value::as_object)
        .ok_or_else(|| github_error("github_eval_collection_failed_family"))?;
    if families.is_empty()
        || families
            .values()
            .any(|value| value.as_str() != Some("pass"))
    {
        return Err(github_error("github_eval_collection_failed_family"));
    }
    let matrix = collection
        .get("producer_matrix")
        .and_then(Value::as_array)
        .ok_or_else(|| github_error("github_eval_collection_matrix_mismatch"))?;
    if matrix.len() != families.len() {
        return Err(github_error("github_eval_collection_matrix_mismatch"));
    }
    let mut observed = BTreeMap::new();
    for row in matrix {
        let row = row
            .as_object()
            .ok_or_else(|| github_error("github_eval_collection_matrix_mismatch"))?;
        let name = row
            .get("name")
            .and_then(Value::as_str)
            .ok_or_else(|| github_error("github_eval_collection_matrix_mismatch"))?;
        if row.get("exit").and_then(Value::as_i64) != Some(0)
            || row.get("status").and_then(Value::as_str) != Some("pass")
            || observed
                .insert(name.to_owned(), Value::String("pass".to_owned()))
                .is_some()
        {
            return Err(github_error("github_eval_collection_matrix_mismatch"));
        }
    }
    if observed.len() != families.len() || families.keys().any(|key| !observed.contains_key(key)) {
        return Err(github_error("github_eval_collection_matrix_mismatch"));
    }
    let exported = collection
        .get("exported_files")
        .and_then(Value::as_object)
        .ok_or_else(|| github_error("github_eval_collection_incomplete"))?;
    for (directory, key) in [
        ("eval-results", "eval_results"),
        ("producer-logs", "producer_logs"),
    ] {
        let root = boundary
            .resolve(&spool.join(directory))
            .map_err(|_| github_error("github_eval_collection_incomplete"))?;
        let mut count = 0_u64;
        let mut pending = vec![root];
        while let Some(directory) = pending.pop() {
            let entries = fs::read_dir(&directory)
                .map_err(|_| github_error("github_eval_collection_incomplete"))?;
            for entry in entries {
                let path = entry
                    .map_err(|_| github_error("github_eval_collection_incomplete"))?
                    .path();
                let metadata = fs::symlink_metadata(&path)
                    .map_err(|_| github_error("github_eval_collection_incomplete"))?;
                if metadata.file_type().is_symlink() {
                    return Err(github_error("github_eval_artifact_type_invalid"));
                }
                if metadata.is_dir() {
                    pending.push(path);
                } else if metadata.is_file() {
                    count += 1;
                }
            }
        }
        if count == 0 || exported.get(key).and_then(Value::as_u64) != Some(count) {
            return Err(github_error("github_eval_collection_incomplete"));
        }
    }
    Ok(())
}

fn is_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

pub(super) fn deliver_main_evals(
    context: &ArchiveContext,
    published_run_ids: &mut BTreeSet<String>,
    no_pull: bool,
) -> Result<usize, ArchiveError> {
    let runtime_root = archive_runtime_root(context)?;
    let remote = source_remote(&context.source_root).map_err(|error| {
        ArchiveError::new("source_identity_preflight_failed", error.to_string())
    })?;
    let identity = normalize_remote(&remote).map_err(|error| {
        ArchiveError::new("source_identity_preflight_failed", error.to_string())
    })?;
    let Some(repository) = identity.strip_prefix("github.com/") else {
        return Ok(0);
    };
    let limits = EvalArtifactLimits::from_manifest(
        &context.canon_root.join("bootstrap/host/manifest.toml"),
    )?;
    let boundary =
        RuntimeSpoolBoundary::for_source(&context.source_root, Some(&runtime_root), true)
            .map_err(|error| ArchiveError::new("github_eval_runtime_root_invalid", error))?;
    let stage_root = Path::new("spool/github-main-evals");
    boundary
        .ensure_directory(stage_root)
        .map_err(|error| ArchiveError::new("github_eval_stage_invalid", error))?;
    let _lock = boundary
        .lock_with_empty_marker(Path::new("locks/github-main-evals.lock"))
        .map_err(|_| github_error("github_eval_delivery_busy"))?;
    let stage_root_absolute = boundary.root().join(stage_root);
    for previous in fs::read_dir(&stage_root_absolute)
        .map_err(|error| ArchiveError::new("github_eval_stage_invalid", error.to_string()))?
    {
        let previous = previous
            .map_err(|error| ArchiveError::new("github_eval_stage_invalid", error.to_string()))?;
        let name = previous.file_name().to_string_lossy().into_owned();
        if stage_run_id(&name).is_some_and(|run_id| published_run_ids.contains(&run_id)) {
            remove_stage_directory(&boundary, &previous.path())?;
        }
    }
    let repository_value = github_json(&format!("repos/{repository}"), &context.source_root)?;
    let repo_id = repository_value
        .get("id")
        .and_then(Value::as_i64)
        .filter(|value| *value > 0)
        .ok_or_else(|| github_error("github_eval_repository_invalid"))?;
    let workflow = github_json(
        &format!("repos/{repository}/actions/workflows/{WORKFLOW_PATH}"),
        &context.source_root,
    )?;
    let workflow_id = workflow
        .get("id")
        .and_then(Value::as_i64)
        .ok_or_else(|| github_error("github_eval_workflow_mismatch"))?;
    if workflow.get("path").and_then(Value::as_str) != Some(WORKFLOW_PATH) {
        return Err(github_error("github_eval_workflow_mismatch"));
    }
    let mut page = 1_u64;
    let mut delivered = 0_usize;
    let mut failures = Vec::new();
    loop {
        let listing = github_json(
            &format!("repos/{repository}/actions/artifacts?per_page=100&page={page}"),
            &context.source_root,
        )?;
        let artifacts = listing
            .get("artifacts")
            .and_then(Value::as_array)
            .ok_or_else(|| github_error("github_eval_artifact_listing_invalid"))?;
        for artifact in artifacts {
            let Some(object) = artifact.as_object() else {
                continue;
            };
            let Some(name) = object.get("name").and_then(Value::as_str) else {
                continue;
            };
            let Some((run_number, attempt)) = artifact_name(name) else {
                continue;
            };
            let summary = object
                .get("workflow_run")
                .and_then(Value::as_object)
                .ok_or_else(|| github_error("github_eval_artifact_listing_invalid"))?;
            let head = summary
                .get("head_sha")
                .and_then(Value::as_str)
                .unwrap_or("");
            if summary.get("repository_id").and_then(Value::as_i64) != Some(repo_id)
                || summary.get("head_repository_id").and_then(Value::as_i64) != Some(repo_id)
                || summary.get("head_branch").and_then(Value::as_str) != Some("main")
            {
                continue;
            }
            if !is_hex(head, 40) {
                return Err(github_error("github_eval_head_invalid"));
            }
            let run_id = format!("main-{head}-{run_number}-{attempt}");
            if published_run_ids.contains(&run_id) {
                continue;
            }
            let process = github_json(
                &format!("repos/{repository}/actions/runs/{run_number}/attempts/{attempt}"),
                &context.source_root,
            );
            let run = match process {
                Ok(run) => run,
                Err(error) => {
                    failures.push(format!("{run_id}:{}", error.code));
                    continue;
                }
            };
            if run.get("event").and_then(Value::as_str) != Some("push")
                || run.get("head_branch").and_then(Value::as_str) != Some("main")
                || run.get("path").and_then(Value::as_str) != Some(WORKFLOW_PATH)
                || run.get("workflow_id").and_then(Value::as_i64) != Some(workflow_id)
                || run
                    .get("repository")
                    .and_then(|value| value.get("id"))
                    .and_then(Value::as_i64)
                    != Some(repo_id)
                || run
                    .get("head_repository")
                    .and_then(|value| value.get("id"))
                    .and_then(Value::as_i64)
                    != Some(repo_id)
                || run.get("status").and_then(Value::as_str) != Some("completed")
            {
                continue;
            }
            if summary.get("id").and_then(Value::as_i64) != Some(run_number as i64)
                || run.get("id").and_then(Value::as_i64) != Some(run_number as i64)
                || run.get("run_attempt").and_then(Value::as_i64) != Some(attempt as i64)
                || run.get("head_sha").and_then(Value::as_str) != Some(head)
            {
                failures.push(format!("{run_id}:github_eval_run_mismatch"));
                continue;
            }
            match deliver_one_artifact(
                context,
                repository,
                &boundary,
                &stage_root_absolute,
                &run_id,
                head,
                object,
                limits,
                no_pull,
            ) {
                Ok(true) => {
                    published_run_ids.insert(run_id);
                    delivered += 1;
                }
                Ok(false) => {}
                Err(error) => {
                    println!(
                        "RUNTIME_LOG_ARCHIVE_MAIN_EVAL_PENDING={run_id}:{}",
                        error.code
                    );
                    failures.push(format!("{run_id}:{}", error.code));
                }
            }
        }
        if artifacts.len() < 100 {
            break;
        }
        page += 1;
    }
    if let Some(first) = failures.first() {
        return Err(ArchiveError::new(
            "github_eval_delivery_pending",
            format!("{}:{first}", failures.len()),
        ));
    }
    Ok(delivered)
}

fn stage_run_id(name: &str) -> Option<String> {
    static NAME: OnceLock<regex::Regex> = OnceLock::new();
    let regex = NAME.get_or_init(|| {
        regex::Regex::new(r"^(main-[0-9a-f]{40}-[1-9][0-9]*-[1-9][0-9]*)-[1-9][0-9]*$")
            .expect("static stage name regex")
    });
    regex
        .captures(name)?
        .get(1)
        .map(|value| value.as_str().to_owned())
}

fn artifact_name(name: &str) -> Option<(u64, u64)> {
    static NAME: OnceLock<regex::Regex> = OnceLock::new();
    let regex = NAME.get_or_init(|| {
        regex::Regex::new(r"^agent-canon-main-eval-([1-9][0-9]*)-([1-9][0-9]*)$")
            .expect("static artifact name regex")
    });
    let captures = regex.captures(name)?;
    Some((
        captures.get(1)?.as_str().parse().ok()?,
        captures.get(2)?.as_str().parse().ok()?,
    ))
}

fn remove_stage_directory(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
) -> Result<(), ArchiveError> {
    let path = boundary
        .resolve(path)
        .map_err(|_| github_error("github_eval_stage_invalid"))?;
    match fs::symlink_metadata(&path) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(ArchiveError::new(
            "github_eval_stage_cleanup_failed",
            error.to_string(),
        )),
        Ok(metadata) if metadata.file_type().is_symlink() => {
            Err(github_error("github_eval_stage_cleanup_failed"))
        }
        Ok(metadata) if metadata.is_dir() => fs::remove_dir_all(&path).map_err(|error| {
            ArchiveError::new("github_eval_stage_cleanup_failed", error.to_string())
        }),
        Ok(_) => Err(github_error("github_eval_stage_cleanup_failed")),
    }
}

fn deliver_one_artifact(
    context: &ArchiveContext,
    repository: &str,
    boundary: &RuntimeArtifactBoundary,
    stage_root: &Path,
    run_id: &str,
    head: &str,
    artifact: &serde_json::Map<String, Value>,
    limits: EvalArtifactLimits,
    no_pull: bool,
) -> Result<bool, ArchiveError> {
    let artifact_id = artifact
        .get("id")
        .and_then(Value::as_i64)
        .filter(|value| *value > 0)
        .ok_or_else(|| github_error("github_eval_artifact_id_invalid"))?;
    let size = artifact
        .get("size_in_bytes")
        .and_then(Value::as_i64)
        .filter(|value| *value > 0)
        .ok_or_else(|| github_error("github_eval_archive_quota_exceeded"))? as u64;
    if size > limits.artifact_bytes {
        return Err(github_error("github_eval_archive_quota_exceeded"));
    }
    let digest = artifact
        .get("digest")
        .and_then(Value::as_str)
        .filter(|value| {
            value
                .strip_prefix("sha256:")
                .is_some_and(|value| is_hex(value, 64))
        })
        .ok_or_else(|| github_error("github_eval_artifact_digest_missing"))?
        .to_owned();
    let stage_name = format!("{run_id}-{artifact_id}");
    let stage_relative = stage_root.join(&stage_name);
    let stage = boundary
        .ensure_directory(&stage_relative)
        .map_err(|error| ArchiveError::new("github_eval_stage_invalid", error))?;
    let archive_relative = stage_relative.join("artifact.zip");
    let partial_relative = stage_relative.join("artifact.zip.part");
    let archive = boundary
        .resolve(&archive_relative)
        .map_err(|_| github_error("github_eval_stage_invalid"))?;
    let partial = boundary
        .resolve(&partial_relative)
        .map_err(|_| github_error("github_eval_stage_invalid"))?;
    if let Ok(metadata) = fs::symlink_metadata(&partial) {
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(github_error("github_eval_stage_changed"));
        }
        if metadata.len() > limits.artifact_bytes {
            return Err(github_error("github_eval_archive_quota_exceeded"));
        }
    }
    if !archive.exists()
        && partial.is_file()
        && format!("sha256:{}", sha256_file(&partial, boundary)?) == digest
    {
        fs::rename(&partial, &archive).map_err(|_| github_error("github_eval_stage_changed"))?;
    }
    if !archive.exists() {
        if artifact.get("expired").and_then(Value::as_bool) != Some(false) {
            return Err(github_error("github_eval_artifact_expired"));
        }
        let used = directory_bytes(boundary.root())?;
        let previous_bytes = fs::metadata(&partial)
            .map(|metadata| metadata.len())
            .unwrap_or(0);
        let available = limits
            .runtime_bytes
            .saturating_sub(used)
            .saturating_add(previous_bytes);
        if size > available {
            return Err(github_error("github_eval_runtime_quota_exceeded"));
        }
        download(
            &format!("repos/{repository}/actions/artifacts/{artifact_id}/zip"),
            &partial,
            &context.source_root,
            limits.artifact_bytes.min(available),
            boundary,
        )?;
        if format!("sha256:{}", sha256_file(&partial, boundary)?) != digest {
            return Err(github_error("github_eval_artifact_digest_mismatch"));
        }
        fs::rename(&partial, &archive).map_err(|_| github_error("github_eval_stage_changed"))?;
    }
    let metadata =
        fs::symlink_metadata(&archive).map_err(|_| github_error("github_eval_stage_changed"))?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > limits.artifact_bytes
        || format!("sha256:{}", sha256_file(&archive, boundary)?) != digest
    {
        return Err(github_error("github_eval_artifact_digest_mismatch"));
    }
    let spool_relative = stage_relative.join("spool");
    let spool = boundary
        .resolve(&spool_relative)
        .map_err(|_| github_error("github_eval_stage_invalid"))?;
    extract_archive(&archive_relative, &spool_relative, limits, boundary)?;
    collection_complete(&spool, run_id, head, boundary)?;
    let options = CommandOptions {
        values: BTreeMap::from([
            ("spool-root".to_owned(), spool.display().to_string()),
            ("run-id".to_owned(), run_id.to_owned()),
        ]),
        flags: BTreeSet::new(),
    };
    if command_archive_eval(context, &options, no_pull)
        .map_err(|_| github_error("github_eval_archive_publication_failed"))?
        != 0
    {
        return Err(github_error("github_eval_archive_publication_failed"));
    }
    remove_stage_directory(boundary, &stage)?;
    Ok(true)
}
