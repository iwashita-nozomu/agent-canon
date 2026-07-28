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
pub(crate) enum ManifestError {
    Io(String),
    Git(String),
    Transport(String),
    SnapshotInconsistent(String),
}

impl fmt::Display for ManifestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(message)
            | Self::Git(message)
            | Self::Transport(message)
            | Self::SnapshotInconsistent(message) => formatter.write_str(message),
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
    file_mode: &'static str,
    exists: bool,
}

fn missing_source_path() -> SourcePathRead {
    SourcePathRead {
        bytes: Vec::new(),
        file_mode: "100644",
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
            file_mode: "120000",
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
            file_mode: "100644",
            exists: true,
        });
    }
    Err(ManifestError::Io(format!(
        "source path is not a regular file or symlink: {}",
        path.display()
    )))
}

fn source_fingerprint_for_paths(root: &Path, paths: &[String]) -> Result<String, ManifestError> {
    let mut rows = Vec::new();
    let mut processed = BTreeSet::new();
    for (index, relative) in paths.iter().enumerate() {
        if !processed.insert(relative.clone()) {
            return Err(ManifestError::SnapshotInconsistent(
                "candidate source path was processed twice".to_string(),
            ));
        }
        let remaining_before = paths.len() - index;
        if !source_path_is_explicitly_excluded(relative) {
            let source = read_source_path(root, relative)?;
            rows.push(format!(
                "{}\0{}\0{}\0{}\n",
                relative,
                source.exists,
                source.file_mode,
                hash_bytes(&source.bytes)
            ));
        }
        let remaining_after = paths.len() - processed.len();
        if remaining_after >= remaining_before {
            return Err(ManifestError::SnapshotInconsistent(
                "candidate source measure did not decrease".to_string(),
            ));
        }
    }
    if processed.len() != paths.len() {
        return Err(ManifestError::SnapshotInconsistent(
            "candidate source processed set is incomplete".to_string(),
        ));
    }
    Ok(hash_text(&rows.concat()))
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
    let candidate_paths = git_visible_paths(&root)?;
    let source_fingerprint = source_fingerprint_for_paths(&root, &candidate_paths)?;
    let status = source_status_bytes(&root)?;
    let head = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
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
    let candidate_paths = git_visible_paths(&root)?;
    let source_fingerprint_before = source_fingerprint_for_paths(&root, &candidate_paths)?;
    let git_head = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
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
    let excluded_paths = candidate_paths
        .iter()
        .filter(|path| source_path_is_explicitly_excluded(path))
        .cloned()
        .collect::<Vec<_>>();
    let excluded_set = excluded_paths.iter().cloned().collect::<BTreeSet<_>>();
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
    let identity_by_path = candidate_paths
        .iter()
        .map(|path| (path.clone(), hash_text(&format!("source:{path}"))))
        .collect::<BTreeMap<_, _>>();
    let mut source_identities = Vec::new();
    let mut source_exclusions = Vec::new();
    let mut declarations = Vec::new();
    let mut manifests = BTreeMap::new();
    let mut diagnostics = Vec::new();
    let mut processed = BTreeSet::new();
    for (index, relative) in candidate_paths.iter().enumerate() {
        if !processed.insert(relative.clone())
            || candidate_paths.len() - processed.len() >= candidate_paths.len() - index
        {
            return Err(ManifestError::SnapshotInconsistent(
                "candidate source processing is not monotone".to_string(),
            ));
        }
        let path = root.join(relative);
        let source = read_source_path(&root, relative)?;
        let identity_id = identity_by_path.get(relative).cloned().unwrap_or_default();
        let blob = git_text(&root, &["hash-object", "--", relative])
            .or_else(|_| git_text(&root, &["rev-parse", &format!(":{relative}")]))
            .unwrap_or_default();
        source_identities.push(SourceIdentity {
            identity_id: identity_id.clone(),
            logical_id: format!("source:{relative}"),
            repo_rel_path: relative.clone(),
            canonical_locator: relative.clone(),
            alternate_locators: Vec::new(),
            locator_kind: "repo-relative".to_string(),
            path_role: "source".to_string(),
            file_mode: source.file_mode.to_string(),
            exists: source.exists,
            is_dirty: dirty_set.contains(relative),
            content_hash: hash_bytes(&source.bytes),
            git_blob_or_gitlink: blob,
            submodule_commit: String::new(),
            snapshot_id: snapshot_id.clone(),
        });
        if excluded_set.contains(relative) {
            source_exclusions.push(SourceExclusion {
                source_exclusion_id: hash_text(&format!("exclude:{identity_id}")),
                source_identity_id: identity_id,
                repo_rel_path: relative.clone(),
                reason_code: "generated_output".to_string(),
                rule_id: "source-owner-exclusion".to_string(),
                scope: relative.clone(),
                evidence_id: hash_text(relative),
                covered: true,
                snapshot_id: snapshot_id.clone(),
            });
            continue;
        }
        let Ok(text) = String::from_utf8(source.bytes) else {
            continue;
        };
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
                    let resolved = identity_by_path
                        .get(&target_path)
                        .filter(|_| !excluded_set.contains(&target_path))
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
    let candidate_paths_after = git_visible_paths(&root)?;
    let source_fingerprint_after = source_fingerprint_for_paths(&root, &candidate_paths_after)?;
    let git_head_after = git_text(&root, &["rev-parse", "--verify", "HEAD"])?;
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
        surface_relations: Vec::new(),
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
    let header = json!({"record_type":"header","schema_version":SNAPSHOT_SCHEMA_VERSION,"snapshot_id":snapshot.header.snapshot_id,"git_head":snapshot.header.git_head,"source_fingerprint":snapshot.header.source_fingerprint,"profile":snapshot.header.profile,"dirty_paths":snapshot.header.dirty_paths});
    writeln!(
        writer,
        "{}",
        serde_json::to_string(&header)
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
