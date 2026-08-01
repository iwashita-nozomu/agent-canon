// @dependency-start
// contract implementation
// responsibility Owns cross-owner semantic-index domain identities and pure identity helpers.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

pub(super) const OPENAI_COMPATIBLE_EMBEDDING_PROVIDER: &str = "openai-compatible-embedding";
pub(super) const MERGE_CANDIDATE_MIN_LINES: i64 = 4;

pub(super) fn validate_discourse_profile(profile: &str) -> Result<(), String> {
    match profile {
        "general" | "experiment-report" | "methods-protocol" | "academic-argument"
        | "refactor-design" => Ok(()),
        unknown => Err(format!("unknown discourse profile {unknown}")),
    }
}

pub(super) struct TextNode {
    pub(super) kind: String,
    pub(super) line_start: usize,
    pub(super) line_end: usize,
    pub(super) text: String,
    pub(super) parent_index: Option<usize>,
}

#[derive(Debug, Clone)]
pub(super) struct IndexedNode {
    pub(super) node_id: i64,
    pub(super) file_id: i64,
    pub(super) path: String,
    pub(super) kind: String,
    pub(super) line_start: i64,
    pub(super) line_end: i64,
    pub(super) vector: Vec<f32>,
}

#[derive(Debug, Clone)]
pub(super) struct ScoredNode {
    pub(super) node: IndexedNode,
    pub(super) score: f32,
    pub(super) rank: usize,
}

pub(super) fn is_merge_candidate_node(node: &IndexedNode) -> bool {
    if node.kind != "document" && node.kind != "section" {
        return false;
    }
    let line_count = node.line_end.saturating_sub(node.line_start) + 1;
    line_count >= MERGE_CANDIDATE_MIN_LINES
}

pub(super) fn merge_candidate_bucket(node: &IndexedNode) -> Option<String> {
    let path = node.path.replace('\\', "/");
    if is_alignment_or_log_surface(&path) {
        return None;
    }
    let surface = merge_candidate_surface_kind(&path)?;
    let responsibility = responsibility_scope_bucket(&path);
    let topic = match surface {
        "docs" => document_responsibility_bucket(&path).to_string(),
        _ => Path::new(&path)
            .extension()
            .and_then(|part| part.to_str())
            .unwrap_or("none")
            .to_ascii_lowercase(),
    };
    Some(format!("{surface}:{responsibility}:{topic}"))
}

pub(super) fn merge_candidate_surface_kind(path: &str) -> Option<&'static str> {
    let extension = Path::new(&path)
        .extension()
        .and_then(|part| part.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    match extension.as_str() {
        "md" | "markdown" | "txt" | "rst" => Some("docs"),
        "rs" | "py" | "sh" | "sql" => Some("code"),
        "toml" | "yaml" | "yml" | "json" | "jsonl" => Some("config"),
        _ => None,
    }
}

pub(super) fn is_alignment_or_log_surface(path: &str) -> bool {
    path.starts_with("agents/evals/results/")
        || path.starts_with("reports/")
        || path.starts_with(".agent-canon/")
        || path.starts_with(".agents/skills/")
        || path.starts_with("templates/agents/_partials/")
        || path.starts_with("codex-cli-guide/source/")
        || path.starts_with("codex-cli-guide/sections/")
}

pub(super) fn is_document_text_path(path: &str) -> bool {
    let extension = Path::new(path)
        .extension()
        .and_then(|part| part.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    matches!(extension.as_str(), "md" | "markdown" | "txt" | "rst")
}

pub(super) fn is_thin_doc_protected_surface(path: &str) -> bool {
    path == "README.md"
        || path == "AGENTS.md"
        || path == "ROOT_AGENTS.md"
        || path.ends_with("/README.md")
        || path.starts_with(".github/")
        || path.starts_with(".codex/")
}

pub(super) fn is_thin_doc_non_candidate_surface(path: &str) -> bool {
    path.starts_with("templates/agents/") || path.starts_with("tests/fixtures/")
}

pub(super) fn document_responsibility_bucket(path: &str) -> &'static str {
    if path == "README.md" || path.ends_with("/README.md") {
        return "readme";
    }
    if path.starts_with("agents/skills/") {
        return "skill";
    }
    if path.starts_with("agents/workflows/") {
        return "workflow";
    }
    if path.starts_with("documents/tools/") {
        return "tool-doc";
    }
    if path.starts_with("documents/") {
        return "document";
    }
    if path.starts_with("issues/") {
        return "issue";
    }
    if path.starts_with("memory/") {
        return "memory";
    }
    if path.starts_with("notes/") {
        return "note";
    }
    if path.starts_with("references/") {
        return "reference";
    }
    if path.starts_with("tests/fixtures/") {
        return "fixture";
    }
    if path.starts_with(".github/") {
        return "github";
    }
    "general"
}

pub(super) fn responsibility_scope_bucket(path: &str) -> &'static str {
    let normalized = path.replace('\\', "/");
    if normalized.starts_with("evidence/agent-evals/")
        || normalized.starts_with("agents/evals/results/")
    {
        return "eval-and-hook-evidence";
    }
    if normalized.starts_with("issues/") {
        return "operational-issues";
    }
    if normalized.starts_with("tests/") {
        return "test-surfaces";
    }
    if normalized.starts_with("tools/")
        || normalized.starts_with("rust/")
        || normalized == "helper_inventory_guard_policy.json"
    {
        return "shared-tooling";
    }
    if normalized == "CONTAINER_OPERATIONS.md"
        || normalized == "README.md"
        || normalized == "responsibility-scope.toml"
        || normalized.starts_with("documents/")
        || normalized.starts_with("notes/")
        || normalized.starts_with("memory/")
        || normalized.starts_with("references/")
    {
        return "shared-policy-documents";
    }
    if normalized.starts_with(".github/") {
        return "github-automation";
    }
    if normalized.starts_with("vendor/") {
        return "external-skill-vendor";
    }
    if normalized == "AGENTS.md"
        || normalized == "ROOT_AGENTS.md"
        || normalized.starts_with(".agents/")
        || normalized.starts_with(".codex/")
        || normalized.starts_with(".devcontainer/")
        || normalized == "agent-canon-environment.toml"
        || normalized.starts_with("agents/")
        || normalized.starts_with("mcp/")
    {
        return "runtime-entrypoints";
    }
    "general"
}

pub(super) fn vector_to_blob(vector: &[f32]) -> Vec<u8> {
    let mut blob = Vec::with_capacity(vector.len() * 4);
    for value in vector {
        blob.extend_from_slice(&value.to_le_bytes());
    }
    blob
}

pub(super) fn blob_to_vector(blob: &[u8]) -> Vec<f32> {
    blob.chunks_exact(4)
        .map(|chunk| {
            let mut bytes = [0_u8; 4];
            bytes.copy_from_slice(chunk);
            f32::from_le_bytes(bytes)
        })
        .collect()
}

pub(super) fn sorted_counts(counts: &HashMap<String, usize>) -> Vec<(String, usize)> {
    let mut output: Vec<(String, usize)> = counts
        .iter()
        .map(|(key, value)| (key.clone(), *value))
        .collect();
    output.sort_by(|left, right| right.1.cmp(&left.1).then_with(|| left.0.cmp(&right.0)));
    output
}

pub(super) fn sorted_intersection(left: &HashSet<String>, right: &HashSet<String>) -> Vec<String> {
    let mut output: Vec<String> = left.intersection(right).cloned().collect();
    output.sort();
    output
}

pub(super) fn sorted_difference(left: &HashSet<String>, right: &HashSet<String>) -> Vec<String> {
    let mut output: Vec<String> = left.difference(right).cloned().collect();
    output.sort();
    output
}

pub(super) fn sorted_strings(values: &HashSet<String>) -> Vec<String> {
    let mut output: Vec<String> = values.iter().cloned().collect();
    output.sort_by(|left, right| {
        directory_depth(left)
            .cmp(&directory_depth(right))
            .then_with(|| left.cmp(right))
    });
    output
}

pub(super) fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

pub(super) fn directory_ancestors_for_file(path: &str) -> Vec<String> {
    let normalized = path.replace('\\', "/");
    let parts: Vec<&str> = normalized
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect();
    let mut directories = vec![".".to_string()];
    if parts.len() <= 1 {
        return directories;
    }
    let mut current = String::new();
    for part in parts.iter().take(parts.len() - 1) {
        if !current.is_empty() {
            current.push('/');
        }
        current.push_str(part);
        directories.push(current.clone());
    }
    directories
}

pub(super) fn directory_parent(path: &str) -> Option<String> {
    if path == "." {
        return None;
    }
    path.rsplit_once('/')
        .map(|(parent, _)| parent.to_string())
        .or_else(|| Some(".".to_string()))
}

pub(super) fn directory_depth(path: &str) -> usize {
    if path == "." {
        0
    } else {
        path.split('/').filter(|part| !part.is_empty()).count()
    }
}

pub(super) fn count_lines(text: &str) -> usize {
    text.lines().count()
}

pub(super) fn hex_hash(text: &str) -> String {
    let digest = Sha256::digest(text.as_bytes());
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

pub(super) fn bytes_hex_hash(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

pub(super) fn unix_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

pub(super) fn run_id() -> String {
    format!("{}", unix_millis())
}
