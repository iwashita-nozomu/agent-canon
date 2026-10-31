#![recursion_limit = "256"]

//! Shared AgentCanon runtime, LSP analysis, theorem-board, private feedback, artifact, catalog, and proof APIs.

// @dependency-start
// contract implementation
// responsibility Exposes shared runtime, LSP analysis, native evaluation, artifact, catalog, and proof-coverage APIs.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust implementation ownership
// upstream implementation runtime_boundary.rs owns external runtime and restricted spool capabilities
// upstream implementation runtime_boundary.rs owns external artifact I/O capabilities
// upstream implementation private_feedback.rs owns private feedback storage using the shared boundary
// upstream implementation artifacts/artifact_identity.rs owns artifact byte identity
// upstream implementation artifacts/external_artifact_binding.rs owns projection acknowledgements
// upstream implementation environment_dependencies.rs owns complete environment dependency plans and executable receipts
// downstream implementation python_text.rs shares Python-compatible Unicode whitespace semantics
// downstream implementation python_cli_integer.rs parses Python-compatible integer options
// downstream implementation eval_manifest_paths.rs resolves canonical/legacy Eval manifests
// downstream implementation report_artifact_checks.rs owns pure report artifact checks
// downstream implementation run_evaluation.rs evaluates one selected run bundle
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// downstream implementation theorem_graph_board.rs owns theorem-graph route-board classification and rendering
// downstream implementation lsp_code_analysis.rs owns the reusable native LSP analysis API
// downstream implementation scip_index.rs owns the native generated-index reader and SCIP command
// downstream implementation git_dependency_diff_summary.rs owns native Git dependency summaries
// downstream implementation main.rs consumes the shared runtime and CLI library APIs
// downstream test ../tests/artifacts_native.rs validates the shared artifact API
// downstream test ../tests/catalog_native.rs validates the shared catalog API
// downstream test ../tests/theorem_graph_board_native.rs validates theorem-board API and CLI behavior
// @dependency-end

pub mod artifacts;
pub mod catalog;
// This shared source module also serves the CLI's AST tools; the reusable LSP
// API uses only the newline and source-offset helpers from this owner.
pub mod environment_dependencies;
pub mod eval_manifest_paths;
pub mod git_dependency_diff_summary;
pub mod lsp_code_analysis;
pub mod private_feedback;
#[allow(dead_code)]
pub(crate) mod python_ast;
pub(crate) mod python_cli_integer;
pub(crate) mod python_text;
pub mod report_artifact_checks;
pub mod run_evaluation;
pub mod runtime_boundary;
pub mod scip_index;
pub mod theorem_graph_board;
pub mod tool_proof_coverage;
