// @dependency-start
// contract test
// responsibility Verifies native catalog validation, lexical path policy, route records, and source-span behavior.
// upstream implementation ../src/catalog/mod.rs native catalog core under test
// @dependency-end

#[path = "../src/catalog/mod.rs"]
mod catalog;

use catalog::path_policy;
use catalog::skill_routes::{
    build_capability_index, capability_routes, derive_skill_invocation_order,
    load_skill_route_rules, load_skill_route_rules_from_root, related_skill_candidates,
};
use catalog::tool_catalog::{
    extract_public_surface, render_json, render_markdown, rust_tokens, token_sequence_matches,
    validate_catalog, yaml_id_spans,
};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use yaml_rust2::YamlLoader;

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new(name: &str) -> Self {
        let nonce = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!("agent-canon-catalog-{name}-{}-{sequence}-{nonce}", std::process::id()));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }

    fn write(&self, relative: &str, text: &str) {
        let path = self.0.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, text).unwrap();
    }

    fn path(&self) -> &Path { &self.0 }
}

impl Drop for TempRoot {
    fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); }
}

#[test]
fn retired_path_policy_keeps_legacy_lexical_rules() {
    for path in [
        "./tools/old/Legacy.py",
        r".\tools\old\legacy_runner.sh",
        "tools/../tools/legacy.py",
        "tools/legacy-adapter",
    ] {
        assert!(path_policy::is_retired_legacy_tool_path(path), "{path}");
    }
    for path in ["tools/current/run.py", "other/legacy.py", "tools/normal.py"] {
        assert!(!path_policy::is_retired_legacy_tool_path(path), "{path}");
    }

    let root = TempRoot::new("path-policy");
    root.write("tools/legacy/old.py", "legacy");
    root.write("tools/sub/old_legacy.py", "legacy");
    root.write("tools/sub/current.py", "current");
    assert_eq!(
        path_policy::iter_retired_legacy_tool_paths(root.path()),
        vec!["tools/legacy".to_owned(), "tools/sub/old_legacy.py".to_owned()]
    );
    assert_eq!(path_policy::retired_legacy_tool_detail("tools/legacy"), "legacy-directory-present");
    assert_eq!(path_policy::retired_legacy_tool_detail("tools/sub/old_legacy.py"), "legacy-tools-are-retired");
}

#[test]
fn rust_token_spans_ignore_nested_comments_and_keep_unicode_columns() {
    let source = r#"α /* outer /* nested */ end */
if args[1] == "x\"y" { /* tail */ }"#;
    let tokens = rust_tokens(source).unwrap();
    let if_token = tokens.iter().find(|token| token.value == "if").unwrap();
    assert_eq!((if_token.start_line, if_token.start_column), (2, 1));
    let string = tokens.iter().find(|token| token.value == "\"x\\\"y\"").unwrap();
    assert_eq!((string.start_line, string.start_column), (2, 15));
    assert_eq!((string.end_line, string.end_column), (2, 21));
    assert_eq!(token_sequence_matches(&tokens, &["args", "[", "1", "]"]).len(), 1);
    assert_eq!(rust_tokens("/* outer /* nested */").unwrap_err(), "unterminated block comment");
    assert_eq!(rust_tokens("let value = \"open").unwrap_err(), "unterminated string literal");
}

#[test]
fn yaml_id_spans_preserve_plain_quoted_utf8_and_duplicate_first_mark() {
    let text = "items:\n  - id: plain # comment\n  - id: \"quoted\"\n  - id: plain\n  - label: 日本\n    id: café\n";
    let spans = yaml_id_spans("tools/catalog.yaml", text).unwrap();
    let plain = spans.iter().find(|(id, _)| id == "plain").unwrap().1.clone();
    let quoted = spans.iter().find(|(id, _)| id == "quoted").unwrap().1.clone();
    let unicode = spans.iter().find(|(id, _)| id == "café").unwrap().1.clone();
    assert_eq!((plain.start_line, plain.start_column, plain.end_line, plain.end_column), (2, 9, 2, 14));
    assert_eq!((quoted.start_line, quoted.start_column, quoted.end_line, quoted.end_column), (3, 9, 3, 17));
    assert_eq!((unicode.start_line, unicode.start_column, unicode.end_line, unicode.end_column), (6, 9, 6, 13));
    assert_eq!(spans.iter().filter(|(id, _)| id == "plain").count(), 1);
}

fn valid_tool_catalog_root() -> TempRoot {
    let root = TempRoot::new("tool-catalog");
    root.write("tools/catalog.yaml", r#"version: 1
families:
  core:
    audience: operators
    placement: repository
status_values: [canonical]
role_values: [checker]
audience_values: [operators]
placement_values: [repository]
entries:
  - id: demo-tool
    path: tools/demo_tool.py
    summary: Demonstration tool.
    family: core
    role: checker
    status: canonical
    public: false
    docs: [documents/tools/demo-tool.md]
    tests: [tests/demo_tool_test.py]
    default_wiring: {ci: false, pr_check: false}
"#);
    root.write("tools/demo_tool.py", "# source\n");
    root.write("documents/tools/demo-tool.md", "# Demo\n");
    root.write("tests/demo_tool_test.py", "# test\n");
    root.write("tools/README.md", "tools/catalog.yaml tool_catalog.py\n");
    root.write("documents/tools/README.md", "tools/catalog.yaml tool_catalog.py\n");
    root.write("documents/tools/repo-local-tool-imports.md", "tools/catalog.yaml tool_catalog.py\n");
    root.write("documents/tools/tool-docs.toml", r#"# tools/catalog.yaml tool_catalog.py
catalog_kind = "agent_canon_tool_docs"
classification_values = ["public", "internal", "compat", "retired", "example"]

[[tool]]
id = "demo-tool"
tool = "tools/demo_tool.py"
doc = "documents/tools/demo-tool.md"
classification = "internal"
"#);
    root
}

#[test]
fn catalog_validation_and_report_rendering_match_native_records() {
    let root = valid_tool_catalog_root();
    let report = validate_catalog(root.path());
    assert!(report.findings.is_empty(), "{:#?}", report.findings);
    assert_eq!(report.entries.len(), 1);
    assert_eq!(report.entries[0].tool_id, "demo-tool");
    assert_eq!(report.entries[0].audience, "operators");
    assert_eq!(report.entries[0].docs, vec!["documents/tools/demo-tool.md"]);
    assert!(render_markdown(&report).contains("# AgentCanon Tool Catalog"));
    let json = render_json(&report, None);
    assert!(json.contains("agent_canon.catalog_bundle.v1"));
    assert!(json.contains("demo-tool"));
}

fn valid_skill_root() -> TempRoot {
    let root = TempRoot::new("skill-routes");
    root.write("agents/skills/catalog.yaml", r#"skill_families:
  - id: alpha
    canonical_doc: agents/skills/alpha.md
    routing:
      reason: explicit alpha
      stage_policy: deferred
      triggers: [[alpha, route]]
      capabilities:
        - id: route_test
          owner: alpha
          phase: route
          activation: explicit
          exclusive: true
  - id: beta
    canonical_doc: agents/skills/beta.md
"#);
    root.write("agents/skills/skill-dependencies.yaml", r#"skill_dependencies:
  alpha:
    responsibility_group: routing
    required_prerequisites: []
    routing_candidates: [beta]
    successors: []
    order_constraints: []
    parallel_independent: []
  beta:
    responsibility_group: routing
    required_prerequisites: [alpha]
    routing_candidates: []
    successors: []
    order_constraints: []
    parallel_independent: []
"#);
    root
}

#[test]
fn skill_routes_preserve_capabilities_dependencies_and_candidate_only_semantics() {
    let root = valid_skill_root();
    let rules = load_skill_route_rules(root.path()).unwrap();
    assert_eq!(rules.len(), 2);
    assert_eq!(rules[0].triggers, vec![vec!["alpha".to_owned(), "route".to_owned()]]);
    assert_eq!(rules[0].capabilities[0].capability_id, "route_test");
    assert_eq!(rules[0].related_skills, vec!["beta"]);
    assert_eq!(derive_skill_invocation_order(&["beta".to_owned()], &rules).unwrap(), vec!["alpha", "beta"]);

    let index = build_capability_index(&rules);
    let (by_source, candidates) = related_skill_candidates(&["alpha".to_owned()], &index.rules_by_skill, &[]);
    assert_eq!(by_source.get(&"alpha".to_owned()).unwrap(), &vec!["beta"]);
    assert_eq!(candidates, vec!["beta"]);
    let (_, no_pending) = related_skill_candidates(&["alpha".to_owned()], &index.rules_by_skill, &["beta".to_owned()]);
    assert!(no_pending.is_empty());
    assert_eq!(load_skill_route_rules_from_root(root.path()).unwrap(), rules);
}

#[test]
fn capability_catalog_errors_and_root_errors_keep_stable_codes() {
    let invalid = YamlLoader::load_from_str("- {id: bad-name, owner: alpha, phase: route, activation: explicit, exclusive: true}\n").unwrap().remove(0);
    let error = capability_routes(Some(&invalid), "routing.capabilities", "alpha").unwrap_err();
    assert_eq!(error.code, "capability-catalog-invalid:alpha:routing.capabilities[0].id");

    let absent = TempRoot::new("missing-skill-root");
    assert_eq!(load_skill_route_rules_from_root(absent.path()).unwrap_err().code, "capability-root-catalog-missing");
}

#[test]
fn public_surface_extractor_binds_dispatch_docs_and_yaml_source_marks() {
    let root = TempRoot::new("public-surface");
    root.write("tools/runtime/dispatch/agent-canon/src/main.rs", r#"mod graph;
fn main() {
    if args.len() >= 2 && args[1] == "graph" { std::process::exit(graph::run(&args[2..])); }
}
"#);
    root.write("tools/runtime/dispatch/agent-canon/src/graph.rs", r#"match operation {
    "build" => build_graph_with_failure(&parsed),
    "status" => read_graph_status(&parsed),
    "query" => query_graph(&parsed),
    "context" => context_graph(&parsed),
}
"#);
    root.write("agents/canonical/CLI_ENTRYPOINTS.md", "graph build\ngraph status\ngraph query\ngraph context\n");
    root.write("tools/catalog.yaml", "entries:\n  - id: demo-tool\n    public: true\n    command: tools/demo_tool.py\n");
    root.write("agents/skills/catalog.yaml", "skill_families:\n  - id: demo-skill\n    canonical_doc: agents/skills/demo-skill.md\n");
    let report = extract_public_surface(root.path());
    assert!(report.findings.is_empty(), "{:#?}", report.findings);
    assert_eq!(report.rows.len(), 6);
    let tool = report.rows.iter().find(|row| row.surface_id == "tool:demo-tool").unwrap();
    assert_eq!(tool.selector, "tools/demo_tool.py");
    assert_eq!((tool.source_span.start_line, tool.source_span.start_column, tool.source_span.end_column), (2, 9, 18));
    let json = render_json(&validate_catalog(root.path()), Some(&report));
    assert!(json.contains("public-surface.v1"));
}
