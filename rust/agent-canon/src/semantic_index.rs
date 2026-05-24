// @dependency-start
// responsibility Provides Rust-native semantic vector indexing, search, similarity, thin-doc, and eval CLI support.
// upstream design ../../../documents/semantic_index.md semantic index responsibility and generated-cache policy
// upstream design ../../../documents/search-coordination.md coordinated search boundary and advisory search policy
// upstream design ../../../documents/rust-agent-tool-migration.md Rust CLI migration policy
// downstream design ../../../tools/README.md documents root tool entrypoints
// downstream design ../../../documents/tools/README.md documents reader-facing tool entrypoints
// downstream design ../../../tools/catalog.yaml catalogs this Rust CLI surface
// @dependency-end

use rusqlite::{params, Connection};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::env;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const DEFAULT_PROVIDER: &str = "deterministic-dense-v1";
const DEFAULT_MODEL: &str = "hash-token-char-v1";
const DEFAULT_DIM: usize = 128;
const DEFAULT_TOP_K: usize = 10;
const DEFAULT_MIN_SCORE: f32 = 0.80;
const DEFAULT_MAX_FILE_BYTES: u64 = 1_000_000;
const VECTOR_EPSILON: f32 = 1.0e-6;
const MERGE_CANDIDATE_MIN_LINES: i64 = 4;
const DEFAULT_MIN_THIN_SCORE: f32 = 0.50;
const DEFAULT_MIN_THIN_NEIGHBOR_SCORE: f32 = 0.86;

#[derive(Debug, Clone, PartialEq, Eq)]
enum SemanticCommand {
    Help,
}

#[derive(Debug, Clone)]
struct BuildArgs {
    root: PathBuf,
    includes: Vec<PathBuf>,
    excludes: Vec<String>,
    db: PathBuf,
    provider: String,
    model: String,
    dim: usize,
    max_file_bytes: u64,
}

#[derive(Debug, Clone)]
struct SearchArgs {
    root: PathBuf,
    db: PathBuf,
    query: String,
    provider: String,
    model: String,
    dim: usize,
    top_k: usize,
    format: OutputFormat,
}

#[derive(Debug, Clone)]
struct SimilarArgs {
    root: PathBuf,
    db: PathBuf,
    provider: String,
    model: String,
    dim: usize,
    min_score: f32,
    top_k: usize,
    format: OutputFormat,
    cross_file_only: bool,
    kind: SimilarKind,
}

#[derive(Debug, Clone)]
struct ThinDocsArgs {
    root: PathBuf,
    db: PathBuf,
    provider: String,
    model: String,
    dim: usize,
    min_thin_score: f32,
    min_neighbor_score: f32,
    top_k: usize,
    format: OutputFormat,
}

#[derive(Debug, Clone)]
struct EvalArgs {
    fixture: PathBuf,
    db: PathBuf,
    report: Option<PathBuf>,
    provider: String,
    model: String,
    dim: usize,
    top_k: usize,
    format: OutputFormat,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
    Jsonl,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SimilarKind {
    Similar,
    MergeCandidates,
}

#[derive(Debug, Clone)]
enum ParsedArgs {
    Command(SemanticCommand),
    Build(BuildArgs),
    Search(SearchArgs),
    Similar(SimilarArgs),
    ThinDocs(ThinDocsArgs),
    Eval(EvalArgs),
}

#[derive(Debug, Clone)]
struct TextNode {
    kind: String,
    line_start: usize,
    line_end: usize,
    text: String,
    parent_index: Option<usize>,
}

#[derive(Debug, Clone)]
struct IndexedNode {
    node_id: i64,
    file_id: i64,
    path: String,
    kind: String,
    line_start: i64,
    line_end: i64,
    vector: Vec<f32>,
}

#[derive(Debug, Clone)]
struct ScoredNode {
    node: IndexedNode,
    score: f32,
    rank: usize,
}

#[derive(Debug, Clone)]
struct SimilarPair {
    left: IndexedNode,
    right: IndexedNode,
    score: f32,
    rank: usize,
}

#[derive(Debug, Clone)]
struct ThinDocNeighbor {
    node: IndexedNode,
    score: f32,
}

#[derive(Debug, Clone)]
struct ThinDocMetrics {
    total_lines: usize,
    meaningful_lines: usize,
    link_lines: usize,
    wrapper_phrase_hits: usize,
    link_density: f32,
}

#[derive(Debug, Clone)]
struct ThinDocCandidate {
    node: IndexedNode,
    thin_score: f32,
    rank: usize,
    action: String,
    reasons: Vec<String>,
    best_match: Option<ThinDocNeighbor>,
    metrics: ThinDocMetrics,
}

#[derive(Debug, Clone)]
struct BuildStats {
    files: usize,
    nodes: usize,
    embeddings: usize,
    db: PathBuf,
}

pub fn run(args: &[String]) -> i32 {
    match parse_args(args) {
        Ok(ParsedArgs::Command(SemanticCommand::Help)) => {
            print_usage();
            0
        }
        Ok(ParsedArgs::Build(build_args)) => match build_index(&build_args) {
            Ok(stats) => {
                println!("SEMANTIC_INDEX_BUILD=ok");
                println!("SEMANTIC_INDEX_DB={}", stats.db.display());
                println!("SEMANTIC_INDEX_FILES={}", stats.files);
                println!("SEMANTIC_INDEX_NODES={}", stats.nodes);
                println!("SEMANTIC_INDEX_EMBEDDINGS={}", stats.embeddings);
                0
            }
            Err(error) => fail("BUILD", error),
        },
        Ok(ParsedArgs::Search(search_args)) => match search_index(&search_args) {
            Ok(results) => {
                print_search_results(&search_args, &results);
                0
            }
            Err(error) => fail("SEARCH", error),
        },
        Ok(ParsedArgs::Similar(similar_args)) => match similar_pairs(&similar_args) {
            Ok(results) => {
                if let Err(error) = persist_pairs(&similar_args, &results) {
                    fail("SIMILAR_PERSIST", error)
                } else {
                    print_similar_results(&similar_args, &results);
                    0
                }
            }
            Err(error) => fail("SIMILAR", error),
        },
        Ok(ParsedArgs::ThinDocs(thin_docs_args)) => match thin_docs(&thin_docs_args) {
            Ok(results) => {
                if let Err(error) = persist_thin_docs(&thin_docs_args, &results) {
                    fail("THIN_DOCS_PERSIST", error)
                } else {
                    print_thin_docs_results(&thin_docs_args, &results);
                    0
                }
            }
            Err(error) => fail("THIN_DOCS", error),
        },
        Ok(ParsedArgs::Eval(eval_args)) => match run_eval(&eval_args) {
            Ok(report) => {
                if let Some(path) = &eval_args.report {
                    if let Err(error) = write_report(path, &report) {
                        return fail("EVAL_REPORT", error);
                    }
                }
                if eval_args.format == OutputFormat::Json {
                    println!("{}", report);
                } else {
                    print_eval_summary(&report);
                }
                if report.get("semantic_index_eval").and_then(Value::as_str) == Some("pass") {
                    0
                } else {
                    1
                }
            }
            Err(error) => fail("EVAL", error),
        },
        Err(message) => {
            eprintln!("SEMANTIC_INDEX_CLI=fail");
            eprintln!("SEMANTIC_INDEX_CLI_ERROR={message}");
            print_usage();
            2
        }
    }
}

fn parse_args(args: &[String]) -> Result<ParsedArgs, String> {
    let Some(raw_command) = args.first() else {
        return Ok(ParsedArgs::Command(SemanticCommand::Help));
    };
    if raw_command == "--help" || raw_command == "-h" || raw_command == "help" {
        return Ok(ParsedArgs::Command(SemanticCommand::Help));
    }
    match raw_command.as_str() {
        "build" => Ok(ParsedArgs::Build(parse_build_args(&args[1..])?)),
        "search" => Ok(ParsedArgs::Search(parse_search_args(&args[1..])?)),
        "similar" => Ok(ParsedArgs::Similar(parse_similar_args(
            &args[1..],
            SimilarKind::Similar,
        )?)),
        "merge-candidates" => Ok(ParsedArgs::Similar(parse_similar_args(
            &args[1..],
            SimilarKind::MergeCandidates,
        )?)),
        "thin-docs" => Ok(ParsedArgs::ThinDocs(parse_thin_docs_args(&args[1..])?)),
        "eval" => Ok(ParsedArgs::Eval(parse_eval_args(&args[1..])?)),
        unknown => Err(format!("unknown semantic-index command {unknown}")),
    }
}

fn parse_build_args(args: &[String]) -> Result<BuildArgs, String> {
    let mut parsed = BuildArgs {
        root: PathBuf::from("."),
        includes: Vec::new(),
        excludes: default_excludes(),
        db: default_db_path(Path::new(".")),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => {
                parsed.root = value_path(args, index, "--root")?;
                if parsed.db == default_db_path(Path::new(".")) {
                    parsed.db = default_db_path(&parsed.root);
                }
                index += 2;
            }
            "--include" => {
                parsed.includes.push(value_path(args, index, "--include")?);
                index += 2;
            }
            "--exclude" => {
                parsed
                    .excludes
                    .push(value_string(args, index, "--exclude")?);
                index += 2;
            }
            "--db" => {
                parsed.db = value_path(args, index, "--db")?;
                index += 2;
            }
            "--provider" => {
                parsed.provider = value_string(args, index, "--provider")?;
                index += 2;
            }
            "--model" => {
                parsed.model = value_string(args, index, "--model")?;
                index += 2;
            }
            "--dim" => {
                parsed.dim = value_usize(args, index, "--dim")?;
                index += 2;
            }
            "--max-file-bytes" => {
                parsed.max_file_bytes = value_u64(args, index, "--max-file-bytes")?;
                index += 2;
            }
            unknown => return Err(format!("unknown build option {unknown}")),
        }
    }
    if parsed.includes.is_empty() {
        parsed.includes.push(PathBuf::from("."));
    }
    validate_dim(parsed.dim)?;
    Ok(parsed)
}

fn parse_search_args(args: &[String]) -> Result<SearchArgs, String> {
    let mut parsed = SearchArgs {
        root: PathBuf::from("."),
        db: default_db_path(Path::new(".")),
        query: String::new(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        top_k: DEFAULT_TOP_K,
        format: OutputFormat::Text,
    };
    let mut query_sources = 0;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => {
                parsed.root = value_path(args, index, "--root")?;
                if parsed.db == default_db_path(Path::new(".")) {
                    parsed.db = default_db_path(&parsed.root);
                }
                index += 2;
            }
            "--db" => {
                parsed.db = value_path(args, index, "--db")?;
                index += 2;
            }
            "--query" => {
                parsed.query = value_string(args, index, "--query")?;
                query_sources += 1;
                index += 2;
            }
            "--query-file" => {
                let path = value_path(args, index, "--query-file")?;
                parsed.query = fs::read_to_string(&path)
                    .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
                query_sources += 1;
                index += 2;
            }
            "--query-stdin" => {
                let mut query = String::new();
                io::stdin()
                    .read_to_string(&mut query)
                    .map_err(|error| format!("failed to read query from stdin: {error}"))?;
                parsed.query = query;
                query_sources += 1;
                index += 1;
            }
            "--provider" => {
                parsed.provider = value_string(args, index, "--provider")?;
                index += 2;
            }
            "--model" => {
                parsed.model = value_string(args, index, "--model")?;
                index += 2;
            }
            "--dim" => {
                parsed.dim = value_usize(args, index, "--dim")?;
                index += 2;
            }
            "--top-k" => {
                parsed.top_k = value_usize(args, index, "--top-k")?;
                index += 2;
            }
            "--format" => {
                parsed.format = parse_format(&value_string(args, index, "--format")?)?;
                index += 2;
            }
            unknown => return Err(format!("unknown search option {unknown}")),
        }
    }
    if query_sources > 1 {
        return Err("use only one of --query, --query-file, or --query-stdin".to_string());
    }
    if parsed.query.trim().is_empty() {
        return Err("--query, --query-file, or --query-stdin is required".to_string());
    }
    validate_dim(parsed.dim)?;
    Ok(parsed)
}

fn parse_similar_args(args: &[String], kind: SimilarKind) -> Result<SimilarArgs, String> {
    let mut parsed = SimilarArgs {
        root: PathBuf::from("."),
        db: default_db_path(Path::new(".")),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        min_score: DEFAULT_MIN_SCORE,
        top_k: DEFAULT_TOP_K,
        format: OutputFormat::Text,
        cross_file_only: kind == SimilarKind::MergeCandidates,
        kind,
    };
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => {
                parsed.root = value_path(args, index, "--root")?;
                if parsed.db == default_db_path(Path::new(".")) {
                    parsed.db = default_db_path(&parsed.root);
                }
                index += 2;
            }
            "--db" => {
                parsed.db = value_path(args, index, "--db")?;
                index += 2;
            }
            "--provider" => {
                parsed.provider = value_string(args, index, "--provider")?;
                index += 2;
            }
            "--model" => {
                parsed.model = value_string(args, index, "--model")?;
                index += 2;
            }
            "--dim" => {
                parsed.dim = value_usize(args, index, "--dim")?;
                index += 2;
            }
            "--min-score" => {
                parsed.min_score = value_f32(args, index, "--min-score")?;
                index += 2;
            }
            "--top-k" => {
                parsed.top_k = value_usize(args, index, "--top-k")?;
                index += 2;
            }
            "--format" => {
                parsed.format = parse_format(&value_string(args, index, "--format")?)?;
                index += 2;
            }
            "--cross-file-only" => {
                parsed.cross_file_only = true;
                index += 1;
            }
            "--allow-same-file" => {
                parsed.cross_file_only = false;
                index += 1;
            }
            unknown => return Err(format!("unknown similar option {unknown}")),
        }
    }
    validate_dim(parsed.dim)?;
    validate_min_score(parsed.min_score)?;
    Ok(parsed)
}

fn parse_thin_docs_args(args: &[String]) -> Result<ThinDocsArgs, String> {
    let mut parsed = ThinDocsArgs {
        root: PathBuf::from("."),
        db: default_db_path(Path::new(".")),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        min_thin_score: DEFAULT_MIN_THIN_SCORE,
        min_neighbor_score: DEFAULT_MIN_THIN_NEIGHBOR_SCORE,
        top_k: DEFAULT_TOP_K,
        format: OutputFormat::Text,
    };
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => {
                parsed.root = value_path(args, index, "--root")?;
                if parsed.db == default_db_path(Path::new(".")) {
                    parsed.db = default_db_path(&parsed.root);
                }
                index += 2;
            }
            "--db" => {
                parsed.db = value_path(args, index, "--db")?;
                index += 2;
            }
            "--provider" => {
                parsed.provider = value_string(args, index, "--provider")?;
                index += 2;
            }
            "--model" => {
                parsed.model = value_string(args, index, "--model")?;
                index += 2;
            }
            "--dim" => {
                parsed.dim = value_usize(args, index, "--dim")?;
                index += 2;
            }
            "--min-thin-score" => {
                parsed.min_thin_score = value_f32(args, index, "--min-thin-score")?;
                index += 2;
            }
            "--min-neighbor-score" => {
                parsed.min_neighbor_score = value_f32(args, index, "--min-neighbor-score")?;
                index += 2;
            }
            "--top-k" => {
                parsed.top_k = value_usize(args, index, "--top-k")?;
                index += 2;
            }
            "--format" => {
                parsed.format = parse_format(&value_string(args, index, "--format")?)?;
                index += 2;
            }
            unknown => return Err(format!("unknown thin-docs option {unknown}")),
        }
    }
    validate_dim(parsed.dim)?;
    validate_min_score(parsed.min_thin_score)?;
    validate_min_score(parsed.min_neighbor_score)?;
    Ok(parsed)
}

fn parse_eval_args(args: &[String]) -> Result<EvalArgs, String> {
    let mut fixture: Option<PathBuf> = None;
    let mut parsed = EvalArgs {
        fixture: PathBuf::new(),
        db: env::temp_dir().join(format!(
            "agent-canon-semantic-index-eval-{}.sqlite",
            run_id()
        )),
        report: None,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        top_k: DEFAULT_TOP_K,
        format: OutputFormat::Text,
    };
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--fixture" => {
                fixture = Some(value_path(args, index, "--fixture")?);
                index += 2;
            }
            "--db" => {
                parsed.db = value_path(args, index, "--db")?;
                index += 2;
            }
            "--report" => {
                parsed.report = Some(value_path(args, index, "--report")?);
                index += 2;
            }
            "--provider" => {
                parsed.provider = value_string(args, index, "--provider")?;
                index += 2;
            }
            "--model" => {
                parsed.model = value_string(args, index, "--model")?;
                index += 2;
            }
            "--dim" => {
                parsed.dim = value_usize(args, index, "--dim")?;
                index += 2;
            }
            "--top-k" => {
                parsed.top_k = value_usize(args, index, "--top-k")?;
                index += 2;
            }
            "--format" => {
                parsed.format = parse_format(&value_string(args, index, "--format")?)?;
                index += 2;
            }
            unknown => return Err(format!("unknown eval option {unknown}")),
        }
    }
    parsed.fixture = fixture.ok_or_else(|| "--fixture is required".to_string())?;
    validate_dim(parsed.dim)?;
    if parsed.format == OutputFormat::Jsonl {
        return Err("--format jsonl is not supported for eval".to_string());
    }
    Ok(parsed)
}

fn build_index(args: &BuildArgs) -> Result<BuildStats, String> {
    ensure_parent_dir(&args.db)?;
    let write_db = prepare_write_db(&args.db)?;
    let mut conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    clear_index(&conn)?;
    let files = discover_files(
        &args.root,
        &args.includes,
        &args.excludes,
        args.max_file_bytes,
    )?;
    let root_for_relative = fs::canonicalize(&args.root).unwrap_or_else(|_| args.root.clone());
    let tx = conn.transaction().map_err(|error| error.to_string())?;
    let mut file_count = 0;
    let mut node_count = 0;
    let mut embedding_count = 0;
    for path in files {
        let text = fs::read_to_string(&path).map_err(|error| {
            format!("failed to read indexable file {}: {error}", path.display())
        })?;
        let relative = relative_path(&root_for_relative, &path);
        let line_count = count_lines(&text);
        let file_id = insert_file(&tx, &relative, &text, path_metadata_size(&path)?)?;
        file_count += 1;
        let nodes = segment_text(&relative, &text);
        let mut inserted_ids: Vec<i64> = Vec::new();
        for node in nodes {
            let parent_id = node
                .parent_index
                .and_then(|parent| inserted_ids.get(parent).copied());
            let node_id = insert_node(&tx, file_id, parent_id, &node)?;
            let vector = embed_text(&node.text, args.dim);
            insert_embedding(&tx, node_id, &args.provider, &args.model, args.dim, &vector)?;
            inserted_ids.push(node_id);
            node_count += 1;
            embedding_count += 1;
        }
        if line_count == 0 {
            continue;
        }
    }
    tx.commit().map_err(|error| error.to_string())?;
    finish_write_db(&write_db, &args.db)?;
    Ok(BuildStats {
        files: file_count,
        nodes: node_count,
        embeddings: embedding_count,
        db: args.db.clone(),
    })
}

fn search_index(args: &SearchArgs) -> Result<Vec<ScoredNode>, String> {
    let conn = open_cache_connection(&args.db)?;
    let query = embed_text(&args.query, args.dim);
    let mut results: Vec<ScoredNode> = load_nodes(&conn, &args.provider, &args.model, args.dim)?
        .into_iter()
        .map(|node| {
            let score = cosine_score(&query, &node.vector);
            ScoredNode {
                node,
                score,
                rank: 0,
            }
        })
        .filter(|result| result.score > 0.0)
        .collect();
    sort_scored_nodes(&mut results);
    results.truncate(args.top_k);
    for (index, result) in results.iter_mut().enumerate() {
        result.rank = index + 1;
    }
    Ok(results)
}

fn similar_pairs(args: &SimilarArgs) -> Result<Vec<SimilarPair>, String> {
    let conn = open_cache_connection(&args.db)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, args.dim)?;
    let mut bucket_ids: HashMap<String, usize> = HashMap::new();
    let mut buckets: Vec<Option<usize>> = Vec::with_capacity(nodes.len());
    for node in &nodes {
        let bucket = comparison_bucket(args.kind, node);
        let bucket_id = bucket.map(|value| {
            let next_id = bucket_ids.len();
            *bucket_ids.entry(value).or_insert(next_id)
        });
        buckets.push(bucket_id);
    }
    let mut pairs: Vec<SimilarPair> = Vec::new();
    let mut inverted: HashMap<(usize, usize, bool), Vec<usize>> = HashMap::new();
    let prune_limit = args.top_k.saturating_mul(16).max(1024);
    for right_index in 0..nodes.len() {
        let right = &nodes[right_index];
        let Some(bucket) = buckets[right_index] else {
            continue;
        };
        let mut candidates: HashSet<usize> = HashSet::new();
        for (index, sign) in prefix_features(&right.vector, args.min_score) {
            if let Some(indices) = inverted.get(&(bucket, index, sign)) {
                candidates.extend(indices.iter().copied());
            }
        }
        for left_index in candidates {
            let left = &nodes[left_index];
            if args.cross_file_only && left.file_id == right.file_id {
                continue;
            }
            let score = cosine_score(&left.vector, &right.vector);
            if score + f32::EPSILON >= args.min_score {
                pairs.push(SimilarPair {
                    left: left.clone(),
                    right: right.clone(),
                    score,
                    rank: 0,
                });
                if pairs.len() > prune_limit {
                    sort_pairs(&mut pairs);
                    pairs.truncate(args.top_k);
                }
            }
        }
        for (index, sign) in all_signed_features(&right.vector) {
            inverted
                .entry((bucket, index, sign))
                .or_default()
                .push(right_index);
        }
    }
    sort_pairs(&mut pairs);
    pairs.truncate(args.top_k);
    for (index, pair) in pairs.iter_mut().enumerate() {
        pair.rank = index + 1;
    }
    Ok(pairs)
}

fn thin_docs(args: &ThinDocsArgs) -> Result<Vec<ThinDocCandidate>, String> {
    let conn = open_cache_connection(&args.db)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, args.dim)?;
    let document_nodes: Vec<IndexedNode> = nodes
        .into_iter()
        .filter(|node| node.kind == "document")
        .filter(|node| is_document_text_path(&node.path))
        .filter(|node| !is_alignment_or_log_surface(&node.path))
        .filter(|node| !is_thin_doc_non_candidate_surface(&node.path))
        .collect();
    let mut candidates = Vec::new();
    for node in &document_nodes {
        let metrics = thin_doc_metrics(&args.root, &node.path);
        if !has_thin_doc_shape(&metrics) {
            continue;
        }
        let best_match = best_thin_doc_neighbor(node, &document_nodes, args.min_neighbor_score);
        let best_score = best_match
            .as_ref()
            .map(|neighbor| neighbor.score)
            .unwrap_or(0.0);
        let protected = is_thin_doc_protected_surface(&node.path);
        let mut reasons = thin_doc_reasons(&metrics, best_score, args.min_neighbor_score);
        if protected {
            reasons.push("protected_entrypoint".to_string());
        }
        let thin_score = thin_doc_score(&metrics, best_score, args.min_neighbor_score);
        if thin_score + f32::EPSILON < args.min_thin_score {
            continue;
        }
        candidates.push(ThinDocCandidate {
            node: node.clone(),
            thin_score,
            rank: 0,
            action: thin_doc_action(&metrics, best_score, args.min_neighbor_score, protected),
            reasons,
            best_match,
            metrics,
        });
    }
    sort_thin_docs(&mut candidates);
    candidates.truncate(args.top_k);
    for (index, candidate) in candidates.iter_mut().enumerate() {
        candidate.rank = index + 1;
    }
    Ok(candidates)
}

fn run_eval(args: &EvalArgs) -> Result<Value, String> {
    let input_root = args.fixture.join("input");
    let expected_path = args.fixture.join("expected.json");
    let expected_text = fs::read_to_string(&expected_path)
        .map_err(|error| format!("failed to read {}: {error}", expected_path.display()))?;
    let expected: Value = serde_json::from_str(&expected_text)
        .map_err(|error| format!("failed to parse {}: {error}", expected_path.display()))?;
    let build_args = BuildArgs {
        root: input_root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: args.db.clone(),
        provider: args.provider.clone(),
        model: args.model.clone(),
        dim: args.dim,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    let started = unix_millis();
    let stats = build_index(&build_args)?;
    let build_ms = unix_millis().saturating_sub(started);
    let queries = eval_queries(args, &expected)?;
    let pairs = eval_pairs(args, &expected, false)?;
    let must_not = eval_pairs(args, &expected, true)?;
    let passed = queries["failed"].as_u64().unwrap_or(0) == 0
        && pairs["failed"].as_u64().unwrap_or(0) == 0
        && must_not["failed"].as_u64().unwrap_or(0) == 0;
    Ok(json!({
        "semantic_index_eval": if passed { "pass" } else { "fail" },
        "fixture": args.fixture.display().to_string(),
        "db": args.db.display().to_string(),
        "build": {
            "indexed_files": stats.files,
            "indexed_nodes": stats.nodes,
            "missing_embeddings": stats.nodes.saturating_sub(stats.embeddings),
            "build_ms": build_ms
        },
        "search": queries,
        "similarity": pairs,
        "must_not_pairs": must_not
    }))
}

fn eval_queries(args: &EvalArgs, expected: &Value) -> Result<Value, String> {
    let Some(queries) = expected.get("queries").and_then(Value::as_array) else {
        return Ok(json!({"cases": 0, "failed": 0, "results": []}));
    };
    let mut results = Vec::new();
    let mut failed = 0;
    let mut recall_sum = 0.0;
    let mut mrr_sum = 0.0;
    for case in queries {
        let id = string_field(case, "id")?;
        let text = string_field(case, "text")?;
        let expected_paths = string_array_field(case, "expected_paths")?;
        let min_recall = case
            .get("min_recall_at_5")
            .and_then(Value::as_f64)
            .unwrap_or(1.0);
        let search_args = SearchArgs {
            root: args.fixture.join("input"),
            db: args.db.clone(),
            query: text,
            provider: args.provider.clone(),
            model: args.model.clone(),
            dim: args.dim,
            top_k: args.top_k.max(5),
            format: OutputFormat::Json,
        };
        let hits = search_index(&search_args)?;
        let top5: Vec<&ScoredNode> = hits.iter().take(5).collect();
        let found = expected_paths
            .iter()
            .filter(|expected_path| top5.iter().any(|hit| hit.node.path == **expected_path))
            .count();
        let recall = if expected_paths.is_empty() {
            1.0
        } else {
            found as f64 / expected_paths.len() as f64
        };
        let reciprocal_rank = reciprocal_rank(&hits, &expected_paths);
        let pass = recall + f64::EPSILON >= min_recall;
        if !pass {
            failed += 1;
        }
        recall_sum += recall;
        mrr_sum += reciprocal_rank;
        results.push(json!({
            "id": id,
            "recall_at_5": recall,
            "mrr": reciprocal_rank,
            "pass": pass,
            "top_paths": hits.iter().take(5).map(|hit| hit.node.path.clone()).collect::<Vec<_>>()
        }));
    }
    let cases = queries.len() as f64;
    Ok(json!({
        "cases": queries.len(),
        "failed": failed,
        "mean_recall_at_5": if cases == 0.0 { 0.0 } else { recall_sum / cases },
        "mrr": if cases == 0.0 { 0.0 } else { mrr_sum / cases },
        "results": results
    }))
}

fn eval_pairs(args: &EvalArgs, expected: &Value, must_not: bool) -> Result<Value, String> {
    let key = if must_not {
        "must_not_pairs"
    } else {
        "similar_pairs"
    };
    let Some(cases) = expected.get(key).and_then(Value::as_array) else {
        return Ok(json!({"cases": 0, "failed": 0, "results": []}));
    };
    let conn = open_cache_connection(&args.db)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, args.dim)?;
    let mut results = Vec::new();
    let mut failed = 0;
    for case in cases {
        let id = string_field(case, "id")?;
        let left_path = string_field(case, "left")?;
        let right_path = string_field(case, "right")?;
        let score = max_path_pair_score(&nodes, &left_path, &right_path);
        let pass = if must_not {
            let max_score = case
                .get("max_score")
                .and_then(Value::as_f64)
                .unwrap_or(DEFAULT_MIN_SCORE as f64);
            score.is_some_and(|value| value <= max_score as f32)
        } else {
            let min_score = case
                .get("min_score")
                .and_then(Value::as_f64)
                .unwrap_or(DEFAULT_MIN_SCORE as f64);
            score.is_some_and(|value| value + f32::EPSILON >= min_score as f32)
        };
        if !pass {
            failed += 1;
        }
        results.push(json!({
            "id": id,
            "left": left_path,
            "right": right_path,
            "score": score.unwrap_or(0.0),
            "missing_path": score.is_none(),
            "pass": pass
        }));
    }
    Ok(json!({
        "cases": cases.len(),
        "failed": failed,
        "results": results
    }))
}

fn persist_pairs(args: &SimilarArgs, pairs: &[SimilarPair]) -> Result<(), String> {
    let write_db = prepare_existing_write_db(&args.db)?;
    let conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    let run_id = run_id();
    let kind = match args.kind {
        SimilarKind::Similar => "similar",
        SimilarKind::MergeCandidates => "merge-candidates",
    };
    conn.execute(
        "INSERT INTO analysis_runs(run_id, kind, created_at, params_json) VALUES (?1, ?2, ?3, ?4)",
        params![
            run_id,
            kind,
            unix_millis().to_string(),
            json!({
                "min_score": args.min_score,
                "top_k": args.top_k,
                "cross_file_only": args.cross_file_only,
                "provider": args.provider,
                "model": args.model,
                "dim": args.dim
            })
            .to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    for pair in pairs {
        conn.execute(
            "INSERT INTO similar_pairs(run_id, left_node_id, right_node_id, score, rank) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                run_id,
                pair.left.node_id,
                pair.right.node_id,
                pair.score,
                pair.rank as i64
            ],
        )
        .map_err(|error| error.to_string())?;
    }
    finish_write_db(&write_db, &args.db)?;
    Ok(())
}

fn persist_thin_docs(args: &ThinDocsArgs, candidates: &[ThinDocCandidate]) -> Result<(), String> {
    let write_db = prepare_existing_write_db(&args.db)?;
    let conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    let run_id = run_id();
    conn.execute(
        "INSERT INTO analysis_runs(run_id, kind, created_at, params_json) VALUES (?1, ?2, ?3, ?4)",
        params![
            run_id,
            "thin-docs",
            unix_millis().to_string(),
            json!({
                "min_thin_score": args.min_thin_score,
                "min_neighbor_score": args.min_neighbor_score,
                "top_k": args.top_k,
                "provider": args.provider,
                "model": args.model,
                "dim": args.dim
            })
            .to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    for candidate in candidates {
        let target_node_id = candidate
            .best_match
            .as_ref()
            .map(|neighbor| neighbor.node.node_id);
        let target_score = candidate.best_match.as_ref().map(|neighbor| neighbor.score);
        conn.execute(
            r#"
            INSERT INTO thin_docs(
                run_id, node_id, thin_score, rank, action, reasons_json,
                metrics_json, target_node_id, target_score
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)
            "#,
            params![
                run_id,
                candidate.node.node_id,
                candidate.thin_score,
                candidate.rank as i64,
                candidate.action,
                json!(candidate.reasons).to_string(),
                thin_doc_metrics_json(&candidate.metrics).to_string(),
                target_node_id,
                target_score,
            ],
        )
        .map_err(|error| error.to_string())?;
    }
    finish_write_db(&write_db, &args.db)?;
    Ok(())
}

fn init_schema(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        r#"
        PRAGMA busy_timeout = 5000;
        PRAGMA user_version = 1;
        CREATE TABLE IF NOT EXISTS files(
            file_id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            content_hash TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nodes(
            node_id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            node_kind TEXT NOT NULL,
            parent_node_id INTEGER,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            text_hash TEXT NOT NULL,
            FOREIGN KEY(file_id) REFERENCES files(file_id)
        );
        CREATE TABLE IF NOT EXISTS embeddings(
            node_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            dtype TEXT NOT NULL,
            vector BLOB NOT NULL,
            PRIMARY KEY(node_id, provider, model, dim),
            FOREIGN KEY(node_id) REFERENCES nodes(node_id)
        );
        CREATE TABLE IF NOT EXISTS analysis_runs(
            run_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            params_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS similar_pairs(
            run_id TEXT NOT NULL,
            left_node_id INTEGER NOT NULL,
            right_node_id INTEGER NOT NULL,
            score REAL NOT NULL,
            rank INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS thin_docs(
            run_id TEXT NOT NULL,
            node_id INTEGER NOT NULL,
            thin_score REAL NOT NULL,
            rank INTEGER NOT NULL,
            action TEXT NOT NULL,
            reasons_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            target_node_id INTEGER,
            target_score REAL
        );
        "#,
    )
    .map_err(|error| error.to_string())
}

fn open_cache_connection(path: &Path) -> Result<Connection, String> {
    Connection::open(path).map_err(|error| error.to_string())
}

fn clear_index(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        r#"
        DELETE FROM thin_docs;
        DELETE FROM similar_pairs;
        DELETE FROM analysis_runs;
        DELETE FROM embeddings;
        DELETE FROM nodes;
        DELETE FROM files;
        "#,
    )
    .map_err(|error| error.to_string())
}

fn insert_file(conn: &Connection, path: &str, text: &str, size_bytes: u64) -> Result<i64, String> {
    conn.execute(
        "INSERT INTO files(path, content_hash, size_bytes, indexed_at) VALUES (?1, ?2, ?3, ?4)",
        params![
            path,
            hex_hash(text),
            size_bytes as i64,
            unix_millis().to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    Ok(conn.last_insert_rowid())
}

fn insert_node(
    conn: &Connection,
    file_id: i64,
    parent_id: Option<i64>,
    node: &TextNode,
) -> Result<i64, String> {
    conn.execute(
        "INSERT INTO nodes(file_id, node_kind, parent_node_id, line_start, line_end, text_hash) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            file_id,
            node.kind,
            parent_id,
            node.line_start as i64,
            node.line_end as i64,
            hex_hash(&node.text)
        ],
    )
    .map_err(|error| error.to_string())?;
    Ok(conn.last_insert_rowid())
}

fn insert_embedding(
    conn: &Connection,
    node_id: i64,
    provider: &str,
    model: &str,
    dim: usize,
    vector: &[f32],
) -> Result<(), String> {
    conn.execute(
        "INSERT INTO embeddings(node_id, provider, model, dim, dtype, vector) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![node_id, provider, model, dim as i64, "f32le", vector_to_blob(vector)],
    )
    .map_err(|error| error.to_string())?;
    Ok(())
}

fn load_nodes(
    conn: &Connection,
    provider: &str,
    model: &str,
    dim: usize,
) -> Result<Vec<IndexedNode>, String> {
    let mut statement = conn
        .prepare(
            r#"
            SELECT n.node_id, n.file_id, f.path, n.node_kind, n.line_start, n.line_end, e.vector
            FROM nodes n
            JOIN files f ON f.file_id = n.file_id
            JOIN embeddings e ON e.node_id = n.node_id
            WHERE e.provider = ?1 AND e.model = ?2 AND e.dim = ?3
            "#,
        )
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map(params![provider, model, dim as i64], |row| {
            let blob: Vec<u8> = row.get(6)?;
            Ok(IndexedNode {
                node_id: row.get(0)?,
                file_id: row.get(1)?,
                path: row.get(2)?,
                kind: row.get(3)?,
                line_start: row.get(4)?,
                line_end: row.get(5)?,
                vector: blob_to_vector(&blob),
            })
        })
        .map_err(|error| error.to_string())?;
    let mut nodes = Vec::new();
    for row in rows {
        let node = row.map_err(|error| error.to_string())?;
        if node.vector.len() == dim {
            nodes.push(node);
        }
    }
    Ok(nodes)
}

fn discover_files(
    root: &Path,
    includes: &[PathBuf],
    excludes: &[String],
    max_file_bytes: u64,
) -> Result<Vec<PathBuf>, String> {
    let mut files = Vec::new();
    let mut seen = HashSet::new();
    let root_canonical = fs::canonicalize(root)
        .map_err(|error| format!("failed to canonicalize root {}: {error}", root.display()))?;
    for include in includes {
        let requested = if include.is_absolute() {
            if !include.starts_with(root) && !include.starts_with(&root_canonical) {
                return Err(format!(
                    "--include path {} is outside --root {}",
                    include.display(),
                    root.display()
                ));
            }
            include.clone()
        } else {
            root.join(include)
        };
        let start = fs::canonicalize(&requested).map_err(|error| {
            format!(
                "failed to canonicalize include path {}: {error}",
                requested.display()
            )
        })?;
        if !start.starts_with(&root_canonical) {
            return Err(format!(
                "--include path {} resolves outside --root {}",
                requested.display(),
                root.display()
            ));
        }
        collect_files(
            &root_canonical,
            &start,
            excludes,
            max_file_bytes,
            &mut seen,
            &mut files,
        )?;
    }
    files.sort();
    Ok(files)
}

fn collect_files(
    root: &Path,
    path: &Path,
    excludes: &[String],
    max_file_bytes: u64,
    seen: &mut HashSet<PathBuf>,
    files: &mut Vec<PathBuf>,
) -> Result<(), String> {
    if should_exclude(root, path, excludes) {
        return Ok(());
    }
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(_) => return Ok(()),
    };
    if metadata.file_type().is_symlink() {
        return Ok(());
    }
    if metadata.is_dir() {
        let entries = fs::read_dir(path)
            .map_err(|error| format!("failed to read directory {}: {error}", path.display()))?;
        for entry in entries {
            let entry = entry.map_err(|error| error.to_string())?;
            collect_files(root, &entry.path(), excludes, max_file_bytes, seen, files)?;
        }
        return Ok(());
    }
    if !metadata.is_file() || metadata.len() > max_file_bytes || !is_indexable(path) {
        return Ok(());
    }
    let canonical = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    if !canonical.starts_with(root) {
        return Ok(());
    }
    if seen.insert(canonical) {
        files.push(path.to_path_buf());
    }
    Ok(())
}

fn should_exclude(root: &Path, path: &Path, excludes: &[String]) -> bool {
    let relative = relative_path(root, path);
    let name = path
        .file_name()
        .and_then(|part| part.to_str())
        .unwrap_or("");
    excludes
        .iter()
        .any(|exclude| relative.contains(exclude) || name == exclude)
}

fn is_indexable(path: &Path) -> bool {
    let Some(extension) = path.extension().and_then(|part| part.to_str()) else {
        return false;
    };
    matches!(
        extension,
        "md" | "txt"
            | "rst"
            | "rs"
            | "py"
            | "toml"
            | "yaml"
            | "yml"
            | "json"
            | "jsonl"
            | "sh"
            | "sql"
    )
}

fn segment_text(path: &str, text: &str) -> Vec<TextNode> {
    let total_lines = count_lines(text).max(1);
    let mut nodes = vec![TextNode {
        kind: "document".to_string(),
        line_start: 1,
        line_end: total_lines,
        text: format!("{path}\n{text}"),
        parent_index: None,
    }];
    if path.ends_with(".md") || path.ends_with(".markdown") {
        nodes.extend(markdown_sections(text));
    }
    nodes.extend(block_nodes(text));
    nodes
}

fn markdown_sections(text: &str) -> Vec<TextNode> {
    let lines: Vec<&str> = text.lines().collect();
    let mut heading_starts = Vec::new();
    for (index, line) in lines.iter().enumerate() {
        if line.trim_start().starts_with('#') {
            heading_starts.push(index);
        }
    }
    let mut nodes = Vec::new();
    for (position, start) in heading_starts.iter().enumerate() {
        let end = heading_starts
            .get(position + 1)
            .copied()
            .unwrap_or(lines.len());
        let section_text = lines[*start..end].join("\n");
        nodes.push(TextNode {
            kind: "section".to_string(),
            line_start: start + 1,
            line_end: end.max(start + 1),
            text: section_text,
            parent_index: Some(0),
        });
    }
    nodes
}

fn block_nodes(text: &str) -> Vec<TextNode> {
    let mut nodes = Vec::new();
    let mut start_line: Option<usize> = None;
    let mut buffer = Vec::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            if let Some(start) = start_line.take() {
                nodes.push(TextNode {
                    kind: "block".to_string(),
                    line_start: start,
                    line_end: index,
                    text: buffer.join("\n"),
                    parent_index: Some(0),
                });
                buffer.clear();
            }
        } else {
            if start_line.is_none() {
                start_line = Some(index + 1);
            }
            buffer.push(line);
        }
    }
    if let Some(start) = start_line {
        nodes.push(TextNode {
            kind: "block".to_string(),
            line_start: start,
            line_end: count_lines(text).max(start),
            text: buffer.join("\n"),
            parent_index: Some(0),
        });
    }
    nodes
}

fn embed_text(text: &str, dim: usize) -> Vec<f32> {
    let text = strip_dependency_manifest(text);
    let mut vector = vec![0.0_f32; dim];
    for token in text_tokens(&text) {
        add_feature(&mut vector, &format!("tok:{token}"), 1.0);
    }
    for gram in char_grams(&text, 3) {
        add_feature(&mut vector, &format!("chr:{gram}"), 0.35);
    }
    normalize_vector(&mut vector);
    vector
}

fn strip_dependency_manifest(text: &str) -> String {
    let trimmed = text.trim_start();
    if !trimmed.starts_with("<!--") || !trimmed.contains("@dependency-start") {
        return text.to_string();
    }
    let Some(end) = trimmed.find("-->") else {
        return text.to_string();
    };
    trimmed[end + 3..].to_string()
}

fn text_tokens(text: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    for ch in text.chars().flat_map(char::to_lowercase) {
        if ch.is_alphanumeric() || ch == '_' || ch == '-' {
            current.push(ch);
        } else if !current.is_empty() {
            tokens.push(std::mem::take(&mut current));
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}

fn char_grams(text: &str, width: usize) -> Vec<String> {
    let compact: Vec<char> = text
        .chars()
        .flat_map(char::to_lowercase)
        .filter(|ch| !ch.is_whitespace() && !ch.is_control())
        .collect();
    if compact.len() < width {
        return Vec::new();
    }
    compact
        .windows(width)
        .map(|window| window.iter().collect())
        .collect()
}

fn add_feature(vector: &mut [f32], feature: &str, weight: f32) {
    if vector.is_empty() {
        return;
    }
    let digest = Sha256::digest(feature.as_bytes());
    let mut bytes = [0_u8; 8];
    bytes.copy_from_slice(&digest[..8]);
    let hash = u64::from_le_bytes(bytes);
    let index = (hash as usize) % vector.len();
    let sign = if digest[8] % 2 == 0 { 1.0 } else { -1.0 };
    vector[index] += sign * weight;
}

fn normalize_vector(vector: &mut [f32]) {
    let norm = vector.iter().map(|value| value * value).sum::<f32>().sqrt();
    if norm == 0.0 {
        return;
    }
    for value in vector.iter_mut() {
        *value /= norm;
    }
}

fn dot(left: &[f32], right: &[f32]) -> f32 {
    left.iter()
        .zip(right.iter())
        .map(|(left_value, right_value)| left_value * right_value)
        .sum()
}

fn cosine_score(left: &[f32], right: &[f32]) -> f32 {
    dot(left, right).clamp(-1.0, 1.0)
}

fn prefix_features(vector: &[f32], min_score: f32) -> Vec<(usize, bool)> {
    let mut features = signed_features_by_magnitude(vector);
    let mut suffix_squared = features
        .iter()
        .map(|(_, _, value)| value * value)
        .sum::<f32>();
    let mut prefix = Vec::new();
    for (index, sign, value) in features.drain(..) {
        if suffix_squared.sqrt() + VECTOR_EPSILON < min_score {
            break;
        }
        prefix.push((index, sign));
        suffix_squared = (suffix_squared - value * value).max(0.0);
    }
    prefix
}

fn all_signed_features(vector: &[f32]) -> Vec<(usize, bool)> {
    vector
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            if value.abs() <= VECTOR_EPSILON {
                None
            } else {
                Some((index, *value > 0.0))
            }
        })
        .collect()
}

fn signed_features_by_magnitude(vector: &[f32]) -> Vec<(usize, bool, f32)> {
    let mut features: Vec<(usize, bool, f32)> = vector
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            let magnitude = value.abs();
            if magnitude <= VECTOR_EPSILON {
                None
            } else {
                Some((index, *value > 0.0, magnitude))
            }
        })
        .collect();
    features.sort_by(|left, right| {
        right
            .2
            .partial_cmp(&left.2)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.0.cmp(&right.0))
    });
    features
}

fn comparison_bucket(kind: SimilarKind, node: &IndexedNode) -> Option<String> {
    match kind {
        SimilarKind::Similar => Some("similar:any".to_string()),
        SimilarKind::MergeCandidates => {
            if !is_merge_candidate_node(node) {
                return None;
            }
            merge_candidate_bucket(node)
                .map(|bucket| format!("merge:{bucket}:node-kind:{}", node.kind))
        }
    }
}

fn is_merge_candidate_node(node: &IndexedNode) -> bool {
    if node.kind != "document" && node.kind != "section" {
        return false;
    }
    let line_count = node.line_end.saturating_sub(node.line_start) + 1;
    line_count >= MERGE_CANDIDATE_MIN_LINES
}

fn merge_candidate_bucket(node: &IndexedNode) -> Option<String> {
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

fn merge_candidate_surface_kind(path: &str) -> Option<&'static str> {
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

fn is_alignment_or_log_surface(path: &str) -> bool {
    path.starts_with("agents/evals/results/")
        || path.starts_with("reports/")
        || path.starts_with(".agent-canon/")
        || path.starts_with(".agents/skills/")
        || path.starts_with(".claude/skills/")
        || path.starts_with("agents/templates/_partials/")
        || path.starts_with("codex-cli-guide/source/")
        || path.starts_with("codex-cli-guide/sections/")
}

fn is_document_text_path(path: &str) -> bool {
    let extension = Path::new(path)
        .extension()
        .and_then(|part| part.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    matches!(extension.as_str(), "md" | "markdown" | "txt" | "rst")
}

fn is_thin_doc_protected_surface(path: &str) -> bool {
    path == "README.md"
        || path == "AGENTS.md"
        || path == "ROOT_AGENTS.md"
        || path == "CLAUDE.md"
        || path.ends_with("/README.md")
        || path.starts_with(".github/")
        || path.starts_with(".codex/")
        || path.starts_with(".claude/")
}

fn is_thin_doc_non_candidate_surface(path: &str) -> bool {
    path.starts_with("agents/templates/") || path.starts_with("tests/fixtures/")
}

fn best_thin_doc_neighbor(
    node: &IndexedNode,
    document_nodes: &[IndexedNode],
    min_neighbor_score: f32,
) -> Option<ThinDocNeighbor> {
    let bucket = document_responsibility_bucket(&node.path);
    let mut best: Option<ThinDocNeighbor> = None;
    for candidate in document_nodes {
        if candidate.file_id == node.file_id {
            continue;
        }
        if document_responsibility_bucket(&candidate.path) != bucket {
            continue;
        }
        let score = cosine_score(&node.vector, &candidate.vector);
        if score + f32::EPSILON < min_neighbor_score {
            continue;
        }
        let replace = best
            .as_ref()
            .map(|current| score > current.score)
            .unwrap_or(true);
        if replace {
            best = Some(ThinDocNeighbor {
                node: candidate.clone(),
                score,
            });
        }
    }
    best
}

fn thin_doc_metrics(root: &Path, path: &str) -> ThinDocMetrics {
    let full_path = root.join(path);
    let text = fs::read_to_string(full_path).unwrap_or_default();
    let stripped = strip_dependency_manifest(&text);
    let mut meaningful_lines = 0;
    let mut link_lines = 0;
    let mut in_fence = false;
    for line in stripped.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("```") {
            in_fence = !in_fence;
            continue;
        }
        if trimmed.is_empty() || trimmed.starts_with('#') || is_markdown_table_rule(trimmed) {
            continue;
        }
        meaningful_lines += 1;
        if !in_fence && line_has_reference(trimmed) {
            link_lines += 1;
        }
    }
    let wrapper_phrase_hits = wrapper_phrase_hits(&stripped);
    let link_density = if meaningful_lines == 0 {
        0.0
    } else {
        link_lines as f32 / meaningful_lines as f32
    };
    ThinDocMetrics {
        total_lines: count_lines(&text),
        meaningful_lines,
        link_lines,
        wrapper_phrase_hits,
        link_density,
    }
}

fn is_markdown_table_rule(line: &str) -> bool {
    line.chars()
        .all(|ch| ch == '|' || ch == '-' || ch == ':' || ch.is_whitespace())
        && line.contains('-')
}

fn line_has_reference(line: &str) -> bool {
    line.contains("](")
        || line.contains(".md")
        || line.contains(".rst")
        || line.contains(".txt")
        || line.contains("`agents/")
        || line.contains("`documents/")
        || line.contains("`tools/")
}

fn wrapper_phrase_hits(text: &str) -> usize {
    let lower = text.to_ascii_lowercase();
    [
        "see ",
        "entrypoint",
        "compatibility",
        "mirror",
        "source of truth",
        "thin",
        "wrapper",
        "redirect",
        "instead",
    ]
    .iter()
    .filter(|phrase| lower.contains(**phrase))
    .count()
}

fn thin_doc_score(metrics: &ThinDocMetrics, best_score: f32, min_neighbor_score: f32) -> f32 {
    let content = thin_content_score(metrics.meaningful_lines);
    let neighbor = if best_score + f32::EPSILON >= min_neighbor_score {
        best_score
    } else {
        0.0
    };
    let link = metrics.link_density.min(1.0);
    let wrapper = (metrics.wrapper_phrase_hits as f32 / 2.0).min(1.0);
    (0.40 * content + 0.35 * neighbor + 0.15 * link + 0.10 * wrapper).clamp(0.0, 1.0)
}

fn has_thin_doc_shape(metrics: &ThinDocMetrics) -> bool {
    thin_content_score(metrics.meaningful_lines) > 0.0 || metrics.link_density >= 0.40
}

fn thin_content_score(meaningful_lines: usize) -> f32 {
    match meaningful_lines {
        0..=4 => 1.0,
        5..=8 => 0.85,
        9..=16 => 0.65,
        17..=24 => 0.35,
        _ => 0.0,
    }
}

fn thin_doc_reasons(
    metrics: &ThinDocMetrics,
    best_score: f32,
    min_neighbor_score: f32,
) -> Vec<String> {
    let mut reasons = Vec::new();
    if metrics.meaningful_lines <= 8 {
        reasons.push("low_meaningful_content".to_string());
    }
    if best_score + f32::EPSILON >= min_neighbor_score {
        reasons.push("high_single_target_similarity".to_string());
    }
    if metrics.link_density >= 0.40 {
        reasons.push("high_reference_density".to_string());
    }
    if metrics.wrapper_phrase_hits > 0 {
        reasons.push("wrapper_phrase".to_string());
    }
    reasons
}

fn thin_doc_action(
    metrics: &ThinDocMetrics,
    best_score: f32,
    min_neighbor_score: f32,
    protected: bool,
) -> String {
    if protected {
        return "keep_entrypoint".to_string();
    }
    if best_score + f32::EPSILON >= min_neighbor_score && metrics.meaningful_lines <= 16 {
        return "inline_into_target".to_string();
    }
    if metrics.link_density >= 0.50 && metrics.meaningful_lines <= 12 {
        return "replace_with_catalog_row".to_string();
    }
    if best_score + f32::EPSILON >= min_neighbor_score {
        return "merge_with_peer".to_string();
    }
    "manual_review".to_string()
}

fn document_responsibility_bucket(path: &str) -> &'static str {
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

fn responsibility_scope_bucket(path: &str) -> &'static str {
    let normalized = path.replace('\\', "/");
    if normalized.starts_with("agents/evals/") {
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
        || normalized == "CLAUDE.md"
        || normalized == "ROOT_AGENTS.md"
        || normalized.starts_with(".agents/")
        || normalized.starts_with(".claude/")
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

fn vector_to_blob(vector: &[f32]) -> Vec<u8> {
    let mut blob = Vec::with_capacity(vector.len() * 4);
    for value in vector {
        blob.extend_from_slice(&value.to_le_bytes());
    }
    blob
}

fn blob_to_vector(blob: &[u8]) -> Vec<f32> {
    blob.chunks_exact(4)
        .map(|chunk| {
            let mut bytes = [0_u8; 4];
            bytes.copy_from_slice(chunk);
            f32::from_le_bytes(bytes)
        })
        .collect()
}

fn max_path_pair_score(nodes: &[IndexedNode], left_path: &str, right_path: &str) -> Option<f32> {
    let left_nodes: Vec<&IndexedNode> =
        nodes.iter().filter(|node| node.path == left_path).collect();
    let right_nodes: Vec<&IndexedNode> = nodes
        .iter()
        .filter(|node| node.path == right_path)
        .collect();
    if left_nodes.is_empty() || right_nodes.is_empty() {
        return None;
    }
    let mut best = 0.0_f32;
    for left in left_nodes {
        for right in &right_nodes {
            best = best.max(cosine_score(&left.vector, &right.vector));
        }
    }
    Some(best)
}

fn reciprocal_rank(hits: &[ScoredNode], expected_paths: &[String]) -> f64 {
    for hit in hits.iter().take(10) {
        if expected_paths.contains(&hit.node.path) {
            return 1.0 / hit.rank.max(1) as f64;
        }
    }
    0.0
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

fn sort_pairs(pairs: &mut [SimilarPair]) {
    pairs.sort_by(|left, right| {
        right
            .score
            .partial_cmp(&left.score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.left.path.cmp(&right.left.path))
            .then_with(|| left.right.path.cmp(&right.right.path))
    });
}

fn sort_thin_docs(candidates: &mut [ThinDocCandidate]) {
    candidates.sort_by(|left, right| {
        right
            .thin_score
            .partial_cmp(&left.thin_score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.node.path.cmp(&right.node.path))
    });
}

fn print_search_results(args: &SearchArgs, results: &[ScoredNode]) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_search": "ok",
                "query": args.query,
                "results": results.iter().map(scored_node_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_search": "ok",
                "query_chars": args.query.chars().count(),
                "result_count": results.len()
            })
        );
        for result in results {
            println!("{}", scored_node_json(result));
        }
        return;
    }
    println!("SEMANTIC_INDEX_SEARCH=ok");
    for result in results {
        println!(
            "rank={} score={:.4} path={} lines={}-{} kind={}",
            result.rank,
            result.score,
            result.node.path,
            result.node.line_start,
            result.node.line_end,
            result.node.kind
        );
    }
}

fn print_similar_results(args: &SimilarArgs, pairs: &[SimilarPair]) {
    let status = match args.kind {
        SimilarKind::Similar => "SEMANTIC_INDEX_SIMILAR=ok",
        SimilarKind::MergeCandidates => "SEMANTIC_INDEX_MERGE_CANDIDATES=ok",
    };
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_pairs": "ok",
                "kind": match args.kind {
                    SimilarKind::Similar => "similar",
                    SimilarKind::MergeCandidates => "merge-candidates",
                },
                "results": pairs.iter().map(pair_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_pairs": "ok",
                "kind": match args.kind {
                    SimilarKind::Similar => "similar",
                    SimilarKind::MergeCandidates => "merge-candidates",
                },
                "result_count": pairs.len()
            })
        );
        for pair in pairs {
            println!("{}", pair_json(pair));
        }
        return;
    }
    println!("{status}");
    for pair in pairs {
        let left_responsibility = responsibility_scope_bucket(&pair.left.path);
        let right_responsibility = responsibility_scope_bucket(&pair.right.path);
        let candidate_bucket = merge_candidate_bucket(&pair.left)
            .filter(|bucket| {
                merge_candidate_bucket(&pair.right)
                    .as_ref()
                    .is_some_and(|right_bucket| right_bucket == bucket)
            })
            .unwrap_or_else(|| "similar:any".to_string());
        println!(
            "rank={} score={:.4} responsibility={} same_responsibility={} candidate_bucket={} left={}:{}-{} right={}:{}-{}",
            pair.rank,
            pair.score,
            left_responsibility,
            left_responsibility == right_responsibility,
            candidate_bucket,
            pair.left.path,
            pair.left.line_start,
            pair.left.line_end,
            pair.right.path,
            pair.right.line_start,
            pair.right.line_end
        );
    }
}

fn print_thin_docs_results(args: &ThinDocsArgs, candidates: &[ThinDocCandidate]) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_thin_docs": "ok",
                "results": candidates.iter().map(thin_doc_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_thin_docs": "ok",
                "result_count": candidates.len()
            })
        );
        for candidate in candidates {
            println!("{}", thin_doc_json(candidate));
        }
        return;
    }
    println!("SEMANTIC_INDEX_THIN_DOCS=ok");
    for candidate in candidates {
        let target = candidate
            .best_match
            .as_ref()
            .map(|neighbor| {
                format!(
                    "{}:{}-{}:{:.4}",
                    neighbor.node.path,
                    neighbor.node.line_start,
                    neighbor.node.line_end,
                    neighbor.score
                )
            })
            .unwrap_or_else(|| "none".to_string());
        println!(
            "rank={} thin_score={:.4} action={} path={} lines={}-{} target={} reasons={}",
            candidate.rank,
            candidate.thin_score,
            candidate.action,
            candidate.node.path,
            candidate.node.line_start,
            candidate.node.line_end,
            target,
            candidate.reasons.join(",")
        );
    }
}

fn print_eval_summary(report: &Value) {
    println!(
        "SEMANTIC_INDEX_EVAL={}",
        report
            .get("semantic_index_eval")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
    );
    if let Some(build) = report.get("build") {
        println!(
            "SEMANTIC_INDEX_EVAL_FILES={}",
            build
                .get("indexed_files")
                .and_then(Value::as_u64)
                .unwrap_or(0)
        );
        println!(
            "SEMANTIC_INDEX_EVAL_NODES={}",
            build
                .get("indexed_nodes")
                .and_then(Value::as_u64)
                .unwrap_or(0)
        );
    }
    for key in ["search", "similarity", "must_not_pairs"] {
        if let Some(section) = report.get(key) {
            println!(
                "SEMANTIC_INDEX_EVAL_{}_FAILED={}",
                key.to_ascii_uppercase(),
                section.get("failed").and_then(Value::as_u64).unwrap_or(0)
            );
        }
    }
}

fn scored_node_json(result: &ScoredNode) -> Value {
    json!({
        "rank": result.rank,
        "score": result.score,
        "path": result.node.path,
        "node_kind": result.node.kind,
        "line_start": result.node.line_start,
        "line_end": result.node.line_end
    })
}

fn pair_json(pair: &SimilarPair) -> Value {
    let left_responsibility = responsibility_scope_bucket(&pair.left.path);
    let right_responsibility = responsibility_scope_bucket(&pair.right.path);
    let left_candidate_bucket = merge_candidate_bucket(&pair.left);
    let right_candidate_bucket = merge_candidate_bucket(&pair.right);
    let candidate_bucket = if left_candidate_bucket == right_candidate_bucket {
        left_candidate_bucket
    } else {
        None
    };
    json!({
        "rank": pair.rank,
        "score": pair.score,
        "same_responsibility": left_responsibility == right_responsibility,
        "candidate_bucket": candidate_bucket,
        "left": {
            "path": pair.left.path,
            "responsibility_bucket": left_responsibility,
            "node_kind": pair.left.kind,
            "line_start": pair.left.line_start,
            "line_end": pair.left.line_end
        },
        "right": {
            "path": pair.right.path,
            "responsibility_bucket": right_responsibility,
            "node_kind": pair.right.kind,
            "line_start": pair.right.line_start,
            "line_end": pair.right.line_end
        }
    })
}

fn thin_doc_json(candidate: &ThinDocCandidate) -> Value {
    json!({
        "rank": candidate.rank,
        "thin_score": candidate.thin_score,
        "action": candidate.action,
        "reasons": candidate.reasons,
        "path": candidate.node.path,
        "node_kind": candidate.node.kind,
        "line_start": candidate.node.line_start,
        "line_end": candidate.node.line_end,
        "best_match": candidate.best_match.as_ref().map(|neighbor| {
            json!({
                "path": neighbor.node.path,
                "score": neighbor.score,
                "node_kind": neighbor.node.kind,
                "line_start": neighbor.node.line_start,
                "line_end": neighbor.node.line_end
            })
        }),
        "metrics": thin_doc_metrics_json(&candidate.metrics)
    })
}

fn thin_doc_metrics_json(metrics: &ThinDocMetrics) -> Value {
    json!({
        "total_lines": metrics.total_lines,
        "meaningful_lines": metrics.meaningful_lines,
        "link_lines": metrics.link_lines,
        "wrapper_phrase_hits": metrics.wrapper_phrase_hits,
        "link_density": metrics.link_density
    })
}

fn write_report(path: &Path, report: &Value) -> Result<(), String> {
    ensure_parent_dir(path)?;
    fs::write(path, format!("{}\n", report)).map_err(|error| error.to_string())
}

fn ensure_parent_dir(path: &Path) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn prepare_write_db(target: &Path) -> Result<PathBuf, String> {
    if is_local_temp_path(target) {
        let _ = fs::remove_file(target);
        return Ok(target.to_path_buf());
    }
    Ok(temp_db_path(target))
}

fn prepare_existing_write_db(target: &Path) -> Result<PathBuf, String> {
    if is_local_temp_path(target) {
        return Ok(target.to_path_buf());
    }
    let temp = temp_db_path(target);
    let _ = fs::remove_file(&temp);
    fs::copy(target, &temp).map_err(|error| {
        format!(
            "failed to copy cache db {} to temp {}: {error}",
            target.display(),
            temp.display()
        )
    })?;
    Ok(temp)
}

fn finish_write_db(write_db: &Path, target: &Path) -> Result<(), String> {
    if write_db == target {
        return Ok(());
    }
    ensure_parent_dir(target)?;
    let publish_path = sibling_publish_path(target);
    let _ = fs::remove_file(&publish_path);
    fs::copy(write_db, &publish_path).map_err(|error| {
        format!(
            "failed to copy temp cache db {} to publish path {}: {error}",
            write_db.display(),
            publish_path.display()
        )
    })?;
    fs::rename(&publish_path, target).map_err(|error| {
        let _ = fs::remove_file(&publish_path);
        format!(
            "failed to publish temp cache db {} to {}: {error}",
            publish_path.display(),
            target.display()
        )
    })?;
    let _ = fs::remove_file(write_db);
    Ok(())
}

fn sibling_publish_path(target: &Path) -> PathBuf {
    let file_name = target
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("index.sqlite");
    target.with_file_name(format!(".{file_name}.tmp-{}", run_id()))
}

fn temp_db_path(target: &Path) -> PathBuf {
    let digest = Sha256::digest(target.to_string_lossy().as_bytes());
    let suffix: String = digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    env::temp_dir().join(format!(
        "agent-canon-semantic-index-{suffix}-{}.sqlite",
        run_id()
    ))
}

fn is_local_temp_path(path: &Path) -> bool {
    path.is_absolute() && path.starts_with(env::temp_dir())
}

fn default_db_path(root: &Path) -> PathBuf {
    semantic_index_home()
        .join(repo_cache_key(root))
        .join("index.sqlite")
}

fn semantic_index_home() -> PathBuf {
    if let Ok(value) = env::var("AGENT_CANON_SEMANTIC_INDEX_HOME") {
        if !value.trim().is_empty() {
            return PathBuf::from(value);
        }
    }
    if let Ok(value) = env::var("HOME") {
        if !value.trim().is_empty() {
            return PathBuf::from(value)
                .join(".cache")
                .join("agent-canon")
                .join("semantic-index");
        }
    }
    env::temp_dir().join("agent-canon").join("semantic-index")
}

fn repo_cache_key(root: &Path) -> String {
    let canonical = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let display = canonical.to_string_lossy();
    let name = canonical
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("repo");
    let safe_name: String = name
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' {
                ch
            } else {
                '-'
            }
        })
        .collect();
    let trimmed_name = safe_name.trim_matches('-');
    let repo_name = if trimmed_name.is_empty() {
        "repo"
    } else {
        trimmed_name
    };
    let digest = Sha256::digest(display.as_bytes());
    let suffix: String = digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    format!("{repo_name}-{suffix}")
}

fn default_excludes() -> Vec<String> {
    [
        ".git",
        ".agent-canon/semantic-index",
        ".agent-canon/search-index",
        "target",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "reports/agents",
    ]
    .iter()
    .map(|value| value.to_string())
    .collect()
}

fn value_string(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn value_path(args: &[String], index: usize, flag: &str) -> Result<PathBuf, String> {
    Ok(PathBuf::from(value_string(args, index, flag)?))
}

fn value_usize(args: &[String], index: usize, flag: &str) -> Result<usize, String> {
    value_string(args, index, flag)?
        .parse::<usize>()
        .map_err(|_| format!("{flag} requires a positive integer"))
}

fn value_u64(args: &[String], index: usize, flag: &str) -> Result<u64, String> {
    value_string(args, index, flag)?
        .parse::<u64>()
        .map_err(|_| format!("{flag} requires a positive integer"))
}

fn value_f32(args: &[String], index: usize, flag: &str) -> Result<f32, String> {
    value_string(args, index, flag)?
        .parse::<f32>()
        .map_err(|_| format!("{flag} requires a numeric value"))
}

fn parse_format(value: &str) -> Result<OutputFormat, String> {
    match value {
        "text" => Ok(OutputFormat::Text),
        "json" => Ok(OutputFormat::Json),
        "jsonl" => Ok(OutputFormat::Jsonl),
        unknown => Err(format!("unknown format {unknown}")),
    }
}

fn validate_dim(dim: usize) -> Result<(), String> {
    if dim == 0 {
        return Err("--dim must be greater than zero".to_string());
    }
    Ok(())
}

fn validate_min_score(min_score: f32) -> Result<(), String> {
    if !(min_score.is_finite() && min_score > 0.0) {
        return Err("--min-score must be greater than zero".to_string());
    }
    Ok(())
}

fn string_field(value: &Value, key: &str) -> Result<String, String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(|value| value.to_string())
        .ok_or_else(|| format!("expected string field {key}"))
}

fn string_array_field(value: &Value, key: &str) -> Result<Vec<String>, String> {
    let Some(values) = value.get(key).and_then(Value::as_array) else {
        return Err(format!("expected array field {key}"));
    };
    values
        .iter()
        .map(|item| {
            item.as_str()
                .map(|value| value.to_string())
                .ok_or_else(|| format!("{key} must contain only strings"))
        })
        .collect()
}

fn path_metadata_size(path: &Path) -> Result<u64, String> {
    Ok(fs::metadata(path)
        .map_err(|error| format!("failed to stat {}: {error}", path.display()))?
        .len())
}

fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn count_lines(text: &str) -> usize {
    text.lines().count()
}

fn hex_hash(text: &str) -> String {
    let digest = Sha256::digest(text.as_bytes());
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn unix_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn run_id() -> String {
    format!("{}", unix_millis())
}

fn fail(scope: &str, message: String) -> i32 {
    eprintln!("SEMANTIC_INDEX_{scope}=fail");
    eprintln!("SEMANTIC_INDEX_ERROR={message}");
    1
}

fn print_usage() {
    eprintln!(
        "usage: agent-canon semantic-index <build|search|similar|merge-candidates|thin-docs|eval> [options]"
    );
    eprintln!("build: --root <repo-root> [--include path] [--db path] [--dim N]");
    eprintln!("search: (--query <text>|--query-file path|--query-stdin) [--root repo] [--db path] [--top-k N] [--format text|json|jsonl]");
    eprintln!("similar: [--root repo] [--db path] [--min-score S] [--cross-file-only] [--format text|json|jsonl]");
    eprintln!(
        "merge-candidates: [--root repo] [--db path] [--min-score S] [--format text|json|jsonl]"
    );
    eprintln!("thin-docs: [--root repo] [--db path] [--min-thin-score S] [--min-neighbor-score S] [--top-k N] [--format text|json|jsonl]");
    eprintln!("eval: --fixture <fixture-dir> [--db path] [--report path] [--format text|json]");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn markdown_segmentation_emits_document_sections_and_blocks() {
        let nodes = segment_text("documents/example.md", "# One\nalpha beta\n\n## Two\ngamma");
        assert!(nodes.iter().any(|node| node.kind == "document"));
        assert_eq!(
            nodes.iter().filter(|node| node.kind == "section").count(),
            2
        );
        assert_eq!(nodes.iter().filter(|node| node.kind == "block").count(), 2);
    }

    #[test]
    fn embedding_is_normalized_and_zero_safe() {
        let vector = embed_text("semantic index search", 32);
        let norm = vector.iter().map(|value| value * value).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 0.0001);
        let empty = embed_text("   ", 32);
        assert!(empty.iter().all(|value| *value == 0.0));
    }

    #[test]
    fn embedding_ignores_dependency_manifest_comment() {
        let with_manifest = "<!--\n@dependency-start\nresponsibility noisy header\n@dependency-end\n-->\n\n# Topic\nunique semantic payload";
        let without_manifest = "# Topic\nunique semantic payload";
        assert!(
            dot(
                &embed_text(with_manifest, 32),
                &embed_text(without_manifest, 32)
            ) > 0.99
        );
    }

    #[test]
    fn sqlite_build_and_search_roundtrip() {
        let root = unique_temp_dir("semantic-index-search");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::write(
            root.join("docs").join("update.md"),
            "# AgentCanon update\nsubmodule pin latest workflow",
        )
        .unwrap();
        fs::write(
            root.join("docs").join("security.md"),
            "# Security audit\nsecret scanner hardening",
        )
        .unwrap();
        let db = root.join(".agent-canon/semantic-index/index.sqlite");
        let build_args = BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from("docs")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        };
        let stats = build_index(&build_args).unwrap();
        assert_eq!(stats.files, 2);
        assert!(stats.nodes >= 4);
        let search_args = SearchArgs {
            root,
            db,
            query: "latest submodule update workflow".to_string(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            top_k: 3,
            format: OutputFormat::Json,
        };
        let hits = search_index(&search_args).unwrap();
        assert!(hits.iter().any(|hit| hit.node.path == "docs/update.md"));
    }

    #[test]
    fn parse_search_requires_query() {
        let args = vec![
            "search".to_string(),
            "--format".to_string(),
            "json".to_string(),
        ];
        let error = parse_args(&args).unwrap_err();
        assert!(error.contains("--query, --query-file, or --query-stdin is required"));
    }

    #[test]
    fn mismatched_search_dimension_returns_no_hits() {
        let root = unique_temp_dir("semantic-index-dim");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::write(
            root.join("docs").join("alpha.md"),
            "# Alpha\nsemantic vector",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        let build_args = BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from("docs")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 32,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        };
        build_index(&build_args).unwrap();
        let search_args = SearchArgs {
            root,
            db,
            query: "semantic vector".to_string(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            top_k: 5,
            format: OutputFormat::Json,
        };
        assert!(search_index(&search_args).unwrap().is_empty());
    }

    #[test]
    fn merge_candidates_exclude_same_file_pairs_by_default() {
        let root = unique_temp_dir("semantic-index-cross-file");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::write(
            root.join("docs").join("one.md"),
            "# One\nshared semantic topic\nwith enough lines\nfor merge candidates",
        )
        .unwrap();
        fs::write(
            root.join("docs").join("two.md"),
            "# Two\nshared semantic topic\nwith enough lines\nfor merge candidates",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        let build_args = BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from("docs")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        };
        build_index(&build_args).unwrap();
        let args = SimilarArgs {
            root,
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            min_score: 0.5,
            top_k: 20,
            format: OutputFormat::Json,
            cross_file_only: true,
            kind: SimilarKind::MergeCandidates,
        };
        let pairs = similar_pairs(&args).unwrap();
        assert!(!pairs.is_empty());
        assert!(pairs
            .iter()
            .all(|pair| pair.left.file_id != pair.right.file_id));
    }

    #[test]
    fn merge_candidates_stay_within_responsibility_bucket_on_full_repo_input() {
        let root = unique_temp_dir("semantic-index-merge-buckets");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::create_dir_all(root.join("src")).unwrap();
        let duplicate = "# Duplicate\nshared responsibility vector phrase\n\nshared responsibility vector phrase";
        fs::write(root.join("docs").join("one.md"), duplicate).unwrap();
        fs::write(root.join("docs").join("two.md"), duplicate).unwrap();
        fs::write(root.join("src").join("one.py"), duplicate).unwrap();
        let db = root.join("index.sqlite");
        let build_args = BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        };
        build_index(&build_args).unwrap();
        let args = SimilarArgs {
            root,
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            min_score: 0.95,
            top_k: 50,
            format: OutputFormat::Json,
            cross_file_only: true,
            kind: SimilarKind::MergeCandidates,
        };
        let pairs = similar_pairs(&args).unwrap();
        let doc_pair = pairs
            .iter()
            .find(|pair| pair.left.path.ends_with(".md") && pair.right.path.ends_with(".md"))
            .expect("docs pair should stay eligible inside one responsibility bucket");
        let doc_json = pair_json(doc_pair);
        assert_eq!(
            doc_json.get("same_responsibility").and_then(Value::as_bool),
            Some(true)
        );
        assert_eq!(
            doc_json
                .get("candidate_bucket")
                .and_then(Value::as_str)
                .unwrap_or(""),
            "docs:general:general"
        );
        assert!(pairs.iter().all(|pair| {
            let left_is_doc = pair.left.path.ends_with(".md");
            let right_is_doc = pair.right.path.ends_with(".md");
            let left_is_code = pair.left.path.ends_with(".py");
            let right_is_code = pair.right.path.ends_with(".py");
            !(left_is_doc && right_is_code || left_is_code && right_is_doc)
        }));
    }

    #[test]
    fn responsibility_scope_bucket_tracks_manifest_surfaces() {
        assert_eq!(
            responsibility_scope_bucket("agents/workflows/run.md"),
            "runtime-entrypoints"
        );
        assert_eq!(
            responsibility_scope_bucket("agents/evals/results/run.json"),
            "eval-and-hook-evidence"
        );
        assert_eq!(
            responsibility_scope_bucket("documents/search-coordination.md"),
            "shared-policy-documents"
        );
        assert_eq!(
            responsibility_scope_bucket("rust/agent-canon/src/semantic_index.rs"),
            "shared-tooling"
        );
        assert_eq!(
            responsibility_scope_bucket("tests/agent_tools/test_semantic.py"),
            "test-surfaces"
        );
        assert_eq!(
            merge_candidate_bucket(&IndexedNode {
                node_id: 1,
                file_id: 1,
                path: "documents/tools/semantic-index.md".to_string(),
                kind: "document".to_string(),
                line_start: 1,
                line_end: 10,
                vector: Vec::new(),
            })
            .as_deref(),
            Some("docs:shared-policy-documents:tool-doc")
        );
    }

    #[test]
    fn similar_pairs_can_cross_responsibility_bucket_for_alignment_search() {
        let root = unique_temp_dir("semantic-index-similar-cross-bucket");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::create_dir_all(root.join("src")).unwrap();
        let duplicate = "# Alignment\nsame exact phrase for code and docs";
        fs::write(root.join("docs").join("alignment.md"), duplicate).unwrap();
        fs::write(root.join("src").join("alignment.py"), duplicate).unwrap();
        let db = root.join("index.sqlite");
        let build_args = BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        };
        build_index(&build_args).unwrap();
        let args = SimilarArgs {
            root,
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            min_score: 0.99,
            top_k: 20,
            format: OutputFormat::Json,
            cross_file_only: true,
            kind: SimilarKind::Similar,
        };
        let pairs = similar_pairs(&args).unwrap();
        assert!(pairs.iter().any(|pair| {
            let left_is_doc = pair.left.path.ends_with(".md");
            let right_is_doc = pair.right.path.ends_with(".md");
            let left_is_code = pair.left.path.ends_with(".py");
            let right_is_code = pair.right.path.ends_with(".py");
            left_is_doc && right_is_code || left_is_code && right_is_doc
        }));
    }

    #[test]
    fn merge_candidates_skip_alignment_mirrors_and_eval_logs() {
        let root = unique_temp_dir("semantic-index-skip-alignment");
        fs::create_dir_all(root.join("documents")).unwrap();
        fs::create_dir_all(root.join(".agents/skills/example")).unwrap();
        fs::create_dir_all(root.join(".claude/skills/example")).unwrap();
        fs::create_dir_all(root.join("agents/evals/results/example")).unwrap();
        fs::create_dir_all(root.join("agents/templates/_partials")).unwrap();
        fs::create_dir_all(root.join("codex-cli-guide/source")).unwrap();
        fs::create_dir_all(root.join("codex-cli-guide/sections")).unwrap();
        let mergeable_duplicate =
            "# Same\nshared duplicate section text\nwith enough lines\nfor a merge candidate";
        fs::write(root.join("documents").join("one.md"), mergeable_duplicate).unwrap();
        fs::write(root.join("documents").join("two.md"), mergeable_duplicate).unwrap();
        fs::write(
            root.join(".agents/skills/example").join("SKILL.md"),
            mergeable_duplicate,
        )
        .unwrap();
        fs::write(
            root.join(".claude/skills/example").join("SKILL.md"),
            mergeable_duplicate,
        )
        .unwrap();
        fs::write(
            root.join("agents/evals/results/example").join("one.md"),
            mergeable_duplicate,
        )
        .unwrap();
        fs::write(
            root.join("agents/evals/results/example").join("two.md"),
            mergeable_duplicate,
        )
        .unwrap();
        fs::write(
            root.join("agents/templates/_partials").join("table.md"),
            mergeable_duplicate,
        )
        .unwrap();
        fs::write(
            root.join("codex-cli-guide/source").join("guide.full.md"),
            mergeable_duplicate,
        )
        .unwrap();
        fs::write(
            root.join("codex-cli-guide/sections").join("guide.md"),
            mergeable_duplicate,
        )
        .unwrap();
        let db = root.join("index.sqlite");
        let build_args = BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        };
        build_index(&build_args).unwrap();
        let args = SimilarArgs {
            root,
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            min_score: 0.95,
            top_k: 50,
            format: OutputFormat::Json,
            cross_file_only: true,
            kind: SimilarKind::MergeCandidates,
        };
        let pairs = similar_pairs(&args).unwrap();
        assert!(pairs
            .iter()
            .any(|pair| pair.left.path.starts_with("documents/")
                && pair.right.path.starts_with("documents/")));
        assert!(pairs.iter().all(|pair| {
            let paths = [&pair.left.path, &pair.right.path];
            !paths.iter().any(|path| {
                path.starts_with(".agents/")
                    || path.starts_with(".claude/")
                    || path.starts_with("agents/evals/results/")
                    || path.starts_with("agents/templates/_partials/")
                    || path.starts_with("codex-cli-guide/source/")
                    || path.starts_with("codex-cli-guide/sections/")
            })
        }));
    }

    #[test]
    fn merge_candidates_skip_tiny_heading_only_sections() {
        let root = unique_temp_dir("semantic-index-skip-tiny");
        fs::create_dir_all(root.join("documents")).unwrap();
        fs::write(
            root.join("documents").join("one.md"),
            "# One\n\n## Standard Flow\n\nlong duplicate body\nwith enough lines\nfor scoring",
        )
        .unwrap();
        fs::write(
            root.join("documents").join("two.md"),
            "# Two\n\n## Standard Flow\n\nlong duplicate body\nwith enough lines\nfor scoring",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        let build_args = BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        };
        build_index(&build_args).unwrap();
        let args = SimilarArgs {
            root,
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            min_score: 0.95,
            top_k: 50,
            format: OutputFormat::Json,
            cross_file_only: true,
            kind: SimilarKind::MergeCandidates,
        };
        let pairs = similar_pairs(&args).unwrap();
        assert!(pairs.iter().all(|pair| {
            let left_lines = pair.left.line_end.saturating_sub(pair.left.line_start) + 1;
            let right_lines = pair.right.line_end.saturating_sub(pair.right.line_start) + 1;
            left_lines >= MERGE_CANDIDATE_MIN_LINES && right_lines >= MERGE_CANDIDATE_MIN_LINES
        }));
    }

    #[test]
    fn thin_docs_reports_short_wrapper_from_vector_db() {
        let root = unique_temp_dir("semantic-index-thin-docs");
        fs::create_dir_all(root.join("documents")).unwrap();
        fs::write(
            root.join("documents").join("canonical.md"),
            "# Canonical\nsemantic index cache search routing document wrapper analysis\nsemantic index cache search routing document wrapper analysis\nsemantic index cache search routing document wrapper analysis",
        )
        .unwrap();
        fs::write(
            root.join("documents").join("wrapper.md"),
            "# Wrapper\nsemantic index cache search routing document wrapper analysis\nSee [canonical](canonical.md).\nThis compatibility entrypoint redirects to canonical semantic index cache search routing document.",
        )
        .unwrap();
        fs::write(
            root.join("documents").join("substantial.md"),
            "# Substantial\nalpha beta gamma delta epsilon\nzeta eta theta iota kappa\nlambda mu nu xi omicron\npi rho sigma tau upsilon\nphi chi psi omega",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        build_index(&BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        let candidates = thin_docs(&ThinDocsArgs {
            root,
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            min_thin_score: 0.60,
            min_neighbor_score: 0.75,
            top_k: 10,
            format: OutputFormat::Json,
        })
        .unwrap();
        let wrapper = candidates
            .iter()
            .find(|candidate| candidate.node.path == "documents/wrapper.md")
            .expect("wrapper should be reported as a thin doc");
        assert_eq!(wrapper.action, "inline_into_target");
        assert!(wrapper
            .reasons
            .contains(&"low_meaningful_content".to_string()));
        assert!(wrapper
            .reasons
            .contains(&"high_single_target_similarity".to_string()));
        assert_eq!(
            wrapper
                .best_match
                .as_ref()
                .map(|neighbor| neighbor.node.path.as_str()),
            Some("documents/canonical.md")
        );
        assert!(!candidates
            .iter()
            .any(|candidate| candidate.node.path == "documents/substantial.md"));
    }

    #[test]
    fn thin_docs_marks_readme_wrappers_as_protected_entrypoints() {
        let root = unique_temp_dir("semantic-index-thin-protected");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::write(
            root.join("README.md"),
            "# Project\nsemantic index cache search routing\nSee [docs](docs/README.md).",
        )
        .unwrap();
        fs::write(
            root.join("docs").join("README.md"),
            "# Docs\nsemantic index cache search routing\nSee [root](../README.md).",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        build_index(&BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        let candidates = thin_docs(&ThinDocsArgs {
            root,
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            min_thin_score: 0.60,
            min_neighbor_score: 0.75,
            top_k: 10,
            format: OutputFormat::Json,
        })
        .unwrap();
        let readme = candidates
            .iter()
            .find(|candidate| candidate.node.path == "README.md")
            .expect("protected README wrapper should still be visible");
        assert_eq!(readme.action, "keep_entrypoint");
        assert!(readme.reasons.contains(&"protected_entrypoint".to_string()));
    }

    #[test]
    fn parse_similar_rejects_non_positive_min_score() {
        let args = vec![
            "merge-candidates".to_string(),
            "--min-score".to_string(),
            "0".to_string(),
        ];
        let error = parse_args(&args).unwrap_err();
        assert!(error.contains("--min-score must be greater than zero"));
    }

    #[test]
    fn parse_search_accepts_query_file_and_jsonl_for_long_text() {
        let root = unique_temp_dir("semantic-index-query-file");
        let query_path = root.join("query.txt");
        fs::write(
            &query_path,
            "This is a long natural-language task description for semantic search.",
        )
        .unwrap();
        let args = vec![
            "search".to_string(),
            "--query-file".to_string(),
            query_path.display().to_string(),
            "--format".to_string(),
            "jsonl".to_string(),
        ];
        let ParsedArgs::Search(parsed) = parse_args(&args).unwrap() else {
            panic!("expected search args");
        };
        assert!(parsed.query.contains("natural-language task"));
        assert_eq!(parsed.format, OutputFormat::Jsonl);
    }

    #[test]
    fn default_db_path_lives_under_home_cache_and_outside_repo() {
        let root = unique_temp_dir("semantic-index-default-db");
        let db = default_db_path(&root);
        assert!(db.is_absolute());
        assert!(!db.starts_with(&root));
        assert!(db.ends_with("index.sqlite"));
        if let Ok(home) = env::var("HOME") {
            if !home.trim().is_empty() {
                assert!(db.starts_with(Path::new(&home)));
            }
        }
    }

    #[test]
    fn eval_fixture_reports_pass() {
        let fixture = unique_temp_dir("semantic-index-eval");
        let input = fixture.join("input").join("docs");
        fs::create_dir_all(&input).unwrap();
        fs::write(
            input.join("agent_update.md"),
            "# Agent update\nAgentCanon latest submodule pin workflow",
        )
        .unwrap();
        fs::write(
            input.join("agent_sync.md"),
            "# Agent sync\nAgentCanon latest submodule pin process",
        )
        .unwrap();
        fs::write(
            input.join("security.md"),
            "# Security\nsecret scanner credential audit",
        )
        .unwrap();
        fs::write(
            fixture.join("expected.json"),
            r#"{
              "queries": [
                {
                  "id": "agent_update",
                  "text": "AgentCanon latest submodule workflow",
                  "expected_paths": ["docs/agent_update.md"],
                  "min_recall_at_5": 1.0
                }
              ],
              "similar_pairs": [
                {
                  "id": "update_sync",
                  "left": "docs/agent_update.md",
                  "right": "docs/agent_sync.md",
                  "min_score": 0.40
                }
              ],
              "must_not_pairs": [
                {
                  "id": "update_security",
                  "left": "docs/agent_update.md",
                  "right": "docs/security.md",
                  "max_score": 0.95
                }
              ]
            }"#,
        )
        .unwrap();
        let args = EvalArgs {
            fixture: fixture.clone(),
            db: fixture.join("eval.sqlite"),
            report: None,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            top_k: 5,
            format: OutputFormat::Json,
        };
        let report = run_eval(&args).unwrap();
        assert_eq!(
            report
                .get("semantic_index_eval")
                .and_then(Value::as_str)
                .unwrap(),
            "pass"
        );
    }

    #[test]
    fn eval_run_returns_nonzero_when_quality_fails() {
        let fixture = unique_temp_dir("semantic-index-failing-eval");
        let input = fixture.join("input").join("docs");
        fs::create_dir_all(&input).unwrap();
        fs::write(input.join("only.md"), "# Only\nunrelated text").unwrap();
        fs::write(
            fixture.join("expected.json"),
            r#"{
              "queries": [
                {
                  "id": "missing",
                  "text": "not present",
                  "expected_paths": ["docs/missing.md"],
                  "min_recall_at_5": 1.0
                }
              ]
            }"#,
        )
        .unwrap();
        let args = vec![
            "eval".to_string(),
            "--fixture".to_string(),
            fixture.display().to_string(),
            "--db".to_string(),
            fixture.join("eval.sqlite").display().to_string(),
            "--format".to_string(),
            "json".to_string(),
        ];
        assert_eq!(run(&args), 1);
    }

    #[test]
    fn eval_missing_must_not_path_fails() {
        let fixture = unique_temp_dir("semantic-index-missing-path");
        let input = fixture.join("input").join("docs");
        fs::create_dir_all(&input).unwrap();
        fs::write(input.join("one.md"), "# One\nsemantic content").unwrap();
        fs::write(
            fixture.join("expected.json"),
            r#"{
              "must_not_pairs": [
                {
                  "id": "missing_path",
                  "left": "docs/one.md",
                  "right": "docs/missing.md",
                  "max_score": 0.9
                }
              ]
            }"#,
        )
        .unwrap();
        let args = EvalArgs {
            fixture: fixture.clone(),
            db: fixture.join("eval.sqlite"),
            report: None,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            top_k: 5,
            format: OutputFormat::Json,
        };
        let report = run_eval(&args).unwrap();
        assert_eq!(
            report
                .get("semantic_index_eval")
                .and_then(Value::as_str)
                .unwrap(),
            "fail"
        );
        assert!(report["must_not_pairs"]["results"][0]["missing_path"]
            .as_bool()
            .unwrap());
    }

    #[test]
    fn absolute_include_outside_root_is_rejected() {
        let root = unique_temp_dir("semantic-index-root");
        let outside = unique_temp_dir("semantic-index-outside");
        fs::write(outside.join("outside.md"), "# Outside\nexternal").unwrap();
        let args = BuildArgs {
            root: root.clone(),
            includes: vec![outside],
            excludes: default_excludes(),
            db: root.join("index.sqlite"),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        };
        let error = build_index(&args).unwrap_err();
        assert!(error.contains("outside --root"));
    }

    fn unique_temp_dir(prefix: &str) -> PathBuf {
        let path = env::temp_dir().join(format!("{prefix}-{}-{}", std::process::id(), run_id()));
        fs::create_dir_all(&path).unwrap();
        path
    }
}
