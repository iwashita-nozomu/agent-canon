// @dependency-start
// contract test
// responsibility Checks the native skill/dependency graph against the independently generated JSON and Mermaid artifacts.
// upstream implementation ../src/catalog/skill_dependency_graph.rs owns graph identity and actual Mermaid readback
// upstream design ../../../../../documents/design/skill-tool-invocation-graph.md defines the graph and checker contract
// upstream test ../../../../../tests/fixtures/skill_dependency_graph/expected.json records the frozen summary oracle
// @dependency-end

use agent_canon::catalog::skill_dependency_graph::{
    check_artifacts, GRAPH_JSON_PATH, GRAPH_MARKDOWN_PATH, GRAPH_SCHEMA,
};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};

const EXPECTED: &str =
    include_str!("../../../../../tests/fixtures/skill_dependency_graph/expected.json");
const CHECK_INPUTS: &[&str] = &[
    "agents/skills/catalog.yaml",
    "agents/skills/skill-dependencies.yaml",
    "agents/canonical/skills.md",
    "documents/design/skill-tool-invocation-graph.md",
    GRAPH_MARKDOWN_PATH,
    GRAPH_JSON_PATH,
];

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .expect("crate is nested under the repository root")
        .to_path_buf()
}

fn copy_check_inputs(source: &Path, destination: &Path) {
    for relative in CHECK_INPUTS {
        let from = source.join(relative);
        let to = destination.join(relative);
        fs::create_dir_all(to.parent().expect("artifact has parent directory"))
            .expect("create copied input parent");
        fs::copy(from, to).expect("copy graph checker input");
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut rendered = String::with_capacity(64);
    for byte in Sha256::digest(bytes) {
        use std::fmt::Write as _;
        let _ = write!(rendered, "{byte:02x}");
    }
    rendered
}

#[test]
fn native_checker_matches_the_independent_v2_artifact_oracle() {
    let root = repository_root();
    let expected: Value = serde_json::from_str(EXPECTED).expect("parse fixture oracle");
    assert_eq!(expected["schema"].as_str(), Some(GRAPH_SCHEMA));
    assert_eq!(expected["version"].as_u64(), Some(2));
    let summary = check_artifacts(&root).expect("validate generated graph artifacts");
    assert_eq!(
        summary.skill_count,
        expected["skill_count"].as_u64().unwrap() as usize
    );
    assert_eq!(
        summary.command_count,
        expected["command_count"].as_u64().unwrap() as usize
    );
    assert_eq!(
        summary.tool_count,
        expected["tool_count"].as_u64().unwrap() as usize
    );
    assert_eq!(
        summary.edge_count,
        expected["edge_count"].as_u64().unwrap() as usize
    );
    assert_eq!(
        summary.graph_digest,
        expected["graph_digest"].as_str().unwrap()
    );
    assert_eq!(
        summary.json_digest,
        expected["json_digest"].as_str().unwrap()
    );
    assert_eq!(
        summary.mermaid_digest,
        expected["mermaid_digest"].as_str().unwrap()
    );
    let json_bytes = fs::read(root.join(GRAPH_JSON_PATH)).expect("read checked JSON artifact");
    assert_eq!(
        sha256_hex(&json_bytes),
        expected["json_sha256"].as_str().unwrap()
    );
}

#[test]
fn actual_mermaid_node_removal_fails_even_when_readback_comments_remain() {
    let source = repository_root();
    let temp = tempfile::tempdir().expect("create temporary graph root");
    copy_check_inputs(&source, temp.path());
    let path = temp.path().join(GRAPH_MARKDOWN_PATH);
    let original = fs::read_to_string(&path).expect("read copied Mermaid artifact");
    let node_line = original
        .lines()
        .find(|line| {
            let trimmed = line.trim_start();
            trimmed.starts_with("n_skill_dependency_design[")
        })
        .expect("find actual dependency-design node");
    let edited = original.replacen(&format!("{node_line}\n"), "", 1);
    fs::write(&path, edited).expect("remove actual Mermaid node");

    let error = check_artifacts(temp.path()).expect_err("reject edited Mermaid syntax");
    assert!(error.contains("readback:mermaid_readback_actual_node_order_or_digest_mismatch"));
    assert!(error.contains("documents/runtime/skill-dependency-graph.md:edited-or-stale"));
}
