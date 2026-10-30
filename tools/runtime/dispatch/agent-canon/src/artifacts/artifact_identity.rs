//! Canonical artifact bytes, Git source bindings, and stable filesystem readback.
// @dependency-start
// contract implementation
// responsibility Materializes and verifies canonical artifact byte identities.
// upstream design ../../../../../../agents/COMMUNICATION_PROTOCOL.md owns artifact identity schemas and import rules
// upstream implementation ../runtime_boundary.rs owns no-follow filesystem reads
// downstream implementation external_artifact_binding.rs uses canonical body hashes
// @dependency-end

use crate::runtime_boundary::{RuntimeDirectory, RuntimeFileSnapshot};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use time::OffsetDateTime;

pub(crate) const ARTIFACT_IDENTITY_SCHEMA: &str = "agent-canon.artifact-identity.v1";
const ARTIFACT_ROLES: [&str; 6] = [
    "review_decision",
    "review_target",
    "review_receipt",
    "publication_receipt",
    "publication_authority",
    "source_packet_artifact",
];
const SOURCE_BINDING_KINDS: [&str; 2] = ["git_commit_path", "filesystem_immutable"];
const TEXT_EXTENSIONS: [&str; 8] = [
    ".json", ".md", ".py", ".sh", ".toml", ".yaml", ".yml", ".txt",
];
const IDENTITY_KEYS: [&str; 19] = [
    "schema",
    "schema_version",
    "identity_record_id",
    "artifact_role",
    "repository_id",
    "repository_root",
    "artifact_path",
    "source_binding",
    "byte_size",
    "sha256",
    "git_blob",
    "encoding",
    "bom",
    "line_endings",
    "filesystem_readback",
    "materializer",
    "materialized_at_utc",
    "materialization_order_index",
    "identity_record_body_sha256",
];
const OWNER_PATH: &str = "tools/runtime/artifacts/artifact_identity.py";

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ArtifactIdentityError {
    pub(crate) code: &'static str,
    pub(crate) detail: String,
}

impl ArtifactIdentityError {
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

impl fmt::Display for ArtifactIdentityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.detail.is_empty() {
            formatter.write_str(self.code)
        } else {
            write!(formatter, "{}:{}", self.code, self.detail)
        }
    }
}

impl std::error::Error for ArtifactIdentityError {}

type Result<T> = std::result::Result<T, ArtifactIdentityError>;

fn git_failure(output: &std::process::Output) -> ArtifactIdentityError {
    let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
    ArtifactIdentityError::with_detail("artifact_identity:git_read_failed", detail)
}

fn reject_noncanonical_json(value: &Value) -> Result<()> {
    match value {
        Value::Number(number) if number.is_f64() => Err(ArtifactIdentityError::new(
            "artifact_identity:float_forbidden",
        )),
        Value::Array(values) => {
            for value in values {
                reject_noncanonical_json(value)?;
            }
            Ok(())
        }
        Value::Object(values) => {
            for value in values.values() {
                reject_noncanonical_json(value)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

pub(crate) fn canonical_json_bytes<T: serde::Serialize>(value: &T) -> Result<Vec<u8>> {
    let value = serde_json::to_value(value).map_err(|error| {
        if error.to_string().contains("key must be a string") {
            ArtifactIdentityError::new("artifact_identity:non_string_key")
        } else {
            ArtifactIdentityError::with_detail("artifact_identity:json_invalid", error.to_string())
        }
    })?;
    reject_noncanonical_json(&value)?;
    serde_json::to_vec(&value).map_err(|error| {
        ArtifactIdentityError::with_detail("artifact_identity:json_invalid", error.to_string())
    })
}

pub(crate) fn canonical_body_sha256(record: &Value, hash_field: &str) -> Result<String> {
    let Value::Object(record) = record else {
        return Err(ArtifactIdentityError::new(
            "artifact_identity:record_not_object",
        ));
    };
    let mut body = record.clone();
    body.remove(hash_field);
    Ok(sha256_hex(&canonical_json_bytes(&Value::Object(body))?))
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// Return the SHA-1 object ID Git assigns to a blob containing these exact bytes.
pub(crate) fn git_blob_oid(data: &[u8]) -> String {
    let mut message = format!("blob {}\0", data.len()).into_bytes();
    message.extend_from_slice(data);
    let bit_length = (message.len() as u64).wrapping_mul(8);
    message.push(0x80);
    while message.len() % 64 != 56 {
        message.push(0);
    }
    message.extend_from_slice(&bit_length.to_be_bytes());

    let mut state = [
        0x67452301_u32,
        0xefcdab89,
        0x98badcfe,
        0x10325476,
        0xc3d2e1f0,
    ];
    for chunk in message.chunks_exact(64) {
        let mut words = [0_u32; 80];
        for (index, bytes) in chunk.chunks_exact(4).enumerate() {
            words[index] = u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]);
        }
        for index in 16..80 {
            words[index] =
                (words[index - 3] ^ words[index - 8] ^ words[index - 14] ^ words[index - 16])
                    .rotate_left(1);
        }
        let [mut a, mut b, mut c, mut d, mut e] = state;
        for (index, word) in words.iter().enumerate() {
            let (function, constant) = match index {
                0..=19 => ((b & c) | ((!b) & d), 0x5a827999_u32),
                20..=39 => (b ^ c ^ d, 0x6ed9eba1_u32),
                40..=59 => ((b & c) | (b & d) | (c & d), 0x8f1bbcdc_u32),
                _ => (b ^ c ^ d, 0xca62c1d6_u32),
            };
            let next = a
                .rotate_left(5)
                .wrapping_add(function)
                .wrapping_add(e)
                .wrapping_add(constant)
                .wrapping_add(*word);
            e = d;
            d = c;
            c = b.rotate_left(30);
            b = a;
            a = next;
        }
        state[0] = state[0].wrapping_add(a);
        state[1] = state[1].wrapping_add(b);
        state[2] = state[2].wrapping_add(c);
        state[3] = state[3].wrapping_add(d);
        state[4] = state[4].wrapping_add(e);
    }
    state.iter().map(|word| format!("{word:08x}")).collect()
}

fn run_git(workspace: &Path, args: &[&str]) -> Result<Vec<u8>> {
    let output = Command::new("git")
        .arg("-C")
        .arg(workspace)
        .args(args)
        .output()
        .map_err(|error| {
            ArtifactIdentityError::with_detail(
                "artifact_identity:git_read_failed",
                error.to_string(),
            )
        })?;
    if !output.status.success() {
        return Err(git_failure(&output));
    }
    Ok(output.stdout)
}

fn run_git_text(workspace: &Path, args: &[&str]) -> Result<String> {
    let bytes = run_git(workspace, args)?;
    String::from_utf8(bytes)
        .map(|value| value.trim().to_string())
        .map_err(|error| {
            ArtifactIdentityError::with_detail(
                "artifact_identity:git_read_failed",
                error.to_string(),
            )
        })
}

fn absolute_path(path: &Path, workspace: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        workspace.join(path)
    }
}

fn resolve_with_missing(path: &Path) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| {
                ArtifactIdentityError::with_detail(
                    "artifact_identity:path_invalid",
                    error.to_string(),
                )
            })?
            .join(path)
    };
    resolve_path_with_missing(&absolute, 0)
}

fn resolve_path_with_missing(path: &Path, depth: usize) -> Result<PathBuf> {
    if depth > 40 {
        return Err(ArtifactIdentityError::new("artifact_identity:path_invalid"));
    }
    let mut cursor = PathBuf::from(
        path.components()
            .next()
            .and_then(|component| match component {
                Component::Prefix(prefix) => Some(prefix.as_os_str()),
                _ => None,
            })
            .unwrap_or_else(|| std::ffi::OsStr::new("/")),
    );
    let components = path.components().collect::<Vec<_>>();
    for (index, component) in components.iter().enumerate() {
        match component {
            Component::RootDir | Component::Prefix(_) => {}
            Component::CurDir => {}
            Component::ParentDir => {
                cursor.pop();
            }
            Component::Normal(name) => {
                let candidate = cursor.join(name);
                match fs::symlink_metadata(&candidate) {
                    Ok(metadata) if metadata.file_type().is_symlink() => {
                        let target = fs::read_link(&candidate).map_err(|error| {
                            ArtifactIdentityError::with_detail(
                                "artifact_identity:path_invalid",
                                error.to_string(),
                            )
                        })?;
                        let mut expanded = if target.is_absolute() {
                            target
                        } else {
                            cursor.join(target)
                        };
                        for remainder in components.iter().skip(index + 1) {
                            match remainder {
                                Component::Normal(part) => expanded.push(part),
                                Component::ParentDir => expanded.push(".."),
                                Component::CurDir | Component::RootDir | Component::Prefix(_) => {}
                            }
                        }
                        return resolve_path_with_missing(&expanded, depth + 1);
                    }
                    Ok(_) => {
                        cursor = fs::canonicalize(&candidate).map_err(|error| {
                            ArtifactIdentityError::with_detail(
                                "artifact_identity:path_invalid",
                                error.to_string(),
                            )
                        })?;
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                        cursor.push(name);
                    }
                    Err(error) => {
                        return Err(ArtifactIdentityError::with_detail(
                            "artifact_identity:path_invalid",
                            error.to_string(),
                        ));
                    }
                }
            }
        }
    }
    Ok(cursor)
}

fn normalized_relative_path(workspace: &Path, artifact_path: &Path) -> Result<String> {
    let root = fs::canonicalize(workspace).map_err(|error| {
        ArtifactIdentityError::with_detail("artifact_identity:path_invalid", error.to_string())
    })?;
    let path = resolve_with_missing(&absolute_path(artifact_path, &root))?;
    let relative = path
        .strip_prefix(&root)
        .map_err(|_| ArtifactIdentityError::new("artifact_identity:path_outside_repository"))?;
    let mut parts = Vec::new();
    for component in relative.components() {
        match component {
            Component::Normal(part) => parts.push(
                part.to_str()
                    .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:path_invalid"))?,
            ),
            _ => return Err(ArtifactIdentityError::new("artifact_identity:path_invalid")),
        }
    }
    if parts.is_empty() {
        return Err(ArtifactIdentityError::new("artifact_identity:path_invalid"));
    }
    Ok(parts.join("/"))
}

fn infer_artifact_role(path: &str) -> &'static str {
    let name = Path::new(path)
        .file_name()
        .unwrap_or_else(|| std::ffi::OsStr::new(""))
        .to_string_lossy()
        .to_lowercase();
    if name.contains("review") && (name.contains("decision") || name.contains("receipt")) {
        "review_decision"
    } else if name.contains("review") {
        "review_target"
    } else if name.contains("publication") && (name.contains("receipt") || name.contains("result"))
    {
        "publication_receipt"
    } else if name.contains("publication") || name.contains("authority") {
        "publication_authority"
    } else {
        "source_packet_artifact"
    }
}

fn text_characteristics(path: &str, data: &[u8]) -> (&'static str, &'static str, &'static str) {
    let extension = Path::new(path)
        .extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| format!(".{}", extension.to_lowercase()))
        .unwrap_or_default();
    if !TEXT_EXTENSIONS.contains(&extension.as_str()) {
        return ("binary", "not_applicable", "not_applicable");
    }
    let bom = data.starts_with(&[0xef, 0xbb, 0xbf]);
    let payload = if bom { &data[3..] } else { data };
    if std::str::from_utf8(payload).is_err() {
        return ("binary", "not_applicable", "not_applicable");
    }
    let line_endings = if payload.windows(2).any(|bytes| bytes == b"\r\n")
        || payload
            .iter()
            .enumerate()
            .any(|(index, byte)| *byte == b'\r' && payload.get(index + 1) != Some(&b'\n'))
    {
        "mixed_or_crlf"
    } else {
        "LF"
    };
    (
        "UTF-8",
        if bom { "present" } else { "absent" },
        line_endings,
    )
}

fn snapshot_value(snapshot: RuntimeFileSnapshot, size_before: u64, mtime_before: i128) -> Value {
    json!({
        "nofollow": true,
        "regular_file": true,
        "device": snapshot.device,
        "inode": snapshot.inode,
        "mode": format!("{:06o}", snapshot.mode),
        "size_before": size_before,
        "size_after": snapshot.size,
        "mtime_ns_before": mtime_before,
        "mtime_ns_after": snapshot.mtime_ns,
    })
}

fn stable_read_error(error: std::io::Error) -> ArtifactIdentityError {
    match error.to_string().as_str() {
        "runtime target is not a regular file" => {
            ArtifactIdentityError::new("artifact_identity:not_regular_file")
        }
        "runtime file changed during read" => {
            ArtifactIdentityError::new("artifact_identity:readback_changed")
        }
        "runtime file size changed during read" => {
            ArtifactIdentityError::new("artifact_identity:size_changed")
        }
        detail => {
            ArtifactIdentityError::with_detail("artifact_identity:filesystem_read_failed", detail)
        }
    }
}

fn git_source_binding(workspace: &Path, path: &str) -> Result<Option<(Value, Vec<u8>)>> {
    let head = match run_git_text(workspace, &["rev-parse", "HEAD"]) {
        Ok(value) => value,
        Err(_) => return Ok(None),
    };
    let tree = match run_git_text(workspace, &["rev-parse", "HEAD^{tree}"]) {
        Ok(value) => value,
        Err(_) => return Ok(None),
    };
    let entries = match run_git(workspace, &["ls-tree", "-z", "HEAD", "--", path]) {
        Ok(value) => value,
        Err(_) => return Ok(None),
    };
    let Some(entry) = entries
        .split(|byte| *byte == 0)
        .find(|entry| !entry.is_empty())
    else {
        return Ok(None);
    };
    let separator = entry
        .iter()
        .position(|byte| *byte == b'\t')
        .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:tree_path_mismatch"))?;
    let (metadata, entry_path) = (&entry[..separator], &entry[separator + 1..]);
    if entry_path != path.as_bytes() {
        return Err(ArtifactIdentityError::new(
            "artifact_identity:tree_path_mismatch",
        ));
    }
    let metadata = std::str::from_utf8(metadata)
        .map_err(|_| ArtifactIdentityError::new("artifact_identity:tree_entry_not_blob"))?;
    let fields = metadata.split_whitespace().collect::<Vec<_>>();
    if fields.len() != 3 || fields[1] != "blob" {
        return Err(ArtifactIdentityError::new(
            "artifact_identity:tree_entry_not_blob",
        ));
    }
    let blob = fields[2];
    let data = run_git(workspace, &["cat-file", "blob", blob])?;
    Ok(Some((
        json!({
            "kind": "git_commit_path",
            "commit": head,
            "tree": tree,
            "path_mode": fields[0],
            "tree_blob": blob,
        }),
        data,
    )))
}

fn owner_tool_identity(workspace: &Path) -> Result<Value> {
    if let Some((source, _)) = git_source_binding(workspace, OWNER_PATH)? {
        return Ok(json!({
            "owner_tool": OWNER_PATH,
            "tool_source_commit": source["commit"],
            "tool_source_tree": source["tree"],
            "tool_source_blob": source["tree_blob"],
        }));
    }
    let owner_bytes = fs::read(workspace.join(OWNER_PATH)).map_err(|error| {
        ArtifactIdentityError::with_detail(
            "artifact_identity:owner_tool_unavailable",
            error.to_string(),
        )
    })?;
    let head = run_git_text(workspace, &["rev-parse", "HEAD"])?;
    let tree = run_git_text(workspace, &["rev-parse", "HEAD^{tree}"])?;
    Ok(json!({
        "owner_tool": OWNER_PATH,
        "tool_source_commit": head,
        "tool_source_tree": tree,
        "tool_source_blob": git_blob_oid(&owner_bytes),
    }))
}

fn stable_seed(record: &Value) -> Result<Value> {
    let fields = [
        "artifact_role",
        "repository_id",
        "artifact_path",
        "source_binding",
        "byte_size",
        "sha256",
        "git_blob",
    ];
    let mut seed = Map::new();
    for field in fields {
        let value = record
            .get(field)
            .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:key_set_mismatch"))?;
        seed.insert(field.to_string(), value.clone());
    }
    Ok(Value::Object(seed))
}

pub(crate) fn materialize_artifact_identity(
    workspace: &Path,
    artifact_path: &Path,
) -> Result<Value> {
    let root = fs::canonicalize(workspace).map_err(|error| {
        ArtifactIdentityError::with_detail("artifact_identity:path_invalid", error.to_string())
    })?;
    let relative = normalized_relative_path(&root, artifact_path)?;
    let committed = git_source_binding(&root, &relative)?;
    let (source_binding, data, filesystem_readback) = if let Some((source_binding, data)) =
        committed
    {
        let source_file = root.join(&relative);
        let filesystem_readback = if fs::metadata(&source_file)
            .is_ok_and(|metadata| metadata.is_file())
        {
            let directory = RuntimeDirectory::open_nofollow(&root, false).map_err(|error| {
                ArtifactIdentityError::with_detail(
                    "artifact_identity:filesystem_read_failed",
                    error.to_string(),
                )
            })?;
            let (_, snapshot) = directory
                .read_stable(Path::new(&relative))
                .map_err(stable_read_error)?
                .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:not_regular_file"))?;
            snapshot_value(snapshot, snapshot.size, snapshot.mtime_ns)
        } else {
            json!({
                "nofollow": true,
                "regular_file": true,
                "device": 0,
                "inode": 0,
                "mode": source_binding["path_mode"],
                "size_before": data.len(),
                "size_after": data.len(),
                "mtime_ns_before": 0,
                "mtime_ns_after": 0,
            })
        };
        (source_binding, data, filesystem_readback)
    } else {
        let directory = RuntimeDirectory::open_nofollow(&root, false).map_err(|error| {
            ArtifactIdentityError::with_detail(
                "artifact_identity:filesystem_read_failed",
                error.to_string(),
            )
        })?;
        let (data, snapshot) = directory
            .read_stable(Path::new(&relative))
            .map_err(stable_read_error)?
            .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:not_regular_file"))?;
        let readback = snapshot_value(snapshot, snapshot.size, snapshot.mtime_ns);
        (
            json!({
                "kind": "filesystem_immutable",
                "commit": null,
                "tree": null,
                "path_mode": null,
                "tree_blob": null,
            }),
            data,
            readback,
        )
    };
    let (encoding, bom, line_endings) = text_characteristics(&relative, &data);
    let artifact_role = infer_artifact_role(&relative);
    let repository_id = root
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:repository_id_invalid"))?;
    let digest = sha256_hex(&data);
    let blob = git_blob_oid(&data);
    let stable = json!({
        "artifact_role": artifact_role,
        "repository_id": repository_id,
        "artifact_path": relative,
        "source_binding": source_binding,
        "byte_size": data.len(),
        "sha256": digest,
        "git_blob": blob,
    });
    let identity_record_id = format!(
        "artifact-identity:{}",
        sha256_hex(&canonical_json_bytes(&stable)?)
    );
    let now = OffsetDateTime::now_utc();
    let materialized_at_utc = format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        now.year(),
        u8::from(now.month()),
        now.day(),
        now.hour(),
        now.minute(),
        now.second()
    );
    let mut record = json!({
        "schema": ARTIFACT_IDENTITY_SCHEMA,
        "schema_version": 1,
        "identity_record_id": identity_record_id,
        "artifact_role": artifact_role,
        "repository_id": repository_id,
        "repository_root": root.display().to_string(),
        "artifact_path": relative,
        "source_binding": source_binding,
        "byte_size": data.len(),
        "sha256": digest,
        "git_blob": blob,
        "encoding": encoding,
        "bom": bom,
        "line_endings": line_endings,
        "filesystem_readback": filesystem_readback,
        "materializer": owner_tool_identity(&root)?,
        "materialized_at_utc": materialized_at_utc,
        "materialization_order_index": 1,
        "identity_record_body_sha256": "",
    });
    let body_sha = canonical_body_sha256(&record, "identity_record_body_sha256")?;
    record["identity_record_body_sha256"] = Value::String(body_sha);
    Ok(record)
}

pub(crate) fn verify_identity_record(workspace: &Path, record: &Value) -> Result<Value> {
    if record.get("schema").and_then(Value::as_str) != Some(ARTIFACT_IDENTITY_SCHEMA)
        || record.get("schema_version").and_then(Value::as_u64) != Some(1)
    {
        return Err(ArtifactIdentityError::new(
            "artifact_identity:schema_mismatch",
        ));
    }
    let object = record
        .as_object()
        .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:record_not_object"))?;
    let keys = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = IDENTITY_KEYS.iter().copied().collect::<BTreeSet<_>>();
    if keys != expected {
        return Err(ArtifactIdentityError::new(
            "artifact_identity:key_set_mismatch",
        ));
    }
    let role = record
        .get("artifact_role")
        .and_then(Value::as_str)
        .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:artifact_role_invalid"))?;
    if !ARTIFACT_ROLES.contains(&role) {
        return Err(ArtifactIdentityError::new(
            "artifact_identity:artifact_role_invalid",
        ));
    }
    let source_binding = record
        .get("source_binding")
        .and_then(Value::as_object)
        .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:source_binding_invalid"))?;
    if !source_binding
        .get("kind")
        .and_then(Value::as_str)
        .is_some_and(|kind| SOURCE_BINDING_KINDS.contains(&kind))
    {
        return Err(ArtifactIdentityError::new(
            "artifact_identity:source_binding_invalid",
        ));
    }
    let artifact_path = record
        .get("artifact_path")
        .and_then(Value::as_str)
        .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:path_invalid"))?;
    let current = materialize_artifact_identity(workspace, Path::new(artifact_path))?;
    for field in [
        "artifact_role",
        "repository_id",
        "repository_root",
        "artifact_path",
        "source_binding",
        "byte_size",
        "sha256",
        "git_blob",
        "encoding",
        "bom",
        "line_endings",
        "materializer",
    ] {
        if record.get(field) != current.get(field) {
            return Err(ArtifactIdentityError::with_detail(
                "artifact_identity:readback_mismatch",
                field,
            ));
        }
    }
    let expected_id = format!(
        "artifact-identity:{}",
        sha256_hex(&canonical_json_bytes(&stable_seed(record)?)?)
    );
    if record.get("identity_record_id").and_then(Value::as_str) != Some(expected_id.as_str()) {
        return Err(ArtifactIdentityError::new("artifact_identity:id_mismatch"));
    }
    let expected_body = canonical_body_sha256(record, "identity_record_body_sha256")?;
    if record
        .get("identity_record_body_sha256")
        .and_then(Value::as_str)
        != Some(expected_body.as_str())
    {
        return Err(ArtifactIdentityError::new(
            "artifact_identity:body_hash_mismatch",
        ));
    }
    Ok(json!({
        "schema": "agent-canon.artifact-identity-verification.v1",
        "ok": true,
        "identity_record_id": expected_id,
        "identity_record_body_sha256": record["identity_record_body_sha256"],
        "artifact_path": artifact_path,
        "sha256": record["sha256"],
        "git_blob": record["git_blob"],
    }))
}

pub(crate) fn verify_artifact_identity(workspace: &Path, record_path: &Path) -> Result<Value> {
    let root = fs::canonicalize(workspace).map_err(|error| {
        ArtifactIdentityError::with_detail("artifact_identity:path_invalid", error.to_string())
    })?;
    let relative = normalized_relative_path(&root, record_path)?;
    let directory = RuntimeDirectory::open_nofollow(&root, false).map_err(|error| {
        ArtifactIdentityError::with_detail(
            "artifact_identity:record_unavailable",
            error.to_string(),
        )
    })?;
    let (bytes, _) = directory
        .read_stable(Path::new(&relative))
        .map_err(|error| {
            ArtifactIdentityError::with_detail(
                "artifact_identity:record_unavailable",
                error.to_string(),
            )
        })?
        .ok_or_else(|| ArtifactIdentityError::new("artifact_identity:record_unavailable"))?;
    let record: Value = serde_json::from_slice(&bytes).map_err(|error| {
        ArtifactIdentityError::with_detail("artifact_identity:record_invalid", error.to_string())
    })?;
    verify_identity_record(&root, &record)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Serialize;
    use std::collections::BTreeMap;

    #[derive(Serialize)]
    struct NestedFixture {
        b: bool,
        a: Option<String>,
    }

    #[derive(Serialize)]
    struct ObjectFixture {
        z: u64,
        nested: NestedFixture,
        a: String,
    }

    #[test]
    fn rejects_float_identity_values() {
        let error = canonical_json_bytes(&json!({ "value": 1.5 })).unwrap_err();
        assert_eq!(error.code, "artifact_identity:float_forbidden");
    }

    #[test]
    fn computes_git_blob_oid_for_empty_bytes() {
        assert_eq!(
            git_blob_oid(b""),
            "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
        );
    }

    #[test]
    fn canonical_json_matches_sorted_unicode_fixture_for_structs_and_maps() {
        let fixture = ObjectFixture {
            z: 1,
            nested: NestedFixture { b: true, a: None },
            a: "é".to_string(),
        };
        let expected = r#"{"a":"é","nested":{"a":null,"b":true},"z":1}"#.as_bytes();
        let bytes = canonical_json_bytes(&fixture).expect("serialize struct fixture");
        assert_eq!(bytes.as_slice(), expected);
        assert_eq!(
            sha256_hex(&bytes),
            "8d3427a4781d0d93575fe50fe56942d1d8eadd6bf4f403457f327a47a0b06c77"
        );

        let nested = BTreeMap::from([("b", Value::Bool(true)), ("a", Value::Null)]);
        let map = BTreeMap::from([
            ("z", Value::from(1_u64)),
            (
                "nested",
                Value::Object(
                    nested
                        .into_iter()
                        .map(|(key, value)| (key.to_string(), value))
                        .collect(),
                ),
            ),
            ("a", Value::String("é".to_string())),
        ]);
        assert_eq!(canonical_json_bytes(&map).unwrap(), expected);
    }
}
