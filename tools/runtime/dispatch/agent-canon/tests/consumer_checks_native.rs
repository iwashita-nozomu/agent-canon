// @dependency-start
// contract test
// responsibility Exercises project-owned CMake registrations and Git source independence through the native CLI.
// upstream implementation ../src/experiment_registry/cmake.rs CMake registry validation
// upstream implementation ../src/docs/source_independence.rs index policy validation
// @dependency-end

use std::fs;
use std::path::Path;
use std::process::{Command, Output};

const CMAKE_REGISTRY: &str = r#"
schema_version = 1
[defaults]
integration_branch = "main"
result_layout = "result/<run-id>/{raw,summary}"
[[topic]]
topic = "one"
branch = "experiment/1-one"
topic_dir = "experiments/one"
result_root = "experiments/one/result"
report_root = "experiments/one/report"
"#;

fn cli(root: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .current_dir(root)
        .args(args)
        .output()
        .expect("run native consumer check")
}

fn git(root: &Path, args: &[&str]) -> Vec<u8> {
    let result = Command::new("git")
        .current_dir(root)
        .args(args)
        .output()
        .expect("run Git on fixture");
    assert!(
        result.status.success(),
        "git {args:?}: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    result.stdout
}

fn write(root: &Path, relative: &str, content: &str) {
    let path = root.join(relative);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, content).unwrap();
}

#[test]
fn cmake_registry_reads_project_entry_and_rejects_bad_registrations() {
    let work = tempfile::tempdir().unwrap();
    let root = work.path();
    fs::create_dir_all(root.join("experiments/one")).unwrap();
    write(
        root,
        "project/CMakeLists.txt",
        "project(consumer LANGUAGES CXX)\n",
    );
    let registry = "experiments/registry.toml";
    write(root, registry, CMAKE_REGISTRY);
    let args = [
        "experiment-registry",
        "--repo-root",
        ".",
        "--profile",
        "cmake",
        "--cmake-entry",
        "project/CMakeLists.txt",
    ];
    let output = cli(root, &args);
    assert!(output.status.success(), "{output:?}");
    assert!(!cli(root, &["experiment-registry", "--repo-root", "."])
        .status
        .success());
    for (input, fragment) in [
        (
            CMAKE_REGISTRY.replace("schema_version = 1", "schema_version = 2"),
            "schema_version",
        ),
        (
            CMAKE_REGISTRY.replace("topic_dir = \"experiments/one\"", "topic_dir = false"),
            "topic_dir",
        ),
        (
            CMAKE_REGISTRY.replace("topic_dir = \"experiments/one\"", "topic_dir = \"../\""),
            "within the repository",
        ),
        (
            CMAKE_REGISTRY.replace(
                "topic_dir = \"experiments/one\"",
                "topic_dir = \"experiments/missing\"",
            ),
            "experiments/missing",
        ),
    ] {
        write(root, registry, &input);
        let output = cli(root, &args);
        assert!(!output.status.success(), "{output:?}");
        assert!([output.stdout, output.stderr]
            .iter()
            .any(|part| String::from_utf8_lossy(part).contains(fragment)));
    }
    write(root, registry, CMAKE_REGISTRY);
    fs::remove_file(root.join("project/CMakeLists.txt")).unwrap();
    let output = cli(root, &args);
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stdout).contains("CMake entry"));
}

#[test]
fn declared_source_policy_checks_index_without_requiring_seed_files() {
    let work = tempfile::tempdir().unwrap();
    let root = work.path();
    git(root, &["init", "-q"]);
    write(
        root,
        "README.md",
        "The tool is distributed outside the product.\n",
    );
    write(
        root,
        ".github/workflows/check.yml",
        "name: ordinary consumer\n",
    );
    write(
        root,
        ".github/workflows/approved.yml",
        "name: references vendor/agent-canon\n",
    );
    write(
        root,
        "consumer.toml",
        r#"
source_name_pattern = '(?i)agent[\W_]*canon'
forbidden_paths = ["vendor/agent-canon", ".agent-canon"]
forbidden_path_fragments = ["agent-canon-static-seed"]
[[references]]
paths = [".github/workflows"]
allow_paths = [".github/workflows/approved.yml"]
forbidden = ["vendor/agent-canon", "checkout_agent_canon_submodule"]
"#,
    );
    git(root, &["add", "."]);
    git(
        root,
        &[
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "consumer",
        ],
    );
    let args = [
        "docs",
        "check-bootstrap",
        "--root",
        ".",
        "--source-policy",
        "consumer.toml",
    ];
    let initial = cli(root, &args);
    assert!(initial.status.success(), "{initial:?}");

    write(
        root,
        ".gitmodules",
        "[submodule \"source\"]\n path = vendor/agent-canon\n url = ../agent-canon.git\n",
    );
    write(
        root,
        ".github/workflows/check.yml",
        "name: uses checkout_agent_canon_submodule\n",
    );
    write(root, "nested/agent-canon-static-seed.json", "{}");
    write(root, ".agent-canon/data", "staged source\n");
    write(root, "pointer", "../agent-canon\n");
    git(
        root,
        &[
            "add",
            "-f",
            ".gitmodules",
            ".github/workflows/check.yml",
            "nested",
            ".agent-canon",
        ],
    );
    let blob = String::from_utf8(git(root, &["hash-object", "-w", "pointer"])).unwrap();
    let link = format!("120000,{},source-link", blob.trim());
    git(root, &["update-index", "--add", "--cacheinfo", &link]);
    let head = String::from_utf8(git(root, &["rev-parse", "HEAD"])).unwrap();
    let gitlink = format!("160000,{},vendor/agent-canon", head.trim());
    git(root, &["update-index", "--add", "--cacheinfo", &gitlink]);
    let before = git(root, &["ls-files", "--stage", "-z"]);
    // Verify the staged input rather than accidentally reading the working copy.
    write(
        root,
        ".github/workflows/check.yml",
        "name: working copy has no forbidden reference\n",
    );
    let output = cli(root, &args);
    let text = String::from_utf8(output.stdout).unwrap();
    assert_eq!(output.status.code(), Some(1), "{text}");
    for fragment in [
        "forbidden-source-submodule: .gitmodules",
        "forbidden-source-gitlink: vendor/agent-canon",
        "forbidden-source-symlink: source-link",
        "forbidden-source-path: nested/agent-canon-static-seed.json",
        "forbidden-source-path: .agent-canon/data",
        "forbidden-source-reference: .github/workflows/check.yml: checkout_agent_canon_submodule",
    ] {
        assert!(text.contains(fragment), "{text}");
    }
    assert!(!text.contains("approved.yml"), "{text}");
    assert_eq!(before, git(root, &["ls-files", "--stage", "-z"]));
}
