#![recursion_limit = "256"]

// @dependency-start
// contract implementation
// responsibility Provides the AgentCanon Rust CLI entrypoint.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust tool migration policy
// upstream implementation lib.rs shares runtime-boundary and artifact APIs with the CLI
// downstream implementation lib.rs owns the existing private-feedback command route
// downstream implementation native_release.rs routes native release planning and publication
// downstream implementation lib.rs exposes the shared native docs command API
// downstream implementation check_algorithm_config_partition.rs checks algorithm config ownership and default policy
// downstream implementation config.rs applies managed Codex context defaults while preserving TOML values
// downstream implementation dependency_headers.rs checks selected dependency manifests and typed edge syntax
// downstream implementation check_merge_structure.rs validates local structural integration readback
// downstream implementation run_evaluation.rs scores and reports one agent run bundle
// downstream implementation generated_completeness.rs routes the G2 receipt producer
// downstream implementation graph.rs routes one-build dependency and runtime-evidence graph commands
// downstream implementation graph_client.rs exposes the in-process typed graph client API
// downstream implementation agent_search.rs routes explicit repository-search provider requests
// upstream implementation lib.rs exposes shared user-home path expansion
// downstream implementation tool_drift.rs checks tool, workflow, and documentation traces
// downstream implementation theorem_graph_board.rs builds formal-proof theorem route summaries
// downstream implementation ../../../../../tests/tools/test_fix_mermaid.py exercises docs formatter coverage readback through this CLI
// downstream implementation jit_ir_to_lean.rs routes JIT-canonical JSON to Lean evidence generation
// downstream implementation stablehlo_value_closure.rs exposes scoped SSA dependency closure APIs
// downstream implementation theorem_graph_circularity_check.rs validates theorem graph proof frontiers
// downstream implementation migration_audit.rs validates migration boundaries
// downstream implementation classify_path_risk.rs owns native path-risk and static-gate selection
// downstream implementation semantic_responsibility.rs validates contract schemas, identities, and references
// downstream implementation check_solid_evidence.rs validates SOLID evidence coverage for Python changes
// downstream implementation responsibility_scope.rs validates tracked-path owner coverage and planned path owners
// downstream implementation python_ast.rs shares native Python AST helper behavior
// downstream implementation python_cli_integer.rs shares Python-compatible CLI integer parsing
// downstream implementation python_text.rs shares Python-compatible Unicode string trimming
// downstream implementation python_helper_function_inventory.rs inventories Python helper roles
// downstream implementation surface_manifest.rs provides native source classification snapshots
// downstream implementation file_surface_inventory.rs preserves Git file-surface inventory and explicit report outputs
// downstream implementation rust_migration_plan.rs prints sequential Rust migration candidates
// downstream implementation structured_analysis.rs routes structured prose/document analysis commands
// downstream implementation test_design.rs routes test design resilience diagnostics
// downstream implementation notebook_quality.rs validates notebook quality as readable runnable demos
// downstream implementation result_logs/mod.rs converts and summarizes JSONL result records
// downstream implementation lib.rs exposes the selected native Lean proof environment API
// downstream implementation lsp_code_analysis.rs serves the native LSP CLI and provider API
// upstream implementation lib.rs exposes native SCIP index and Git dependency summary APIs
// @dependency-end

mod agent_search;
mod check_algorithm_config_partition;
mod check_merge_structure;
mod check_solid_evidence;
pub mod classify_path_risk;
mod config;
mod dependency_headers;
mod dependency_manifest;
mod file_surface_inventory;
mod graph;
pub mod graph_client;
mod jit_ir_to_lean;
pub mod log_surface_inventory;
mod migration_audit;
mod notebook_quality;
mod numeric_performance;
mod python_algorithm_contract;
mod python_ast;
mod python_cli_integer;
mod python_helper_function_inventory;
mod python_module_groups;
mod python_structure_hash;
mod python_structure_hash_impact;
mod python_structure_hash_report;
mod python_structure_hash_scope_plan;
mod python_text;
mod responsibility_scope;
mod result_logs;
mod rule_inventory;
mod run_log_contract;
mod rust_migration_plan;
mod semantic_index;
mod semantic_responsibility;
pub mod skill_document_reader;
mod skill_projection_registry;
pub mod source_dependency_graph;
mod structured_analysis;
mod surface_manifest;
mod test_design;
mod tool_drift;

#[cfg(not(test))]
use agent_canon::runtime_boundary;
use agent_canon::{
    catalog, entrypoint_composer, generated_completeness, native_release, run_evaluation,
    stablehlo_value_closure, template_bundle, theorem_graph_board, theorem_graph_circularity_check,
    tool_proof_coverage,
};
use std::env;

const HELP: &str = "AgentCanon's native command line interface.

Usage: agent-canon <command> [arguments]

Commands:
  knowledge|k <search|read|add|status|sync|capture>
  feedback|f <add|status|sync|capture>
  graph <build|status|query|context> [options]
  agent-search [search options]
  check-dependency-headers [--root <repo-root>] [--changed] [--surface <glob>]... [paths...]
  classify-path-risk [--path PATH]... [--paths-file PATH] [--format text|json|github-output] [--full-confidence]
  docs <check|format|check-bootstrap> [options] [paths...]
  codex-config --source-config <path>
  test-design <check> [paths...]
  run-evaluation (--run-id ID|--report-dir PATH) [options]
  materialize-agent-canon-pr-g2 --g1-bundle <path> --source-root <root> --control-parent-root <root> --runtime-root <root> [--output <path>]
  notebook-quality [paths...] [--root <repo-root>] [--changed|--all] [--format text|json]
  check-algorithm-config-partition [--root <repo-root>] [--exclude <pattern>]... [--format text|json] [--fail-on-finding] [--fail-on-default] [paths...]
  responsibility-scope [--root <repo-root>] [--manifest <path>] [--format text|json] [--path <path>]...
  check-merge-structure --source <ref> [--target <ref>] [--compare-commit <ref>] [--repo-root <path>]
  jit-ir-to-lean --jit-ir <path> --namespace <Lean.Namespace> --out <path>
  log-surface-inventory [--root <repo-root>] [--format text|json] [--output <path>] [--check --baseline <path>]
  stablehlo-value-closure --ir <path> --function NAME --value SSA [--region-id ID] [--max-nodes N] [--format text|json]
  theorem-graph-circularity-check --graph <path> [--out <path>] [--format text|json|markdown] [--fail-on-finding]
  numeric-performance [--input <path|->] [--format json]
  tool-catalog [--root <repo-root>] [--format text|json|markdown]
  tool-drift [--root <repo-root>] [--contract NAME]... [--format text|json]
  tool-proof-coverage [--root <repo-root>] [--format text|json|markdown] [--tool-id ID]... [--require-lean-verified]
  theorem-graph-board --graph <path> [--out <path>] [--format json|markdown] [--fail-on-open] [--fail-on-unknown]
  check-run-log-contract [paths...] [--root <repo-root>] [--exclude PATTERN]... [--format text|json] [--fail-on-finding]
  skill-document-reader <index|chunk|admit> [options]
  lsp-code-analysis analyze [--root ROOT] [--files FILES...] [--server LANGUAGE=COMMAND] [--timeout SECONDS] [--format json|text]
  scip-index <index|query> [options]
  git-dependency-diff-summary [options] [pathspecs...]
  jsonl-to-md <input> <output>
  summarize-hlo-jsonl [--top N] [--only-case CASE] <jsonl>
  oop-python-rule-inventory|oop-cpp-rule-inventory [--root <repo-root>] [--format text|json|markdown]
  lean-proof-env <init|smoke|agent-smoke|counterexample-smoke|all-smoke|check-file> [options]
  check-semantic-responsibility-contract [paths...] [--root ROOT] [--template TEMPLATE] [--instance INSTANCE] [--artifact-root ARTIFACT_ROOT] [--format text|json]
  check-solid-evidence [paths...] [--root ROOT] [--changed] [--base-ref BASE_REF] [--evidence EVIDENCE] [--exclude EXCLUDE] [--verbose] [--format text|json]
  rust-migration-audit --root <repo-root>
  rust-migration-plan --root <repo-root> [--limit N] [--format text|json]
  surface-manifest [--root PATH] [--prefix PREFIX] [--manifest PATH] <normalized-snapshot|check-doc|projection-forbidden-roots>
  file-surface-inventory --root <repo-root> [--root-only|--agentcanon-only] [--json-out <path>] [--markdown-out <path>] [--max-markdown-entries N]
  semantic-index <operation>
  structured-analysis <operation>
  python-structure-hash --root <repo-root> [paths...]
  python-structure-hash-report --input <path> [--output <path>]
  python-structure-hash-impact --before <path> --after <path> [--output <path>]
  python-structure-hash-scope-plan --input <path> --dependency-report-dir <dir> [--output <path>]
  python-algorithm-contract-check --root <repo-root> [paths...]
  helper-function-inventory [paths...] [--root <repo-root>] [--format text|json|markdown]
  python-module-groups-check --root <repo-root> [--contract path]
  compose-consumer-entrypoint --base <path> --specific <path> --output <path> [--source-root <path>]
  template-bundle <export|verify|native-package|native-verify|native-version> [options]
  native-release <prepare|select-artifacts|publish|compare-reproducible> [options]

Options:
  -h, --help     Print help
  --version      Print version";

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() == 1 || (args.len() == 2 && matches!(args[1].as_str(), "-h" | "--help" | "help"))
    {
        println!("{HELP}");
        return;
    }

    if args.len() >= 2 && (args[1] == "--version" || args[1] == "version") {
        println!(
            "agent-canon {}",
            option_env!("AGENT_CANON_RELEASE_VERSION").unwrap_or(env!("CARGO_PKG_VERSION"))
        );
        return;
    }

    if args.len() >= 2 && args[1] == "compose-consumer-entrypoint" {
        std::process::exit(entrypoint_composer::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "template-bundle" {
        std::process::exit(template_bundle::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "native-release" {
        std::process::exit(native_release::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "log-surface-inventory" {
        std::process::exit(log_surface_inventory::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "run-evaluation" {
        std::process::exit(run_evaluation::run_cli(&args[2..]));
    }

    if args.len() >= 2 && args[1] == generated_completeness::SELECTOR {
        std::process::exit(generated_completeness::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "numeric-performance" {
        std::process::exit(numeric_performance::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == stablehlo_value_closure::SELECTOR {
        std::process::exit(stablehlo_value_closure::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == theorem_graph_circularity_check::SELECTOR {
        std::process::exit(theorem_graph_circularity_check::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "tool-catalog" {
        std::process::exit(catalog::tool_catalog::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "tool-drift" {
        std::process::exit(tool_drift::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "tool-proof-coverage" {
        std::process::exit(tool_proof_coverage::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "theorem-graph-board" {
        std::process::exit(theorem_graph_board::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "check-run-log-contract" {
        std::process::exit(run_log_contract::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "skill-document-reader" {
        std::process::exit(skill_document_reader::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "classify-path-risk" {
        std::process::exit(classify_path_risk::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "lsp-code-analysis" {
        std::process::exit(agent_canon::lsp_code_analysis::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "scip-index" {
        std::process::exit(agent_canon::scip_index::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "git-dependency-diff-summary" {
        std::process::exit(agent_canon::git_dependency_diff_summary::run(&args[2..]));
    }

    if args.len() >= 2
        && matches!(
            args[1].as_str(),
            rule_inventory::PYTHON_SELECTOR | rule_inventory::CPP_SELECTOR
        )
    {
        std::process::exit(rule_inventory::run(&args[1], &args[2..]));
    }

    if args.len() >= 2 && args[1] == semantic_responsibility::SELECTOR {
        std::process::exit(semantic_responsibility::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == agent_canon::lean_proof_env::SELECTOR {
        std::process::exit(agent_canon::lean_proof_env::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == check_solid_evidence::SELECTOR {
        std::process::exit(check_solid_evidence::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "rust-migration-audit" {
        std::process::exit(migration_audit::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "rust-migration-plan" {
        std::process::exit(rust_migration_plan::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "check-dependency-headers" {
        std::process::exit(dependency_headers::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "surface-manifest" {
        std::process::exit(surface_manifest::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == responsibility_scope::SELECTOR {
        std::process::exit(responsibility_scope::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "file-surface-inventory" {
        std::process::exit(file_surface_inventory::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "docs" {
        // Existing docs commands also run docs.rs post-format visualization
        // identity readback when a projection coverage marker is present.
        std::process::exit(agent_canon::docs::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "codex-config" {
        std::process::exit(config::run(&args[2..]));
    }

    if args.len() >= 2 && matches!(args[1].as_str(), "knowledge" | "k" | "feedback" | "f") {
        std::process::exit(agent_canon::private_feedback::run(&args[1..]));
    }

    if args.len() >= 2 && args[1] == "graph" {
        std::process::exit(graph::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "agent-search" {
        std::process::exit(agent_search::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "jit-ir-to-lean" {
        std::process::exit(jit_ir_to_lean::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "jsonl-to-md" {
        std::process::exit(result_logs::run_jsonl_to_md(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "summarize-hlo-jsonl" {
        std::process::exit(result_logs::run_summary(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "semantic-index" {
        std::process::exit(semantic_index::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "structured-analysis" {
        std::process::exit(structured_analysis::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "test-design" {
        std::process::exit(test_design::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "notebook-quality" {
        std::process::exit(notebook_quality::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "check-merge-structure" {
        std::process::exit(check_merge_structure::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "python-structure-hash" {
        std::process::exit(python_structure_hash::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "python-structure-hash-report" {
        std::process::exit(python_structure_hash_report::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "python-structure-hash-impact" {
        std::process::exit(python_structure_hash_impact::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "python-structure-hash-scope-plan" {
        std::process::exit(python_structure_hash_scope_plan::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "python-algorithm-contract-check" {
        std::process::exit(python_algorithm_contract::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "check-algorithm-config-partition" {
        std::process::exit(check_algorithm_config_partition::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "helper-function-inventory" {
        std::process::exit(python_helper_function_inventory::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "python-module-groups-check" {
        std::process::exit(python_module_groups::run_check(&args[2..]));
    }

    eprintln!("agent-canon: unknown or missing command");
    eprintln!("Run 'agent-canon --help' for usage.");
    std::process::exit(2);
}

#[cfg(test)]
mod source_dependency_tests;

#[cfg(test)]
mod runtime_boundary {
    use std::path::{Path, PathBuf};

    pub(crate) use agent_canon::runtime_boundary::{
        runtime_root_is_explicit, stable_source_key, test_runtime_root_path,
        validate_external_target, RUNTIME_ROOT_ENV,
    };

    // Cargo builds the library as a normal dependency of the binary test target, without `cfg(test)`.
    // Preserve only the binary test fixture selection and delegate all resolution to the library.
    pub(crate) fn resolve_runtime_root(source_root: &Path) -> Result<PathBuf, String> {
        resolve_runtime_root_at(source_root, None)
    }

    pub(crate) fn resolve_runtime_root_at(
        source_root: &Path,
        requested: Option<&Path>,
    ) -> Result<PathBuf, String> {
        match requested {
            Some(requested) => {
                agent_canon::runtime_boundary::resolve_runtime_root_at(source_root, Some(requested))
            }
            None => {
                let test_root = test_runtime_root_path(source_root)?;
                agent_canon::runtime_boundary::resolve_runtime_root_at(
                    source_root,
                    Some(&test_root),
                )
            }
        }
    }
}

#[cfg(test)]
mod agent_search_tests;
