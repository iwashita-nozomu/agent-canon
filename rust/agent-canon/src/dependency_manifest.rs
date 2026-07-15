// @dependency-start
// contract implementation
// responsibility Owns the canonical dependency-manifest grammar and immutable source snapshots.
// upstream design ../../../documents/dependency-manifest-design.md manifest grammar, finite source sets, and graph producer contract
// upstream design ../../../documents/structured-analysis/graph-dsl.md typed graph record and provenance contract
// downstream implementation graph.rs captures the snapshot and materializes graph facts
// @dependency-end

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::io::{self, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Command;

pub const SNAPSHOT_SCHEMA_VERSION: &str = "source_snapshot.v1";
const TOOL_VERSION: &str = "agent-canon 0.1.0";
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
    "review",
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
    Requirements,
    Review,
    Evidence,
}

impl DependencyKind {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Design => "design",
            Self::Implementation => "implementation",
            Self::Environment => "environment",
            Self::Requirements => "requirements",
            Self::Review => "review",
            Self::Evidence => "evidence",
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
    pub manifest_present: bool,
    pub contract: String,
    pub responsibility: String,
    pub coverage: Vec<CoverageDeclaration>,
    pub dependencies: Vec<ManifestDependency>,
    pub source_span: Option<SourceSpan>,
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
    pub(crate) manifests: BTreeMap<String, ManifestAst>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SnapshotRequest {
    pub root: PathBuf,
    pub profile: String,
    pub output_jsonl: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ManifestError {
    Io(String),
    Git(String),
    Invalid { diagnostics: Vec<Diagnostic> },
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
            Self::Invalid { diagnostics } => {
                let summary = diagnostics
                    .iter()
                    .map(|diagnostic| {
                        let location = diagnostic
                            .source_span
                            .as_ref()
                            .map(|span| format!("{}:{}", span.path, span.start_line))
                            .unwrap_or_else(|| "snapshot".to_string());
                        format!("{}@{}", diagnostic.code, location)
                    })
                    .collect::<Vec<_>>()
                    .join(",");
                write!(
                    formatter,
                    "manifest has {} diagnostic(s): {summary}",
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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct GeneratedSourceRule {
    reason_code: &'static str,
    rule_id: &'static str,
    scope: &'static str,
}

fn generated_source_rule(relative_path: &str) -> Option<GeneratedSourceRule> {
    let path_components = relative_path.split('/').collect::<Vec<_>>();
    if matches!(
        relative_path,
        "tools/agent_tools/bind_r2_scope.py"
            | "tools/agent_tools/dependency_manifest_records.py"
            | "tests/fixtures/dependency_manifest/parser_conformance.jsonl"
            | "tests/fixtures/dependency_manifest/relation_reconciliation.jsonl"
            | "tests/fixtures/dependency_manifest/source_universe.jsonl"
            | "tests/fixtures/dependency_manifest/transport_conformance.jsonl"
            | "tests/fixtures/knowledge_graph/freshness_atomic_closure.jsonl"
            | "tests/fixtures/knowledge_graph/query_kind_registry.jsonl"
    ) {
        return Some(GeneratedSourceRule {
            reason_code: "obsolete_graph_route",
            rule_id: "knowledge-graph-replacement-deletion-list",
            scope: "approved graph parser/schema/binder/fixture deletion list",
        });
    }
    if relative_path == ".agent-canon/knowledge-graph"
        || relative_path.starts_with(".agent-canon/knowledge-graph/")
    {
        return Some(GeneratedSourceRule {
            reason_code: "generated_output",
            rule_id: "parent-generated-graph-output",
            scope: ".agent-canon/knowledge-graph/**",
        });
    }
    if path_components.contains(&"__pycache__")
        || relative_path.ends_with(".pyc")
        || relative_path.ends_with(".pyo")
    {
        return Some(GeneratedSourceRule {
            reason_code: "generated_output",
            rule_id: "python-bytecode-cache",
            scope: "**/__pycache__/**|**/*.pyc|**/*.pyo",
        });
    }
    if relative_path == ".agent-canon/log-archive"
        || relative_path.starts_with(".agent-canon/log-archive/")
        || relative_path == "reports/agent-runtime-dashboard"
        || relative_path.starts_with("reports/agent-runtime-dashboard/")
        || (path_components.len() >= 4
            && path_components[0] == "experiments"
            && path_components[2] == "result"
            && path_components[3].starts_with("readonly_agent_log_analysis_"))
    {
        return Some(GeneratedSourceRule {
            reason_code: "source.excluded_runtime_result",
            rule_id: "runtime-result-artifact-placement",
            scope: ".agent-canon/log-archive/**|reports/agent-runtime-dashboard/**|experiments/_template/result/readonly_agent_log_analysis_*/**",
        });
    }
    if relative_path == "reports/agents" || relative_path.starts_with("reports/agents/") {
        return Some(GeneratedSourceRule {
            reason_code: "generated_output",
            rule_id: "run-local-agent-report-placement",
            scope: "reports/agents/**",
        });
    }
    if path_components.len() >= 3
        && path_components[0] == "experiments"
        && path_components[2] == "result"
    {
        return Some(GeneratedSourceRule {
            reason_code: "generated_output",
            rule_id: "managed-experiment-result-placement",
            scope: "experiments/*/result/**",
        });
    }
    None
}

pub(crate) fn source_path_is_explicitly_excluded(relative_path: &str) -> bool {
    generated_source_rule(relative_path).is_some()
}

#[derive(Debug)]
struct SourceIdentityLookups {
    id_by_locator: BTreeMap<String, String>,
}

fn preflight_source_identities_with_exclusions(
    source_identities: &[SourceIdentity],
    excluded_identity_ids: &BTreeSet<String>,
) -> Result<SourceIdentityLookups, ManifestError> {
    let mut identity_ids = BTreeSet::new();
    let mut repo_paths = BTreeSet::new();
    let mut canonical_locators = BTreeSet::new();
    let mut logical_ids = BTreeSet::new();
    for identity in source_identities {
        if !identity_ids.insert(identity.identity_id.as_str()) {
            return Err(ManifestError::Transport(
                "duplicate source identity record ID".to_string(),
            ));
        }
        if !repo_paths.insert(identity.repo_rel_path.as_str()) {
            return Err(ManifestError::Transport(
                "duplicate source identity path".to_string(),
            ));
        }
        if excluded_identity_ids.contains(&identity.identity_id) {
            continue;
        }
        if !canonical_locators.insert(identity.canonical_locator.as_str()) {
            return Err(ManifestError::Transport(
                "duplicate source identity canonical locator".to_string(),
            ));
        }
        if !logical_ids.insert(identity.logical_id.as_str()) {
            return Err(ManifestError::Transport(
                "duplicate source identity logical ID".to_string(),
            ));
        }
        let alternate_locators = identity
            .alternate_locators
            .iter()
            .map(String::as_str)
            .collect::<BTreeSet<_>>();
        if alternate_locators.len() != identity.alternate_locators.len()
            || alternate_locators.iter().copied().collect::<Vec<_>>()
                != identity
                    .alternate_locators
                    .iter()
                    .map(String::as_str)
                    .collect::<Vec<_>>()
        {
            return Err(ManifestError::Transport(format!(
                "alternate locators are not unique and sorted for {}",
                identity.repo_rel_path
            )));
        }
    }

    let mut locator_owners = BTreeMap::<&str, &str>::new();
    for identity in source_identities
        .iter()
        .filter(|identity| !excluded_identity_ids.contains(&identity.identity_id))
    {
        for locator in std::iter::once(identity.repo_rel_path.as_str())
            .chain(std::iter::once(identity.canonical_locator.as_str()))
            .chain(identity.alternate_locators.iter().map(String::as_str))
        {
            if locator_owners
                .insert(locator, identity.identity_id.as_str())
                .is_some_and(|owner| owner != identity.identity_id)
            {
                return Err(ManifestError::Transport(format!(
                    "source identity locator namespace collision for {locator}"
                )));
            }
        }
    }

    let mut id_by_locator = BTreeMap::new();
    for identity in source_identities
        .iter()
        .filter(|identity| !excluded_identity_ids.contains(&identity.identity_id))
    {
        for locator in std::iter::once(&identity.repo_rel_path)
            .chain(std::iter::once(&identity.canonical_locator))
            .chain(identity.alternate_locators.iter())
        {
            id_by_locator.insert(locator.clone(), identity.identity_id.clone());
        }
    }
    Ok(SourceIdentityLookups { id_by_locator })
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
    let mut surface_catalog = read_surface_catalog(&root);
    let mut candidate_paths = git_visible_paths(&root)?;
    candidate_paths.retain(|path| {
        path != ".agent-canon/knowledge-graph" && !path.starts_with(".agent-canon/knowledge-graph/")
    });
    expand_surface_view_paths(&root, &mut candidate_paths, &mut surface_catalog);
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
    let excluded_identity_ids = source_exclusions
        .iter()
        .map(|exclusion| exclusion.source_identity_id.clone())
        .collect::<BTreeSet<_>>();
    let excluded_locators = source_identities
        .iter()
        .filter(|identity| excluded_identity_ids.contains(&identity.identity_id))
        .flat_map(|identity| {
            std::iter::once(identity.repo_rel_path.clone())
                .chain(std::iter::once(identity.canonical_locator.clone()))
                .chain(identity.alternate_locators.iter().cloned())
        })
        .collect::<BTreeSet<_>>();
    let identity_lookups =
        preflight_source_identities_with_exclusions(&source_identities, &excluded_identity_ids)?;

    let mut diagnostics = Vec::new();
    let mut raw_declarations = Vec::new();
    let mut manifests = BTreeMap::new();
    for identity in &source_identities {
        if excluded_identity_ids.contains(&identity.identity_id)
            || !identity.exists
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
        if !ast.manifest_present {
            continue;
        }
        let dependencies = ast.dependencies.clone();
        manifests.insert(identity.identity_id.clone(), ast);
        for dependency in dependencies {
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
            let resolved_target_identity_id = identity_lookups.id_by_locator.get(&target).cloned();
            if resolved_target_identity_id.is_none() && !excluded_locators.contains(&target) {
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
            let resolved_target_identity_id = identity_lookups.id_by_locator.get(&target).cloned();
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

    let manifest_errors = diagnostics
        .iter()
        .filter(|diagnostic| diagnostic.severity == "error")
        .cloned()
        .collect::<Vec<_>>();
    if !manifest_errors.is_empty() {
        return Err(ManifestError::Invalid {
            diagnostics: manifest_errors,
        });
    }

    let manifest_errors = diagnostics
        .iter()
        .filter(|diagnostic| diagnostic.severity == "error")
        .cloned()
        .collect::<Vec<_>>();
    if !manifest_errors.is_empty() {
        return Err(ManifestError::Invalid {
            diagnostics: manifest_errors,
        });
    }

    let mut surface_relations = surface_specs
        .into_iter()
        .map(
            |(source_id, source_path, relation_type, target_path, owner, equal, mode, status)| {
                let target_id = identity_lookups
                    .id_by_locator
                    .get(&target_path)
                    .cloned()
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
        manifests,
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
    let agentcanon = root.join("vendor/agent-canon");
    if agentcanon.join(".git").exists() {
        let submodule_output = git_bytes(
            &agentcanon,
            &[
                "ls-files",
                "--cached",
                "--deleted",
                "--others",
                "--exclude-standard",
                "-z",
            ],
        )?;
        for raw in submodule_output
            .split(|byte| *byte == 0)
            .filter(|raw| !raw.is_empty())
        {
            let path = std::str::from_utf8(raw).map_err(|error| {
                ManifestError::Git(format!("AgentCanon git-visible path is not UTF-8: {error}"))
            })?;
            let path = normalize_repo_path(Path::new(path)).ok_or_else(|| {
                ManifestError::Git(format!("invalid AgentCanon git-visible path {path}"))
            })?;
            paths.insert(format!("vendor/agent-canon/{path}"));
        }
    }
    Ok(paths.into_iter().collect())
}

fn expand_surface_view_paths(
    root: &Path,
    candidate_paths: &mut Vec<String>,
    catalog: &mut SurfaceCatalog,
) {
    let internals = candidate_paths
        .iter()
        .filter(|path| path.starts_with("vendor/agent-canon/"))
        .cloned()
        .collect::<Vec<_>>();
    let view_roots = catalog
        .entries
        .iter()
        .filter(|(path, spec)| spec.mode == "symlink" && root.join(path).is_symlink())
        .map(|(path, spec)| (path.clone(), spec.clone()))
        .collect::<Vec<_>>();
    let mut paths = candidate_paths.iter().cloned().collect::<BTreeSet<_>>();
    for (view_root, spec) in view_roots {
        let source_root = if spec.source.starts_with("vendor/agent-canon/") {
            spec.source.clone()
        } else {
            format!("{}/{}", catalog.prefix, spec.source)
        };
        for internal in &internals {
            let suffix = if internal == &source_root {
                Some("")
            } else {
                internal.strip_prefix(&format!("{source_root}/"))
            };
            let Some(suffix) = suffix else {
                continue;
            };
            let alias = if suffix.is_empty() {
                view_root.clone()
            } else {
                format!("{view_root}/{suffix}")
            };
            if !root.join(&alias).exists() {
                continue;
            }
            paths.insert(alias.clone());
            catalog.entries.entry(alias).or_insert_with(|| SurfaceSpec {
                mode: "symlink".to_string(),
                class: spec.class.clone(),
                source: internal.clone(),
            });
        }
    }
    *candidate_paths = paths.into_iter().collect();
}

fn read_index_entries(root: &Path) -> Result<BTreeMap<String, IndexEntry>, ManifestError> {
    let output = git_bytes(root, &["ls-files", "--stage", "-z"])?;
    let mut entries = BTreeMap::new();
    append_index_entries(&mut entries, &output, "")?;
    let agentcanon = root.join("vendor/agent-canon");
    if agentcanon.join(".git").exists() {
        let submodule_output = git_bytes(&agentcanon, &["ls-files", "--stage", "-z"])?;
        append_index_entries(&mut entries, &submodule_output, "vendor/agent-canon/")?;
    }
    Ok(entries)
}

fn append_index_entries(
    entries: &mut BTreeMap<String, IndexEntry>,
    output: &[u8],
    prefix: &str,
) -> Result<(), ManifestError> {
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
        let normalized = normalize_repo_path(Path::new(path))
            .ok_or_else(|| ManifestError::Git(format!("invalid index path {path}")))?;
        entries.insert(
            format!("{prefix}{normalized}"),
            IndexEntry { mode, object_id },
        );
    }
    Ok(())
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
    let surface_spec = catalog.entries.get(relative_path).cloned();
    let generated_rule = generated_source_rule(relative_path);
    let generated = generated_rule.is_some();
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
        .as_ref()
        .map(|spec| spec.class.clone())
        .unwrap_or_else(|| "unresolved".to_string());
    let mut surface_mode = surface_spec
        .as_ref()
        .map(|spec| spec.mode.clone())
        .unwrap_or_else(|| "regular".to_string());
    let mut surface = None;

    if is_symlink {
        if let Some(target) = canonical_target
            .clone()
            .filter(|_| catalog.entries.contains_key(relative_path))
        {
            canonical_locator = target.clone();
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
    } else if let Some(spec) = surface_spec.as_ref() {
        if spec.mode == "symlink" {
            let target = if spec.source.starts_with("vendor/agent-canon/") {
                spec.source.clone()
            } else {
                format!("{}/{}", catalog.prefix, spec.source)
            };
            canonical_locator = target.clone();
            path_role = "root_view".to_string();
            locator_kind = "symlink-tree".to_string();
            surface_mode = "symlink".to_string();
            surface = Some((
                "view_of".to_string(),
                target,
                owner_class.clone(),
                true,
                surface_mode.clone(),
                "mapped".to_string(),
            ));
        } else if spec.mode == "copy" {
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
        if let Some(spec) = surface_spec.as_ref() {
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
    } else if let Some(rule) = generated_rule {
        Some((
            rule.reason_code.to_string(),
            rule.rule_id.to_string(),
            rule.scope.to_string(),
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
    let content_hash = if generated {
        String::new()
    } else {
        content_hash_for_path(&path, index_entry, root, relative_path)?
    };
    let git_blob_or_gitlink = if generated {
        String::new()
    } else {
        index_entry
            .map(|entry| entry.object_id.clone())
            .unwrap_or_default()
    };
    let submodule_commit = if is_gitlink {
        current_submodule_commit(&root.join(relative_path))
            .unwrap_or_else(|| git_blob_or_gitlink.clone())
    } else {
        String::new()
    };
    let file_mode = canonical_file_mode(metadata.as_ref(), index_entry)?;
    let logical_id = if generated {
        format!("generated:{relative_path}")
    } else {
        hash_parts(&[
            "logical_source.v1",
            &context.parent_repo_id,
            &canonical_locator,
        ])
    };
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
        parts.push(identity.repo_rel_path.clone());
        if let Some((reason_code, rule_id, scope)) = &build.exclusion {
            parts.extend([
                "excluded-source.v1".to_string(),
                reason_code.clone(),
                rule_id.clone(),
                scope.clone(),
                identity.path_role.clone(),
                identity.owner_class.clone(),
                identity.surface_mode.clone(),
            ]);
        } else {
            parts.extend([
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
            let (git_root, git_path) = relative_path
                .strip_prefix("vendor/agent-canon/")
                .map(|path| (root.join("vendor/agent-canon"), path))
                .unwrap_or_else(|| (root.to_path_buf(), relative_path));
            let output = git_bytes(&git_root, &["cat-file", "blob", &entry.object_id])
                .or_else(|_| git_bytes(&git_root, &["show", &format!(":{git_path}")]))?;
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

pub(crate) struct ManifestParser;

impl ManifestParser {
    pub(crate) fn parse(path: &str, text: &str) -> Result<ManifestAst, ManifestError> {
        let lines = text.lines().collect::<Vec<_>>();
        let scan = parse_manifest_block(path, &lines);
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
            return Ok(ManifestAst {
                manifest_present: false,
                contract: String::new(),
                responsibility: String::new(),
                coverage: Vec::new(),
                dependencies: Vec::new(),
                source_span: None,
            });
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
            if !matches!(
                kind,
                "design"
                    | "implementation"
                    | "environment"
                    | "requirements"
                    | "review"
                    | "evidence"
            ) {
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
                "environment" => DependencyKind::Environment,
                "requirements" => DependencyKind::Requirements,
                "review" => DependencyKind::Review,
                _ => DependencyKind::Evidence,
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
            manifest_present: true,
            contract: contract.unwrap_or_default(),
            responsibility: responsibility.unwrap_or_default(),
            coverage,
            dependencies,
            source_span: Some(SourceSpan {
                path: path.to_string(),
                start_line: start + 1,
                start_column: scan.lines[start].start_column,
                end_line: end + 1,
                end_column: lines[end].chars().count() + 1,
            }),
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

#[derive(Debug, Clone, Copy)]
enum RustStringState {
    Normal,
    Raw(usize),
}

fn parse_manifest_block(path: &str, lines: &[&str]) -> ManifestLineScan {
    let mut scanned = Vec::with_capacity(lines.len());
    let mut diagnostics = Vec::new();
    let mut next_wrapper_id = 1usize;
    let mut line_wrapper: Option<(ManifestWrapper, usize, usize)> = None;
    let mut block: Option<BlockWrapperState> = None;
    let mut fence: Option<&'static str> = None;
    let python_source = path.ends_with(".py");
    let mut python_triple: Option<&'static str> = None;
    let shell_source = [".sh", ".bash", ".zsh"]
        .iter()
        .any(|suffix| path.ends_with(suffix));
    let mut shell_heredoc: Option<String> = None;
    let rust_source = path.ends_with(".rs");
    let mut rust_string: Option<RustStringState> = None;

    for (line_index, raw_line) in lines.iter().enumerate() {
        let trimmed = raw_line.trim();
        if rust_source {
            if let Some(state) = rust_string {
                if rust_string_closes(raw_line, state) {
                    rust_string = None;
                }
                scanned.push(empty_scanned_line());
                line_wrapper = None;
                continue;
            }
            if let Some(state) = rust_multiline_string_start(raw_line) {
                rust_string = Some(state);
                scanned.push(empty_scanned_line());
                line_wrapper = None;
                continue;
            }
        }
        if shell_source {
            if let Some(delimiter) = shell_heredoc.as_deref() {
                if trimmed == delimiter {
                    shell_heredoc = None;
                }
                scanned.push(empty_scanned_line());
                line_wrapper = None;
                continue;
            }
            if let Some(delimiter) = shell_heredoc_delimiter(raw_line) {
                shell_heredoc = Some(delimiter);
                scanned.push(empty_scanned_line());
                line_wrapper = None;
                continue;
            }
        }
        if python_source {
            if let Some(delimiter) = python_triple {
                if triple_quote_count(raw_line, delimiter) % 2 == 1 {
                    python_triple = None;
                }
                scanned.push(empty_scanned_line());
                line_wrapper = None;
                continue;
            }
            let single_count = triple_quote_count(raw_line, "'''");
            let double_count = triple_quote_count(raw_line, "\"\"\"");
            if single_count > 0 || double_count > 0 {
                if single_count % 2 == 1 {
                    python_triple = Some("'''");
                } else if double_count % 2 == 1 {
                    python_triple = Some("\"\"\"");
                }
                scanned.push(empty_scanned_line());
                line_wrapper = None;
                continue;
            }
        }
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

fn rust_string_closes(line: &str, state: RustStringState) -> bool {
    match state {
        RustStringState::Normal => unescaped_quote_count(line) % 2 == 1,
        RustStringState::Raw(hashes) => line.contains(&format!("\"{}", "#".repeat(hashes))),
    }
}

fn rust_multiline_string_start(line: &str) -> Option<RustStringState> {
    let bytes = line.as_bytes();
    let mut index = 0usize;
    while index < bytes.len() {
        if bytes[index] == b'/' && bytes.get(index + 1) == Some(&b'/') {
            break;
        }
        if bytes[index] == b'r' {
            let mut cursor = index + 1;
            while bytes.get(cursor) == Some(&b'#') {
                cursor += 1;
            }
            if bytes.get(cursor) == Some(&b'\"') {
                let hashes = cursor - index - 1;
                let close = format!("\"{}", "#".repeat(hashes));
                if !line[cursor + 1..].contains(&close) {
                    return Some(RustStringState::Raw(hashes));
                }
                index = cursor + 1;
            }
        }
        index += 1;
    }
    (unescaped_quote_count(line) % 2 == 1).then_some(RustStringState::Normal)
}

fn unescaped_quote_count(line: &str) -> usize {
    line.match_indices('"')
        .filter(|(index, _)| {
            line[..*index]
                .chars()
                .rev()
                .take_while(|character| *character == '\\')
                .count()
                % 2
                == 0
        })
        .count()
}

fn triple_quote_count(line: &str, delimiter: &str) -> usize {
    line.match_indices(delimiter)
        .filter(|(index, _)| {
            let preceding_backslashes = line[..*index]
                .chars()
                .rev()
                .take_while(|character| *character == '\\')
                .count();
            preceding_backslashes % 2 == 0
        })
        .count()
}

fn shell_heredoc_delimiter(line: &str) -> Option<String> {
    let marker = line.find("<<")?;
    let mut tail = line[marker + 2..].trim_start();
    if let Some(rest) = tail.strip_prefix('-') {
        tail = rest.trim_start();
    }
    let (quote, rest) = match tail.chars().next()? {
        '\'' => (Some('\''), &tail[1..]),
        '"' => (Some('"'), &tail[1..]),
        _ => (None, tail),
    };
    let end = rest
        .char_indices()
        .find(|(_, character)| {
            if let Some(quote) = quote {
                *character == quote
            } else {
                character.is_whitespace() || matches!(*character, ';' | '|' | '&' | ')' | '(')
            }
        })
        .map(|(index, _)| index)
        .unwrap_or(rest.len());
    let delimiter = &rest[..end];
    if delimiter.is_empty() {
        None
    } else {
        Some(delimiter.to_string())
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
    (
        line[offset..].trim_end().to_string(),
        line[..offset].chars().count() + 1,
    )
}

fn span_for_scanned(path: &str, line_index: usize, line: &ScannedManifestLine) -> SourceSpan {
    SourceSpan {
        path: path.to_string(),
        start_line: line_index + 1,
        start_column: line.start_column,
        end_line: line_index + 1,
        end_column: line.start_column + line.content.as_deref().unwrap_or_default().chars().count(),
    }
}

fn span_for(path: &str, line_index: usize, line: &str) -> SourceSpan {
    SourceSpan {
        path: path.to_string(),
        start_line: line_index + 1,
        start_column: 1,
        end_line: line_index + 1,
        end_column: line.chars().count() + 1,
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

pub(crate) fn write_snapshot_jsonl(
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

pub(crate) fn snapshot_profile(snapshot: &ManifestSnapshot) -> &str {
    &snapshot.header.profile
}

pub(crate) fn snapshot_head(snapshot: &ManifestSnapshot) -> &str {
    &snapshot.header.git_head
}

pub(crate) fn snapshot_fingerprint(snapshot: &ManifestSnapshot) -> &str {
    &snapshot.header.source_fingerprint
}

pub(crate) fn snapshot_dirty_fingerprint(snapshot: &ManifestSnapshot) -> &str {
    &snapshot.header.git_status_hash
}

pub(crate) fn snapshot_agent_canon_pin(snapshot: &ManifestSnapshot) -> &str {
    &snapshot.header.agentcanon_pin
}

pub(crate) fn snapshot_source_scope_counts(snapshot: &ManifestSnapshot) -> (usize, usize, usize) {
    (
        snapshot.source_universe.candidate_paths.len(),
        snapshot.source_universe.eligible_paths.len(),
        snapshot.source_universe.excluded_paths.len(),
    )
}

fn write_envelope(
    writer: &mut impl Write,
    record_type: &str,
    record_id: &str,
    snapshot_id: &str,
    payload: Value,
) -> Result<(), ManifestError> {
    let envelope = json!({
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
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

    #[test]
    fn parser_reads_manifest_after_line_eighty() {
        let mut text = (0..90)
            .map(|index| format!("plain line {index}"))
            .collect::<Vec<_>>()
            .join("\n");
        text.push_str(
            "\n# @dependency-start\n# contract implementation\n# responsibility Complete-file fixture.\n# upstream design design.md fixture edge\n# @dependency-end\n",
        );
        let parsed = ManifestParser::parse("fixture.py", &text).expect("complete-file parse");
        assert!(parsed.manifest_present);
        assert_eq!(parsed.dependencies.len(), 1);
        assert_eq!(parsed.dependencies[0].target, "design.md");
        assert_eq!(parsed.dependencies[0].source_span.start_line, 94);
    }

    #[test]
    fn parser_returns_normal_ast_when_manifest_is_absent() {
        let parsed = ManifestParser::parse("plain.py", "print('plain')\n").expect("plain file");
        assert!(!parsed.manifest_present);
        assert!(parsed.contract.is_empty());
        assert!(parsed.responsibility.is_empty());
        assert!(parsed.coverage.is_empty());
        assert!(parsed.dependencies.is_empty());
        assert_eq!(parsed.source_span, None);
    }

    #[test]
    fn parser_rejects_missing_end_marker() {
        let error = ManifestParser::parse(
            "broken.py",
            "# @dependency-start\n# contract implementation\n# responsibility Broken fixture.\n",
        )
        .expect_err("missing end marker must fail");
        assert!(error.to_string().contains("manifest.marker.missing_end"));
    }

    #[test]
    fn parser_ignores_python_and_shell_fixture_literals() {
        let python = "# @dependency-start\n# contract test\n# responsibility Python fixture.\n# @dependency-end\nvalue = \"\"\"\n# @dependency-start\n# @dependency-end\n\"\"\"\n";
        let parsed = ManifestParser::parse("fixture.py", python).expect("Python literal");
        assert!(parsed.manifest_present);

        let shell = "# @dependency-start\n# contract tool\n# responsibility Shell fixture.\n# @dependency-end\ncat <<'EOF'\n# @dependency-start\n# @dependency-end\nEOF\n";
        let parsed = ManifestParser::parse("fixture.sh", shell).expect("shell heredoc");
        assert!(parsed.manifest_present);
    }

    #[test]
    fn generated_source_rules_follow_canonical_artifact_placement() {
        let graph = generated_source_rule(".agent-canon/knowledge-graph/graph.sqlite")
            .expect("graph output exclusion");
        assert_eq!(graph.rule_id, "parent-generated-graph-output");

        let runtime = generated_source_rule(
            "experiments/_template/result/readonly_agent_log_analysis_status/run.log",
        )
        .expect("runtime result exclusion");
        assert_eq!(runtime.reason_code, "source.excluded_runtime_result");

        let report = generated_source_rule("reports/agents/run/design_review.md")
            .expect("run-local report exclusion");
        assert_eq!(report.rule_id, "run-local-agent-report-placement");

        let experiment = generated_source_rule(
            "experiments/_template/result/graph_active_packet_pytest/run_manifest.json",
        )
        .expect("managed experiment exclusion");
        assert_eq!(experiment.rule_id, "managed-experiment-result-placement");

        let obsolete = generated_source_rule("tools/agent_tools/bind_r2_scope.py")
            .expect("approved obsolete route exclusion");
        assert_eq!(
            obsolete.rule_id,
            "knowledge-graph-replacement-deletion-list"
        );

        let bytecode = generated_source_rule("tools/agent_tools/__pycache__/route.pyc")
            .expect("python bytecode exclusion");
        assert_eq!(bytecode.rule_id, "python-bytecode-cache");

        assert!(generated_source_rule("documents/runtime-log-archive.md").is_none());
        assert!(generated_source_rule("experiments/_template/run.py").is_none());
    }
}
