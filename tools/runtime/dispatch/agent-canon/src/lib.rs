#![recursion_limit = "256"]

//! Shared AgentCanon runtime, private feedback, artifact, catalog, proof, and parent-root authority APIs.

// @dependency-start
// contract implementation
// responsibility Exposes shared runtime root, private feedback, artifact identity, external binding, native parent-root authority, catalog, and proof-coverage APIs to the native CLI, tools, and integration tests.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust implementation ownership
// upstream implementation runtime_boundary.rs owns external runtime and restricted spool capabilities
// upstream implementation private_feedback.rs owns private feedback storage using the shared boundary
// upstream implementation artifacts/artifact_identity.rs owns artifact byte identity
// upstream implementation artifacts/external_artifact_binding.rs owns projection acknowledgements
// downstream implementation authority/mod.rs owns authenticated parent-root and child-handoff APIs
// upstream implementation environment_dependencies.rs owns complete environment dependency plans and executable receipts
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// downstream implementation main.rs consumes the shared runtime and CLI library APIs
// downstream test ../tests/artifacts_native.rs validates the shared artifact API
// downstream test ../tests/catalog_native.rs validates the shared catalog API
// @dependency-end

pub mod artifacts;
pub mod authority;
pub mod catalog;
pub mod environment_dependencies;
pub mod private_feedback;
pub mod runtime_boundary;
pub mod tool_proof_coverage;
