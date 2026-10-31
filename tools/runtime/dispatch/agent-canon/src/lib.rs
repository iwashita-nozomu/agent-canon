#![recursion_limit = "256"]

//! Shared AgentCanon runtime, LSP, Template, release, artifact, catalog, parent-root authority, proof, and evaluation APIs.

// @dependency-start
// contract implementation
// responsibility Exposes shared runtime, LSP, native evaluation, private feedback, artifact identity, parent-root authority, Template/release, catalog, and proof APIs.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust implementation ownership
// upstream implementation runtime_boundary.rs owns external runtime and restricted spool capabilities
// upstream implementation runtime_boundary.rs owns external artifact I/O capabilities
// upstream implementation private_feedback.rs owns private feedback storage using the shared boundary
// upstream implementation artifacts/artifact_identity.rs owns artifact byte identity
// upstream implementation artifacts/external_artifact_binding.rs owns projection acknowledgements
// downstream implementation authority/mod.rs owns authenticated parent-root and child-handoff APIs
// upstream implementation environment_dependencies.rs owns complete environment dependency plans and executable receipts
// downstream implementation owner_guarantee.rs owns native owner-guarantee and invalidation packet APIs
// downstream implementation code_template_rendering.rs owns code template rendering
// downstream implementation entrypoint_composer.rs owns consumer entrypoint composition
// downstream implementation native_release.rs owns source-bound native releases
// downstream implementation compare_agent_run_paths.rs owns the run-path comparison API
// downstream implementation template_bundle.rs owns native template package operations
// downstream implementation python_text.rs shares Python-compatible Unicode whitespace semantics
// downstream implementation python_cli_integer.rs parses Python-compatible integer options
// upstream implementation path_resolution.rs owns non-strict physical path resolution shared by source and validation tools
// downstream implementation lean_proof_env.rs owns native Lean proof environment planning and execution
// downstream implementation eval_manifest_paths.rs resolves canonical/legacy Eval manifests
// downstream implementation report_artifact_checks.rs owns pure report artifact checks
// downstream implementation run_evaluation.rs evaluates one selected run bundle
// downstream implementation generated_completeness.rs owns the G2 receipt API and CLI operation
// downstream implementation update_lifecycle_contract.rs validates immutable lifecycle records and gate verdicts
// downstream implementation python_json.rs owns shared Python-compatible JSON values and canonical bytes
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// downstream implementation theorem_graph_board.rs owns theorem-graph route-board classification and rendering
// downstream implementation lsp_code_analysis.rs owns the reusable native LSP analysis API
// downstream implementation path_expansion.rs owns shared user-home path expansion
// downstream implementation scip_index.rs owns the native generated-index reader and SCIP command
// downstream implementation git_dependency_diff_summary.rs owns native Git dependency summaries
// downstream implementation main.rs consumes the shared runtime and CLI library APIs
// downstream test ../tests/owner_guarantee_native.rs validates Python packet and projection oracles
// downstream test ../tests/artifacts_native.rs validates the shared artifact API
// downstream test ../tests/catalog_native.rs validates the shared catalog API
// downstream test template_tests.rs validates native Template APIs
// downstream test ../tests/lean_proof_env_native.rs validates native Lean proof environment planning
// downstream test ../tests/theorem_graph_board_native.rs validates theorem-board API and CLI behavior
// @dependency-end

pub mod artifacts;
pub mod authority;
pub mod catalog;
pub mod code_template_rendering;
pub mod compare_agent_run_paths;
pub mod entrypoint_composer;
pub mod generated_completeness;
// This shared source module also serves the CLI's AST tools; the reusable LSP
// API uses only the newline and source-offset helpers from this owner.
pub mod environment_dependencies;
pub mod eval_manifest_paths;
pub mod git_dependency_diff_summary;
pub mod lean_proof_env;
pub mod lsp_code_analysis;
pub mod native_release;
pub mod owner_guarantee;
pub mod path_expansion;
pub mod path_resolution;
pub mod private_feedback;
#[allow(dead_code)]
pub(crate) mod python_ast;
pub(crate) mod python_cli_integer;
pub mod python_json;
pub(crate) mod python_text;
pub mod report_artifact_checks;
pub mod run_evaluation;
pub mod runtime_boundary;
pub mod scip_index;
pub mod stablehlo_value_closure;
pub mod template_bundle;
pub mod theorem_graph_board;
pub mod theorem_graph_circularity_check;
pub mod tool_proof_coverage;
pub mod update_lifecycle_contract;

#[cfg(test)]
mod template_tests;
