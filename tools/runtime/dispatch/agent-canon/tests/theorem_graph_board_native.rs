// @dependency-start
// contract test
// responsibility Preserves theorem-board route, status, reachability, rendering, limits, and CLI exit contracts.
// upstream implementation ../src/theorem_graph_board.rs builds and renders native theorem boards
// @dependency-end

use agent_canon::theorem_graph_board::{board, render_markdown, BoardSummary, RouteSummary};
use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TemporaryDirectory(PathBuf);

impl TemporaryDirectory {
    fn new() -> Self {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock is before Unix epoch")
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "agent-canon-theorem-board-{}-{timestamp}-{}",
            std::process::id(),
            TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).expect("create theorem-board test directory");
        Self(path)
    }

    fn path(&self) -> &std::path::Path {
        &self.0
    }
}

impl Drop for TemporaryDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn route<'a>(summary: &'a BoardSummary, name: &str) -> &'a RouteSummary {
    summary
        .routes
        .iter()
        .find(|row| row.route == name)
        .unwrap_or_else(|| panic!("missing route {name}"))
}

fn route_contract_fixture() -> Value {
    json!({
        "graph_id": "board-fixture",
        "root": "r",
        "nodes": [
            {"id": "unknown", "kind": "mystery", "status": "pending"},
            {"id": "projection-only", "kind": "lemma", "status": "open", "theorem": "projection"},
            {"id": "extractor", "kind": "lemma", "status": "frontier", "theorem": "generated_source"},
            {"id": "diagnostic-only", "kind": "lemma", "status": "open", "theorem": "algorithm"},
            {"id": "other-open", "kind": "condition", "status": "next_witness"},
            {"id": "backend", "kind": "lemma", "status": "open", "theorem": "backend fp32"},
            {"id": "r", "kind": "lemma", "status": "verified", "theorem": "direct_stop_bridge"},
            {"id": "rejected-edge-only", "kind": "lemma", "status": "open", "theorem": "reverse"}
        ],
        "edges": [
            {"source": "r", "target": "backend", "kind": "uses"},
            {"source": "r", "target": "extractor", "kind": "uses"},
            {"source": "r", "target": "unknown", "kind": "uses"},
            {"source": "r", "target": "other-open", "kind": "uses"},
            {"source": "r", "target": "missing-target", "kind": "uses"},
            {"source": "r", "target": "diagnostic-only", "kind": "diagnostic_dependency"},
            {"source": "r", "target": "projection-only", "kind": "uses", "status": "projection_only"},
            {"source": "r", "target": "rejected-edge-only", "kind": "uses", "status": "rejected"},
            {"source": null, "target": "backend", "kind": "uses"},
            {"source": "r", "target": null, "kind": "uses"}
        ]
    })
}

#[test]
fn route_board_preserves_active_reachability_classification_and_order() {
    let summary = board(&route_contract_fixture()).unwrap();

    assert_eq!(summary.graph_id, json!("board-fixture"));
    assert_eq!(summary.root, "r");
    assert_eq!(summary.reachable_nodes, 6);
    assert_eq!(
        summary
            .routes
            .iter()
            .map(|row| row.route.as_str())
            .collect::<Vec<_>>(),
        vec!["backend", "implementation_extractor", "other", "sufficient"]
    );
    assert_eq!(summary.open_route_count, 3);
    assert_eq!(summary.unknown_route_count, 0);

    let backend = route(&summary, "backend");
    assert_eq!((backend.total, backend.open, backend.unknown), (1, 1, 0));
    assert_eq!(backend.verdict, "actionable_open");
    assert_eq!(backend.open_nodes, vec!["backend".to_owned()]);
    let other = route(&summary, "other");
    assert_eq!((other.total, other.open, other.unknown), (2, 1, 1));
    assert_eq!(other.verdict, "actionable_open");
    assert_eq!(other.open_nodes, vec!["other-open".to_owned()]);
    assert_eq!(other.unknown_nodes, vec!["unknown".to_owned()]);
    assert_eq!(
        other.examples,
        vec!["other-open".to_owned(), "unknown".to_owned()]
    );
    let sufficient = route(&summary, "sufficient");
    assert_eq!((sufficient.total, sufficient.terminal), (1, 1));
    assert_eq!(sufficient.verdict, "closed");
}

#[test]
fn route_ties_choose_the_lexicographically_later_label() {
    let graph = json!({
        "root": "tie",
        "nodes": [{"id": "tie", "kind": "mystery", "status": "pending", "theorem": "sufficient backend"}],
        "edges": []
    });

    let summary = board(&graph).unwrap();

    assert_eq!(summary.routes.len(), 1);
    assert_eq!(summary.routes[0].route, "sufficient");
    assert_eq!(summary.routes[0].verdict, "needs_classification");
    assert_eq!(summary.unknown_route_count, 1);
}

#[test]
fn missing_root_falls_back_to_all_nodes() {
    let graph = json!({
        "root": "absent",
        "nodes": [
            {"id": "z", "kind": "lemma", "status": "open", "theorem": "reverse"},
            {"id": "u", "kind": "lemma", "status": "unverified", "theorem": "algorithm"},
            {"id": "a", "kind": "formal_library", "status": ""}
        ],
        "edges": []
    });

    let summary = board(&graph).unwrap();

    assert_eq!(summary.reachable_nodes, 3);
    assert_eq!(summary.open_route_count, 1);
    assert_eq!(route(&summary, "reverse").open_nodes, vec!["z".to_owned()]);
    let unverified = route(&summary, "algorithm_change");
    assert_eq!(
        (unverified.terminal, unverified.open, unverified.unknown),
        (1, 0, 0)
    );
    assert_eq!(unverified.verdict, "closed");
    assert_eq!(route(&summary, "other").terminal, 1);
}

#[test]
fn node_displays_use_sorted_ids_and_existing_limits() {
    let nodes = (0..26)
        .map(|index| json!({"id": format!("n{index:02}"), "kind": "lemma", "status": "open", "theorem": "backend"}))
        .collect::<Vec<_>>();
    let edges = (0..25)
        .map(|index| {
            json!({
                "source": format!("n{index:02}"),
                "target": format!("n{:02}", index + 1),
                "kind": "uses"
            })
        })
        .collect::<Vec<_>>();
    let graph = json!({"root": "n00", "nodes": nodes, "edges": edges});

    let summary = board(&graph).unwrap();
    let backend = route(&summary, "backend");

    assert_eq!(summary.reachable_nodes, 26);
    assert_eq!(backend.total, 26);
    assert_eq!(backend.open, 26);
    assert_eq!(backend.open_nodes.len(), 20);
    assert_eq!(backend.open_nodes.first().map(String::as_str), Some("n00"));
    assert_eq!(backend.open_nodes.last().map(String::as_str), Some("n19"));
    assert_eq!(
        backend.examples,
        vec![
            "n00".to_owned(),
            "n01".to_owned(),
            "n02".to_owned(),
            "n03".to_owned(),
            "n04".to_owned()
        ]
    );
}

#[test]
fn markdown_layout_and_generated_owner_header_remain_stable() {
    let graph = json!({
        "graph_id": "demo",
        "root": "r",
        "nodes": [{"id": "r", "kind": "lemma", "status": "verified"}],
        "edges": []
    });
    let summary = board(&graph).unwrap();

    assert_eq!(
        render_markdown(&summary),
        concat!(
            "<!--\n",
            "@dependency-start\n",
            "responsibility Records theorem-graph route-board summary for a configured proof graph.\n",
            "upstream implementation theorem_graph_board.rs generates this report from a theorem graph JSON.\n",
            "downstream proof goal-level checkers consume route open and unknown counts.\n",
            "@dependency-end\n",
            "-->\n\n",
            "# Theorem Graph Board\n\n",
            "- graph_id: `demo`\n",
            "- root: `r`\n",
            "- reachable_nodes: `1`\n",
            "- open_route_count: `0`\n",
            "- unknown_route_count: `0`\n\n",
            "| Route | Verdict | Total | Terminal | Open | Unknown | Open Nodes | Unknown Nodes |\n",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |\n",
            "| other | `closed` | 1 | 1 | 0 | 0 | None | None |\n"
        )
    );
}

#[test]
fn native_cli_writes_json_before_fail_on_open_status() {
    let temporary = TemporaryDirectory::new();
    let graph_path = temporary.path().join("graph.json");
    let output_path = temporary.path().join("board.json");
    fs::write(
        &graph_path,
        serde_json::to_vec(&json!({
            "graph_id": "cli",
            "root": "r",
            "nodes": [{"id": "r", "kind": "lemma", "status": "open", "theorem": "backend"}],
            "edges": []
        }))
        .unwrap(),
    )
    .unwrap();

    let result = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "theorem-graph-board",
            "--graph",
            graph_path.to_str().unwrap(),
            "--out",
            output_path.to_str().unwrap(),
            "--format",
            "json",
            "--fail-on-open",
        ])
        .output()
        .unwrap();

    assert_eq!(result.status.code(), Some(1));
    assert!(result.stdout.is_empty());
    let output: Value = serde_json::from_slice(&fs::read(output_path).unwrap()).unwrap();
    assert_eq!(output["graph_id"], "cli");
    assert_eq!(output["reachable_nodes"], 1);
    assert_eq!(output["open_route_count"], 1);
    assert_eq!(output["routes"][0]["route"], "backend");
    assert_eq!(output["routes"][0]["open_nodes"], json!(["r"]));
}

#[test]
fn native_cli_defaults_to_markdown_stdout() {
    let temporary = TemporaryDirectory::new();
    let graph_path = temporary.path().join("graph.json");
    fs::write(
        &graph_path,
        br#"{"root":"r","nodes":[{"id":"r","kind":"lemma","status":"verified"}],"edges":[]}"#,
    )
    .unwrap();

    let result = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "theorem-graph-board",
            "--graph",
            graph_path.to_str().unwrap(),
        ])
        .output()
        .unwrap();

    assert_eq!(result.status.code(), Some(0));
    assert!(result.stderr.is_empty());
    assert!(String::from_utf8(result.stdout)
        .unwrap()
        .starts_with("<!--\n@dependency-start\n"));
}

#[test]
fn native_cli_fail_on_unknown_returns_the_rendered_json() {
    let temporary = TemporaryDirectory::new();
    let graph_path = temporary.path().join("graph.json");
    fs::write(
        &graph_path,
        br#"{"root":"r","nodes":[{"id":"r","kind":"mystery","status":"pending"}],"edges":[]}"#,
    )
    .unwrap();

    let result = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "theorem-graph-board",
            "--graph",
            graph_path.to_str().unwrap(),
            "--format",
            "json",
            "--fail-on-unknown",
        ])
        .output()
        .unwrap();

    assert_eq!(result.status.code(), Some(1));
    assert!(result.stderr.is_empty());
    let output: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(output["unknown_route_count"], 1);
    assert_eq!(output["routes"][0]["verdict"], "needs_classification");
}
