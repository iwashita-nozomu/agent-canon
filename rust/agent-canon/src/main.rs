#![recursion_limit = "256"]

// @dependency-start
// contract implementation
// responsibility Provides the AgentCanon Rust CLI entrypoint.
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// downstream implementation docs.rs routes unified documentation formatting and checks
// downstream implementation jit_ir_to_lean.rs routes JIT-canonical JSON to Lean evidence generation
// downstream implementation local_llm.rs routes local LLM responsibility, search, index, and eval commands
// downstream implementation migration_audit.rs validates migration boundaries
// downstream implementation rust_migration_plan.rs prints sequential Rust migration candidates
// downstream implementation structured_analysis.rs routes structured prose/document analysis commands
// downstream implementation test_design.rs routes test design resilience diagnostics
// @dependency-end

mod docs;
mod jit_ir_to_lean;
mod local_llm;
mod migration_audit;
mod python_algorithm_contract;
mod python_module_groups;
mod python_structure_hash;
mod python_structure_hash_impact;
mod python_structure_hash_report;
mod python_structure_hash_scope_plan;
mod rust_migration_plan;
mod semantic_index;
mod structured_analysis;
mod test_design;

use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() >= 2 && (args[1] == "--version" || args[1] == "version") {
        println!("agent-canon 0.1.0");
        return;
    }

    if args.len() >= 2 && args[1] == "rust-migration-audit" {
        std::process::exit(migration_audit::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "rust-migration-plan" {
        std::process::exit(rust_migration_plan::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "docs" {
        std::process::exit(docs::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "jit-ir-to-lean" {
        std::process::exit(jit_ir_to_lean::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "local-llm" {
        std::process::exit(local_llm::run(&args[2..]));
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

    if args.len() >= 2 && args[1] == "python-module-groups-check" {
        std::process::exit(python_module_groups::run_check(&args[2..]));
    }

    eprintln!("agent-canon: unknown or missing command");
    eprintln!(
        "usage: agent-canon --version | docs <check|format|fix-math|fix-mermaid> [paths...] | test-design <check> [paths...] | jit-ir-to-lean --jit-ir <path> --namespace <Lean.Namespace> --out <path> | rust-migration-audit --root <repo-root> | rust-migration-plan --root <repo-root> [--limit N] | local-llm <command> | semantic-index <build|embed-provider|search|context-pack|responsibility-tree|similar|merge-candidates|thin-docs|natural-relations|discourse-relations|eval|compare-providers|eval-output> | structured-analysis <build|analyze|graph-contract|document-inventory|import-document-inventory> | python-structure-hash --root <repo-root> [paths...] | python-structure-hash-report --input <path> [--output <path>] | python-structure-hash-impact --before <path> --after <path> [--output <path>] | python-structure-hash-scope-plan --input <path> --dependency-report-dir <dir> [--output <path>] | python-algorithm-contract-check --root <repo-root> [paths...] | python-module-groups-check --root <repo-root> [--contract path]"
    );
    std::process::exit(2);
}
