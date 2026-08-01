// @dependency-start
// contract implementation
// responsibility Owns semantic-index parser DTOs, defaults, aliases, and validation.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

pub(super) const DEFAULT_PROVIDER: &str = "deterministic-dense-v1";
pub(super) const OPENAI_COMPATIBLE_EMBEDDING_PROVIDER: &str = "openai-compatible-embedding";
pub(super) const DEFAULT_MODEL: &str = "hash-token-char-v1";
pub(super) const DEFAULT_DIM: usize = 128;
pub(super) const DEFAULT_TOP_K: usize = 10;
pub(super) const DEFAULT_MIN_SCORE: f32 = 0.80;
pub(super) const DEFAULT_MAX_FILE_BYTES: u64 = 1_000_000;
pub(super) const DEFAULT_EMBEDDING_BATCH: usize = 16;
pub(super) const DEFAULT_CONTEXT_CELLS: usize = 12;
pub(super) const DEFAULT_CONTEXT_CELL_CHARS: usize = 900;
pub(super) const DEFAULT_CONTEXT_TOTAL_CHARS: usize = 6000;
pub(super) const DEFAULT_TREE_NODE_KIND: &str = "document";
pub(super) const DEFAULT_MIN_THIN_SCORE: f32 = 0.50;
pub(super) const DEFAULT_MIN_THIN_NEIGHBOR_SCORE: f32 = 0.86;
pub(super) const DEFAULT_MIN_RELATION_SIMILARITY: f32 = 0.72;
pub(super) const DEFAULT_MIN_KIND_OF_SCORE: f32 = 0.62;
pub(super) const DEFAULT_DISCOURSE_PROFILE: &str = "general";
pub(super) const DEFAULT_MIN_DISCOURSE_NATURALNESS: f32 = 0.40;
pub(super) const DEFAULT_DISCOURSE_WINDOW: usize = 3;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) enum SemanticCommand {
    Help,
}

#[derive(Debug, Clone)]
pub(super) struct BuildArgs {
    pub(super) root: PathBuf,
    pub(super) includes: Vec<PathBuf>,
    pub(super) excludes: Vec<String>,
    pub(super) db: PathBuf,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) embedding_url: Option<String>,
    pub(super) embedding_batch: usize,
    pub(super) max_file_bytes: u64,
}

#[derive(Debug, Clone)]
pub(super) struct SearchArgs {
    pub(super) root: PathBuf,
    pub(super) db: PathBuf,
    pub(super) query: String,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) embedding_url: Option<String>,
    pub(super) top_k: usize,
    pub(super) format: OutputFormat,
}

#[derive(Debug, Clone)]
pub(super) struct ContextPackArgs {
    pub(super) root: PathBuf,
    pub(super) db: PathBuf,
    pub(super) query: String,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) embedding_url: Option<String>,
    pub(super) max_cells: usize,
    pub(super) max_cell_chars: usize,
    pub(super) max_total_chars: usize,
    pub(super) format: OutputFormat,
}

#[derive(Debug, Clone)]
pub(super) struct ResponsibilityTreeArgs {
    pub(super) root: PathBuf,
    pub(super) includes: Vec<PathBuf>,
    pub(super) excludes: Vec<String>,
    pub(super) db: PathBuf,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) max_file_bytes: u64,
    pub(super) node_kind: String,
    pub(super) max_depth: Option<usize>,
    pub(super) top_k: Option<usize>,
    pub(super) include_vector: bool,
    pub(super) check_directory_coverage: bool,
    pub(super) report: Option<PathBuf>,
    pub(super) format: OutputFormat,
}

#[derive(Debug, Clone)]
pub(super) struct EmbedProviderArgs {
    pub(super) root: PathBuf,
    pub(super) db: PathBuf,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) embedding_url: Option<String>,
    pub(super) embedding_batch: usize,
}

#[derive(Debug, Clone)]
pub(super) struct SimilarArgs {
    pub(super) root: PathBuf,
    pub(super) db: PathBuf,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) min_score: f32,
    pub(super) top_k: usize,
    pub(super) format: OutputFormat,
    pub(super) cross_file_only: bool,
    pub(super) kind: SimilarKind,
}

#[derive(Debug, Clone)]
pub(super) struct ThinDocsArgs {
    pub(super) root: PathBuf,
    pub(super) db: PathBuf,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) min_thin_score: f32,
    pub(super) min_neighbor_score: f32,
    pub(super) top_k: usize,
    pub(super) format: OutputFormat,
}

#[derive(Debug, Clone)]
pub(super) struct NaturalRelationsArgs {
    pub(super) root: PathBuf,
    pub(super) db: PathBuf,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) min_similarity: f32,
    pub(super) min_kind_of_score: f32,
    pub(super) top_k: usize,
    pub(super) format: OutputFormat,
    pub(super) cross_file_only: bool,
}

#[derive(Debug, Clone)]
pub(super) struct DiscourseRelationsArgs {
    pub(super) root: PathBuf,
    pub(super) db: PathBuf,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) profile: String,
    pub(super) min_naturalness: f32,
    pub(super) window: usize,
    pub(super) top_k: usize,
    pub(super) format: OutputFormat,
}

#[derive(Debug, Clone)]
pub(super) struct EvalArgs {
    pub(super) fixture: PathBuf,
    pub(super) db: PathBuf,
    pub(super) report: Option<PathBuf>,
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) embedding_url: Option<String>,
    pub(super) top_k: usize,
    pub(super) format: OutputFormat,
}

#[derive(Debug, Clone)]
pub(super) struct ProviderSpec {
    pub(super) provider: String,
    pub(super) model: String,
    pub(super) dim: usize,
    pub(super) embedding_url: Option<String>,
}

#[derive(Debug, Clone)]
pub(super) struct CompareProvidersArgs {
    pub(super) db: PathBuf,
    pub(super) query: Option<String>,
    pub(super) left: ProviderSpec,
    pub(super) right: ProviderSpec,
    pub(super) min_score: f32,
    pub(super) top_k: usize,
    pub(super) report: Option<PathBuf>,
    pub(super) format: OutputFormat,
}

#[derive(Debug, Clone)]
pub(super) struct EvalOutputArgs {
    pub(super) merge_candidates: Option<PathBuf>,
    pub(super) thin_docs: Option<PathBuf>,
    pub(super) search: Option<PathBuf>,
    pub(super) report: Option<PathBuf>,
    pub(super) format: OutputFormat,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum OutputFormat {
    Text,
    Json,
    Jsonl,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum SimilarKind {
    Similar,
    MergeCandidates,
}

#[derive(Debug, Clone)]
pub(super) enum ParsedArgs {
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

pub(super) fn parse_args(
    args: &[String],
    temporary_db_identity: fn() -> String,
) -> Result<ParsedArgs, String> {
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
        "eval" => Ok(ParsedArgs::Eval(parse_eval_args(
            &args[1..],
            temporary_db_identity,
        )?)),
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
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
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

fn parse_eval_args(
    args: &[String],
    temporary_db_identity: fn() -> String,
) -> Result<EvalArgs, String> {
    let mut fixture: Option<PathBuf> = None;
    let mut parsed = EvalArgs {
        fixture: PathBuf::new(),
        db: env::temp_dir().join(format!(
            "agent-canon-semantic-index-eval-{}.sqlite",
            temporary_db_identity()
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
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
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

pub(super) fn default_db_path(root: &Path) -> PathBuf {
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

pub(super) fn default_excludes() -> Vec<String> {
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

pub(super) fn validate_dim(dim: usize) -> Result<(), String> {
    if dim == 0 {
        return Err("--dim must be greater than zero".to_string());
    }
    Ok(())
}

pub(super) fn validate_discourse_profile(profile: &str) -> Result<(), String> {
    match profile {
        "general" | "experiment-report" | "methods-protocol" | "academic-argument"
        | "refactor-design" => Ok(()),
        unknown => Err(format!("unknown discourse profile {unknown}")),
    }
}

fn validate_positive(value: usize, flag: &str) -> Result<(), String> {
    if value == 0 {
        return Err(format!("{flag} must be greater than zero"));
    }
    Ok(())
}

fn validate_provider_dim(provider: &str, dim: usize) -> Result<(), String> {
    if provider == OPENAI_COMPATIBLE_EMBEDDING_PROVIDER {
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
