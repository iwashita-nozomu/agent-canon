// @dependency-start
// contract test
// responsibility Tests source context, LSP failures, provider composition, and Unicode case-folding.
// upstream implementation agent_search.rs routes provider requests
// upstream implementation graph_client.rs owns source-derived dependency context
// upstream implementation ../lsp_code_analysis.rs owns bounded LSP analysis
// upstream implementation semantic_index/mod.rs owns semantic retrieval
// @dependency-end

use crate::agent_search::{run_search_with_lsp_overrides, SearchRequest};
use agent_canon::lsp_code_analysis::{LanguageId, LspServerSpec};
use serde_json::json;
use std::collections::BTreeMap;
use std::fs;
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
