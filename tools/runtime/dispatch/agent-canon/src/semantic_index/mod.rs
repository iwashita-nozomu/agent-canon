// @dependency-start
// contract implementation
// responsibility Owns the semantic-index crate-facing entrypoint and module declarations.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/repository/github/review_backlog_scan.sh process-level semantic-index behavior oracle
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

pub(crate) fn run(args: &[String]) -> i32 {
    cli::run(args)
}
