// @dependency-start
// contract implementation
// responsibility Owns the canonical dependency-manifest grammar and immutable source snapshots.
// upstream design ../../../documents/dependency-manifest-design.md manifest grammar and transport contract
// upstream design ../../../documents/structured-analysis/graph-dsl.md typed graph record and provenance contract
// downstream implementation main.rs dispatches the dependency-manifest CLI
// downstream implementation structured_analysis.rs consumes the snapshot transport in a later unit
// downstream implementation semantic_index.rs receives graph-derived context in a later unit
// downstream implementation ../../../tools/agent_tools/dependency_manifest_records.py consumes normalized records in a later unit
// @dependency-end

use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Command;

pub const MANIFEST_SCHEMA_VERSION: &str = "dependency_manifest.normalized.v1";
pub const SNAPSHOT_SCHEMA_VERSION: &str = "source_snapshot.v1";
pub const NORMALIZED_RECORD_SET_VERSION: &str = "normalized_record_set.v1";
const TOOL_VERSION: &str = "agent-canon 0.1.0";
const HEADER_SCAN_LINES: usize = 80;
const PATH_SORT: &str = "utf8-bytewise";
const GITLINK_MODE: &str = "160000";
const CANONICAL_GIT_MODES: &[&str] = &["100644", "100755", "120000", "040000", GITLINK_MODE];

const CONTRACT_KINDS: &[&str] = &[
    "agent-runtime",
    "configuration",
    "data",
    "design",
    "environment",
    "implementation",
    "issue",
    "policy",
    "reference",
    "registry",
    "report",
    "skill",
    "template",
    "test",
    "tool",
    "workflow",
];

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
pub(crate) enum ManifestDirection {
    Upstream,
    Downstream,
}

impl ManifestDirection {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Upstream => "upstream",
            Self::Downstream => "downstream",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum DependencyKind {
    Design,
    Implementation,
    Environment,
}

impl DependencyKind {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Design => "design",
            Self::Implementation => "implementation",
            Self::Environment => "environment",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CoverageDeclaration {
    pub id: String,
    pub requirements: Vec<Vec<String>>,
    pub source_span: SourceSpan,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ManifestDependency {
    pub direction: ManifestDirection,
    pub kind: DependencyKind,
    pub target: String,
    pub reason: String,
    pub source_span: SourceSpan,
    pub raw_line_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ManifestAst {
    pub contract: String,
    pub responsibility: String,
    pub coverage: Vec<CoverageDeclaration>,
    pub dependencies: Vec<ManifestDependency>,
    pub source_span: SourceSpan,
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
    owner_class: String,
    surface_mode: String,
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
    snapshot_id: String,
    parent_repo_id: String,
    root_realpath: String,
    git_head: String,
    git_index_tree: String,
    git_worktree_dirty: bool,
    git_status_hash: String,
    dirty_paths: Vec<String>,
    agentcanon_pin: String,
    schema_version: String,
    tool_version: String,
    profile: String,
    path_sort: String,
    source_fingerprint: String,
    captured_before_hash: String,
    captured_after_hash: String,
    snapshot_consistent: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SourceUniverse {
    pub(crate) candidate_paths: Vec<String>,
    pub(crate) excluded_paths: Vec<String>,
    pub(crate) eligible_paths: Vec<String>,
    pub(crate) eligible_equals_candidate_minus_excluded: bool,
    pub(crate) union_equals_candidate: bool,
    pub(crate) intersection_empty: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ManifestSnapshot {
    pub(crate) header: SnapshotHeader,
    pub(crate) source_identities: Vec<SourceIdentity>,
    pub(crate) declarations: Vec<DependencyDeclaration>,
    pub(crate) source_exclusions: Vec<SourceExclusion>,
    pub(crate) surface_relations: Vec<SurfaceRelation>,
    pub(crate) source_universe: SourceUniverse,
    pub(crate) diagnostics: Vec<Diagnostic>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SnapshotRequest {
    pub root: PathBuf,
    pub profile: String,
    pub output_jsonl: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ManifestError {
    Usage(String),
    Io(String),
    Git(String),
    Invalid { diagnostics: Vec<Diagnostic> },
    Transport(String),
    SnapshotInconsistent(String),
}

impl fmt::Display for ManifestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Usage(message)
            | Self::Io(message)
            | Self::Git(message)
            | Self::Transport(message)
            | Self::SnapshotInconsistent(message) => formatter.write_str(message),
            Self::Invalid { diagnostics } => {
                write!(
                    formatter,
                    "manifest has {} diagnostic(s)",
                    diagnostics.len()
                )
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RawDeclaration {
    source_identity_id: String,
    dependency: ManifestDependency,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct IndexEntry {
    mode: String,
    object_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SurfaceSpec {
    mode: String,
    class: String,
    source: String,
}

#[derive(Debug, Default, Clone)]
struct SurfaceCatalog {
    prefix: String,
    entries: BTreeMap<String, SurfaceSpec>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct IdentityBuild {
    identity: SourceIdentity,
    exclusion: Option<(String, String, String)>,
    surface: Option<(String, String, String, bool, String, String)>,
}

pub fn run(args: &[String]) -> i32 {
    let request = match parse_snapshot_args(args) {
        Ok(request) => request,
        Err(message) => {
            eprintln!("DEPENDENCY_MANIFEST_STATUS=usage");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC=usage:{message}");
            return 2;
        }
    };
    let snapshot = match capture_snapshot(&request) {
        Ok(snapshot) => snapshot,
        Err(error) => {
            let exit = match error {
                ManifestError::Usage(_) => 2,
                ManifestError::SnapshotInconsistent(_) | ManifestError::Git(_) => 20,
                ManifestError::Transport(_) | ManifestError::Invalid { .. } => 22,
                ManifestError::Io(_) => 20,
            };
            eprintln!("DEPENDENCY_MANIFEST_STATUS=snapshot-invalid");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
            return exit;
        }
    };
    for diagnostic in &snapshot.diagnostics {
        render_diagnostic(diagnostic);
    }
    let mut bytes = Vec::new();
    if let Err(error) = write_snapshot_jsonl(&snapshot, &mut bytes) {
        eprintln!("DEPENDENCY_MANIFEST_STATUS=output-failed");
        eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
        return 24;
    }
    if request.output_jsonl == Path::new("-") {
        if let Err(error) = io::stdout().write_all(&bytes) {
            eprintln!("DEPENDENCY_MANIFEST_STATUS=output-failed");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
            return 24;
        }
        return 0;
    }
    if let Err(error) = write_atomic(&request.output_jsonl, &bytes) {
        eprintln!("DEPENDENCY_MANIFEST_STATUS=output-failed");
        eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
        return 24;
    }
    0
}

fn parse_snapshot_args(args: &[String]) -> Result<SnapshotRequest, String> {
    if args.first().map(String::as_str) != Some("snapshot") {
        return Err("expected dependency-manifest snapshot".to_string());
    }
    let mut root = None;
    let mut profile = None;
    let mut output_jsonl = None;
    let mut index = 1;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => root = Some(next_arg(args, &mut index, "--root")?),
            "--profile" => profile = Some(next_arg(args, &mut index, "--profile")?),
            "--output-jsonl" => {
                output_jsonl = Some(PathBuf::from(next_arg(args, &mut index, "--output-jsonl")?))
            }
            flag => return Err(format!("unknown flag {flag}")),
        }
    }
    let profile = profile.ok_or_else(|| "missing --profile".to_string())?;
    if profile != "parent" {
        return Err(format!("invalid profile {profile}"));
    }
    Ok(SnapshotRequest {
        root: PathBuf::from(root.ok_or_else(|| "missing --root".to_string())?),
        profile,
        output_jsonl: output_jsonl.ok_or_else(|| "missing --output-jsonl".to_string())?,
    })
}

fn next_arg(args: &[String], index: &mut usize, flag: &str) -> Result<String, String> {
    let value = args
        .get(*index + 1)
        .ok_or_else(|| format!("{flag} requires a value"))?
        .clone();
    *index += 2;
    Ok(value)
}

pub(crate) fn capture_snapshot(
    request: &SnapshotRequest,
) -> Result<ManifestSnapshot, ManifestError> {
    let root = fs::canonicalize(&request.root)
        .map_err(|error| ManifestError::Io(format!("root {}: {error}", request.root.display())))?;
    if !root.is_dir() {
        return Err(ManifestError::Io(format!(
            "root is not a directory: {}",
            root.display()
        )));
    }
    let before = GitContext::capture(&root)?;
    let index_entries = read_index_entries(&root)?;
    let candidate_paths = git_visible_paths(&root)?;
    let surface_catalog = read_surface_catalog(&root);
    let mut builds = Vec::new();
    for relative_path in &candidate_paths {
        builds.push(build_identity(
            &root,
            relative_path,
            index_entries.get(relative_path),
            &before.dirty_paths,
            &before,
            &surface_catalog,
        )?);
    }
    builds.sort_by(|left, right| {
        left.identity
            .repo_rel_path
            .cmp(&right.identity.repo_rel_path)
    });
    let after = GitContext::capture(&root)?;
    let captured_before_hash = before.capture_hash(&request.profile);
    let captured_after_hash = after.capture_hash(&request.profile);
    if captured_before_hash != captured_after_hash {
        return Err(ManifestError::SnapshotInconsistent(
            "git/filesystem state changed during snapshot capture".to_string(),
        ));
    }

    let source_fingerprint = source_fingerprint(&builds, &before, &request.profile);
    let snapshot_id = hash_parts(&[
        "source_snapshot.v1",
        &before.parent_repo_id,
        &source_fingerprint,
        SNAPSHOT_SCHEMA_VERSION,
        TOOL_VERSION,
        &request.profile,
    ]);
    let mut source_identities = Vec::new();
    let mut source_exclusions = Vec::new();
    let mut surface_specs = Vec::new();
    for build in &builds {
        let mut identity = build.identity.clone();
        identity.snapshot_id = snapshot_id.clone();
        if let Some((reason_code, rule_id, scope)) = &build.exclusion {
            let exclusion_id = hash_parts(&[
                "source_exclusion.v1",
                &identity.identity_id,
                reason_code,
                scope,
            ]);
            source_exclusions.push(SourceExclusion {
                source_exclusion_id: exclusion_id,
                source_identity_id: identity.identity_id.clone(),
                repo_rel_path: identity.repo_rel_path.clone(),
                reason_code: reason_code.clone(),
                rule_id: rule_id.clone(),
                scope: scope.clone(),
                evidence_id: identity.identity_id.clone(),
                covered: false,
                snapshot_id: snapshot_id.clone(),
            });
        }
        if let Some((relation_type, target_path, owner, equal, mode, status)) = &build.surface {
            surface_specs.push((
                identity.identity_id.clone(),
                identity.repo_rel_path.clone(),
                relation_type.clone(),
                target_path.clone(),
                owner.clone(),
                *equal,
                mode.clone(),
                status.clone(),
            ));
        }
        source_identities.push(identity);
    }
    let identity_by_path = source_identities
        .iter()
        .map(|identity| (identity.repo_rel_path.clone(), identity.identity_id.clone()))
        .collect::<BTreeMap<_, _>>();
    let identity_by_locator = source_identities
        .iter()
        .map(|identity| {
            (
                identity.canonical_locator.clone(),
                identity.identity_id.clone(),
            )
        })
        .collect::<BTreeMap<_, _>>();

    let mut diagnostics = Vec::new();
    let mut raw_declarations = Vec::new();
    for identity in &source_identities {
        if !identity.exists
            || identity.path_role == "generated_output"
            || identity.path_role == "submodule_pin"
        {
            continue;
        }
        let path = root.join(&identity.repo_rel_path);
        if !fs::metadata(&path)
            .map(|metadata| metadata.is_file())
            .unwrap_or(false)
        {
            continue;
        }
        let bytes = match fs::read(&path) {
            Ok(bytes) => bytes,
            Err(error) => {
                diagnostics.push(Diagnostic {
                    code: "manifest.read_failed".to_string(),
                    message: format!("{}: {error}", identity.repo_rel_path),
                    severity: "warn".to_string(),
                    source_span: None,
                });
                continue;
            }
        };
        let text = match String::from_utf8(bytes) {
            Ok(text) => text,
            Err(_) => {
                diagnostics.push(Diagnostic {
                    code: "manifest.non_utf8".to_string(),
                    message: identity.repo_rel_path.clone(),
                    severity: "info".to_string(),
                    source_span: None,
                });
                continue;
            }
        };
        if !contains_manifest_marker(&text) {
            continue;
        }
        let ast = match ManifestParser::parse(&identity.repo_rel_path, &text) {
            Ok(ast) => ast,
            Err(ManifestError::Invalid {
                diagnostics: errors,
            }) => {
                diagnostics.extend(errors);
                continue;
            }
            Err(error) => {
                diagnostics.push(Diagnostic {
                    code: "manifest.parse_failed".to_string(),
                    message: error.to_string(),
                    severity: "error".to_string(),
                    source_span: None,
                });
                continue;
            }
        };
        for dependency in ast.dependencies {
            let target =
                match normalize_dependency_target(&identity.repo_rel_path, &dependency.target) {
                    Ok(target) => target,
                    Err(code) => {
                        diagnostics.push(Diagnostic {
                            code,
                            message: format!("invalid dependency target {}", dependency.target),
                            severity: "error".to_string(),
                            source_span: Some(dependency.source_span.clone()),
                        });
                        dependency.target.clone()
                    }
                };
            let resolved_target_identity_id = identity_by_path
                .get(&target)
                .cloned()
                .or_else(|| identity_by_locator.get(&target).cloned());
            if resolved_target_identity_id.is_none() {
                diagnostics.push(Diagnostic {
                    code: "dependency.target_unresolved".to_string(),
                    message: format!("{} -> {}", identity.repo_rel_path, target),
                    severity: "info".to_string(),
                    source_span: Some(dependency.source_span.clone()),
                });
            }
            raw_declarations.push(RawDeclaration {
                source_identity_id: identity.identity_id.clone(),
                dependency: ManifestDependency {
                    target,
                    ..dependency
                },
            });
        }
    }
    let mut declarations = raw_declarations
        .into_iter()
        .map(|raw| {
            let target = raw.dependency.target.clone();
            let resolved_target_identity_id = identity_by_path
                .get(&target)
                .cloned()
                .or_else(|| identity_by_locator.get(&target).cloned());
            let start_line = raw.dependency.source_span.start_line.to_string();
            let end_line = raw.dependency.source_span.end_line.to_string();
            let declaration_id = hash_parts(&[
                "dependency_declaration.v1",
                &raw.source_identity_id,
                &start_line,
                &end_line,
                raw.dependency.direction.as_str(),
                raw.dependency.kind.as_str(),
                &target,
                &raw.dependency.raw_line_hash,
            ]);
            let attestation_key = hash_parts(&[
                "dependency_attestation.v1",
                &snapshot_id,
                &raw.source_identity_id,
                &start_line,
                &end_line,
                raw.dependency.direction.as_str(),
                raw.dependency.kind.as_str(),
                &target,
                &raw.dependency.raw_line_hash,
            ]);
            DependencyDeclaration {
                declaration_id,
                source_identity_id: raw.source_identity_id,
                declared_direction: raw.dependency.direction.as_str().to_string(),
                declared_kind: raw.dependency.kind.as_str().to_string(),
                declared_target: target,
                resolved_target_identity_id,
                source_span: raw.dependency.source_span,
                reason: raw.dependency.reason,
                raw_line_hash: raw.dependency.raw_line_hash,
                attestation_key,
                snapshot_id: snapshot_id.clone(),
            }
        })
        .collect::<Vec<_>>();
    declarations.sort_by(|left, right| left.declaration_id.cmp(&right.declaration_id));

    let mut surface_relations = surface_specs
        .into_iter()
        .map(
            |(source_id, source_path, relation_type, target_path, owner, equal, mode, status)| {
                let target_id = identity_by_path
                    .get(&target_path)
                    .cloned()
                    .or_else(|| identity_by_locator.get(&target_path).cloned())
                    .unwrap_or_else(|| {
                        hash_parts(&["source_identity.v1", &before.parent_repo_id, &target_path])
                    });
                let relation_id = hash_parts(&[
                    "surface_relation.v1",
                    &source_id,
                    &target_id,
                    &relation_type,
                ]);
                SurfaceRelation {
                    relation_id: relation_id.clone(),
                    relation_type,
                    source_identity_id: source_id,
                    target_identity_id: target_id,
                    source_path,
                    target_path,
                    owner_class: owner,
                    surface_mode: mode,
                    content_hash_equal: equal,
                    evidence_id: relation_id,
                    status,
                    snapshot_id: snapshot_id.clone(),
                }
            },
        )
        .collect::<Vec<_>>();
    surface_relations.sort_by(|left, right| left.relation_id.cmp(&right.relation_id));
    let source_universe =
        materialize_source_universe(&candidate_paths, &source_identities, &source_exclusions)?;

    Ok(ManifestSnapshot {
        header: SnapshotHeader {
            snapshot_id,
            parent_repo_id: before.parent_repo_id,
            root_realpath: root.to_string_lossy().into_owned(),
            git_head: before.git_head,
            git_index_tree: before.git_index_tree,
            git_worktree_dirty: before.git_worktree_dirty,
            git_status_hash: before.git_status_hash,
            dirty_paths: before.dirty_paths,
            agentcanon_pin: before.agentcanon_pin,
            schema_version: SNAPSHOT_SCHEMA_VERSION.to_string(),
            tool_version: TOOL_VERSION.to_string(),
            profile: request.profile.clone(),
            path_sort: PATH_SORT.to_string(),
            source_fingerprint,
            captured_before_hash: captured_before_hash.clone(),
            captured_after_hash,
            snapshot_consistent: true,
        },
        source_identities,
        declarations,
        source_exclusions,
        surface_relations,
        source_universe,
        diagnostics,
    })
}

struct GitContext {
    parent_repo_id: String,
    git_head: String,
    git_index_tree: String,
    git_worktree_dirty: bool,
    git_status_hash: String,
    dirty_paths: Vec<String>,
    agentcanon_pin: String,
}

impl GitContext {
    fn capture(root: &Path) -> Result<Self, ManifestError> {
        let git_head = git_text(root, &["rev-parse", "HEAD"])?;
        let git_index_tree = git_text(root, &["write-tree"])?;
        let status = git_bytes(root, &["status", "--porcelain=v2", "-z"])?;
        let dirty_paths = parse_dirty_paths(&status);
        let agentcanon_pin = submodule_pin(root);
        let locator = git_text_optional(root, &["config", "--get", "remote.origin.url"])
            .unwrap_or_else(|| root.to_string_lossy().into_owned());
        Ok(Self {
            parent_repo_id: hash_parts(&["parent_repo.v1", &locator]),
            git_head,
            git_index_tree,
            git_worktree_dirty: !status.is_empty(),
            git_status_hash: sha256_bytes(&status),
            dirty_paths,
            agentcanon_pin,
        })
    }

    fn capture_hash(&self, profile: &str) -> String {
        hash_parts(&[
            &self.git_head,
            &self.git_index_tree,
            &self.git_status_hash,
            &self.agentcanon_pin,
            SNAPSHOT_SCHEMA_VERSION,
            TOOL_VERSION,
            profile,
        ])
    }
}

fn git_visible_paths(root: &Path) -> Result<Vec<String>, ManifestError> {
    let output = git_bytes(
        root,
        &[
            "ls-files",
            "--cached",
            "--deleted",
            "--others",
            "--exclude-standard",
            "-z",
        ],
    )?;
    let mut paths = BTreeSet::new();
    for raw in output
        .split(|byte| *byte == 0)
        .filter(|raw| !raw.is_empty())
    {
        let path = std::str::from_utf8(raw).map_err(|error| {
            ManifestError::Git(format!("git-visible path is not UTF-8: {error}"))
        })?;
        paths.insert(
            normalize_repo_path(Path::new(path))
                .ok_or_else(|| ManifestError::Git(format!("invalid git-visible path {path}")))?,
        );
    }
    Ok(paths.into_iter().collect())
}

fn read_index_entries(root: &Path) -> Result<BTreeMap<String, IndexEntry>, ManifestError> {
    let output = git_bytes(root, &["ls-files", "--stage", "-z"])?;
    let mut entries = BTreeMap::new();
    for raw in output
        .split(|byte| *byte == 0)
        .filter(|raw| !raw.is_empty())
    {
        let text = String::from_utf8_lossy(raw);
        let (metadata, path) = text
            .split_once('\t')
            .ok_or_else(|| ManifestError::Git(format!("malformed index record {text}")))?;
        let mut fields = metadata.split_whitespace();
        let mode = fields.next().unwrap_or_default().to_string();
        let object_id = fields.next().unwrap_or_default().to_string();
        if mode.is_empty() || object_id.is_empty() || path.is_empty() {
            return Err(ManifestError::Git(format!("malformed index record {text}")));
        }
        entries.insert(
            normalize_repo_path(Path::new(path))
                .ok_or_else(|| ManifestError::Git(format!("invalid index path {path}")))?,
            IndexEntry { mode, object_id },
        );
    }
    Ok(entries)
}

fn build_identity(
    root: &Path,
    relative_path: &str,
    index_entry: Option<&IndexEntry>,
    dirty_paths: &[String],
    context: &GitContext,
    catalog: &SurfaceCatalog,
) -> Result<IdentityBuild, ManifestError> {
    let path = root.join(relative_path);
    let metadata = fs::symlink_metadata(&path).ok();
    let exists = metadata.is_some();
    let is_gitlink = index_entry
        .map(|entry| entry.mode == GITLINK_MODE)
        .unwrap_or(false);
    let is_symlink = metadata
        .as_ref()
        .map(|value| value.file_type().is_symlink())
        .unwrap_or(false);
    let is_regular = metadata
        .as_ref()
        .map(|value| value.file_type().is_file())
        .unwrap_or(false);
    let is_directory = metadata
        .as_ref()
        .map(|value| value.file_type().is_dir())
        .unwrap_or(false);
    let symlink_target = if is_symlink {
        fs::read_link(&path).ok()
    } else {
        None
    };
    let canonical_target = symlink_target.as_ref().and_then(|target| {
        let absolute = if target.is_absolute() {
            target.clone()
        } else {
            path.parent().unwrap_or(root).join(target)
        };
        let resolved = fs::canonicalize(&absolute).unwrap_or(absolute);
        let normalized = normalize_absolute_path(&resolved);
        let root_prefix = format!("{}/", root.to_string_lossy());
        normalized
            .strip_prefix(&root_prefix)
            .map(ToString::to_string)
    });
    let surface_spec = catalog.entries.get(relative_path);
    let generated = relative_path == ".agent-canon/knowledge-graph"
        || relative_path.starts_with(".agent-canon/knowledge-graph/");
    let submodule_internal = relative_path.starts_with("vendor/agent-canon/");
    let unsupported = exists && !is_gitlink && !is_symlink && !is_regular && !is_directory;
    let mut canonical_locator = relative_path.to_string();
    let mut locator_kind = if is_gitlink {
        "submodule".to_string()
    } else if is_symlink {
        "symlink".to_string()
    } else {
        "file".to_string()
    };
    let mut path_role = if is_gitlink {
        "submodule_pin".to_string()
    } else if generated {
        "generated_output".to_string()
    } else if !exists {
        "deleted".to_string()
    } else {
        "source".to_string()
    };
    let mut owner_class = surface_spec
        .map(|spec| spec.class.clone())
        .unwrap_or_else(|| "unresolved".to_string());
    let mut surface_mode = surface_spec
        .map(|spec| spec.mode.clone())
        .unwrap_or_else(|| "regular".to_string());
    let mut surface = None;

    if is_symlink {
        if let Some(target) = canonical_target.clone() {
            canonical_locator = target.clone();
            if catalog.entries.contains_key(relative_path) {
                path_role = "root_view".to_string();
                surface_mode = "symlink".to_string();
                surface = Some((
                    "view_of".to_string(),
                    target,
                    owner_class.clone(),
                    true,
                    surface_mode.clone(),
                    "mapped".to_string(),
                ));
            }
        }
    } else if let Some(spec) = surface_spec {
        if spec.mode == "copy" {
            let target = if spec.source.starts_with("vendor/agent-canon/") {
                spec.source.clone()
            } else {
                format!("{}/{}", catalog.prefix, spec.source)
            };
            let source_hash = content_hash_for_path(&path, index_entry, root, relative_path)?;
            let target_hash =
                content_hash_for_path(&root.join(&target), None, root, &target).unwrap_or_default();
            let equal = !source_hash.is_empty() && source_hash == target_hash;
            path_role = "root_view".to_string();
            locator_kind = "copy".to_string();
            if equal {
                canonical_locator = target.clone();
            }
            surface = Some((
                "view_of".to_string(),
                target,
                owner_class.clone(),
                equal,
                "copy".to_string(),
                if equal { "mapped" } else { "content-mismatch" }.to_string(),
            ));
        }
    }
    if is_gitlink {
        surface = Some((
            "submodule_pin".to_string(),
            relative_path.to_string(),
            "agent-canon-submodule".to_string(),
            true,
            "gitlink".to_string(),
            "pin-captured".to_string(),
        ));
        owner_class = "agent-canon-submodule".to_string();
        surface_mode = "gitlink".to_string();
    }
    if surface.is_none() {
        if let Some(spec) = surface_spec {
            surface = Some((
                "owned_by".to_string(),
                spec.source.clone(),
                owner_class.clone(),
                true,
                surface_mode.clone(),
                "classified".to_string(),
            ));
        }
    }

    let exclusion = if is_symlink && canonical_target.is_none() && symlink_target.is_some() {
        Some((
            "symlink_outside_root".to_string(),
            "source-universe-symlink-boundary".to_string(),
            relative_path.to_string(),
        ))
    } else if generated {
        Some((
            "generated_output".to_string(),
            "parent-generated-graph-output".to_string(),
            ".agent-canon/knowledge-graph/**".to_string(),
        ))
    } else if submodule_internal {
        Some((
            "submodule_internal".to_string(),
            "parent-submodule-boundary".to_string(),
            "vendor/agent-canon/**".to_string(),
        ))
    } else if unsupported {
        Some((
            "unsupported_file_kind".to_string(),
            "source-universe-file-kind".to_string(),
            relative_path.to_string(),
        ))
    } else {
        None
    };
    let content_hash = content_hash_for_path(&path, index_entry, root, relative_path)?;
    let git_blob_or_gitlink = index_entry
        .map(|entry| entry.object_id.clone())
        .unwrap_or_default();
    let submodule_commit = if is_gitlink {
        current_submodule_commit(&root.join(relative_path))
            .unwrap_or_else(|| git_blob_or_gitlink.clone())
    } else {
        String::new()
    };
    let file_mode = canonical_file_mode(metadata.as_ref(), index_entry)?;
    let logical_id = hash_parts(&[
        "logical_source.v1",
        &context.parent_repo_id,
        &canonical_locator,
    ]);
    let identity_id = hash_parts(&["source_identity.v1", &context.parent_repo_id, relative_path]);
    let is_dirty = dirty_paths.iter().any(|path| path == relative_path)
        || (canonical_locator.starts_with("vendor/agent-canon/")
            && dirty_paths.iter().any(|path| path == "vendor/agent-canon"));
    let alternate_locators = if canonical_locator == relative_path {
        Vec::new()
    } else {
        vec![relative_path.to_string()]
    };
    Ok(IdentityBuild {
        identity: SourceIdentity {
            identity_id,
            logical_id,
            repo_rel_path: relative_path.to_string(),
            canonical_locator,
            alternate_locators,
            locator_kind,
            path_role,
            file_mode,
            exists,
            is_dirty,
            content_hash,
            git_blob_or_gitlink,
            submodule_commit,
            snapshot_id: String::new(),
            owner_class,
            surface_mode,
        },
        exclusion,
        surface,
    })
}

fn source_fingerprint(builds: &[IdentityBuild], context: &GitContext, profile: &str) -> String {
    let mut parts = vec![
        "source_fingerprint.v1".to_string(),
        context.git_head.clone(),
        context.git_worktree_dirty.to_string(),
        context.git_status_hash.clone(),
        context.agentcanon_pin.clone(),
        SNAPSHOT_SCHEMA_VERSION.to_string(),
        TOOL_VERSION.to_string(),
        profile.to_string(),
    ];
    for build in builds {
        let identity = &build.identity;
        parts.extend([
            identity.repo_rel_path.clone(),
            identity.file_mode.clone(),
            identity.exists.to_string(),
            identity.content_hash.clone(),
            identity.git_blob_or_gitlink.clone(),
            identity.submodule_commit.clone(),
            identity.path_role.clone(),
            identity.owner_class.clone(),
            identity.surface_mode.clone(),
        ]);
    }
    hash_parts(&parts.iter().map(String::as_str).collect::<Vec<_>>())
}

fn materialize_source_universe(
    candidate_paths: &[String],
    source_identities: &[SourceIdentity],
    source_exclusions: &[SourceExclusion],
) -> Result<SourceUniverse, ManifestError> {
    let candidate = candidate_paths.iter().cloned().collect::<BTreeSet<_>>();
    if candidate.len() != candidate_paths.len() {
        return Err(ManifestError::Transport(
            "duplicate path in candidate source set P".to_string(),
        ));
    }
    let identity_paths = source_identities
        .iter()
        .map(|identity| identity.repo_rel_path.clone())
        .collect::<BTreeSet<_>>();
    if identity_paths.len() != source_identities.len() || identity_paths != candidate {
        return Err(ManifestError::Transport(
            "source identities do not represent candidate source set P exactly".to_string(),
        ));
    }
    let identities_by_id = source_identities
        .iter()
        .map(|identity| {
            (
                identity.identity_id.as_str(),
                identity.repo_rel_path.as_str(),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut excluded_identity_ids = BTreeSet::new();
    let mut excluded = BTreeSet::new();
    for exclusion in source_exclusions {
        let Some(identity_path) = identities_by_id.get(exclusion.source_identity_id.as_str())
        else {
            return Err(ManifestError::Transport(format!(
                "source exclusion {} references an unknown source identity",
                exclusion.source_exclusion_id
            )));
        };
        if *identity_path != exclusion.repo_rel_path {
            return Err(ManifestError::Transport(format!(
                "source exclusion {} path does not match its source identity",
                exclusion.source_exclusion_id
            )));
        }
        if !excluded_identity_ids.insert(exclusion.source_identity_id.as_str())
            || !excluded.insert(exclusion.repo_rel_path.clone())
        {
            return Err(ManifestError::Transport(
                "duplicate member in source exclusion set E_src".to_string(),
            ));
        }
    }
    let eligible = source_identities
        .iter()
        .filter(|identity| !excluded_identity_ids.contains(identity.identity_id.as_str()))
        .map(|identity| identity.repo_rel_path.clone())
        .collect::<BTreeSet<_>>();
    let candidate_minus_excluded = candidate
        .difference(&excluded)
        .cloned()
        .collect::<BTreeSet<_>>();
    let eligible_equals_candidate_minus_excluded = eligible == candidate_minus_excluded;
    let union_equals_candidate =
        eligible.union(&excluded).cloned().collect::<BTreeSet<_>>() == candidate;
    let intersection_empty = eligible.is_disjoint(&excluded);
    if !(eligible_equals_candidate_minus_excluded && union_equals_candidate && intersection_empty) {
        return Err(ManifestError::Transport(
            "source-universe set equations failed".to_string(),
        ));
    }
    Ok(SourceUniverse {
        candidate_paths: candidate.into_iter().collect(),
        excluded_paths: excluded.into_iter().collect(),
        eligible_paths: eligible.into_iter().collect(),
        eligible_equals_candidate_minus_excluded,
        union_equals_candidate,
        intersection_empty,
    })
}

fn content_hash_for_path(
    path: &Path,
    index_entry: Option<&IndexEntry>,
    root: &Path,
    relative_path: &str,
) -> Result<String, ManifestError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            let target = fs::read_link(path).map_err(|error| {
                ManifestError::Io(format!("read symlink {}: {error}", path.display()))
            })?;
            Ok(sha256_bytes(target.to_string_lossy().as_bytes()))
        }
        Ok(metadata) if metadata.file_type().is_file() => {
            let bytes = fs::read(path)
                .map_err(|error| ManifestError::Io(format!("read {}: {error}", path.display())))?;
            Ok(sha256_bytes(&bytes))
        }
        Ok(metadata)
            if metadata.file_type().is_dir()
                && index_entry
                    .map(|entry| entry.mode == GITLINK_MODE)
                    .unwrap_or(false) =>
        {
            Ok(index_entry
                .map(|entry| entry.object_id.clone())
                .unwrap_or_default())
        }
        Ok(_) => Ok(String::new()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            let Some(entry) = index_entry else {
                return Ok(String::new());
            };
            let output = git_bytes(root, &["cat-file", "blob", &entry.object_id])
                .or_else(|_| git_bytes(root, &["show", &format!(":{relative_path}")]))?;
            Ok(sha256_bytes(&output))
        }
        Err(error) => Err(ManifestError::Io(format!(
            "stat {}: {error}",
            path.display()
        ))),
    }
}

fn canonical_file_mode(
    metadata: Option<&fs::Metadata>,
    index_entry: Option<&IndexEntry>,
) -> Result<String, ManifestError> {
    if let Some(entry) = index_entry {
        if CANONICAL_GIT_MODES.contains(&entry.mode.as_str()) {
            return Ok(entry.mode.clone());
        }
        return Err(ManifestError::Git(format!(
            "non-canonical index mode {}",
            entry.mode
        )));
    }
    let Some(metadata) = metadata else {
        return Err(ManifestError::Io(
            "git-visible path has neither an index entry nor filesystem metadata".to_string(),
        ));
    };
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = if metadata.file_type().is_symlink() {
            "120000"
        } else if metadata.file_type().is_file() {
            if metadata.permissions().mode() & 0o111 == 0 {
                "100644"
            } else {
                "100755"
            }
        } else {
            "040000"
        };
        return Ok(mode.to_string());
    }
    #[cfg(not(unix))]
    {
        if metadata.file_type().is_symlink() {
            Ok("120000".to_string())
        } else if metadata.file_type().is_file() {
            Ok("100644".to_string())
        } else {
            Ok("040000".to_string())
        }
    }
}

fn parse_dirty_paths(status: &[u8]) -> Vec<String> {
    let records = status.split(|byte| *byte == 0).collect::<Vec<_>>();
    let mut paths = BTreeSet::new();
    let mut index = 0;
    while index < records.len() {
        let record = records[index];
        if record.is_empty() {
            index += 1;
            continue;
        }
        let text = String::from_utf8_lossy(record);
        let kind = text.as_bytes()[0] as char;
        let path = match kind {
            '1' => text.splitn(9, ' ').nth(8),
            '2' => text.splitn(10, ' ').nth(9),
            'u' => text.splitn(11, ' ').nth(10),
            '?' | '!' => text.splitn(2, ' ').nth(1),
            _ => None,
        };
        if let Some(path) = path.and_then(|path| normalize_repo_path(Path::new(path))) {
            paths.insert(path);
        }
        if kind == '2' {
            if let Some(original) = records
                .get(index + 1)
                .and_then(|value| std::str::from_utf8(value).ok())
                .and_then(|value| normalize_repo_path(Path::new(value)))
            {
                paths.insert(original);
                index += 1;
            }
        }
        index += 1;
    }
    paths.into_iter().collect()
}

fn submodule_pin(root: &Path) -> String {
    let path = root.join("vendor/agent-canon");
    if !path.exists() {
        return String::new();
    }
    git_text_optional(&path, &["rev-parse", "HEAD"]).unwrap_or_default()
}

fn current_submodule_commit(path: &Path) -> Option<String> {
    git_text_optional(path, &["rev-parse", "HEAD"])
}

fn git_bytes(root: &Path, args: &[&str]) -> Result<Vec<u8>, ManifestError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| ManifestError::Git(format!("git {}: {error}", args.join(" "))))?;
    if !output.status.success() {
        return Err(ManifestError::Git(format!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    Ok(output.stdout)
}

fn git_text(root: &Path, args: &[&str]) -> Result<String, ManifestError> {
    Ok(String::from_utf8_lossy(&git_bytes(root, args)?)
        .trim()
        .to_string())
}

fn git_text_optional(root: &Path, args: &[&str]) -> Option<String> {
    git_bytes(root, args)
        .ok()
        .map(|bytes| String::from_utf8_lossy(&bytes).trim().to_string())
        .filter(|value| !value.is_empty())
}

fn read_surface_catalog(root: &Path) -> SurfaceCatalog {
    let path = root.join("vendor/agent-canon/documents/shared-runtime-surfaces.toml");
    let Ok(text) = fs::read_to_string(path) else {
        return SurfaceCatalog::default();
    };
    let mut catalog = SurfaceCatalog {
        prefix: "vendor/agent-canon".to_string(),
        entries: BTreeMap::new(),
    };
    let mut section_paths = Vec::new();
    let mut mode = String::new();
    let mut class = String::new();
    let mut source = String::new();
    let mut in_paths = false;
    for line in text.lines() {
        let line = line.trim();
        if line.starts_with("[[surface]]") || line.starts_with("[[group]]") {
            flush_surface_section(
                &mut catalog,
                &mut section_paths,
                &mut mode,
                &mut class,
                &mut source,
            );
            mode.clear();
            class.clear();
            source.clear();
            in_paths = false;
            continue;
        }
        if let Some(value) = toml_string(line, "prefix") {
            catalog.prefix = value;
            continue;
        }
        if let Some(value) = toml_string(line, "mode") {
            mode = value;
            continue;
        }
        if let Some(value) = toml_string(line, "class") {
            class = value;
            continue;
        }
        if let Some(value) = toml_string(line, "source") {
            source = value;
            continue;
        }
        if let Some(value) = toml_string(line, "path") {
            section_paths.push(value);
            continue;
        }
        if line.starts_with("paths") && line.contains('[') {
            in_paths = true;
        }
        if in_paths {
            if let Some(path) = first_quoted(line) {
                section_paths.push(path);
            }
            if line.contains(']') {
                in_paths = false;
            }
        }
    }
    flush_surface_section(
        &mut catalog,
        &mut section_paths,
        &mut mode,
        &mut class,
        &mut source,
    );
    catalog
}

fn flush_surface_section(
    catalog: &mut SurfaceCatalog,
    paths: &mut Vec<String>,
    mode: &mut String,
    class: &mut String,
    source: &mut String,
) {
    for path in std::mem::take(paths) {
        let source_path = if source.is_empty() {
            path.clone()
        } else {
            source.clone()
        };
        catalog.entries.insert(
            path,
            SurfaceSpec {
                mode: if mode.is_empty() {
                    "regular".to_string()
                } else {
                    mode.clone()
                },
                class: if class.is_empty() {
                    "unresolved".to_string()
                } else {
                    class.clone()
                },
                source: source_path,
            },
        );
    }
}

fn toml_string(line: &str, key: &str) -> Option<String> {
    let prefix = format!("{key} =");
    line.strip_prefix(&prefix)
        .and_then(|value| first_quoted(value.trim()))
}

fn first_quoted(value: &str) -> Option<String> {
    let start = value.find('"')? + 1;
    let end = value[start..].find('"')? + start;
    Some(value[start..end].to_string())
}

fn normalize_absolute_path(path: &Path) -> String {
    let mut components = Vec::new();
    for component in path.components() {
        match component {
            Component::RootDir => components.clear(),
            Component::CurDir => {}
            Component::ParentDir => {
                components.pop();
            }
            Component::Normal(value) => components.push(value.to_string_lossy().to_string()),
            Component::Prefix(value) => {
                components.push(value.as_os_str().to_string_lossy().to_string())
            }
        }
    }
    format!("/{}", components.join("/"))
}

fn normalize_repo_path(path: &Path) -> Option<String> {
    if path.is_absolute() {
        return None;
    }
    let mut components = Vec::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::Normal(value) => components.push(value.to_string_lossy().to_string()),
            Component::ParentDir => {
                components.pop()?;
            }
            Component::RootDir | Component::Prefix(_) => return None,
        }
    }
    if components.is_empty() {
        None
    } else {
        Some(components.join("/"))
    }
}

fn normalize_dependency_target(source_path: &str, target: &str) -> Result<String, String> {
    if target.trim().is_empty() || Path::new(target).is_absolute() {
        return Err("dependency.target.invalid_path".to_string());
    }
    let base = Path::new(source_path)
        .parent()
        .unwrap_or_else(|| Path::new(""));
    normalize_repo_path(&base.join(target))
        .ok_or_else(|| "dependency.target.outside_root".to_string())
}

fn contains_manifest_marker(text: &str) -> bool {
    let lines = text.lines().take(HEADER_SCAN_LINES).collect::<Vec<_>>();
    let scan = scan_manifest_lines("", &lines);
    scan.lines.iter().any(|line| {
        line.content.as_deref() == Some("@dependency-start")
            || line.content.as_deref() == Some("@dependency-end")
    }) || scan
        .diagnostics
        .iter()
        .any(|diagnostic| diagnostic.code.starts_with("manifest.marker.bare_"))
}

pub(crate) struct ManifestParser;

impl ManifestParser {
    pub(crate) fn parse(path: &str, text: &str) -> Result<ManifestAst, ManifestError> {
        let lines = text.lines().take(HEADER_SCAN_LINES).collect::<Vec<_>>();
        let scan = scan_manifest_lines(path, &lines);
        let starts = scan
            .lines
            .iter()
            .enumerate()
            .filter(|(_, line)| line.content.as_deref() == Some("@dependency-start"))
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        let ends = scan
            .lines
            .iter()
            .enumerate()
            .filter(|(_, line)| line.content.as_deref() == Some("@dependency-end"))
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        let mut diagnostics = scan.diagnostics;
        if starts.is_empty() {
            diagnostics.push(diagnostic(
                "manifest.marker.missing_start",
                "missing @dependency-start",
                None,
            ));
        } else if starts.len() > 1 {
            diagnostics.push(diagnostic(
                "manifest.marker.duplicate_start",
                "duplicate @dependency-start",
                Some(span_for_scanned(path, starts[1], &scan.lines[starts[1]])),
            ));
        }
        if ends.is_empty() {
            diagnostics.push(diagnostic(
                "manifest.marker.missing_end",
                "missing @dependency-end",
                None,
            ));
        } else if ends.len() > 1 {
            diagnostics.push(diagnostic(
                "manifest.marker.duplicate_end",
                "duplicate @dependency-end",
                Some(span_for_scanned(path, ends[1], &scan.lines[ends[1]])),
            ));
        }
        let Some(start) = starts.first().copied() else {
            return Err(ManifestError::Invalid { diagnostics });
        };
        let Some(end) = ends.iter().copied().find(|end| *end > start) else {
            diagnostics.push(diagnostic(
                "manifest.marker.invalid_order",
                "@dependency-end precedes @dependency-start",
                ends.first()
                    .map(|index| span_for_scanned(path, *index, &scan.lines[*index])),
            ));
            return Err(ManifestError::Invalid { diagnostics });
        };
        let wrapper_id = scan.lines[start].wrapper_id;
        if wrapper_id.is_none() || scan.lines[end].wrapper_id != wrapper_id {
            diagnostics.push(diagnostic(
                "manifest.wrapper.mismatch",
                "manifest markers must use one documented outer comment wrapper",
                Some(span_for_scanned(path, end, &scan.lines[end])),
            ));
        }
        let mut contract = None;
        let mut responsibility = None;
        let mut coverage = Vec::new();
        let mut dependencies = Vec::new();
        for index in start + 1..end {
            if lines[index].trim().is_empty() {
                continue;
            }
            let Some(line) = scan.lines[index].content.as_deref() else {
                diagnostics.push(diagnostic(
                    "manifest.wrapper.required",
                    "manifest lines must use the block's outer comment wrapper",
                    Some(span_for(path, index, lines[index])),
                ));
                continue;
            };
            if scan.lines[index].wrapper_id != wrapper_id {
                diagnostics.push(diagnostic(
                    "manifest.wrapper.mismatch",
                    "manifest lines must use one documented outer comment wrapper",
                    Some(span_for_scanned(path, index, &scan.lines[index])),
                ));
                continue;
            }
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let source_span = span_for_scanned(path, index, &scan.lines[index]);
            if let Some(value) = directive_value(line, "contract") {
                let value = value.trim();
                if value.is_empty() {
                    diagnostics.push(diagnostic(
                        "manifest.contract.malformed",
                        "contract requires a registered kind",
                        Some(source_span),
                    ));
                } else if contract.replace(value.to_string()).is_some() {
                    diagnostics.push(diagnostic(
                        "manifest.contract.duplicate",
                        "manifest has more than one contract",
                        Some(source_span),
                    ));
                } else if !CONTRACT_KINDS.contains(&value) {
                    diagnostics.push(diagnostic(
                        "manifest.contract.unknown_kind",
                        format!("unknown contract kind {value}"),
                        Some(source_span),
                    ));
                }
                continue;
            }
            if let Some(value) = directive_value(line, "responsibility") {
                let value = value.trim();
                if value.is_empty() {
                    diagnostics.push(diagnostic(
                        "manifest.responsibility.missing",
                        "responsibility requires text",
                        Some(source_span),
                    ));
                } else if responsibility.replace(value.to_string()).is_some() {
                    diagnostics.push(diagnostic(
                        "manifest.responsibility.duplicate",
                        "manifest has more than one responsibility",
                        Some(source_span),
                    ));
                }
                continue;
            }
            if let Some(value) = directive_value(line, "coverage") {
                match parse_coverage(value.trim(), source_span.clone()) {
                    Ok(value) => coverage.push(value),
                    Err(code) => diagnostics.push(diagnostic(
                        &code,
                        "malformed coverage declaration",
                        Some(source_span),
                    )),
                }
                continue;
            }
            if ["contract", "responsibility", "coverage"]
                .iter()
                .any(|keyword| line.starts_with(keyword))
            {
                diagnostics.push(diagnostic(
                    "manifest.directive.invalid_boundary",
                    "manifest directive keyword must be followed by whitespace",
                    Some(source_span),
                ));
                continue;
            }
            if matches!(line, "@dependency-start" | "@dependency-end") {
                continue;
            }
            let mut fields = line.splitn(4, char::is_whitespace);
            let direction = fields.next().unwrap_or_default();
            let kind = fields.next().unwrap_or_default();
            let target = fields.next().unwrap_or_default();
            let reason = fields.next().unwrap_or_default().trim();
            if !matches!(direction, "upstream" | "downstream") {
                diagnostics.push(diagnostic(
                    "manifest.dependency.unknown_direction",
                    format!("unknown direction {direction}"),
                    Some(source_span),
                ));
                continue;
            }
            if !matches!(kind, "design" | "implementation" | "environment") {
                diagnostics.push(diagnostic(
                    "manifest.dependency.unknown_kind",
                    format!("unknown dependency kind {kind}"),
                    Some(source_span),
                ));
                continue;
            }
            if target.is_empty() {
                diagnostics.push(diagnostic(
                    "manifest.dependency.missing_target",
                    "dependency requires a target",
                    Some(source_span),
                ));
                continue;
            }
            if reason.is_empty() {
                diagnostics.push(diagnostic(
                    "manifest.dependency.missing_reason",
                    "dependency requires a reason",
                    Some(source_span),
                ));
                continue;
            }
            let direction = if direction == "upstream" {
                ManifestDirection::Upstream
            } else {
                ManifestDirection::Downstream
            };
            let kind = match kind {
                "design" => DependencyKind::Design,
                "implementation" => DependencyKind::Implementation,
                _ => DependencyKind::Environment,
            };
            dependencies.push(ManifestDependency {
                direction,
                kind,
                target: target.to_string(),
                reason: reason.to_string(),
                source_span: source_span.clone(),
                raw_line_hash: sha256_bytes(lines[index].as_bytes()),
            });
        }
        if contract.is_none() {
            diagnostics.push(diagnostic(
                "manifest.contract.missing",
                "manifest requires exactly one contract",
                Some(span_for_scanned(path, start, &scan.lines[start])),
            ));
        }
        if responsibility.is_none() {
            diagnostics.push(diagnostic(
                "manifest.responsibility.missing",
                "manifest requires exactly one responsibility",
                Some(span_for_scanned(path, start, &scan.lines[start])),
            ));
        }
        if !diagnostics.is_empty() {
            return Err(ManifestError::Invalid { diagnostics });
        }
        Ok(ManifestAst {
            contract: contract.unwrap_or_default(),
            responsibility: responsibility.unwrap_or_default(),
            coverage,
            dependencies,
            source_span: SourceSpan {
                path: path.to_string(),
                start_line: start + 1,
                start_column: scan.lines[start].start_column,
                end_line: end + 1,
                end_column: lines[end].len() + 1,
            },
        })
    }
}

fn directive_value<'a>(line: &'a str, keyword: &str) -> Option<&'a str> {
    let value = line.strip_prefix(keyword)?;
    if value.is_empty() || value.chars().next().is_some_and(char::is_whitespace) {
        Some(value)
    } else {
        None
    }
}

fn parse_coverage(value: &str, source_span: SourceSpan) -> Result<CoverageDeclaration, String> {
    let (id, requirements) = value
        .split_once(" requires ")
        .ok_or_else(|| "manifest.coverage.malformed".to_string())?;
    let id = id.trim();
    if id.is_empty() {
        return Err("manifest.coverage.missing_id".to_string());
    }
    let requirements = requirements
        .split(';')
        .map(|group| {
            group
                .split('|')
                .map(|term| term.trim().to_string())
                .filter(|term| !term.is_empty())
                .collect::<Vec<_>>()
        })
        .filter(|group| !group.is_empty())
        .collect::<Vec<_>>();
    if requirements.is_empty() {
        return Err("manifest.coverage.missing_requirements".to_string());
    }
    Ok(CoverageDeclaration {
        id: id.to_string(),
        requirements,
        source_span,
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ManifestWrapper {
    HashLine,
    SlashLine,
    HtmlBlock,
    CBlock,
}

#[derive(Debug, Clone)]
struct ScannedManifestLine {
    content: Option<String>,
    wrapper_id: Option<usize>,
    start_column: usize,
}

#[derive(Debug)]
struct ManifestLineScan {
    lines: Vec<ScannedManifestLine>,
    diagnostics: Vec<Diagnostic>,
}

#[derive(Debug, Clone, Copy)]
struct BlockWrapperState {
    wrapper: ManifestWrapper,
    wrapper_id: usize,
    open_line: usize,
    has_manifest_marker: bool,
}

fn scan_manifest_lines(path: &str, lines: &[&str]) -> ManifestLineScan {
    let mut scanned = Vec::with_capacity(lines.len());
    let mut diagnostics = Vec::new();
    let mut next_wrapper_id = 1usize;
    let mut line_wrapper: Option<(ManifestWrapper, usize, usize)> = None;
    let mut block: Option<BlockWrapperState> = None;
    let mut fence: Option<&'static str> = None;

    for (line_index, raw_line) in lines.iter().enumerate() {
        let trimmed = raw_line.trim();
        if let Some(delimiter) = fence {
            if trimmed.starts_with(delimiter) {
                fence = None;
            }
            scanned.push(empty_scanned_line());
            line_wrapper = None;
            continue;
        }
        if block.is_none() {
            if let Some(delimiter) = fence_delimiter(trimmed) {
                fence = Some(delimiter);
                scanned.push(empty_scanned_line());
                line_wrapper = None;
                continue;
            }
        }
        if let Some(mut state) = block {
            let closing = match state.wrapper {
                ManifestWrapper::HtmlBlock => trimmed == "-->",
                ManifestWrapper::CBlock => trimmed == "*/",
                ManifestWrapper::HashLine | ManifestWrapper::SlashLine => false,
            };
            if closing {
                scanned.push(empty_scanned_line());
                block = None;
                line_wrapper = None;
                continue;
            }
            let prefix_len = if state.wrapper == ManifestWrapper::CBlock
                && raw_line.trim_start().starts_with('*')
            {
                1
            } else {
                0
            };
            let (content, start_column) = comment_content(raw_line, prefix_len);
            if matches!(content.as_str(), "@dependency-start" | "@dependency-end") {
                state.has_manifest_marker = true;
            }
            block = Some(state);
            scanned.push(ScannedManifestLine {
                content: Some(content),
                wrapper_id: Some(state.wrapper_id),
                start_column,
            });
            continue;
        }

        let block_wrapper = match trimmed {
            "<!--" => Some(ManifestWrapper::HtmlBlock),
            "/*" => Some(ManifestWrapper::CBlock),
            _ => None,
        };
        if let Some(wrapper) = block_wrapper {
            let wrapper_id = next_wrapper_id;
            next_wrapper_id += 1;
            block = Some(BlockWrapperState {
                wrapper,
                wrapper_id,
                open_line: line_index,
                has_manifest_marker: false,
            });
            scanned.push(empty_scanned_line());
            line_wrapper = None;
            continue;
        }

        let line_comment = if trimmed.starts_with('#') {
            Some((ManifestWrapper::HashLine, 1usize))
        } else if trimmed.starts_with("//") {
            Some((ManifestWrapper::SlashLine, 2usize))
        } else {
            None
        };
        if let Some((wrapper, prefix_len)) = line_comment {
            let wrapper_id = match line_wrapper {
                Some((previous, wrapper_id, previous_line))
                    if previous == wrapper && previous_line + 1 == line_index =>
                {
                    wrapper_id
                }
                _ => {
                    let wrapper_id = next_wrapper_id;
                    next_wrapper_id += 1;
                    wrapper_id
                }
            };
            line_wrapper = Some((wrapper, wrapper_id, line_index));
            let (content, start_column) = comment_content(raw_line, prefix_len);
            scanned.push(ScannedManifestLine {
                content: Some(content),
                wrapper_id: Some(wrapper_id),
                start_column,
            });
            continue;
        }

        line_wrapper = None;
        if matches!(trimmed, "@dependency-start" | "@dependency-end") {
            let marker = trimmed.trim_start_matches("@dependency-");
            diagnostics.push(diagnostic(
                &format!("manifest.marker.bare_{marker}"),
                format!("bare {trimmed} is not inside a documented comment wrapper"),
                Some(span_for(path, line_index, raw_line)),
            ));
        }
        scanned.push(empty_scanned_line());
    }

    if let Some(state) = block {
        if state.has_manifest_marker {
            diagnostics.push(diagnostic(
                "manifest.wrapper.unclosed",
                "manifest outer comment wrapper is not closed",
                Some(span_for(path, state.open_line, lines[state.open_line])),
            ));
        }
    }
    ManifestLineScan {
        lines: scanned,
        diagnostics,
    }
}

fn empty_scanned_line() -> ScannedManifestLine {
    ScannedManifestLine {
        content: None,
        wrapper_id: None,
        start_column: 1,
    }
}

fn fence_delimiter(line: &str) -> Option<&'static str> {
    if line.starts_with("```") {
        Some("```")
    } else if line.starts_with("~~~") {
        Some("~~~")
    } else {
        None
    }
}

fn comment_content(line: &str, prefix_len: usize) -> (String, usize) {
    let leading = line.len() - line.trim_start().len();
    let mut offset = leading + prefix_len;
    while line
        .as_bytes()
        .get(offset)
        .is_some_and(|byte| byte.is_ascii_whitespace())
    {
        offset += 1;
    }
    (line[offset..].trim_end().to_string(), offset + 1)
}

fn span_for_scanned(path: &str, line_index: usize, line: &ScannedManifestLine) -> SourceSpan {
    SourceSpan {
        path: path.to_string(),
        start_line: line_index + 1,
        start_column: line.start_column,
        end_line: line_index + 1,
        end_column: line.start_column + line.content.as_deref().unwrap_or_default().len(),
    }
}

fn span_for(path: &str, line_index: usize, line: &str) -> SourceSpan {
    SourceSpan {
        path: path.to_string(),
        start_line: line_index + 1,
        start_column: 1,
        end_line: line_index + 1,
        end_column: line.len() + 1,
    }
}

fn diagnostic(
    code: &str,
    message: impl Into<String>,
    source_span: Option<SourceSpan>,
) -> Diagnostic {
    Diagnostic {
        code: code.to_string(),
        message: message.into(),
        severity: "error".to_string(),
        source_span,
    }
}

fn render_diagnostic(diagnostic: &Diagnostic) {
    let location = diagnostic
        .source_span
        .as_ref()
        .map(|span| format!("{}:{}", span.path, span.start_line))
        .unwrap_or_else(|| "snapshot".to_string());
    eprintln!(
        "DEPENDENCY_MANIFEST_DIAGNOSTIC={}:{}:{}",
        diagnostic.code, location, diagnostic.message
    );
}

fn write_snapshot_jsonl(
    snapshot: &ManifestSnapshot,
    writer: &mut impl Write,
) -> Result<(), ManifestError> {
    let header_payload = json!({
        "snapshot_id": snapshot.header.snapshot_id,
        "parent_repo_id": snapshot.header.parent_repo_id,
        "root_realpath": snapshot.header.root_realpath,
        "git_head": snapshot.header.git_head,
        "git_index_tree": snapshot.header.git_index_tree,
        "git_worktree_dirty": snapshot.header.git_worktree_dirty,
        "git_status_hash": snapshot.header.git_status_hash,
        "dirty_paths": snapshot.header.dirty_paths,
        "agentcanon_pin": snapshot.header.agentcanon_pin,
        "schema_version": snapshot.header.schema_version,
        "tool_version": snapshot.header.tool_version,
        "profile": snapshot.header.profile,
        "path_sort": snapshot.header.path_sort,
        "source_fingerprint": snapshot.header.source_fingerprint,
        "captured_before_hash": snapshot.header.captured_before_hash,
        "captured_after_hash": snapshot.header.captured_after_hash,
        "snapshot_consistent": snapshot.header.snapshot_consistent,
    });
    write_envelope(
        writer,
        SNAPSHOT_SCHEMA_VERSION,
        &snapshot.header.snapshot_id,
        &snapshot.header.snapshot_id,
        header_payload,
    )?;

    let mut identities = snapshot.source_identities.clone();
    identities.sort_by(|left, right| left.repo_rel_path.cmp(&right.repo_rel_path));
    for identity in identities {
        let payload = json!({
            "identity_id": identity.identity_id,
            "logical_id": identity.logical_id,
            "repo_rel_path": identity.repo_rel_path,
            "canonical_locator": identity.canonical_locator,
            "alternate_locators": identity.alternate_locators,
            "locator_kind": identity.locator_kind,
            "path_role": identity.path_role,
            "file_mode": identity.file_mode,
            "exists": identity.exists,
            "is_dirty": identity.is_dirty,
            "content_hash": identity.content_hash,
            "git_blob_or_gitlink": identity.git_blob_or_gitlink,
            "submodule_commit": identity.submodule_commit,
            "snapshot_id": identity.snapshot_id,
        });
        write_envelope(
            writer,
            "source_identity.v1",
            &identity.identity_id,
            &snapshot.header.snapshot_id,
            payload,
        )?;
    }

    let mut surfaces = snapshot.surface_relations.clone();
    surfaces.sort_by(|left, right| left.relation_id.cmp(&right.relation_id));
    for relation in surfaces {
        let payload = json!({
            "relation_id": relation.relation_id,
            "relation_type": relation.relation_type,
            "source_identity_id": relation.source_identity_id,
            "target_identity_id": relation.target_identity_id,
            "source_path": relation.source_path,
            "target_path": relation.target_path,
            "owner_class": relation.owner_class,
            "surface_mode": relation.surface_mode,
            "content_hash_equal": relation.content_hash_equal,
            "evidence_id": relation.evidence_id,
            "status": relation.status,
            "snapshot_id": relation.snapshot_id,
        });
        write_envelope(
            writer,
            "surface_relation.v1",
            &relation.relation_id,
            &snapshot.header.snapshot_id,
            payload,
        )?;
    }

    let mut exclusions = snapshot.source_exclusions.clone();
    exclusions.sort_by(|left, right| left.repo_rel_path.cmp(&right.repo_rel_path));
    for exclusion in exclusions {
        let payload = json!({
            "source_exclusion_id": exclusion.source_exclusion_id,
            "source_identity_id": exclusion.source_identity_id,
            "repo_rel_path": exclusion.repo_rel_path,
            "reason_code": exclusion.reason_code,
            "rule_id": exclusion.rule_id,
            "scope": exclusion.scope,
            "evidence_id": exclusion.evidence_id,
            "covered": exclusion.covered,
            "snapshot_id": exclusion.snapshot_id,
        });
        write_envelope(
            writer,
            "source_exclusion.v1",
            &exclusion.source_exclusion_id,
            &snapshot.header.snapshot_id,
            payload,
        )?;
    }

    let mut declarations = snapshot.declarations.clone();
    declarations.sort_by(|left, right| left.declaration_id.cmp(&right.declaration_id));
    for declaration in declarations {
        let payload = json!({
            "declaration_id": declaration.declaration_id,
            "source_identity_id": declaration.source_identity_id,
            "declared_direction": declaration.declared_direction,
            "declared_kind": declaration.declared_kind,
            "declared_target": declaration.declared_target,
            "resolved_target_identity_id": declaration.resolved_target_identity_id,
            "source_span": source_span_json(&declaration.source_span),
            "reason": declaration.reason,
            "raw_line_hash": declaration.raw_line_hash,
            "attestation_key": declaration.attestation_key,
            "snapshot_id": declaration.snapshot_id,
        });
        write_envelope(
            writer,
            "dependency_declaration.v1",
            &declaration.declaration_id,
            &snapshot.header.snapshot_id,
            payload,
        )?;
    }
    Ok(())
}

fn write_envelope(
    writer: &mut impl Write,
    record_type: &str,
    record_id: &str,
    snapshot_id: &str,
    payload: Value,
) -> Result<(), ManifestError> {
    let envelope = json!({
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "record_type": record_type,
        "record_id": record_id,
        "snapshot_id": snapshot_id,
        "payload": payload,
    });
    serde_json::to_writer(&mut *writer, &envelope)
        .map_err(|error| ManifestError::Transport(error.to_string()))?;
    writer
        .write_all(b"\n")
        .map_err(|error| ManifestError::Io(error.to_string()))
}

fn source_span_json(span: &SourceSpan) -> Value {
    json!({
        "path": span.path,
        "start_line": span.start_line,
        "start_column": span.start_column,
        "end_line": span.end_line,
        "end_column": span.end_column,
    })
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), ManifestError> {
    write_atomic_with_failure(path, bytes, AtomicFailurePoint::None)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AtomicFailurePoint {
    None,
    Write,
    Sync,
    Rename,
}

struct CandidateCleanup {
    path: PathBuf,
    armed: bool,
}

impl CandidateCleanup {
    fn new(path: PathBuf) -> Self {
        Self { path, armed: true }
    }

    fn disarm(&mut self) {
        self.armed = false;
    }
}

impl Drop for CandidateCleanup {
    fn drop(&mut self) {
        if self.armed {
            let _ = fs::remove_file(&self.path);
        }
    }
}

fn write_atomic_with_failure(
    path: &Path,
    bytes: &[u8],
    failure: AtomicFailurePoint,
) -> Result<(), ManifestError> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent).map_err(|error| ManifestError::Io(error.to_string()))?;
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("source_snapshot.v1.jsonl");
    let candidate = parent.join(format!(".{file_name}.{}.candidate", std::process::id()));
    let mut cleanup = CandidateCleanup::new(candidate.clone());
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&candidate)
        .map_err(|error| ManifestError::Io(error.to_string()))?;
    if failure == AtomicFailurePoint::Write {
        return Err(ManifestError::Io(
            "injected candidate write failure".to_string(),
        ));
    }
    file.write_all(bytes)
        .map_err(|error| ManifestError::Io(error.to_string()))?;
    if failure == AtomicFailurePoint::Sync {
        return Err(ManifestError::Io(
            "injected candidate sync failure".to_string(),
        ));
    }
    file.sync_all()
        .map_err(|error| ManifestError::Io(error.to_string()))?;
    drop(file);
    if failure == AtomicFailurePoint::Rename {
        return Err(ManifestError::Io(
            "injected candidate rename failure".to_string(),
        ));
    }
    fs::rename(&candidate, path).map_err(|error| ManifestError::Io(error.to_string()))?;
    cleanup.disarm();
    if let Ok(directory) = File::open(parent) {
        let _ = directory.sync_all();
    }
    Ok(())
}

pub(crate) fn parse_snapshot(reader: impl BufRead) -> Result<ManifestSnapshot, ManifestError> {
    let mut records = Vec::new();
    for (line_index, line) in reader.lines().enumerate() {
        let line = line.map_err(|error| ManifestError::Transport(error.to_string()))?;
        if line.trim().is_empty() {
            return Err(ManifestError::Transport(format!(
                "blank JSONL line {}",
                line_index + 1
            )));
        }
        records.push(serde_json::from_str::<Value>(&line).map_err(|error| {
            ManifestError::Transport(format!("line {}: {error}", line_index + 1))
        })?);
    }
    let first = records
        .first()
        .ok_or_else(|| ManifestError::Transport("empty snapshot".to_string()))?;
    if first.get("record_type").and_then(Value::as_str) != Some(SNAPSHOT_SCHEMA_VERSION) {
        return Err(ManifestError::Transport(
            "source_snapshot.v1 must be the first record".to_string(),
        ));
    }
    let header_envelope = parse_envelope(first, SNAPSHOT_SCHEMA_VERSION, true)?;
    let header = parse_snapshot_header(header_envelope.payload)?;
    if header.snapshot_id != header_envelope.snapshot_id
        || header.snapshot_id != header_envelope.record_id
    {
        return Err(ManifestError::Transport(
            "snapshot header payload snapshot_id mismatch".to_string(),
        ));
    }
    let snapshot_id = header.snapshot_id.clone();
    let mut source_identities = Vec::new();
    let mut declarations = Vec::new();
    let mut source_exclusions = Vec::new();
    let mut surface_relations = Vec::new();
    for value in records.iter().skip(1) {
        let record_type = value
            .get("record_type")
            .and_then(Value::as_str)
            .ok_or_else(|| ManifestError::Transport("record_type is required".to_string()))?;
        let envelope = parse_envelope(value, record_type, false)?;
        if envelope.snapshot_id != snapshot_id {
            return Err(ManifestError::Transport("mixed snapshot IDs".to_string()));
        }
        match record_type {
            SNAPSHOT_SCHEMA_VERSION => {
                return Err(ManifestError::Transport(
                    "duplicate source snapshot header record ID".to_string(),
                ));
            }
            "source_identity.v1" => {
                let record = parse_source_identity(envelope.record_id, envelope.payload)?;
                if record.snapshot_id != snapshot_id {
                    return Err(ManifestError::Transport(
                        "source identity snapshot mismatch".to_string(),
                    ));
                }
                source_identities.push(record);
            }
            "dependency_declaration.v1" => {
                let record = parse_declaration(envelope.record_id, envelope.payload)?;
                if record.snapshot_id != snapshot_id {
                    return Err(ManifestError::Transport(
                        "declaration snapshot mismatch".to_string(),
                    ));
                }
                declarations.push(record);
            }
            "source_exclusion.v1" => {
                let record = parse_source_exclusion(envelope.record_id, envelope.payload)?;
                if record.snapshot_id != snapshot_id {
                    return Err(ManifestError::Transport(
                        "source exclusion snapshot mismatch".to_string(),
                    ));
                }
                source_exclusions.push(record);
            }
            "surface_relation.v1" => {
                let record = parse_surface_relation(envelope.record_id, envelope.payload)?;
                if record.snapshot_id != snapshot_id {
                    return Err(ManifestError::Transport(
                        "surface relation snapshot mismatch".to_string(),
                    ));
                }
                surface_relations.push(record);
            }
            _ => {
                return Err(ManifestError::Transport(format!(
                    "unknown snapshot record type {record_type}"
                )))
            }
        }
    }
    if !header.snapshot_consistent {
        return Err(ManifestError::SnapshotInconsistent(
            "snapshot_consistent=false".to_string(),
        ));
    }
    ensure_unique_record_ids(
        "source identity",
        source_identities
            .iter()
            .map(|item| item.identity_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "dependency declaration",
        declarations.iter().map(|item| item.declaration_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "source exclusion",
        source_exclusions
            .iter()
            .map(|item| item.source_exclusion_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "surface relation",
        surface_relations
            .iter()
            .map(|item| item.relation_id.as_str()),
    )?;
    source_identities.sort_by(|left, right| left.repo_rel_path.cmp(&right.repo_rel_path));
    declarations.sort_by(|left, right| left.declaration_id.cmp(&right.declaration_id));
    source_exclusions
        .sort_by(|left, right| left.source_exclusion_id.cmp(&right.source_exclusion_id));
    surface_relations.sort_by(|left, right| left.relation_id.cmp(&right.relation_id));
    validate_snapshot_transport(
        &header,
        &mut source_identities,
        &declarations,
        &source_exclusions,
        &surface_relations,
    )?;
    let candidate_paths = source_identities
        .iter()
        .map(|identity| identity.repo_rel_path.clone())
        .collect::<Vec<_>>();
    let source_universe =
        materialize_source_universe(&candidate_paths, &source_identities, &source_exclusions)?;
    Ok(ManifestSnapshot {
        header,
        source_identities,
        declarations,
        source_exclusions,
        surface_relations,
        source_universe,
        diagnostics: Vec::new(),
    })
}

fn ensure_unique_record_ids<'a>(
    family: &str,
    ids: impl Iterator<Item = &'a str>,
) -> Result<(), ManifestError> {
    let mut seen = BTreeSet::new();
    for id in ids {
        if !seen.insert(id) {
            return Err(ManifestError::Transport(format!(
                "duplicate {family} record ID {id}"
            )));
        }
    }
    Ok(())
}

struct ParsedEnvelope<'a> {
    record_id: &'a str,
    snapshot_id: String,
    payload: &'a Value,
}

fn parse_envelope<'a>(
    value: &'a Value,
    expected_type: &str,
    header: bool,
) -> Result<ParsedEnvelope<'a>, ManifestError> {
    let object = value
        .as_object()
        .ok_or_else(|| ManifestError::Transport("record must be an object".to_string()))?;
    ensure_exact_keys(
        object,
        &[
            "schema_version",
            "record_type",
            "record_id",
            "snapshot_id",
            "payload",
        ],
    )?;
    if object.get("schema_version").and_then(Value::as_str) != Some(MANIFEST_SCHEMA_VERSION) {
        return Err(ManifestError::Transport("schema mismatch".to_string()));
    }
    if object.get("record_type").and_then(Value::as_str) != Some(expected_type) {
        return Err(ManifestError::Transport("record type mismatch".to_string()));
    }
    let record_id = object
        .get("record_id")
        .and_then(Value::as_str)
        .ok_or_else(|| ManifestError::Transport("record_id must be a string".to_string()))?;
    let snapshot_id = object
        .get("snapshot_id")
        .and_then(Value::as_str)
        .ok_or_else(|| ManifestError::Transport("snapshot_id must be a string".to_string()))?
        .to_string();
    if header && record_id != snapshot_id {
        return Err(ManifestError::Transport(
            "snapshot header record_id mismatch".to_string(),
        ));
    }
    Ok(ParsedEnvelope {
        record_id,
        snapshot_id,
        payload: object
            .get("payload")
            .ok_or_else(|| ManifestError::Transport("payload is required".to_string()))?,
    })
}

fn parse_snapshot_header(value: &Value) -> Result<SnapshotHeader, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("snapshot payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "snapshot_id",
            "parent_repo_id",
            "root_realpath",
            "git_head",
            "git_index_tree",
            "git_worktree_dirty",
            "git_status_hash",
            "dirty_paths",
            "agentcanon_pin",
            "schema_version",
            "tool_version",
            "profile",
            "path_sort",
            "source_fingerprint",
            "captured_before_hash",
            "captured_after_hash",
            "snapshot_consistent",
        ],
    )?;
    Ok(SnapshotHeader {
        snapshot_id: string_field(object, "snapshot_id")?,
        parent_repo_id: string_field(object, "parent_repo_id")?,
        root_realpath: string_field(object, "root_realpath")?,
        git_head: string_field(object, "git_head")?,
        git_index_tree: string_field(object, "git_index_tree")?,
        git_worktree_dirty: bool_field(object, "git_worktree_dirty")?,
        git_status_hash: string_field(object, "git_status_hash")?,
        dirty_paths: string_array_field(object, "dirty_paths")?,
        agentcanon_pin: string_field(object, "agentcanon_pin")?,
        schema_version: string_field(object, "schema_version")?,
        tool_version: string_field(object, "tool_version")?,
        profile: string_field(object, "profile")?,
        path_sort: string_field(object, "path_sort")?,
        source_fingerprint: string_field(object, "source_fingerprint")?,
        captured_before_hash: string_field(object, "captured_before_hash")?,
        captured_after_hash: string_field(object, "captured_after_hash")?,
        snapshot_consistent: bool_field(object, "snapshot_consistent")?,
    })
}

fn parse_source_identity(record_id: &str, value: &Value) -> Result<SourceIdentity, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("source identity payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "identity_id",
            "logical_id",
            "repo_rel_path",
            "canonical_locator",
            "alternate_locators",
            "locator_kind",
            "path_role",
            "file_mode",
            "exists",
            "is_dirty",
            "content_hash",
            "git_blob_or_gitlink",
            "submodule_commit",
            "snapshot_id",
        ],
    )?;
    let identity_id = string_field(object, "identity_id")?;
    if identity_id != record_id {
        return Err(ManifestError::Transport(
            "source identity record_id mismatch".to_string(),
        ));
    }
    Ok(SourceIdentity {
        identity_id,
        logical_id: string_field(object, "logical_id")?,
        repo_rel_path: string_field(object, "repo_rel_path")?,
        canonical_locator: string_field(object, "canonical_locator")?,
        alternate_locators: string_array_field(object, "alternate_locators")?,
        locator_kind: string_field(object, "locator_kind")?,
        path_role: string_field(object, "path_role")?,
        file_mode: string_field(object, "file_mode")?,
        exists: bool_field(object, "exists")?,
        is_dirty: bool_field(object, "is_dirty")?,
        content_hash: string_field(object, "content_hash")?,
        git_blob_or_gitlink: string_field(object, "git_blob_or_gitlink")?,
        submodule_commit: string_field(object, "submodule_commit")?,
        snapshot_id: string_field(object, "snapshot_id")?,
        owner_class: String::new(),
        surface_mode: String::new(),
    })
}

fn parse_declaration(
    record_id: &str,
    value: &Value,
) -> Result<DependencyDeclaration, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("declaration payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "declaration_id",
            "source_identity_id",
            "declared_direction",
            "declared_kind",
            "declared_target",
            "resolved_target_identity_id",
            "source_span",
            "reason",
            "raw_line_hash",
            "attestation_key",
            "snapshot_id",
        ],
    )?;
    let declaration_id = string_field(object, "declaration_id")?;
    if declaration_id != record_id {
        return Err(ManifestError::Transport(
            "declaration record_id mismatch".to_string(),
        ));
    }
    Ok(DependencyDeclaration {
        declaration_id,
        source_identity_id: string_field(object, "source_identity_id")?,
        declared_direction: string_field(object, "declared_direction")?,
        declared_kind: string_field(object, "declared_kind")?,
        declared_target: string_field(object, "declared_target")?,
        resolved_target_identity_id: optional_string_field(object, "resolved_target_identity_id")?,
        source_span: parse_source_span(
            object
                .get("source_span")
                .ok_or_else(|| ManifestError::Transport("source_span missing".to_string()))?,
        )?,
        reason: string_field(object, "reason")?,
        raw_line_hash: string_field(object, "raw_line_hash")?,
        attestation_key: string_field(object, "attestation_key")?,
        snapshot_id: string_field(object, "snapshot_id")?,
    })
}

fn parse_source_exclusion(
    record_id: &str,
    value: &Value,
) -> Result<SourceExclusion, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("source exclusion payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "source_exclusion_id",
            "source_identity_id",
            "repo_rel_path",
            "reason_code",
            "rule_id",
            "scope",
            "evidence_id",
            "covered",
            "snapshot_id",
        ],
    )?;
    let source_exclusion_id = string_field(object, "source_exclusion_id")?;
    if source_exclusion_id != record_id {
        return Err(ManifestError::Transport(
            "source exclusion record_id mismatch".to_string(),
        ));
    }
    Ok(SourceExclusion {
        source_exclusion_id,
        source_identity_id: string_field(object, "source_identity_id")?,
        repo_rel_path: string_field(object, "repo_rel_path")?,
        reason_code: string_field(object, "reason_code")?,
        rule_id: string_field(object, "rule_id")?,
        scope: string_field(object, "scope")?,
        evidence_id: string_field(object, "evidence_id")?,
        covered: bool_field(object, "covered")?,
        snapshot_id: string_field(object, "snapshot_id")?,
    })
}

fn parse_surface_relation(
    record_id: &str,
    value: &Value,
) -> Result<SurfaceRelation, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("surface relation payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "relation_id",
            "relation_type",
            "source_identity_id",
            "target_identity_id",
            "source_path",
            "target_path",
            "owner_class",
            "surface_mode",
            "content_hash_equal",
            "evidence_id",
            "status",
            "snapshot_id",
        ],
    )?;
    let relation_id = string_field(object, "relation_id")?;
    if relation_id != record_id {
        return Err(ManifestError::Transport(
            "surface relation record_id mismatch".to_string(),
        ));
    }
    Ok(SurfaceRelation {
        relation_id,
        relation_type: string_field(object, "relation_type")?,
        source_identity_id: string_field(object, "source_identity_id")?,
        target_identity_id: string_field(object, "target_identity_id")?,
        source_path: string_field(object, "source_path")?,
        target_path: string_field(object, "target_path")?,
        owner_class: string_field(object, "owner_class")?,
        surface_mode: string_field(object, "surface_mode")?,
        content_hash_equal: bool_field(object, "content_hash_equal")?,
        evidence_id: string_field(object, "evidence_id")?,
        status: string_field(object, "status")?,
        snapshot_id: string_field(object, "snapshot_id")?,
    })
}

fn validate_snapshot_transport(
    header: &SnapshotHeader,
    source_identities: &mut [SourceIdentity],
    declarations: &[DependencyDeclaration],
    source_exclusions: &[SourceExclusion],
    surface_relations: &[SurfaceRelation],
) -> Result<(), ManifestError> {
    if !is_hex_id(&header.snapshot_id) {
        return Err(ManifestError::Transport(
            "snapshot_id must be lowercase 64-hex".to_string(),
        ));
    }
    for (field, value) in [
        ("parent_repo_id", header.parent_repo_id.as_str()),
        ("git_status_hash", header.git_status_hash.as_str()),
        ("source_fingerprint", header.source_fingerprint.as_str()),
        ("captured_before_hash", header.captured_before_hash.as_str()),
        ("captured_after_hash", header.captured_after_hash.as_str()),
    ] {
        if !is_hex_id(value) {
            return Err(ManifestError::Transport(format!(
                "{field} must be lowercase 64-hex"
            )));
        }
    }
    if header.schema_version != SNAPSHOT_SCHEMA_VERSION {
        return Err(ManifestError::Transport(
            "snapshot schema mismatch".to_string(),
        ));
    }
    if header.tool_version != TOOL_VERSION {
        return Err(ManifestError::Transport(
            "snapshot tool version mismatch".to_string(),
        ));
    }
    if header.profile != "parent" {
        return Err(ManifestError::Transport(
            "snapshot profile mismatch".to_string(),
        ));
    }
    if header.path_sort != PATH_SORT {
        return Err(ManifestError::Transport(
            "snapshot path_sort mismatch".to_string(),
        ));
    }
    let dirty_paths = header.dirty_paths.iter().cloned().collect::<BTreeSet<_>>();
    if dirty_paths.len() != header.dirty_paths.len()
        || dirty_paths.iter().cloned().collect::<Vec<_>>() != header.dirty_paths
    {
        return Err(ManifestError::Transport(
            "dirty_paths must be unique and UTF-8 bytewise sorted".to_string(),
        ));
    }
    if header.captured_before_hash != header.captured_after_hash {
        return Err(ManifestError::SnapshotInconsistent(
            "snapshot_consistent=true but capture hashes differ".to_string(),
        ));
    }
    let expected_capture_hash = hash_parts(&[
        &header.git_head,
        &header.git_index_tree,
        &header.git_status_hash,
        &header.agentcanon_pin,
        &header.schema_version,
        &header.tool_version,
        &header.profile,
    ]);
    if header.captured_before_hash != expected_capture_hash
        || header.captured_after_hash != expected_capture_hash
    {
        return Err(ManifestError::Transport(
            "snapshot capture hash mismatch".to_string(),
        ));
    }

    let identities_by_id = source_identities
        .iter()
        .map(|identity| (identity.identity_id.clone(), identity.repo_rel_path.clone()))
        .collect::<BTreeMap<_, _>>();
    if identities_by_id.len() != source_identities.len() {
        return Err(ManifestError::Transport(
            "duplicate source identity record ID".to_string(),
        ));
    }
    let identity_by_path = source_identities
        .iter()
        .map(|identity| (identity.repo_rel_path.clone(), identity.identity_id.clone()))
        .collect::<BTreeMap<_, _>>();
    let identity_by_locator = source_identities
        .iter()
        .map(|identity| {
            (
                identity.canonical_locator.clone(),
                identity.identity_id.clone(),
            )
        })
        .collect::<BTreeMap<_, _>>();
    for identity in source_identities.iter() {
        if identity.snapshot_id != header.snapshot_id {
            return Err(ManifestError::Transport(
                "source identity snapshot mismatch".to_string(),
            ));
        }
        let expected_identity_id = hash_parts(&[
            "source_identity.v1",
            &header.parent_repo_id,
            &identity.repo_rel_path,
        ]);
        if identity.identity_id != expected_identity_id {
            return Err(ManifestError::Transport(format!(
                "source identity ID mismatch for {}",
                identity.repo_rel_path
            )));
        }
        let expected_logical_id = hash_parts(&[
            "logical_source.v1",
            &header.parent_repo_id,
            &identity.canonical_locator,
        ]);
        if identity.logical_id != expected_logical_id {
            return Err(ManifestError::Transport(format!(
                "logical source ID mismatch for {}",
                identity.repo_rel_path
            )));
        }
        if !CANONICAL_GIT_MODES.contains(&identity.file_mode.as_str()) {
            return Err(ManifestError::Transport(format!(
                "non-canonical Git mode {} for {}",
                identity.file_mode, identity.repo_rel_path
            )));
        }
        let alternate_locators = identity
            .alternate_locators
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        if alternate_locators.len() != identity.alternate_locators.len()
            || alternate_locators.iter().cloned().collect::<Vec<_>>() != identity.alternate_locators
        {
            return Err(ManifestError::Transport(format!(
                "alternate locators are not unique and sorted for {}",
                identity.repo_rel_path
            )));
        }
    }

    let mut classifications = BTreeMap::<String, (String, String)>::new();
    for relation in surface_relations {
        if relation.snapshot_id != header.snapshot_id {
            return Err(ManifestError::Transport(
                "surface relation snapshot mismatch".to_string(),
            ));
        }
        let Some(source_path) = identities_by_id.get(&relation.source_identity_id) else {
            return Err(ManifestError::Transport(format!(
                "surface relation {} references an unknown source identity",
                relation.relation_id
            )));
        };
        if source_path != &relation.source_path {
            return Err(ManifestError::Transport(format!(
                "surface relation {} source path mismatch",
                relation.relation_id
            )));
        }
        let expected_target_identity_id = identity_by_path
            .get(&relation.target_path)
            .cloned()
            .or_else(|| identity_by_locator.get(&relation.target_path).cloned())
            .unwrap_or_else(|| {
                hash_parts(&[
                    "source_identity.v1",
                    &header.parent_repo_id,
                    &relation.target_path,
                ])
            });
        if relation.target_identity_id != expected_target_identity_id {
            return Err(ManifestError::Transport(format!(
                "surface relation target identity ID mismatch for {}",
                relation.source_path
            )));
        }
        let expected_relation_id = hash_parts(&[
            "surface_relation.v1",
            &relation.source_identity_id,
            &relation.target_identity_id,
            &relation.relation_type,
        ]);
        if relation.relation_id != expected_relation_id
            || relation.evidence_id != relation.relation_id
        {
            return Err(ManifestError::Transport(format!(
                "surface relation ID mismatch for {}",
                relation.source_path
            )));
        }
        if relation.owner_class.is_empty() || relation.surface_mode.is_empty() {
            return Err(ManifestError::Transport(format!(
                "surface relation {} lacks owner/mode provenance",
                relation.relation_id
            )));
        }
        let classification = (relation.owner_class.clone(), relation.surface_mode.clone());
        if classifications
            .insert(relation.source_identity_id.clone(), classification.clone())
            .is_some_and(|previous| previous != classification)
        {
            return Err(ManifestError::Transport(format!(
                "conflicting surface classification for {}",
                relation.source_path
            )));
        }
    }
    for identity in source_identities.iter_mut() {
        if let Some((owner_class, surface_mode)) = classifications.get(&identity.identity_id) {
            identity.owner_class = owner_class.clone();
            identity.surface_mode = surface_mode.clone();
        } else {
            identity.owner_class = "unresolved".to_string();
            identity.surface_mode = "regular".to_string();
        }
    }

    for exclusion in source_exclusions {
        if exclusion.snapshot_id != header.snapshot_id {
            return Err(ManifestError::Transport(
                "source exclusion snapshot mismatch".to_string(),
            ));
        }
        if exclusion.covered {
            return Err(ManifestError::Transport(format!(
                "source exclusion {} must have covered=false",
                exclusion.source_exclusion_id
            )));
        }
        let expected_exclusion_id = hash_parts(&[
            "source_exclusion.v1",
            &exclusion.source_identity_id,
            &exclusion.reason_code,
            &exclusion.scope,
        ]);
        if exclusion.source_exclusion_id != expected_exclusion_id
            || exclusion.evidence_id != exclusion.source_identity_id
        {
            return Err(ManifestError::Transport(format!(
                "source exclusion ID mismatch for {}",
                exclusion.repo_rel_path
            )));
        }
    }
    for declaration in declarations {
        if declaration.snapshot_id != header.snapshot_id {
            return Err(ManifestError::Transport(
                "declaration snapshot mismatch".to_string(),
            ));
        }
        let Some(source_path) = identities_by_id.get(&declaration.source_identity_id) else {
            return Err(ManifestError::Transport(format!(
                "declaration {} references an unknown source identity",
                declaration.declaration_id
            )));
        };
        if source_path != &declaration.source_span.path {
            return Err(ManifestError::Transport(format!(
                "declaration {} source span path mismatch",
                declaration.declaration_id
            )));
        }
        if !matches!(
            declaration.declared_direction.as_str(),
            "upstream" | "downstream"
        ) || !matches!(
            declaration.declared_kind.as_str(),
            "design" | "implementation" | "environment"
        ) {
            return Err(ManifestError::Transport(format!(
                "declaration {} has an invalid direction or kind",
                declaration.declaration_id
            )));
        }
        if let Some(target_id) = &declaration.resolved_target_identity_id {
            if !identities_by_id.contains_key(target_id) {
                return Err(ManifestError::Transport(format!(
                    "declaration {} resolved target is unknown",
                    declaration.declaration_id
                )));
            }
        }
        let start_line = declaration.source_span.start_line.to_string();
        let end_line = declaration.source_span.end_line.to_string();
        let expected_declaration_id = hash_parts(&[
            "dependency_declaration.v1",
            &declaration.source_identity_id,
            &start_line,
            &end_line,
            &declaration.declared_direction,
            &declaration.declared_kind,
            &declaration.declared_target,
            &declaration.raw_line_hash,
        ]);
        let expected_attestation_key = hash_parts(&[
            "dependency_attestation.v1",
            &header.snapshot_id,
            &declaration.source_identity_id,
            &start_line,
            &end_line,
            &declaration.declared_direction,
            &declaration.declared_kind,
            &declaration.declared_target,
            &declaration.raw_line_hash,
        ]);
        if declaration.declaration_id != expected_declaration_id
            || declaration.attestation_key != expected_attestation_key
        {
            return Err(ManifestError::Transport(format!(
                "declaration ID mismatch for {}",
                declaration.source_span.path
            )));
        }
    }

    let expected_source_fingerprint = source_fingerprint_from_transport(header, source_identities);
    if header.source_fingerprint != expected_source_fingerprint {
        return Err(ManifestError::Transport(
            "source fingerprint mismatch".to_string(),
        ));
    }
    let expected_snapshot_id = hash_parts(&[
        "source_snapshot.v1",
        &header.parent_repo_id,
        &header.source_fingerprint,
        &header.schema_version,
        &header.tool_version,
        &header.profile,
    ]);
    if header.snapshot_id != expected_snapshot_id {
        return Err(ManifestError::Transport("snapshot ID mismatch".to_string()));
    }
    Ok(())
}

fn source_fingerprint_from_transport(
    header: &SnapshotHeader,
    source_identities: &[SourceIdentity],
) -> String {
    let mut parts = vec![
        "source_fingerprint.v1".to_string(),
        header.git_head.clone(),
        header.git_worktree_dirty.to_string(),
        header.git_status_hash.clone(),
        header.agentcanon_pin.clone(),
        header.schema_version.clone(),
        header.tool_version.clone(),
        header.profile.clone(),
    ];
    for identity in source_identities {
        parts.extend([
            identity.repo_rel_path.clone(),
            identity.file_mode.clone(),
            identity.exists.to_string(),
            identity.content_hash.clone(),
            identity.git_blob_or_gitlink.clone(),
            identity.submodule_commit.clone(),
            identity.path_role.clone(),
            identity.owner_class.clone(),
            identity.surface_mode.clone(),
        ]);
    }
    hash_parts(&parts.iter().map(String::as_str).collect::<Vec<_>>())
}

fn parse_source_span(value: &Value) -> Result<SourceSpan, ManifestError> {
    let object = value
        .as_object()
        .ok_or_else(|| ManifestError::Transport("source_span must be an object".to_string()))?;
    ensure_exact_keys(
        object,
        &[
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
        ],
    )?;
    Ok(SourceSpan {
        path: string_field(object, "path")?,
        start_line: usize_field(object, "start_line")?,
        start_column: usize_field(object, "start_column")?,
        end_line: usize_field(object, "end_line")?,
        end_column: usize_field(object, "end_column")?,
    })
}

fn ensure_exact_keys(object: &Map<String, Value>, expected: &[&str]) -> Result<(), ManifestError> {
    let expected = expected.iter().copied().collect::<BTreeSet<_>>();
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    if expected != actual {
        return Err(ManifestError::Transport(format!(
            "schema fields mismatch: expected {expected:?}, actual {actual:?}"
        )));
    }
    Ok(())
}

fn string_field(object: &Map<String, Value>, field: &str) -> Result<String, ManifestError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .map(ToString::to_string)
        .ok_or_else(|| ManifestError::Transport(format!("{field} must be a string")))
}

fn optional_string_field(
    object: &Map<String, Value>,
    field: &str,
) -> Result<Option<String>, ManifestError> {
    match object.get(field) {
        Some(Value::Null) => Ok(None),
        Some(Value::String(value)) => Ok(Some(value.clone())),
        _ => Err(ManifestError::Transport(format!(
            "{field} must be string or null"
        ))),
    }
}

fn bool_field(object: &Map<String, Value>, field: &str) -> Result<bool, ManifestError> {
    object
        .get(field)
        .and_then(Value::as_bool)
        .ok_or_else(|| ManifestError::Transport(format!("{field} must be boolean")))
}

fn usize_field(object: &Map<String, Value>, field: &str) -> Result<usize, ManifestError> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .ok_or_else(|| ManifestError::Transport(format!("{field} must be a non-negative integer")))
}

fn string_array_field(
    object: &Map<String, Value>,
    field: &str,
) -> Result<Vec<String>, ManifestError> {
    object
        .get(field)
        .and_then(Value::as_array)
        .ok_or_else(|| ManifestError::Transport(format!("{field} must be an array")))?
        .iter()
        .map(|value| {
            value
                .as_str()
                .map(ToString::to_string)
                .ok_or_else(|| ManifestError::Transport(format!("{field} must contain strings")))
        })
        .collect()
}

fn is_hex_id(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn hash_parts(parts: &[&str]) -> String {
    let mut hasher = Sha256::new();
    for part in parts {
        hasher.update(part.as_bytes());
        hasher.update([0]);
    }
    format!("{:x}", hasher.finalize())
}

fn sha256_bytes(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use std::time::{SystemTime, UNIX_EPOCH};

    const PARSER_FIXTURE: &str =
        include_str!("../../../tests/fixtures/dependency_manifest/parser_conformance.jsonl");
    const SOURCE_FIXTURE: &str =
        include_str!("../../../tests/fixtures/dependency_manifest/source_universe.jsonl");

    #[test]
    fn parser_conformance_fixture_covers_valid_and_diagnostic_cases() {
        let mut seen = BTreeSet::new();
        for line in PARSER_FIXTURE.lines() {
            let case: Value = serde_json::from_str(line).expect("valid fixture JSON");
            let name = case["case"].as_str().expect("case name");
            let source = case["source"].as_str().expect("case source");
            let expected = case["expect"].as_str().expect("case expectation");
            let result = ManifestParser::parse("fixture.txt", source);
            match expected {
                "accept" => assert!(result.is_ok(), "{name}: {result:?}"),
                "reject" => {
                    let error = result.expect_err(name);
                    let diagnostics = match error {
                        ManifestError::Invalid { diagnostics } => diagnostics,
                        other => panic!("{name}: unexpected error {other:?}"),
                    };
                    let expected_code = case["diagnostic"].as_str().expect("diagnostic code");
                    let diagnostic = diagnostics
                        .iter()
                        .find(|diagnostic| diagnostic.code == expected_code)
                        .unwrap_or_else(|| {
                            panic!("{name}: missing {expected_code}: {diagnostics:?}")
                        });
                    if let Some(expected_span) = case.get("span") {
                        let span = diagnostic
                            .source_span
                            .as_ref()
                            .unwrap_or_else(|| panic!("{name}: missing source span"));
                        assert_eq!(
                            span.start_line,
                            expected_span["start_line"].as_u64().expect("start_line") as usize,
                            "{name}: start line"
                        );
                        assert_eq!(
                            span.start_column,
                            expected_span["start_column"]
                                .as_u64()
                                .expect("start_column") as usize,
                            "{name}: start column"
                        );
                        assert_eq!(
                            span.end_line,
                            expected_span["end_line"].as_u64().expect("end_line") as usize,
                            "{name}: end line"
                        );
                    }
                }
                other => panic!("unknown fixture expectation {other}"),
            }
            seen.insert(name.to_string());
        }
        assert!(seen.contains("valid_markdown_block"));
        assert!(seen.contains("valid_c_block"));
        assert!(seen.contains("bare_markers"));
        assert!(seen.contains("fenced_manifest_is_not_source"));
        assert!(seen.contains("duplicate_start"));
        assert!(seen.contains("malformed_reason"));
        assert!(seen.contains("unknown_kind"));
    }

    #[cfg(unix)]
    #[test]
    fn source_universe_fixture_executes_every_named_case() {
        use std::os::unix::fs::PermissionsExt;

        let (root, outside_target) = source_universe_git_repo();
        let request = snapshot_request(&root);
        let mut snapshot = capture_snapshot(&request).expect("initial source-universe snapshot");
        let initial_hashes = snapshot
            .source_identities
            .iter()
            .map(|identity| {
                (
                    identity.repo_rel_path.clone(),
                    identity.content_hash.clone(),
                )
            })
            .collect::<BTreeMap<_, _>>();
        let mut executed = BTreeSet::new();
        for line in SOURCE_FIXTURE.lines() {
            let case: Value = serde_json::from_str(line).expect("valid fixture JSON");
            let name = case["case"].as_str().expect("case");
            let action = case["action"].as_str().expect("action");
            match action {
                "inspect" => {}
                "assert_source_sets" => assert_source_universe(&snapshot),
                "write" => {
                    let path = case["path"].as_str().expect("write path");
                    let contents = case["contents"].as_str().expect("write contents");
                    fs::write(root.join(path), contents).expect("write fixture path");
                    snapshot = capture_snapshot(&request).expect("snapshot after write");
                }
                "delete" => {
                    let path = case["path"].as_str().expect("delete path");
                    fs::remove_file(root.join(path)).expect("delete fixture path");
                    snapshot = capture_snapshot(&request).expect("snapshot after delete");
                }
                "rename" => {
                    let path = case["path"].as_str().expect("rename path");
                    let new_path = case["new_path"].as_str().expect("new path");
                    fs::rename(root.join(path), root.join(new_path)).expect("rename fixture path");
                    snapshot = capture_snapshot(&request).expect("snapshot after rename");
                }
                "chmod_executable" => {
                    let path = root.join(case["path"].as_str().expect("chmod path"));
                    let mut permissions =
                        fs::metadata(&path).expect("chmod metadata").permissions();
                    permissions.set_mode(0o755);
                    fs::set_permissions(path, permissions).expect("chmod fixture path");
                    snapshot = capture_snapshot(&request).expect("snapshot after chmod");
                }
                "assert_dirty_paths" => {}
                other => panic!("{name}: unknown action {other}"),
            }

            if action == "assert_dirty_paths" {
                let expected = &case["expect"];
                let actual = &snapshot.header.dirty_paths;
                let sorted = actual.iter().cloned().collect::<BTreeSet<_>>();
                assert_eq!(sorted.len(), actual.len(), "{name}: dirty paths unique");
                assert_eq!(
                    sorted.iter().cloned().collect::<Vec<_>>(),
                    *actual,
                    "{name}: dirty paths sorted"
                );
                for path in expected["contains"].as_array().expect("dirty contains") {
                    let path = path.as_str().expect("dirty path");
                    assert!(actual.iter().any(|actual| actual == path), "{name}: {path}");
                }
            } else if action != "assert_source_sets" {
                assert_source_fixture_expectation(&snapshot, &case, &initial_hashes);
            }
            assert_source_universe(&snapshot);
            assert!(
                snapshot
                    .source_identities
                    .iter()
                    .all(|identity| { CANONICAL_GIT_MODES.contains(&identity.file_mode.as_str()) }),
                "{name}: non-canonical mode"
            );

            if case["expect"]["deterministic_recapture"] == Value::Bool(true) {
                let recaptured = capture_snapshot(&request).expect("deterministic recapture");
                let identity = source_identity(
                    &snapshot,
                    case["path"].as_str().expect("deterministic path"),
                );
                let recaptured_identity = source_identity(
                    &recaptured,
                    case["path"].as_str().expect("deterministic path"),
                );
                assert_eq!(identity.file_mode, recaptured_identity.file_mode);
                assert_eq!(identity.content_hash, recaptured_identity.content_hash);
                assert_eq!(snapshot.header.snapshot_id, recaptured.header.snapshot_id);
            }
            executed.insert(name.to_string());
        }
        assert_eq!(executed.len(), SOURCE_FIXTURE.lines().count());
        assert_eq!(
            canonical_file_mode(Some(&fs::metadata(&root).expect("root metadata")), None)
                .expect("directory mode"),
            "040000"
        );
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[cfg(unix)]
    fn assert_source_fixture_expectation(
        snapshot: &ManifestSnapshot,
        case: &Value,
        initial_hashes: &BTreeMap<String, String>,
    ) {
        let name = case["case"].as_str().expect("case name");
        let expected = &case["expect"];
        if case["action"] == "rename" {
            let old = source_identity(snapshot, case["path"].as_str().expect("old path"));
            let new = source_identity(snapshot, case["new_path"].as_str().expect("new path"));
            assert_eq!(
                old.exists,
                expected["old_exists"].as_bool().expect("old exists")
            );
            assert_eq!(
                new.exists,
                expected["new_exists"].as_bool().expect("new exists")
            );
            return;
        }
        let path = case["path"].as_str().expect("fixture path");
        let identity = snapshot
            .source_identities
            .iter()
            .find(|identity| identity.repo_rel_path == path);
        let present = expected["present"].as_bool().unwrap_or(true);
        assert_eq!(identity.is_some(), present, "{name}: presence of {path}");
        let Some(identity) = identity else { return };
        if let Some(value) = expected.get("exists").and_then(Value::as_bool) {
            assert_eq!(identity.exists, value, "{name}: exists");
        }
        if let Some(value) = expected.get("is_dirty").and_then(Value::as_bool) {
            assert_eq!(identity.is_dirty, value, "{name}: dirty");
        }
        for (field, actual) in [
            ("file_mode", identity.file_mode.as_str()),
            ("locator_kind", identity.locator_kind.as_str()),
            ("path_role", identity.path_role.as_str()),
            ("canonical_locator", identity.canonical_locator.as_str()),
        ] {
            if let Some(value) = expected.get(field).and_then(Value::as_str) {
                assert_eq!(actual, value, "{name}: {field}");
            }
        }
        if expected["content_hash_changed"] == Value::Bool(true) {
            assert_ne!(
                &identity.content_hash,
                initial_hashes.get(path).expect("initial content hash"),
                "{name}: content hash"
            );
        }
        if let Some(reason) = expected.get("exclusion_reason").and_then(Value::as_str) {
            assert!(
                snapshot.source_exclusions.iter().any(|exclusion| {
                    exclusion.source_identity_id == identity.identity_id
                        && exclusion.reason_code == reason
                }),
                "{name}: exclusion {reason}"
            );
        }
        if let Some(relation_type) = expected.get("relation_type").and_then(Value::as_str) {
            let relation = snapshot
                .surface_relations
                .iter()
                .find(|relation| {
                    relation.source_identity_id == identity.identity_id
                        && relation.relation_type == relation_type
                })
                .unwrap_or_else(|| panic!("{name}: relation {relation_type}"));
            if let Some(status) = expected.get("relation_status").and_then(Value::as_str) {
                assert_eq!(relation.status, status, "{name}: relation status");
            }
            if let Some(equal) = expected.get("content_hash_equal").and_then(Value::as_bool) {
                assert_eq!(relation.content_hash_equal, equal, "{name}: relation hash");
            }
        }
        if expected.get("submodule_commit").and_then(Value::as_str) == Some("nonempty") {
            assert!(
                !identity.submodule_commit.is_empty(),
                "{name}: submodule pin"
            );
        }
    }

    #[test]
    fn snapshot_round_trip_is_deterministic() {
        let root = temporary_git_repo();
        let request = SnapshotRequest {
            root: root.clone(),
            profile: "parent".to_string(),
            output_jsonl: PathBuf::from("-"),
        };
        let left = capture_snapshot(&request).expect("first snapshot");
        let right = capture_snapshot(&request).expect("second snapshot");
        let mut left_bytes = Vec::new();
        let mut right_bytes = Vec::new();
        write_snapshot_jsonl(&left, &mut left_bytes).expect("left JSONL");
        write_snapshot_jsonl(&right, &mut right_bytes).expect("right JSONL");
        assert_eq!(left_bytes, right_bytes);
        let parsed = parse_snapshot(Cursor::new(left_bytes)).expect("round trip");
        assert_eq!(parsed.header.snapshot_id, left.header.snapshot_id);
        assert_eq!(
            parsed.header.source_fingerprint,
            left.header.source_fingerprint
        );
        assert_eq!(parsed.source_identities.len(), left.source_identities.len());
        assert_source_universe(&parsed);
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_transport_rejects_tampered_header_hashes_fingerprint_and_ids() {
        let (root, outside_target) = source_universe_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("transport snapshot");
        let values = snapshot_values(&snapshot);

        let mut tampered = values.clone();
        tampered[0]["payload"]["snapshot_id"] = Value::String("0".repeat(64));
        assert_transport_error(tampered, "header payload snapshot_id mismatch");

        let mut tampered = values.clone();
        tampered[0]["payload"]["captured_after_hash"] = Value::String("1".repeat(64));
        assert_transport_error(tampered, "capture hashes differ");

        let mut tampered = values.clone();
        tampered[0]["payload"]["git_index_tree"] = Value::String("tampered-tree".to_string());
        assert_transport_error(tampered, "capture hash mismatch");

        let mut tampered = values.clone();
        let identity_index = record_index(&tampered, "source_identity.v1");
        tampered[identity_index]["payload"]["content_hash"] = Value::String("2".repeat(64));
        assert_transport_error(tampered, "source fingerprint mismatch");

        let mut tampered = values.clone();
        let identity_index = record_index(&tampered, "source_identity.v1");
        let fake_id = "3".repeat(64);
        tampered[identity_index]["record_id"] = Value::String(fake_id.clone());
        tampered[identity_index]["payload"]["identity_id"] = Value::String(fake_id);
        assert_transport_error(tampered, "source identity ID mismatch");

        let mut tampered = values.clone();
        let identity_index = record_index(&tampered, "source_identity.v1");
        tampered[identity_index]["payload"]["logical_id"] = Value::String("6".repeat(64));
        assert_transport_error(tampered, "logical source ID mismatch");

        for (record_type, payload_id, expected, replacement) in [
            (
                "dependency_declaration.v1",
                "declaration_id",
                "declaration ID mismatch",
                '7',
            ),
            (
                "source_exclusion.v1",
                "source_exclusion_id",
                "source exclusion ID mismatch",
                '8',
            ),
            (
                "surface_relation.v1",
                "relation_id",
                "surface relation ID mismatch",
                '9',
            ),
        ] {
            let mut tampered = values.clone();
            let index = record_index(&tampered, record_type);
            let fake_id = replacement.to_string().repeat(64);
            tampered[index]["record_id"] = Value::String(fake_id.clone());
            tampered[index]["payload"][payload_id] = Value::String(fake_id);
            assert_transport_error(tampered, expected);
        }

        let mut tampered = values.clone();
        tampered[0]["payload"]["source_fingerprint"] = Value::String("4".repeat(64));
        assert_transport_error(tampered, "source fingerprint mismatch");

        let mut tampered = values.clone();
        let relation_index = record_index(&tampered, "surface_relation.v1");
        let source_identity_id = tampered[relation_index]["payload"]["source_identity_id"]
            .as_str()
            .expect("surface source identity")
            .to_string();
        let relation_type = tampered[relation_index]["payload"]["relation_type"]
            .as_str()
            .expect("surface relation type")
            .to_string();
        let fake_target_identity_id = "a".repeat(64);
        let fake_relation_id = hash_parts(&[
            "surface_relation.v1",
            &source_identity_id,
            &fake_target_identity_id,
            &relation_type,
        ]);
        tampered[relation_index]["record_id"] = Value::String(fake_relation_id.clone());
        tampered[relation_index]["payload"]["relation_id"] =
            Value::String(fake_relation_id.clone());
        tampered[relation_index]["payload"]["target_identity_id"] =
            Value::String(fake_target_identity_id);
        tampered[relation_index]["payload"]["evidence_id"] = Value::String(fake_relation_id);
        assert_transport_error(tampered, "surface relation target identity ID mismatch");

        let mut tampered = values.clone();
        let exclusion_index = record_index(&tampered, "source_exclusion.v1");
        tampered[exclusion_index]["payload"]["covered"] = Value::Bool(true);
        assert_transport_error(tampered, "must have covered=false");

        let simple_root = temporary_git_repo();
        let simple = capture_snapshot(&snapshot_request(&simple_root)).expect("simple snapshot");
        let mut retagged = snapshot_values(&simple);
        let fake_snapshot_id = "5".repeat(64);
        for value in &mut retagged {
            value["snapshot_id"] = Value::String(fake_snapshot_id.clone());
            value["payload"]["snapshot_id"] = Value::String(fake_snapshot_id.clone());
        }
        retagged[0]["record_id"] = Value::String(fake_snapshot_id);
        assert_transport_error(retagged, "snapshot ID mismatch");

        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
        let _ = fs::remove_dir_all(simple_root);
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_transport_rejects_duplicate_id_in_each_record_family() {
        let (root, outside_target) = source_universe_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("transport snapshot");
        let values = snapshot_values(&snapshot);
        let mut duplicated_header = values.clone();
        duplicated_header.insert(1, duplicated_header[0].clone());
        assert_transport_error(
            duplicated_header,
            "duplicate source snapshot header record ID",
        );
        for (record_type, expected) in [
            ("source_identity.v1", "duplicate source identity record ID"),
            (
                "dependency_declaration.v1",
                "duplicate dependency declaration record ID",
            ),
            (
                "source_exclusion.v1",
                "duplicate source exclusion record ID",
            ),
            (
                "surface_relation.v1",
                "duplicate surface relation record ID",
            ),
        ] {
            let mut duplicated = values.clone();
            let index = record_index(&duplicated, record_type);
            duplicated.insert(index + 1, duplicated[index].clone());
            assert_transport_error(duplicated, expected);
        }
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[test]
    fn atomic_output_failure_removes_candidate_and_preserves_old_output() {
        let root = unique_temp_path("agent-canon-r1-atomic");
        fs::create_dir_all(&root).expect("atomic fixture root");
        let output = root.join("source_snapshot.v1.jsonl");
        let candidate = root.join(format!(
            ".source_snapshot.v1.jsonl.{}.candidate",
            std::process::id()
        ));
        for failure in [
            AtomicFailurePoint::Write,
            AtomicFailurePoint::Sync,
            AtomicFailurePoint::Rename,
        ] {
            fs::write(&output, b"old-output\n").expect("old output");
            let error = write_atomic_with_failure(&output, b"new-output\n", failure)
                .expect_err("injected atomic failure");
            assert!(error.to_string().contains("injected candidate"));
            assert_eq!(
                fs::read(&output).expect("preserved output"),
                b"old-output\n"
            );
            assert!(!candidate.exists(), "candidate remains after {failure:?}");
        }
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn run_local_validation_artifact_is_produced_when_requested() {
        let Ok(path) = std::env::var("R1_VALIDATION_ARTIFACT") else {
            return;
        };
        let (snapshot, deterministic_two_build_equality, cleanup_root) =
            match std::env::var("R1_VALIDATION_JSONL") {
                Ok(jsonl) => {
                    let bytes = fs::read(jsonl).expect("validation JSONL");
                    let second = fs::read(
                        std::env::var("R1_VALIDATION_JSONL_SECOND")
                            .expect("R1_VALIDATION_JSONL_SECOND for two-capture evidence"),
                    )
                    .expect("second validation JSONL");
                    let snapshot = parse_snapshot(Cursor::new(bytes.clone()))
                        .expect("parsed validation snapshot");
                    let second_snapshot = parse_snapshot(Cursor::new(second.clone()))
                        .expect("parsed second validation snapshot");
                    assert_eq!(
                        snapshot.header.snapshot_id,
                        second_snapshot.header.snapshot_id
                    );
                    (snapshot, bytes == second, None)
                }
                Err(_) => {
                    let root = temporary_git_repo();
                    let request = snapshot_request(&root);
                    let first = capture_snapshot(&request).expect("validation snapshot");
                    let second = capture_snapshot(&request).expect("second validation snapshot");
                    let mut first_bytes = Vec::new();
                    let mut second_bytes = Vec::new();
                    write_snapshot_jsonl(&first, &mut first_bytes).expect("first validation JSONL");
                    write_snapshot_jsonl(&second, &mut second_bytes)
                        .expect("second validation JSONL");
                    (first, first_bytes == second_bytes, Some(root))
                }
            };
        let parser_cases = fixture_case_names(PARSER_FIXTURE);
        let source_cases = fixture_case_names(SOURCE_FIXTURE);
        let artifact = json!({
            "schema_version": "r1-parser-schema-snapshot.v1",
            "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "snapshot_id": snapshot.header.snapshot_id,
            "source_fingerprint": snapshot.header.source_fingerprint,
            "snapshot_consistent": snapshot.header.snapshot_consistent,
            "capture_hashes_equal": snapshot.header.captured_before_hash == snapshot.header.captured_after_hash,
            "transport_ids_and_fingerprint_verified": true,
            "parser_fixture_cases": parser_cases,
            "source_universe_fixture_cases": source_cases,
            "candidate_source_count": snapshot.source_universe.candidate_paths.len(),
            "eligible_source_count": snapshot.source_universe.eligible_paths.len(),
            "source_exclusion_count": snapshot.source_universe.excluded_paths.len(),
            "declaration_count": snapshot.declarations.len(),
            "surface_relation_count": snapshot.surface_relations.len(),
            "diagnostic_count": snapshot.diagnostics.len(),
            "deterministic_two_build_equality": deterministic_two_build_equality,
            "source_universe": {
                "P": {
                    "count": snapshot.source_universe.candidate_paths.len(),
                    "members": snapshot.source_universe.candidate_paths,
                },
                "E_src": {
                    "count": snapshot.source_universe.excluded_paths.len(),
                    "members": snapshot.source_universe.excluded_paths,
                },
                "U": {
                    "count": snapshot.source_universe.eligible_paths.len(),
                    "members": snapshot.source_universe.eligible_paths,
                },
                "eligible_equals_candidate_minus_excluded": snapshot.source_universe.eligible_equals_candidate_minus_excluded,
                "union_equals_candidate": snapshot.source_universe.union_equals_candidate,
                "intersection_empty": snapshot.source_universe.intersection_empty,
            },
            "identity_rules": {
                "symlink": "view_of or symlink_outside_root",
                "copy": "view_of only when content hash agrees",
                "submodule": "gitlink pin with internal paths excluded",
                "generated": "generated_output excluded"
            }
        });
        let path = PathBuf::from(path);
        fs::create_dir_all(path.parent().expect("artifact parent")).expect("artifact directory");
        fs::write(
            path,
            format!(
                "{}\n",
                serde_json::to_string_pretty(&artifact).expect("artifact JSON")
            ),
        )
        .expect("artifact write");
        if let Some(root) = cleanup_root {
            let _ = fs::remove_dir_all(root);
        }
    }

    fn assert_source_universe(snapshot: &ManifestSnapshot) {
        assert!(
            snapshot
                .source_universe
                .eligible_equals_candidate_minus_excluded
        );
        assert!(snapshot.source_universe.union_equals_candidate);
        assert!(snapshot.source_universe.intersection_empty);
        assert_eq!(
            snapshot.source_universe.candidate_paths.len(),
            snapshot.source_identities.len()
        );
        assert_eq!(
            snapshot.source_universe.excluded_paths.len(),
            snapshot.source_exclusions.len()
        );
    }

    fn source_identity<'a>(snapshot: &'a ManifestSnapshot, path: &str) -> &'a SourceIdentity {
        snapshot
            .source_identities
            .iter()
            .find(|identity| identity.repo_rel_path == path)
            .unwrap_or_else(|| panic!("missing source identity {path}"))
    }

    fn snapshot_request(root: &Path) -> SnapshotRequest {
        SnapshotRequest {
            root: root.to_path_buf(),
            profile: "parent".to_string(),
            output_jsonl: PathBuf::from("-"),
        }
    }

    fn snapshot_values(snapshot: &ManifestSnapshot) -> Vec<Value> {
        let mut bytes = Vec::new();
        write_snapshot_jsonl(snapshot, &mut bytes).expect("snapshot JSONL");
        String::from_utf8(bytes)
            .expect("UTF-8 JSONL")
            .lines()
            .map(|line| serde_json::from_str(line).expect("JSONL record"))
            .collect()
    }

    fn record_index(values: &[Value], record_type: &str) -> usize {
        values
            .iter()
            .position(|value| value["record_type"].as_str() == Some(record_type))
            .unwrap_or_else(|| panic!("missing record family {record_type}"))
    }

    fn assert_transport_error(values: Vec<Value>, expected: &str) {
        let mut bytes = Vec::new();
        for value in values {
            serde_json::to_writer(&mut bytes, &value).expect("tampered JSON");
            bytes.push(b'\n');
        }
        let error = parse_snapshot(Cursor::new(bytes)).expect_err("tampered snapshot accepted");
        assert!(
            error.to_string().contains(expected),
            "expected {expected:?}, got {error:?}"
        );
    }

    fn fixture_case_names(fixture: &str) -> Vec<String> {
        fixture
            .lines()
            .map(|line| {
                let value: Value = serde_json::from_str(line).expect("fixture JSON");
                value["case"].as_str().expect("fixture case").to_string()
            })
            .collect()
    }

    fn unique_temp_path(prefix: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        std::env::temp_dir().join(format!("{prefix}-{suffix}"))
    }

    fn temporary_git_repo() -> PathBuf {
        let root = unique_temp_path("agent-canon-r1");
        fs::create_dir_all(&root).expect("temporary repo");
        for (name, contents) in [
            ("tracked.txt", "tracked\n"),
            ("rename.txt", "rename\n"),
            ("deleted.txt", "delete\n"),
        ] {
            fs::write(root.join(name), contents).expect("fixture file");
        }
        initialize_and_commit(&root);
        root
    }

    #[cfg(unix)]
    fn source_universe_git_repo() -> (PathBuf, PathBuf) {
        use std::os::unix::fs::{symlink, PermissionsExt};

        let root = unique_temp_path("agent-canon-r1-source-universe");
        let outside_target = root.with_extension("outside-target");
        fs::create_dir_all(root.join(".agent-canon/knowledge-graph")).expect("generated directory");
        fs::create_dir_all(root.join("vendor/agent-canon/documents")).expect("submodule documents");
        fs::write(&outside_target, "outside\n").expect("outside target");
        fs::write(root.join("inside-target.txt"), "inside\n").expect("inside target");
        symlink("inside-target.txt", root.join("inside-link")).expect("inside symlink");
        symlink(&outside_target, root.join("outside-link")).expect("outside symlink");
        fs::write(root.join("copy-match.txt"), "canonical\n").expect("matching copy");
        fs::write(root.join("copy-mismatch.txt"), "mismatch\n").expect("mismatching copy");
        fs::write(root.join("modify.txt"), "original\n").expect("modify source");
        fs::write(root.join("delete.txt"), "delete\n").expect("delete source");
        fs::write(root.join("rename.txt"), "rename\n").expect("rename source");
        fs::write(
            root.join("tracked.txt"),
            "# @dependency-start\n# contract implementation\n# responsibility Provides the fixture manifest.\n# upstream implementation modify.txt resolves a fixture target\n# @dependency-end\n",
        )
        .expect("tracked manifest");
        fs::write(root.join("executable.sh"), "#!/bin/sh\nexit 0\n").expect("executable");
        let mut executable_permissions = fs::metadata(root.join("executable.sh"))
            .expect("executable metadata")
            .permissions();
        executable_permissions.set_mode(0o755);
        fs::set_permissions(root.join("executable.sh"), executable_permissions)
            .expect("executable permissions");
        fs::write(
            root.join(".agent-canon/knowledge-graph/graph.sqlite"),
            "generated\n",
        )
        .expect("generated fixture");
        fs::write(root.join(".gitignore"), "ignored.txt\n").expect("gitignore");
        fs::write(root.join("ignored.txt"), "ignored\n").expect("ignored fixture");

        let submodule = root.join("vendor/agent-canon");
        fs::write(submodule.join("canonical.txt"), "canonical\n").expect("canonical source");
        fs::write(
            submodule.join("documents/shared-runtime-surfaces.toml"),
            "prefix = \"vendor/agent-canon\"\n\n[[group]]\nmode = \"symlink\"\nclass = \"runtime_surface\"\npaths = [\n  \"inside-link\",\n  \"outside-link\",\n]\n\n[[group]]\nmode = \"copy\"\nclass = \"runtime_surface\"\nsource = \"canonical.txt\"\npaths = [\n  \"copy-match.txt\",\n  \"copy-mismatch.txt\",\n]\n",
        )
        .expect("surface catalog");
        initialize_and_commit(&submodule);
        initialize_and_commit(&root);
        (root, outside_target)
    }

    fn initialize_and_commit(root: &Path) {
        run_git(root, &["init", "-q"]);
        run_git(root, &["config", "user.email", "r1@example.invalid"]);
        run_git(root, &["config", "user.name", "R1 Fixture"]);
        run_git(root, &["add", "."]);
        run_git(root, &["commit", "-qm", "fixture"]);
    }

    fn run_git(root: &Path, args: &[&str]) {
        let output = Command::new("git")
            .arg("-C")
            .arg(root)
            .args(args)
            .output()
            .expect("git command");
        assert!(
            output.status.success(),
            "git {args:?}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
}
