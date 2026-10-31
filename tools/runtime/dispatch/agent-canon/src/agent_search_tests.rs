// @dependency-start
// contract test
// responsibility Tests source context, LSP failures, provider composition, and Unicode case-folding.
// upstream implementation agent_search.rs routes provider requests
// upstream implementation lib.rs exposes shared user-home path expansion
// upstream implementation graph_client.rs owns source-derived dependency context
// upstream implementation ../lsp_code_analysis.rs owns bounded LSP analysis
// upstream implementation semantic_index/mod.rs owns semantic retrieval
// @dependency-end

use crate::agent_search::{
    build_request_with_environment, expand_user_path_with, run_search_with_lsp_overrides,
    selected_providers, CliArgs, HomeLookupRequest, PathExpansionError, SearchInputError,
    SearchPathEnvironment, SearchPathPlatform, SearchRequest,
};
use crate::python_text::python_strip;
use agent_canon::lsp_code_analysis::{LanguageId, LspServerSpec};
use serde_json::json;
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs;
use std::io::Cursor;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "agent-canon-search-native-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir_all(&root).expect("create search fixture root");
        let root = fs::canonicalize(root).expect("resolve search fixture root");
        Self(root)
    }

    fn write(&self, relative: impl AsRef<Path>, contents: impl AsRef<[u8]>) -> PathBuf {
        let path = self.0.join(relative);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("create fixture parent");
        }
        fs::write(&path, contents).expect("write fixture input");
        path
    }

    fn track_all(&self) {
        for args in [
            vec![
                "-C",
                self.0.to_str().expect("fixture path is UTF-8"),
                "init",
                "-q",
            ],
            vec![
                "-C",
                self.0.to_str().expect("fixture path is UTF-8"),
                "add",
                "--",
                ".",
            ],
        ] {
            let output = Command::new("git")
                .args(args)
                .output()
                .expect("Git fixture setup must run");
            assert!(output.status.success(), "Git fixture setup must succeed");
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn request(root: &Path, query: &str, provider: &str) -> SearchRequest {
    SearchRequest {
        root: root.to_path_buf(),
        query: query.to_string(),
        providers: vec![provider.to_string()],
        surfaces: Vec::new(),
        excludes: Vec::new(),
        query_file: None,
        query_stdin: false,
        regex: false,
        word_regexp: false,
        case_sensitive: false,
        top: 12,
    }
}

fn cli_args(root: &Path, options: &[&str]) -> CliArgs {
    let mut args = vec!["--root".to_string(), root.to_string_lossy().into_owned()];
    args.extend(options.iter().map(|value| value.to_string()));
    CliArgs::parse(&args).expect("search fixture arguments parse")
}

#[test]
fn query_file_uses_injected_current_home_and_keeps_raw_query_text() {
    let fixture = Fixture::new();
    let home = fixture.0.join("home/current");
    let query_path = fixture.write(
        "home/current/patterns.txt",
        "\u{001f} alpha|beta \u{001f}\n",
    );
    let environment = SearchPathEnvironment {
        home: Some(home.into_os_string()),
        ..SearchPathEnvironment::default()
    };
    let args = cli_args(
        Path::new("~literal-search-root"),
        &["--query-file", "~/patterns.txt", "--providers", "text"],
    );
    let mut stdin = Cursor::new(Vec::<u8>::new());
    let report = build_request_with_environment(
        args,
        &environment,
        SearchPathPlatform::Posix,
        |_| panic!("present HOME must take precedence over account lookup"),
        &mut stdin,
    )
    .unwrap();

    assert_eq!(report.query, "\u{001f} alpha|beta \u{001f}\n");
    assert_eq!(
        report.query_file,
        Some(crate::semantic_responsibility::resolve_non_strict(&query_path).unwrap())
    );
    assert_eq!(
        report.root,
        crate::semantic_responsibility::resolve_non_strict(Path::new("~literal-search-root"))
            .unwrap()
    );
}

#[test]
fn posix_home_lookup_uses_injected_current_and_named_accounts() {
    let fixture = Fixture::new();
    let current_home = fixture.0.join("homes/current");
    let named_home = fixture.0.join("homes/alice");
    let current_query = fixture.write("homes/current/current.txt", "current query\n");
    let named_query = fixture.write("homes/alice/named.txt", " named query \n");
    let environment = SearchPathEnvironment::default();

    let current_args = cli_args(
        &fixture.0,
        &["--query-file", "~/current.txt", "--providers", "text"],
    );
    let mut current_stdin = Cursor::new(Vec::<u8>::new());
    let mut current_requests = Vec::new();
    let current_request = build_request_with_environment(
        current_args,
        &environment,
        SearchPathPlatform::Posix,
        |request| {
            current_requests.push(request.clone());
            match request {
                HomeLookupRequest::CurrentUser => Ok(Some(current_home.clone())),
                HomeLookupRequest::NamedUser(_) => panic!("current-user lookup was requested"),
            }
        },
        &mut current_stdin,
    )
    .unwrap();
    assert_eq!(current_request.query, "current query\n");
    assert_eq!(
        current_request.query_file,
        Some(crate::semantic_responsibility::resolve_non_strict(&current_query).unwrap())
    );
    assert_eq!(current_requests, vec![HomeLookupRequest::CurrentUser]);

    let named_args = cli_args(
        &fixture.0,
        &["--query-file", "~alice/named.txt", "--providers", "text"],
    );
    let environment_with_other_home = SearchPathEnvironment {
        home: Some(fixture.0.join("homes/ignored").into_os_string()),
        ..SearchPathEnvironment::default()
    };
    let mut named_stdin = Cursor::new(Vec::<u8>::new());
    let mut named_requests = Vec::new();
    let named_request = build_request_with_environment(
        named_args,
        &environment_with_other_home,
        SearchPathPlatform::Posix,
        |request| {
            named_requests.push(request.clone());
            match request {
                HomeLookupRequest::NamedUser(username) if username == "alice" => {
                    Ok(Some(named_home.clone()))
                }
                _ => panic!("named-user lookup must request alice"),
            }
        },
        &mut named_stdin,
    )
    .unwrap();
    assert_eq!(named_request.query, " named query \n");
    assert_eq!(
        named_request.query_file,
        Some(crate::semantic_responsibility::resolve_non_strict(&named_query).unwrap())
    );
    assert_eq!(
        named_requests,
        vec![HomeLookupRequest::NamedUser("alice".to_string())]
    );
}

#[test]
fn posix_empty_home_expands_to_root_without_account_lookup() {
    let environment = SearchPathEnvironment {
        home: Some(OsString::new()),
        ..SearchPathEnvironment::default()
    };
    for (query_path, expected) in [("~", "/"), ("~/query.txt", "/query.txt")] {
        let expanded = expand_user_path_with(
            Path::new(query_path),
            SearchPathPlatform::Posix,
            &environment,
            |_| panic!("present empty HOME must take precedence over account lookup"),
        )
        .unwrap();
        assert_eq!(expanded, PathBuf::from(expected), "input: {query_path}");
    }
}

#[test]
fn unresolved_home_keeps_the_runtime_error_category_and_exit_code() {
    let fixture = Fixture::new();
    let args = cli_args(
        &fixture.0,
        &[
            "--query-file",
            "~agentcanon_no_such_user_7f2a/query.txt",
            "--providers",
            "text",
        ],
    );
    let mut stdin = Cursor::new(Vec::<u8>::new());
    let error = build_request_with_environment(
        args,
        &SearchPathEnvironment::default(),
        SearchPathPlatform::Posix,
        |_| Ok(None),
        &mut stdin,
    )
    .unwrap_err();

    assert_eq!(error, SearchInputError::UnresolvedHome);
    assert_eq!(error.message(), "Could not determine home directory.");
    assert_eq!(error.exit_code(), 1);
}

#[test]
fn windows_home_expansion_matches_profile_fallback_and_sibling_rules() {
    let profile = SearchPathEnvironment {
        home: Some(OsString::from(r"D:\Home\ignored")),
        user_profile: Some(OsString::from(r"C:\Users\alice")),
        home_drive: Some(OsString::from("D:")),
        home_path: Some(OsString::from(r"\Profiles\ignored")),
        user_name: Some(OsString::from("alice")),
    };
    assert_eq!(
        expand_user_path_with(
            Path::new(r"~\queries\patterns.txt"),
            SearchPathPlatform::Windows,
            &profile,
            |_| { panic!("Windows home expansion uses the profile environment") }
        )
        .unwrap(),
        PathBuf::from(r"C:\Users\alice\queries\patterns.txt")
    );
    assert_eq!(
        expand_user_path_with(
            Path::new("~bob/queries/patterns.txt"),
            SearchPathPlatform::Windows,
            &profile,
            |_| panic!("Windows named-user expansion uses the profile heuristic"),
        )
        .unwrap(),
        PathBuf::from(r"C:\Users\bob\queries\patterns.txt")
    );

    let fallback = SearchPathEnvironment {
        home_drive: Some(OsString::from("C:")),
        home_path: Some(OsString::from(r"\Users\alice")),
        user_name: Some(OsString::from("alice")),
        ..SearchPathEnvironment::default()
    };
    assert_eq!(
        expand_user_path_with(
            Path::new("~/patterns.txt"),
            SearchPathPlatform::Windows,
            &fallback,
            |_| panic!("Windows environment fallback does not query an account database"),
        )
        .unwrap(),
        PathBuf::from(r"C:\Users\alice\patterns.txt")
    );

    let missing_drive = SearchPathEnvironment {
        home_path: Some(OsString::from(r"\Users\alice")),
        user_name: Some(OsString::from("alice")),
        ..SearchPathEnvironment::default()
    };
    assert_eq!(
        expand_user_path_with(
            Path::new("~/patterns.txt"),
            SearchPathPlatform::Windows,
            &missing_drive,
            |_| panic!("HOMEDRIVE is optional when HOMEPATH is present"),
        )
        .unwrap(),
        PathBuf::from(r"\Users\alice\patterns.txt")
    );

    let mismatch = SearchPathEnvironment {
        user_profile: Some(OsString::from(r"C:\Profiles\service")),
        user_name: Some(OsString::from("alice")),
        ..SearchPathEnvironment::default()
    };
    assert_eq!(
        expand_user_path_with(
            Path::new("~bob/patterns.txt"),
            SearchPathPlatform::Windows,
            &mismatch,
            |_| panic!("Windows named-user expansion uses the profile heuristic"),
        )
        .unwrap_err(),
        PathExpansionError::UnresolvedHome
    );

    let empty_profile = SearchPathEnvironment {
        user_profile: Some(OsString::new()),
        home_drive: Some(OsString::from("C:")),
        home_path: Some(OsString::from(r"\Users\alice")),
        ..SearchPathEnvironment::default()
    };
    assert_eq!(
        expand_user_path_with(
            Path::new("~"),
            SearchPathPlatform::Windows,
            &empty_profile,
            |_| { panic!("present USERPROFILE takes precedence even when empty") }
        )
        .unwrap(),
        PathBuf::new()
    );

    assert_eq!(
        expand_user_path_with(
            Path::new("~"),
            SearchPathPlatform::Windows,
            &SearchPathEnvironment::default(),
            |_| panic!("missing USERPROFILE and HOMEPATH do not query a user database"),
        )
        .unwrap_err(),
        PathExpansionError::UnresolvedHome
    );
}

#[test]
fn search_uses_python_whitespace_without_stripping_nonblank_queries() {
    assert!(python_strip("\u{001f}\u{001f}").is_empty());
    assert_eq!(
        selected_providers("\u{001f}text\u{001f}").unwrap(),
        vec!["text".to_string()]
    );

    let fixture = Fixture::new();
    let raw_query = " \u{001f}alpha\u{001f} ";
    let args = cli_args(&fixture.0, &["--query", raw_query, "--providers", "text"]);
    let mut stdin = Cursor::new(Vec::<u8>::new());
    let request = build_request_with_environment(
        args,
        &SearchPathEnvironment::default(),
        SearchPathPlatform::Posix,
        |_| panic!("inline query does not request home lookup"),
        &mut stdin,
    )
    .unwrap();
    assert_eq!(request.query, raw_query);

    let control_query = "\u{001f}";
    let args = cli_args(
        &fixture.0,
        &["--query", control_query, "--providers", "text"],
    );
    let mut stdin = Cursor::new(Vec::<u8>::new());
    let error = build_request_with_environment(
        args,
        &SearchPathEnvironment::default(),
        SearchPathPlatform::Posix,
        |_| panic!("blank query fails before provider dispatch"),
        &mut stdin,
    )
    .unwrap_err();
    assert_eq!(error.message(), "query-or-purpose-required");
    assert_eq!(error.exit_code(), 2);
}

fn python_executable() -> PathBuf {
    let output = Command::new("python3")
        .args(["-c", "import sys; print(sys.executable)"])
        .output()
        .expect("native search LSP fixture requires the test runtime Python");
    assert!(output.status.success(), "python3 reports its executable");
    let executable = String::from_utf8(output.stdout).expect("Python path is UTF-8");
    let executable = PathBuf::from(executable.trim());
    assert!(executable.is_absolute(), "Python path is absolute");
    executable
}

fn fake_lsp(directory: &Fixture, symbols: &[&str], missing_symbols: bool) -> LspServerSpec {
    let script = r#"
import json
import sys

symbols = json.loads(__SYMBOLS__)
missing_symbols = __MISSING_SYMBOLS__

def read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\n", b"\r\n"):
            break
        key, value = line.decode().split(":", 1)
        headers[key.lower().strip()] = value.strip()
    length = int(headers["content-length"])
    return json.loads(sys.stdin.buffer.read(length).decode())

def send(value):
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
    sys.stdout.buffer.flush()

def respond(message, result):
    send({"jsonrpc": "2.0", "id": message["id"], "result": result})

def symbol(name):
    location = {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}
    return {"name": name, "kind": 12, "range": location, "selectionRange": location}

while True:
    message = read_message()
    if message is None:
        break
    method = message.get("method")
    if method == "initialize":
        capabilities = {} if missing_symbols else {"documentSymbolProvider": True}
        respond(message, {"serverInfo": {"name": "search-fixture", "version": "1"}, "capabilities": capabilities})
    elif method == "textDocument/documentSymbol":
        respond(message, [symbol(name) for name in symbols])
    elif method == "shutdown":
        respond(message, None)
    elif method == "exit":
        break
"#;
    let serialized_symbols = serde_json::to_string(symbols).expect("fixture symbols serialize");
    let python_symbols_string =
        serde_json::to_string(&serialized_symbols).expect("fixture JSON string serializes");
    let script = script
        .replace("__SYMBOLS__", &python_symbols_string)
        .replace(
            "__MISSING_SYMBOLS__",
            if missing_symbols { "True" } else { "False" },
        );
    let script_path = directory.write("fake_lsp.py", script.as_bytes());
    let command = vec![
        python_executable().to_string_lossy().into_owned(),
        "-u".to_string(),
        script_path.to_string_lossy().into_owned(),
    ];
    LspServerSpec::caller_override(LanguageId::Python, command)
        .expect("fake LSP command is an absolute caller override")
}

fn code_search(root: &Path, query: &str, spec: LspServerSpec) -> crate::agent_search::SearchReport {
    let mut overrides = BTreeMap::new();
    overrides.insert(LanguageId::Python, spec);
    run_search_with_lsp_overrides(&request(root, query, "code-deps"), &overrides)
}

#[test]
fn source_dependency_provider_uses_graph_client_without_runtime_state() {
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
        "# Source evidence\n\nSupporting context.\n",
    );
    fixture.write(
        "tools/feature.py",
        "# @dependency-start\n# contract tool\n# responsibility Implements the feature contract.\n# upstream design ../documents/design/feature.md feature design\n# @dependency-end\ndef feature():\n    pass\n",
    );
    fixture.track_all();

    let mut request = request(&fixture.0, "documents/design/feature.md", "header-deps");
    request.query = "documents/design/feature.md".to_string();
    let report = run_search_with_lsp_overrides(&request, &BTreeMap::new());

    assert_eq!(report.status, "pass");
    assert_eq!(report.providers, vec!["header-deps".to_string()]);
    assert_eq!(report.results.len(), 1);
    assert_eq!(
        report.results[0].result[0]["resolved_path"],
        "documents/design/feature.md"
    );
    assert_eq!(
        report.results[0].result[0]["parent_paths"],
        json!(["documents/design/parent.md"])
    );
    assert!(!fixture.0.join(".agent-canon").exists());
}

#[test]
fn code_dependency_filter_uses_full_unicode_casefold() {
    let fixture = Fixture::new();
    fixture.write("src/module.py", "# LSP fixture source\n");
    let spec = fake_lsp(&fixture, &["Straße", "ΟΣ", "İstanbul", "unrelated"], false);

    for (query, expected) in [
        ("strasse", "Straße"),
        ("οσ", "ΟΣ"),
        ("i\u{307}stanbul", "İstanbul"),
    ] {
        let report = code_search(&fixture.0, query, spec.clone());
        assert_eq!(report.status, "pass", "query: {query}");
        assert_eq!(report.providers, vec!["code-deps".to_string()]);
        let symbols = report.results[0].result["symbols"]
            .as_array()
            .expect("LSP symbol list remains in its owner field");
        assert!(
            symbols.iter().any(|symbol| symbol["name"] == expected),
            "query {query:?} retains {expected:?}"
        );
        assert_eq!(
            symbols.len(),
            1,
            "query {query:?} filters unrelated symbols"
        );
    }
}

#[test]
fn code_dependency_lsp_failure_is_not_replaced_by_text_search() {
    let fixture = Fixture::new();
    fixture.write("src/module.py", "target()\n");
    let spec = fake_lsp(&fixture, &[], true);
    let report = code_search(&fixture.0, "target", spec);

    assert_eq!(report.status, "fail");
    assert_eq!(report.providers, vec!["code-deps".to_string()]);
    assert_eq!(report.results.len(), 1);
    assert_eq!(report.results[0].status, "fail");
    assert_eq!(report.results[0].result["status"], "failed");
    assert_eq!(
        report.results[0].result["error"]["code"],
        "capability-unavailable"
    );
}
