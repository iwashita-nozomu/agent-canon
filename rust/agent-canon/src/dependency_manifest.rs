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

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceSpan {
    pub path: String,
    pub start_line: usize,
    pub start_column: usize,
    pub end_line: usize,
    pub end_column: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Diagnostic {
    pub code: String,
    pub message: String,
    pub severity: String,
    pub source_span: Option<SourceSpan>,
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
    owner: String,
    surface_class: String,
    local_override_allowed: bool,
    optional: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SurfaceManifestSnapshot {
    prefix: String,
    entries: Vec<SurfaceManifestEntry>,
    requires_parent_gitlink: bool,
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
struct GitlinkAuthority {
    path: String,
    staged_oid: String,
    submodule_head: String,
    submodule_root: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum GitlinkIndexState {
    Missing,
    NonGitlinkMode { mode: String },
    Conflict { stage: String },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ManifestError {
    Io(String),
    Git(String),
    Transport(String),
    SurfaceManifest(String),
    Gitlink(String),
    GitlinkIndexState {
        path: String,
        state: GitlinkIndexState,
    },
    GitlinkHeadMismatch {
        path: String,
        staged_oid: String,
        head_oid: String,
    },
    SnapshotInconsistent(String),
}

impl fmt::Display for ManifestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(message)
            | Self::Git(message)
            | Self::Transport(message)
            | Self::SurfaceManifest(message)
            | Self::Gitlink(message)
            | Self::SnapshotInconsistent(message) => formatter.write_str(message),
            Self::GitlinkIndexState { path, state } => match state {
                GitlinkIndexState::Missing => {
                    write!(formatter, "gitlink_index_state: path={path} state=missing")
                }
                GitlinkIndexState::NonGitlinkMode { mode } => write!(
                    formatter,
                    "gitlink_index_state: path={path} state=non-160000 mode={mode}"
                ),
                GitlinkIndexState::Conflict { stage } => write!(
                    formatter,
                    "gitlink_index_state: path={path} state=conflict stage={stage}"
                ),
            },
            Self::GitlinkHeadMismatch {
                path,
                staged_oid,
                head_oid,
            } => write!(
                formatter,
                "gitlink_head_mismatch: path={path} staged_oid={staged_oid} submodule_head={head_oid}"
            ),
        }
    }
}

fn hash_bytes(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
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

fn git_bytes_owned(root: &Path, args: &[String]) -> Result<Vec<u8>, ManifestError> {
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

fn surface_manifest_script(root: &Path) -> Result<(PathBuf, bool), ManifestError> {
    let parent_script = root.join("vendor/agent-canon/tools/agent_tools/surface_manifest.py");
    if parent_script.is_file() {
        return Ok((parent_script, true));
    }
    let standalone_script = root.join("tools/agent_tools/surface_manifest.py");
    if standalone_script.is_file() {
        return Ok((standalone_script, false));
    }
    Err(ManifestError::SurfaceManifest(
        "surface_manifest_snapshot: canonical Python producer is missing".to_string(),
    ))
}

fn load_surface_manifest_snapshot(root: &Path) -> Result<SurfaceManifestSnapshot, ManifestError> {
    let (script, requires_parent_gitlink) = surface_manifest_script(root)?;
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
            "vendor/agent-canon",
            "--manifest",
            "documents/runtime/shared-runtime-surfaces.toml",
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
                "class",
                "local_override_allowed",
                "mode",
                "optional",
                "owner",
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
        let owner_value = required_json_string(entry, "owner", &owner)?;
        let surface_class = required_json_string(entry, "class", &owner)?;
        if matches!(mode.as_str(), "symlink" | "copy") && source.is_empty() {
            return Err(ManifestError::SurfaceManifest(format!(
                "surface_manifest_snapshot: {path} projection source is empty"
            )));
        }
        entries.push(SurfaceManifestEntry {
            path,
            mode,
            source,
            owner: owner_value,
            surface_class,
            local_override_allowed: required_json_bool(entry, "local_override_allowed", &owner)?,
            optional: required_json_bool(entry, "optional", &owner)?,
        });
    }
    Ok(SurfaceManifestSnapshot {
        prefix,
        entries,
        requires_parent_gitlink,
    })
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
) -> Diagnostic {
    Diagnostic {
        code: target_path_diagnostic_code(error).to_string(),
        message: format!("{relative}:{line_number}:{target}"),
        severity: "error".to_string(),
        source_span: Some(SourceSpan {
            path: relative.to_string(),
            start_line: line_number,
            start_column: 1,
            end_line: line_number,
            end_column: line.len() + 1,
        }),
    }
}

fn target_unresolved_diagnostic(
    relative: &str,
    line_number: usize,
    line: &str,
    target: &str,
) -> Diagnostic {
    Diagnostic {
        code: "target-unresolved".to_string(),
        message: format!("{relative}:{line_number}:{target}"),
        severity: "error".to_string(),
        source_span: Some(SourceSpan {
            path: relative.to_string(),
            start_line: line_number,
            start_column: 1,
            end_line: line_number,
            end_column: line.len() + 1,
        }),
    }
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

fn source_candidate_is_explicitly_excluded(candidate: &SourceCandidate) -> bool {
    source_path_is_explicitly_excluded(&candidate.relative)
        || (candidate.locator_kind == "submodule-path"
            && source_path_is_explicitly_excluded(&candidate.canonical_locator))
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

fn staged_gitlink(root: &Path, prefix: &str) -> Result<String, ManifestError> {
    let bytes = git_bytes(root, &["ls-files", "--stage", "-z"])?;
    let mut found = None;
    for record in bytes
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
    {
        let (metadata, path) = split_tab_record(record).ok_or_else(|| {
            ManifestError::Gitlink("gitlink index record is malformed".to_string())
        })?;
        let fields = metadata.split(|byte| *byte == b' ').collect::<Vec<_>>();
        if fields.len() != 3 {
            return Err(ManifestError::Gitlink(
                "gitlink index metadata is malformed".to_string(),
            ));
        }
        if path != prefix.as_bytes() {
            continue;
        }
        let stage = String::from_utf8_lossy(fields[2]).to_string();
        if stage != "0" {
            return Err(ManifestError::GitlinkIndexState {
                path: prefix.to_string(),
                state: GitlinkIndexState::Conflict { stage },
            });
        }
        if fields[0] != b"160000" {
            return Err(ManifestError::GitlinkIndexState {
                path: prefix.to_string(),
                state: GitlinkIndexState::NonGitlinkMode {
                    mode: String::from_utf8_lossy(fields[0]).to_string(),
                },
            });
        }
        {
            let oid = String::from_utf8(fields[1].to_vec()).map_err(|error| {
                ManifestError::Gitlink(format!("gitlink index OID is not UTF-8: {error}"))
            })?;
            if found.replace(oid).is_some() {
                return Err(ManifestError::Gitlink(
                    "gitlink index contains duplicate path".to_string(),
                ));
            }
        }
    }
    found.ok_or_else(|| ManifestError::GitlinkIndexState {
        path: prefix.to_string(),
        state: GitlinkIndexState::Missing,
    })
}

fn gitlink_authority(
    root: &Path,
    manifest: &SurfaceManifestSnapshot,
) -> Result<Option<GitlinkAuthority>, ManifestError> {
    if !manifest.requires_parent_gitlink {
        return Ok(None);
    }
    let staged_oid = staged_gitlink(root, &manifest.prefix)?;
    let submodule_root = root.join(&manifest.prefix);
    let submodule_head = git_text(&submodule_root, &["rev-parse", "--verify", "HEAD"])
        .map_err(|error| ManifestError::Gitlink(format!("submodule HEAD unavailable: {error}")))?;
    if staged_oid != submodule_head {
        return Err(ManifestError::GitlinkHeadMismatch {
            path: manifest.prefix.clone(),
            staged_oid,
            head_oid: submodule_head,
        });
    }
    Ok(Some(GitlinkAuthority {
        path: manifest.prefix.clone(),
        staged_oid,
        submodule_head,
        submodule_root,
    }))
}

fn split_tab_record(record: &[u8]) -> Option<(&[u8], &[u8])> {
    let index = record.iter().position(|byte| *byte == b'\t')?;
    Some((&record[..index], &record[index + 1..]))
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PinnedGitEntry {
    relative: String,
    mode: String,
    object_type: String,
    object_id: String,
}

fn pinned_git_entries(authority: &GitlinkAuthority) -> Result<Vec<PinnedGitEntry>, ManifestError> {
    let args = vec![
        "ls-tree".to_string(),
        "--full-tree".to_string(),
        "-r".to_string(),
        "-t".to_string(),
        "-z".to_string(),
        authority.staged_oid.clone(),
    ];
    let bytes = git_bytes_owned(&authority.submodule_root, &args).map_err(|error| {
        ManifestError::Gitlink(format!("pinned submodule tree unavailable: {error}"))
    })?;
    let mut entries = Vec::new();
    for record in bytes
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
    {
        let (metadata, path) = split_tab_record(record).ok_or_else(|| {
            ManifestError::Gitlink("pinned submodule tree record is malformed".to_string())
        })?;
        let fields = metadata.split(|byte| *byte == b' ').collect::<Vec<_>>();
        if fields.len() != 3 {
            return Err(ManifestError::Gitlink(
                "pinned submodule tree metadata is malformed".to_string(),
            ));
        }
        let relative = String::from_utf8(path.to_vec()).map_err(|error| {
            ManifestError::Gitlink(format!("pinned submodule path is not UTF-8: {error}"))
        })?;
        let mode = String::from_utf8(fields[0].to_vec()).map_err(|error| {
            ManifestError::Gitlink(format!("pinned submodule mode is not UTF-8: {error}"))
        })?;
        let object_type = String::from_utf8(fields[1].to_vec()).map_err(|error| {
            ManifestError::Gitlink(format!(
                "pinned submodule object type is not UTF-8: {error}"
            ))
        })?;
        let object_id = String::from_utf8(fields[2].to_vec()).map_err(|error| {
            ManifestError::Gitlink(format!("pinned submodule object OID is not UTF-8: {error}"))
        })?;
        if !matches!(object_type.as_str(), "blob" | "tree") {
            return Err(ManifestError::Gitlink(format!(
                "pinned submodule object type is unsupported: {object_type}"
            )));
        }
        entries.push(PinnedGitEntry {
            relative,
            mode,
            object_type,
            object_id,
        });
    }
    entries.sort_by(|left, right| left.relative.cmp(&right.relative));
    Ok(entries)
}

fn pinned_git_object_bytes(
    authority: &GitlinkAuthority,
    entry: &PinnedGitEntry,
) -> Result<Vec<u8>, ManifestError> {
    if entry.object_type == "tree" {
        return Ok(Vec::new());
    }
    let args = vec![
        "cat-file".to_string(),
        "blob".to_string(),
        entry.object_id.clone(),
    ];
    git_bytes_owned(&authority.submodule_root, &args).map_err(|error| {
        ManifestError::Gitlink(format!(
            "pinned submodule object unavailable for {}: {error}",
            entry.relative
        ))
    })
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
        if !source_candidate_is_explicitly_excluded(candidate) {
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
    authority: Option<&GitlinkAuthority>,
) -> Result<Vec<SourceCandidate>, ManifestError> {
    let authority_id = authority
        .map(|value| format!("parent-gitlink:160000:{}:{}", value.path, value.staged_oid))
        .unwrap_or_else(|| format!("standalone-git:{git_head}"));
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
    let Some(authority) = authority else {
        candidates.sort_by(|left, right| left.relative.cmp(&right.relative));
        return Ok(candidates);
    };
    let root_candidate = SourceCandidate {
        relative: authority.path.clone(),
        authority_id: authority_id.clone(),
        canonical_locator: authority.path.clone(),
        locator_kind: "gitlink".to_string(),
        path_role: "gitlink".to_string(),
        file_mode: "160000".to_string(),
        exists: true,
        bytes: authority.staged_oid.as_bytes().to_vec(),
        git_blob_or_gitlink: authority.staged_oid.clone(),
        submodule_commit: authority.submodule_head.clone(),
    };
    candidates.push(root_candidate);
    for entry in pinned_git_entries(authority)? {
        let bytes = pinned_git_object_bytes(authority, &entry)?;
        let relative = format!("{}/{}", authority.path, entry.relative);
        let path_role = if entry.object_type == "tree" {
            "submodule-tree"
        } else {
            "source"
        };
        candidates.push(SourceCandidate {
            relative,
            authority_id: authority_id.clone(),
            canonical_locator: entry.relative,
            locator_kind: "submodule-path".to_string(),
            path_role: path_role.to_string(),
            file_mode: entry.mode,
            exists: true,
            bytes,
            git_blob_or_gitlink: entry.object_id,
            submodule_commit: authority.submodule_head.clone(),
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
    authority: Option<&GitlinkAuthority>,
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
    if let Some(authority) = authority {
        Ok(Some(format!("{}/{}", authority.path, normalized)))
    } else {
        let _ = manifest;
        Ok(Some(normalized))
    }
}

fn canonicalize_surface_path(
    manifest: &SurfaceManifestSnapshot,
    authority: Option<&GitlinkAuthority>,
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
        let replace = selected.map_or(true, |(selected_entry, _)| {
            let selected_view = selected_entry.path.trim_end_matches('/');
            view.len() > selected_view.len()
                || (view.len() == selected_view.len() && view < selected_view)
        });
        if replace {
            selected = Some((entry, suffix));
        }
    }
    if let Some((entry, suffix)) = selected {
        let source = if let Some(authority) = authority {
            format!("{}/{}", authority.path, entry.source)
        } else {
            entry.source.clone()
        };
        let joined = format!("{source}{suffix}");
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
    authority: Option<&GitlinkAuthority>,
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
        let Some(target_path) = surface_target_path(manifest, entry, authority)? else {
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
            owner_class: format!("{}:{}", entry.owner, entry.surface_class),
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
    relative: &str,
) -> (&'static str, &'static str) {
    if manifest.entries.iter().any(|entry| {
        entry.path == relative
            && entry.source.is_empty()
            && (entry.mode == "repo_state"
                || matches!(
                    entry.surface_class.as_str(),
                    "generated_evidence" | "transaction_state" | "projection_view"
                ))
    }) {
        ("generated_state", "surface-manifest-state")
    } else {
        ("generated_output", "source-owner-exclusion")
    }
}

fn source_status_bytes(root: &Path) -> Result<Vec<u8>, ManifestError> {
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
        if paths
            .iter()
            .all(|path| source_path_is_explicitly_excluded(path))
        {
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
) -> Result<SnapshotProbe, ManifestError> {
    let root = fs::canonicalize(root).map_err(|error| ManifestError::Io(error.to_string()))?;
    let surface_manifest = load_surface_manifest_snapshot(&root)?;
    let head = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
    let authority = gitlink_authority(&root, &surface_manifest)?;
    let candidates = source_candidates(&root, &surface_manifest, &head, authority.as_ref())?;
    let source_fingerprint = source_fingerprint_for_candidates(&candidates)?;
    let status = source_status_bytes(&root)?;
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
    let surface_manifest = load_surface_manifest_snapshot(&root)?;
    let git_head = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
    let authority = gitlink_authority(&root, &surface_manifest)?;
    let candidates = source_candidates(&root, &surface_manifest, &git_head, authority.as_ref())?;
    let candidate_paths = candidates
        .iter()
        .map(|candidate| candidate.relative.clone())
        .collect::<Vec<_>>();
    let source_fingerprint_before = source_fingerprint_for_candidates(&candidates)?;
    let index_hash = hash_bytes(&git_bytes(&root, &["ls-files", "--stage", "-z"])?);
    let status_bytes = source_status_bytes(&root)?;
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
    let mut excluded_set = candidates
        .iter()
        .filter(|candidate| source_candidate_is_explicitly_excluded(candidate))
        .map(|candidate| candidate.relative.clone())
        .collect::<BTreeSet<_>>();
    for entry in &surface_manifest.entries {
        if entry.source.is_empty()
            && (entry.mode == "repo_state"
                || matches!(
                    entry.surface_class.as_str(),
                    "generated_evidence" | "transaction_state" | "projection_view"
                ))
        {
            excluded_set.insert(entry.path.clone());
        }
    }
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
            let (reason_code, rule_id) = exclusion_metadata(&surface_manifest, relative);
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
        if authority.is_some()
            && surface_manifest.entries.iter().any(|entry| {
                entry.path == relative.as_str() && matches!(entry.mode.as_str(), "symlink" | "copy")
            })
        {
            // Parent root views are projections; parse their pinned canonical source once.
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
            let mut fields = line.splitn(4, ' ');
            let direction = fields.next().unwrap_or_default();
            let kind = fields.next().unwrap_or_default();
            let target = fields.next().unwrap_or_default();
            let reason = fields.next().unwrap_or_default().trim().to_string();
            if !matches!(direction, "upstream" | "downstream") {
                continue;
            }
            if !matches!(kind, "design" | "implementation" | "environment")
                || target.is_empty()
                || reason.is_empty()
            {
                diagnostics.push(Diagnostic {
                    code: "manifest-grammar".to_string(),
                    message: format!("{relative}:{line_number}:{line}"),
                    severity: "error".to_string(),
                    source_span: None,
                });
                continue;
            }
            let resolved = match resolve_source_relative_target(relative, target) {
                Ok(target_path) => {
                    let canonical_target_path = canonicalize_surface_path(
                        &surface_manifest,
                        authority.as_ref(),
                        &target_path,
                    )?;
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
                        ));
                    }
                    resolved
                }
                Err(error) => {
                    diagnostics.push(target_path_diagnostic(
                        relative,
                        line_number,
                        &line,
                        target,
                        error,
                    ));
                    None
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
                resolved_target_identity_id: resolved,
                source_span: SourceSpan {
                    path: relative.clone(),
                    start_line: line_number,
                    start_column: 1,
                    end_line: line_number,
                    end_column: line.len() + 1,
                },
                reason,
                raw_line_hash: hash_text(&line),
                attestation_key: "dependency-header".to_string(),
                snapshot_id: snapshot_id.clone(),
            });
        }
    }
    let git_head_after = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
    let authority_after = gitlink_authority(&root, &surface_manifest)?;
    let candidates_after = source_candidates(
        &root,
        &surface_manifest,
        &git_head_after,
        authority_after.as_ref(),
    )?;
    let candidate_paths_after = candidates_after
        .iter()
        .map(|candidate| candidate.relative.clone())
        .collect::<Vec<_>>();
    let source_fingerprint_after = source_fingerprint_for_candidates(&candidates_after)?;
    let index_hash_after = hash_bytes(&git_bytes(&root, &["ls-files", "--stage", "-z"])?);
    let status_after = source_status_bytes(&root)?;
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
        authority.as_ref(),
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
            agentcanon_pin: authority
                .as_ref()
                .map(|value| value.staged_oid.clone())
                .unwrap_or_default(),
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
        let value = json!({"record_type":"dependency_declaration","declaration_id":declaration.declaration_id,"source_identity_id":declaration.source_identity_id,"declared_direction":declaration.declared_direction,"declared_kind":declaration.declared_kind,"declared_target":declaration.declared_target,"resolved_target_identity_id":declaration.resolved_target_identity_id,"source_span": {"path":declaration.source_span.path,"start_line":declaration.source_span.start_line,"start_column":declaration.source_span.start_column,"end_line":declaration.source_span.end_line,"end_column":declaration.source_span.end_column},"reason":declaration.reason,"snapshot_id":declaration.snapshot_id});
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
        manifest_lines, resolve_source_relative_target, target_path_diagnostic_code,
        TargetPathError,
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
}
