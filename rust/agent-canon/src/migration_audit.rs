use std::path::Path;

pub fn run(args: &[String]) {
    let mut root = ".";

    let mut i = 0;
    while i < args.len() {
        if args[i] == "--root" && i + 1 < args.len() {
            root = &args[i + 1];
            i += 1;
        }
        i += 1;
    }

    let root_path = Path::new(root);
    let cargo_manifest = root_path.join("rust/agent-canon/Cargo.toml");

    if !cargo_manifest.exists() {
        eprintln!("RUST_MIGRATION_AUDIT=fail");
        eprintln!("RUST_MIGRATION_FINDING=missing-cargo-manifest");
        std::process::exit(1);
    }

    println!("RUST_MIGRATION_AUDIT=pass");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_root_argument() {
        let args = vec!["--root".to_string(), ".".to_string()];
        run(&args);
    }
}
