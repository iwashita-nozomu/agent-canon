// @dependency-start
// responsibility Provides the AgentCanon Rust CLI entrypoint.
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// downstream implementation local_llm.rs routes local LLM responsibility, search, index, and eval commands
// downstream implementation migration_audit.rs validates migration boundaries
// downstream implementation mcp_inventory.rs checks MCP preflight scope and inventory
// downstream implementation rust_migration_plan.rs prints sequential Rust migration candidates
// @dependency-end

mod local_llm;
mod mcp_inventory;
mod migration_audit;
mod python_algorithm_contract;
mod python_module_groups;
mod python_structure_hash;
mod python_structure_hash_impact;
mod python_structure_hash_report;
mod rust_migration_plan;
mod semantic_index;

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

    if args.len() >= 2 && args[1] == "mcp-inventory" {
        std::process::exit(mcp_inventory::run_inventory(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "mcp-preflight-policy" {
        std::process::exit(mcp_inventory::run_policy(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "local-llm" {
        std::process::exit(local_llm::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "semantic-index" {
        std::process::exit(semantic_index::run(&args[2..]));
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

    if args.len() >= 2 && args[1] == "python-algorithm-contract-check" {
        std::process::exit(python_algorithm_contract::run(&args[2..]));
    }

    if args.len() >= 2 && args[1] == "python-module-groups-check" {
        std::process::exit(python_module_groups::run_check(&args[2..]));
    }

    eprintln!("agent-canon: unknown or missing command");
    eprintln!(
        "usage: agent-canon --version | rust-migration-audit --root <repo-root> | rust-migration-plan --root <repo-root> [--limit N] | mcp-inventory --root <repo-root> --require <server> [--session-cache] | mcp-preflight-policy --request-kind <kind> | local-llm <command> | semantic-index <build|embed-provider|search|context-pack|responsibility-tree|similar|merge-candidates|thin-docs|natural-relations|discourse-relations|eval|compare-providers|eval-output> | python-structure-hash --root <repo-root> [paths...] | python-structure-hash-report --input <path> [--output <path>] | python-structure-hash-impact --before <path> --after <path> [--output <path>] | python-algorithm-contract-check --root <repo-root> [paths...] | python-module-groups-check --root <repo-root> [--contract path]"
    );
    std::process::exit(2);
}
