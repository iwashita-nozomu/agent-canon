use crate::graph_client::GraphClient;
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

fn graph_client_fixture() -> Fixture {
    let fixture = Fixture::new();
    fixture.write(
        "agents/skills/catalog.yaml",
        "skill_families:\n  - id: example\n    canonical_doc: agents/skills/example.md\n    shim: .codex/personal/skills/example/SKILL.md\n",
    );
    fixture.write("agents/skills/example.md", "Canonical skill owner.\n");
    fixture.write(
        "documents/design/parent.md",
        "<!--\n@dependency-start\ncontract design\nresponsibility Defines the parent contract.\ndownstream design feature.md specializes the parent\n@dependency-end\n-->\n# Parent\n",
    );
    fixture.write(
        "documents/design/feature.md",
        "<!--\n@dependency-start\ncontract design\nresponsibility Defines the feature contract.\nupstream design parent.md inherits the parent contract\nupstream reference ../notes/source-evidence.md records non-authoritative context\ndownstream implementation ../../tools/feature.py implements the feature\n@dependency-end\n-->\n# Feature\n",
    );
    fixture.write(
        "documents/notes/source-evidence.md",
        "# Source evidence\n\nThis note is supporting context, not a design owner.\n",
    );
    fixture.write(
        "tools/feature.py",
        "# @dependency-start\n# contract tool\n# responsibility Implements the feature contract.\n# upstream design ../documents/design/feature.md feature design\n# @dependency-end\ndef feature() -> None:\n    pass\n",
    );
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

#[test]
fn graph_client_dependency_query_and_context_use_source_without_runtime_state() {
    let fixture = graph_client_fixture();
    let missing_provider = fixture.0.join("missing-agent-canon");
    let client = GraphClient::with_executable(&fixture.0, &missing_provider).unwrap();

    let response = client.query(None, "dependency", "both", 0, true).unwrap();
    assert_eq!(response.status, "fresh");
    assert_eq!(response.payload["projection"], "tracked-source");
    let facts = response.dependency_facts().unwrap();
    assert!(facts.len() >= 4);
    assert!(!fixture.0.join(".agent-canon").exists());

    let context = client.context("documents/design/feature.md", None).unwrap();
    let identity = context.source_identity().unwrap().unwrap();
    assert_eq!(identity.source_path, "documents/design/feature.md");
    assert_eq!(identity.content_sha256.len(), 64);
    assert_eq!(
        context.payload["parent_paths"],
        json!(["documents/design/parent.md"])
    );
    assert_eq!(
        context.payload["evidence_paths"],
        json!([
            "documents/design/feature.md",
            "documents/design/parent.md",
            "documents/notes/source-evidence.md",
            "tools/feature.py"
        ])
    );
    assert!(!fixture.0.join(".agent-canon").exists());
}

#[test]
fn graph_client_persisted_operations_keep_the_explicit_executable_provider() {
    let fixture = graph_client_fixture();
    let missing_provider = fixture.0.join("missing-agent-canon");
    let client = GraphClient::with_executable(&fixture.0, &missing_provider).unwrap();

    assert!(client
        .build()
        .unwrap_err()
        .to_string()
        .contains("process launch failed"));
    assert!(client
        .status()
        .unwrap_err()
        .to_string()
        .contains("process launch failed"));
    assert!(client
        .query(None, "owner", "both", 0, true)
        .unwrap_err()
        .to_string()
        .contains("process launch failed"));
    assert!(client
        .query(
            Some("documents/design/feature.md"),
            "dependency",
            "outgoing",
            1,
            false
        )
        .unwrap_err()
        .to_string()
        .contains("process launch failed"));
    assert!(client
        .context("documents/design/feature.md", Some("claim-token"))
        .unwrap_err()
        .to_string()
        .contains("process launch failed"));
}

#[test]
fn graph_client_source_query_fails_closed_on_escape_and_relation_errors() {
    let fixture = graph_client_fixture();
    fixture.write(
        "tools/escape.py",
        "# @dependency-start\n# contract tool\n# responsibility Tests source containment.\n# upstream design ../../outside.md escapes the root\n# @dependency-end\n",
    );
    let client = GraphClient::new(&fixture.0).unwrap();
    let error = client
        .query(None, "dependency", "both", 0, true)
        .unwrap_err()
        .to_string();
    assert!(error.contains("source dependency projection failed"));
    assert!(error.contains("escapes repository root"));
    assert!(client
        .query(None, "citation", "both", 0, true)
        .unwrap_err()
        .to_string()
        .contains("unsupported graph relation: citation"));
}

#[test]
fn graph_client_generated_skill_views_resolve_to_catalog_owners() {
    let fixture = graph_client_fixture();
    fixture.write(
        "agents/skills/catalog.yaml",
        "skill_families:\n  - id: alpha\n    canonical_doc: agents/skills/alpha.md\n    shim: .codex/personal/skills/alpha/SKILL.md\n  - id: beta\n    canonical_doc: agents/skills/beta.md\n    shim: .codex/personal/skills/beta/SKILL.md\n",
    );
    fixture.write("agents/skills/alpha.md", "Canonical alpha skill.\n");
    fixture.write("agents/skills/beta.md", "Canonical beta skill.\n");
    fixture.write(
        "tools/consumer.py",
        "# @dependency-start\n# contract tool\n# responsibility References generated skill views.\n# downstream implementation ../.codex/personal/skills/alpha/SKILL.md exact owner view\n# downstream reference ../.codex/personal/skills/*/SKILL.md all catalog owner views\n# @dependency-end\n",
    );
    let client = GraphClient::new(&fixture.0).unwrap();
    let response = client.query(None, "dependency", "both", 0, true).unwrap();
    let facts = response.dependency_facts().unwrap();
    let consumer_facts: Vec<_> = facts
        .iter()
        .filter(|fact| fact.source == "tools/consumer.py")
        .collect();
    assert_eq!(consumer_facts.len(), 3);
    assert_eq!(
        consumer_facts
            .iter()
            .map(|fact| fact.target.as_str())
            .collect::<std::collections::BTreeSet<_>>(),
        std::collections::BTreeSet::from(["agents/skills/alpha.md", "agents/skills/beta.md"])
    );
    let context = client
        .context(".codex/personal/skills/alpha/SKILL.md", None)
        .unwrap();
    assert_eq!(
        context.source_identity().unwrap().unwrap().source_path,
        "agents/skills/alpha.md"
    );
    assert!(!fixture.0.join(".codex").exists());
}

#[test]
fn graph_client_rejects_unknown_and_unmatched_generated_skill_views() {
    for (target, expected) in [
        (
            "../.codex/personal/skills/removed/SKILL.md",
            "unknown generated skill view",
        ),
        (
            "../.codex/personal/skills/missing-*/SKILL.md",
            "unknown generated skill view",
        ),
    ] {
        let fixture = graph_client_fixture();
        fixture.write(
            "tools/consumer.py",
            &format!(
                "# @dependency-start\n# contract tool\n# responsibility References a generated view.\n# downstream implementation {target} stale generated view\n# @dependency-end\n"
            ),
        );
        let error = GraphClient::new(&fixture.0)
            .unwrap()
            .query(None, "dependency", "both", 0, true)
            .unwrap_err()
            .to_string();
        assert!(error.contains("source dependency projection failed"));
        assert!(error.contains(expected));
    }
}

#[test]
fn graph_client_source_query_preserves_cycle_edges_without_persisted_state() {
    let fixture = Fixture::new();
    fixture.write(
        "a.md",
        "<!--\n@dependency-start\ndownstream design b.md forms first edge\n@dependency-end\n-->\n",
    );
    fixture.write(
        "b.md",
        "<!--\n@dependency-start\ndownstream design a.md forms return edge\n@dependency-end\n-->\n",
    );
    let client = GraphClient::new(&fixture.0).unwrap();
    let response = client.query(None, "dependency", "both", 0, true).unwrap();
    let edges = response
        .dependency_facts()
        .unwrap()
        .into_iter()
        .map(|fact| (fact.source, fact.target))
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(
        edges,
        std::collections::BTreeSet::from([
            ("a.md".to_string(), "b.md".to_string()),
            ("b.md".to_string(), "a.md".to_string()),
        ])
    );
    assert!(!fixture.0.join(".agent-canon").exists());
}
