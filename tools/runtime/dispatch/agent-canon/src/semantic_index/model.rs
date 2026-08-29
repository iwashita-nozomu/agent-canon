// @dependency-start
// contract implementation
// responsibility Owns cross-owner semantic-index domain identities and pure identity helpers.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/repository/github/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;

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

pub(super) fn responsibility_scope_bucket(path: &str) -> &'static str {
    let normalized = path.replace('\\', "/");
    if normalized.starts_with("eval/")
        || normalized.starts_with("agents/evals/results/")
    {
        return "eval-and-hook-evidence";
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
        || normalized.starts_with("documents/notes/")
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
