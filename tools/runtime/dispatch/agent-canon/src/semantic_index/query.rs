// @dependency-start
// contract implementation
// responsibility Owns semantic-index search, context-pack, and responsibility-tree read results.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{ContextPackArgs, OutputFormat, ResponsibilityTreeArgs, SearchArgs};
use super::embedding::{cosine_score, embed_one_for_provider, normalize_vector};
use super::model::{
    bytes_hex_hash, directory_ancestors_for_file, directory_depth, directory_parent, relative_path,
    responsibility_scope_bucket, sorted_counts, sorted_difference, sorted_strings, vector_to_blob,
    IndexedNode, ScoredNode,
};
use super::source::{context_excerpt, discover_files};
use super::storage::{
    load_file_paths, load_nodes, open_cache_connection, resolve_provider_dim, validate_analysis_db,
};
use rusqlite::Connection;
use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub(super) struct SearchResults {
    pub(super) results: Vec<ScoredNode>,
    pub(super) stale_path_count: usize,
}

#[derive(Debug, Clone)]
pub(super) struct ContextCell {
    pub(super) rank: usize,
    pub(super) score: f32,
    pub(super) path: String,
    pub(super) line_start: i64,
    pub(super) line_end: i64,
    pub(super) node_kind: String,
    pub(super) responsibility_bucket: String,
    pub(super) excerpt: String,
}

#[derive(Debug, Clone)]
pub(super) struct DirectoryCoverage {
    pub(super) status: String,
    pub(super) expected_directories: Vec<String>,
    pub(super) db_directories: Vec<String>,
    pub(super) missing_directories: Vec<String>,
    pub(super) stale_directories: Vec<String>,
}

#[derive(Debug, Clone)]
pub(super) struct DirectoryResponsibilityNode {
    pub(super) path: String,
    pub(super) parent: Option<String>,
    pub(super) depth: usize,
    pub(super) file_count: usize,
    pub(super) node_count: usize,
    pub(super) vector: Vec<f32>,
    pub(super) vector_hash: String,
    pub(super) dominant_responsibility: String,
    pub(super) dominant_share: f64,
    pub(super) responsibility_counts: Vec<(String, usize)>,
    pub(super) node_kind_counts: Vec<(String, usize)>,
    pub(super) parent_similarity: Option<f32>,
}

#[derive(Debug, Clone)]
pub(super) struct ResponsibilityTreeReport {
    pub(super) db: PathBuf,
    pub(super) root: PathBuf,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) node_kind: String,
    pub(super) include_vector: bool,
    pub(super) directories: Vec<DirectoryResponsibilityNode>,
    pub(super) directory_count_total: usize,
    pub(super) coverage: DirectoryCoverage,
}

#[derive(Debug, Clone)]
pub(super) struct DirectoryAccumulator {
    files: HashSet<i64>,
    node_count: usize,
    vector_sum: Vec<f32>,
    responsibility_counts: HashMap<String, usize>,
    node_kind_counts: HashMap<String, usize>,
}

pub(super) fn search_index(args: &SearchArgs) -> Result<SearchResults, String> {
    validate_analysis_db(&args.root, &args.db)?;
    let conn = open_cache_connection(&args.db)?;
    let query = embed_one_for_provider(
        &args.provider,
        &args.model,
        args.dim,
        args.embedding_url.as_deref(),
        &args.query,
    )?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, query.len())?;
    let stale_path_count = nodes
        .iter()
        .filter(|node| !indexed_node_path_exists(&args.root, node))
        .count();
    let live_nodes: Vec<IndexedNode> = nodes
        .into_iter()
        .filter(|node| indexed_node_path_exists(&args.root, node))
        .collect();
    Ok(SearchResults {
        results: score_nodes(&live_nodes, &query, args.top_k),
        stale_path_count,
    })
}

pub(super) fn context_pack(args: &ContextPackArgs) -> Result<Vec<ContextCell>, String> {
    let search_args = SearchArgs {
        root: args.root.clone(),
        db: args.db.clone(),
        query: args.query.clone(),
        provider: args.provider.clone(),
        model: args.model.clone(),
        dim: args.dim,
        embedding_url: args.embedding_url.clone(),
        top_k: args.max_cells,
        format: OutputFormat::Json,
    };
    let hits = search_index(&search_args)?;
    let mut cells = Vec::new();
    let mut used_chars = 0_usize;
    for hit in hits.results {
        if cells.len() >= args.max_cells || used_chars >= args.max_total_chars {
            break;
        }
        let remaining_chars = args.max_total_chars.saturating_sub(used_chars);
        let cell_limit = args.max_cell_chars.min(remaining_chars);
        if cell_limit == 0 {
            break;
        }
        let excerpt = context_excerpt(&args.root, &hit.node, cell_limit)?;
        used_chars += excerpt.chars().count();
        cells.push(ContextCell {
            rank: hit.rank,
            score: hit.score,
            path: hit.node.path.clone(),
            line_start: hit.node.line_start,
            line_end: hit.node.line_end,
            node_kind: hit.node.kind.clone(),
            responsibility_bucket: responsibility_scope_bucket(&hit.node.path).to_string(),
            excerpt,
        });
    }
    Ok(cells)
}

pub(super) fn responsibility_tree(
    args: &ResponsibilityTreeArgs,
) -> Result<ResponsibilityTreeReport, String> {
    validate_analysis_db(&args.root, &args.db)?;
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, dim)?;
    let coverage = directory_coverage(&conn, args)?;
    let mut accumulators: HashMap<String, DirectoryAccumulator> = HashMap::new();
    for node in nodes
        .iter()
        .filter(|node| tree_node_kind_matches(node, &args.node_kind))
    {
        for directory in directory_ancestors_for_file(&node.path) {
            if args
                .max_depth
                .is_some_and(|max_depth| directory_depth(&directory) > max_depth)
            {
                continue;
            }
            accumulators
                .entry(directory)
                .or_insert_with(|| DirectoryAccumulator::new(dim))
                .add(node);
        }
    }
    let mut vectors_by_path: HashMap<String, Vec<f32>> = HashMap::new();
    for (path, accumulator) in &accumulators {
        let mut vector = accumulator.vector_sum.clone();
        normalize_vector(&mut vector);
        vectors_by_path.insert(path.clone(), vector);
    }
    let mut directories = Vec::new();
    for (path, accumulator) in accumulators {
        let vector = vectors_by_path
            .get(&path)
            .cloned()
            .unwrap_or_else(|| vec![0.0; dim]);
        let responsibility_counts = sorted_counts(&accumulator.responsibility_counts);
        let node_kind_counts = sorted_counts(&accumulator.node_kind_counts);
        let dominant_count = responsibility_counts
            .first()
            .map(|(_, count)| *count)
            .unwrap_or(0);
        let dominant_responsibility = responsibility_counts
            .first()
            .map(|(name, _)| name.clone())
            .unwrap_or_else(|| "none".to_string());
        let parent = directory_parent(&path);
        let parent_similarity = parent.as_ref().and_then(|parent_path| {
            vectors_by_path
                .get(parent_path)
                .map(|parent_vector| cosine_score(parent_vector, &vector))
        });
        directories.push(DirectoryResponsibilityNode {
            path: path.clone(),
            parent,
            depth: directory_depth(&path),
            file_count: accumulator.files.len(),
            node_count: accumulator.node_count,
            vector_hash: bytes_hex_hash(&vector_to_blob(&vector)),
            vector,
            dominant_responsibility,
            dominant_share: if accumulator.node_count == 0 {
                0.0
            } else {
                dominant_count as f64 / accumulator.node_count as f64
            },
            responsibility_counts,
            node_kind_counts,
            parent_similarity,
        });
    }
    directories.sort_by(|left, right| {
        left.depth
            .cmp(&right.depth)
            .then_with(|| left.path.cmp(&right.path))
    });
    let directory_count_total = directories.len();
    if let Some(top_k) = args.top_k {
        directories.truncate(top_k);
    }
    Ok(ResponsibilityTreeReport {
        db: args.db.clone(),
        root: args.root.clone(),
        provider: args.provider.clone(),
        model: args.model.clone(),
        dim,
        node_kind: args.node_kind.clone(),
        include_vector: args.include_vector,
        directories,
        directory_count_total,
        coverage,
    })
}

impl DirectoryAccumulator {
    fn new(dim: usize) -> Self {
        Self {
            files: HashSet::new(),
            node_count: 0,
            vector_sum: vec![0.0; dim],
            responsibility_counts: HashMap::new(),
            node_kind_counts: HashMap::new(),
        }
    }

    fn add(&mut self, node: &IndexedNode) {
        self.files.insert(node.file_id);
        self.node_count += 1;
        for (left, right) in self.vector_sum.iter_mut().zip(node.vector.iter()) {
            *left += *right;
        }
        *self
            .responsibility_counts
            .entry(responsibility_scope_bucket(&node.path).to_string())
            .or_insert(0) += 1;
        *self.node_kind_counts.entry(node.kind.clone()).or_insert(0) += 1;
    }
}

fn tree_node_kind_matches(node: &IndexedNode, node_kind: &str) -> bool {
    node_kind == "all" || node.kind == node_kind
}

fn directory_coverage(
    conn: &Connection,
    args: &ResponsibilityTreeArgs,
) -> Result<DirectoryCoverage, String> {
    let expected_files = discover_files(
        &args.root,
        &args.includes,
        &args.excludes,
        args.max_file_bytes,
    )?;
    let root_for_relative = fs::canonicalize(&args.root).unwrap_or_else(|_| args.root.clone());
    let mut expected = HashSet::new();
    for path in expected_files {
        let relative = relative_path(&root_for_relative, &path);
        expected.extend(directory_ancestors_for_file(&relative));
    }
    let mut db = HashSet::new();
    for path in load_file_paths(conn)? {
        db.extend(directory_ancestors_for_file(&path));
    }
    let expected_directories = sorted_strings(&expected);
    let db_directories = sorted_strings(&db);
    let missing_directories = sorted_difference(&expected, &db);
    let stale_directories = sorted_difference(&db, &expected);
    let status = if missing_directories.is_empty() && stale_directories.is_empty() {
        "pass"
    } else {
        "fail"
    }
    .to_string();
    Ok(DirectoryCoverage {
        status,
        expected_directories,
        db_directories,
        missing_directories,
        stale_directories,
    })
}

pub(super) fn score_nodes(nodes: &[IndexedNode], query: &[f32], top_k: usize) -> Vec<ScoredNode> {
    let mut results: Vec<ScoredNode> = nodes
        .iter()
        .cloned()
        .map(|node| {
            let score = cosine_score(query, &node.vector);
            ScoredNode {
                node,
                score,
                rank: 0,
            }
        })
        .filter(|result| result.score > 0.0)
        .collect();
    sort_scored_nodes(&mut results);
    results.truncate(top_k);
    for (index, result) in results.iter_mut().enumerate() {
        result.rank = index + 1;
    }
    results
}

fn indexed_node_path_exists(root: &Path, node: &IndexedNode) -> bool {
    let path = Path::new(&node.path);
    if path.is_absolute() {
        return path.exists();
    }
    root.join(path).exists()
}

fn sort_scored_nodes(results: &mut [ScoredNode]) {
    results.sort_by(|left, right| {
        right
            .score
            .partial_cmp(&left.score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.node.path.cmp(&right.node.path))
            .then_with(|| left.node.line_start.cmp(&right.node.line_start))
    });
}
