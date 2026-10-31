#![recursion_limit = "256"]

//! Shared AgentCanon runtime, private feedback, artifact, catalog, and proof APIs.

// @dependency-start
// contract implementation
// responsibility Exposes shared runtime root, private feedback, artifact identity, external binding, native evaluation, report-check, Eval-path, catalog, and proof-coverage APIs to the CLI and integration tests.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust implementation ownership
// upstream implementation runtime_boundary.rs owns external runtime and restricted spool capabilities
// upstream implementation runtime_boundary.rs owns external artifact I/O capabilities
// upstream implementation private_feedback.rs owns private feedback storage using the shared boundary
// upstream implementation artifacts/artifact_identity.rs owns artifact byte identity
// upstream implementation artifacts/external_artifact_binding.rs owns projection acknowledgements
// upstream implementation environment_dependencies.rs owns complete environment dependency plans and executable receipts
// downstream implementation eval_manifest_paths.rs resolves canonical/legacy Eval manifests
// downstream implementation report_artifact_checks.rs owns pure report artifact checks
// downstream implementation run_evaluation.rs evaluates one selected run bundle
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// downstream implementation main.rs consumes the shared runtime and CLI library APIs
// downstream test ../tests/artifacts_native.rs validates the shared artifact API
// downstream test ../tests/catalog_native.rs validates the shared catalog API
// @dependency-end

pub mod artifacts;
pub mod catalog;
pub mod environment_dependencies;
pub mod eval_manifest_paths;
pub mod private_feedback;
pub mod report_artifact_checks;
pub mod run_evaluation;
pub mod runtime_boundary;
pub mod tool_proof_coverage;
