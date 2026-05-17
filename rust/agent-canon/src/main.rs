// @dependency-start
// responsibility Provides the AgentCanon Rust CLI entrypoint.
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// downstream implementation migration_audit.rs validates migration boundaries
// @dependency-end

mod migration_audit;

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

    eprintln!("agent-canon: unknown or missing command");
    eprintln!("usage: agent-canon --version | rust-migration-audit --root <repo-root>");
    std::process::exit(2);
}
