#![recursion_limit = "256"]

//! Shared AgentCanon runtime, LSP analysis, private feedback, artifact, catalog, and proof APIs.

// @dependency-start
// contract implementation
// responsibility Exposes shared runtime root, LSP analysis, private feedback, artifact identity, external binding, catalog, and proof-coverage APIs.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust implementation ownership
// upstream implementation runtime_boundary.rs owns external runtime and restricted spool capabilities
// upstream implementation private_feedback.rs owns private feedback storage using the shared boundary
// upstream implementation artifacts/artifact_identity.rs owns artifact byte identity
// upstream implementation artifacts/external_artifact_binding.rs owns projection acknowledgements
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// downstream implementation lsp_code_analysis.rs owns the reusable native LSP analysis API
// downstream implementation main.rs consumes the shared runtime and CLI library APIs
// downstream test ../tests/artifacts_native.rs validates the shared artifact API
// downstream test ../tests/catalog_native.rs validates the shared catalog API
// @dependency-end

pub mod artifacts;
pub mod catalog;
// This shared source module also serves the CLI's AST tools; the reusable LSP
// API uses only the newline and source-offset helpers from this owner.
pub mod lsp_code_analysis;
pub mod private_feedback;
#[allow(dead_code)]
pub(crate) mod python_ast;
pub mod runtime_boundary;
pub mod tool_proof_coverage;
