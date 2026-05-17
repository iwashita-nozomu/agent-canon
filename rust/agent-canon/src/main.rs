// @dependency-start
// responsibility Provides the AgentCanon Rust CLI entrypoint.
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// downstream implementation migration_audit.rs validates migration boundaries
// downstream implementation mcp_inventory.rs checks MCP preflight scope and inventory
// downstream implementation rust_migration_plan.rs prints sequential Rust migration candidates
// @dependency-end

mod mcp_inventory;
mod migration_audit;
mod rust_migration_plan;

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

    eprintln!("agent-canon: unknown or missing command");
    eprintln!(
        "usage: agent-canon --version | rust-migration-audit --root <repo-root> | rust-migration-plan --root <repo-root> [--limit N] | mcp-inventory --root <repo-root> --require <server> [--session-cache] | mcp-preflight-policy --request-kind <kind>"
    );
    std::process::exit(2);
}
