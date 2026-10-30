// @dependency-start
// contract implementation
// responsibility Exposes shared catalog and proof-coverage APIs to the native CLI and integration tests.
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// @dependency-end

pub mod catalog;
pub mod tool_proof_coverage;
