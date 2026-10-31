// @dependency-start
// contract test
// responsibility Verifies bounded SCIP queries from official generated Index bytes and the native index command's status/artifact boundary.
// upstream implementation ../src/scip_index.rs owns SCIP producer and query behavior
// upstream implementation ../src/runtime_boundary.rs owns external artifact paths
// upstream implementation ../src/environment_dependencies.rs owns verified executable receipts
// @dependency-end

use protobuf::{EnumOrUnknown, Message, MessageField};
use scip::types::occurrence::Typed_range;
use scip::types::{
    Document, Index, Metadata, Occurrence, Relationship, SingleLineRange, SymbolInformation,
    TextEncoding, ToolInfo,
};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "agent-canon-scip-native-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir_all(&root).expect("create SCIP fixture root");
        let root = fs::canonicalize(root).expect("resolve SCIP fixture root");
        fs::create_dir_all(root.join("source tree")).expect("create source root");
        fs::create_dir_all(root.join("runtime")).expect("create runtime root");
        Self(root)
    }

    fn source(&self) -> PathBuf {
        self.0.join("source tree")
    }

    fn runtime(&self) -> PathBuf {
        self.0.join("runtime")
    }

    fn write_source(&self, relative: &str, text: &str) {
        let path = self.source().join(relative);
        fs::create_dir_all(path.parent().expect("source fixture has parent"))
            .expect("create source fixture parent");
        fs::write(path, text).expect("write source fixture");
    }

    fn write_index(&self, relative: &str, bytes: &[u8]) {
        let path = self.runtime().join(relative);
        fs::create_dir_all(path.parent().expect("index fixture has parent"))
            .expect("create index fixture parent");
        fs::write(path, bytes).expect("write official SCIP fixture bytes");
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn file_uri(path: &Path) -> String {
    let mut encoded = String::new();
    for byte in path.to_string_lossy().as_bytes() {
        if byte.is_ascii_alphanumeric() || matches!(*byte, b'/' | b'-' | b'.' | b'_' | b'~') {
            encoded.push(char::from(*byte));
        } else {
            encoded.push_str(&format!("%{byte:02X}"));
        }
    }
    format!("file://{encoded}")
}

fn typed_occurrence(symbol: &str, roles: i32, start: i32, end: i32) -> Occurrence {
    let mut range = SingleLineRange::new();
    range.line = 1;
    range.start_character = start;
    range.end_character = end;
    let mut occurrence = Occurrence::new();
    occurrence.symbol = symbol.to_string();
    occurrence.symbol_roles = roles;
    occurrence.typed_range = Some(Typed_range::SingleLineRange(range));
    occurrence
}

fn legacy_occurrence(symbol: &str, roles: i32, range: &[i32]) -> Occurrence {
    let mut occurrence = Occurrence::new();
    occurrence.symbol = symbol.to_string();
    occurrence.symbol_roles = roles;
    occurrence.range = range.to_vec();
    occurrence
}

fn symbol_information(symbol: &str, relationships: Vec<Relationship>) -> SymbolInformation {
    let mut information = SymbolInformation::new();
    information.symbol = symbol.to_string();
    information.relationships = relationships;
    information
}

fn document(
    relative_path: &str,
    language: &str,
    occurrences: Vec<Occurrence>,
    symbols: Vec<SymbolInformation>,
) -> Document {
    let mut document = Document::new();
    document.relative_path = relative_path.to_string();
    document.language = language.to_string();
    document.occurrences = occurrences;
    document.symbols = symbols;
    document
}

fn index_bytes(
    root: &Path,
    documents: Vec<Document>,
    external_symbols: Vec<SymbolInformation>,
) -> Vec<u8> {
    let mut metadata = Metadata::new();
    metadata.project_root = file_uri(root);
    metadata.tool_info = MessageField::some(ToolInfo {
        name: "fixture-indexer".to_string(),
        version: "1.2.3".to_string(),
        ..ToolInfo::new()
    });
    metadata.text_document_encoding = EnumOrUnknown::new(TextEncoding::UTF8);
    let mut index = Index::new();
    index.metadata = MessageField::some(metadata);
    index.documents = documents;
    index.external_symbols = external_symbols;
    index
        .write_to_bytes()
        .expect("official generated SCIP Index serializes")
}

fn query_cli(
    fixture: &Fixture,
    index_paths: &[&str],
    target_paths: &[&str],
    symbols: &[&str],
) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
    command.args([
        "scip-index",
        "query",
        "--root",
        fixture
            .source()
            .to_str()
            .expect("fixture source path is UTF-8"),
        "--runtime-root",
        fixture
            .runtime()
            .to_str()
            .expect("fixture runtime path is UTF-8"),
    ]);
    for index in index_paths {
        command.args(["--index", index]);
    }
    for path in target_paths {
        command.args(["--path", path]);
    }
    for symbol in symbols {
        command.args(["--symbol", symbol]);
    }
    command
        .output()
        .expect("current native agent-canon executable runs")
}

fn json_output(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).expect("native SCIP output is JSON")
}

fn files_below(root: &Path) -> Vec<PathBuf> {
    let mut pending = vec![root.to_path_buf()];
    let mut files = Vec::new();
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(directory).expect("read runtime fixture directory") {
            let entry = entry.expect("runtime fixture entry is readable");
            let path = entry.path();
            let file_type = entry.file_type().expect("runtime fixture type is readable");
            if file_type.is_dir() {
                pending.push(path);
            } else if file_type.is_file() {
                files.push(path);
            }
        }
    }
    files.sort();
    files
}

fn sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn query_projects_selected_symbol_relations_from_official_index_bytes() {
    let fixture = Fixture::new();
    fixture.write_source("pkg/api.py", "def run(): pass\n");
    fixture.write_source("pkg/use.py", "run()\n");
    fixture.write_source("pkg/ref_only.py", "run()\n");
    fixture.write_source("pkg/impl.py", "class FastRun: pass\n");
    fixture.write_source("pkg/unrelated.py", "def unrelated(): pass\n");
    let target_symbol = "scip-python python demo 0.1.0 pkg.api/run().";
    let implementation_symbol = "scip-python python demo 0.1.0 pkg.impl/FastRun#";
    let mut implementation = Relationship::new();
    implementation.symbol = target_symbol.to_string();
    implementation.is_implementation = true;
    let bytes = index_bytes(
        &fixture.source(),
        vec![
            document(
                "pkg/api.py",
                "python",
                vec![typed_occurrence(target_symbol, 0x1, 4, 7)],
                vec![symbol_information(target_symbol, Vec::new())],
            ),
            document(
                "pkg/use.py",
                "python",
                vec![legacy_occurrence(target_symbol, 0x8, &[1, 11, 14])],
                Vec::new(),
            ),
            document(
                "pkg/ref_only.py",
                "python",
                vec![legacy_occurrence(target_symbol, 0x8, &[1, 2, 8])],
                Vec::new(),
            ),
            document(
                "pkg/impl.py",
                "python",
                vec![legacy_occurrence(implementation_symbol, 0x1, &[1, 0, 8])],
                vec![symbol_information(
                    implementation_symbol,
                    vec![implementation],
                )],
            ),
            document(
                "pkg/unrelated.py",
                "python",
                vec![legacy_occurrence(
                    "scip-python python demo 0.1.0 pkg.other/unrelated().",
                    0x1,
                    &[1, 0, 9],
                )],
                Vec::new(),
            ),
        ],
        Vec::new(),
    );
    fixture.write_index("runs/python/index.scip", &bytes);

    let output = query_cli(&fixture, &["runs/python/index.scip"], &["pkg/api.py"], &[]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload = json_output(&output);
    assert_eq!(payload["status"], "projected");
    assert_eq!(payload["symbols"], serde_json::json!([target_symbol]));
    assert_eq!(
        payload["definitions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row["path"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec!["pkg/api.py"]
    );
    assert_eq!(payload["definitions"][0]["range"]["start"]["line"], 1);
    assert_eq!(
        payload["references"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row["path"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec!["pkg/use.py", "pkg/ref_only.py"]
    );
    assert_eq!(payload["references"][0]["range"]["start"]["character"], 11);
    assert_eq!(
        payload["references"][0]["roles"],
        serde_json::json!(["read-access"])
    );
    assert_eq!(payload["implementations"][0]["path"], "pkg/impl.py");
    assert_eq!(payload["capabilities"]["callers"], "not-represented");
    assert_eq!(payload["capabilities"]["callees"], "not-represented");
    assert_eq!(payload["capabilities"]["source_freshness"], "unverified");
    assert_eq!(payload["index_refs"][0]["sha256"], sha256(&bytes));
    assert_eq!(payload["index_refs"][0]["project_root"], ".");
    assert_eq!(payload["index_refs"][0]["text_encoding"], "1");
    assert_eq!(
        files_below(&fixture.runtime()),
        vec![fixture.runtime().join("runs/python/index.scip")]
    );

    let reference_seed = json_output(&query_cli(
        &fixture,
        &["runs/python/index.scip"],
        &["pkg/ref_only.py"],
        &[],
    ));
    assert_eq!(
        reference_seed["symbols"],
        serde_json::json!([target_symbol])
    );
    assert_eq!(reference_seed["definitions"][0]["path"], "pkg/api.py");

    let directory_seed = json_output(&query_cli(
        &fixture,
        &["runs/python/index.scip"],
        &["."],
        &[],
    ));
    assert_eq!(directory_seed["capabilities"]["target_paths"], "partial");

    let symbol_seed = json_output(&query_cli(
        &fixture,
        &["runs/python/index.scip"],
        &[],
        &[target_symbol],
    ));
    assert_eq!(symbol_seed["capabilities"]["target_paths"], "not-selected");
}

#[test]
fn query_marks_unindexed_target_without_claiming_no_references() {
    let fixture = Fixture::new();
    let bytes = index_bytes(
        &fixture.source(),
        vec![document("src/lib.rs", "rust", Vec::new(), Vec::new())],
        Vec::new(),
    );
    fixture.write_index("index.scip", &bytes);

    let output = query_cli(&fixture, &["index.scip"], &["src/unsupported.sh"], &[]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload = json_output(&output);
    assert_eq!(payload["status"], "unindexed-target");
    assert_eq!(
        payload["unindexed_targets"],
        serde_json::json!(["src/unsupported.sh"])
    );
    assert_eq!(payload["definitions"], serde_json::json!([]));
    assert_eq!(payload["references"], serde_json::json!([]));
    assert_eq!(payload["capabilities"]["target_paths"], "partial");
}

#[test]
fn unsupported_languages_do_not_create_external_runtime_state() {
    let fixture = Fixture::new();
    for language in ["shell", "rust"] {
        let output_path = format!("runs/{language}/index.scip");
        let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
            .args([
                "scip-index",
                "index",
                "--root",
                fixture.source().to_str().unwrap(),
                "--runtime-root",
                fixture.runtime().to_str().unwrap(),
                "--output",
                output_path.as_str(),
                "--language",
                language,
            ])
            .output()
            .expect("current native agent-canon executable runs");
        assert!(output.status.success());
        let payload = json_output(&output);
        assert_eq!(payload["status"], "unsupported");
        assert_eq!(payload["language"], language);
        assert_eq!(payload["capabilities"][language], "unsupported");
    }
    assert!(!fixture.runtime().join("runs").exists());
}

#[test]
fn supported_indexer_requires_project_owned_inputs_before_runtime_creation() {
    let fixture = Fixture::new();
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "scip-index",
            "index",
            "--root",
            fixture.source().to_str().unwrap(),
            "--runtime-root",
            fixture.runtime().to_str().unwrap(),
            "--output",
            "runs/python/index.scip",
            "--language",
            "python",
        ])
        .output()
        .expect("current native agent-canon executable runs");

    assert!(output.status.success());
    let payload = json_output(&output);
    assert_eq!(payload["status"], "input-required");
    assert_eq!(payload["language"], "python");
    assert_eq!(payload["capabilities"]["python"], "input-required");
    assert!(!fixture.runtime().join("runs").exists());
}
