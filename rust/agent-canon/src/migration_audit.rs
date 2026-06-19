// @dependency-start
// contract implementation
// responsibility Validates AgentCanon Rust migration boundaries.
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// upstream environment ../../../.devcontainer/post-create.sh installs Rust tooling outside Dockerfile
// downstream implementation ../../../tools/bin/agent-canon invokes this command through the CLI wrapper
// @dependency-end

use std::fs;
use std::path::{Path, PathBuf};

const REQUIRED_PATHS: &[&str] = &[
    "documents/rust-agent-tool-migration.md",
    "agent-canon-environment.toml",
    "rust/agent-canon/Cargo.toml",
    "rust/agent-canon/src/main.rs",
    "rust/agent-canon/src/local_llm.rs",
    "rust/agent-canon/src/mcp_inventory.rs",
    "rust/agent-canon/src/migration_audit.rs",
    "rust/agent-canon/src/rust_migration_plan.rs",
    "tools/bin/agent-canon",
];

const REQUIRED_POST_CREATE_SNIPPETS: &[&str] = &[
    "rustup toolchain install",
    "rustfmt",
    "clippy",
    "rust-analyzer",
    "cargo build --release",
    "${tools_home}/agent-canon/bin/agent-canon",
    "/usr/local/bin/agent-canon",
];

const FORBIDDEN_DOCKERFILE_SNIPPETS: &[&str] = &[
    "rustup",
    "cargo build",
    "cargo install",
    "cargo test",
    "cargo clippy",
    "cargo fmt",
    "rustc --version",
];

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args) {
        Ok(parsed) => render(findings(&parsed.root)),
        Err(message) => {
            eprintln!("RUST_MIGRATION_AUDIT=fail");
            eprintln!("RUST_MIGRATION_FINDING=invalid-arguments:{message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut root = PathBuf::from(".");
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    let value = args
                        .get(index + 1)
                        .ok_or_else(|| "--root requires a value".to_string())?;
                    root = PathBuf::from(value);
                    index += 2;
                }
                unknown => return Err(format!("unknown argument {unknown}")),
            }
        }
        Ok(Self { root })
    }
}

fn findings(root: &Path) -> Vec<String> {
    let mut result = Vec::new();
    result.extend(missing_required_paths(root));
    result.extend(missing_post_create_snippets(root));
    result.extend(forbidden_dockerfile_snippets(root));
    result
}

fn missing_required_paths(root: &Path) -> Vec<String> {
    REQUIRED_PATHS
        .iter()
        .filter(|relative| !root.join(relative).exists())
        .map(|relative| format!("missing-path:{relative}"))
        .collect()
}

fn missing_post_create_snippets(root: &Path) -> Vec<String> {
    let relative = ".devcontainer/post-create.sh";
    let Some(text) = read_optional(root.join(relative)) else {
        return vec![format!("missing-path:{relative}")];
    };
    REQUIRED_POST_CREATE_SNIPPETS
        .iter()
        .filter(|snippet| !text.contains(**snippet))
        .map(|snippet| format!("post-create-missing:{snippet}"))
        .collect()
}

fn forbidden_dockerfile_snippets(root: &Path) -> Vec<String> {
    let Some(text) = read_optional(root.join("docker/Dockerfile")) else {
        return Vec::new();
    };
    FORBIDDEN_DOCKERFILE_SNIPPETS
        .iter()
        .filter(|snippet| text.contains(**snippet))
        .map(|snippet| format!("dockerfile-forbidden:{snippet}"))
        .collect()
}

fn read_optional(path: PathBuf) -> Option<String> {
    fs::read_to_string(path).ok()
}

fn render(findings: Vec<String>) -> i32 {
    if findings.is_empty() {
        println!("RUST_MIGRATION_AUDIT=pass");
        return 0;
    }
    eprintln!("RUST_MIGRATION_AUDIT=fail");
    for finding in findings {
        eprintln!("RUST_MIGRATION_FINDING={finding}");
    }
    1
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn parse_root_argument() {
        let args = vec!["--root".to_string(), ".".to_string()];
        let parsed = Args::parse(&args).expect("argument parse should succeed");
        assert_eq!(parsed.root, PathBuf::from("."));
    }

    #[test]
    fn audit_passes_for_complete_fixture() {
        let root = make_fixture_root();
        write_fixture(&root);

        assert!(findings(&root).is_empty());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn audit_reports_missing_wrapper() {
        let root = make_fixture_root();
        write_fixture(&root);
        fs::remove_file(root.join("tools/bin/agent-canon")).expect("remove wrapper");

        assert!(findings(&root).contains(&"missing-path:tools/bin/agent-canon".to_string()));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn audit_rejects_dockerfile_cargo_test() {
        let root = make_fixture_root();
        write_fixture(&root);
        write(
            &root,
            "docker/Dockerfile",
            "FROM ubuntu:22.04\nRUN cargo test\n",
        );

        assert!(findings(&root).contains(&"dockerfile-forbidden:cargo test".to_string()));
        let _ = fs::remove_dir_all(root);
    }

    fn make_fixture_root() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("agent-canon-rust-audit-{suffix}"))
    }

    fn write_fixture(root: &Path) {
        for path in REQUIRED_PATHS {
            write(root, path, "fixture\n");
        }
        write(
            root,
            ".devcontainer/post-create.sh",
            &REQUIRED_POST_CREATE_SNIPPETS.join("\n"),
        );
        write(root, "docker/Dockerfile", "FROM ubuntu:22.04\n");
    }

    fn write(root: &Path, relative: &str, text: &str) {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().expect("fixture path has parent")).expect("mkdir");
        fs::write(path, text).expect("write fixture");
    }
}
