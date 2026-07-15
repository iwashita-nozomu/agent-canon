// @dependency-start
// contract implementation
// responsibility Owns the parent-scoped AgentCanon graph build, status, query, and context operations.
// upstream design ../../../reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_brief.md approved graph responsibility contract
// upstream implementation dependency_manifest.rs provides the sole complete-file manifest parser and source snapshot
// upstream implementation structured_analysis.rs provides the Graph DSL schema and validator
// upstream implementation semantic_index.rs provides bounded optional context evidence
// downstream implementation main.rs dispatches the public graph command
// downstream implementation ../../../tools/agent_tools/graph_client.py consumes the canonical JSON schemas
// @dependency-end

use crate::dependency_manifest::{
    capture_snapshot, snapshot_agent_canon_pin, snapshot_dirty_fingerprint, snapshot_fingerprint,
    snapshot_head, snapshot_profile, snapshot_source_scope_counts,
    source_path_is_explicitly_excluded, write_snapshot_jsonl, DependencyDeclaration, ManifestError,
    ManifestSnapshot, SnapshotRequest, SourceSpan, SourceUniverse,
};
use crate::structured_analysis::{initialize_graph_schema, validate_graph_connection};
use rusqlite::{params, Connection};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

const GRAPH_SCHEMA_VERSION: &str = "graph_storage_core.v1";
const PUBLIC_PROFILE: &str = "default";
const SOURCE_PROFILE: &str = "parent";
const GRAPH_RELATION_KINDS: &[&str] = &[
    "dependency",
    "owner",
    "scope",
    "import",
    "include",
    "symbol",
    "call",
    "containment",
    "document",
    "catalog",
    "pin",
    "view",
    "generated",
    "submodule",
    "public",
];
const SCANNER_SUFFIXES: &[&str] = &[
    ".py", ".c", ".cc", ".cpp", ".h", ".hpp", ".sh", ".bash", ".zsh",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum GraphDirection {
    Outgoing,
    Incoming,
    Both,
}

impl GraphDirection {
    fn as_str(self) -> &'static str {
        match self {
            Self::Outgoing => "outgoing",
            Self::Incoming => "incoming",
            Self::Both => "both",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum GraphBuildFailurePoint {
    None,
    Producer,
    Validation,
    Write,
    Sync,
    Rename,
    DirectorySync,
}

#[derive(Debug, Clone)]
struct GraphBuildArgs {
    root: PathBuf,
    profile: String,
    format: OutputFormat,
}

type GraphStatusArgs = GraphBuildArgs;

#[derive(Debug, Clone)]
struct GraphQueryArgs {
    root: PathBuf,
    profile: String,
    format: OutputFormat,
    path: Option<String>,
    all: bool,
    relation: String,
    direction: GraphDirection,
    depth: u8,
}

#[derive(Debug, Clone)]
struct GraphContextArgs {
    root: PathBuf,
    profile: String,
    format: OutputFormat,
    path: String,
    token: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
struct ProducerArtifact {
    producer_id: String,
    version: String,
    command: String,
    root: String,
    content_sha256: String,
    relation_families: Vec<String>,
    artifact_ref: String,
    payload: Vec<u8>,
}

impl ProducerArtifact {
    fn json(&self) -> Value {
        json!({
            "producer_id": self.producer_id,
            "version": self.version,
            "command": self.command,
            "root": self.root,
            "content_sha256": self.content_sha256,
            "relation_families": self.relation_families,
            "artifact_ref": self.artifact_ref,
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
struct GraphFact {
    id: String,
    layer: String,
    kind: String,
    from: String,
    to: Option<String>,
    owner: Option<String>,
    source_path: Option<String>,
    source_span: Option<SourceSpan>,
    producer: String,
    evidence_ref: String,
    authority: String,
    inferred: bool,
    dependency_detail: Option<Value>,
    payload: Value,
}

impl GraphFact {
    fn json(&self) -> Value {
        json!({
            "id": self.id,
            "layer": self.layer,
            "kind": self.kind,
            "from": self.from,
            "to": self.to,
            "owner": self.owner,
            "source_path": self.source_path,
            "source_span": self.source_span.as_ref().map(source_span_json),
            "producer": self.producer,
            "evidence_ref": self.evidence_ref,
            "authority": self.authority,
            "inferred": self.inferred,
            "dependency_detail": self.dependency_detail,
            "payload": self.payload,
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
struct GraphDiagnostic {
    id: String,
    set: String,
    code: String,
    severity: String,
    relation: Option<String>,
    path: Option<String>,
    target: Option<String>,
    source_span: Option<SourceSpan>,
    reason: String,
    producer: String,
    evidence_ref: String,
    suggested_action_json: String,
}

impl GraphDiagnostic {
    fn json(&self) -> Value {
        json!({
            "id": self.id,
            "set": self.set,
            "scope": diagnostic_scope(self),
            "code": self.code,
            "severity": self.severity,
            "relation": self.relation,
            "path": self.path,
            "target": self.target,
            "source_span": self.source_span.as_ref().map(source_span_json),
            "reason": self.reason,
            "producer": self.producer,
            "evidence_ref": self.evidence_ref,
            "suggested_action_json": self.suggested_action_json,
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
struct SourceNode {
    id: String,
    selector: String,
    path: Option<String>,
    source_member: bool,
    source_span: Option<SourceSpan>,
    payload: Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum RelationKind {
    Dependency,
    Owner,
    Scope,
    Import,
    Include,
    Symbol,
    Call,
    Containment,
    Document,
    Catalog,
    Pin,
    View,
    Generated,
    Submodule,
    Public,
}

impl RelationKind {
    fn parse(value: &str) -> Result<Self, GraphError> {
        match value {
            "dependency" => Ok(Self::Dependency),
            "owner" => Ok(Self::Owner),
            "scope" => Ok(Self::Scope),
            "import" => Ok(Self::Import),
            "include" => Ok(Self::Include),
            "symbol" => Ok(Self::Symbol),
            "call" => Ok(Self::Call),
            "containment" => Ok(Self::Containment),
            "document" => Ok(Self::Document),
            "catalog" => Ok(Self::Catalog),
            "pin" => Ok(Self::Pin),
            "view" => Ok(Self::View),
            "generated" => Ok(Self::Generated),
            "submodule" => Ok(Self::Submodule),
            "public" => Ok(Self::Public),
            _ => Err(GraphError::Validation {
                stage: "relation-kind".to_string(),
                reason: format!("relation kind is outside the closed registry: {value}"),
            }),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Dependency => "dependency",
            Self::Owner => "owner",
            Self::Scope => "scope",
            Self::Import => "import",
            Self::Include => "include",
            Self::Symbol => "symbol",
            Self::Call => "call",
            Self::Containment => "containment",
            Self::Document => "document",
            Self::Catalog => "catalog",
            Self::Pin => "pin",
            Self::View => "view",
            Self::Generated => "generated",
            Self::Submodule => "submodule",
            Self::Public => "public",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct TypedRelation {
    id: String,
    kind: RelationKind,
    from: String,
    to: String,
    producer: String,
    evidence_ref: String,
    inferred: bool,
}

impl TypedRelation {
    fn from_fact(fact: &GraphFact) -> Result<Self, GraphError> {
        let to = fact.to.clone().ok_or_else(|| GraphError::Validation {
            stage: "relation-totality".to_string(),
            reason: format!("accepted relation {} has no target", fact.id),
        })?;
        Ok(Self {
            id: fact.id.clone(),
            kind: RelationKind::parse(&fact.kind)?,
            from: fact.from.clone(),
            to,
            producer: fact.producer.clone(),
            evidence_ref: fact.evidence_ref.clone(),
            inferred: fact.inferred,
        })
    }

    fn json(&self) -> Value {
        json!({
            "id": self.id,
            "kind": self.kind.as_str(),
            "from": self.from,
            "to": self.to,
            "producer": self.producer,
            "evidence_ref": self.evidence_ref,
            "inferred": self.inferred,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct GraphContractWitness {
    candidate_sources: BTreeSet<String>,
    excluded_sources: BTreeSet<String>,
    eligible_sources: BTreeSet<String>,
    declarations: BTreeSet<String>,
    accepted_relations: BTreeSet<String>,
    graph_members: BTreeSet<String>,
    profile_members: BTreeSet<String>,
    relation_exclusions: BTreeSet<String>,
    unresolved: BTreeSet<String>,
    ambiguous: BTreeSet<String>,
    uncovered: BTreeSet<String>,
    source_identity: BTreeMap<String, String>,
    relation_endpoints: BTreeMap<String, TypedRelation>,
    reverse_projection: BTreeMap<String, String>,
}

impl GraphContractWitness {
    fn profile_complete(&self) -> bool {
        self.unresolved.is_empty() && self.ambiguous.is_empty() && self.uncovered.is_empty()
    }

    fn payload_json(&self) -> Value {
        let set = |values: &BTreeSet<String>| values.iter().cloned().collect::<Vec<_>>();
        json!({
            "schema": "agent-canon.graph.mathematical-contract.v1",
            "profile": PUBLIC_PROFILE,
            "finite_sets": {
                "P(S)": set(&self.candidate_sources),
                "X(S)": set(&self.excluded_sources),
                "U(S)": set(&self.eligible_sources),
                "D": set(&self.declarations),
                "R": set(&self.accepted_relations),
                "G": set(&self.graph_members),
                "Vp": set(&self.profile_members),
                "X_R(S,p)": set(&self.relation_exclusions),
                "Unresolved(S,p)": set(&self.unresolved),
                "Ambiguous(S,p)": set(&self.ambiguous),
                "Uncovered(S,p)": set(&self.uncovered),
            },
            "typed_functions": {
                "source_identity": self.source_identity,
                "relation_endpoints": self.relation_endpoints.values().map(TypedRelation::json).collect::<Vec<_>>(),
                "reverse_projection": self.reverse_projection,
            },
            "closure": {
                "operator": "F(Q)=Q union typed_successors(Q); mu F is obtained from bottom by finite monotone iteration",
                "reverse_edge_rule": "for each r in R there is exactly one reverse:r with swapped endpoints and identical kind/evidence",
            },
            "obligations": {
                "source_partition": true,
                "source_disjointness": true,
                "source_identity_total_unique": true,
                "relation_kind_closed": true,
                "relation_endpoints_total": true,
                "relation_producer_total": true,
                "reverse_projection_bijection": true,
                "exclusion_dominance": true,
                "declaration_representation_exact": true,
                "graph_materialization_exact": true,
                "profile_projection_subset": true,
                "profile_projection_exact": true,
                "unresolved_empty": self.unresolved.is_empty(),
                "ambiguous_empty": self.ambiguous.is_empty(),
                "uncovered_empty": self.uncovered.is_empty(),
                "profile_complete": self.profile_complete(),
                "fingerprint_preservation": true,
                "atomic_failure_preserves_old_state": true,
            },
        })
    }

    fn fingerprint(&self) -> String {
        hash_bytes(canonical_json(&self.payload_json()).as_bytes())
    }

    fn json(&self) -> Value {
        let mut value = self.payload_json();
        value.as_object_mut().expect("contract object").insert(
            "contract_fingerprint".to_string(),
            Value::String(self.fingerprint()),
        );
        value
    }
}

#[derive(Debug, Clone)]
struct GraphIntegrationRecord {
    root: String,
    db_path: String,
    profile: String,
    source_snapshot_profile: String,
    snapshot_head: String,
    input_fingerprint: String,
    graph_fingerprint: String,
    contract_fingerprint: String,
    producer_artifacts: Vec<ProducerArtifact>,
    verified: bool,
    verification_code: String,
}

impl GraphIntegrationRecord {
    fn json(&self) -> Value {
        json!({
            "schema": "agent-canon.graph.integration.v1",
            "root": self.root,
            "db_path": self.db_path,
            "schema_version": GRAPH_SCHEMA_VERSION,
            "profile": self.profile,
            "source_snapshot_profile": self.source_snapshot_profile,
            "snapshot_head": self.snapshot_head,
            "input_fingerprint": self.input_fingerprint,
            "graph_fingerprint": self.graph_fingerprint,
            "contract_fingerprint": self.contract_fingerprint,
            "producer_artifacts": self.producer_artifacts.iter().map(ProducerArtifact::json).collect::<Vec<_>>(),
            "verified": self.verified,
            "verification_code": self.verification_code,
        })
    }
}

#[derive(Debug)]
enum GraphError {
    Usage(String),
    Producer { producer: String, reason: String },
    Validation { stage: String, reason: String },
    CandidateWrite { reason: String },
    CandidateSync { reason: String },
    Rename { reason: String },
    DirectorySync { reason: String },
    Unavailable { reason: String },
}

impl fmt::Display for GraphError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Usage(reason)
            | Self::CandidateWrite { reason }
            | Self::CandidateSync { reason }
            | Self::Rename { reason }
            | Self::DirectorySync { reason }
            | Self::Unavailable { reason } => formatter.write_str(reason),
            Self::Producer { producer, reason } => write!(formatter, "{producer}: {reason}"),
            Self::Validation { stage, reason } => write!(formatter, "{stage}: {reason}"),
        }
    }
}

#[derive(Debug)]
struct CandidateHandle {
    dir: PathBuf,
    db: PathBuf,
}

struct GraphCandidateCleanup {
    dir: PathBuf,
}

impl GraphCandidateCleanup {
    fn new(dir: PathBuf) -> Self {
        Self { dir }
    }

    fn cleanup(&self) -> Result<(), GraphError> {
        if !self.dir.exists() {
            return Ok(());
        }
        fs::remove_dir_all(&self.dir).map_err(|error| GraphError::CandidateWrite {
            reason: format!("candidate cleanup {}: {error}", self.dir.display()),
        })
    }
}

impl Drop for GraphCandidateCleanup {
    fn drop(&mut self) {
        let _ = self.cleanup();
    }
}

struct TemporaryDirectory {
    path: PathBuf,
}

struct ArmedDirectoryCleanup {
    path: PathBuf,
    armed: bool,
}

impl ArmedDirectoryCleanup {
    fn new(path: PathBuf) -> Self {
        Self { path, armed: true }
    }

    fn disarm(&mut self) {
        self.armed = false;
    }
}

impl Drop for ArmedDirectoryCleanup {
    fn drop(&mut self) {
        if self.armed {
            let _ = fs::remove_dir_all(&self.path);
        }
    }
}

impl TemporaryDirectory {
    fn create(label: &str) -> Result<Self, GraphError> {
        let path = std::env::temp_dir().join(format!(
            "agent-canon-{label}-{}-{}",
            std::process::id(),
            now_nanos()
        ));
        fs::create_dir_all(&path).map_err(|error| GraphError::CandidateWrite {
            reason: format!("create temporary producer directory: {error}"),
        })?;
        Ok(Self { path })
    }
}

impl Drop for TemporaryDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}

#[derive(Debug)]
struct BuildMaterial {
    root: PathBuf,
    graph_root: PathBuf,
    candidate_dir: PathBuf,
    snapshot: ManifestSnapshot,
    nodes: Vec<SourceNode>,
    facts: Vec<GraphFact>,
    diagnostics: Vec<GraphDiagnostic>,
    contract: GraphContractWitness,
    producer_artifacts: Vec<ProducerArtifact>,
    input_fingerprint: String,
    graph_fingerprint: String,
    created_at: String,
}

pub(crate) fn run(args: &[String]) -> i32 {
    let Some(command) = args.first() else {
        emit_usage("missing graph command");
        return 2;
    };
    match command.as_str() {
        "build" => run_build(&args[1..]),
        "status" => run_status(&args[1..]),
        "query" => run_query(&args[1..]),
        "context" => run_context(&args[1..]),
        "help" | "--help" | "-h" => {
            print_usage();
            2
        }
        unknown => {
            emit_usage(&format!("unknown graph command {unknown}"));
            2
        }
    }
}

fn print_usage() {
    eprintln!(
        "usage: agent-canon graph build|status [--root PATH] [--profile default] [--format text|json] | query (--path REPO_PATH|--all) [--relation KIND|all] [--direction outgoing|incoming|both] [--depth 0..64] [--root PATH] [--profile default] [--format text|json] | context --path REPO_PATH [--token TOKEN] [--root PATH] [--profile default] [--format text|json]"
    );
}

fn emit_usage(reason: &str) {
    eprintln!("AGENT_CANON_GRAPH=fail");
    eprintln!("AGENT_CANON_GRAPH_ERROR=usage:{reason}");
    print_usage();
}

fn run_build(args: &[String]) -> i32 {
    let parsed = match parse_build_args(args) {
        Ok(value) => value,
        Err(error) => {
            emit_usage(&error.to_string());
            return 2;
        }
    };
    match build_graph(&parsed) {
        Ok(response) => emit_response(&response, parsed.format),
        Err(error) => {
            let response = build_failure_response(&parsed, &error);
            emit_response(&response, parsed.format)
        }
    }
}

fn run_status(args: &[String]) -> i32 {
    let parsed = match parse_build_args(args) {
        Ok(value) => value,
        Err(error) => {
            emit_usage(&error.to_string());
            return 2;
        }
    };
    match read_graph_status(&parsed) {
        Ok(response) => emit_response(&response, parsed.format),
        Err(error) => emit_response(&status_error_response(&parsed, &error), parsed.format),
    }
}

fn run_query(args: &[String]) -> i32 {
    let parsed = match parse_query_args(args) {
        Ok(value) => value,
        Err(error) => {
            emit_usage(&error.to_string());
            return 2;
        }
    };
    match query_graph(&parsed) {
        Ok(response) => emit_response(&response, parsed.format),
        Err(error) => emit_response(&query_error_response(&parsed, &error), parsed.format),
    }
}

fn run_context(args: &[String]) -> i32 {
    let parsed = match parse_context_args(args) {
        Ok(value) => value,
        Err(error) => {
            emit_usage(&error.to_string());
            return 2;
        }
    };
    match context_graph(&parsed) {
        Ok(response) => emit_response(&response, parsed.format),
        Err(error) => emit_response(&context_error_response(&parsed, &error), parsed.format),
    }
}

fn emit_response(response: &Value, format: OutputFormat) -> i32 {
    let exit_code = response
        .get("exit_code")
        .and_then(Value::as_u64)
        .unwrap_or(3) as i32;
    if format == OutputFormat::Json {
        println!("{}", canonical_json(response));
    } else {
        println!(
            "AGENT_CANON_GRAPH={} command={} status={}",
            if exit_code == 0 { "pass" } else { "fail" },
            response
                .get("command")
                .and_then(Value::as_str)
                .unwrap_or("unknown"),
            response
                .get("status")
                .and_then(Value::as_str)
                .unwrap_or("invalid"),
        );
        if let Some(reason) = response.get("reason").and_then(Value::as_str) {
            println!("AGENT_CANON_GRAPH_REASON={reason}");
        }
    }
    exit_code
}

fn parse_build_args(args: &[String]) -> Result<GraphBuildArgs, GraphError> {
    let mut root = PathBuf::from(".");
    let mut profile = PUBLIC_PROFILE.to_string();
    let mut format = OutputFormat::Text;
    let mut seen = BTreeSet::new();
    let mut index = 0;
    while index < args.len() {
        let flag = args[index].as_str();
        if !seen.insert(flag.to_string()) {
            return Err(GraphError::Usage(format!("repeated flag {flag}")));
        }
        match flag {
            "--root" => {
                root = PathBuf::from(next_value(args, &mut index, flag)?);
            }
            "--profile" => profile = next_value(args, &mut index, flag)?,
            "--format" => format = parse_format(&next_value(args, &mut index, flag)?)?,
            _ => return Err(GraphError::Usage(format!("unknown argument {flag}"))),
        }
        index += 1;
    }
    snapshot_profile_for_graph(&profile)?;
    Ok(GraphBuildArgs {
        root,
        profile,
        format,
    })
}

fn parse_query_args(args: &[String]) -> Result<GraphQueryArgs, GraphError> {
    let mut root = PathBuf::from(".");
    let mut profile = PUBLIC_PROFILE.to_string();
    let mut format = OutputFormat::Text;
    let mut path = None;
    let mut all = false;
    let mut relation = "all".to_string();
    let mut direction = GraphDirection::Both;
    let mut depth = None;
    let mut seen = BTreeSet::new();
    let mut index = 0;
    while index < args.len() {
        let flag = args[index].as_str();
        if !seen.insert(flag.to_string()) {
            return Err(GraphError::Usage(format!("repeated flag {flag}")));
        }
        match flag {
            "--root" => root = PathBuf::from(next_value(args, &mut index, flag)?),
            "--profile" => profile = next_value(args, &mut index, flag)?,
            "--format" => format = parse_format(&next_value(args, &mut index, flag)?)?,
            "--path" => path = Some(normalize_repo_path(&next_value(args, &mut index, flag)?)?),
            "--all" => all = true,
            "--relation" => relation = next_value(args, &mut index, flag)?,
            "--direction" => {
                direction = match next_value(args, &mut index, flag)?.as_str() {
                    "outgoing" => GraphDirection::Outgoing,
                    "incoming" => GraphDirection::Incoming,
                    "both" => GraphDirection::Both,
                    value => return Err(GraphError::Usage(format!("unknown direction {value}"))),
                }
            }
            "--depth" => {
                let value = next_value(args, &mut index, flag)?;
                depth = Some(
                    value
                        .parse::<u8>()
                        .map_err(|_| GraphError::Usage("--depth must be 0..64".to_string()))?,
                );
            }
            _ => return Err(GraphError::Usage(format!("unknown argument {flag}"))),
        }
        index += 1;
    }
    snapshot_profile_for_graph(&profile)?;
    if (path.is_some() as u8 + all as u8) != 1 {
        return Err(GraphError::Usage(
            "query requires exactly one --path or --all".to_string(),
        ));
    }
    if relation != "all" && !GRAPH_RELATION_KINDS.contains(&relation.as_str()) {
        return Err(GraphError::Usage(format!("unknown relation {relation}")));
    }
    let depth = depth.unwrap_or(if all { 0 } else { 1 });
    if depth > 64 || (all && depth != 0) {
        return Err(GraphError::Usage(
            "--all requires --depth 0 and depth must be 0..64".to_string(),
        ));
    }
    Ok(GraphQueryArgs {
        root,
        profile,
        format,
        path,
        all,
        relation,
        direction,
        depth,
    })
}

fn parse_context_args(args: &[String]) -> Result<GraphContextArgs, GraphError> {
    let mut root = PathBuf::from(".");
    let mut profile = PUBLIC_PROFILE.to_string();
    let mut format = OutputFormat::Text;
    let mut path = None;
    let mut token = None;
    let mut seen = BTreeSet::new();
    let mut index = 0;
    while index < args.len() {
        let flag = args[index].as_str();
        if !seen.insert(flag.to_string()) {
            return Err(GraphError::Usage(format!("repeated flag {flag}")));
        }
        match flag {
            "--root" => root = PathBuf::from(next_value(args, &mut index, flag)?),
            "--profile" => profile = next_value(args, &mut index, flag)?,
            "--format" => format = parse_format(&next_value(args, &mut index, flag)?)?,
            "--path" => path = Some(normalize_repo_path(&next_value(args, &mut index, flag)?)?),
            "--token" => token = Some(next_value(args, &mut index, flag)?),
            _ => return Err(GraphError::Usage(format!("unknown argument {flag}"))),
        }
        index += 1;
    }
    snapshot_profile_for_graph(&profile)?;
    let path = path.ok_or_else(|| GraphError::Usage("context requires --path".to_string()))?;
    Ok(GraphContextArgs {
        root,
        profile,
        format,
        path,
        token,
    })
}

fn next_value(args: &[String], index: &mut usize, flag: &str) -> Result<String, GraphError> {
    *index += 1;
    args.get(*index)
        .cloned()
        .ok_or_else(|| GraphError::Usage(format!("{flag} requires a value")))
}

fn parse_format(value: &str) -> Result<OutputFormat, GraphError> {
    match value {
        "text" => Ok(OutputFormat::Text),
        "json" => Ok(OutputFormat::Json),
        _ => Err(GraphError::Usage(format!("unknown format {value}"))),
    }
}

fn snapshot_profile_for_graph(profile: &str) -> Result<&'static str, GraphError> {
    if profile == PUBLIC_PROFILE {
        Ok(SOURCE_PROFILE)
    } else {
        Err(GraphError::Usage(format!(
            "unsupported graph profile {profile}"
        )))
    }
}

fn normalize_repo_path(value: &str) -> Result<String, GraphError> {
    if value.is_empty() || value.contains('\0') || value.contains('\\') {
        return Err(GraphError::Usage(
            "repository path is empty or malformed".to_string(),
        ));
    }
    let path = Path::new(value);
    if path.is_absolute() {
        return Err(GraphError::Usage(
            "repository path must be relative".to_string(),
        ));
    }
    let mut parts = Vec::new();
    for component in path.components() {
        match component {
            Component::Normal(part) => parts.push(part.to_string_lossy().to_string()),
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(GraphError::Usage(
                    "repository path escapes root".to_string(),
                ))
            }
        }
    }
    if parts.is_empty() {
        return Err(GraphError::Usage("repository path is empty".to_string()));
    }
    Ok(parts.join("/"))
}

fn resolve_root(path: &Path) -> Result<PathBuf, GraphError> {
    let root = fs::canonicalize(path).map_err(|error| GraphError::Unavailable {
        reason: format!("root {}: {error}", path.display()),
    })?;
    if !root.is_dir() {
        return Err(GraphError::Unavailable {
            reason: format!("root is not a directory: {}", root.display()),
        });
    }
    Ok(root)
}

fn canon_root(root: &Path) -> PathBuf {
    let vendored = root.join("vendor/agent-canon");
    if vendored.join("rust/agent-canon/Cargo.toml").is_file() {
        vendored
    } else {
        root.to_path_buf()
    }
}

fn graph_root(root: &Path) -> PathBuf {
    root.join(".agent-canon/knowledge-graph")
}

fn graph_db(root: &Path) -> PathBuf {
    graph_root(root).join("graph.sqlite")
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DurableGraphStateWitness {
    Missing,
    Present { content_sha256: String },
}

fn durable_graph_state(path: &Path) -> Result<DurableGraphStateWitness, GraphError> {
    if !path.exists() {
        return Ok(DurableGraphStateWitness::Missing);
    }
    if path.is_symlink() || !path.is_file() {
        return Err(GraphError::Validation {
            stage: "atomic-state".to_string(),
            reason: format!(
                "durable graph path is not a regular file: {}",
                path.display()
            ),
        });
    }
    let bytes = fs::read(path).map_err(|error| GraphError::Validation {
        stage: "atomic-state".to_string(),
        reason: format!("read durable graph state {}: {error}", path.display()),
    })?;
    Ok(DurableGraphStateWitness::Present {
        content_sha256: hash_bytes(&bytes),
    })
}

fn assert_durable_graph_state(
    path: &Path,
    expected: &DurableGraphStateWitness,
) -> Result<(), GraphError> {
    let observed = durable_graph_state(path)?;
    if &observed != expected {
        return Err(GraphError::Validation {
            stage: "atomic-old-state-invariance".to_string(),
            reason: format!(
                "failed graph transition changed durable state: expected {expected:?}, observed {observed:?}"
            ),
        });
    }
    Ok(())
}

fn build_graph(args: &GraphBuildArgs) -> Result<Value, GraphError> {
    build_graph_with_failure(args, GraphBuildFailurePoint::None)
}

fn build_graph_with_failure(
    args: &GraphBuildArgs,
    point: GraphBuildFailurePoint,
) -> Result<Value, GraphError> {
    let root = resolve_root(&args.root)?;
    let target = graph_db(&root);
    let old_state = durable_graph_state(&target)?;
    let result = (|| {
        let material = collect_build_material(args, point)?;
        let cleanup = GraphCandidateCleanup::new(material.candidate_dir.clone());
        let handle = match write_graph_candidate(&material, point) {
            Ok(value) => value,
            Err(error) => {
                cleanup.cleanup()?;
                return Err(error);
            }
        };
        if point == GraphBuildFailurePoint::Validation {
            cleanup.cleanup()?;
            return Err(GraphError::Validation {
                stage: "injected".to_string(),
                reason: "validation failure seam".to_string(),
            });
        }
        if let Err(error) = validate_graph_store(&handle.db, &material) {
            cleanup.cleanup()?;
            return Err(error);
        }
        let integration = integration_record(&material, true);
        let status = if material.contract.profile_complete() {
            "fresh"
        } else {
            "incomplete"
        };
        publish_graph(&material.graph_root, handle, point)?;
        Ok(build_response(
            &material,
            &integration,
            status,
            "published",
            "durable",
            None,
            None,
        ))
    })();
    if result.is_err() {
        assert_durable_graph_state(&target, &old_state)?;
    }
    result
}

fn collect_build_material(
    args: &GraphBuildArgs,
    point: GraphBuildFailurePoint,
) -> Result<BuildMaterial, GraphError> {
    collect_build_material_with_mode(args, point, false)
}

fn collect_build_material_with_mode(
    args: &GraphBuildArgs,
    point: GraphBuildFailurePoint,
    probe: bool,
) -> Result<BuildMaterial, GraphError> {
    let root = resolve_root(&args.root)?;
    let graph_root = graph_root(&root);
    let build_id =
        hash_bytes(format!("{}:{}:{}", root.display(), std::process::id(), now_nanos()).as_bytes());
    let candidate_dir = if probe {
        std::env::temp_dir().join(format!("agent-canon-graph-probe-{build_id}"))
    } else {
        fs::create_dir_all(graph_root.join(".candidate")).map_err(|error| {
            GraphError::CandidateWrite {
                reason: format!("create graph root: {error}"),
            }
        })?;
        graph_root.join(".candidate").join(build_id)
    };
    fs::create_dir_all(&candidate_dir).map_err(|error| GraphError::CandidateWrite {
        reason: format!("create candidate: {error}"),
    })?;
    let mut candidate_cleanup = ArmedDirectoryCleanup::new(candidate_dir.clone());
    let producer_workspace = TemporaryDirectory::create("graph-producers")?;
    if point == GraphBuildFailurePoint::Producer {
        return Err(GraphError::Producer {
            producer: "source-snapshot".to_string(),
            reason: "injected producer failure seam".to_string(),
        });
    }
    let snapshot_path = producer_workspace.path.join("source-snapshot.jsonl");
    let request = SnapshotRequest {
        root: root.clone(),
        profile: snapshot_profile_for_graph(&args.profile)?.to_string(),
        output_jsonl: snapshot_path.clone(),
    };
    let snapshot = capture_snapshot(&request).map_err(manifest_error)?;
    if snapshot_profile(&snapshot) != SOURCE_PROFILE {
        return Err(GraphError::Validation {
            stage: "source-snapshot-profile".to_string(),
            reason: format!(
                "expected {SOURCE_PROFILE}, observed {}",
                snapshot_profile(&snapshot)
            ),
        });
    }
    let mut snapshot_bytes = Vec::new();
    write_snapshot_jsonl(&snapshot, &mut snapshot_bytes).map_err(manifest_error)?;
    write_synced_file(&snapshot_path, &snapshot_bytes)?;
    let mut producer_artifacts = vec![ProducerArtifact {
        producer_id: "source-snapshot".to_string(),
        version: "source_snapshot.v1".to_string(),
        command: "dependency_manifest::capture_snapshot graph-profile=default profile=parent"
            .to_string(),
        root: ".".to_string(),
        content_sha256: hash_bytes(&snapshot_bytes),
        relation_families: vec![
            "dependency".to_string(),
            "pin".to_string(),
            "submodule".to_string(),
        ],
        artifact_ref: producer_artifact_ref(
            "source-snapshot",
            "source-snapshot.jsonl",
            &hash_bytes(&snapshot_bytes),
        ),
        payload: snapshot_bytes.clone(),
    }];
    let (mut nodes, mut facts, mut diagnostics) = snapshot_graph_records(&root, &snapshot)?;
    let catalog = capture_structure_and_public_surface(&root, &producer_workspace.path)?;
    producer_artifacts.extend(catalog.0);
    facts.extend(catalog.1);
    diagnostics.extend(catalog.2);
    let structured = capture_structured_analysis(&root, &producer_workspace.path)?;
    producer_artifacts.push(structured.0);
    facts.extend(structured.1);
    diagnostics.extend(structured.2);
    let responsibility = capture_responsibility_scope(&root)?;
    producer_artifacts.push(responsibility.0);
    facts.extend(responsibility.1);
    diagnostics.extend(responsibility.2);
    let import_policy = capture_import_responsibility(&root)?;
    producer_artifacts.push(import_policy.0);
    diagnostics.extend(import_policy.1);
    let runtime = capture_runtime_dashboard(&root, &producer_workspace.path)?;
    producer_artifacts.push(runtime);
    let scanner = capture_code_dependencies(&root, &producer_workspace.path, &snapshot)?;
    producer_artifacts.push(scanner.0);
    facts.extend(scanner.1);
    diagnostics.extend(scanner.2);
    apply_exclusion_dominance(&mut facts, &mut diagnostics, &snapshot.source_universe);
    canonicalize_build_records(
        &mut nodes,
        &mut facts,
        &mut diagnostics,
        &mut producer_artifacts,
    )?;
    bind_fact_endpoints(&mut nodes, &mut facts);
    add_reverse_projections(&mut facts)?;
    canonicalize_build_records(
        &mut nodes,
        &mut facts,
        &mut diagnostics,
        &mut producer_artifacts,
    )?;
    let contract =
        derive_graph_contract(&snapshot, &nodes, &facts, &diagnostics, &producer_artifacts)?;
    let input_fingerprint = graph_input_fingerprint(&snapshot, &producer_artifacts);
    let graph_fingerprint = graph_fingerprint(
        &input_fingerprint,
        &nodes,
        &facts,
        &diagnostics,
        &producer_artifacts,
        &contract,
    );
    let created_at = git_head_timestamp(&root)?;
    candidate_cleanup.disarm();
    Ok(BuildMaterial {
        root,
        graph_root,
        candidate_dir,
        snapshot,
        nodes,
        facts,
        diagnostics,
        contract,
        producer_artifacts,
        input_fingerprint,
        graph_fingerprint,
        created_at,
    })
}

fn manifest_error(error: ManifestError) -> GraphError {
    GraphError::Producer {
        producer: "source-snapshot".to_string(),
        reason: error.to_string(),
    }
}

fn snapshot_graph_records(
    _root: &Path,
    snapshot: &ManifestSnapshot,
) -> Result<(Vec<SourceNode>, Vec<GraphFact>, Vec<GraphDiagnostic>), GraphError> {
    let mut nodes = Vec::new();
    let mut facts = Vec::new();
    let mut diagnostics = Vec::new();
    let mut path_by_identity = BTreeMap::new();
    let excluded_by_identity = snapshot
        .source_exclusions
        .iter()
        .map(|exclusion| exclusion.source_identity_id.as_str())
        .collect::<BTreeSet<_>>();
    let excluded_paths = snapshot
        .source_exclusions
        .iter()
        .map(|exclusion| exclusion.repo_rel_path.as_str())
        .collect::<BTreeSet<_>>();
    let target_is_excluded = |target: &str| {
        excluded_paths.contains(target)
            || excluded_paths.contains(format!("vendor/agent-canon/{target}").as_str())
            || source_path_is_explicitly_excluded(target)
    };
    for identity in &snapshot.source_identities {
        path_by_identity.insert(identity.identity_id.clone(), identity.repo_rel_path.clone());
        if excluded_by_identity.contains(identity.identity_id.as_str()) {
            continue;
        }
        let manifest = snapshot.manifests.get(&identity.identity_id);
        let manifest_present = manifest.is_some();
        let contract = manifest.map(|value| value.contract.clone());
        let responsibility = manifest.map(|value| value.responsibility.clone());
        let manifest_span = manifest.and_then(|value| value.source_span.clone());
        let node_id = source_node_id(&identity.repo_rel_path);
        nodes.push(SourceNode {
            id: node_id,
            selector: identity.repo_rel_path.clone(),
            path: Some(identity.repo_rel_path.clone()),
            source_member: true,
            source_span: manifest_span.clone(),
            payload: json!({
                "path": identity.repo_rel_path,
                "selector": identity.repo_rel_path,
                "source_member": true,
                "content_sha256": identity.content_hash,
                "exists": identity.exists,
                "manifest_present": manifest_present,
                "manifest_contract": contract,
                "manifest_responsibility": responsibility,
                "manifest_source_span": manifest_span.as_ref().map(source_span_json),
                "producer": "source-snapshot",
                "authority": "ManifestParser",
                "evidence_ref": format!("source-snapshot:{}", identity.identity_id),
            }),
        });
        if !identity.exists {
            diagnostics.push(graph_diagnostic(
                "unresolved",
                "source.deleted",
                "warn",
                None,
                Some(&identity.repo_rel_path),
                None,
                None,
                "eligible source is deleted in the captured worktree",
                "source-snapshot",
                &format!("source-snapshot:{}", identity.identity_id),
            ));
        }
    }
    for exclusion in &snapshot.source_exclusions {
        diagnostics.push(graph_diagnostic(
            "excluded",
            "source.excluded",
            "info",
            None,
            Some(&exclusion.repo_rel_path),
            None,
            None,
            &format!("{} ({})", exclusion.reason_code, exclusion.rule_id),
            "source-snapshot",
            &format!("source-snapshot:{}", exclusion.evidence_id),
        ));
    }
    for declaration in &snapshot.declarations {
        if target_is_excluded(&declaration.declared_target) {
            diagnostics.push(graph_diagnostic(
                "excluded",
                "dependency.target_excluded",
                "info",
                Some("dependency"),
                path_by_identity
                    .get(&declaration.source_identity_id)
                    .map(String::as_str),
                Some(&declaration.declared_target),
                Some(declaration.source_span.clone()),
                "manifest target is an explicitly excluded AgentCanon submodule source",
                "source-snapshot",
                &format!("source-snapshot:{}", declaration.declaration_id),
            ));
        } else if declaration.resolved_target_identity_id.is_none() {
            diagnostics.push(graph_diagnostic(
                "unresolved",
                "dependency.target_unresolved",
                "warn",
                Some("dependency"),
                path_by_identity
                    .get(&declaration.source_identity_id)
                    .map(String::as_str),
                Some(&declaration.declared_target),
                Some(declaration.source_span.clone()),
                "manifest target is not in the source universe",
                "source-snapshot",
                &format!("source-snapshot:{}", declaration.declaration_id),
            ));
        } else {
            facts.push(dependency_fact(declaration, &path_by_identity));
        }
    }
    for relation in &snapshot.surface_relations {
        if matches!(
            relation.relation_type.as_str(),
            "view" | "view_of" | "generated" | "generated_from"
        ) {
            continue;
        }
        let kind = match relation.relation_type.as_str() {
            "view" | "view_of" => "view",
            "generated" | "generated_from" => "generated",
            "submodule" | "submodule_pin" => "submodule",
            _ => "containment",
        };
        facts.push(GraphFact {
            id: relation.relation_id.clone(),
            layer: "source-snapshot".to_string(),
            kind: kind.to_string(),
            from: relation.source_path.clone(),
            to: path_by_identity
                .get(&relation.target_identity_id)
                .cloned()
                .or_else(|| Some(relation.target_path.clone())),
            owner: Some(relation.owner_class.clone()),
            source_path: Some(relation.source_path.clone()),
            source_span: None,
            producer: "source-snapshot".to_string(),
            evidence_ref: format!("source-snapshot:{}", relation.evidence_id),
            authority: "source-snapshot".to_string(),
            inferred: false,
            dependency_detail: None,
            payload: json!({"surface_mode": relation.surface_mode, "status": relation.status, "content_hash_equal": relation.content_hash_equal}),
        });
    }
    for diagnostic in &snapshot.diagnostics {
        if diagnostic.code == "dependency.target_unresolved" {
            continue;
        }
        diagnostics.push(graph_diagnostic(
            "unresolved",
            &diagnostic.code,
            if diagnostic.severity == "error" {
                "blocker"
            } else {
                "warn"
            },
            Some("dependency"),
            diagnostic
                .source_span
                .as_ref()
                .map(|span| span.path.as_str()),
            None,
            diagnostic.source_span.clone(),
            &diagnostic.message,
            "source-snapshot",
            "source-snapshot:diagnostic",
        ));
    }
    Ok((nodes, facts, diagnostics))
}

fn dependency_fact(
    declaration: &DependencyDeclaration,
    paths: &BTreeMap<String, String>,
) -> GraphFact {
    let source = paths
        .get(&declaration.source_identity_id)
        .cloned()
        .unwrap_or_else(|| declaration.source_identity_id.clone());
    let target = declaration
        .resolved_target_identity_id
        .as_ref()
        .and_then(|identity| paths.get(identity))
        .cloned()
        .unwrap_or_else(|| declaration.declared_target.clone());
    GraphFact {
        id: declaration.declaration_id.clone(),
        layer: "manifest".to_string(),
        kind: "dependency".to_string(),
        from: source.clone(),
        to: Some(target.clone()),
        owner: None,
        source_path: Some(source.clone()),
        source_span: Some(declaration.source_span.clone()),
        producer: "source-snapshot".to_string(),
        evidence_ref: format!("source-snapshot:{}", declaration.declaration_id),
        authority: "ManifestParser".to_string(),
        inferred: false,
        dependency_detail: Some(json!({
            "direction": declaration.declared_direction,
            "kind": declaration.declared_kind,
            "reason": declaration.reason,
            "declared_target": declaration.declared_target,
            "resolved_target": if declaration.resolved_target_identity_id.is_some() { Some(target) } else { None::<String> },
            "raw_line_hash": declaration.raw_line_hash,
        })),
        payload: json!({"attestation_key": declaration.attestation_key}),
    }
}

fn capture_code_dependencies(
    root: &Path,
    candidate_dir: &Path,
    snapshot: &ManifestSnapshot,
) -> Result<(ProducerArtifact, Vec<GraphFact>, Vec<GraphDiagnostic>), GraphError> {
    let mut diagnostics = Vec::new();
    let scanner_paths = snapshot
        .source_universe
        .eligible_paths
        .iter()
        .filter(|path| SCANNER_SUFFIXES.iter().any(|suffix| path.ends_with(suffix)))
        .filter(|path| {
            let full = root.join(path);
            full.is_file() && !full.is_symlink()
        })
        .cloned()
        .collect::<Vec<_>>();
    let scanner_path_set = scanner_paths
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    for path in &snapshot.source_universe.eligible_paths {
        if scanner_path_set.contains(path.as_str()) {
            continue;
        }
        let full = root.join(path);
        if !full.exists() {
            continue;
        }
        if !SCANNER_SUFFIXES.iter().any(|suffix| path.ends_with(suffix)) {
            diagnostics.push(graph_diagnostic(
                "excluded",
                "scanner.unsupported_suffix",
                "info",
                Some("import"),
                Some(path),
                None,
                None,
                "code-dependency relation is outside the scanner suffix grammar",
                "code-dependencies",
                &format!("code-dependencies:unsupported:{path}"),
            ));
        } else if full.is_symlink() || !full.is_file() {
            diagnostics.push(graph_diagnostic(
                "unresolved",
                "source.unreadable",
                "warn",
                None,
                Some(path),
                None,
                None,
                "eligible scanner source is not a regular non-symlink file",
                "code-dependencies",
                &format!("code-dependencies:source:{path}"),
            ));
        }
    }
    let paths_file = candidate_dir.join("scanner-paths.txt");
    let paths_bytes = if scanner_paths.is_empty() {
        Vec::new()
    } else {
        format!("{}\n", scanner_paths.join("\n")).into_bytes()
    };
    write_synced_file(&paths_file, &paths_bytes)?;
    let script = canon_root(root).join("tools/agent_tools/scan_code_dependencies.sh");
    let output = Command::new("bash")
        .arg(&script)
        .arg("--root")
        .arg(root)
        .arg("--print-unresolved")
        .arg("--paths-file")
        .arg(&paths_file)
        .current_dir(root)
        .output()
        .map_err(|error| GraphError::Producer {
            producer: "code-dependencies".to_string(),
            reason: error.to_string(),
        })?;
    if !output.status.success() {
        return Err(process_producer_error("code-dependencies", &output));
    }
    let stdout =
        String::from_utf8(output.stdout.clone()).map_err(|error| GraphError::Producer {
            producer: "code-dependencies".to_string(),
            reason: format!("stdout UTF-8: {error}"),
        })?;
    let mut facts = Vec::new();
    let lines = stdout
        .lines()
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>();
    let marker = lines.last().ok_or_else(|| GraphError::Producer {
        producer: "code-dependencies".to_string(),
        reason: "missing completion marker".to_string(),
    })?;
    if *marker != format!("CODE_DEPENDENCY_SCAN=pass files={}", scanner_paths.len()) {
        return Err(GraphError::Producer {
            producer: "code-dependencies".to_string(),
            reason: format!("completion marker mismatch: {marker}"),
        });
    }
    for line in lines.iter().take(lines.len().saturating_sub(1)) {
        let fields = line.split('\t').collect::<Vec<_>>();
        if fields.len() != 7 || fields[0] != "CODE_DEPENDENCY" {
            return Err(GraphError::Producer {
                producer: "code-dependencies".to_string(),
                reason: format!("malformed TSV row: {line}"),
            });
        }
        let kind = match (fields[1], fields[2]) {
            ("python", "import") => "import",
            ("python", "from-import-symbol") => "symbol",
            ("c-family", "include") | ("shell", "source") => "include",
            _ => {
                return Err(GraphError::Producer {
                    producer: "code-dependencies".to_string(),
                    reason: format!("unsupported scanner kind {}/{}", fields[1], fields[2]),
                })
            }
        };
        let source = fields[3].to_string();
        let target = fields[4].to_string();
        let evidence_ref = format!("code-dependencies:{}:{}", source, fields[5]);
        if target.is_empty() {
            diagnostics.push(graph_diagnostic(
                "unresolved",
                "scanner.target_unresolved",
                "warn",
                Some(kind),
                Some(&source),
                None,
                None,
                fields[6],
                "code-dependencies",
                &evidence_ref,
            ));
            continue;
        }
        if target.starts_with("external:") {
            diagnostics.push(graph_diagnostic(
                "excluded",
                "scanner.external_target",
                "info",
                Some(kind),
                Some(&source),
                Some(&target),
                None,
                fields[6],
                "code-dependencies",
                &evidence_ref,
            ));
            continue;
        }
        facts.push(GraphFact {
            id: hash_parts(&["code-dependency", kind, &source, &target, fields[5], fields[6]]),
            layer: "code".to_string(),
            kind: kind.to_string(),
            from: source.clone(),
            to: Some(target.clone()),
            owner: None,
            source_path: Some(source),
            source_span: None,
            producer: "code-dependencies".to_string(),
            evidence_ref,
            authority: "scan_code_dependencies.sh".to_string(),
            inferred: false,
            dependency_detail: None,
            payload: json!({"language": fields[1], "scanner_kind": fields[2], "symbol": fields[5], "raw": fields[6]}),
        });
    }
    Ok((ProducerArtifact {
        producer_id: "code-dependencies".to_string(),
        version: "code-dependencies.v1".to_string(),
        command: format!("bash {} --root <parent-root> --print-unresolved --paths-file <candidate>/scanner-paths.txt", repo_artifact_ref(root, &script)),
        root: ".".to_string(),
        content_sha256: hash_bytes(&output.stdout),
        relation_families: vec!["import".to_string(), "include".to_string(), "symbol".to_string()],
        artifact_ref: producer_artifact_ref("code-dependencies", "code-dependencies.tsv", &hash_bytes(&output.stdout)),
        payload: output.stdout.clone(),
    }, facts, diagnostics))
}

fn capture_structure_and_public_surface(
    root: &Path,
    candidate_dir: &Path,
) -> Result<(Vec<ProducerArtifact>, Vec<GraphFact>, Vec<GraphDiagnostic>), GraphError> {
    let structure_tool = canon_root(root).join("tools/agent_tools/repo_structure_contract.py");
    let structure_contract = canon_root(root).join("documents/repo-structure-contract.toml");
    let structure_output = python_command()
        .arg(&structure_tool)
        .arg("--root")
        .arg(root)
        .arg("--contract")
        .arg(&structure_contract)
        .arg("--format")
        .arg("json")
        .current_dir(root)
        .output()
        .map_err(|error| GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: error.to_string(),
        })?;
    if !structure_output.status.success() {
        return Err(process_producer_error(
            "structure-catalog",
            &structure_output,
        ));
    }
    let structure_value: Value =
        serde_json::from_slice(&structure_output.stdout).map_err(|error| GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: format!("invalid structure JSON: {error}"),
        })?;
    if structure_value.get("status").and_then(Value::as_str) != Some("pass") {
        return Err(GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: "repository structure contract failed".to_string(),
        });
    }
    let tool = canon_root(root).join("tools/agent_tools/tool_catalog.py");
    let output = python_command()
        .arg(&tool)
        .arg("--root")
        .arg(root)
        .arg("--format")
        .arg("json")
        .current_dir(root)
        .output()
        .map_err(|error| GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: error.to_string(),
        })?;
    if !output.status.success() {
        return Err(process_producer_error("structure-catalog", &output));
    }
    let artifact_path =
        candidate_dir.join("producer-artifacts/structure-catalog/catalog-bundle.json");
    write_synced_file(&artifact_path, &output.stdout)?;
    let value: Value =
        serde_json::from_slice(&output.stdout).map_err(|error| GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: format!("invalid catalog JSON: {error}"),
        })?;
    if value.get("schema").and_then(Value::as_str) != Some("agent_canon.catalog_bundle.v1") {
        return Err(GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: "catalog bundle schema mismatch".to_string(),
        });
    }
    let catalog = value
        .get("catalog")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: "missing catalog report".to_string(),
        })?;
    if catalog.get("status").and_then(Value::as_str) != Some("pass") {
        return Err(GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: "tool catalog validation failed".to_string(),
        });
    }
    let public = value
        .get("public")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Producer {
            producer: "public-surface".to_string(),
            reason: "missing public report".to_string(),
        })?;
    if public.get("status").and_then(Value::as_str) != Some("pass") {
        return Err(GraphError::Producer {
            producer: "public-surface".to_string(),
            reason: "public extraction failed".to_string(),
        });
    }
    let rows = public
        .get("rows")
        .and_then(Value::as_array)
        .ok_or_else(|| GraphError::Producer {
            producer: "public-surface".to_string(),
            reason: "public rows missing".to_string(),
        })?;
    let mut facts = Vec::new();
    let public_spans = rows
        .iter()
        .filter_map(|row| {
            let object = row.as_object()?;
            let surface_id = object.get("surface_id")?.as_str()?;
            let span = object.get("source_span")?.as_object()?;
            Some((surface_id.to_string(), span.clone()))
        })
        .collect::<BTreeMap<_, _>>();
    let entries = catalog
        .get("entries")
        .and_then(Value::as_array)
        .ok_or_else(|| GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: "catalog entries missing".to_string(),
        })?;
    for row in entries {
        let object = row.as_object().ok_or_else(|| GraphError::Producer {
            producer: "structure-catalog".to_string(),
            reason: "catalog entry must be object".to_string(),
        })?;
        let tool_id = required_string(object, "tool_id", "structure-catalog")?;
        let path = producer_repo_path(root, &required_string(object, "path", "structure-catalog")?);
        let surface_id = format!("tool:{tool_id}");
        let source_span = public_spans
            .get(&surface_id)
            .map(|span| source_span_from_json(root, span))
            .transpose()?;
        facts.push(GraphFact {
            id: hash_parts(&["catalog", &tool_id, &path]),
            layer: "structure-catalog".to_string(),
            kind: "catalog".to_string(),
            from: surface_id.clone(),
            to: Some(path.clone()),
            owner: None,
            source_path: source_span.as_ref().map(|span| span.path.clone()),
            source_span,
            producer: "structure-catalog".to_string(),
            evidence_ref: format!("structure-catalog:{surface_id}"),
            authority: "CatalogReport".to_string(),
            inferred: false,
            dependency_detail: None,
            payload: row.clone(),
        });
    }
    for row in rows {
        let object = row.as_object().ok_or_else(|| GraphError::Producer {
            producer: "public-surface".to_string(),
            reason: "public row must be object".to_string(),
        })?;
        let surface_id = required_string(object, "surface_id", "public-surface")?;
        let selector = required_string(object, "selector", "public-surface")?;
        let primary_path =
            producer_repo_path(root, &required_string(object, "path", "public-surface")?);
        let primary = object
            .get("source_span")
            .and_then(Value::as_object)
            .ok_or_else(|| GraphError::Producer {
                producer: "public-surface".to_string(),
                reason: format!("{surface_id}: source span missing"),
            })?;
        facts.push(GraphFact {
            id: surface_id.clone(),
            layer: "public-surface".to_string(),
            kind: "public".to_string(),
            from: selector.clone(),
            to: Some(primary_path.clone()),
            owner: None,
            source_path: Some(primary_path.clone()),
            source_span: Some(source_span_from_json(root, primary)?),
            producer: "public-surface".to_string(),
            evidence_ref: format!("public-surface:{surface_id}"),
            authority: "public-surface".to_string(),
            inferred: false,
            dependency_detail: None,
            payload: json!({"selector": selector, "surface_kind": object.get("kind").cloned().unwrap_or(Value::Null), "secondary_spans": object.get("secondary_spans").cloned().unwrap_or_else(|| json!([]))}),
        });
    }
    let structure_payload = canonical_json(&json!({
        "schema": "agent_canon.structure_catalog.v1",
        "repo_structure": structure_value,
        "catalog_bundle": value,
    }))
    .into_bytes();
    let structure_hash = hash_bytes(&structure_payload);
    let public_hash = hash_bytes(&output.stdout);
    Ok((vec![
        ProducerArtifact {
            producer_id: "structure-catalog".to_string(),
            version: "structure-catalog.v1".to_string(),
            command: format!(
                "python3 {} --root <parent-root> --contract {} --format json + python3 {} --root <parent-root> --format json",
                repo_artifact_ref(root, &structure_tool),
                repo_artifact_ref(root, &structure_contract),
                repo_artifact_ref(root, &tool),
            ),
            root: ".".to_string(),
            content_sha256: structure_hash.clone(),
            relation_families: vec!["catalog".to_string(), "view".to_string(), "generated".to_string()],
            artifact_ref: producer_artifact_ref("structure-catalog", "structure-catalog.json", &structure_hash),
            payload: structure_payload,
        },
        ProducerArtifact {
            producer_id: "public-surface".to_string(),
            version: public.get("producer_version").and_then(Value::as_str).unwrap_or("public-surface.v1").to_string(),
            command: "tool_catalog.py::extract_public_surface captured in structure-catalog invocation".to_string(),
            root: ".".to_string(),
            content_sha256: public_hash.clone(),
            relation_families: vec!["public".to_string()],
            artifact_ref: producer_artifact_ref("public-surface", "catalog-bundle.json", &public_hash),
            payload: output.stdout.clone(),
        },
    ], facts, Vec::new()))
}

fn required_string(
    object: &Map<String, Value>,
    field: &str,
    producer: &str,
) -> Result<String, GraphError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .map(ToString::to_string)
        .ok_or_else(|| GraphError::Producer {
            producer: producer.to_string(),
            reason: format!("{field} must be string"),
        })
}

fn capture_structured_analysis(
    root: &Path,
    candidate_dir: &Path,
) -> Result<(ProducerArtifact, Vec<GraphFact>, Vec<GraphDiagnostic>), GraphError> {
    let tool = std::env::current_exe().map_err(|error| GraphError::Producer {
        producer: "structured-analysis".to_string(),
        reason: format!("resolve current agent-canon executable: {error}"),
    })?;
    let output_dir = candidate_dir.join("producer-artifacts/structured-analysis");
    fs::create_dir_all(&output_dir).map_err(|error| GraphError::CandidateWrite {
        reason: format!("create structured-analysis artifact directory: {error}"),
    })?;
    let json_path = output_dir.join("document-inventory.json");
    let markdown_path = output_dir.join("document-inventory.md");
    let output = Command::new(&tool)
        .arg("structured-analysis")
        .arg("document-inventory")
        .arg("--root")
        .arg(root)
        .arg("--json-out")
        .arg(&json_path)
        .arg("--markdown-out")
        .arg(&markdown_path)
        .current_dir(root)
        .output()
        .map_err(|error| GraphError::Producer {
            producer: "structured-analysis".to_string(),
            reason: error.to_string(),
        })?;
    if !output.status.success() {
        return Err(process_producer_error("structured-analysis", &output));
    }
    let bytes = fs::read(&json_path).map_err(|error| GraphError::Producer {
        producer: "structured-analysis".to_string(),
        reason: format!("read document inventory: {error}"),
    })?;
    let value: Value = serde_json::from_slice(&bytes).map_err(|error| GraphError::Producer {
        producer: "structured-analysis".to_string(),
        reason: format!("invalid document inventory JSON: {error}"),
    })?;
    if value.get("status").and_then(Value::as_str) != Some("pass") {
        return Err(GraphError::Producer {
            producer: "structured-analysis".to_string(),
            reason: "document inventory status is not pass".to_string(),
        });
    }
    let documents = value
        .get("documents")
        .and_then(Value::as_array)
        .ok_or_else(|| GraphError::Producer {
            producer: "structured-analysis".to_string(),
            reason: "document inventory rows missing".to_string(),
        })?;
    let mut facts = Vec::new();
    for row in documents {
        let object = row.as_object().ok_or_else(|| GraphError::Producer {
            producer: "structured-analysis".to_string(),
            reason: "document inventory row must be object".to_string(),
        })?;
        let path = required_string(object, "path", "structured-analysis")?;
        let title = required_string(object, "title", "structured-analysis")?;
        let document_selector = format!("document:{path}");
        facts.push(GraphFact {
            id: hash_parts(&["document", &path]),
            layer: "structured-analysis".to_string(),
            kind: "document".to_string(),
            from: path.clone(),
            to: Some(document_selector),
            owner: None,
            source_path: Some(path.clone()),
            source_span: None,
            producer: "structured-analysis".to_string(),
            evidence_ref: format!("structured-analysis:{path}"),
            authority: "document-inventory".to_string(),
            inferred: false,
            dependency_detail: None,
            payload: json!({"title": title}),
        });
        let parent = Path::new(&path)
            .parent()
            .and_then(Path::to_str)
            .filter(|value| !value.is_empty())
            .unwrap_or(".");
        facts.push(GraphFact {
            id: hash_parts(&["containment", parent, &path]),
            layer: "structured-analysis".to_string(),
            kind: "containment".to_string(),
            from: format!("directory:{parent}"),
            to: Some(path.clone()),
            owner: None,
            source_path: Some(path.clone()),
            source_span: None,
            producer: "structured-analysis".to_string(),
            evidence_ref: format!("structured-analysis:{path}"),
            authority: "document-inventory".to_string(),
            inferred: false,
            dependency_detail: None,
            payload: json!({"parent": parent, "child": path}),
        });
    }
    let diagnostics = producer_findings(
        "structured-analysis",
        value.get("findings").and_then(Value::as_array),
        "document",
    );
    let content_sha256 = hash_bytes(&bytes);
    Ok((ProducerArtifact {
        producer_id: "structured-analysis".to_string(),
        version: "document-inventory.v1".to_string(),
        command: "agent-canon structured-analysis document-inventory --root <parent-root> --json-out <producer-workspace>/document-inventory.json --markdown-out <producer-workspace>/document-inventory.md".to_string(),
        root: ".".to_string(),
        content_sha256: content_sha256.clone(),
        relation_families: vec!["containment".to_string(), "document".to_string()],
        artifact_ref: producer_artifact_ref("structured-analysis", "document-inventory.json", &content_sha256),
        payload: bytes,
    }, facts, diagnostics))
}

fn capture_responsibility_scope(
    root: &Path,
) -> Result<(ProducerArtifact, Vec<GraphFact>, Vec<GraphDiagnostic>), GraphError> {
    let tool = canon_root(root).join("tools/agent_tools/responsibility_scope.py");
    let output = python_command()
        .arg(&tool)
        .arg("--root")
        .arg(root)
        .arg("--format")
        .arg("json")
        .current_dir(root)
        .output()
        .map_err(|error| GraphError::Producer {
            producer: "responsibility-scope".to_string(),
            reason: error.to_string(),
        })?;
    if !output.status.success() {
        return Err(process_producer_error("responsibility-scope", &output));
    }
    let value: Value =
        serde_json::from_slice(&output.stdout).map_err(|error| GraphError::Producer {
            producer: "responsibility-scope".to_string(),
            reason: format!("invalid JSON: {error}"),
        })?;
    if value.get("status").and_then(Value::as_str) != Some("pass") {
        return Err(GraphError::Producer {
            producer: "responsibility-scope".to_string(),
            reason: "responsibility scope status is not pass".to_string(),
        });
    }
    let scopes = value
        .get("scopes")
        .and_then(Value::as_array)
        .ok_or_else(|| GraphError::Producer {
            producer: "responsibility-scope".to_string(),
            reason: "scope rows missing".to_string(),
        })?;
    let mut facts = Vec::new();
    for row in scopes {
        let object = row.as_object().ok_or_else(|| GraphError::Producer {
            producer: "responsibility-scope".to_string(),
            reason: "scope row must be object".to_string(),
        })?;
        let scope_id = required_string(object, "scope_id", "responsibility-scope")?;
        let owner = required_string(object, "owner", "responsibility-scope")?;
        let paths = object
            .get("paths")
            .and_then(Value::as_array)
            .ok_or_else(|| GraphError::Producer {
                producer: "responsibility-scope".to_string(),
                reason: format!("{scope_id}: paths missing"),
            })?;
        for path in paths.iter().filter_map(Value::as_str) {
            for kind in ["owner", "scope"] {
                facts.push(GraphFact {
                    id: hash_parts(&[kind, &scope_id, &owner, path]),
                    layer: "responsibility-scope".to_string(),
                    kind: kind.to_string(),
                    from: if kind == "owner" {
                        format!("owner:{owner}")
                    } else {
                        format!("scope:{scope_id}")
                    },
                    to: Some(format!("path-pattern:{path}")),
                    owner: Some(owner.clone()),
                    source_path: Some("responsibility-scope.toml".to_string()),
                    source_span: None,
                    producer: "responsibility-scope".to_string(),
                    evidence_ref: format!("responsibility-scope:{scope_id}:{path}"),
                    authority: "ScopeReport".to_string(),
                    inferred: false,
                    dependency_detail: None,
                    payload: row.clone(),
                });
            }
        }
    }
    let diagnostics = producer_findings(
        "responsibility-scope",
        value.get("findings").and_then(Value::as_array),
        "scope",
    );
    let content_sha256 = hash_bytes(&output.stdout);
    Ok((
        ProducerArtifact {
            producer_id: "responsibility-scope".to_string(),
            version: "responsibility-scope.v1".to_string(),
            command: format!(
                "python3 {} --root <parent-root> --format json",
                repo_artifact_ref(root, &tool)
            ),
            root: ".".to_string(),
            content_sha256: content_sha256.clone(),
            relation_families: vec!["owner".to_string(), "scope".to_string()],
            artifact_ref: producer_artifact_ref(
                "responsibility-scope",
                "responsibility-scope.json",
                &content_sha256,
            ),
            payload: output.stdout,
        },
        facts,
        diagnostics,
    ))
}

fn capture_import_responsibility(
    root: &Path,
) -> Result<(ProducerArtifact, Vec<GraphDiagnostic>), GraphError> {
    let tool = canon_root(root).join("tools/agent_tools/import_responsibility.py");
    let output = python_command()
        .arg(&tool)
        .arg("--root")
        .arg(root)
        .arg("--format")
        .arg("json")
        .current_dir(root)
        .output()
        .map_err(|error| GraphError::Producer {
            producer: "import-responsibility".to_string(),
            reason: error.to_string(),
        })?;
    if !output.status.success() {
        return Err(process_producer_error("import-responsibility", &output));
    }
    let value: Value =
        serde_json::from_slice(&output.stdout).map_err(|error| GraphError::Producer {
            producer: "import-responsibility".to_string(),
            reason: format!("invalid JSON: {error}"),
        })?;
    if value.get("status").and_then(Value::as_str) != Some("pass") {
        return Err(GraphError::Producer {
            producer: "import-responsibility".to_string(),
            reason: "import responsibility status is not pass".to_string(),
        });
    }
    let diagnostics = producer_findings(
        "import-responsibility",
        value.get("findings").and_then(Value::as_array),
        "import",
    );
    let content_sha256 = hash_bytes(&output.stdout);
    Ok((
        ProducerArtifact {
            producer_id: "import-responsibility".to_string(),
            version: "import-responsibility.v1".to_string(),
            command: format!(
                "python3 {} --root <parent-root> --format json",
                repo_artifact_ref(root, &tool)
            ),
            root: ".".to_string(),
            content_sha256: content_sha256.clone(),
            relation_families: Vec::new(),
            artifact_ref: producer_artifact_ref(
                "import-responsibility",
                "import-responsibility.json",
                &content_sha256,
            ),
            payload: output.stdout,
        },
        diagnostics,
    ))
}

fn capture_runtime_dashboard(
    root: &Path,
    producer_workspace: &Path,
) -> Result<ProducerArtifact, GraphError> {
    let tool = canon_root(root).join("tools/agent_tools/generate_agent_runtime_dashboard.py");
    let dashboard_path = producer_workspace.join("runtime-dashboard.md");
    let api_path = producer_workspace.join("runtime-dashboard.json");
    let output = python_command()
        .arg(&tool)
        .arg("--root")
        .arg(root)
        .arg("--out")
        .arg(&dashboard_path)
        .arg("--api-out")
        .arg(&api_path)
        .current_dir(root)
        .output()
        .map_err(|error| GraphError::Producer {
            producer: "runtime-dashboard".to_string(),
            reason: error.to_string(),
        })?;
    if !output.status.success() {
        return Err(process_producer_error("runtime-dashboard", &output));
    }
    let bytes = fs::read(&api_path).map_err(|error| GraphError::Producer {
        producer: "runtime-dashboard".to_string(),
        reason: format!("read runtime dashboard API: {error}"),
    })?;
    let value: Value = serde_json::from_slice(&bytes).map_err(|error| GraphError::Producer {
        producer: "runtime-dashboard".to_string(),
        reason: format!("invalid runtime dashboard API JSON: {error}"),
    })?;
    if value.get("schema").and_then(Value::as_str) != Some("agent_runtime_dashboard.v1") {
        return Err(GraphError::Producer {
            producer: "runtime-dashboard".to_string(),
            reason: "runtime dashboard schema mismatch".to_string(),
        });
    }
    let measurements = value
        .get("runtime_measurements")
        .and_then(Value::as_array)
        .ok_or_else(|| GraphError::Producer {
            producer: "runtime-dashboard".to_string(),
            reason: "runtime_measurements must be an array".to_string(),
        })?;
    for measurement in measurements {
        let object = measurement
            .as_object()
            .ok_or_else(|| GraphError::Producer {
                producer: "runtime-dashboard".to_string(),
                reason: "runtime measurement must be an object".to_string(),
            })?;
        validate_runtime_measurement(object)?;
    }
    for diagnostic in value
        .get("diagnostics")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let object = diagnostic.as_object().ok_or_else(|| GraphError::Producer {
            producer: "runtime-dashboard".to_string(),
            reason: "runtime diagnostic must be an object".to_string(),
        })?;
        required_string(object, "code", "runtime-dashboard")?;
        required_string(object, "set", "runtime-dashboard")?;
        let source_severity = required_string(object, "severity", "runtime-dashboard")?;
        match source_severity.as_str() {
            "info" | "warning" | "error" => {}
            value => {
                return Err(GraphError::Producer {
                    producer: "runtime-dashboard".to_string(),
                    reason: format!("unsupported runtime diagnostic severity {value}"),
                })
            }
        }
        required_string(object, "producer", "runtime-dashboard")?;
        required_string(object, "evidence_ref", "runtime-dashboard")?;
        required_string(object, "reason", "runtime-dashboard")?;
    }
    let rejections = value
        .get("selection_path_rejections")
        .and_then(Value::as_array)
        .ok_or_else(|| GraphError::Producer {
            producer: "runtime-dashboard".to_string(),
            reason: "selection_path_rejections must be an array".to_string(),
        })?;
    for rejection in rejections {
        let object = rejection.as_object().ok_or_else(|| GraphError::Producer {
            producer: "runtime-dashboard".to_string(),
            reason: "selection path rejection must be an object".to_string(),
        })?;
        for field in [
            "code",
            "set",
            "severity",
            "producer",
            "responsibility",
            "name",
            "path",
            "evidence_ref",
            "reason",
        ] {
            required_string(object, field, "runtime-dashboard")?;
        }
    }
    let content_sha256 = hash_bytes(&bytes);
    Ok(ProducerArtifact {
        producer_id: "runtime-dashboard".to_string(),
        version: "agent_runtime_dashboard.v1".to_string(),
        command: "python3 vendor/agent-canon/tools/agent_tools/generate_agent_runtime_dashboard.py --root <parent-root> --out <producer-workspace>/runtime-dashboard.md --api-out <producer-workspace>/runtime-dashboard.json".to_string(),
        root: ".".to_string(),
        content_sha256: content_sha256.clone(),
        relation_families: Vec::new(),
        artifact_ref: producer_artifact_ref(
            "runtime-dashboard",
            "runtime-dashboard.json",
            &content_sha256,
        ),
        payload: bytes,
    })
}

fn validate_runtime_measurement(object: &Map<String, Value>) -> Result<(), GraphError> {
    required_string(object, "responsibility_unit_id", "runtime-dashboard")?;
    for field in ["generation_parent", "reuse_mode", "packet_hash"] {
        if !object
            .get(field)
            .is_some_and(|value| value.is_null() || value.is_string())
        {
            return Err(GraphError::Producer {
                producer: "runtime-dashboard".to_string(),
                reason: format!("runtime measurement {field} must be a string or null"),
            });
        }
    }
    for field in [
        "finding_iteration",
        "review_iteration",
        "launch_epoch",
        "finish_epoch",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "retries",
        "waits",
        "progress_bytes",
    ] {
        if !object
            .get(field)
            .is_some_and(|value| value.is_null() || value.as_u64().is_some())
        {
            return Err(GraphError::Producer {
                producer: "runtime-dashboard".to_string(),
                reason: format!(
                    "runtime measurement {field} must be a nonnegative integer or null"
                ),
            });
        }
    }
    for field in ["writer_ids", "reviewer_ids", "repeated_artifact_hashes"] {
        if !object
            .get(field)
            .and_then(Value::as_array)
            .is_some_and(|items| items.iter().all(Value::is_string))
        {
            return Err(GraphError::Producer {
                producer: "runtime-dashboard".to_string(),
                reason: format!("runtime measurement {field} must be a string array"),
            });
        }
    }
    if !object
        .get("context_bytes_by_source")
        .and_then(Value::as_object)
        .is_some_and(|items| items.values().all(|value| value.as_u64().is_some()))
    {
        return Err(GraphError::Producer {
            producer: "runtime-dashboard".to_string(),
            reason: "runtime measurement context_bytes_by_source must contain nonnegative integers"
                .to_string(),
        });
    }
    Ok(())
}

fn producer_findings(
    producer: &str,
    findings: Option<&Vec<Value>>,
    relation: &str,
) -> Vec<GraphDiagnostic> {
    findings
        .into_iter()
        .flatten()
        .enumerate()
        .map(|(index, finding)| {
            let path = finding.get("path").and_then(Value::as_str).unwrap_or(".");
            graph_diagnostic(
                "uncovered",
                &format!("{producer}.finding"),
                "warn",
                Some(relation),
                Some(path),
                None,
                None,
                &canonical_json(finding),
                producer,
                &format!("{producer}:finding:{index}"),
            )
        })
        .collect()
}

fn source_span_from_json(
    root: &Path,
    object: &Map<String, Value>,
) -> Result<SourceSpan, GraphError> {
    Ok(SourceSpan {
        path: producer_repo_path(root, &required_string(object, "path", "public-surface")?),
        start_line: required_usize(object, "start_line")?,
        start_column: required_usize(object, "start_column")?,
        end_line: required_usize(object, "end_line")?,
        end_column: required_usize(object, "end_column")?,
    })
}

fn producer_repo_path(root: &Path, path: &str) -> String {
    if path.starts_with("vendor/agent-canon/") || canon_root(root) == root {
        path.to_string()
    } else {
        format!("vendor/agent-canon/{path}")
    }
}

fn required_usize(object: &Map<String, Value>, field: &str) -> Result<usize, GraphError> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .map(|value| value as usize)
        .ok_or_else(|| GraphError::Producer {
            producer: "public-surface".to_string(),
            reason: format!("{field} must be integer"),
        })
}

fn python_command() -> Command {
    let mut command = Command::new("python3");
    command.env("PYTHONDONTWRITEBYTECODE", "1");
    command
}

fn process_producer_error(producer: &str, output: &Output) -> GraphError {
    GraphError::Producer {
        producer: producer.to_string(),
        reason: format!(
            "exit={} stderr={}",
            output.status.code().unwrap_or(-1),
            String::from_utf8_lossy(&output.stderr).trim()
        ),
    }
}

fn bind_fact_endpoints(nodes: &mut Vec<SourceNode>, facts: &mut [GraphFact]) {
    let mut known = nodes
        .iter()
        .map(|node| node.selector.clone())
        .collect::<BTreeSet<_>>();
    for fact in facts.iter() {
        for selector in std::iter::once(&fact.from).chain(fact.to.iter()) {
            if known.insert(selector.clone()) {
                nodes.push(SourceNode {
                    id: selector_node_id(selector),
                    selector: selector.clone(),
                    path: None,
                    source_member: false,
                    source_span: None,
                    payload: json!({"path": Value::Null, "selector": selector, "source_member": false, "producer": fact.producer}),
                });
            }
        }
    }
    let ids = nodes
        .iter()
        .map(|node| (node.selector.clone(), node.id.clone()))
        .collect::<BTreeMap<_, _>>();
    for fact in facts {
        let from_selector = fact.from.clone();
        let to_selector = fact.to.clone();
        fact.from = ids
            .get(&from_selector)
            .cloned()
            .unwrap_or_else(|| selector_node_id(&from_selector));
        fact.to = to_selector.as_ref().map(|selector| {
            ids.get(selector)
                .cloned()
                .unwrap_or_else(|| selector_node_id(selector))
        });
        let mut payload = fact.payload.as_object().cloned().unwrap_or_default();
        payload.insert("from_selector".to_string(), Value::String(from_selector));
        payload.insert(
            "to_selector".to_string(),
            to_selector.map(Value::String).unwrap_or(Value::Null),
        );
        fact.payload = Value::Object(payload);
    }
}

fn canonicalize_build_records(
    nodes: &mut Vec<SourceNode>,
    facts: &mut Vec<GraphFact>,
    diagnostics: &mut Vec<GraphDiagnostic>,
    producers: &mut Vec<ProducerArtifact>,
) -> Result<(), GraphError> {
    let mut node_by_id = BTreeMap::<String, SourceNode>::new();
    for node in std::mem::take(nodes) {
        if let Some(previous) = node_by_id.insert(node.id.clone(), node.clone()) {
            if previous != node {
                return Err(GraphError::Validation {
                    stage: "node-uniqueness".to_string(),
                    reason: format!("node ID {} has multiple definitions", node.id),
                });
            }
        }
    }
    *nodes = node_by_id.into_values().collect();

    let mut fact_by_id = BTreeMap::<String, GraphFact>::new();
    for fact in std::mem::take(facts) {
        if let Some(previous) = fact_by_id.insert(fact.id.clone(), fact.clone()) {
            if previous != fact {
                return Err(GraphError::Validation {
                    stage: "relation-uniqueness".to_string(),
                    reason: format!("relation ID {} has multiple definitions", fact.id),
                });
            }
        }
    }
    *facts = fact_by_id.into_values().collect();

    let mut diagnostic_by_id = BTreeMap::<String, GraphDiagnostic>::new();
    for diagnostic in std::mem::take(diagnostics) {
        if let Some(previous) = diagnostic_by_id.insert(diagnostic.id.clone(), diagnostic.clone()) {
            if previous != diagnostic {
                return Err(GraphError::Validation {
                    stage: "diagnostic-uniqueness".to_string(),
                    reason: format!("diagnostic ID {} has multiple definitions", diagnostic.id),
                });
            }
        }
    }
    *diagnostics = diagnostic_by_id.into_values().collect();

    let mut producer_by_id = BTreeMap::<String, ProducerArtifact>::new();
    for producer in std::mem::take(producers) {
        if let Some(previous) =
            producer_by_id.insert(producer.producer_id.clone(), producer.clone())
        {
            if previous != producer {
                return Err(GraphError::Validation {
                    stage: "producer-uniqueness".to_string(),
                    reason: format!(
                        "producer ID {} has multiple artifacts",
                        producer.producer_id
                    ),
                });
            }
        }
    }
    *producers = producer_by_id.into_values().collect();
    Ok(())
}

fn apply_exclusion_dominance(
    facts: &mut Vec<GraphFact>,
    diagnostics: &mut Vec<GraphDiagnostic>,
    universe: &SourceUniverse,
) {
    let excluded = universe
        .excluded_paths
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    facts.retain(|fact| {
        let excluded_endpoint = std::iter::once(fact.from.as_str())
            .chain(fact.to.as_deref())
            .find(|selector| excluded.contains(*selector));
        let Some(selector) = excluded_endpoint else {
            return true;
        };
        diagnostics.push(graph_diagnostic(
            "excluded",
            "relation.endpoint_excluded",
            "info",
            Some(&fact.kind),
            fact.source_path.as_deref(),
            Some(selector),
            fact.source_span.clone(),
            "an explicit source exclusion dominates relation materialization",
            &fact.producer,
            &fact.evidence_ref,
        ));
        false
    });
}

fn add_reverse_projections(facts: &mut Vec<GraphFact>) -> Result<(), GraphError> {
    let explicit = facts
        .iter()
        .filter(|fact| !fact.inferred)
        .cloned()
        .collect::<Vec<_>>();
    let explicit_ids = explicit
        .iter()
        .map(|fact| fact.id.clone())
        .collect::<BTreeSet<_>>();
    for fact in explicit {
        let target = fact.to.clone().ok_or_else(|| GraphError::Validation {
            stage: "reverse-projection".to_string(),
            reason: format!("explicit relation {} has no target", fact.id),
        })?;
        let reverse_id = format!("reverse:{}", fact.id);
        if explicit_ids.contains(reverse_id.as_str()) {
            return Err(GraphError::Validation {
                stage: "reverse-projection".to_string(),
                reason: format!("explicit relation collides with projection ID {reverse_id}"),
            });
        }
        facts.push(GraphFact {
            id: reverse_id,
            layer: "graph-projection".to_string(),
            kind: fact.kind.clone(),
            from: target,
            to: Some(fact.from.clone()),
            owner: fact.owner.clone(),
            source_path: fact.source_path.clone(),
            source_span: fact.source_span.clone(),
            producer: "graph-projection".to_string(),
            evidence_ref: fact.evidence_ref.clone(),
            authority: fact.authority.clone(),
            inferred: true,
            dependency_detail: None,
            payload: json!({"projection_of": fact.id}),
        });
    }
    Ok(())
}

fn finite_set(label: &str, values: &[String]) -> Result<BTreeSet<String>, GraphError> {
    let set = values.iter().cloned().collect::<BTreeSet<_>>();
    if set.len() != values.len() {
        return Err(GraphError::Validation {
            stage: "finite-set".to_string(),
            reason: format!("{label} contains duplicate members"),
        });
    }
    Ok(set)
}

fn diagnostic_scope(diagnostic: &GraphDiagnostic) -> &'static str {
    if diagnostic.code.starts_with("source.") {
        "source"
    } else {
        "relation"
    }
}

fn derive_graph_contract(
    snapshot: &ManifestSnapshot,
    nodes: &[SourceNode],
    facts: &[GraphFact],
    diagnostics: &[GraphDiagnostic],
    producers: &[ProducerArtifact],
) -> Result<GraphContractWitness, GraphError> {
    let candidate_sources = finite_set("P(S)", &snapshot.source_universe.candidate_paths)?;
    let excluded_sources = finite_set("X(S)", &snapshot.source_universe.excluded_paths)?;
    let eligible_sources = finite_set("U(S)", &snapshot.source_universe.eligible_paths)?;
    if eligible_sources
        .union(&excluded_sources)
        .cloned()
        .collect::<BTreeSet<_>>()
        != candidate_sources
        || !eligible_sources.is_disjoint(&excluded_sources)
        || eligible_sources
            != candidate_sources
                .difference(&excluded_sources)
                .cloned()
                .collect::<BTreeSet<_>>()
    {
        return Err(GraphError::Validation {
            stage: "source-partition".to_string(),
            reason:
                "P(S), X(S), and U(S) do not satisfy U=P\\X, P=U union X, and U intersect X=empty"
                    .to_string(),
        });
    }

    let declarations = snapshot
        .declarations
        .iter()
        .map(|declaration| declaration.declaration_id.clone())
        .collect::<BTreeSet<_>>();
    if declarations.len() != snapshot.declarations.len() {
        return Err(GraphError::Validation {
            stage: "declaration-uniqueness".to_string(),
            reason: "D contains duplicate declaration IDs".to_string(),
        });
    }

    let mut source_identity = BTreeMap::new();
    let mut node_ids = BTreeSet::new();
    for node in nodes {
        if !node_ids.insert(node.id.clone()) {
            return Err(GraphError::Validation {
                stage: "node-uniqueness".to_string(),
                reason: format!("duplicate node ID {}", node.id),
            });
        }
        if excluded_sources.contains(&node.selector) {
            return Err(GraphError::Validation {
                stage: "exclusion-dominance".to_string(),
                reason: format!("excluded source became a graph endpoint: {}", node.selector),
            });
        }
        if node.source_member {
            let path = node.path.clone().ok_or_else(|| GraphError::Validation {
                stage: "source-identity-totality".to_string(),
                reason: format!("source node {} has no RepoPath", node.id),
            })?;
            if !eligible_sources.contains(&path) {
                return Err(GraphError::Validation {
                    stage: "source-identity-totality".to_string(),
                    reason: format!("source identity is outside U(S): {path}"),
                });
            }
            if source_identity
                .insert(path.clone(), node.id.clone())
                .is_some()
            {
                return Err(GraphError::Validation {
                    stage: "source-identity-uniqueness".to_string(),
                    reason: format!("eligible source has multiple node identities: {path}"),
                });
            }
        } else if node.path.is_some() {
            return Err(GraphError::Validation {
                stage: "source-identity-totality".to_string(),
                reason: format!("selector node {} carries a source path", node.id),
            });
        }
    }
    if source_identity.keys().cloned().collect::<BTreeSet<_>>() != eligible_sources {
        return Err(GraphError::Validation {
            stage: "source-identity-totality".to_string(),
            reason: "source_identity is not a total function U(S) -> V(G)".to_string(),
        });
    }

    let producer_ids = producers
        .iter()
        .map(|producer| producer.producer_id.clone())
        .collect::<BTreeSet<_>>();
    if producer_ids.len() != producers.len() {
        return Err(GraphError::Validation {
            stage: "producer-uniqueness".to_string(),
            reason: "producer artifact IDs are not unique".to_string(),
        });
    }
    for producer in producers {
        for relation in &producer.relation_families {
            RelationKind::parse(relation)?;
        }
    }

    let mut relation_endpoints = BTreeMap::new();
    let mut accepted_relations = BTreeSet::new();
    let mut inferred_relations = BTreeSet::new();
    for fact in facts {
        let relation = TypedRelation::from_fact(fact)?;
        if !node_ids.contains(&relation.from) || !node_ids.contains(&relation.to) {
            return Err(GraphError::Validation {
                stage: "relation-endpoint-totality".to_string(),
                reason: format!("relation {} references an unknown endpoint", relation.id),
            });
        }
        if relation.producer.is_empty() || relation.evidence_ref.is_empty() {
            return Err(GraphError::Validation {
                stage: "relation-provenance-totality".to_string(),
                reason: format!("relation {} lacks producer provenance", relation.id),
            });
        }
        if relation.inferred {
            inferred_relations.insert(relation.id.clone());
        } else {
            if !producer_ids.contains(&relation.producer) {
                return Err(GraphError::Validation {
                    stage: "relation-producer-totality".to_string(),
                    reason: format!(
                        "relation {} references unknown producer {}",
                        relation.id, relation.producer
                    ),
                });
            }
            accepted_relations.insert(relation.id.clone());
        }
        if relation_endpoints
            .insert(relation.id.clone(), relation)
            .is_some()
        {
            return Err(GraphError::Validation {
                stage: "relation-uniqueness".to_string(),
                reason: format!("duplicate relation ID {}", fact.id),
            });
        }
    }

    let expected_resolved_declarations = snapshot
        .declarations
        .iter()
        .filter(|declaration| declaration.resolved_target_identity_id.is_some())
        .filter(|declaration| {
            !excluded_sources.contains(&declaration.declared_target)
                && !excluded_sources.contains(&format!(
                    "vendor/agent-canon/{}",
                    declaration.declared_target
                ))
                && !source_path_is_explicitly_excluded(&declaration.declared_target)
        })
        .map(|declaration| declaration.declaration_id.clone())
        .collect::<BTreeSet<_>>();
    let represented_resolved_declarations = facts
        .iter()
        .filter(|fact| {
            !fact.inferred && fact.kind == "dependency" && fact.producer == "source-snapshot"
        })
        .map(|fact| fact.id.clone())
        .collect::<BTreeSet<_>>();
    if represented_resolved_declarations != expected_resolved_declarations {
        return Err(GraphError::Validation {
            stage: "declaration-representation".to_string(),
            reason: "resolved declaration representation differs from canonical D".to_string(),
        });
    }

    let mut reverse_projection = BTreeMap::new();
    for relation_id in &accepted_relations {
        let explicit = &relation_endpoints[relation_id];
        let reverse_id = format!("reverse:{relation_id}");
        let reverse =
            relation_endpoints
                .get(&reverse_id)
                .ok_or_else(|| GraphError::Validation {
                    stage: "reverse-projection-closure".to_string(),
                    reason: format!("relation {relation_id} has no reverse projection"),
                })?;
        if !reverse.inferred
            || reverse.from != explicit.to
            || reverse.to != explicit.from
            || reverse.kind != explicit.kind
            || reverse.evidence_ref != explicit.evidence_ref
            || reverse.producer != "graph-projection"
        {
            return Err(GraphError::Validation {
                stage: "reverse-projection-closure".to_string(),
                reason: format!("reverse projection {reverse_id} violates its typed relation"),
            });
        }
        reverse_projection.insert(relation_id.clone(), reverse_id);
    }
    if reverse_projection
        .values()
        .cloned()
        .collect::<BTreeSet<_>>()
        != inferred_relations
    {
        return Err(GraphError::Validation {
            stage: "reverse-projection-closure".to_string(),
            reason: "inferred relation set is not exactly reverse(R)".to_string(),
        });
    }

    let diagnostics_by_set = |set_name: &str| {
        diagnostics
            .iter()
            .filter(|diagnostic| diagnostic.set == set_name)
            .map(|diagnostic| diagnostic.id.clone())
            .collect::<BTreeSet<_>>()
    };
    let unresolved = diagnostics_by_set("unresolved");
    let ambiguous = diagnostics_by_set("ambiguous");
    let uncovered = diagnostics_by_set("uncovered");
    let relation_exclusions = diagnostics
        .iter()
        .filter(|diagnostic| {
            diagnostic.set == "excluded" && diagnostic_scope(diagnostic) == "relation"
        })
        .map(|diagnostic| diagnostic.id.clone())
        .collect::<BTreeSet<_>>();

    let graph_members = nodes
        .iter()
        .map(|node| format!("node:{}", node.id))
        .chain(declarations.iter().map(|id| format!("declaration:{id}")))
        .chain(facts.iter().map(|fact| format!("relation:{}", fact.id)))
        .chain(
            diagnostics
                .iter()
                .map(|diagnostic| format!("diagnostic:{}", diagnostic.id)),
        )
        .collect::<BTreeSet<_>>();
    let profile_members = graph_members.clone();
    if !profile_members.is_subset(&graph_members) || profile_members != graph_members {
        return Err(GraphError::Validation {
            stage: "profile-projection".to_string(),
            reason: "Vp is not the exact default projection of G".to_string(),
        });
    }

    Ok(GraphContractWitness {
        candidate_sources,
        excluded_sources,
        eligible_sources,
        declarations,
        accepted_relations,
        graph_members,
        profile_members,
        relation_exclusions,
        unresolved,
        ambiguous,
        uncovered,
        source_identity,
        relation_endpoints,
        reverse_projection,
    })
}

fn write_graph_candidate(
    material: &BuildMaterial,
    point: GraphBuildFailurePoint,
) -> Result<CandidateHandle, GraphError> {
    let db = material.candidate_dir.join("graph.sqlite");
    if point == GraphBuildFailurePoint::Write {
        return Err(GraphError::CandidateWrite {
            reason: "injected candidate write failure seam".to_string(),
        });
    }
    let local_db = std::env::temp_dir().join(format!(
        "agent-canon-graph-{}-{}.sqlite",
        std::process::id(),
        now_nanos()
    ));
    let local_result = (|| {
        let connection =
            Connection::open(&local_db).map_err(|error| GraphError::CandidateWrite {
                reason: format!("open local materialization database: {error}"),
            })?;
        materialize_graph_store(&connection, material)?;
        connection
            .execute_batch("PRAGMA wal_checkpoint(TRUNCATE);")
            .map_err(|error| GraphError::CandidateWrite {
                reason: format!("checkpoint local materialization database: {error}"),
            })?;
        drop(connection);
        let bytes = fs::read(&local_db).map_err(|error| GraphError::CandidateWrite {
            reason: format!("read local materialization database: {error}"),
        })?;
        write_synced_file(&db, &bytes)
    })();
    let local_cleanup = fs::remove_file(&local_db);
    if let Err(error) = local_result {
        return Err(error);
    }
    if let Err(error) = local_cleanup {
        if error.kind() != std::io::ErrorKind::NotFound {
            return Err(GraphError::CandidateWrite {
                reason: format!("remove local materialization database: {error}"),
            });
        }
    }
    if point == GraphBuildFailurePoint::Sync {
        return Err(GraphError::CandidateSync {
            reason: "injected candidate sync failure seam".to_string(),
        });
    }
    File::open(&db)
        .and_then(|file| file.sync_all())
        .map_err(|error| GraphError::CandidateSync {
            reason: format!("sync candidate: {error}"),
        })?;
    Ok(CandidateHandle {
        dir: material.candidate_dir.clone(),
        db,
    })
}

fn materialize_graph_store(
    connection: &Connection,
    material: &BuildMaterial,
) -> Result<(), GraphError> {
    initialize_graph_schema(connection).map_err(|error| GraphError::CandidateWrite {
        reason: format!("initialize Graph DSL: {error}"),
    })?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('schema_version',?)",
            [GRAPH_SCHEMA_VERSION],
        )
        .map_err(sql_write)?;
    connection
        .execute(
            "INSERT INTO documents(id,path,title,kind,created_at) VALUES(?,?,?,?,?)",
            params![
                "doc:knowledge-graph",
                ".agent-canon/knowledge-graph/graph.sqlite",
                "AgentCanon knowledge graph",
                "knowledge-graph",
                material.created_at
            ],
        )
        .map_err(sql_write)?;
    for node in &material.nodes {
        let (start, end) = source_scalar_offsets(&material.root, node.source_span.as_ref())?;
        connection.execute(
            "INSERT INTO nodes(id,document_id,layer,kind,label,text,source_start,source_end,confidence,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
            params![node.id, "doc:knowledge-graph", "source", if node.source_member { "path" } else { "selector" }, node.selector, node.selector, start, end, 1.0f64, canonical_json(&node.payload)],
        ).map_err(sql_write)?;
    }
    for fact in &material.facts {
        let Some(target) = &fact.to else { continue };
        let evidence_id = format!("fact:{}", fact.id);
        let evidence_payload = json!({
            "fact_id": fact.id,
            "source_path": fact.source_path,
            "source_span": fact.source_span.as_ref().map(source_span_json),
            "producer": fact.producer,
            "evidence_ref": fact.evidence_ref,
            "authority": fact.authority,
        });
        let (evidence_start, evidence_end) =
            source_scalar_offsets(&material.root, fact.source_span.as_ref())?;
        connection.execute(
            "INSERT INTO nodes(id,document_id,layer,kind,label,text,source_start,source_end,confidence,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
            params![evidence_id, "doc:knowledge-graph", "evidence", "fact", fact.id, fact.evidence_ref, evidence_start, evidence_end, 1.0f64, canonical_json(&evidence_payload)],
        ).map_err(sql_write)?;
        let mut payload = fact.payload.as_object().cloned().unwrap_or_default();
        payload.insert("fact".to_string(), fact.json());
        connection.execute(
            "INSERT INTO edges(id,layer,kind,from_node_id,to_node_id,order_kind,confidence,evidence_node_id,payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
            params![fact.id, fact.layer, fact.kind, fact.from, target, "explicit", 1.0f64, evidence_id, canonical_json(&Value::Object(payload))],
        ).map_err(sql_write)?;
    }
    let node_ids = material
        .nodes
        .iter()
        .map(|node| node.id.as_str())
        .collect::<BTreeSet<_>>();
    let edge_ids = material
        .facts
        .iter()
        .map(|fact| fact.id.as_str())
        .collect::<BTreeSet<_>>();
    for diagnostic in &material.diagnostics {
        let target_node_id = diagnostic
            .path
            .as_deref()
            .map(source_node_id)
            .filter(|node_id| node_ids.contains(node_id.as_str()))
            .or_else(|| {
                diagnostic
                    .target
                    .as_deref()
                    .map(source_node_id)
                    .filter(|node_id| node_ids.contains(node_id.as_str()))
            })
            .unwrap_or_default();
        let target_edge_id = diagnostic
            .relation
            .as_deref()
            .filter(|edge_id| edge_ids.contains(*edge_id))
            .unwrap_or_default();
        connection.execute(
            "INSERT INTO diagnostics(id,layer,target_node_id,target_edge_id,severity,rule,message,suggested_action_json) VALUES(?,?,?,?,?,?,?,?)",
            params![diagnostic.id, "diagnostics", target_node_id, target_edge_id, diagnostic.severity, diagnostic.code, diagnostic.reason, diagnostic.suggested_action_json],
        ).map_err(sql_write)?;
    }
    let integration = integration_record(material, true).json();
    let relation_counts =
        material
            .facts
            .iter()
            .fold(BTreeMap::<String, usize>::new(), |mut counts, fact| {
                *counts.entry(fact.kind.clone()).or_default() += 1;
                counts
            });
    let tool_versions = material
        .producer_artifacts
        .iter()
        .map(|artifact| (artifact.producer_id.clone(), artifact.version.clone()))
        .collect::<BTreeMap<_, _>>();
    let (candidate_count, eligible_count, excluded_count) =
        snapshot_source_scope_counts(&material.snapshot);
    let runtime_artifact = material
        .producer_artifacts
        .iter()
        .find(|artifact| artifact.producer_id == "runtime-dashboard");
    let runtime_api = runtime_artifact
        .map(|artifact| serde_json::from_slice::<Value>(&artifact.payload))
        .transpose()
        .map_err(|error| GraphError::CandidateWrite {
            reason: format!("decode runtime dashboard metadata: {error}"),
        })?
        .unwrap_or_else(|| json!({}));
    let runtime_context_diagnostics = runtime_api
        .get("diagnostics")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .map(|mut diagnostic| {
            if let (Some(object), Some(artifact)) = (diagnostic.as_object_mut(), runtime_artifact) {
                object.insert("artifact_ref".to_string(), json!(artifact.artifact_ref));
                object.insert("producer_version".to_string(), json!(artifact.version));
                object.insert(
                    "producer_content_sha256".to_string(),
                    json!(artifact.content_sha256),
                );
            }
            diagnostic
        })
        .collect::<Vec<_>>();
    let metadata = [
        ("root", ".".to_string()),
        ("profile", PUBLIC_PROFILE.to_string()),
        ("source_snapshot_profile", SOURCE_PROFILE.to_string()),
        (
            "snapshot_head",
            snapshot_head(&material.snapshot).to_string(),
        ),
        (
            "dirty_fingerprint",
            snapshot_dirty_fingerprint(&material.snapshot).to_string(),
        ),
        (
            "agent_canon_pin",
            snapshot_agent_canon_pin(&material.snapshot).to_string(),
        ),
        ("input_fingerprint", material.input_fingerprint.clone()),
        ("graph_fingerprint", material.graph_fingerprint.clone()),
        (
            "mathematical_contract",
            canonical_json(&material.contract.json()),
        ),
        (
            "producer_artifacts",
            canonical_json(&Value::Array(
                material
                    .producer_artifacts
                    .iter()
                    .map(ProducerArtifact::json)
                    .collect(),
            )),
        ),
        (
            "producer_artifact_payloads",
            producer_artifact_payloads_json(&material.producer_artifacts),
        ),
        (
            "source_scope_counts",
            canonical_json(&json!({
                "candidate": candidate_count,
                "eligible": eligible_count,
                "excluded": excluded_count,
            })),
        ),
        ("relation_counts", canonical_json(&json!(relation_counts))),
        ("tool_versions", canonical_json(&json!(tool_versions))),
        ("integration_record", canonical_json(&integration)),
        ("created_at", material.created_at.clone()),
        (
            "graph_diagnostics",
            canonical_json(&Value::Array(
                material
                    .diagnostics
                    .iter()
                    .map(GraphDiagnostic::json)
                    .collect(),
            )),
        ),
        (
            "runtime_measurements",
            canonical_json(
                runtime_api
                    .get("runtime_measurements")
                    .unwrap_or(&Value::Array(Vec::new())),
            ),
        ),
        (
            "runtime_context_diagnostics",
            canonical_json(&Value::Array(runtime_context_diagnostics)),
        ),
    ];
    for (key, value) in metadata {
        connection
            .execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",
                params![key, value],
            )
            .map_err(sql_write)?;
    }
    Ok(())
}

fn git_head_timestamp(root: &Path) -> Result<String, GraphError> {
    let output = Command::new("git")
        .args(["show", "-s", "--format=%cI", "HEAD"])
        .current_dir(root)
        .output()
        .map_err(|error| GraphError::Producer {
            producer: "source-snapshot".to_string(),
            reason: format!("read HEAD timestamp: {error}"),
        })?;
    if !output.status.success() {
        return Err(process_producer_error("source-snapshot", &output));
    }
    String::from_utf8(output.stdout)
        .map(|value| value.trim().to_string())
        .map_err(|error| GraphError::Producer {
            producer: "source-snapshot".to_string(),
            reason: format!("HEAD timestamp UTF-8: {error}"),
        })
}

fn sql_write(error: rusqlite::Error) -> GraphError {
    GraphError::CandidateWrite {
        reason: error.to_string(),
    }
}

fn json_string_set(value: &Value, field: &str) -> Result<BTreeSet<String>, GraphError> {
    let values =
        value
            .get(field)
            .and_then(Value::as_array)
            .ok_or_else(|| GraphError::Validation {
                stage: "mathematical-contract".to_string(),
                reason: format!("finite set {field} is missing"),
            })?;
    let strings = values
        .iter()
        .map(|item| {
            item.as_str()
                .map(ToString::to_string)
                .ok_or_else(|| GraphError::Validation {
                    stage: "mathematical-contract".to_string(),
                    reason: format!("finite set {field} has a non-string member"),
                })
        })
        .collect::<Result<Vec<_>, _>>()?;
    let set = strings.iter().cloned().collect::<BTreeSet<_>>();
    if set.len() != strings.len() || set.iter().cloned().collect::<Vec<_>>() != strings {
        return Err(GraphError::Validation {
            stage: "mathematical-contract".to_string(),
            reason: format!("finite set {field} is not unique and sorted"),
        });
    }
    Ok(set)
}

fn validate_contract_value(value: &Value) -> Result<(), GraphError> {
    let object = value.as_object().ok_or_else(|| GraphError::Validation {
        stage: "mathematical-contract".to_string(),
        reason: "mathematical contract must be an object".to_string(),
    })?;
    if object.get("schema").and_then(Value::as_str)
        != Some("agent-canon.graph.mathematical-contract.v1")
        || object.get("profile").and_then(Value::as_str) != Some(PUBLIC_PROFILE)
    {
        return Err(GraphError::Validation {
            stage: "mathematical-contract".to_string(),
            reason: "mathematical contract schema/profile mismatch".to_string(),
        });
    }
    let finite_sets = object
        .get("finite_sets")
        .ok_or_else(|| GraphError::Validation {
            stage: "mathematical-contract".to_string(),
            reason: "finite_sets is missing".to_string(),
        })?;
    let p = json_string_set(finite_sets, "P(S)")?;
    let x = json_string_set(finite_sets, "X(S)")?;
    let u = json_string_set(finite_sets, "U(S)")?;
    let d = json_string_set(finite_sets, "D")?;
    let r = json_string_set(finite_sets, "R")?;
    let g = json_string_set(finite_sets, "G")?;
    let vp = json_string_set(finite_sets, "Vp")?;
    let xr = json_string_set(finite_sets, "X_R(S,p)")?;
    let unresolved = json_string_set(finite_sets, "Unresolved(S,p)")?;
    let ambiguous = json_string_set(finite_sets, "Ambiguous(S,p)")?;
    let uncovered = json_string_set(finite_sets, "Uncovered(S,p)")?;
    let _ = (d, xr);
    if u.union(&x).cloned().collect::<BTreeSet<_>>() != p
        || !u.is_disjoint(&x)
        || u != p.difference(&x).cloned().collect::<BTreeSet<_>>()
    {
        return Err(GraphError::Validation {
            stage: "source-partition".to_string(),
            reason: "persisted P(S), X(S), and U(S) equations are false".to_string(),
        });
    }
    if !vp.is_subset(&g) || vp != g {
        return Err(GraphError::Validation {
            stage: "profile-projection".to_string(),
            reason: "persisted Vp is not the exact default projection of G".to_string(),
        });
    }

    let functions = object
        .get("typed_functions")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Validation {
            stage: "mathematical-contract".to_string(),
            reason: "typed_functions is missing".to_string(),
        })?;
    let source_identity = functions
        .get("source_identity")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Validation {
            stage: "source-identity-totality".to_string(),
            reason: "source_identity function is missing".to_string(),
        })?;
    if source_identity.keys().cloned().collect::<BTreeSet<_>>() != u
        || source_identity
            .values()
            .filter_map(Value::as_str)
            .collect::<BTreeSet<_>>()
            .len()
            != source_identity.len()
        || source_identity
            .values()
            .any(|node| node.as_str().is_none_or(|node_id| node_id.is_empty()))
        || source_identity.keys().any(|path| x.contains(path))
    {
        return Err(GraphError::Validation {
            stage: "source-identity-totality".to_string(),
            reason:
                "source_identity is not a total unique function on U(S) or violates X(S) dominance"
                    .to_string(),
        });
    }

    let relations = functions
        .get("relation_endpoints")
        .and_then(Value::as_array)
        .ok_or_else(|| GraphError::Validation {
            stage: "relation-endpoint-totality".to_string(),
            reason: "relation_endpoints function is missing".to_string(),
        })?;
    let mut relation_by_id = BTreeMap::<String, &Map<String, Value>>::new();
    for relation in relations {
        let relation = relation.as_object().ok_or_else(|| GraphError::Validation {
            stage: "relation-endpoint-totality".to_string(),
            reason: "relation endpoint record is not an object".to_string(),
        })?;
        let required = |field: &str| {
            relation
                .get(field)
                .and_then(Value::as_str)
                .filter(|item| !item.is_empty())
                .ok_or_else(|| GraphError::Validation {
                    stage: "relation-endpoint-totality".to_string(),
                    reason: format!("relation endpoint record lacks {field}"),
                })
        };
        let id = required("id")?.to_string();
        RelationKind::parse(required("kind")?)?;
        required("from")?;
        required("to")?;
        required("producer")?;
        required("evidence_ref")?;
        if relation.get("inferred").and_then(Value::as_bool).is_none()
            || relation_by_id.insert(id.clone(), relation).is_some()
        {
            return Err(GraphError::Validation {
                stage: "relation-uniqueness".to_string(),
                reason: format!("relation endpoint function is not unique at {id}"),
            });
        }
    }
    let explicit_ids = relation_by_id
        .iter()
        .filter(|(_, relation)| relation.get("inferred").and_then(Value::as_bool) == Some(false))
        .map(|(id, _)| id.clone())
        .collect::<BTreeSet<_>>();
    if explicit_ids != r {
        return Err(GraphError::Validation {
            stage: "relation-representation".to_string(),
            reason: "persisted R differs from explicit relation_endpoints domain".to_string(),
        });
    }
    let reverse_projection = functions
        .get("reverse_projection")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Validation {
            stage: "reverse-projection-closure".to_string(),
            reason: "reverse_projection function is missing".to_string(),
        })?;
    if reverse_projection.keys().cloned().collect::<BTreeSet<_>>() != r {
        return Err(GraphError::Validation {
            stage: "reverse-projection-closure".to_string(),
            reason: "reverse_projection domain differs from R".to_string(),
        });
    }
    let mut reverse_range = BTreeSet::new();
    for relation_id in &r {
        let reverse_id = reverse_projection
            .get(relation_id)
            .and_then(Value::as_str)
            .ok_or_else(|| GraphError::Validation {
                stage: "reverse-projection-closure".to_string(),
                reason: format!("reverse projection for {relation_id} is not a relation ID"),
            })?;
        if !reverse_range.insert(reverse_id) {
            return Err(GraphError::Validation {
                stage: "reverse-projection-closure".to_string(),
                reason: "reverse_projection is not injective".to_string(),
            });
        }
        let explicit = relation_by_id[relation_id];
        let reverse = relation_by_id
            .get(reverse_id)
            .ok_or_else(|| GraphError::Validation {
                stage: "reverse-projection-closure".to_string(),
                reason: format!("reverse relation {reverse_id} is absent"),
            })?;
        if reverse.get("inferred").and_then(Value::as_bool) != Some(true)
            || reverse.get("from") != explicit.get("to")
            || reverse.get("to") != explicit.get("from")
            || reverse.get("kind") != explicit.get("kind")
            || reverse.get("evidence_ref") != explicit.get("evidence_ref")
        {
            return Err(GraphError::Validation {
                stage: "reverse-projection-closure".to_string(),
                reason: format!("reverse relation {reverse_id} is not the typed inverse"),
            });
        }
    }
    let inferred_ids = relation_by_id
        .iter()
        .filter(|(_, relation)| relation.get("inferred").and_then(Value::as_bool) == Some(true))
        .map(|(id, _)| id.as_str())
        .collect::<BTreeSet<_>>();
    if inferred_ids != reverse_range {
        return Err(GraphError::Validation {
            stage: "reverse-projection-closure".to_string(),
            reason: "inferred relation domain differs from reverse(R)".to_string(),
        });
    }

    let obligations = object
        .get("obligations")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Validation {
            stage: "mathematical-contract".to_string(),
            reason: "obligations are missing".to_string(),
        })?;
    for obligation in [
        "source_partition",
        "source_disjointness",
        "source_identity_total_unique",
        "relation_kind_closed",
        "relation_endpoints_total",
        "relation_producer_total",
        "reverse_projection_bijection",
        "exclusion_dominance",
        "declaration_representation_exact",
        "graph_materialization_exact",
        "profile_projection_subset",
        "profile_projection_exact",
        "fingerprint_preservation",
        "atomic_failure_preserves_old_state",
    ] {
        if obligations.get(obligation).and_then(Value::as_bool) != Some(true) {
            return Err(GraphError::Validation {
                stage: "mathematical-contract".to_string(),
                reason: format!("structural obligation is false: {obligation}"),
            });
        }
    }
    let complete = unresolved.is_empty() && ambiguous.is_empty() && uncovered.is_empty();
    for (obligation, expected) in [
        ("unresolved_empty", unresolved.is_empty()),
        ("ambiguous_empty", ambiguous.is_empty()),
        ("uncovered_empty", uncovered.is_empty()),
        ("profile_complete", complete),
    ] {
        if obligations.get(obligation).and_then(Value::as_bool) != Some(expected) {
            return Err(GraphError::Validation {
                stage: "mathematical-contract".to_string(),
                reason: format!("completeness obligation mismatch: {obligation}"),
            });
        }
    }

    let stored_fingerprint = object
        .get("contract_fingerprint")
        .and_then(Value::as_str)
        .ok_or_else(|| GraphError::Validation {
            stage: "contract-fingerprint".to_string(),
            reason: "contract_fingerprint is missing".to_string(),
        })?;
    let mut payload = value.clone();
    payload
        .as_object_mut()
        .expect("validated object")
        .remove("contract_fingerprint");
    let recomputed = hash_bytes(canonical_json(&payload).as_bytes());
    if stored_fingerprint != recomputed {
        return Err(GraphError::Validation {
            stage: "contract-fingerprint".to_string(),
            reason: "contract fingerprint does not preserve the canonical finite-set witness"
                .to_string(),
        });
    }
    Ok(())
}

fn validate_graph_store(path: &Path, material: &BuildMaterial) -> Result<(), GraphError> {
    let connection = Connection::open_with_flags(path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|error| GraphError::Validation {
            stage: "open".to_string(),
            reason: error.to_string(),
        })?;
    validate_graph_connection(&connection).map_err(|reason| GraphError::Validation {
        stage: "graph-dsl".to_string(),
        reason,
    })?;
    let profile = metadata_value(&connection, "profile")?;
    let source_profile = metadata_value(&connection, "source_snapshot_profile")?;
    if profile != PUBLIC_PROFILE || source_profile != SOURCE_PROFILE {
        return Err(GraphError::Validation {
            stage: "profile".to_string(),
            reason: format!("invalid profile pair {profile}/{source_profile}"),
        });
    }
    for (key, expected) in [
        ("input_fingerprint", material.input_fingerprint.as_str()),
        ("graph_fingerprint", material.graph_fingerprint.as_str()),
    ] {
        let observed = metadata_value(&connection, key)?;
        if observed != expected {
            return Err(GraphError::Validation {
                stage: "fingerprint-preservation".to_string(),
                reason: format!("{key} changed during materialization"),
            });
        }
    }
    let encoded_contract = metadata_value(&connection, "mathematical_contract")?;
    let contract_value: Value =
        serde_json::from_str(&encoded_contract).map_err(|error| GraphError::Validation {
            stage: "mathematical-contract".to_string(),
            reason: error.to_string(),
        })?;
    validate_contract_value(&contract_value)?;
    if canonical_json(&contract_value) != canonical_json(&material.contract.json()) {
        return Err(GraphError::Validation {
            stage: "mathematical-contract".to_string(),
            reason: "materialized mathematical contract differs from the validated candidate"
                .to_string(),
        });
    }
    let edge_ids = connection
        .prepare("SELECT id FROM edges ORDER BY id")
        .and_then(|mut statement| {
            statement
                .query_map([], |row| row.get::<_, String>(0))?
                .collect::<Result<BTreeSet<_>, _>>()
        })
        .map_err(|error| GraphError::Validation {
            stage: "relation-representation".to_string(),
            reason: error.to_string(),
        })?;
    let expected_edge_ids = material
        .facts
        .iter()
        .map(|fact| fact.id.clone())
        .collect::<BTreeSet<_>>();
    if edge_ids != expected_edge_ids {
        return Err(GraphError::Validation {
            stage: "relation-representation".to_string(),
            reason: "materialized edge domain differs from R union reverse(R)".to_string(),
        });
    }
    let persisted_fingerprint = persisted_graph_fingerprint(&connection)?;
    if persisted_fingerprint != material.graph_fingerprint {
        return Err(GraphError::Validation {
            stage: "fingerprint-preservation".to_string(),
            reason: "materialized records do not preserve graph_fingerprint".to_string(),
        });
    }
    Ok(())
}

fn metadata_value(connection: &Connection, key: &str) -> Result<String, GraphError> {
    connection
        .query_row("SELECT value FROM metadata WHERE key=?", [key], |row| {
            row.get(0)
        })
        .map_err(|error| GraphError::Validation {
            stage: "metadata".to_string(),
            reason: format!("{key}: {error}"),
        })
}

fn publish_graph(
    graph_root: &Path,
    handle: CandidateHandle,
    point: GraphBuildFailurePoint,
) -> Result<(), GraphError> {
    let _candidate_cleanup = GraphCandidateCleanup::new(handle.dir.clone());
    let target = graph_root.join("graph.sqlite");
    let previous = handle.dir.join("previous.sqlite");
    let had_previous = target.exists();
    if had_previous {
        if target.is_symlink() || !target.is_file() {
            return Err(GraphError::Rename {
                reason: format!(
                    "publication target is not a regular file: {}",
                    target.display()
                ),
            });
        }
        fs::hard_link(&target, &previous).map_err(|error| GraphError::Rename {
            reason: format!(
                "preserve previous graph {} -> {}: {error}",
                target.display(),
                previous.display()
            ),
        })?;
    }
    if point == GraphBuildFailurePoint::Rename {
        return Err(GraphError::Rename {
            reason: "injected rename failure seam".to_string(),
        });
    }
    fs::rename(&handle.db, &target).map_err(|error| GraphError::Rename {
        reason: format!(
            "rename {} -> {}: {error}",
            handle.db.display(),
            target.display()
        ),
    })?;
    let directory_sync = if point == GraphBuildFailurePoint::DirectorySync {
        Err(std::io::Error::other(
            "injected directory sync failure seam",
        ))
    } else {
        File::open(graph_root).and_then(|directory| directory.sync_all())
    };
    if let Err(error) = directory_sync {
        let rollback = if had_previous {
            fs::rename(&previous, &target)
        } else {
            fs::remove_file(&target)
        };
        rollback.map_err(|rollback_error| GraphError::DirectorySync {
            reason: format!("sync graph directory: {error}; rollback failed: {rollback_error}"),
        })?;
        File::open(graph_root)
            .and_then(|directory| directory.sync_all())
            .map_err(|rollback_error| GraphError::DirectorySync {
                reason: format!(
                    "sync graph directory: {error}; rollback sync failed: {rollback_error}"
                ),
            })?;
        let _ = GraphCandidateCleanup::new(handle.dir).cleanup();
        return Err(GraphError::DirectorySync {
            reason: format!("sync graph directory: {error}; previous state restored"),
        });
    }
    let _ = GraphCandidateCleanup::new(handle.dir).cleanup();
    Ok(())
}

fn read_graph_status(args: &GraphStatusArgs) -> Result<Value, GraphError> {
    let root = resolve_root(&args.root)?;
    let db = graph_db(&root);
    let current_fingerprint = probe_input_fingerprint(&root, &args.profile)?;
    if !db.exists() {
        return Ok(status_response(
            &root,
            "missing",
            None,
            None,
            None,
            Vec::new(),
            Some("graph database is missing"),
            None,
            None,
            1,
        ));
    }
    if !db.is_file() || db.is_symlink() {
        return Ok(status_response(
            &root,
            "unavailable",
            None,
            None,
            None,
            Vec::new(),
            Some("graph database is not a regular file"),
            None,
            None,
            3,
        ));
    }
    let connection =
        match Connection::open_with_flags(&db, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY) {
            Ok(value) => value,
            Err(error) => {
                return Ok(status_response(
                    &root,
                    "invalid",
                    None,
                    None,
                    None,
                    Vec::new(),
                    Some(&error.to_string()),
                    None,
                    None,
                    3,
                ))
            }
        };
    if let Err(reason) = validate_graph_connection(&connection) {
        return Ok(status_response(
            &root,
            "invalid",
            None,
            None,
            None,
            Vec::new(),
            Some(&reason),
            None,
            None,
            3,
        ));
    }
    let schema = metadata_value(&connection, "schema_version")?;
    if schema != GRAPH_SCHEMA_VERSION {
        return Ok(status_response(
            &root,
            "schema-mismatch",
            None,
            None,
            None,
            Vec::new(),
            Some(&format!(
                "expected {GRAPH_SCHEMA_VERSION}, observed {schema}"
            )),
            None,
            None,
            3,
        ));
    }
    let profile = metadata_value(&connection, "profile")?;
    let source_profile = metadata_value(&connection, "source_snapshot_profile")?;
    if profile != PUBLIC_PROFILE || source_profile != SOURCE_PROFILE {
        return Ok(status_response(
            &root,
            "invalid",
            None,
            None,
            None,
            Vec::new(),
            Some("stored profile mapping is invalid"),
            None,
            None,
            3,
        ));
    }
    let stored_fingerprint = metadata_value(&connection, "input_fingerprint")?;
    let graph_fingerprint = metadata_value(&connection, "graph_fingerprint")?;
    let persisted_fingerprint = match persisted_graph_fingerprint(&connection) {
        Ok(value) => value,
        Err(error) => {
            return Ok(status_response(
                &root,
                "invalid",
                Some(&stored_fingerprint),
                Some(&graph_fingerprint),
                None,
                Vec::new(),
                Some(&error.to_string()),
                None,
                Some("fingerprint-preservation"),
                3,
            ))
        }
    };
    if persisted_fingerprint != graph_fingerprint {
        return Ok(status_response(
            &root,
            "invalid",
            Some(&stored_fingerprint),
            Some(&graph_fingerprint),
            None,
            Vec::new(),
            Some("persisted graph records do not preserve graph_fingerprint"),
            None,
            Some("fingerprint-preservation"),
            3,
        ));
    }
    let integration =
        match validated_integration_record(&connection, &stored_fingerprint, &graph_fingerprint) {
            Ok(value) => value,
            Err(reason) => {
                return Ok(status_response(
                    &root,
                    "invalid",
                    None,
                    None,
                    None,
                    Vec::new(),
                    Some(&reason),
                    None,
                    None,
                    3,
                ))
            }
        };
    let diagnostics = load_diagnostics(&connection)?;
    if stored_fingerprint != current_fingerprint {
        return Ok(status_response(
            &root,
            "stale",
            Some(&stored_fingerprint),
            Some(&graph_fingerprint),
            None,
            diagnostics,
            Some("input fingerprint differs from current snapshot"),
            None,
            None,
            1,
        ));
    }
    let incomplete = diagnostics.iter().any(|item| {
        item.get("set")
            .and_then(Value::as_str)
            .is_some_and(|set| matches!(set, "unresolved" | "ambiguous" | "uncovered"))
    });
    Ok(status_response(
        &root,
        if incomplete { "incomplete" } else { "fresh" },
        Some(&stored_fingerprint),
        Some(&graph_fingerprint),
        if incomplete { None } else { Some(integration) },
        diagnostics,
        None,
        None,
        None,
        if incomplete { 1 } else { 0 },
    ))
}

fn validated_integration_record(
    connection: &Connection,
    input_fingerprint: &str,
    graph_fingerprint: &str,
) -> Result<Value, String> {
    let contract =
        metadata_value(connection, "mathematical_contract").map_err(|error| error.to_string())?;
    let contract_value: Value = serde_json::from_str(&contract)
        .map_err(|error| format!("mathematical contract is invalid JSON: {error}"))?;
    validate_contract_value(&contract_value).map_err(|error| error.to_string())?;
    let contract_fingerprint = contract_value
        .get("contract_fingerprint")
        .and_then(Value::as_str)
        .ok_or_else(|| "mathematical contract fingerprint is missing".to_string())?;
    let encoded =
        metadata_value(connection, "integration_record").map_err(|error| error.to_string())?;
    let value: Value = serde_json::from_str(&encoded)
        .map_err(|error| format!("integration record is invalid JSON: {error}"))?;
    let object = value
        .as_object()
        .ok_or_else(|| "integration record must be an object".to_string())?;
    for (field, expected) in [
        ("schema", "agent-canon.graph.integration.v1"),
        ("root", "."),
        ("db_path", ".agent-canon/knowledge-graph/graph.sqlite"),
        ("schema_version", GRAPH_SCHEMA_VERSION),
        ("profile", PUBLIC_PROFILE),
        ("source_snapshot_profile", SOURCE_PROFILE),
        ("input_fingerprint", input_fingerprint),
        ("graph_fingerprint", graph_fingerprint),
        ("contract_fingerprint", contract_fingerprint),
        ("verification_code", "graph.integration.verified"),
    ] {
        if object.get(field).and_then(Value::as_str) != Some(expected) {
            return Err(format!("integration record {field} mismatch"));
        }
    }
    if object.get("verified").and_then(Value::as_bool) != Some(true) {
        return Err("integration record is not verified".to_string());
    }
    if object
        .get("snapshot_head")
        .and_then(Value::as_str)
        .is_none_or(str::is_empty)
    {
        return Err("integration record snapshot_head is missing".to_string());
    }
    if !object
        .get("producer_artifacts")
        .is_some_and(Value::is_array)
    {
        return Err("integration record producer_artifacts is missing".to_string());
    }
    Ok(value)
}

fn probe_input_fingerprint(root: &Path, profile: &str) -> Result<String, GraphError> {
    let args = GraphBuildArgs {
        root: root.to_path_buf(),
        profile: profile.to_string(),
        format: OutputFormat::Json,
    };
    let material = collect_build_material_with_mode(&args, GraphBuildFailurePoint::None, true)?;
    let fingerprint = material.input_fingerprint.clone();
    GraphCandidateCleanup::new(material.candidate_dir).cleanup()?;
    Ok(fingerprint)
}

fn query_graph(args: &GraphQueryArgs) -> Result<Value, GraphError> {
    let status_args = GraphStatusArgs {
        root: args.root.clone(),
        profile: args.profile.clone(),
        format: args.format,
    };
    let mut status = read_graph_status(&status_args)?;
    let root = resolve_root(&args.root)?;
    if status.get("status").and_then(Value::as_str) != Some("fresh") {
        return Ok(query_response_from_status(
            args,
            &root,
            &status,
            Vec::new(),
            Vec::new(),
        ));
    }
    let connection =
        Connection::open_with_flags(graph_db(&root), rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)
            .map_err(|error| GraphError::Unavailable {
                reason: error.to_string(),
            })?;
    let nodes = load_nodes(&connection)?;
    let facts = load_facts(&connection)?;
    if let Some(path) = args.path.as_deref() {
        if !nodes
            .iter()
            .any(|node| node.get("path").and_then(Value::as_str) == Some(path))
        {
            let diagnostic = graph_diagnostic(
                "unresolved",
                "query.seed_unresolved",
                "warn",
                None,
                Some(path),
                None,
                None,
                "query seed is not a unique source member of Vp",
                "graph-query",
                &format!("graph-query:{path}"),
            )
            .json();
            if let Some(object) = status.as_object_mut() {
                object.insert("status".to_string(), json!("incomplete"));
                object.insert("exit_code".to_string(), json!(1));
                object.insert("reason".to_string(), json!("query seed is unresolved"));
                object.insert("unresolved_count".to_string(), json!(1));
                object.insert("unresolved".to_string(), json!([diagnostic]));
            }
            return Ok(query_response_from_status(
                args,
                &root,
                &status,
                Vec::new(),
                Vec::new(),
            ));
        }
    }
    let (selected_nodes, selected_facts) = if args.all {
        let selected = facts
            .into_iter()
            .filter(|fact| relation_matches(fact, &args.relation))
            .collect::<Vec<_>>();
        (nodes, selected)
    } else {
        bfs_query(args, &nodes, &facts)?
    };
    Ok(query_response_from_status(
        args,
        &root,
        &status,
        selected_nodes,
        selected_facts,
    ))
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ClosureDerivation {
    predecessor: String,
    edge_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ClosureWitness {
    distance: BTreeMap<String, u8>,
    selected_edges: BTreeSet<String>,
    derivation: BTreeMap<String, ClosureDerivation>,
}

fn traversal_neighbor<'a>(
    fact: &'a Value,
    current: &str,
    direction: GraphDirection,
) -> Option<&'a str> {
    let from = fact.get("from").and_then(Value::as_str)?;
    let to = fact.get("to").and_then(Value::as_str)?;
    match direction {
        GraphDirection::Outgoing if from == current => Some(to),
        GraphDirection::Incoming if to == current => Some(from),
        GraphDirection::Both if from == current => Some(to),
        GraphDirection::Both if to == current => Some(from),
        _ => None,
    }
}

fn closure_operator(
    current: &BTreeMap<String, u8>,
    facts: &[Value],
    relation: &str,
    direction: GraphDirection,
    depth: u8,
) -> (BTreeMap<String, u8>, BTreeMap<String, ClosureDerivation>) {
    let mut next = current.clone();
    let mut derivations = BTreeMap::new();
    for (node, distance) in current {
        if *distance >= depth {
            continue;
        }
        for fact in facts.iter().filter(|fact| relation_matches(fact, relation)) {
            let Some(neighbor) = traversal_neighbor(fact, node, direction) else {
                continue;
            };
            let candidate_distance = distance + 1;
            let should_replace = next
                .get(neighbor)
                .is_none_or(|observed| candidate_distance < *observed);
            if should_replace {
                next.insert(neighbor.to_string(), candidate_distance);
                if let Some(edge_id) = fact.get("id").and_then(Value::as_str) {
                    derivations.insert(
                        neighbor.to_string(),
                        ClosureDerivation {
                            predecessor: node.clone(),
                            edge_id: edge_id.to_string(),
                        },
                    );
                }
            }
        }
    }
    (next, derivations)
}

fn least_fixed_point_closure(
    seed: &str,
    facts: &[Value],
    relation: &str,
    direction: GraphDirection,
    depth: u8,
) -> Result<ClosureWitness, GraphError> {
    let mut distance = BTreeMap::from([(seed.to_string(), 0u8)]);
    let mut derivation = BTreeMap::new();
    loop {
        let (next, additions) = closure_operator(&distance, facts, relation, direction, depth);
        for (node, witness) in additions {
            derivation.insert(node, witness);
        }
        if next == distance {
            break;
        }
        distance = next;
    }
    let (fixed, _) = closure_operator(&distance, facts, relation, direction, depth);
    if fixed != distance {
        return Err(GraphError::Validation {
            stage: "query-closure-fixed-point".to_string(),
            reason: "closure iteration did not reach a fixed point".to_string(),
        });
    }
    for (node, node_distance) in &distance {
        if node == seed {
            if *node_distance != 0 {
                return Err(GraphError::Validation {
                    stage: "query-closure-leastness".to_string(),
                    reason: "closure seed does not have distance zero".to_string(),
                });
            }
            continue;
        }
        let witness = derivation.get(node).ok_or_else(|| GraphError::Validation {
            stage: "query-closure-leastness".to_string(),
            reason: format!("closure member {node} has no derivation from the seed"),
        })?;
        let predecessor_distance =
            distance
                .get(&witness.predecessor)
                .ok_or_else(|| GraphError::Validation {
                    stage: "query-closure-leastness".to_string(),
                    reason: format!("closure predecessor {} is absent", witness.predecessor),
                })?;
        if predecessor_distance + 1 != *node_distance {
            return Err(GraphError::Validation {
                stage: "query-closure-leastness".to_string(),
                reason: format!("closure member {node} is not minimally derived"),
            });
        }
        let edge = facts
            .iter()
            .find(|fact| fact.get("id").and_then(Value::as_str) == Some(&witness.edge_id))
            .ok_or_else(|| GraphError::Validation {
                stage: "query-closure-leastness".to_string(),
                reason: format!("closure derivation edge {} is absent", witness.edge_id),
            })?;
        if traversal_neighbor(edge, &witness.predecessor, direction) != Some(node.as_str())
            || !relation_matches(edge, relation)
        {
            return Err(GraphError::Validation {
                stage: "query-closure-leastness".to_string(),
                reason: format!("closure derivation for {node} is not a typed traversal"),
            });
        }
    }
    let mut selected_edges = BTreeSet::new();
    for (node, node_distance) in &distance {
        if *node_distance >= depth {
            continue;
        }
        for fact in facts.iter().filter(|fact| relation_matches(fact, relation)) {
            if traversal_neighbor(fact, node, direction).is_some() {
                if let Some(edge_id) = fact.get("id").and_then(Value::as_str) {
                    selected_edges.insert(edge_id.to_string());
                }
            }
        }
    }
    Ok(ClosureWitness {
        distance,
        selected_edges,
        derivation,
    })
}

fn bfs_query(
    args: &GraphQueryArgs,
    nodes: &[Value],
    facts: &[Value],
) -> Result<(Vec<Value>, Vec<Value>), GraphError> {
    let seed_path = args.path.as_deref().unwrap_or_default();
    let Some(seed) = nodes
        .iter()
        .find(|node| node.get("path").and_then(Value::as_str) == Some(seed_path))
        .and_then(|node| node.get("id"))
        .and_then(Value::as_str)
        .map(ToString::to_string)
    else {
        return Ok((Vec::new(), Vec::new()));
    };
    let closure =
        least_fixed_point_closure(&seed, facts, &args.relation, args.direction, args.depth)?;
    let mut selected_nodes = nodes
        .iter()
        .filter_map(|node| {
            let id = node.get("id").and_then(Value::as_str)?;
            let value = closure.distance.get(id)?;
            let mut projected = node.clone();
            projected
                .as_object_mut()?
                .insert("distance".to_string(), json!(value));
            Some(projected)
        })
        .collect::<Vec<_>>();
    selected_nodes.sort_by(|left, right| {
        (
            left.get("distance").and_then(Value::as_u64).unwrap_or(0),
            left.get("id").and_then(Value::as_str).unwrap_or(""),
        )
            .cmp(&(
                right.get("distance").and_then(Value::as_u64).unwrap_or(0),
                right.get("id").and_then(Value::as_str).unwrap_or(""),
            ))
    });
    let selected_facts = facts
        .iter()
        .filter(|fact| {
            fact.get("id")
                .and_then(Value::as_str)
                .is_some_and(|id| closure.selected_edges.contains(id))
        })
        .cloned()
        .collect::<Vec<_>>();
    Ok((selected_nodes, selected_facts))
}

fn relation_matches(fact: &Value, relation: &str) -> bool {
    relation == "all" || fact.get("kind").and_then(Value::as_str) == Some(relation)
}

fn context_token_path(claim_path: &str, token: &str) -> Option<String> {
    if token.is_empty()
        || token.contains('\0')
        || token.contains('\\')
        || Path::new(token).is_absolute()
    {
        return None;
    }
    if !token.starts_with("./") && !token.starts_with("../") {
        return normalize_repo_path(token).ok();
    }
    let mut parts = claim_path.split('/').collect::<Vec<_>>();
    parts.pop();
    for component in Path::new(token).components() {
        match component {
            Component::Normal(part) => parts.push(part.to_str()?),
            Component::CurDir => {}
            Component::ParentDir => {
                parts.pop()?;
            }
            Component::RootDir | Component::Prefix(_) => return None,
        }
    }
    (!parts.is_empty()).then(|| parts.join("/"))
}

fn context_graph(args: &GraphContextArgs) -> Result<Value, GraphError> {
    let status_args = GraphStatusArgs {
        root: args.root.clone(),
        profile: args.profile.clone(),
        format: args.format,
    };
    let status = read_graph_status(&status_args)?;
    let root = resolve_root(&args.root)?;
    if status.get("status").and_then(Value::as_str) != Some("fresh") {
        return Ok(context_response_from_status(
            args,
            &root,
            &status,
            None,
            None,
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        ));
    }
    let connection =
        Connection::open_with_flags(graph_db(&root), rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)
            .map_err(|error| GraphError::Unavailable {
                reason: error.to_string(),
            })?;
    let claim_node = load_source_node(&connection, &args.path)?;
    let resolved_token = args
        .token
        .as_deref()
        .and_then(|token| context_token_path(&args.path, token));
    let token_node = match resolved_token.as_deref() {
        Some(path) => load_source_node(&connection, path)?,
        None => None,
    };
    let resolved_path = if args.token.is_none() {
        claim_node.as_ref().map(|_| args.path.clone())
    } else {
        token_node.as_ref().and(resolved_token.clone())
    };
    let context_path = resolved_path.as_deref().unwrap_or(&args.path);
    let node = token_node.as_ref().or(claim_node.as_ref());
    let nodes = load_nodes(&connection)?;
    let paths_by_id = nodes
        .iter()
        .filter_map(|node| {
            Some((
                node.get("id")?.as_str()?.to_string(),
                node.get("path")?.as_str()?.to_string(),
            ))
        })
        .collect::<BTreeMap<_, _>>();
    let facts = load_facts(&connection)?;
    let source_id = source_node_id(&args.path);
    let mut witnesses = facts
        .iter()
        .filter(|fact| {
            fact.get("kind").and_then(Value::as_str) == Some("dependency")
                && !fact
                    .get("inferred")
                    .and_then(Value::as_bool)
                    .unwrap_or(false)
                && (fact.get("from").and_then(Value::as_str) == Some(source_id.as_str())
                    || fact.get("to").and_then(Value::as_str) == Some(source_id.as_str()))
        })
        .map(|fact| dependency_witness_json(fact, &paths_by_id))
        .collect::<Result<Vec<_>, _>>()?;
    witnesses.sort_by(|left, right| {
        left.get("edge_id")
            .and_then(Value::as_str)
            .cmp(&right.get("edge_id").and_then(Value::as_str))
    });
    let mut items = Vec::new();
    let mut owner = None;
    if let Some(node) = node {
        let payload = node
            .get("payload")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        owner = payload
            .get("manifest_responsibility")
            .and_then(Value::as_str)
            .map(ToString::to_string);
        let span = payload
            .get("manifest_source_span")
            .cloned()
            .filter(|value| !value.is_null());
        items.push(context_item(
            "source.path",
            context_path,
            "graph",
            Some("source-snapshot"),
            Some(context_path),
            span.clone(),
            payload.get("evidence_ref").and_then(Value::as_str),
            "source-snapshot",
        ));
        let present = payload
            .get("manifest_present")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        items.push(context_item(
            "manifest.present",
            if present { "true" } else { "false" },
            "manifest",
            Some("source-snapshot"),
            Some(context_path),
            span.clone(),
            payload.get("evidence_ref").and_then(Value::as_str),
            "ManifestParser",
        ));
        if let Some(contract) = payload.get("manifest_contract").and_then(Value::as_str) {
            items.push(context_item(
                "manifest.contract",
                contract,
                "manifest",
                Some("source-snapshot"),
                Some(context_path),
                span.clone(),
                payload.get("evidence_ref").and_then(Value::as_str),
                "ManifestParser",
            ));
        }
        if let Some(responsibility) = payload
            .get("manifest_responsibility")
            .and_then(Value::as_str)
        {
            items.push(context_item(
                "manifest.responsibility",
                responsibility,
                "manifest",
                Some("source-snapshot"),
                Some(context_path),
                span.clone(),
                payload.get("evidence_ref").and_then(Value::as_str),
                "ManifestParser",
            ));
        }
    }
    let runtime_measurements = select_runtime_measurements(
        metadata_json_array(&connection, "runtime_measurements")?,
        &args.path,
    );
    let context_diagnostics = metadata_json_array(&connection, "runtime_context_diagnostics")?;
    let runtime_artifact_ref = metadata_json_array(&connection, "producer_artifacts")?
        .into_iter()
        .find(|artifact| {
            artifact.get("producer_id").and_then(Value::as_str) == Some("runtime-dashboard")
        })
        .and_then(|artifact| {
            artifact
                .get("artifact_ref")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        });
    for measurement in &runtime_measurements {
        items.push(context_item(
            "runtime.measurement",
            &canonical_json(measurement),
            "runtime-dashboard",
            Some("runtime-dashboard"),
            None,
            None,
            runtime_artifact_ref.as_deref(),
            "generate_agent_runtime_dashboard.py",
        ));
    }
    items.sort_by(|left, right| canonical_json(left).cmp(&canonical_json(right)));
    Ok(context_response_from_status(
        args,
        &root,
        &status,
        resolved_path,
        owner,
        witnesses,
        items,
        runtime_measurements,
        context_diagnostics,
    ))
}

fn select_runtime_measurements(measurements: Vec<Value>, context_path: &str) -> Vec<Value> {
    let parts = context_path.split('/').collect::<Vec<_>>();
    let unit_id = parts
        .windows(3)
        .find(|parts| parts[0] == "reports" && parts[1] == "agents")
        .map(|parts| parts[2]);
    let Some(unit_id) = unit_id else {
        return measurements;
    };
    measurements
        .into_iter()
        .filter(|measurement| {
            measurement
                .get("responsibility_unit_id")
                .and_then(Value::as_str)
                == Some(unit_id)
        })
        .collect()
}

fn metadata_json_array(connection: &Connection, key: &str) -> Result<Vec<Value>, GraphError> {
    serde_json::from_str(&metadata_value(connection, key)?).map_err(|error| {
        GraphError::Validation {
            stage: "metadata".to_string(),
            reason: format!("{key}: {error}"),
        }
    })
}

fn load_source_node(connection: &Connection, path: &str) -> Result<Option<Value>, GraphError> {
    let id = source_node_id(path);
    let mut statement = connection
        .prepare("SELECT id,layer,kind,payload_json FROM nodes WHERE id=?")
        .map_err(sql_validation)?;
    match statement.query_row([id], |row| {
        let payload: String = row.get(3)?;
        Ok(json!({"id": row.get::<_, String>(0)?, "layer": row.get::<_, String>(1)?, "kind": row.get::<_, String>(2)?, "payload": serde_json::from_str::<Value>(&payload).unwrap_or(Value::Null)}))
    }) {
        Ok(value) => Ok(Some(value)),
        Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
        Err(error) => Err(sql_validation(error)),
    }
}

fn load_nodes(connection: &Connection) -> Result<Vec<Value>, GraphError> {
    let mut statement = connection
        .prepare(
            "SELECT id,layer,kind,label,payload_json FROM nodes WHERE layer='source' ORDER BY id",
        )
        .map_err(sql_validation)?;
    let rows = statement
        .query_map([], |row| {
            let payload: String = row.get(4)?;
            let value = serde_json::from_str::<Value>(&payload).unwrap_or(Value::Null);
            Ok(json!({
                "id": row.get::<_, String>(0)?,
                "path": value.get("path").cloned().unwrap_or(Value::Null),
                "selector": value.get("selector").cloned().unwrap_or(Value::Null),
                "layer": row.get::<_, String>(1)?,
                "kind": row.get::<_, String>(2)?,
                "owner": value.get("manifest_responsibility").cloned().unwrap_or(Value::Null),
                "source_path": value.get("path").cloned().unwrap_or(Value::Null),
                "source_span": value.get("manifest_source_span").cloned().unwrap_or(Value::Null),
                "distance": 0,
                "payload": value,
            }))
        })
        .map_err(sql_validation)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sql_validation)
}

fn load_facts(connection: &Connection) -> Result<Vec<Value>, GraphError> {
    let mut statement = connection
        .prepare("SELECT payload_json FROM edges ORDER BY id")
        .map_err(sql_validation)?;
    let rows = statement
        .query_map([], |row| {
            let payload: String = row.get(0)?;
            let value = serde_json::from_str::<Value>(&payload).unwrap_or(Value::Null);
            Ok(value.get("fact").cloned().unwrap_or(Value::Null))
        })
        .map_err(sql_validation)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sql_validation)
}

fn load_diagnostics(connection: &Connection) -> Result<Vec<Value>, GraphError> {
    let raw = metadata_value(connection, "graph_diagnostics")?;
    serde_json::from_str::<Vec<Value>>(&raw).map_err(|error| GraphError::Validation {
        stage: "diagnostics".to_string(),
        reason: error.to_string(),
    })
}

fn persisted_graph_fingerprint(connection: &Connection) -> Result<String, GraphError> {
    let input = metadata_value(connection, "input_fingerprint")?;
    let contract: Value =
        serde_json::from_str(&metadata_value(connection, "mathematical_contract")?).map_err(
            |error| GraphError::Validation {
                stage: "fingerprint-preservation".to_string(),
                reason: format!("decode mathematical contract: {error}"),
            },
        )?;
    let diagnostics = load_diagnostics(connection)?
        .into_iter()
        .map(|diagnostic| {
            let id = diagnostic
                .get("id")
                .and_then(Value::as_str)
                .ok_or_else(|| GraphError::Validation {
                    stage: "fingerprint-preservation".to_string(),
                    reason: "persisted diagnostic lacks ID".to_string(),
                })?;
            Ok((id.to_string(), diagnostic))
        })
        .collect::<Result<BTreeMap<_, _>, GraphError>>()?;
    let producers =
        serde_json::from_str::<Vec<Value>>(&metadata_value(connection, "producer_artifacts")?)
            .map_err(|error| GraphError::Validation {
                stage: "fingerprint-preservation".to_string(),
                reason: format!("decode producer artifacts: {error}"),
            })?
            .into_iter()
            .map(|producer| {
                let id = producer
                    .get("producer_id")
                    .and_then(Value::as_str)
                    .ok_or_else(|| GraphError::Validation {
                        stage: "fingerprint-preservation".to_string(),
                        reason: "persisted producer lacks producer_id".to_string(),
                    })?;
                Ok((id.to_string(), producer))
            })
            .collect::<Result<BTreeMap<_, _>, GraphError>>()?;
    let mut node_statement = connection
        .prepare("SELECT id,payload_json FROM nodes WHERE layer='source' ORDER BY id")
        .map_err(sql_validation)?;
    let nodes = node_statement
        .query_map([], |row| {
            let id: String = row.get(0)?;
            let payload: String = row.get(1)?;
            Ok((id, payload))
        })
        .map_err(sql_validation)?
        .map(|row| {
            let (id, payload) = row.map_err(sql_validation)?;
            let payload = serde_json::from_str::<Value>(&payload).map_err(|error| {
                GraphError::Validation {
                    stage: "fingerprint-preservation".to_string(),
                    reason: format!("decode node {id}: {error}"),
                }
            })?;
            Ok((id.clone(), json!({"id": id, "payload": payload})))
        })
        .collect::<Result<BTreeMap<_, _>, GraphError>>()?;
    let facts = load_facts(connection)?
        .into_iter()
        .map(|fact| {
            let id =
                fact.get("id")
                    .and_then(Value::as_str)
                    .ok_or_else(|| GraphError::Validation {
                        stage: "fingerprint-preservation".to_string(),
                        reason: "persisted fact lacks ID".to_string(),
                    })?;
            Ok((id.to_string(), fact))
        })
        .collect::<Result<BTreeMap<_, _>, GraphError>>()?;
    Ok(graph_fingerprint_records(
        &input,
        nodes,
        facts,
        diagnostics,
        producers,
        contract,
    ))
}

fn sql_validation(error: rusqlite::Error) -> GraphError {
    GraphError::Validation {
        stage: "query".to_string(),
        reason: error.to_string(),
    }
}

fn status_response(
    _root: &Path,
    status: &str,
    input_fingerprint: Option<&str>,
    graph_fingerprint: Option<&str>,
    integration: Option<Value>,
    diagnostics: Vec<Value>,
    reason: Option<&str>,
    producer_id: Option<&str>,
    failure_stage: Option<&str>,
    exit_code: u8,
) -> Value {
    let (unresolved, ambiguous, uncovered, excluded) = split_diagnostics(diagnostics);
    json!({
        "schema": "agent-canon.graph.status.v1",
        "command": "status",
        "status": status,
        "profile": PUBLIC_PROFILE,
        "root": ".",
        "db_path": ".agent-canon/knowledge-graph/graph.sqlite",
        "input_fingerprint": input_fingerprint,
        "graph_fingerprint": graph_fingerprint,
        "integration_record": integration,
        "unresolved_count": unresolved.len(), "ambiguous_count": ambiguous.len(), "uncovered_count": uncovered.len(), "excluded_count": excluded.len(),
        "unresolved": unresolved, "ambiguous": ambiguous, "uncovered": uncovered, "excluded": excluded,
        "reason": reason, "stderr_summary": Value::Null, "producer_id": producer_id, "failure_stage": failure_stage, "exit_code": exit_code,
    })
}

fn build_response(
    material: &BuildMaterial,
    integration: &GraphIntegrationRecord,
    status: &str,
    publication: &str,
    durability: &str,
    failure_stage: Option<&str>,
    reason: Option<&str>,
) -> Value {
    let diagnostics = material
        .diagnostics
        .iter()
        .map(GraphDiagnostic::json)
        .collect::<Vec<_>>();
    let (unresolved, ambiguous, uncovered, excluded) = split_diagnostics(diagnostics);
    let exit_code = match status {
        "fresh" => 0,
        "incomplete" => 1,
        "publication-failed" => 5,
        _ => 4,
    };
    json!({
        "schema": "agent-canon.graph.build.v1", "command": "build", "status": status,
        "graph_status": if matches!(status, "fresh" | "incomplete") { Value::String(status.to_string()) } else { Value::Null },
        "profile": PUBLIC_PROFILE, "root": ".", "db_path": ".agent-canon/knowledge-graph/graph.sqlite",
        "input_fingerprint": material.input_fingerprint, "graph_fingerprint": material.graph_fingerprint,
        "unresolved_count": unresolved.len(), "ambiguous_count": ambiguous.len(), "uncovered_count": uncovered.len(), "excluded_count": excluded.len(),
        "unresolved": unresolved, "ambiguous": ambiguous, "uncovered": uncovered, "excluded": excluded,
        "reason": reason, "stderr_summary": Value::Null, "publication": publication, "durability": durability,
        "failure_stage": failure_stage, "exit_code": exit_code,
        "producer_artifacts": material.producer_artifacts.iter().map(ProducerArtifact::json).collect::<Vec<_>>(),
        "integration_record": if status == "fresh" { integration.json() } else { Value::Null },
    })
}

fn build_failure_response(args: &GraphBuildArgs, error: &GraphError) -> Value {
    let _ = args;
    let (status, publication, durability, stage, exit_code) = match error {
        GraphError::DirectorySync { .. } => (
            "publication-failed",
            "not-published",
            "durable",
            "directory-sync",
            5,
        ),
        _ => ("build-failed", "not-published", "not-durable", "build", 4),
    };
    json!({
        "schema": "agent-canon.graph.build.v1", "command": "build", "status": status, "graph_status": Value::Null,
        "profile": PUBLIC_PROFILE, "root": ".", "db_path": ".agent-canon/knowledge-graph/graph.sqlite",
        "input_fingerprint": Value::Null, "graph_fingerprint": Value::Null,
        "unresolved_count": 0, "ambiguous_count": 0, "uncovered_count": 0, "excluded_count": 0,
        "unresolved": [], "ambiguous": [], "uncovered": [], "excluded": [],
        "reason": error.to_string(), "stderr_summary": Value::Null, "publication": publication, "durability": durability,
        "failure_stage": stage, "exit_code": exit_code, "producer_artifacts": [],
    })
}

fn status_error_response(args: &GraphStatusArgs, error: &GraphError) -> Value {
    let root = resolve_root(&args.root).unwrap_or_else(|_| args.root.clone());
    let (status, exit) = match error {
        GraphError::Producer { .. } => ("build-failed", 4),
        GraphError::Unavailable { .. } => ("unavailable", 3),
        _ => ("invalid", 3),
    };
    status_response(
        &root,
        status,
        None,
        None,
        None,
        Vec::new(),
        Some(&error.to_string()),
        None,
        Some("producer-probe"),
        exit,
    )
}

fn query_response_from_status(
    args: &GraphQueryArgs,
    _root: &Path,
    status: &Value,
    nodes: Vec<Value>,
    facts: Vec<Value>,
) -> Value {
    json!({
        "schema": "agent-canon.graph.query.v1", "command": "query",
        "status": status.get("status").cloned().unwrap_or_else(|| json!("invalid")), "profile": PUBLIC_PROFILE, "root": ".", "db_path": ".agent-canon/knowledge-graph/graph.sqlite",
        "path": args.path, "all": args.all, "relation": args.relation, "direction": args.direction.as_str(), "depth": args.depth,
        "graph_fingerprint": status.get("graph_fingerprint").cloned().unwrap_or(Value::Null), "reason": status.get("reason").cloned().unwrap_or(Value::Null), "stderr_summary": Value::Null,
        "exit_code": status.get("exit_code").cloned().unwrap_or_else(|| json!(3)),
        "unresolved_count": status.get("unresolved_count").cloned().unwrap_or_else(|| json!(0)), "ambiguous_count": status.get("ambiguous_count").cloned().unwrap_or_else(|| json!(0)), "uncovered_count": status.get("uncovered_count").cloned().unwrap_or_else(|| json!(0)), "excluded_count": status.get("excluded_count").cloned().unwrap_or_else(|| json!(0)),
        "nodes": nodes, "facts": facts,
        "unresolved": status.get("unresolved").cloned().unwrap_or_else(|| json!([])), "ambiguous": status.get("ambiguous").cloned().unwrap_or_else(|| json!([])), "uncovered": status.get("uncovered").cloned().unwrap_or_else(|| json!([])), "excluded": status.get("excluded").cloned().unwrap_or_else(|| json!([])),
    })
}

fn query_error_response(args: &GraphQueryArgs, error: &GraphError) -> Value {
    let root = resolve_root(&args.root).unwrap_or_else(|_| args.root.clone());
    let status = status_error_response(
        &GraphStatusArgs {
            root: root.clone(),
            profile: args.profile.clone(),
            format: args.format,
        },
        error,
    );
    query_response_from_status(args, &root, &status, Vec::new(), Vec::new())
}

fn context_response_from_status(
    args: &GraphContextArgs,
    _root: &Path,
    status: &Value,
    resolved_path: Option<String>,
    owner: Option<String>,
    witnesses: Vec<Value>,
    items: Vec<Value>,
    runtime_measurements: Vec<Value>,
    context_diagnostics: Vec<Value>,
) -> Value {
    let source_span = items.iter().find_map(|item| {
        item.get("source_span")
            .cloned()
            .filter(|value| !value.is_null())
    });
    json!({
        "schema": "agent-canon.graph.context.v1", "command": "context",
        "status": status.get("status").cloned().unwrap_or_else(|| json!("invalid")), "profile": PUBLIC_PROFILE, "root": ".", "db_path": ".agent-canon/knowledge-graph/graph.sqlite",
        "claim_path": args.path, "token": args.token, "resolved_path": resolved_path, "source_span": source_span, "owner": owner,
        "dependency_witnesses": witnesses, "items": items, "runtime_measurements": runtime_measurements, "context_diagnostics": context_diagnostics, "producer": "source-snapshot",
        "semantic_index": "missing", "semantic_index_path": Value::Null, "semantic_index_content_sha256": Value::Null,
        "graph_fingerprint": status.get("graph_fingerprint").cloned().unwrap_or(Value::Null), "reason": status.get("reason").cloned().unwrap_or(Value::Null), "stderr_summary": Value::Null,
        "exit_code": status.get("exit_code").cloned().unwrap_or_else(|| json!(3)),
        "unresolved_count": status.get("unresolved_count").cloned().unwrap_or_else(|| json!(0)), "ambiguous_count": status.get("ambiguous_count").cloned().unwrap_or_else(|| json!(0)), "uncovered_count": status.get("uncovered_count").cloned().unwrap_or_else(|| json!(0)), "excluded_count": status.get("excluded_count").cloned().unwrap_or_else(|| json!(0)),
        "unresolved": status.get("unresolved").cloned().unwrap_or_else(|| json!([])), "ambiguous": status.get("ambiguous").cloned().unwrap_or_else(|| json!([])), "uncovered": status.get("uncovered").cloned().unwrap_or_else(|| json!([])), "excluded": status.get("excluded").cloned().unwrap_or_else(|| json!([])),
    })
}

fn context_error_response(args: &GraphContextArgs, error: &GraphError) -> Value {
    let root = resolve_root(&args.root).unwrap_or_else(|_| args.root.clone());
    let status = status_error_response(
        &GraphStatusArgs {
            root: root.clone(),
            profile: args.profile.clone(),
            format: args.format,
        },
        error,
    );
    context_response_from_status(
        args,
        &root,
        &status,
        None,
        None,
        Vec::new(),
        Vec::new(),
        Vec::new(),
        Vec::new(),
    )
}

fn context_item(
    kind: &str,
    value: &str,
    source_store: &str,
    producer: Option<&str>,
    source_path: Option<&str>,
    source_span: Option<Value>,
    evidence_ref: Option<&str>,
    authority: &str,
) -> Value {
    json!({
        "kind": kind, "value": value, "source_store": source_store, "producer": producer, "source_path": source_path, "source_span": source_span,
        "evidence_ref": evidence_ref, "authority": authority, "rank": Value::Null, "score": Value::Null, "bucket": Value::Null, "excerpt": Value::Null, "cache_state": Value::Null,
    })
}

fn dependency_witness_json(
    fact: &Value,
    paths_by_id: &BTreeMap<String, String>,
) -> Result<Value, GraphError> {
    let required_string = |field: &str| {
        fact.get(field)
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| GraphError::Validation {
                stage: "context-witness".to_string(),
                reason: format!("dependency fact lacks {field}"),
            })
    };
    let edge_id = required_string("id")?;
    let from_id = required_string("from")?;
    let to_id = required_string("to")?;
    let endpoint_path = |endpoint: &str| {
        paths_by_id
            .get(endpoint)
            .cloned()
            .ok_or_else(|| GraphError::Validation {
                stage: "context-witness".to_string(),
                reason: format!("dependency fact {edge_id} endpoint lacks RepoPath: {endpoint}"),
            })
    };
    Ok(json!({
        "edge_id": edge_id,
        "relation": "dependency",
        "from": endpoint_path(from_id)?,
        "to": endpoint_path(to_id)?,
        "owner": fact.get("owner").cloned().unwrap_or(Value::Null),
        "source_path": required_string("source_path")?,
        "source_span": fact.get("source_span").cloned().unwrap_or(Value::Null),
        "producer": required_string("producer")?,
        "evidence_ref": required_string("evidence_ref")?,
        "authority": required_string("authority")?,
    }))
}

fn split_diagnostics(diagnostics: Vec<Value>) -> (Vec<Value>, Vec<Value>, Vec<Value>, Vec<Value>) {
    let mut unresolved = Vec::new();
    let mut ambiguous = Vec::new();
    let mut uncovered = Vec::new();
    let mut excluded = Vec::new();
    for diagnostic in diagnostics {
        match diagnostic.get("set").and_then(Value::as_str) {
            Some("unresolved") => unresolved.push(diagnostic),
            Some("ambiguous") => ambiguous.push(diagnostic),
            Some("uncovered") => uncovered.push(diagnostic),
            Some("excluded") => excluded.push(diagnostic),
            _ => unresolved.push(diagnostic),
        }
    }
    (unresolved, ambiguous, uncovered, excluded)
}

fn graph_diagnostic(
    set: &str,
    code: &str,
    severity: &str,
    relation: Option<&str>,
    path: Option<&str>,
    target: Option<&str>,
    source_span: Option<SourceSpan>,
    reason: &str,
    producer: &str,
    evidence_ref: &str,
) -> GraphDiagnostic {
    let id = format!(
        "diagnostic:{}",
        hash_parts(&[
            set,
            code,
            severity,
            relation.unwrap_or(""),
            path.unwrap_or(""),
            target.unwrap_or(""),
            reason,
            producer,
            evidence_ref,
        ])
    );
    GraphDiagnostic {
        id,
        set: set.to_string(),
        code: code.to_string(),
        severity: severity.to_string(),
        relation: relation.map(ToString::to_string),
        path: path.map(ToString::to_string),
        target: target.map(ToString::to_string),
        source_span,
        reason: reason.to_string(),
        producer: producer.to_string(),
        evidence_ref: evidence_ref.to_string(),
        suggested_action_json: canonical_json(
            &json!({"action": "repair-owner-source", "owner": producer, "retryable": true}),
        ),
    }
}

fn integration_record(material: &BuildMaterial, verified: bool) -> GraphIntegrationRecord {
    GraphIntegrationRecord {
        root: ".".to_string(),
        db_path: ".agent-canon/knowledge-graph/graph.sqlite".to_string(),
        profile: PUBLIC_PROFILE.to_string(),
        source_snapshot_profile: SOURCE_PROFILE.to_string(),
        snapshot_head: snapshot_head(&material.snapshot).to_string(),
        input_fingerprint: material.input_fingerprint.clone(),
        graph_fingerprint: material.graph_fingerprint.clone(),
        contract_fingerprint: material.contract.fingerprint(),
        producer_artifacts: material.producer_artifacts.clone(),
        verified,
        verification_code: if verified {
            "graph.integration.verified"
        } else {
            "graph.integration.unverified"
        }
        .to_string(),
    }
}

fn graph_fingerprint(
    input: &str,
    nodes: &[SourceNode],
    facts: &[GraphFact],
    diagnostics: &[GraphDiagnostic],
    producers: &[ProducerArtifact],
    contract: &GraphContractWitness,
) -> String {
    let node_records = nodes
        .iter()
        .map(|node| {
            (
                node.id.clone(),
                json!({"id": node.id, "payload": node.payload}),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let fact_records = facts
        .iter()
        .map(|fact| (fact.id.clone(), fact.json()))
        .collect::<BTreeMap<_, _>>();
    let diagnostic_records = diagnostics
        .iter()
        .map(|diagnostic| (diagnostic.id.clone(), diagnostic.json()))
        .collect::<BTreeMap<_, _>>();
    let producer_records = producers
        .iter()
        .map(|producer| (producer.producer_id.clone(), producer.json()))
        .collect::<BTreeMap<_, _>>();
    graph_fingerprint_records(
        input,
        node_records,
        fact_records,
        diagnostic_records,
        producer_records,
        contract.json(),
    )
}

fn graph_fingerprint_records(
    input: &str,
    nodes: BTreeMap<String, Value>,
    facts: BTreeMap<String, Value>,
    diagnostics: BTreeMap<String, Value>,
    producers: BTreeMap<String, Value>,
    contract: Value,
) -> String {
    hash_bytes(
        canonical_json(&json!({
            "input_fingerprint": input,
            "nodes": nodes,
            "facts": facts,
            "diagnostics": diagnostics,
            "producers": producers,
            "mathematical_contract": contract,
        }))
        .as_bytes(),
    )
}

fn graph_input_fingerprint(snapshot: &ManifestSnapshot, producers: &[ProducerArtifact]) -> String {
    let producer_identity = producers
        .iter()
        .map(producer_input_identity)
        .collect::<Vec<_>>()
        .join("\n");
    hash_parts(&[
        snapshot_fingerprint(snapshot),
        "graph_profile=default\0source_snapshot_profile=parent",
        GRAPH_SCHEMA_VERSION,
        &producer_identity,
    ])
}

fn producer_input_identity(producer: &ProducerArtifact) -> String {
    if producer.producer_id == "runtime-dashboard" {
        format!(
            "{}\0{}\0non-authorizing-observation-projection",
            producer.producer_id, producer.version
        )
    } else {
        format!(
            "{}\0{}\0{}",
            producer.producer_id, producer.version, producer.content_sha256
        )
    }
}

fn source_node_id(path: &str) -> String {
    format!("node:source:{}", hash_parts(&[path]))
}

fn selector_node_id(selector: &str) -> String {
    let family = selector
        .split_once(':')
        .map(|(prefix, _)| prefix)
        .filter(|prefix| {
            matches!(
                *prefix,
                "owner"
                    | "scope"
                    | "surface"
                    | "symbol"
                    | "external"
                    | "directory"
                    | "path-pattern"
            )
        })
        .unwrap_or("source");
    format!("node:{family}:{}", hash_parts(&[selector]))
}

fn source_span_json(span: &SourceSpan) -> Value {
    json!({"path": span.path, "start_line": span.start_line, "start_column": span.start_column, "end_line": span.end_line, "end_column": span.end_column})
}

fn source_scalar_offsets(
    root: &Path,
    span: Option<&SourceSpan>,
) -> Result<(usize, usize), GraphError> {
    let Some(span) = span else {
        return Ok((0, 0));
    };
    let relative = Path::new(&span.path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(GraphError::Validation {
            stage: "source-span".to_string(),
            reason: format!("source span path is outside root: {}", span.path),
        });
    }
    let bytes = fs::read(root.join(relative)).map_err(|error| GraphError::Validation {
        stage: "source-span".to_string(),
        reason: format!("{}: {error}", span.path),
    })?;
    let text = std::str::from_utf8(&bytes).map_err(|error| GraphError::Validation {
        stage: "source-span".to_string(),
        reason: format!("{}: source is not UTF-8: {error}", span.path),
    })?;
    let mut lines = Vec::<(usize, usize)>::new();
    let mut byte_start = 0usize;
    for part in text.split_inclusive('\n') {
        let byte_end = byte_start + part.len() - usize::from(part.ends_with('\n'));
        lines.push((byte_start, byte_end));
        byte_start += part.len();
    }
    if text.is_empty() {
        lines.push((0, 0));
    } else if text.ends_with('\n') {
        lines.push((text.len(), text.len()));
    }
    let offset = |line: usize, column: usize, label: &str| -> Result<usize, GraphError> {
        let (line_start, line_end) = lines
            .get(line.checked_sub(1).ok_or_else(|| GraphError::Validation {
                stage: "source-span".to_string(),
                reason: format!("{}: {label} line is zero", span.path),
            })?)
            .copied()
            .ok_or_else(|| GraphError::Validation {
                stage: "source-span".to_string(),
                reason: format!("{}: missing {label} line {line}", span.path),
            })?;
        let byte_column = column
            .checked_sub(1)
            .ok_or_else(|| GraphError::Validation {
                stage: "source-span".to_string(),
                reason: format!("{}: {label} column is zero", span.path),
            })?;
        let absolute =
            line_start
                .checked_add(byte_column)
                .ok_or_else(|| GraphError::Validation {
                    stage: "source-span".to_string(),
                    reason: format!("{}: {label} byte offset overflow", span.path),
                })?;
        if absolute > line_end || !text.is_char_boundary(absolute) {
            return Err(GraphError::Validation {
                stage: "source-span".to_string(),
                reason: format!(
                    "{}: {label} column {column} is not a valid UTF-8 byte boundary",
                    span.path
                ),
            });
        }
        Ok(text[..absolute].chars().count())
    };
    let start = offset(span.start_line, span.start_column, "start")?;
    let end = offset(span.end_line, span.end_column, "end")?;
    if start > end {
        return Err(GraphError::Validation {
            stage: "source-span".to_string(),
            reason: format!("{}: source span end precedes start", span.path),
        });
    }
    Ok((start, end))
}

fn repo_artifact_ref(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn producer_artifact_ref(producer_id: &str, relative_path: &str, content_sha256: &str) -> String {
    format!("producer:{producer_id}/{relative_path}#sha256={content_sha256}")
}

fn producer_artifact_payloads_json(artifacts: &[ProducerArtifact]) -> String {
    let payloads = artifacts
        .iter()
        .map(|artifact| {
            (
                format!("{}:{}", artifact.producer_id, artifact.content_sha256),
                Value::String(base64_standard(&artifact.payload)),
            )
        })
        .collect::<Map<String, Value>>();
    canonical_json(&Value::Object(payloads))
}

fn base64_standard(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut output = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let value = ((chunk[0] as u32) << 16)
            | ((chunk.get(1).copied().unwrap_or(0) as u32) << 8)
            | chunk.get(2).copied().unwrap_or(0) as u32;
        output.push(TABLE[((value >> 18) & 0x3f) as usize] as char);
        output.push(TABLE[((value >> 12) & 0x3f) as usize] as char);
        output.push(if chunk.len() > 1 {
            TABLE[((value >> 6) & 0x3f) as usize] as char
        } else {
            '='
        });
        output.push(if chunk.len() > 2 {
            TABLE[(value & 0x3f) as usize] as char
        } else {
            '='
        });
    }
    output
}

fn write_synced_file(path: &Path, bytes: &[u8]) -> Result<(), GraphError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| GraphError::CandidateWrite {
            reason: format!("create {}: {error}", parent.display()),
        })?;
    }
    let mut file = File::create(path).map_err(|error| GraphError::CandidateWrite {
        reason: format!("create {}: {error}", path.display()),
    })?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|error| GraphError::CandidateWrite {
            reason: format!("write {}: {error}", path.display()),
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

fn hash_bytes(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn canonical_json(value: &Value) -> String {
    match value {
        Value::Object(object) => {
            let mut keys = object.keys().collect::<Vec<_>>();
            keys.sort();
            let body = keys
                .into_iter()
                .map(|key| {
                    format!(
                        "{}:{}",
                        serde_json::to_string(key).unwrap_or_default(),
                        canonical_json(&object[key])
                    )
                })
                .collect::<Vec<_>>()
                .join(",");
            format!("{{{body}}}")
        }
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(canonical_json)
                .collect::<Vec<_>>()
                .join(",")
        ),
        _ => serde_json::to_string(value).unwrap_or_else(|_| "null".to_string()),
    }
}

fn now_nanos() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_contract() -> GraphContractWitness {
        GraphContractWitness {
            candidate_sources: BTreeSet::new(),
            excluded_sources: BTreeSet::new(),
            eligible_sources: BTreeSet::new(),
            declarations: BTreeSet::new(),
            accepted_relations: BTreeSet::new(),
            graph_members: BTreeSet::new(),
            profile_members: BTreeSet::new(),
            relation_exclusions: BTreeSet::new(),
            unresolved: BTreeSet::new(),
            ambiguous: BTreeSet::new(),
            uncovered: BTreeSet::new(),
            source_identity: BTreeMap::new(),
            relation_endpoints: BTreeMap::new(),
            reverse_projection: BTreeMap::new(),
        }
    }

    fn resign_contract(value: &mut Value) {
        value
            .as_object_mut()
            .expect("contract object")
            .remove("contract_fingerprint");
        let fingerprint = hash_bytes(canonical_json(value).as_bytes());
        value.as_object_mut().expect("contract object").insert(
            "contract_fingerprint".to_string(),
            Value::String(fingerprint),
        );
    }

    #[test]
    fn profile_adapter_is_one_way() {
        assert_eq!(snapshot_profile_for_graph("default").unwrap(), "parent");
        assert!(snapshot_profile_for_graph("parent").is_err());
    }

    #[test]
    fn omitted_and_explicit_default_profiles_are_equal() {
        let omitted = parse_build_args(&[]).expect("omitted profile");
        let explicit = parse_build_args(&["--profile".to_string(), "default".to_string()])
            .expect("explicit default profile");
        assert_eq!(omitted.root, explicit.root);
        assert_eq!(omitted.profile, explicit.profile);
        assert_eq!(
            snapshot_profile_for_graph(&omitted.profile).unwrap(),
            snapshot_profile_for_graph(&explicit.profile).unwrap()
        );
    }

    #[test]
    fn integration_record_validation_rejects_profile_mismatch() {
        let connection = Connection::open_in_memory().expect("in-memory SQLite");
        connection
            .execute_batch("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
            .expect("metadata schema");
        let contract = empty_contract().json();
        let contract_fingerprint = contract["contract_fingerprint"]
            .as_str()
            .expect("contract fingerprint");
        connection
            .execute(
                "INSERT INTO metadata(key,value) VALUES('mathematical_contract',?)",
                [canonical_json(&contract)],
            )
            .expect("contract metadata");
        let mut record = json!({
            "schema": "agent-canon.graph.integration.v1",
            "root": ".",
            "db_path": ".agent-canon/knowledge-graph/graph.sqlite",
            "schema_version": GRAPH_SCHEMA_VERSION,
            "profile": PUBLIC_PROFILE,
            "source_snapshot_profile": SOURCE_PROFILE,
            "snapshot_head": "0123456789abcdef",
            "input_fingerprint": "input",
            "graph_fingerprint": "graph",
            "contract_fingerprint": contract_fingerprint,
            "producer_artifacts": [],
            "verified": true,
            "verification_code": "graph.integration.verified",
        });
        connection
            .execute(
                "INSERT INTO metadata(key,value) VALUES('integration_record',?)",
                [canonical_json(&record)],
            )
            .expect("integration metadata");
        assert!(validated_integration_record(&connection, "input", "graph").is_ok());

        record["source_snapshot_profile"] = Value::String(PUBLIC_PROFILE.to_string());
        connection
            .execute(
                "UPDATE metadata SET value=? WHERE key='integration_record'",
                [canonical_json(&record)],
            )
            .expect("mismatched integration metadata");
        assert!(validated_integration_record(&connection, "input", "graph").is_err());
    }

    #[test]
    fn repo_path_rejects_escape() {
        assert!(normalize_repo_path("../outside").is_err());
        assert_eq!(
            normalize_repo_path("./documents/x.md").unwrap(),
            "documents/x.md"
        );
    }

    #[test]
    fn runtime_measurement_context_selects_matching_report_unit() {
        let measurements = vec![
            json!({"responsibility_unit_id": "unit-a"}),
            json!({"responsibility_unit_id": "unit-b"}),
        ];
        assert_eq!(
            select_runtime_measurements(
                measurements.clone(),
                "reports/agents/unit-b/design_brief.md"
            ),
            vec![json!({"responsibility_unit_id": "unit-b"})]
        );
        assert_eq!(
            select_runtime_measurements(measurements.clone(), "documents/README.md"),
            measurements
        );
        assert!(select_runtime_measurements(
            vec![json!({"responsibility_unit_id": "unit-a"})],
            "reports/agents/unit-missing/design_brief.md"
        )
        .is_empty());
    }

    #[test]
    fn dependency_witness_projects_repo_paths_not_node_ids() {
        let fact = json!({
            "id": "edge-1",
            "from": "node-a",
            "to": "node-b",
            "owner": "ManifestParser",
            "source_path": "a.py",
            "source_span": null,
            "producer": "source-snapshot",
            "evidence_ref": "source-snapshot:a.py:1",
            "authority": "declared",
        });
        let paths = BTreeMap::from([
            ("node-a".to_string(), "a.py".to_string()),
            ("node-b".to_string(), "b.py".to_string()),
        ]);
        let witness = dependency_witness_json(&fact, &paths).expect("path witness");
        assert_eq!(witness["from"], "a.py");
        assert_eq!(witness["to"], "b.py");
        assert!(dependency_witness_json(&fact, &BTreeMap::new()).is_err());
    }

    #[test]
    fn query_endpoint_projection_excludes_evidence_nodes() {
        let connection = Connection::open_in_memory().expect("in-memory graph");
        initialize_graph_schema(&connection).expect("Graph DSL schema");
        connection
            .execute(
                "INSERT INTO documents(id,path,title,kind,created_at) VALUES(?,?,?,?,?)",
                params!["doc", "graph.sqlite", "graph", "knowledge-graph", "time"],
            )
            .expect("document");
        for (id, layer, payload) in [
            (
                "node:a",
                "source",
                json!({"path":"a.py","selector":"a.py","source_member":true}),
            ),
            ("fact:edge", "evidence", json!({"fact_id":"edge"})),
        ] {
            connection
                .execute(
                    "INSERT INTO nodes(id,document_id,layer,kind,label,text,source_start,source_end,confidence,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    params![id, "doc", layer, "path", id, id, 0, 0, 1.0, canonical_json(&payload)],
                )
                .expect("node");
        }
        let nodes = load_nodes(&connection).expect("query nodes");
        assert_eq!(nodes.len(), 1);
        assert_eq!(nodes[0]["id"], "node:a");
    }

    #[test]
    fn finite_contract_directly_decides_partition_projection_and_completeness() {
        let mut contract = empty_contract();
        contract.candidate_sources = BTreeSet::from(["a".to_string(), "generated".to_string()]);
        contract.excluded_sources = BTreeSet::from(["generated".to_string()]);
        contract.eligible_sources = BTreeSet::from(["a".to_string()]);
        contract.graph_members = BTreeSet::from(["node:a".to_string()]);
        contract.profile_members = contract.graph_members.clone();
        contract
            .source_identity
            .insert("a".to_string(), "node:a".to_string());
        assert!(validate_contract_value(&contract.json()).is_ok());

        contract.unresolved.insert("diagnostic:u".to_string());
        let incomplete = contract.json();
        assert_eq!(
            incomplete["obligations"]["profile_complete"],
            Value::Bool(false)
        );
        assert!(validate_contract_value(&incomplete).is_ok());

        let mut false_completeness = incomplete;
        false_completeness["obligations"]["unresolved_empty"] = Value::Bool(true);
        resign_contract(&mut false_completeness);
        assert!(validate_contract_value(&false_completeness).is_err());

        let mut false_partition = contract.json();
        false_partition["finite_sets"]["U(S)"] = json!([]);
        resign_contract(&mut false_partition);
        assert!(validate_contract_value(&false_partition).is_err());
    }

    #[test]
    fn reverse_projection_is_a_typed_bijection() {
        let explicit = TypedRelation {
            id: "edge".to_string(),
            kind: RelationKind::Dependency,
            from: "node:a".to_string(),
            to: "node:b".to_string(),
            producer: "source-snapshot".to_string(),
            evidence_ref: "evidence".to_string(),
            inferred: false,
        };
        let reverse = TypedRelation {
            id: "reverse:edge".to_string(),
            kind: RelationKind::Dependency,
            from: "node:b".to_string(),
            to: "node:a".to_string(),
            producer: "graph-projection".to_string(),
            evidence_ref: "evidence".to_string(),
            inferred: true,
        };
        let mut contract = empty_contract();
        contract.accepted_relations.insert("edge".to_string());
        contract.graph_members = BTreeSet::from([
            "relation:edge".to_string(),
            "relation:reverse:edge".to_string(),
        ]);
        contract.profile_members = contract.graph_members.clone();
        contract
            .relation_endpoints
            .insert(explicit.id.clone(), explicit);
        contract
            .relation_endpoints
            .insert(reverse.id.clone(), reverse);
        contract
            .reverse_projection
            .insert("edge".to_string(), "reverse:edge".to_string());
        let valid = contract.json();
        assert!(validate_contract_value(&valid).is_ok());

        let mut invalid = valid;
        invalid["typed_functions"]["relation_endpoints"][1]["to"] = json!("node:wrong");
        resign_contract(&mut invalid);
        assert!(validate_contract_value(&invalid).is_err());
    }

    #[test]
    fn bounded_closure_is_the_least_fixed_point_of_typed_successors() {
        let facts = vec![
            json!({"id":"ab","kind":"dependency","from":"a","to":"b"}),
            json!({"id":"bc","kind":"dependency","from":"b","to":"c"}),
            json!({"id":"ca","kind":"dependency","from":"c","to":"a"}),
            json!({"id":"ignored","kind":"owner","from":"c","to":"d"}),
        ];
        let depth_one =
            least_fixed_point_closure("a", &facts, "dependency", GraphDirection::Outgoing, 1)
                .expect("depth-one closure");
        assert_eq!(
            depth_one.distance,
            BTreeMap::from([("a".to_string(), 0), ("b".to_string(), 1)])
        );
        let closure =
            least_fixed_point_closure("a", &facts, "dependency", GraphDirection::Outgoing, 3)
                .expect("least fixed point");
        assert_eq!(
            closure.distance,
            BTreeMap::from([
                ("a".to_string(), 0),
                ("b".to_string(), 1),
                ("c".to_string(), 2),
            ])
        );
        let (fixed, _) = closure_operator(
            &closure.distance,
            &facts,
            "dependency",
            GraphDirection::Outgoing,
            3,
        );
        assert_eq!(fixed, closure.distance);
        assert!(!closure.distance.contains_key("d"));
    }

    #[test]
    fn graph_fingerprint_is_preserved_under_input_order_permutation() {
        let node_a = SourceNode {
            id: "a".to_string(),
            selector: "a".to_string(),
            path: Some("a".to_string()),
            source_member: true,
            source_span: None,
            payload: json!({"path":"a"}),
        };
        let node_b = SourceNode {
            id: "b".to_string(),
            selector: "b".to_string(),
            path: Some("b".to_string()),
            source_member: true,
            source_span: None,
            payload: json!({"path":"b"}),
        };
        let fact = GraphFact {
            id: "edge".to_string(),
            layer: "source".to_string(),
            kind: "dependency".to_string(),
            from: "a".to_string(),
            to: Some("b".to_string()),
            owner: None,
            source_path: Some("a".to_string()),
            source_span: None,
            producer: "source-snapshot".to_string(),
            evidence_ref: "evidence".to_string(),
            authority: "ManifestParser".to_string(),
            inferred: false,
            dependency_detail: None,
            payload: json!({}),
        };
        let contract = empty_contract();
        let forward = graph_fingerprint(
            "input",
            &[node_a.clone(), node_b.clone()],
            std::slice::from_ref(&fact),
            &[],
            &[],
            &contract,
        );
        let reverse = graph_fingerprint("input", &[node_b, node_a], &[fact], &[], &[], &contract);
        assert_eq!(forward, reverse);
        let mutated = graph_fingerprint_records(
            "input",
            BTreeMap::new(),
            BTreeMap::from([("edge".to_string(), json!({"id":"edge","to":"changed"}))]),
            BTreeMap::new(),
            BTreeMap::new(),
            contract.json(),
        );
        assert_ne!(forward, mutated);
    }

    #[test]
    fn mutable_runtime_observations_do_not_self_invalidate_input_freshness() {
        let artifact = |producer_id: &str, content_sha256: &str| ProducerArtifact {
            producer_id: producer_id.to_string(),
            version: "v1".to_string(),
            command: "command".to_string(),
            root: ".".to_string(),
            content_sha256: content_sha256.to_string(),
            relation_families: Vec::new(),
            artifact_ref: "artifact".to_string(),
            payload: Vec::new(),
        };
        assert_eq!(
            producer_input_identity(&artifact("runtime-dashboard", "before")),
            producer_input_identity(&artifact("runtime-dashboard", "after"))
        );
        assert_ne!(
            producer_input_identity(&artifact("source-snapshot", "before")),
            producer_input_identity(&artifact("source-snapshot", "after"))
        );
    }

    #[test]
    fn directory_sync_failure_restores_exact_old_graph_state() {
        let temporary = TemporaryDirectory::create("atomic-publication-test")
            .expect("temporary publication root");
        let graph_root = temporary.path.join("knowledge-graph");
        let candidate_dir = graph_root.join(".candidate/test");
        fs::create_dir_all(&candidate_dir).expect("candidate directory");
        let target = graph_root.join("graph.sqlite");
        fs::write(&target, b"old-validated-state").expect("old graph");
        let candidate = candidate_dir.join("graph.sqlite");
        fs::write(&candidate, b"new-validated-state").expect("candidate graph");
        let old_state = durable_graph_state(&target).expect("old state witness");
        let result = publish_graph(
            &graph_root,
            CandidateHandle {
                dir: candidate_dir,
                db: candidate,
            },
            GraphBuildFailurePoint::DirectorySync,
        );
        assert!(matches!(result, Err(GraphError::DirectorySync { .. })));
        assert_durable_graph_state(&target, &old_state).expect("old state invariance");
        assert_eq!(
            fs::read(&target).expect("restored graph"),
            b"old-validated-state"
        );
    }

    #[test]
    fn source_spans_convert_utf8_byte_columns_to_scalar_offsets() {
        let temporary = TemporaryDirectory::create("source-span-test").expect("temporary root");
        let path = temporary.path.join("source.txt");
        fs::write(&path, "aéz\nβx\n").expect("unicode source");
        let span = SourceSpan {
            path: "source.txt".to_string(),
            start_line: 1,
            start_column: 2,
            end_line: 2,
            end_column: 3,
        };
        assert_eq!(
            source_scalar_offsets(&temporary.path, Some(&span)).expect("scalar offsets"),
            (1, 5)
        );
        let invalid = SourceSpan {
            start_column: 3,
            ..span
        };
        assert!(source_scalar_offsets(&temporary.path, Some(&invalid)).is_err());
    }
}
