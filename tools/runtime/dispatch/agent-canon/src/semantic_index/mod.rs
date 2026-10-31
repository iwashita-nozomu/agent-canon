// @dependency-start
// contract implementation
// responsibility Owns the semantic-index crate-facing entrypoint and module declarations.
// upstream design ../../../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../../catalog.yaml command catalog and public command source
// downstream implementation ../../../../../repository/github/review_backlog_scan.sh process-level semantic-index behavior oracle
// downstream implementation ../agent_search.rs consumes native semantic-index results in-process
// @dependency-end

mod args;
mod cli;
mod embedding;
mod eval;
mod model;
mod pipeline;
mod query;
mod relations;
mod report;
mod source;
mod storage;

#[cfg(test)]
mod tests;

use args::{
    default_db_path, OutputFormat, SearchArgs, DEFAULT_DIM, DEFAULT_MODEL, DEFAULT_PROVIDER,
};
use serde_json::{json, Value};
use std::path::Path;

pub(crate) fn run(args: &[String]) -> i32 {
    cli::run(args)
}

pub(crate) fn search_for_agent(root: &Path, query: &str, top_k: usize) -> Result<Value, String> {
    let args = SearchArgs {
        root: root.to_path_buf(),
        db: default_db_path(root),
        query: query.to_string(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: DEFAULT_DIM,
        embedding_url: None,
        top_k,
        format: OutputFormat::Json,
    };
    let results = query::search_index(&args)?;
    Ok(json!({
        "semantic_index_search": "ok",
        "query": args.query,
        "stale_path_count": results.stale_path_count,
        "results": results.results.iter().map(report::scored_node_json).collect::<Vec<_>>()
    }))
}
