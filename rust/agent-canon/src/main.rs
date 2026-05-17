mod migration_audit;

use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() >= 2 && args[1] == "rust-migration-audit" {
        migration_audit::run(&args[2..]);
        return;
    }

    println!("agent-canon 0.1.0");
}
