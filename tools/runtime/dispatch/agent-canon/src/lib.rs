#![recursion_limit = "256"]

//! Shared AgentCanon runtime, private feedback, and artifact APIs.

// @dependency-start
// contract implementation
// responsibility Owns shared runtime root, spool, private feedback storage, artifact identity, and external binding APIs.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust implementation ownership
// upstream implementation runtime_boundary.rs owns external runtime and restricted spool capabilities
// upstream implementation private_feedback.rs owns private feedback storage using the shared boundary
// upstream implementation artifacts/artifact_identity.rs owns artifact byte identity
// upstream implementation artifacts/external_artifact_binding.rs owns projection acknowledgements
// downstream implementation main.rs uses the runtime boundary for CLI consumers
// downstream test ../tests/artifacts_native.rs validates the shared artifact API
// @dependency-end

pub mod artifacts;
pub mod private_feedback;
pub mod runtime_boundary;
