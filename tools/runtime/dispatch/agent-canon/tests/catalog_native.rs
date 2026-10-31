// @dependency-start
// contract test
// responsibility Verifies native catalog validation, lexical path policy, route records, and source-span behavior.
// upstream implementation ../src/catalog/mod.rs native catalog core under test
// @dependency-end

use agent_canon::{catalog, tool_proof_coverage};

use catalog::path_policy::{self, LEGACY_TOKEN_RE};
use catalog::skill_routes::{
    build_capability_index, capability_routes, derive_skill_invocation_order, load_skill_catalog,
    load_skill_dependency_map, load_skill_route_rules, load_skill_route_rules_from_root,
    related_skill_candidates, CAPABILITY_ID_RE, SKILL_DEPENDENCY_MAP_PATH,
};
use catalog::tool_catalog::{
    as_mapping, as_sequence, check_tool_docs_manifest, extract_public_surface,
    referenced_tool_paths_from_text, render_json, render_markdown, resolve_repo_path, rust_tokens,
    token_sequence_matches, validate_catalog, yaml_id_spans, TOOL_REFERENCE_RE,
};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use yaml_rust2::YamlLoader;

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new(name: &str) -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-catalog-{name}-{}-{sequence}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }

    fn write(&self, relative: &str, text: &str) {
        let path = self.0.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, text).unwrap();
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn run_native_cli(root: &Path, args: &[&str]) -> Output {
    let mut command_args = vec![
        "tool-catalog".to_owned(),
        "--root".to_owned(),
        root.display().to_string(),
    ];
    command_args.extend(args.iter().map(|argument| (*argument).to_owned()));
    Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(command_args)
        .output()
        .expect("native catalog CLI starts")
}

fn shared_graph_dispatch_source(status_handler: &str, duplicate_build: bool) -> String {
    let duplicate_build_arm = if duplicate_build {
        "        \"build\" => build_graph_with_failure(args),\n"
    } else {
        ""
    };
    r#"fn dispatch_command(command: &str, args: &GraphArgs) -> Result<Value, GraphError> {
    match command {
        "build" => build_graph_with_failure(args),
        "status" => __STATUS_HANDLER__,
        "query" => query_graph(args),
        "context" => context_graph(args),
__DUPLICATE_BUILD_ARM__        _ => Err(GraphError::Usage(format!("unknown graph command {command}"))),
    }
}

pub(crate) fn invoke(root: &Path, command: &str, options: &[String]) -> Result<Value, GraphError> {
    let parsed = parse_args(options)?;
    dispatch_command(command, &parsed)
}

pub(crate) fn run(args: &[String]) -> i32 {
    let parsed = parse_args(args)?;
    let result = dispatch_command(command, &parsed);
    emit(&result)
}
"#
    .replace("__STATUS_HANDLER__", status_handler)
    .replace("__DUPLICATE_BUILD_ARM__", duplicate_build_arm)
}

#[test]
fn retired_path_policy_keeps_legacy_lexical_rules() {
    assert_eq!(
        LEGACY_TOKEN_RE
            .split("legacy_runner")
            .filter(|token| !token.is_empty())
            .collect::<Vec<_>>(),
        vec!["legacy", "runner"]
    );
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
        vec![
            "tools/legacy".to_owned(),
            "tools/sub/old_legacy.py".to_owned()
        ]
    );
    assert_eq!(
        path_policy::retired_legacy_tool_detail("tools/legacy"),
        "legacy-directory-present"
    );
    assert_eq!(
        path_policy::retired_legacy_tool_detail("tools/sub/old_legacy.py"),
        "legacy-tools-are-retired"
    );
}

#[test]
fn rust_token_spans_ignore_nested_comments_and_keep_unicode_columns() {
    let source = r#"α /* outer /* nested */ end */
if args[1] == "x\"y" { /* tail */ }"#;
    let tokens = rust_tokens(source).unwrap();
    let if_token = tokens.iter().find(|token| token.value == "if").unwrap();
    assert_eq!((if_token.start_line, if_token.start_column), (2, 1));
    let string = tokens
        .iter()
        .find(|token| token.value == "\"x\\\"y\"")
        .unwrap();
    assert_eq!((string.start_line, string.start_column), (2, 15));
    assert_eq!((string.end_line, string.end_column), (2, 21));
    assert_eq!(
        token_sequence_matches(&tokens, &["args", "[", "1", "]"]).len(),
        1
    );
    assert_eq!(
        rust_tokens("/* outer /* nested */").unwrap_err(),
        "unterminated block comment"
    );
    assert_eq!(
        rust_tokens("let value = \"open").unwrap_err(),
        "unterminated string literal"
    );
}

#[test]
fn yaml_id_spans_preserve_plain_quoted_utf8_and_duplicate_first_mark() {
    let text = "items:\n  - id: plain # comment\n  - id: \"quoted\"\n  - id: plain\n  - label: 日本\n    id: café\n";
    let spans = yaml_id_spans("tools/catalog.yaml", text).unwrap();
    let plain = spans
        .iter()
        .find(|(id, _)| id == "plain")
        .unwrap()
        .1
        .clone();
    let quoted = spans
        .iter()
        .find(|(id, _)| id == "quoted")
        .unwrap()
        .1
        .clone();
    let unicode = spans.iter().find(|(id, _)| id == "café").unwrap().1.clone();
    assert_eq!(
        (
            plain.start_line,
            plain.start_column,
            plain.end_line,
            plain.end_column
        ),
        (2, 9, 2, 14)
    );
    assert_eq!(
        (
            quoted.start_line,
            quoted.start_column,
            quoted.end_line,
            quoted.end_column
        ),
        (3, 9, 3, 17)
    );
    assert_eq!(
        (
            unicode.start_line,
            unicode.start_column,
            unicode.end_line,
            unicode.end_column
        ),
        (6, 9, 6, 13)
    );
    assert_eq!(spans.iter().filter(|(id, _)| id == "plain").count(), 1);
    assert_eq!(
        yaml_id_spans("tools/catalog.yaml", "id: first\n---\nid: second\n").unwrap_err(),
        "expected a single YAML document"
    );
}

fn valid_tool_catalog_root() -> TempRoot {
    let root = TempRoot::new("tool-catalog");
    root.write(
        "tools/catalog.yaml",
        r#"version: 1
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
    path: tools/demo-tool.py
    summary: Demonstration tool.
    family: core
    role: checker
    status: canonical
    public: false
    docs: [documents/tools/demo-tool.md]
    tests: [tests/demo_tool_test.py]
    default_wiring: {ci: false, pr_check: false}
"#,
    );
    root.write("tools/demo-tool.py", "# source\n");
    root.write("documents/tools/demo-tool.md", "# Demo\n");
    root.write("tests/demo_tool_test.py", "# test\n");
    root.write("tools/README.md", "tools/catalog.yaml tool_catalog.rs\n");
    root.write(
        "documents/tools/README.md",
        "tools/catalog.yaml tool_catalog.rs\n",
    );
    root.write(
        "documents/tools/repo-local-tool-imports.md",
        "tools/catalog.yaml tool_catalog.rs\n",
    );
    root.write(
        "documents/tools/tool-docs.toml",
        r#"# tools/catalog.yaml tool_catalog.rs
catalog_kind = "agent_canon_tool_docs"
classification_values = ["public", "internal", "compat", "retired", "example"]

[[tool]]
id = "demo-tool"
    tool = "tools/demo-tool.py"
doc = "documents/tools/demo-tool.md"
classification = "internal"
"#,
    );
    root
}

fn native_cli_wiring_root(dispatch_args: &[&str], shell_source: &str) -> TempRoot {
    assert!(dispatch_args.len() >= 2);
    assert_eq!(dispatch_args[0], "tools/bin/agent-canon");
    let root = valid_tool_catalog_root();
    let native_path = "tools/runtime/dispatch/agent-canon/src/demo_tool.rs";
    let native_doc = "documents/tools/demo_tool.md";
    root.write(native_path, "// native fixture\n");
    root.write(native_doc, "# Native demo\n");

    let catalog_path = root.path().join("tools/catalog.yaml");
    let catalog = fs::read_to_string(catalog_path).unwrap();
    let command = dispatch_args[1..].join(" ");
    let dispatch_argv = dispatch_args
        .iter()
        .map(|argument| format!("\"{argument}\""))
        .collect::<Vec<_>>()
        .join(", ");
    let native_entry_route = format!(
        "    path: {native_path}\n    command: tools/bin/agent-canon {command}\n    dispatch: {{argv: [{dispatch_argv}]}}\n"
    );
    let catalog = catalog
        .replace("    path: tools/demo-tool.py\n", &native_entry_route)
        .replace(
            "    docs: [documents/tools/demo-tool.md]\n",
            &format!("    docs: [{native_doc}]\n"),
        )
        .replace(
            "    default_wiring: {ci: false, pr_check: false}",
            "    default_wiring: {ci: true, pr_check: false}",
        );
    assert!(catalog.contains(native_path));
    assert!(catalog.contains(&command));
    root.write("tools/catalog.yaml", &catalog);

    let tool_docs_path = root.path().join("documents/tools/tool-docs.toml");
    let tool_docs = fs::read_to_string(tool_docs_path).unwrap();
    let tool_docs = tool_docs
        .replace("tools/demo-tool.py", native_path)
        .replace("documents/tools/demo-tool.md", native_doc);
    root.write("documents/tools/tool-docs.toml", &tool_docs);
    root.write(
        "tools/validation/ci/runners/run_all_checks.sh",
        shell_source,
    );
    root
}

fn native_wiring_is_unreferenced(root: &TempRoot) -> bool {
    validate_catalog(root.path())
        .findings
        .iter()
        .any(|finding| {
            finding.check == "default_wiring"
                && finding.path == "tools/runtime/dispatch/agent-canon/src/demo_tool.rs"
                && finding.detail == "wired-entry-not-referenced"
        })
}

fn native_notebook_all_flag_is_unreferenced(shell_source: &str) -> bool {
    let root = native_cli_wiring_root(
        &["tools/bin/agent-canon", "notebook-quality", "--all"],
        shell_source,
    );
    native_wiring_is_unreferenced(&root)
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

#[test]
fn catalog_and_route_loaders_reject_multiple_documents_and_type_empty_input() {
    let catalog_root = valid_tool_catalog_root();
    let catalog_path = catalog_root.path().join("tools/catalog.yaml");
    let catalog_text = fs::read_to_string(&catalog_path).unwrap();
    catalog_root.write(
        "tools/catalog.yaml",
        &format!("{catalog_text}---\nversion: 1\n"),
    );
    let catalog_report = validate_catalog(catalog_root.path());
    assert!(catalog_report.findings.iter().any(|finding| {
        finding.check == "catalog"
            && finding.path == "tools/catalog.yaml"
            && finding.detail == "yaml-parse-failed"
    }));
    let (_, proof_findings) = tool_proof_coverage::load_catalog_entries(catalog_root.path());
    assert!(proof_findings.iter().any(|finding| {
        finding.check == "catalog"
            && finding.tool_id == "tools/catalog.yaml"
            && finding.detail == "yaml-parse-failed"
    }));

    catalog_root.write("tools/catalog.yaml", "");
    let empty_report = validate_catalog(catalog_root.path());
    assert!(empty_report.findings.iter().any(|finding| {
        finding.path == "tools/catalog.yaml" && finding.detail == "must-parse-as-mapping"
    }));

    let skill_root = valid_skill_root();
    let skill_catalog =
        fs::read_to_string(skill_root.path().join("agents/skills/catalog.yaml")).unwrap();
    skill_root.write(
        "agents/skills/catalog.yaml",
        &format!("{skill_catalog}---\nskill_families: []\n"),
    );
    assert!(load_skill_catalog(skill_root.path())
        .unwrap_err()
        .contains("expected a single YAML document"));
    assert_eq!(
        load_skill_route_rules_from_root(skill_root.path())
            .unwrap_err()
            .code,
        "capability-root-catalog-invalid"
    );

    let dependency_root = valid_skill_root();
    let dependencies = fs::read_to_string(
        dependency_root
            .path()
            .join("agents/skills/skill-dependencies.yaml"),
    )
    .unwrap();
    dependency_root.write(
        "agents/skills/skill-dependencies.yaml",
        &format!("{dependencies}---\nskill_dependencies: {{}}\n"),
    );
    let skill_ids = ["alpha".to_owned(), "beta".to_owned()];
    assert_eq!(
        load_skill_dependency_map(dependency_root.path(), Some(&skill_ids)).unwrap_err(),
        "skill-dependency-map-unavailable"
    );

    let empty_dependency_root = valid_skill_root();
    empty_dependency_root.write("agents/skills/skill-dependencies.yaml", "");
    assert_eq!(
        load_skill_dependency_map(empty_dependency_root.path(), Some(&skill_ids)).unwrap_err(),
        "skill-dependency-map-unavailable"
    );

    let empty_skill_root = TempRoot::new("empty-skill-catalog");
    empty_skill_root.write("agents/skills/catalog.yaml", "");
    assert!(load_skill_catalog(empty_skill_root.path())
        .unwrap_err()
        .contains("must parse as a mapping"));
}

#[test]
fn existing_invalid_utf8_wiring_and_catalog_docs_fail_validation() {
    let root = valid_tool_catalog_root();
    let wiring_path = root
        .path()
        .join("tools/validation/ci/runners/run_all_checks.sh");
    fs::create_dir_all(wiring_path.parent().unwrap()).unwrap();
    fs::write(&wiring_path, [0xff_u8]).unwrap();
    fs::write(root.path().join("tools/README.md"), [0xff_u8]).unwrap();

    let report = validate_catalog(root.path());
    assert!(report.findings.iter().any(|finding| {
        finding.check == "default_wiring"
            && finding.path == "tools/validation/ci/runners/run_all_checks.sh"
            && finding.detail == "read-failed"
    }));
    assert!(report.findings.iter().any(|finding| {
        finding.check == "catalog_docs"
            && finding.path == "tools/README.md"
            && finding.detail == "read-failed"
    }));
}

#[test]
fn mapping_sequence_and_source_root_helpers_keep_direct_caller_contracts() {
    let mapping = YamlLoader::load_from_str("name: value\n")
        .unwrap()
        .remove(0);
    assert_eq!(as_mapping(&mapping).unwrap()[0].0, "name");
    assert!(as_sequence(&mapping).is_none());
    let sequence = YamlLoader::load_from_str("- value\n").unwrap().remove(0);
    assert_eq!(as_sequence(&sequence).unwrap().len(), 1);
    let scalar = YamlLoader::load_from_str("value\n").unwrap().remove(0);
    assert!(as_sequence(&scalar).is_none());

    let root = TempRoot::new("source-root-helper");
    let source_root = root.path().join("external-source");
    fs::create_dir_all(&source_root).unwrap();
    assert_eq!(
        resolve_repo_path(root.path(), "catalog.yaml", Some(&source_root)),
        source_root.canonicalize().unwrap().join("catalog.yaml")
    );
}

#[test]
fn default_reference_pattern_excludes_test_paths_and_keeps_tool_paths() {
    let text = "python3 tests/tools/test_catalog_fixture.py\npython3 tests/tools/tools/run_symlink_lint.py\npython3 tools/runtime/manifest/uncataloged.py\n";
    let references = referenced_tool_paths_from_text(text);
    assert_eq!(
        references,
        std::collections::BTreeSet::from(["tools/runtime/manifest/uncataloged.py".to_owned()])
    );
    assert_eq!(
        TOOL_REFERENCE_RE
            .captures_iter(text)
            .filter_map(|capture| capture.get(1).map(|path| path.as_str()))
            .collect::<Vec<_>>(),
        vec!["tools/runtime/manifest/uncataloged.py"]
    );
}

#[test]
fn native_default_wiring_recognizes_catalogued_wrapper_command() {
    let root = native_cli_wiring_root(
        &["tools/bin/agent-canon", "native-check"],
        "if run_agent_canon native-check --root .; then\n  :\nfi\n",
    );
    assert!(
        !native_wiring_is_unreferenced(&root),
        "the catalogued native selector is invoked through the CI wrapper"
    );
}

#[test]
fn native_default_wiring_recognizes_direct_catalogued_cli_command() {
    let root = native_cli_wiring_root(
        &["tools/bin/agent-canon", "native-check"],
        "if tools/bin/agent-canon native-check --root .; then\n  :\nfi\n",
    );
    assert!(
        !native_wiring_is_unreferenced(&root),
        "the catalogued native selector is invoked through the CLI"
    );
}

#[test]
fn native_default_wiring_reports_missing_and_misbound_calls() {
    let dispatch = &["tools/bin/agent-canon", "native-check"];
    let missing = native_cli_wiring_root(dispatch, "echo no native check call\n");
    assert!(native_wiring_is_unreferenced(&missing));

    let misbound = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon different-check --root .; then\n  :\nfi\n",
    );
    assert!(native_wiring_is_unreferenced(&misbound));
}

#[test]
fn native_default_wiring_does_not_accept_a_comment_as_a_call() {
    let native_path = "tools/runtime/dispatch/agent-canon/src/demo_tool.rs";
    let comment = format!("# if run_agent_canon native-check --root . {native_path}\n");
    let root = native_cli_wiring_root(&["tools/bin/agent-canon", "native-check"], &comment);
    assert!(native_wiring_is_unreferenced(&root));
}

#[test]
fn native_default_wiring_requires_static_dispatch_flags_and_keeps_quotes() {
    let dispatch = &["tools/bin/agent-canon", "notebook-quality", "--all"];
    let unquoted = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon notebook-quality --all --root \"$ROOT\"; then\n  :\nfi\n",
    );
    assert!(!native_wiring_is_unreferenced(&unquoted));

    let wired = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon \"notebook-quality\" \"--all\" --root \"$ROOT\"; then\n  :\nfi\n",
    );
    assert!(!native_wiring_is_unreferenced(&wired));

    let missing_flag = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon notebook-quality --root \"$ROOT\"; then\n  :\nfi\n",
    );
    assert!(native_wiring_is_unreferenced(&missing_flag));

    let misbound_flag = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon notebook-quality --changed; then\n  :\nfi\n",
    );
    assert!(native_wiring_is_unreferenced(&misbound_flag));
}

#[test]
fn native_default_wiring_preserves_placeholder_and_static_argument_order() {
    let dispatch = &[
        "tools/bin/agent-canon",
        "native-check",
        "--root",
        "<repo-root>",
        "--format",
        "json",
    ];
    let ordered = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon native-check --root \"$ROOT\" --format json; then\n  :\nfi\n",
    );
    assert!(!native_wiring_is_unreferenced(&ordered));

    let reordered = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon native-check --format json --root \"$ROOT\"; then\n  :\nfi\n",
    );
    assert!(native_wiring_is_unreferenced(&reordered));
}

#[test]
fn native_default_wiring_does_not_find_static_args_after_command_separator() {
    let dispatch = &[
        "tools/bin/agent-canon",
        "native-check",
        "--root",
        "<repo-root>",
        "--format",
        "json",
    ];
    let root = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon native-check --root \"$ROOT\"; then\n  echo --format json\nfi\n",
    );
    assert!(native_wiring_is_unreferenced(&root));
}

#[test]
fn native_default_wiring_does_not_find_static_args_in_inline_comments() {
    let dispatch = &[
        "tools/bin/agent-canon",
        "native-check",
        "--root",
        "<repo-root>",
        "--format",
        "json",
    ];
    let root = native_cli_wiring_root(
        dispatch,
        "if run_agent_canon native-check --root \"$ROOT\" # --format json\nthen\n  :\nfi\n",
    );
    assert!(native_wiring_is_unreferenced(&root));
}

#[test]
fn native_default_wiring_rejects_equals_suffix_on_static_argument() {
    assert!(native_notebook_all_flag_is_unreferenced(
        "if run_agent_canon notebook-quality --all=false; then\n  :\nfi\n"
    ));
}

#[test]
fn native_default_wiring_rejects_hyphen_suffix_on_static_argument() {
    assert!(native_notebook_all_flag_is_unreferenced(
        "if run_agent_canon notebook-quality --all-incorrect; then\n  :\nfi\n"
    ));
}

#[test]
fn native_default_wiring_rejects_concatenated_quoted_static_argument() {
    assert!(native_notebook_all_flag_is_unreferenced(
        "if run_agent_canon notebook-quality \"--all\"suffix; then\n  :\nfi\n"
    ));
}

#[test]
fn catalog_cli_adapter_preserves_existing_output_contract() {
    let root = valid_tool_catalog_root();
    let markdown = run_native_cli(root.path(), &["--format", "markdown"]);
    assert_eq!(
        markdown.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&markdown.stderr)
    );
    assert!(String::from_utf8(markdown.stdout)
        .unwrap()
        .contains("# AgentCanon Tool Catalog"));

    let text = run_native_cli(root.path(), &[]);
    assert_eq!(text.status.code(), Some(1));
    assert!(String::from_utf8(text.stdout)
        .unwrap()
        .contains("TOOL_CATALOG_FINDINGS=4\nTOOL_CATALOG=fail"));

    let json_output = run_native_cli(root.path(), &["--format=json"]);
    assert_eq!(json_output.status.code(), Some(1));
    let json = String::from_utf8(json_output.stdout).unwrap();
    assert!(json.contains("agent_canon.catalog_bundle.v1"));
    assert!(json.contains("public-surface.v1"));

    let invalid = run_native_cli(root.path(), &["--format", "yaml"]);
    assert_eq!(invalid.status.code(), Some(2));
    assert!(String::from_utf8(invalid.stderr)
        .unwrap()
        .contains("invalid choice: 'yaml'"));
}

#[test]
fn public_tool_declarations_are_bidirectionally_complete_native() {
    let root = valid_tool_catalog_root();
    let catalog_path = root.path().join("tools/catalog.yaml");
    let catalog_text = fs::read_to_string(&catalog_path)
        .unwrap()
        .replace("    public: false\n", "    public: true\n");
    root.write("tools/catalog.yaml", &catalog_text);
    let docs_path = root.path().join("documents/tools/tool-docs.toml");
    let public_docs = fs::read_to_string(&docs_path).unwrap().replace(
        "classification = \"internal\"",
        "classification = \"public\"",
    );
    root.write("documents/tools/tool-docs.toml", &public_docs);
    let catalog = YamlLoader::load_from_str(&catalog_text).unwrap().remove(0);
    let entries = catalog["entries"].as_vec().unwrap();
    let entry_refs = entries.iter().collect::<Vec<_>>();
    assert!(check_tool_docs_manifest(root.path(), &entry_refs).is_empty());

    let catalog_without_public_mark = catalog_text.replace("    public: true\n", "");
    root.write("tools/catalog.yaml", &catalog_without_public_mark);
    let unmarked_catalog = YamlLoader::load_from_str(&catalog_without_public_mark)
        .unwrap()
        .remove(0);
    let unmarked_entries = unmarked_catalog["entries"]
        .as_vec()
        .unwrap()
        .iter()
        .collect::<Vec<_>>();
    let missing_mark = check_tool_docs_manifest(root.path(), &unmarked_entries);
    assert!(missing_mark.iter().any(|finding| {
        finding.render()
            == "TOOL_CATALOG_FINDING=public_tools:documents/tools/tool-docs.toml:missing-public-mark:demo-tool:tools/demo-tool.py"
    }));

    root.write(
        "tools/runtime/manifest/catalog_only.py",
        "# catalog-only fixture\n",
    );
    root.write("documents/tools/catalog_only.md", "# catalog-only doc\n");
    let with_catalog_only = format!(
        "{catalog_without_public_mark}  - id: catalog-only\n    path: tools/runtime/manifest/catalog_only.py\n    summary: Catalog-only fixture.\n    family: core\n    role: checker\n    status: canonical\n    public: true\n    docs: [documents/tools/catalog_only.md]\n    tests: [tests/demo_tool_test.py]\n    default_wiring: {{ci: false, pr_check: false}}\n"
    );
    let expanded = YamlLoader::load_from_str(&with_catalog_only)
        .unwrap()
        .remove(0);
    let expanded_entries = expanded["entries"]
        .as_vec()
        .unwrap()
        .iter()
        .collect::<Vec<_>>();
    let findings = check_tool_docs_manifest(root.path(), &expanded_entries);
    assert!(findings.iter().any(|finding| {
        finding.render()
            == "TOOL_CATALOG_FINDING=public_tools:tools/catalog.yaml:missing-public-documentation:catalog-only:tools/runtime/manifest/catalog_only.py"
    }));
}

#[test]
fn missing_non_default_public_catalog_entry_is_reported_native() {
    let root = valid_tool_catalog_root();
    root.write("tools/runtime/manifest/extra.py", "# extra fixture\n");
    root.write("documents/tools/extra.md", "# extra doc\n");
    let docs_path = root.path().join("documents/tools/tool-docs.toml");
    let docs = fs::read_to_string(&docs_path).unwrap()
        + "\n[[tool]]\nid = \"extra-public\"\nclassification = \"public\"\ntool = \"tools/runtime/manifest/extra.py\"\ndoc = \"documents/tools/extra.md\"\n";
    root.write("documents/tools/tool-docs.toml", &docs);
    let catalog_text = fs::read_to_string(root.path().join("tools/catalog.yaml")).unwrap();
    let catalog = YamlLoader::load_from_str(&catalog_text).unwrap().remove(0);
    let entries = catalog["entries"]
        .as_vec()
        .unwrap()
        .iter()
        .collect::<Vec<_>>();
    let findings = check_tool_docs_manifest(root.path(), &entries);
    assert!(findings.iter().any(|finding| {
        finding.render()
            == "TOOL_CATALOG_FINDING=public_tools:documents/tools/tool-docs.toml:missing-catalog-entry:extra-public:tools/runtime/manifest/extra.py"
    }));
}

#[test]
fn internal_tool_declaration_is_excluded_from_public_set_native() {
    let root = valid_tool_catalog_root();
    let catalog_path = root.path().join("tools/catalog.yaml");
    let catalog_text = fs::read_to_string(catalog_path)
        .unwrap()
        .replace("    public: false\n", "");
    let catalog = YamlLoader::load_from_str(&catalog_text).unwrap().remove(0);
    let entries = catalog["entries"]
        .as_vec()
        .unwrap()
        .iter()
        .collect::<Vec<_>>();
    let findings = check_tool_docs_manifest(root.path(), &entries);
    assert!(!findings
        .iter()
        .any(|finding| finding.check == "public_tools"));
}

#[test]
fn distinct_native_selectors_share_one_documented_implementation() {
    let root = TempRoot::new("native-shared-tool-doc");
    let tool_path = "tools/native/rule_inventory.rs";
    let python_doc = "documents/python/rule_inventory.md";
    let cpp_doc = "documents/cpp/rule_inventory.md";
    root.write(tool_path, "// shared Rust owner\n");
    root.write(python_doc, "# Python rule inventory\n");
    root.write(cpp_doc, "# C++ rule inventory\n");
    root.write(
        "documents/tools/tool-docs.toml",
        r#"catalog_kind = "agent_canon_tool_docs"
classification_values = ["public", "internal", "compat", "retired", "example"]

[[tool]]
id = "oop-python-rule-inventory"
classification = "public"
tool = "tools/native/rule_inventory.rs"
doc = "documents/python/rule_inventory.md"

[[tool]]
id = "oop-cpp-rule-inventory"
classification = "public"
tool = "tools/native/rule_inventory.rs"
doc = "documents/cpp/rule_inventory.md"
"#,
    );

    let distinct_catalog = YamlLoader::load_from_str(
        "entries:\n  - id: oop-python-rule-inventory\n    path: tools/native/rule_inventory.rs\n    public: true\n    docs: [documents/python/rule_inventory.md]\n    dispatch: {argv: [tools/bin/agent-canon, oop-python-rule-inventory]}\n  - id: oop-cpp-rule-inventory\n    path: tools/native/rule_inventory.rs\n    public: true\n    docs: [documents/cpp/rule_inventory.md]\n    dispatch: {argv: [tools/bin/agent-canon, oop-cpp-rule-inventory]}\n",
    )
    .unwrap()
    .remove(0);
    let distinct_entries = distinct_catalog["entries"]
        .as_vec()
        .unwrap()
        .iter()
        .collect::<Vec<_>>();
    assert!(check_tool_docs_manifest(root.path(), &distinct_entries).is_empty());

    let repeated_catalog = YamlLoader::load_from_str(
        "entries:\n  - id: oop-python-rule-inventory\n    path: tools/native/rule_inventory.rs\n    public: true\n    docs: [documents/python/rule_inventory.md]\n    dispatch: {argv: [tools/bin/agent-canon, oop-python-rule-inventory]}\n  - id: oop-cpp-rule-inventory\n    path: tools/native/rule_inventory.rs\n    public: true\n    docs: [documents/cpp/rule_inventory.md]\n    dispatch: {argv: [tools/bin/agent-canon, oop-python-rule-inventory]}\n",
    )
    .unwrap()
    .remove(0);
    let repeated_entries = repeated_catalog["entries"]
        .as_vec()
        .unwrap()
        .iter()
        .collect::<Vec<_>>();
    let findings = check_tool_docs_manifest(root.path(), &repeated_entries);
    assert!(findings
        .iter()
        .any(|finding| finding.check == "tool_docs" && finding.detail == "duplicate-tool"));
}

fn valid_skill_root() -> TempRoot {
    let root = TempRoot::new("skill-routes");
    root.write(
        "agents/skills/catalog.yaml",
        r#"skill_families:
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
"#,
    );
    root.write(
        "agents/skills/skill-dependencies.yaml",
        r#"skill_dependencies:
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
"#,
    );
    root
}

#[test]
fn skill_routes_preserve_capabilities_dependencies_and_candidate_only_semantics() {
    let root = valid_skill_root();
    assert!(load_skill_catalog(root.path()).unwrap().as_hash().is_some());
    assert_eq!(
        SKILL_DEPENDENCY_MAP_PATH,
        "agents/skills/skill-dependencies.yaml"
    );
    assert!(CAPABILITY_ID_RE.is_match("route_test"));
    assert!(!CAPABILITY_ID_RE.is_match("route-test"));
    let rules = load_skill_route_rules(root.path()).unwrap();
    assert_eq!(rules.len(), 2);
    assert_eq!(
        rules[0].triggers,
        vec![vec!["alpha".to_owned(), "route".to_owned()]]
    );
    assert_eq!(rules[0].capabilities[0].capability_id, "route_test");
    assert_eq!(rules[0].related_skills, vec!["beta"]);
    assert_eq!(
        derive_skill_invocation_order(&["beta".to_owned()], &rules).unwrap(),
        vec!["alpha", "beta"]
    );

    let index = build_capability_index(&rules);
    let (by_source, candidates) =
        related_skill_candidates(&["alpha".to_owned()], &index.rules_by_skill, &[]);
    assert_eq!(by_source.get(&"alpha".to_owned()).unwrap(), &vec!["beta"]);
    assert_eq!(candidates, vec!["beta"]);
    let (_, no_pending) = related_skill_candidates(
        &["alpha".to_owned()],
        &index.rules_by_skill,
        &["beta".to_owned()],
    );
    assert!(no_pending.is_empty());
    assert_eq!(
        load_skill_route_rules_from_root(root.path()).unwrap(),
        rules
    );
}

#[test]
fn capability_catalog_errors_and_root_errors_keep_stable_codes() {
    let invalid = YamlLoader::load_from_str(
        "- {id: bad-name, owner: alpha, phase: route, activation: explicit, exclusive: true}\n",
    )
    .unwrap()
    .remove(0);
    let error = capability_routes(Some(&invalid), "routing.capabilities", "alpha").unwrap_err();
    assert_eq!(
        error.code,
        "capability-catalog-invalid:alpha:routing.capabilities[0].id"
    );

    let absent = TempRoot::new("missing-skill-root");
    assert_eq!(
        load_skill_route_rules_from_root(absent.path())
            .unwrap_err()
            .code,
        "capability-root-catalog-missing"
    );
}

#[test]
fn public_surface_extractor_binds_dispatch_docs_and_yaml_source_marks() {
    let root = TempRoot::new("public-surface");
    root.write(
        "tools/runtime/dispatch/agent-canon/src/main.rs",
        r#"mod graph;
fn main() {
    if args.len() >= 2 && args[1] == "graph" { std::process::exit(graph::run(&args[2..])); }
}
"#,
    );
    root.write(
        "tools/runtime/dispatch/agent-canon/src/graph.rs",
        r#"match operation {
    "build" => build_graph_with_failure(&parsed),
    "status" => read_graph_status(&parsed),
    "query" => query_graph(&parsed),
    "context" => context_graph(&parsed),
}
"#,
    );
    root.write(
        "agents/canonical/CLI_ENTRYPOINTS.md",
        "graph build\ngraph status\ngraph query\ngraph context\n",
    );
    root.write(
        "tools/catalog.yaml",
        "entries:\n  - id: demo-tool\n    public: true\n    command: tools/demo_tool.py\n",
    );
    root.write(
        "agents/skills/catalog.yaml",
        "skill_families:\n  - id: demo-skill\n    canonical_doc: agents/skills/demo-skill.md\n",
    );
    let report = extract_public_surface(root.path());
    assert!(report.findings.is_empty(), "{:#?}", report.findings);
    assert_eq!(report.rows.len(), 6);
    let tool = report
        .rows
        .iter()
        .find(|row| row.surface_id == "tool:demo-tool")
        .unwrap();
    assert_eq!(tool.selector, "tools/demo_tool.py");
    assert_eq!(
        (
            tool.source_span.start_line,
            tool.source_span.start_column,
            tool.source_span.end_column
        ),
        (2, 9, 18)
    );
    let json = render_json(&validate_catalog(root.path()), Some(&report));
    assert!(json.contains("public-surface.v1"));

    root.write(
        "tools/catalog.yaml",
        "entries:\n  - id: demo-tool\n    public: true\n---\nentries: []\n",
    );
    let multi_document = extract_public_surface(root.path());
    assert!(multi_document.findings.iter().any(|finding| {
        finding.path == "tools/catalog.yaml" && finding.detail.starts_with("yaml-parse-failed:")
    }));
}

#[test]
fn public_surface_extractor_binds_shared_graph_dispatch_and_rejects_bad_arms() {
    let root = TempRoot::new("public-surface-shared-dispatch");
    root.write(
        "tools/runtime/dispatch/agent-canon/src/main.rs",
        r#"mod graph;
fn main() {
    if args.len() >= 2 && args[1] == "graph" { std::process::exit(graph::run(&args[2..])); }
}
"#,
    );
    root.write(
        "tools/runtime/dispatch/agent-canon/src/graph.rs",
        &shared_graph_dispatch_source("read_graph_status(args)", false),
    );
    root.write(
        "agents/canonical/CLI_ENTRYPOINTS.md",
        "graph build\ngraph status\ngraph query\ngraph context\n",
    );
    root.write(
        "tools/catalog.yaml",
        "entries:\n  - id: demo-tool\n    public: true\n    command: tools/demo_tool.py\n",
    );
    root.write(
        "agents/skills/catalog.yaml",
        "skill_families:\n  - id: demo-skill\n    canonical_doc: agents/skills/demo-skill.md\n",
    );

    let report = extract_public_surface(root.path());
    assert!(report.findings.is_empty(), "{:#?}", report.findings);
    assert_eq!(report.rows.len(), 6);
    for (operation, source_line) in [("build", 3), ("status", 4), ("query", 5), ("context", 6)] {
        let row = report
            .rows
            .iter()
            .find(|row| row.surface_id == format!("cli:graph {operation}"))
            .expect("shared graph operation is reported");
        assert_eq!(
            row.source_span.path,
            "tools/runtime/dispatch/agent-canon/src/graph.rs"
        );
        assert_eq!(row.source_span.start_line, source_line);
        assert!(row.source_span.start_column > 0);
        assert_eq!(
            row.secondary_spans
                .iter()
                .filter(|span| span.path == row.source_span.path)
                .count(),
            2,
            "both CLI and in-process calls bind graph {operation}"
        );
        assert!(row
            .secondary_spans
            .iter()
            .any(|span| span.path == "tools/runtime/dispatch/agent-canon/src/main.rs"));
        assert!(row
            .secondary_spans
            .iter()
            .any(|span| span.path == "agents/canonical/CLI_ENTRYPOINTS.md"));
    }

    root.write(
        "tools/runtime/dispatch/agent-canon/src/graph.rs",
        &shared_graph_dispatch_source("read_graph_status(args)", true),
    );
    let duplicate = extract_public_surface(root.path());
    assert!(duplicate.findings.iter().any(|finding| {
        finding.path == "tools/runtime/dispatch/agent-canon/src/graph.rs"
            && finding.detail == "rust_dispatch_ambiguous:build"
    }));

    root.write(
        "tools/runtime/dispatch/agent-canon/src/graph.rs",
        &shared_graph_dispatch_source("build_graph_with_failure(args)", false),
    );
    let misbound = extract_public_surface(root.path());
    assert!(misbound.findings.iter().any(|finding| {
        finding.path == "tools/runtime/dispatch/agent-canon/src/graph.rs"
            && finding.detail == "rust_dispatch_invalid:status"
    }));
}
