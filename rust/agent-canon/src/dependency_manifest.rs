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
use std::io::{self, BufRead, Cursor, Write};
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

pub(crate) type TransportError = ManifestError;
pub(crate) type NormalizationError = ManifestError;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct NormalizeRequest {
    pub root: PathBuf,
    pub profile: String,
    pub snapshot_jsonl: PathBuf,
    pub evidence_jsonl: Vec<PathBuf>,
    pub relation_registry_json: PathBuf,
    pub output_jsonl: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct RelationRegistryEntryV1 {
    pub capability_id: String,
    pub discriminator: String,
    pub family: String,
    pub layer: String,
    pub raw_kind: String,
    pub stored_kind: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct RelationRegistryArtifactV1 {
    pub entries: Vec<RelationRegistryEntryV1>,
    pub registry_fingerprint: String,
    pub registry_version: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ObservedEvidence {
    pub observation_id: String,
    pub extractor_id: String,
    pub extractor_version: String,
    pub capability_id: String,
    pub relation_kind: String,
    pub from_locator: String,
    pub to_locator: String,
    pub from_identity_id: String,
    pub to_identity_id: String,
    pub source_span: SourceSpan,
    pub payload_hash: String,
    pub classification: String,
    pub accepted: bool,
    pub snapshot_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ExtractorCapability {
    pub capability_id: String,
    pub extractor_id: String,
    pub extractor_version: String,
    pub relation_kinds: Vec<String>,
    pub input_scope: String,
    pub supported_file_kinds: Vec<String>,
    pub unsupported_behavior: String,
    pub dynamic_behavior: String,
    pub provenance_fields: Vec<String>,
    pub completeness_claim: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Attestation {
    pub attestation_id: String,
    pub attestation_key: String,
    pub evidence_type: String,
    pub evidence_id: String,
    pub declaring_identity_id: String,
    pub dependent_identity_id: String,
    pub prerequisite_identity_id: String,
    pub declared_direction: String,
    pub relation_kind: String,
    pub source_span: SourceSpan,
    pub reason: String,
    pub raw_line_hash: String,
    pub accepted: bool,
    pub rejection_reason: String,
    pub snapshot_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct NormalizedRelation {
    pub fact_id: String,
    pub from_identity_id: String,
    pub to_identity_id: String,
    pub relation_kind: String,
    pub semantic_direction: String,
    pub pair_identity: String,
    pub attestation_ids: Vec<String>,
    pub observation_ids: Vec<String>,
    pub authority: String,
    pub accepted: bool,
    pub reconciliation_status: String,
    pub source_snapshot_id: String,
    pub source_content_hashes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct AmbiguityA {
    pub ambiguity_id: String,
    pub source_identity_id: String,
    pub candidate_fact_ids: Vec<String>,
    pub candidate_targets: Vec<String>,
    pub relation_kind: String,
    pub reason_code: String,
    pub evidence_ids: Vec<String>,
    pub resolution_required: bool,
    pub covered: bool,
    pub snapshot_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct NormalizationSummary {
    pub snapshot_id: String,
    pub record_counts: BTreeMap<String, usize>,
    pub accepted_fact_count: usize,
    pub rejected_declaration_count: usize,
    pub rejected_observation_count: usize,
    pub ambiguity_count: usize,
    pub source_exclusion_count: usize,
    pub normalized_record_fingerprint: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct NormalizedRecordSet {
    pub(crate) header: SnapshotHeader,
    pub(crate) source_identities: Vec<SourceIdentity>,
    pub(crate) declarations: Vec<DependencyDeclaration>,
    pub(crate) attestations: Vec<Attestation>,
    pub(crate) relations: Vec<NormalizedRelation>,
    pub(crate) observations: Vec<ObservedEvidence>,
    pub(crate) surface_relations: Vec<SurfaceRelation>,
    pub(crate) source_exclusions: Vec<SourceExclusion>,
    pub(crate) ambiguities: Vec<AmbiguityA>,
    pub(crate) capabilities: Vec<ExtractorCapability>,
    pub(crate) source_universe: SourceUniverse,
    pub(crate) summary: NormalizationSummary,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg(test)]
pub(crate) struct RelationKindSpec {
    pub capability_id: &'static str,
    pub raw_kind: &'static str,
    pub discriminator: &'static str,
    pub stored_kind: &'static str,
    pub layer: &'static str,
    pub query_family: &'static str,
}

#[cfg(test)]
// Non-authoritative compiled baseline for fixture conformance and supported-value translation.
// Runtime semantic acceptance is always derived from RelationRegistryArtifactV1.
pub(crate) const RELATION_KIND_REGISTRY: &[RelationKindSpec] = &[
    RelationKindSpec {
        capability_id: "header-target-resolver.v1",
        raw_kind: "header_context",
        discriminator: "declared_kind=design",
        stored_kind: "design",
        layer: "deps",
        query_family: "dependency",
    },
    RelationKindSpec {
        capability_id: "header-target-resolver.v1",
        raw_kind: "header_context",
        discriminator: "declared_kind=implementation",
        stored_kind: "implementation",
        layer: "deps",
        query_family: "dependency",
    },
    RelationKindSpec {
        capability_id: "header-target-resolver.v1",
        raw_kind: "header_context",
        discriminator: "declared_kind=environment",
        stored_kind: "environment",
        layer: "deps",
        query_family: "dependency",
    },
    RelationKindSpec {
        capability_id: "code-static.v1",
        raw_kind: "code_reference",
        discriminator: "reference_kind=import",
        stored_kind: "import",
        layer: "code",
        query_family: "import",
    },
    RelationKindSpec {
        capability_id: "code-static.v1",
        raw_kind: "code_reference",
        discriminator: "reference_kind=include",
        stored_kind: "include",
        layer: "code",
        query_family: "import",
    },
    RelationKindSpec {
        capability_id: "code-static.v1",
        raw_kind: "code_reference",
        discriminator: "reference_kind=source",
        stored_kind: "source",
        layer: "code",
        query_family: "import",
    },
    RelationKindSpec {
        capability_id: "rust-structured.v1",
        raw_kind: "symbol",
        discriminator: "",
        stored_kind: "symbol_reference",
        layer: "code",
        query_family: "call",
    },
    RelationKindSpec {
        capability_id: "rust-structured.v1",
        raw_kind: "call",
        discriminator: "",
        stored_kind: "call",
        layer: "code",
        query_family: "call",
    },
    RelationKindSpec {
        capability_id: "structure-contract.v1",
        raw_kind: "contains",
        discriminator: "",
        stored_kind: "contains",
        layer: "artifact",
        query_family: "containment",
    },
    RelationKindSpec {
        capability_id: "structure-contract.v1",
        raw_kind: "generated_from",
        discriminator: "",
        stored_kind: "generated_from",
        layer: "artifact",
        query_family: "generated",
    },
    RelationKindSpec {
        capability_id: "structure-contract.v1",
        raw_kind: "view_of",
        discriminator: "",
        stored_kind: "view_of",
        layer: "artifact",
        query_family: "view",
    },
    RelationKindSpec {
        capability_id: "responsibility-scope.v1",
        raw_kind: "owned_by",
        discriminator: "",
        stored_kind: "owned_by",
        layer: "artifact",
        query_family: "ownership",
    },
    RelationKindSpec {
        capability_id: "responsibility-scope.v1",
        raw_kind: "contains",
        discriminator: "",
        stored_kind: "contains",
        layer: "artifact",
        query_family: "containment",
    },
    RelationKindSpec {
        capability_id: "import-responsibility.v1",
        raw_kind: "import_boundary",
        discriminator: "",
        stored_kind: "import_boundary",
        layer: "code",
        query_family: "import",
    },
    RelationKindSpec {
        capability_id: "document-inventory.v1",
        raw_kind: "document",
        discriminator: "",
        stored_kind: "document_relation",
        layer: "document-canon",
        query_family: "document",
    },
    RelationKindSpec {
        capability_id: "document-inventory.v1",
        raw_kind: "view_of",
        discriminator: "",
        stored_kind: "view_of",
        layer: "artifact",
        query_family: "view",
    },
    RelationKindSpec {
        capability_id: "catalog-route.v1",
        raw_kind: "catalog",
        discriminator: "catalog_type=skill",
        stored_kind: "skill_catalog_member",
        layer: "artifact",
        query_family: "catalog",
    },
    RelationKindSpec {
        capability_id: "catalog-route.v1",
        raw_kind: "catalog",
        discriminator: "catalog_type=tool",
        stored_kind: "tool_catalog_member",
        layer: "artifact",
        query_family: "catalog",
    },
    RelationKindSpec {
        capability_id: "catalog-route.v1",
        raw_kind: "catalog",
        discriminator: "catalog_type=workflow",
        stored_kind: "workflow_catalog_member",
        layer: "artifact",
        query_family: "catalog",
    },
    RelationKindSpec {
        capability_id: "source-universe.v1",
        raw_kind: "submodule_pin",
        discriminator: "",
        stored_kind: "submodule_pin",
        layer: "artifact",
        query_family: "submodule",
    },
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ClosureResult {
    pub reachable_identity_ids: Vec<String>,
    pub direct_witness_fact_ids: Vec<String>,
    pub allowed_relation_kinds: Vec<String>,
    pub visited_trace: Vec<Vec<String>>,
    pub iterations: usize,
    pub termination_bound: usize,
    pub monotone: bool,
    pub order_independent: bool,
    pub source_exclusion_count: usize,
    pub ambiguity_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct AdjacencyProjection {
    pub downstream: BTreeMap<String, Vec<String>>,
    pub upstream: BTreeMap<String, Vec<String>>,
    pub direct_fact_count: usize,
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

#[derive(Debug)]
struct SourceIdentityLookups {
    path_by_id: BTreeMap<String, String>,
    id_by_locator: BTreeMap<String, String>,
}

fn preflight_source_identities(
    source_identities: &[SourceIdentity],
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
    for identity in source_identities {
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

    let path_by_id = source_identities
        .iter()
        .map(|identity| (identity.identity_id.clone(), identity.repo_rel_path.clone()))
        .collect::<BTreeMap<_, _>>();
    let mut id_by_locator = BTreeMap::new();
    for identity in source_identities {
        for locator in std::iter::once(&identity.repo_rel_path)
            .chain(std::iter::once(&identity.canonical_locator))
            .chain(identity.alternate_locators.iter())
        {
            id_by_locator.insert(locator.clone(), identity.identity_id.clone());
        }
    }
    Ok(SourceIdentityLookups {
        path_by_id,
        id_by_locator,
    })
}

fn write_success_output(
    output_jsonl: &Path,
    bytes: &[u8],
    stdout: &mut dyn Write,
    status: &mut dyn Write,
) -> Result<(), ManifestError> {
    if output_jsonl == Path::new("-") {
        stdout
            .write_all(bytes)
            .map_err(|error| ManifestError::Io(error.to_string()))?;
    } else {
        write_atomic(output_jsonl, bytes)?;
    }
    status
        .write_all(b"DEPENDENCY_MANIFEST_STATUS=ok\n")
        .map_err(|error| ManifestError::Io(error.to_string()))
}

pub fn run(args: &[String]) -> i32 {
    if args.first().map(String::as_str) == Some("normalize") {
        return run_normalize(args);
    }
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
    if let Err(error) = write_success_output(
        &request.output_jsonl,
        &bytes,
        &mut io::stdout(),
        &mut io::stderr(),
    ) {
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

fn parse_normalize_args(args: &[String]) -> Result<NormalizeRequest, String> {
    if args.first().map(String::as_str) != Some("normalize") {
        return Err("expected dependency-manifest normalize".to_string());
    }
    let mut root = None;
    let mut profile = None;
    let mut snapshot_jsonl = None;
    let mut evidence_jsonl = Vec::new();
    let mut relation_registry_json = None;
    let mut output_jsonl = None;
    let mut index = 1;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => root = Some(next_arg(args, &mut index, "--root")?),
            "--profile" => profile = Some(next_arg(args, &mut index, "--profile")?),
            "--snapshot-jsonl" => {
                snapshot_jsonl = Some(PathBuf::from(next_arg(
                    args,
                    &mut index,
                    "--snapshot-jsonl",
                )?))
            }
            "--evidence-jsonl" | "--evidence-input" => {
                let flag = args[index].clone();
                evidence_jsonl.push(PathBuf::from(next_arg(args, &mut index, &flag)?));
            }
            "--relation-registry-json" => {
                if relation_registry_json.is_some() {
                    return Err("duplicate --relation-registry-json".to_string());
                }
                relation_registry_json = Some(PathBuf::from(next_arg(
                    args,
                    &mut index,
                    "--relation-registry-json",
                )?));
            }
            "--output-jsonl" => {
                output_jsonl = Some(PathBuf::from(next_arg(args, &mut index, "--output-jsonl")?))
            }
            "--format" => {
                let format = next_arg(args, &mut index, "--format")?;
                if format != "jsonl" {
                    return Err(format!("invalid format {format}"));
                }
            }
            flag => return Err(format!("unknown flag {flag}")),
        }
    }
    let profile = profile.ok_or_else(|| "missing --profile".to_string())?;
    if profile != "parent" {
        return Err(format!("invalid profile {profile}"));
    }
    Ok(NormalizeRequest {
        root: PathBuf::from(root.ok_or_else(|| "missing --root".to_string())?),
        profile,
        snapshot_jsonl: snapshot_jsonl.ok_or_else(|| "missing --snapshot-jsonl".to_string())?,
        evidence_jsonl,
        relation_registry_json: relation_registry_json
            .ok_or_else(|| "missing --relation-registry-json".to_string())?,
        output_jsonl: output_jsonl.ok_or_else(|| "missing --output-jsonl".to_string())?,
    })
}

fn relation_registry_entry_value(entry: &RelationRegistryEntryV1) -> Value {
    json!({
        "capability_id": entry.capability_id,
        "discriminator": entry.discriminator,
        "family": entry.family,
        "layer": entry.layer,
        "raw_kind": entry.raw_kind,
        "stored_kind": entry.stored_kind,
    })
}

fn relation_registry_entries_value(entries: &[RelationRegistryEntryV1]) -> Value {
    Value::Array(entries.iter().map(relation_registry_entry_value).collect())
}

fn relation_registry_fingerprint(
    entries: &[RelationRegistryEntryV1],
    registry_version: &str,
) -> Result<String, ManifestError> {
    let value = json!({
        "entries": relation_registry_entries_value(entries),
        "registry_version": registry_version,
    });
    let bytes =
        serde_json::to_vec(&value).map_err(|error| ManifestError::Transport(error.to_string()))?;
    Ok(sha256_bytes(&bytes))
}

struct StrictJsonKeyScanner<'a> {
    bytes: &'a [u8],
    cursor: usize,
}

impl<'a> StrictJsonKeyScanner<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, cursor: 0 }
    }

    fn scan_document(mut self) -> Result<(), String> {
        self.scan_value()?;
        self.skip_whitespace();
        if self.cursor != self.bytes.len() {
            return Err(format!(
                "unexpected trailing JSON bytes at offset {}",
                self.cursor
            ));
        }
        Ok(())
    }

    fn scan_value(&mut self) -> Result<(), String> {
        self.skip_whitespace();
        match self.peek() {
            Some(b'{') => self.scan_object(),
            Some(b'[') => self.scan_array(),
            Some(b'"') => self.scan_string_token().map(|_| ()),
            Some(b't') => self.scan_literal(b"true"),
            Some(b'f') => self.scan_literal(b"false"),
            Some(b'n') => self.scan_literal(b"null"),
            Some(b'-' | b'0'..=b'9') => self.scan_number(),
            Some(byte) => Err(format!(
                "unexpected JSON byte 0x{byte:02x} at offset {}",
                self.cursor
            )),
            None => Err("unexpected end of JSON value".to_string()),
        }
    }

    fn scan_object(&mut self) -> Result<(), String> {
        self.expect(b'{')?;
        self.skip_whitespace();
        if self.consume(b'}') {
            return Ok(());
        }
        let mut keys = BTreeSet::new();
        loop {
            self.skip_whitespace();
            let (start, end) = self.scan_string_token()?;
            let key = serde_json::from_slice::<String>(&self.bytes[start..end])
                .map_err(|error| format!("invalid JSON object key: {error}"))?;
            if !keys.insert(key.clone()) {
                return Err(format!("duplicate JSON key: {key}"));
            }
            self.skip_whitespace();
            self.expect(b':')?;
            self.scan_value()?;
            self.skip_whitespace();
            if self.consume(b'}') {
                return Ok(());
            }
            self.expect(b',')?;
        }
    }

    fn scan_array(&mut self) -> Result<(), String> {
        self.expect(b'[')?;
        self.skip_whitespace();
        if self.consume(b']') {
            return Ok(());
        }
        loop {
            self.scan_value()?;
            self.skip_whitespace();
            if self.consume(b']') {
                return Ok(());
            }
            self.expect(b',')?;
        }
    }

    fn scan_string_token(&mut self) -> Result<(usize, usize), String> {
        let start = self.cursor;
        self.expect(b'"')?;
        while let Some(byte) = self.peek() {
            match byte {
                b'"' => {
                    self.cursor += 1;
                    return Ok((start, self.cursor));
                }
                b'\\' => {
                    self.cursor += 1;
                    let escape = self
                        .peek()
                        .ok_or_else(|| "unterminated JSON escape at end of input".to_string())?;
                    self.cursor += 1;
                    if escape == b'u' {
                        for _ in 0..4 {
                            let digit = self
                                .peek()
                                .ok_or_else(|| "unterminated JSON unicode escape".to_string())?;
                            if !digit.is_ascii_hexdigit() {
                                return Err(format!(
                                    "invalid JSON unicode escape at offset {}",
                                    self.cursor
                                ));
                            }
                            self.cursor += 1;
                        }
                    } else if !matches!(
                        escape,
                        b'"' | b'\\' | b'/' | b'b' | b'f' | b'n' | b'r' | b't'
                    ) {
                        return Err(format!("invalid JSON escape at offset {}", self.cursor - 1));
                    }
                }
                0x00..=0x1f => {
                    return Err(format!(
                        "unescaped JSON control byte at offset {}",
                        self.cursor
                    ));
                }
                _ => self.cursor += 1,
            }
        }
        Err("unterminated JSON string".to_string())
    }

    fn scan_literal(&mut self, literal: &[u8]) -> Result<(), String> {
        if self.bytes.get(self.cursor..self.cursor + literal.len()) != Some(literal) {
            return Err(format!("invalid JSON literal at offset {}", self.cursor));
        }
        self.cursor += literal.len();
        Ok(())
    }

    fn scan_number(&mut self) -> Result<(), String> {
        self.consume(b'-');
        match self.peek() {
            Some(b'0') => self.cursor += 1,
            Some(b'1'..=b'9') => {
                self.cursor += 1;
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.cursor += 1;
                }
            }
            _ => return Err(format!("invalid JSON number at offset {}", self.cursor)),
        }
        if self.consume(b'.') {
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(format!(
                    "invalid JSON number fraction at offset {}",
                    self.cursor
                ));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.cursor += 1;
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            self.cursor += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.cursor += 1;
            }
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(format!(
                    "invalid JSON number exponent at offset {}",
                    self.cursor
                ));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.cursor += 1;
            }
        }
        Ok(())
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\n' | b'\r' | b'\t')) {
            self.cursor += 1;
        }
    }

    fn expect(&mut self, expected: u8) -> Result<(), String> {
        if self.consume(expected) {
            Ok(())
        } else {
            Err(format!(
                "expected JSON byte 0x{expected:02x} at offset {}",
                self.cursor
            ))
        }
    }

    fn consume(&mut self, expected: u8) -> bool {
        if self.peek() == Some(expected) {
            self.cursor += 1;
            true
        } else {
            false
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.cursor).copied()
    }
}

fn parse_strict_json_value(bytes: &[u8], label: &str) -> Result<Value, ManifestError> {
    StrictJsonKeyScanner::new(bytes)
        .scan_document()
        .map_err(|message| ManifestError::Transport(format!("{label}: {message}")))?;
    serde_json::from_slice::<Value>(bytes)
        .map_err(|error| ManifestError::Transport(format!("{label}: {error}")))
}

fn read_canonical_jsonl(reader: impl BufRead, label: &str) -> Result<Vec<Value>, ManifestError> {
    let mut values = Vec::new();
    let mut reader = reader;
    let mut raw_line = Vec::new();
    let mut line_number = 0usize;
    loop {
        raw_line.clear();
        let read = reader
            .read_until(b'\n', &mut raw_line)
            .map_err(|error| ManifestError::Transport(format!("{label}: {error}")))?;
        if read == 0 {
            break;
        }
        line_number += 1;
        if !raw_line.ends_with(b"\n") || raw_line.ends_with(b"\r\n") {
            return Err(ManifestError::Transport(format!(
                "{label} line {line_number} is not one canonical LF-terminated record"
            )));
        }
        let json_bytes = &raw_line[..raw_line.len() - 1];
        if json_bytes.is_empty() {
            return Err(ManifestError::Transport(format!(
                "blank {label} JSONL line {line_number}"
            )));
        }
        if line_number == 1 && json_bytes.starts_with(b"\xef\xbb\xbf") {
            return Err(ManifestError::Transport(format!(
                "{label} must not contain a UTF-8 BOM"
            )));
        }
        let value = parse_strict_json_value(json_bytes, &format!("{label} line {line_number}"))?;
        let canonical = serde_json::to_vec(&value)
            .map_err(|error| ManifestError::Transport(error.to_string()))?;
        if canonical != json_bytes {
            return Err(ManifestError::Transport(format!(
                "{label} line {line_number} is not canonical JSON"
            )));
        }
        values.push(value);
    }
    Ok(values)
}

#[cfg(test)]
fn canonical_relation_registry_entries() -> Vec<RelationRegistryEntryV1> {
    let mut entries = RELATION_KIND_REGISTRY
        .iter()
        .map(|spec| RelationRegistryEntryV1 {
            capability_id: spec.capability_id.to_string(),
            discriminator: spec.discriminator.to_string(),
            family: spec.query_family.to_string(),
            layer: spec.layer.to_string(),
            raw_kind: spec.raw_kind.to_string(),
            stored_kind: spec.stored_kind.to_string(),
        })
        .collect::<Vec<_>>();
    entries.sort_by(|left, right| {
        (
            &left.capability_id,
            &left.raw_kind,
            &left.discriminator,
            &left.stored_kind,
            &left.layer,
            &left.family,
        )
            .cmp(&(
                &right.capability_id,
                &right.raw_kind,
                &right.discriminator,
                &right.stored_kind,
                &right.layer,
                &right.family,
            ))
    });
    entries
}

#[cfg(test)]
fn builtin_relation_registry_artifact() -> Result<RelationRegistryArtifactV1, ManifestError> {
    let entries = canonical_relation_registry_entries();
    let registry_version = "relation_registry.v1".to_string();
    let registry_fingerprint = relation_registry_fingerprint(&entries, &registry_version)?;
    Ok(RelationRegistryArtifactV1 {
        entries,
        registry_fingerprint,
        registry_version,
    })
}

fn parse_relation_registry_artifact_bytes(
    bytes: &[u8],
) -> Result<RelationRegistryArtifactV1, ManifestError> {
    if bytes.last() != Some(&b'\n') {
        return Err(ManifestError::Transport(
            "relation registry artifact must end with one LF".to_string(),
        ));
    }
    let json_bytes = &bytes[..bytes.len() - 1];
    let value = parse_strict_json_value(json_bytes, "relation registry JSON")?;
    let canonical =
        serde_json::to_vec(&value).map_err(|error| ManifestError::Transport(error.to_string()))?;
    if canonical != json_bytes {
        return Err(ManifestError::Transport(
            "relation registry artifact is not canonical JSON".to_string(),
        ));
    }
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("relation registry artifact must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &["entries", "registry_fingerprint", "registry_version"],
    )?;
    let registry_version = string_field(object, "registry_version")?;
    if registry_version != "relation_registry.v1" {
        return Err(ManifestError::Transport(format!(
            "unsupported relation registry version {registry_version}"
        )));
    }
    let entries_value = object
        .get("entries")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            ManifestError::Transport("relation registry entries must be an array".to_string())
        })?;
    let mut entries = Vec::with_capacity(entries_value.len());
    for value in entries_value {
        let entry = value.as_object().ok_or_else(|| {
            ManifestError::Transport("relation registry entry must be an object".to_string())
        })?;
        ensure_exact_keys(
            entry,
            &[
                "capability_id",
                "discriminator",
                "family",
                "layer",
                "raw_kind",
                "stored_kind",
            ],
        )?;
        entries.push(RelationRegistryEntryV1 {
            capability_id: string_field(entry, "capability_id")?,
            discriminator: string_field(entry, "discriminator")?,
            family: string_field(entry, "family")?,
            layer: string_field(entry, "layer")?,
            raw_kind: string_field(entry, "raw_kind")?,
            stored_kind: string_field(entry, "stored_kind")?,
        });
    }
    if entries.is_empty()
        || entries.iter().any(|entry| {
            entry.capability_id.is_empty()
                || entry.raw_kind.is_empty()
                || entry.stored_kind.is_empty()
                || entry.layer.is_empty()
                || entry.family.is_empty()
        })
    {
        return Err(ManifestError::Transport(
            "relation registry entries contain an empty required field".to_string(),
        ));
    }
    let mut semantic_keys = BTreeSet::new();
    if entries.iter().any(|entry| {
        !semantic_keys.insert((
            entry.capability_id.as_str(),
            entry.raw_kind.as_str(),
            entry.discriminator.as_str(),
        ))
    }) {
        return Err(ManifestError::Transport(
            "relation registry entries contain a duplicate semantic key".to_string(),
        ));
    }
    let mut sorted_entries = entries.clone();
    sorted_entries.sort_by(|left, right| {
        (
            &left.capability_id,
            &left.raw_kind,
            &left.discriminator,
            &left.stored_kind,
            &left.layer,
            &left.family,
        )
            .cmp(&(
                &right.capability_id,
                &right.raw_kind,
                &right.discriminator,
                &right.stored_kind,
                &right.layer,
                &right.family,
            ))
    });
    if entries != sorted_entries {
        return Err(ManifestError::Transport(
            "relation registry entries are not in canonical order".to_string(),
        ));
    }
    let registry_fingerprint = string_field(object, "registry_fingerprint")?;
    let expected_fingerprint = relation_registry_fingerprint(&entries, &registry_version)?;
    if registry_fingerprint != expected_fingerprint {
        return Err(ManifestError::Transport(
            "relation registry fingerprint mismatch".to_string(),
        ));
    }
    Ok(RelationRegistryArtifactV1 {
        entries,
        registry_fingerprint,
        registry_version,
    })
}

pub(crate) fn load_relation_registry_artifact(
    path: &Path,
) -> Result<RelationRegistryArtifactV1, ManifestError> {
    let bytes = fs::read(path).map_err(|error| {
        ManifestError::Transport(format!("relation registry artifact: {error}"))
    })?;
    parse_relation_registry_artifact_bytes(&bytes)
}

fn run_normalize(args: &[String]) -> i32 {
    let request = match parse_normalize_args(args) {
        Ok(request) => request,
        Err(message) => {
            eprintln!("DEPENDENCY_MANIFEST_STATUS=usage");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC=usage:{message}");
            return 2;
        }
    };
    let relation_registry = match load_relation_registry_artifact(&request.relation_registry_json) {
        Ok(registry) => registry,
        Err(error) => {
            eprintln!("DEPENDENCY_MANIFEST_STATUS=transport-invalid");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
            return 22;
        }
    };
    let root = match fs::canonicalize(&request.root) {
        Ok(root) if root.is_dir() => root,
        Ok(root) => {
            eprintln!("DEPENDENCY_MANIFEST_STATUS=snapshot-invalid");
            eprintln!(
                "DEPENDENCY_MANIFEST_DIAGNOSTIC=root is not a directory: {}",
                root.display()
            );
            return 20;
        }
        Err(error) => {
            eprintln!("DEPENDENCY_MANIFEST_STATUS=snapshot-invalid");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC=root: {error}");
            return 20;
        }
    };
    let snapshot_bytes = match fs::read(&request.snapshot_jsonl) {
        Ok(bytes) => bytes,
        Err(error) => {
            eprintln!("DEPENDENCY_MANIFEST_STATUS=snapshot-invalid");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC=snapshot input: {error}");
            return 20;
        }
    };
    let snapshot = match parse_snapshot(Cursor::new(snapshot_bytes)) {
        Ok(snapshot) => snapshot,
        Err(error) => {
            let status = if error.to_string().contains("schema mismatch") {
                "schema-mismatch"
            } else {
                "snapshot-invalid"
            };
            eprintln!("DEPENDENCY_MANIFEST_STATUS={status}");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
            return if status == "schema-mismatch" { 21 } else { 20 };
        }
    };
    if normalize_root_matches(&root, &snapshot.header.root_realpath).is_err()
        || snapshot.header.profile != request.profile
    {
        eprintln!("DEPENDENCY_MANIFEST_STATUS=snapshot-invalid");
        eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC=snapshot/root/profile mismatch");
        return 20;
    }
    let records = match normalize_snapshot(&request, snapshot, &relation_registry) {
        Ok(records) => records,
        Err(error) => {
            let exit = match error {
                ManifestError::Usage(_) => 2,
                ManifestError::SnapshotInconsistent(_) => 20,
                ManifestError::Transport(_) => 22,
                ManifestError::Invalid { .. } => 23,
                ManifestError::Io(_) | ManifestError::Git(_) => 23,
            };
            let status = if exit == 22 {
                "transport-invalid"
            } else {
                "normalization-failed"
            };
            eprintln!("DEPENDENCY_MANIFEST_STATUS={status}");
            eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
            return exit;
        }
    };
    let mut bytes = Vec::new();
    if let Err(error) = write_normalized_record_set(&records, &relation_registry, &mut bytes) {
        eprintln!("DEPENDENCY_MANIFEST_STATUS=transport-invalid");
        eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
        return 22;
    }
    if let Err(error) = write_success_output(
        &request.output_jsonl,
        &bytes,
        &mut io::stdout(),
        &mut io::stderr(),
    ) {
        eprintln!("DEPENDENCY_MANIFEST_STATUS=output-failed");
        eprintln!("DEPENDENCY_MANIFEST_DIAGNOSTIC={error}");
        return 24;
    }
    0
}

fn normalize_root_matches(root: &Path, snapshot_root: &str) -> Result<(), ManifestError> {
    let snapshot_root = fs::canonicalize(snapshot_root)
        .map_err(|error| ManifestError::SnapshotInconsistent(error.to_string()))?;
    if root != snapshot_root {
        return Err(ManifestError::SnapshotInconsistent(
            "snapshot root does not match normalize root".to_string(),
        ));
    }
    Ok(())
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
    let identity_lookups = preflight_source_identities(&source_identities)?;

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
            let resolved_target_identity_id = identity_lookups.id_by_locator.get(&target).cloned();
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

#[derive(Debug, Clone)]
struct RelationCandidate {
    attestation: Attestation,
    from_identity_id: String,
    to_identity_id: String,
    relation_kind: String,
    pair_identity: String,
    evidence_type: String,
    observation_id: Option<String>,
    fact_id: String,
}

impl RelationNormalizer {
    #[cfg(test)]
    fn validate_compiled_registry_conformance_baseline() -> Result<(), ManifestError> {
        let mut keys = BTreeSet::new();
        for spec in RELATION_KIND_REGISTRY {
            if spec.capability_id.is_empty()
                || spec.raw_kind.is_empty()
                || spec.stored_kind.is_empty()
                || spec.layer.is_empty()
                || spec.query_family.is_empty()
            {
                return Err(ManifestError::Transport(
                    "relation kind registry contains an empty required field".to_string(),
                ));
            }
            if !keys.insert((spec.capability_id, spec.raw_kind, spec.discriminator)) {
                return Err(ManifestError::Transport(format!(
                    "duplicate relation kind registry key {}:{}:{}",
                    spec.capability_id, spec.raw_kind, spec.discriminator
                )));
            }
        }
        Ok(())
    }

    pub(crate) fn normalize_relation_kind(
        registry: &RelationRegistryArtifactV1,
        capability_id: &str,
        raw_kind: &str,
        discriminator: &str,
    ) -> Result<RelationRegistryEntryV1, String> {
        let matches = registry
            .entries
            .iter()
            .filter(|spec| {
                spec.capability_id == capability_id
                    && spec.raw_kind == raw_kind
                    && spec.discriminator == discriminator
            })
            .cloned()
            .collect::<Vec<_>>();
        match matches.as_slice() {
            [spec] => Ok(spec.clone()),
            [] => Err(format!(
                "unregistered relation kind {capability_id}:{raw_kind}:{discriminator}"
            )),
            _ => Err(format!(
                "ambiguous relation kind {capability_id}:{raw_kind}:{discriminator}"
            )),
        }
    }

    pub(crate) fn allowed_kinds_for_family(
        registry: &RelationRegistryArtifactV1,
        family: &str,
    ) -> Vec<String> {
        let kinds = registry
            .entries
            .iter()
            .filter(|spec| spec.family == family)
            .map(|spec| spec.stored_kind.to_string())
            .collect::<BTreeSet<_>>();
        kinds.iter().cloned().collect()
    }

    pub(crate) fn derive_reverse_adjacency(
        relations: &[NormalizedRelation],
    ) -> AdjacencyProjection {
        let mut downstream = BTreeMap::<String, BTreeSet<String>>::new();
        let mut upstream = BTreeMap::<String, BTreeSet<String>>::new();
        let mut direct_fact_count = 0;
        for relation in relations.iter().filter(|relation| relation.accepted) {
            direct_fact_count += 1;
            downstream
                .entry(relation.from_identity_id.clone())
                .or_default()
                .insert(relation.to_identity_id.clone());
            upstream
                .entry(relation.to_identity_id.clone())
                .or_default()
                .insert(relation.from_identity_id.clone());
        }
        AdjacencyProjection {
            downstream: downstream
                .into_iter()
                .map(|(key, values)| (key, values.into_iter().collect()))
                .collect(),
            upstream: upstream
                .into_iter()
                .map(|(key, values)| (key, values.into_iter().collect()))
                .collect(),
            direct_fact_count,
        }
    }

    pub(crate) fn least_fixed_point(
        registry: &RelationRegistryArtifactV1,
        identities: &[SourceIdentity],
        source_exclusions: &[SourceExclusion],
        ambiguities: &[AmbiguityA],
        relations: &[NormalizedRelation],
        seeds: &[String],
        query_family: &str,
        allowed_relation_kinds: &[String],
    ) -> Result<ClosureResult, ManifestError> {
        let registered_family_kinds = Self::allowed_kinds_for_family(registry, query_family)
            .into_iter()
            .collect::<BTreeSet<_>>();
        if registered_family_kinds.is_empty() {
            return Err(ManifestError::Transport(format!(
                "unknown closure query family {query_family}"
            )));
        }
        let allowed = allowed_relation_kinds
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        if allowed.len() != allowed_relation_kinds.len()
            || allowed
                .iter()
                .any(|kind| !registered_family_kinds.contains(kind))
        {
            return Err(ManifestError::Transport(format!(
                "closure kinds must be unique members of query family {query_family}"
            )));
        }
        let vertices = identities
            .iter()
            .filter(|identity| identity.exists)
            .map(|identity| identity.identity_id.clone())
            .collect::<BTreeSet<_>>();
        let excluded = source_exclusions
            .iter()
            .map(|exclusion| exclusion.source_identity_id.as_str())
            .collect::<BTreeSet<_>>();
        let accepted_fact_ids = relations
            .iter()
            .filter(|relation| relation.accepted)
            .map(|relation| relation.fact_id.as_str())
            .collect::<BTreeSet<_>>();
        if ambiguities.iter().any(|ambiguity| {
            ambiguity
                .candidate_fact_ids
                .iter()
                .any(|fact_id| accepted_fact_ids.contains(fact_id.as_str()))
        }) {
            return Err(ManifestError::Transport(
                "accepted direct facts overlap ambiguity candidates".to_string(),
            ));
        }
        let registered_stored_kinds = registry
            .entries
            .iter()
            .map(|spec| spec.stored_kind.as_str())
            .collect::<BTreeSet<_>>();
        for relation in relations.iter().filter(|relation| relation.accepted) {
            if !registered_stored_kinds.contains(relation.relation_kind.as_str()) {
                return Err(ManifestError::Transport(format!(
                    "accepted relation uses unregistered kind {}",
                    relation.relation_kind
                )));
            }
            if !vertices.contains(&relation.from_identity_id)
                || !vertices.contains(&relation.to_identity_id)
                || excluded.contains(relation.from_identity_id.as_str())
                || excluded.contains(relation.to_identity_id.as_str())
            {
                return Err(ManifestError::Transport(
                    "accepted relation endpoint is outside U".to_string(),
                ));
            }
        }
        let trace = Self::closure_trace(&vertices, &excluded, relations, seeds, &allowed, false);
        let reachable_set = trace.last().cloned().unwrap_or_default();
        let reachable = reachable_set.iter().cloned().collect::<Vec<_>>();
        let mut witness_fact_ids = relations
            .iter()
            .filter(|relation| {
                relation.accepted
                    && allowed.contains(&relation.relation_kind)
                    && reachable_set.contains(&relation.from_identity_id)
                    && reachable_set.contains(&relation.to_identity_id)
            })
            .map(|relation| relation.fact_id.clone())
            .collect::<Vec<_>>();
        witness_fact_ids.sort();
        witness_fact_ids.dedup();
        let mut reversed_seeds = seeds.to_vec();
        reversed_seeds.reverse();
        let reverse_trace = Self::closure_trace(
            &vertices,
            &excluded,
            relations,
            &reversed_seeds,
            &allowed,
            true,
        );
        let visited_trace = trace
            .iter()
            .map(|visited| visited.iter().cloned().collect::<Vec<_>>())
            .collect::<Vec<_>>();
        let monotone = trace
            .windows(2)
            .all(|window| window[0].is_subset(&window[1]));
        let iterations = trace.len().saturating_sub(1);
        Ok(ClosureResult {
            reachable_identity_ids: reachable,
            direct_witness_fact_ids: witness_fact_ids,
            allowed_relation_kinds: allowed.into_iter().collect(),
            visited_trace,
            iterations,
            termination_bound: vertices.len(),
            monotone,
            order_independent: reverse_trace.last() == Some(&reachable_set),
            source_exclusion_count: source_exclusions.len(),
            ambiguity_count: ambiguities.len(),
        })
    }

    fn closure_trace(
        vertices: &BTreeSet<String>,
        excluded: &BTreeSet<&str>,
        relations: &[NormalizedRelation],
        seeds: &[String],
        allowed: &BTreeSet<String>,
        reverse_relation_order: bool,
    ) -> Vec<BTreeSet<String>> {
        let mut visited = seeds
            .iter()
            .filter(|seed| vertices.contains(*seed) && !excluded.contains(seed.as_str()))
            .cloned()
            .collect::<BTreeSet<_>>();
        let mut trace = vec![visited.clone()];
        loop {
            let mut next = visited.clone();
            let mut consider = |relation: &NormalizedRelation| {
                if relation.accepted
                    && visited.contains(&relation.from_identity_id)
                    && allowed.contains(&relation.relation_kind)
                    && vertices.contains(&relation.to_identity_id)
                    && !excluded.contains(relation.to_identity_id.as_str())
                {
                    next.insert(relation.to_identity_id.clone());
                }
            };
            if reverse_relation_order {
                relations.iter().rev().for_each(&mut consider);
            } else {
                relations.iter().for_each(&mut consider);
            }
            if next == visited {
                break;
            }
            visited = next;
            trace.push(visited.clone());
        }
        trace
    }
}

pub(crate) struct RelationNormalizer;

fn producer_capability_rows(
    registry: &RelationRegistryArtifactV1,
) -> Vec<(String, String, Vec<String>)> {
    let mut raw_kinds = BTreeMap::<String, BTreeSet<String>>::new();
    for spec in &registry.entries {
        raw_kinds
            .entry(spec.capability_id.clone())
            .or_default()
            .insert(spec.raw_kind.clone());
    }
    raw_kinds
        .into_iter()
        .map(|(capability_id, kinds)| {
            let extractor_id = capability_id
                .strip_suffix(".v1")
                .unwrap_or(&capability_id)
                .to_string();
            (capability_id, extractor_id, kinds.into_iter().collect())
        })
        .collect()
}

fn capability_rejection_reason(
    registry: &RelationRegistryArtifactV1,
    capability: Option<&ExtractorCapability>,
    observation: &ObservedEvidence,
) -> Option<String> {
    let Some(capability) = capability else {
        return Some("capability_unknown".to_string());
    };
    let expected = producer_capability_rows(registry)
        .into_iter()
        .find(|(capability_id, _, _)| capability_id == &capability.capability_id);
    let Some((_, expected_extractor, expected_raw_kinds)) = expected else {
        return Some("capability_unknown".to_string());
    };
    let required_provenance = ["payload_hash", "snapshot_id", "source_span"]
        .into_iter()
        .map(str::to_string)
        .collect::<BTreeSet<_>>();
    let actual_provenance = capability
        .provenance_fields
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    let status = format!(
        "{} {}",
        capability.input_scope.to_ascii_lowercase(),
        capability.completeness_claim.to_ascii_lowercase()
    );
    if !capability.input_scope.starts_with("connected:")
        || !capability.completeness_claim.contains("connected")
        || ["unavailable", "provided-empty", "o=empty", "coverage=0"]
            .iter()
            .any(|marker| status.contains(marker))
    {
        return Some("capability_unavailable".to_string());
    }
    if capability.extractor_id != expected_extractor
        || capability.extractor_id != observation.extractor_id
        || capability.extractor_version != observation.extractor_version
        || capability.extractor_version.is_empty()
        || capability.extractor_version == "unavailable"
        || capability.relation_kinds != expected_raw_kinds
        || actual_provenance != required_provenance
    {
        return Some("provenance_incomplete".to_string());
    }
    None
}

fn observation_producer_rejection_reason(
    registry: &RelationRegistryArtifactV1,
    observation: &ObservedEvidence,
    capability: Option<&ExtractorCapability>,
    spec: Option<&RelationRegistryEntryV1>,
) -> Option<String> {
    capability_rejection_reason(registry, capability, observation)
        .or_else(|| {
            let classification = observation.classification.to_ascii_lowercase();
            (classification.contains("dynamic")
                || classification.contains("reflection")
                || classification.contains("runtime"))
            .then(|| "dynamic_or_reflection".to_string())
        })
        .or_else(|| {
            observation
                .classification
                .to_ascii_lowercase()
                .contains("unresolved")
                .then(|| "unsupported_relation".to_string())
        })
        .or_else(|| (!observation.accepted).then(|| "unsupported_relation".to_string()))
        .or_else(|| spec.is_none().then(|| "kind_unregistered".to_string()))
        .or_else(|| {
            spec.filter(|registered| registered.family.is_empty())
                .map(|_| "query_family_unregistered".to_string())
        })
}

fn merge_surface_relations(
    snapshot_relations: Vec<SurfaceRelation>,
    evidence_relations: Vec<SurfaceRelation>,
) -> Result<Vec<SurfaceRelation>, ManifestError> {
    let mut merged = BTreeMap::<String, SurfaceRelation>::new();
    for relation in snapshot_relations.into_iter().chain(evidence_relations) {
        match merged.get(&relation.relation_id) {
            Some(previous) if previous == &relation => {
                // Exact cross-input duplicates are explicitly idempotent.
            }
            Some(_) => {
                return Err(ManifestError::Transport(format!(
                    "conflicting snapshot/evidence surface relation {}",
                    relation.relation_id
                )))
            }
            None => {
                merged.insert(relation.relation_id.clone(), relation);
            }
        }
    }
    Ok(merged.into_values().collect())
}

pub(crate) fn normalize_snapshot(
    request: &NormalizeRequest,
    snapshot: ManifestSnapshot,
    registry: &RelationRegistryArtifactV1,
) -> Result<NormalizedRecordSet, NormalizationError> {
    if snapshot.header.schema_version != SNAPSHOT_SCHEMA_VERSION
        || snapshot.header.profile != request.profile
        || !snapshot.header.snapshot_consistent
    {
        return Err(ManifestError::SnapshotInconsistent(
            "normalization requires a consistent source_snapshot.v1".to_string(),
        ));
    }
    let (mut observations, supplied_capabilities, supplied_surfaces, _) =
        read_evidence_inputs(&request.evidence_jsonl, &snapshot.header.snapshot_id)?;
    observations.sort_by(|left, right| left.observation_id.cmp(&right.observation_id));
    let capabilities = materialize_capabilities(
        registry,
        &supplied_capabilities,
        &observations,
        &request.evidence_jsonl,
    );
    let capabilities_by_id = capabilities
        .iter()
        .map(|capability| (capability.capability_id.as_str(), capability))
        .collect::<BTreeMap<_, _>>();
    let mut declarations = snapshot.declarations.clone();
    declarations.sort_by(|left, right| left.declaration_id.cmp(&right.declaration_id));
    let surface_relations =
        merge_surface_relations(snapshot.surface_relations.clone(), supplied_surfaces)?;

    let identities_by_id = snapshot
        .source_identities
        .iter()
        .map(|identity| (identity.identity_id.as_str(), identity))
        .collect::<BTreeMap<_, _>>();
    let excluded = snapshot
        .source_exclusions
        .iter()
        .map(|exclusion| exclusion.source_identity_id.as_str())
        .collect::<BTreeSet<_>>();
    let logical_by_id = identities_by_id
        .iter()
        .map(|(identity_id, identity)| (*identity_id, identity.logical_id.as_str()))
        .collect::<BTreeMap<_, _>>();
    let mut attestations_by_key = BTreeMap::<String, Attestation>::new();
    let mut attestation_evidence_keys = BTreeSet::<(String, String)>::new();
    let mut candidates = Vec::<RelationCandidate>::new();
    let mut ambiguities = BTreeMap::<String, AmbiguityA>::new();
    let mut rejected_declarations = BTreeSet::new();
    let mut rejected_observations = BTreeSet::new();

    for capability in &supplied_capabilities {
        if !registry
            .entries
            .iter()
            .any(|spec| spec.capability_id == capability.capability_id)
        {
            add_ambiguity(
                &mut ambiguities,
                ambiguity_record(
                    &snapshot.header.snapshot_id,
                    "",
                    Vec::new(),
                    Vec::new(),
                    "capability_unknown",
                    "",
                    vec![capability.capability_id.clone()],
                ),
            );
        }
    }

    for declaration in &declarations {
        let spec = match RelationNormalizer::normalize_relation_kind(
            registry,
            "header-target-resolver.v1",
            "header_context",
            &format!("declared_kind={}", declaration.declared_kind),
        ) {
            Ok(spec) => spec,
            Err(_) => {
                rejected_declarations.insert(declaration.declaration_id.clone());
                add_ambiguity(
                    &mut ambiguities,
                    ambiguity_for_declaration(
                        declaration,
                        "kind_unregistered",
                        &[],
                        &[],
                        &declaration.declared_kind,
                    ),
                );
                continue;
            }
        };
        let attestation_id = hash_parts(&["attestation.v1", &declaration.attestation_key]);
        let (from, to, rejection) =
            declaration_endpoints(declaration, &identities_by_id, &excluded);
        let accepted = rejection.is_none();
        let (dependent, prerequisite) = (
            from.clone().unwrap_or_default(),
            to.clone().unwrap_or_default(),
        );
        let attestation = Attestation {
            attestation_id: attestation_id.clone(),
            attestation_key: declaration.attestation_key.clone(),
            evidence_type: "declaration".to_string(),
            evidence_id: declaration.declaration_id.clone(),
            declaring_identity_id: declaration.source_identity_id.clone(),
            dependent_identity_id: dependent.clone(),
            prerequisite_identity_id: prerequisite.clone(),
            declared_direction: declaration.declared_direction.clone(),
            relation_kind: spec.stored_kind.to_string(),
            source_span: declaration.source_span.clone(),
            reason: declaration.reason.clone(),
            raw_line_hash: declaration.raw_line_hash.clone(),
            accepted,
            rejection_reason: rejection.clone().unwrap_or_default(),
            snapshot_id: snapshot.header.snapshot_id.clone(),
        };
        let evidence_key = (
            "declaration".to_string(),
            declaration.declaration_id.clone(),
        );
        if !attestation_evidence_keys.insert(evidence_key)
            || attestations_by_key
                .insert(declaration.attestation_key.clone(), attestation.clone())
                .is_some()
        {
            return Err(ManifestError::Transport(format!(
                "duplicate declaration attestation provenance {}",
                declaration.declaration_id
            )));
        }
        if let Some(reason) = rejection {
            rejected_declarations.insert(declaration.declaration_id.clone());
            add_ambiguity(
                &mut ambiguities,
                ambiguity_for_declaration(
                    declaration,
                    &reason,
                    &[],
                    &[declaration.declared_target.clone()],
                    &spec.stored_kind,
                ),
            );
            continue;
        }
        let pair_identity = pair_identity_for(
            &snapshot.header.parent_repo_id,
            &logical_by_id,
            &dependent,
            &prerequisite,
        );
        let fact_id = hash_parts(&["normalized_relation.v1", &pair_identity, &spec.stored_kind]);
        candidates.push(RelationCandidate {
            attestation,
            from_identity_id: dependent,
            to_identity_id: prerequisite,
            relation_kind: spec.stored_kind.to_string(),
            pair_identity,
            evidence_type: "declaration".to_string(),
            observation_id: None,
            fact_id,
        });
    }

    for observation in &mut observations {
        let discriminator = observation_discriminator(observation);
        let spec = RelationNormalizer::normalize_relation_kind(
            registry,
            &observation.capability_id,
            &observation.relation_kind,
            &discriminator,
        )
        .ok();
        let attestation_key = hash_parts(&[
            "observed_attestation.v1",
            &observation.snapshot_id,
            &observation.observation_id,
            &observation.payload_hash,
        ]);
        let attestation_id = hash_parts(&["attestation.v1", &attestation_key]);
        let (dependent, prerequisite, rejection) =
            observed_endpoints(observation, &identities_by_id, &excluded);
        let rejection = rejection.or_else(|| {
            observation_producer_rejection_reason(
                registry,
                observation,
                capabilities_by_id
                    .get(observation.capability_id.as_str())
                    .copied(),
                spec.as_ref(),
            )
        });
        let accepted = rejection.is_none();
        observation.accepted = accepted;
        let dependent = dependent.unwrap_or_default();
        let prerequisite = prerequisite.unwrap_or_default();
        let stored_kind = spec
            .as_ref()
            .map(|registered| registered.stored_kind.clone())
            .unwrap_or_else(|| observation.relation_kind.clone());
        let attestation = Attestation {
            attestation_id: attestation_id.clone(),
            attestation_key: attestation_key.clone(),
            evidence_type: "observation".to_string(),
            evidence_id: observation.observation_id.clone(),
            declaring_identity_id: observation.from_identity_id.clone(),
            dependent_identity_id: dependent.clone(),
            prerequisite_identity_id: prerequisite.clone(),
            declared_direction: "observed".to_string(),
            relation_kind: stored_kind.to_string(),
            source_span: observation.source_span.clone(),
            reason: observation.classification.clone(),
            raw_line_hash: observation.payload_hash.clone(),
            accepted,
            rejection_reason: rejection.clone().unwrap_or_default(),
            snapshot_id: snapshot.header.snapshot_id.clone(),
        };
        let evidence_key = (
            "observation".to_string(),
            observation.observation_id.clone(),
        );
        if !attestation_evidence_keys.insert(evidence_key)
            || attestations_by_key
                .insert(attestation_key, attestation.clone())
                .is_some()
        {
            return Err(ManifestError::Transport(format!(
                "duplicate observation attestation provenance {}",
                observation.observation_id
            )));
        }
        if let Some(reason) = rejection {
            rejected_observations.insert(observation.observation_id.clone());
            add_ambiguity(
                &mut ambiguities,
                ambiguity_for_observation(observation, &reason, &stored_kind),
            );
            continue;
        }
        let spec = spec.expect("accepted observation kind registered");
        let pair_identity = pair_identity_for(
            &snapshot.header.parent_repo_id,
            &logical_by_id,
            &dependent,
            &prerequisite,
        );
        let fact_id = hash_parts(&["normalized_relation.v1", &pair_identity, &spec.stored_kind]);
        candidates.push(RelationCandidate {
            attestation,
            from_identity_id: dependent,
            to_identity_id: prerequisite,
            relation_kind: spec.stored_kind.to_string(),
            pair_identity,
            evidence_type: "observation".to_string(),
            observation_id: Some(observation.observation_id.clone()),
            fact_id,
        });
    }

    let mut by_pair = BTreeMap::<String, Vec<RelationCandidate>>::new();
    for candidate in candidates {
        by_pair
            .entry(candidate.pair_identity.clone())
            .or_default()
            .push(candidate);
    }
    let mut relations = Vec::new();
    let mut matched_count = 0;
    let mut declared_only_count = 0;
    let mut observed_only_count = 0;
    for (pair, mut group) in by_pair {
        group.sort_by(|left, right| {
            left.attestation
                .attestation_id
                .cmp(&right.attestation.attestation_id)
        });
        let kinds = group
            .iter()
            .map(|candidate| candidate.relation_kind.clone())
            .collect::<BTreeSet<_>>();
        if kinds.len() > 1 {
            for candidate in &group {
                let attestation = attestations_by_key
                    .get_mut(&candidate.attestation.attestation_key)
                    .expect("candidate attestation retained");
                attestation.accepted = false;
                attestation.rejection_reason = "kind_contradiction".to_string();
                match candidate.evidence_type.as_str() {
                    "declaration" => {
                        rejected_declarations.insert(candidate.attestation.evidence_id.clone());
                    }
                    _ => {
                        rejected_observations.insert(candidate.attestation.evidence_id.clone());
                        if let Some(observation) = observations.iter_mut().find(|observation| {
                            observation.observation_id == candidate.attestation.evidence_id
                        }) {
                            observation.accepted = false;
                        }
                    }
                }
            }
            let fact_ids = group
                .iter()
                .map(|candidate| candidate.fact_id.clone())
                .collect::<BTreeSet<_>>();
            let evidence_ids = group
                .iter()
                .map(|candidate| candidate.attestation.evidence_id.clone())
                .collect::<BTreeSet<_>>();
            let targets = group
                .iter()
                .flat_map(|candidate| {
                    [
                        candidate.from_identity_id.clone(),
                        candidate.to_identity_id.clone(),
                    ]
                })
                .collect::<BTreeSet<_>>();
            add_ambiguity(
                &mut ambiguities,
                ambiguity_record(
                    &snapshot.header.snapshot_id,
                    &group[0].from_identity_id,
                    fact_ids.into_iter().collect(),
                    targets.into_iter().collect(),
                    "kind_contradiction",
                    "kind_contradiction",
                    evidence_ids.into_iter().collect(),
                ),
            );
            continue;
        }
        let first = &group[0];
        let has_declaration = group
            .iter()
            .any(|candidate| candidate.evidence_type == "declaration");
        let has_observation = group
            .iter()
            .any(|candidate| candidate.evidence_type == "observation");
        let reconciliation_status = if has_declaration && has_observation {
            matched_count += 1;
            "matched"
        } else if has_declaration {
            declared_only_count += 1;
            "declared_only"
        } else {
            observed_only_count += 1;
            "observed_only"
        };
        let attestation_ids = group
            .iter()
            .map(|candidate| candidate.attestation.attestation_id.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        let observation_ids = group
            .iter()
            .filter_map(|candidate| candidate.observation_id.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        let authority = match (has_declaration, has_observation) {
            (true, true) => "declaration+observation",
            (true, false) => "declaration",
            _ => "observation",
        };
        let source_content_hashes = [
            first.from_identity_id.as_str(),
            first.to_identity_id.as_str(),
        ]
        .iter()
        .filter_map(|identity_id| {
            identities_by_id
                .get(identity_id)
                .map(|identity| identity.content_hash.clone())
        })
        .collect::<Vec<_>>();
        relations.push(NormalizedRelation {
            fact_id: first.fact_id.clone(),
            from_identity_id: first.from_identity_id.clone(),
            to_identity_id: first.to_identity_id.clone(),
            relation_kind: first.relation_kind.clone(),
            semantic_direction: "depends_on".to_string(),
            pair_identity: pair,
            attestation_ids,
            observation_ids,
            authority: authority.to_string(),
            accepted: true,
            reconciliation_status: reconciliation_status.to_string(),
            source_snapshot_id: snapshot.header.snapshot_id.clone(),
            source_content_hashes,
        });
    }
    relations.sort_by(|left, right| left.fact_id.cmp(&right.fact_id));
    let mut ambiguities = ambiguities.into_values().collect::<Vec<_>>();
    ambiguities.sort_by(|left, right| left.ambiguity_id.cmp(&right.ambiguity_id));
    let attestations = attestations_by_key.into_values().collect::<Vec<_>>();
    let mut record_counts = BTreeMap::new();
    record_counts.insert("source_snapshot.v1".to_string(), 1);
    record_counts.insert(
        "source_identity.v1".to_string(),
        snapshot.source_identities.len(),
    );
    record_counts.insert("dependency_declaration.v1".to_string(), declarations.len());
    record_counts.insert("attestation.v1".to_string(), attestations.len());
    record_counts.insert("normalized_relation.v1".to_string(), relations.len());
    record_counts.insert("observed_evidence.v1".to_string(), observations.len());
    record_counts.insert("surface_relation.v1".to_string(), surface_relations.len());
    record_counts.insert(
        "source_exclusion.v1".to_string(),
        snapshot.source_exclusions.len(),
    );
    record_counts.insert("ambiguity_a.v1".to_string(), ambiguities.len());
    record_counts.insert("extractor_capability.v1".to_string(), capabilities.len());
    record_counts.insert("accepted_direct_fact_count".to_string(), relations.len());
    record_counts.insert(
        "rejected_declaration_count".to_string(),
        rejected_declarations.len(),
    );
    record_counts.insert(
        "rejected_observation_count".to_string(),
        rejected_observations.len(),
    );
    record_counts.insert("matched_count".to_string(), matched_count);
    record_counts.insert("declared_only_count".to_string(), declared_only_count);
    record_counts.insert("observed_only_count".to_string(), observed_only_count);
    record_counts.insert(
        "excluded_count".to_string(),
        snapshot.source_exclusions.len(),
    );
    record_counts.insert("unresolved_count".to_string(), ambiguities.len());
    record_counts.insert("duplicate_evidence_count".to_string(), 0);
    record_counts.insert("x_core_count".to_string(), 0);
    let mut records = NormalizedRecordSet {
        header: snapshot.header.clone(),
        source_identities: snapshot.source_identities.clone(),
        declarations,
        attestations,
        relations,
        observations,
        surface_relations,
        source_exclusions: snapshot.source_exclusions.clone(),
        ambiguities,
        capabilities,
        source_universe: snapshot.source_universe.clone(),
        summary: NormalizationSummary {
            snapshot_id: snapshot.header.snapshot_id.clone(),
            record_counts,
            accepted_fact_count: 0,
            rejected_declaration_count: 0,
            rejected_observation_count: 0,
            ambiguity_count: 0,
            source_exclusion_count: snapshot.source_exclusions.len(),
            normalized_record_fingerprint: String::new(),
        },
    };
    records.summary.accepted_fact_count = records.relations.len();
    records
        .source_identities
        .sort_by(|left, right| left.identity_id.cmp(&right.identity_id));
    records
        .declarations
        .sort_by(|left, right| left.declaration_id.cmp(&right.declaration_id));
    records
        .attestations
        .sort_by(|left, right| left.attestation_id.cmp(&right.attestation_id));
    records
        .relations
        .sort_by(|left, right| left.fact_id.cmp(&right.fact_id));
    records
        .observations
        .sort_by(|left, right| left.observation_id.cmp(&right.observation_id));
    records
        .surface_relations
        .sort_by(|left, right| left.relation_id.cmp(&right.relation_id));
    records
        .source_exclusions
        .sort_by(|left, right| left.source_exclusion_id.cmp(&right.source_exclusion_id));
    records
        .ambiguities
        .sort_by(|left, right| left.ambiguity_id.cmp(&right.ambiguity_id));
    records
        .capabilities
        .sort_by(|left, right| left.capability_id.cmp(&right.capability_id));
    records.summary.rejected_declaration_count = records
        .attestations
        .iter()
        .filter(|attestation| attestation.evidence_type == "declaration" && !attestation.accepted)
        .count();
    records.summary.rejected_observation_count = records
        .attestations
        .iter()
        .filter(|attestation| attestation.evidence_type == "observation" && !attestation.accepted)
        .count();
    records.summary.ambiguity_count = records.ambiguities.len();
    records.summary.record_counts = normalized_record_counts(&records);
    records.summary.normalized_record_fingerprint = normalized_record_fingerprint(&records)?;
    validate_normalized_record_set(&records, registry)?;
    Ok(records)
}

fn observation_discriminator(observation: &ObservedEvidence) -> String {
    if observation.classification.contains('=') {
        observation.classification.clone()
    } else {
        String::new()
    }
}

fn pair_identity_for(
    parent_repo_id: &str,
    logical_by_id: &BTreeMap<&str, &str>,
    dependent: &str,
    prerequisite: &str,
) -> String {
    let dependent = logical_by_id.get(dependent).copied().unwrap_or(dependent);
    let prerequisite = logical_by_id
        .get(prerequisite)
        .copied()
        .unwrap_or(prerequisite);
    hash_parts(&["relation_pair.v1", parent_repo_id, dependent, prerequisite])
}

fn declaration_endpoints(
    declaration: &DependencyDeclaration,
    identities: &BTreeMap<&str, &SourceIdentity>,
    excluded: &BTreeSet<&str>,
) -> (Option<String>, Option<String>, Option<String>) {
    let source = identities.get(declaration.source_identity_id.as_str());
    let target_id = declaration.resolved_target_identity_id.as_deref();
    let target = target_id.and_then(|target_id| identities.get(target_id).copied());
    let reason = if source.is_none() {
        Some("unresolved_source".to_string())
    } else if excluded.contains(declaration.source_identity_id.as_str()) {
        Some("source_excluded_source".to_string())
    } else if !source.expect("source checked").exists {
        Some("stale_source".to_string())
    } else if target_id.is_none() {
        Some("missing_target".to_string())
    } else if target.is_none() {
        Some("unresolved_target".to_string())
    } else if excluded.contains(target_id.expect("target checked")) {
        Some("source_excluded_target".to_string())
    } else if !target.expect("target checked").exists {
        Some("stale_target".to_string())
    } else {
        None
    };
    let source_id = declaration.source_identity_id.clone();
    let target_id = target_id.map(ToString::to_string);
    match declaration.declared_direction.as_str() {
        "upstream" => (Some(source_id), target_id, reason),
        "downstream" => (target_id, Some(source_id), reason),
        _ => (
            Some(source_id),
            target_id,
            Some("invalid_direction".to_string()),
        ),
    }
}

fn observed_endpoints(
    observation: &ObservedEvidence,
    identities: &BTreeMap<&str, &SourceIdentity>,
    excluded: &BTreeSet<&str>,
) -> (Option<String>, Option<String>, Option<String>) {
    let from = identities.get(observation.from_identity_id.as_str());
    let to = identities.get(observation.to_identity_id.as_str());
    let reason = if from.is_none() || to.is_none() {
        Some("unresolved_observation".to_string())
    } else if observation.observation_id.is_empty()
        || observation.extractor_id.is_empty()
        || observation.extractor_version.is_empty()
        || observation.capability_id.is_empty()
        || observation.relation_kind.is_empty()
        || observation.from_locator.is_empty()
        || observation.to_locator.is_empty()
        || observation.source_span.path.is_empty()
        || !is_hex_id(&observation.payload_hash)
        || observation.snapshot_id.is_empty()
    {
        Some("provenance_incomplete".to_string())
    } else if !identity_matches_locator(from.expect("from checked"), &observation.from_locator)
        || !identity_matches_locator(to.expect("to checked"), &observation.to_locator)
        || !identity_matches_locator(from.expect("from checked"), &observation.source_span.path)
    {
        Some("provenance_incomplete".to_string())
    } else if excluded.contains(observation.from_identity_id.as_str()) {
        Some("source_excluded_source".to_string())
    } else if excluded.contains(observation.to_identity_id.as_str()) {
        Some("source_excluded_target".to_string())
    } else if !from.expect("from checked").exists || !to.expect("to checked").exists {
        Some("stale_target".to_string())
    } else {
        None
    };
    (
        Some(observation.from_identity_id.clone()),
        Some(observation.to_identity_id.clone()),
        reason,
    )
}

fn identity_matches_locator(identity: &SourceIdentity, locator: &str) -> bool {
    locator == identity.repo_rel_path
        || locator == identity.canonical_locator
        || identity
            .alternate_locators
            .iter()
            .any(|alternate| alternate == locator)
}

fn add_ambiguity(ambiguities: &mut BTreeMap<String, AmbiguityA>, ambiguity: AmbiguityA) {
    ambiguities.insert(ambiguity.ambiguity_id.clone(), ambiguity);
}

fn ambiguity_for_declaration(
    declaration: &DependencyDeclaration,
    reason: &str,
    candidate_fact_ids: &[String],
    candidate_targets: &[String],
    relation_kind: &str,
) -> AmbiguityA {
    ambiguity_record(
        &declaration.snapshot_id,
        &declaration.source_identity_id,
        candidate_fact_ids.to_vec(),
        candidate_targets.to_vec(),
        reason,
        relation_kind,
        vec![declaration.declaration_id.clone()],
    )
}

fn ambiguity_for_observation(
    observation: &ObservedEvidence,
    reason: &str,
    relation_kind: &str,
) -> AmbiguityA {
    ambiguity_record(
        &observation.snapshot_id,
        &observation.from_identity_id,
        Vec::new(),
        vec![observation.to_identity_id.clone()],
        reason,
        relation_kind,
        vec![observation.observation_id.clone()],
    )
}

fn ambiguity_record(
    snapshot_id: &str,
    source_identity_id: &str,
    mut candidate_fact_ids: Vec<String>,
    mut candidate_targets: Vec<String>,
    reason_code: &str,
    relation_kind: &str,
    mut evidence_ids: Vec<String>,
) -> AmbiguityA {
    candidate_fact_ids.sort();
    candidate_fact_ids.dedup();
    candidate_targets.sort();
    candidate_targets.dedup();
    evidence_ids.sort();
    evidence_ids.dedup();
    let ambiguity_id = hash_parts(&[
        "ambiguity_a.v1",
        snapshot_id,
        source_identity_id,
        reason_code,
        relation_kind,
        &candidate_fact_ids.join(","),
        &candidate_targets.join(","),
        &evidence_ids.join(","),
    ]);
    AmbiguityA {
        ambiguity_id,
        source_identity_id: source_identity_id.to_string(),
        candidate_fact_ids,
        candidate_targets,
        relation_kind: relation_kind.to_string(),
        reason_code: reason_code.to_string(),
        evidence_ids,
        resolution_required: true,
        covered: false,
        snapshot_id: snapshot_id.to_string(),
    }
}

fn read_evidence_inputs(
    paths: &[PathBuf],
    snapshot_id: &str,
) -> Result<
    (
        Vec<ObservedEvidence>,
        Vec<ExtractorCapability>,
        Vec<SurfaceRelation>,
        usize,
    ),
    ManifestError,
> {
    let mut observations = BTreeMap::<String, ObservedEvidence>::new();
    let mut capabilities = BTreeMap::<String, ExtractorCapability>::new();
    let mut surfaces = BTreeMap::<String, SurfaceRelation>::new();
    for path in paths {
        let bytes = fs::read(path).map_err(|error| {
            ManifestError::Transport(format!("evidence input {}: {error}", path.display()))
        })?;
        let label = format!("evidence input {}", path.display());
        for value in read_canonical_jsonl(Cursor::new(bytes), &label)? {
            let record_type = value
                .get("record_type")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    ManifestError::Transport("evidence record_type is required".to_string())
                })?;
            let envelope = parse_envelope(&value, record_type, false)?;
            if envelope.snapshot_id != snapshot_id {
                return Err(ManifestError::Transport(
                    "evidence snapshot mismatch".to_string(),
                ));
            }
            match record_type {
                "observed_evidence.v1" => {
                    let observation =
                        parse_observed_evidence(envelope.record_id, envelope.payload)?;
                    if observation.snapshot_id != snapshot_id {
                        return Err(ManifestError::Transport(
                            "observation snapshot mismatch".to_string(),
                        ));
                    }
                    if let Some(previous) = observations.get(&observation.observation_id) {
                        let qualifier = if previous == &observation {
                            "exact"
                        } else {
                            "conflicting"
                        };
                        return Err(ManifestError::Transport(format!(
                            "{qualifier} duplicate observation {}",
                            observation.observation_id
                        )));
                    } else {
                        observations.insert(observation.observation_id.clone(), observation);
                    }
                }
                "extractor_capability.v1" => {
                    let capability =
                        parse_extractor_capability(envelope.record_id, envelope.payload)?;
                    if let Some(previous) = capabilities.get(&capability.capability_id) {
                        let qualifier = if previous == &capability {
                            "exact"
                        } else {
                            "conflicting"
                        };
                        return Err(ManifestError::Transport(format!(
                            "{qualifier} duplicate capability {}",
                            capability.capability_id
                        )));
                    } else {
                        capabilities.insert(capability.capability_id.clone(), capability);
                    }
                }
                "surface_relation.v1" => {
                    let relation = parse_surface_relation(envelope.record_id, envelope.payload)?;
                    if let Some(previous) = surfaces.get(&relation.relation_id) {
                        let qualifier = if previous == &relation {
                            "exact"
                        } else {
                            "conflicting"
                        };
                        return Err(ManifestError::Transport(format!(
                            "{qualifier} duplicate surface relation {}",
                            relation.relation_id
                        )));
                    } else {
                        surfaces.insert(relation.relation_id.clone(), relation);
                    }
                }
                _ => {
                    return Err(ManifestError::Transport(format!(
                        "unknown evidence record type {record_type}"
                    )))
                }
            }
        }
    }
    Ok((
        observations.into_values().collect(),
        capabilities.into_values().collect(),
        surfaces.into_values().collect(),
        0,
    ))
}

fn materialize_capabilities(
    registry: &RelationRegistryArtifactV1,
    supplied: &[ExtractorCapability],
    observations: &[ObservedEvidence],
    evidence_paths: &[PathBuf],
) -> Vec<ExtractorCapability> {
    let supplied = supplied
        .iter()
        .map(|capability| (capability.capability_id.clone(), capability.clone()))
        .collect::<BTreeMap<_, _>>();
    let known_capability_ids = registry
        .entries
        .iter()
        .map(|spec| spec.capability_id.as_str())
        .collect::<BTreeSet<_>>();
    let mut result = supplied
        .iter()
        .map(|(capability_id, capability)| {
            let mut capability = capability.clone();
            if !known_capability_ids.contains(capability_id.as_str()) {
                capability.input_scope = "unavailable:unregistered-capability".to_string();
                capability.completeness_claim =
                    "unavailable; O=empty; coverage=0; capability-unregistered".to_string();
            }
            (capability_id.clone(), capability)
        })
        .collect::<BTreeMap<_, _>>();
    for (capability_id, extractor_id, raw_kinds) in producer_capability_rows(registry) {
        if supplied.contains_key(&capability_id) {
            continue;
        }
        let used = observations
            .iter()
            .any(|observation| observation.capability_id == capability_id);
        result.insert(
            capability_id.clone(),
            ExtractorCapability {
                capability_id,
                extractor_id,
                extractor_version: "unavailable".to_string(),
                relation_kinds: raw_kinds,
                input_scope: if used {
                    "unavailable:explicit-evidence-without-connected-capability".to_string()
                } else if evidence_paths.is_empty() {
                    "unavailable:no-adapter-connected".to_string()
                } else {
                    "explicit-evidence-input:empty".to_string()
                },
                supported_file_kinds: Vec::new(),
                unsupported_behavior: "unsupported-and-unresolved-to-A".to_string(),
                dynamic_behavior: "dynamic-reflection-to-A".to_string(),
                provenance_fields: vec![
                    "payload_hash".to_string(),
                    "snapshot_id".to_string(),
                    "source_span".to_string(),
                ],
                completeness_claim: if evidence_paths.is_empty() {
                    "unavailable; O=empty; coverage=0; adapter-not-connected".to_string()
                } else if used {
                    "unavailable; supplied-O-rejected; coverage=0; capability-not-connected"
                        .to_string()
                } else {
                    "provided-empty; O=empty; coverage=0".to_string()
                },
            },
        );
    }
    result.into_values().collect()
}

fn parse_observed_evidence(
    record_id: &str,
    value: &Value,
) -> Result<ObservedEvidence, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("observed evidence payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "observation_id",
            "extractor_id",
            "extractor_version",
            "capability_id",
            "relation_kind",
            "from_locator",
            "to_locator",
            "from_identity_id",
            "to_identity_id",
            "source_span",
            "payload_hash",
            "classification",
            "accepted",
            "snapshot_id",
        ],
    )?;
    let observation_id = string_field(object, "observation_id")?;
    if observation_id != record_id || !observation_id.starts_with("O-") {
        return Err(ManifestError::Transport(
            "observation record_id must equal O-<sha256> observation_id".to_string(),
        ));
    }
    let payload_hash = string_field(object, "payload_hash")?;
    if !is_hex_id(&payload_hash) {
        return Err(ManifestError::Transport(
            "observation payload_hash must be lowercase 64-hex".to_string(),
        ));
    }
    Ok(ObservedEvidence {
        observation_id,
        extractor_id: string_field(object, "extractor_id")?,
        extractor_version: string_field(object, "extractor_version")?,
        capability_id: string_field(object, "capability_id")?,
        relation_kind: string_field(object, "relation_kind")?,
        from_locator: string_field(object, "from_locator")?,
        to_locator: string_field(object, "to_locator")?,
        from_identity_id: string_field(object, "from_identity_id")?,
        to_identity_id: string_field(object, "to_identity_id")?,
        source_span: parse_source_span(object.get("source_span").ok_or_else(|| {
            ManifestError::Transport("observation source_span missing".to_string())
        })?)?,
        payload_hash,
        classification: string_field(object, "classification")?,
        accepted: bool_field(object, "accepted")?,
        snapshot_id: string_field(object, "snapshot_id")?,
    })
}

fn parse_extractor_capability(
    record_id: &str,
    value: &Value,
) -> Result<ExtractorCapability, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("extractor capability payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "capability_id",
            "extractor_id",
            "extractor_version",
            "relation_kinds",
            "input_scope",
            "supported_file_kinds",
            "unsupported_behavior",
            "dynamic_behavior",
            "provenance_fields",
            "completeness_claim",
        ],
    )?;
    let capability_id = string_field(object, "capability_id")?;
    if capability_id != record_id {
        return Err(ManifestError::Transport(
            "extractor capability record_id mismatch".to_string(),
        ));
    }
    Ok(ExtractorCapability {
        capability_id,
        extractor_id: string_field(object, "extractor_id")?,
        extractor_version: string_field(object, "extractor_version")?,
        relation_kinds: string_array_field(object, "relation_kinds")?,
        input_scope: string_field(object, "input_scope")?,
        supported_file_kinds: string_array_field(object, "supported_file_kinds")?,
        unsupported_behavior: string_field(object, "unsupported_behavior")?,
        dynamic_behavior: string_field(object, "dynamic_behavior")?,
        provenance_fields: string_array_field(object, "provenance_fields")?,
        completeness_claim: string_field(object, "completeness_claim")?,
    })
}

fn source_snapshot_payload(header: &SnapshotHeader) -> Value {
    json!({
        "snapshot_id": header.snapshot_id,
        "parent_repo_id": header.parent_repo_id,
        "root_realpath": header.root_realpath,
        "git_head": header.git_head,
        "git_index_tree": header.git_index_tree,
        "git_worktree_dirty": header.git_worktree_dirty,
        "git_status_hash": header.git_status_hash,
        "dirty_paths": header.dirty_paths,
        "agentcanon_pin": header.agentcanon_pin,
        "schema_version": header.schema_version,
        "tool_version": header.tool_version,
        "path_sort": header.path_sort,
        "captured_before_hash": header.captured_before_hash,
        "captured_after_hash": header.captured_after_hash,
        "snapshot_consistent": header.snapshot_consistent,
    })
}

fn normalized_header_payload(header: &SnapshotHeader) -> Value {
    json!({
        "schema_version": NORMALIZED_RECORD_SET_VERSION,
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "relation_schema_version": "relation.v1",
        "snapshot_id": header.snapshot_id,
        "source_fingerprint": header.source_fingerprint,
        "tool_version": header.tool_version,
        "profile": header.profile,
    })
}

fn normalized_record_values(records: &NormalizedRecordSet) -> Vec<(String, String, Value)> {
    let mut values = Vec::new();
    values.push((
        SNAPSHOT_SCHEMA_VERSION.to_string(),
        records.header.snapshot_id.clone(),
        source_snapshot_payload(&records.header),
    ));
    for identity in &records.source_identities {
        values.push((
            "source_identity.v1".to_string(),
            identity.identity_id.clone(),
            json!({
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
            }),
        ));
    }
    for declaration in &records.declarations {
        values.push((
            "dependency_declaration.v1".to_string(),
            declaration.declaration_id.clone(),
            declaration_payload(declaration),
        ));
    }
    for attestation in &records.attestations {
        values.push((
            "attestation.v1".to_string(),
            attestation.attestation_id.clone(),
            attestation_payload(attestation),
        ));
    }
    for relation in &records.relations {
        values.push((
            "normalized_relation.v1".to_string(),
            relation.fact_id.clone(),
            normalized_relation_payload(relation),
        ));
    }
    for observation in &records.observations {
        values.push((
            "observed_evidence.v1".to_string(),
            observation.observation_id.clone(),
            observed_evidence_payload(observation),
        ));
    }
    for relation in &records.surface_relations {
        values.push((
            "surface_relation.v1".to_string(),
            relation.relation_id.clone(),
            surface_relation_payload(relation),
        ));
    }
    for exclusion in &records.source_exclusions {
        values.push((
            "source_exclusion.v1".to_string(),
            exclusion.source_exclusion_id.clone(),
            source_exclusion_payload(exclusion),
        ));
    }
    for ambiguity in &records.ambiguities {
        values.push((
            "ambiguity_a.v1".to_string(),
            ambiguity.ambiguity_id.clone(),
            ambiguity_payload(ambiguity),
        ));
    }
    for capability in &records.capabilities {
        values.push((
            "extractor_capability.v1".to_string(),
            capability.capability_id.clone(),
            capability_payload(capability),
        ));
    }
    values.sort_by(|left, right| {
        normalized_record_family_rank(&left.0)
            .cmp(&normalized_record_family_rank(&right.0))
            .then_with(|| left.1.cmp(&right.1))
    });
    values
}

fn normalized_record_family_rank(record_type: &str) -> usize {
    match record_type {
        SNAPSHOT_SCHEMA_VERSION => 1,
        "source_identity.v1" => 2,
        "dependency_declaration.v1" => 3,
        "attestation.v1" => 4,
        "normalized_relation.v1" => 5,
        "observed_evidence.v1" => 6,
        "surface_relation.v1" => 7,
        "source_exclusion.v1" => 8,
        "ambiguity_a.v1" => 9,
        "extractor_capability.v1" => 10,
        other => panic!("unknown normalized record family {other}"),
    }
}

fn validate_normalized_record_order(
    values: &[(String, String, Value)],
) -> Result<(), ManifestError> {
    if values.first().map(|value| value.0.as_str()) != Some(SNAPSHOT_SCHEMA_VERSION) {
        return Err(ManifestError::Transport(
            "normalized body must begin with source snapshot".to_string(),
        ));
    }
    for pair in values.windows(2) {
        let previous_rank = normalized_record_family_rank(&pair[0].0);
        let current_rank = normalized_record_family_rank(&pair[1].0);
        if previous_rank > current_rank || (previous_rank == current_rank && pair[0].1 >= pair[1].1)
        {
            return Err(ManifestError::Transport(
                "normalized records are not in canonical family and record-ID order".to_string(),
            ));
        }
    }
    Ok(())
}

fn normalized_record_fingerprint(records: &NormalizedRecordSet) -> Result<String, ManifestError> {
    let mut bytes = Vec::new();
    for (record_type, record_id, payload) in normalized_record_values(records) {
        serde_json::to_writer(
            &mut bytes,
            &json!({"record_type": record_type, "record_id": record_id, "payload": payload}),
        )
        .map_err(|error| ManifestError::Transport(error.to_string()))?;
        bytes.push(0);
    }
    Ok(sha256_bytes(&bytes))
}

pub(crate) fn write_normalized_record_set(
    records: &NormalizedRecordSet,
    registry: &RelationRegistryArtifactV1,
    writer: impl Write,
) -> Result<(), TransportError> {
    validate_normalized_record_set(records, registry)?;
    let mut writer = writer;
    write_envelope(
        &mut writer,
        "normalized_record_set_header.v1",
        &records.header.snapshot_id,
        &records.header.snapshot_id,
        normalized_header_payload(&records.header),
    )?;
    let values = normalized_record_values(records);
    validate_normalized_record_order(&values)?;
    for (record_type, record_id, payload) in values {
        write_envelope(
            &mut writer,
            &record_type,
            &record_id,
            &records.header.snapshot_id,
            payload,
        )?;
    }
    let summary_payload = json!({
        "snapshot_id": records.summary.snapshot_id,
        "record_counts": records.summary.record_counts,
        "accepted_fact_count": records.summary.accepted_fact_count,
        "rejected_declaration_count": records.summary.rejected_declaration_count,
        "rejected_observation_count": records.summary.rejected_observation_count,
        "ambiguity_count": records.summary.ambiguity_count,
        "source_exclusion_count": records.summary.source_exclusion_count,
        "normalized_record_fingerprint": records.summary.normalized_record_fingerprint,
    });
    write_envelope(
        &mut writer,
        "normalization_summary.v1",
        &records.summary.snapshot_id,
        &records.header.snapshot_id,
        summary_payload,
    )
}

fn declaration_payload(declaration: &DependencyDeclaration) -> Value {
    json!({
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
    })
}

fn attestation_payload(attestation: &Attestation) -> Value {
    json!({
        "attestation_id": attestation.attestation_id,
        "attestation_key": attestation.attestation_key,
        "evidence_type": attestation.evidence_type,
        "evidence_id": attestation.evidence_id,
        "declaring_identity_id": attestation.declaring_identity_id,
        "dependent_identity_id": attestation.dependent_identity_id,
        "prerequisite_identity_id": attestation.prerequisite_identity_id,
        "declared_direction": attestation.declared_direction,
        "relation_kind": attestation.relation_kind,
        "source_span": source_span_json(&attestation.source_span),
        "reason": attestation.reason,
        "raw_line_hash": attestation.raw_line_hash,
        "accepted": attestation.accepted,
        "rejection_reason": attestation.rejection_reason,
        "snapshot_id": attestation.snapshot_id,
    })
}

fn normalized_relation_payload(relation: &NormalizedRelation) -> Value {
    json!({
        "fact_id": relation.fact_id,
        "from_identity_id": relation.from_identity_id,
        "to_identity_id": relation.to_identity_id,
        "relation_kind": relation.relation_kind,
        "semantic_direction": relation.semantic_direction,
        "pair_identity": relation.pair_identity,
        "attestation_ids": relation.attestation_ids,
        "observation_ids": relation.observation_ids,
        "authority": relation.authority,
        "accepted": relation.accepted,
        "reconciliation_status": relation.reconciliation_status,
        "source_snapshot_id": relation.source_snapshot_id,
        "source_content_hashes": relation.source_content_hashes,
    })
}

fn observed_evidence_payload(observation: &ObservedEvidence) -> Value {
    json!({
        "observation_id": observation.observation_id,
        "extractor_id": observation.extractor_id,
        "extractor_version": observation.extractor_version,
        "capability_id": observation.capability_id,
        "relation_kind": observation.relation_kind,
        "from_locator": observation.from_locator,
        "to_locator": observation.to_locator,
        "from_identity_id": observation.from_identity_id,
        "to_identity_id": observation.to_identity_id,
        "source_span": source_span_json(&observation.source_span),
        "payload_hash": observation.payload_hash,
        "classification": observation.classification,
        "accepted": observation.accepted,
        "snapshot_id": observation.snapshot_id,
    })
}

fn surface_relation_payload(relation: &SurfaceRelation) -> Value {
    json!({
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
    })
}

fn source_exclusion_payload(exclusion: &SourceExclusion) -> Value {
    json!({
        "source_exclusion_id": exclusion.source_exclusion_id,
        "source_identity_id": exclusion.source_identity_id,
        "repo_rel_path": exclusion.repo_rel_path,
        "reason_code": exclusion.reason_code,
        "rule_id": exclusion.rule_id,
        "scope": exclusion.scope,
        "evidence_id": exclusion.evidence_id,
        "covered": exclusion.covered,
        "snapshot_id": exclusion.snapshot_id,
    })
}

fn ambiguity_payload(ambiguity: &AmbiguityA) -> Value {
    json!({
        "ambiguity_id": ambiguity.ambiguity_id,
        "source_identity_id": ambiguity.source_identity_id,
        "candidate_fact_ids": ambiguity.candidate_fact_ids,
        "candidate_targets": ambiguity.candidate_targets,
        "relation_kind": ambiguity.relation_kind,
        "reason_code": ambiguity.reason_code,
        "evidence_ids": ambiguity.evidence_ids,
        "resolution_required": ambiguity.resolution_required,
        "covered": ambiguity.covered,
        "snapshot_id": ambiguity.snapshot_id,
    })
}

fn capability_payload(capability: &ExtractorCapability) -> Value {
    json!({
        "capability_id": capability.capability_id,
        "extractor_id": capability.extractor_id,
        "extractor_version": capability.extractor_version,
        "relation_kinds": capability.relation_kinds,
        "input_scope": capability.input_scope,
        "supported_file_kinds": capability.supported_file_kinds,
        "unsupported_behavior": capability.unsupported_behavior,
        "dynamic_behavior": capability.dynamic_behavior,
        "provenance_fields": capability.provenance_fields,
        "completeness_claim": capability.completeness_claim,
    })
}

fn parse_attestation(record_id: &str, value: &Value) -> Result<Attestation, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("attestation payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "attestation_id",
            "attestation_key",
            "evidence_type",
            "evidence_id",
            "declaring_identity_id",
            "dependent_identity_id",
            "prerequisite_identity_id",
            "declared_direction",
            "relation_kind",
            "source_span",
            "reason",
            "raw_line_hash",
            "accepted",
            "rejection_reason",
            "snapshot_id",
        ],
    )?;
    let attestation_id = string_field(object, "attestation_id")?;
    if attestation_id != record_id {
        return Err(ManifestError::Transport(
            "attestation record_id mismatch".to_string(),
        ));
    }
    Ok(Attestation {
        attestation_id,
        attestation_key: string_field(object, "attestation_key")?,
        evidence_type: string_field(object, "evidence_type")?,
        evidence_id: string_field(object, "evidence_id")?,
        declaring_identity_id: string_field(object, "declaring_identity_id")?,
        dependent_identity_id: string_field(object, "dependent_identity_id")?,
        prerequisite_identity_id: string_field(object, "prerequisite_identity_id")?,
        declared_direction: string_field(object, "declared_direction")?,
        relation_kind: string_field(object, "relation_kind")?,
        source_span: parse_source_span(object.get("source_span").ok_or_else(|| {
            ManifestError::Transport("attestation source_span missing".to_string())
        })?)?,
        reason: string_field(object, "reason")?,
        raw_line_hash: string_field(object, "raw_line_hash")?,
        accepted: bool_field(object, "accepted")?,
        rejection_reason: string_field(object, "rejection_reason")?,
        snapshot_id: string_field(object, "snapshot_id")?,
    })
}

fn parse_normalized_relation(
    record_id: &str,
    value: &Value,
) -> Result<NormalizedRelation, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("normalized relation payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "fact_id",
            "from_identity_id",
            "to_identity_id",
            "relation_kind",
            "semantic_direction",
            "pair_identity",
            "attestation_ids",
            "observation_ids",
            "authority",
            "accepted",
            "reconciliation_status",
            "source_snapshot_id",
            "source_content_hashes",
        ],
    )?;
    let fact_id = string_field(object, "fact_id")?;
    if fact_id != record_id {
        return Err(ManifestError::Transport(
            "normalized relation record_id mismatch".to_string(),
        ));
    }
    Ok(NormalizedRelation {
        fact_id,
        from_identity_id: string_field(object, "from_identity_id")?,
        to_identity_id: string_field(object, "to_identity_id")?,
        relation_kind: string_field(object, "relation_kind")?,
        semantic_direction: string_field(object, "semantic_direction")?,
        pair_identity: string_field(object, "pair_identity")?,
        attestation_ids: string_array_field(object, "attestation_ids")?,
        observation_ids: string_array_field(object, "observation_ids")?,
        authority: string_field(object, "authority")?,
        accepted: bool_field(object, "accepted")?,
        reconciliation_status: string_field(object, "reconciliation_status")?,
        source_snapshot_id: string_field(object, "source_snapshot_id")?,
        source_content_hashes: string_array_field(object, "source_content_hashes")?,
    })
}

fn parse_ambiguity(record_id: &str, value: &Value) -> Result<AmbiguityA, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("ambiguity payload must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "ambiguity_id",
            "source_identity_id",
            "candidate_fact_ids",
            "candidate_targets",
            "relation_kind",
            "reason_code",
            "evidence_ids",
            "resolution_required",
            "covered",
            "snapshot_id",
        ],
    )?;
    let ambiguity_id = string_field(object, "ambiguity_id")?;
    if ambiguity_id != record_id {
        return Err(ManifestError::Transport(
            "ambiguity record_id mismatch".to_string(),
        ));
    }
    Ok(AmbiguityA {
        ambiguity_id,
        source_identity_id: string_field(object, "source_identity_id")?,
        candidate_fact_ids: string_array_field(object, "candidate_fact_ids")?,
        candidate_targets: string_array_field(object, "candidate_targets")?,
        relation_kind: string_field(object, "relation_kind")?,
        reason_code: string_field(object, "reason_code")?,
        evidence_ids: string_array_field(object, "evidence_ids")?,
        resolution_required: bool_field(object, "resolution_required")?,
        covered: bool_field(object, "covered")?,
        snapshot_id: string_field(object, "snapshot_id")?,
    })
}

fn parse_normalized_header(
    record_id: &str,
    value: &Value,
) -> Result<
    (
        String,
        String,
        String,
        String,
        String,
        String,
        String,
        String,
    ),
    ManifestError,
> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("normalized record-set header must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "schema_version",
            "snapshot_schema_version",
            "manifest_schema_version",
            "relation_schema_version",
            "snapshot_id",
            "source_fingerprint",
            "tool_version",
            "profile",
        ],
    )?;
    let schema_version = string_field(object, "schema_version")?;
    let snapshot_schema_version = string_field(object, "snapshot_schema_version")?;
    let manifest_schema_version = string_field(object, "manifest_schema_version")?;
    let relation_schema_version = string_field(object, "relation_schema_version")?;
    let snapshot_id = string_field(object, "snapshot_id")?;
    if record_id != snapshot_id {
        return Err(ManifestError::Transport(
            "normalized header record_id mismatch".to_string(),
        ));
    }
    Ok((
        schema_version,
        snapshot_schema_version,
        manifest_schema_version,
        relation_schema_version,
        snapshot_id,
        string_field(object, "source_fingerprint")?,
        string_field(object, "tool_version")?,
        string_field(object, "profile")?,
    ))
}

fn parse_normalized_source_snapshot(
    value: &Value,
    source_fingerprint: &str,
    tool_version: &str,
    profile: &str,
) -> Result<SnapshotHeader, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("normalized source snapshot payload must be an object".to_string())
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
            "path_sort",
            "captured_before_hash",
            "captured_after_hash",
            "snapshot_consistent",
        ],
    )?;
    let payload_schema = string_field(object, "schema_version")?;
    let payload_tool = string_field(object, "tool_version")?;
    if payload_schema != SNAPSHOT_SCHEMA_VERSION || payload_tool != tool_version {
        return Err(ManifestError::Transport(
            "normalized source snapshot schema/tool mismatch".to_string(),
        ));
    }
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
        schema_version: payload_schema,
        tool_version: payload_tool,
        profile: profile.to_string(),
        path_sort: string_field(object, "path_sort")?,
        source_fingerprint: source_fingerprint.to_string(),
        captured_before_hash: string_field(object, "captured_before_hash")?,
        captured_after_hash: string_field(object, "captured_after_hash")?,
        snapshot_consistent: bool_field(object, "snapshot_consistent")?,
    })
}

fn parse_normalization_summary(
    record_id: &str,
    value: &Value,
) -> Result<NormalizationSummary, ManifestError> {
    let object = value.as_object().ok_or_else(|| {
        ManifestError::Transport("normalization summary must be an object".to_string())
    })?;
    ensure_exact_keys(
        object,
        &[
            "snapshot_id",
            "record_counts",
            "accepted_fact_count",
            "rejected_declaration_count",
            "rejected_observation_count",
            "ambiguity_count",
            "source_exclusion_count",
            "normalized_record_fingerprint",
        ],
    )?;
    let snapshot_id = string_field(object, "snapshot_id")?;
    if record_id != snapshot_id {
        return Err(ManifestError::Transport(
            "normalization summary record_id mismatch".to_string(),
        ));
    }
    let counts_object = object
        .get("record_counts")
        .and_then(Value::as_object)
        .ok_or_else(|| ManifestError::Transport("record_counts must be an object".to_string()))?;
    let mut record_counts = BTreeMap::new();
    for (key, value) in counts_object {
        let count = value
            .as_u64()
            .and_then(|value| usize::try_from(value).ok())
            .ok_or_else(|| {
                ManifestError::Transport(format!(
                    "record_counts.{key} must be a non-negative integer"
                ))
            })?;
        record_counts.insert(key.clone(), count);
    }
    Ok(NormalizationSummary {
        snapshot_id,
        record_counts,
        accepted_fact_count: usize_field(object, "accepted_fact_count")?,
        rejected_declaration_count: usize_field(object, "rejected_declaration_count")?,
        rejected_observation_count: usize_field(object, "rejected_observation_count")?,
        ambiguity_count: usize_field(object, "ambiguity_count")?,
        source_exclusion_count: usize_field(object, "source_exclusion_count")?,
        normalized_record_fingerprint: string_field(object, "normalized_record_fingerprint")?,
    })
}

pub(crate) fn read_normalized_record_set(
    reader: impl BufRead,
    expected_snapshot_id: &str,
    registry: &RelationRegistryArtifactV1,
) -> Result<NormalizedRecordSet, TransportError> {
    if !is_hex_id(expected_snapshot_id) {
        return Err(ManifestError::Transport(
            "expected snapshot ID must be lowercase 64-hex".to_string(),
        ));
    }
    let values = read_canonical_jsonl(reader, "normalized")?;
    if values.len() < 3 {
        return Err(ManifestError::Transport(
            "normalized record set requires header, snapshot, and summary".to_string(),
        ));
    }
    let header_value = &values[0];
    let header_envelope = parse_envelope(header_value, "normalized_record_set_header.v1", true)?;
    let (
        schema_version,
        snapshot_schema_version,
        manifest_schema_version,
        relation_schema_version,
        snapshot_id,
        source_fingerprint,
        tool_version,
        profile,
    ) = parse_normalized_header(header_envelope.record_id, header_envelope.payload)?;
    if schema_version != NORMALIZED_RECORD_SET_VERSION
        || snapshot_schema_version != SNAPSHOT_SCHEMA_VERSION
        || manifest_schema_version != MANIFEST_SCHEMA_VERSION
        || relation_schema_version != "relation.v1"
        || snapshot_id != expected_snapshot_id
        || header_envelope.snapshot_id != expected_snapshot_id
    {
        return Err(ManifestError::Transport(
            "normalized record-set schema or snapshot mismatch".to_string(),
        ));
    }
    let mut header = None;
    let mut source_identities = Vec::new();
    let mut declarations = Vec::new();
    let mut attestations = Vec::new();
    let mut relations = Vec::new();
    let mut observations = Vec::new();
    let mut surface_relations = Vec::new();
    let mut source_exclusions = Vec::new();
    let mut ambiguities = Vec::new();
    let mut capabilities = Vec::new();
    let mut summary = None;
    let mut last_rank = 0usize;
    let mut last_record_id = None::<String>;
    for (index, value) in values.iter().enumerate().skip(1) {
        let record_type = value
            .get("record_type")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                ManifestError::Transport("normalized record_type is required".to_string())
            })?;
        let envelope = parse_envelope(value, record_type, false)?;
        if envelope.snapshot_id != expected_snapshot_id {
            return Err(ManifestError::Transport(
                "mixed normalized snapshot IDs".to_string(),
            ));
        }
        let rank = match record_type {
            SNAPSHOT_SCHEMA_VERSION
            | "source_identity.v1"
            | "dependency_declaration.v1"
            | "attestation.v1"
            | "normalized_relation.v1"
            | "observed_evidence.v1"
            | "surface_relation.v1"
            | "source_exclusion.v1"
            | "ambiguity_a.v1"
            | "extractor_capability.v1" => normalized_record_family_rank(record_type),
            "normalization_summary.v1" => 11,
            _ => {
                return Err(ManifestError::Transport(format!(
                    "unknown normalized record type {record_type}"
                )))
            }
        };
        if rank < last_rank || (rank == 11 && index + 1 != values.len()) {
            return Err(ManifestError::Transport(
                "normalized record families are not in canonical order".to_string(),
            ));
        }
        if rank == last_rank
            && last_record_id
                .as_deref()
                .is_some_and(|previous| previous >= envelope.record_id)
        {
            return Err(ManifestError::Transport(
                "normalized record IDs are not strictly increasing within a family".to_string(),
            ));
        }
        last_rank = rank;
        last_record_id = Some(envelope.record_id.to_string());
        match record_type {
            SNAPSHOT_SCHEMA_VERSION => {
                if header.is_some() {
                    return Err(ManifestError::Transport(
                        "duplicate normalized source snapshot".to_string(),
                    ));
                }
                let parsed = parse_normalized_source_snapshot(
                    envelope.payload,
                    &source_fingerprint,
                    &tool_version,
                    &profile,
                )?;
                if parsed.snapshot_id != expected_snapshot_id {
                    return Err(ManifestError::Transport(
                        "normalized source snapshot mismatch".to_string(),
                    ));
                }
                header = Some(parsed);
            }
            "source_identity.v1" => {
                source_identities.push(parse_source_identity(envelope.record_id, envelope.payload)?)
            }
            "dependency_declaration.v1" => {
                declarations.push(parse_declaration(envelope.record_id, envelope.payload)?)
            }
            "attestation.v1" => {
                attestations.push(parse_attestation(envelope.record_id, envelope.payload)?)
            }
            "normalized_relation.v1" => relations.push(parse_normalized_relation(
                envelope.record_id,
                envelope.payload,
            )?),
            "observed_evidence.v1" => observations.push(parse_observed_evidence(
                envelope.record_id,
                envelope.payload,
            )?),
            "surface_relation.v1" => surface_relations.push(parse_surface_relation(
                envelope.record_id,
                envelope.payload,
            )?),
            "source_exclusion.v1" => source_exclusions.push(parse_source_exclusion(
                envelope.record_id,
                envelope.payload,
            )?),
            "ambiguity_a.v1" => {
                ambiguities.push(parse_ambiguity(envelope.record_id, envelope.payload)?)
            }
            "extractor_capability.v1" => capabilities.push(parse_extractor_capability(
                envelope.record_id,
                envelope.payload,
            )?),
            "normalization_summary.v1" => {
                if summary.is_some() {
                    return Err(ManifestError::Transport(
                        "duplicate normalization summary".to_string(),
                    ));
                }
                summary = Some(parse_normalization_summary(
                    envelope.record_id,
                    envelope.payload,
                )?);
            }
            _ => unreachable!(),
        }
    }
    let header = header.ok_or_else(|| {
        ManifestError::Transport("missing normalized source snapshot".to_string())
    })?;
    let summary = summary
        .ok_or_else(|| ManifestError::Transport("missing normalization summary".to_string()))?;
    if header.source_fingerprint != source_fingerprint
        || header.tool_version != tool_version
        || header.profile != profile
    {
        return Err(ManifestError::Transport(
            "normalized header/source metadata mismatch".to_string(),
        ));
    }
    ensure_unique_record_ids(
        "normalized source identity",
        source_identities
            .iter()
            .map(|item| item.identity_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "normalized declaration",
        declarations.iter().map(|item| item.declaration_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "normalized attestation",
        attestations.iter().map(|item| item.attestation_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "normalized relation",
        relations.iter().map(|item| item.fact_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "normalized observation",
        observations.iter().map(|item| item.observation_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "normalized surface relation",
        surface_relations
            .iter()
            .map(|item| item.relation_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "normalized exclusion",
        source_exclusions
            .iter()
            .map(|item| item.source_exclusion_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "normalized ambiguity",
        ambiguities.iter().map(|item| item.ambiguity_id.as_str()),
    )?;
    ensure_unique_record_ids(
        "normalized capability",
        capabilities.iter().map(|item| item.capability_id.as_str()),
    )?;
    validate_snapshot_transport(
        &header,
        &mut source_identities,
        &declarations,
        &source_exclusions,
        &surface_relations,
    )?;
    let source_universe = materialize_source_universe(
        &source_identities
            .iter()
            .map(|identity| identity.repo_rel_path.clone())
            .collect::<Vec<_>>(),
        &source_identities,
        &source_exclusions,
    )?;
    let records = NormalizedRecordSet {
        header,
        source_identities,
        declarations,
        attestations,
        relations,
        observations,
        surface_relations,
        source_exclusions,
        ambiguities,
        capabilities,
        source_universe,
        summary,
    };
    validate_normalized_record_order(&normalized_record_values(&records))?;
    validate_normalized_record_set(&records, registry)?;
    Ok(records)
}

fn validate_normalized_record_set(
    records: &NormalizedRecordSet,
    registry: &RelationRegistryArtifactV1,
) -> Result<(), ManifestError> {
    if records.header.schema_version != SNAPSHOT_SCHEMA_VERSION
        || records.header.profile != "parent"
        || !records.header.snapshot_consistent
        || !is_hex_id(&records.header.snapshot_id)
    {
        return Err(ManifestError::Transport(
            "normalized source snapshot is invalid".to_string(),
        ));
    }
    let mut identities = records.source_identities.clone();
    validate_snapshot_transport(
        &records.header,
        &mut identities,
        &records.declarations,
        &records.source_exclusions,
        &records.surface_relations,
    )?;
    if identities.len() != records.source_identities.len() {
        return Err(ManifestError::Transport(
            "normalized identity count changed during validation".to_string(),
        ));
    }
    let expected_candidate_paths = records
        .source_identities
        .iter()
        .map(|identity| identity.repo_rel_path.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    if records.source_universe.candidate_paths != expected_candidate_paths {
        return Err(ManifestError::Transport(
            "normalized source universe does not represent identities".to_string(),
        ));
    }
    if !records
        .source_universe
        .eligible_equals_candidate_minus_excluded
        || !records.source_universe.union_equals_candidate
        || !records.source_universe.intersection_empty
    {
        return Err(ManifestError::Transport(
            "normalized source algebra failed".to_string(),
        ));
    }
    if records.source_exclusions.iter().any(|exclusion| {
        exclusion.snapshot_id != records.header.snapshot_id
            || exclusion.source_exclusion_id.is_empty()
            || exclusion.source_identity_id.is_empty()
            || exclusion.repo_rel_path.is_empty()
            || exclusion.reason_code.is_empty()
            || exclusion.rule_id.is_empty()
            || exclusion.scope.is_empty()
            || exclusion.evidence_id.is_empty()
            || exclusion.covered
    }) {
        return Err(ManifestError::Transport(
            "source-exclusion provenance is incomplete or covered".to_string(),
        ));
    }
    let identities_by_id = records
        .source_identities
        .iter()
        .map(|identity| (identity.identity_id.as_str(), identity))
        .collect::<BTreeMap<_, _>>();
    let logical_by_id = identities_by_id
        .iter()
        .map(|(identity_id, identity)| (*identity_id, identity.logical_id.as_str()))
        .collect::<BTreeMap<_, _>>();
    let excluded_identity_ids = records
        .source_exclusions
        .iter()
        .map(|exclusion| exclusion.source_identity_id.as_str())
        .collect::<BTreeSet<_>>();
    let declarations_by_id = records
        .declarations
        .iter()
        .map(|declaration| (declaration.declaration_id.as_str(), declaration))
        .collect::<BTreeMap<_, _>>();
    let observations_by_id = records
        .observations
        .iter()
        .map(|observation| (observation.observation_id.as_str(), observation))
        .collect::<BTreeMap<_, _>>();
    let capabilities_by_id = records
        .capabilities
        .iter()
        .map(|capability| (capability.capability_id.as_str(), capability))
        .collect::<BTreeMap<_, _>>();
    let registered_capability_ids = producer_capability_rows(registry)
        .into_iter()
        .map(|(capability_id, _, _)| capability_id)
        .collect::<BTreeSet<_>>();
    if records.capabilities.len() != capabilities_by_id.len()
        || registered_capability_ids
            .iter()
            .any(|capability_id| !capabilities_by_id.contains_key(capability_id.as_str()))
    {
        return Err(ManifestError::Transport(
            "registered capability transport is incomplete or duplicated".to_string(),
        ));
    }
    if records.observations.is_empty() {
        for capability_id in &registered_capability_ids {
            let capability = capabilities_by_id
                .get(capability_id.as_str())
                .expect("registered capability presence checked");
            if !capability.completeness_claim.contains("O=empty")
                || !capability.completeness_claim.contains("coverage=0")
                || (!capability.input_scope.contains("unavailable")
                    && !capability.completeness_claim.contains("provided-empty"))
            {
                return Err(ManifestError::Transport(
                    "empty observation set requires unavailable/provided-empty capability status"
                        .to_string(),
                ));
            }
        }
    }
    let mut attestation_by_id = BTreeMap::new();
    let mut attestation_by_evidence = BTreeMap::new();
    for attestation in &records.attestations {
        if attestation.snapshot_id != records.header.snapshot_id
            || attestation.attestation_key.is_empty()
            || attestation.evidence_id.is_empty()
            || attestation.declaring_identity_id.is_empty()
            || attestation.declared_direction.is_empty()
            || attestation.relation_kind.is_empty()
            || attestation.source_span.path.is_empty()
            || attestation.reason.is_empty()
            || !is_hex_id(&attestation.attestation_key)
            || !is_hex_id(&attestation.raw_line_hash)
            || !matches!(
                attestation.evidence_type.as_str(),
                "declaration" | "observation"
            )
            || attestation.accepted == !attestation.rejection_reason.is_empty()
        {
            return Err(ManifestError::Transport(
                "attestation provenance or rejection partition is invalid".to_string(),
            ));
        }
        let expected_id = hash_parts(&["attestation.v1", &attestation.attestation_key]);
        if expected_id != attestation.attestation_id {
            return Err(ManifestError::Transport(format!(
                "attestation ID mismatch for {}",
                attestation.evidence_id
            )));
        }
        if attestation_by_id
            .insert(attestation.attestation_id.as_str(), attestation)
            .is_some()
        {
            return Err(ManifestError::Transport(
                "duplicate attestation ID".to_string(),
            ));
        }
        if attestation_by_evidence
            .insert(
                (
                    attestation.evidence_type.as_str(),
                    attestation.evidence_id.as_str(),
                ),
                attestation,
            )
            .is_some()
        {
            return Err(ManifestError::Transport(
                "duplicate attestation evidence provenance".to_string(),
            ));
        }
    }
    for capability in &records.capabilities {
        if capability.capability_id.is_empty()
            || capability.extractor_id.is_empty()
            || capability.extractor_version.is_empty()
            || capability.input_scope.is_empty()
            || capability.unsupported_behavior.is_empty()
            || capability.dynamic_behavior.is_empty()
            || capability.completeness_claim.is_empty()
            || capability.relation_kinds.is_empty()
            || capability.provenance_fields.iter().any(String::is_empty)
            || capability
                .relation_kinds
                .windows(2)
                .any(|window| window[0] >= window[1])
            || capability
                .provenance_fields
                .windows(2)
                .any(|window| window[0] >= window[1])
        {
            return Err(ManifestError::Transport(
                "extractor capability provenance is incomplete".to_string(),
            ));
        }
        let known = producer_capability_rows(registry)
            .into_iter()
            .find(|(capability_id, _, _)| capability_id == &capability.capability_id);
        if let Some((_, extractor_id, raw_kinds)) = known {
            if capability.extractor_id != extractor_id || capability.relation_kinds != raw_kinds {
                return Err(ManifestError::Transport(format!(
                    "registered capability {} disagrees with the relation registry",
                    capability.capability_id
                )));
            }
        } else if !capability.input_scope.contains("unavailable")
            || !capability.completeness_claim.contains("unavailable")
            || !records.ambiguities.iter().any(|ambiguity| {
                ambiguity.reason_code == "capability_unknown"
                    && ambiguity.evidence_ids.contains(&capability.capability_id)
            })
        {
            return Err(ManifestError::Transport(
                "unknown capability is not retained as typed unavailable/A".to_string(),
            ));
        }
    }
    for observation in &records.observations {
        if observation.snapshot_id != records.header.snapshot_id
            || observation.observation_id.is_empty()
            || observation.extractor_id.is_empty()
            || observation.extractor_version.is_empty()
            || observation.capability_id.is_empty()
            || observation.relation_kind.is_empty()
            || observation.from_locator.is_empty()
            || observation.to_locator.is_empty()
            || observation.from_identity_id.is_empty()
            || observation.to_identity_id.is_empty()
            || observation.source_span.path.is_empty()
            || observation.classification.is_empty()
            || !is_hex_id(&observation.payload_hash)
        {
            return Err(ManifestError::Transport(
                "observation provenance is incomplete".to_string(),
            ));
        }
        let registered_kind = RelationNormalizer::normalize_relation_kind(
            &registry,
            &observation.capability_id,
            &observation.relation_kind,
            &observation_discriminator(observation),
        );
        if !observation
            .observation_id
            .strip_prefix("O-")
            .is_some_and(is_hex_id)
        {
            return Err(ManifestError::Transport(
                "observation ID is invalid".to_string(),
            ));
        }
        let attestation = attestation_by_evidence
            .get(&("observation", observation.observation_id.as_str()))
            .ok_or_else(|| {
                ManifestError::Transport("observation attestation missing".to_string())
            })?;
        let (dependent, prerequisite, endpoint_rejection) =
            observed_endpoints(observation, &identities_by_id, &excluded_identity_ids);
        let contradiction = records.ambiguities.iter().any(|ambiguity| {
            ambiguity.reason_code == "kind_contradiction"
                && ambiguity.evidence_ids.contains(&observation.observation_id)
        });
        let expected_rejection = endpoint_rejection
            .or_else(|| contradiction.then(|| "kind_contradiction".to_string()))
            .or_else(|| {
                observation_producer_rejection_reason(
                    registry,
                    observation,
                    capabilities_by_id
                        .get(observation.capability_id.as_str())
                        .copied(),
                    registered_kind.as_ref().ok(),
                )
            });
        let expected_kind = registered_kind
            .as_ref()
            .map(|spec| spec.stored_kind.clone())
            .unwrap_or_else(|_| observation.relation_kind.clone());
        if attestation.attestation_key
            != hash_parts(&[
                "observed_attestation.v1",
                &observation.snapshot_id,
                &observation.observation_id,
                &observation.payload_hash,
            ])
            || attestation.declaring_identity_id != observation.from_identity_id
            || attestation.dependent_identity_id != dependent.unwrap_or_default()
            || attestation.prerequisite_identity_id != prerequisite.unwrap_or_default()
            || attestation.declared_direction != "observed"
            || attestation.relation_kind != expected_kind
            || attestation.source_span != observation.source_span
            || attestation.reason != observation.classification
            || attestation.raw_line_hash != observation.payload_hash
            || attestation.accepted != expected_rejection.is_none()
            || attestation.rejection_reason != expected_rejection.unwrap_or_default()
            || observation.accepted != attestation.accepted
        {
            return Err(ManifestError::Transport(
                "observation attestation consistency failed".to_string(),
            ));
        }
    }
    for ambiguity in &records.ambiguities {
        let expected_ambiguity_id = hash_parts(&[
            "ambiguity_a.v1",
            &ambiguity.snapshot_id,
            &ambiguity.source_identity_id,
            &ambiguity.reason_code,
            &ambiguity.relation_kind,
            &ambiguity.candidate_fact_ids.join(","),
            &ambiguity.candidate_targets.join(","),
            &ambiguity.evidence_ids.join(","),
        ]);
        if ambiguity.snapshot_id != records.header.snapshot_id
            || ambiguity.ambiguity_id != expected_ambiguity_id
            || ambiguity.covered
            || !ambiguity.resolution_required
            || ambiguity.reason_code.is_empty()
            || ambiguity.evidence_ids.is_empty()
            || ambiguity.evidence_ids.iter().any(String::is_empty)
            || ambiguity
                .candidate_fact_ids
                .iter()
                .any(|fact_id| !is_hex_id(fact_id))
            || ambiguity
                .candidate_fact_ids
                .windows(2)
                .any(|window| window[0] >= window[1])
            || ambiguity
                .candidate_targets
                .windows(2)
                .any(|window| window[0] >= window[1])
            || ambiguity
                .evidence_ids
                .windows(2)
                .any(|window| window[0] >= window[1])
        {
            return Err(ManifestError::Transport(
                "ambiguity provenance is stale, mixed, covered, or non-canonical".to_string(),
            ));
        }
        let contradiction = ambiguity.reason_code == "kind_contradiction";
        if !contradiction && ambiguity.evidence_ids.len() != 1 {
            return Err(ManifestError::Transport(
                "non-contradiction ambiguity must own exactly one evidence row".to_string(),
            ));
        }
        let mut expected_source_identity_id = String::new();
        let mut expected_relation_kind = if contradiction {
            "kind_contradiction".to_string()
        } else {
            String::new()
        };
        let mut expected_candidate_fact_ids = BTreeSet::new();
        let mut expected_candidate_targets = BTreeSet::new();
        let mut evidence_domain = None;
        for evidence_id in &ambiguity.evidence_ids {
            let declaration = declarations_by_id.get(evidence_id.as_str());
            let observation = observations_by_id.get(evidence_id.as_str());
            let capability = capabilities_by_id.get(evidence_id.as_str());
            let domain_count = declaration.is_some() as usize
                + observation.is_some() as usize
                + capability.is_some() as usize;
            if domain_count != 1 {
                return Err(ManifestError::Transport(
                    "ambiguity evidence is not a unique typed declaration, observation, or capability ID"
                        .to_string(),
                ));
            }
            if let Some(declaration) = declaration {
                let attestation = attestation_by_evidence
                    .get(&("declaration", declaration.declaration_id.as_str()))
                    .ok_or_else(|| {
                        ManifestError::Transport(
                            "declaration ambiguity evidence lacks an attestation".to_string(),
                        )
                    })?;
                if attestation.accepted || attestation.rejection_reason != ambiguity.reason_code {
                    return Err(ManifestError::Transport(
                        "ambiguity evidence must reference a rejected attestation with the exact reason"
                            .to_string(),
                    ));
                }
                if evidence_domain.is_some_and(|domain| {
                    domain == "capability" || (!contradiction && domain != "declaration")
                }) {
                    return Err(ManifestError::Transport(
                        "ambiguity evidence mixes typed declaration and non-declaration domains"
                            .to_string(),
                    ));
                }
                evidence_domain = Some("declaration");
                if contradiction {
                    if expected_source_identity_id.is_empty() {
                        expected_source_identity_id = attestation.dependent_identity_id.clone();
                    } else if expected_source_identity_id != attestation.dependent_identity_id {
                        return Err(ManifestError::Transport(
                            "contradiction ambiguity source closure is not exact".to_string(),
                        ));
                    }
                    for endpoint in [
                        &attestation.dependent_identity_id,
                        &attestation.prerequisite_identity_id,
                    ] {
                        if !endpoint.is_empty() {
                            expected_candidate_targets.insert(endpoint.clone());
                        }
                    }
                    if let (Some(dependent), Some(prerequisite)) = (
                        logical_by_id.get(attestation.dependent_identity_id.as_str()),
                        logical_by_id.get(attestation.prerequisite_identity_id.as_str()),
                    ) {
                        let pair_identity = hash_parts(&[
                            "relation_pair.v1",
                            &records.header.parent_repo_id,
                            dependent,
                            prerequisite,
                        ]);
                        expected_candidate_fact_ids.insert(hash_parts(&[
                            "normalized_relation.v1",
                            &pair_identity,
                            &attestation.relation_kind,
                        ]));
                    }
                } else {
                    expected_source_identity_id = declaration.source_identity_id.clone();
                    expected_candidate_targets.insert(declaration.declared_target.clone());
                    expected_relation_kind = attestation.relation_kind.clone();
                }
            }
            if let Some(observation) = observation {
                let attestation = attestation_by_evidence
                    .get(&("observation", observation.observation_id.as_str()))
                    .ok_or_else(|| {
                        ManifestError::Transport(
                            "observation ambiguity evidence lacks an attestation".to_string(),
                        )
                    })?;
                if attestation.accepted || attestation.rejection_reason != ambiguity.reason_code {
                    return Err(ManifestError::Transport(
                        "ambiguity evidence must reference a rejected attestation with the exact reason"
                            .to_string(),
                    ));
                }
                if evidence_domain.is_some_and(|domain| {
                    domain == "capability" || (!contradiction && domain != "observation")
                }) {
                    return Err(ManifestError::Transport(
                        "ambiguity evidence mixes typed observation and non-observation domains"
                            .to_string(),
                    ));
                }
                evidence_domain = Some("observation");
                if contradiction {
                    if expected_source_identity_id.is_empty() {
                        expected_source_identity_id = attestation.dependent_identity_id.clone();
                    } else if expected_source_identity_id != attestation.dependent_identity_id {
                        return Err(ManifestError::Transport(
                            "contradiction ambiguity source closure is not exact".to_string(),
                        ));
                    }
                    for endpoint in [
                        &attestation.dependent_identity_id,
                        &attestation.prerequisite_identity_id,
                    ] {
                        if !endpoint.is_empty() {
                            expected_candidate_targets.insert(endpoint.clone());
                        }
                    }
                    if let (Some(dependent), Some(prerequisite)) = (
                        logical_by_id.get(attestation.dependent_identity_id.as_str()),
                        logical_by_id.get(attestation.prerequisite_identity_id.as_str()),
                    ) {
                        let pair_identity = hash_parts(&[
                            "relation_pair.v1",
                            &records.header.parent_repo_id,
                            dependent,
                            prerequisite,
                        ]);
                        expected_candidate_fact_ids.insert(hash_parts(&[
                            "normalized_relation.v1",
                            &pair_identity,
                            &attestation.relation_kind,
                        ]));
                    }
                } else {
                    expected_source_identity_id = observation.from_identity_id.clone();
                    expected_candidate_targets.insert(observation.to_identity_id.clone());
                    expected_relation_kind = attestation.relation_kind.clone();
                }
            }
            if let Some(capability) = capability {
                if evidence_domain.is_some_and(|domain| domain != "capability") {
                    return Err(ManifestError::Transport(
                        "ambiguity evidence mixes typed capability and non-capability domains"
                            .to_string(),
                    ));
                }
                evidence_domain = Some("capability");
                if ambiguity.reason_code != "capability_unknown"
                    || !ambiguity.source_identity_id.is_empty()
                    || !ambiguity.candidate_fact_ids.is_empty()
                    || !ambiguity.candidate_targets.is_empty()
                    || capability.capability_id != *evidence_id
                    || registered_capability_ids.contains(capability.capability_id.as_str())
                {
                    return Err(ManifestError::Transport(
                        "capability ambiguity evidence is not an explicit capability diagnostic"
                            .to_string(),
                    ));
                }
            }
        }
        if ambiguity.source_identity_id != expected_source_identity_id
            || ambiguity.relation_kind != expected_relation_kind
            || ambiguity
                .candidate_fact_ids
                .iter()
                .cloned()
                .collect::<BTreeSet<_>>()
                != expected_candidate_fact_ids
            || ambiguity
                .candidate_targets
                .iter()
                .cloned()
                .collect::<BTreeSet<_>>()
                != expected_candidate_targets
        {
            return Err(ManifestError::Transport(
                "ambiguity reason/source/candidate/fact closure is not exact".to_string(),
            ));
        }
    }
    for attestation in &records.attestations {
        let matches = records
            .ambiguities
            .iter()
            .filter(|ambiguity| ambiguity.evidence_ids.contains(&attestation.evidence_id))
            .collect::<Vec<_>>();
        if attestation.accepted && !matches.is_empty() {
            return Err(ManifestError::Transport(
                "accepted evidence cannot have ambiguity provenance".to_string(),
            ));
        }
        if !attestation.accepted
            && (matches.len() != 1 || matches[0].reason_code != attestation.rejection_reason)
        {
            return Err(ManifestError::Transport(
                "rejected attestation must have exactly one matching ambiguity reason".to_string(),
            ));
        }
    }
    let relation_by_fact = records
        .relations
        .iter()
        .map(|relation| (relation.fact_id.as_str(), relation))
        .collect::<BTreeMap<_, _>>();
    let registered_stored_kinds = registry
        .entries
        .iter()
        .map(|spec| spec.stored_kind.as_str())
        .collect::<BTreeSet<_>>();
    let mut consumed_accepted_attestations = BTreeSet::new();
    for relation in &records.relations {
        if !relation.accepted
            || relation.semantic_direction != "depends_on"
            || relation.source_snapshot_id != records.header.snapshot_id
            || relation.attestation_ids.is_empty()
            || !registered_stored_kinds.contains(relation.relation_kind.as_str())
            || !matches!(
                relation.reconciliation_status.as_str(),
                "matched" | "declared_only" | "observed_only"
            )
        {
            return Err(ManifestError::Transport(
                "normalized direct fact contract failed".to_string(),
            ));
        }
        let dependent = identities_by_id
            .get(relation.from_identity_id.as_str())
            .ok_or_else(|| {
                ManifestError::Transport("relation dependent identity missing".to_string())
            })?;
        let prerequisite = identities_by_id
            .get(relation.to_identity_id.as_str())
            .ok_or_else(|| {
                ManifestError::Transport("relation prerequisite identity missing".to_string())
            })?;
        if excluded_identity_ids.contains(relation.from_identity_id.as_str())
            || excluded_identity_ids.contains(relation.to_identity_id.as_str())
            || !dependent.exists
            || !prerequisite.exists
        {
            return Err(ManifestError::Transport(
                "accepted relation endpoint is outside U".to_string(),
            ));
        }
        let expected_pair = hash_parts(&[
            "relation_pair.v1",
            &records.header.parent_repo_id,
            &dependent.logical_id,
            &prerequisite.logical_id,
        ]);
        let expected_fact = hash_parts(&[
            "normalized_relation.v1",
            &expected_pair,
            &relation.relation_kind,
        ]);
        if relation.pair_identity != expected_pair || relation.fact_id != expected_fact {
            return Err(ManifestError::Transport(format!(
                "normalized fact identity mismatch {}",
                relation.fact_id
            )));
        }
        if relation
            .attestation_ids
            .windows(2)
            .any(|window| window[0] >= window[1])
            || relation
                .observation_ids
                .windows(2)
                .any(|window| window[0] >= window[1])
        {
            return Err(ManifestError::Transport(
                "fact provenance is not sorted and unique".to_string(),
            ));
        }
        let mut expected_observation_ids = Vec::new();
        let mut has_declaration = false;
        let mut has_observation = false;
        for attestation_id in &relation.attestation_ids {
            let attestation = attestation_by_id
                .get(attestation_id.as_str())
                .ok_or_else(|| {
                    ManifestError::Transport("relation attestation provenance missing".to_string())
                })?;
            if !attestation.accepted {
                return Err(ManifestError::Transport(
                    "rejected attestation promoted to fact".to_string(),
                ));
            }
            if attestation.dependent_identity_id != relation.from_identity_id
                || attestation.prerequisite_identity_id != relation.to_identity_id
                || attestation.relation_kind != relation.relation_kind
                || attestation.snapshot_id != relation.source_snapshot_id
                || !consumed_accepted_attestations.insert(attestation.attestation_id.as_str())
            {
                return Err(ManifestError::Transport(
                    "fact attestation endpoint, kind, snapshot, or membership mismatch".to_string(),
                ));
            }
            match attestation.evidence_type.as_str() {
                "declaration" => has_declaration = true,
                "observation" => {
                    has_observation = true;
                    expected_observation_ids.push(attestation.evidence_id.clone());
                }
                _ => unreachable!("attestation evidence type validated"),
            }
        }
        expected_observation_ids.sort();
        if relation.observation_ids != expected_observation_ids {
            return Err(ManifestError::Transport(
                "fact observation provenance membership is incomplete".to_string(),
            ));
        }
        for observation_id in &expected_observation_ids {
            if !records
                .observations
                .iter()
                .any(|observation| observation.observation_id == *observation_id)
            {
                return Err(ManifestError::Transport(
                    "relation observation provenance missing".to_string(),
                ));
            }
        }
        let expected_status = match (has_declaration, has_observation) {
            (true, true) => "matched",
            (true, false) => "declared_only",
            (false, true) => "observed_only",
            (false, false) => unreachable!("nonempty attestation provenance"),
        };
        let expected_authority = match (has_declaration, has_observation) {
            (true, true) => "declaration+observation",
            (true, false) => "declaration",
            (false, true) => "observation",
            (false, false) => unreachable!("nonempty attestation provenance"),
        };
        let expected_hashes = vec![
            dependent.content_hash.clone(),
            prerequisite.content_hash.clone(),
        ];
        if relation.reconciliation_status != expected_status
            || relation.authority != expected_authority
            || relation.source_content_hashes != expected_hashes
            || !content_identity_is_canonical(dependent, &relation.source_content_hashes[0])
            || !content_identity_is_canonical(prerequisite, &relation.source_content_hashes[1])
        {
            return Err(ManifestError::Transport(
                "relation content provenance incomplete".to_string(),
            ));
        }
    }
    let accepted_attestation_ids = records
        .attestations
        .iter()
        .filter(|attestation| attestation.accepted)
        .map(|attestation| attestation.attestation_id.as_str())
        .collect::<BTreeSet<_>>();
    if consumed_accepted_attestations != accepted_attestation_ids {
        return Err(ManifestError::Transport(
            "accepted fact provenance membership is incomplete".to_string(),
        ));
    }
    let accepted_fact_ids = records
        .relations
        .iter()
        .map(|relation| relation.fact_id.as_str())
        .collect::<BTreeSet<_>>();
    if records.ambiguities.iter().any(|ambiguity| {
        ambiguity
            .candidate_fact_ids
            .iter()
            .any(|candidate| accepted_fact_ids.contains(candidate.as_str()))
    }) {
        return Err(ManifestError::Transport(
            "accepted facts overlap ambiguity candidates".to_string(),
        ));
    }
    for declaration in &records.declarations {
        let attestation = attestation_by_evidence
            .get(&("declaration", declaration.declaration_id.as_str()))
            .ok_or_else(|| {
                ManifestError::Transport("declaration attestation missing".to_string())
            })?;
        if declaration.snapshot_id != records.header.snapshot_id
            || declaration.declaration_id.is_empty()
            || declaration.source_identity_id.is_empty()
            || declaration.declared_direction.is_empty()
            || declaration.declared_kind.is_empty()
            || declaration.declared_target.is_empty()
            || declaration.source_span.path.is_empty()
            || declaration.reason.is_empty()
            || declaration.attestation_key.is_empty()
            || !is_hex_id(&declaration.raw_line_hash)
        {
            return Err(ManifestError::Transport(
                "declaration provenance is incomplete".to_string(),
            ));
        }
        let registered_kind = RelationNormalizer::normalize_relation_kind(
            &registry,
            "header-target-resolver.v1",
            "header_context",
            &format!("declared_kind={}", declaration.declared_kind),
        );
        let (dependent, prerequisite, endpoint_rejection) =
            declaration_endpoints(declaration, &identities_by_id, &excluded_identity_ids);
        let contradiction = records.ambiguities.iter().any(|ambiguity| {
            ambiguity.reason_code == "kind_contradiction"
                && ambiguity.evidence_ids.contains(&declaration.declaration_id)
        });
        let expected_rejection = endpoint_rejection
            .or_else(|| {
                registered_kind
                    .as_ref()
                    .err()
                    .map(|_| "kind_unregistered".to_string())
            })
            .or_else(|| contradiction.then(|| "kind_contradiction".to_string()));
        let expected_kind = registered_kind
            .as_ref()
            .map(|spec| spec.stored_kind.clone())
            .unwrap_or_else(|_| declaration.declared_kind.clone());
        if attestation.attestation_key != declaration.attestation_key
            || attestation.declaring_identity_id != declaration.source_identity_id
            || attestation.dependent_identity_id != dependent.clone().unwrap_or_default()
            || attestation.prerequisite_identity_id != prerequisite.clone().unwrap_or_default()
            || attestation.declared_direction != declaration.declared_direction
            || attestation.relation_kind != expected_kind
            || attestation.source_span != declaration.source_span
            || attestation.reason != declaration.reason
            || attestation.raw_line_hash != declaration.raw_line_hash
            || attestation.accepted != expected_rejection.is_none()
            || attestation.rejection_reason != expected_rejection.unwrap_or_default()
        {
            return Err(ManifestError::Transport(
                "declaration attestation consistency failed".to_string(),
            ));
        }
        if attestation.accepted {
            let dependent = dependent.expect("accepted declaration dependent");
            let prerequisite = prerequisite.expect("accepted declaration prerequisite");
            let pair = pair_identity_for(
                &records.header.parent_repo_id,
                &logical_by_id,
                &dependent,
                &prerequisite,
            );
            let fact = hash_parts(&["normalized_relation.v1", &pair, &expected_kind]);
            if !relation_by_fact.contains_key(fact.as_str()) {
                return Err(ManifestError::Transport(
                    "accepted declaration has no direct fact".to_string(),
                ));
            }
        }
    }
    let matched_count = records
        .relations
        .iter()
        .filter(|relation| relation.reconciliation_status == "matched")
        .count();
    let declared_only_count = records
        .relations
        .iter()
        .filter(|relation| relation.reconciliation_status == "declared_only")
        .count();
    let observed_only_count = records
        .relations
        .iter()
        .filter(|relation| relation.reconciliation_status == "observed_only")
        .count();
    if matched_count + declared_only_count + observed_only_count != records.relations.len()
        || records.attestations.len() != records.declarations.len() + records.observations.len()
    {
        return Err(ManifestError::Transport(
            "accepted reconciliation or evidence partition is not exhaustive and disjoint"
                .to_string(),
        ));
    }
    let expected_counts = normalized_record_counts(records);
    let rejected_declaration_count = records
        .attestations
        .iter()
        .filter(|attestation| attestation.evidence_type == "declaration" && !attestation.accepted)
        .count();
    let rejected_observation_count = records
        .attestations
        .iter()
        .filter(|attestation| attestation.evidence_type == "observation" && !attestation.accepted)
        .count();
    if records.summary.record_counts != expected_counts
        || records.summary.accepted_fact_count != records.relations.len()
        || records.summary.rejected_declaration_count != rejected_declaration_count
        || records.summary.rejected_observation_count != rejected_observation_count
        || records.summary.ambiguity_count != records.ambiguities.len()
        || records.summary.source_exclusion_count != records.source_exclusions.len()
        || records.summary.snapshot_id != records.header.snapshot_id
    {
        return Err(ManifestError::Transport(
            "normalization summary count mismatch".to_string(),
        ));
    }
    let expected_fingerprint = normalized_record_fingerprint(records)?;
    if records.summary.normalized_record_fingerprint != expected_fingerprint {
        return Err(ManifestError::Transport(
            "normalized record fingerprint mismatch".to_string(),
        ));
    }
    Ok(())
}

fn normalized_record_counts(records: &NormalizedRecordSet) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    counts.insert("source_snapshot.v1".to_string(), 1);
    counts.insert(
        "source_identity.v1".to_string(),
        records.source_identities.len(),
    );
    counts.insert(
        "dependency_declaration.v1".to_string(),
        records.declarations.len(),
    );
    counts.insert("attestation.v1".to_string(), records.attestations.len());
    counts.insert(
        "normalized_relation.v1".to_string(),
        records.relations.len(),
    );
    counts.insert(
        "observed_evidence.v1".to_string(),
        records.observations.len(),
    );
    counts.insert(
        "surface_relation.v1".to_string(),
        records.surface_relations.len(),
    );
    counts.insert(
        "source_exclusion.v1".to_string(),
        records.source_exclusions.len(),
    );
    counts.insert("ambiguity_a.v1".to_string(), records.ambiguities.len());
    counts.insert(
        "extractor_capability.v1".to_string(),
        records.capabilities.len(),
    );
    for status in ["matched", "declared_only", "observed_only"] {
        counts.insert(
            format!("{status}_count"),
            records
                .relations
                .iter()
                .filter(|relation| relation.reconciliation_status == status)
                .count(),
        );
    }
    counts.insert(
        "accepted_direct_fact_count".to_string(),
        records.relations.len(),
    );
    counts.insert(
        "rejected_declaration_count".to_string(),
        records
            .attestations
            .iter()
            .filter(|attestation| {
                attestation.evidence_type == "declaration" && !attestation.accepted
            })
            .count(),
    );
    counts.insert(
        "rejected_observation_count".to_string(),
        records
            .attestations
            .iter()
            .filter(|attestation| {
                attestation.evidence_type == "observation" && !attestation.accepted
            })
            .count(),
    );
    counts.insert(
        "excluded_count".to_string(),
        records.source_exclusions.len(),
    );
    counts.insert("unresolved_count".to_string(), records.ambiguities.len());
    counts.insert("duplicate_evidence_count".to_string(), 0);
    counts.insert("x_core_count".to_string(), 0);
    counts
}

pub(crate) fn parse_snapshot(reader: impl BufRead) -> Result<ManifestSnapshot, ManifestError> {
    let records = read_canonical_jsonl(reader, "source snapshot")?;
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
    let mut seen_record_ids = BTreeSet::<(String, String)>::new();
    let mut last_rank = 0usize;
    let mut last_order_key = None::<String>;
    for value in records.iter().skip(1) {
        let record_type = value
            .get("record_type")
            .and_then(Value::as_str)
            .ok_or_else(|| ManifestError::Transport("record_type is required".to_string()))?;
        let envelope = parse_envelope(value, record_type, false)?;
        if envelope.snapshot_id != snapshot_id {
            return Err(ManifestError::Transport("mixed snapshot IDs".to_string()));
        }
        if record_type == SNAPSHOT_SCHEMA_VERSION {
            return Err(ManifestError::Transport(
                "duplicate source snapshot header record ID".to_string(),
            ));
        }
        let payload = envelope.payload.as_object().ok_or_else(|| {
            ManifestError::Transport(format!("{record_type} payload must be an object"))
        })?;
        let (rank, order_key, family_label) = match record_type {
            "source_identity.v1" => (
                1,
                string_field(payload, "repo_rel_path")?,
                "source identity",
            ),
            "surface_relation.v1" => (2, envelope.record_id.to_string(), "surface relation"),
            "source_exclusion.v1" => (
                3,
                string_field(payload, "repo_rel_path")?,
                "source exclusion",
            ),
            "dependency_declaration.v1" => {
                (4, envelope.record_id.to_string(), "dependency declaration")
            }
            _ => {
                return Err(ManifestError::Transport(format!(
                    "unknown snapshot record type {record_type}"
                )))
            }
        };
        if !seen_record_ids.insert((record_type.to_string(), envelope.record_id.to_string())) {
            return Err(ManifestError::Transport(format!(
                "duplicate {family_label} record ID {}",
                envelope.record_id
            )));
        }
        if rank < last_rank
            || (rank == last_rank
                && last_order_key
                    .as_deref()
                    .is_some_and(|previous| previous >= order_key.as_str()))
        {
            return Err(ManifestError::Transport(
                "snapshot records are not in canonical family and record order".to_string(),
            ));
        }
        last_rank = rank;
        last_order_key = Some(order_key);
        match record_type {
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
            _ => unreachable!("snapshot family validated before projection"),
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

    let identity_lookups = preflight_source_identities(source_identities)?;
    let identities_by_id = &identity_lookups.path_by_id;
    let identity_by_locator = &identity_lookups.id_by_locator;
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
        if !content_identity_is_canonical(identity, &identity.content_hash) {
            return Err(ManifestError::Transport(format!(
                "content identity representation is invalid for {}",
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
        let expected_target_identity_id = identity_by_locator
            .get(&relation.target_path)
            .cloned()
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
        let source_path = identities_by_id
            .get(&declaration.source_identity_id)
            .cloned()
            .unwrap_or_else(|| declaration.source_span.path.clone());
        if !identities_by_id.contains_key(&declaration.source_identity_id)
            && declaration.source_identity_id
                != hash_parts(&[
                    "source_identity.v1",
                    &header.parent_repo_id,
                    &declaration.source_span.path,
                ])
        {
            return Err(ManifestError::Transport(format!(
                "declaration {} references an unknown source identity",
                declaration.declaration_id
            )));
        }
        if source_path.as_str() != declaration.source_span.path.as_str() {
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
    let mut sorted_identities = source_identities.iter().collect::<Vec<_>>();
    sorted_identities.sort_by(|left, right| left.repo_rel_path.cmp(&right.repo_rel_path));
    for identity in sorted_identities {
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

fn is_git_object_id(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn content_identity_is_canonical(identity: &SourceIdentity, value: &str) -> bool {
    match identity.file_mode.as_str() {
        GITLINK_MODE => is_git_object_id(value) && value == identity.git_blob_or_gitlink,
        "100644" | "100755" | "120000" => is_hex_id(value),
        _ => false,
    }
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
    const RELATION_FIXTURE: &str =
        include_str!("../../../tests/fixtures/dependency_manifest/relation_reconciliation.jsonl");
    const TRANSPORT_FIXTURE: &str =
        include_str!("../../../tests/fixtures/dependency_manifest/transport_conformance.jsonl");
    const KIND_REGISTRY_FIXTURE: &str =
        include_str!("../../../tests/fixtures/knowledge_graph/query_kind_registry.jsonl");
    const CLOSURE_FIXTURE: &str =
        include_str!("../../../tests/fixtures/knowledge_graph/freshness_atomic_closure.jsonl");
    const RETAINED_PARENT_SNAPSHOT: &str = include_str!(
        "../../../reports/agents/20260712-090608-context-packettool-skill-routing/validation/source_snapshot.v1.jsonl"
    );

    #[test]
    fn relation_registry_cli_requires_exactly_one_artifact_path() {
        let valid = vec![
            "normalize".to_string(),
            "--root".to_string(),
            "/tmp/root".to_string(),
            "--profile".to_string(),
            "parent".to_string(),
            "--snapshot-jsonl".to_string(),
            "snapshot.jsonl".to_string(),
            "--relation-registry-json".to_string(),
            "registry.json".to_string(),
            "--output-jsonl".to_string(),
            "output.jsonl".to_string(),
        ];
        let request = parse_normalize_args(&valid).expect("registry path accepted");
        assert_eq!(
            request.relation_registry_json,
            PathBuf::from("registry.json")
        );

        let mut missing = valid.clone();
        let flag = missing
            .iter()
            .position(|value| value == "--relation-registry-json")
            .expect("registry flag");
        missing.drain(flag..=flag + 1);
        assert_eq!(
            parse_normalize_args(&missing).expect_err("missing registry must fail"),
            "missing --relation-registry-json"
        );

        let mut duplicate = valid;
        duplicate.splice(
            9..9,
            [
                "--relation-registry-json".to_string(),
                "other.json".to_string(),
            ],
        );
        assert_eq!(
            parse_normalize_args(&duplicate).expect_err("duplicate registry must fail"),
            "duplicate --relation-registry-json"
        );
    }

    #[test]
    fn relation_registry_loader_uses_canonical_caller_artifact_as_authority() {
        let path = unique_temp_path("agent-canon-relation-registry");
        let expected = builtin_relation_registry_artifact().expect("builtin registry");
        let artifact = json!({
            "entries": relation_registry_entries_value(&expected.entries),
            "registry_fingerprint": expected.registry_fingerprint,
            "registry_version": expected.registry_version,
        });
        let artifact_bytes = serde_json::to_vec(&artifact)
            .expect("registry JSON")
            .into_iter()
            .chain([b'\n'])
            .collect::<Vec<_>>();
        fs::write(&path, &artifact_bytes).expect("registry artifact");
        let artifact = load_relation_registry_artifact(&path).expect("registry artifact loads");
        assert_eq!(artifact.entries.len(), 20);
        assert_eq!(artifact.registry_version, "relation_registry.v1");
        assert_eq!(
            artifact.registry_fingerprint,
            "1308cf12d7d9c2aa8d67b3cff250484d905e70304a6fb3dafdd7da94a7925624"
        );

        let mut caller_entries = artifact.entries.clone();
        caller_entries[0].stored_kind = "caller_owned_kind".to_string();
        let caller_fingerprint =
            relation_registry_fingerprint(&caller_entries, "relation_registry.v1")
                .expect("caller registry fingerprint");
        let caller_artifact = json!({
            "entries": relation_registry_entries_value(&caller_entries),
            "registry_fingerprint": caller_fingerprint,
            "registry_version": "relation_registry.v1",
        });
        let caller_bytes = serde_json::to_vec(&caller_artifact)
            .expect("caller registry JSON")
            .into_iter()
            .chain([b'\n'])
            .collect::<Vec<_>>();
        fs::write(&path, caller_bytes).expect("caller registry artifact");
        let caller_registry =
            load_relation_registry_artifact(&path).expect("caller registry accepted");
        assert_eq!(caller_registry.entries[0].stored_kind, "caller_owned_kind");

        let mut noncanonical = vec![b' '];
        noncanonical.extend_from_slice(&artifact_bytes);
        fs::write(&path, noncanonical).expect("noncanonical registry artifact");
        assert!(matches!(
            load_relation_registry_artifact(&path),
            Err(ManifestError::Transport(message)) if message.contains("canonical")
        ));
        let _ = fs::remove_file(path);
    }

    #[test]
    fn snapshot_stdout_success_keeps_jsonl_and_emits_one_status_line() {
        let bytes = b"{\"record\":\"snapshot\"}\n";
        let mut stdout = Vec::new();
        let mut status = Vec::new();
        write_success_output(Path::new("-"), bytes, &mut stdout, &mut status)
            .expect("stdout publication");
        assert_eq!(stdout, bytes);
        assert_eq!(status, b"DEPENDENCY_MANIFEST_STATUS=ok\n");
        assert_eq!(
            String::from_utf8(status)
                .expect("UTF-8 status")
                .lines()
                .count(),
            1
        );
    }

    #[test]
    fn normalized_transport_fixture_executes_every_exact_byte_case() {
        let snapshot = parse_snapshot(Cursor::new(RETAINED_PARENT_SNAPSHOT.as_bytes()))
            .expect("retained parent snapshot");
        let snapshot_id = snapshot.header.snapshot_id.clone();
        let registry = builtin_relation_registry_artifact().expect("builtin registry");
        let records = normalize_snapshot(
            &NormalizeRequest {
                root: PathBuf::from("/mnt/l/workspace/project_template"),
                profile: "parent".to_string(),
                snapshot_jsonl: PathBuf::from("retained-parent-snapshot.v1.jsonl"),
                evidence_jsonl: Vec::new(),
                relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                output_jsonl: PathBuf::from("-"),
            },
            snapshot,
            &registry,
        )
        .expect("retained normalization");
        let mut canonical = Vec::new();
        write_normalized_record_set(&records, &registry, &mut canonical)
            .expect("canonical normalized transport");
        let mut executed = BTreeSet::new();
        for line in TRANSPORT_FIXTURE.lines() {
            let case = serde_json::from_str::<Value>(line).expect("transport fixture");
            let name = case["case"].as_str().expect("transport case");
            match name {
                "r2-transport-canonical-envelope-order" => {
                    read_normalized_record_set(
                        Cursor::new(canonical.clone()),
                        &snapshot_id,
                        &registry,
                    )
                    .expect("canonical transport accepted");
                    assert_eq!(case["expected"], "accept");
                }
                "r2-reader-same-family-reorder" => {
                    let mut values = normalized_values(&records);
                    let positions = values
                        .iter()
                        .enumerate()
                        .filter(|(_, value)| value["record_type"] == "source_identity.v1")
                        .map(|(index, _)| index)
                        .take(2)
                        .collect::<Vec<_>>();
                    assert_eq!(positions.len(), 2);
                    values.swap(positions[0], positions[1]);
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                    assert_eq!(case["refresh_normalized_record_fingerprint"], true);
                }
                "r2-reader-refreshed-fingerprint" => {
                    let mut values = normalized_values(&records);
                    let summary = values.last_mut().expect("normalization summary");
                    let count = summary["payload"]["record_counts"]["source_identity.v1"]
                        .as_u64()
                        .expect("source identity count");
                    summary["payload"]["record_counts"]["source_identity.v1"] =
                        Value::from(count + 1);
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                    assert_eq!(case["refresh_summary_counts"], true);
                    assert_eq!(case["refresh_normalized_record_fingerprint"], true);
                }
                "r2-reader-cross-family-snapshot-refresh" => {
                    let mut values = normalized_values(&records);
                    let family = case["family"].as_str().expect("transport family");
                    let snapshot_field = case["snapshot_field"]
                        .as_str()
                        .expect("transport snapshot field");
                    let family_count = values
                        .iter()
                        .filter(|value| value["record_type"] == family)
                        .count();
                    let family_record = values
                        .iter_mut()
                        .find(|value| value["record_type"] == family)
                        .expect("transport family record");
                    family_record["payload"][snapshot_field] = Value::String("f".repeat(64));
                    values.last_mut().expect("normalization summary")["payload"]["record_counts"]
                        [family] = Value::from(family_count);
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                    assert_eq!(case["refresh_summary_counts"], true);
                    assert_eq!(case["refresh_normalized_record_fingerprint"], true);
                }
                "r2-reader-registry-kind-authority" => {
                    let mut values = normalized_values(&records);
                    first_normalized_payload_mut(&mut values, "normalized_relation.v1")
                        ["relation_kind"] = Value::String("unregistered_kind".to_string());
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-source-universe-endpoint" => {
                    let mut values = normalized_values(&records);
                    first_normalized_payload_mut(&mut values, "normalized_relation.v1")
                        ["from_identity_id"] = Value::String("0".repeat(64));
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-identity-id-derivation" => {
                    let mut values = normalized_values(&records);
                    let identity = values
                        .iter_mut()
                        .find(|value| value["record_type"] == "source_identity.v1")
                        .expect("source identity");
                    identity["record_id"] = Value::String("0".repeat(64));
                    identity["payload"]["identity_id"] = Value::String("0".repeat(64));
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-source-identity-uniqueness" => {
                    let mutations = case["mutations"]
                        .as_array()
                        .expect("source identity uniqueness mutations");
                    for mutation in mutations {
                        let (field, expected) = match mutation
                            .as_str()
                            .expect("source identity uniqueness mutation")
                        {
                            "duplicate_canonical_locator" => (
                                "canonical_locator",
                                "duplicate source identity canonical locator",
                            ),
                            "duplicate_logical_id" => {
                                ("logical_id", "duplicate source identity logical ID")
                            }
                            other => panic!("unknown source identity mutation {other}"),
                        };
                        let mut values = normalized_values(&records);
                        let positions = values
                            .iter()
                            .enumerate()
                            .filter(|(_, value)| value["record_type"] == "source_identity.v1")
                            .map(|(index, _)| index)
                            .take(2)
                            .collect::<Vec<_>>();
                        assert_eq!(positions.len(), 2);
                        let duplicate = values[positions[0]]["payload"][field].clone();
                        values[positions[1]]["payload"][field] = duplicate;
                        refresh_normalized_value_fingerprint(&mut values);
                        let error = assert_normalized_transport_error(values, &snapshot_id);
                        assert!(
                            error.to_string().contains(expected),
                            "expected {expected:?}, got {error:?}"
                        );
                    }
                }
                "r2-reader-fact-id-derivation" => {
                    let mut values = normalized_values(&records);
                    let relation = values
                        .iter_mut()
                        .find(|value| value["record_type"] == "normalized_relation.v1")
                        .expect("normalized relation");
                    relation["record_id"] = Value::String("0".repeat(64));
                    relation["payload"]["fact_id"] = Value::String("0".repeat(64));
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-pair-id-derivation" => {
                    let mut values = normalized_values(&records);
                    first_normalized_payload_mut(&mut values, "normalized_relation.v1")
                        ["pair_identity"] = Value::String("0".repeat(64));
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-attestation-membership" => {
                    let mut values = normalized_values(&records);
                    first_normalized_payload_mut(&mut values, "normalized_relation.v1")
                        ["attestation_ids"] = Value::Array(Vec::new());
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-attestation-endpoint" => {
                    let mut values = normalized_values(&records);
                    let attestation_id = values
                        .iter()
                        .find(|value| value["record_type"] == "normalized_relation.v1")
                        .and_then(|value| value["payload"]["attestation_ids"].as_array())
                        .and_then(|ids| ids.first())
                        .and_then(Value::as_str)
                        .expect("relation attestation")
                        .to_string();
                    let attestation = values
                        .iter_mut()
                        .find(|value| {
                            value["record_type"] == "attestation.v1"
                                && value["record_id"] == attestation_id
                        })
                        .expect("consumed attestation");
                    attestation["payload"]["dependent_identity_id"] = Value::String("0".repeat(64));
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-observation-membership" => {
                    let mut values = normalized_values(&records);
                    first_normalized_payload_mut(&mut values, "normalized_relation.v1")
                        ["observation_ids"] =
                        Value::Array(vec![Value::String(format!("O-{}", "0".repeat(64)))]);
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-reconciliation-partition" => {
                    let mut values = normalized_values(&records);
                    let relation =
                        first_normalized_payload_mut(&mut values, "normalized_relation.v1");
                    relation["reconciliation_status"] = Value::String("matched".to_string());
                    relation["authority"] = Value::String("declaration+observation".to_string());
                    let counts = values.last_mut().expect("summary")["payload"]["record_counts"]
                        .as_object_mut()
                        .expect("summary counts");
                    let matched = counts["matched_count"].as_u64().expect("matched count");
                    let declared = counts["declared_only_count"]
                        .as_u64()
                        .expect("declared count");
                    counts.insert("matched_count".to_string(), Value::from(matched + 1));
                    counts.insert("declared_only_count".to_string(), Value::from(declared - 1));
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-reader-source-content-provenance" => {
                    let mut values = normalized_values(&records);
                    let hashes =
                        first_normalized_payload_mut(&mut values, "normalized_relation.v1")
                            ["source_content_hashes"]
                            .as_array_mut()
                            .expect("source hashes");
                    hashes[0] = Value::String("f".repeat(64));
                    refresh_normalized_value_fingerprint(&mut values);
                    assert_normalized_transport_error(values, &snapshot_id);
                }
                "r2-json-duplicate-key-preflight" => {
                    let registry_bytes = canonical_registry_bytes(&registry);
                    let relation = records
                        .surface_relations
                        .first()
                        .expect("surface relation for evidence byte gate");
                    let mut evidence_bytes = Vec::new();
                    write_envelope(
                        &mut evidence_bytes,
                        "surface_relation.v1",
                        &relation.relation_id,
                        &snapshot_id,
                        surface_relation_payload(relation),
                    )
                    .expect("canonical evidence bytes");
                    let evidence_path = unique_temp_path("agent-canon-duplicate-evidence-key");
                    let mut expected_mutations = fixture_strings(&case, "shared_mutations");
                    expected_mutations.extend(fixture_strings(&case, "rust_only_mutations"));
                    let mut executed_mutations = BTreeSet::new();
                    for mutation in &expected_mutations {
                        let error = match mutation.as_str() {
                            "registry_top_level" => {
                                parse_relation_registry_artifact_bytes(&duplicate_json_field(
                                    &registry_bytes,
                                    "registry_version",
                                    Value::String("relation_registry.v1".to_string()),
                                    0,
                                ))
                                .expect_err("duplicate registry top-level key accepted")
                            }
                            "registry_nested" => {
                                parse_relation_registry_artifact_bytes(&duplicate_json_field(
                                    &registry_bytes,
                                    "capability_id",
                                    Value::String(registry.entries[0].capability_id.clone()),
                                    0,
                                ))
                                .expect_err("duplicate registry nested key accepted")
                            }
                            "normalized_top_level" => read_normalized_record_set(
                                Cursor::new(duplicate_json_field(
                                    &canonical,
                                    "record_type",
                                    Value::String("normalized_record_set_header.v1".to_string()),
                                    0,
                                )),
                                &snapshot_id,
                                &registry,
                            )
                            .expect_err("duplicate normalized top-level key accepted"),
                            "normalized_nested" => read_normalized_record_set(
                                Cursor::new(duplicate_json_field(
                                    &canonical,
                                    "schema_version",
                                    Value::String(NORMALIZED_RECORD_SET_VERSION.to_string()),
                                    0,
                                )),
                                &snapshot_id,
                                &registry,
                            )
                            .expect_err("duplicate normalized nested key accepted"),
                            "normalized_escaped_equivalent" => read_normalized_record_set(
                                Cursor::new(replace_first_bytes(
                                    &duplicate_json_field(
                                        &canonical,
                                        "record_type",
                                        Value::String(
                                            "normalized_record_set_header.v1".to_string(),
                                        ),
                                        0,
                                    ),
                                    b"\"record_type\":",
                                    b"\"\\u0072ecord_type\":",
                                )),
                                &snapshot_id,
                                &registry,
                            )
                            .expect_err("escaped-equivalent duplicate normalized key accepted"),
                            "snapshot_top_level" => {
                                parse_snapshot(Cursor::new(duplicate_json_field(
                                    RETAINED_PARENT_SNAPSHOT.as_bytes(),
                                    "record_type",
                                    Value::String(SNAPSHOT_SCHEMA_VERSION.to_string()),
                                    0,
                                )))
                                .expect_err("duplicate snapshot top-level key accepted")
                            }
                            "snapshot_nested" => parse_snapshot(Cursor::new(duplicate_json_field(
                                RETAINED_PARENT_SNAPSHOT.as_bytes(),
                                "schema_version",
                                Value::String(SNAPSHOT_SCHEMA_VERSION.to_string()),
                                0,
                            )))
                            .expect_err("duplicate snapshot nested key accepted"),
                            "evidence_top_level" | "evidence_nested" => {
                                let (field, value) = if mutation == "evidence_top_level" {
                                    (
                                        "record_type",
                                        Value::String("surface_relation.v1".to_string()),
                                    )
                                } else {
                                    ("status", Value::String(relation.status.clone()))
                                };
                                fs::write(
                                    &evidence_path,
                                    duplicate_json_field(&evidence_bytes, field, value, 0),
                                )
                                .expect("duplicate evidence input");
                                read_evidence_inputs(
                                    std::slice::from_ref(&evidence_path),
                                    &snapshot_id,
                                )
                                .expect_err("duplicate evidence key accepted")
                            }
                            other => panic!("unknown duplicate-key mutation {other}"),
                        };
                        assert!(
                            error.to_string().contains("duplicate JSON key"),
                            "{mutation}: duplicate key was not rejected before Value: {error}"
                        );
                        executed_mutations.insert(mutation.clone());
                    }
                    assert_eq!(
                        executed_mutations,
                        expected_mutations.into_iter().collect::<BTreeSet<_>>()
                    );
                    let _ = fs::remove_file(evidence_path);
                }
                "r2-evidence-jsonl-raw-byte-gate" => {
                    let relation = records
                        .surface_relations
                        .first()
                        .expect("surface relation for evidence byte gate");
                    let mut evidence_bytes = Vec::new();
                    write_envelope(
                        &mut evidence_bytes,
                        "surface_relation.v1",
                        &relation.relation_id,
                        &snapshot_id,
                        surface_relation_payload(relation),
                    )
                    .expect("canonical evidence bytes");
                    let evidence_value = serde_json::from_slice::<Value>(
                        &evidence_bytes[..evidence_bytes.len() - 1],
                    )
                    .expect("evidence fixture value");
                    let evidence_path = unique_temp_path("agent-canon-evidence-byte-gate");
                    let mut executed_mutations = BTreeSet::new();
                    for mutation in fixture_strings(&case, "mutations") {
                        let mutated = match mutation.as_str() {
                            "bom" => b"\xef\xbb\xbf"
                                .iter()
                                .copied()
                                .chain(evidence_bytes.iter().copied())
                                .collect(),
                            "crlf" => evidence_bytes[..evidence_bytes.len() - 1]
                                .iter()
                                .copied()
                                .chain([b'\r', b'\n'])
                                .collect(),
                            "missing_final_lf" => {
                                evidence_bytes[..evidence_bytes.len() - 1].to_vec()
                            }
                            "noncanonical_key_order" => {
                                noncanonical_envelope_bytes(&evidence_value)
                            }
                            other => panic!("unknown evidence byte mutation {other}"),
                        };
                        fs::write(&evidence_path, mutated).expect("evidence byte mutation");
                        assert!(
                            read_evidence_inputs(
                                std::slice::from_ref(&evidence_path),
                                &snapshot_id,
                            )
                            .is_err(),
                            "evidence raw-byte mutation accepted: {mutation}"
                        );
                        executed_mutations.insert(mutation);
                    }
                    assert_eq!(
                        executed_mutations,
                        fixture_strings(&case, "mutations")
                            .into_iter()
                            .collect::<BTreeSet<_>>()
                    );
                    let _ = fs::remove_file(evidence_path);
                }
                "r2-reader-global-locator-namespace" => {
                    let mut executed_mutations = BTreeSet::new();
                    for mutation in fixture_strings(&case, "mutations") {
                        let mut values = normalized_values(&records);
                        let positions = values
                            .iter()
                            .enumerate()
                            .filter(|(_, value)| value["record_type"] == "source_identity.v1")
                            .map(|(index, _)| index)
                            .collect::<Vec<_>>();
                        assert!(positions.len() >= 2);
                        match mutation.as_str() {
                            "path_vs_canonical" => {
                                let path_position = *positions
                                    .iter()
                                    .find(|position| {
                                        values[**position]["payload"]["repo_rel_path"]
                                            != values[**position]["payload"]["canonical_locator"]
                                    })
                                    .expect("identity path distinct from canonical locator");
                                let collision_position = *positions
                                    .iter()
                                    .find(|position| **position != path_position)
                                    .expect("second identity");
                                let path_locator = values[path_position]["payload"]
                                    ["repo_rel_path"]
                                    .as_str()
                                    .expect("repo path")
                                    .to_string();
                                values[collision_position]["payload"]["canonical_locator"] =
                                    Value::String(path_locator.clone());
                                values[collision_position]["payload"]["logical_id"] =
                                    Value::String(hash_parts(&[
                                        "logical_source.v1",
                                        &records.header.parent_repo_id,
                                        &path_locator,
                                    ]));
                            }
                            "alternate_vs_alternate" => {
                                for position in positions.iter().take(2) {
                                    values[*position]["payload"]["alternate_locators"] =
                                        Value::Array(vec![Value::String(
                                            "alternate://shared-collision".to_string(),
                                        )]);
                                }
                            }
                            other => panic!("unknown locator namespace mutation {other}"),
                        }
                        refresh_normalized_value_fingerprint(&mut values);
                        let error = assert_normalized_transport_error(values, &snapshot_id);
                        assert!(
                            error
                                .to_string()
                                .contains("source identity locator namespace collision"),
                            "{mutation}: unexpected locator collision error: {error}"
                        );
                        executed_mutations.insert(mutation);
                    }
                    assert_eq!(
                        executed_mutations,
                        fixture_strings(&case, "mutations")
                            .into_iter()
                            .collect::<BTreeSet<_>>()
                    );
                    let mut executed_preflight = BTreeSet::new();
                    for mutation in fixture_strings(&case, "rust_preflight_mutations") {
                        let mut identities = vec![test_identity("first"), test_identity("second")];
                        let expected = match mutation.as_str() {
                            "duplicate_identity_id" => {
                                identities[1].identity_id = identities[0].identity_id.clone();
                                "duplicate source identity record ID"
                            }
                            "duplicate_repo_path" => {
                                identities[1].repo_rel_path = identities[0].repo_rel_path.clone();
                                "duplicate source identity path"
                            }
                            "duplicate_canonical_locator" => {
                                identities[1].canonical_locator =
                                    identities[0].canonical_locator.clone();
                                "duplicate source identity canonical locator"
                            }
                            "duplicate_logical_id" => {
                                identities[1].logical_id = identities[0].logical_id.clone();
                                "duplicate source identity logical ID"
                            }
                            other => panic!("unknown identity preflight mutation {other}"),
                        };
                        let error = preflight_source_identities(&identities)
                            .expect_err("identity preflight accepted duplicate key");
                        assert!(
                            error.to_string().contains(expected),
                            "{mutation}: unexpected identity preflight error: {error}"
                        );
                        executed_preflight.insert(mutation);
                    }
                    assert_eq!(
                        executed_preflight,
                        fixture_strings(&case, "rust_preflight_mutations")
                            .into_iter()
                            .collect::<BTreeSet<_>>()
                    );
                    assert_eq!(case["producer_mutation"], "tracked_symlink_and_target");
                    #[cfg(unix)]
                    {
                        use std::os::unix::fs::symlink;

                        let root = unique_temp_path("agent-canon-locator-producer");
                        fs::create_dir_all(&root).expect("locator producer root");
                        fs::write(root.join("target.txt"), "target\n").expect("locator target");
                        symlink("target.txt", root.join("alias.txt")).expect("locator alias");
                        initialize_and_commit(&root);
                        let error = capture_snapshot(&snapshot_request(&root))
                            .expect_err("producer accepted duplicate canonical identity");
                        assert!(
                            error
                                .to_string()
                                .contains("duplicate source identity canonical locator"),
                            "unexpected producer preflight error: {error}"
                        );
                        let _ = fs::remove_dir_all(root);
                    }
                }
                other => panic!("unknown transport fixture case {other}"),
            }
            executed.insert(name.to_string());
        }
        assert_eq!(executed.len(), TRANSPORT_FIXTURE.lines().count());
    }

    #[test]
    fn normalized_reader_rejects_noncanonical_and_duplicate_key_bytes() {
        let snapshot = parse_snapshot(Cursor::new(RETAINED_PARENT_SNAPSHOT.as_bytes()))
            .expect("retained parent snapshot");
        let snapshot_id = snapshot.header.snapshot_id.clone();
        let registry = builtin_relation_registry_artifact().expect("builtin registry");
        let records = normalize_snapshot(
            &NormalizeRequest {
                root: PathBuf::from("/mnt/l/workspace/project_template"),
                profile: "parent".to_string(),
                snapshot_jsonl: PathBuf::from("retained-parent-snapshot.v1.jsonl"),
                evidence_jsonl: Vec::new(),
                relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                output_jsonl: PathBuf::from("-"),
            },
            snapshot,
            &registry,
        )
        .expect("retained normalization");
        let mut canonical = Vec::new();
        write_normalized_record_set(&records, &registry, &mut canonical)
            .expect("canonical normalized transport");

        let mut whitespace = canonical.clone();
        whitespace.insert(1, b' ');
        let mut duplicate = canonical.clone();
        duplicate.splice(
            1..1,
            b"\"schema_version\":\"dependency_manifest.normalized.v1\","
                .iter()
                .copied(),
        );
        let mut missing_final_lf = canonical;
        assert_eq!(missing_final_lf.pop(), Some(b'\n'));
        for mutation in [whitespace, duplicate, missing_final_lf] {
            assert!(
                read_normalized_record_set(Cursor::new(mutation), &snapshot_id, &registry).is_err()
            );
        }
    }

    #[test]
    fn source_snapshot_reader_rejects_noncanonical_bytes_and_pre_sort_order() {
        let canonical = RETAINED_PARENT_SNAPSHOT.as_bytes().to_vec();
        parse_snapshot(Cursor::new(canonical.clone())).expect("canonical retained snapshot");
        let lines = RETAINED_PARENT_SNAPSHOT
            .lines()
            .map(str::to_string)
            .collect::<Vec<_>>();
        let record_type = |line: &str| {
            serde_json::from_str::<Value>(line).expect("snapshot fixture line")["record_type"]
                .as_str()
                .expect("snapshot record type")
                .to_string()
        };
        let identity_positions = lines
            .iter()
            .enumerate()
            .filter(|(_, line)| record_type(line) == "source_identity.v1")
            .map(|(index, _)| index)
            .take(2)
            .collect::<Vec<_>>();
        let surface_position = lines
            .iter()
            .position(|line| record_type(line) == "surface_relation.v1")
            .expect("surface family");
        let declaration_position = lines
            .iter()
            .position(|line| record_type(line) == "dependency_declaration.v1")
            .expect("declaration family");
        let encode = |values: &[String]| {
            values
                .iter()
                .flat_map(|line| line.as_bytes().iter().copied().chain([b'\n']))
                .collect::<Vec<_>>()
        };

        let mut bom = b"\xef\xbb\xbf".to_vec();
        bom.extend_from_slice(&canonical);
        let mut crlf = canonical.clone();
        let first_lf = crlf.iter().position(|byte| *byte == b'\n').expect("LF");
        crlf.insert(first_lf, b'\r');
        let mut missing_final_lf = canonical.clone();
        assert_eq!(missing_final_lf.pop(), Some(b'\n'));
        let mut duplicate_key = canonical.clone();
        duplicate_key.splice(
            1..1,
            b"\"schema_version\":\"dependency_manifest.normalized.v1\","
                .iter()
                .copied(),
        );
        let mut family_reorder = lines.clone();
        family_reorder.swap(surface_position, declaration_position);
        let mut id_reorder = lines.clone();
        id_reorder.swap(identity_positions[0], identity_positions[1]);
        let mut duplicate_id = lines;
        duplicate_id.insert(
            identity_positions[0] + 1,
            duplicate_id[identity_positions[0]].clone(),
        );
        for (name, mutation) in [
            ("bom", bom),
            ("crlf", crlf),
            ("missing-final-lf", missing_final_lf),
            ("duplicate-key", duplicate_key),
            ("family-reorder", encode(&family_reorder)),
            ("record-order", encode(&id_reorder)),
            ("duplicate-id", encode(&duplicate_id)),
        ] {
            assert!(
                parse_snapshot(Cursor::new(mutation)).is_err(),
                "source snapshot mutation accepted: {name}"
            );
        }
    }

    #[test]
    fn snapshot_evidence_surface_merge_is_explicit_and_conflict_closed() {
        let snapshot = parse_snapshot(Cursor::new(RETAINED_PARENT_SNAPSHOT.as_bytes()))
            .expect("retained parent snapshot");
        let relation = snapshot
            .surface_relations
            .first()
            .expect("retained surface relation")
            .clone();
        let evidence_path = unique_temp_path("agent-canon-surface-merge");
        let mut exact_bytes = Vec::new();
        write_envelope(
            &mut exact_bytes,
            "surface_relation.v1",
            &relation.relation_id,
            &snapshot.header.snapshot_id,
            surface_relation_payload(&relation),
        )
        .expect("exact surface evidence");
        fs::write(&evidence_path, exact_bytes).expect("surface evidence input");
        let request = NormalizeRequest {
            root: PathBuf::from("/mnt/l/workspace/project_template"),
            profile: "parent".to_string(),
            snapshot_jsonl: PathBuf::from("retained-parent-snapshot.v1.jsonl"),
            evidence_jsonl: vec![evidence_path.clone()],
            relation_registry_json: PathBuf::from("relation-registry.v1.json"),
            output_jsonl: PathBuf::from("-"),
        };
        let registry = builtin_relation_registry_artifact().expect("builtin registry");
        let exact = normalize_snapshot(&request, snapshot.clone(), &registry)
            .expect("exact cross-input duplicate is idempotent");
        assert_eq!(
            exact.surface_relations.len(),
            snapshot.surface_relations.len()
        );

        let mut conflicting = relation;
        conflicting.status = "conflicting-review-status".to_string();
        let mut conflicting_bytes = Vec::new();
        write_envelope(
            &mut conflicting_bytes,
            "surface_relation.v1",
            &conflicting.relation_id,
            &snapshot.header.snapshot_id,
            surface_relation_payload(&conflicting),
        )
        .expect("conflicting surface evidence");
        fs::write(&evidence_path, conflicting_bytes).expect("conflicting evidence input");
        assert!(matches!(
            normalize_snapshot(&request, snapshot, &registry),
            Err(ManifestError::Transport(message))
                if message.contains("conflicting snapshot/evidence surface relation")
        ));
        let _ = fs::remove_file(evidence_path);
    }

    #[test]
    fn r2_parent_gitlink_relation_preserves_index_identity() {
        let snapshot = parse_snapshot(Cursor::new(RETAINED_PARENT_SNAPSHOT.as_bytes()))
            .expect("retained parent snapshot");
        let gitlink = source_identity(&snapshot, "vendor/agent-canon").clone();
        assert_eq!(gitlink.file_mode, GITLINK_MODE);
        assert!(is_git_object_id(&gitlink.content_hash));
        assert!(is_git_object_id(&gitlink.git_blob_or_gitlink));
        assert!(is_git_object_id(&gitlink.submodule_commit));
        assert_eq!(gitlink.content_hash, gitlink.git_blob_or_gitlink);
        assert_ne!(gitlink.content_hash, gitlink.submodule_commit);

        let gitlink_fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-gitlink-transport-identity")
            .expect("gitlink transport fixture");
        let valid = gitlink.content_hash.clone();
        assert!(content_identity_is_canonical(&gitlink, &valid));
        for mutation in fixture_strings(&gitlink_fixture, "reject") {
            let mut tampered = gitlink.clone();
            tampered.content_hash = match mutation.as_str() {
                "gitlink-39hex" => "a".repeat(39),
                "gitlink-41hex" => "a".repeat(41),
                "gitlink-nonhex" => "g".repeat(40),
                "gitlink-mismatched-valid-40hex" => "b".repeat(40),
                other => panic!("unknown gitlink mutation {other}"),
            };
            assert!(
                !content_identity_is_canonical(&tampered, &tampered.content_hash),
                "gitlink mutation accepted: {mutation}"
            );
        }

        let records = normalize_snapshot(
            &NormalizeRequest {
                root: PathBuf::from("/mnt/l/workspace/project_template"),
                profile: "parent".to_string(),
                snapshot_jsonl: PathBuf::from("retained-parent-snapshot.v1.jsonl"),
                evidence_jsonl: Vec::new(),
                relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                output_jsonl: PathBuf::from("-"),
            },
            snapshot,
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("parent snapshot normalization");
        let relation = records
            .relations
            .iter()
            .find(|relation| {
                relation.from_identity_id == gitlink.identity_id
                    || relation.to_identity_id == gitlink.identity_id
            })
            .expect("parent gitlink relation");
        let endpoint_index = if relation.from_identity_id == gitlink.identity_id {
            0
        } else {
            1
        };
        assert_eq!(
            relation.source_content_hashes[endpoint_index],
            gitlink.content_hash
        );
        assert_eq!(relation.source_content_hashes[endpoint_index].len(), 40);
    }

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

    #[test]
    fn r2_relation_fixture_covers_all_required_reconciliation_cases() {
        let cases = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture JSON"))
            .collect::<Vec<_>>();
        let names = cases
            .iter()
            .map(|case| case["case"].as_str().expect("fixture case"))
            .collect::<BTreeSet<_>>();
        for required in [
            "r2-direction-truth-table",
            "r2-attestation-key-order-independence",
            "r2-duplicate-multi-attestation",
            "r2-kind-contradiction",
            "r2-observation-locator-identity-mismatch",
            "r2-observation-capability-authorization",
            "r2-missing-stale-excluded-target",
            "r2-reconciliation-partitions",
            "r2-attestation-provenance-tamper",
            "r2-summary-rejected-count-tamper",
            "r2-one-edge-reverse-adjacency",
            "r2-observation-acceptance-vetoes",
            "r2-observation-excluded-endpoints",
            "r2-valid-gitlink-relation",
            "r2-normalized-record-order",
            "r2-gitlink-transport-identity",
            "r2-declaration-endpoint-u-adversaries",
            "r2-ambiguity-evidence-forward-membership",
        ] {
            assert!(names.contains(required), "missing {required}");
        }
        let truth_table = cases
            .iter()
            .find(|case| case["case"] == "r2-direction-truth-table")
            .expect("truth table");
        assert_eq!(truth_table["rows"].as_array().expect("rows").len(), 6);
        let source = test_identity("s");
        let target = test_identity("t");
        let identities = BTreeMap::from([
            (source.identity_id.as_str(), &source),
            (target.identity_id.as_str(), &target),
        ]);
        for (index, row) in truth_table["rows"]
            .as_array()
            .expect("direction rows")
            .iter()
            .enumerate()
        {
            let direction = row["declared_direction"].as_str().expect("direction");
            let kind = row["declared_kind"].as_str().expect("kind");
            let declaration = DependencyDeclaration {
                declaration_id: format!("D-{index}"),
                source_identity_id: source.identity_id.clone(),
                declared_direction: direction.to_string(),
                declared_kind: kind.to_string(),
                declared_target: target.repo_rel_path.clone(),
                resolved_target_identity_id: Some(target.identity_id.clone()),
                source_span: SourceSpan {
                    path: source.repo_rel_path.clone(),
                    start_line: 1,
                    start_column: 1,
                    end_line: 1,
                    end_column: 2,
                },
                reason: "fixture".to_string(),
                raw_line_hash: hash_parts(&["direction", &index.to_string()]),
                attestation_key: hash_parts(&["attestation", &index.to_string()]),
                snapshot_id: "snapshot".to_string(),
            };
            let (dependent, prerequisite, rejection) =
                declaration_endpoints(&declaration, &identities, &BTreeSet::new());
            assert!(rejection.is_none(), "direction row {index}");
            assert_eq!(
                dependent.expect("dependent"),
                row["dependent"].as_str().expect("expected dependent")
            );
            assert_eq!(
                prerequisite.expect("prerequisite"),
                row["prerequisite"].as_str().expect("expected prerequisite")
            );
            let spec = RelationNormalizer::normalize_relation_kind(
                &builtin_relation_registry_artifact().expect("builtin registry"),
                "header-target-resolver.v1",
                "header_context",
                &format!("declared_kind={kind}"),
            )
            .expect("direction kind");
            assert_eq!(spec.stored_kind, row["stored_kind"]);
        }
        let partition = cases
            .iter()
            .find(|case| case["case"] == "r2-reconciliation-partitions")
            .expect("partition fixture");
        assert_eq!(
            fixture_strings(partition, "accepted_comparable_partitions"),
            vec!["matched", "declared_only", "observed_only"]
        );
        assert_eq!(
            fixture_strings(partition, "rejected_evidence_partitions"),
            vec!["excluded", "unresolved"]
        );
        assert_eq!(fixture_strings(partition, "reader_count_fields").len(), 5);
    }

    #[test]
    fn r2_compiled_registry_conformance_baseline_matches_fixture() {
        RelationNormalizer::validate_compiled_registry_conformance_baseline()
            .expect("valid compiled conformance baseline");
        let registry_keys = RELATION_KIND_REGISTRY
            .iter()
            .map(|spec| {
                (
                    spec.capability_id.to_string(),
                    spec.raw_kind.to_string(),
                    spec.discriminator.to_string(),
                )
            })
            .collect::<BTreeSet<_>>();
        let mut fixture_keys = BTreeSet::new();
        let mut fixture_rows = 0;
        for line in KIND_REGISTRY_FIXTURE.lines() {
            let case: Value = serde_json::from_str(line).expect("registry fixture JSON");
            let producer = case["producer"].as_str().expect("producer");
            let raw_kind = case["raw_kind"].as_str().expect("raw kind");
            let discriminator = case["discriminator"].as_str().expect("discriminator");
            assert!(
                fixture_keys.insert((
                    producer.to_string(),
                    raw_kind.to_string(),
                    discriminator.to_string(),
                )),
                "duplicate registry fixture key"
            );
            fixture_rows += 1;
            let spec = RelationNormalizer::normalize_relation_kind(
                &builtin_relation_registry_artifact().expect("builtin registry"),
                producer,
                raw_kind,
                discriminator,
            )
            .expect("registered conversion");
            assert_eq!(spec.stored_kind, case["stored_kind"]);
            assert_eq!(spec.layer, case["layer"]);
            assert_eq!(spec.family, case["query_family"]);
        }
        assert_eq!(fixture_rows, RELATION_KIND_REGISTRY.len());
        assert_eq!(fixture_keys, registry_keys);
        assert_eq!(
            RELATION_KIND_REGISTRY
                .iter()
                .filter(|spec| spec.stored_kind == "view_of")
                .count(),
            2,
            "intentional shared stored kind must be preserved"
        );
        assert_eq!(
            RELATION_KIND_REGISTRY
                .iter()
                .filter(|spec| spec.stored_kind == "contains")
                .count(),
            2,
            "intentional shared stored kind must be preserved"
        );
        assert!(RelationNormalizer::normalize_relation_kind(
            &builtin_relation_registry_artifact().expect("builtin registry"),
            "code-static.v1",
            "code_reference",
            "reference_kind=unknown"
        )
        .is_err());
        assert_eq!(
            RelationNormalizer::allowed_kinds_for_family(
                &builtin_relation_registry_artifact().expect("builtin registry"),
                "dependency",
            ),
            vec!["design", "environment", "implementation"]
        );
    }

    #[test]
    fn r2_closure_fixture_proves_monotone_termination_and_order_independence() {
        let cases = CLOSURE_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("closure fixture JSON"))
            .collect::<Vec<_>>();
        let mut executed = BTreeSet::new();
        for case in cases.iter().filter(|case| {
            case["case"]
                .as_str()
                .is_some_and(|name| name.starts_with("r2-closure"))
        }) {
            let name = case["case"].as_str().expect("closure case");
            let identities = fixture_strings(case, "vertices")
                .iter()
                .map(|path| test_identity(path))
                .collect::<Vec<_>>();
            let relations = fixture_relations(case);
            let seeds = fixture_strings(case, "seeds");
            let allowed = fixture_strings(case, "allowed_kinds");
            let exclusions = fixture_strings(case, "excluded_vertices")
                .into_iter()
                .map(|identity_id| SourceExclusion {
                    source_exclusion_id: hash_parts(&["fixture-exclusion", &identity_id]),
                    source_identity_id: identity_id.clone(),
                    repo_rel_path: identity_id.clone(),
                    reason_code: "generated_output".to_string(),
                    rule_id: "fixture".to_string(),
                    scope: "closure".to_string(),
                    evidence_id: hash_parts(&["fixture-exclusion-evidence", &identity_id]),
                    covered: false,
                    snapshot_id: "snapshot".to_string(),
                })
                .collect::<Vec<_>>();
            let ambiguities = case
                .get("ambiguity_edge_index")
                .and_then(Value::as_u64)
                .map(|index| {
                    let relation = &relations[index as usize];
                    vec![ambiguity_record(
                        "snapshot",
                        &relation.from_identity_id,
                        vec![relation.fact_id.clone()],
                        vec![relation.to_identity_id.clone()],
                        "fixture_ambiguity",
                        &relation.relation_kind,
                        vec!["fixture-evidence".to_string()],
                    )]
                })
                .unwrap_or_default();
            let query_family = case["query_family"].as_str().expect("query family");
            let result = RelationNormalizer::least_fixed_point(
                &builtin_relation_registry_artifact().expect("builtin registry"),
                &identities,
                &exclusions,
                &ambiguities,
                &relations,
                &seeds,
                query_family,
                &allowed,
            );
            if let Some(expected_error) = case.get("expected_error").and_then(Value::as_str) {
                assert!(
                    result.expect_err(name).to_string().contains(expected_error),
                    "{name}: expected {expected_error}"
                );
                executed.insert(name.to_string());
                continue;
            }
            let result = result.unwrap_or_else(|error| panic!("{name}: {error}"));
            assert_eq!(
                result.reachable_identity_ids,
                fixture_strings(case, "expected_reachable"),
                "{name}: reachable"
            );
            if case.get("expected_trace").is_some() {
                let expected_trace = case["expected_trace"]
                    .as_array()
                    .expect("expected trace")
                    .iter()
                    .map(|value| {
                        value
                            .as_array()
                            .expect("trace row")
                            .iter()
                            .map(|item| item.as_str().expect("trace identity").to_string())
                            .collect::<Vec<_>>()
                    })
                    .collect::<Vec<_>>();
                assert_eq!(result.visited_trace, expected_trace, "{name}: trace");
            }
            assert!(result.monotone, "{name}: monotone");
            assert!(result.order_independent, "{name}: reverse order");
            assert!(
                result.iterations <= result.termination_bound,
                "{name}: termination bound"
            );
            assert!(result.visited_trace.windows(2).all(|window| {
                let left = window[0].iter().collect::<BTreeSet<_>>();
                let right = window[1].iter().collect::<BTreeSet<_>>();
                left.is_subset(&right)
            }));
            if case["execute_every_edge_permutation"].as_bool() == Some(true) {
                let expected_reachable = result.reachable_identity_ids.clone();
                let expected_witnesses = result.direct_witness_fact_ids.clone();
                let permutations = all_permutations(&relations);
                assert_eq!(permutations.len(), 6, "three-edge permutation count");
                for permutation in permutations {
                    let permuted = RelationNormalizer::least_fixed_point(
                        &builtin_relation_registry_artifact().expect("builtin registry"),
                        &identities,
                        &exclusions,
                        &ambiguities,
                        &permutation,
                        &seeds,
                        query_family,
                        &allowed,
                    )
                    .expect("permuted closure");
                    assert_eq!(permuted.reachable_identity_ids, expected_reachable);
                    assert_eq!(permuted.direct_witness_fact_ids, expected_witnesses);
                }
            }
            executed.insert(name.to_string());
        }
        let named_closure_cases = cases
            .iter()
            .filter_map(|case| case["case"].as_str())
            .filter(|name| name.starts_with("r2-closure"))
            .map(str::to_string)
            .collect::<BTreeSet<_>>();
        assert_eq!(executed, named_closure_cases);

        let adjacency_relations = vec![test_relation(
            "a",
            "b",
            "design",
            &hash_parts(&["adjacency", "a", "b"]),
        )];
        let adjacency = RelationNormalizer::derive_reverse_adjacency(&adjacency_relations);
        assert_eq!(adjacency.direct_fact_count, 1);
        assert_eq!(adjacency.downstream["a"], vec!["b"]);
        assert_eq!(adjacency.upstream["b"], vec!["a"]);
    }

    #[cfg(unix)]
    #[test]
    fn r2_normalization_emits_o_capability_status_and_strict_round_trip() {
        let (root, outside_target) = source_universe_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("R2 snapshot");
        let tracked = source_identity(&snapshot, "tracked.txt");
        let modify = source_identity(&snapshot, "modify.txt");
        let observation_id = format!("O-{}", "a".repeat(64));
        let observation = ObservedEvidence {
            observation_id: observation_id.clone(),
            extractor_id: "header-target-resolver".to_string(),
            extractor_version: "test".to_string(),
            capability_id: "header-target-resolver.v1".to_string(),
            relation_kind: "header_context".to_string(),
            from_locator: tracked.repo_rel_path.clone(),
            to_locator: modify.repo_rel_path.clone(),
            from_identity_id: tracked.identity_id.clone(),
            to_identity_id: modify.identity_id.clone(),
            source_span: SourceSpan {
                path: tracked.repo_rel_path.clone(),
                start_line: 4,
                start_column: 1,
                end_line: 4,
                end_column: 80,
            },
            payload_hash: "b".repeat(64),
            classification: "declared_kind=implementation".to_string(),
            accepted: true,
            snapshot_id: snapshot.header.snapshot_id.clone(),
        };
        let capability = ExtractorCapability {
            capability_id: "header-target-resolver.v1".to_string(),
            extractor_id: "header-target-resolver".to_string(),
            extractor_version: "test".to_string(),
            relation_kinds: vec!["header_context".to_string()],
            input_scope: "connected:explicit-evidence-input".to_string(),
            supported_file_kinds: vec!["text".to_string()],
            unsupported_behavior: "unsupported-and-unresolved-to-A".to_string(),
            dynamic_behavior: "dynamic-reflection-to-A".to_string(),
            provenance_fields: vec![
                "payload_hash".to_string(),
                "snapshot_id".to_string(),
                "source_span".to_string(),
            ],
            completeness_claim:
                "connected; supplied-records-complete; semantic-completeness-not-claimed"
                    .to_string(),
        };
        let evidence_path = unique_temp_path("agent-canon-r2-evidence");
        let mut evidence_bytes = Vec::new();
        write_envelope(
            &mut evidence_bytes,
            "extractor_capability.v1",
            &capability.capability_id,
            &snapshot.header.snapshot_id,
            capability_payload(&capability),
        )
        .expect("capability evidence JSONL");
        write_envelope(
            &mut evidence_bytes,
            "observed_evidence.v1",
            &observation.observation_id,
            &snapshot.header.snapshot_id,
            observed_evidence_payload(&observation),
        )
        .expect("evidence JSONL");
        fs::write(&evidence_path, &evidence_bytes).expect("evidence file");
        let request = NormalizeRequest {
            root: root.clone(),
            profile: "parent".to_string(),
            snapshot_jsonl: PathBuf::from("-"),
            evidence_jsonl: vec![evidence_path.clone()],
            relation_registry_json: PathBuf::from("relation-registry.v1.json"),
            output_jsonl: PathBuf::from("-"),
        };
        let records = normalize_snapshot(
            &request,
            snapshot.clone(),
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("R2 normalization");
        let duplicate_fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-duplicate-multi-attestation")
            .expect("duplicate fixture");
        assert_eq!(records.observations.len(), 1);
        assert_eq!(
            records.relations.len(),
            duplicate_fixture["expected_direct_fact_count"]
                .as_u64()
                .expect("expected fact count") as usize
        );
        assert_eq!(records.relations[0].reconciliation_status, "matched");
        assert_eq!(
            records.relations[0].attestation_ids.len(),
            duplicate_fixture["expected_attestation_count"]
                .as_u64()
                .expect("expected attestation count") as usize
        );
        assert!(records
            .capabilities
            .iter()
            .any(|capability| capability.capability_id == "code-static.v1"
                && (capability.completeness_claim.contains("unavailable")
                    || capability.completeness_claim.contains("provided-empty"))));
        let mut bytes = Vec::new();
        let registry = builtin_relation_registry_artifact().expect("builtin registry");
        write_normalized_record_set(&records, &registry, &mut bytes).expect("normalized transport");
        let parsed = read_normalized_record_set(
            Cursor::new(bytes.clone()),
            &snapshot.header.snapshot_id,
            &registry,
        )
        .expect("strict normalized reader");
        assert_eq!(parsed, records);

        let duplicate_path = unique_temp_path("agent-canon-r2-evidence-duplicate");
        let mut duplicate_bytes = Vec::new();
        write_envelope(
            &mut duplicate_bytes,
            "observed_evidence.v1",
            &observation.observation_id,
            &snapshot.header.snapshot_id,
            observed_evidence_payload(&observation),
        )
        .expect("duplicate observation JSONL");
        fs::write(&duplicate_path, duplicate_bytes).expect("duplicate evidence file");
        let mut first_order = request.clone();
        first_order.evidence_jsonl = vec![evidence_path.clone(), duplicate_path.clone()];
        let mut second_order = request.clone();
        second_order.evidence_jsonl = vec![duplicate_path.clone(), evidence_path.clone()];
        for duplicate_request in [first_order, second_order] {
            let error = normalize_snapshot(
                &duplicate_request,
                snapshot.clone(),
                &builtin_relation_registry_artifact().expect("builtin registry"),
            )
            .expect_err("duplicate observation accepted");
            assert!(error.to_string().contains("exact duplicate observation"));
        }
        assert_eq!(duplicate_fixture["duplicate_transport_expected"], "reject");
        assert_eq!(
            records.summary.record_counts["duplicate_evidence_count"],
            duplicate_fixture["expected_duplicate_evidence_count_for_valid_set"]
                .as_u64()
                .expect("valid duplicate count") as usize
        );

        let mut tampered: Vec<Value> = String::from_utf8(bytes)
            .expect("UTF-8 normalized transport")
            .lines()
            .map(|line| serde_json::from_str(line).expect("normalized JSON"))
            .collect();
        let summary_index = tampered.len() - 1;
        tampered[summary_index]["payload"]["accepted_fact_count"] = Value::from(99u64);
        assert_normalized_transport_error(tampered, &snapshot.header.snapshot_id);
        let mut tampered = normalized_values(&records);
        tampered[0]["payload"]["schema_version"] = Value::String("wrong.v1".to_string());
        assert_normalized_transport_error(tampered, &snapshot.header.snapshot_id);
        let mut tampered = normalized_values(&records);
        tampered[0]["unexpected"] = Value::Bool(true);
        assert_normalized_transport_error(tampered, &snapshot.header.snapshot_id);

        let _ = fs::remove_file(evidence_path);
        let _ = fs::remove_file(duplicate_path);
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[cfg(unix)]
    #[test]
    fn r2_kind_contradiction_rejects_both_attestations_and_retains_a() {
        let fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-kind-contradiction")
            .expect("contradiction fixture");
        let (root, outside_target) = source_universe_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("contradiction snapshot");
        let tracked = source_identity(&snapshot, "tracked.txt");
        let modify = source_identity(&snapshot, "modify.txt");
        let observation = test_observation(
            &snapshot.header.snapshot_id,
            tracked,
            modify,
            'c',
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            "header_context",
            "declared_kind=design",
        );
        let capability = connected_capability(
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            &["header_context"],
        );
        let evidence_path = write_evidence_input(
            &snapshot.header.snapshot_id,
            &[capability],
            &[observation],
            "agent-canon-r2-contradiction",
        );
        let records = normalize_with_evidence(&root, snapshot.clone(), evidence_path.clone());
        assert_eq!(
            records.summary.accepted_fact_count,
            fixture["expected_accepted_fact_count"]
                .as_u64()
                .expect("expected fact count") as usize
        );
        assert!(records.relations.is_empty());
        assert_eq!(records.attestations.len(), 2);
        assert!(records.attestations.iter().all(|attestation| {
            !attestation.accepted && attestation.rejection_reason == "kind_contradiction"
        }));
        assert!(records
            .observations
            .iter()
            .all(|observation| !observation.accepted));
        assert!(records.ambiguities.iter().any(|ambiguity| {
            ambiguity.reason_code
                == fixture["expected_ambiguity_reason"]
                    .as_str()
                    .expect("ambiguity reason")
                && ambiguity.evidence_ids.len() == 2
        }));
        assert_eq!(records.summary.rejected_declaration_count, 1);
        assert_eq!(records.summary.rejected_observation_count, 1);
        assert_eq!(
            records.summary.record_counts["rejected_declaration_count"],
            1
        );
        assert_eq!(
            records.summary.record_counts["rejected_observation_count"],
            1
        );
        let mut bytes = Vec::new();
        let registry = builtin_relation_registry_artifact().expect("builtin registry");
        write_normalized_record_set(&records, &registry, &mut bytes)
            .expect("contradiction transport");
        read_normalized_record_set(Cursor::new(bytes), &snapshot.header.snapshot_id, &registry)
            .expect("strict contradiction round trip");
        let _ = fs::remove_file(evidence_path);
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[cfg(unix)]
    #[test]
    fn r2_attestation_fixture_permutations_are_byte_identical() {
        let fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-attestation-key-order-independence")
            .expect("attestation order fixture");
        let (root, outside_target) = source_universe_git_repo();
        fs::write(
            root.join("tracked.txt"),
            "# @dependency-start\n# contract implementation\n# responsibility Exercises R2 attestation order.\n# upstream implementation modify.txt first edge\n# upstream design rename.txt second edge\n# @dependency-end\n",
        )
        .expect("order manifest");
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("order snapshot");
        assert_eq!(snapshot.declarations.len(), 2);
        let tracked = source_identity(&snapshot, "tracked.txt");
        let modify = source_identity(&snapshot, "modify.txt");
        let observation = test_observation(
            &snapshot.header.snapshot_id,
            tracked,
            modify,
            'a',
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            "header_context",
            "declared_kind=implementation",
        );
        let capability = connected_capability(
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            &["header_context"],
        );
        let evidence_path = write_evidence_input(
            &snapshot.header.snapshot_id,
            &[capability],
            &[observation],
            "agent-canon-r2-attestation-order",
        );
        let declaration_a = snapshot
            .declarations
            .iter()
            .find(|declaration| declaration.declared_target == "modify.txt")
            .expect("declaration a")
            .clone();
        let declaration_b = snapshot
            .declarations
            .iter()
            .find(|declaration| declaration.declared_target == "rename.txt")
            .expect("declaration b")
            .clone();
        let mut outputs = Vec::new();
        for permutation in fixture["permutations"]
            .as_array()
            .expect("attestation permutations")
        {
            let mut permuted_snapshot = snapshot.clone();
            permuted_snapshot.declarations = permutation
                .as_array()
                .expect("attestation permutation")
                .iter()
                .filter_map(|item| match item.as_str().expect("attestation item") {
                    "declaration-a" => Some(declaration_a.clone()),
                    "declaration-b" => Some(declaration_b.clone()),
                    "observation-a" => None,
                    other => panic!("unknown attestation fixture item {other}"),
                })
                .collect();
            let records = normalize_with_evidence(&root, permuted_snapshot, evidence_path.clone());
            assert!(records.relations.iter().all(|relation| {
                relation
                    .attestation_ids
                    .windows(2)
                    .all(|window| window[0] < window[1])
                    && relation
                        .observation_ids
                        .windows(2)
                        .all(|window| window[0] < window[1])
            }));
            let mut bytes = Vec::new();
            write_normalized_record_set(
                &records,
                &builtin_relation_registry_artifact().expect("builtin registry"),
                &mut bytes,
            )
            .expect("ordered output");
            outputs.push(bytes);
        }
        assert_eq!(outputs.len(), 3);
        assert!(outputs.windows(2).all(|window| window[0] == window[1]));
        let _ = fs::remove_file(evidence_path);
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[test]
    fn r2_strict_reader_rejects_same_family_reorder_with_refreshed_fingerprint() {
        let fixture = CLOSURE_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("closure fixture"))
            .find(|case| case["case"] == "r2-reader-same-family-reorder")
            .expect("same-family reorder fixture");
        let root = temporary_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("order snapshot");
        let records = normalize_snapshot(
            &NormalizeRequest {
                root: root.clone(),
                profile: "parent".to_string(),
                snapshot_jsonl: PathBuf::from("retained-order-snapshot.v1.jsonl"),
                evidence_jsonl: Vec::new(),
                relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                output_jsonl: PathBuf::from("-"),
            },
            snapshot.clone(),
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("order normalization");
        let mut tampered = normalized_values(&records);
        let source_indices = tampered
            .iter()
            .enumerate()
            .filter(|(_, value)| value["record_type"] == fixture["family"])
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        assert!(
            source_indices.len() >= 2,
            "fixture needs two source identities"
        );
        let summary_index = tampered.len() - 1;
        tampered[summary_index]["payload"]["normalized_record_fingerprint"] =
            Value::String(normalized_record_fingerprint(&records).expect("fingerprint"));
        tampered.swap(source_indices[0], source_indices[1]);
        assert_eq!(
            tampered[summary_index]["payload"]["normalized_record_fingerprint"],
            records.summary.normalized_record_fingerprint
        );
        assert_normalized_transport_error(tampered, &snapshot.header.snapshot_id);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn r2_observation_locators_must_name_the_declared_identities() {
        let fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-observation-locator-identity-mismatch")
            .expect("locator fixture");
        let root = temporary_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("locator snapshot");
        let from = source_identity(&snapshot, "tracked.txt");
        let to = source_identity(&snapshot, "rename.txt");
        for (index, field) in fixture["mismatches"]
            .as_array()
            .expect("locator mismatches")
            .iter()
            .enumerate()
        {
            let mut observation = test_observation(
                &snapshot.header.snapshot_id,
                from,
                to,
                if index == 0 { 'd' } else { 'e' },
                "header-target-resolver.v1",
                "header-target-resolver",
                "test",
                "header_context",
                "declared_kind=design",
            );
            match field.as_str().expect("locator field") {
                "from_locator" => observation.from_locator = "wrong/from".to_string(),
                "to_locator" => observation.to_locator = "wrong/to".to_string(),
                other => panic!("unknown locator mismatch {other}"),
            }
            let capability = connected_capability(
                "header-target-resolver.v1",
                "header-target-resolver",
                "test",
                &["header_context"],
            );
            let evidence_path = write_evidence_input(
                &snapshot.header.snapshot_id,
                &[capability],
                &[observation],
                "agent-canon-r2-locator",
            );
            let records = normalize_with_evidence(&root, snapshot.clone(), evidence_path.clone());
            assert!(records.relations.is_empty());
            assert_eq!(records.observations.len(), 1);
            assert!(!records.observations[0].accepted);
            assert_eq!(records.attestations.len(), 1);
            assert!(!records.attestations[0].accepted);
            assert_eq!(
                records.attestations[0].rejection_reason,
                fixture["expected_ambiguity_reason"]
                    .as_str()
                    .expect("locator ambiguity reason")
            );
            assert!(records.ambiguities.iter().any(|ambiguity| {
                ambiguity.reason_code == "provenance_incomplete"
                    && ambiguity
                        .evidence_ids
                        .contains(&records.observations[0].observation_id)
            }));
            let _ = fs::remove_file(evidence_path);
        }
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn r2_only_connected_provenance_complete_capabilities_authorize_o() {
        let fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-observation-capability-authorization")
            .expect("capability fixture");
        let root = temporary_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("capability snapshot");
        let from = source_identity(&snapshot, "tracked.txt");
        let to = source_identity(&snapshot, "rename.txt");
        let statuses = fixture["statuses"].as_array().expect("capability statuses");
        for (index, status) in statuses.iter().enumerate() {
            let status = status.as_str().expect("capability status");
            let suffix = ['a', 'b', 'c', 'd'][index];
            let (capability_id, extractor_id, relation_kind, classification) =
                if status == "unknown" {
                    (
                        "unknown-producer.v1",
                        "unknown-producer",
                        "mystery",
                        "unknown",
                    )
                } else {
                    (
                        "header-target-resolver.v1",
                        "header-target-resolver",
                        "header_context",
                        "declared_kind=design",
                    )
                };
            let observation = test_observation(
                &snapshot.header.snapshot_id,
                from,
                to,
                suffix,
                capability_id,
                extractor_id,
                "test",
                relation_kind,
                classification,
            );
            let capabilities = match status {
                "connected" => vec![connected_capability(
                    capability_id,
                    extractor_id,
                    "test",
                    &[relation_kind],
                )],
                "unavailable" => Vec::new(),
                "provided-empty" => {
                    let mut capability =
                        connected_capability(capability_id, extractor_id, "test", &[relation_kind]);
                    capability.input_scope = "explicit-evidence-input:empty".to_string();
                    capability.completeness_claim =
                        "provided-empty; O=empty; coverage=0".to_string();
                    vec![capability]
                }
                "unknown" => vec![connected_capability(
                    capability_id,
                    extractor_id,
                    "test",
                    &[relation_kind],
                )],
                other => panic!("unknown capability fixture status {other}"),
            };
            let evidence_path = write_evidence_input(
                &snapshot.header.snapshot_id,
                &capabilities,
                &[observation],
                "agent-canon-r2-capability",
            );
            let records = normalize_with_evidence(&root, snapshot.clone(), evidence_path.clone());
            let should_accept = status == "connected";
            assert_eq!(records.observations[0].accepted, should_accept, "{status}");
            assert_eq!(
                records.relations.len(),
                usize::from(should_accept),
                "{status}"
            );
            if !should_accept {
                let expected_reason = if status == "unknown" {
                    "capability_unknown"
                } else {
                    "capability_unavailable"
                };
                assert_eq!(records.attestations[0].rejection_reason, expected_reason);
                assert!(records.ambiguities.iter().any(|ambiguity| {
                    ambiguity.reason_code == expected_reason
                        && ambiguity
                            .evidence_ids
                            .contains(&records.observations[0].observation_id)
                }));
            }
            if status == "unknown" {
                let retained = records
                    .capabilities
                    .iter()
                    .find(|capability| capability.capability_id == capability_id)
                    .expect("unknown capability retained");
                assert!(retained.input_scope.contains("unavailable"));
                assert!(retained.completeness_claim.contains("unavailable"));
                assert!(records.ambiguities.iter().any(|ambiguity| {
                    ambiguity.reason_code == "capability_unknown"
                        && ambiguity.evidence_ids.contains(&capability_id.to_string())
                }));
            }
            let _ = fs::remove_file(evidence_path);
        }
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn r2_observation_acceptance_vetoes_dynamic_and_excluded_endpoints() {
        let fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-observation-acceptance-vetoes")
            .expect("acceptance veto fixture");
        let endpoint_fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-observation-excluded-endpoints")
            .expect("excluded endpoint fixture");
        let (root, outside_target) = source_universe_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("acceptance snapshot");
        let source = source_identity(&snapshot, "tracked.txt");
        let target = source_identity(&snapshot, "modify.txt");
        let excluded = source_identity(&snapshot, ".agent-canon/knowledge-graph/graph.sqlite");
        let capability = connected_capability(
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            &["header_context"],
        );
        let mut observations = Vec::new();
        for (index, classification) in fixture["classifications"]
            .as_array()
            .expect("classifications")
            .iter()
            .enumerate()
        {
            let mut observation = test_observation(
                &snapshot.header.snapshot_id,
                source,
                target,
                ['a', 'b', 'c'][index],
                "header-target-resolver.v1",
                "header-target-resolver",
                "test",
                "header_context",
                classification.as_str().expect("classification"),
            );
            observation.accepted = fixture["producer_accepted"]
                .as_bool()
                .expect("producer bit");
            observations.push(observation);
        }
        let mut source_excluded = test_observation(
            &snapshot.header.snapshot_id,
            excluded,
            target,
            'd',
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            "header_context",
            "declared_kind=design",
        );
        source_excluded.accepted = true;
        let mut target_excluded = test_observation(
            &snapshot.header.snapshot_id,
            source,
            excluded,
            'e',
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            "header_context",
            "declared_kind=design",
        );
        target_excluded.accepted = true;
        observations.extend([source_excluded, target_excluded]);
        let evidence_path = write_evidence_input(
            &snapshot.header.snapshot_id,
            &[capability],
            &observations,
            "agent-canon-r2-acceptance-veto",
        );
        let records = normalize_with_evidence(&root, snapshot, evidence_path.clone());
        for (index, expected_reason) in [
            "dynamic_or_reflection",
            "dynamic_or_reflection",
            "dynamic_or_reflection",
            "source_excluded_source",
            "source_excluded_target",
        ]
        .into_iter()
        .enumerate()
        {
            let observation = &records.observations[index];
            assert!(!observation.accepted, "observation {index} accepted");
            let attestation = records
                .attestations
                .iter()
                .find(|attestation| attestation.evidence_id == observation.observation_id)
                .expect("observation attestation");
            assert!(
                !attestation.accepted,
                "observation {index} attestation accepted"
            );
            assert_eq!(attestation.rejection_reason, expected_reason);
            assert!(records.ambiguities.iter().any(|ambiguity| {
                ambiguity.reason_code == expected_reason
                    && ambiguity.evidence_ids.contains(&observation.observation_id)
                    && !ambiguity.covered
            }));
            assert!(!records.relations.iter().any(|relation| relation
                .observation_ids
                .contains(&observation.observation_id)));
        }
        assert_eq!(endpoint_fixture["expected_accepted"].as_bool(), Some(false));
        let _ = fs::remove_file(evidence_path);
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[cfg(unix)]
    #[test]
    fn r2_strict_reader_rejects_refreshed_observation_acceptance_tamper() {
        let fixture = CLOSURE_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("closure fixture"))
            .find(|case| case["case"] == "r2-reader-accepted-bit-tamper")
            .expect("accepted-bit fixture");
        let ghost_fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-ambiguity-evidence-forward-membership")
            .expect("ghost ambiguity fixture");
        let expected_cases = fixture_strings(&fixture, "mutations")
            .into_iter()
            .collect::<BTreeSet<_>>();
        assert_eq!(
            fixture["semantic_failure"],
            "observation attestation consistency failed"
        );
        assert_eq!(
            expected_cases,
            BTreeSet::from([
                "dynamic".to_string(),
                "reflection".to_string(),
                "runtime".to_string(),
                "excluded_source".to_string(),
                "excluded_target".to_string(),
                "capability_unavailable".to_string(),
                "capability_unknown".to_string(),
            ])
        );
        let mut executed = BTreeSet::new();
        for case_name in fixture_strings(&fixture, "mutations") {
            let (root, outside_target) = source_universe_git_repo();
            let snapshot = capture_snapshot(&snapshot_request(&root)).expect("tamper snapshot");
            let source = source_identity(&snapshot, "tracked.txt");
            let target = source_identity(&snapshot, "modify.txt");
            let excluded = source_identity(&snapshot, ".agent-canon/knowledge-graph/graph.sqlite");
            let observation = match case_name.as_str() {
                "dynamic" | "reflection" | "runtime" => test_observation(
                    &snapshot.header.snapshot_id,
                    source,
                    target,
                    match case_name.as_str() {
                        "dynamic" => 'a',
                        "reflection" => 'b',
                        "runtime" => 'c',
                        _ => unreachable!(),
                    },
                    "header-target-resolver.v1",
                    "header-target-resolver",
                    "test",
                    "header_context",
                    &case_name,
                ),
                "excluded_source" => test_observation(
                    &snapshot.header.snapshot_id,
                    excluded,
                    target,
                    'd',
                    "header-target-resolver.v1",
                    "header-target-resolver",
                    "test",
                    "header_context",
                    "declared_kind=design",
                ),
                "excluded_target" => test_observation(
                    &snapshot.header.snapshot_id,
                    source,
                    excluded,
                    'e',
                    "header-target-resolver.v1",
                    "header-target-resolver",
                    "test",
                    "header_context",
                    "declared_kind=design",
                ),
                "capability_unavailable" => test_observation(
                    &snapshot.header.snapshot_id,
                    source,
                    target,
                    'f',
                    "header-target-resolver.v1",
                    "header-target-resolver",
                    "test",
                    "header_context",
                    "declared_kind=design",
                ),
                "capability_unknown" => test_observation(
                    &snapshot.header.snapshot_id,
                    source,
                    target,
                    '0',
                    "unknown-capability.v1",
                    "unknown-capability",
                    "test",
                    "unknown_relation",
                    "unknown",
                ),
                other => panic!("unknown accepted-bit mutation {other}"),
            };
            let capabilities = match case_name.as_str() {
                "dynamic" | "reflection" | "runtime" | "excluded_source" | "excluded_target" => {
                    vec![connected_capability(
                        "header-target-resolver.v1",
                        "header-target-resolver",
                        "test",
                        &["header_context"],
                    )]
                }
                "capability_unavailable" => Vec::new(),
                "capability_unknown" => vec![connected_capability(
                    "unknown-capability.v1",
                    "unknown-capability",
                    "test",
                    &["unknown_relation"],
                )],
                _ => unreachable!(),
            };
            let evidence_path = write_evidence_input(
                &snapshot.header.snapshot_id,
                &capabilities,
                &[observation],
                "agent-canon-r2-accepted-bit-tamper",
            );
            let records = normalize_with_evidence(&root, snapshot.clone(), evidence_path.clone());
            assert_eq!(records.observations.len(), 1, "{case_name}: O retention");
            assert_eq!(records.attestations.len(), records.declarations.len() + 1);
            let observation = &records.observations[0];
            assert!(!observation.accepted, "{case_name}: producer accepted O");
            let attestation = records
                .attestations
                .iter()
                .find(|attestation| attestation.evidence_id == observation.observation_id)
                .expect("O attestation");
            assert!(!attestation.accepted, "{case_name}: producer accepted T");
            assert!(records.ambiguities.iter().any(|ambiguity| {
                ambiguity.evidence_ids.contains(&observation.observation_id) && !ambiguity.covered
            }));
            assert!(records.relations.iter().all(|relation| {
                !relation
                    .observation_ids
                    .contains(&observation.observation_id)
            }));
            if case_name == "dynamic" {
                let mut ghost = records.clone();
                ghost.ambiguities[0]
                    .evidence_ids
                    .push("ghost-ambiguity-evidence".to_string());
                ghost.ambiguities[0].evidence_ids.sort();
                refresh_normalized_summary(&mut ghost);
                let error = read_normalized_record_set(
                    Cursor::new(unchecked_normalized_bytes(&ghost)),
                    &snapshot.header.snapshot_id,
                    &builtin_relation_registry_artifact().expect("builtin registry"),
                )
                .expect_err("ghost ambiguity evidence accepted");
                assert!(matches!(error, ManifestError::Transport(_)));
                assert!(ghost_fixture["refresh_fingerprint"].as_bool() == Some(true));
            }

            let mut tampered = records.clone();
            let observation_index = tampered
                .observations
                .iter()
                .position(|item| item.observation_id == observation.observation_id)
                .expect("tampered observation");
            tampered.observations[observation_index].accepted = true;
            tampered.observations[observation_index].payload_hash =
                hash_parts(&["refreshed-payload", &case_name]);
            let tampered_payload_hash = tampered.observations[observation_index]
                .payload_hash
                .clone();
            let attestation_index = tampered
                .attestations
                .iter()
                .position(|item| item.evidence_id == observation.observation_id)
                .expect("tampered attestation");
            let attestation_key = hash_parts(&[
                "observed_attestation.v1",
                &tampered.observations[observation_index].snapshot_id,
                &tampered.observations[observation_index].observation_id,
                &tampered_payload_hash,
            ]);
            tampered.attestations[attestation_index].accepted = true;
            tampered.attestations[attestation_index]
                .rejection_reason
                .clear();
            tampered.attestations[attestation_index].attestation_key = attestation_key.clone();
            tampered.attestations[attestation_index].raw_line_hash = tampered_payload_hash;
            tampered.attestations[attestation_index].attestation_id =
                hash_parts(&["attestation.v1", &attestation_key]);
            tampered
                .ambiguities
                .retain(|ambiguity| !ambiguity.evidence_ids.contains(&observation.observation_id));
            refresh_normalized_summary(&mut tampered);
            let error = read_normalized_record_set(
                Cursor::new(unchecked_normalized_bytes(&tampered)),
                &snapshot.header.snapshot_id,
                &builtin_relation_registry_artifact().expect("builtin registry"),
            )
            .expect_err("semantic accepted-bit tamper accepted");
            assert!(matches!(&error, ManifestError::Transport(_)));
            assert!(
                error
                    .to_string()
                    .contains("observation attestation consistency failed"),
                "{case_name}: accepted-bit mutation failed for another reason: {error}"
            );
            assert_eq!(
                if matches!(&error, ManifestError::Transport(_)) {
                    22
                } else {
                    0
                },
                22
            );
            assert_eq!(
                if matches!(&error, ManifestError::Transport(_)) {
                    "transport-invalid"
                } else {
                    "other"
                },
                fixture["expected_status"]
                    .as_str()
                    .expect("transport status")
            );
            executed.insert(case_name);
            let _ = fs::remove_file(evidence_path);
            let _ = fs::remove_dir_all(root);
            let _ = fs::remove_file(outside_target);
        }
        assert_eq!(executed, expected_cases);
    }

    #[cfg(unix)]
    #[test]
    fn r2_strict_reader_recomputes_counts_and_rejects_provenance_tamper() {
        let named_cases = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .filter(|case| {
                matches!(
                    case["case"].as_str(),
                    Some("r2-attestation-provenance-tamper")
                        | Some("r2-summary-rejected-count-tamper")
                )
            })
            .collect::<Vec<_>>();
        assert_eq!(named_cases.len(), 2);
        let (root, outside_target) = source_universe_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("tamper snapshot");
        let tracked = source_identity(&snapshot, "tracked.txt");
        let modify = source_identity(&snapshot, "modify.txt");
        let observation = test_observation(
            &snapshot.header.snapshot_id,
            tracked,
            modify,
            'f',
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            "header_context",
            "declared_kind=implementation",
        );
        let capability = connected_capability(
            "header-target-resolver.v1",
            "header-target-resolver",
            "test",
            &["header_context"],
        );
        let evidence_path = write_evidence_input(
            &snapshot.header.snapshot_id,
            &[capability],
            &[observation],
            "agent-canon-r2-reader-tamper",
        );
        let records = normalize_with_evidence(&root, snapshot.clone(), evidence_path.clone());
        assert_eq!(records.relations.len(), 1);
        assert_eq!(records.relations[0].attestation_ids.len(), 2);

        for field in [
            "rejected_declaration_count",
            "rejected_observation_count",
            "record_counts.rejected_declaration_count",
            "record_counts.rejected_observation_count",
            "record_counts.duplicate_evidence_count",
        ] {
            let mut tampered = records.clone();
            match field {
                "rejected_declaration_count" => tampered.summary.rejected_declaration_count += 1,
                "rejected_observation_count" => tampered.summary.rejected_observation_count += 1,
                "record_counts.rejected_declaration_count" => {
                    *tampered
                        .summary
                        .record_counts
                        .get_mut("rejected_declaration_count")
                        .expect("declaration count") += 1
                }
                "record_counts.rejected_observation_count" => {
                    *tampered
                        .summary
                        .record_counts
                        .get_mut("rejected_observation_count")
                        .expect("observation count") += 1
                }
                "record_counts.duplicate_evidence_count" => {
                    *tampered
                        .summary
                        .record_counts
                        .get_mut("duplicate_evidence_count")
                        .expect("duplicate evidence count") += 1
                }
                _ => unreachable!(),
            }
            assert!(
                read_normalized_record_set(
                    Cursor::new(unchecked_normalized_bytes(&tampered)),
                    &snapshot.header.snapshot_id,
                    &builtin_relation_registry_artifact().expect("builtin registry"),
                )
                .is_err(),
                "summary tamper accepted: {field}"
            );
        }

        for tamper_case in [
            "duplicate_evidence_key",
            "endpoint",
            "kind",
            "snapshot",
            "dropped_attestation",
            "dropped_fact_membership",
            "empty_source_hash",
        ] {
            let mut tampered = records.clone();
            match tamper_case {
                "duplicate_evidence_key" => {
                    let mut duplicate = tampered.attestations[0].clone();
                    duplicate.attestation_key = hash_parts(&["duplicate-attestation-key"]);
                    duplicate.attestation_id =
                        hash_parts(&["attestation.v1", &duplicate.attestation_key]);
                    tampered.attestations.push(duplicate);
                }
                "endpoint" => {
                    tampered.attestations[0].dependent_identity_id =
                        tampered.attestations[0].prerequisite_identity_id.clone();
                }
                "kind" => tampered.attestations[0].relation_kind = "design".to_string(),
                "snapshot" => tampered.attestations[0].snapshot_id = "0".repeat(64),
                "dropped_attestation" => {
                    tampered.attestations.remove(0);
                }
                "dropped_fact_membership" => {
                    tampered.relations[0].attestation_ids.remove(0);
                }
                "empty_source_hash" => {
                    tampered.relations[0].source_content_hashes[0].clear();
                }
                _ => unreachable!(),
            }
            refresh_normalized_summary(&mut tampered);
            assert!(
                read_normalized_record_set(
                    Cursor::new(unchecked_normalized_bytes(&tampered)),
                    &snapshot.header.snapshot_id,
                    &builtin_relation_registry_artifact().expect("builtin registry"),
                )
                .is_err(),
                "provenance tamper accepted after refreshed fingerprint: {tamper_case}"
            );
        }
        let _ = fs::remove_file(evidence_path);
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[test]
    fn r2_freshness_and_reader_tamper_fixture_cases_are_executable() {
        let cases = CLOSURE_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("closure fixture"))
            .collect::<Vec<_>>();
        let freshness = cases
            .iter()
            .find(|case| case["case"] == "r2-freshness-snapshot-mismatch")
            .expect("freshness fixture");
        let reader = cases
            .iter()
            .find(|case| case["case"] == "r2-reader-tamper-rejection")
            .expect("reader fixture");
        let root = temporary_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("freshness snapshot");
        let records = normalize_snapshot(
            &NormalizeRequest {
                root: root.clone(),
                profile: "parent".to_string(),
                snapshot_jsonl: PathBuf::from("-"),
                evidence_jsonl: Vec::new(),
                relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                output_jsonl: PathBuf::from("-"),
            },
            snapshot.clone(),
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("freshness normalization");
        let baseline = normalized_values(&records);
        let mut executed_freshness = BTreeSet::new();
        for mutation in fixture_strings(freshness, "mutations") {
            let mut tampered = baseline.clone();
            match mutation.as_str() {
                "snapshot_id" => {
                    tampered[0]["payload"]["snapshot_id"] = Value::String("0".repeat(64));
                }
                "schema_version" => {
                    tampered[0]["payload"]["schema_version"] =
                        Value::String("wrong.v1".to_string());
                }
                "tool_version" => {
                    tampered[0]["payload"]["tool_version"] =
                        Value::String("tampered-tool".to_string());
                }
                "agentcanon_pin" => {
                    let snapshot_index = record_index(&tampered, SNAPSHOT_SCHEMA_VERSION);
                    tampered[snapshot_index]["payload"]["agentcanon_pin"] =
                        Value::String("tampered-pin".to_string());
                }
                "profile" => {
                    tampered[0]["payload"]["profile"] = Value::String("wrong".to_string());
                }
                other => panic!("unknown freshness mutation {other}"),
            }
            assert_normalized_transport_error(tampered, &snapshot.header.snapshot_id);
            executed_freshness.insert(mutation);
        }
        assert_eq!(
            executed_freshness,
            fixture_strings(freshness, "mutations")
                .into_iter()
                .collect::<BTreeSet<_>>()
        );

        let mut executed_reader = BTreeSet::new();
        for field in fixture_strings(reader, "tamper_fields") {
            let mut tampered = baseline.clone();
            let summary_index = tampered.len() - 1;
            match field.as_str() {
                "schema_version" => {
                    tampered[0]["payload"]["schema_version"] =
                        Value::String("wrong.v1".to_string());
                }
                "snapshot_id" => {
                    tampered[0]["payload"]["snapshot_id"] = Value::String("0".repeat(64));
                }
                "record_counts" => {
                    tampered[summary_index]["payload"]["record_counts"]["source_identity.v1"] =
                        Value::from(999u64);
                }
                "rejected_declaration_count" => {
                    tampered[summary_index]["payload"]["rejected_declaration_count"] =
                        Value::from(999u64);
                }
                "rejected_observation_count" => {
                    tampered[summary_index]["payload"]["rejected_observation_count"] =
                        Value::from(999u64);
                }
                "normalized_record_fingerprint" => {
                    tampered[summary_index]["payload"]["normalized_record_fingerprint"] =
                        Value::String("0".repeat(64));
                }
                "unknown_top_level_field" => {
                    tampered[0]["unexpected"] = Value::Bool(true);
                }
                other => panic!("unknown reader tamper field {other}"),
            }
            assert_normalized_transport_error(tampered, &snapshot.header.snapshot_id);
            executed_reader.insert(field);
        }
        assert_eq!(
            executed_reader,
            fixture_strings(reader, "tamper_fields")
                .into_iter()
                .collect::<BTreeSet<_>>()
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn r2_normalization_without_evidence_is_explicitly_unavailable_not_covered() {
        let root = temporary_git_repo();
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("R2 snapshot");
        let request = NormalizeRequest {
            root: root.clone(),
            profile: "parent".to_string(),
            snapshot_jsonl: PathBuf::from("-"),
            evidence_jsonl: Vec::new(),
            relation_registry_json: PathBuf::from("relation-registry.v1.json"),
            output_jsonl: PathBuf::from("-"),
        };
        let records = normalize_snapshot(
            &request,
            snapshot,
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("R2 empty O normalization");
        assert!(records.observations.is_empty());
        assert_eq!(
            records.summary.record_counts["accepted_direct_fact_count"],
            records.relations.len()
        );
        assert_eq!(records.summary.record_counts["x_core_count"], 0);
        assert!(records.capabilities.iter().all(|capability| {
            capability.completeness_claim.contains("unavailable")
                || capability.completeness_claim.contains("provided-empty")
        }));
        let fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-empty-o-capability-transport")
            .expect("empty-O capability fixture");
        let registered_capability_ids = producer_capability_rows(
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .into_iter()
        .map(|(capability_id, _, _)| capability_id)
        .collect::<BTreeSet<_>>();
        let materialized_capability_ids = records
            .capabilities
            .iter()
            .map(|capability| capability.capability_id.clone())
            .collect::<BTreeSet<_>>();
        assert_eq!(materialized_capability_ids, registered_capability_ids);
        let mut executed = BTreeSet::new();
        for mutation in fixture_strings(&fixture, "mutations") {
            let mut tampered = records.clone();
            match mutation.as_str() {
                "status-flip" => {
                    let capability = tampered
                        .capabilities
                        .iter_mut()
                        .find(|capability| capability.capability_id == "code-static.v1")
                        .expect("registered capability row");
                    capability.input_scope = "connected:tampered".to_string();
                    capability.completeness_claim =
                        "connected; supplied-records-complete; coverage=1".to_string();
                }
                "row-delete" => {
                    tampered
                        .capabilities
                        .retain(|capability| capability.capability_id != "code-static.v1");
                }
                other => panic!("unknown empty-O capability mutation {other}"),
            }
            refresh_normalized_summary(&mut tampered);
            let error = read_normalized_record_set(
                Cursor::new(unchecked_normalized_bytes(&tampered)),
                &records.header.snapshot_id,
                &builtin_relation_registry_artifact().expect("builtin registry"),
            )
            .expect_err("empty-O capability mutation accepted");
            assert!(matches!(error, ManifestError::Transport(_)));
            let expected_error = if mutation == "status-flip" {
                "empty observation set requires unavailable/provided-empty capability status"
            } else {
                "registered capability transport is incomplete or duplicated"
            };
            assert!(
                error.to_string().contains(expected_error),
                "{mutation}: unexpected capability error: {error}"
            );
            executed.insert(mutation);
        }
        assert_eq!(
            executed,
            fixture_strings(&fixture, "mutations")
                .into_iter()
                .collect::<BTreeSet<_>>()
        );
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn r2_missing_stale_and_excluded_targets_are_typed_a_and_never_facts() {
        let (root, outside_target) = source_universe_git_repo();
        fs::remove_file(root.join("delete.txt")).expect("stale target deletion");
        fs::write(
            root.join("tracked.txt"),
            "# @dependency-start\n# contract implementation\n# responsibility Exercises R2 target diagnostics.\n# upstream implementation missing.txt missing target\n# upstream implementation delete.txt stale target\n# upstream implementation .agent-canon/knowledge-graph/graph.sqlite generated target\n# @dependency-end\n",
        )
        .expect("R2 diagnostic manifest");
        let snapshot = capture_snapshot(&snapshot_request(&root)).expect("R2 diagnostic snapshot");
        let request = NormalizeRequest {
            root: root.clone(),
            profile: "parent".to_string(),
            snapshot_jsonl: PathBuf::from("-"),
            evidence_jsonl: Vec::new(),
            relation_registry_json: PathBuf::from("relation-registry.v1.json"),
            output_jsonl: PathBuf::from("-"),
        };
        let records = normalize_snapshot(
            &request,
            snapshot,
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("R2 diagnostics");
        let reasons = records
            .ambiguities
            .iter()
            .map(|ambiguity| ambiguity.reason_code.as_str())
            .collect::<BTreeSet<_>>();
        assert!(reasons.contains("missing_target"));
        assert!(reasons.contains("stale_target"));
        assert!(reasons.contains("source_excluded_target"));
        assert!(records.relations.is_empty());
        assert_eq!(records.summary.accepted_fact_count, 0);
        assert!(records
            .ambiguities
            .iter()
            .all(|ambiguity| !ambiguity.covered));
        assert!(records
            .declarations
            .iter()
            .all(
                |declaration| records.attestations.iter().any(|attestation| attestation
                    .evidence_id
                    == declaration.declaration_id
                    && !attestation.accepted
                    && attestation.rejection_reason
                        == records
                            .ambiguities
                            .iter()
                            .find(|ambiguity| ambiguity
                                .evidence_ids
                                .contains(&declaration.declaration_id))
                            .expect("declaration ambiguity")
                            .reason_code)
            ));
        assert_eq!(
            records.summary.record_counts["unresolved_count"],
            records.ambiguities.len()
        );
        assert_eq!(
            records.summary.record_counts["excluded_count"],
            records.source_exclusions.len()
        );
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[cfg(unix)]
    #[test]
    fn r2_ambiguity_provenance_is_bidirectionally_closed() {
        let fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-ambiguity-closure-mutations")
            .expect("ambiguity closure fixture");
        let (root, outside_target) = source_universe_git_repo();
        let accepted_snapshot = capture_snapshot(&snapshot_request(&root)).expect("D snapshot");
        let accepted_records = normalize_snapshot(
            &NormalizeRequest {
                root: root.clone(),
                profile: "parent".to_string(),
                snapshot_jsonl: PathBuf::from("-"),
                evidence_jsonl: Vec::new(),
                relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                output_jsonl: PathBuf::from("-"),
            },
            accepted_snapshot,
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("accepted D normalization");
        let accepted_declaration = accepted_records
            .declarations
            .first()
            .expect("accepted declaration")
            .clone();
        assert!(accepted_records.ambiguities.is_empty());

        fs::write(
            root.join("tracked.txt"),
            "# @dependency-start\n# contract implementation\n# responsibility Provides the fixture manifest.\n# upstream implementation missing.txt unresolved fixture target\n# @dependency-end\n",
        )
        .expect("missing-target manifest");
        let rejected_snapshot = capture_snapshot(&snapshot_request(&root)).expect("A snapshot");
        let rejected_records = normalize_snapshot(
            &NormalizeRequest {
                root: root.clone(),
                profile: "parent".to_string(),
                snapshot_jsonl: PathBuf::from("-"),
                evidence_jsonl: Vec::new(),
                relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                output_jsonl: PathBuf::from("-"),
            },
            rejected_snapshot,
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("rejected D normalization");
        let rejected_ambiguity = rejected_records
            .ambiguities
            .iter()
            .find(|ambiguity| ambiguity.reason_code == "missing_target")
            .expect("missing-target ambiguity")
            .clone();
        let mut executed = BTreeSet::new();
        for mutation in fixture_strings(&fixture, "mutations") {
            let mut tampered = if mutation == "accepted" {
                let mut records = accepted_records.clone();
                records.ambiguities.push(ambiguity_for_declaration(
                    &accepted_declaration,
                    "missing_target",
                    &[],
                    std::slice::from_ref(&accepted_declaration.declared_target),
                    "design",
                ));
                records
            } else {
                rejected_records.clone()
            };
            if mutation != "accepted" {
                let index = tampered
                    .ambiguities
                    .iter()
                    .position(|ambiguity| ambiguity.ambiguity_id == rejected_ambiguity.ambiguity_id)
                    .expect("mutation ambiguity");
                let (reason, candidate_fact_ids, candidate_targets) = match mutation.as_str() {
                    "wrong-reason" => (
                        "stale_target",
                        rejected_ambiguity.candidate_fact_ids.clone(),
                        rejected_ambiguity.candidate_targets.clone(),
                    ),
                    "wrong-candidate" => (
                        "missing_target",
                        rejected_ambiguity.candidate_fact_ids.clone(),
                        vec!["wrong-candidate-target".to_string()],
                    ),
                    "ghost-fact" => (
                        "missing_target",
                        vec!["f".repeat(64)],
                        rejected_ambiguity.candidate_targets.clone(),
                    ),
                    other => panic!("unknown ambiguity closure mutation {other}"),
                };
                tampered.ambiguities[index] = ambiguity_record(
                    &rejected_ambiguity.snapshot_id,
                    &rejected_ambiguity.source_identity_id,
                    candidate_fact_ids,
                    candidate_targets,
                    reason,
                    &rejected_ambiguity.relation_kind,
                    rejected_ambiguity.evidence_ids.clone(),
                );
            }
            refresh_normalized_summary(&mut tampered);
            let error = read_normalized_record_set(
                Cursor::new(unchecked_normalized_bytes(&tampered)),
                &tampered.header.snapshot_id,
                &builtin_relation_registry_artifact().expect("builtin registry"),
            )
            .expect_err("A closure mutation accepted");
            assert!(matches!(error, ManifestError::Transport(_)));
            let expected_error = if matches!(mutation.as_str(), "accepted" | "wrong-reason") {
                "ambiguity evidence must reference a rejected attestation with the exact reason"
            } else {
                "ambiguity reason/source/candidate/fact closure is not exact"
            };
            assert!(
                error.to_string().contains(expected_error),
                "{mutation}: unexpected A closure error: {error}"
            );
            executed.insert(mutation);
        }
        assert_eq!(
            executed,
            fixture_strings(&fixture, "mutations")
                .into_iter()
                .collect::<BTreeSet<_>>()
        );
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_file(outside_target);
    }

    #[cfg(unix)]
    #[test]
    fn r2_declaration_endpoints_require_u_and_retain_source_diagnostics() {
        let fixture = RELATION_FIXTURE
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).expect("relation fixture"))
            .find(|case| case["case"] == "r2-declaration-endpoint-u-adversaries")
            .expect("declaration endpoint fixture");
        let fixture_cases = fixture_strings(&fixture, "cases")
            .into_iter()
            .collect::<BTreeSet<_>>();
        assert_eq!(
            fixture_cases,
            BTreeSet::from([
                "excluded-source".to_string(),
                "stale-source".to_string(),
                "nonexistent-source".to_string(),
            ])
        );

        for (case_name, excluded_source, expected_reason) in [
            ("excluded-source", true, "source_excluded_source"),
            ("stale-source", false, "stale_source"),
            ("nonexistent-source", false, "unresolved_source"),
        ] {
            let (root, outside_target) = source_universe_git_repo();
            if case_name == "stale-source" {
                fs::remove_file(root.join("delete.txt")).expect("stale source deletion");
            }
            let mut snapshot = capture_snapshot(&snapshot_request(&root)).expect("D snapshot");
            let source_path = if excluded_source {
                ".agent-canon/knowledge-graph/graph.sqlite"
            } else if case_name == "nonexistent-source" {
                "missing-source.txt"
            } else {
                "delete.txt"
            };
            let source = if case_name == "nonexistent-source" {
                let mut source = test_identity(source_path);
                source.identity_id = hash_parts(&[
                    "source_identity.v1",
                    &snapshot.header.parent_repo_id,
                    source_path,
                ]);
                source.logical_id = hash_parts(&[
                    "logical_source.v1",
                    &snapshot.header.parent_repo_id,
                    source_path,
                ]);
                source.snapshot_id = snapshot.header.snapshot_id.clone();
                source
            } else {
                source_identity(&snapshot, source_path).clone()
            };
            let target = source_identity(&snapshot, "modify.txt").clone();
            let declaration = snapshot
                .declarations
                .first_mut()
                .expect("fixture declaration");
            declaration.source_identity_id = source.identity_id.clone();
            declaration.source_span.path = source.repo_rel_path.clone();
            declaration.resolved_target_identity_id = Some(target.identity_id.clone());
            let start_line = declaration.source_span.start_line.to_string();
            let end_line = declaration.source_span.end_line.to_string();
            declaration.declaration_id = hash_parts(&[
                "dependency_declaration.v1",
                &declaration.source_identity_id,
                &start_line,
                &end_line,
                &declaration.declared_direction,
                &declaration.declared_kind,
                &declaration.declared_target,
                &declaration.raw_line_hash,
            ]);
            declaration.attestation_key = hash_parts(&[
                "dependency_attestation.v1",
                &snapshot.header.snapshot_id,
                &declaration.source_identity_id,
                &start_line,
                &end_line,
                &declaration.declared_direction,
                &declaration.declared_kind,
                &declaration.declared_target,
                &declaration.raw_line_hash,
            ]);
            let records = normalize_snapshot(
                &NormalizeRequest {
                    root: root.clone(),
                    profile: "parent".to_string(),
                    snapshot_jsonl: PathBuf::from("D-adversary-snapshot.v1.jsonl"),
                    evidence_jsonl: Vec::new(),
                    relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                    output_jsonl: PathBuf::from("-"),
                },
                snapshot,
                &builtin_relation_registry_artifact().expect("builtin registry"),
            )
            .expect("D endpoint diagnostic normalization");
            let attestation = records
                .attestations
                .iter()
                .find(|attestation| attestation.evidence_type == "declaration")
                .expect("declaration attestation");
            assert!(!attestation.accepted, "{case_name}: declaration accepted");
            assert_eq!(attestation.rejection_reason, expected_reason);
            assert!(records.relations.is_empty(), "{case_name}: fact emitted");
            assert!(records.ambiguities.iter().any(|ambiguity| {
                ambiguity.reason_code == expected_reason
                    && ambiguity.evidence_ids.contains(&attestation.evidence_id)
                    && !ambiguity.covered
            }));
            assert_eq!(
                records.ambiguities.len(),
                1,
                "{case_name}: normalized A count"
            );
            assert_eq!(records.summary.record_counts["unresolved_count"], 1);
            let _ = fs::remove_dir_all(root);
            let _ = fs::remove_file(outside_target);
        }

        let source = test_identity("missing-source");
        let target = test_identity("target");
        let identities = BTreeMap::from([(target.identity_id.as_str(), &target)]);
        let declaration = DependencyDeclaration {
            declaration_id: "D-missing-source".to_string(),
            source_identity_id: source.identity_id.clone(),
            declared_direction: "upstream".to_string(),
            declared_kind: "design".to_string(),
            declared_target: target.repo_rel_path.clone(),
            resolved_target_identity_id: Some(target.identity_id.clone()),
            source_span: SourceSpan {
                path: source.repo_rel_path.clone(),
                start_line: 1,
                start_column: 1,
                end_line: 1,
                end_column: 2,
            },
            reason: "missing source".to_string(),
            raw_line_hash: hash_parts(&["missing-source"]),
            attestation_key: hash_parts(&["missing-source-attestation"]),
            snapshot_id: "snapshot".to_string(),
        };
        let (dependent, prerequisite, rejection) =
            declaration_endpoints(&declaration, &identities, &BTreeSet::new());
        assert_eq!(dependent.as_deref(), Some("missing-source"));
        assert_eq!(prerequisite.as_deref(), Some("target"));
        assert_eq!(rejection.as_deref(), Some("unresolved_source"));
        let ambiguity = ambiguity_for_declaration(
            &declaration,
            rejection.as_deref().expect("source rejection"),
            &[],
            &[declaration.declared_target.clone()],
            "design",
        );
        assert_eq!(ambiguity.evidence_ids, vec![declaration.declaration_id]);
        assert!(ambiguity.candidate_fact_ids.is_empty());
        assert!(fixture_cases.contains("nonexistent-source"));
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
            if matches!(
                record_type,
                "dependency_declaration.v1" | "surface_relation.v1"
            ) {
                let mut family = tampered
                    .iter()
                    .filter(|value| value["record_type"] == record_type)
                    .cloned()
                    .collect::<Vec<_>>();
                family.sort_by(|left, right| {
                    left["record_id"].as_str().cmp(&right["record_id"].as_str())
                });
                let mut family = family.into_iter();
                for value in tampered
                    .iter_mut()
                    .filter(|value| value["record_type"] == record_type)
                {
                    *value = family.next().expect("sorted family row");
                }
            }
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
        let mut family = tampered
            .iter()
            .filter(|value| value["record_type"] == "surface_relation.v1")
            .cloned()
            .collect::<Vec<_>>();
        family.sort_by(|left, right| left["record_id"].as_str().cmp(&right["record_id"].as_str()));
        let mut family = family.into_iter();
        for value in tampered
            .iter_mut()
            .filter(|value| value["record_type"] == "surface_relation.v1")
        {
            *value = family.next().expect("sorted surface relation row");
        }
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
        let fixture: Value = CLOSURE_FIXTURE
            .lines()
            .map(|line| serde_json::from_str(line).expect("closure fixture"))
            .find(|case: &Value| case["case"] == "r2-atomic-candidate-failure")
            .expect("atomic fixture");
        let root = unique_temp_path("agent-canon-r1-atomic");
        fs::create_dir_all(&root).expect("atomic fixture root");
        let output = root.join("source_snapshot.v1.jsonl");
        let candidate = root.join(format!(
            ".source_snapshot.v1.jsonl.{}.candidate",
            std::process::id()
        ));
        for failure in fixture["failure_points"]
            .as_array()
            .expect("atomic failure points")
            .iter()
            .map(|failure| match failure.as_str().expect("atomic failure") {
                "write" => AtomicFailurePoint::Write,
                "sync" => AtomicFailurePoint::Sync,
                "rename" => AtomicFailurePoint::Rename,
                other => panic!("unknown atomic failure {other}"),
            })
        {
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

    fn normalized_values(records: &NormalizedRecordSet) -> Vec<Value> {
        let mut bytes = Vec::new();
        write_normalized_record_set(
            records,
            &builtin_relation_registry_artifact().expect("builtin registry"),
            &mut bytes,
        )
        .expect("normalized JSONL");
        String::from_utf8(bytes)
            .expect("UTF-8 normalized JSONL")
            .lines()
            .map(|line| serde_json::from_str(line).expect("normalized record"))
            .collect()
    }

    fn first_normalized_payload_mut<'a>(
        values: &'a mut [Value],
        record_type: &str,
    ) -> &'a mut Value {
        values
            .iter_mut()
            .find(|value| value["record_type"] == record_type)
            .map(|value| &mut value["payload"])
            .expect("normalized family payload")
    }

    fn unchecked_normalized_bytes(records: &NormalizedRecordSet) -> Vec<u8> {
        let mut bytes = Vec::new();
        write_envelope(
            &mut bytes,
            "normalized_record_set_header.v1",
            &records.header.snapshot_id,
            &records.header.snapshot_id,
            normalized_header_payload(&records.header),
        )
        .expect("unchecked normalized header");
        for (record_type, record_id, payload) in normalized_record_values(records) {
            write_envelope(
                &mut bytes,
                &record_type,
                &record_id,
                &records.header.snapshot_id,
                payload,
            )
            .expect("unchecked normalized record");
        }
        write_envelope(
            &mut bytes,
            "normalization_summary.v1",
            &records.summary.snapshot_id,
            &records.header.snapshot_id,
            json!({
                "snapshot_id": records.summary.snapshot_id,
                "record_counts": records.summary.record_counts,
                "accepted_fact_count": records.summary.accepted_fact_count,
                "rejected_declaration_count": records.summary.rejected_declaration_count,
                "rejected_observation_count": records.summary.rejected_observation_count,
                "ambiguity_count": records.summary.ambiguity_count,
                "source_exclusion_count": records.summary.source_exclusion_count,
                "normalized_record_fingerprint": records.summary.normalized_record_fingerprint,
            }),
        )
        .expect("unchecked normalized summary");
        bytes
    }

    fn assert_normalized_transport_error(
        values: Vec<Value>,
        expected_snapshot_id: &str,
    ) -> ManifestError {
        let mut bytes = Vec::new();
        for value in values {
            serde_json::to_writer(&mut bytes, &value).expect("tampered normalized JSON");
            bytes.push(b'\n');
        }
        read_normalized_record_set(
            Cursor::new(bytes),
            expected_snapshot_id,
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect_err("tampered normalized transport accepted")
    }

    fn refresh_normalized_value_fingerprint(values: &mut [Value]) {
        let mut bytes = Vec::new();
        for value in values.iter().filter(|value| {
            !matches!(
                value["record_type"].as_str(),
                Some("normalized_record_set_header.v1" | "normalization_summary.v1")
            )
        }) {
            serde_json::to_writer(
                &mut bytes,
                &json!({
                    "record_type": value["record_type"],
                    "record_id": value["record_id"],
                    "payload": value["payload"],
                }),
            )
            .expect("refreshed normalized fingerprint record");
            bytes.push(0);
        }
        let fingerprint = sha256_bytes(&bytes);
        values.last_mut().expect("normalization summary")["payload"]
            ["normalized_record_fingerprint"] = Value::String(fingerprint);
    }

    fn fixture_strings(case: &Value, field: &str) -> Vec<String> {
        case.get(field)
            .and_then(Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .map(|value| value.as_str().expect("fixture string").to_string())
                    .collect()
            })
            .unwrap_or_default()
    }

    fn fixture_relations(case: &Value) -> Vec<NormalizedRelation> {
        case["direct_edges"]
            .as_array()
            .expect("direct edges")
            .iter()
            .enumerate()
            .map(|(index, edge)| {
                let edge = edge.as_array().expect("edge tuple");
                let from = edge[0].as_str().expect("edge from");
                let kind = edge[1].as_str().expect("edge kind");
                let to = edge[2].as_str().expect("edge to");
                test_relation(
                    from,
                    to,
                    kind,
                    &hash_parts(&["fixture-fact", &index.to_string(), from, kind, to]),
                )
            })
            .collect()
    }

    fn all_permutations<T: Clone>(values: &[T]) -> Vec<Vec<T>> {
        if values.is_empty() {
            return vec![Vec::new()];
        }
        let mut result = Vec::new();
        for index in 0..values.len() {
            let mut remaining = values.to_vec();
            let head = remaining.remove(index);
            for mut tail in all_permutations(&remaining) {
                let mut permutation = vec![head.clone()];
                permutation.append(&mut tail);
                result.push(permutation);
            }
        }
        result
    }

    fn connected_capability(
        capability_id: &str,
        extractor_id: &str,
        extractor_version: &str,
        relation_kinds: &[&str],
    ) -> ExtractorCapability {
        ExtractorCapability {
            capability_id: capability_id.to_string(),
            extractor_id: extractor_id.to_string(),
            extractor_version: extractor_version.to_string(),
            relation_kinds: relation_kinds
                .iter()
                .map(|kind| (*kind).to_string())
                .collect(),
            input_scope: "connected:explicit-evidence-input".to_string(),
            supported_file_kinds: vec!["text".to_string()],
            unsupported_behavior: "unsupported-and-unresolved-to-A".to_string(),
            dynamic_behavior: "dynamic-reflection-to-A".to_string(),
            provenance_fields: vec![
                "payload_hash".to_string(),
                "snapshot_id".to_string(),
                "source_span".to_string(),
            ],
            completeness_claim:
                "connected; supplied-records-complete; semantic-completeness-not-claimed"
                    .to_string(),
        }
    }

    fn test_observation(
        snapshot_id: &str,
        from: &SourceIdentity,
        to: &SourceIdentity,
        observation_suffix: char,
        capability_id: &str,
        extractor_id: &str,
        extractor_version: &str,
        relation_kind: &str,
        classification: &str,
    ) -> ObservedEvidence {
        ObservedEvidence {
            observation_id: format!("O-{}", observation_suffix.to_string().repeat(64)),
            extractor_id: extractor_id.to_string(),
            extractor_version: extractor_version.to_string(),
            capability_id: capability_id.to_string(),
            relation_kind: relation_kind.to_string(),
            from_locator: from.canonical_locator.clone(),
            to_locator: to.canonical_locator.clone(),
            from_identity_id: from.identity_id.clone(),
            to_identity_id: to.identity_id.clone(),
            source_span: SourceSpan {
                path: from.repo_rel_path.clone(),
                start_line: 1,
                start_column: 1,
                end_line: 1,
                end_column: 2,
            },
            payload_hash: observation_suffix.to_string().repeat(64),
            classification: classification.to_string(),
            accepted: true,
            snapshot_id: snapshot_id.to_string(),
        }
    }

    fn write_evidence_input(
        snapshot_id: &str,
        capabilities: &[ExtractorCapability],
        observations: &[ObservedEvidence],
        prefix: &str,
    ) -> PathBuf {
        let path = unique_temp_path(prefix);
        let mut bytes = Vec::new();
        for capability in capabilities {
            write_envelope(
                &mut bytes,
                "extractor_capability.v1",
                &capability.capability_id,
                snapshot_id,
                capability_payload(capability),
            )
            .expect("capability evidence");
        }
        for observation in observations {
            write_envelope(
                &mut bytes,
                "observed_evidence.v1",
                &observation.observation_id,
                snapshot_id,
                observed_evidence_payload(observation),
            )
            .expect("observation evidence");
        }
        fs::write(&path, bytes).expect("evidence input");
        path
    }

    fn normalize_with_evidence(
        root: &Path,
        snapshot: ManifestSnapshot,
        evidence_path: PathBuf,
    ) -> NormalizedRecordSet {
        normalize_snapshot(
            &NormalizeRequest {
                root: root.to_path_buf(),
                profile: "parent".to_string(),
                snapshot_jsonl: PathBuf::from("-"),
                evidence_jsonl: vec![evidence_path],
                relation_registry_json: PathBuf::from("relation-registry.v1.json"),
                output_jsonl: PathBuf::from("-"),
            },
            snapshot,
            &builtin_relation_registry_artifact().expect("builtin registry"),
        )
        .expect("fixture normalization")
    }

    fn refresh_normalized_summary(records: &mut NormalizedRecordSet) {
        records.summary.record_counts = normalized_record_counts(records);
        records.summary.accepted_fact_count = records.relations.len();
        records.summary.rejected_declaration_count = records
            .attestations
            .iter()
            .filter(|attestation| {
                attestation.evidence_type == "declaration" && !attestation.accepted
            })
            .count();
        records.summary.rejected_observation_count = records
            .attestations
            .iter()
            .filter(|attestation| {
                attestation.evidence_type == "observation" && !attestation.accepted
            })
            .count();
        records.summary.ambiguity_count = records.ambiguities.len();
        records.summary.source_exclusion_count = records.source_exclusions.len();
        records.summary.normalized_record_fingerprint =
            normalized_record_fingerprint(records).expect("refreshed normalized fingerprint");
    }

    fn test_identity(path: &str) -> SourceIdentity {
        SourceIdentity {
            identity_id: path.to_string(),
            logical_id: path.to_string(),
            repo_rel_path: path.to_string(),
            canonical_locator: path.to_string(),
            alternate_locators: Vec::new(),
            locator_kind: "regular_file".to_string(),
            path_role: "source".to_string(),
            file_mode: "100644".to_string(),
            exists: true,
            is_dirty: false,
            content_hash: hash_parts(&["content", path]),
            git_blob_or_gitlink: hash_parts(&["blob", path]),
            submodule_commit: String::new(),
            snapshot_id: String::new(),
            owner_class: "test".to_string(),
            surface_mode: "regular".to_string(),
        }
    }

    fn test_relation(
        from_identity_id: &str,
        to_identity_id: &str,
        relation_kind: &str,
        fact_id: &str,
    ) -> NormalizedRelation {
        NormalizedRelation {
            fact_id: fact_id.to_string(),
            from_identity_id: from_identity_id.to_string(),
            to_identity_id: to_identity_id.to_string(),
            relation_kind: relation_kind.to_string(),
            semantic_direction: "depends_on".to_string(),
            pair_identity: "pair".to_string(),
            attestation_ids: vec![format!("attestation-{fact_id}")],
            observation_ids: Vec::new(),
            authority: "test".to_string(),
            accepted: true,
            reconciliation_status: "not_comparable".to_string(),
            source_snapshot_id: "snapshot".to_string(),
            source_content_hashes: vec!["source-a".to_string(), "source-b".to_string()],
        }
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

    fn canonical_registry_bytes(registry: &RelationRegistryArtifactV1) -> Vec<u8> {
        serde_json::to_vec(&json!({
            "entries": relation_registry_entries_value(&registry.entries),
            "registry_fingerprint": registry.registry_fingerprint,
            "registry_version": registry.registry_version,
        }))
        .expect("canonical registry bytes")
        .into_iter()
        .chain([b'\n'])
        .collect()
    }

    fn duplicate_json_field(raw: &[u8], field: &str, value: Value, occurrence: usize) -> Vec<u8> {
        let mut object = Map::new();
        object.insert(field.to_string(), value);
        let encoded_object = serde_json::to_vec(&Value::Object(object)).expect("JSON field bytes");
        let encoded_field = &encoded_object[1..encoded_object.len() - 1];
        let positions = raw
            .windows(encoded_field.len())
            .enumerate()
            .filter_map(|(index, candidate)| (candidate == encoded_field).then_some(index))
            .collect::<Vec<_>>();
        let position = *positions
            .get(occurrence)
            .unwrap_or_else(|| panic!("missing {field} occurrence {occurrence}"));
        let mut mutated = Vec::with_capacity(raw.len() + encoded_field.len() + 1);
        mutated.extend_from_slice(&raw[..position]);
        mutated.extend_from_slice(encoded_field);
        mutated.push(b',');
        mutated.extend_from_slice(&raw[position..]);
        mutated
    }

    fn replace_first_bytes(raw: &[u8], needle: &[u8], replacement: &[u8]) -> Vec<u8> {
        let position = raw
            .windows(needle.len())
            .position(|candidate| candidate == needle)
            .expect("replacement needle");
        let mut replaced = Vec::with_capacity(raw.len() + replacement.len() - needle.len());
        replaced.extend_from_slice(&raw[..position]);
        replaced.extend_from_slice(replacement);
        replaced.extend_from_slice(&raw[position + needle.len()..]);
        replaced
    }

    fn noncanonical_envelope_bytes(value: &Value) -> Vec<u8> {
        let object = value.as_object().expect("envelope object");
        let mut bytes = vec![b'{'];
        for (index, field) in [
            "record_id",
            "payload",
            "record_type",
            "schema_version",
            "snapshot_id",
        ]
        .iter()
        .enumerate()
        {
            if index > 0 {
                bytes.push(b',');
            }
            bytes.extend_from_slice(
                &serde_json::to_vec(&Value::String((*field).to_string()))
                    .expect("envelope field name"),
            );
            bytes.push(b':');
            bytes.extend_from_slice(
                &serde_json::to_vec(object.get(*field).expect("envelope field"))
                    .expect("envelope field value"),
            );
        }
        bytes.extend_from_slice(b"}\n");
        bytes
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
        fs::write(root.join(".gitignore"), "ignored.txt\ninside-target.txt\n").expect("gitignore");
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
