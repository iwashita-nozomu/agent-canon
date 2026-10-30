use crate::source_dependency_graph;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock must be after the Unix epoch")
            .as_nanos();
        let count = SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "agent-canon-source-dependency-{}-{nanos}-{count}",
            std::process::id()
        ));
        fs::create_dir_all(&root).expect("fixture root must be created");
        Self(root)
    }

    fn write(&self, relative: &str, text: &str) {
        let path = self.0.join(relative);
        fs::create_dir_all(path.parent().expect("fixture file has a parent"))
            .expect("fixture parent must be created");
        fs::write(path, text).expect("fixture source must be written");
    }

    fn track_all(&self) {
        let init = Command::new("git")
            .arg("-C")
            .arg(&self.0)
            .args(["init", "-q"])
            .status()
            .expect("git init must run");
        assert!(init.success(), "git init must succeed");
        let add = Command::new("git")
            .arg("-C")
            .arg(&self.0)
            .args(["add", "--", "."])
            .status()
            .expect("git add must run");
        assert!(add.success(), "git add must succeed");
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn oracle_id(prefix: &str, values: &[Value]) -> String {
    let mut record = vec![Value::String(prefix.to_string())];
    record.extend_from_slice(values);
    format!(
        "{prefix}:{}",
        sha256_hex(
            &serde_json::to_vec(&Value::Array(record)).expect("oracle JSON is serializable")
        )
    )
}

fn fixture() -> Fixture {
    let fixture = Fixture::new();
    fixture.write(
        "agents/skills/catalog.yaml",
        "skill_families:\n  - id: example\n    canonical_doc: agents/skills/example.md\n    shim: .codex/personal/skills/example/SKILL.md\n",
    );
    fixture.write("agents/skills/example.md", "Canonical skill owner.\n");
    fixture.write("documents/architecture.md", "Architecture source.\n");
    fixture.write("documents/user_guide.md", "User documentation.\n");
    fixture.write(
        "documents/consumer.md",
        "<!--\n@dependency-start\nupstream design architecture.md architecture context\ndownstream reference user_guide.md reader documentation\ndownstream implementation ../.codex/personal/skills/*/SKILL.md canonical skill owner\n@dependency-end\n-->\nConsumer source.\n",
    );
    fixture.track_all();
    fixture
}

#[test]
fn tracked_source_projection_has_stable_ids_hash_context_and_review_outputs() {
    let fixture = fixture();
    let root = &fixture.0;
    let edges = source_dependency_graph::dependency_edges(root).unwrap();
    assert_eq!(
        edges,
        vec![
            source_dependency_graph::SourceDependencyEdge {
                source: "documents/consumer.md".into(),
                direction: "downstream".into(),
                kind: "implementation".into(),
                target: "agents/skills/example.md".into(),
                reason: "canonical skill owner".into(),
                line: 5,
            },
            source_dependency_graph::SourceDependencyEdge {
                source: "documents/consumer.md".into(),
                direction: "downstream".into(),
                kind: "reference".into(),
                target: "documents/user_guide.md".into(),
                reason: "reader documentation".into(),
                line: 4,
            },
            source_dependency_graph::SourceDependencyEdge {
                source: "documents/consumer.md".into(),
                direction: "upstream".into(),
                kind: "design".into(),
                target: "documents/architecture.md".into(),
                reason: "architecture context".into(),
                line: 3,
            },
        ]
    );

    let expected_node_paths = [
        "agents/skills/example.md",
        "documents/architecture.md",
        "documents/consumer.md",
        "documents/user_guide.md",
    ];
    let expected_nodes: Vec<Value> = expected_node_paths
        .iter()
        .map(|path| {
            json!({
                "id": oracle_id("node", &[json!(path)]),
                "path": path
            })
        })
        .collect();
    let consumer = oracle_id("node", &[json!("documents/consumer.md")]);
    let skill = oracle_id("node", &[json!("agents/skills/example.md")]);
    let guide = oracle_id("node", &[json!("documents/user_guide.md")]);
    let architecture = oracle_id("node", &[json!("documents/architecture.md")]);
    let expected_facts = vec![
        json!({
            "id": oracle_id("dependency", &[
                json!("documents/consumer.md"), json!("downstream"), json!("implementation"),
                json!("agents/skills/example.md"), json!("canonical skill owner"), json!(5)
            ]),
            "kind": "dependency", "inferred": false, "from": consumer, "to": skill,
            "producer": "tracked-source-manifest", "source_path": "documents/consumer.md",
            "source_span": {"path": "documents/consumer.md", "start_line": 5, "start_column": 1, "end_line": 5, "end_column": 1},
            "evidence_ref": "documents/consumer.md:5", "authority": "tracked-source",
            "dependency_detail": {"direction": "downstream", "kind": "implementation", "reason": "canonical skill owner"}
        }),
        json!({
            "id": oracle_id("dependency", &[
                json!("documents/consumer.md"), json!("downstream"), json!("reference"),
                json!("documents/user_guide.md"), json!("reader documentation"), json!(4)
            ]),
            "kind": "dependency", "inferred": false, "from": consumer, "to": guide,
            "producer": "tracked-source-manifest", "source_path": "documents/consumer.md",
            "source_span": {"path": "documents/consumer.md", "start_line": 4, "start_column": 1, "end_line": 4, "end_column": 1},
            "evidence_ref": "documents/consumer.md:4", "authority": "tracked-source",
            "dependency_detail": {"direction": "downstream", "kind": "reference", "reason": "reader documentation"}
        }),
        json!({
            "id": oracle_id("dependency", &[
                json!("documents/consumer.md"), json!("upstream"), json!("design"),
                json!("documents/architecture.md"), json!("architecture context"), json!(3)
            ]),
            "kind": "dependency", "inferred": false, "from": consumer, "to": architecture,
            "producer": "tracked-source-manifest", "source_path": "documents/consumer.md",
            "source_span": {"path": "documents/consumer.md", "start_line": 3, "start_column": 1, "end_line": 3, "end_column": 1},
            "evidence_ref": "documents/consumer.md:3", "authority": "tracked-source",
            "dependency_detail": {"direction": "upstream", "kind": "design", "reason": "architecture context"}
        }),
    ];
    let expected_fingerprint = sha256_hex(
        &serde_json::to_vec(&Value::Array(expected_facts.clone()))
            .expect("oracle facts are serializable"),
    );
    let projection = source_dependency_graph::build_dependency_projection(root).unwrap();
    assert_eq!(projection.nodes, expected_nodes);
    assert_eq!(projection.facts, expected_facts);
    assert_eq!(projection.fingerprint, expected_fingerprint);
    assert_eq!(projection.payload()["projection"], "tracked-source");

    let context =
        source_dependency_graph::build_context_projection(root, "documents/consumer.md", 1)
            .unwrap();
    assert_eq!(context.resolved_path, "documents/consumer.md");
    assert_eq!(context.snapshot_commit, "working-tree");
    assert_eq!(
        context.content_sha256,
        sha256_hex(
            fs::read(root.join("documents/consumer.md"))
                .unwrap()
                .as_slice()
        )
    );
    assert_eq!(
        context.evidence_paths,
        vec![
            "agents/skills/example.md".to_string(),
            "documents/architecture.md".to_string(),
            "documents/consumer.md".to_string(),
            "documents/user_guide.md".to_string()
        ]
    );
    assert_eq!(
        context.parent_paths,
        vec!["documents/architecture.md".to_string()]
    );
    assert_eq!(context.fingerprint, expected_fingerprint);
    assert_eq!(context.payload()["projection"], "tracked-source");
    assert!(
        source_dependency_graph::build_context_projection(root, "documents/consumer.md", -1)
            .unwrap_err()
            .to_string()
            .contains("context depth must be non-negative")
    );

    let edges_out = root.join("scratch/review/edges.tsv");
    let manifests_out = root.join("scratch/review/manifests.txt");
    source_dependency_graph::write_review_projection(root, &edges_out, &manifests_out).unwrap();
    assert_eq!(
        fs::read_to_string(edges_out).unwrap(),
        "downstream\timplementation\tdocuments/consumer.md\tagents/skills/example.md\ndownstream\treference\tdocuments/consumer.md\tdocuments/user_guide.md\nupstream\tdesign\tdocuments/consumer.md\tdocuments/architecture.md\n"
    );
    assert_eq!(
        fs::read_to_string(manifests_out).unwrap(),
        "documents/consumer.md\n"
    );
    assert!(!root.join(".agent-canon").exists());
}

#[test]
fn source_selection_and_header_failures_match_the_review_contract() {
    let fixture = fixture();
    let root = &fixture.0;
    assert!(source_dependency_graph::is_text_source("docs/README.MD"));
    assert!(!source_dependency_graph::is_text_source(
        "reports/review.md"
    ));
    assert!(!source_dependency_graph::is_text_source(
        "tests/fixtures/nvidia/raw.txt"
    ));
    assert!(source_dependency_graph::is_text_source(
        "tests/fixtures/nvidia/raw.TXT"
    ));
    assert!(source_dependency_graph::source_paths(root)
        .unwrap()
        .contains(&"documents/consumer.md".to_string()));

    fixture.write(
        "documents/duplicate.md",
        "# @dependency-start\n# @dependency-start\n# @dependency-end\n",
    );
    assert_eq!(
        source_dependency_graph::parse_manifest_document(root, "documents/duplicate.md")
            .unwrap_err()
            .to_string(),
        "documents/duplicate.md:2: duplicate @dependency-start"
    );

    fixture.write("lib.rs", "Shared implementation.\n");
    fixture.write(
        "tools/component.rs",
        "// @dependency-start\n// upstream implementation ../lib.rs support  with spaces,\n// @dependency-end\n",
    );
    assert_eq!(
        source_dependency_graph::parse_manifest_edges(root, "tools/component.rs").unwrap(),
        vec![source_dependency_graph::SourceDependencyEdge {
            source: "tools/component.rs".into(),
            direction: "upstream".into(),
            kind: "implementation".into(),
            target: "lib.rs".into(),
            reason: "support  with spaces".into(),
            line: 2,
        }]
    );

    fixture.write(
        "documents/invalid_kind.md",
        "<!--\n@dependency-start\nupstream invalid architecture.md invalid kind\n@dependency-end\n-->\n",
    );
    assert_eq!(
        source_dependency_graph::parse_manifest_document(root, "documents/invalid_kind.md")
            .unwrap_err()
            .to_string(),
        "documents/invalid_kind.md:3: invalid dependency kind: invalid"
    );

    fixture.write(
        "documents/escape.md",
        "<!--\n@dependency-start\nupstream design ../../outside.md must stay in root\n@dependency-end\n-->\n",
    );
    let error = source_dependency_graph::parse_manifest_document(root, "documents/escape.md")
        .unwrap_err()
        .to_string();
    assert!(error.starts_with("path escapes repository root: "));

    let after_header = format!(
        "{}@dependency-start\n@dependency-end\n",
        "# filler\n".repeat(80)
    );
    fixture.write("documents/after_header.md", &after_header);
    let document =
        source_dependency_graph::parse_manifest_document(root, "documents/after_header.md")
            .unwrap();
    assert!(!document.manifest_present);
    assert!(document.edges.is_empty());
}
