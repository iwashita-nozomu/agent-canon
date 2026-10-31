// @dependency-start
// contract test
// responsibility Preserves the native LSP provider's discovery, protocol, report, timeout, and failure contracts with an independent fake server.
// upstream implementation ../src/lsp_code_analysis.rs owns the native one-shot analysis API
// upstream implementation ../src/catalog/path_policy.rs owns retired-tools path filtering
// @dependency-end

use agent_canon::lsp_code_analysis::{
    analyze, discover_lsp_files, language_for_path, CodeAnalysisReport, LanguageId, LspServerSpec,
};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "agent-canon-lsp-native-{}-{}",
            std::process::id(),
            NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).expect("create LSP test directory");
        Self(path)
    }

    fn write(&self, relative: impl AsRef<Path>, contents: impl AsRef<[u8]>) -> PathBuf {
        let path = self.0.join(relative);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("create fixture parent");
        }
        fs::write(&path, contents).expect("write LSP fixture");
        path
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn python_executable() -> PathBuf {
    let output = Command::new("python3")
        .args(["-c", "import sys; print(sys.executable)"])
        .output()
        .expect("the native fake-server tests require the test runtime's Python interpreter");
    assert!(
        output.status.success(),
        "python3 did not report its executable"
    );
    let value = String::from_utf8(output.stdout).expect("Python path is UTF-8");
    let path = PathBuf::from(value.trim());
    assert!(
        path.is_absolute(),
        "Python test server path must be absolute"
    );
    path
}

fn fake_server(directory: &TestDirectory, mode: &str, exit_code: i32) -> PathBuf {
    let script = r#"
import json
import sys
import time

mode = __FAKE_SERVER_MODE__
exit_code = __FAKE_SERVER_EXIT_CODE__

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
    return json.loads(sys.stdin.buffer.read(int(headers["content-length"])).decode())

def send(value):
    payload = json.dumps(value, separators=(",", ":")).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
    sys.stdout.buffer.flush()

def response(message, result):
    send({"jsonrpc": "2.0", "id": message["id"], "result": result})

def symbol(uri, name="main", line=0, character=0, end=4):
    return {
        "name": name,
        "kind": 12,
        "range": {"start": {"line": line, "character": character}, "end": {"line": line, "character": end}},
        "selectionRange": {"start": {"line": line, "character": character}, "end": {"line": line, "character": end}},
    }

diagnostic = {
    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
    "severity": "bad" if mode == "bad-diagnostic" else 2,
    "code": "E1",
    "message": "warning",
    "source": "fake",
    "version": 3,
}

while True:
    message = read_message()
    if message is None:
        break
    method = message.get("method")
    if method == "initialize":
        capabilities = {"documentSymbolProvider": True}
        if mode in ("references", "optional"):
            capabilities["referencesProvider"] = True
        if mode == "optional":
            capabilities["definitionProvider"] = True
            capabilities["callHierarchyProvider"] = True
        if mode in ("pull-diagnostic", "bad-diagnostic", "exit-nonzero"):
            capabilities["diagnosticProvider"] = {"identifier": "fake"}
        if mode == "push-diagnostic":
            capabilities["textDocumentSync"] = {"openClose": True}
        if mode == "stderr-flood":
            sys.stderr.buffer.write(b"x" * (2 * 1024 * 1024))
            sys.stderr.buffer.flush()
        response(message, {"serverInfo": {"name": "fake", "version": "9.9"}, "capabilities": capabilities})
    elif method == "textDocument/didOpen" and mode == "push-diagnostic":
        send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"uri": message["params"]["textDocument"]["uri"], "diagnostics": [diagnostic]}})
    elif method == "textDocument/documentSymbol":
        if mode == "partial-header":
            sys.stdout.buffer.write(b"Content-Length: 1")
            sys.stdout.buffer.flush()
            time.sleep(2)
            break
        if mode == "malformed-json":
            sys.stdout.buffer.write(b"Content-Length: 1\r\n\r\n{")
            sys.stdout.buffer.flush()
            continue
        if mode == "malformed-symbol":
            response(message, [{"name": "broken"}])
        elif mode == "outside-symbol":
            response(message, [{"name": "outside", "kind": 12, "location": {"uri": "file:///tmp/outside-symbol.py", "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 4}}}}])
        elif mode == "external-symbol":
            response(message, [{"name": "external", "kind": 12, "location": {"uri": "https://example.invalid/symbol.py", "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 4}}}}])
        elif mode in ("references", "optional"):
            response(message, [symbol(message["params"]["textDocument"]["uri"], "first", 1, 2, 7), symbol(message["params"]["textDocument"]["uri"], "second", 3, 4, 10)])
        else:
            response(message, [symbol(message["params"]["textDocument"]["uri"])])
    elif method == "textDocument/definition" and mode == "optional":
        uri = message["params"]["textDocument"]["uri"]
        response(message, [{"uri": uri, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}}])
    elif method == "textDocument/references" and mode in ("references", "optional"):
        uri = message["params"]["textDocument"]["uri"]
        position = message["params"]["position"]
        response(message, [{"uri": uri, "range": {"start": position, "end": position}}])
    elif method == "textDocument/prepareCallHierarchy" and mode == "optional":
        uri = message["params"]["textDocument"]["uri"]
        position = message["params"]["position"]
        response(message, [{"name": "prepared", "kind": 12, "uri": uri, "range": {"start": position, "end": position}, "selectionRange": {"start": position, "end": position}}])
    elif method == "callHierarchy/incomingCalls" and mode == "optional":
        response(message, [{"from": message["params"]["item"]}])
    elif method == "callHierarchy/outgoingCalls" and mode == "optional":
        response(message, [{"to": message["params"]["item"]}])
    elif method == "textDocument/diagnostic" and mode in ("pull-diagnostic", "bad-diagnostic", "exit-nonzero"):
        response(message, {"items": [diagnostic]})
    elif method == "shutdown":
        response(message, None)
    elif method == "exit":
        if mode == "exit-nonzero":
            sys.exit(exit_code)
        break
"#
    .replace(
        "__FAKE_SERVER_MODE__",
        &serde_json::to_string(mode).expect("serialize fake-server mode"),
    )
    .replace("__FAKE_SERVER_EXIT_CODE__", &exit_code.to_string());
    directory.write("fake_lsp.py", script.as_bytes())
}

fn fake_spec(
    directory: &TestDirectory,
    language: LanguageId,
    mode: &str,
    exit_code: i32,
) -> LspServerSpec {
    let script = fake_server(directory, mode, exit_code);
    let mut command = vec![python_executable().to_string_lossy().into_owned()];
    command.extend(["-u".to_owned(), script.to_string_lossy().into_owned()]);
    LspServerSpec::caller_override(language, command).expect("fake server command is absolute")
}

fn analyze_python(
    directory: &TestDirectory,
    source: &Path,
    mode: &str,
    timeout: Duration,
) -> CodeAnalysisReport {
    let spec = fake_spec(directory, LanguageId::Python, mode, 7);
    let overrides = BTreeMap::from([(LanguageId::Python, spec)]);
    analyze(&directory.0, &[source.to_path_buf()], &overrides, timeout)
}

fn assert_status_and_error(report: &CodeAnalysisReport, code: &str) {
    assert_eq!(report.status, "failed");
    assert_eq!(
        report.error.as_ref().map(|error| error.code.as_str()),
        Some(code)
    );
    assert!(report.symbols.is_empty());
    assert!(report.relations.is_empty());
    assert!(report.diagnostics.is_empty());
    assert!(report.lexical_candidates.is_empty());
}

fn relative_files(root: &Path, files: &[PathBuf]) -> Vec<String> {
    files
        .iter()
        .map(|path| {
            path.strip_prefix(root)
                .expect("discovered file is root-relative")
                .to_string_lossy()
                .into_owned()
        })
        .collect()
}

#[test]
fn discovery_keeps_code_suffixes_and_boundaries() {
    let directory = TestDirectory::new();
    directory.write("src/main.py", "def main():\n    pass\n");
    directory.write("src/main.cpp", "int main() { return 0; }\n");
    directory.write("src/header.hxx", "int main();\n");
    directory.write("src/main.rs", "mod helper;\n");
    directory.write("src/excluded/skip.rs", "mod skip;\n");
    directory.write("src/.git/objects/leak.rs", "mod leak;\n");
    directory.write("other/outside.cpp", "int outside;\n");
    #[cfg(unix)]
    std::os::unix::fs::symlink(
        directory.0.join("other/outside.cpp"),
        directory.0.join("src/link.rs"),
    )
    .expect("create file symlink");

    let files = discover_lsp_files(
        &directory.0,
        &[
            "src".to_owned(),
            "src/main.cpp".to_owned(),
            "src".to_owned(),
        ],
        &["excluded".to_owned()],
    )
    .unwrap();

    assert_eq!(
        relative_files(&directory.0, &files),
        vec![
            "src/header.hxx".to_owned(),
            "src/main.cpp".to_owned(),
            "src/main.py".to_owned(),
            "src/main.rs".to_owned(),
        ]
    );
}

#[test]
fn default_discovery_is_bounded_and_skips_symlinks() {
    let directory = TestDirectory::new();
    for relative in [
        "python/app.py",
        "src/app.cpp",
        "include/app.hpp",
        "tests/test_app.py",
        "tools/app.py",
        "tools/legacy-helper/leak.py",
        "workspace/leak.py",
        "vendor/leak.py",
        "reports/leak.py",
        "build/leak.py",
        ".venv/leak.py",
    ] {
        directory.write(relative, "x = 1\n");
    }
    #[cfg(unix)]
    std::os::unix::fs::symlink(
        directory.0.join("python/app.py"),
        directory.0.join("src/linked.py"),
    )
    .expect("create source symlink");

    let files = discover_lsp_files(&directory.0, &[], &[]).unwrap();

    assert_eq!(
        relative_files(&directory.0, &files),
        vec![
            "include/app.hpp".to_owned(),
            "python/app.py".to_owned(),
            "src/app.cpp".to_owned(),
            "tests/test_app.py".to_owned(),
            "tools/app.py".to_owned(),
        ]
    );
}

#[cfg(unix)]
#[test]
fn discovery_rejects_explicit_file_beneath_symlink_ancestor() {
    let directory = TestDirectory::new();
    directory.write("real/main.py", "x = 1\n");
    std::os::unix::fs::symlink(directory.0.join("real"), directory.0.join("linked"))
        .expect("create directory symlink");

    let files = discover_lsp_files(&directory.0, &["linked/main.py".to_owned()], &[]).unwrap();

    assert!(files.is_empty());
}

#[cfg(unix)]
#[test]
fn discovery_missing_prefix_cannot_hide_symlink_ancestor() {
    let directory = TestDirectory::new();
    directory.write("real/main.py", "x = 1\n");
    std::os::unix::fs::symlink(directory.0.join("real"), directory.0.join("linked"))
        .expect("create directory symlink");

    let files =
        discover_lsp_files(&directory.0, &["missing/../linked/main.py".to_owned()], &[]).unwrap();

    assert!(files.is_empty());
}

#[test]
fn manifest_language_mapping_uses_shared_record_ids() {
    assert_eq!(
        language_for_path(Path::new("module.PY")),
        Some(LanguageId::Python)
    );
    assert_eq!(
        language_for_path(Path::new("header.hxx")),
        Some(LanguageId::Cpp)
    );
    assert_eq!(
        LanguageId::Cpp.dependency_record_id(),
        "clangd-language-server"
    );
    assert_eq!(LanguageId::Rust.dependency_record_id(), "rust-toolchain");
}

#[test]
fn fake_server_emits_schema_symbols_and_provenance() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "def main():\n    return 1\n");
    let report = analyze_python(&directory, &source, "standard", Duration::from_secs(2));

    assert_eq!(report.status, "complete");
    let payload = report.as_json(&directory.0);
    assert_eq!(
        payload["schema_version"],
        "agent-canon.lsp-code-analysis.v1"
    );
    assert_eq!(payload["symbols"][0]["name"], "main");
    assert_eq!(payload["symbols"][0]["uri"], "main.py");
    assert_eq!(payload["symbols"][0]["encoding"], "utf-16");
    assert_eq!(payload["provenance"]["python"]["record"], "python-custom");
    assert_eq!(payload["servers"][0]["version"], "9.9");
    assert_eq!(
        payload["capabilities"]["python"]["documentSymbolProvider"],
        "supported_facts"
    );
    assert!(payload["lifecycle"]["python"]
        .as_array()
        .unwrap()
        .contains(&Value::String("initialize(sent)".to_owned())));
    assert!(payload["lifecycle"]["python"]
        .as_array()
        .unwrap()
        .contains(&Value::String("documentSymbol:main.py".to_owned())));
    assert!(payload["error"].is_null());
}

#[test]
fn file_uris_round_trip_spaces_and_utf8_paths() {
    let directory = TestDirectory::new();
    let source = directory.write("dir/space & 日本語.py", "x = 1\n");
    let report = analyze_python(&directory, &source, "standard", Duration::from_secs(2));
    assert_eq!(report.status, "complete");
    let payload = report.as_json(&directory.0);
    assert_eq!(payload["files"], json!(["dir/space & 日本語.py"]));
    assert_eq!(payload["symbols"][0]["uri"], "dir/space & 日本語.py");
}

#[test]
fn non_file_symbol_uri_retains_external_unknown_projection() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "x = 1\n");
    let report = analyze_python(
        &directory,
        &source,
        "external-symbol",
        Duration::from_secs(2),
    );
    assert_eq!(report.status, "complete");
    let payload = report.as_json(&directory.0);
    assert_eq!(
        payload["symbols"][0]["uri"],
        "external:unknown:https://example.invalid/symbol.py"
    );
}

#[test]
fn references_use_each_symbol_selection_position() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "\n\n\n\n\n");
    let report = analyze_python(&directory, &source, "references", Duration::from_secs(2));
    assert_eq!(report.status, "complete");
    let references = report.as_json(&directory.0)["relations"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|relation| relation["orientation"] == "reference")
        .map(|relation| relation["position"].clone())
        .collect::<Vec<_>>();
    assert_eq!(
        references,
        [
            json!({"line": 1, "character": 2}),
            json!({"line": 3, "character": 4})
        ]
    );
}

#[test]
fn optional_definitions_and_call_hierarchy_are_validated() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "import dep\n\n\n\n\n");
    let report = analyze_python(&directory, &source, "optional", Duration::from_secs(2));
    assert_eq!(report.status, "complete");
    let orientations = report
        .relations
        .iter()
        .map(|relation| relation.orientation.as_str())
        .collect::<Vec<_>>();
    assert!(orientations.contains(&"definition"));
    assert!(orientations.contains(&"call-incoming"));
    assert!(orientations.contains(&"call-outgoing"));
}

#[test]
fn partial_header_is_bounded_by_request_timeout() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "x = 1\n");
    let report = analyze_python(
        &directory,
        &source,
        "partial-header",
        Duration::from_millis(100),
    );
    assert_status_and_error(&report, "request-timeout");
}

#[test]
fn large_stderr_does_not_deadlock_protocol() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "x = 1\n");
    let report = analyze_python(&directory, &source, "stderr-flood", Duration::from_secs(3));
    assert_eq!(report.status, "complete");
}

#[test]
fn outside_root_file_is_typed_path_escape() {
    let directory = TestDirectory::new();
    let root = directory.0.join("repo");
    fs::create_dir(&root).unwrap();
    let outside = directory.write("outside.py", "x = 1\n");
    let report = analyze(&root, &[outside], &BTreeMap::new(), Duration::from_secs(1));
    assert_status_and_error(&report, "path-escape");
}

#[cfg(unix)]
#[test]
fn explicit_symlink_ancestor_is_rejected() {
    let directory = TestDirectory::new();
    let target = directory.0.join("target");
    fs::create_dir(&target).unwrap();
    let source = directory.write("target/main.py", "x = 1\n");
    std::os::unix::fs::symlink(&target, directory.0.join("link")).unwrap();
    let report = analyze(
        &directory.0,
        &[directory.0.join("link/main.py")],
        &BTreeMap::new(),
        Duration::from_secs(1),
    );
    assert_status_and_error(&report, "path-escape");
    assert!(source.is_file());
}

#[cfg(unix)]
#[test]
fn nonexistent_prefix_cannot_bypass_symlink_rejection() {
    let directory = TestDirectory::new();
    let target = directory.0.join("target");
    fs::create_dir(&target).unwrap();
    directory.write("target/main.py", "x = 1\n");
    std::os::unix::fs::symlink(&target, directory.0.join("linked")).unwrap();
    let candidate = directory.0.join("missing/../linked/main.py");
    let report = analyze(
        &directory.0,
        &[candidate],
        &BTreeMap::new(),
        Duration::from_secs(1),
    );
    assert_status_and_error(&report, "path-escape");
}

#[test]
fn custom_server_requires_absolute_executable() {
    let directory = TestDirectory::new();
    directory.write("main.py", "x = 1\n");
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "lsp-code-analysis",
            "analyze",
            "--root",
            directory.0.to_str().unwrap(),
            "--files",
            "main.py",
            "--server",
            "python=pyright-langserver",
        ])
        .output()
        .expect("run native LSP CLI");
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("absolute path"));
    assert!(output.stdout.is_empty());
}

#[test]
fn explicit_empty_files_stays_empty_in_the_native_cli() {
    let directory = TestDirectory::new();
    directory.write("main.py", "x = 1\n");
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "lsp-code-analysis",
            "analyze",
            "--root",
            directory.0.to_str().unwrap(),
            "--files",
            "--format",
            "json",
        ])
        .output()
        .expect("run native LSP CLI");
    assert_eq!(output.status.code(), Some(0));
    let payload: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["status"], "complete");
    assert_eq!(payload["files"], json!([]));
    assert_eq!(payload["servers"], json!([]));
}

#[test]
fn native_cli_text_format_keeps_the_status_marker() {
    let directory = TestDirectory::new();
    directory.write("main.py", "x = 1\n");
    let server = fake_server(&directory, "standard", 0);
    let python = python_executable();
    let override_value = format!("python={} -u {}", python.display(), server.display());
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "lsp-code-analysis",
            "analyze",
            "--root",
            directory.0.to_str().unwrap(),
            "--files",
            "main.py",
            "--server",
            override_value.as_str(),
            "--format",
            "text",
        ])
        .output()
        .expect("run native LSP CLI");
    assert_eq!(output.status.code(), Some(0));
    assert_eq!(
        String::from_utf8(output.stdout).unwrap(),
        "AGENT_ANALYSIS=complete\n"
    );
    assert!(output.stderr.is_empty());
}

#[test]
fn lexical_candidates_resolve_local_modules_and_utf16_columns() {
    let directory = TestDirectory::new();
    directory.write("package.py", "value = 1\n");
    let source = directory.write("main.py", "import package\n");
    let report = analyze_python(&directory, &source, "standard", Duration::from_secs(2));
    assert_eq!(report.status, "complete");
    let candidate = report
        .lexical_candidates
        .iter()
        .find(|candidate| candidate.token == "package")
        .unwrap();
    assert_eq!(candidate.target, "package.py");
    assert_eq!(candidate.position.as_ref().unwrap().character, 7);
}

#[test]
fn python_lexical_candidates_preserve_modules_symbols_and_positions() {
    let directory = TestDirectory::new();
    for relative in [
        "pkg/__init__.py",
        "pkg/sub/__init__.py",
        "pkg/bar.py",
        "pkg/bar/__init__.py",
        "pkg/bar/baz.py",
        "pkg/a.py",
        "pkg/a/__init__.py",
        "pkg/a/x.py",
        "pkg/a/y.py",
        "pkg/foo.py",
    ] {
        directory.write(relative, "");
    }
    let sources = [
        ("pkg/sub/relative.py", "from ..bar import baz\n"),
        ("pkg/absolute.py", "from pkg.a import x, y\n"),
        ("pkg/local.py", "from . import foo\n"),
    ];
    let paths = sources
        .iter()
        .map(|(relative, contents)| directory.write(relative, contents))
        .collect::<Vec<_>>();
    let spec = fake_spec(&directory, LanguageId::Python, "standard", 0);
    let overrides = BTreeMap::from([(LanguageId::Python, spec)]);
    let report = analyze(&directory.0, &paths, &overrides, Duration::from_secs(3));
    assert_eq!(report.status, "complete");
    let observed = report
        .lexical_candidates
        .iter()
        .map(|candidate| {
            (
                candidate.source.as_str(),
                candidate.legacy_kind,
                candidate.token.as_str(),
                candidate.target.as_str(),
                candidate.position.as_ref().unwrap().line,
                candidate.position.as_ref().unwrap().character,
            )
        })
        .collect::<Vec<_>>();
    let mut expected = vec![
        (
            "pkg/sub/relative.py",
            Some("import"),
            "..bar",
            "pkg/bar.py",
            0u64,
            5u64,
        ),
        (
            "pkg/sub/relative.py",
            Some("from-import-symbol"),
            "..bar.baz",
            "pkg/bar/baz.py",
            0,
            18,
        ),
        ("pkg/absolute.py", Some("import"), "pkg.a", "pkg/a.py", 0, 5),
        (
            "pkg/absolute.py",
            Some("from-import-symbol"),
            "pkg.a.x",
            "pkg/a/x.py",
            0,
            18,
        ),
        (
            "pkg/absolute.py",
            Some("from-import-symbol"),
            "pkg.a.y",
            "pkg/a/y.py",
            0,
            21,
        ),
        ("pkg/local.py", Some("import"), ".", "pkg/__init__.py", 0, 5),
        (
            "pkg/local.py",
            Some("from-import-symbol"),
            ".foo",
            "pkg/foo.py",
            0,
            14,
        ),
    ];
    expected.sort();
    let mut observed_sorted = observed;
    observed_sorted.sort();
    assert_eq!(observed_sorted, expected);
    let payload = report.as_json(&directory.0);
    assert!(payload["lexical_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .all(|candidate| !candidate.as_object().unwrap().contains_key("legacy_kind")));
}

#[test]
fn malformed_document_symbol_has_no_partial_pass() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "def main():\n    return 1\n");
    let report = analyze_python(
        &directory,
        &source,
        "malformed-symbol",
        Duration::from_secs(2),
    );
    assert_status_and_error(&report, "malformed-response");
}

#[test]
fn outside_symbol_information_fails_as_point_lsp_report() {
    let directory = TestDirectory::new();
    directory.write("main.py", "def main():\n    return 1\n");
    let server = fake_server(&directory, "outside-symbol", 0);
    let python = python_executable();
    let override_value = format!("python={} -u {}", python.display(), server.display());
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "lsp-code-analysis",
            "analyze",
            "--root",
            directory.0.to_str().unwrap(),
            "--files",
            "main.py",
            "--server",
            override_value.as_str(),
            "--format",
            "json",
        ])
        .output()
        .expect("run native LSP CLI");
    assert_eq!(output.status.code(), Some(1));
    let stdout = String::from_utf8(output.stdout).unwrap();
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(!stderr.contains("Traceback"));
    let payload: Value = serde_json::from_str(&stdout).unwrap();
    assert_eq!(payload["status"], "failed");
    assert_eq!(payload["error"]["code"], "path-escape");
    assert!(payload["symbols"].as_array().unwrap().is_empty());
}

#[test]
fn malformed_json_response_times_out_without_partial_facts() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "def main():\n    return 1\n");
    let report = analyze_python(
        &directory,
        &source,
        "malformed-json",
        Duration::from_millis(100),
    );
    assert_status_and_error(&report, "request-timeout");
}

#[test]
fn pull_diagnostics_preserve_source_and_version() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "x = 1\n");
    let report = analyze_python(
        &directory,
        &source,
        "pull-diagnostic",
        Duration::from_secs(2),
    );
    assert_eq!(report.status, "complete");
    assert_eq!(report.diagnostics[0].source.as_deref(), Some("fake"));
    assert_eq!(report.diagnostics[0].version, Some(3));
    assert_eq!(
        report.capabilities["python"]["diagnostics"],
        "supported_facts"
    );
}

#[test]
fn push_diagnostics_are_classified_without_capability_flag() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "x = 1\n");
    let report = analyze_python(
        &directory,
        &source,
        "push-diagnostic",
        Duration::from_secs(2),
    );
    assert_eq!(report.status, "complete");
    assert_eq!(report.diagnostics[0].source.as_deref(), Some("fake"));
    assert_eq!(
        report.capabilities["python"]["diagnostics"],
        "supported_empty"
    );
}

#[test]
fn malformed_diagnostic_and_nonzero_exit_fail_closed() {
    let directory = TestDirectory::new();
    let source = directory.write("main.py", "x = 1\n");
    let malformed = analyze_python(
        &directory,
        &source,
        "bad-diagnostic",
        Duration::from_secs(2),
    );
    assert_status_and_error(&malformed, "malformed-response");
    let exited = analyze_python(&directory, &source, "exit-nonzero", Duration::from_secs(2));
    assert_status_and_error(&exited, "server-exit-nonzero");
}

#[test]
fn rust_lexical_candidates_resolve_local_modules() {
    let directory = TestDirectory::new();
    directory.write("src/helper.rs", "pub fn helper() {}\n");
    let source = directory.write("src/main.rs", "mod helper;\n");
    let spec = fake_spec(&directory, LanguageId::Rust, "standard", 0);
    let overrides = BTreeMap::from([(LanguageId::Rust, spec)]);
    let report = analyze(&directory.0, &[source], &overrides, Duration::from_secs(2));
    assert_eq!(report.status, "complete");
    assert!(report
        .lexical_candidates
        .iter()
        .any(|candidate| { candidate.token == "helper" && candidate.target == "src/helper.rs" }));
}
