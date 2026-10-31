#![recursion_limit = "256"]

//! Shared AgentCanon runtime, private feedback, artifact, catalog, proof, and Template APIs.

// @dependency-start
// contract implementation
// responsibility Exposes shared runtime root, private feedback, artifact identity, external binding, Template, catalog, and proof-coverage APIs through one Cargo library.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust implementation ownership
// upstream implementation runtime_boundary.rs owns external runtime and restricted spool capabilities
// upstream implementation private_feedback.rs owns private feedback storage using the shared boundary
// upstream implementation artifacts/artifact_identity.rs owns artifact byte identity
// upstream implementation artifacts/external_artifact_binding.rs owns projection acknowledgements
// upstream implementation environment_dependencies.rs owns complete environment dependency plans and executable receipts
// downstream implementation code_template_rendering.rs owns code template rendering
// downstream implementation entrypoint_composer.rs owns consumer entrypoint composition
// downstream implementation native_release.rs owns source-bound native releases
// downstream implementation template_bundle.rs owns native template package operations
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// downstream implementation main.rs consumes the shared runtime and CLI library APIs
// downstream test ../tests/artifacts_native.rs validates the shared artifact API
// downstream test ../tests/catalog_native.rs validates the shared catalog API
// downstream test template_tests.rs validates native Template APIs
// @dependency-end

pub mod artifacts;
pub mod catalog;
pub mod code_template_rendering;
pub mod entrypoint_composer;
pub mod environment_dependencies;
pub mod native_release;
pub mod private_feedback;
pub mod runtime_boundary;
pub mod template_bundle;
pub mod tool_proof_coverage;

#[cfg(test)]
mod template_tests;
