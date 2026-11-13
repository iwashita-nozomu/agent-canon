// @dependency-start
// contract implementation
// responsibility Owns the SQLite-backed prose graph adapter, deterministic analysis layers, projections, diagnostics, and handoff artifacts.
// upstream design ../../../../../documents/prose-reasoning-graph/dsl-spec.md owns source anchoring and prose graph semantics
// upstream implementation structured_analysis.rs owns shared graph storage and the canonical prose lexicon
// upstream implementation graph_client.rs owns canonical dependency facts imported as evidence
// upstream implementation runtime_boundary.rs owns external graph DB and report paths
// downstream test ../../../../../tests/agent_tools/test_prose_reasoning_graph.py validates CLI behavior and external artifact identity
// @dependency-end

use agent_canon::runtime_boundary as runtime_artifacts;
use rusqlite::{params, Connection, OpenFlags, OptionalExtension, Row};
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cmp::Ordering;
use std::cmp::Reverse;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::LazyLock;

pub const SELECTOR: &str = "prose-reasoning-graph";
const SCHEMA_VERSION: i64 = 1;
const DEFAULT_PROFILE: &str = "writing";
const PROFILES: &[&str] = &[
    "writing",
    "logic",
    "experiment",
    "report",
    "academic",
    "paper",
    "all",
];
const LAYERS: &[&str] = &[
    "source",
    "form",
    "concept",
    "phase",
    "discourse",
    "argument",
    "evidence",
    "experiment",
    "presentation",
    "diagnostics",
    "edit-operation",
    "explanation",
    "projection",
];
const DEFAULT_DB_NAME: &str = "prose_graph.sqlite";
const DEFAULT_CACHE_HASH_LENGTH: usize = 12;
const SQLITE_BUSY_TIMEOUT_SECONDS: u64 = 30;
const WSL_MOUNT_MIN_PATH_PARTS: usize = 3;
const STRUCTURED_ANALYSIS_INVENTORY_STDOUT_KEY: &str =
    "STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY_JSON";
const FORM_NODE_LABEL_WORD_LIMIT: usize = 8;
const CONCEPT_CANDIDATE_LIMIT: usize = 12;
const CONCEPT_NODE_CONFIDENCE: f64 = 0.6;
const CONCEPT_EDGE_CONFIDENCE: f64 = 0.4;
const PHASE_INFERENCE_CONFIDENCE: f64 = 0.55;
const DISCOURSE_CONFIDENCE_FLOOR: f64 = 0.25;
const DISCOURSE_CONFIDENCE_CEILING: f64 = 0.95;
const DISCOURSE_CONFIDENCE_OVERLAP_OFFSET: f64 = 0.35;
const DISCOURSE_SHARED_TERM_LIMIT: usize = 8;
const EXTRACTED_NODE_LABEL_WORD_LIMIT: usize = 10;
const EXTRACTED_NODE_CONFIDENCE: f64 = 0.65;
const EVIDENCE_SUPPORT_MIN_OVERLAP: f64 = 0.12;
const TOPIC_JUMP_MAX_OVERLAP: f64 = 0.05;
const SPLIT_PARAGRAPH_SENTENCE_LIMIT: usize = 3;
const MERGE_PARAGRAPH_MIN_OVERLAP: f64 = 0.18;
const EXPLANATION_CLAIM_LIMIT: usize = 5;
const EXPLANATION_DISCOURSE_EDGE_LIMIT: usize = 6;
const DISPLAY_MATH_EMPTY_DELIMITER_LENGTH: usize = 4;
const EXPLANATION_DIAGNOSTIC_LIMIT: usize = 8;
const EXPLANATION_OPERATION_LIMIT: usize = 6;
const PROJECTION_VIEW_FALLBACK_CONFIDENCE: f64 = 0.4;
const DOCUMENT_CANON_FINDING_CONFIDENCE: f64 = 0.8;
const DEFAULT_ORDERING_CONFIDENCE: f64 = 1.0;
const NO_ORDERING_CONFIDENCE: f64 = 0.0;

static HYPOTHESIS_ASSIGNMENT: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"\bhypothesis\s+(?:is|=|:)").expect("fixed regex"));
static HYPOTHESIS_JA_ASSIGNMENT: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"仮説\s*は").expect("fixed regex"));
static METRIC_ASSIGNMENT: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"\bmetric\s+(?:is|=|:)").expect("fixed regex"));
static METRIC_JA_ASSIGNMENT: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"指標\s*は").expect("fixed regex"));
static BASELINE_ASSIGNMENT: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"\bbaseline\s+(?:is|=|:)").expect("fixed regex"));
static BASELINE_JA_ASSIGNMENT: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"ベースライン\s*は").expect("fixed regex"));
static EXPECTED_ASSIGNMENT: LazyLock<regex::Regex> = LazyLock::new(|| {
    regex::Regex::new(r"\bexpected(?:\s+result)?\s+(?:is|=|:)").expect("fixed regex")
});
static EXPECTED_JA_ASSIGNMENT: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"期待(?:結果)?\s*は").expect("fixed regex"));
static FORMULA_SYMBOL: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"[∑∏√≤≥≈→↦]").expect("fixed regex"));
static FORMULA_MATH: LazyLock<regex::Regex> = LazyLock::new(|| {
    regex::Regex::new(r"(?:\$[^$]*[=<>][^$]*\$|\\\([^)]*[=<>][^)]*\\\))").expect("fixed regex")
});
static FORMULA_ASSIGNMENT: LazyLock<regex::Regex> = LazyLock::new(|| {
    regex::Regex::new(r"\b[a-z][a-z0-9_]*\s*(?:=|<=|>=)\s*(?:[-+]?\d|[a-z][a-z0-9_]*\s*[+\-*/^])")
        .expect("fixed regex")
});
static STRUCTURED_BLOCK_PREFIX: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"^(?:```|\||[-*]\s+|\d+[.]\s+)").expect("fixed regex"));
static MERMAID_EDGE_PREFIX: LazyLock<regex::Regex> = LazyLock::new(|| {
    regex::Regex::new(r"^[A-Za-z0-9_]+\s*(?:-->|==>|-\.->|---|--)").expect("fixed regex")
});
static MERMAID_BLOCK_PREFIX: LazyLock<regex::Regex> = LazyLock::new(|| {
    regex::Regex::new(r"^(?:flowchart|graph|subgraph|end\b)").expect("fixed regex")
});
static MERMAID_NODE_PREFIX: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"^[A-Za-z0-9_]+\[").expect("fixed regex"));

const CLAIM_CUES: &[&str] = &[
    "should",
    "must",
    "need",
    "needs",
    "necessary",
    "therefore",
    "thus",
    "so ",
    "重要",
    "必要",
    "べき",
    "はず",
    "したがって",
];
const EVIDENCE_CUES: &[&str] = &[
    "because", "since", "evidence", "source", "shown", "measured", "doi", "http", "根拠", "出典",
    "証拠", "測定",
];
const EXPERIMENT_VOCABULARY_CUES: &[&str] = &[
    "experiment",
    "protocol",
    "仮説",
    "実験",
    "指標",
    "ベースライン",
    "期待",
    "expected",
    "hypothesis",
    "metric",
    "baseline",
];
const EXPERIMENT_ACTIVITY_CUES: &[&str] = &["experiment", "protocol", "実験"];
const GRAPH_TOPOLOGY_CONCEPTS: &[&str] = &[
    "graph",
    "dag",
    "node",
    "edge",
    "anchor",
    "projection",
    "projection-view",
    "projection_view",
    "グラフ",
    "ノード",
    "エッジ",
    "図",
];
const ALIGNED_ATTRIBUTE_CONCEPTS: &[&str] = &[
    "metric",
    "baseline",
    "expected",
    "result",
    "指標",
    "ベースライン",
    "期待",
];
const DECISION_SEQUENCE_CONCEPTS: &[&str] =
    &["option", "choice", "decision", "step", "選択肢", "判断"];
const PHASE_ORDER: &[&str] = &[
    "context",
    "hypothesis",
    "operationalization",
    "development",
    "limitation",
    "recommendation",
];
const SKILL_HANDOFF_TARGETS: &[&str] = &[
    "$long-form-writing",
    "$report-writing",
    "$academic-writing",
    "$paper-writing",
    "$literature-survey",
    "$structure-planning",
    "$formal-proof-workflow",
    "logic-gap-review",
    "citation-evidence-review",
    "$experiment-lifecycle",
    "$result-artifact-writeout",
];

#[derive(Clone, Debug, Serialize, PartialEq)]
struct Node {
    node_id: String,
    document_id: String,
    layer: String,
    kind: String,
    label: String,
    text: String,
    payload: Value,
    source_start: usize,
    source_end: usize,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
struct Edge {
    edge_id: String,
    layer: String,
    kind: String,
    from_node_id: String,
    to_node_id: String,
    order_kind: String,
    confidence: f64,
    payload: Value,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
struct Diagnostic {
    diagnostic_id: String,
    layer: String,
    severity: String,
    rule: String,
    message: String,
    target_node_id: String,
    target_edge_id: String,
    action: Value,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
struct EditOperation {
    operation_id: String,
    kind: String,
    target_ids: Vec<String>,
    reason: String,
    payload: Value,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
struct ProjectionView {
    view_id: String,
    profile: String,
    members: Vec<String>,
    role: String,
    reader_state_before: String,
    reader_state_after: String,
    abstraction_level: String,
    recommended_format: String,
    format_reason: String,
    inference_basis: Value,
    confidence: f64,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
struct ProjectionFormatEvidence {
    member_anchor_ids: Vec<String>,
    role: String,
    presentation_features: Vec<String>,
    presentation_feature_edges: Vec<String>,
    derived_layers: Vec<String>,
    derived_kinds: Vec<String>,
    edge_layers: Vec<String>,
    edge_kinds: Vec<String>,
}

#[derive(Clone, Debug)]
struct DependencyRecord {
    role: String,
    body: String,
    text: String,
    source_start: usize,
    source_end: usize,
}

#[derive(Clone, Debug, Default)]
struct Options {
    command: String,
    inputs: Vec<PathBuf>,
    db: Option<PathBuf>,
    kind: String,
    prompt: String,
    prompt_file: Option<PathBuf>,
    recursive: bool,
    profile: String,
    output: Option<PathBuf>,
    format: String,
    stats_out: Option<PathBuf>,
    repo_root: Option<PathBuf>,
    out_dir: Option<PathBuf>,
    structured_profile: String,
    structured_inventory_json: Option<PathBuf>,
    operation_id: Option<String>,
}

fn usage() -> &'static str {
    "usage: agent-canon prose-reasoning-graph <ingest|ingest-set|analyze|lint|project|outline|explain|integrate|rewrite-packet|skill-handoff|check-document> [options]"
}

fn parse_options(args: &[String]) -> Result<Option<Options>, String> {
    if args.iter().any(|arg| arg == "-h" || arg == "--help") {
        return Ok(None);
    }
    let command = args
        .first()
        .ok_or_else(|| "a command is required".to_owned())?
        .clone();
    let mut result = Options {
        command: command.clone(),
        kind: "document".into(),
        profile: DEFAULT_PROFILE.into(),
        format: "yaml".into(),
        structured_profile: "manual".into(),
        ..Options::default()
    };
    let names = [
        ("--db", 0),
        ("--kind", 1),
        ("--prompt", 2),
        ("--prompt-file", 3),
        ("--recursive", 4),
        ("--profile", 5),
        ("--out", 6),
        ("--format", 7),
        ("--stats-out", 8),
        ("--repo-root", 9),
        ("--out-dir", 10),
        ("--structured-profile", 11),
        ("--structured-inventory-json", 12),
        ("--op", 13),
    ];
    let mut index = 1;
    while index < args.len() {
        let raw = &args[index];
        if raw == "--" {
            result
                .inputs
                .extend(args[index + 1..].iter().map(PathBuf::from));
            break;
        }
        if !raw.starts_with('-') {
            result.inputs.push(PathBuf::from(raw));
            index += 1;
            continue;
        }
        let (flag, inline) = raw
            .split_once('=')
            .map_or((raw.as_str(), None), |(flag, value)| (flag, Some(value)));
        let option = crate::python_cli_options::resolve_long_option_prefix(flag, &names)
            .map_err(|_| format!("unrecognized or ambiguous argument: {raw}"))?;
        if option == 4 {
            if inline.is_some() {
                return Err(format!("argument {flag}: ignored explicit argument"));
            }
            result.recursive = true;
            index += 1;
            continue;
        }
        index += 1;
        let value = inline
            .map(str::to_owned)
            .or_else(|| args.get(index).cloned())
            .ok_or_else(|| format!("argument {flag}: expected one argument"))?;
        match option {
            0 => result.db = Some(value.into()),
            1 => result.kind = value,
            2 => result.prompt = value,
            3 => result.prompt_file = Some(value.into()),
            5 if PROFILES.contains(&value.as_str()) => result.profile = value,
            5 => return Err(format!("argument --profile: invalid choice: {value:?}")),
            6 => result.output = Some(value.into()),
            7 if ["yaml", "json"].contains(&value.as_str()) => result.format = value,
            7 => return Err(format!("argument --format: invalid choice: {value:?}")),
            8 => result.stats_out = Some(value.into()),
            9 => result.repo_root = Some(value.into()),
            10 => result.out_dir = Some(value.into()),
            11 => result.structured_profile = value,
            12 => result.structured_inventory_json = Some(value.into()),
            13 => result.operation_id = Some(value),
            _ => unreachable!(),
        }
        index += 1;
    }
    let needs_db = matches!(
        command.as_str(),
        "analyze"
            | "lint"
            | "project"
            | "outline"
            | "explain"
            | "integrate"
            | "rewrite-packet"
            | "skill-handoff"
    );
    if needs_db && result.db.is_none() {
        return Err("the following arguments are required: --db".into());
    }
    if matches!(
        command.as_str(),
        "lint"
            | "project"
            | "outline"
            | "explain"
            | "integrate"
            | "rewrite-packet"
            | "skill-handoff"
    ) && result.output.is_none()
    {
        return Err("the following arguments are required: --out".into());
    }
    if command == "rewrite-packet" && result.operation_id.is_none() {
        return Err("the following arguments are required: --op".into());
    }
    if command == "check-document" && result.inputs.len() != 1 {
        return Err("check-document requires exactly one input document".into());
    }
    if command == "ingest" && result.inputs.len() != 1 {
        return Err("ingest requires exactly one input document".into());
    }
    if command == "ingest-set" && result.inputs.is_empty() {
        return Err("ingest-set requires one or more input paths".into());
    }
    if command == "check-document" && result.out_dir.is_none() {
        return Err("the following arguments are required: --out-dir".into());
    }
    if ![
        "ingest",
        "ingest-set",
        "analyze",
        "lint",
        "project",
        "outline",
        "explain",
        "integrate",
        "rewrite-packet",
        "skill-handoff",
        "check-document",
    ]
    .contains(&command.as_str())
    {
        return Err(format!("invalid choice: {command:?}"));
    }
    Ok(Some(result))
}

fn graph_source_root() -> PathBuf {
    for name in ["AGENT_CANON_SOURCE_ROOT", "AGENT_CANON_PARENT_ROOT"] {
        if let Some(value) = std::env::var_os(name).filter(|value| !value.is_empty()) {
            if let Ok(path) = PathBuf::from(value).canonicalize() {
                return path;
            }
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .unwrap_or(Path::new("."))
        .to_path_buf()
}

fn runtime_boundary(
    create: bool,
) -> Result<agent_canon::runtime_boundary::RuntimeArtifactBoundary, String> {
    runtime_artifacts::RuntimeArtifactBoundary::for_source(&graph_source_root(), None, create)
}

fn runtime_resolve(path: &Path, purpose: &str) -> Result<PathBuf, String> {
    runtime_boundary(true)?
        .resolve(path)
        .map_err(|error| format!("{purpose}: {error}"))
}

fn write_output(path: &Path, text: &str) -> Result<PathBuf, String> {
    let boundary = runtime_boundary(true)?;
    let target = boundary.resolve(path)?;
    let parent = target
        .parent()
        .ok_or_else(|| "runtime output path has no parent".to_owned())?;
    let relative = parent
        .strip_prefix(boundary.root())
        .map_err(|_| "runtime output parent escapes root")?;
    if !relative.as_os_str().is_empty() {
        boundary.ensure_directory(relative)?;
    }
    boundary.atomic_write_text(path, text, 0o600)
}

fn utc_now() -> String {
    time::OffsetDateTime::now_utc()
        .replace_nanosecond(0)
        .unwrap_or_else(|_| time::OffsetDateTime::now_utc())
        .format(&time::format_description::well_known::Rfc3339)
        .unwrap_or_default()
}

fn compact_json(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "null".into())
}
fn scalar(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string())
}

fn set_metadata(connection: &Connection, key: &str, value: &Value) -> Result<(), String> {
    connection
        .execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES (?1,?2)",
            params![key, compact_json(value)],
        )
        .map_err(|error| error.to_string())?;
    Ok(())
}

fn metadata_json(connection: &Connection, key: &str, default: Value) -> Result<Value, String> {
    let raw = connection
        .query_row(
            "SELECT value FROM metadata WHERE key=?1",
            params![key],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|error| error.to_string())?;
    raw.map(|value| serde_json::from_str(&value).map_err(|error| error.to_string()))
        .unwrap_or(Ok(default))
}

fn initialize_schema(connection: &Connection) -> Result<(), String> {
    crate::structured_analysis::initialize_graph_schema(connection)
        .map_err(|error| error.to_string())?;
    connection.execute_batch("CREATE TABLE IF NOT EXISTS edit_operations(id TEXT PRIMARY KEY,kind TEXT NOT NULL,target_ids_json TEXT NOT NULL,reason TEXT NOT NULL,payload_json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS judgements(id TEXT PRIMARY KEY,target_type TEXT NOT NULL,target_id TEXT NOT NULL,source TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL);").map_err(|error|error.to_string())?;
    set_metadata(connection, "schema_version", &json!(SCHEMA_VERSION))
}

fn connect(path: &Path) -> Result<Connection, String> {
    let physical = runtime_resolve(path, "prose-reasoning-graph-db")?;
    if let Some(parent) = physical.parent() {
        let boundary = runtime_boundary(true)?;
        let relative = parent
            .strip_prefix(boundary.root())
            .map_err(|_| "database path escapes runtime root")?;
        if !relative.as_os_str().is_empty() {
            boundary.ensure_directory(relative)?;
        }
    }
    let connection = if is_wsl_mount(&physical) {
        let quoted = percent_encode_path(&physical);
        Connection::open_with_flags(
            format!("file:{quoted}?mode=rwc&nolock=1"),
            OpenFlags::SQLITE_OPEN_READ_WRITE
                | OpenFlags::SQLITE_OPEN_CREATE
                | OpenFlags::SQLITE_OPEN_URI,
        )
        .map_err(|error| error.to_string())?
    } else {
        Connection::open(&physical).map_err(|error| error.to_string())?
    };
    connection
        .busy_timeout(std::time::Duration::from_secs(SQLITE_BUSY_TIMEOUT_SECONDS))
        .map_err(|error| error.to_string())?;
    connection
        .execute_batch("PRAGMA foreign_keys = ON;")
        .map_err(|error| error.to_string())?;
    Ok(connection)
}

fn is_wsl_mount(path: &Path) -> bool {
    path.is_absolute()
        && path.components().count() >= WSL_MOUNT_MIN_PATH_PARTS
        && path
            .components()
            .nth(1)
            .is_some_and(|component| component.as_os_str() == "mnt")
}

fn percent_encode_path(path: &Path) -> String {
    let mut output = String::new();
    for byte in path.to_string_lossy().as_bytes() {
        if byte.is_ascii_alphanumeric() || b"/-._~:".contains(byte) {
            output.push(*byte as char);
        } else {
            output.push_str(&format!("%{byte:02X}"));
        }
    }
    output
}

fn default_graph_db_path(inputs: &[PathBuf]) -> Result<PathBuf, String> {
    let cwd = std::env::current_dir()
        .map_err(|error| error.to_string())?
        .canonicalize()
        .map_err(|error| error.to_string())?;
    let repo_label = sanitize_cache_segment(
        cwd.file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("workspace"),
    );
    let label = if inputs.len() == 1 {
        let first = &inputs[0];
        if first.is_file() {
            first
                .file_stem()
                .and_then(|value| value.to_str())
                .unwrap_or("workspace")
                .to_owned()
        } else {
            first
                .file_name()
                .and_then(|value| value.to_str())
                .unwrap_or("workspace")
                .to_owned()
        }
    } else {
        "ingest-set".into()
    };
    let basis = inputs
        .iter()
        .map(|path| resolved_path_text(path))
        .collect::<Vec<_>>()
        .join("\n");
    let path = PathBuf::from("prose-reasoning-graph")
        .join(format!(
            "{}-{}",
            repo_label,
            short_hash(&cwd.to_string_lossy())
        ))
        .join(format!(
            "{}-{}",
            sanitize_cache_segment(&label),
            short_hash(&basis)
        ))
        .join(DEFAULT_DB_NAME);
    runtime_resolve(&path, "prose-reasoning-graph-db")
}

fn short_hash(value: &str) -> String {
    Sha256::digest(value.as_bytes())[..DEFAULT_CACHE_HASH_LENGTH / 2]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
fn sanitize_cache_segment(value: &str) -> String {
    let filtered = value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || "._-".contains(ch) {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>();
    let filtered = filtered.trim_matches('_');
    if filtered.is_empty() {
        "workspace".into()
    } else {
        filtered.into()
    }
}
fn resolved_path_text(path: &Path) -> String {
    path.canonicalize()
        .unwrap_or_else(|_| std::env::current_dir().unwrap_or_default().join(path))
        .to_string_lossy()
        .replace('\\', "/")
}

fn graph_db_path(options: &Options) -> Result<PathBuf, String> {
    let path = if let Some(path) = options.db.as_deref() {
        path.to_path_buf()
    } else {
        default_graph_db_path(&options.inputs)?
    };
    runtime_resolve(&path, "prose-reasoning-graph-db")
}

fn clear_database(connection: &Connection) -> Result<(), String> {
    connection.execute_batch("DELETE FROM metadata; DELETE FROM judgements; DELETE FROM edit_operations; DELETE FROM diagnostics; DELETE FROM edges; DELETE FROM nodes; DELETE FROM documents;").map_err(|error|error.to_string())?;
    Ok(())
}

fn insert_node(connection: &Connection, node: &Node, confidence: f64) -> Result<(), String> {
    connection.execute("INSERT OR REPLACE INTO nodes(id,document_id,layer,kind,label,text,source_start,source_end,confidence,payload_json) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)",params![node.node_id,node.document_id,node.layer,node.kind,node.label,node.text,node.source_start as i64,node.source_end as i64,confidence,compact_json(&node.payload)]).map_err(|error|error.to_string())?;
    Ok(())
}

fn insert_edge(connection: &Connection, edge: &Edge) -> Result<(), String> {
    connection.execute("INSERT OR REPLACE INTO edges(id,layer,kind,from_node_id,to_node_id,order_kind,confidence,evidence_node_id,payload_json) VALUES (?1,?2,?3,?4,?5,?6,?7,NULL,?8)",params![edge.edge_id,edge.layer,edge.kind,edge.from_node_id,edge.to_node_id,edge.order_kind,edge.confidence,compact_json(&edge.payload)]).map_err(|error|error.to_string())?;
    Ok(())
}

fn insert_diagnostic(connection: &Connection, value: &Diagnostic) -> Result<(), String> {
    connection.execute("INSERT OR REPLACE INTO diagnostics(id,layer,target_node_id,target_edge_id,severity,rule,message,suggested_action_json) VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",params![value.diagnostic_id,value.layer,value.target_node_id,value.target_edge_id,value.severity,value.rule,value.message,compact_json(&value.action)]).map_err(|error|error.to_string())?;
    Ok(())
}

fn insert_operation(connection: &Connection, value: &EditOperation) -> Result<(), String> {
    connection.execute("INSERT OR REPLACE INTO edit_operations(id,kind,target_ids_json,reason,payload_json) VALUES (?1,?2,?3,?4,?5)",params![value.operation_id,value.kind,compact_json(&json!(value.target_ids)),value.reason,compact_json(&value.payload)]).map_err(|error|error.to_string())?;
    Ok(())
}

fn payload_value(raw: &str) -> Value {
    serde_json::from_str(raw).unwrap_or_else(|_| json!({}))
}

fn fetch_nodes(
    connection: &Connection,
    layer: Option<&str>,
    kind: Option<&str>,
) -> Result<Vec<Node>, String> {
    let sql = match (layer.is_some(), kind.is_some()) {
        (true, true) => {
            "SELECT * FROM nodes WHERE layer=?1 AND kind=?2 ORDER BY document_id,source_start,id"
        }
        (true, false) => "SELECT * FROM nodes WHERE layer=?1 ORDER BY document_id,source_start,id",
        (false, true) => "SELECT * FROM nodes WHERE kind=?1 ORDER BY document_id,source_start,id",
        (false, false) => "SELECT * FROM nodes ORDER BY document_id,source_start,id",
    };
    let mut statement = connection.prepare(sql).map_err(|error| error.to_string())?;
    let mut rows = if let (Some(layer), Some(kind)) = (layer, kind) {
        statement.query(params![layer, kind])
    } else if let Some(layer) = layer {
        statement.query(params![layer])
    } else if let Some(kind) = kind {
        statement.query(params![kind])
    } else {
        statement.query([])
    }
    .map_err(|error| error.to_string())?;
    let mut output = Vec::new();
    while let Some(row) = rows.next().map_err(|error| error.to_string())? {
        output.push(node_from_row(row)?);
    }
    Ok(output)
}

fn node_from_row(row: &Row<'_>) -> Result<Node, String> {
    Ok(Node {
        node_id: row.get("id").map_err(|error| error.to_string())?,
        document_id: row.get("document_id").map_err(|error| error.to_string())?,
        layer: row.get("layer").map_err(|error| error.to_string())?,
        kind: row.get("kind").map_err(|error| error.to_string())?,
        label: row.get("label").map_err(|error| error.to_string())?,
        text: row.get("text").map_err(|error| error.to_string())?,
        payload: payload_value(
            &row.get::<_, String>("payload_json")
                .map_err(|error| error.to_string())?,
        ),
        source_start: row
            .get::<_, i64>("source_start")
            .map_err(|error| error.to_string())?
            .max(0) as usize,
        source_end: row
            .get::<_, i64>("source_end")
            .map_err(|error| error.to_string())?
            .max(0) as usize,
    })
}

fn fetch_edges(connection: &Connection) -> Result<Vec<Edge>, String> {
    let mut statement = connection
        .prepare("SELECT * FROM edges ORDER BY id")
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map([], |row| {
            Ok(Edge {
                edge_id: row.get("id")?,
                layer: row.get("layer")?,
                kind: row.get("kind")?,
                from_node_id: row.get("from_node_id")?,
                to_node_id: row.get("to_node_id")?,
                order_kind: row.get("order_kind")?,
                confidence: row.get("confidence")?,
                payload: payload_value(&row.get::<_, String>("payload_json")?),
            })
        })
        .map_err(|error| error.to_string())?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|error| error.to_string())
}

fn fetch_diagnostics(connection: &Connection) -> Result<Vec<Diagnostic>, String> {
    let mut statement = connection
        .prepare("SELECT * FROM diagnostics ORDER BY severity,id")
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map([], |row| {
            Ok(Diagnostic {
                diagnostic_id: row.get("id")?,
                layer: row.get("layer")?,
                severity: row.get("severity")?,
                rule: row.get("rule")?,
                message: row.get("message")?,
                target_node_id: row.get("target_node_id")?,
                target_edge_id: row.get("target_edge_id")?,
                action: payload_value(&row.get::<_, String>("suggested_action_json")?),
            })
        })
        .map_err(|error| error.to_string())?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|error| error.to_string())
}

fn fetch_operations(connection: &Connection) -> Result<Vec<EditOperation>, String> {
    let exists = connection
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='edit_operations'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .map_err(|error| error.to_string())?
        .is_some();
    if !exists {
        return Ok(Vec::new());
    }
    let mut statement = connection
        .prepare("SELECT * FROM edit_operations ORDER BY id")
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map([], |row| {
            let ids = payload_value(&row.get::<_, String>("target_ids_json")?);
            Ok(EditOperation {
                operation_id: row.get("id")?,
                kind: row.get("kind")?,
                target_ids: ids
                    .as_array()
                    .map(|values| {
                        values
                            .iter()
                            .filter_map(Value::as_str)
                            .map(str::to_owned)
                            .collect()
                    })
                    .unwrap_or_default(),
                reason: row.get("reason")?,
                payload: payload_value(&row.get::<_, String>("payload_json")?),
            })
        })
        .map_err(|error| error.to_string())?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|error| error.to_string())
}

fn fetch_document_records(connection: &Connection) -> Result<Vec<Value>, String> {
    let mut statement = connection
        .prepare("SELECT * FROM documents ORDER BY id")
        .map_err(|error| error.to_string())?;
    let rows=statement.query_map([],|row|Ok(json!({"document_id":row.get::<_,String>("id")?,"path":row.get::<_,String>("path")?,"title":row.get::<_,String>("title")?,"kind":row.get::<_,String>("kind")?,"created_at":row.get::<_,String>("created_at")?}))).map_err(|error|error.to_string())?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|error| error.to_string())
}

fn layer_counts(connection: &Connection) -> Result<BTreeMap<String, usize>, String> {
    let mut counts = BTreeMap::new();
    for query in [
        "SELECT layer,COUNT(*) FROM nodes GROUP BY layer",
        "SELECT layer,COUNT(*) FROM edges GROUP BY layer",
    ] {
        let mut statement = connection
            .prepare(query)
            .map_err(|error| error.to_string())?;
        let rows = statement
            .query_map([], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
            })
            .map_err(|error| error.to_string())?;
        for row in rows {
            let (layer, count) = row.map_err(|error| error.to_string())?;
            *counts.entry(layer).or_insert(0) += count.max(0) as usize;
        }
    }
    let diagnostics = connection
        .query_row("SELECT COUNT(*) FROM diagnostics", [], |row| {
            row.get::<_, i64>(0)
        })
        .map_err(|error| error.to_string())?
        .max(0) as usize;
    *counts.entry("diagnostics".into()).or_insert(0) += diagnostics;
    if table_exists(connection, "edit_operations")? {
        let operations = connection
            .query_row("SELECT COUNT(*) FROM edit_operations", [], |row| {
                row.get::<_, i64>(0)
            })
            .map_err(|error| error.to_string())?
            .max(0) as usize;
        *counts.entry("edit-operation".into()).or_insert(0) += operations;
    }
    Ok(counts)
}

fn table_exists(connection: &Connection, name: &str) -> Result<bool, String> {
    connection
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?1",
            params![name],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .map(|value| value.is_some())
        .map_err(|error| error.to_string())
}

fn graph_source_path(root: &Path, input: &Path) -> Result<String, String> {
    let root = root.canonicalize().map_err(|error| error.to_string())?;
    let path = input.canonicalize().map_err(|error| error.to_string())?;
    Ok(path
        .strip_prefix(&root)
        .map(|relative| relative.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().replace('\\', "/")))
}

fn source_scalar_offset(
    text: &str,
    line: usize,
    column: usize,
    path: &str,
) -> Result<usize, String> {
    if line == 0 || column == 0 {
        return Err(format!(
            "canonical graph source span has invalid line or column: {path}"
        ));
    }
    let lines = text.split_inclusive('\n').collect::<Vec<_>>();
    if line > lines.len() {
        return Err(format!(
            "canonical graph source span line is out of range: {path}:{line}"
        ));
    }
    let line_text = lines[line - 1];
    let scalar_line = line_text.trim_end_matches(['\r', '\n']);
    let scalar_len = scalar_line.chars().count();
    if column > scalar_len + 1 {
        return Err(format!(
            "canonical graph source span column is out of range: {path}:{line}:{column}"
        ));
    }
    let prefix = lines
        .iter()
        .take(line - 1)
        .map(|value| value.chars().count())
        .sum::<usize>();
    Ok(prefix + column - 1)
}

fn graph_source_offsets(
    text: &str,
    span: Option<&Value>,
    path: &str,
) -> Result<(usize, usize), String> {
    let span = span
        .and_then(Value::as_object)
        .ok_or_else(|| format!("canonical graph source span is missing: {path}"))?;
    let span_path = span.get("path").and_then(Value::as_str).unwrap_or_default();
    if span_path != path {
        return Err(format!(
            "canonical graph source span path mismatch: {span_path:?} != {path:?}"
        ));
    }
    let read = |key: &str| {
        span.get(key)
            .and_then(Value::as_u64)
            .filter(|value| *value > 0)
            .map(|value| value as usize)
            .ok_or_else(|| format!("canonical graph source span {key} is invalid: {path}"))
    };
    let start = source_scalar_offset(text, read("start_line")?, read("start_column")?, path)?;
    let end = source_scalar_offset(text, read("end_line")?, read("end_column")?, path)?;
    if end < start {
        return Err(format!("canonical graph source span is reversed: {path}"));
    }
    Ok((start, end))
}

fn graph_dependency_records_for_inputs(
    root: &Path,
    documents: &[(PathBuf, String)],
) -> Result<(BTreeMap<String, Vec<DependencyRecord>>, String), String> {
    let client = crate::graph_client::GraphClient::new(root)
        .map_err(|error| format!("canonical graph dependency query failed: {error}"))?;
    let response = client
        .query(None, "dependency", "both", 0, true)
        .map_err(|error| format!("canonical graph dependency query failed: {error}"))?;
    if response.status != "fresh" || response.exit_code != 0 {
        return Err(format!(
            "canonical graph dependency query is unavailable: status={} reason={}",
            response.status,
            response
                .payload
                .get("reason")
                .and_then(Value::as_str)
                .unwrap_or("")
        ));
    }
    let fingerprint = response
        .payload
        .get("graph_fingerprint")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or("canonical graph query lacks graph_fingerprint")?
        .to_owned();
    let facts = response
        .dependency_facts()
        .map_err(|error| format!("canonical graph dependency query failed: {error}"))?;
    let mut by_source = BTreeMap::new();
    for (input, text) in documents {
        let source_path = graph_source_path(root, input)?;
        let mut records = Vec::new();
        if let Some(nodes) = response.payload.get("nodes").and_then(Value::as_array) {
            if let Some(source) = nodes
                .iter()
                .find(|node| node.get("path").and_then(Value::as_str) == Some(source_path.as_str()))
            {
                let responsibility = source
                    .get("payload")
                    .and_then(|payload| payload.get("manifest_responsibility"))
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                if !responsibility.is_empty() {
                    let start_end =
                        graph_source_offsets(text, source.get("source_span"), &source_path)?;
                    records.push(DependencyRecord {
                        role: "responsibility".into(),
                        body: responsibility.into(),
                        text: format!("responsibility {responsibility}"),
                        source_start: start_end.0,
                        source_end: start_end.1,
                    });
                }
            }
        }
        for fact in &facts {
            if fact.source != source_path {
                continue;
            }
            let body = format!("{} {}", fact.target, fact.reason).trim().to_owned();
            let role = format!("{} {}", fact.direction, fact.kind);
            let span = fact
                .source_span
                .as_ref()
                .map(|value| Value::Object(value.clone()));
            let (start, end) = graph_source_offsets(text, span.as_ref(), &source_path)?;
            records.push(DependencyRecord {
                role: role.clone(),
                body: body.clone(),
                text: format!("{role} {body}"),
                source_start: start,
                source_end: end,
            });
        }
        records.sort_by(|left, right| {
            (left.source_start, &left.role, &left.text).cmp(&(
                right.source_start,
                &right.role,
                &right.text,
            ))
        });
        by_source.insert(source_path, records);
    }
    Ok((by_source, fingerprint))
}

#[derive(Clone, Debug)]
struct MarkdownBlock {
    text: String,
    start: usize,
    end: usize,
}

fn markdown_blocks(text: &str) -> Vec<MarkdownBlock> {
    let mut blocks = Vec::new();
    let mut current = String::new();
    let mut current_start = 0usize;
    let mut offset = 0usize;
    for line in text.split_inclusive('\n') {
        let stripped = line.trim();
        let length = line.chars().count();
        if stripped.is_empty() {
            if !current.is_empty() {
                blocks.push(MarkdownBlock {
                    text: current.trim().to_owned(),
                    start: current_start,
                    end: offset,
                });
                current.clear();
            }
            offset += length;
            continue;
        }
        if stripped.starts_with('#') {
            if !current.is_empty() {
                blocks.push(MarkdownBlock {
                    text: current.trim().to_owned(),
                    start: current_start,
                    end: offset,
                });
                current.clear();
            }
            blocks.push(MarkdownBlock {
                text: stripped.to_owned(),
                start: offset,
                end: offset + length,
            });
        } else {
            if current.is_empty() {
                current_start = offset;
            }
            current.push_str(line);
        }
        offset += length;
    }
    if !current.is_empty() {
        blocks.push(MarkdownBlock {
            text: current.trim().to_owned(),
            start: current_start,
            end: offset,
        });
    }
    blocks
}

fn split_sentences(text: &str) -> Vec<String> {
    let chars = text.chars().collect::<Vec<_>>();
    let stripped = text.trim().to_owned();
    if stripped.is_empty() {
        return Vec::new();
    }
    let mut sentences = Vec::new();
    let mut start = 0usize;
    let mut index = 0usize;
    while index < chars.len() {
        let ch = chars[index];
        let end = if "。！？".contains(ch) {
            Some(index + 1)
        } else if ".!?".contains(ch) && is_ascii_sentence_boundary(&chars, index) {
            Some(include_closing_punctuation(&chars, index + 1))
        } else {
            None
        };
        if let Some(end) = end {
            let candidate = chars[start..end].iter().collect::<String>();
            let candidate = candidate.trim();
            if !candidate.is_empty() {
                sentences.push(candidate.to_owned());
            }
            start = skip_sentence_gap(&chars, end);
            index = start;
        } else {
            index += 1;
        }
    }
    let remainder = chars[start..].iter().collect::<String>();
    if !remainder.trim().is_empty() {
        sentences.push(remainder.trim().to_owned());
    }
    if sentences.is_empty() {
        vec![stripped]
    } else {
        sentences
    }
}

fn include_closing_punctuation(chars: &[char], mut index: usize) -> usize {
    while index < chars.len() && "\"')]}”’".contains(chars[index]) {
        index += 1;
    }
    index
}
fn skip_sentence_gap(chars: &[char], mut index: usize) -> usize {
    while index < chars.len() && chars[index].is_whitespace() {
        index += 1;
    }
    index
}

fn is_ascii_sentence_boundary(chars: &[char], index: usize) -> bool {
    let ch = chars[index];
    let next = include_closing_punctuation(chars, index + 1);
    if next < chars.len() && !chars[next].is_whitespace() {
        return false;
    }
    if ch != '.' {
        return true;
    }
    if index > 0
        && index + 1 < chars.len()
        && chars[index - 1].is_ascii_digit()
        && chars[index + 1].is_ascii_digit()
    {
        return false;
    }
    !is_ascii_abbreviation_period(chars, index)
}

fn is_ascii_abbreviation_period(chars: &[char], index: usize) -> bool {
    let before = chars[..index].iter().collect::<String>();
    let token = before
        .split_whitespace()
        .last()
        .unwrap_or("")
        .trim_matches(['"', '\'', '(', '[', '{', '<']);
    let normalized = token.to_lowercase();
    if [
        "dr", "e.g", "fig", "figs", "i.e", "mr", "mrs", "ms", "no", "prof", "sec", "vs",
    ]
    .contains(&normalized.as_str())
    {
        return true;
    }
    let letters = token.chars().collect::<Vec<_>>();
    if letters.len() == 1 && letters[0].is_ascii_uppercase() {
        return true;
    }
    let mut chars = letters.iter().rev();
    let mut saw_digit = false;
    let mut saw_dot = false;
    for ch in chars.by_ref() {
        if ch.is_ascii_digit() {
            saw_digit = true;
            continue;
        }
        if *ch == '.' && saw_digit && !saw_dot {
            saw_dot = true;
            continue;
        }
        if ch.is_ascii_alphabetic() && saw_digit {
            return true;
        }
        break;
    }
    false
}

fn first_words(text: &str, count: usize) -> String {
    text.replace('\n', " ")
        .split_whitespace()
        .take(count)
        .collect::<Vec<_>>()
        .join(" ")
}

fn infer_title(text: &str, path: &Path) -> String {
    text.lines()
        .find_map(|line| {
            line.strip_prefix("# ")
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(str::to_owned)
        })
        .unwrap_or_else(|| {
            path.file_stem()
                .and_then(|value| value.to_str())
                .unwrap_or("document")
                .replace(['_', '-'], " ")
                .trim()
                .to_owned()
        })
}

fn anchor_payload(span_kind: &str, source_locator: &str, basis: &str, extra: Value) -> Value {
    let mut payload =
        json!({"span_kind":span_kind,"source_locator":source_locator,"segmentation_basis":basis});
    if let (Some(target), Some(source)) = (payload.as_object_mut(), extra.as_object()) {
        for (key, value) in source {
            target.insert(key.clone(), value.clone());
        }
    }
    payload
}

#[allow(clippy::too_many_arguments)]
fn insert_form_node(
    connection: &Connection,
    id: &str,
    document_id: &str,
    kind: &str,
    label: &str,
    text: &str,
    start: usize,
    end: usize,
    payload: Value,
) -> Result<(), String> {
    insert_node(
        connection,
        &Node {
            node_id: id.into(),
            document_id: document_id.into(),
            layer: "form".into(),
            kind: kind.into(),
            label: label.into(),
            text: text.into(),
            payload,
            source_start: start,
            source_end: end,
        },
        1.0,
    )
}

#[allow(clippy::too_many_arguments)]
fn insert_form_edge(
    connection: &Connection,
    id: &str,
    layer: &str,
    kind: &str,
    from: &str,
    to: &str,
    order_kind: &str,
    confidence: f64,
    payload: Value,
) -> Result<(), String> {
    insert_edge(
        connection,
        &Edge {
            edge_id: id.into(),
            layer: layer.into(),
            kind: kind.into(),
            from_node_id: from.into(),
            to_node_id: to.into(),
            order_kind: order_kind.into(),
            confidence,
            payload,
        },
    )
}

#[allow(clippy::too_many_arguments)]
fn ingest_document(
    connection: &Connection,
    path: &Path,
    text: &str,
    document_id: &str,
    source_node_id: &str,
    kind: &str,
    node_prefix: &str,
    dependencies: &[DependencyRecord],
) -> Result<(), String> {
    connection
        .execute(
            "INSERT INTO documents(id,path,title,kind,created_at) VALUES (?1,?2,?3,?4,?5)",
            params![
                document_id,
                path.to_string_lossy(),
                infer_title(text, path),
                kind,
                utc_now()
            ],
        )
        .map_err(|error| error.to_string())?;
    let dep_values=dependencies.iter().map(|record|json!({"role":record.role,"body":record.body,"text":record.text,"source_start":record.source_start,"source_end":record.source_end})).collect::<Vec<_>>();
    insert_node(
        connection,
        &Node {
            node_id: source_node_id.into(),
            document_id: document_id.into(),
            layer: "source".into(),
            kind: "document".into(),
            label: infer_title(text, path),
            text: text.into(),
            payload: json!({"path":path,"kind":kind,"graph_dependency_records":dep_values}),
            source_start: 0,
            source_end: text.chars().count(),
        },
        1.0,
    )?;
    let blocks = markdown_blocks(text);
    let mut sections = Vec::<String>::new();
    let mut paragraph_index = 0usize;
    let mut sentence_index = 0usize;
    let mut previous_block = String::new();
    for (index, block) in blocks.iter().enumerate() {
        if block.text.starts_with('#') {
            let level = block.text.chars().take_while(|value| *value == '#').count();
            let label = block
                .text
                .chars()
                .skip(level)
                .collect::<String>()
                .trim()
                .to_owned();
            let id = format!("{node_prefix}sec:{}", index + 1);
            sections.truncate(level.saturating_sub(1));
            sections.push(id.clone());
            insert_form_node(
                connection,
                &id,
                document_id,
                "section",
                &label,
                &block.text,
                block.start,
                block.end,
                anchor_payload(
                    "section",
                    &path.to_string_lossy(),
                    "markdown_heading",
                    json!({"level":level,"section_path":sections}),
                ),
            )?;
        } else {
            paragraph_index += 1;
            let paragraph_id = format!("{node_prefix}p:{paragraph_index}");
            insert_form_node(
                connection,
                &paragraph_id,
                document_id,
                "paragraph",
                &first_words(&block.text, FORM_NODE_LABEL_WORD_LIMIT),
                &block.text,
                block.start,
                block.end,
                anchor_payload(
                    "paragraph",
                    &path.to_string_lossy(),
                    "markdown_block",
                    json!({"section_path":sections,"ordinal":paragraph_index}),
                ),
            )?;
            if !previous_block.is_empty() {
                insert_form_edge(
                    connection,
                    &format!("{node_prefix}order:{previous_block}->{paragraph_id}"),
                    "presentation",
                    "precedes",
                    &previous_block,
                    &paragraph_id,
                    "hard_before",
                    1.0,
                    json!({"source":"ingest_order","participates_in_ordering_dag":true,"ordering_subgraph":"presentation"}),
                )?;
            }
            previous_block = paragraph_id.clone();
            for sentence in split_sentences(&block.text) {
                sentence_index += 1;
                let sentence_start = find_char_offset(text, &sentence, block.start, block.end)
                    .unwrap_or(block.start);
                let sentence_end = sentence_start + sentence.chars().count();
                let sentence_id = format!("{node_prefix}s:{sentence_index}");
                insert_form_node(
                    connection,
                    &sentence_id,
                    document_id,
                    "sentence",
                    &first_words(&sentence, FORM_NODE_LABEL_WORD_LIMIT),
                    &sentence,
                    sentence_start,
                    sentence_end,
                    anchor_payload(
                        "sentence",
                        &path.to_string_lossy(),
                        "sentence_split",
                        json!({"paragraph_id":paragraph_id,"ordinal":sentence_index}),
                    ),
                )?;
                insert_form_edge(
                    connection,
                    &format!("{node_prefix}contains:{paragraph_id}->{sentence_id}"),
                    "form",
                    "contains",
                    &paragraph_id,
                    &sentence_id,
                    "",
                    1.0,
                    json!({"source":"sentence_split","participates_in_projection_order":true,"ordering_subgraph":"form_containment"}),
                )?;
            }
        }
    }
    Ok(())
}

fn find_char_offset(text: &str, needle: &str, start: usize, end: usize) -> Option<usize> {
    let mut byte_start = None;
    let mut byte_end = None;
    for (char_offset, (byte_index, _ch)) in text.char_indices().enumerate() {
        if char_offset == start {
            byte_start = Some(byte_index);
        }
        if char_offset == end {
            byte_end = Some(byte_index);
            break;
        }
    }
    let begin = byte_start.unwrap_or_else(|| {
        if start == text.chars().count() {
            text.len()
        } else {
            0
        }
    });
    let finish = byte_end.unwrap_or(text.len());
    let relative = text.get(begin..finish)?.find(needle)?;
    Some(start + text.get(begin..begin + relative)?.chars().count())
}

fn prompt_context(options: &Options) -> Result<String, String> {
    let mut parts = Vec::new();
    if !options.prompt.is_empty() {
        parts.push(options.prompt.clone());
    }
    if let Some(path) = options.prompt_file.as_ref() {
        if !path.is_file() {
            return Err(format!("prompt file does not exist: {}", path.display()));
        }
        parts.push(fs::read_to_string(path).map_err(|error| error.to_string())?);
    }
    Ok(parts.join("\n"))
}

fn expand_ingest_inputs(inputs: &[PathBuf], recursive: bool) -> Result<Vec<PathBuf>, String> {
    let mut output = Vec::new();
    for input in inputs {
        if input.is_dir() {
            let mut stack = vec![input.clone()];
            let mut matches = Vec::new();
            while let Some(directory) = stack.pop() {
                let mut entries = fs::read_dir(&directory)
                    .map_err(|error| error.to_string())?
                    .map(|entry| {
                        entry
                            .map(|entry| entry.path())
                            .map_err(|error| error.to_string())
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                entries.sort();
                for path in entries {
                    if path.is_dir() {
                        if recursive {
                            stack.push(path);
                        }
                    } else if path.is_file()
                        && path
                            .extension()
                            .and_then(|value| value.to_str())
                            .is_some_and(|value| matches!(value, "md" | "markdown" | "txt"))
                    {
                        matches.push(path);
                    }
                }
            }
            matches.sort();
            output.extend(matches);
        } else if input.is_file() {
            output.push(input.clone());
        } else {
            return Err(format!("ingest input does not exist: {}", input.display()));
        }
    }
    if output.is_empty() {
        return Err("ingest-set found no input files".into());
    }
    Ok(output)
}

fn experiment_plan_assignment_kinds(texts: &[String]) -> BTreeSet<String> {
    let mut kinds = BTreeSet::new();
    for text in texts {
        let lower = text.to_lowercase();
        if HYPOTHESIS_ASSIGNMENT.is_match(&lower) || HYPOTHESIS_JA_ASSIGNMENT.is_match(text) {
            kinds.insert("hypothesis".into());
        }
        if METRIC_ASSIGNMENT.is_match(&lower) || METRIC_JA_ASSIGNMENT.is_match(text) {
            kinds.insert("metric".into());
        }
        if BASELINE_ASSIGNMENT.is_match(&lower) || BASELINE_JA_ASSIGNMENT.is_match(text) {
            kinds.insert("baseline".into());
        }
        if EXPECTED_ASSIGNMENT.is_match(&lower) || EXPECTED_JA_ASSIGNMENT.is_match(text) {
            kinds.insert("expected_result".into());
        }
    }
    kinds
}

fn experiment_plan_analysis_status(texts: &[String]) -> &'static str {
    if !experiment_plan_assignment_kinds(texts).is_empty() {
        "present"
    } else if texts
        .iter()
        .any(|text| has_any(text, EXPERIMENT_VOCABULARY_CUES))
    {
        "vocabulary_only"
    } else {
        "absent"
    }
}

fn semantic_prose_ir_payload(
    inputs: &[(PathBuf, String)],
    prompt: &str,
    db_path: &Path,
) -> Result<Value, String> {
    let texts = inputs
        .iter()
        .map(|(_, text)| text.clone())
        .collect::<Vec<_>>();
    let lexical = crate::structured_analysis::analyze_prose_lexicon(&texts, prompt);
    let terms = lexical
        .get("top_terms")
        .cloned()
        .unwrap_or_else(|| json!([]));
    let corpus_hints = lexical
        .get("corpus_hints")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let ir_path = db_path
        .parent()
        .unwrap_or(Path::new("."))
        .join("semantic_prose_ir.json");
    let mut all_hints = vec![
        json!({"corpus_id":"deterministic_prose","label":"Deterministic prose and document-structure corpus","score":terms.as_array().map(Vec::len).unwrap_or(0),"selected":true,"basis":{"source":"deterministic_capability_evidence","terms":terms.clone()}}),
    ];
    all_hints.extend(corpus_hints);
    let payload = json!({
        "schema":"semantic-prose-ir/v1",
        "artifact_path":ir_path,
        "source":"deterministic_capability_evidence",
        "documents":inputs.iter().map(|(path,_)|path.canonicalize().unwrap_or_else(|_|path.clone())).collect::<Vec<_>>(),
        "prompt_present":!prompt.trim().is_empty(),
        "terms":terms,
        "segmentation":lexical["segmentation"],
        "analysis_intents":[{"intent":"experiment_plan","status":experiment_plan_analysis_status(&texts)}],
        "corpus_hints":all_hints
    });
    let text = serde_json::to_string_pretty(&payload).map_err(|error| error.to_string())? + "\n";
    write_output(&ir_path, &text)?;
    Ok(payload)
}

fn corpus_hints_from_semantic_ir(payload: &Value) -> Vec<Value> {
    payload.get("corpus_hints").and_then(Value::as_array).filter(|values|!values.is_empty()).cloned().unwrap_or_else(||vec![json!({"corpus_id":"general_prose","label":"General prose and document-structure corpus","score":0,"selected":true,"basis":{"source":"deterministic_capability_evidence","signals":[]}})])
}

fn emit_stats(options: &Options, status_key: &str, fields: Value) -> Result<(), String> {
    if let Some(path) = options.stats_out.as_deref() {
        let path = runtime_resolve(path, "prose-reasoning-graph-stats")?;
        let payload = json!({"schema":"prose_reasoning_graph.stats.v1","status":"pass","command":options.command,"fields":fields});
        let text =
            serde_json::to_string_pretty(&payload).map_err(|error| error.to_string())? + "\n";
        write_output(&path, &text)?;
        println!(
            "{status_key}=pass\nPROSE_REASONING_GRAPH_STATS={}",
            path.display()
        );
    } else {
        println!("{status_key}=pass");
        if let Some(fields) = fields.as_object() {
            for (key, value) in fields {
                println!("{key}={}", scalar(value));
            }
        }
    }
    Ok(())
}

fn command_ingest(options: &Options) -> Result<i32, String> {
    let input = &options.inputs[0];
    let db = graph_db_path(options)?;
    let text = fs::read_to_string(input).map_err(|error| error.to_string())?;
    let prompt = prompt_context(options)?;
    let root = structured_repo_root(options, input)?;
    let docs = vec![(input.clone(), text.clone())];
    let (dependencies, fingerprint) = graph_dependency_records_for_inputs(&root, &docs)?;
    let semantic = semantic_prose_ir_payload(&docs, &prompt, &db)?;
    let hints = corpus_hints_from_semantic_ir(&semantic);
    let connection = connect(&db)?;
    initialize_schema(&connection)?;
    clear_database(&connection)?;
    set_metadata(&connection, "semantic_prose_ir", &semantic)?;
    set_metadata(&connection, "corpus_hints", &json!(hints))?;
    set_metadata(
        &connection,
        "canonical_graph_fingerprint",
        &json!(fingerprint),
    )?;
    set_metadata(
        &connection,
        "corpus_hint_inputs",
        &json!({"source":"semantic_prose_ir","document_path":input,"prompt_supplied":!prompt.trim().is_empty(),"ir_schema":semantic["schema"]}),
    )?;
    let key = graph_source_path(&root, input)?;
    ingest_document(
        &connection,
        input,
        &text,
        "doc:1",
        "src:1",
        &options.kind,
        "",
        dependencies.get(&key).map(Vec::as_slice).unwrap_or(&[]),
    )?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_INGEST",
        json!({"PROSE_REASONING_GRAPH_DB":db,"PROSE_REASONING_GRAPH_SEMANTIC_IR":semantic["artifact_path"]}),
    )?;
    Ok(0)
}

fn command_ingest_set(options: &Options) -> Result<i32, String> {
    let db = graph_db_path(options)?;
    let paths = expand_ingest_inputs(&options.inputs, options.recursive)?;
    let prompt = prompt_context(options)?;
    let docs = paths
        .iter()
        .map(|path| {
            Ok((
                path.clone(),
                fs::read_to_string(path).map_err(|error| error.to_string())?,
            ))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let root = structured_repo_root(options, &paths[0])?;
    let (dependencies, fingerprint) = graph_dependency_records_for_inputs(&root, &docs)?;
    let semantic = semantic_prose_ir_payload(&docs, &prompt, &db)?;
    let hints = corpus_hints_from_semantic_ir(&semantic);
    let connection = connect(&db)?;
    initialize_schema(&connection)?;
    clear_database(&connection)?;
    set_metadata(&connection, "semantic_prose_ir", &semantic)?;
    set_metadata(&connection, "corpus_hints", &json!(hints))?;
    set_metadata(
        &connection,
        "canonical_graph_fingerprint",
        &json!(fingerprint),
    )?;
    set_metadata(
        &connection,
        "corpus_hint_inputs",
        &json!({"source":"semantic_prose_ir","document_paths":docs.iter().map(|(path,_)|path).collect::<Vec<_>>(),"prompt_supplied":!prompt.trim().is_empty(),"ir_schema":semantic["schema"]}),
    )?;
    connection.execute("INSERT INTO documents(id,path,title,kind,created_at) VALUES ('doc:analysis','analysis://collection','Document collection analysis','analysis',?1)",params![utc_now()]).map_err(|error|error.to_string())?;
    for (index, (path, text)) in docs.iter().enumerate() {
        let key = graph_source_path(&root, path)?;
        ingest_document(
            &connection,
            path,
            text,
            &format!("doc:{}", index + 1),
            &format!("src:{}", index + 1),
            &options.kind,
            &format!("d{}:", index + 1),
            dependencies.get(&key).map(Vec::as_slice).unwrap_or(&[]),
        )?;
    }
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_INGEST_SET",
        json!({"PROSE_REASONING_GRAPH_DB":db,"PROSE_REASONING_GRAPH_DOCUMENTS":docs.len(),"PROSE_REASONING_GRAPH_SEMANTIC_IR":semantic["artifact_path"]}),
    )?;
    Ok(0)
}

fn structured_repo_root(options: &Options, input: &Path) -> Result<PathBuf, String> {
    if let Some(root) = options.repo_root.as_ref() {
        return root.canonicalize().map_err(|error| error.to_string());
    }
    let resolved = input.canonicalize().map_err(|error| error.to_string())?;
    let parts = resolved.components().collect::<Vec<_>>();
    for index in 0..parts.len().saturating_sub(1) {
        if parts[index].as_os_str() == "vendor" && parts[index + 1].as_os_str() == "agent-canon" {
            return parts[..=index + 1]
                .iter()
                .fold(PathBuf::new(), |mut path, part| {
                    path.push(part.as_os_str());
                    path
                })
                .canonicalize()
                .map_err(|error| error.to_string());
        }
    }
    let output = Command::new("git")
        .args([
            "-C",
            resolved
                .parent()
                .unwrap_or(Path::new("."))
                .to_string_lossy()
                .as_ref(),
            "rev-parse",
            "--show-toplevel",
        ])
        .output()
        .map_err(|error| error.to_string())?;
    let git_root = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    if output.status.success() && !git_root.is_empty() {
        PathBuf::from(git_root)
            .canonicalize()
            .map_err(|error| error.to_string())
    } else {
        Ok(resolved.parent().unwrap_or(Path::new(".")).to_path_buf())
    }
}

fn clear_analysis(connection: &Connection) -> Result<(), String> {
    connection
        .execute_batch(
            "DELETE FROM judgements; DELETE FROM edit_operations; DELETE FROM diagnostics; \
             DELETE FROM edges WHERE layer NOT IN ('form', 'presentation'); \
             DELETE FROM nodes WHERE layer NOT IN ('source', 'form');",
        )
        .map_err(|error| error.to_string())
}

fn fetch_document_id(connection: &Connection) -> Result<String, String> {
    connection
        .query_row(
            "SELECT id FROM documents WHERE id='doc:analysis'",
            [],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|error| error.to_string())?
        .or_else(|| {
            connection
                .query_row("SELECT id FROM documents ORDER BY id LIMIT 1", [], |row| {
                    row.get::<_, String>(0)
                })
                .optional()
                .ok()
                .flatten()
        })
        .ok_or_else(|| "database has no document; run ingest first".into())
}

fn dependency_records_from_source_payload(
    payload: &Value,
    source_node_id: &str,
) -> Result<Vec<DependencyRecord>, String> {
    let records = payload
        .get("graph_dependency_records")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            format!("source node lacks canonical graph dependency records: {source_node_id}")
        })?;
    records
        .iter()
        .enumerate()
        .map(|(index, value)| {
            let invalid =
                || format!("source node dependency record is invalid: {source_node_id}:{index}");
            let source_start = value
                .get("source_start")
                .and_then(Value::as_u64)
                .ok_or_else(invalid)? as usize;
            let source_end = value
                .get("source_end")
                .and_then(Value::as_u64)
                .ok_or_else(invalid)? as usize;
            Ok(DependencyRecord {
                role: value
                    .get("role")
                    .and_then(Value::as_str)
                    .ok_or_else(invalid)?
                    .into(),
                body: value
                    .get("body")
                    .and_then(Value::as_str)
                    .ok_or_else(invalid)?
                    .into(),
                text: value
                    .get("text")
                    .and_then(Value::as_str)
                    .ok_or_else(invalid)?
                    .into(),
                source_start,
                source_end,
            })
        })
        .collect()
}

fn analysis_lexicon(connection: &Connection) -> Result<BTreeMap<String, Vec<String>>, String> {
    let nodes = fetch_nodes(connection, None, None)?;
    let mut texts = Vec::new();
    let mut seen = HashSet::new();
    let mut add = |text: String| {
        if seen.insert(text.clone()) {
            texts.push(text);
        }
    };
    add(String::new());
    for node in &nodes {
        add(node.text.clone());
        add(node
            .payload
            .get("section_path")
            .map_or_else(String::new, |value| {
                value
                    .as_array()
                    .map(|items| {
                        format!(
                            "[{}]",
                            items
                                .iter()
                                .map(|item| format!("'{}'", item.as_str().unwrap_or_default()))
                                .collect::<Vec<_>>()
                                .join(", ")
                        )
                    })
                    .unwrap_or_else(|| value.as_str().unwrap_or_default().to_owned())
            }));
        if node.layer == "source" && node.kind == "document" {
            for record in dependency_records_from_source_payload(&node.payload, &node.node_id)? {
                add(record.body);
                add(record.text);
            }
        }
    }
    let response = crate::structured_analysis::analyze_prose_lexicon(&texts, "");
    let terms = response
        .get("terms")
        .and_then(Value::as_array)
        .ok_or("native prose lexicon response lacks terms")?;
    if terms.len() != texts.len() {
        return Err("native prose lexicon response term count does not match inputs".into());
    }
    Ok(texts
        .into_iter()
        .zip(terms)
        .map(|(text, values)| {
            let values = values
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect();
            (text, values)
        })
        .collect())
}

fn has_any(text: &str, cues: &[&str]) -> bool {
    let lowered = text.to_lowercase();
    cues.iter().any(|cue| {
        if cue.is_ascii()
            && cue
                .chars()
                .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-'))
        {
            let cue = cue.to_lowercase();
            lowered.match_indices(&cue).any(|(start, matched)| {
                let end = start + matched.len();
                let boundary = |byte: Option<u8>| {
                    !byte.is_some_and(|value| {
                        value.is_ascii_alphanumeric() || matches!(value, b'_' | b'-')
                    })
                };
                boundary(
                    start
                        .checked_sub(1)
                        .and_then(|index| lowered.as_bytes().get(index).copied()),
                ) && boundary(lowered.as_bytes().get(end).copied())
            })
        } else {
            text.contains(cue)
        }
    })
}

fn derived_anchor_payload(anchor_id: &str, basis: &str) -> Value {
    json!({
        "sentence_id":anchor_id,
        "member_anchor_ids":[anchor_id],
        "source_anchor_id":anchor_id,
        "derivation_basis":basis,
    })
}

#[allow(clippy::too_many_arguments)]
fn add_analysis_node(
    connection: &Connection,
    id: &str,
    document_id: &str,
    layer: &str,
    kind: &str,
    label: &str,
    text: &str,
    start: usize,
    end: usize,
    confidence: f64,
    payload: Value,
) -> Result<(), String> {
    insert_node(
        connection,
        &Node {
            node_id: id.into(),
            document_id: document_id.into(),
            layer: layer.into(),
            kind: kind.into(),
            label: label.into(),
            text: text.into(),
            payload,
            source_start: start,
            source_end: end,
        },
        confidence,
    )
}

#[allow(clippy::too_many_arguments)]
fn add_analysis_edge(
    connection: &Connection,
    id: &str,
    layer: &str,
    kind: &str,
    source: &str,
    target: &str,
    order_kind: &str,
    confidence: f64,
    payload: Value,
) -> Result<(), String> {
    insert_edge(
        connection,
        &Edge {
            edge_id: id.into(),
            layer: layer.into(),
            kind: kind.into(),
            from_node_id: source.into(),
            to_node_id: target.into(),
            order_kind: order_kind.into(),
            confidence,
            payload,
        },
    )
}

fn analyze_graph(connection: &Connection, profile: &str) -> Result<(), String> {
    let document_id = fetch_document_id(connection)?;
    let paragraphs = fetch_nodes(connection, Some("form"), Some("paragraph"))?;
    let sentences = fetch_nodes(connection, Some("form"), Some("sentence"))?;
    let sections = fetch_nodes(connection, Some("form"), Some("section"))?;
    let lexicon = analysis_lexicon(connection)?;
    add_projection_layer(connection, &document_id, profile)?;
    add_concept_layer(connection, &document_id, &paragraphs, &lexicon)?;
    add_phase_layer(connection, &document_id, &paragraphs, profile)?;
    add_discourse_layer(connection, &paragraphs, &lexicon)?;
    let claims = add_argument_layer(connection, &document_id, &sentences)?;
    let evidence = add_evidence_layer(connection, &document_id, &sentences, &claims, &lexicon)?;
    add_experiment_layer(connection, &document_id, &sentences, profile)?;
    add_presentation_feature_layer(connection, &document_id, &paragraphs, &sentences)?;
    add_explanation_layer(connection, &document_id, profile)?;
    add_section_edges(connection, &sections, &paragraphs)?;
    add_diagnostics(
        connection,
        &paragraphs,
        &claims,
        &evidence,
        profile,
        &lexicon,
    )?;
    add_edit_operations(connection, &paragraphs, &lexicon)?;
    Ok(())
}

fn add_projection_layer(
    connection: &Connection,
    document_id: &str,
    profile: &str,
) -> Result<(), String> {
    add_analysis_node(
        connection,
        "projection:profile",
        document_id,
        "projection",
        "profile",
        profile,
        &format!("Projection profile: {profile}"),
        0,
        0,
        1.0,
        json!({"profile":profile,"canonical_graph":"text_anchored_semantic_graph","projection_view_export":"projection_views","outputs":["yaml","json","markdown"]}),
    )
}

fn add_concept_layer(
    connection: &Connection,
    document_id: &str,
    paragraphs: &[Node],
    lexicon: &BTreeMap<String, Vec<String>>,
) -> Result<(), String> {
    let mut counts = BTreeMap::<String, (usize, usize)>::new();
    let mut next_order = 0usize;
    for paragraph in paragraphs {
        for term in lexicon.get(&paragraph.text).into_iter().flatten() {
            let item = counts.entry(term.clone()).or_insert_with(|| {
                let order = next_order;
                next_order += 1;
                (0, order)
            });
            item.0 += 1;
        }
    }
    let mut candidates = counts
        .iter()
        .filter(|(_, (count, _))| *count > 1)
        .map(|(term, (count, order))| (term.clone(), *count, *order))
        .collect::<Vec<_>>();
    candidates.sort_by_key(|(_, count, order)| (Reverse(*count), *order));
    candidates.truncate(CONCEPT_CANDIDATE_LIMIT);
    let terms = candidates
        .iter()
        .map(|(term, _, _)| term.clone())
        .collect::<Vec<_>>();
    for (index, (term, frequency, _)) in candidates.iter().enumerate() {
        add_analysis_node(
            connection,
            &format!("concept:{}", index + 1),
            document_id,
            "concept",
            "term",
            term,
            term,
            0,
            0,
            CONCEPT_NODE_CONFIDENCE,
            json!({"frequency":frequency}),
        )?;
    }
    for (index, pair) in terms.windows(2).enumerate() {
        add_analysis_edge(
            connection,
            &format!("concept-edge:{}", index + 1),
            "concept",
            "related_to",
            &concept_id_for(&terms, &pair[0]),
            &concept_id_for(&terms, &pair[1]),
            "",
            CONCEPT_EDGE_CONFIDENCE,
            json!({"basis":"term_cooccurrence"}),
        )?;
    }
    for paragraph in paragraphs {
        let tokens = lexicon.get(&paragraph.text).cloned().unwrap_or_default();
        let mut term_frequency = BTreeMap::<String, usize>::new();
        for term in tokens {
            *term_frequency.entry(term).or_default() += 1;
        }
        let mentioned = terms
            .iter()
            .filter(|term| term_frequency.contains_key(*term))
            .cloned()
            .collect::<Vec<_>>();
        for term in &terms {
            let Some(frequency) = term_frequency.get(term) else {
                continue;
            };
            let concept_id = concept_id_for(&terms, term);
            add_analysis_edge(
                connection,
                &format!("concept-mention:{}->{concept_id}", paragraph.node_id),
                "concept",
                "mentions",
                &paragraph.node_id,
                &concept_id,
                "",
                CONCEPT_EDGE_CONFIDENCE,
                json!({"basis":"paragraph_term_membership","term_frequency":frequency,"participates_in_projection_features":true}),
            )?;
        }
        for left in 0..mentioned.len() {
            for right in left + 1..mentioned.len() {
                let left_id = concept_id_for(&terms, &mentioned[left]);
                let right_id = concept_id_for(&terms, &mentioned[right]);
                add_analysis_edge(
                    connection,
                    &format!(
                        "concept-cooccurs:{}:{left_id}->{right_id}",
                        paragraph.node_id
                    ),
                    "concept",
                    "cooccurs_in_anchor",
                    &left_id,
                    &right_id,
                    "",
                    CONCEPT_EDGE_CONFIDENCE,
                    json!({"basis":"paragraph_concept_subgraph","source_anchor_id":paragraph.node_id,"participates_in_projection_features":true}),
                )?;
            }
        }
    }
    Ok(())
}

fn concept_id_for(candidates: &[String], term: &str) -> String {
    format!(
        "concept:{}",
        candidates
            .iter()
            .position(|candidate| candidate == term)
            .unwrap_or(0)
            + 1
    )
}

fn add_phase_layer(
    connection: &Connection,
    document_id: &str,
    paragraphs: &[Node],
    profile: &str,
) -> Result<(), String> {
    for (index, paragraph) in paragraphs.iter().enumerate() {
        let phase = infer_phase(&paragraph.text, index + 1, profile);
        let phase_id = format!("phase:{}", index + 1);
        add_analysis_node(
            connection,
            &phase_id,
            document_id,
            "phase",
            "move",
            &phase,
            &paragraph.text,
            0,
            0,
            PHASE_INFERENCE_CONFIDENCE,
            json!({"paragraph_id":paragraph.node_id,"profile":profile}),
        )?;
        add_analysis_edge(
            connection,
            &format!("phase-map:{}->{phase_id}", paragraph.node_id),
            "phase",
            "realizes_move",
            &paragraph.node_id,
            &phase_id,
            "",
            1.0,
            json!({"profile":profile}),
        )?;
    }
    Ok(())
}

fn infer_phase(text: &str, index: usize, profile: &str) -> String {
    let lowered = text.to_lowercase();
    if matches!(profile, "experiment" | "all") && has_any(&lowered, &["hypothesis", "仮説"]) {
        return "hypothesis".into();
    }
    if has_any(
        &lowered,
        &["metric", "baseline", "protocol", "指標", "ベースライン"],
    ) {
        return "operationalization".into();
    }
    if has_any(&lowered, &["risk", "limitation", "ただし", "制限", "限界"]) {
        return "limitation".into();
    }
    if has_any(&lowered, &["therefore", "recommend", "結論", "推奨"]) {
        return "recommendation".into();
    }
    if index == 1 {
        "context".into()
    } else {
        "development".into()
    }
}

fn lexical_overlap(left: &str, right: &str, lexicon: &BTreeMap<String, Vec<String>>) -> f64 {
    let left = lexicon
        .get(left)
        .into_iter()
        .flatten()
        .cloned()
        .collect::<BTreeSet<_>>();
    let right = lexicon
        .get(right)
        .into_iter()
        .flatten()
        .cloned()
        .collect::<BTreeSet<_>>();
    if left.is_empty() || right.is_empty() {
        return 0.0;
    }
    let intersection = left.intersection(&right).count();
    let union = left.union(&right).count().max(1);
    intersection as f64 / union as f64
}

fn infer_discourse_relation(text: &str) -> String {
    let lowered = text.to_lowercase();
    if has_any(&lowered, &["however", "but", "although", "ただし", "一方"]) {
        "contrasts".into()
    } else if has_any(
        &lowered,
        &[
            "because",
            "therefore",
            "thus",
            "so ",
            "なので",
            "したがって",
            "このため",
            "根拠",
        ],
    ) {
        "causes".into()
    } else if has_any(&lowered, &["for example", "e.g.", "例えば", "具体例"]) {
        "exemplifies".into()
    } else if has_any(&lowered, &["limitation", "risk", "制限", "リスク"]) {
        "limits".into()
    } else {
        "elaborates".into()
    }
}

fn first_discourse_signal(text: &str) -> String {
    let lowered = text.to_lowercase();
    [
        "however",
        "because",
        "therefore",
        "for example",
        "limitation",
        "ただし",
        "一方",
        "例えば",
        "具体例",
        "このため",
        "この図",
        "また",
        "次は",
        "根拠",
        "制限",
    ]
    .into_iter()
    .find(|cue| lowered.contains(&cue.to_lowercase()))
    .unwrap_or("")
    .into()
}

fn add_discourse_layer(
    connection: &Connection,
    paragraphs: &[Node],
    lexicon: &BTreeMap<String, Vec<String>>,
) -> Result<(), String> {
    for (index, pair) in paragraphs.windows(2).enumerate() {
        let left = &pair[0];
        let right = &pair[1];
        let overlap = lexical_overlap(&left.text, &right.text, lexicon);
        let mut shared = lexicon
            .get(&left.text)
            .into_iter()
            .flatten()
            .filter(|term| {
                lexicon
                    .get(&right.text)
                    .is_some_and(|other| other.contains(term))
            })
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        shared.truncate(DISCOURSE_SHARED_TERM_LIMIT);
        let confidence = (overlap + DISCOURSE_CONFIDENCE_OVERLAP_OFFSET)
            .clamp(DISCOURSE_CONFIDENCE_FLOOR, DISCOURSE_CONFIDENCE_CEILING);
        add_analysis_edge(
            connection,
            &format!("discourse:{}", index + 1),
            "discourse",
            &infer_discourse_relation(&right.text),
            &left.node_id,
            &right.node_id,
            "adjacency_preferred",
            confidence,
            json!({"shared_terms":shared,"lexical_overlap":overlap,"surface_signal":first_discourse_signal(&right.text),"participates_in_ordering_dag":true,"ordering_subgraph":"discourse_adjacency"}),
        )?;
    }
    Ok(())
}

fn add_argument_layer(
    connection: &Connection,
    document_id: &str,
    sentences: &[Node],
) -> Result<Vec<Node>, String> {
    let mut claims = Vec::new();
    for sentence in sentences {
        if !has_any(&sentence.text, CLAIM_CUES) {
            continue;
        }
        let id = format!("claim:{}", claims.len() + 1);
        let label = first_words(&sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT);
        let payload = derived_anchor_payload(&sentence.node_id, "cue_heuristic");
        add_analysis_node(
            connection,
            &id,
            document_id,
            "argument",
            "claim",
            &label,
            &sentence.text,
            sentence.source_start,
            sentence.source_end,
            EXTRACTED_NODE_CONFIDENCE,
            payload.clone(),
        )?;
        add_analysis_edge(
            connection,
            &format!("claim-source:{id}"),
            "argument",
            "stated_in",
            &id,
            &sentence.node_id,
            "",
            1.0,
            json!({"source":"cue_heuristic"}),
        )?;
        claims.push(Node {
            node_id: id,
            document_id: document_id.into(),
            layer: "argument".into(),
            kind: "claim".into(),
            label,
            text: sentence.text.clone(),
            payload,
            source_start: sentence.source_start,
            source_end: sentence.source_end,
        });
    }
    Ok(claims)
}

fn add_graph_dependency_evidence_nodes(
    connection: &Connection,
    document_id: &str,
    lexicon: &BTreeMap<String, Vec<String>>,
) -> Result<Vec<Node>, String> {
    let source = fetch_nodes(connection, Some("source"), Some("document"))?
        .into_iter()
        .find(|node| node.document_id == document_id);
    let Some(source) = source else {
        return Ok(Vec::new());
    };
    let records = dependency_records_from_source_payload(&source.payload, &source.node_id)?;
    let mut evidence_nodes = Vec::new();
    for (index, record) in records.iter().enumerate() {
        let id = format!("evidence:dependency:{}", index + 1);
        let kind = if record.role == "responsibility" {
            "document_responsibility"
        } else {
            "graph_dependency"
        };
        let label = first_words(&record.text, EXTRACTED_NODE_LABEL_WORD_LIMIT);
        let mut responsibility_terms = lexicon.get(&record.body).cloned().unwrap_or_default();
        responsibility_terms.sort();
        responsibility_terms.dedup();
        let base_payload = json!({
            "source":"canonical_graph",
            "manifest_role":record.role,
            "responsibility_terms":responsibility_terms,
            "strength":"responsibility_contract",
        });
        let mut stored_payload = base_payload.clone();
        stored_payload["source_anchor_id"] = json!(source.node_id);
        stored_payload["member_anchor_ids"] = json!([source.node_id]);
        stored_payload["derivation_basis"] = json!("dependency_manifest");
        add_analysis_node(
            connection,
            &id,
            document_id,
            "evidence",
            kind,
            &label,
            &record.text,
            source.source_start + record.source_start,
            source.source_start + record.source_end,
            EXTRACTED_NODE_CONFIDENCE,
            stored_payload,
        )?;
        let mut node_payload = base_payload;
        node_payload["source_anchor_id"] = json!(source.node_id);
        node_payload["member_anchor_ids"] = json!([source.node_id]);
        node_payload["derivation_basis"] = json!("canonical_graph");
        evidence_nodes.push(Node {
            node_id: id,
            document_id: document_id.into(),
            layer: "evidence".into(),
            kind: kind.into(),
            label,
            text: record.text.clone(),
            payload: node_payload,
            source_start: source.source_start + record.source_start,
            source_end: source.source_start + record.source_end,
        });
    }
    Ok(evidence_nodes)
}

fn graph_dependency_covers_claim(
    claim: &Node,
    evidence: &Node,
    lexicon: &BTreeMap<String, Vec<String>>,
) -> bool {
    let claim_terms = lexicon
        .get(&claim.text)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .collect::<BTreeSet<_>>();
    let evidence_terms = lexicon
        .get(&evidence.text)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .collect::<BTreeSet<_>>();
    if claim_terms.is_empty() || evidence_terms.is_empty() {
        return false;
    }
    !claim_terms.is_disjoint(&evidence_terms)
}

fn best_supporting_evidence<'a>(
    claim: &Node,
    evidence_nodes: &'a [Node],
    lexicon: &BTreeMap<String, Vec<String>>,
) -> Option<&'a Node> {
    let claim_sentence = claim
        .payload
        .get("sentence_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if let Some(evidence) = evidence_nodes.iter().find(|item| {
        item.payload.get("sentence_id").and_then(Value::as_str) == Some(claim_sentence)
    }) {
        return Some(evidence);
    }
    evidence_nodes.iter().find(|evidence| {
        if matches!(
            evidence.kind.as_str(),
            "document_responsibility" | "graph_dependency"
        ) {
            return graph_dependency_covers_claim(claim, evidence, lexicon);
        }
        lexical_overlap(&claim.text, &evidence.text, lexicon) >= EVIDENCE_SUPPORT_MIN_OVERLAP
    })
}

fn add_evidence_layer(
    connection: &Connection,
    document_id: &str,
    sentences: &[Node],
    claims: &[Node],
    lexicon: &BTreeMap<String, Vec<String>>,
) -> Result<Vec<Node>, String> {
    let mut evidence_nodes = Vec::new();
    for sentence in sentences {
        if !has_any(&sentence.text, EVIDENCE_CUES) {
            continue;
        }
        let id = format!("evidence:{}", evidence_nodes.len() + 1);
        let label = first_words(&sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT);
        let mut payload = derived_anchor_payload(&sentence.node_id, "evidence_cue");
        payload["strength"] = json!("candidate");
        add_analysis_node(
            connection,
            &id,
            document_id,
            "evidence",
            "evidence",
            &label,
            &sentence.text,
            sentence.source_start,
            sentence.source_end,
            EXTRACTED_NODE_CONFIDENCE,
            payload.clone(),
        )?;
        evidence_nodes.push(Node {
            node_id: id,
            document_id: document_id.into(),
            layer: "evidence".into(),
            kind: "evidence".into(),
            label,
            text: sentence.text.clone(),
            payload,
            source_start: sentence.source_start,
            source_end: sentence.source_end,
        });
    }
    evidence_nodes.extend(add_graph_dependency_evidence_nodes(
        connection,
        document_id,
        lexicon,
    )?);
    for claim in claims {
        let Some(evidence) = best_supporting_evidence(claim, &evidence_nodes, lexicon) else {
            continue;
        };
        let graph_basis = matches!(
            evidence.kind.as_str(),
            "document_responsibility" | "graph_dependency"
        );
        let basis = if graph_basis {
            "graph_dependency_concept_coverage"
        } else if evidence.payload.get("sentence_id") == claim.payload.get("sentence_id") {
            "same_sentence_evidence"
        } else {
            "document_neighborhood"
        };
        let payload = json!({"basis":basis,"member_anchor_ids":[evidence.payload.get("source_anchor_id").and_then(Value::as_str).unwrap_or(&evidence.node_id),claim.payload.get("source_anchor_id").and_then(Value::as_str).unwrap_or(&claim.node_id)]});
        add_analysis_edge(
            connection,
            &format!("support:{}->{}", evidence.node_id, claim.node_id),
            "evidence",
            "supports",
            &evidence.node_id,
            &claim.node_id,
            "",
            0.5,
            payload.clone(),
        )?;
        let evidence_anchor = evidence
            .payload
            .get("source_anchor_id")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let claim_anchor = claim
            .payload
            .get("source_anchor_id")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if !evidence_anchor.is_empty()
            && !claim_anchor.is_empty()
            && evidence_anchor != claim_anchor
        {
            add_analysis_edge(
                connection,
                &format!("anchor-support:{evidence_anchor}->{claim_anchor}"),
                "evidence",
                "supports",
                evidence_anchor,
                claim_anchor,
                "",
                0.5,
                json!({"basis":basis,"claim_node_id":claim.node_id,"evidence_node_id":evidence.node_id,"participates_in_ordering_dag":false}),
            )?;
        }
    }
    Ok(evidence_nodes)
}

fn experiment_sentence_kinds(text: &str) -> Vec<&'static str> {
    let mut kinds = Vec::new();
    for (kind, cues) in [
        ("hypothesis", &(["hypothesis", "仮説"][..])),
        ("metric", &(["metric", "指標"][..])),
        ("baseline", &(["baseline", "ベースライン"][..])),
        ("experiment", EXPERIMENT_ACTIVITY_CUES),
        ("expected_result", &(["expected", "期待"][..])),
    ] {
        if has_any(text, cues) {
            kinds.push(kind);
        }
    }
    kinds
}

fn add_experiment_layer(
    connection: &Connection,
    document_id: &str,
    sentences: &[Node],
    profile: &str,
) -> Result<(), String> {
    let semantic = metadata_json(connection, "semantic_prose_ir", json!({}))?;
    let status = semantic
        .pointer("/analysis_intents")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .find(|intent| intent.get("intent").and_then(Value::as_str) == Some("experiment_plan"))
        .and_then(|intent| intent.get("status"))
        .and_then(Value::as_str)
        .unwrap_or("");
    if status == "present" || (status == "vocabulary_only" && profile == "experiment") {
        // These are the existing deterministic plan applicability rules.
    } else if status == "absent" || status == "vocabulary_only" {
        return Ok(());
    } else if status.is_empty() {
        insert_document_diagnostic(connection,"semantic_experiment_plan_ir_missing","Deterministic experiment-plan intent is missing; repair prose IR generation before accepting experiment-plan diagnostics.",Some(json!({"add":"deterministic semantic prose IR with analysis_intents.experiment_plan status","verification_route":"semantic_environment_repair","verification_question":"Why is deterministic semantic prose evidence missing from a graph that requires experiment-plan applicability?","verification_targets":["$prose-reasoning-graph","deterministic semantic prose evidence"],"evidence_required":["semantic_prose_ir.analysis_intents","deterministic capability and owner evidence"]})))?;
        return Ok(());
    }
    let mut counts = BTreeMap::<String, usize>::new();
    for sentence in sentences {
        for kind in experiment_sentence_kinds(&sentence.text) {
            let count = counts.entry(kind.into()).or_default();
            *count += 1;
            let id = format!("experiment:{kind}:{count}");
            add_analysis_node(
                connection,
                &id,
                document_id,
                "experiment",
                kind,
                &first_words(&sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT),
                &sentence.text,
                sentence.source_start,
                sentence.source_end,
                EXTRACTED_NODE_CONFIDENCE,
                derived_anchor_payload(&sentence.node_id, &format!("experiment_{kind}_cue")),
            )?;
        }
    }
    Ok(())
}

fn add_presentation_feature_layer(
    connection: &Connection,
    document_id: &str,
    paragraphs: &[Node],
    sentences: &[Node],
) -> Result<(), String> {
    let phases = fetch_nodes(connection, Some("phase"), Some("move"))?
        .into_iter()
        .filter_map(|node| {
            node.payload
                .get("paragraph_id")
                .and_then(Value::as_str)
                .map(|id| (id.to_owned(), node.label))
        })
        .collect::<BTreeMap<_, _>>();
    let mut sentence_ids = BTreeMap::<String, BTreeSet<String>>::new();
    for sentence in sentences {
        if let Some(id) = sentence.payload.get("paragraph_id").and_then(Value::as_str) {
            sentence_ids
                .entry(id.into())
                .or_default()
                .insert(sentence.node_id.clone());
        }
    }
    for paragraph in paragraphs {
        if is_structured_presentation_block(&paragraph.text) {
            continue;
        }
        let role = phases
            .get(&paragraph.node_id)
            .map(String::as_str)
            .unwrap_or("");
        let topology = concept_relation_edges_for_anchor(
            connection,
            &paragraph.node_id,
            GRAPH_TOPOLOGY_CONCEPTS,
        )?;
        if !topology.is_empty() {
            insert_presentation_feature(
                connection,
                document_id,
                paragraph,
                "relational_topology",
                "concept relation subgraph exists inside the projection anchor",
                &topology,
            )?;
        }
        let attributes = concept_relation_edges_for_anchor(
            connection,
            &paragraph.node_id,
            ALIGNED_ATTRIBUTE_CONCEPTS,
        )?;
        if has_formula_signal(&paragraph.text) {
            insert_presentation_feature(
                connection,
                document_id,
                paragraph,
                "formal_constraint",
                "source anchor contains a formal relation signal",
                &[],
            )?;
        }
        let experiment = experiment_kinds_for_anchors(
            connection,
            sentence_ids
                .get(&paragraph.node_id)
                .unwrap_or(&BTreeSet::new()),
        )?;
        if role == "operationalization" || !experiment.is_empty() || !attributes.is_empty() {
            insert_presentation_feature(
                connection,
                document_id,
                paragraph,
                "aligned_attribute_set",
                "phase or experiment nodes create an attribute-set subgraph",
                &attributes,
            )?;
        }
        let sequence = concept_relation_edges_for_anchor(
            connection,
            &paragraph.node_id,
            DECISION_SEQUENCE_CONCEPTS,
        )?;
        if role == "recommendation" || !sequence.is_empty() {
            insert_presentation_feature(
                connection,
                document_id,
                paragraph,
                "dependency_sequence",
                "recommendation phase creates a decision-sequence projection",
                &sequence,
            )?;
        }
    }
    Ok(())
}

fn concept_relation_edges_for_anchor(
    connection: &Connection,
    paragraph_id: &str,
    allowed: &[&str],
) -> Result<Vec<String>, String> {
    let mut statement=connection.prepare("SELECT e.id,left_node.label,right_node.label FROM edges e JOIN nodes left_node ON left_node.id=e.from_node_id JOIN nodes right_node ON right_node.id=e.to_node_id WHERE e.layer='concept' AND e.kind='cooccurs_in_anchor' AND json_extract(e.payload_json,'$.source_anchor_id')=?1 ORDER BY e.id").map_err(|error|error.to_string())?;
    let rows = statement
        .query_map(params![paragraph_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|error| error.to_string())?;
    let mut output = Vec::new();
    for row in rows {
        let (id, left, right) = row.map_err(|error| error.to_string())?;
        if allowed.contains(&left.to_lowercase().as_str())
            && allowed.contains(&right.to_lowercase().as_str())
        {
            output.push(id);
        }
    }
    Ok(output)
}

fn experiment_kinds_for_anchors(
    connection: &Connection,
    anchor_ids: &BTreeSet<String>,
) -> Result<BTreeSet<String>, String> {
    let mut kinds = BTreeSet::new();
    for node in fetch_nodes(connection, Some("experiment"), None)? {
        if node
            .payload
            .get("source_anchor_id")
            .and_then(Value::as_str)
            .is_some_and(|id| anchor_ids.contains(id))
        {
            kinds.insert(node.kind);
        }
    }
    Ok(kinds)
}

fn insert_presentation_feature(
    connection: &Connection,
    document_id: &str,
    paragraph: &Node,
    kind: &str,
    basis: &str,
    basis_edges: &[String],
) -> Result<(), String> {
    let id = format!("presentation-feature:{}:{kind}", paragraph.node_id);
    add_analysis_node(
        connection,
        &id,
        document_id,
        "presentation",
        "feature",
        kind,
        kind,
        paragraph.source_start,
        paragraph.source_end,
        EXTRACTED_NODE_CONFIDENCE,
        json!({"feature_kind":kind,"source_anchor_id":paragraph.node_id,"member_anchor_ids":[paragraph.node_id],"basis":basis,"basis_edge_ids":basis_edges}),
    )?;
    add_analysis_edge(
        connection,
        &format!("presentation-feature-edge:{}->{id}", paragraph.node_id),
        "presentation",
        "has_feature",
        &paragraph.node_id,
        &id,
        "",
        EXTRACTED_NODE_CONFIDENCE,
        json!({"feature_kind":kind,"basis_edge_ids":basis_edges,"participates_in_projection_features":true}),
    )
}

fn has_formula_signal(text: &str) -> bool {
    FORMULA_SYMBOL.is_match(text)
        || FORMULA_MATH.is_match(text)
        || FORMULA_ASSIGNMENT.is_match(text)
}

fn edge_from_row(row: &Row<'_>) -> rusqlite::Result<Edge> {
    Ok(Edge {
        edge_id: row.get("id")?,
        layer: row.get("layer")?,
        kind: row.get("kind")?,
        from_node_id: row.get("from_node_id")?,
        to_node_id: row.get("to_node_id")?,
        order_kind: row
            .get::<_, Option<String>>("order_kind")?
            .unwrap_or_default(),
        confidence: row.get("confidence")?,
        payload: payload_value(&row.get::<_, String>("payload_json")?),
    })
}

fn incident_edges_for_members(
    connection: &Connection,
    members: &[String],
) -> Result<Vec<Edge>, String> {
    if members.is_empty() {
        return Ok(Vec::new());
    }
    let placeholders = std::iter::repeat_n("?", members.len())
        .collect::<Vec<_>>()
        .join(",");
    let sql=format!("SELECT * FROM edges WHERE from_node_id IN ({placeholders}) OR to_node_id IN ({placeholders}) ORDER BY id");
    let mut statement = connection
        .prepare(&sql)
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map(
            rusqlite::params_from_iter(members.iter().chain(members.iter())),
            edge_from_row,
        )
        .map_err(|error| error.to_string())?;
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .map_err(|error| error.to_string())
}

fn basis_edges_for_members(
    connection: &Connection,
    members: &[String],
) -> Result<Vec<String>, String> {
    Ok(incident_edges_for_members(connection, members)?
        .into_iter()
        .map(|edge| edge.edge_id)
        .collect())
}

fn build_projection_views(
    connection: &Connection,
    profile: &str,
) -> Result<Vec<ProjectionView>, String> {
    let paragraphs = fetch_nodes(connection, Some("form"), Some("paragraph"))?;
    let sentences = fetch_nodes(connection, Some("form"), Some("sentence"))?;
    let phases = fetch_nodes(connection, Some("phase"), Some("move"))?;
    let phase_by_paragraph = phases
        .iter()
        .filter_map(|phase| {
            phase
                .payload
                .get("paragraph_id")
                .and_then(Value::as_str)
                .map(|id| (id.to_owned(), phase.clone()))
        })
        .collect::<BTreeMap<_, _>>();
    let mut sentences_by_paragraph = BTreeMap::<String, Vec<String>>::new();
    for sentence in sentences {
        if let Some(id) = sentence.payload.get("paragraph_id").and_then(Value::as_str) {
            sentences_by_paragraph
                .entry(id.into())
                .or_default()
                .push(sentence.node_id);
        }
    }
    let mut views = Vec::new();
    for (index, paragraph) in paragraphs.iter().enumerate() {
        let role = phase_by_paragraph
            .get(&paragraph.node_id)
            .map(|node| node.label.clone())
            .unwrap_or_else(|| paragraph.label.clone());
        let mut members = vec![paragraph.node_id.clone()];
        members.extend(
            sentences_by_paragraph
                .get(&paragraph.node_id)
                .cloned()
                .unwrap_or_default(),
        );
        let evidence = projection_format_evidence(connection, paragraph, &members, &role)?;
        let (recommended_format, format_reason) = presentation_recommendation(&evidence);
        let basis_edges = basis_edges_for_members(connection, &members)?;
        let basis_nodes = phase_by_paragraph
            .get(&paragraph.node_id)
            .map(|node| vec![node.node_id.clone()])
            .unwrap_or_default();
        views.push(ProjectionView{view_id:format!("view:{profile}:{}",index+1),profile:profile.into(),members:members.clone(),role:role.clone(),reader_state_before:reader_state_before(&role).into(),reader_state_after:reader_state_after(&role).into(),abstraction_level:abstraction_level_for_role(&role).into(),recommended_format:recommended_format.into(),format_reason:format_reason.into(),inference_basis:json!({"source":"canonical_graph_projection","member_anchor_ids":members,"basis_edges":basis_edges,"basis_nodes":basis_nodes,"presentation_evidence":evidence}),confidence:if phase_by_paragraph.contains_key(&paragraph.node_id){PHASE_INFERENCE_CONFIDENCE}else{PROJECTION_VIEW_FALLBACK_CONFIDENCE}});
    }
    Ok(views)
}

fn projection_format_evidence(
    connection: &Connection,
    _paragraph: &Node,
    members: &[String],
    role: &str,
) -> Result<ProjectionFormatEvidence, String> {
    let incident = incident_edges_for_members(connection, members)?;
    let member_set = members.iter().cloned().collect::<BTreeSet<_>>();
    let mut feature_nodes = BTreeSet::new();
    let mut feature_edges = Vec::new();
    for edge in &incident {
        if edge.layer == "presentation" && edge.kind == "has_feature" {
            feature_nodes.insert(edge.to_node_id.clone());
            feature_edges.push(edge.edge_id.clone());
        }
    }
    let all_nodes = fetch_nodes(connection, None, None)?;
    let derived = all_nodes
        .into_iter()
        .filter(|node| {
            member_set.contains(&node.node_id)
                || node
                    .payload
                    .get("source_anchor_id")
                    .and_then(Value::as_str)
                    .is_some_and(|anchor| member_set.contains(anchor))
                || node
                    .payload
                    .get("sentence_id")
                    .and_then(Value::as_str)
                    .is_some_and(|anchor| member_set.contains(anchor))
                || node
                    .payload
                    .get("paragraph_id")
                    .and_then(Value::as_str)
                    .is_some_and(|anchor| member_set.contains(anchor))
        })
        .collect::<Vec<_>>();
    let feature_labels = derived
        .iter()
        .filter(|node| feature_nodes.contains(&node.node_id))
        .map(|node| node.label.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let derived_layers = derived
        .iter()
        .filter(|node| !member_set.contains(&node.node_id))
        .map(|node| node.layer.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let derived_kinds = derived
        .iter()
        .filter(|node| !member_set.contains(&node.node_id))
        .map(|node| node.kind.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    Ok(ProjectionFormatEvidence {
        member_anchor_ids: members.to_vec(),
        role: role.into(),
        presentation_features: feature_labels,
        presentation_feature_edges: feature_edges,
        derived_layers,
        derived_kinds,
        edge_layers: incident
            .iter()
            .map(|edge| edge.layer.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect(),
        edge_kinds: incident
            .iter()
            .map(|edge| edge.kind.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect(),
    })
}

fn presentation_recommendation(
    evidence: &ProjectionFormatEvidence,
) -> (&'static str, &'static str) {
    let features = evidence
        .presentation_features
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if features.contains("formal_constraint") {
        (
            "equation",
            "presentation feature subgraph formal_constraint",
        )
    } else if features.contains("aligned_attribute_set") {
        (
            "table",
            "presentation feature subgraph aligned_attribute_set",
        )
    } else if features.contains("relational_topology") {
        (
            "figure",
            "presentation feature subgraph relational_topology",
        )
    } else if features.contains("dependency_sequence") {
        (
            "ordered_list",
            "presentation feature subgraph dependency_sequence",
        )
    } else if features.contains("parallel_sibling_set") {
        (
            "bulleted_list",
            "presentation feature subgraph parallel_sibling_set",
        )
    } else {
        ("prose", "continuous explanation preserves local flow")
    }
}

fn reader_state_before(role: &str) -> &'static str {
    match role {
        "context" => "topic not yet framed",
        "operationalization" => "claim not yet measurable",
        "recommendation" => "decision not yet stated",
        "limitation" => "risk not yet bounded",
        _ => "current thread established",
    }
}
fn reader_state_after(role: &str) -> &'static str {
    match role {
        "context" => "topic framed",
        "operationalization" => "claim mapped to observable terms",
        "recommendation" => "next decision stated",
        "limitation" => "risk or boundary introduced",
        _ => "thread developed",
    }
}
fn abstraction_level_for_role(role: &str) -> &'static str {
    match role {
        "operationalization" | "hypothesis" => "operational",
        "recommendation" | "limitation" => "meta",
        "context" => "conceptual",
        _ => "surface",
    }
}

fn phase_by_sentence_anchor(
    connection: &Connection,
    sentences: &[Node],
) -> Result<BTreeMap<String, String>, String> {
    let phases = fetch_nodes(connection, Some("phase"), Some("move"))?;
    let by_paragraph = phases
        .iter()
        .filter_map(|phase| {
            phase
                .payload
                .get("paragraph_id")
                .and_then(Value::as_str)
                .map(|id| (id.to_owned(), phase.label.clone()))
        })
        .collect::<BTreeMap<_, _>>();
    Ok(sentences
        .iter()
        .filter_map(|sentence| {
            sentence
                .payload
                .get("paragraph_id")
                .and_then(Value::as_str)
                .map(|paragraph| {
                    (
                        sentence.node_id.clone(),
                        by_paragraph.get(paragraph).cloned().unwrap_or_default(),
                    )
                })
        })
        .collect())
}

fn ordered_anchor_record(
    node: &Node,
    position: usize,
    profile: &str,
    phases: &BTreeMap<String, String>,
) -> Value {
    let phase = phases.get(&node.node_id).cloned().unwrap_or_default();
    json!({"position":position,"node_id":node.node_id,"document_id":node.document_id,"kind":node.kind,"text":node.text,"source_start":node.source_start,"source_end":node.source_end,"paragraph_id":node.payload.get("paragraph_id").cloned().unwrap_or_else(||json!("")),"section_path":node.payload.get("section_path").cloned().unwrap_or_else(||json!([])),"phase":phase,"profile_priority":phase_priority(&phase,profile)})
}

fn selected_ordering_payload(connection: &Connection, profile: &str) -> Result<Value, String> {
    let sentences = fetch_nodes(connection, Some("form"), Some("sentence"))?;
    let edges = selected_ordering_edges(connection, &sentences)?;
    let phases = phase_by_sentence_anchor(connection, &sentences)?;
    let (ordered, cycle, relaxed) =
        priority_topological_order(&sentences, &edges, profile, &phases);
    let by_id = sentences
        .iter()
        .map(|node| (node.node_id.as_str(), node))
        .collect::<BTreeMap<_, _>>();
    let records = ordered
        .iter()
        .enumerate()
        .filter_map(|(index, id)| {
            by_id
                .get(id.as_str())
                .map(|node| ordered_anchor_record(node, index + 1, profile, &phases))
        })
        .collect::<Vec<_>>();
    Ok(
        json!({"scope":"whole_document_source_anchors","unit_kind":"sentence","profile":profile,"algorithm":"priority_topological_sort_selected_ordering_subgraph","ordering_policy":["presentation/form hard_before edges as topological constraints","form containment and source anchor membership","profile phase preference","discourse adjacency_preferred edges as soft queue priorities","soft-edge confidence score","source order as final stable tie-breaker"],"cycle_policy":"diagnose hard constraint cycles and relax only cyclic hard edges","cycle_detected":cycle,"relaxed_edges":relaxed,"ordering_edges":edges,"ordered_anchor_ids":ordered,"ordered_anchors":records}),
    )
}

fn source_anchor_nodes(nodes: &[Node]) -> Vec<Node> {
    nodes
        .iter()
        .filter(|node| {
            node.layer == "form"
                && matches!(
                    node.kind.as_str(),
                    "section" | "paragraph" | "sentence" | "edu"
                )
        })
        .cloned()
        .collect()
}

fn projection_payload(
    connection: &Connection,
    profile: &str,
    db_path: &Path,
) -> Result<Value, String> {
    let counts = layer_counts(connection)?;
    let nodes = fetch_nodes(connection, None, None)?;
    let edges = fetch_edges(connection)?;
    let diagnostics = fetch_diagnostics(connection)?;
    let operations = fetch_operations(connection)?;
    let views = build_projection_views(connection, profile)?;
    let layers = LAYERS
        .iter()
        .map(|layer| {
            (
                layer.to_string(),
                json!(counts.get(*layer).copied().unwrap_or(0)),
            )
        })
        .collect::<serde_json::Map<_, _>>();
    Ok(
        json!({"profile":profile,"graph_db":db_path,"canonical_graph":"text_anchored_semantic_graph","documents":fetch_document_records(connection)?,"semantic_prose_ir":metadata_json(connection,"semantic_prose_ir",json!({}))?,"corpus_hints":metadata_json(connection,"corpus_hints",json!([]))?,"layers":layers,"skill_handoffs":skill_handoffs(profile,db_path),"source_anchors":source_anchor_nodes(&nodes),"selected_ordering":selected_ordering_payload(connection,profile)?,"projection_views":views,"nodes":nodes,"edges":edges,"diagnostics":diagnostics,"edit_operations":operations}),
    )
}

fn command_project(options: &Options) -> Result<i32, String> {
    let db = graph_db_path(options)?;
    let connection = connect(&db)?;
    let payload = projection_payload(&connection, &options.profile, &db)?;
    let text = if options.format == "json" {
        serde_json::to_string_pretty(&payload).map_err(|error| error.to_string())? + "\n"
    } else {
        serde_json::to_string_pretty(&payload).map_err(|error| error.to_string())? + "\n"
    };
    write_output(options.output.as_deref().ok_or("--out is required")?, &text)?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_PROJECT",
        json!({"PROSE_REASONING_GRAPH_PROJECTION":options.output}),
    )?;
    Ok(0)
}

fn add_section_edges(
    connection: &Connection,
    sections: &[Node],
    paragraphs: &[Node],
) -> Result<(), String> {
    for (index, paragraph) in paragraphs.iter().enumerate() {
        let Some(section_path) = paragraph
            .payload
            .get("section_path")
            .and_then(Value::as_array)
        else {
            continue;
        };
        let Some(section_id) = section_path.last().and_then(Value::as_str) else {
            continue;
        };
        if sections.iter().any(|section| section.node_id == section_id) {
            add_analysis_edge(
                connection,
                &format!("section-content:{section_id}->{}", paragraph.node_id),
                "form",
                "contains",
                section_id,
                &paragraph.node_id,
                "",
                1.0,
                json!({"source":"markdown_section_path","ordinal":index + 1}),
            )?;
        }
    }
    Ok(())
}

fn section_path(node: &Node) -> Vec<String> {
    node.payload
        .get("section_path")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect()
}

fn is_display_math_block(text: &str) -> bool {
    let stripped = text.trim();
    stripped.starts_with("$$")
        && stripped.ends_with("$$")
        && stripped.chars().count() > DISPLAY_MATH_EMPTY_DELIMITER_LENGTH
}

fn is_structured_presentation_block(text: &str) -> bool {
    let stripped = text.trim_start();
    is_display_math_block(stripped)
        || stripped.starts_with("<!--")
        || STRUCTURED_BLOCK_PREFIX.is_match(stripped)
        || MERMAID_EDGE_PREFIX.is_match(stripped)
        || MERMAID_BLOCK_PREFIX.is_match(stripped)
        || MERMAID_NODE_PREFIX.is_match(stripped)
}

fn insert_document_diagnostic(
    connection: &Connection,
    rule: &str,
    message: &str,
    action: Option<Value>,
) -> Result<(), String> {
    let target = fetch_nodes(connection, Some("source"), Some("document"))?
        .first()
        .map(|node| node.node_id.clone())
        .unwrap_or_default();
    insert_diagnostic(
        connection,
        &Diagnostic {
            diagnostic_id: format!("diag:{rule}"),
            layer: "diagnostics".into(),
            severity: "warn".into(),
            rule: rule.into(),
            message: message.into(),
            target_node_id: target,
            target_edge_id: String::new(),
            action: action.unwrap_or_else(|| verification_action_for_rule(rule)),
        },
    )
}

fn verification_action_for_rule(rule: &str) -> Value {
    if matches!(rule, "unsupported_claim" | "claim_without_evidence_layer") {
        return json!({"add":"evidence, warrant, limitation, or verification result","verification_route":"claim_support_verification","verification_question":"Is the claim supported by source evidence, a valid warrant, a formal proof obligation, or a stated limitation?","verification_targets":["logic-gap-review","$literature-survey","citation-evidence-review"],"conditional_verification_targets":[{"target":"$formal-proof-workflow","when":"the claim is mathematical, proof-like, or implementation-derived"}],"evidence_required":["source packet","citation or measured result","explicit warrant or proof obligation"],"recursive_verification":recursive_verification_for_route("claim_support_verification")});
    }
    if rule == "topic_jump_without_bridge" {
        return json!({"add":"verified bridge, explicit relation, reorder decision, or separation","verification_route":"connection_verification","verification_question":"Do the adjacent units share a valid discourse relation, missing premise, or reader-state transition?","verification_targets":["$structure-planning","logic-gap-review"],"conditional_verification_targets":[{"target":"$literature-survey","when":"the bridge depends on an external factual or scholarly premise"}],"evidence_required":["relation label","shared question or warrant","reader-state before/after"],"recursive_verification":recursive_verification_for_route("connection_verification")});
    }
    if rule.starts_with("experiment_") || rule == "metric_without_baseline" {
        return json!({"add":"experiment-plan field or documented not-applicable decision","verification_route":"experiment_plan_verification","verification_question":"Is the experiment claim testable with a hypothesis, metric, baseline, and expected result?","verification_targets":["$experiment-lifecycle","$report-writing"],"evidence_required":["hypothesis","metric","baseline","expected result","run or rerun decision"],"recursive_verification":recursive_verification_for_route("experiment_plan_verification")});
    }
    if rule == "presentation_format_candidate" {
        return json!({"add":"accepted rendering decision, rejected candidate reason, or combined presentation plan","verification_route":"presentation_format_verification","verification_question":"Does the projection view communicate better as the recommended non-prose form while preserving source anchors?","verification_targets":["$structure-planning","$report-writing"],"evidence_required":["projection view","member anchors","format reason","reader-state before/after"],"recursive_verification":recursive_verification_for_route("presentation_format_verification")});
    }
    if rule == "selected_ordering_cycle" {
        return json!({"add":"reorder decision, relaxed edge explanation, or graph edge correction","verification_route":"ordering_cycle_verification","verification_question":"Which hard ordering constraints should be relaxed, split, or corrected so the reader sequence remains acyclic?","verification_targets":["$structure-planning","$prose-reasoning-graph"],"evidence_required":["selected_ordering.relaxed_edges","source anchors","preserved source ids"],"recursive_verification":recursive_verification_for_route("ordering_cycle_verification")});
    }
    json!({})
}

fn recursive_verification_for_route(route: &str) -> Value {
    let common = json!({"max_depth":3,"closure_condition":"all child questions have evidence, checked proof/experiment evidence, an explicit limitation, or an unresolved-leaf record","unresolved_leaf_policy":"do not rewrite as settled prose; record blocker/warn with owner, route, missing evidence, and next verification command"});
    let step = |id: &str, route: &str, question: &str, unresolved: &str| json!({"id":id,"route":route,"question":question,"if_unresolved":unresolved});
    let steps=match route {
        "claim_support_verification"=>vec![step("decompose_claim","logic-gap-review","What are the atomic claim, assumptions, warrants, and evidence requirements?","create child claim_support_verification items for each missing premise or warrant"),step("verify_external_support","$literature-survey / citation-evidence-review","Does a source packet, citation, measurement, or contrary source settle each atomic claim?","record missing source packet or limitation and keep the child open"),step("verify_formal_obligation","$formal-proof-workflow","If the claim is mathematical, proof-like, or implementation-derived, can a proof obligation be checked?","record proof_status and the exact missing checker, command, lemma, or environment")],
        "connection_verification"=>vec![step("classify_relation","$structure-planning","What discourse relation or reader-state transition is claimed between the adjacent units?","try reorder, separation, or explicit limitation before adding a bridge"),step("verify_missing_premise","logic-gap-review","Does the connection require an unstated premise or warrant?","create child claim_support_verification items for the missing premise"),step("verify_external_bridge","$literature-survey","Does the bridge depend on external factual or scholarly support?","record missing source packet or remove the bridge claim")],
        "experiment_plan_verification"=>vec![step("decompose_empirical_claim","$experiment-lifecycle","What hypothesis, metric, baseline, expected result, and stop condition are required?","create child experiment_plan_verification items for each missing field"),step("verify_measurement_contract","$experiment-lifecycle","Can the metric be measured with a valid denominator, directionality, and comparison?","record rerun or protocol-design blocker"),step("verify_report_claim","$report-writing","Does the report claim stay within the verified experiment result and limitations?","downgrade to limitation or keep the claim out of prose")],
        "presentation_format_verification"=>vec![step("verify_projection_feature","$structure-planning","Which graph feature makes prose weaker than the recommended format?","downgrade the candidate to prose or keep an unresolved presentation warning"),step("verify_renderer_contract","$report-writing","Can the recommended table, figure, list, or equation preserve member anchors and source evidence?","keep prose and record why the rendering was rejected"),step("verify_reader_state","$structure-planning","Does the format improve the reader-state transition without hiding necessary prose warrants?","combine prose with the candidate or keep the warning open")],
        "ordering_cycle_verification"=>vec![json!({"id":"inspect_relaxed_edges","question":"Which relaxed hard ordering edges create the cycle?","route":"$prose-reasoning-graph"}),json!({"id":"choose_reader_order","question":"Which acyclic order preserves source anchors and reader-state transition?","route":"$structure-planning"}),json!({"id":"record_relaxation","question":"Is the relaxed edge explained as a reorder edit, limitation, or graph correction?","route":"$prose-reasoning-graph"})],
        _=>return json!({"max_depth":3,"closure_condition":"all child questions have evidence, checked proof/experiment evidence, an explicit limitation, or an unresolved-leaf record","unresolved_leaf_policy":"do not rewrite as settled prose; record blocker/warn with owner, route, missing evidence, and next verification command"}),
    };
    let mut result = common;
    result["steps"] = json!(steps);
    result
}

fn experiment_layer_applicable(connection: &Connection) -> Result<bool, String> {
    if layer_counts(connection)?
        .get("experiment")
        .copied()
        .unwrap_or(0)
        > 0
    {
        return Ok(true);
    }
    let semantic = metadata_json(connection, "semantic_prose_ir", json!({}))?;
    let status = semantic
        .pointer("/analysis_intents")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .find(|intent| intent.get("intent").and_then(Value::as_str) == Some("experiment_plan"))
        .and_then(|intent| intent.get("status"))
        .and_then(Value::as_str)
        .unwrap_or("");
    Ok(status == "present")
}

fn required_layers_for_profile(profile: &str, experiment_applicable: bool) -> Vec<&'static str> {
    let mut layers = vec![
        "source",
        "form",
        "concept",
        "phase",
        "discourse",
        "presentation",
        "projection",
        "explanation",
    ];
    if matches!(profile, "logic" | "academic" | "paper" | "all") {
        layers.extend(["argument", "evidence"]);
    }
    if profile == "experiment" || (profile == "all" && experiment_applicable) {
        layers.push("experiment");
    }
    layers
}

fn add_layer_coverage_diagnostic(connection: &Connection, profile: &str) -> Result<(), String> {
    let counts = layer_counts(connection)?;
    let experiment_applicable = experiment_layer_applicable(connection)?;
    let missing = required_layers_for_profile(profile, experiment_applicable)
        .into_iter()
        .filter(|layer| counts.get(*layer).copied().unwrap_or(0) == 0)
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        insert_document_diagnostic(
            connection,
            "missing_layer_representation",
            &format!(
                "Missing graph layer representations: {}.",
                missing.join(", ")
            ),
            None,
        )?;
    }
    Ok(())
}

fn add_diagnostics(
    connection: &Connection,
    paragraphs: &[Node],
    claims: &[Node],
    evidence: &[Node],
    profile: &str,
    lexicon: &BTreeMap<String, Vec<String>>,
) -> Result<(), String> {
    let mut statement = connection
        .prepare("SELECT to_node_id FROM edges WHERE layer='evidence' AND kind='supports'")
        .map_err(|error| error.to_string())?;
    let supported = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| error.to_string())?
        .collect::<rusqlite::Result<BTreeSet<_>>>()
        .map_err(|error| error.to_string())?;
    for claim in claims {
        if !supported.contains(&claim.node_id) {
            insert_diagnostic(
                connection,
                &Diagnostic {
                    diagnostic_id: format!("diag:unsupported:{}", claim.node_id),
                    layer: "argument".into(),
                    severity: "blocker".into(),
                    rule: "unsupported_claim".into(),
                    message: format!("Claim `{}` has no supporting evidence edge.", claim.node_id),
                    target_node_id: claim.node_id.clone(),
                    target_edge_id: String::new(),
                    action: verification_action_for_rule("unsupported_claim"),
                },
            )?;
        }
    }
    let semantic = metadata_json(connection, "semantic_prose_ir", json!({}))?;
    let status = semantic
        .pointer("/analysis_intents")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .find(|item| item.get("intent").and_then(Value::as_str) == Some("experiment_plan"))
        .and_then(|item| item.get("status"))
        .and_then(Value::as_str)
        .unwrap_or("");
    if status.is_empty() {
        insert_document_diagnostic(connection,"semantic_experiment_plan_ir_missing","Deterministic experiment-plan intent is missing; repair prose IR generation before accepting experiment-plan diagnostics.",Some(json!({"add":"deterministic semantic prose IR with analysis_intents.experiment_plan status","verification_route":"semantic_environment_repair","verification_question":"Why is deterministic semantic prose evidence missing from a graph that requires experiment-plan applicability?","verification_targets":["$prose-reasoning-graph","deterministic semantic prose evidence"],"evidence_required":["semantic_prose_ir.analysis_intents","deterministic capability and owner evidence"]})))?;
    }
    let experiment_applicable =
        status == "present" || (status == "vocabulary_only" && profile == "experiment");
    if experiment_applicable {
        let kinds = fetch_nodes(connection, Some("experiment"), None)?
            .into_iter()
            .map(|node| node.kind)
            .collect::<BTreeSet<_>>();
        for (kind, rule, message) in [
            (
                "hypothesis",
                "experiment_without_hypothesis",
                "Experiment language appears without a hypothesis node.",
            ),
            (
                "metric",
                "experiment_without_metric",
                "Experiment planning lacks a metric node.",
            ),
            (
                "baseline",
                "metric_without_baseline",
                "Experiment planning lacks a baseline node.",
            ),
            (
                "expected_result",
                "experiment_without_expected_result",
                "Experiment planning lacks an expected-result node.",
            ),
        ] {
            if !kinds.contains(kind) {
                insert_document_diagnostic(connection, rule, message, None)?;
            }
        }
    }
    for (index, pair) in paragraphs.windows(2).enumerate() {
        let left = &pair[0];
        let right = &pair[1];
        if left.document_id != right.document_id || section_path(left) != section_path(right) {
            continue;
        }
        if lexical_overlap(&left.text, &right.text, lexicon) < TOPIC_JUMP_MAX_OVERLAP
            && first_discourse_signal(&right.text).is_empty()
            && !is_structured_presentation_block(&left.text)
            && !is_structured_presentation_block(&right.text)
        {
            insert_diagnostic(
                connection,
                &Diagnostic {
                    diagnostic_id: format!("diag:topic-jump:{}", index + 1),
                    layer: "discourse".into(),
                    severity: "warn".into(),
                    rule: "topic_jump_without_bridge".into(),
                    message: format!(
                        "Paragraph `{}` to `{}` has low shared terms and no bridge cue.",
                        left.node_id, right.node_id
                    ),
                    target_node_id: right.node_id.clone(),
                    target_edge_id: String::new(),
                    action: verification_action_for_rule("topic_jump_without_bridge"),
                },
            )?;
        }
    }
    if !claims.is_empty() && evidence.is_empty() {
        insert_document_diagnostic(
            connection,
            "claim_without_evidence_layer",
            "Claims exist but the evidence layer has no evidence nodes.",
            None,
        )?;
    }
    add_layer_coverage_diagnostic(connection, profile)?;
    add_presentation_format_diagnostics(connection, profile)?;
    add_selected_ordering_cycle_diagnostic(connection, profile)?;
    Ok(())
}

fn add_presentation_format_diagnostics(
    connection: &Connection,
    profile: &str,
) -> Result<(), String> {
    for view in build_projection_views(connection, profile)? {
        if view.recommended_format == "prose" {
            continue;
        }
        let target = view.members.first().cloned().unwrap_or_default();
        let mut action = verification_action_for_rule("presentation_format_candidate");
        action["recommended_format"] = json!(view.recommended_format);
        action["format_reason"] = json!(view.format_reason);
        action["view_id"] = json!(view.view_id);
        action["member_anchor_ids"] = json!(view.members);
        insert_diagnostic(
            connection,
            &Diagnostic {
                diagnostic_id: format!("diag:presentation-format:{}", view.view_id),
                layer: "presentation".into(),
                severity: "warn".into(),
                rule: "presentation_format_candidate".into(),
                message: format!(
                    "Projection `{}` recommends `{}`: {}.",
                    view.view_id, view.recommended_format, view.format_reason
                ),
                target_node_id: target,
                target_edge_id: String::new(),
                action,
            },
        )?;
    }
    Ok(())
}

fn add_edit_operations(
    connection: &Connection,
    paragraphs: &[Node],
    lexicon: &BTreeMap<String, Vec<String>>,
) -> Result<(), String> {
    let prose = paragraphs
        .iter()
        .filter(|paragraph| !is_structured_presentation_block(&paragraph.text))
        .collect::<Vec<_>>();
    for paragraph in &prose {
        let sentence_count = split_sentences(&paragraph.text).len();
        if sentence_count > SPLIT_PARAGRAPH_SENTENCE_LIMIT {
            insert_operation(
                connection,
                &EditOperation {
                    operation_id: format!("op:split:{}", paragraph.node_id),
                    kind: "split_paragraph".into(),
                    target_ids: vec![paragraph.node_id.clone()],
                    reason: format!(
                        "`{}` has {sentence_count} sentence units and may need a split.",
                        paragraph.node_id
                    ),
                    payload: json!({"provenance":"source_graph_nodes","history_effect":"records_candidate_without_mutating_source","preserve":"source spans and section path","sentence_count":sentence_count}),
                },
            )?;
            break;
        }
    }
    for pair in prose.windows(2) {
        let overlap = lexical_overlap(&pair[0].text, &pair[1].text, lexicon);
        if overlap > MERGE_PARAGRAPH_MIN_OVERLAP {
            insert_operation(
                connection,
                &EditOperation {
                    operation_id: format!("op:merge:{}:{}", pair[0].node_id, pair[1].node_id),
                    kind: "merge_paragraphs".into(),
                    target_ids: vec![pair[0].node_id.clone(), pair[1].node_id.clone()],
                    reason: format!(
                        "`{}` and `{}` share focus and may be integrated.",
                        pair[0].node_id, pair[1].node_id
                    ),
                    payload: json!({"provenance":"source_graph_nodes","history_effect":"records_candidate_without_mutating_source","lexical_overlap":overlap,"preserve":"claims and evidence from both paragraphs"}),
                },
            )?;
            break;
        }
    }
    let mut statement = connection
        .prepare("SELECT target_node_id FROM diagnostics WHERE rule='topic_jump_without_bridge'")
        .map_err(|error| error.to_string())?;
    let targets = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| error.to_string())?
        .collect::<rusqlite::Result<BTreeSet<_>>>()
        .map_err(|error| error.to_string())?;
    for pair in prose.windows(2) {
        if targets.contains(&pair[1].node_id) {
            insert_operation(
                connection,
                &EditOperation {
                    operation_id: format!("op:bridge:{}:{}", pair[0].node_id, pair[1].node_id),
                    kind: "add_bridge".into(),
                    target_ids: vec![pair[0].node_id.clone(), pair[1].node_id.clone()],
                    reason: format!(
                        "`{}` to `{}` needs an explicit bridge.",
                        pair[0].node_id, pair[1].node_id
                    ),
                    payload: json!({"provenance":"source_graph_nodes","history_effect":"records_candidate_without_mutating_source","bridge_intent":"state the discourse relation and shared question"}),
                },
            )?;
            break;
        }
    }
    if prose.len() > 2 && !targets.is_empty() {
        insert_operation(
            connection,
            &EditOperation {
                operation_id: "op:reorder:presentation".into(),
                kind: "reorder_paragraphs".into(),
                target_ids: prose.iter().map(|node| node.node_id.clone()).collect(),
                reason:
                    "Presentation order can be checked against phase order and hard-before edges."
                        .into(),
                payload: json!({"provenance":"source_graph_nodes","history_effect":"records_candidate_without_mutating_source","strategy":"priority topological sort with phase preference"}),
            },
        )?;
    }
    Ok(())
}

fn document_canon_severity(kind: &str) -> &'static str {
    match kind {
        "broken_dependency_target" => "blocker",
        "duplicate_heading_candidate"
        | "stale_name_candidate"
        | "missing_reverse_edge"
        | "document_responsibility_gap" => "warn",
        _ => "info",
    }
}

fn command_lint(options: &Options) -> Result<i32, String> {
    let path = graph_db_path(options)?;
    let connection = connect(&path)?;
    let output = render_diagnostics(&connection, &options.profile)?;
    write_output(
        options.output.as_deref().ok_or("--out is required")?,
        &output,
    )?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_LINT",
        json!({"PROSE_REASONING_GRAPH_DIAGNOSTICS":options.output}),
    )?;
    Ok(0)
}

fn render_diagnostics(connection: &Connection, profile: &str) -> Result<String, String> {
    let diagnostics = fetch_diagnostics(connection)?;
    let mut lines = vec![
        "# Prose Reasoning Graph Diagnostics".into(),
        String::new(),
        format!("- profile: `{profile}`"),
        format!("- diagnostics: `{}`", diagnostics.len()),
        String::new(),
    ];
    if diagnostics.is_empty() {
        lines.push("No diagnostics recorded.".into());
    } else {
        for item in diagnostics {
            let target = if item.target_node_id.is_empty() {
                &item.target_edge_id
            } else {
                &item.target_node_id
            };
            let suffix = diagnostic_verification_summary(&item);
            lines.push(format!(
                "- `{}` `{}` target=`{target}`: {}{suffix}",
                item.severity, item.rule, item.message
            ));
        }
    }
    lines.push(String::new());
    Ok(lines.join("\n"))
}

fn diagnostic_verification_summary(item: &Diagnostic) -> String {
    let Some(route) = item
        .action
        .get("verification_route")
        .and_then(Value::as_str)
    else {
        return String::new();
    };
    let targets = item
        .action
        .get("verification_targets")
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .map(|value| value.as_str().unwrap_or_default())
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>()
                .join(", ")
        })
        .unwrap_or_default();
    if targets.is_empty() {
        format!(" verification_route=`{route}`")
    } else {
        format!(" verification_route=`{route}` targets=`{targets}`")
    }
}

fn command_outline(options: &Options) -> Result<i32, String> {
    let path = graph_db_path(options)?;
    let connection = connect(&path)?;
    let paragraphs = fetch_nodes(&connection, Some("form"), Some("paragraph"))?;
    let sections = fetch_nodes(&connection, Some("form"), Some("section"))?;
    let mut lines = vec!["# Prose Reasoning Graph Outline".into(), String::new()];
    for section in sections {
        lines.push(format!(
            "- section `{}`: {}",
            section.node_id, section.label
        ));
    }
    for paragraph in paragraphs {
        lines.push(format!(
            "- paragraph `{}`: {}",
            paragraph.node_id, paragraph.label
        ));
    }
    lines.push(String::new());
    write_output(
        options.output.as_deref().ok_or("--out is required")?,
        &lines.join("\n"),
    )?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_OUTLINE",
        json!({"PROSE_REASONING_GRAPH_OUTLINE_PATH":options.output}),
    )?;
    Ok(0)
}

fn command_explain(options: &Options) -> Result<i32, String> {
    let path = graph_db_path(options)?;
    let connection = connect(&path)?;
    let text = render_explanation(&connection, &options.profile, &path)?;
    write_output(options.output.as_deref().ok_or("--out is required")?, &text)?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_EXPLAIN",
        json!({"PROSE_REASONING_GRAPH_EXPLANATION":options.output}),
    )?;
    Ok(0)
}

fn render_explanation(
    connection: &Connection,
    profile: &str,
    db_path: &Path,
) -> Result<String, String> {
    let counts = layer_counts(connection)?;
    let claims = fetch_nodes(connection, Some("argument"), Some("claim"))?;
    let diagnostics = fetch_diagnostics(connection)?;
    let operations = fetch_operations(connection)?;
    let discourse = fetch_edges(connection)?
        .into_iter()
        .filter(|edge| edge.layer == "discourse")
        .collect::<Vec<_>>();
    let layers = LAYERS
        .iter()
        .filter(|layer| counts.get(**layer).copied().unwrap_or(0) > 0)
        .count();
    let mut lines = vec!["# Prose Reasoning Graph Explanation".into(), String::new(), "## Summary".into(), String::new(), format!("The graph for profile `{profile}` stores {} layer items across {layers} requested layers. The analysis DB is `{}`.", counts.values().sum::<usize>(), db_path.display()), String::new(), "## Main Claim Path".into(), String::new()];
    if claims.is_empty() {
        lines.push("1. No explicit claim nodes were detected.".into());
    } else {
        lines.extend(
            claims
                .iter()
                .take(EXPLANATION_CLAIM_LIMIT)
                .map(|claim| format!("1. `{}` {}", claim.node_id, claim.text)),
        );
    }
    lines.extend([String::new(), "## Discourse Edges".into(), String::new()]);
    if discourse.is_empty() {
        lines.push("- No discourse edges recorded.".into());
    } else {
        lines.extend(
            discourse
                .iter()
                .take(EXPLANATION_DISCOURSE_EDGE_LIMIT)
                .map(|edge| {
                    format!(
                        "- `{}` `{}` -> `{}` relation=`{}`",
                        edge.edge_id, edge.from_node_id, edge.to_node_id, edge.kind
                    )
                }),
        );
    }
    lines.extend([String::new(), "## Gaps".into(), String::new()]);
    if diagnostics.is_empty() {
        lines.push("- No graph diagnostics recorded.".into());
    } else {
        lines.extend(
            diagnostics
                .iter()
                .take(EXPLANATION_DIAGNOSTIC_LIMIT)
                .map(|item| {
                    format!(
                        "- `{}` `{}` on `{}`: {}{}",
                        item.severity,
                        item.rule,
                        item.target_node_id,
                        item.message,
                        diagnostic_verification_summary(item)
                    )
                }),
        );
    }
    lines.extend([
        String::new(),
        "## Recommended Next Edits".into(),
        String::new(),
    ]);
    if operations.is_empty() {
        lines.push("1. No edit operations recorded.".into());
    } else {
        lines.extend(
            operations
                .iter()
                .take(EXPLANATION_OPERATION_LIMIT)
                .map(|item| {
                    format!(
                        "1. `{}` `{}`: {}",
                        item.operation_id, item.kind, item.reason
                    )
                }),
        );
    }
    lines.extend([String::new(), "## Provenance Boundary".into(), String::new(), "This explanation is generated from graph nodes, edges, diagnostics, and edit operations. It is advisory evidence for the receiving skill, not policy authority.".into(), String::new()]);
    Ok(lines.join("\n"))
}

fn command_integrate(options: &Options) -> Result<i32, String> {
    let path = graph_db_path(options)?;
    let connection = connect(&path)?;
    let text = render_integration_plan(&connection, &options.profile)?;
    write_output(options.output.as_deref().ok_or("--out is required")?, &text)?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_INTEGRATE",
        json!({"PROSE_REASONING_GRAPH_INTEGRATION_PLAN":options.output}),
    )?;
    Ok(0)
}

fn render_integration_plan(connection: &Connection, profile: &str) -> Result<String, String> {
    let operations = fetch_operations(connection)?;
    let diagnostics = fetch_diagnostics(connection)?;
    let mut lines = vec![
        "# Prose Reasoning Graph Integration Plan".into(),
        String::new(),
        format!("- profile: `{profile}`"),
        format!("- operations: `{}`", operations.len()),
        String::new(),
    ];
    if operations.is_empty() {
        lines.push("No edit operations recorded.".into());
    }
    for operation in operations {
        let targets = operation
            .target_ids
            .iter()
            .map(|target| format!("`{target}`"))
            .collect::<Vec<_>>()
            .join(", ");
        lines.extend([
            format!("## `{}`", operation.operation_id),
            String::new(),
            format!("- kind: `{}`", operation.kind),
            format!("- targets: {targets}"),
            format!("- reason: {}", operation.reason),
            format!(
                "- rewrite packet: `agent-canon prose-reasoning-graph rewrite-packet --op {}`",
                operation.operation_id
            ),
            String::new(),
        ]);
    }
    let routed = diagnostics
        .iter()
        .filter(|item| item.action.get("verification_route").is_some())
        .collect::<Vec<_>>();
    lines.extend([
        String::new(),
        "## Verification Routes".into(),
        String::new(),
    ]);
    if routed.is_empty() {
        lines.push("No verification routes recorded.".into());
    }
    for item in routed {
        let action = &item.action;
        let list = |key: &str| {
            action
                .get(key)
                .and_then(Value::as_array)
                .filter(|items| !items.is_empty())
                .map(|items| {
                    items
                        .iter()
                        .map(|value| format!("`{}`", value.as_str().unwrap_or_default()))
                        .collect::<Vec<_>>()
                        .join(", ")
                })
                .unwrap_or_else(|| "`not_recorded`".into())
        };
        let conditional = action
            .get("conditional_verification_targets")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .map(|item| {
                        format!(
                            "`{}` when {}",
                            item["target"].as_str().unwrap_or("unknown"),
                            item["when"].as_str().unwrap_or("unspecified")
                        )
                    })
                    .collect::<Vec<_>>()
                    .join("; ")
            })
            .filter(|text| !text.is_empty())
            .unwrap_or_else(|| "`not_recorded`".into());
        lines.extend([
            format!(
                "### `{}` on `{}`",
                item.rule,
                if item.target_node_id.is_empty() {
                    &item.target_edge_id
                } else {
                    &item.target_node_id
                }
            ),
            String::new(),
            format!(
                "- route: `{}`",
                action["verification_route"].as_str().unwrap_or_default()
            ),
            format!(
                "- question: {}",
                action["verification_question"].as_str().unwrap_or_default()
            ),
            format!("- targets: {}", list("verification_targets")),
            format!("- conditional_targets: {conditional}"),
            format!("- evidence_required: {}", list("evidence_required")),
        ]);
        lines.extend(format_recursive_verification(
            action.get("recursive_verification"),
        ));
        lines.push(String::new());
    }
    Ok(lines.join("\n"))
}

fn format_recursive_verification(value: Option<&Value>) -> Vec<String> {
    let Some(payload) = value.and_then(Value::as_object) else {
        return vec!["- recursive_verification: `not_recorded`".into()];
    };
    let mut lines = vec![
        format!(
            "- recursive_max_depth: `{}`",
            payload
                .get("max_depth")
                .map(scalar)
                .unwrap_or_else(|| "not_recorded".into())
        ),
        format!(
            "- closure_condition: {}",
            payload
                .get("closure_condition")
                .map(scalar)
                .unwrap_or_else(|| "not_recorded".into())
        ),
        format!(
            "- unresolved_leaf_policy: {}",
            payload
                .get("unresolved_leaf_policy")
                .map(scalar)
                .unwrap_or_else(|| "not_recorded".into())
        ),
        "- recursive_steps:".into(),
    ];
    let steps = payload
        .get("steps")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if steps.is_empty() {
        lines.push("  - `not_recorded`".into());
    }
    for step in steps {
        lines.push(format!(
            "  - `{}` route=`{}` question={} if_unresolved={}",
            step["id"].as_str().unwrap_or("step"),
            step["route"].as_str().unwrap_or("not_recorded"),
            step["question"].as_str().unwrap_or("not_recorded"),
            step["if_unresolved"].as_str().unwrap_or("not_recorded")
        ));
    }
    lines
}

fn command_rewrite_packet(options: &Options) -> Result<i32, String> {
    let path = graph_db_path(options)?;
    let connection = connect(&path)?;
    let operation_id = options.operation_id.as_deref().ok_or("--op is required")?;
    let has_table = connection
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='edit_operations'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .map_err(|error| error.to_string())?
        .is_some();
    if !has_table {
        return Err("graph DB has no edit_operations table; run analyze on an ingest DB before rewrite-packet".into());
    }
    let operation = connection
        .query_row(
            "SELECT id,kind,target_ids_json,reason,payload_json FROM edit_operations WHERE id=?1",
            params![operation_id],
            |row| {
                Ok(EditOperation {
                    operation_id: row.get(0)?,
                    kind: row.get(1)?,
                    target_ids: serde_json::from_str::<Vec<String>>(&row.get::<_, String>(2)?)
                        .unwrap_or_default(),
                    reason: row.get(3)?,
                    payload: payload_value(&row.get::<_, String>(4)?),
                })
            },
        )
        .optional()
        .map_err(|error| error.to_string())?
        .ok_or_else(|| format!("missing edit operation: {operation_id}"))?;
    let text = render_rewrite_packet(&operation);
    write_output(options.output.as_deref().ok_or("--out is required")?, &text)?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_REWRITE_PACKET",
        json!({"PROSE_REASONING_GRAPH_REWRITE_PACKET_PATH":options.output}),
    )?;
    Ok(0)
}

fn render_rewrite_packet(operation: &EditOperation) -> String {
    let targets = operation
        .target_ids
        .iter()
        .map(|target| format!("`{target}`"))
        .collect::<Vec<_>>()
        .join(", ");
    let payload = operation
        .payload
        .as_object()
        .map(|items| {
            items
                .iter()
                .map(|(key, value)| format!("- {key}: {value}"))
                .collect::<Vec<_>>()
                .join("\n")
        })
        .unwrap_or_default();
    let payload_lines = if payload.is_empty() {
        "- Follow the operation kind and target ids.".to_owned()
    } else {
        payload
    };
    let lines = vec![
        "# Prose Reasoning Graph Rewrite Packet".to_owned(),
        String::new(),
        "## Rewrite Goal".into(),
        String::new(),
        format!("Apply `{}` for {targets}.", operation.kind),
        String::new(),
        "## Reason".into(),
        String::new(),
        operation.reason.clone(),
        String::new(),
        "## Preserve".into(),
        String::new(),
        "- source provenance".into(),
        "- claim and evidence ids".into(),
        "- existing skill authority boundaries".into(),
        String::new(),
        "## Change".into(),
        String::new(),
        payload_lines,
        String::new(),
        "## Do Not".into(),
        String::new(),
        "- Do not invent new claims not present in graph nodes.".into(),
        "- Do not change diagnostic severity without reviewer approval.".into(),
        "- Do not replace the receiving skill's review responsibility.".into(),
        String::new(),
    ];
    lines.join("\n")
}

fn skill_handoffs(profile: &str, db_path: &Path) -> Value {
    let targets: &[&str] = match profile {
        "writing" => &["$long-form-writing", "$structure-planning"],
        "logic" => &["logic-gap-review", "$academic-writing"],
        "experiment" => &["$experiment-lifecycle", "$report-writing"],
        "report" => &["$report-writing", "$result-artifact-writeout"],
        "academic" => &[
            "$academic-writing",
            "logic-gap-review",
            "citation-evidence-review",
        ],
        "paper" => &[
            "$paper-writing",
            "citation-evidence-review",
            "logic-gap-review",
        ],
        _ => SKILL_HANDOFF_TARGETS,
    };
    json!(targets.iter().map(|target|json!({"target":target,"graph_db":db_path,"projection":"agent-canon prose-reasoning-graph project","diagnostics":"agent-canon prose-reasoning-graph lint","explanation":"agent-canon prose-reasoning-graph explain","rewrite_plan":"agent-canon prose-reasoning-graph integrate","projection_fields":["canonical_graph","source_anchors","selected_ordering","selected_ordering.ordered_anchor_ids","selected_ordering.ordered_anchors","projection_views","projection_views[].recommended_format","projection_views[].format_reason","corpus_hints","diagnostics","edit_operations"]})).collect::<Vec<_>>())
}

fn render_skill_handoff(profile: &str, db_path: &Path) -> Result<String, String> {
    let handoffs = skill_handoffs(profile, db_path);
    let targets = handoffs.as_array().cloned().unwrap_or_default();
    let connection = connect(db_path)?;
    let diagnostics = fetch_diagnostics(&connection)?;
    let mut lines = vec![
        "# Prose Reasoning Graph Skill Handoff".to_owned(),
        String::new(),
        format!("- profile: `{profile}`"),
        format!("- prose_graph_db: `{}`", db_path.display()),
        String::new(),
        "## Targets".into(),
        String::new(),
    ];
    for item in targets {
        let fields = item["projection_fields"]
            .as_array()
            .map(|values| {
                values
                    .iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join(", ")
            })
            .unwrap_or_default();
        lines.extend([
            format!("### {}", item["target"].as_str().unwrap_or_default()),
            String::new(),
            format!(
                "- prose_graph_db: {}",
                item["graph_db"].as_str().unwrap_or_default()
            ),
            format!(
                "- prose_graph_projection: {}",
                item["projection"].as_str().unwrap_or_default()
            ),
            format!(
                "- prose_graph_diagnostics: {}",
                item["diagnostics"].as_str().unwrap_or_default()
            ),
            format!(
                "- prose_graph_explanation: {}",
                item["explanation"].as_str().unwrap_or_default()
            ),
            format!(
                "- prose_graph_rewrite_plan: {}",
                item["rewrite_plan"].as_str().unwrap_or_default()
            ),
            format!("- projection_fields: `{fields}`"),
            String::new(),
        ]);
    }
    lines.extend(render_verification_routes(&diagnostics));
    lines.extend(["## Authority Boundary".into(),String::new(),"This handoff gives graph-derived evidence to existing skills and reviewers. It does not replace their review gates or source-packet responsibilities.".into(),String::new()]);
    Ok(lines.join("\n"))
}

fn render_verification_routes(diagnostics: &[Diagnostic]) -> Vec<String> {
    let routed = diagnostics
        .iter()
        .filter(|item| item.action.get("verification_route").is_some())
        .collect::<Vec<_>>();
    let mut lines = vec![
        String::new(),
        "## Verification Routes".into(),
        String::new(),
    ];
    if routed.is_empty() {
        lines.push("No verification routes recorded.".into());
        return lines;
    }
    let list = |value: Option<&Value>| {
        value
            .and_then(Value::as_array)
            .filter(|items| !items.is_empty())
            .map(|items| {
                items
                    .iter()
                    .map(|item| format!("`{}`", item.as_str().unwrap_or_default()))
                    .collect::<Vec<_>>()
                    .join(", ")
            })
            .unwrap_or_else(|| "`not_recorded`".into())
    };
    for diagnostic in routed {
        let action = &diagnostic.action;
        let target = if diagnostic.target_node_id.is_empty() {
            &diagnostic.target_edge_id
        } else {
            &diagnostic.target_node_id
        };
        lines.extend([
            format!("### `{}` on `{target}`", diagnostic.rule),
            String::new(),
            format!(
                "- route: `{}`",
                action["verification_route"].as_str().unwrap_or_default()
            ),
            format!(
                "- question: {}",
                action["verification_question"].as_str().unwrap_or_default()
            ),
            format!("- targets: {}", list(action.get("verification_targets"))),
        ]);
        let conditional = action
            .get("conditional_verification_targets")
            .and_then(Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .map(|item| {
                        format!(
                            "`{}` when {}",
                            item["target"].as_str().unwrap_or("unknown"),
                            item["when"].as_str().unwrap_or("unspecified")
                        )
                    })
                    .collect::<Vec<_>>()
                    .join("; ")
            })
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "`not_recorded`".into());
        lines.push(format!("- conditional_targets: {conditional}"));
        lines.push(format!(
            "- evidence_required: {}",
            list(action.get("evidence_required"))
        ));
        lines.extend(format_recursive_verification(
            action.get("recursive_verification"),
        ));
        lines.push(String::new());
    }
    lines
}

fn command_skill_handoff(options: &Options) -> Result<i32, String> {
    let db_path = graph_db_path(options)?;
    let text = render_skill_handoff(&options.profile, &db_path)?;
    write_output(options.output.as_deref().ok_or("--out is required")?, &text)?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_SKILL_HANDOFF",
        json!({"PROSE_REASONING_GRAPH_SKILL_HANDOFF_PATH":options.output}),
    )?;
    Ok(0)
}

fn target_path_candidates(input: &Path, repo_root: &Path) -> BTreeSet<String> {
    let mut candidates = BTreeSet::new();
    candidates.insert(input.to_string_lossy().replace('\\', "/"));
    if let Some(name) = input.file_name() {
        candidates.insert(name.to_string_lossy().into_owned());
    }
    if let Ok(resolved) = input.canonicalize() {
        candidates.insert(resolved.to_string_lossy().replace('\\', "/"));
        if let Ok(relative) = resolved.strip_prefix(repo_root) {
            candidates.insert(relative.to_string_lossy().replace('\\', "/"));
        }
        if let Ok(cwd) = std::env::current_dir() {
            if let Ok(relative) = resolved.strip_prefix(cwd) {
                candidates.insert(relative.to_string_lossy().replace('\\', "/"));
            }
        }
    }
    candidates.remove("");
    candidates
}

fn string_field(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

fn document_canon_action(
    kind: &str,
    action: &str,
    path: &str,
    canonical_path: &str,
    reason: &str,
) -> Value {
    if kind == "document_responsibility_gap" {
        return json!({"action":action,"path":path,"canonical_path":canonical_path,"reason":reason,"verification_route":"document_responsibility_verification","verification_question":"Does the downstream document cover the upstream design responsibility declared by its dependency manifest?","verification_targets":[path,canonical_path],"evidence_required":["upstream coverage rule","downstream document wording","dependency header edge"],"recursive_verification":{"max_depth":3,"closure_condition":"every declared coverage group is covered, explicitly out of scope, or recorded as an unresolved document-canon finding","unresolved_leaf_policy":"keep document_responsibility_gap active and route the leaf to the owning document","steps":[{"id":"expand_coverage_rule","route":"document-canon","question":"Which upstream coverage groups are missing from the downstream document?","if_unresolved":"preserve the responsibility gap finding"},{"id":"trace_downstream_claim","route":"prose-reasoning-graph","question":"Which downstream paragraph, sentence, or graph node should carry the missing responsibility?","if_unresolved":"create a child document-canon finding for the target document"},{"id":"verify_rewritten_contract","route":"structured-analysis","question":"Does rerunning structured-analysis close the coverage gap without introducing a new graph or document responsibility gap?","if_unresolved":"record the remaining gap as blocker or warn"}]}});
    }
    json!({"action":action,"path":path,"canonical_path":canonical_path,"reason":reason})
}

fn import_target_document_canon_findings(
    connection: &Connection,
    inventory_path: &Path,
    repo_root: &Path,
    input_path: &Path,
) -> Result<Vec<Value>, String> {
    let payload: Value =
        serde_json::from_slice(&fs::read(inventory_path).map_err(|error| error.to_string())?)
            .map_err(|error| error.to_string())?;
    let documents = payload
        .get("documents")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let all_findings = payload
        .get("findings")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let candidates = target_path_candidates(input_path, repo_root);
    let findings = all_findings
        .into_iter()
        .filter(|finding| {
            candidates.contains(&string_field(finding, "path"))
                || candidates.contains(&string_field(finding, "canonical_path"))
        })
        .collect::<Vec<_>>();
    connection
        .execute("DELETE FROM diagnostics WHERE layer='document-canon'", [])
        .map_err(|error| error.to_string())?;
    connection
        .execute("DELETE FROM edges WHERE layer='document-canon'", [])
        .map_err(|error| error.to_string())?;
    connection
        .execute("DELETE FROM nodes WHERE layer='document-canon'", [])
        .map_err(|error| error.to_string())?;
    let document_id = fetch_document_id(connection)?;
    let mut paths = BTreeSet::new();
    for finding in &findings {
        for field in ["path", "canonical_path"] {
            let value = string_field(finding, field);
            if !value.is_empty() {
                paths.insert(value);
            }
        }
    }
    for doc in &documents {
        let path = string_field(doc, "path");
        if candidates.contains(&path) && !path.is_empty() {
            paths.insert(path);
        }
    }
    let mut records = documents
        .iter()
        .filter(|doc| paths.contains(&string_field(doc, "path")))
        .cloned()
        .collect::<Vec<_>>();
    let seen = records
        .iter()
        .map(|record| string_field(record, "path"))
        .collect::<BTreeSet<_>>();
    for path in paths.difference(&seen) {
        records.push(
            json!({"path":path,"title":path,"responsibility":path,"has_dependency_manifest":false}),
        );
    }
    let mut path_to_node = BTreeMap::new();
    for (index, record) in records.iter().enumerate() {
        let path = string_field(record, "path");
        let title = if string_field(record, "title").is_empty() {
            path.clone()
        } else {
            string_field(record, "title")
        };
        let responsibility = if string_field(record, "responsibility").is_empty() {
            path.clone()
        } else {
            string_field(record, "responsibility")
        };
        let id = format!("doccanon:document:{}", index + 1);
        add_analysis_node(
            connection,
            &id,
            &document_id,
            "document-canon",
            "document_record",
            &title,
            &responsibility,
            0,
            0,
            1.0,
            json!({"path":path,"title":title,"responsibility":responsibility,"has_dependency_manifest":record.get("has_dependency_manifest").and_then(Value::as_bool).unwrap_or(false),"inventory_path":inventory_path}),
        )?;
        path_to_node.insert(path, id);
    }
    for (index, finding) in findings.iter().enumerate() {
        let path = string_field(finding, "path");
        let kind = string_field(finding, "kind");
        let canonical = string_field(finding, "canonical_path");
        let action = string_field(finding, "action");
        let reason = string_field(finding, "reason");
        let id = format!("doccanon:finding:{}", index + 1);
        let message = format!("{kind}: `{path}` -> `{canonical}`. {reason}");
        add_analysis_node(
            connection,
            &id,
            &document_id,
            "document-canon",
            "finding",
            &kind,
            &message,
            0,
            0,
            DOCUMENT_CANON_FINDING_CONFIDENCE,
            json!({"path":path,"kind":kind,"canonical_path":canonical,"action":action,"reason":reason,"inventory_path":inventory_path}),
        )?;
        if let Some(target) = path_to_node.get(&path) {
            add_analysis_edge(
                connection,
                &format!("doccanon:target:{}", index + 1),
                "document-canon",
                "targets_document",
                &id,
                target,
                "",
                1.0,
                json!({"path":path}),
            )?;
        }
        if let Some(target) = path_to_node.get(&canonical) {
            add_analysis_edge(
                connection,
                &format!("doccanon:canonical:{}", index + 1),
                "document-canon",
                "references_canonical",
                &id,
                target,
                "",
                1.0,
                json!({"canonical_path":canonical}),
            )?;
        }
        insert_diagnostic(
            connection,
            &Diagnostic {
                diagnostic_id: format!("diag:document-canon:{}", index + 1),
                layer: "document-canon".into(),
                severity: document_canon_severity(&kind).into(),
                rule: kind.clone(),
                message,
                target_node_id: id,
                target_edge_id: String::new(),
                action: document_canon_action(&kind, &action, &path, &canonical, &reason),
            },
        )?;
    }
    set_metadata(
        connection,
        "document_canon_inventory",
        &json!({"inventory_path":inventory_path,"repo_root":repo_root,"target_candidates":candidates,"document_count":paths.len(),"finding_count":findings.len()}),
    )?;
    Ok(findings)
}

fn run_structured_analysis_build(repo_root: &Path, profile: &str) -> Result<PathBuf, String> {
    let selected = std::env::var("AGENT_CANON_CLI")
        .ok()
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| repo_root.join("tools/bin/agent-canon"));
    let output = Command::new(selected)
        .args(["structured-analysis", "build", "--root"])
        .arg(repo_root)
        .args(["--profile", profile])
        .current_dir(repo_root)
        .output()
        .map_err(|error| error.to_string())?;
    if !output.status.success() {
        return Err(format!(
            "structured-analysis build failed: exit={}\nstdout={}\nstderr={}",
            output.status.code().unwrap_or(2),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let key = format!("{STRUCTURED_ANALYSIS_INVENTORY_STDOUT_KEY}=");
    let path = stdout
        .lines()
        .find_map(|line| line.strip_prefix(&key).map(str::trim))
        .filter(|value| !value.is_empty())
        .ok_or(
            "structured-analysis build did not emit STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY_JSON",
        )?;
    let path = PathBuf::from(path);
    if !path.is_file() {
        return Err(format!(
            "structured-analysis inventory JSON was not created: {}",
            path.display()
        ));
    }
    Ok(path)
}

#[allow(clippy::too_many_arguments)]
fn render_document_check_report(
    input: &Path,
    root: &Path,
    db: &Path,
    profile: &str,
    inventory: &Path,
    diagnostics: &Path,
    explanation: &Path,
    integration: &Path,
    handoff: &Path,
    prose_count: usize,
    operation_count: usize,
    findings: &[Value],
) -> String {
    let mut lines=vec!["# Prose Reasoning Graph Document Check".into(),String::new(),format!("- target: `{}`",input.display()),format!("- structured_root: `{}`",root.display()),format!("- profile: `{profile}`"),format!("- prose_graph_db: `{}`",db.display()),format!("- structured_inventory: `{}`",inventory.display()),format!("- prose diagnostics: `{prose_count}`"),format!("- edit operations: `{operation_count}`"),format!("- document-canon findings: `{}`",findings.len()),String::new(),"## Tool Path".into(),String::new(),"This command runs the prose graph path and the Rust structured-analysis document-canon path for the same target before writing result artifacts.".into(),String::new(),"## Artifacts".into(),String::new(),format!("- diagnostics: `{}`",diagnostics.display()),format!("- explanation: `{}`",explanation.display()),format!("- integration plan: `{}`",integration.display()),format!("- skill handoff: `{}`",handoff.display()),String::new(),"## Document-Canon Findings".into(),String::new()];
    if findings.is_empty() {
        lines.push("No target document-canon findings were recorded.".into());
    } else {
        for finding in findings {
            lines.push(format!(
                "- `{}` path=`{}` canonical=`{}` action=`{}`: {}",
                string_field(finding, "kind"),
                string_field(finding, "path"),
                string_field(finding, "canonical_path"),
                string_field(finding, "action"),
                string_field(finding, "reason")
            ));
        }
    }
    lines.extend([String::new(),"## Next Route".into(),String::new(),"Use the diagnostics and integration artifacts first. For a selected graph analysis, if a diagnostic carries a verification route, verify and rerun this command to update that analysis; the route does not gate ordinary writing.".into(),String::new()]);
    lines.join("\n")
}

fn command_check_document(options: &Options) -> Result<i32, String> {
    let input = options
        .inputs
        .first()
        .ok_or("check-document requires one input document")?
        .clone();
    let db = graph_db_path(options)?;
    let out_dir = runtime_resolve(
        options.out_dir.as_deref().ok_or("--out-dir is required")?,
        "prose-reasoning-graph-output",
    )?;
    let boundary = runtime_boundary(true)?;
    let relative = out_dir
        .strip_prefix(boundary.root())
        .map_err(|_| "output directory escapes runtime root")?;
    if !relative.as_os_str().is_empty() {
        boundary.ensure_directory(relative)?;
    }
    let repo_root = structured_repo_root(options, &input)?;
    let inventory = if let Some(path) = options.structured_inventory_json.as_ref() {
        if !path.is_file() {
            return Err(format!(
                "structured inventory JSON does not exist: {}",
                path.display()
            ));
        }
        path.clone()
    } else {
        run_structured_analysis_build(&repo_root, &options.structured_profile)?
    };
    let prompt = prompt_context(options)?;
    let source = fs::read_to_string(&input).map_err(|error| error.to_string())?;
    let docs = vec![(input.clone(), source.clone())];
    let (dependencies, fingerprint) = graph_dependency_records_for_inputs(&repo_root, &docs)?;
    let semantic = semantic_prose_ir_payload(&docs, &prompt, &db)?;
    let hints = corpus_hints_from_semantic_ir(&semantic);
    let diagnostics_path = out_dir.join("prose_diagnostics.md");
    let explanation_path = out_dir.join("prose_explanation.md");
    let integration_path = out_dir.join("prose_integration.md");
    let handoff_path = out_dir.join("prose_handoff.md");
    let report_path = out_dir.join("document_check.md");
    let connection = connect(&db)?;
    initialize_schema(&connection)?;
    clear_database(&connection)?;
    set_metadata(&connection, "semantic_prose_ir", &semantic)?;
    set_metadata(&connection, "corpus_hints", &json!(hints))?;
    set_metadata(
        &connection,
        "canonical_graph_fingerprint",
        &json!(fingerprint),
    )?;
    set_metadata(
        &connection,
        "corpus_hint_inputs",
        &json!({"source":"semantic_prose_ir","document_path":input,"prompt_supplied":!prompt.trim().is_empty(),"ir_schema":semantic["schema"]}),
    )?;
    let key = graph_source_path(&repo_root, &input)?;
    ingest_document(
        &connection,
        &input,
        &source,
        "doc:1",
        "src:1",
        &options.kind,
        "",
        dependencies.get(&key).map(Vec::as_slice).unwrap_or(&[]),
    )?;
    clear_analysis(&connection)?;
    analyze_graph(&connection, &options.profile)?;
    let findings =
        import_target_document_canon_findings(&connection, &inventory, &repo_root, &input)?;
    let all_diagnostics = fetch_diagnostics(&connection)?;
    let prose_diagnostics = all_diagnostics
        .iter()
        .filter(|item| item.layer != "document-canon")
        .count();
    let operations = fetch_operations(&connection)?;
    let diagnostics_markdown = render_diagnostics(&connection, &options.profile)?;
    let explanation_markdown = render_explanation(&connection, &options.profile, &db)?;
    let integration_markdown = render_integration_plan(&connection, &options.profile)?;
    drop(connection);
    write_output(&diagnostics_path, &diagnostics_markdown)?;
    write_output(&explanation_path, &explanation_markdown)?;
    write_output(&integration_path, &integration_markdown)?;
    write_output(&handoff_path, &render_skill_handoff(&options.profile, &db)?)?;
    let report = render_document_check_report(
        &input,
        &repo_root,
        &db,
        &options.profile,
        &inventory,
        &diagnostics_path,
        &explanation_path,
        &integration_path,
        &handoff_path,
        prose_diagnostics,
        operations.len(),
        &findings,
    );
    write_output(&report_path, &report)?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_CHECK_DOCUMENT",
        json!({"PROSE_REASONING_GRAPH_DB":db,"PROSE_REASONING_GRAPH_DOCUMENT_CHECK":report_path,"PROSE_REASONING_GRAPH_DIAGNOSTICS":diagnostics_path,"PROSE_REASONING_GRAPH_EXPLANATION":explanation_path,"PROSE_REASONING_GRAPH_INTEGRATION_PLAN":integration_path,"PROSE_REASONING_GRAPH_SKILL_HANDOFF":handoff_path,"PROSE_REASONING_GRAPH_STRUCTURED_ANALYSIS_INVENTORY":inventory,"PROSE_REASONING_GRAPH_SEMANTIC_IR":semantic["artifact_path"],"PROSE_REASONING_GRAPH_PROSE_DIAGNOSTICS":prose_diagnostics,"PROSE_REASONING_GRAPH_EDIT_OPERATIONS":operations.len(),"PROSE_REASONING_GRAPH_DOCUMENT_CANON_FINDINGS":findings.len()}),
    )?;
    Ok(0)
}

pub fn run(args: &[String]) -> i32 {
    let options = match parse_options(args) {
        Ok(Some(options)) => options,
        Ok(None) => {
            println!("{}", usage());
            return 0;
        }
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let result = match options.command.as_str() {
        "ingest" => command_ingest(&options),
        "ingest-set" => command_ingest_set(&options),
        "analyze" => command_analyze(&options),
        "lint" => command_lint(&options),
        "project" => command_project(&options),
        "outline" => command_outline(&options),
        "explain" => command_explain(&options),
        "integrate" => command_integrate(&options),
        "rewrite-packet" => command_rewrite_packet(&options),
        "skill-handoff" => command_skill_handoff(&options),
        "check-document" => command_check_document(&options),
        _ => Err(format!("invalid choice: {:?}", options.command)),
    };
    match result {
        Ok(code) => code,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sentence(id: &str, start: usize) -> Node {
        Node {
            node_id: id.into(),
            document_id: "doc".into(),
            layer: "form".into(),
            kind: "sentence".into(),
            label: id.into(),
            text: format!("{id}."),
            payload: json!({}),
            source_start: start,
            source_end: start + 1,
        }
    }

    #[test]
    fn document_canon_severity_preserves_the_existing_mapping() {
        assert_eq!(
            document_canon_severity("missing_dependency_manifest"),
            "info"
        );
        assert_eq!(
            document_canon_severity("broken_dependency_target"),
            "blocker"
        );
    }

    #[test]
    fn selected_ordering_hard_edges_override_source_order() {
        let anchors = vec![
            sentence("s:later", 10),
            sentence("s:earlier", 0),
            sentence("s:tail", 21),
        ];
        let edges = vec![
            json!({"edge_id":"edge:explicit-order","from_node_id":"s:later","to_node_id":"s:earlier","order_kind":"hard_before"}),
        ];
        let (ordered, cycle, relaxed) =
            priority_topological_order(&anchors, &edges, "report", &BTreeMap::new());
        assert_eq!(
            ordered,
            vec![
                "s:later".to_owned(),
                "s:earlier".to_owned(),
                "s:tail".to_owned()
            ]
        );
        assert!(!cycle);
        assert!(relaxed.is_empty());
    }

    #[test]
    fn selected_ordering_soft_edges_are_priorities_not_constraints() {
        let anchors = vec![sentence("s:earlier", 0), sentence("s:later", 10)];
        let edges = vec![
            json!({"edge_id":"soft-a-b","from_node_id":"s:earlier","to_node_id":"s:later","order_kind":"adjacency_preferred","confidence":0.8}),
            json!({"edge_id":"soft-b-a","from_node_id":"s:later","to_node_id":"s:earlier","order_kind":"adjacency_preferred","confidence":0.8}),
        ];
        let (ordered, cycle, relaxed) =
            priority_topological_order(&anchors, &edges, "report", &BTreeMap::new());
        assert_eq!(ordered, vec!["s:earlier".to_owned(), "s:later".to_owned()]);
        assert!(!cycle);
        assert!(relaxed.is_empty());
    }

    #[test]
    fn soft_edge_can_override_source_order_tie_break() {
        let anchors = vec![sentence("s:later", 10), sentence("s:earlier", 0)];
        let edges = vec![
            json!({"edge_id":"soft-later-earlier","from_node_id":"s:later","to_node_id":"s:earlier","order_kind":"adjacency_preferred","confidence":0.9}),
        ];
        let (ordered, cycle, relaxed) =
            priority_topological_order(&anchors, &edges, "report", &BTreeMap::new());
        assert!(
            ordered.iter().position(|id| id == "s:later").unwrap()
                < ordered.iter().position(|id| id == "s:earlier").unwrap()
        );
        assert!(!cycle);
        assert!(relaxed.is_empty());
    }

    #[test]
    fn cycle_relaxation_preserves_hard_edges_between_components() {
        let anchors = vec![sentence("s:a", 0), sentence("s:c", 11), sentence("s:b", 21)];
        let edges = vec![
            json!({"edge_id":"edge:a-b","from_node_id":"s:a","to_node_id":"s:b","order_kind":"hard_before"}),
            json!({"edge_id":"edge:b-a","from_node_id":"s:b","to_node_id":"s:a","order_kind":"hard_before"}),
            json!({"edge_id":"edge:b-c","from_node_id":"s:b","to_node_id":"s:c","order_kind":"hard_before"}),
        ];
        let (ordered, cycle, relaxed) =
            priority_topological_order(&anchors, &edges, "report", &BTreeMap::new());
        assert!(cycle);
        assert!(
            ordered.iter().position(|id| id == "s:b").unwrap()
                < ordered.iter().position(|id| id == "s:c").unwrap()
        );
        assert_eq!(
            relaxed
                .iter()
                .map(|edge| edge["edge_id"].as_str().unwrap())
                .collect::<BTreeSet<_>>(),
            BTreeSet::from(["edge:a-b", "edge:b-a"])
        );
    }

    #[test]
    fn hard_order_cycle_is_recorded_as_a_projection_diagnostic() {
        let connection = Connection::open_in_memory().unwrap();
        initialize_schema(&connection).unwrap();
        connection.execute("INSERT INTO documents(id,path,title,kind,created_at) VALUES ('doc','cycle.md','Cycle','document','2026-06-08T00:00:00Z')",[]).unwrap();
        for (id, start) in [("s:a", 0usize), ("s:b", 11usize)] {
            insert_node(
                &connection,
                &Node {
                    node_id: id.into(),
                    document_id: "doc".into(),
                    layer: "form".into(),
                    kind: "sentence".into(),
                    label: id.into(),
                    text: format!("Sentence {id}."),
                    payload: json!({"span_kind":"sentence"}),
                    source_start: start,
                    source_end: start + 10,
                },
                1.0,
            )
            .unwrap();
        }
        for (id, from, to) in [("edge:a-b", "s:a", "s:b"), ("edge:b-a", "s:b", "s:a")] {
            insert_edge(
                &connection,
                &Edge {
                    edge_id: id.into(),
                    layer: "presentation".into(),
                    kind: "precedes".into(),
                    from_node_id: from.into(),
                    to_node_id: to.into(),
                    order_kind: "hard_before".into(),
                    confidence: 1.0,
                    payload: json!({}),
                },
            )
            .unwrap();
        }
        add_selected_ordering_cycle_diagnostic(&connection, "report").unwrap();
        let diagnostic = fetch_diagnostics(&connection)
            .unwrap()
            .into_iter()
            .find(|item| item.rule == "selected_ordering_cycle")
            .unwrap();
        assert_eq!(diagnostic.layer, "projection");
        assert_eq!(
            diagnostic.action["verification_route"],
            "ordering_cycle_verification"
        );
    }
}

fn add_selected_ordering_cycle_diagnostic(
    connection: &Connection,
    profile: &str,
) -> Result<(), String> {
    let sentences = fetch_nodes(connection, Some("form"), Some("sentence"))?;
    if sentences.is_empty() {
        return Ok(());
    }
    let edges = selected_ordering_edges(connection, &sentences)?;
    let phases = phase_by_sentence_anchor(connection, &sentences)?;
    let (_ordered, cycle, relaxed) =
        priority_topological_order(&sentences, &edges, profile, &phases);
    if !cycle {
        return Ok(());
    }
    let first = relaxed.first().cloned().unwrap_or_else(|| json!({}));
    let target = first["from_node_id"]
        .as_str()
        .unwrap_or(&sentences[0].node_id);
    let edge = first["edge_id"].as_str().unwrap_or_default();
    insert_diagnostic(connection,&Diagnostic{diagnostic_id:"diag:selected-ordering-cycle".into(),layer:"projection".into(),severity:"warn".into(),rule:"selected_ordering_cycle".into(),message:"Selected ordering hard constraints contain a cycle; projection relaxed cyclic hard edges.".into(),target_node_id:target.into(),target_edge_id:edge.into(),action:verification_action_for_rule("selected_ordering_cycle")})
}

#[derive(Clone, Copy, Debug, Default)]
struct SoftOrderingPriority {
    incoming_count: usize,
    outgoing_count: usize,
    incoming_confidence: f64,
    outgoing_confidence: f64,
}

fn edge_participates_in_ordering(edge: &Edge) -> bool {
    matches!(
        edge.order_kind.as_str(),
        "hard_before" | "adjacency_preferred"
    ) || edge
        .payload
        .get("participates_in_ordering_dag")
        .and_then(Value::as_bool)
        .unwrap_or(false)
}

fn ordering_constraint_strength(order_kind: &str) -> &'static str {
    match order_kind {
        "hard_before" => "hard",
        "adjacency_preferred" => "soft",
        "source_order_tie_break" => "tie_breaker",
        _ => "selected",
    }
}

fn ordering_edge_record(edge: &Edge, basis: &str) -> Value {
    json!({"edge_id":edge.edge_id,"from_node_id":edge.from_node_id,"to_node_id":edge.to_node_id,"layer":edge.layer,"kind":edge.kind,"order_kind":if edge.order_kind.is_empty(){"selected_order"}else{&edge.order_kind},"constraint_strength":ordering_constraint_strength(&edge.order_kind),"confidence":edge.confidence,"basis":basis})
}

fn selected_ordering_edges(
    connection: &Connection,
    anchors: &[Node],
) -> Result<Vec<Value>, String> {
    let ids = anchors
        .iter()
        .map(|node| node.node_id.as_str())
        .collect::<BTreeSet<_>>();
    let edges = fetch_edges(connection)?;
    let mut output = edges
        .iter()
        .filter(|edge| {
            ids.contains(edge.from_node_id.as_str())
                && ids.contains(edge.to_node_id.as_str())
                && edge_participates_in_ordering(edge)
        })
        .map(|edge| ordering_edge_record(edge, "direct"))
        .collect::<Vec<_>>();
    let mut by_paragraph = BTreeMap::<String, Vec<&Node>>::new();
    for anchor in anchors {
        if let Some(paragraph) = anchor.payload.get("paragraph_id").and_then(Value::as_str) {
            by_paragraph
                .entry(paragraph.into())
                .or_default()
                .push(anchor);
        }
    }
    for (paragraph, mut nodes) in by_paragraph {
        nodes.sort_by(|left, right| source_anchor_cmp(left, right));
        for (index, pair) in nodes.windows(2).enumerate() {
            output.push(json!({"edge_id":format!("derived-sentence-order:{paragraph}:{}",index+1),"from_node_id":pair[0].node_id,"to_node_id":pair[1].node_id,"layer":"form","kind":"contains_order","order_kind":"hard_before","constraint_strength":"hard","confidence":DEFAULT_ORDERING_CONFIDENCE,"basis":"paragraph_sentence_sequence"}));
        }
        let _ = paragraph;
    }
    let mut paragraph_to_sentences = BTreeMap::<String, Vec<&Node>>::new();
    for anchor in anchors {
        if let Some(paragraph) = anchor.payload.get("paragraph_id").and_then(Value::as_str) {
            paragraph_to_sentences
                .entry(paragraph.into())
                .or_default()
                .push(anchor);
        }
    }
    for values in paragraph_to_sentences.values_mut() {
        values.sort_by(|left, right| source_anchor_cmp(left, right));
    }
    for edge in edges
        .iter()
        .filter(|edge| edge_participates_in_ordering(edge))
    {
        let (Some(from), Some(to)) = (
            paragraph_to_sentences.get(&edge.from_node_id),
            paragraph_to_sentences.get(&edge.to_node_id),
        ) else {
            continue;
        };
        output.push(json!({"edge_id":format!("derived-paragraph-order:{}",edge.edge_id),"from_node_id":from.last().map(|node|&node.node_id),"to_node_id":to.first().map(|node|&node.node_id),"layer":edge.layer,"kind":edge.kind,"order_kind":if edge.order_kind.is_empty(){"selected_order"}else{&edge.order_kind},"constraint_strength":ordering_constraint_strength(&edge.order_kind),"confidence":edge.confidence,"basis":format!("paragraph_order_edge:{}",edge.edge_id)}));
    }
    if output.is_empty() {
        let mut ordered = anchors.to_vec();
        ordered.sort_by(source_anchor_cmp);
        for (index, pair) in ordered.windows(2).enumerate() {
            output.push(json!({"edge_id":format!("fallback-source-order:{}",index+1),"from_node_id":pair[0].node_id,"to_node_id":pair[1].node_id,"layer":"projection","kind":"source_order_tie_break","order_kind":"source_order_tie_break","constraint_strength":"tie_breaker","confidence":DEFAULT_ORDERING_CONFIDENCE,"basis":"source_order_final_tie_breaker"}));
        }
    }
    output.sort_by_key(|edge| edge["edge_id"].as_str().unwrap_or_default().to_owned());
    Ok(output)
}

fn source_anchor_cmp(left: &Node, right: &Node) -> Ordering {
    (
        &left.document_id,
        left.source_start,
        left.source_end,
        &left.node_id,
    )
        .cmp(&(
            &right.document_id,
            right.source_start,
            right.source_end,
            &right.node_id,
        ))
}

fn phase_priority(phase: &str, profile: &str) -> usize {
    if !matches!(profile, "writing" | "report" | "academic" | "paper" | "all") {
        return PHASE_ORDER.len();
    }
    PHASE_ORDER
        .iter()
        .position(|candidate| *candidate == phase)
        .unwrap_or(PHASE_ORDER.len())
}

fn soft_ordering_priorities(
    edges: &[Value],
    anchors: &[Node],
) -> BTreeMap<String, SoftOrderingPriority> {
    let ids = anchors
        .iter()
        .map(|node| node.node_id.as_str())
        .collect::<BTreeSet<_>>();
    let mut values = BTreeMap::<String, SoftOrderingPriority>::new();
    for edge in edges {
        if edge["order_kind"].as_str() != Some("adjacency_preferred") {
            continue;
        }
        let (Some(from), Some(to)) = (edge["from_node_id"].as_str(), edge["to_node_id"].as_str())
        else {
            continue;
        };
        if !ids.contains(from) || !ids.contains(to) {
            continue;
        }
        let confidence = edge["confidence"]
            .as_f64()
            .or_else(|| edge["confidence"].as_u64().map(|value| value as f64))
            .unwrap_or(NO_ORDERING_CONFIDENCE);
        let outgoing = values.entry(from.into()).or_default();
        outgoing.outgoing_count += 1;
        outgoing.outgoing_confidence += confidence;
        let incoming = values.entry(to.into()).or_default();
        incoming.incoming_count += 1;
        incoming.incoming_confidence += confidence;
    }
    values
}

fn compare_anchor_priority(
    left: &Node,
    right: &Node,
    profile: &str,
    phases: &BTreeMap<String, String>,
    soft: &BTreeMap<String, SoftOrderingPriority>,
) -> Ordering {
    let default = SoftOrderingPriority::default();
    let left_soft = soft.get(&left.node_id).unwrap_or(&default);
    let right_soft = soft.get(&right.node_id).unwrap_or(&default);
    (
        phase_priority(
            phases.get(&left.node_id).map(String::as_str).unwrap_or(""),
            profile,
        ),
        left_soft.incoming_count,
        Reverse(left_soft.outgoing_count),
    )
        .cmp(&(
            phase_priority(
                phases.get(&right.node_id).map(String::as_str).unwrap_or(""),
                profile,
            ),
            right_soft.incoming_count,
            Reverse(right_soft.outgoing_count),
        ))
        .then_with(|| {
            left_soft
                .incoming_confidence
                .total_cmp(&right_soft.incoming_confidence)
        })
        .then_with(|| {
            right_soft
                .outgoing_confidence
                .total_cmp(&left_soft.outgoing_confidence)
        })
        .then_with(|| source_anchor_cmp(left, right))
}

fn ordering_is_hard(edge: &Value) -> bool {
    edge["order_kind"].as_str() == Some("hard_before")
}

fn strongly_connected_components(
    node_ids: &BTreeSet<String>,
    edges: &[Value],
) -> Vec<BTreeSet<String>> {
    let mut adjacency = node_ids
        .iter()
        .map(|id| (id.clone(), BTreeSet::<String>::new()))
        .collect::<BTreeMap<_, _>>();
    let mut reverse = adjacency.clone();
    for edge in edges {
        let (Some(from), Some(to)) = (edge["from_node_id"].as_str(), edge["to_node_id"].as_str())
        else {
            continue;
        };
        if node_ids.contains(from) && node_ids.contains(to) {
            adjacency.entry(from.into()).or_default().insert(to.into());
            reverse.entry(to.into()).or_default().insert(from.into());
        }
    }
    let mut visited = BTreeSet::new();
    let mut finished = Vec::new();
    for start in node_ids {
        if !visited.insert(start.clone()) {
            continue;
        }
        let mut stack = vec![(start.clone(), 0usize)];
        while let Some((node, index)) = stack.last_mut() {
            let neighbors = adjacency
                .get(node)
                .map(|values| values.iter().cloned().collect::<Vec<_>>())
                .unwrap_or_default();
            if *index < neighbors.len() {
                let next = neighbors[*index].clone();
                *index += 1;
                if visited.insert(next.clone()) {
                    stack.push((next, 0));
                }
            } else {
                finished.push(node.clone());
                stack.pop();
            }
        }
    }
    visited.clear();
    let mut components = Vec::new();
    for start in finished.into_iter().rev() {
        if !visited.insert(start.clone()) {
            continue;
        }
        let mut component = BTreeSet::new();
        let mut stack = vec![start];
        while let Some(node) = stack.pop() {
            component.insert(node.clone());
            for next in reverse.get(&node).into_iter().flatten() {
                if visited.insert(next.clone()) {
                    stack.push(next.clone());
                }
            }
        }
        components.push(component);
    }
    components.sort_by(|left, right| left.iter().next().cmp(&right.iter().next()));
    components
}

fn priority_topological_order(
    anchors: &[Node],
    edges: &[Value],
    profile: &str,
    phases: &BTreeMap<String, String>,
) -> (Vec<String>, bool, Vec<Value>) {
    let node_by_id = anchors
        .iter()
        .map(|node| (node.node_id.clone(), node))
        .collect::<BTreeMap<_, _>>();
    let hard = edges
        .iter()
        .filter(|edge| ordering_is_hard(edge))
        .cloned()
        .collect::<Vec<_>>();
    let soft = soft_ordering_priorities(edges, anchors);
    let mut adjacency = node_by_id
        .keys()
        .map(|id| (id.clone(), BTreeSet::<String>::new()))
        .collect::<BTreeMap<_, _>>();
    let mut indegree = node_by_id
        .keys()
        .map(|id| (id.clone(), 0usize))
        .collect::<BTreeMap<_, _>>();
    let mut pairs = BTreeSet::new();
    for edge in &hard {
        let (Some(from), Some(to)) = (edge["from_node_id"].as_str(), edge["to_node_id"].as_str())
        else {
            continue;
        };
        if !node_by_id.contains_key(from)
            || !node_by_id.contains_key(to)
            || !pairs.insert((from.to_owned(), to.to_owned()))
        {
            continue;
        }
        adjacency
            .get_mut(from)
            .expect("node present")
            .insert(to.into());
        *indegree.get_mut(to).expect("node present") += 1;
    }
    let mut ordered = Vec::new();
    loop {
        let mut ready = indegree
            .iter()
            .filter(|(_, degree)| **degree == 0)
            .map(|(id, _)| id.clone())
            .filter(|id| !ordered.contains(id))
            .collect::<Vec<_>>();
        if ready.is_empty() {
            break;
        }
        ready.sort_by(|left, right| {
            compare_anchor_priority(node_by_id[left], node_by_id[right], profile, phases, &soft)
        });
        let next = ready.remove(0);
        ordered.push(next.clone());
        if let Some(children) = adjacency.get(&next) {
            for child in children {
                if let Some(degree) = indegree.get_mut(child) {
                    *degree = degree.saturating_sub(1);
                }
            }
        }
    }
    if ordered.len() == anchors.len() {
        return (ordered, false, Vec::new());
    }
    let ordered_set = ordered.iter().cloned().collect::<BTreeSet<_>>();
    let remaining = anchors
        .iter()
        .filter(|node| !ordered_set.contains(&node.node_id))
        .map(|node| node.node_id.clone())
        .collect::<BTreeSet<_>>();
    let remaining_edges = hard
        .iter()
        .filter(|edge| {
            remaining.contains(edge["from_node_id"].as_str().unwrap_or_default())
                && remaining.contains(edge["to_node_id"].as_str().unwrap_or_default())
        })
        .cloned()
        .collect::<Vec<_>>();
    let components = strongly_connected_components(&remaining, &remaining_edges);
    let mut component_by_node = BTreeMap::new();
    for (index, component) in components.iter().enumerate() {
        for node in component {
            component_by_node.insert(node.clone(), index);
        }
    }
    let relaxed = remaining_edges
        .iter()
        .filter(|edge| {
            component_by_node.get(edge["from_node_id"].as_str().unwrap_or_default())
                == component_by_node.get(edge["to_node_id"].as_str().unwrap_or_default())
        })
        .cloned()
        .collect::<Vec<_>>();
    let mut comp_out = vec![BTreeSet::new(); components.len()];
    let mut comp_indegree = vec![0usize; components.len()];
    let mut comp_pairs = BTreeSet::new();
    for edge in &remaining_edges {
        let from = component_by_node[edge["from_node_id"].as_str().unwrap_or_default()];
        let to = component_by_node[edge["to_node_id"].as_str().unwrap_or_default()];
        if from != to && comp_pairs.insert((from, to)) {
            comp_out[from].insert(to);
            comp_indegree[to] += 1;
        }
    }
    let comp_priority = |index: usize| {
        components[index]
            .iter()
            .filter_map(|id| node_by_id.get(id))
            .min_by(|left, right| compare_anchor_priority(left, right, profile, phases, &soft))
            .map(|node| node.node_id.clone())
            .unwrap_or_default()
    };
    let mut order = Vec::new();
    loop {
        let mut ready = (0..components.len())
            .filter(|index| comp_indegree[*index] == 0 && !order.contains(index))
            .collect::<Vec<_>>();
        if ready.is_empty() {
            break;
        }
        ready.sort_by_key(|index| comp_priority(*index));
        let next = ready[0];
        order.push(next);
        for child in comp_out[next].clone() {
            comp_indegree[child] = comp_indegree[child].saturating_sub(1);
        }
    }
    if order.len() < components.len() {
        for index in 0..components.len() {
            if !order.contains(&index) {
                order.push(index);
            }
        }
    }
    for component_index in order {
        let mut nodes = components[component_index]
            .iter()
            .filter_map(|id| node_by_id.get(id).map(|node| (*node).clone()))
            .collect::<Vec<_>>();
        nodes.sort_by(|left, right| compare_anchor_priority(left, right, profile, phases, &soft));
        ordered.extend(nodes.into_iter().map(|node| node.node_id));
    }
    (ordered, true, relaxed)
}

fn add_explanation_layer(
    connection: &Connection,
    document_id: &str,
    profile: &str,
) -> Result<(), String> {
    add_analysis_node(
        connection,
        "explanation:summary",
        document_id,
        "explanation",
        "summary",
        "graph explanation",
        "Natural-language explanation generated from graph facts.",
        0,
        0,
        1.0,
        json!({"profile":profile,"source":"graph_facts"}),
    )
}

fn command_analyze(options: &Options) -> Result<i32, String> {
    let path = graph_db_path(options)?;
    let connection = connect(&path)?;
    initialize_schema(&connection)?;
    clear_analysis(&connection)?;
    analyze_graph(&connection, &options.profile)?;
    emit_stats(
        options,
        "PROSE_REASONING_GRAPH_ANALYZE",
        json!({"PROSE_REASONING_GRAPH_PROFILE":options.profile}),
    )?;
    Ok(0)
}
