// @dependency-start
// contract implementation
// responsibility Exposes native evaluation, report-check, Eval-path, runtime, catalog, and proof APIs to the CLI and integration tests.
// upstream implementation runtime_boundary.rs owns external artifact I/O capabilities
// downstream implementation eval_manifest_paths.rs resolves canonical/legacy Eval manifests
// downstream implementation report_artifact_checks.rs owns pure report artifact checks
// downstream implementation run_evaluation.rs evaluates one selected run bundle
// downstream implementation catalog/mod.rs owns catalog, route, path, and source-span behavior
// downstream implementation tool_proof_coverage.rs owns catalog-backed proof coverage reports
// @dependency-end

pub mod catalog;
pub mod eval_manifest_paths;
pub mod report_artifact_checks;
pub mod run_evaluation;
pub mod runtime_boundary;
pub mod tool_proof_coverage;
