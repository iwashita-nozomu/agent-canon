// @dependency-start
// contract implementation
// responsibility Provides Rust-native semantic vector indexing, search, similarity, natural/discourse-relation, thin-doc, and eval CLI support.
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
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

const DEFAULT_PROVIDER: &str = "deterministic-dense-v1";
const DEFAULT_MODEL: &str = "hash-token-char-v1";
const LLAMA_SERVER_EMBEDDING_PROVIDER: &str = "llama-server-embedding";
const OPENAI_COMPATIBLE_EMBEDDING_PROVIDER: &str = "openai-compatible-embedding";
const DEFAULT_EMBEDDING_URL: &str = "http://127.0.0.1:8080/v1/embeddings";
const DEFAULT_REMOTE_EMBEDDING_MAX_CHARS: usize = 3000;
const DEFAULT_DIM: usize = 128;
const DEFAULT_TOP_K: usize = 10;
const DEFAULT_MIN_SCORE: f32 = 0.80;
const DEFAULT_MAX_FILE_BYTES: u64 = 1_000_000;
const DEFAULT_EMBEDDING_BATCH: usize = 16;
const DEFAULT_CONTEXT_CELLS: usize = 12;
const DEFAULT_CONTEXT_CELL_CHARS: usize = 900;
const DEFAULT_CONTEXT_TOTAL_CHARS: usize = 6000;
const DEFAULT_TREE_NODE_KIND: &str = "document";
const VECTOR_EPSILON: f32 = 1.0e-6;
const MERGE_CANDIDATE_MIN_LINES: i64 = 4;
const DEFAULT_MIN_THIN_SCORE: f32 = 0.50;
const DEFAULT_MIN_THIN_NEIGHBOR_SCORE: f32 = 0.86;
const DEFAULT_MIN_RELATION_SIMILARITY: f32 = 0.72;
const DEFAULT_MIN_KIND_OF_SCORE: f32 = 0.62;
const NATURAL_RELATION_FEATURE_FANOUT: usize = 64;
const DEFAULT_DISCOURSE_PROFILE: &str = "general";
const DEFAULT_MIN_DISCOURSE_NATURALNESS: f32 = 0.40;
const DEFAULT_DISCOURSE_WINDOW: usize = 3;
const DISCOURSE_TEXT_CHARS: usize = 1600;

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
    embedding_url: Option<String>,
    embedding_batch: usize,
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
    embedding_url: Option<String>,
    top_k: usize,
    format: OutputFormat,
}

#[derive(Debug, Clone)]
struct ContextPackArgs {
    root: PathBuf,
    db: PathBuf,
    query: String,
    provider: String,
    model: String,
    dim: usize,
    embedding_url: Option<String>,
    max_cells: usize,
    max_cell_chars: usize,
    max_total_chars: usize,
    format: OutputFormat,
}

#[derive(Debug, Clone)]
struct ResponsibilityTreeArgs {
    root: PathBuf,
    includes: Vec<PathBuf>,
    excludes: Vec<String>,
    db: PathBuf,
    provider: String,
    model: String,
    dim: usize,
    max_file_bytes: u64,
    node_kind: String,
    max_depth: Option<usize>,
    top_k: Option<usize>,
    include_vector: bool,
    check_directory_coverage: bool,
    report: Option<PathBuf>,
    format: OutputFormat,
}

#[derive(Debug, Clone)]
struct EmbedProviderArgs {
    root: PathBuf,
    db: PathBuf,
    provider: String,
    model: String,
    dim: usize,
    embedding_url: Option<String>,
    embedding_batch: usize,
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
struct NaturalRelationsArgs {
    root: PathBuf,
    db: PathBuf,
    provider: String,
    model: String,
    dim: usize,
    min_similarity: f32,
    min_kind_of_score: f32,
    top_k: usize,
    format: OutputFormat,
    cross_file_only: bool,
}

#[derive(Debug, Clone)]
struct DiscourseRelationsArgs {
    root: PathBuf,
    db: PathBuf,
    provider: String,
    model: String,
    dim: usize,
    profile: String,
    min_naturalness: f32,
    window: usize,
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
    embedding_url: Option<String>,
    top_k: usize,
    format: OutputFormat,
}

#[derive(Debug, Clone)]
struct ProviderSpec {
    provider: String,
    model: String,
    dim: usize,
    embedding_url: Option<String>,
}

#[derive(Debug, Clone)]
struct CompareProvidersArgs {
    db: PathBuf,
    query: Option<String>,
    left: ProviderSpec,
    right: ProviderSpec,
    min_score: f32,
    top_k: usize,
    report: Option<PathBuf>,
    format: OutputFormat,
}

#[derive(Debug, Clone)]
struct EvalOutputArgs {
    merge_candidates: Option<PathBuf>,
    thin_docs: Option<PathBuf>,
    search: Option<PathBuf>,
    report: Option<PathBuf>,
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
    ContextPack(ContextPackArgs),
    ResponsibilityTree(ResponsibilityTreeArgs),
    EmbedProvider(EmbedProviderArgs),
    Similar(SimilarArgs),
    ThinDocs(ThinDocsArgs),
    NaturalRelations(NaturalRelationsArgs),
    DiscourseRelations(DiscourseRelationsArgs),
    Eval(EvalArgs),
    CompareProviders(CompareProvidersArgs),
    EvalOutput(EvalOutputArgs),
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
struct SearchResults {
    results: Vec<ScoredNode>,
    stale_path_count: usize,
}

#[derive(Debug, Clone)]
struct ContextCell {
    rank: usize,
    score: f32,
    path: String,
    line_start: i64,
    line_end: i64,
    node_kind: String,
    responsibility_bucket: String,
    excerpt: String,
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
struct NaturalRelation {
    left: IndexedNode,
    right: IndexedNode,
    similarity_score: f32,
    left_is_kind_of_right_score: f32,
    right_is_kind_of_left_score: f32,
    relation_kind: String,
    rank: usize,
}

#[derive(Debug, Clone)]
struct DiscourseRelation {
    left: IndexedNode,
    right: IndexedNode,
    similarity_score: f32,
    connective_profile: String,
    relation_family: String,
    relation_schema: String,
    surface_phrase: String,
    inverse_surface_phrase: Option<String>,
    surface_order: String,
    logical_direction: String,
    naturalness_score: f32,
    inverse_naturalness_score: Option<f32>,
    direction_confidence: f32,
    ambiguity: String,
    gap_flags: Vec<String>,
    rank: usize,
}

#[derive(Debug, Clone)]
struct DiscourseRealization {
    relation_family: &'static str,
    relation_schema: &'static str,
    surface_phrase: &'static str,
    inverse_surface_phrase: Option<&'static str>,
    surface_order: &'static str,
    logical_direction: &'static str,
    profile_boost: f32,
}

#[derive(Debug, Clone)]
struct DirectoryCoverage {
    status: String,
    expected_directories: Vec<String>,
    db_directories: Vec<String>,
    missing_directories: Vec<String>,
    stale_directories: Vec<String>,
}

#[derive(Debug, Clone)]
struct DirectoryResponsibilityNode {
    path: String,
    parent: Option<String>,
    depth: usize,
    file_count: usize,
    node_count: usize,
    vector: Vec<f32>,
    vector_hash: String,
    dominant_responsibility: String,
    dominant_share: f64,
    responsibility_counts: Vec<(String, usize)>,
    node_kind_counts: Vec<(String, usize)>,
    parent_similarity: Option<f32>,
}

#[derive(Debug, Clone)]
struct ResponsibilityTreeReport {
    db: PathBuf,
    root: PathBuf,
    provider: String,
    model: String,
    dim: usize,
    node_kind: String,
    include_vector: bool,
    directories: Vec<DirectoryResponsibilityNode>,
    directory_count_total: usize,
    coverage: DirectoryCoverage,
}

#[derive(Debug, Clone)]
struct DirectoryAccumulator {
    files: HashSet<i64>,
    node_count: usize,
    vector_sum: Vec<f32>,
    responsibility_counts: HashMap<String, usize>,
    node_kind_counts: HashMap<String, usize>,
}

#[derive(Debug, Clone)]
struct BuildStats {
    files: usize,
    nodes: usize,
    embeddings: usize,
    db: PathBuf,
}

#[derive(Debug, Clone)]
struct EmbedStats {
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
        Ok(ParsedArgs::ContextPack(context_args)) => match context_pack(&context_args) {
            Ok(cells) => {
                print_context_pack_results(&context_args, &cells);
                0
            }
            Err(error) => fail("CONTEXT_PACK", error),
        },
        Ok(ParsedArgs::ResponsibilityTree(tree_args)) => match responsibility_tree(&tree_args) {
            Ok(report) => {
                let value = responsibility_tree_report_json(&report);
                if let Some(path) = &tree_args.report {
                    if let Err(error) = write_pretty_report(path, &value) {
                        return fail("RESPONSIBILITY_TREE_REPORT", error);
                    }
                }
                print_responsibility_tree_results(&tree_args, &report, &value);
                if tree_args.check_directory_coverage && report.coverage.status != "pass" {
                    1
                } else {
                    0
                }
            }
            Err(error) => fail("RESPONSIBILITY_TREE", error),
        },
        Ok(ParsedArgs::EmbedProvider(embed_args)) => match embed_existing_nodes(&embed_args) {
            Ok(stats) => {
                println!("SEMANTIC_INDEX_EMBED_PROVIDER=ok");
                println!("SEMANTIC_INDEX_DB={}", stats.db.display());
                println!("SEMANTIC_INDEX_NODES={}", stats.nodes);
                println!("SEMANTIC_INDEX_EMBEDDINGS={}", stats.embeddings);
                0
            }
            Err(error) => fail("EMBED_PROVIDER", error),
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
        Ok(ParsedArgs::NaturalRelations(relation_args)) => {
            match natural_relations(&relation_args) {
                Ok(results) => {
                    if let Err(error) = persist_natural_relations(&relation_args, &results) {
                        fail("NATURAL_RELATIONS_PERSIST", error)
                    } else {
                        print_natural_relation_results(&relation_args, &results);
                        0
                    }
                }
                Err(error) => fail("NATURAL_RELATIONS", error),
            }
        }
        Ok(ParsedArgs::DiscourseRelations(discourse_args)) => {
            match discourse_relations(&discourse_args) {
                Ok(results) => {
                    if let Err(error) = persist_discourse_relations(&discourse_args, &results) {
                        fail("DISCOURSE_RELATIONS_PERSIST", error)
                    } else {
                        print_discourse_relation_results(&discourse_args, &results);
                        0
                    }
                }
                Err(error) => fail("DISCOURSE_RELATIONS", error),
            }
        }
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
        Ok(ParsedArgs::CompareProviders(compare_args)) => match compare_providers(&compare_args) {
            Ok(report) => {
                if let Some(path) = &compare_args.report {
                    if let Err(error) = write_report(path, &report) {
                        return fail("COMPARE_PROVIDERS_REPORT", error);
                    }
                }
                if compare_args.format == OutputFormat::Json {
                    println!("{}", report);
                } else {
                    print_provider_compare_summary(&report);
                }
                0
            }
            Err(error) => fail("COMPARE_PROVIDERS", error),
        },
        Ok(ParsedArgs::EvalOutput(eval_output_args)) => match eval_output(&eval_output_args) {
            Ok(report) => {
                if let Some(path) = &eval_output_args.report {
                    if let Err(error) = write_report(path, &report) {
                        return fail("OUTPUT_EVAL_REPORT", error);
                    }
                }
                if eval_output_args.format == OutputFormat::Json {
                    println!("{}", report);
                } else {
                    print_output_eval_summary(&report);
                }
                if report
                    .get("semantic_index_output_eval")
                    .and_then(Value::as_str)
                    == Some("pass")
                {
                    0
                } else {
                    1
                }
            }
            Err(error) => fail("OUTPUT_EVAL", error),
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
        "context-pack" => Ok(ParsedArgs::ContextPack(parse_context_pack_args(
            &args[1..],
        )?)),
        "responsibility-tree" | "directory-tree" => Ok(ParsedArgs::ResponsibilityTree(
            parse_responsibility_tree_args(&args[1..])?,
        )),
        "embed-provider" => Ok(ParsedArgs::EmbedProvider(parse_embed_provider_args(
            &args[1..],
        )?)),
        "similar" => Ok(ParsedArgs::Similar(parse_similar_args(
            &args[1..],
            SimilarKind::Similar,
        )?)),
        "merge-candidates" => Ok(ParsedArgs::Similar(parse_similar_args(
            &args[1..],
            SimilarKind::MergeCandidates,
        )?)),
        "thin-docs" => Ok(ParsedArgs::ThinDocs(parse_thin_docs_args(&args[1..])?)),
        "natural-relations" | "nl-relations" => Ok(ParsedArgs::NaturalRelations(
            parse_natural_relations_args(&args[1..])?,
        )),
        "discourse-relations" | "discourse-edges" => Ok(ParsedArgs::DiscourseRelations(
            parse_discourse_relations_args(&args[1..])?,
        )),
        "eval" => Ok(ParsedArgs::Eval(parse_eval_args(&args[1..])?)),
        "compare-providers" => Ok(ParsedArgs::CompareProviders(parse_compare_providers_args(
            &args[1..],
        )?)),
        "eval-output" => Ok(ParsedArgs::EvalOutput(parse_eval_output_args(&args[1..])?)),
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
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            "--embedding-url" | "--embed-base-url" => {
                parsed.embedding_url = Some(value_string(args, index, "--embedding-url")?);
                index += 2;
            }
            "--embedding-batch" | "--embed-batch-size" => {
                parsed.embedding_batch = value_usize(args, index, "--embedding-batch")?;
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
    validate_provider_dim(&parsed.provider, parsed.dim)?;
    validate_embedding_batch(parsed.embedding_batch)?;
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
        embedding_url: None,
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
            "--embedding-url" | "--embed-base-url" => {
                parsed.embedding_url = Some(value_string(args, index, "--embedding-url")?);
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
    validate_provider_dim(&parsed.provider, parsed.dim)?;
    Ok(parsed)
}

fn parse_context_pack_args(args: &[String]) -> Result<ContextPackArgs, String> {
    let mut parsed = ContextPackArgs {
        root: PathBuf::from("."),
        db: default_db_path(Path::new(".")),
        query: String::new(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        embedding_url: None,
        max_cells: DEFAULT_CONTEXT_CELLS,
        max_cell_chars: DEFAULT_CONTEXT_CELL_CHARS,
        max_total_chars: DEFAULT_CONTEXT_TOTAL_CHARS,
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
            "--embedding-url" | "--embed-base-url" => {
                parsed.embedding_url = Some(value_string(args, index, "--embedding-url")?);
                index += 2;
            }
            "--top-k" | "--max-cells" => {
                parsed.max_cells = value_usize(args, index, "--max-cells")?;
                index += 2;
            }
            "--max-cell-chars" => {
                parsed.max_cell_chars = value_usize(args, index, "--max-cell-chars")?;
                index += 2;
            }
            "--max-total-chars" => {
                parsed.max_total_chars = value_usize(args, index, "--max-total-chars")?;
                index += 2;
            }
            "--format" => {
                parsed.format = parse_format(&value_string(args, index, "--format")?)?;
                index += 2;
            }
            unknown => return Err(format!("unknown context-pack option {unknown}")),
        }
    }
    if query_sources > 1 {
        return Err("use only one of --query, --query-file, or --query-stdin".to_string());
    }
    if parsed.query.trim().is_empty() {
        return Err("--query, --query-file, or --query-stdin is required".to_string());
    }
    validate_provider_dim(&parsed.provider, parsed.dim)?;
    validate_positive(parsed.max_cells, "--max-cells")?;
    validate_positive(parsed.max_cell_chars, "--max-cell-chars")?;
    validate_positive(parsed.max_total_chars, "--max-total-chars")?;
    Ok(parsed)
}

fn parse_responsibility_tree_args(args: &[String]) -> Result<ResponsibilityTreeArgs, String> {
    let mut parsed = ResponsibilityTreeArgs {
        root: PathBuf::from("."),
        includes: Vec::new(),
        excludes: default_excludes(),
        db: default_db_path(Path::new(".")),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        node_kind: DEFAULT_TREE_NODE_KIND.to_string(),
        max_depth: None,
        top_k: None,
        include_vector: false,
        check_directory_coverage: false,
        report: None,
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
            "--node-kind" => {
                parsed.node_kind = value_string(args, index, "--node-kind")?;
                index += 2;
            }
            "--max-depth" => {
                parsed.max_depth = Some(value_usize(args, index, "--max-depth")?);
                index += 2;
            }
            "--top-k" | "--limit" => {
                parsed.top_k = Some(value_usize(args, index, "--top-k")?);
                index += 2;
            }
            "--include-vector" | "--include-vectors" => {
                parsed.include_vector = true;
                index += 1;
            }
            "--check-directory-coverage" | "--check-coverage" => {
                parsed.check_directory_coverage = true;
                index += 1;
            }
            "--report" => {
                parsed.report = Some(value_path(args, index, "--report")?);
                index += 2;
            }
            "--format" => {
                parsed.format = parse_format(&value_string(args, index, "--format")?)?;
                index += 2;
            }
            unknown => return Err(format!("unknown responsibility-tree option {unknown}")),
        }
    }
    if parsed.includes.is_empty() {
        parsed.includes.push(PathBuf::from("."));
    }
    if parsed.node_kind.trim().is_empty() {
        return Err("--node-kind must not be empty".to_string());
    }
    validate_provider_dim_or_auto(&parsed.provider, parsed.dim, "--dim")?;
    Ok(parsed)
}

fn parse_embed_provider_args(args: &[String]) -> Result<EmbedProviderArgs, String> {
    let mut parsed = EmbedProviderArgs {
        root: PathBuf::from("."),
        db: default_db_path(Path::new(".")),
        provider: LLAMA_SERVER_EMBEDDING_PROVIDER.to_string(),
        model: env::var("AGENT_CANON_LOCAL_LLM_EMBEDDING_MODEL")
            .unwrap_or_else(|_| "local-embedding-model".to_string()),
        dim: 0,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            "--embedding-url" | "--embed-base-url" => {
                parsed.embedding_url = Some(value_string(args, index, "--embedding-url")?);
                index += 2;
            }
            "--embedding-batch" | "--embed-batch-size" => {
                parsed.embedding_batch = value_usize(args, index, "--embedding-batch")?;
                index += 2;
            }
            unknown => return Err(format!("unknown embed-provider option {unknown}")),
        }
    }
    validate_provider_dim(&parsed.provider, parsed.dim)?;
    validate_embedding_batch(parsed.embedding_batch)?;
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
    validate_provider_dim_or_auto(&parsed.provider, parsed.dim, "--dim")?;
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
    validate_provider_dim_or_auto(&parsed.provider, parsed.dim, "--dim")?;
    validate_min_score(parsed.min_thin_score)?;
    validate_min_score(parsed.min_neighbor_score)?;
    Ok(parsed)
}

fn parse_natural_relations_args(args: &[String]) -> Result<NaturalRelationsArgs, String> {
    let mut parsed = NaturalRelationsArgs {
        root: PathBuf::from("."),
        db: default_db_path(Path::new(".")),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        min_similarity: DEFAULT_MIN_RELATION_SIMILARITY,
        min_kind_of_score: DEFAULT_MIN_KIND_OF_SCORE,
        top_k: DEFAULT_TOP_K,
        format: OutputFormat::Text,
        cross_file_only: true,
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
            "--min-similarity" | "--min-score" => {
                parsed.min_similarity = value_f32(args, index, "--min-similarity")?;
                index += 2;
            }
            "--min-kind-of-score" => {
                parsed.min_kind_of_score = value_f32(args, index, "--min-kind-of-score")?;
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
            unknown => return Err(format!("unknown natural-relations option {unknown}")),
        }
    }
    validate_provider_dim_or_auto(&parsed.provider, parsed.dim, "--dim")?;
    validate_min_score(parsed.min_similarity)?;
    validate_min_score(parsed.min_kind_of_score)?;
    validate_positive(parsed.top_k, "--top-k")?;
    Ok(parsed)
}

fn parse_discourse_relations_args(args: &[String]) -> Result<DiscourseRelationsArgs, String> {
    let mut parsed = DiscourseRelationsArgs {
        root: PathBuf::from("."),
        db: default_db_path(Path::new(".")),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        profile: DEFAULT_DISCOURSE_PROFILE.to_string(),
        min_naturalness: DEFAULT_MIN_DISCOURSE_NATURALNESS,
        window: DEFAULT_DISCOURSE_WINDOW,
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
            "--profile" | "--connective-profile" => {
                parsed.profile = value_string(args, index, "--profile")?;
                index += 2;
            }
            "--min-naturalness" | "--min-score" => {
                parsed.min_naturalness = value_f32(args, index, "--min-naturalness")?;
                index += 2;
            }
            "--window" | "--max-window" => {
                parsed.window = value_usize(args, index, "--window")?;
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
            unknown => return Err(format!("unknown discourse-relations option {unknown}")),
        }
    }
    validate_provider_dim_or_auto(&parsed.provider, parsed.dim, "--dim")?;
    validate_min_score(parsed.min_naturalness)?;
    validate_positive(parsed.window, "--window")?;
    validate_positive(parsed.top_k, "--top-k")?;
    validate_discourse_profile(&parsed.profile)?;
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
        embedding_url: None,
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
            "--embedding-url" | "--embed-base-url" => {
                parsed.embedding_url = Some(value_string(args, index, "--embedding-url")?);
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
    validate_provider_dim(&parsed.provider, parsed.dim)?;
    if parsed.format == OutputFormat::Jsonl {
        return Err("--format jsonl is not supported for eval".to_string());
    }
    Ok(parsed)
}

fn parse_compare_providers_args(args: &[String]) -> Result<CompareProvidersArgs, String> {
    let mut parsed = CompareProvidersArgs {
        db: default_db_path(Path::new(".")),
        query: None,
        left: ProviderSpec {
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 0,
            embedding_url: None,
        },
        right: ProviderSpec {
            provider: LLAMA_SERVER_EMBEDDING_PROVIDER.to_string(),
            model: env::var("AGENT_CANON_LOCAL_LLM_EMBEDDING_MODEL")
                .unwrap_or_else(|_| "local-embedding-model".to_string()),
            dim: 0,
            embedding_url: None,
        },
        min_score: DEFAULT_MIN_SCORE,
        top_k: DEFAULT_TOP_K,
        report: None,
        format: OutputFormat::Text,
    };
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => {
                let root = value_path(args, index, "--root")?;
                if parsed.db == default_db_path(Path::new(".")) {
                    parsed.db = default_db_path(&root);
                }
                index += 2;
            }
            "--db" => {
                parsed.db = value_path(args, index, "--db")?;
                index += 2;
            }
            "--query" => {
                parsed.query = Some(value_string(args, index, "--query")?);
                index += 2;
            }
            "--query-file" => {
                let path = value_path(args, index, "--query-file")?;
                parsed.query = Some(
                    fs::read_to_string(&path)
                        .map_err(|error| format!("failed to read {}: {error}", path.display()))?,
                );
                index += 2;
            }
            "--left-provider" => {
                parsed.left.provider = value_string(args, index, "--left-provider")?;
                index += 2;
            }
            "--left-model" => {
                parsed.left.model = value_string(args, index, "--left-model")?;
                index += 2;
            }
            "--left-dim" => {
                parsed.left.dim = value_usize(args, index, "--left-dim")?;
                index += 2;
            }
            "--left-embedding-url" | "--left-embed-base-url" => {
                parsed.left.embedding_url =
                    Some(value_string(args, index, "--left-embedding-url")?);
                index += 2;
            }
            "--right-provider" => {
                parsed.right.provider = value_string(args, index, "--right-provider")?;
                index += 2;
            }
            "--right-model" => {
                parsed.right.model = value_string(args, index, "--right-model")?;
                index += 2;
            }
            "--right-dim" => {
                parsed.right.dim = value_usize(args, index, "--right-dim")?;
                index += 2;
            }
            "--right-embedding-url" | "--right-embed-base-url" => {
                parsed.right.embedding_url =
                    Some(value_string(args, index, "--right-embedding-url")?);
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
            "--report" => {
                parsed.report = Some(value_path(args, index, "--report")?);
                index += 2;
            }
            "--format" => {
                parsed.format = parse_format(&value_string(args, index, "--format")?)?;
                index += 2;
            }
            unknown => return Err(format!("unknown compare-providers option {unknown}")),
        }
    }
    validate_provider_dim_or_auto(&parsed.left.provider, parsed.left.dim, "--left-dim")?;
    validate_provider_dim_or_auto(&parsed.right.provider, parsed.right.dim, "--right-dim")?;
    validate_min_score(parsed.min_score)?;
    if parsed.format == OutputFormat::Jsonl {
        return Err("--format jsonl is not supported for compare-providers".to_string());
    }
    Ok(parsed)
}

fn parse_eval_output_args(args: &[String]) -> Result<EvalOutputArgs, String> {
    let mut parsed = EvalOutputArgs {
        merge_candidates: None,
        thin_docs: None,
        search: None,
        report: None,
        format: OutputFormat::Text,
    };
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--merge-candidates" => {
                parsed.merge_candidates = Some(value_path(args, index, "--merge-candidates")?);
                index += 2;
            }
            "--thin-docs" => {
                parsed.thin_docs = Some(value_path(args, index, "--thin-docs")?);
                index += 2;
            }
            "--search" => {
                parsed.search = Some(value_path(args, index, "--search")?);
                index += 2;
            }
            "--report" => {
                parsed.report = Some(value_path(args, index, "--report")?);
                index += 2;
            }
            "--format" => {
                parsed.format = parse_format(&value_string(args, index, "--format")?)?;
                index += 2;
            }
            unknown => return Err(format!("unknown eval-output option {unknown}")),
        }
    }
    if parsed.merge_candidates.is_none() && parsed.thin_docs.is_none() && parsed.search.is_none() {
        return Err(
            "at least one of --merge-candidates, --thin-docs, or --search is required".to_string(),
        );
    }
    if parsed.format == OutputFormat::Jsonl {
        return Err("--format jsonl is not supported for eval-output".to_string());
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
    let mut remote_embedding_inputs: Vec<(i64, String)> = Vec::new();
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
            if is_remote_embedding_provider(&args.provider) {
                remote_embedding_inputs.push((node_id, node.text.clone()));
            } else {
                let vector = embed_text(&node.text, args.dim);
                insert_embedding(&tx, node_id, &args.provider, &args.model, args.dim, &vector)?;
                embedding_count += 1;
            }
            inserted_ids.push(node_id);
            node_count += 1;
        }
        if line_count == 0 {
            continue;
        }
    }
    if is_remote_embedding_provider(&args.provider) {
        let texts: Vec<String> = remote_embedding_inputs
            .iter()
            .map(|(_, text)| text.clone())
            .collect();
        let vectors = embed_texts_for_provider(
            &args.provider,
            &args.model,
            args.dim,
            args.embedding_url.as_deref(),
            &texts,
            args.embedding_batch,
        )?;
        if vectors.len() != remote_embedding_inputs.len() {
            return Err(format!(
                "embedding provider returned {} vectors for {} nodes",
                vectors.len(),
                remote_embedding_inputs.len()
            ));
        }
        for ((node_id, _), vector) in remote_embedding_inputs.iter().zip(vectors.iter()) {
            insert_embedding(
                &tx,
                *node_id,
                &args.provider,
                &args.model,
                vector.len(),
                vector,
            )?;
            embedding_count += 1;
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

fn embed_existing_nodes(args: &EmbedProviderArgs) -> Result<EmbedStats, String> {
    let mut conn = open_cache_connection(&args.db)?;
    let node_texts =
        load_missing_node_texts(&conn, &args.root, &args.provider, &args.model, args.dim)?;
    if node_texts.is_empty() {
        return Ok(EmbedStats {
            nodes: 0,
            embeddings: 0,
            db: args.db.clone(),
        });
    }
    let mut embedding_count = 0;
    for chunk in node_texts.chunks(args.embedding_batch.max(1)) {
        let texts: Vec<String> = chunk.iter().map(|(_, text)| text.clone()).collect();
        let vectors = embed_texts_for_provider(
            &args.provider,
            &args.model,
            args.dim,
            args.embedding_url.as_deref(),
            &texts,
            args.embedding_batch,
        )?;
        let tx = conn.transaction().map_err(|error| error.to_string())?;
        for ((node_id, _), vector) in chunk.iter().zip(vectors.iter()) {
            insert_embedding(
                &tx,
                *node_id,
                &args.provider,
                &args.model,
                vector.len(),
                vector,
            )?;
            embedding_count += 1;
        }
        tx.commit().map_err(|error| error.to_string())?;
    }
    Ok(EmbedStats {
        nodes: node_texts.len(),
        embeddings: embedding_count,
        db: args.db.clone(),
    })
}

fn search_index(args: &SearchArgs) -> Result<SearchResults, String> {
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

fn context_pack(args: &ContextPackArgs) -> Result<Vec<ContextCell>, String> {
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

fn responsibility_tree(args: &ResponsibilityTreeArgs) -> Result<ResponsibilityTreeReport, String> {
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

fn similar_pairs(args: &SimilarArgs) -> Result<Vec<SimilarPair>, String> {
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, dim)?;
    Ok(similar_pairs_from_nodes(
        &nodes,
        args.kind,
        args.min_score,
        args.top_k,
        args.cross_file_only,
    ))
}

fn score_nodes(nodes: &[IndexedNode], query: &[f32], top_k: usize) -> Vec<ScoredNode> {
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

fn similar_pairs_from_nodes(
    nodes: &[IndexedNode],
    kind: SimilarKind,
    min_score: f32,
    top_k: usize,
    cross_file_only: bool,
) -> Vec<SimilarPair> {
    let mut bucket_ids: HashMap<String, usize> = HashMap::new();
    let mut buckets: Vec<Option<usize>> = Vec::with_capacity(nodes.len());
    for node in nodes {
        let bucket = comparison_bucket(kind, node);
        let bucket_id = bucket.map(|value| {
            let next_id = bucket_ids.len();
            *bucket_ids.entry(value).or_insert(next_id)
        });
        buckets.push(bucket_id);
    }
    let mut pairs: Vec<SimilarPair> = Vec::new();
    let mut inverted: HashMap<(usize, usize, bool), Vec<usize>> = HashMap::new();
    let prune_limit = top_k.saturating_mul(16).max(1024);
    for right_index in 0..nodes.len() {
        let right = &nodes[right_index];
        let Some(bucket) = buckets[right_index] else {
            continue;
        };
        let mut candidates: HashSet<usize> = HashSet::new();
        for (index, sign) in prefix_features(&right.vector, min_score) {
            if let Some(indices) = inverted.get(&(bucket, index, sign)) {
                candidates.extend(indices.iter().copied());
            }
        }
        for left_index in candidates {
            let left = &nodes[left_index];
            if cross_file_only && left.file_id == right.file_id {
                continue;
            }
            let score = cosine_score(&left.vector, &right.vector);
            if score + f32::EPSILON >= min_score {
                pairs.push(SimilarPair {
                    left: left.clone(),
                    right: right.clone(),
                    score,
                    rank: 0,
                });
                if pairs.len() > prune_limit {
                    sort_pairs(&mut pairs);
                    pairs.truncate(top_k);
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
    pairs.truncate(top_k);
    for (index, pair) in pairs.iter_mut().enumerate() {
        pair.rank = index + 1;
    }
    pairs
}

fn thin_docs(args: &ThinDocsArgs) -> Result<Vec<ThinDocCandidate>, String> {
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, dim)?;
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

fn natural_relations(args: &NaturalRelationsArgs) -> Result<Vec<NaturalRelation>, String> {
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let nodes: Vec<IndexedNode> = load_nodes(&conn, &args.provider, &args.model, dim)?
        .into_iter()
        .filter(is_natural_relation_node)
        .collect();
    let pairs = natural_relation_candidate_pairs_from_nodes(&nodes, args);
    let mut term_cache: HashMap<i64, Vec<String>> = HashMap::new();
    let mut relations = Vec::new();
    for pair in pairs {
        let left_terms = relation_terms_for_node(args, &pair.left, &mut term_cache)?;
        let right_terms = relation_terms_for_node(args, &pair.right, &mut term_cache)?;
        let left_is_kind_of_right = directed_kind_of_score(&left_terms, &right_terms, pair.score);
        let right_is_kind_of_left = directed_kind_of_score(&right_terms, &left_terms, pair.score);
        let relation_kind = classify_natural_relation(
            left_is_kind_of_right,
            right_is_kind_of_left,
            args.min_kind_of_score,
        )
        .to_string();
        relations.push(NaturalRelation {
            left: pair.left,
            right: pair.right,
            similarity_score: pair.score,
            left_is_kind_of_right_score: left_is_kind_of_right,
            right_is_kind_of_left_score: right_is_kind_of_left,
            relation_kind,
            rank: 0,
        });
    }
    sort_natural_relations(&mut relations);
    relations.truncate(args.top_k);
    for (index, relation) in relations.iter_mut().enumerate() {
        relation.rank = index + 1;
    }
    Ok(relations)
}

fn natural_relation_candidate_pairs_from_nodes(
    nodes: &[IndexedNode],
    args: &NaturalRelationsArgs,
) -> Vec<SimilarPair> {
    let mut pairs: Vec<SimilarPair> = Vec::new();
    let mut inverted: HashMap<(usize, bool), Vec<usize>> = HashMap::new();
    let prune_limit = args.top_k.saturating_mul(64).max(1024);
    for right_index in 0..nodes.len() {
        let right = &nodes[right_index];
        let mut candidates: HashSet<usize> = HashSet::new();
        for (index, sign) in prefix_features(&right.vector, args.min_similarity) {
            if let Some(indices) = inverted.get(&(index, sign)) {
                candidates.extend(
                    indices
                        .iter()
                        .rev()
                        .take(NATURAL_RELATION_FEATURE_FANOUT)
                        .copied(),
                );
            }
        }
        for left_index in candidates {
            let left = &nodes[left_index];
            if args.cross_file_only && left.file_id == right.file_id {
                continue;
            }
            let score = cosine_score(&left.vector, &right.vector);
            if score + f32::EPSILON >= args.min_similarity {
                pairs.push(SimilarPair {
                    left: left.clone(),
                    right: right.clone(),
                    score,
                    rank: 0,
                });
                if pairs.len() > prune_limit {
                    sort_pairs(&mut pairs);
                    pairs.truncate(args.top_k.saturating_mul(16).max(args.top_k));
                }
            }
        }
        for (index, sign) in all_signed_features(&right.vector) {
            inverted.entry((index, sign)).or_default().push(right_index);
        }
    }
    sort_pairs(&mut pairs);
    pairs.truncate(args.top_k.saturating_mul(16).max(args.top_k));
    for (index, pair) in pairs.iter_mut().enumerate() {
        pair.rank = index + 1;
    }
    pairs
}

fn discourse_relations(args: &DiscourseRelationsArgs) -> Result<Vec<DiscourseRelation>, String> {
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let mut nodes: Vec<IndexedNode> = load_nodes(&conn, &args.provider, &args.model, dim)?
        .into_iter()
        .filter(is_discourse_relation_node)
        .collect();
    nodes.sort_by(|left, right| {
        left.path
            .cmp(&right.path)
            .then_with(|| left.line_start.cmp(&right.line_start))
            .then_with(|| left.line_end.cmp(&right.line_end))
    });
    let pairs = discourse_candidate_pairs_from_nodes(&nodes, args.window);
    let mut text_cache: HashMap<i64, String> = HashMap::new();
    let mut relations = Vec::new();
    for pair in pairs {
        let left_text = discourse_text_for_node(args, &pair.left, &mut text_cache)?;
        let right_text = discourse_text_for_node(args, &pair.right, &mut text_cache)?;
        if let Some(mut relation) =
            score_discourse_pair(args, pair, left_text.as_str(), right_text.as_str())
        {
            if relation.naturalness_score + f32::EPSILON >= args.min_naturalness {
                relation.rank = 0;
                relations.push(relation);
            }
        }
    }
    sort_discourse_relations(&mut relations);
    relations.truncate(args.top_k);
    for (index, relation) in relations.iter_mut().enumerate() {
        relation.rank = index + 1;
    }
    Ok(relations)
}

fn discourse_candidate_pairs_from_nodes(nodes: &[IndexedNode], window: usize) -> Vec<SimilarPair> {
    let mut grouped: HashMap<&str, Vec<&IndexedNode>> = HashMap::new();
    for node in nodes {
        grouped.entry(&node.path).or_default().push(node);
    }
    let mut pairs = Vec::new();
    for file_nodes in grouped.values_mut() {
        file_nodes.sort_by(|left, right| {
            left.line_start
                .cmp(&right.line_start)
                .then_with(|| left.line_end.cmp(&right.line_end))
        });
        for left_index in 0..file_nodes.len() {
            let max_right = (left_index + window + 1).min(file_nodes.len());
            for right in file_nodes.iter().take(max_right).skip(left_index + 1) {
                let left = file_nodes[left_index];
                let score = cosine_score(&left.vector, &right.vector);
                pairs.push(SimilarPair {
                    left: left.clone(),
                    right: (*right).clone(),
                    score,
                    rank: 0,
                });
            }
        }
    }
    pairs
}

fn is_discourse_relation_node(node: &IndexedNode) -> bool {
    if is_alignment_or_log_surface(&node.path) {
        return false;
    }
    if !is_document_text_path(&node.path) {
        return false;
    }
    node.kind == "block"
}

fn discourse_text_for_node(
    args: &DiscourseRelationsArgs,
    node: &IndexedNode,
    cache: &mut HashMap<i64, String>,
) -> Result<String, String> {
    if let Some(text) = cache.get(&node.node_id) {
        return Ok(text.clone());
    }
    let text = context_excerpt(&args.root, node, DISCOURSE_TEXT_CHARS)?;
    cache.insert(node.node_id, text.clone());
    Ok(text)
}

fn score_discourse_pair(
    args: &DiscourseRelationsArgs,
    pair: SimilarPair,
    left_text: &str,
    right_text: &str,
) -> Option<DiscourseRelation> {
    let similarity_score = pair.score.max(0.0);
    let term_overlap = discourse_term_overlap(left_text, right_text);
    let mut best: Option<(DiscourseRealization, f32, f32, String, Vec<String>)> = None;
    for realization in discourse_realizations(&args.profile) {
        let surface_score = connective_surface_score(right_text, realization.surface_phrase);
        if surface_score <= 0.0 {
            continue;
        }
        let naturalness = (0.36 * similarity_score
            + 0.34 * surface_score
            + 0.18 * term_overlap
            + 0.12 * realization.profile_boost)
            .clamp(0.0, 1.0);
        let direction_confidence =
            discourse_direction_confidence(&realization, surface_score, term_overlap);
        let ambiguity = discourse_ambiguity(&realization, surface_score, right_text);
        let gap_flags = discourse_gap_flags(naturalness, direction_confidence, &ambiguity, true);
        if best
            .as_ref()
            .is_none_or(|(_, best_score, _, _, _)| naturalness > *best_score)
        {
            best = Some((
                realization,
                naturalness,
                direction_confidence,
                ambiguity,
                gap_flags,
            ));
        }
    }
    let (realization, naturalness_score, direction_confidence, ambiguity, gap_flags) = best
        .unwrap_or_else(|| {
            let naturalness =
                (0.62 * similarity_score + 0.26 * term_overlap + 0.12).clamp(0.0, 1.0);
            (
                implicit_discourse_realization(&args.profile),
                naturalness,
                0.55,
                "medium".to_string(),
                discourse_gap_flags(naturalness, 0.55, "medium", false),
            )
        });
    let inverse_naturalness_score = realization.inverse_surface_phrase.map(|_| {
        (naturalness_score
            * if realization.surface_phrase == "because" {
                1.02
            } else {
                0.96
            })
        .min(1.0)
    });
    Some(DiscourseRelation {
        left: pair.left,
        right: pair.right,
        similarity_score,
        connective_profile: args.profile.clone(),
        relation_family: realization.relation_family.to_string(),
        relation_schema: realization.relation_schema.to_string(),
        surface_phrase: realization.surface_phrase.to_string(),
        inverse_surface_phrase: realization.inverse_surface_phrase.map(str::to_string),
        surface_order: realization.surface_order.to_string(),
        logical_direction: realization.logical_direction.to_string(),
        naturalness_score,
        inverse_naturalness_score,
        direction_confidence,
        ambiguity,
        gap_flags,
        rank: 0,
    })
}

fn validate_discourse_profile(profile: &str) -> Result<(), String> {
    match profile {
        "general" | "experiment-report" | "methods-protocol" | "academic-argument"
        | "refactor-design" => Ok(()),
        unknown => Err(format!("unknown discourse profile {unknown}")),
    }
}

fn discourse_realizations(profile: &str) -> Vec<DiscourseRealization> {
    let mut realizations = vec![
        DiscourseRealization {
            relation_family: "causal",
            relation_schema: "reason_to_result",
            surface_phrase: "therefore",
            inverse_surface_phrase: Some("because"),
            surface_order: "reason_then_result",
            logical_direction: "left_to_right",
            profile_boost: 0.72,
        },
        DiscourseRealization {
            relation_family: "causal",
            relation_schema: "reason_to_result",
            surface_phrase: "as a result",
            inverse_surface_phrase: Some("because"),
            surface_order: "reason_then_result",
            logical_direction: "left_to_right",
            profile_boost: 0.70,
        },
        DiscourseRealization {
            relation_family: "causal",
            relation_schema: "reason_to_result",
            surface_phrase: "because",
            inverse_surface_phrase: Some("therefore"),
            surface_order: "result_then_reason",
            logical_direction: "right_to_left",
            profile_boost: 0.72,
        },
        DiscourseRealization {
            relation_family: "contrast",
            relation_schema: "contrast_peer",
            surface_phrase: "however",
            inverse_surface_phrase: Some("however"),
            surface_order: "peer_then_peer",
            logical_direction: "symmetric",
            profile_boost: 0.64,
        },
        DiscourseRealization {
            relation_family: "elaboration",
            relation_schema: "claim_to_example",
            surface_phrase: "for example",
            inverse_surface_phrase: Some("for instance"),
            surface_order: "claim_then_example",
            logical_direction: "left_to_right",
            profile_boost: 0.66,
        },
        DiscourseRealization {
            relation_family: "evidence",
            relation_schema: "evidence_to_claim",
            surface_phrase: "this shows",
            inverse_surface_phrase: Some("because"),
            surface_order: "evidence_then_claim",
            logical_direction: "left_to_right",
            profile_boost: 0.68,
        },
        DiscourseRealization {
            relation_family: "condition",
            relation_schema: "condition_to_outcome",
            surface_phrase: "if",
            inverse_surface_phrase: Some("only if"),
            surface_order: "condition_then_outcome",
            logical_direction: "left_to_right",
            profile_boost: 0.60,
        },
    ];
    match profile {
        "experiment-report" => {
            for realization in &mut realizations {
                if matches!(realization.relation_family, "causal" | "evidence") {
                    realization.profile_boost = (realization.profile_boost + 0.16).min(1.0);
                }
            }
        }
        "methods-protocol" => {
            for realization in &mut realizations {
                if matches!(realization.relation_family, "condition" | "causal") {
                    realization.profile_boost = (realization.profile_boost + 0.14).min(1.0);
                }
            }
        }
        "academic-argument" => {
            for realization in &mut realizations {
                if matches!(
                    realization.relation_family,
                    "causal" | "contrast" | "evidence" | "elaboration"
                ) {
                    realization.profile_boost = (realization.profile_boost + 0.10).min(1.0);
                }
            }
        }
        "refactor-design" => {
            for realization in &mut realizations {
                if matches!(realization.relation_family, "causal" | "condition") {
                    realization.profile_boost = (realization.profile_boost + 0.12).min(1.0);
                }
            }
        }
        _ => {}
    }
    realizations
}

fn implicit_discourse_realization(profile: &str) -> DiscourseRealization {
    let profile_boost = match profile {
        "experiment-report" => 0.62,
        "methods-protocol" => 0.58,
        "academic-argument" => 0.60,
        "refactor-design" => 0.56,
        _ => 0.50,
    };
    DiscourseRealization {
        relation_family: "continuation",
        relation_schema: "implicit_neighbor",
        surface_phrase: "implicit",
        inverse_surface_phrase: None,
        surface_order: "left_then_right",
        logical_direction: "left_to_right",
        profile_boost,
    }
}

fn connective_surface_score(text: &str, phrase: &str) -> f32 {
    let normalized = normalize_connective_surface(text);
    let phrase = phrase.to_ascii_lowercase();
    if normalized.starts_with(&phrase)
        && normalized
            .chars()
            .nth(phrase.chars().count())
            .is_none_or(|ch| ch.is_whitespace() || matches!(ch, ',' | ':' | ';' | '.'))
    {
        return 1.0;
    }
    let bounded = normalized.chars().take(220).collect::<String>();
    if bounded.contains(&format!(" {phrase} ")) {
        0.72
    } else {
        0.0
    }
}

fn normalize_connective_surface(text: &str) -> String {
    let lowered = text.trim_start().to_ascii_lowercase();
    let trimmed = lowered
        .trim_start_matches('#')
        .trim_start_matches('-')
        .trim_start_matches('*')
        .trim_start_matches(|ch: char| ch.is_ascii_digit() || ch == '.' || ch == ')')
        .trim_start();
    trimmed
        .chars()
        .map(|ch| if ch.is_ascii_alphanumeric() { ch } else { ' ' })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn discourse_term_overlap(left_text: &str, right_text: &str) -> f32 {
    let left_terms: HashSet<String> = relation_terms(left_text).into_iter().collect();
    let right_terms: HashSet<String> = relation_terms(right_text).into_iter().collect();
    if left_terms.is_empty() || right_terms.is_empty() {
        return 0.0;
    }
    let intersection = left_terms.intersection(&right_terms).count();
    let union = left_terms.union(&right_terms).count();
    if union == 0 {
        0.0
    } else {
        intersection as f32 / union as f32
    }
}

fn discourse_direction_confidence(
    realization: &DiscourseRealization,
    surface_score: f32,
    term_overlap: f32,
) -> f32 {
    if realization.logical_direction == "symmetric" {
        return 0.50;
    }
    (0.68 + 0.22 * surface_score + 0.10 * term_overlap).clamp(0.0, 1.0)
}

fn discourse_ambiguity(
    realization: &DiscourseRealization,
    surface_score: f32,
    right_text: &str,
) -> String {
    if realization.logical_direction == "symmetric" {
        return "medium".to_string();
    }
    if realization.surface_phrase == "if" || realization.surface_phrase == "because" {
        return "medium".to_string();
    }
    let normalized = normalize_connective_surface(right_text);
    let signal_count = discourse_realizations(DEFAULT_DISCOURSE_PROFILE)
        .iter()
        .filter(|candidate| connective_surface_score(&normalized, candidate.surface_phrase) > 0.0)
        .count();
    if signal_count > 1 {
        "high".to_string()
    } else if surface_score >= 0.99 {
        "low".to_string()
    } else {
        "medium".to_string()
    }
}

fn discourse_gap_flags(
    naturalness: f32,
    direction_confidence: f32,
    ambiguity: &str,
    explicit_connective: bool,
) -> Vec<String> {
    let mut flags = Vec::new();
    if !explicit_connective {
        flags.push("implicit_relation".to_string());
    }
    if naturalness < 0.50 {
        flags.push("weak_transition_evidence".to_string());
    }
    if direction_confidence < 0.60 {
        flags.push("low_direction_confidence".to_string());
    }
    if ambiguity == "high" {
        flags.push("ambiguous_connective".to_string());
    }
    flags
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
        embedding_url: args.embedding_url.clone(),
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: args.embedding_url.clone(),
            top_k: args.top_k.max(5),
            format: OutputFormat::Json,
        };
        let hits = search_index(&search_args)?;
        let top5: Vec<&ScoredNode> = hits.results.iter().take(5).collect();
        let found = expected_paths
            .iter()
            .filter(|expected_path| top5.iter().any(|hit| hit.node.path == **expected_path))
            .count();
        let recall = if expected_paths.is_empty() {
            1.0
        } else {
            found as f64 / expected_paths.len() as f64
        };
        let reciprocal_rank = reciprocal_rank(&hits.results, &expected_paths);
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
            "top_paths": hits.results.iter().take(5).map(|hit| hit.node.path.clone()).collect::<Vec<_>>()
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

fn compare_providers(args: &CompareProvidersArgs) -> Result<Value, String> {
    let conn = open_cache_connection(&args.db)?;
    let left_dim =
        resolve_provider_dim(&conn, &args.left.provider, &args.left.model, args.left.dim)?;
    let right_dim = resolve_provider_dim(
        &conn,
        &args.right.provider,
        &args.right.model,
        args.right.dim,
    )?;
    let left_nodes = load_nodes(&conn, &args.left.provider, &args.left.model, left_dim)?;
    let right_nodes = load_nodes(&conn, &args.right.provider, &args.right.model, right_dim)?;
    let left_pairs = similar_pairs_from_nodes(
        &left_nodes,
        SimilarKind::MergeCandidates,
        args.min_score,
        args.top_k,
        true,
    );
    let right_pairs = similar_pairs_from_nodes(
        &right_nodes,
        SimilarKind::MergeCandidates,
        args.min_score,
        args.top_k,
        true,
    );
    let merge_delta = compare_pair_sets(&left_pairs, &right_pairs);
    let search_delta = if let Some(query) = &args.query {
        let left_query = embed_one_for_provider(
            &args.left.provider,
            &args.left.model,
            left_dim,
            args.left.embedding_url.as_deref(),
            query,
        )?;
        let right_query = embed_one_for_provider(
            &args.right.provider,
            &args.right.model,
            right_dim,
            args.right.embedding_url.as_deref(),
            query,
        )?;
        let left_hits = score_nodes(&left_nodes, &left_query, args.top_k);
        let right_hits = score_nodes(&right_nodes, &right_query, args.top_k);
        Some(compare_search_sets(query, &left_hits, &right_hits))
    } else {
        None
    };
    Ok(json!({
        "semantic_index_provider_compare": "ok",
        "db": args.db,
        "top_k": args.top_k,
        "min_score": args.min_score,
        "left": {
            "provider": args.left.provider,
            "model": args.left.model,
            "dim": left_dim,
            "nodes": left_nodes.len(),
            "merge_candidates": left_pairs.len()
        },
        "right": {
            "provider": args.right.provider,
            "model": args.right.model,
            "dim": right_dim,
            "nodes": right_nodes.len(),
            "merge_candidates": right_pairs.len()
        },
        "merge_candidates": merge_delta,
        "search": search_delta
    }))
}

fn eval_output(args: &EvalOutputArgs) -> Result<Value, String> {
    let mut artifacts = Vec::new();
    let mut findings = Vec::new();
    if let Some(path) = &args.merge_candidates {
        artifacts.push(eval_merge_candidates_output(path, &mut findings)?);
    }
    if let Some(path) = &args.thin_docs {
        artifacts.push(eval_thin_docs_output(path, &mut findings)?);
    }
    if let Some(path) = &args.search {
        artifacts.push(eval_search_output(path, &mut findings)?);
    }
    let error_count = findings
        .iter()
        .filter(|finding| {
            finding
                .get("severity")
                .and_then(Value::as_str)
                .is_some_and(|severity| severity == "error")
        })
        .count();
    Ok(json!({
        "semantic_index_output_eval": if error_count == 0 { "pass" } else { "fail" },
        "artifacts": artifacts,
        "findings": findings,
        "error_count": error_count
    }))
}

fn eval_merge_candidates_output(path: &Path, findings: &mut Vec<Value>) -> Result<Value, String> {
    let (summary, results) = read_jsonl_artifact(path)?;
    let artifact = path.display().to_string();
    expect_summary_field(findings, &artifact, &summary, "semantic_index_pairs", "ok");
    expect_summary_field(findings, &artifact, &summary, "kind", "merge-candidates");
    check_result_count(findings, &artifact, &summary, results.len());
    for (index, result) in results.iter().enumerate() {
        let context = format!("result[{index}]");
        check_rank_score(findings, &artifact, &context, result, "score");
        if !result
            .get("same_responsibility")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "merge candidate is not same_responsibility=true",
            );
        }
        let candidate_bucket = result
            .get("candidate_bucket")
            .and_then(Value::as_str)
            .unwrap_or("");
        if candidate_bucket.is_empty() || candidate_bucket == "similar:any" {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "merge candidate is missing a concrete candidate_bucket",
            );
        }
        let Some(left) = result.get("left") else {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "missing left object",
            );
            continue;
        };
        let Some(right) = result.get("right") else {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "missing right object",
            );
            continue;
        };
        let left_responsibility = json_str(left, "responsibility_bucket");
        let right_responsibility = json_str(right, "responsibility_bucket");
        if left_responsibility.is_empty()
            || right_responsibility.is_empty()
            || left_responsibility != right_responsibility
        {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "left/right responsibility_bucket must be present and equal",
            );
        }
        if left_responsibility == "eval-and-hook-evidence" {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "eval-and-hook-evidence must not be emitted as merge evidence",
            );
        }
        if json_str(left, "node_kind") != json_str(right, "node_kind") {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "merge candidate node_kind differs across sides",
            );
        }
        if json_str(left, "path").is_empty() || json_str(right, "path").is_empty() {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "merge candidate left/right path must be present",
            );
        }
    }
    Ok(json!({
        "artifact": artifact,
        "kind": "merge-candidates",
        "results": results.len()
    }))
}

fn eval_thin_docs_output(path: &Path, findings: &mut Vec<Value>) -> Result<Value, String> {
    let (summary, results) = read_jsonl_artifact(path)?;
    let artifact = path.display().to_string();
    expect_summary_field(
        findings,
        &artifact,
        &summary,
        "semantic_index_thin_docs",
        "ok",
    );
    check_result_count(findings, &artifact, &summary, results.len());
    for (index, result) in results.iter().enumerate() {
        let context = format!("result[{index}]");
        check_rank_score(findings, &artifact, &context, result, "thin_score");
        let action = json_str(result, "action");
        if !matches!(
            action.as_str(),
            "keep_entrypoint"
                | "inline_into_target"
                | "replace_with_catalog_row"
                | "merge_with_peer"
                | "manual_review"
        ) {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "thin-doc action is missing or unknown",
            );
        }
        if json_str(result, "path").is_empty() {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "thin-doc path must be present",
            );
        }
        let protected = result
            .get("reasons")
            .and_then(Value::as_array)
            .is_some_and(|reasons| {
                reasons
                    .iter()
                    .any(|reason| reason.as_str() == Some("protected_entrypoint"))
            });
        if protected && action != "keep_entrypoint" {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "protected_entrypoint must use keep_entrypoint action",
            );
        }
    }
    Ok(json!({
        "artifact": artifact,
        "kind": "thin-docs",
        "results": results.len()
    }))
}

fn eval_search_output(path: &Path, findings: &mut Vec<Value>) -> Result<Value, String> {
    let (summary, results) = read_jsonl_artifact(path)?;
    let artifact = path.display().to_string();
    expect_summary_field(findings, &artifact, &summary, "semantic_index_search", "ok");
    check_result_count(findings, &artifact, &summary, results.len());
    if summary.get("query").is_some() {
        push_output_finding(
            findings,
            &artifact,
            "error",
            "summary",
            "search JSONL summary must not echo full query text",
        );
    }
    if summary.get("query_chars").and_then(Value::as_u64).is_none() {
        push_output_finding(
            findings,
            &artifact,
            "error",
            "summary",
            "search JSONL summary must include query_chars",
        );
    }
    for (index, result) in results.iter().enumerate() {
        let context = format!("result[{index}]");
        check_rank_score(findings, &artifact, &context, result, "score");
        if json_str(result, "path").is_empty() {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "search result path must be present",
            );
        }
    }
    Ok(json!({
        "artifact": artifact,
        "kind": "search",
        "results": results.len()
    }))
}

fn read_jsonl_artifact(path: &Path) -> Result<(Value, Vec<Value>), String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    let mut values = Vec::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let value = serde_json::from_str::<Value>(line).map_err(|error| {
            format!(
                "failed to parse {} line {} as JSON: {error}",
                path.display(),
                index + 1
            )
        })?;
        values.push(value);
    }
    if values.is_empty() {
        return Err(format!("{} is empty", path.display()));
    }
    let summary = values.remove(0);
    Ok((summary, values))
}

fn expect_summary_field(
    findings: &mut Vec<Value>,
    artifact: &str,
    summary: &Value,
    field: &str,
    expected: &str,
) {
    if summary.get(field).and_then(Value::as_str) != Some(expected) {
        push_output_finding(
            findings,
            artifact,
            "error",
            "summary",
            &format!("summary field {field} must equal {expected}"),
        );
    }
}

fn check_result_count(
    findings: &mut Vec<Value>,
    artifact: &str,
    summary: &Value,
    actual_count: usize,
) {
    if summary.get("result_count").and_then(Value::as_u64) != Some(actual_count as u64) {
        push_output_finding(
            findings,
            artifact,
            "error",
            "summary",
            "summary result_count must match JSONL result rows",
        );
    }
}

fn check_rank_score(
    findings: &mut Vec<Value>,
    artifact: &str,
    context: &str,
    result: &Value,
    score_field: &str,
) {
    if result.get("rank").and_then(Value::as_u64).unwrap_or(0) == 0 {
        push_output_finding(
            findings,
            artifact,
            "error",
            context,
            "rank must be positive",
        );
    }
    let Some(score) = result.get(score_field).and_then(Value::as_f64) else {
        push_output_finding(
            findings,
            artifact,
            "error",
            context,
            &format!("{score_field} must be present"),
        );
        return;
    };
    if !(0.0..=1.000_001).contains(&score) {
        push_output_finding(
            findings,
            artifact,
            "error",
            context,
            &format!("{score_field} must be in [0, 1]"),
        );
    }
}

fn json_str(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
}

fn push_output_finding(
    findings: &mut Vec<Value>,
    artifact: &str,
    severity: &str,
    context: &str,
    message: &str,
) {
    findings.push(json!({
        "artifact": artifact,
        "severity": severity,
        "context": context,
        "message": message
    }));
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

fn persist_natural_relations(
    args: &NaturalRelationsArgs,
    relations: &[NaturalRelation],
) -> Result<(), String> {
    let write_db = prepare_existing_write_db(&args.db)?;
    let conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    let run_id = run_id();
    conn.execute(
        "INSERT INTO analysis_runs(run_id, kind, created_at, params_json) VALUES (?1, ?2, ?3, ?4)",
        params![
            run_id,
            "natural-relations",
            unix_millis().to_string(),
            json!({
                "min_similarity": args.min_similarity,
                "min_kind_of_score": args.min_kind_of_score,
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
    for relation in relations {
        conn.execute(
            r#"
            INSERT INTO natural_language_relations(
                run_id, left_node_id, right_node_id, similarity_score,
                left_is_kind_of_right_score, right_is_kind_of_left_score,
                relation_kind, rank
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
            "#,
            params![
                run_id,
                relation.left.node_id,
                relation.right.node_id,
                relation.similarity_score,
                relation.left_is_kind_of_right_score,
                relation.right_is_kind_of_left_score,
                relation.relation_kind,
                relation.rank as i64,
            ],
        )
        .map_err(|error| error.to_string())?;
    }
    finish_write_db(&write_db, &args.db)?;
    Ok(())
}

fn persist_discourse_relations(
    args: &DiscourseRelationsArgs,
    relations: &[DiscourseRelation],
) -> Result<(), String> {
    let write_db = prepare_existing_write_db(&args.db)?;
    let conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    let run_id = run_id();
    conn.execute(
        "INSERT INTO analysis_runs(run_id, kind, created_at, params_json) VALUES (?1, ?2, ?3, ?4)",
        params![
            run_id,
            "discourse-relations",
            unix_millis().to_string(),
            json!({
                "profile": args.profile,
                "min_naturalness": args.min_naturalness,
                "window": args.window,
                "top_k": args.top_k,
                "provider": args.provider,
                "model": args.model,
                "dim": args.dim
            })
            .to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    for relation in relations {
        conn.execute(
            r#"
            INSERT INTO discourse_relations(
                run_id, left_node_id, right_node_id, similarity_score,
                connective_profile, relation_family, relation_schema,
                surface_phrase, inverse_surface_phrase, surface_order,
                logical_direction, naturalness_score, inverse_naturalness_score,
                direction_confidence, ambiguity, gap_flags_json, rank
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17)
            "#,
            params![
                run_id,
                relation.left.node_id,
                relation.right.node_id,
                relation.similarity_score,
                relation.connective_profile,
                relation.relation_family,
                relation.relation_schema,
                relation.surface_phrase,
                relation.inverse_surface_phrase,
                relation.surface_order,
                relation.logical_direction,
                relation.naturalness_score,
                relation.inverse_naturalness_score,
                relation.direction_confidence,
                relation.ambiguity,
                json!(relation.gap_flags).to_string(),
                relation.rank as i64,
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
        CREATE TABLE IF NOT EXISTS natural_language_relations(
            run_id TEXT NOT NULL,
            left_node_id INTEGER NOT NULL,
            right_node_id INTEGER NOT NULL,
            similarity_score REAL NOT NULL,
            left_is_kind_of_right_score REAL NOT NULL,
            right_is_kind_of_left_score REAL NOT NULL,
            relation_kind TEXT NOT NULL,
            rank INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS discourse_relations(
            run_id TEXT NOT NULL,
            left_node_id INTEGER NOT NULL,
            right_node_id INTEGER NOT NULL,
            similarity_score REAL NOT NULL,
            connective_profile TEXT NOT NULL,
            relation_family TEXT NOT NULL,
            relation_schema TEXT NOT NULL,
            surface_phrase TEXT NOT NULL,
            inverse_surface_phrase TEXT,
            surface_order TEXT NOT NULL,
            logical_direction TEXT NOT NULL,
            naturalness_score REAL NOT NULL,
            inverse_naturalness_score REAL,
            direction_confidence REAL NOT NULL,
            ambiguity TEXT NOT NULL,
            gap_flags_json TEXT NOT NULL,
            rank INTEGER NOT NULL
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
        DELETE FROM discourse_relations;
        DELETE FROM natural_language_relations;
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
        "INSERT OR REPLACE INTO embeddings(node_id, provider, model, dim, dtype, vector) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
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

fn load_file_paths(conn: &Connection) -> Result<Vec<String>, String> {
    let mut statement = conn
        .prepare("SELECT path FROM files ORDER BY path")
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| error.to_string())?;
    let mut paths = Vec::new();
    for row in rows {
        paths.push(row.map_err(|error| error.to_string())?);
    }
    Ok(paths)
}

fn indexed_node_path_exists(root: &Path, node: &IndexedNode) -> bool {
    let path = Path::new(&node.path);
    if path.is_absolute() {
        return path.exists();
    }
    root.join(path).exists()
}

fn provider_dimensions(
    conn: &Connection,
    provider: &str,
    model: &str,
) -> Result<Vec<usize>, String> {
    let mut statement = conn
        .prepare(
            r#"
            SELECT DISTINCT dim
            FROM embeddings
            WHERE provider = ?1 AND model = ?2
            ORDER BY dim
            "#,
        )
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map(params![provider, model], |row| {
            let dim: i64 = row.get(0)?;
            Ok(dim as usize)
        })
        .map_err(|error| error.to_string())?;
    let mut dims = Vec::new();
    for row in rows {
        dims.push(row.map_err(|error| error.to_string())?);
    }
    Ok(dims)
}

fn resolve_provider_dim(
    conn: &Connection,
    provider: &str,
    model: &str,
    requested_dim: usize,
) -> Result<usize, String> {
    if requested_dim > 0 {
        return Ok(requested_dim);
    }
    let dims = provider_dimensions(conn, provider, model)?;
    match dims.as_slice() {
        [dim] => Ok(*dim),
        [] => Err(format!(
            "no embeddings found for provider={provider} model={model}"
        )),
        _ => Err(format!(
            "multiple embedding dimensions found for provider={provider} model={model}; pass --dim"
        )),
    }
}

fn load_missing_node_texts(
    conn: &Connection,
    root: &Path,
    provider: &str,
    model: &str,
    dim: usize,
) -> Result<Vec<(i64, String)>, String> {
    let root_for_files = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let mut statement = conn
        .prepare(
            r#"
            SELECT n.node_id, f.path, n.line_start, n.line_end
            FROM nodes n
            JOIN files f ON f.file_id = n.file_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM embeddings e
                WHERE e.node_id = n.node_id
                  AND e.provider = ?1
                  AND e.model = ?2
                  AND (?3 = 0 OR e.dim = ?3)
            )
            ORDER BY n.node_id
            "#,
        )
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map(params![provider, model, dim as i64], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })
        .map_err(|error| error.to_string())?;
    let mut output = Vec::new();
    for row in rows {
        let (node_id, relative, line_start, line_end) = row.map_err(|error| error.to_string())?;
        let path = root_for_files.join(&relative);
        let text = fs::read_to_string(&path)
            .map_err(|error| format!("failed to read indexed file {}: {error}", path.display()))?;
        output.push((node_id, line_range_text(&text, line_start, line_end)));
    }
    Ok(output)
}

fn line_range_text(text: &str, line_start: i64, line_end: i64) -> String {
    text.lines()
        .enumerate()
        .filter_map(|(index, line)| {
            let line_number = index as i64 + 1;
            if line_number >= line_start && line_number <= line_end {
                Some(line)
            } else {
                None
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn context_excerpt(root: &Path, node: &IndexedNode, max_chars: usize) -> Result<String, String> {
    let path = root.join(&node.path);
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read context file {}: {error}", path.display()))?;
    let excerpt = line_range_text(&text, node.line_start, node.line_end);
    Ok(bound_excerpt(&excerpt, max_chars))
}

fn bound_excerpt(text: &str, max_chars: usize) -> String {
    let trimmed = text.trim();
    if trimmed.chars().count() <= max_chars {
        return trimmed.to_string();
    }
    trimmed.chars().take(max_chars).collect::<String>()
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

fn embed_one_for_provider(
    provider: &str,
    model: &str,
    dim: usize,
    embedding_url: Option<&str>,
    text: &str,
) -> Result<Vec<f32>, String> {
    let vectors =
        embed_texts_for_provider(provider, model, dim, embedding_url, &[text.to_string()], 1)?;
    vectors
        .into_iter()
        .next()
        .ok_or_else(|| "embedding provider returned no vector".to_string())
}

fn embed_texts_for_provider(
    provider: &str,
    model: &str,
    dim: usize,
    embedding_url: Option<&str>,
    texts: &[String],
    batch_size: usize,
) -> Result<Vec<Vec<f32>>, String> {
    if !is_remote_embedding_provider(provider) {
        validate_dim(dim)?;
        return Ok(texts.iter().map(|text| embed_text(text, dim)).collect());
    }
    let endpoint = embedding_endpoint(embedding_url);
    let expected_dim = remote_expected_dim(dim);
    let batch_size = batch_size.max(1);
    let max_chars = remote_embedding_max_chars();
    let mut output = Vec::with_capacity(texts.len());
    for chunk in texts.chunks(batch_size) {
        let bounded_chunk: Vec<String> = chunk
            .iter()
            .map(|text| bound_remote_embedding_text(text, max_chars))
            .collect();
        let mut vectors = request_openai_compatible_embeddings(&endpoint, model, &bounded_chunk)?;
        for vector in &mut vectors {
            if let Some(expected) = expected_dim {
                if vector.len() != expected {
                    return Err(format!(
                        "embedding dimension mismatch: expected {expected}, got {}",
                        vector.len()
                    ));
                }
            }
            normalize_vector(vector);
        }
        output.extend(vectors);
    }
    Ok(output)
}

fn is_remote_embedding_provider(provider: &str) -> bool {
    matches!(
        provider,
        LLAMA_SERVER_EMBEDDING_PROVIDER
            | OPENAI_COMPATIBLE_EMBEDDING_PROVIDER
            | "llama-server"
            | "openai-compatible"
    )
}

fn remote_expected_dim(dim: usize) -> Option<usize> {
    if dim == 0 || dim == DEFAULT_DIM {
        None
    } else {
        Some(dim)
    }
}

fn embedding_endpoint(explicit: Option<&str>) -> String {
    explicit
        .map(str::to_string)
        .or_else(|| env::var("AGENT_CANON_SEMANTIC_INDEX_EMBEDDING_URL").ok())
        .or_else(|| env::var("AGENT_CANON_LLAMA_EMBEDDING_URL").ok())
        .unwrap_or_else(|| DEFAULT_EMBEDDING_URL.to_string())
}

fn remote_embedding_max_chars() -> usize {
    env::var("AGENT_CANON_SEMANTIC_INDEX_EMBEDDING_MAX_CHARS")
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_REMOTE_EMBEDDING_MAX_CHARS)
}

fn bound_remote_embedding_text(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    text.chars().take(max_chars).collect()
}

fn request_openai_compatible_embeddings(
    endpoint: &str,
    model: &str,
    texts: &[String],
) -> Result<Vec<Vec<f32>>, String> {
    let payload = json!({
        "model": model,
        "input": texts,
    })
    .to_string();
    let curl = env::var("AGENT_CANON_EMBEDDING_CURL").unwrap_or_else(|_| "curl".to_string());
    let output = Command::new(curl)
        .arg("-fsS")
        .arg("--retry")
        .arg("2")
        .arg("--retry-delay")
        .arg("1")
        .arg("-H")
        .arg("Content-Type: application/json")
        .arg("-d")
        .arg(payload)
        .arg(endpoint)
        .output()
        .map_err(|error| format!("embedding request failed to launch curl: {error}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "embedding request failed for {endpoint}: status={} stderr={}",
            output.status,
            stderr.trim()
        ));
    }
    let body = String::from_utf8(output.stdout)
        .map_err(|error| format!("embedding response was not utf-8: {error}"))?;
    parse_openai_embeddings_response(&body, texts.len())
}

fn parse_openai_embeddings_response(
    body: &str,
    expected_count: usize,
) -> Result<Vec<Vec<f32>>, String> {
    let value: Value = serde_json::from_str(body.trim())
        .map_err(|error| format!("embedding response is not JSON: {error}"))?;
    let data = value
        .get("data")
        .and_then(Value::as_array)
        .ok_or_else(|| "embedding response missing data array".to_string())?;
    if data.len() != expected_count {
        return Err(format!(
            "embedding response count mismatch: expected {expected_count}, got {}",
            data.len()
        ));
    }
    let mut vectors: Vec<Option<Vec<f32>>> = vec![None; expected_count];
    for (position, item) in data.iter().enumerate() {
        let index = item
            .get("index")
            .and_then(Value::as_u64)
            .map(|value| value as usize)
            .unwrap_or(position);
        if index >= expected_count {
            return Err(format!("embedding response index {index} out of range"));
        }
        let array = item
            .get("embedding")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("embedding response data[{index}] missing embedding array"))?;
        if array.is_empty() {
            return Err(format!(
                "embedding response data[{index}] has empty embedding"
            ));
        }
        let mut vector = Vec::with_capacity(array.len());
        for value in array {
            let number = value.as_f64().ok_or_else(|| {
                format!("embedding response data[{index}] contains a non-numeric value")
            })?;
            if !number.is_finite() {
                return Err(format!(
                    "embedding response data[{index}] contains a non-finite value"
                ));
            }
            vector.push(number as f32);
        }
        vectors[index] = Some(vector);
    }
    vectors
        .into_iter()
        .enumerate()
        .map(|(index, vector)| {
            vector.ok_or_else(|| format!("embedding response missing vector for index {index}"))
        })
        .collect()
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
        || path.ends_with("/README.md")
        || path.starts_with(".github/")
        || path.starts_with(".codex/")
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

fn is_natural_relation_node(node: &IndexedNode) -> bool {
    if is_alignment_or_log_surface(&node.path) {
        return false;
    }
    if is_document_text_path(&node.path) {
        return matches!(node.kind.as_str(), "document" | "section");
    }
    matches!(node.kind.as_str(), "document" | "block")
}

fn relation_terms_for_node(
    args: &NaturalRelationsArgs,
    node: &IndexedNode,
    cache: &mut HashMap<i64, Vec<String>>,
) -> Result<Vec<String>, String> {
    if let Some(terms) = cache.get(&node.node_id) {
        return Ok(terms.clone());
    }
    let text = context_excerpt(&args.root, node, DEFAULT_REMOTE_EMBEDDING_MAX_CHARS)?;
    let terms = relation_terms(&format!("{}\n{}", node.path, text));
    cache.insert(node.node_id, terms.clone());
    Ok(terms)
}

fn relation_terms(text: &str) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut terms = Vec::new();
    for token in text_tokens(&strip_dependency_manifest(text)) {
        if token.len() < 3 || is_relation_stop_word(&token) {
            continue;
        }
        if seen.insert(token.clone()) {
            terms.push(token);
        }
    }
    terms
}

fn is_relation_stop_word(token: &str) -> bool {
    matches!(
        token,
        "the"
            | "and"
            | "for"
            | "with"
            | "that"
            | "this"
            | "from"
            | "into"
            | "onto"
            | "when"
            | "then"
            | "than"
            | "must"
            | "should"
            | "will"
            | "can"
            | "are"
            | "was"
            | "were"
            | "has"
            | "have"
            | "had"
            | "not"
            | "but"
            | "one"
            | "two"
            | "via"
            | "out"
            | "all"
            | "any"
            | "none"
            | "true"
            | "false"
    )
}

fn directed_kind_of_score(
    specific_terms: &[String],
    general_terms: &[String],
    similarity_score: f32,
) -> f32 {
    if specific_terms.is_empty() || general_terms.is_empty() {
        return 0.0;
    }
    let specific: HashSet<&str> = specific_terms.iter().map(String::as_str).collect();
    let matched_general_terms = general_terms
        .iter()
        .filter(|term| specific.contains(term.as_str()))
        .count();
    let coverage = matched_general_terms as f32 / general_terms.len() as f32;
    let length_balance = (specific_terms.len() as f32 / general_terms.len() as f32).min(1.0);
    (0.85 * coverage * length_balance + 0.15 * similarity_score).clamp(0.0, 1.0)
}

fn classify_natural_relation(
    left_is_kind_of_right_score: f32,
    right_is_kind_of_left_score: f32,
    min_kind_of_score: f32,
) -> &'static str {
    let left_high = left_is_kind_of_right_score + f32::EPSILON >= min_kind_of_score;
    let right_high = right_is_kind_of_left_score + f32::EPSILON >= min_kind_of_score;
    match (left_high, right_high) {
        (true, true) => "equivalent",
        (true, false) => "left_is_kind_of_right",
        (false, true) => "right_is_kind_of_left",
        (false, false) => "unrelated",
    }
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

fn compare_pair_sets(left: &[SimilarPair], right: &[SimilarPair]) -> Value {
    let left_keys: HashSet<String> = left.iter().map(pair_key).collect();
    let right_keys: HashSet<String> = right.iter().map(pair_key).collect();
    let shared: Vec<String> = sorted_intersection(&left_keys, &right_keys);
    let left_only: Vec<String> = sorted_difference(&left_keys, &right_keys)
        .into_iter()
        .take(10)
        .collect();
    let right_only: Vec<String> = sorted_difference(&right_keys, &left_keys)
        .into_iter()
        .take(10)
        .collect();
    let denominator = left_keys.len().max(right_keys.len()).max(1);
    json!({
        "left_count": left_keys.len(),
        "right_count": right_keys.len(),
        "shared_count": shared.len(),
        "overlap_ratio": shared.len() as f64 / denominator as f64,
        "shared": shared.into_iter().take(10).collect::<Vec<_>>(),
        "left_only": left_only,
        "right_only": right_only
    })
}

fn compare_search_sets(query: &str, left: &[ScoredNode], right: &[ScoredNode]) -> Value {
    let left_keys: HashSet<String> = left.iter().map(|hit| node_key(&hit.node)).collect();
    let right_keys: HashSet<String> = right.iter().map(|hit| node_key(&hit.node)).collect();
    let shared: Vec<String> = sorted_intersection(&left_keys, &right_keys);
    let denominator = left_keys.len().max(right_keys.len()).max(1);
    json!({
        "query_chars": query.chars().count(),
        "left_count": left_keys.len(),
        "right_count": right_keys.len(),
        "shared_count": shared.len(),
        "overlap_ratio": shared.len() as f64 / denominator as f64,
        "left_top": left.iter().take(10).map(scored_node_json).collect::<Vec<_>>(),
        "right_top": right.iter().take(10).map(scored_node_json).collect::<Vec<_>>(),
        "left_only": sorted_difference(&left_keys, &right_keys).into_iter().take(10).collect::<Vec<_>>(),
        "right_only": sorted_difference(&right_keys, &left_keys).into_iter().take(10).collect::<Vec<_>>()
    })
}

fn sorted_intersection(left: &HashSet<String>, right: &HashSet<String>) -> Vec<String> {
    let mut output: Vec<String> = left.intersection(right).cloned().collect();
    output.sort();
    output
}

fn sorted_difference(left: &HashSet<String>, right: &HashSet<String>) -> Vec<String> {
    let mut output: Vec<String> = left.difference(right).cloned().collect();
    output.sort();
    output
}

fn sorted_strings(values: &HashSet<String>) -> Vec<String> {
    let mut output: Vec<String> = values.iter().cloned().collect();
    output.sort_by(|left, right| {
        directory_depth(left)
            .cmp(&directory_depth(right))
            .then_with(|| left.cmp(right))
    });
    output
}

fn sorted_counts(counts: &HashMap<String, usize>) -> Vec<(String, usize)> {
    let mut output: Vec<(String, usize)> = counts
        .iter()
        .map(|(key, value)| (key.clone(), *value))
        .collect();
    output.sort_by(|left, right| right.1.cmp(&left.1).then_with(|| left.0.cmp(&right.0)));
    output
}

fn pair_key(pair: &SimilarPair) -> String {
    let left = node_key(&pair.left);
    let right = node_key(&pair.right);
    if left <= right {
        format!("{left}|{right}")
    } else {
        format!("{right}|{left}")
    }
}

fn node_key(node: &IndexedNode) -> String {
    format!(
        "{}:{}:{}-{}",
        node.path, node.kind, node.line_start, node.line_end
    )
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

fn sort_natural_relations(relations: &mut [NaturalRelation]) {
    relations.sort_by(|left, right| {
        right
            .left_is_kind_of_right_score
            .max(right.right_is_kind_of_left_score)
            .partial_cmp(
                &left
                    .left_is_kind_of_right_score
                    .max(left.right_is_kind_of_left_score),
            )
            .unwrap_or(Ordering::Equal)
            .then_with(|| {
                right
                    .similarity_score
                    .partial_cmp(&left.similarity_score)
                    .unwrap_or(Ordering::Equal)
            })
            .then_with(|| left.left.path.cmp(&right.left.path))
            .then_with(|| left.right.path.cmp(&right.right.path))
    });
}

fn sort_discourse_relations(relations: &mut [DiscourseRelation]) {
    relations.sort_by(|left, right| {
        right
            .naturalness_score
            .partial_cmp(&left.naturalness_score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| {
                right
                    .direction_confidence
                    .partial_cmp(&left.direction_confidence)
                    .unwrap_or(Ordering::Equal)
            })
            .then_with(|| left.left.path.cmp(&right.left.path))
            .then_with(|| left.left.line_start.cmp(&right.left.line_start))
            .then_with(|| left.right.line_start.cmp(&right.right.line_start))
    });
}

fn print_search_results(args: &SearchArgs, search_results: &SearchResults) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_search": "ok",
                "query": args.query,
                "stale_path_count": search_results.stale_path_count,
                "results": search_results.results.iter().map(scored_node_json).collect::<Vec<_>>()
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
                "result_count": search_results.results.len(),
                "stale_path_count": search_results.stale_path_count
            })
        );
        for result in &search_results.results {
            println!("{}", scored_node_json(result));
        }
        return;
    }
    println!("SEMANTIC_INDEX_SEARCH=ok");
    println!(
        "SEMANTIC_INDEX_STALE_PATHS_SKIPPED={}",
        search_results.stale_path_count
    );
    for result in &search_results.results {
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

fn print_context_pack_results(args: &ContextPackArgs, cells: &[ContextCell]) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_context_pack": "ok",
                "query_chars": args.query.chars().count(),
                "provider": args.provider,
                "model": args.model,
                "max_cells": args.max_cells,
                "max_cell_chars": args.max_cell_chars,
                "max_total_chars": args.max_total_chars,
                "cell_count": cells.len(),
                "cells": cells.iter().map(context_cell_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_context_pack": "ok",
                "query_chars": args.query.chars().count(),
                "provider": args.provider,
                "model": args.model,
                "cell_count": cells.len()
            })
        );
        for cell in cells {
            println!("{}", context_cell_json(cell));
        }
        return;
    }
    println!("SEMANTIC_INDEX_CONTEXT_PACK=ok");
    println!("SEMANTIC_INDEX_CONTEXT_PACK_CELLS={}", cells.len());
    for cell in cells {
        println!(
            "CELL rank={} score={:.4} responsibility={} path={} lines={}-{} kind={} chars={}",
            cell.rank,
            cell.score,
            cell.responsibility_bucket,
            cell.path,
            cell.line_start,
            cell.line_end,
            cell.node_kind,
            cell.excerpt.chars().count()
        );
        println!("EXCERPT_BEGIN");
        println!("{}", cell.excerpt);
        println!("EXCERPT_END");
    }
}

fn print_responsibility_tree_results(
    args: &ResponsibilityTreeArgs,
    report: &ResponsibilityTreeReport,
    value: &Value,
) {
    if args.format == OutputFormat::Json {
        println!("{value}");
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_responsibility_tree": "ok",
                "provider": report.provider,
                "model": report.model,
                "dim": report.dim,
                "node_kind": report.node_kind,
                "directory_count_total": report.directory_count_total,
                "directory_count_returned": report.directories.len(),
                "coverage_status": report.coverage.status,
                "missing_directories": report.coverage.missing_directories.len(),
                "stale_directories": report.coverage.stale_directories.len()
            })
        );
        for directory in &report.directories {
            println!("{}", directory_node_json(directory, report.include_vector));
        }
        return;
    }
    println!("SEMANTIC_INDEX_RESPONSIBILITY_TREE=ok");
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_DB={}",
        report.db.display()
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_DIRECTORIES={}",
        report.directory_count_total
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_RETURNED={}",
        report.directories.len()
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_COVERAGE={}",
        report.coverage.status
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_MISSING_DIRS={}",
        report.coverage.missing_directories.len()
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_STALE_DIRS={}",
        report.coverage.stale_directories.len()
    );
    if let Some(path) = &args.report {
        println!(
            "SEMANTIC_INDEX_RESPONSIBILITY_TREE_REPORT={}",
            path.display()
        );
    }
    for directory in &report.directories {
        let parent_similarity = directory
            .parent_similarity
            .map(|value| format!("{value:.4}"))
            .unwrap_or_else(|| "none".to_string());
        println!(
            "DIR path={} parent={} depth={} files={} nodes={} responsibility={} share={:.3} parent_similarity={} vector_hash={}",
            directory.path,
            directory.parent.as_deref().unwrap_or("none"),
            directory.depth,
            directory.file_count,
            directory.node_count,
            directory.dominant_responsibility,
            directory.dominant_share,
            parent_similarity,
            directory.vector_hash
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

fn print_natural_relation_results(args: &NaturalRelationsArgs, relations: &[NaturalRelation]) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_natural_relations": "ok",
                "min_similarity": args.min_similarity,
                "min_kind_of_score": args.min_kind_of_score,
                "results": relations.iter().map(natural_relation_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_natural_relations": "ok",
                "min_similarity": args.min_similarity,
                "min_kind_of_score": args.min_kind_of_score,
                "result_count": relations.len()
            })
        );
        for relation in relations {
            println!("{}", natural_relation_json(relation));
        }
        return;
    }
    println!("SEMANTIC_INDEX_NATURAL_RELATIONS=ok");
    for relation in relations {
        println!(
            "rank={} relation={} similarity={:.4} left_kind_of_right={:.4} right_kind_of_left={:.4} left={}:{}-{} right={}:{}-{}",
            relation.rank,
            relation.relation_kind,
            relation.similarity_score,
            relation.left_is_kind_of_right_score,
            relation.right_is_kind_of_left_score,
            relation.left.path,
            relation.left.line_start,
            relation.left.line_end,
            relation.right.path,
            relation.right.line_start,
            relation.right.line_end
        );
    }
}

fn print_discourse_relation_results(
    args: &DiscourseRelationsArgs,
    relations: &[DiscourseRelation],
) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_discourse_relations": "ok",
                "profile": args.profile,
                "min_naturalness": args.min_naturalness,
                "window": args.window,
                "results": relations.iter().map(discourse_relation_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_discourse_relations": "ok",
                "profile": args.profile,
                "min_naturalness": args.min_naturalness,
                "window": args.window,
                "result_count": relations.len()
            })
        );
        for relation in relations {
            println!("{}", discourse_relation_json(relation));
        }
        return;
    }
    println!("SEMANTIC_INDEX_DISCOURSE_RELATIONS=ok");
    println!("SEMANTIC_INDEX_DISCOURSE_PROFILE={}", args.profile);
    for relation in relations {
        println!(
            "rank={} family={} schema={} phrase={} inverse={} naturalness={:.4} direction={} confidence={:.4} ambiguity={} left={}:{}-{} right={}:{}-{} flags={}",
            relation.rank,
            relation.relation_family,
            relation.relation_schema,
            relation.surface_phrase,
            relation
                .inverse_surface_phrase
                .as_deref()
                .unwrap_or("none"),
            relation.naturalness_score,
            relation.logical_direction,
            relation.direction_confidence,
            relation.ambiguity,
            relation.left.path,
            relation.left.line_start,
            relation.left.line_end,
            relation.right.path,
            relation.right.line_start,
            relation.right.line_end,
            relation.gap_flags.join(",")
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

fn print_output_eval_summary(report: &Value) {
    println!(
        "SEMANTIC_INDEX_OUTPUT_EVAL={}",
        report
            .get("semantic_index_output_eval")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
    );
    println!(
        "SEMANTIC_INDEX_OUTPUT_EVAL_ERRORS={}",
        report
            .get("error_count")
            .and_then(Value::as_u64)
            .unwrap_or(0)
    );
    println!(
        "SEMANTIC_INDEX_OUTPUT_EVAL_ARTIFACTS={}",
        report
            .get("artifacts")
            .and_then(Value::as_array)
            .map(Vec::len)
            .unwrap_or(0)
    );
}

fn print_provider_compare_summary(report: &Value) {
    println!(
        "SEMANTIC_INDEX_PROVIDER_COMPARE={}",
        report
            .get("semantic_index_provider_compare")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
    );
    if let Some(left) = report.get("left") {
        println!(
            "SEMANTIC_INDEX_PROVIDER_COMPARE_LEFT={}:{}:{}",
            left.get("provider").and_then(Value::as_str).unwrap_or(""),
            left.get("model").and_then(Value::as_str).unwrap_or(""),
            left.get("dim").and_then(Value::as_u64).unwrap_or(0)
        );
    }
    if let Some(right) = report.get("right") {
        println!(
            "SEMANTIC_INDEX_PROVIDER_COMPARE_RIGHT={}:{}:{}",
            right.get("provider").and_then(Value::as_str).unwrap_or(""),
            right.get("model").and_then(Value::as_str).unwrap_or(""),
            right.get("dim").and_then(Value::as_u64).unwrap_or(0)
        );
    }
    if let Some(merge) = report.get("merge_candidates") {
        println!(
            "SEMANTIC_INDEX_PROVIDER_COMPARE_MERGE_OVERLAP={:.4}",
            merge
                .get("overlap_ratio")
                .and_then(Value::as_f64)
                .unwrap_or(0.0)
        );
    }
    if let Some(search) = report.get("search").filter(|value| !value.is_null()) {
        println!(
            "SEMANTIC_INDEX_PROVIDER_COMPARE_SEARCH_OVERLAP={:.4}",
            search
                .get("overlap_ratio")
                .and_then(Value::as_f64)
                .unwrap_or(0.0)
        );
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

fn responsibility_tree_report_json(report: &ResponsibilityTreeReport) -> Value {
    json!({
        "semantic_index_responsibility_tree": "ok",
        "root": report.root.display().to_string(),
        "db": report.db.display().to_string(),
        "provider": report.provider,
        "model": report.model,
        "dim": report.dim,
        "node_kind": report.node_kind,
        "directory_count_total": report.directory_count_total,
        "directory_count_returned": report.directories.len(),
        "include_vector": report.include_vector,
        "coverage": coverage_json(&report.coverage),
        "directories": report
            .directories
            .iter()
            .map(|directory| directory_node_json(directory, report.include_vector))
            .collect::<Vec<_>>()
    })
}

fn coverage_json(coverage: &DirectoryCoverage) -> Value {
    json!({
        "status": coverage.status,
        "expected_directory_count": coverage.expected_directories.len(),
        "db_directory_count": coverage.db_directories.len(),
        "missing_directory_count": coverage.missing_directories.len(),
        "stale_directory_count": coverage.stale_directories.len(),
        "repo_tree_directories": coverage.expected_directories,
        "db_tree_directories": coverage.db_directories,
        "missing_directories": coverage.missing_directories,
        "stale_directories": coverage.stale_directories
    })
}

fn directory_node_json(directory: &DirectoryResponsibilityNode, include_vector: bool) -> Value {
    let mut value = json!({
        "path": directory.path,
        "parent": directory.parent,
        "depth": directory.depth,
        "file_count": directory.file_count,
        "node_count": directory.node_count,
        "vector_dim": directory.vector.len(),
        "vector_hash": directory.vector_hash,
        "dominant_responsibility": directory.dominant_responsibility,
        "dominant_share": directory.dominant_share,
        "responsibility_counts": counts_json(&directory.responsibility_counts),
        "node_kind_counts": counts_json(&directory.node_kind_counts),
        "parent_similarity": directory.parent_similarity
    });
    if include_vector {
        value["vector"] = json!(directory.vector);
    }
    value
}

fn counts_json(counts: &[(String, usize)]) -> Value {
    let mut object = serde_json::Map::new();
    for (key, value) in counts {
        object.insert(key.clone(), json!(value));
    }
    Value::Object(object)
}

fn context_cell_json(cell: &ContextCell) -> Value {
    json!({
        "rank": cell.rank,
        "score": cell.score,
        "path": cell.path,
        "node_kind": cell.node_kind,
        "line_start": cell.line_start,
        "line_end": cell.line_end,
        "responsibility_bucket": cell.responsibility_bucket,
        "excerpt_chars": cell.excerpt.chars().count(),
        "excerpt": cell.excerpt
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

fn natural_relation_json(relation: &NaturalRelation) -> Value {
    json!({
        "rank": relation.rank,
        "relation_kind": relation.relation_kind,
        "similarity_score": relation.similarity_score,
        "left_is_kind_of_right_score": relation.left_is_kind_of_right_score,
        "right_is_kind_of_left_score": relation.right_is_kind_of_left_score,
        "left": {
            "path": relation.left.path,
            "responsibility_bucket": responsibility_scope_bucket(&relation.left.path),
            "surface_kind": merge_candidate_surface_kind(&relation.left.path),
            "node_kind": relation.left.kind,
            "line_start": relation.left.line_start,
            "line_end": relation.left.line_end
        },
        "right": {
            "path": relation.right.path,
            "responsibility_bucket": responsibility_scope_bucket(&relation.right.path),
            "surface_kind": merge_candidate_surface_kind(&relation.right.path),
            "node_kind": relation.right.kind,
            "line_start": relation.right.line_start,
            "line_end": relation.right.line_end
        }
    })
}

fn discourse_relation_json(relation: &DiscourseRelation) -> Value {
    json!({
        "rank": relation.rank,
        "connective_profile": relation.connective_profile,
        "relation_family": relation.relation_family,
        "relation_schema": relation.relation_schema,
        "surface_phrase": relation.surface_phrase,
        "inverse_surface_phrase": relation.inverse_surface_phrase,
        "surface_order": relation.surface_order,
        "logical_direction": relation.logical_direction,
        "similarity_score": relation.similarity_score,
        "naturalness_score": relation.naturalness_score,
        "inverse_naturalness_score": relation.inverse_naturalness_score,
        "direction_confidence": relation.direction_confidence,
        "ambiguity": relation.ambiguity,
        "gap_flags": relation.gap_flags,
        "left": {
            "path": relation.left.path,
            "responsibility_bucket": responsibility_scope_bucket(&relation.left.path),
            "node_kind": relation.left.kind,
            "line_start": relation.left.line_start,
            "line_end": relation.left.line_end
        },
        "right": {
            "path": relation.right.path,
            "responsibility_bucket": responsibility_scope_bucket(&relation.right.path),
            "node_kind": relation.right.kind,
            "line_start": relation.right.line_start,
            "line_end": relation.right.line_end
        }
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

fn write_pretty_report(path: &Path, report: &Value) -> Result<(), String> {
    ensure_parent_dir(path)?;
    let text = serde_json::to_string_pretty(report).map_err(|error| error.to_string())?;
    fs::write(path, format!("{text}\n")).map_err(|error| error.to_string())
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
        ".agent-canon/log-archive",
        ".agent-canon/semantic-index",
        ".agent-canon/search-index",
        "agents/evals/results",
        "target",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "reports/agents",
        "reports/hooks",
        "reports/.cache",
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

fn validate_positive(value: usize, flag: &str) -> Result<(), String> {
    if value == 0 {
        return Err(format!("{flag} must be greater than zero"));
    }
    Ok(())
}

fn validate_provider_dim(provider: &str, dim: usize) -> Result<(), String> {
    if is_remote_embedding_provider(provider) {
        return Ok(());
    }
    validate_dim(dim)
}

fn validate_provider_dim_or_auto(provider: &str, dim: usize, flag: &str) -> Result<(), String> {
    if dim == 0 {
        return Ok(());
    }
    validate_provider_dim(provider, dim).map_err(|error| error.replace("--dim", flag))
}

fn validate_embedding_batch(batch_size: usize) -> Result<(), String> {
    if batch_size == 0 {
        return Err("--embedding-batch must be greater than zero".to_string());
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

fn directory_ancestors_for_file(path: &str) -> Vec<String> {
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

fn directory_parent(path: &str) -> Option<String> {
    if path == "." {
        return None;
    }
    path.rsplit_once('/')
        .map(|(parent, _)| parent.to_string())
        .or_else(|| Some(".".to_string()))
}

fn directory_depth(path: &str) -> usize {
    if path == "." {
        0
    } else {
        path.split('/').filter(|part| !part.is_empty()).count()
    }
}

fn count_lines(text: &str) -> usize {
    text.lines().count()
}

fn hex_hash(text: &str) -> String {
    let digest = Sha256::digest(text.as_bytes());
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn bytes_hex_hash(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
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
        "usage: agent-canon semantic-index <build|embed-provider|search|context-pack|responsibility-tree|similar|merge-candidates|thin-docs|natural-relations|discourse-relations|eval|compare-providers|eval-output> [options]"
    );
    eprintln!("build: --root <repo-root> [--include path] [--db path] [--provider name] [--model name] [--dim N] [--embedding-url URL] [--embedding-batch N]");
    eprintln!("embed-provider: --root <repo-root> --db path --provider name --model name [--dim N] [--embedding-url URL] [--embedding-batch N]");
    eprintln!("search: (--query <text>|--query-file path|--query-stdin) [--root repo] [--db path] [--provider name] [--model name] [--embedding-url URL] [--top-k N] [--format text|json|jsonl]");
    eprintln!("context-pack: (--query <text>|--query-file path|--query-stdin) [--root repo] [--db path] [--provider name] [--model name] [--embedding-url URL] [--max-cells N] [--max-cell-chars N] [--max-total-chars N] [--format text|json|jsonl]");
    eprintln!("responsibility-tree: [--root repo] [--include path] [--db path] [--provider name] [--model name] [--dim N] [--node-kind document|section|block|all] [--check-directory-coverage] [--report path] [--format text|json|jsonl]");
    eprintln!("similar: [--root repo] [--db path] [--min-score S] [--cross-file-only] [--format text|json|jsonl]");
    eprintln!(
        "merge-candidates: [--root repo] [--db path] [--min-score S] [--format text|json|jsonl]"
    );
    eprintln!("thin-docs: [--root repo] [--db path] [--min-thin-score S] [--min-neighbor-score S] [--top-k N] [--format text|json|jsonl]");
    eprintln!("natural-relations: [--root repo] [--db path] [--min-similarity S] [--min-kind-of-score S] [--top-k N] [--format text|json|jsonl]");
    eprintln!("discourse-relations: [--root repo] [--db path] [--profile general|experiment-report|methods-protocol|academic-argument|refactor-design] [--min-naturalness S] [--window N] [--top-k N] [--format text|json|jsonl]");
    eprintln!("eval: --fixture <fixture-dir> [--db path] [--report path] [--format text|json]");
    eprintln!("compare-providers: --db path [--query-file path] [--left-provider name] [--right-provider name] [--left-dim N] [--right-dim N] [--report path]");
    eprintln!("eval-output: [--merge-candidates path] [--thin-docs path] [--search path] [--report path] [--format text|json]");
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
    fn openai_embedding_response_parses_indexed_batch() {
        let response = r#"{
          "object": "list",
          "data": [
            {"object": "embedding", "embedding": [0.1, 0.2, 0.3], "index": 1},
            {"object": "embedding", "embedding": [0.4, 0.5, 0.6], "index": 0}
          ],
          "model": "fixture-embedding"
        }"#;
        let vectors = parse_openai_embeddings_response(response, 2).unwrap();
        assert_eq!(vectors[0], vec![0.4, 0.5, 0.6]);
        assert_eq!(vectors[1], vec![0.1, 0.2, 0.3]);
    }

    #[test]
    fn openai_embedding_response_rejects_bad_shapes() {
        for response in [
            r#"{"object":"list"}"#,
            r#"{"data":[{"embedding":["bad"],"index":0}]}"#,
            r#"{"data":[{"embedding":[],"index":0}]}"#,
            "prefix noise {\"data\":[]}",
        ] {
            assert!(parse_openai_embeddings_response(response, 1).is_err());
        }
    }

    #[test]
    fn remote_embedding_text_is_bounded_without_splitting_chars() {
        let bounded = bound_remote_embedding_text("abcdef", 3);
        assert_eq!(bounded, "abc");
        assert_eq!(bound_remote_embedding_text("abc", 3), "abc");
    }

    #[test]
    fn provider_compare_reuses_existing_responsibility_buckets() {
        let root = unique_temp_dir("semantic-index-provider-compare");
        fs::create_dir_all(root.join("documents")).unwrap();
        let duplicate = "# Duplicate\nshared provider comparison phrase\nwith enough lines\nfor merge candidates";
        fs::write(root.join("documents").join("one.md"), duplicate).unwrap();
        fs::write(root.join("documents").join("two.md"), duplicate).unwrap();
        let db = root.join("index.sqlite");
        build_index(&BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        let mut conn = open_cache_connection(&db).unwrap();
        let tx = conn.transaction().unwrap();
        let nodes = load_nodes(&tx, DEFAULT_PROVIDER, DEFAULT_MODEL, 64).unwrap();
        for node in &nodes {
            insert_embedding(
                &tx,
                node.node_id,
                "fixture-llm",
                "fixture",
                64,
                &node.vector,
            )
            .unwrap();
        }
        tx.commit().unwrap();

        let report = compare_providers(&CompareProvidersArgs {
            db,
            query: Some("provider comparison phrase".to_string()),
            left: ProviderSpec {
                provider: DEFAULT_PROVIDER.to_string(),
                model: DEFAULT_MODEL.to_string(),
                dim: 64,
                embedding_url: None,
            },
            right: ProviderSpec {
                provider: "fixture-llm".to_string(),
                model: "fixture".to_string(),
                dim: 64,
                embedding_url: None,
            },
            min_score: 0.5,
            top_k: 10,
            report: None,
            format: OutputFormat::Json,
        })
        .unwrap();
        assert_eq!(
            report
                .get("semantic_index_provider_compare")
                .and_then(Value::as_str),
            Some("ok")
        );
        assert_eq!(
            report["merge_candidates"]["overlap_ratio"].as_f64(),
            Some(1.0)
        );
        assert_eq!(report["search"]["query_chars"].as_u64(), Some(26));
        assert!(report["search"].get("query").is_none());
    }

    #[test]
    fn embed_provider_adds_vectors_without_rebuilding_nodes() {
        let root = unique_temp_dir("semantic-index-embed-provider");
        fs::create_dir_all(root.join("documents")).unwrap();
        fs::write(
            root.join("documents").join("one.md"),
            "# One\nprovider add vector text\nwith enough lines\nfor an indexed node",
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        let stats = embed_existing_nodes(&EmbedProviderArgs {
            root: root.clone(),
            db: db.clone(),
            provider: "fixture-provider".to_string(),
            model: "fixture-model".to_string(),
            dim: 32,
            embedding_url: None,
            embedding_batch: 2,
        })
        .unwrap();
        assert_eq!(stats.nodes, stats.embeddings);
        let resumed_stats = embed_existing_nodes(&EmbedProviderArgs {
            root: root.clone(),
            db: db.clone(),
            provider: "fixture-provider".to_string(),
            model: "fixture-model".to_string(),
            dim: 32,
            embedding_url: None,
            embedding_batch: 2,
        })
        .unwrap();
        assert_eq!(resumed_stats.nodes, 0);
        assert_eq!(resumed_stats.embeddings, 0);
        let different_dim_stats = embed_existing_nodes(&EmbedProviderArgs {
            root: root.clone(),
            db: db.clone(),
            provider: "fixture-provider".to_string(),
            model: "fixture-model".to_string(),
            dim: 16,
            embedding_url: None,
            embedding_batch: 2,
        })
        .unwrap();
        assert_eq!(different_dim_stats.nodes, stats.nodes);
        assert_eq!(different_dim_stats.embeddings, stats.embeddings);
        let conn = open_cache_connection(&db).unwrap();
        assert_eq!(
            provider_dimensions(&conn, "fixture-provider", "fixture-model").unwrap(),
            vec![16, 32]
        );
        assert!(!load_nodes(&conn, "fixture-provider", "fixture-model", 32)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn candidate_commands_auto_resolve_provider_dimension() {
        let root = unique_temp_dir("semantic-index-auto-provider-dim");
        fs::create_dir_all(root.join("documents")).unwrap();
        fs::write(
            root.join("documents").join("one.md"),
            "# One\nshared auto provider phrase\nwith enough lines\nfor merge candidates",
        )
        .unwrap();
        fs::write(
            root.join("documents").join("two.md"),
            "# Two\nshared auto provider phrase\nwith enough lines\nfor merge candidates",
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        let mut conn = open_cache_connection(&db).unwrap();
        let tx = conn.transaction().unwrap();
        let nodes = load_nodes(&tx, DEFAULT_PROVIDER, DEFAULT_MODEL, 64).unwrap();
        let mut vector = vec![0.0; 32];
        vector[0] = 1.0;
        for node in &nodes {
            insert_embedding(
                &tx,
                node.node_id,
                "fixture-provider",
                "fixture-model",
                32,
                &vector,
            )
            .unwrap();
        }
        tx.commit().unwrap();

        let pairs = similar_pairs(&SimilarArgs {
            root: root.clone(),
            db: db.clone(),
            provider: "fixture-provider".to_string(),
            model: "fixture-model".to_string(),
            dim: 0,
            min_score: 0.99,
            top_k: 10,
            format: OutputFormat::Jsonl,
            cross_file_only: true,
            kind: SimilarKind::MergeCandidates,
        })
        .unwrap();
        assert!(!pairs.is_empty());

        let candidates = thin_docs(&ThinDocsArgs {
            root,
            db,
            provider: "fixture-provider".to_string(),
            model: "fixture-model".to_string(),
            dim: 0,
            min_thin_score: 0.1,
            min_neighbor_score: 0.99,
            top_k: 10,
            format: OutputFormat::Jsonl,
        })
        .unwrap();
        assert!(!candidates.is_empty());
    }

    #[test]
    fn directed_kind_of_score_classifies_equivalent_and_containment() {
        let specific = relation_terms(
            "Python reviewer checks Python diffs with ruff pyright pytest evidence.",
        );
        let general = relation_terms("Reviewer checks diffs and records evidence.");
        let left = directed_kind_of_score(&specific, &general, 0.80);
        let right = directed_kind_of_score(&general, &specific, 0.80);
        assert_eq!(
            classify_natural_relation(left, right, DEFAULT_MIN_KIND_OF_SCORE),
            "left_is_kind_of_right"
        );

        let equivalent_left = relation_terms("Agent update validates submodule pin workflow.");
        let equivalent_right = relation_terms("Submodule pin workflow validates agent update.");
        let left = directed_kind_of_score(&equivalent_left, &equivalent_right, 0.95);
        let right = directed_kind_of_score(&equivalent_right, &equivalent_left, 0.95);
        assert_eq!(
            classify_natural_relation(left, right, DEFAULT_MIN_KIND_OF_SCORE),
            "equivalent"
        );
    }

    #[test]
    fn natural_relations_persist_directed_kind_of_analysis() {
        let root = unique_temp_dir("semantic-index-natural-relations");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::write(
            root.join("docs").join("python_review.md"),
            "# Python Review\nPython reviewer checks Python diffs with ruff pyright pytest evidence.",
        )
        .unwrap();
        fs::write(
            root.join("docs").join("review.md"),
            "# Review\nReviewer checks diffs and records evidence.",
        )
        .unwrap();
        fs::write(
            root.join("docs").join("security.md"),
            "# Security\nSecret scanner credential exposure audit.",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        build_index(&BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from("docs")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        let args = NaturalRelationsArgs {
            root: root.clone(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            min_similarity: 0.05,
            min_kind_of_score: DEFAULT_MIN_KIND_OF_SCORE,
            top_k: 20,
            format: OutputFormat::Jsonl,
            cross_file_only: true,
        };
        let relations = natural_relations(&args).unwrap();
        let review_relation = relations
            .iter()
            .find(|relation| {
                relation.left.path == "docs/python_review.md"
                    && relation.right.path == "docs/review.md"
                    && relation.relation_kind == "left_is_kind_of_right"
            })
            .expect("expected Python review to be a kind of review");
        assert!(
            review_relation.left_is_kind_of_right_score
                > review_relation.right_is_kind_of_left_score
        );

        persist_natural_relations(&args, &relations).unwrap();
        let conn = open_cache_connection(&db).unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM natural_language_relations WHERE relation_kind = 'left_is_kind_of_right'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert!(count >= 1);
    }

    #[test]
    fn discourse_relations_pair_therefore_and_because_variants() {
        let root = unique_temp_dir("semantic-index-discourse-relations");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::write(
            root.join("docs").join("flow.md"),
            "# Flow\nThe runtime log branch may not be mounted before an AgentCanon update.\n\nTherefore the update tool should warn and continue without blocking validation.\n\nThe warning belongs in workflow guidance.\n\nBecause the same missing mount can appear before the log archive checkout exists.",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        build_index(&BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from("docs")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        let args = DiscourseRelationsArgs {
            root: root.clone(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            profile: "experiment-report".to_string(),
            min_naturalness: 0.20,
            window: 2,
            top_k: 20,
            format: OutputFormat::Jsonl,
        };
        let relations = discourse_relations(&args).unwrap();
        let therefore = relations
            .iter()
            .find(|relation| {
                relation.surface_phrase == "therefore"
                    && relation.relation_schema == "reason_to_result"
                    && relation.logical_direction == "left_to_right"
            })
            .expect("expected therefore to map reason-to-result left-to-right");
        assert_eq!(therefore.inverse_surface_phrase.as_deref(), Some("because"));

        let because = relations
            .iter()
            .find(|relation| {
                relation.surface_phrase == "because"
                    && relation.relation_schema == "reason_to_result"
                    && relation.logical_direction == "right_to_left"
            })
            .expect("expected because to map the same schema with reverse logical direction");
        assert_eq!(because.inverse_surface_phrase.as_deref(), Some("therefore"));

        persist_discourse_relations(&args, &relations).unwrap();
        let conn = open_cache_connection(&db).unwrap();
        let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM discourse_relations WHERE relation_schema = 'reason_to_result'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert!(count >= 2);
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: None,
            top_k: 3,
            format: OutputFormat::Json,
        };
        let hits = search_index(&search_args).unwrap();
        assert!(hits
            .results
            .iter()
            .any(|hit| hit.node.path == "docs/update.md"));
        assert_eq!(hits.stale_path_count, 0);
    }

    #[test]
    fn context_pack_returns_bounded_evidence_cells() {
        let root = unique_temp_dir("semantic-index-context-pack");
        fs::create_dir_all(root.join("docs")).unwrap();
        fs::write(
            root.join("docs").join("routing.md"),
            "# Routing\nskill workflow tool responsibility candidate context phrase\nsecond line for bounded excerpt\nthird line stays local",
        )
        .unwrap();
        fs::write(
            root.join("docs").join("other.md"),
            "# Other\nunrelated content",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        build_index(&BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from("docs")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();

        let cells = context_pack(&ContextPackArgs {
            root,
            db,
            query: "skill workflow responsibility".to_string(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
            max_cells: 2,
            max_cell_chars: 40,
            max_total_chars: 80,
            format: OutputFormat::Jsonl,
        })
        .unwrap();

        assert!(!cells.is_empty());
        assert!(cells.len() <= 2);
        assert!(cells.iter().all(|cell| cell.excerpt.chars().count() <= 40));
        assert!(cells.iter().any(|cell| cell.path.ends_with("routing.md")));
    }

    #[test]
    fn responsibility_tree_reports_vectors_and_coverage() {
        let root = unique_temp_dir("semantic-index-responsibility-tree");
        fs::create_dir_all(root.join("documents")).unwrap();
        fs::create_dir_all(root.join("tools")).unwrap();
        fs::write(
            root.join("documents").join("policy.md"),
            "# Policy\nsemantic index directory coverage responsibility tree",
        )
        .unwrap();
        fs::write(
            root.join("tools").join("scan.py"),
            "print('semantic index directory coverage tool')\n",
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        let args = ResponsibilityTreeArgs {
            root: root.clone(),
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
            node_kind: "document".to_string(),
            max_depth: None,
            top_k: None,
            include_vector: true,
            check_directory_coverage: true,
            report: None,
            format: OutputFormat::Json,
        };
        let report = responsibility_tree(&args).unwrap();
        assert_eq!(report.coverage.status, "pass");
        assert!(report
            .directories
            .iter()
            .any(|directory| directory.path == "documents" && directory.vector.len() == 64));
        assert!(report
            .directories
            .iter()
            .any(|directory| directory.path == "tools" && directory.vector.len() == 64));
        let json = responsibility_tree_report_json(&report);
        assert_eq!(
            json["coverage"]["missing_directory_count"].as_u64(),
            Some(0)
        );
        assert!(json["directories"]
            .as_array()
            .unwrap()
            .iter()
            .any(|directory| directory.get("vector").is_some()));
        let output = root.join("responsibility_tree.json");
        write_pretty_report(&output, &json).unwrap();
        let parsed: Value = serde_json::from_str(&fs::read_to_string(output).unwrap()).unwrap();
        assert_eq!(
            parsed
                .get("semantic_index_responsibility_tree")
                .and_then(Value::as_str),
            Some("ok")
        );
    }

    #[test]
    fn responsibility_tree_detects_missing_directory_coverage() {
        let root = unique_temp_dir("semantic-index-responsibility-tree-missing");
        fs::create_dir_all(root.join("documents")).unwrap();
        fs::create_dir_all(root.join("tools")).unwrap();
        fs::write(
            root.join("documents").join("policy.md"),
            "# Policy\nsemantic index coverage baseline",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        build_index(&BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from("documents")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        fs::write(
            root.join("tools").join("new_tool.py"),
            "print('not yet indexed')\n",
        )
        .unwrap();
        let report = responsibility_tree(&ResponsibilityTreeArgs {
            root,
            includes: vec![PathBuf::from(".")],
            excludes: default_excludes(),
            db,
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
            node_kind: "document".to_string(),
            max_depth: None,
            top_k: None,
            include_vector: false,
            check_directory_coverage: true,
            report: None,
            format: OutputFormat::Json,
        })
        .unwrap();
        assert_eq!(report.coverage.status, "fail");
        assert!(report
            .coverage
            .missing_directories
            .contains(&"tools".to_string()));
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: None,
            top_k: 5,
            format: OutputFormat::Json,
        };
        assert!(search_index(&search_args).unwrap().results.is_empty());
    }

    #[test]
    fn search_skips_cached_nodes_for_deleted_paths() {
        let root = unique_temp_dir("semantic-index-stale-paths");
        fs::create_dir_all(root.join("docs")).unwrap();
        let stale_path = root.join("docs").join("stale.md");
        fs::write(
            &stale_path,
            "# Stale\nsemantic vector deleted path phrase\nwith enough lines\nfor an indexed node",
        )
        .unwrap();
        let db = root.join("index.sqlite");
        build_index(&BuildArgs {
            root: root.clone(),
            includes: vec![PathBuf::from("docs")],
            excludes: default_excludes(),
            db: db.clone(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
            max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        })
        .unwrap();
        fs::remove_file(stale_path).unwrap();

        let hits = search_index(&SearchArgs {
            root,
            db,
            query: "deleted path phrase".to_string(),
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
            top_k: 5,
            format: OutputFormat::Json,
        })
        .unwrap();

        assert!(hits.results.is_empty());
        assert!(hits.stale_path_count > 0);
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            responsibility_scope_bucket("evidence/agent-evals/skill_workflow_prompt_eval.toml"),
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
            embedding_url: None,
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
            embedding_url: None,
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
    fn eval_output_accepts_valid_review_artifacts() {
        let root = unique_temp_dir("semantic-index-output-eval-pass");
        let merge_path = root.join("merge.jsonl");
        let thin_path = root.join("thin.jsonl");
        let search_path = root.join("search.jsonl");
        fs::write(
            &merge_path,
            r#"{"semantic_index_pairs":"ok","kind":"merge-candidates","result_count":1}
{"rank":1,"score":0.95,"same_responsibility":true,"candidate_bucket":"docs:shared-policy-documents:document","left":{"path":"documents/a.md","responsibility_bucket":"shared-policy-documents","node_kind":"document","line_start":1,"line_end":4},"right":{"path":"documents/b.md","responsibility_bucket":"shared-policy-documents","node_kind":"document","line_start":1,"line_end":4}}
"#,
        )
        .unwrap();
        fs::write(
            &thin_path,
            r#"{"semantic_index_thin_docs":"ok","result_count":1}
{"rank":1,"thin_score":0.72,"action":"keep_entrypoint","reasons":["protected_entrypoint"],"path":"README.md","node_kind":"document","line_start":1,"line_end":3}
"#,
        )
        .unwrap();
        fs::write(
            &search_path,
            r#"{"semantic_index_search":"ok","query_chars":42,"result_count":1}
{"rank":1,"score":0.61,"path":"documents/semantic_index.md","node_kind":"block","line_start":10,"line_end":12}
"#,
        )
        .unwrap();
        let report = eval_output(&EvalOutputArgs {
            merge_candidates: Some(merge_path),
            thin_docs: Some(thin_path),
            search: Some(search_path),
            report: None,
            format: OutputFormat::Json,
        })
        .unwrap();
        assert_eq!(
            report
                .get("semantic_index_output_eval")
                .and_then(Value::as_str),
            Some("pass")
        );
        assert_eq!(report.get("error_count").and_then(Value::as_u64), Some(0));
    }

    #[test]
    fn eval_output_rejects_cross_responsibility_and_query_echo() {
        let root = unique_temp_dir("semantic-index-output-eval-fail");
        let merge_path = root.join("merge.jsonl");
        let search_path = root.join("search.jsonl");
        fs::write(
            &merge_path,
            r#"{"semantic_index_pairs":"ok","kind":"merge-candidates","result_count":1}
{"rank":1,"score":0.95,"same_responsibility":false,"candidate_bucket":"similar:any","left":{"path":"documents/a.md","responsibility_bucket":"shared-policy-documents","node_kind":"document","line_start":1,"line_end":4},"right":{"path":"agents/a.md","responsibility_bucket":"runtime-entrypoints","node_kind":"document","line_start":1,"line_end":4}}
"#,
        )
        .unwrap();
        fs::write(
            &search_path,
            r#"{"semantic_index_search":"ok","query":"long user request should not echo","result_count":0}
"#,
        )
        .unwrap();
        let report = eval_output(&EvalOutputArgs {
            merge_candidates: Some(merge_path),
            thin_docs: None,
            search: Some(search_path),
            report: None,
            format: OutputFormat::Json,
        })
        .unwrap();
        assert_eq!(
            report
                .get("semantic_index_output_eval")
                .and_then(Value::as_str),
            Some("fail")
        );
        assert!(
            report
                .get("error_count")
                .and_then(Value::as_u64)
                .unwrap_or(0)
                >= 3
        );
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
            embedding_url: None,
            embedding_batch: DEFAULT_EMBEDDING_BATCH,
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
