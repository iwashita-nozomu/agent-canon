#![recursion_limit = "256"]

// @dependency-start
// contract implementation
// responsibility Provides the AgentCanon Rust CLI entrypoint.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust tool migration policy
// downstream implementation docs.rs routes unified documentation formatting and checks
// downstream implementation config.rs applies managed Codex context defaults while preserving TOML values
// downstream implementation dependency_headers.rs checks selected dependency manifests and typed edge syntax
// downstream implementation check_merge_structure.rs validates local structural integration readback
// downstream implementation graph.rs routes one-build dependency and runtime-evidence graph commands
// downstream implementation ../../../../../tests/tools/test_fix_mermaid.py exercises docs formatter coverage readback through this CLI
// downstream implementation jit_ir_to_lean.rs routes JIT-canonical JSON to Lean evidence generation
// downstream implementation migration_audit.rs validates migration boundaries
// downstream implementation python_ast.rs shares native Python AST helper behavior
// downstream implementation python_helper_function_inventory.rs inventories Python helper roles
// downstream implementation surface_manifest.rs provides native source classification snapshots
// downstream implementation file_surface_inventory.rs preserves Git file-surface inventory and explicit report outputs
// downstream implementation rust_migration_plan.rs prints sequential Rust migration candidates
// downstream implementation structured_analysis.rs routes structured prose/document analysis commands
// downstream implementation test_design.rs routes test design resilience diagnostics
// @dependency-end

mod check_merge_structure;
mod config;
mod dependency_headers;
mod dependency_manifest;
mod docs;
mod file_surface_inventory;
mod graph;
mod jit_ir_to_lean;
mod migration_audit;
mod numeric_performance;
mod private_feedback;
mod python_algorithm_contract;
mod python_ast;
mod python_helper_function_inventory;
mod python_module_groups;
mod python_structure_hash;
mod python_structure_hash_impact;
mod python_structure_hash_report;
mod python_structure_hash_scope_plan;
mod rule_inventory;
mod runtime_boundary;
mod rust_migration_plan;
mod semantic_index;
mod skill_projection_registry;
mod structured_analysis;
mod surface_manifest;
mod test_design;

use std::env;

const HELP: &str = "AgentCanon's native command line interface.

Usage: agent-canon <command> [arguments]

Commands:
  knowledge|k <search|read|add|status|sync|capture>
  feedback|f <add|status|sync|capture>
  graph <build|status|query|context> [options]
  check-dependency-headers [--root <repo-root>] [--changed] [--surface <glob>]... [paths...]
  docs <check|format> [paths...]
  codex-config --source-config <path>
  test-design <check> [paths...]
  check-merge-structure --source <ref> [--target <ref>] [--compare-commit <ref>] [--repo-root <path>]
  jit-ir-to-lean --jit-ir <path> --namespace <Lean.Namespace> --out <path>
  numeric-performance [--input <path|->] [--format json]
  oop-python-rule-inventory|oop-cpp-rule-inventory [--root <repo-root>] [--format text|json|markdown]
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

    if args.len() >= 2 && args[1] == "numeric-performance" {
        std::process::exit(numeric_performance::run(&args[2..]));
    }

    if args.len() >= 2
        && matches!(
            args[1].as_str(),
            rule_inventory::PYTHON_SELECTOR | rule_inventory::CPP_SELECTOR
        )
    {
        std::process::exit(rule_inventory::run(&args[1], &args[2..]));
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

    if args.len() >= 2 && args[1] == "file-surface-inventory" {
        std::process::exit(file_surface_inventory::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "docs" {
        // Existing docs commands also run docs.rs post-format visualization
        // identity readback when a projection coverage marker is present.
        std::process::exit(docs::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "codex-config" {
        std::process::exit(config::run(&args[2..]));
    }

    if args.len() >= 2 && matches!(args[1].as_str(), "knowledge" | "k" | "feedback" | "f") {
        std::process::exit(private_feedback::run(&args[1..]));
    }

    if args.len() >= 2 && args[1] == "graph" {
        std::process::exit(graph::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "jit-ir-to-lean" {
        std::process::exit(jit_ir_to_lean::run(&args[2..]));
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
