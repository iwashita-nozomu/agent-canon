// @dependency-start
// contract implementation
// responsibility Owns the complete-file dependency manifest snapshot consumed by the graph transaction.
// upstream design ../../../documents/design/dependency-manifest-design.md canonical dependency-header grammar
// downstream implementation graph.rs builds one graph from this source snapshot
// @dependency-end

use serde_json::json;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::io::Write;
#[cfg(unix)]
use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const SNAPSHOT_SCHEMA_VERSION: &str = "source_snapshot.v1";
const SURFACE_MANIFEST_SNAPSHOT_SCHEMA: &str = "agent-canon.surface-manifest.v1";
const DEFAULT_SURFACE_MANIFEST: &str = "documents/runtime/shared-runtime-surfaces.toml";
pub(crate) const PRODUCER_IDENTITY_VERSION: &str = "agent-canon.surface-manifest-producer.v1";
pub(crate) const PRODUCER_IDENTITY_CONTRACT: &str = "agent-canon.surface-manifest.v1";
pub(crate) const SOURCE_DIAGNOSTIC_SCHEMA: &str = "agent-canon.source-diagnostic.v1";

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ProducerIdentity {
    pub source_root: String,
    pub producer_path: String,
    pub version: String,
    pub contract: String,
    pub producer_sha256: String,
    pub manifest_path: String,
    pub manifest_sha256: String,
}

impl ProducerIdentity {
    pub(crate) fn fingerprint_material(&self) -> String {
        serde_json::to_string(self).unwrap_or_default()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceSpan {
    pub path: String,
    pub start_line: usize,
    pub start_column: usize,
    pub end_line: usize,
    pub end_column: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct DeclarationIdentity {
    pub direction: String,
    pub kind: String,
    pub target: String,
    pub reason: String,
    pub canonical_declaration: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Diagnostic {
    pub code: String,
    pub message: String,
    pub severity: String,
    pub source_span: SourceSpan,
    pub declaration: DeclarationIdentity,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ManifestAst {
    pub path: String,
    pub responsibility: String,
    pub contract_kind: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct DependencyDeclaration {
    pub declaration_id: String,
    pub source_identity_id: String,
    pub declared_direction: String,
    pub declared_kind: String,
    pub declared_target: String,
    pub canonical_target: String,
    pub resolved_target_identity_id: Option<String>,
    pub source_span: SourceSpan,
    pub reason: String,
    pub raw_line_hash: String,
    pub attestation_key: String,
    pub snapshot_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceIdentity {
    pub identity_id: String,
    pub authority_id: String,
    pub logical_id: String,
    pub repo_rel_path: String,
    pub canonical_locator: String,
    pub alternate_locators: Vec<String>,
    pub locator_kind: String,
    pub path_role: String,
    pub file_mode: String,
    pub exists: bool,
    pub is_dirty: bool,
    pub content_hash: String,
    pub git_blob_or_gitlink: String,
    pub submodule_commit: String,
    pub snapshot_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceExclusion {
    pub source_exclusion_id: String,
    pub source_identity_id: String,
    pub repo_rel_path: String,
    pub reason_code: String,
    pub rule_id: String,
    pub scope: String,
    pub evidence_id: String,
    pub covered: bool,
    pub snapshot_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SurfaceRelation {
    pub relation_id: String,
    pub relation_type: String,
    pub source_identity_id: String,
    pub target_identity_id: String,
    pub source_path: String,
    pub target_path: String,
    pub owner_class: String,
    pub surface_mode: String,
    pub content_hash_equal: bool,
    pub evidence_id: String,
    pub status: String,
    pub snapshot_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SnapshotHeader {
    pub snapshot_id: String,
    pub parent_repo_id: String,
    pub root_realpath: String,
    pub git_head: String,
    pub git_index_tree: String,
    pub git_worktree_dirty: bool,
    pub git_status_hash: String,
    pub dirty_paths: Vec<String>,
    pub agentcanon_pin: String,
    pub schema_version: String,
    pub tool_version: String,
    pub profile: String,
    pub path_sort: String,
    pub source_fingerprint: String,
    pub captured_before_hash: String,
    pub captured_after_hash: String,
    pub snapshot_consistent: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceUniverse {
    pub candidate_paths: Vec<String>,
    pub excluded_paths: Vec<String>,
    pub eligible_paths: Vec<String>,
    pub eligible_equals_candidate_minus_excluded: bool,
    pub union_equals_candidate: bool,
    pub intersection_empty: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ManifestSnapshot {
    pub header: SnapshotHeader,
    pub source_identities: Vec<SourceIdentity>,
    pub declarations: Vec<DependencyDeclaration>,
    pub source_exclusions: Vec<SourceExclusion>,
    pub surface_relations: Vec<SurfaceRelation>,
    pub source_universe: SourceUniverse,
    pub diagnostics: Vec<Diagnostic>,
    pub manifests: BTreeMap<String, ManifestAst>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SnapshotRequest {
    pub root: PathBuf,
    pub profile: String,
    pub output_jsonl: PathBuf,
    pub surface_manifest_producer: Option<PathBuf>,
    pub surface_manifest: Option<PathBuf>,
    pub producer_identity: Option<ProducerIdentity>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SnapshotProbe {
    pub git_head: String,
    pub git_status_hash: String,
    pub source_fingerprint: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SurfaceManifestEntry {
    path: String,
    mode: String,
    source: String,
    projection_producer: String,
    projection_kind: String,
    local_override_allowed: bool,
    optional: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SurfaceManifestSnapshot {
    prefix: String,
    entries: Vec<SurfaceManifestEntry>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SourceCandidate {
    relative: String,
    authority_id: String,
    canonical_locator: String,
    locator_kind: String,
    path_role: String,
    file_mode: String,
    exists: bool,
    bytes: Vec<u8>,
    git_blob_or_gitlink: String,
    submodule_commit: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ManifestError {
    Io(String),
    Git(String),
    Transport(String),
    SurfaceManifest(String),
    SnapshotInconsistent(String),
}

impl fmt::Display for ManifestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(message)
            | Self::Git(message)
            | Self::Transport(message)
            | Self::SurfaceManifest(message)
            | Self::SnapshotInconsistent(message) => formatter.write_str(message),
        }
    }
}

fn hash_bytes(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn validate_producer_identity_inner(
    identity: &ProducerIdentity,
    producer: Option<&Path>,
    verify_content: bool,
) -> Result<(), ManifestError> {
    if identity.version != PRODUCER_IDENTITY_VERSION
        || identity.contract != PRODUCER_IDENTITY_CONTRACT
    {
        return Err(ManifestError::SurfaceManifest(
            "producer identity version or contract is invalid".to_string(),
        ));
    }
    let source_root = fs::canonicalize(&identity.source_root)
        .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?;
    if source_root.to_string_lossy() != identity.source_root || !source_root.is_dir() {
        return Err(ManifestError::SurfaceManifest(
            "producer identity source root is not canonical".to_string(),
        ));
    }
    let canonical_file = |value: &str, field: &str| -> Result<PathBuf, ManifestError> {
        let path = fs::canonicalize(value)
            .map_err(|error| ManifestError::SurfaceManifest(format!("{field}: {error}")))?;
        if path.to_string_lossy() != value
            || !fs::symlink_metadata(&path)
                .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?
                .file_type()
                .is_file()
        {
            return Err(ManifestError::SurfaceManifest(format!(
                "producer identity {field} is not canonical regular file"
            )));
        }
        if path.strip_prefix(&source_root).is_err() {
            return Err(ManifestError::SurfaceManifest(format!(
                "producer identity {field} escapes source root"
            )));
        }
        Ok(path)
    };
    let producer_path = canonical_file(&identity.producer_path, "producer_path")?;
    let manifest_path = canonical_file(&identity.manifest_path, "manifest_path")?;
    if producer.is_some()
        && producer.map(|path| {
            fs::canonicalize(path)
                .map(|canonical| canonical == producer_path)
                .unwrap_or(false)
        }) != Some(true)
    {
        return Err(ManifestError::SurfaceManifest(
            "producer identity does not bind the executing producer".to_string(),
        ));
    }
    if verify_content {
        let producer_sha256 = hash_bytes(
            &fs::read(&producer_path)
                .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?,
        );
        let manifest_sha256 = hash_bytes(
            &fs::read(&manifest_path)
                .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?,
        );
        if identity.producer_sha256 != producer_sha256
            || identity.manifest_sha256 != manifest_sha256
        {
            return Err(ManifestError::SurfaceManifest(
                "producer identity content hash mismatch".to_string(),
            ));
        }
    }
    Ok(())
}

pub(crate) fn validate_producer_identity(
    identity: &ProducerIdentity,
    producer: Option<&Path>,
) -> Result<(), ManifestError> {
    validate_producer_identity_inner(identity, producer, true)
}

pub(crate) fn validate_persisted_producer_identity(
    identity: &ProducerIdentity,
) -> Result<(), ManifestError> {
    validate_producer_identity_inner(identity, None, false)
}

pub(crate) fn current_producer_identity(root: &Path) -> Result<ProducerIdentity, ManifestError> {
    let root = fs::canonicalize(root).map_err(|error| ManifestError::Io(error.to_string()))?;
    let source_root = fs::canonicalize(&root)
        .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?;
    let producer_path = fs::canonicalize(source_root.join("tools/agent_tools/surface_manifest.py"))
        .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?;
    let manifest_path =
        fs::canonicalize(source_root.join("documents/runtime/shared-runtime-surfaces.toml"))
            .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?;
    let identity = ProducerIdentity {
        source_root: source_root.to_string_lossy().into_owned(),
        producer_path: producer_path.to_string_lossy().into_owned(),
        version: PRODUCER_IDENTITY_VERSION.to_string(),
        contract: PRODUCER_IDENTITY_CONTRACT.to_string(),
        producer_sha256: hash_bytes(
            &fs::read(&producer_path)
                .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?,
        ),
        manifest_path: manifest_path.to_string_lossy().into_owned(),
        manifest_sha256: hash_bytes(
            &fs::read(&manifest_path)
                .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?,
        ),
    };
    validate_producer_identity(&identity, Some(&producer_path))?;
    Ok(identity)
}

fn hash_text(value: &str) -> String {
    hash_bytes(value.as_bytes())
}

fn git_text(root: &Path, args: &[&str]) -> Result<String, ManifestError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| ManifestError::Git(error.to_string()))?;
    if !output.status.success() {
        return Err(ManifestError::Git(
            String::from_utf8_lossy(&output.stderr).trim().to_string(),
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn required_json_object<'a>(
    value: &'a serde_json::Value,
    owner: &str,
) -> Result<&'a serde_json::Map<String, serde_json::Value>, ManifestError> {
    value.as_object().ok_or_else(|| {
        ManifestError::SurfaceManifest(format!("surface_manifest_snapshot: {owner} must be object"))
    })
}

fn required_json_string(
    object: &serde_json::Map<String, serde_json::Value>,
    key: &str,
    owner: &str,
) -> Result<String, ManifestError> {
    object
        .get(key)
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .ok_or_else(|| {
            ManifestError::SurfaceManifest(format!(
                "surface_manifest_snapshot: {owner}.{key} must be nonempty string"
            ))
        })
}

fn required_json_bool(
    object: &serde_json::Map<String, serde_json::Value>,
    key: &str,
    owner: &str,
) -> Result<bool, ManifestError> {
    object
        .get(key)
        .and_then(serde_json::Value::as_bool)
        .ok_or_else(|| {
            ManifestError::SurfaceManifest(format!(
                "surface_manifest_snapshot: {owner}.{key} must be boolean"
            ))
        })
}

fn require_exact_json_keys(
    object: &serde_json::Map<String, serde_json::Value>,
    expected: &[&str],
    owner: &str,
) -> Result<(), ManifestError> {
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = expected.iter().copied().collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(ManifestError::SurfaceManifest(format!(
            "surface_manifest_snapshot: {owner} fields are not canonical"
        )));
    }
    Ok(())
}

fn surface_manifest_script(root: &Path, producer: Option<&Path>) -> Result<PathBuf, ManifestError> {
    if let Some(producer) = producer {
        let metadata = fs::metadata(producer).map_err(|error| {
            ManifestError::SurfaceManifest(format!(
                "surface_manifest_snapshot: producer unavailable: {error}"
            ))
        })?;
        if !metadata.is_file() {
            return Err(ManifestError::SurfaceManifest(
                "surface_manifest_snapshot: producer is not a regular file".to_string(),
            ));
        }
        return Ok(producer.to_path_buf());
    }
    let standalone_script = root.join("tools/agent_tools/surface_manifest.py");
    if standalone_script.is_file() {
        return Ok(standalone_script);
    }
    Err(ManifestError::SurfaceManifest(
        "surface_manifest_snapshot: canonical Python producer is missing".to_string(),
    ))
}

fn load_surface_manifest_snapshot(
    root: &Path,
    producer: Option<&Path>,
    manifest: Option<&Path>,
) -> Result<SurfaceManifestSnapshot, ManifestError> {
    let script = surface_manifest_script(root, producer)?;
    let output = Command::new("python3")
        .arg(script)
        .args([
            "--root",
            root.to_str().ok_or_else(|| {
                ManifestError::SurfaceManifest(
                    "surface_manifest_snapshot: root is not UTF-8".to_string(),
                )
            })?,
            "--prefix",
            ".",
            "--manifest",
            manifest
                .unwrap_or_else(|| Path::new(DEFAULT_SURFACE_MANIFEST))
                .to_str()
                .ok_or_else(|| {
                    ManifestError::SurfaceManifest(
                        "surface_manifest_snapshot: manifest is not UTF-8".to_string(),
                    )
                })?,
            "normalized-snapshot",
        ])
        .output()
        .map_err(|error| ManifestError::SurfaceManifest(error.to_string()))?;
    if !output.status.success() {
        return Err(ManifestError::SurfaceManifest(format!(
            "surface_manifest_snapshot: producer failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    let value: serde_json::Value = serde_json::from_slice(&output.stdout).map_err(|error| {
        ManifestError::SurfaceManifest(format!("surface_manifest_snapshot: invalid JSON: {error}"))
    })?;
    let object = required_json_object(&value, "snapshot")?;
    require_exact_json_keys(object, &["entries", "prefix", "schema"], "snapshot")?;
    if object.get("schema").and_then(serde_json::Value::as_str)
        != Some(SURFACE_MANIFEST_SNAPSHOT_SCHEMA)
    {
        return Err(ManifestError::SurfaceManifest(
            "surface_manifest_snapshot: schema mismatch".to_string(),
        ));
    }
    let prefix = required_json_string(object, "prefix", "snapshot")?;
    let raw_entries = object
        .get("entries")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            ManifestError::SurfaceManifest(
                "surface_manifest_snapshot: snapshot.entries must be array".to_string(),
            )
        })?;
    let mut entries = Vec::with_capacity(raw_entries.len());
    let mut paths = BTreeSet::new();
    for (index, raw_entry) in raw_entries.iter().enumerate() {
        let owner = format!("snapshot.entries[{index}]");
        let entry = required_json_object(raw_entry, &owner)?;
        require_exact_json_keys(
            entry,
            &[
                "projection_kind",
                "local_override_allowed",
                "mode",
                "optional",
                "projection_producer",
                "path",
                "source",
            ],
            &owner,
        )?;
        let path = required_json_string(entry, "path", &owner)?;
        if !paths.insert(path.clone()) {
            return Err(ManifestError::SurfaceManifest(format!(
                "surface_manifest_snapshot: duplicate path {path}"
            )));
        }
        let mode = required_json_string(entry, "mode", &owner)?;
        let source = entry
            .get("source")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| {
                ManifestError::SurfaceManifest(format!(
                    "surface_manifest_snapshot: {owner}.source must be string"
                ))
            })?
            .to_string();
        let projection_producer = required_json_string(entry, "projection_producer", &owner)?;
        let projection_kind = required_json_string(entry, "projection_kind", &owner)?;
        if matches!(mode.as_str(), "symlink" | "copy") && source.is_empty() {
            return Err(ManifestError::SurfaceManifest(format!(
                "surface_manifest_snapshot: {path} projection source is empty"
            )));
        }
        entries.push(SurfaceManifestEntry {
            path,
            mode,
            source,
            projection_producer,
            projection_kind,
            local_override_allowed: required_json_bool(entry, "local_override_allowed", &owner)?,
            optional: required_json_bool(entry, "optional", &owner)?,
        });
    }
    Ok(SurfaceManifestSnapshot { prefix, entries })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TargetPathError {
    Absolute,
    EscapesRoot,
}

fn normalize_relative(path: &Path) -> Result<String, TargetPathError> {
    let mut components: Vec<String> = Vec::new();
    for component in path.components() {
        match component {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                if components.pop().is_none() {
                    return Err(TargetPathError::EscapesRoot);
                }
            }
            std::path::Component::Normal(value) => {
                components.push(value.to_string_lossy().to_string())
            }
            std::path::Component::RootDir | std::path::Component::Prefix(_) => {
                return Err(TargetPathError::Absolute)
            }
        }
    }
    Ok(components.join("/"))
}

fn resolve_source_relative_target(
    source_path: &str,
    declared_target: &str,
) -> Result<String, TargetPathError> {
    let target = Path::new(declared_target);
    if target.is_absolute() {
        return Err(TargetPathError::Absolute);
    }
    let source_parent = Path::new(source_path).parent().unwrap_or(Path::new("."));
    normalize_relative(&source_parent.join(target))
}

fn normalize_declaration_component(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn invalid_declaration_component(name: &str, line: &str) -> String {
    format!("invalid-{name}:{}", hash_text(line))
}

fn declaration_identity(
    direction: &str,
    kind: &str,
    target: &str,
    reason: &str,
) -> DeclarationIdentity {
    let direction = normalize_declaration_component(direction);
    let kind = normalize_declaration_component(kind);
    let target = normalize_declaration_component(target);
    let reason = normalize_declaration_component(reason);
    let identity_seed = format!("{direction}\0{kind}\0{target}\0{reason}");
    let direction = if direction.is_empty() {
        invalid_declaration_component("direction", &identity_seed)
    } else {
        direction
    };
    let kind = if kind.is_empty() {
        invalid_declaration_component("kind", &identity_seed)
    } else {
        kind
    };
    let target = if target.is_empty() {
        invalid_declaration_component("target", &identity_seed)
    } else {
        target
    };
    let reason = if reason.is_empty() {
        invalid_declaration_component("reason", &identity_seed)
    } else {
        reason
    };
    let canonical_declaration = format!("{direction} {kind} {target} {reason}");
    DeclarationIdentity {
        direction,
        kind,
        target,
        reason,
        canonical_declaration,
    }
}

fn source_span(relative: &str, line_number: usize, line: &str) -> SourceSpan {
    SourceSpan {
        path: relative.to_string(),
        start_line: line_number,
        start_column: 1,
        end_line: line_number,
        end_column: line.len() + 1,
    }
}

fn source_diagnostic(
    code: &str,
    message: String,
    severity: &str,
    span: SourceSpan,
    declaration: DeclarationIdentity,
) -> Diagnostic {
    Diagnostic {
        code: code.to_string(),
        message,
        severity: severity.to_string(),
        source_span: span,
        declaration,
    }
}

pub(crate) fn diagnostic_identity_json(diagnostic: &Diagnostic) -> serde_json::Value {
    let declaration = &diagnostic.declaration;
    json!({
        "schema": SOURCE_DIAGNOSTIC_SCHEMA,
        "code": diagnostic.code,
        "source": diagnostic.source_span.path,
        "target": declaration.target,
        "declaration": declaration.canonical_declaration,
        "source_span": {
            "path": diagnostic.source_span.path,
            "start_line": diagnostic.source_span.start_line,
            "start_column": diagnostic.source_span.start_column,
            "end_line": diagnostic.source_span.end_line,
            "end_column": diagnostic.source_span.end_column,
        },
        "declaration_components": {
            "direction": declaration.direction,
            "kind": declaration.kind,
            "target": declaration.target,
            "reason": declaration.reason,
        },
    })
}

fn target_path_diagnostic_code(error: TargetPathError) -> &'static str {
    match error {
        TargetPathError::Absolute => "target-absolute",
        TargetPathError::EscapesRoot => "target-escapes-root",
    }
}

fn target_path_diagnostic(
    relative: &str,
    line_number: usize,
    line: &str,
    target: &str,
    error: TargetPathError,
    declaration: DeclarationIdentity,
) -> Diagnostic {
    source_diagnostic(
        target_path_diagnostic_code(error),
        format!("{relative}:{line_number}:{target}"),
        "error",
        source_span(relative, line_number, line),
        declaration,
    )
}

fn target_unresolved_diagnostic(
    relative: &str,
    line_number: usize,
    line: &str,
    target: &str,
    declaration: DeclarationIdentity,
) -> Diagnostic {
    source_diagnostic(
        "target-unresolved",
        format!("{relative}:{line_number}:{target}"),
        "error",
        source_span(relative, line_number, line),
        declaration,
    )
}

pub(crate) fn diagnostic_category(code: &str) -> &'static str {
    match code {
        "target-ambiguous" => "ambiguous",
        "source-uncovered" => "uncovered",
        _ => "unresolved",
    }
}

pub(crate) fn snapshot_completeness(snapshot: &ManifestSnapshot) -> (usize, usize, usize) {
    let mut counts = [0; 3];
    for diagnostic in &snapshot.diagnostics {
        match diagnostic_category(&diagnostic.code) {
            "unresolved" => counts[0] += 1,
            "ambiguous" => counts[1] += 1,
            "uncovered" => counts[2] += 1,
            _ => unreachable!("diagnostic category is closed"),
        }
    }
    (counts[0], counts[1], counts[2])
}

pub(crate) fn source_path_is_explicitly_excluded(relative_path: &str) -> bool {
    let parts: Vec<&str> = relative_path.split('/').collect();
    if parts.iter().any(|part| {
        matches!(
            *part,
            ".git" | "__pycache__" | ".pytest_cache" | ".mypy_cache" | ".ruff_cache"
        )
    }) || relative_path.ends_with(".pyc")
        || relative_path.ends_with(".pyo")
    {
        return true;
    }
    if relative_path == ".agent-canon/knowledge-graph"
        || relative_path.starts_with(".agent-canon/knowledge-graph/")
        || relative_path == ".agent-canon/log-archive"
        || relative_path.starts_with(".agent-canon/log-archive/")
        || relative_path == ".agent-canon/runtime-event-spool"
        || relative_path.starts_with(".agent-canon/runtime-event-spool/")
        || relative_path == ".agent-canon/update-state.toml"
        || relative_path == ".agent-canon/update-lifecycle"
        || relative_path.starts_with(".agent-canon/update-lifecycle/")
    {
        return true;
    }
    if relative_path == "reports/agents"
        || relative_path.starts_with("reports/agents/")
        || relative_path == "reports/agent-runtime-dashboard"
        || relative_path.starts_with("reports/agent-runtime-dashboard/")
    {
        return true;
    }
    parts.len() >= 3 && parts[0] == "experiments" && matches!(parts[2], "result" | "report")
}

pub(crate) fn source_path_is_historical_dependency_record(relative_path: &str) -> bool {
    relative_path
        .split('/')
        .collect::<Vec<_>>()
        .windows(2)
        .any(|components| components == ["issues", "closed"])
}

fn path_is_surface_or_descendant(relative: &str, surface: &str) -> bool {
    relative
        .strip_prefix(surface)
        .is_some_and(|suffix| suffix.is_empty() || suffix.starts_with('/'))
}

fn manifest_repo_state_entry<'a>(
    manifest: &'a SurfaceManifestSnapshot,
    canonical_locator: &str,
) -> Option<&'a SurfaceManifestEntry> {
    let mut selected: Option<&SurfaceManifestEntry> = None;
    for entry in &manifest.entries {
        if entry.mode != "repo_state"
            || !path_is_surface_or_descendant(canonical_locator, &entry.path)
        {
            continue;
        }
        if selected.is_none_or(|current| {
            entry.path.len() > current.path.len()
                || (entry.path.len() == current.path.len() && entry.path < current.path)
        }) {
            selected = Some(entry);
        }
    }
    selected
}

fn source_candidate_is_explicitly_excluded(
    candidate: &SourceCandidate,
    manifest: &SurfaceManifestSnapshot,
) -> bool {
    source_path_is_explicitly_excluded(&candidate.relative)
        || manifest_repo_state_entry(manifest, &candidate.canonical_locator).is_some()
}

fn git_bytes(root: &Path, args: &[&str]) -> Result<Vec<u8>, ManifestError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| ManifestError::Git(error.to_string()))?;
    if !output.status.success() {
        return Err(ManifestError::Git(
            String::from_utf8_lossy(&output.stderr).trim().to_string(),
        ));
    }
    Ok(output.stdout)
}

fn git_visible_paths(root: &Path) -> Result<Vec<String>, ManifestError> {
    let bytes = git_bytes(
        root,
        &[
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
    )?;
    let mut paths = bytes
        .split(|byte| *byte == 0)
        .filter(|value| !value.is_empty())
        .map(|value| String::from_utf8_lossy(value).to_string())
        .filter(|value| {
            let path = root.join(value);
            path.is_file() || path.is_symlink() || !path.exists()
        })
        .collect::<Vec<_>>();
    paths.sort();
    paths.dedup();
    Ok(paths)
}

struct SourcePathRead {
    bytes: Vec<u8>,
    file_mode: String,
    exists: bool,
}

fn missing_source_path() -> SourcePathRead {
    SourcePathRead {
        bytes: Vec::new(),
        file_mode: "100644".to_string(),
        exists: false,
    }
}

fn read_source_path(root: &Path, relative: &str) -> Result<SourcePathRead, ManifestError> {
    let path = root.join(relative);
    let metadata = match fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(missing_source_path())
        }
        Err(error) => return Err(ManifestError::Io(error.to_string())),
    };
    if metadata.file_type().is_symlink() {
        let target = match fs::read_link(&path) {
            Ok(target) => target,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(missing_source_path())
            }
            Err(error) => return Err(ManifestError::Io(error.to_string())),
        };
        return Ok(SourcePathRead {
            bytes: target.as_os_str().as_bytes().to_vec(),
            file_mode: "120000".to_string(),
            exists: true,
        });
    }
    if metadata.file_type().is_file() {
        let bytes = match fs::read(&path) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(missing_source_path())
            }
            Err(error) => return Err(ManifestError::Io(error.to_string())),
        };
        return Ok(SourcePathRead {
            bytes,
            file_mode: "100644".to_string(),
            exists: true,
        });
    }
    Err(ManifestError::Io(format!(
        "source path is not a regular file or symlink: {}",
        path.display()
    )))
}

fn source_fingerprint_for_candidates(
    candidates: &[SourceCandidate],
    manifest: &SurfaceManifestSnapshot,
) -> Result<String, ManifestError> {
    let mut rows = Vec::new();
    let mut processed = BTreeSet::new();
    for (index, candidate) in candidates.iter().enumerate() {
        if !processed.insert(candidate.relative.clone()) {
            return Err(ManifestError::SnapshotInconsistent(
                "candidate source path was processed twice".to_string(),
            ));
        }
        let remaining_before = candidates.len() - index;
        if !source_candidate_is_explicitly_excluded(candidate, manifest) {
            rows.push(format!(
                "{}\0{}\0{}\0{}\0{}\0{}\0{}\0{}\n",
                candidate.authority_id,
                candidate.canonical_locator,
                candidate.locator_kind,
                candidate.relative,
                candidate.exists,
                candidate.file_mode,
                candidate.git_blob_or_gitlink,
                // Content is an evidence term for freshness, never an identity key.
                hash_bytes(&candidate.bytes)
            ));
        }
        let remaining_after = candidates.len() - processed.len();
        if remaining_after >= remaining_before {
            return Err(ManifestError::SnapshotInconsistent(
                "candidate source measure did not decrease".to_string(),
            ));
        }
    }
    if processed.len() != candidates.len() {
        return Err(ManifestError::SnapshotInconsistent(
            "candidate source processed set is incomplete".to_string(),
        ));
    }
    Ok(hash_text(&rows.concat()))
}

fn source_candidates(
    root: &Path,
    manifest: &SurfaceManifestSnapshot,
    git_head: &str,
) -> Result<Vec<SourceCandidate>, ManifestError> {
    let authority_id = format!("standalone-git:{git_head}");
    let mut candidates = Vec::new();
    for relative in git_visible_paths(root)? {
        let source = read_source_path(root, &relative)?;
        let git_blob_or_gitlink = git_text(root, &["hash-object", "--", &relative])
            .or_else(|_| git_text(root, &["rev-parse", &format!(":{relative}")]))
            .unwrap_or_default();
        candidates.push(SourceCandidate {
            relative: relative.clone(),
            authority_id: authority_id.clone(),
            canonical_locator: relative,
            locator_kind: "repo-relative".to_string(),
            path_role: "source".to_string(),
            file_mode: source.file_mode,
            exists: source.exists,
            bytes: source.bytes,
            git_blob_or_gitlink,
            submodule_commit: String::new(),
        });
    }
    candidates.sort_by(|left, right| left.relative.cmp(&right.relative));
    for pair in candidates.windows(2) {
        if pair[0].relative == pair[1].relative {
            return Err(ManifestError::SnapshotInconsistent(format!(
                "source candidate path is duplicated: {}",
                pair[0].relative
            )));
        }
    }
    let _ = manifest;
    Ok(candidates)
}

fn surface_target_path(
    manifest: &SurfaceManifestSnapshot,
    entry: &SurfaceManifestEntry,
) -> Result<Option<String>, ManifestError> {
    if entry.source.is_empty() || !matches!(entry.mode.as_str(), "symlink" | "copy") {
        return Ok(None);
    }
    let source = Path::new(&entry.source);
    let normalized = normalize_relative(source).map_err(|error| {
        ManifestError::SurfaceManifest(format!(
            "surface_manifest_snapshot: {} source path is invalid: {error:?}",
            entry.path
        ))
    })?;
    let _ = manifest;
    Ok(Some(normalized))
}

fn canonicalize_surface_path(
    manifest: &SurfaceManifestSnapshot,
    relative: &str,
) -> Result<String, ManifestError> {
    let mut selected: Option<(&SurfaceManifestEntry, &str)> = None;
    for entry in &manifest.entries {
        if !matches!(entry.mode.as_str(), "symlink" | "copy") || entry.source.is_empty() {
            continue;
        }
        let view = entry.path.trim_end_matches('/');
        let Some(suffix) = relative
            .strip_prefix(view)
            .filter(|suffix| suffix.is_empty() || suffix.starts_with('/'))
        else {
            continue;
        };
        let replace = selected.is_none_or(|(selected_entry, _)| {
            let selected_view = selected_entry.path.trim_end_matches('/');
            view.len() > selected_view.len()
                || (view.len() == selected_view.len() && view < selected_view)
        });
        if replace {
            selected = Some((entry, suffix));
        }
    }
    if let Some((entry, suffix)) = selected {
        let joined = format!("{}{suffix}", entry.source);
        return normalize_relative(Path::new(&joined)).map_err(|error| {
            ManifestError::SurfaceManifest(format!(
                "surface_manifest_snapshot: projected path is invalid: {joined}: {error:?}"
            ))
        });
    }
    Ok(relative.to_string())
}

fn manifest_surface_relations(
    manifest: &SurfaceManifestSnapshot,
    identities: &[SourceIdentity],
    excluded: &BTreeSet<String>,
    snapshot_id: &str,
) -> Result<Vec<SurfaceRelation>, ManifestError> {
    let by_path = identities
        .iter()
        .map(|identity| (identity.repo_rel_path.as_str(), identity))
        .collect::<BTreeMap<_, _>>();
    let mut relations = Vec::new();
    for entry in &manifest.entries {
        let Some(target_path) = surface_target_path(manifest, entry)? else {
            continue;
        };
        if excluded.contains(&entry.path) || excluded.contains(&target_path) {
            continue;
        }
        let Some(source) = by_path.get(entry.path.as_str()) else {
            continue;
        };
        let Some(target) = by_path.get(target_path.as_str()) else {
            continue;
        };
        relations.push(SurfaceRelation {
            relation_id: hash_text(&format!(
                "surface\0{}\0{}\0{}\0{}",
                entry.mode, entry.path, target_path, source.authority_id
            )),
            relation_type: "view".to_string(),
            source_identity_id: source.identity_id.clone(),
            target_identity_id: target.identity_id.clone(),
            source_path: entry.path.clone(),
            target_path,
            owner_class: format!(
                "projection_producer={};projection_kind={}",
                entry.projection_producer, entry.projection_kind
            ),
            surface_mode: entry.mode.clone(),
            content_hash_equal: entry.mode == "copy" && source.content_hash == target.content_hash,
            evidence_id: hash_text(&format!(
                "surface-evidence\0{}\0{}\0{}",
                source.content_hash, target.content_hash, snapshot_id
            )),
            status: "active".to_string(),
            snapshot_id: snapshot_id.to_string(),
        });
    }
    Ok(relations)
}

fn exclusion_metadata(
    manifest: &SurfaceManifestSnapshot,
    candidate: &SourceCandidate,
) -> (&'static str, &'static str) {
    if manifest_repo_state_entry(manifest, &candidate.canonical_locator).is_some() {
        ("manifest_owned_state", "surface-manifest-repo-state")
    } else {
        ("generated_output", "source-owner-exclusion")
    }
}

fn source_status_bytes(
    root: &Path,
    manifest: &SurfaceManifestSnapshot,
) -> Result<Vec<u8>, ManifestError> {
    let raw = git_bytes(root, &["status", "--porcelain=v1", "--untracked-files=all"])?;
    let mut filtered = Vec::new();
    for line in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
    {
        if line.len() < 4 || line[2] != b' ' {
            return Err(ManifestError::SnapshotInconsistent(
                "git porcelain-v1 status line is malformed".to_string(),
            ));
        }
        let field = String::from_utf8_lossy(&line[3..]);
        let paths = field
            .split(" -> ")
            .map(|path| path.trim().trim_matches('"'))
            .collect::<Vec<_>>();
        if paths.iter().all(|path| {
            source_path_is_explicitly_excluded(path)
                || manifest_repo_state_entry(manifest, path).is_some()
        }) {
            continue;
        }
        filtered.extend_from_slice(line);
        filtered.push(b'\n');
    }
    Ok(filtered)
}

fn dependency_comment_payload<'a>(path: &Path, raw: &'a str) -> Option<&'a str> {
    let trimmed = raw.trim_start();
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default();
    if matches!(extension, "md" | "html" | "xml" | "svg") {
        return Some(trimmed.trim());
    }
    if matches!(
        extension,
        "rs" | "c" | "cc" | "cpp" | "h" | "hpp" | "js" | "ts"
    ) {
        return trimmed.strip_prefix("//").map(str::trim);
    }
    trimmed.strip_prefix('#').map(str::trim)
}

fn manifest_lines(path: &Path, text: &str) -> Vec<(usize, String)> {
    let mut inside = false;
    let mut markup_comment = false;
    let mut ended = false;
    let mut lines = Vec::new();
    for (index, raw) in text.lines().enumerate().take(80) {
        let raw_trimmed = raw.trim();
        if matches!(
            path.extension().and_then(|value| value.to_str()),
            Some("md" | "html" | "xml" | "svg")
        ) {
            if raw_trimmed == "<!--" {
                markup_comment = true;
                continue;
            }
            if raw_trimmed == "-->" {
                if inside {
                    return Vec::new();
                }
                markup_comment = false;
                continue;
            }
            if !markup_comment {
                continue;
            }
        }
        let Some(trimmed) = dependency_comment_payload(path, raw) else {
            if inside {
                return Vec::new();
            }
            continue;
        };
        if trimmed == "@dependency-start" {
            inside = true;
            continue;
        }
        if trimmed == "@dependency-end" {
            ended = inside;
            break;
        }
        if inside && !trimmed.is_empty() {
            lines.push((index + 1, trimmed.to_string()));
        }
    }
    if inside && ended {
        lines
    } else {
        Vec::new()
    }
}

fn snapshot_capture_hash(
    profile: &str,
    head: &str,
    index_hash: &str,
    status_hash: &str,
    source_fingerprint: &str,
) -> String {
    hash_text(&format!(
        "{profile}\0{head}\0{index_hash}\0{status_hash}\0{source_fingerprint}"
    ))
}

pub(crate) fn probe_snapshot_identity(
    root: &Path,
    profile: &str,
    producer: Option<&Path>,
    manifest: Option<&Path>,
) -> Result<SnapshotProbe, ManifestError> {
    let root = fs::canonicalize(root).map_err(|error| ManifestError::Io(error.to_string()))?;
    let surface_manifest = load_surface_manifest_snapshot(&root, producer, manifest)?;
    let head = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
    let candidates = source_candidates(&root, &surface_manifest, &head)?;
    let source_fingerprint = source_fingerprint_for_candidates(&candidates, &surface_manifest)?;
    let status = source_status_bytes(&root, &surface_manifest)?;
    let index_hash = hash_bytes(&git_bytes(&root, &["ls-files", "--stage", "-z"])?);
    let status_hash = hash_bytes(&status);
    let _capture_hash = snapshot_capture_hash(
        profile,
        &head,
        &index_hash,
        &status_hash,
        &source_fingerprint,
    );
    Ok(SnapshotProbe {
        git_head: head,
        git_status_hash: status_hash,
        source_fingerprint,
    })
}

pub(crate) fn capture_snapshot(
    request: &SnapshotRequest,
) -> Result<ManifestSnapshot, ManifestError> {
    let root =
        fs::canonicalize(&request.root).map_err(|error| ManifestError::Io(error.to_string()))?;
    if !root.is_dir() {
        return Err(ManifestError::Io(format!(
            "root is not a directory: {}",
            root.display()
        )));
    }
    if let Some(identity) = request.producer_identity.as_ref() {
        validate_producer_identity(identity, request.surface_manifest_producer.as_deref())?;
    } else if request.surface_manifest_producer.is_some() {
        return Err(ManifestError::SurfaceManifest(
            "explicit surface manifest producer requires producer identity".to_string(),
        ));
    }
    let surface_manifest = load_surface_manifest_snapshot(
        &root,
        request.surface_manifest_producer.as_deref(),
        request.surface_manifest.as_deref(),
    )?;
    let git_head = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
    let candidates = source_candidates(&root, &surface_manifest, &git_head)?;
    let candidate_paths = candidates
        .iter()
        .map(|candidate| candidate.relative.clone())
        .collect::<Vec<_>>();
    let source_fingerprint_before =
        source_fingerprint_for_candidates(&candidates, &surface_manifest)?;
    let index_hash = hash_bytes(&git_bytes(&root, &["ls-files", "--stage", "-z"])?);
    let status_bytes = source_status_bytes(&root, &surface_manifest)?;
    let status_hash = hash_bytes(&status_bytes);
    let captured_before_hash = snapshot_capture_hash(
        &request.profile,
        &git_head,
        &index_hash,
        &status_hash,
        &source_fingerprint_before,
    );
    let dirty_paths = String::from_utf8_lossy(&status_bytes)
        .lines()
        .map(|line| line.get(3..).unwrap_or(line).to_string())
        .collect::<Vec<_>>();
    let dirty_set = dirty_paths.iter().cloned().collect::<BTreeSet<_>>();
    let excluded_set = candidates
        .iter()
        .filter(|candidate| source_candidate_is_explicitly_excluded(candidate, &surface_manifest))
        .map(|candidate| candidate.relative.clone())
        .collect::<BTreeSet<_>>();
    let excluded_paths = excluded_set.iter().cloned().collect::<Vec<_>>();
    let eligible_paths = candidate_paths
        .iter()
        .filter(|path| !excluded_set.contains(*path))
        .cloned()
        .collect::<Vec<_>>();
    let snapshot_id = hash_text(&format!(
        "{SNAPSHOT_SCHEMA_VERSION}\0{}\0{}\0{}",
        root.display(),
        git_head,
        source_fingerprint_before
    ));
    let identity_by_path = candidates
        .iter()
        .map(|candidate| {
            (
                candidate.relative.clone(),
                hash_text(&format!(
                    "identity:{}\0{}\0{}",
                    candidate.authority_id, candidate.canonical_locator, candidate.locator_kind
                )),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut source_identities = Vec::new();
    let mut source_exclusions = Vec::new();
    let mut declarations = Vec::new();
    let mut manifests = BTreeMap::new();
    let mut diagnostics = Vec::new();
    let mut processed = BTreeSet::new();
    for (index, candidate) in candidates.iter().enumerate() {
        let relative = &candidate.relative;
        if !processed.insert(relative.clone())
            || candidates.len() - processed.len() >= candidates.len() - index
        {
            return Err(ManifestError::SnapshotInconsistent(
                "candidate source processing is not monotone".to_string(),
            ));
        }
        let identity_id = identity_by_path.get(relative).cloned().unwrap_or_default();
        source_identities.push(SourceIdentity {
            identity_id: identity_id.clone(),
            authority_id: candidate.authority_id.clone(),
            logical_id: format!("source:{relative}"),
            repo_rel_path: relative.to_string(),
            canonical_locator: candidate.canonical_locator.clone(),
            alternate_locators: Vec::new(),
            locator_kind: candidate.locator_kind.clone(),
            path_role: candidate.path_role.clone(),
            file_mode: candidate.file_mode.clone(),
            exists: candidate.exists,
            is_dirty: dirty_set.contains(relative),
            // Content hash is evidence; identity is the authority/locator key above.
            content_hash: hash_bytes(&candidate.bytes),
            git_blob_or_gitlink: candidate.git_blob_or_gitlink.clone(),
            submodule_commit: candidate.submodule_commit.clone(),
            snapshot_id: snapshot_id.clone(),
        });
        if excluded_set.contains(relative) {
            let (reason_code, rule_id) = exclusion_metadata(&surface_manifest, candidate);
            source_exclusions.push(SourceExclusion {
                source_exclusion_id: hash_text(&format!("exclude:{identity_id}")),
                source_identity_id: identity_id,
                repo_rel_path: relative.clone(),
                reason_code: reason_code.to_string(),
                rule_id: rule_id.to_string(),
                scope: relative.clone(),
                evidence_id: hash_text(relative),
                covered: true,
                snapshot_id: snapshot_id.clone(),
            });
            continue;
        }
        if source_path_is_historical_dependency_record(relative) {
            continue;
        }
        let Ok(text) = String::from_utf8(candidate.bytes.clone()) else {
            continue;
        };
        let path = root.join(relative);
        let entries = manifest_lines(&path, &text);
        if entries.is_empty() {
            continue;
        }
        let responsibility = entries
            .iter()
            .find_map(|(_, line)| line.strip_prefix("responsibility ").map(str::to_string))
            .unwrap_or_default();
        let contract_kind = entries
            .iter()
            .find_map(|(_, line)| line.strip_prefix("contract ").map(str::to_string))
            .unwrap_or_default();
        manifests.insert(
            relative.clone(),
            ManifestAst {
                path: relative.clone(),
                responsibility,
                contract_kind,
            },
        );
        for (line_number, line) in entries {
            let mut fields = line.split_whitespace();
            let direction = fields.next().unwrap_or_default();
            let kind = fields.next().unwrap_or_default();
            let target = fields.next().unwrap_or_default();
            let reason = fields.collect::<Vec<_>>().join(" ");
            if matches!(direction, "contract" | "responsibility" | "coverage") {
                continue;
            }
            if !matches!(direction, "upstream" | "downstream") {
                diagnostics.push(source_diagnostic(
                    "manifest-grammar",
                    format!("{relative}:{line_number}:{line}"),
                    "error",
                    source_span(relative, line_number, &line),
                    declaration_identity(direction, kind, target, &reason),
                ));
                continue;
            }
            if !matches!(kind, "design" | "implementation" | "environment")
                || target.is_empty()
                || reason.is_empty()
            {
                diagnostics.push(source_diagnostic(
                    "manifest-grammar",
                    format!("{relative}:{line_number}:{line}"),
                    "error",
                    source_span(relative, line_number, &line),
                    declaration_identity(direction, kind, target, &reason),
                ));
                continue;
            }
            let (resolved, attestation_key, canonical_target) =
                match resolve_source_relative_target(relative, target) {
                    Ok(target_path) => {
                        let canonical_target_path =
                            canonicalize_surface_path(&surface_manifest, &target_path)?;
                        if manifest_repo_state_entry(&surface_manifest, &canonical_target_path)
                            .is_some()
                        {
                            (None, "surface-manifest-repo-state", canonical_target_path)
                        } else {
                            let resolved = identity_by_path
                                .get(&canonical_target_path)
                                .filter(|_| !excluded_set.contains(&canonical_target_path))
                                .cloned();
                            if resolved.is_none() {
                                diagnostics.push(target_unresolved_diagnostic(
                                    relative,
                                    line_number,
                                    &line,
                                    target,
                                    declaration_identity(
                                        direction,
                                        kind,
                                        &canonical_target_path,
                                        &reason,
                                    ),
                                ));
                            }
                            (resolved, "dependency-header", canonical_target_path)
                        }
                    }
                    Err(error) => {
                        diagnostics.push(target_path_diagnostic(
                            relative,
                            line_number,
                            &line,
                            target,
                            error,
                            declaration_identity(direction, kind, target, &reason),
                        ));
                        (
                            None,
                            "dependency-header",
                            normalize_declaration_component(target),
                        )
                    }
                };
            declarations.push(DependencyDeclaration {
                declaration_id: hash_text(&format!(
                    "{snapshot_id}\0{relative}\0{line_number}\0{line}"
                )),
                source_identity_id: identity_by_path.get(relative).cloned().unwrap_or_default(),
                declared_direction: direction.to_string(),
                declared_kind: kind.to_string(),
                declared_target: target.to_string(),
                canonical_target,
                resolved_target_identity_id: resolved,
                source_span: source_span(relative, line_number, &line),
                reason,
                raw_line_hash: hash_text(&line),
                attestation_key: attestation_key.to_string(),
                snapshot_id: snapshot_id.clone(),
            });
        }
    }
    let git_head_after = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
    let candidates_after = source_candidates(&root, &surface_manifest, &git_head_after)?;
    let candidate_paths_after = candidates_after
        .iter()
        .map(|candidate| candidate.relative.clone())
        .collect::<Vec<_>>();
    let source_fingerprint_after =
        source_fingerprint_for_candidates(&candidates_after, &surface_manifest)?;
    let index_hash_after = hash_bytes(&git_bytes(&root, &["ls-files", "--stage", "-z"])?);
    let status_after = source_status_bytes(&root, &surface_manifest)?;
    let captured_after_hash = snapshot_capture_hash(
        &request.profile,
        &git_head_after,
        &index_hash_after,
        &hash_bytes(&status_after),
        &source_fingerprint_after,
    );
    if candidate_paths_after != candidate_paths || captured_after_hash != captured_before_hash {
        return Err(ManifestError::SnapshotInconsistent(
            "git/filesystem state changed during snapshot capture".to_string(),
        ));
    }
    let surface_relations = manifest_surface_relations(
        &surface_manifest,
        &source_identities,
        &excluded_set,
        &snapshot_id,
    )?;
    Ok(ManifestSnapshot {
        header: SnapshotHeader {
            snapshot_id: snapshot_id.clone(),
            parent_repo_id: root.display().to_string(),
            root_realpath: root.display().to_string(),
            git_head,
            git_index_tree: index_hash,
            git_worktree_dirty: !dirty_paths.is_empty(),
            git_status_hash: status_hash,
            dirty_paths,
            agentcanon_pin: String::new(),
            schema_version: SNAPSHOT_SCHEMA_VERSION.to_string(),
            tool_version: "agent-canon.graph.v1".to_string(),
            profile: request.profile.clone(),
            path_sort: "UTF-8-byte-order".to_string(),
            source_fingerprint: source_fingerprint_before,
            captured_before_hash,
            captured_after_hash,
            snapshot_consistent: true,
        },
        source_identities,
        declarations,
        source_exclusions,
        surface_relations,
        source_universe: SourceUniverse {
            candidate_paths,
            excluded_paths,
            eligible_paths,
            eligible_equals_candidate_minus_excluded: true,
            union_equals_candidate: true,
            intersection_empty: true,
        },
        diagnostics,
        manifests,
    })
}

pub(crate) fn write_snapshot_jsonl(
    snapshot: &ManifestSnapshot,
    writer: &mut impl Write,
) -> Result<(), ManifestError> {
    let header = json!({"record_type":"header","schema_version":SNAPSHOT_SCHEMA_VERSION,"snapshot_id":snapshot.header.snapshot_id,"git_head":snapshot.header.git_head,"git_index_tree":snapshot.header.git_index_tree,"agentcanon_pin":snapshot.header.agentcanon_pin,"source_fingerprint":snapshot.header.source_fingerprint,"profile":snapshot.header.profile,"dirty_paths":snapshot.header.dirty_paths});
    writeln!(
        writer,
        "{}",
        serde_json::to_string(&header)
            .map_err(|error| ManifestError::Transport(error.to_string()))?
    )
    .map_err(|error| ManifestError::Io(error.to_string()))?;
    for identity in &snapshot.source_identities {
        let value = json!({"record_type":"source_identity","identity_id":identity.identity_id,"authority_id":identity.authority_id,"logical_id":identity.logical_id,"repo_rel_path":identity.repo_rel_path,"canonical_locator":identity.canonical_locator,"alternate_locators":identity.alternate_locators,"locator_kind":identity.locator_kind,"path_role":identity.path_role,"file_mode":identity.file_mode,"exists":identity.exists,"is_dirty":identity.is_dirty,"content_hash":identity.content_hash,"git_blob_or_gitlink":identity.git_blob_or_gitlink,"submodule_commit":identity.submodule_commit,"snapshot_id":identity.snapshot_id});
        writeln!(
            writer,
            "{}",
            serde_json::to_string(&value)
                .map_err(|error| ManifestError::Transport(error.to_string()))?
        )
        .map_err(|error| ManifestError::Io(error.to_string()))?;
    }
    for exclusion in &snapshot.source_exclusions {
        let value = json!({"record_type":"source_exclusion","source_exclusion_id":exclusion.source_exclusion_id,"source_identity_id":exclusion.source_identity_id,"repo_rel_path":exclusion.repo_rel_path,"reason_code":exclusion.reason_code,"rule_id":exclusion.rule_id,"scope":exclusion.scope,"evidence_id":exclusion.evidence_id,"covered":exclusion.covered,"snapshot_id":exclusion.snapshot_id});
        writeln!(
            writer,
            "{}",
            serde_json::to_string(&value)
                .map_err(|error| ManifestError::Transport(error.to_string()))?
        )
        .map_err(|error| ManifestError::Io(error.to_string()))?;
    }
    for relation in &snapshot.surface_relations {
        let value = json!({"record_type":"surface_relation","relation_id":relation.relation_id,"relation_type":relation.relation_type,"source_identity_id":relation.source_identity_id,"target_identity_id":relation.target_identity_id,"source_path":relation.source_path,"target_path":relation.target_path,"owner_class":relation.owner_class,"surface_mode":relation.surface_mode,"content_hash_equal":relation.content_hash_equal,"evidence_id":relation.evidence_id,"status":relation.status,"snapshot_id":relation.snapshot_id});
        writeln!(
            writer,
            "{}",
            serde_json::to_string(&value)
                .map_err(|error| ManifestError::Transport(error.to_string()))?
        )
        .map_err(|error| ManifestError::Io(error.to_string()))?;
    }
    let universe = json!({"record_type":"source_universe","candidate_paths":snapshot.source_universe.candidate_paths,"excluded_paths":snapshot.source_universe.excluded_paths,"eligible_paths":snapshot.source_universe.eligible_paths,"eligible_equals_candidate_minus_excluded":snapshot.source_universe.eligible_equals_candidate_minus_excluded,"union_equals_candidate":snapshot.source_universe.union_equals_candidate,"intersection_empty":snapshot.source_universe.intersection_empty});
    writeln!(
        writer,
        "{}",
        serde_json::to_string(&universe)
            .map_err(|error| ManifestError::Transport(error.to_string()))?
    )
    .map_err(|error| ManifestError::Io(error.to_string()))?;
    for declaration in &snapshot.declarations {
        let value = json!({"record_type":"dependency_declaration","declaration_id":declaration.declaration_id,"source_identity_id":declaration.source_identity_id,"declared_direction":declaration.declared_direction,"declared_kind":declaration.declared_kind,"declared_target":declaration.declared_target,"canonical_target":declaration.canonical_target,"resolved_target_identity_id":declaration.resolved_target_identity_id,"source_span": {"path":declaration.source_span.path,"start_line":declaration.source_span.start_line,"start_column":declaration.source_span.start_column,"end_line":declaration.source_span.end_line,"end_column":declaration.source_span.end_column},"reason":declaration.reason,"attestation_key":declaration.attestation_key,"snapshot_id":declaration.snapshot_id});
        writeln!(
            writer,
            "{}",
            serde_json::to_string(&value)
                .map_err(|error| ManifestError::Transport(error.to_string()))?
        )
        .map_err(|error| ManifestError::Io(error.to_string()))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        declaration_identity, diagnostic_identity_json, manifest_lines,
        resolve_source_relative_target, source_diagnostic,
        source_path_is_historical_dependency_record, source_span, target_path_diagnostic_code,
        TargetPathError, SOURCE_DIAGNOSTIC_SCHEMA,
    };
    use std::path::Path;

    #[test]
    fn python_dependency_manifest_requires_line_comments() {
        let docstring = "\"\"\"\n@dependency-start\ncontract implementation\nresponsibility not grammar\n@dependency-end\n\"\"\"\n";
        assert!(manifest_lines(Path::new("tool.py"), docstring).is_empty());

        let comments = "# @dependency-start\n# contract implementation\n# responsibility canonical\n# upstream design docs/spec.md reason\n# @dependency-end\n\"\"\"module docs\"\"\"\n";
        let lines = manifest_lines(Path::new("tool.py"), comments);
        assert_eq!(lines[0].1, "contract implementation");
        assert_eq!(lines[2].1, "upstream design docs/spec.md reason");
    }

    #[test]
    fn rust_dependency_manifest_rejects_block_comment_and_unclosed_block() {
        let block =
            "/*\n * @dependency-start\n * contract implementation\n * @dependency-end\n */\n";
        assert!(manifest_lines(Path::new("tool.rs"), block).is_empty());
        assert!(manifest_lines(
            Path::new("tool.rs"),
            "// @dependency-start\n// contract implementation\n"
        )
        .is_empty());
        assert_eq!(
            manifest_lines(
                Path::new("tool.rs"),
                "// @dependency-start\n// contract implementation\n// @dependency-end\n"
            )[0]
            .1,
            "contract implementation"
        );
    }

    #[test]
    fn closed_issues_are_historical_dependency_records() {
        assert!(source_path_is_historical_dependency_record(
            "issues/closed/AC-20260612-wave-activation-launcher-gap.md"
        ));
        assert!(!source_path_is_historical_dependency_record(
            "issues/open/AC-20260612-active-finding.md"
        ));
    }

    #[test]
    fn source_relative_targets_resolve_parent_current_and_bare_sibling() {
        assert_eq!(
            resolve_source_relative_target(
                ".agents/skills/academic-writing/SKILL.md",
                "../../../agents/canonical/skills.md"
            ),
            Ok("agents/canonical/skills.md".to_string())
        );
        assert_eq!(
            resolve_source_relative_target("documents/design/example.md", "./dependency.md"),
            Ok("documents/design/dependency.md".to_string())
        );
        assert_eq!(
            resolve_source_relative_target("documents/design/example.md", "sibling.md"),
            Ok("documents/design/sibling.md".to_string())
        );
    }

    #[test]
    fn source_relative_targets_reject_absolute_paths_and_root_escape() {
        assert_eq!(
            resolve_source_relative_target("documents/design/example.md", "/README.md"),
            Err(TargetPathError::Absolute)
        );
        assert_eq!(
            target_path_diagnostic_code(TargetPathError::Absolute),
            "target-absolute"
        );
        assert_eq!(
            resolve_source_relative_target("README.md", "../outside.md"),
            Err(TargetPathError::EscapesRoot)
        );
        assert_eq!(
            target_path_diagnostic_code(TargetPathError::EscapesRoot),
            "target-escapes-root"
        );
    }

    #[test]
    fn diagnostic_identity_normalizes_declaration_and_excludes_location_and_message() {
        let declaration = declaration_identity(
            " upstream ",
            " design ",
            "documents/target.md",
            "reason   with   spaces",
        );
        let moved = source_diagnostic(
            "target-unresolved",
            "different:message:format".to_string(),
            "error",
            source_span("documents/source.md", 18, "moved line"),
            declaration_identity(
                "upstream",
                "design",
                "documents/target.md",
                "reason with spaces",
            ),
        );
        let original = source_diagnostic(
            "target-unresolved",
            "documents/source.md:3:documents/target.md".to_string(),
            "error",
            source_span("documents/source.md", 3, "original line"),
            declaration,
        );
        let original_payload = diagnostic_identity_json(&original);
        let moved_payload = diagnostic_identity_json(&moved);
        for field in ["code", "source", "target", "declaration"] {
            assert_eq!(
                original_payload[field], moved_payload[field],
                "field={field}"
            );
        }
        assert_ne!(
            original_payload["source_span"], moved_payload["source_span"],
            "location evidence remains separate from identity"
        );

        let direction_change = declaration_identity(
            "downstream",
            "design",
            "documents/target.md",
            "reason with spaces",
        );
        let kind_change = declaration_identity(
            "upstream",
            "implementation",
            "documents/target.md",
            "reason with spaces",
        );
        let reason_change = declaration_identity(
            "upstream",
            "design",
            "documents/target.md",
            "different reason",
        );
        assert_ne!(
            original.declaration.canonical_declaration,
            direction_change.canonical_declaration
        );
        assert_ne!(
            original.declaration.canonical_declaration,
            kind_change.canonical_declaration
        );
        assert_ne!(
            original.declaration.canonical_declaration,
            reason_change.canonical_declaration
        );
    }

    #[test]
    fn malformed_manifest_diagnostic_has_nonempty_typed_identity() {
        let diagnostic = source_diagnostic(
            "manifest-grammar",
            "source.md:7:upstream design".to_string(),
            "error",
            source_span("source.md", 7, "upstream design"),
            declaration_identity("upstream", "design", "", ""),
        );
        let payload = diagnostic_identity_json(&diagnostic);
        assert_eq!(payload["schema"], SOURCE_DIAGNOSTIC_SCHEMA);
        for field in ["code", "source", "target", "declaration"] {
            assert!(payload[field]
                .as_str()
                .is_some_and(|value| !value.is_empty()));
        }
        for field in ["direction", "kind", "target", "reason"] {
            assert!(payload["declaration_components"][field]
                .as_str()
                .is_some_and(|value| !value.is_empty()));
        }
        assert_eq!(payload["source_span"]["path"], "source.md");
        assert_eq!(payload["source_span"]["start_line"], 7);
    }
}
