//! Internal Rust library surface for AgentCanon-owned tools.

// @dependency-start
// contract implementation
// responsibility Exposes native parent-root authority, catalog, and proof-coverage APIs to AgentCanon tools and integration tests.
// downstream implementation authority/mod.rs owns authenticated parent-root and child-handoff APIs
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// @dependency-end

pub mod authority;
pub mod catalog;
pub mod tool_proof_coverage;
