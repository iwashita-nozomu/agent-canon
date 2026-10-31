// @dependency-start
// contract implementation
// responsibility Owns bounded LSP file discovery, verified server selection, one-shot analysis, and deterministic code facts.
// upstream design ../../../../../documents/structured-analysis/code-analysis.md code-analysis boundary
// upstream design ../../../../../documents/tools/lsp_code_analysis.md LSP adapter contract
// upstream implementation python_ast.rs shares Python newline normalization and source offsets
// upstream implementation catalog/path_policy.rs filters retired tool paths
// upstream implementation ../../../../../bootstrap/container/image/dependencies.toml pins the public JSON-RPC transport runtime
// downstream implementation ../../../../../tests/agent_tools/test_lsp_code_analysis.py preserves live Python callers and old assertions
// downstream implementation ../tests/lsp_code_analysis_native.rs verifies native protocol and report behavior
// @dependency-end
//! Bounded, one-shot LSP code analysis with no persistent index or fallback provider.

use crate::catalog::path_policy::is_retired_legacy_tool_path;
use crate::python_ast::{line_at_offset, normalize_python_newlines};
use lsp_server::{ErrorCode, Message, Notification, ReqQueue, Request, Response};
use regex::Regex;
use rustpython_ast::{Ranged, Visitor};
use rustpython_parser::{ast, Parse};
use serde::Serialize;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::env;
use std::error::Error;
use std::fmt;
use std::fs;
use std::io::{BufReader, Read};
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, SyncSender};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

pub const SCHEMA_VERSION: &str = "agent-canon.lsp-code-analysis.v1";
pub const LSP_VERSION: &str = "3.17";
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(15);
const STDERR_LIMIT: usize = 64 * 1024;
const NOTIFICATION_QUIET: Duration = Duration::from_millis(50);
const CLEAN_EXIT_WAIT: Duration = Duration::from_secs(1);
const THREAD_JOIN_WAIT: Duration = Duration::from_millis(200);
const READER_QUEUE_CAPACITY: usize = 128;
const IMAGE_RECEIPT_ROOT: &str = "/usr/local/share/agent-canon/image-dependencies/receipts";
const IMAGE_MANIFEST_ROOT: &str = "/usr/local/share/agent-canon/runtime";

const DEFAULT_SURFACES: &[&str] = &[
    "tools",
    "agents",
    ".agents",
    ".codex",
    "documents",
    "mcp",
    "python",
    "src",
    "include",
    "tests",
];
const EXCLUDED_PARTS: &[&str] = &[
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "legacy",
    "node_modules",
    "reports",
    "vendor",
    "workspace",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum LanguageId {
    C,
    Cpp,
    Python,
    Rust,
    Shellscript,
}

impl LanguageId {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::C => "c",
            Self::Cpp => "cpp",
            Self::Python => "python",
            Self::Rust => "rust",
            Self::Shellscript => "shellscript",
        }
    }

    pub fn dependency_record_id(self) -> &'static str {
        match self {
            Self::C | Self::Cpp => "clangd-language-server",
            Self::Python => "pyright-language-server",
            Self::Rust => "rust-toolchain",
            Self::Shellscript => "bash-language-server",
        }
    }

    fn command(self) -> &'static [&'static str] {
        match self {
            Self::C | Self::Cpp => &["clangd-18"],
            Self::Python => &["pyright-langserver", "--stdio"],
            Self::Rust => &["rust-analyzer"],
            Self::Shellscript => &["bash-language-server", "start"],
        }
    }
}

impl fmt::Display for LanguageId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

pub fn language_for_path(path: &Path) -> Option<LanguageId> {
    let suffix = path.extension()?.to_str()?.to_ascii_lowercase();
    match suffix.as_str() {
        "py" | "pyi" => Some(LanguageId::Python),
        "c" => Some(LanguageId::C),
        "cc" | "cpp" | "cxx" | "h" | "hh" | "hpp" | "hxx" => Some(LanguageId::Cpp),
        "sh" | "bash" | "zsh" => Some(LanguageId::Shellscript),
        "rs" => Some(LanguageId::Rust),
        _ => None,
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LspAnalysisError {
    pub code: &'static str,
    pub message: String,
}

impl LspAnalysisError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

impl fmt::Display for LspAnalysisError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl Error for LspAnalysisError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LspServerSpec {
    pub language_id: LanguageId,
    command: Vec<String>,
    pub record_id: String,
    pub version: String,
    pub executable: String,
    pub resolution: String,
    pub verification_output: String,
}

impl LspServerSpec {
    pub fn caller_override(
        language_id: LanguageId,
        command: Vec<String>,
    ) -> Result<Self, LspAnalysisError> {
        let executable = command.first().cloned().ok_or_else(|| {
            LspAnalysisError::new(
                "server-unavailable",
                "LspServerSpec.command must not be empty",
            )
        })?;
        if !Path::new(&executable).is_absolute() {
            return Err(LspAnalysisError::new(
                "server-unavailable",
                "custom LSP executable must be an absolute path",
            ));
        }
        Ok(Self {
            language_id,
            command,
            record_id: format!("{}-custom", language_id.as_str()),
            version: String::new(),
            executable,
            resolution: "caller-override".to_owned(),
            verification_output: String::new(),
        })
    }

    pub fn for_language(
        language_id: LanguageId,
        analysis_root: &Path,
    ) -> Result<Self, LspAnalysisError> {
        if analysis_root.as_os_str().is_empty() {
            return Err(LspAnalysisError::new(
                "server-unavailable",
                "manifest executable resolution requires an analysis root",
            ));
        }
        let source_root = source_repository_root()?;
        let manifest_override = env::var("AGENT_CANON_DEPENDENCY_MANIFEST")
            .ok()
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .map(|value| expand_user_path(&value));
        let receipt_override = env::var("AGENT_CANON_DEPENDENCY_RECEIPTS")
            .ok()
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .map(|value| expand_user_path(&value));
        let (manifest, receipts) = select_dependency_paths(
            &source_root,
            &PathBuf::from(IMAGE_MANIFEST_ROOT).join("dependencies.toml"),
            Path::new(IMAGE_RECEIPT_ROOT),
            manifest_override.as_deref(),
            None,
            receipt_override.as_deref(),
        )?;
        let workspace = manifest
            .parent()
            .and_then(Path::parent)
            .and_then(Path::parent)
            .ok_or_else(|| {
                LspAnalysisError::new(
                    "server-unavailable",
                    "dependency manifest has no workspace root",
                )
            })?;
        let command = language_id.command();
        let verified = crate::environment_dependencies::resolve_verified_executable(
            workspace,
            &receipts,
            language_id.dependency_record_id(),
            command[0],
            Some(&manifest),
        )
        .map_err(|error| {
            LspAnalysisError::new(
                "server-unavailable",
                format!("manifest executable verification failed for {language_id}: {error}"),
            )
        })?;
        let executable = verified.absolute_path.to_string_lossy().into_owned();
        let mut resolved_command = Vec::with_capacity(command.len());
        resolved_command.push(executable.clone());
        resolved_command.extend(
            command
                .iter()
                .skip(1)
                .map(|argument| (*argument).to_owned()),
        );
        Ok(Self {
            language_id,
            command: resolved_command,
            record_id: verified.record_id,
            version: verified.manifest_version,
            executable,
            resolution: "manifest".to_owned(),
            verification_output: verified.verification_output,
        })
    }

    pub fn command(&self) -> &[String] {
        &self.command
    }

    fn as_json(&self) -> Value {
        json!({
            "languageId": self.language_id.as_str(),
            "record": self.record_id,
            "command": self.command,
            "version": self.version,
            "executable": if self.executable.is_empty() { self.command.first().cloned().unwrap_or_default() } else { self.executable.clone() },
            "resolution": self.resolution,
            "verificationOutput": self.verification_output,
        })
    }
}

fn source_repository_root() -> Result<PathBuf, LspAnalysisError> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .map(Path::to_path_buf)
        .ok_or_else(|| {
            LspAnalysisError::new(
                "server-unavailable",
                "native LSP source root is unavailable",
            )
        })
}

fn expand_user_path(value: &str) -> PathBuf {
    if value == "~" {
        return env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(value));
    }
    if let Some(suffix) = value.strip_prefix("~/") {
        if let Some(home) = env::var_os("HOME") {
            return PathBuf::from(home).join(suffix);
        }
    }
    PathBuf::from(value)
}

fn select_dependency_paths(
    source_root: &Path,
    image_manifest: &Path,
    image_receipts: &Path,
    manifest_override: Option<&Path>,
    explicit_receipts: Option<&Path>,
    receipt_override: Option<&Path>,
) -> Result<(PathBuf, PathBuf), LspAnalysisError> {
    let source_manifest = source_root.join("bootstrap/container/image/dependencies.toml");
    let manifest = if let Some(path) = manifest_override {
        resolve_path(path)
    } else if source_manifest.is_file() {
        resolve_path(&source_manifest)
    } else {
        resolve_path(image_manifest)
    };
    if !manifest.is_file() {
        return Err(LspAnalysisError::new(
            "server-unavailable",
            "shared tool dependency manifest is unavailable; start bootstrap.sh",
        ));
    }
    let receipts = if let Some(path) = explicit_receipts {
        path.to_path_buf()
    } else if image_receipts.is_dir() {
        image_receipts.to_path_buf()
    } else if let Some(path) = receipt_override {
        resolve_path(path)
    } else {
        return Err(LspAnalysisError::new(
            "server-unavailable",
            "shared tool dependency receipts are unavailable; start bootstrap.sh",
        ));
    };
    Ok((manifest, receipts))
}

fn resolve_path(path: &Path) -> PathBuf {
    fs::canonicalize(path).unwrap_or_else(|_| {
        if path.is_absolute() {
            path.to_path_buf()
        } else {
            env::current_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join(path)
        }
    })
}

#[cfg(test)]
mod dependency_selection_tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_ROOT: AtomicUsize = AtomicUsize::new(0);

    struct TestRoot(PathBuf);

    impl TestRoot {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "agent-canon-lsp-dependency-selection-{}-{}",
                std::process::id(),
                NEXT_ROOT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).expect("create dependency-selection fixture");
            let path = fs::canonicalize(path).expect("resolve dependency-selection fixture");
            Self(path)
        }

        fn write(&self, relative: &str, contents: &str) -> PathBuf {
            let path = self.0.join(relative);
            fs::create_dir_all(path.parent().unwrap()).expect("create fixture parent");
            fs::write(&path, contents).expect("write fixture file");
            path
        }

        fn directory(&self, relative: &str) -> PathBuf {
            let path = self.0.join(relative);
            fs::create_dir_all(&path).expect("create fixture directory");
            path
        }
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn manifest_and_receipt_selection_preserves_override_image_and_source_precedence() {
        let fixture = TestRoot::new();
        let source_root = fixture.0.join("source");
        let source_manifest = fixture.write(
            "source/bootstrap/container/image/dependencies.toml",
            "source\n",
        );
        let image_manifest = fixture.write("image/dependencies.toml", "image\n");
        let image_receipts = fixture.directory("image-receipts");
        let manifest_override = fixture.write("override/dependencies.toml", "override\n");
        let receipt_override = fixture.directory("receipt-override");
        let environment_receipts = fixture.directory("environment-receipts");

        let (manifest, receipts) = select_dependency_paths(
            &source_root,
            &image_manifest,
            &image_receipts,
            Some(&manifest_override),
            Some(&receipt_override),
            Some(&environment_receipts),
        )
        .unwrap();
        assert_eq!(manifest, fs::canonicalize(manifest_override).unwrap());
        assert_eq!(receipts, receipt_override);

        let (manifest, receipts) = select_dependency_paths(
            &source_root,
            &image_manifest,
            &image_receipts,
            None,
            None,
            Some(&environment_receipts),
        )
        .unwrap();
        assert_eq!(manifest, fs::canonicalize(source_manifest).unwrap());
        assert_eq!(receipts, image_receipts);

        fs::remove_file(source_root.join("bootstrap/container/image/dependencies.toml")).unwrap();
        fs::remove_dir_all(&image_receipts).unwrap();
        let (manifest, receipts) = select_dependency_paths(
            &source_root,
            &image_manifest,
            &image_receipts,
            None,
            None,
            Some(&environment_receipts),
        )
        .unwrap();
        assert_eq!(manifest, fs::canonicalize(image_manifest).unwrap());
        assert_eq!(receipts, environment_receipts);
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Position {
    pub line: u64,
    pub character: u64,
}

impl Position {
    fn as_json(&self) -> Value {
        json!({"line": self.line, "character": self.character})
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LspRange {
    pub start: Position,
    pub end: Position,
}

impl LspRange {
    fn as_json(&self) -> Value {
        json!({"start": self.start.as_json(), "end": self.end.as_json()})
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodeSymbol {
    pub uri: String,
    pub name: String,
    pub kind: u64,
    pub range: LspRange,
    pub selection_range: LspRange,
    pub container: Option<String>,
}

impl CodeSymbol {
    fn as_json(&self, root: &Path) -> Result<Value, LspAnalysisError> {
        Ok(json!({
            "uri": uri_path(root, &self.uri)
                .map_err(|error| LspAnalysisError::new(error.code, error.message))?,
            "name": self.name,
            "kind": self.kind,
            "range": self.range.as_json(),
            "selectionRange": self.selection_range.as_json(),
            "container": self.container,
            "encoding": "utf-16",
        }))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodeRelation {
    pub orientation: String,
    pub source: String,
    pub target: String,
    pub position: Option<Position>,
}

impl CodeRelation {
    fn as_json(&self) -> Value {
        json!({
            "orientation": self.orientation,
            "source": self.source,
            "target": self.target,
            "position": self.position.as_ref().map(Position::as_json),
            "encoding": "utf-16",
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodeDiagnostic {
    pub uri: String,
    pub range: LspRange,
    pub severity: Option<u64>,
    pub code: Option<Value>,
    pub message: String,
    pub source: Option<String>,
    pub version: Option<u64>,
}

impl CodeDiagnostic {
    fn as_json(&self, root: &Path) -> Result<Value, LspAnalysisError> {
        Ok(json!({
            "uri": uri_path(root, &self.uri)
                .map_err(|error| LspAnalysisError::new(error.code, error.message))?,
            "range": self.range.as_json(),
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "source": self.source,
            "version": self.version,
            "encoding": "utf-16",
        }))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LexicalDependencyCandidate {
    pub source: String,
    pub token: String,
    pub target: String,
    pub position: Option<Position>,
    pub legacy_kind: Option<&'static str>,
}

impl LexicalDependencyCandidate {
    fn as_json(&self) -> Value {
        json!({
            "source": self.source,
            "token": self.token,
            "target": self.target,
            "position": self.position.as_ref().map(Position::as_json),
            "encoding": "utf-16",
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodeAnalysisReport {
    pub root: PathBuf,
    pub files: Vec<String>,
    pub servers: Vec<Value>,
    pub capabilities: BTreeMap<String, BTreeMap<String, String>>,
    pub symbols: Vec<CodeSymbol>,
    pub relations: Vec<CodeRelation>,
    pub diagnostics: Vec<CodeDiagnostic>,
    pub lexical_candidates: Vec<LexicalDependencyCandidate>,
    pub lifecycle: Value,
    pub status: String,
    pub provenance: Value,
    pub error: Option<ReportError>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ReportError {
    pub code: String,
    pub message: String,
}

impl CodeAnalysisReport {
    pub fn as_json(&self, root: &Path) -> Value {
        let symbols = self
            .symbols
            .iter()
            .map(|symbol| {
                symbol
                    .as_json(root)
                    .expect("analyzed symbol URIs were validated against the report root")
            })
            .collect::<Vec<_>>();
        let diagnostics = self
            .diagnostics
            .iter()
            .map(|diagnostic| {
                diagnostic
                    .as_json(root)
                    .expect("analyzed diagnostic URIs were validated against the report root")
            })
            .collect::<Vec<_>>();
        json!({
            "schema_version": SCHEMA_VERSION,
            "root": path_as_posix(&self.root),
            "files": self.files,
            "servers": self.servers,
            "capabilities": self.capabilities,
            "symbols": symbols,
            "relations": self.relations.iter().map(CodeRelation::as_json).collect::<Vec<_>>(),
            "diagnostics": diagnostics,
            "lexical_candidates": self.lexical_candidates.iter().map(LexicalDependencyCandidate::as_json).collect::<Vec<_>>(),
            "lifecycle": self.lifecycle,
            "status": self.status,
            "provenance": self.provenance,
            "error": self.error,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct CapabilityMatrix {
    document_symbols: bool,
    definitions: bool,
    references: bool,
    call_hierarchy: bool,
    diagnostics: bool,
}

impl CapabilityMatrix {
    fn from_initialize(capabilities: &Map<String, Value>) -> Self {
        Self {
            document_symbols: json_truthy(capabilities.get("documentSymbolProvider")),
            definitions: json_truthy(capabilities.get("definitionProvider")),
            references: json_truthy(capabilities.get("referencesProvider")),
            call_hierarchy: json_truthy(capabilities.get("callHierarchyProvider")),
            diagnostics: json_truthy(capabilities.get("diagnosticProvider")),
        }
    }

    fn as_json(self) -> BTreeMap<String, String> {
        BTreeMap::from([
            (
                "callHierarchyProvider".to_owned(),
                capability_label(self.call_hierarchy),
            ),
            (
                "definitionProvider".to_owned(),
                capability_label(self.definitions),
            ),
            ("diagnostics".to_owned(), capability_label(self.diagnostics)),
            (
                "documentSymbolProvider".to_owned(),
                capability_label(self.document_symbols),
            ),
            (
                "referencesProvider".to_owned(),
                capability_label(self.references),
            ),
        ])
    }
}

fn capability_label(supported: bool) -> String {
    if supported {
        "supported_facts"
    } else {
        "unsupported"
    }
    .to_owned()
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct AnalysisFailure {
    code: &'static str,
    message: String,
}

impl AnalysisFailure {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }

    fn report_error(&self) -> ReportError {
        ReportError {
            code: self.code.to_owned(),
            message: self.message.clone(),
        }
    }
}

impl fmt::Display for AnalysisFailure {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl Error for AnalysisFailure {}

enum ReaderEvent {
    Message(Message),
    Closed,
    Failure(AnalysisFailure),
}

struct LspProcessSession {
    spec: LspServerSpec,
    root: PathBuf,
    timeout: Duration,
    child: Option<Child>,
    stdin: Option<std::process::ChildStdin>,
    events: Receiver<ReaderEvent>,
    reader_done: Receiver<()>,
    reader_thread: Option<JoinHandle<()>>,
    stderr_done: Receiver<()>,
    stderr_thread: Option<JoinHandle<()>>,
    requests: ReqQueue<String, String>,
    request_count: usize,
    lifecycle: Vec<String>,
    published_diagnostics: Vec<Value>,
    finished: bool,
}

impl LspProcessSession {
    fn start(spec: LspServerSpec, root: &Path, timeout: Duration) -> Result<Self, AnalysisFailure> {
        let Some((executable, args)) = spec.command.split_first() else {
            return Err(AnalysisFailure::new(
                "server-unavailable",
                "LspServerSpec.command must not be empty",
            ));
        };
        let mut child = Command::new(executable)
            .args(args)
            .current_dir(root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|_| {
                AnalysisFailure::new(
                    "server-unavailable",
                    format!("unable to start {executable}"),
                )
            })?;
        let stdin = child.stdin.take();
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        if stdin.is_none() || stdout.is_none() || stderr.is_none() {
            stop_child(&mut child);
            return Err(AnalysisFailure::new(
                "server-unavailable",
                "LSP process pipes could not be opened",
            ));
        }

        let (event_tx, events) = mpsc::sync_channel(READER_QUEUE_CAPACITY);
        let (reader_done_tx, reader_done) = mpsc::sync_channel(1);
        let reader_stdout = stdout.expect("stdout was checked");
        let reader_thread = match thread::Builder::new()
            .name("agent-canon-lsp-stdout".to_owned())
            .spawn(move || read_lsp_messages(reader_stdout, event_tx, reader_done_tx))
        {
            Ok(thread) => thread,
            Err(error) => {
                stop_child(&mut child);
                return Err(AnalysisFailure::new(
                    "server-unavailable",
                    format!("unable to start LSP stdout reader: {error}"),
                ));
            }
        };

        let stderr_bytes = Arc::new(Mutex::new(Vec::with_capacity(STDERR_LIMIT)));
        let (stderr_done_tx, stderr_done) = mpsc::sync_channel(1);
        let stderr_stream = stderr.expect("stderr was checked");
        let stderr_capture = Arc::clone(&stderr_bytes);
        let stderr_thread = match thread::Builder::new()
            .name("agent-canon-lsp-stderr".to_owned())
            .spawn(move || drain_stderr(stderr_stream, stderr_capture, stderr_done_tx))
        {
            Ok(thread) => thread,
            Err(error) => {
                stop_child(&mut child);
                drop(events);
                join_when_done(reader_thread, &reader_done);
                return Err(AnalysisFailure::new(
                    "server-unavailable",
                    format!("unable to start LSP stderr reader: {error}"),
                ));
            }
        };

        Ok(Self {
            spec,
            root: root.to_path_buf(),
            timeout,
            child: Some(child),
            stdin,
            events,
            reader_done,
            reader_thread: Some(reader_thread),
            stderr_done,
            stderr_thread: Some(stderr_thread),
            requests: ReqQueue::default(),
            request_count: 0,
            lifecycle: vec!["created".to_owned()],
            published_diagnostics: Vec::new(),
            finished: false,
        })
    }

    fn request(&mut self, method: &str, params: Value) -> Result<Value, AnalysisFailure> {
        if self.process_status()?.is_some() {
            return Err(AnalysisFailure::new(
                "protocol-violation",
                "LSP server exited before responding",
            ));
        }
        let request = self
            .requests
            .outgoing
            .register(method.to_owned(), params, method.to_owned());
        let request_id = request.id.clone();
        self.request_count += 1;
        let stdin = self.stdin.as_mut().ok_or_else(|| {
            AnalysisFailure::new("protocol-violation", "LSP process is not running")
        })?;
        Message::Request(request)
            .write(stdin)
            .map_err(|_| AnalysisFailure::new("protocol-violation", "LSP JSON-RPC write failed"))?;

        let deadline = Instant::now() + self.timeout;
        loop {
            let now = Instant::now();
            if now >= deadline {
                return Err(AnalysisFailure::new(
                    "request-timeout",
                    format!("LSP request timed out: {method}"),
                ));
            }
            let remaining = deadline.saturating_duration_since(now);
            match self
                .events
                .recv_timeout(remaining.min(Duration::from_millis(50)))
            {
                Ok(ReaderEvent::Message(Message::Response(response))) => {
                    let completed = self.requests.outgoing.complete(response.id.clone());
                    if completed.as_deref() != Some(method) || response.id != request_id {
                        return Err(AnalysisFailure::new(
                            "protocol-violation",
                            "LSP response did not match an outstanding request",
                        ));
                    }
                    return response.response_result.map_err(|error| {
                        AnalysisFailure::new(
                            "protocol-violation",
                            format!("LSP {method} failed: {}", error.message),
                        )
                    });
                }
                Ok(ReaderEvent::Message(Message::Notification(notification))) => {
                    self.handle_notification(notification)?;
                }
                Ok(ReaderEvent::Message(Message::Request(request))) => {
                    self.handle_server_request(request)?;
                }
                Ok(ReaderEvent::Closed) => {
                    return Err(AnalysisFailure::new(
                        "protocol-violation",
                        "LSP server closed stdout",
                    ));
                }
                Ok(ReaderEvent::Failure(error)) => return Err(error),
                Err(RecvTimeoutError::Disconnected) => {
                    return Err(AnalysisFailure::new(
                        "protocol-violation",
                        "LSP message reader stopped",
                    ));
                }
                Err(RecvTimeoutError::Timeout) => {
                    if self.process_status()?.is_some() {
                        return Err(AnalysisFailure::new(
                            "protocol-violation",
                            "LSP server exited before responding",
                        ));
                    }
                }
            }
        }
    }

    fn notify(&mut self, method: &str, params: Value) -> Result<(), AnalysisFailure> {
        if self.process_status()?.is_some() {
            return Err(AnalysisFailure::new(
                "protocol-violation",
                "LSP server exited before notification",
            ));
        }
        let stdin = self.stdin.as_mut().ok_or_else(|| {
            AnalysisFailure::new("protocol-violation", "LSP process is not running")
        })?;
        Message::Notification(Notification::new(method.to_owned(), params))
            .write(stdin)
            .map_err(|_| {
                AnalysisFailure::new(
                    "protocol-violation",
                    format!("LSP {method} notification could not be sent"),
                )
            })
    }

    fn handle_notification(&mut self, notification: Notification) -> Result<(), AnalysisFailure> {
        if notification.method != "textDocument/publishDiagnostics" {
            return Ok(());
        }
        let params = notification.params;
        let object = params.as_object().ok_or_else(|| {
            AnalysisFailure::new(
                "malformed-response",
                "publishDiagnostics params must be an object",
            )
        })?;
        if !object.get("uri").is_some_and(Value::is_string) {
            return Err(AnalysisFailure::new(
                "malformed-response",
                "publishDiagnostics URI must be a string",
            ));
        }
        let diagnostics = object.get("diagnostics").and_then(Value::as_array);
        if !diagnostics.is_some_and(|items| items.iter().all(Value::is_object)) {
            return Err(AnalysisFailure::new(
                "malformed-response",
                "publishDiagnostics diagnostics must be an object list",
            ));
        }
        self.published_diagnostics.push(params);
        Ok(())
    }

    fn handle_server_request(&mut self, request: Request) -> Result<(), AnalysisFailure> {
        let id = request.id.clone();
        let method = request.method.clone();
        self.requests.incoming.register(id.clone(), method.clone());
        let result = match method.as_str() {
            "client/registerCapability"
            | "client/unregisterCapability"
            | "$/progress"
            | "window/workDoneProgress/create" => Some(Value::Null),
            "workspace/configuration" => {
                let count = request
                    .params
                    .get("items")
                    .and_then(Value::as_array)
                    .map_or(0, Vec::len);
                Some(Value::Array(vec![Value::Null; count]))
            }
            "workspace/workspaceFolders" => Some(json!([{
                "uri": file_uri(&self.root),
                "name": self.root.file_name().and_then(|name| name.to_str()).unwrap_or_default(),
            }])),
            "textDocument/publishDiagnostics" => {
                self.handle_notification(Notification::new(
                    method.clone(),
                    request.params.clone(),
                ))?;
                Some(Value::Null)
            }
            _ => None,
        };
        self.requests.incoming.complete(&id).ok_or_else(|| {
            AnalysisFailure::new(
                "protocol-violation",
                "LSP server request did not match an outstanding request",
            )
        })?;
        let response = match result {
            Some(value) => Response::new_ok(id, value),
            None => Response::new_err(
                id,
                ErrorCode::MethodNotFound as i32,
                format!("method not found: {method}"),
            ),
        };
        let stdin = self.stdin.as_mut().ok_or_else(|| {
            AnalysisFailure::new("protocol-violation", "LSP process is not running")
        })?;
        Message::Response(response)
            .write(stdin)
            .map_err(|_| AnalysisFailure::new("protocol-violation", "LSP JSON-RPC write failed"))
    }

    fn drain_notifications(&mut self) -> Result<(), AnalysisFailure> {
        let deadline = Instant::now() + self.timeout;
        let mut quiet_deadline = Instant::now() + NOTIFICATION_QUIET;
        loop {
            let now = Instant::now();
            if now >= quiet_deadline {
                return Ok(());
            }
            if now >= deadline {
                return Err(AnalysisFailure::new(
                    "request-timeout",
                    "LSP notifications did not become quiet",
                ));
            }
            let wait = quiet_deadline
                .saturating_duration_since(now)
                .min(deadline.saturating_duration_since(now))
                .min(Duration::from_millis(50));
            match self.events.recv_timeout(wait) {
                Ok(ReaderEvent::Message(Message::Notification(notification))) => {
                    quiet_deadline = Instant::now() + NOTIFICATION_QUIET;
                    self.handle_notification(notification)?;
                }
                Ok(ReaderEvent::Message(Message::Request(request))) => {
                    quiet_deadline = Instant::now() + NOTIFICATION_QUIET;
                    self.handle_server_request(request)?;
                }
                Ok(ReaderEvent::Message(Message::Response(response))) => {
                    if self
                        .requests
                        .outgoing
                        .complete(response.id.clone())
                        .is_none()
                    {
                        return Err(AnalysisFailure::new(
                            "protocol-violation",
                            "LSP response did not match an outstanding request",
                        ));
                    }
                    return Err(AnalysisFailure::new(
                        "protocol-violation",
                        "unexpected LSP response while draining notifications",
                    ));
                }
                Ok(ReaderEvent::Closed) => {
                    return Err(AnalysisFailure::new(
                        "protocol-violation",
                        "LSP server closed stdout",
                    ));
                }
                Ok(ReaderEvent::Failure(error)) => return Err(error),
                Err(RecvTimeoutError::Disconnected) => {
                    return Err(AnalysisFailure::new(
                        "protocol-violation",
                        "LSP message reader stopped",
                    ));
                }
                Err(RecvTimeoutError::Timeout) => {
                    if self.process_status()?.is_some() {
                        return Err(AnalysisFailure::new(
                            "protocol-violation",
                            "LSP server exited while draining notifications",
                        ));
                    }
                }
            }
        }
    }

    fn process_status(&mut self) -> Result<Option<ExitStatus>, AnalysisFailure> {
        self.child
            .as_mut()
            .ok_or_else(|| {
                AnalysisFailure::new("protocol-violation", "LSP process is not running")
            })?
            .try_wait()
            .map_err(|error| {
                AnalysisFailure::new(
                    "protocol-violation",
                    format!("unable to read LSP process status: {error}"),
                )
            })
    }

    fn finish(&mut self) -> Result<(), AnalysisFailure> {
        let mut failed = false;
        if self.process_status()?.is_none() {
            match self.request("shutdown", Value::Null) {
                Ok(_) => self.lifecycle.push("shutdown".to_owned()),
                Err(_) => failed = true,
            }
            if !failed && self.process_status()?.is_none() {
                self.notify("exit", Value::Null)?;
            }
        }
        if failed {
            self.stop_process();
        } else {
            let wait = self.timeout.min(CLEAN_EXIT_WAIT);
            let deadline = Instant::now() + wait;
            while self.process_status()?.is_none() {
                let now = Instant::now();
                if now >= deadline {
                    self.stop_process();
                    break;
                }
                thread::sleep(
                    deadline
                        .saturating_duration_since(now)
                        .min(Duration::from_millis(10)),
                );
            }
        }
        self.lifecycle.push("exit".to_owned());
        let status = self.wait_process()?;
        self.join_background_threads();
        self.finished = true;
        if !failed && !status.success() {
            return Err(AnalysisFailure::new(
                "server-exit-nonzero",
                format!(
                    "{} server exited with {}",
                    self.spec.language_id,
                    status.code().unwrap_or(-1)
                ),
            ));
        }
        Ok(())
    }

    fn stop_process(&mut self) {
        if let Some(child) = self.child.as_mut() {
            if child.try_wait().ok().flatten().is_none() {
                let _ = child.kill();
            }
            let _ = child.wait();
        }
    }

    fn wait_process(&mut self) -> Result<ExitStatus, AnalysisFailure> {
        self.child
            .as_mut()
            .ok_or_else(|| {
                AnalysisFailure::new("protocol-violation", "LSP process is not running")
            })?
            .wait()
            .map_err(|error| {
                AnalysisFailure::new(
                    "protocol-violation",
                    format!("unable to reap LSP process: {error}"),
                )
            })
    }

    fn join_background_threads(&mut self) {
        if let Some(thread) = self.reader_thread.take() {
            join_when_done(thread, &self.reader_done);
        }
        if let Some(thread) = self.stderr_thread.take() {
            join_when_done(thread, &self.stderr_done);
        }
    }
}

impl Drop for LspProcessSession {
    fn drop(&mut self) {
        if !self.finished {
            self.stop_process();
            self.join_background_threads();
            self.finished = true;
        }
    }
}

fn stop_child(child: &mut Child) {
    if child.try_wait().ok().flatten().is_none() {
        let _ = child.kill();
    }
    let _ = child.wait();
}

fn join_when_done(thread: JoinHandle<()>, done: &Receiver<()>) {
    if done.recv_timeout(THREAD_JOIN_WAIT).is_ok() {
        let _ = thread.join();
    }
}

fn read_lsp_messages(
    stdout: std::process::ChildStdout,
    sender: SyncSender<ReaderEvent>,
    done: SyncSender<()>,
) {
    let mut reader = BufReader::new(stdout);
    loop {
        match Message::read(&mut reader) {
            Ok(Some(message)) => {
                if sender.send(ReaderEvent::Message(message)).is_err() {
                    break;
                }
            }
            Ok(None) => {
                let _ = sender.send(ReaderEvent::Closed);
                break;
            }
            Err(error)
                if error.kind() == std::io::ErrorKind::InvalidData
                    && error.to_string().contains("malformed LSP payload") =>
            {
                // The old JSON-RPC reader discarded malformed payloads; the outstanding
                // request remains pending and resolves through its normal timeout.
                continue;
            }
            Err(error) => {
                let _ = sender.send(ReaderEvent::Failure(AnalysisFailure::new(
                    "protocol-violation",
                    format!("LSP JSON-RPC reader failed ({:?})", error.kind()),
                )));
                break;
            }
        }
    }
    let _ = done.send(());
}

fn drain_stderr(
    mut stderr: std::process::ChildStderr,
    buffer: Arc<Mutex<Vec<u8>>>,
    done: SyncSender<()>,
) {
    let mut chunk = [0u8; 4096];
    loop {
        match stderr.read(&mut chunk) {
            Ok(0) | Err(_) => break,
            Ok(count) => {
                let mut capture = buffer.lock().unwrap_or_else(|poison| poison.into_inner());
                let remaining = STDERR_LIMIT.saturating_sub(capture.len());
                if remaining > 0 {
                    capture.extend_from_slice(&chunk[..count.min(remaining)]);
                }
            }
        }
    }
    let _ = done.send(());
}

fn failed_report(
    root: &Path,
    files: Vec<String>,
    failure: AnalysisFailure,
    capabilities: BTreeMap<String, BTreeMap<String, String>>,
    servers: Vec<Value>,
    mut provenance: Value,
    mut lifecycle: Value,
) -> CodeAnalysisReport {
    if let Some(object) = lifecycle.as_object_mut() {
        object.insert("state".to_owned(), Value::String("failed".to_owned()));
    } else {
        lifecycle = json!({"state": "failed"});
    }
    if !provenance.is_object() {
        provenance = Value::Object(Map::new());
    }
    CodeAnalysisReport {
        root: root.to_path_buf(),
        files,
        servers,
        capabilities,
        symbols: Vec::new(),
        relations: Vec::new(),
        diagnostics: Vec::new(),
        lexical_candidates: Vec::new(),
        lifecycle,
        status: "failed".to_owned(),
        provenance,
        error: Some(failure.report_error()),
    }
}

pub fn analyze(
    root: &Path,
    files: &[PathBuf],
    overrides: &BTreeMap<LanguageId, LspServerSpec>,
    timeout: Duration,
) -> CodeAnalysisReport {
    let root = resolve_path(root);
    let mut resolved = BTreeMap::<String, PathBuf>::new();
    for raw_path in files {
        let candidate = if raw_path.is_absolute() {
            raw_path.clone()
        } else {
            root.join(raw_path)
        };
        if has_symlink_component(&candidate, &root)
            || fs::symlink_metadata(&candidate)
                .is_ok_and(|metadata| metadata.file_type().is_symlink())
        {
            return failed_report(
                &root,
                Vec::new(),
                AnalysisFailure::new(
                    "path-escape",
                    format!(
                        "noncanonical or symlink file path is not allowed: {}",
                        candidate.display()
                    ),
                ),
                BTreeMap::new(),
                Vec::new(),
                Value::Object(Map::new()),
                Value::Object(Map::new()),
            );
        }
        let path = match resolve_weakly(&candidate) {
            Ok(path) => path,
            Err(error) => {
                return failed_report(
                    &root,
                    Vec::new(),
                    AnalysisFailure::new("server-unavailable", error.to_string()),
                    BTreeMap::new(),
                    Vec::new(),
                    Value::Object(Map::new()),
                    Value::Object(Map::new()),
                );
            }
        };
        let Some(relative) = relative_to_root(&root, &path) else {
            return failed_report(
                &root,
                Vec::new(),
                AnalysisFailure::new("path-escape", path_as_posix(&path)),
                BTreeMap::new(),
                Vec::new(),
                Value::Object(Map::new()),
                Value::Object(Map::new()),
            );
        };
        if !fs::metadata(&path).is_ok_and(|metadata| metadata.is_file()) {
            return failed_report(
                &root,
                Vec::new(),
                AnalysisFailure::new(
                    "server-unavailable",
                    format!("file not found: {}", path.display()),
                ),
                BTreeMap::new(),
                Vec::new(),
                Value::Object(Map::new()),
                Value::Object(Map::new()),
            );
        }
        resolved.insert(relative, path);
    }

    let file_locators = resolved.keys().cloned().collect::<Vec<_>>();
    let resolved_files = resolved.into_values().collect::<Vec<_>>();
    let mut symbols = Vec::new();
    let mut relations = Vec::new();
    let mut diagnostics = Vec::new();
    let mut capabilities = BTreeMap::<String, BTreeMap<String, String>>::new();
    let mut servers = Vec::<Value>::new();
    let mut lifecycle = json!({
        "state": "created",
        "encoding": "utf-16",
        "protocol": LSP_VERSION,
    });
    let mut provenance = json!({
        "schema": SCHEMA_VERSION,
        "protocol": LSP_VERSION,
        "files": file_locators,
    });

    let analysis = (|| -> Result<(), AnalysisFailure> {
        let languages = resolved_files
            .iter()
            .filter_map(|path| language_for_path(path))
            .collect::<BTreeSet<_>>();
        for language in languages {
            let language_files = resolved_files
                .iter()
                .filter(|path| language_for_path(path) == Some(language))
                .cloned()
                .collect::<Vec<_>>();
            let spec = match overrides.get(&language) {
                Some(spec) => spec.clone(),
                None => LspServerSpec::for_language(language, &root)
                    .map_err(|error| AnalysisFailure::new(error.code, error.message))?,
            };
            let server_index = servers.len();
            servers.push(spec.as_json());
            let mut session = LspProcessSession::start(spec.clone(), &root, timeout)?;
            session.lifecycle.push("initialize(sent)".to_owned());
            let initialize = session.request(
                "initialize",
                json!({
                    "processId": std::process::id(),
                    "rootUri": file_uri(&root),
                    "workspaceFolders": [{"uri": file_uri(&root), "name": root.file_name().and_then(|name| name.to_str()).unwrap_or_default()}],
                    "capabilities": {},
                    "clientInfo": {"name": "agent-canon", "version": SCHEMA_VERSION},
                }),
            )?;
            let initialize = initialize.as_object().ok_or_else(|| {
                AnalysisFailure::new("malformed-response", "initialize result is not an object")
            })?;
            let empty_capabilities = Map::new();
            let caps = match initialize.get("capabilities") {
                None => &empty_capabilities,
                Some(value) => value.as_object().ok_or_else(|| {
                    AnalysisFailure::new(
                        "malformed-response",
                        "initialize capabilities is not an object",
                    )
                })?,
            };
            if let Some(server_info) = initialize.get("serverInfo").and_then(Value::as_object) {
                let server_version = server_info
                    .get("version")
                    .map(|value| {
                        value
                            .as_str()
                            .map(ToOwned::to_owned)
                            .unwrap_or_else(|| value.to_string())
                    })
                    .unwrap_or_default();
                if let Some(server) = servers.get_mut(server_index).and_then(Value::as_object_mut) {
                    server.insert(
                        "version".to_owned(),
                        Value::String(if spec.version.is_empty() {
                            server_version
                        } else {
                            spec.version.clone()
                        }),
                    );
                }
            }
            let matrix = CapabilityMatrix::from_initialize(caps);
            if !matrix.document_symbols {
                return Err(AnalysisFailure::new(
                    "capability-unavailable",
                    format!("{} server lacks documentSymbolProvider", language.as_str()),
                ));
            }
            capabilities.insert(language.as_str().to_owned(), matrix.as_json());
            session.notify("initialized", json!({}))?;
            session.lifecycle.push("initialized".to_owned());

            for path in language_files {
                let uri = file_uri(&path);
                let relative =
                    relative_to_root(&root, &path).unwrap_or_else(|| path_as_posix(&path));
                let text = fs::read_to_string(&path).map_err(|_| {
                    AnalysisFailure::new(
                        "malformed-response",
                        format!("unable to read source file {relative}"),
                    )
                })?;
                let text = normalize_python_newlines(&text);
                let open_close = caps
                    .get("textDocumentSync")
                    .and_then(Value::as_object)
                    .and_then(|sync| sync.get("openClose"))
                    .is_some_and(json_truthy_value);
                if open_close {
                    session.notify(
                        "textDocument/didOpen",
                        json!({"textDocument": {"uri": uri, "languageId": language.as_str(), "version": 1, "text": text}}),
                    )?;
                    session.lifecycle.push(format!("didOpen:{relative}"));
                }
                let raw_symbols = session.request(
                    "textDocument/documentSymbol",
                    json!({"textDocument": {"uri": uri}}),
                )?;
                session.lifecycle.push(format!("documentSymbol:{relative}"));
                let file_symbols = flatten_symbols(&raw_symbols, &uri)?;
                for symbol in &file_symbols {
                    uri_path(&root, &symbol.uri)?;
                }
                symbols.extend(file_symbols);

                if matrix.definitions {
                    for candidate in lexical_candidates(&root, std::slice::from_ref(&path)) {
                        let position = candidate
                            .position
                            .clone()
                            .unwrap_or(Position {
                                line: 0,
                                character: 0,
                            })
                            .as_json();
                        let mut raw_definition = session.request(
                            "textDocument/definition",
                            json!({
                                "textDocument": {"uri": uri},
                                "position": position,
                            }),
                        )?;
                        if raw_definition.is_null() {
                            raw_definition = Value::Array(Vec::new());
                        } else if raw_definition.is_object() {
                            raw_definition = Value::Array(vec![raw_definition]);
                        }
                        let locations = raw_definition.as_array().ok_or_else(|| {
                            AnalysisFailure::new(
                                "malformed-response",
                                "definition response must be a location list",
                            )
                        })?;
                        for item in locations {
                            if !item.is_object() {
                                return Err(AnalysisFailure::new(
                                    "malformed-response",
                                    "definition response contains a non-object",
                                ));
                            }
                            let (target, position) = location(item, &root)?;
                            relations.push(CodeRelation {
                                orientation: "definition".to_owned(),
                                source: candidate.source.clone(),
                                target,
                                position: Some(position),
                            });
                        }
                    }
                }
                if matrix.references {
                    for symbol in symbols.iter().filter(|symbol| symbol.uri == uri) {
                        let raw_references = session.request(
                            "textDocument/references",
                            json!({
                                "textDocument": {"uri": uri},
                                "position": symbol.selection_range.start.as_json(),
                                "context": {"includeDeclaration": true},
                            }),
                        )?;
                        let references = if raw_references.is_null() {
                            &[][..]
                        } else {
                            raw_references.as_array().ok_or_else(|| {
                                AnalysisFailure::new(
                                    "malformed-response",
                                    "references response must be a location list",
                                )
                            })?
                        };
                        for item in references {
                            if !item.is_object() {
                                return Err(AnalysisFailure::new(
                                    "malformed-response",
                                    "references response contains a non-object",
                                ));
                            }
                            let (target, position) = location(item, &root)?;
                            relations.push(CodeRelation {
                                orientation: "reference".to_owned(),
                                source: relative.clone(),
                                target,
                                position: Some(position),
                            });
                        }
                    }
                }

                session.drain_notifications()?;
                if matrix.diagnostics
                    && caps
                        .get("diagnosticProvider")
                        .is_some_and(json_truthy_value)
                {
                    let raw = session.request(
                        "textDocument/diagnostic",
                        json!({"textDocument": {"uri": uri}}),
                    )?;
                    let object = raw.as_object().ok_or_else(|| {
                        AnalysisFailure::new(
                            "malformed-response",
                            "pull diagnostics result must contain an items list",
                        )
                    })?;
                    let items = object
                        .get("items")
                        .and_then(Value::as_array)
                        .ok_or_else(|| {
                            AnalysisFailure::new(
                                "malformed-response",
                                "pull diagnostics result must contain an items list",
                            )
                        })?;
                    for item in items {
                        diagnostics.push(diagnostic(item, &uri)?);
                    }
                } else if !session.published_diagnostics.is_empty() {
                    if let Some(matrix) = capabilities.get_mut(language.as_str()) {
                        matrix.insert("diagnostics".to_owned(), "supported_empty".to_owned());
                    }
                    for published in &session.published_diagnostics {
                        let Some(object) = published.as_object() else {
                            continue;
                        };
                        if object.get("uri").and_then(Value::as_str) != Some(&uri) {
                            continue;
                        }
                        let items = object
                            .get("diagnostics")
                            .and_then(Value::as_array)
                            .ok_or_else(|| {
                                AnalysisFailure::new(
                                    "malformed-response",
                                    "push diagnostics must contain an object list",
                                )
                            })?;
                        for item in items {
                            diagnostics.push(diagnostic(item, &uri)?);
                        }
                    }
                }

                if matrix.call_hierarchy {
                    let file_symbols = symbols
                        .iter()
                        .filter(|symbol| symbol.uri == uri)
                        .cloned()
                        .collect::<Vec<_>>();
                    for symbol in file_symbols {
                        let start = symbol.selection_range.start.clone();
                        let prepared = session.request(
                            "textDocument/prepareCallHierarchy",
                            json!({
                                "textDocument": {"uri": uri},
                                "position": start.as_json(),
                            }),
                        )?;
                        let prepared_items = if prepared.is_null() {
                            &[][..]
                        } else {
                            prepared.as_array().ok_or_else(|| {
                                AnalysisFailure::new(
                                    "malformed-response",
                                    "call hierarchy prepare response must be a list",
                                )
                            })?
                        };
                        for item in prepared_items {
                            let object = item.as_object().ok_or_else(|| {
                                AnalysisFailure::new(
                                    "malformed-response",
                                    "call hierarchy item is malformed",
                                )
                            })?;
                            if !object.get("name").is_some_and(Value::is_string) {
                                return Err(AnalysisFailure::new(
                                    "malformed-response",
                                    "call hierarchy item is malformed",
                                ));
                            }
                            let item_uri = match object.get("uri") {
                                None => uri.as_str(),
                                Some(Value::String(value)) => value.as_str(),
                                Some(_) => {
                                    return Err(AnalysisFailure::new(
                                        "malformed-response",
                                        "call hierarchy item URI is malformed",
                                    ));
                                }
                            };
                            let selection_start = object
                                .get("selectionRange")
                                .and_then(Value::as_object)
                                .map(|range| position(range.get("start")))
                                .transpose()?
                                .unwrap_or_else(|| start.clone());
                            for (method, orientation) in [
                                ("callHierarchy/incomingCalls", "call-incoming"),
                                ("callHierarchy/outgoingCalls", "call-outgoing"),
                            ] {
                                let calls = session.request(method, json!({"item": item}))?;
                                let calls = if calls.is_null() {
                                    &[][..]
                                } else {
                                    calls.as_array().ok_or_else(|| {
                                        AnalysisFailure::new(
                                            "malformed-response",
                                            "call hierarchy response must be a list",
                                        )
                                    })?
                                };
                                for call in calls {
                                    let call = call.as_object().ok_or_else(|| {
                                        AnalysisFailure::new(
                                            "malformed-response",
                                            "call hierarchy call is malformed",
                                        )
                                    })?;
                                    let other_field = if orientation == "call-incoming" {
                                        "from"
                                    } else {
                                        "to"
                                    };
                                    let other = call
                                        .get(other_field)
                                        .and_then(Value::as_object)
                                        .ok_or_else(|| {
                                            AnalysisFailure::new(
                                                "malformed-response",
                                                "call hierarchy endpoint is malformed",
                                            )
                                        })?;
                                    let other_uri = match other.get("uri") {
                                        None => uri.as_str(),
                                        Some(Value::String(value)) => value.as_str(),
                                        Some(_) => {
                                            return Err(AnalysisFailure::new(
                                                "malformed-response",
                                                "call hierarchy endpoint URI is malformed",
                                            ));
                                        }
                                    };
                                    let mut source = uri_path(&root, item_uri)?;
                                    let mut target = uri_path(&root, other_uri)?;
                                    if orientation == "call-incoming" {
                                        std::mem::swap(&mut source, &mut target);
                                    }
                                    relations.push(CodeRelation {
                                        orientation: orientation.to_owned(),
                                        source,
                                        target,
                                        position: Some(selection_start.clone()),
                                    });
                                }
                            }
                        }
                    }
                }
                if open_close {
                    session.notify(
                        "textDocument/didClose",
                        json!({"textDocument": {"uri": uri}}),
                    )?;
                    session.lifecycle.push(format!("didClose:{relative}"));
                }
            }
            session.finish()?;
            if let Some(object) = lifecycle.as_object_mut() {
                object.insert(
                    language.as_str().to_owned(),
                    Value::Array(
                        session
                            .lifecycle
                            .iter()
                            .cloned()
                            .map(Value::String)
                            .collect(),
                    ),
                );
            }
            if let Some(object) = provenance.as_object_mut() {
                object.insert(
                    language.as_str().to_owned(),
                    json!({
                        "record": spec.record_id,
                        "command": spec.command,
                        "version": spec.version,
                        "resolution": spec.resolution,
                        "verificationOutput": spec.verification_output,
                        "requestIds": session.request_count,
                    }),
                );
            }
        }
        if let Some(object) = lifecycle.as_object_mut() {
            object.insert("state".to_owned(), Value::String("complete".to_owned()));
        }
        Ok(())
    })();

    if let Err(failure) = analysis {
        return failed_report(
            &root,
            file_locators,
            failure,
            capabilities,
            servers,
            provenance,
            lifecycle,
        );
    }
    let lexical_candidates = lexical_candidates(&root, &resolved_files);
    CodeAnalysisReport {
        root,
        files: file_locators,
        servers,
        capabilities,
        symbols: unique_symbols(symbols),
        relations: unique_relations(relations),
        diagnostics: unique_diagnostics(diagnostics),
        lexical_candidates: unique_lexical_candidates(lexical_candidates),
        lifecycle,
        status: "complete".to_owned(),
        provenance,
        error: None,
    }
}

fn symbol_from(raw: &Value, uri: &str) -> Result<CodeSymbol, AnalysisFailure> {
    let object = raw.as_object().ok_or_else(|| {
        AnalysisFailure::new(
            "malformed-response",
            "documentSymbol response contains a non-object",
        )
    })?;
    let name = object
        .get("name")
        .and_then(Value::as_str)
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "symbol name must be a string"))?
        .to_owned();
    let kind = object
        .get("kind")
        .and_then(Value::as_u64)
        .filter(|kind| (1..=26).contains(kind))
        .ok_or_else(|| {
            AnalysisFailure::new(
                "malformed-response",
                "symbol kind must be an LSP SymbolKind integer",
            )
        })?;
    let range = lsp_range(object.get("range"))?;
    let selection_range = object
        .get("selectionRange")
        .filter(|value| value.is_object())
        .or_else(|| object.get("range"));
    let selection_range = lsp_range(selection_range)?;
    let container_value = object
        .get("containerName")
        .or_else(|| object.get("container"));
    let container = match container_value {
        None | Some(Value::Null) => None,
        Some(Value::String(value)) => Some(value.clone()),
        Some(_) => {
            return Err(AnalysisFailure::new(
                "malformed-response",
                "symbol container must be a string",
            ));
        }
    };
    Ok(CodeSymbol {
        uri: uri.to_owned(),
        name,
        kind,
        range,
        selection_range,
        container,
    })
}

fn flatten_symbols(raw: &Value, uri: &str) -> Result<Vec<CodeSymbol>, AnalysisFailure> {
    let items = raw.as_array().ok_or_else(|| {
        AnalysisFailure::new(
            "malformed-response",
            "documentSymbol response must be a list",
        )
    })?;
    let mut pending = items.iter().rev().collect::<Vec<_>>();
    let mut symbols = Vec::new();
    while let Some(item) = pending.pop() {
        let object = item.as_object().ok_or_else(|| {
            AnalysisFailure::new(
                "malformed-response",
                "documentSymbol response contains a non-object",
            )
        })?;
        if let Some(location) = object.get("location").and_then(Value::as_object) {
            let location_uri = match location.get("uri") {
                None => uri.to_owned(),
                Some(Value::String(value)) => value.clone(),
                Some(value) => value.to_string(),
            };
            let mut symbol = item.clone();
            let symbol_object = symbol.as_object_mut().expect("symbol object was checked");
            symbol_object.insert(
                "range".to_owned(),
                location.get("range").cloned().unwrap_or(Value::Null),
            );
            symbol_object.insert(
                "selectionRange".to_owned(),
                location.get("range").cloned().unwrap_or(Value::Null),
            );
            symbols.push(symbol_from(&symbol, &location_uri)?);
        } else {
            symbols.push(symbol_from(item, uri)?);
            let children = object
                .get("children")
                .map(|value| {
                    value.as_array().ok_or_else(|| {
                        AnalysisFailure::new(
                            "malformed-response",
                            "documentSymbol response must be a list",
                        )
                    })
                })
                .transpose()?
                .map(Vec::as_slice)
                .unwrap_or(&[]);
            pending.extend(children.iter().rev());
        }
    }
    Ok(symbols)
}

fn location(value: &Value, root: &Path) -> Result<(String, Position), AnalysisFailure> {
    let object = value
        .as_object()
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "location must be an object"))?;
    let uri = object
        .get("uri")
        .filter(|uri| json_truthy(Some(*uri)))
        .or_else(|| object.get("targetUri"))
        .and_then(Value::as_str)
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "location has no URI"))?;
    let range = object
        .get("range")
        .filter(|range| json_truthy(Some(*range)))
        .or_else(|| object.get("targetSelectionRange"))
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "location has no range"))?;
    let range = range
        .as_object()
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "location has no range"))?;
    Ok((uri_path(root, uri)?, position(range.get("start"))?))
}

fn diagnostic(raw: &Value, uri: &str) -> Result<CodeDiagnostic, AnalysisFailure> {
    let object = raw.as_object().ok_or_else(|| {
        AnalysisFailure::new("malformed-response", "diagnostic must be an object")
    })?;
    let severity = match object.get("severity") {
        None | Some(Value::Null) => None,
        Some(value) => {
            let severity = value
                .as_u64()
                .filter(|value| (1..=4).contains(value))
                .ok_or_else(|| {
                    AnalysisFailure::new(
                        "malformed-response",
                        "diagnostic severity must be an LSP integer 1..4",
                    )
                })?;
            Some(severity)
        }
    };
    let code = match object.get("code") {
        None | Some(Value::Null) => None,
        Some(Value::String(value)) => Some(Value::String(value.clone())),
        Some(Value::Number(value)) if value.is_i64() || value.is_u64() => {
            Some(Value::Number(value.clone()))
        }
        Some(_) => {
            return Err(AnalysisFailure::new(
                "malformed-response",
                "diagnostic code must be a string or integer",
            ));
        }
    };
    let source = match object.get("source") {
        None | Some(Value::Null) => None,
        Some(Value::String(value)) => Some(value.clone()),
        Some(_) => {
            return Err(AnalysisFailure::new(
                "malformed-response",
                "diagnostic source must be a string",
            ));
        }
    };
    let version = match object.get("version") {
        None | Some(Value::Null) => None,
        Some(value) => Some(value.as_u64().ok_or_else(|| {
            AnalysisFailure::new(
                "malformed-response",
                "diagnostic version must be a non-negative integer",
            )
        })?),
    };
    let message = object
        .get("message")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            AnalysisFailure::new("malformed-response", "diagnostic message must be a string")
        })?
        .to_owned();
    Ok(CodeDiagnostic {
        uri: uri.to_owned(),
        range: lsp_range(object.get("range"))?,
        severity,
        code,
        message,
        source,
        version,
    })
}

fn utf16_position(source: &str, byte_offset: usize) -> Position {
    let byte_offset = byte_offset.min(source.len());
    let line = line_at_offset(source, byte_offset).saturating_sub(1) as u64;
    let line_start = source[..byte_offset]
        .rfind('\n')
        .map(|offset| offset + 1)
        .unwrap_or(0);
    let prefix = &source[line_start..byte_offset];
    Position {
        line,
        character: prefix.encode_utf16().count() as u64,
    }
}

fn python_splitlines(source: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut line_start = 0;
    let mut characters = source.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        let end = if character == '\r' {
            if characters.peek().is_some_and(|(_, next)| *next == '\n') {
                let (newline_index, newline) = characters.next().expect("peeked newline");
                newline_index + newline.len_utf8()
            } else {
                index + character.len_utf8()
            }
        } else if matches!(
            character,
            '\n' | '\u{000b}'
                | '\u{000c}'
                | '\u{001c}'
                | '\u{001d}'
                | '\u{001e}'
                | '\u{0085}'
                | '\u{2028}'
                | '\u{2029}'
        ) {
            index + character.len_utf8()
        } else {
            continue;
        };
        lines.push(&source[line_start..index]);
        line_start = end;
    }
    if line_start < source.len() {
        lines.push(&source[line_start..]);
    }
    lines
}

struct PythonImportVisitor<'a> {
    root: &'a Path,
    source_path: &'a Path,
    source_name: &'a str,
    source_text: &'a str,
    candidates: Vec<LexicalDependencyCandidate>,
}

impl PythonImportVisitor<'_> {
    fn push_import(&mut self, token: String, byte_offset: usize, legacy_kind: &'static str) {
        self.candidates.push(LexicalDependencyCandidate {
            source: self.source_name.to_owned(),
            target: resolve_lexical_target(self.root, self.source_path, "python", &token),
            token,
            position: Some(utf16_position(self.source_text, byte_offset)),
            legacy_kind: Some(legacy_kind),
        });
    }
}

impl Visitor for PythonImportVisitor<'_> {
    fn visit_stmt_import(&mut self, node: ast::StmtImport) {
        for alias in &node.names {
            self.push_import(
                alias.name.as_str().to_owned(),
                alias.start().to_usize(),
                "import",
            );
        }
        self.generic_visit_stmt_import(node);
    }

    fn visit_stmt_import_from(&mut self, node: ast::StmtImportFrom) {
        let level = node.level.map(|level| level.to_usize()).unwrap_or(0);
        let module = node
            .module
            .as_ref()
            .map(|value| value.as_str())
            .unwrap_or("");
        if level == 0 && module.is_empty() {
            self.generic_visit_stmt_import_from(node);
            return;
        }
        let module_token = format!("{}{}", ".".repeat(level), module);
        let statement_offset = node.start().to_usize();
        let line_start = self.source_text[..statement_offset.min(self.source_text.len())]
            .rfind('\n')
            .map(|offset| offset + 1)
            .unwrap_or(0);
        let line_number = line_at_offset(self.source_text, statement_offset).saturating_sub(1);
        let source_lines = python_splitlines(self.source_text);
        let line = source_lines.get(line_number).copied().unwrap_or_default();
        let from_character = line
            .find("from")
            .map(|byte_offset| line[..byte_offset].chars().count());
        let search_character = from_character.map(|value| value + 4).unwrap_or(3);
        let search_byte = line
            .char_indices()
            .nth(search_character)
            .map(|(byte_offset, _)| byte_offset)
            .unwrap_or(line.len());
        let module_offset = line[search_byte..]
            .find(&module_token)
            .map(|offset| line_start + search_byte + offset)
            .unwrap_or(statement_offset);
        self.push_import(module_token.clone(), module_offset, "import");
        for alias in &node.names {
            let name = alias.name.as_str();
            if name == "*" {
                continue;
            }
            let token = if module_token.is_empty() {
                name.to_owned()
            } else {
                let separator = if module_token.ends_with('.') { "" } else { "." };
                format!("{module_token}{separator}{name}")
            };
            self.push_import(token, alias.start().to_usize(), "from-import-symbol");
        }
        self.generic_visit_stmt_import_from(node);
    }
}

fn lexical_candidates(root: &Path, files: &[PathBuf]) -> Vec<LexicalDependencyCandidate> {
    static PATTERNS: std::sync::OnceLock<Vec<Regex>> = std::sync::OnceLock::new();
    let patterns = PATTERNS.get_or_init(|| {
        [
            r"^\s*from\s+([.]+)\s+import\s+([A-Za-z_]\w*)",
            r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)",
            r"^\s*(?:source|\.)\s+([^\s#]+)",
            r#"^\s*#\s*include\s*[<"]([^>"]+)[>"]"#,
            r"^\s*(?:mod|use)\s+([A-Za-z_][\w:]*)",
        ]
        .into_iter()
        .map(|pattern| Regex::new(pattern).expect("fixed lexical dependency pattern"))
        .collect()
    });
    let mut results = Vec::new();
    for path in files {
        let Ok(text) = fs::read_to_string(path) else {
            continue;
        };
        let source_text = normalize_python_newlines(&text);
        let Some(source) = relative_to_root(root, path) else {
            continue;
        };
        let language = language_for_path(path);
        if language == Some(LanguageId::Python) {
            if let Ok(suite) = ast::Suite::parse(&source_text, &source) {
                let mut visitor = PythonImportVisitor {
                    root,
                    source_path: path,
                    source_name: &source,
                    source_text: &source_text,
                    candidates: Vec::new(),
                };
                for statement in suite {
                    visitor.visit_stmt(statement);
                }
                results.extend(visitor.candidates);
                continue;
            }
        }
        for (line_number, line) in python_splitlines(&source_text).iter().enumerate() {
            let Some(captures) = patterns.iter().find_map(|pattern| pattern.captures(line)) else {
                continue;
            };
            let token = if let Some(second) = captures.get(2) {
                format!(
                    "{}{}",
                    captures.get(1).map_or("", |value| value.as_str()),
                    second.as_str()
                )
            } else {
                captures
                    .get(1)
                    .map(|value| value.as_str())
                    .unwrap_or_default()
                    .to_owned()
            };
            let language_name = language.map(LanguageId::as_str).unwrap_or("unknown");
            let target = if token.starts_with('/')
                || (token.starts_with('.') && language != Some(LanguageId::Python))
            {
                let candidate = if Path::new(&token).is_absolute() {
                    PathBuf::from(&token)
                } else {
                    path.parent().unwrap_or(root).join(&token)
                };
                resolve_weakly(&candidate)
                    .ok()
                    .and_then(|resolved| relative_to_root(root, &resolved))
                    .unwrap_or_else(|| format!("external:unknown:{token}"))
            } else {
                resolve_lexical_target(root, path, language_name, &token)
            };
            let column = line.find(&token).unwrap_or(0);
            results.push(LexicalDependencyCandidate {
                source: source.clone(),
                token,
                target,
                position: Some(Position {
                    line: line_number as u64,
                    character: line[..column].encode_utf16().count() as u64,
                }),
                legacy_kind: None,
            });
        }
    }
    unique_lexical_candidates(results)
}

fn resolve_lexical_target(root: &Path, source: &Path, language: &str, token: &str) -> String {
    let mut candidates = Vec::new();
    if language == "python" {
        let module = token.trim_start_matches('.').replace('.', "/");
        let mut base = if token.starts_with('.') {
            source.parent().unwrap_or(root).to_path_buf()
        } else {
            root.to_path_buf()
        };
        if token.starts_with('.') {
            for _ in 0..token
                .chars()
                .take_while(|character| *character == '.')
                .count()
                .saturating_sub(1)
            {
                base.pop();
            }
        }
        candidates.push(base.join(format!("{module}.py")));
        candidates.push(base.join(&module).join("__init__.py"));
    } else if matches!(language, "c" | "cpp") {
        candidates.push(source.parent().unwrap_or(root).join(token));
        candidates.push(root.join(token));
    } else if language == "rust" {
        let module = token.split("::").next().unwrap_or(token);
        let parent = source.parent().unwrap_or(root);
        candidates.push(parent.join(format!("{module}.rs")));
        candidates.push(parent.join(module).join("mod.rs"));
        candidates.push(root.join(format!("{module}.rs")));
    }
    for candidate in candidates {
        if fs::metadata(&candidate).is_ok_and(|metadata| metadata.is_file()) {
            if let Ok(resolved) = resolve_weakly(&candidate) {
                if let Some(relative) = relative_to_root(root, &resolved) {
                    return relative;
                }
            }
            break;
        }
    }
    format!("external:{language}:{token}")
}

fn unique_lexical_candidates(
    items: impl IntoIterator<Item = LexicalDependencyCandidate>,
) -> Vec<LexicalDependencyCandidate> {
    let mut seen = HashSet::new();
    let mut result = Vec::new();
    for item in items {
        if seen.insert(item.as_json().to_string()) {
            result.push(item);
        }
    }
    result.sort_by(|left, right| {
        (
            &left.source,
            position_json_sort_key(left.position.as_ref()),
            &left.token,
            &left.target,
        )
            .cmp(&(
                &right.source,
                position_json_sort_key(right.position.as_ref()),
                &right.token,
                &right.target,
            ))
    });
    result
}

struct CliOptions {
    root: PathBuf,
    files: Option<Vec<PathBuf>>,
    servers: Vec<String>,
    timeout: Duration,
    json: bool,
}

enum ParsedCli {
    Help,
    Analyze(CliOptions),
}

/// Run the single point-analysis CLI command.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_cli(args) {
        Ok(ParsedCli::Help) => {
            println!("{}", help_text());
            return 0;
        }
        Ok(ParsedCli::Analyze(options)) => options,
        Err(error) => return argument_error(&error),
    };
    let root = resolve_path(&options.root);
    let files = match options.files {
        Some(files) => files,
        None => match discover_lsp_files(&root, &[], &[]) {
            Ok(files) => files,
            Err(error) => {
                let report = failed_report(
                    &root,
                    Vec::new(),
                    AnalysisFailure::new(error.code, error.message),
                    BTreeMap::new(),
                    Vec::new(),
                    Value::Object(Map::new()),
                    Value::Object(Map::new()),
                );
                return render_cli_report(&report, &root, options.json);
            }
        },
    };
    let specs = match parse_server_specs(&options.servers) {
        Ok(specs) => specs,
        Err(error) => {
            eprintln!("LSP_ANALYSIS=fail\nLSP_ANALYSIS_ERROR={error}");
            return 2;
        }
    };
    let report = analyze(&root, &files, &specs, options.timeout);
    render_cli_report(&report, &root, options.json)
}

fn render_cli_report(report: &CodeAnalysisReport, root: &Path, json_output: bool) -> i32 {
    if json_output {
        match serde_json::to_string_pretty(&report.as_json(root)) {
            Ok(payload) => println!("{payload}"),
            Err(error) => {
                eprintln!("LSP_ANALYSIS=fail\nLSP_ANALYSIS_ERROR=serialization:{error}");
                return 1;
            }
        }
    } else {
        println!("AGENT_ANALYSIS={}", report.status);
        if let Some(error) = &report.error {
            println!("AGENT_ANALYSIS_ERROR={}:{}", error.code, error.message);
        }
    }
    if report.status == "complete" {
        0
    } else {
        1
    }
}

fn parse_server_specs(values: &[String]) -> Result<BTreeMap<LanguageId, LspServerSpec>, String> {
    let mut specs = BTreeMap::new();
    for value in values {
        let (language_name, command) = value
            .split_once('=')
            .ok_or_else(|| "--server must be LANGUAGE=COMMAND".to_owned())?;
        let command = shell_words(command)?;
        let Some(executable) = command.first() else {
            return Err("custom --server executable must be an absolute path".to_owned());
        };
        if !Path::new(executable).is_absolute() {
            return Err("custom --server executable must be an absolute path".to_owned());
        }
        let Some(language) = language_id(language_name) else {
            // Python accepted absolute overrides for unrecognized languages
            // and never used them because no suffix maps to such a key.
            continue;
        };
        let spec =
            LspServerSpec::caller_override(language, command).map_err(|error| error.message)?;
        specs.insert(language, spec);
    }
    Ok(specs)
}

fn language_id(value: &str) -> Option<LanguageId> {
    match value {
        "c" => Some(LanguageId::C),
        "cpp" => Some(LanguageId::Cpp),
        "python" => Some(LanguageId::Python),
        "rust" => Some(LanguageId::Rust),
        "shellscript" => Some(LanguageId::Shellscript),
        _ => None,
    }
}

fn shell_words(value: &str) -> Result<Vec<String>, String> {
    let mut words = Vec::new();
    let mut current = String::new();
    let mut chars = value.chars().peekable();
    let mut quote = None;
    let mut started = false;
    while let Some(character) = chars.next() {
        match quote {
            Some('\'') => {
                if character == '\'' {
                    quote = None;
                } else {
                    current.push(character);
                }
            }
            Some('"') => match character {
                '"' => quote = None,
                '\\' => {
                    let Some(next) = chars.next() else {
                        return Err("No escaped character".to_owned());
                    };
                    if next == '"' {
                        current.push(next);
                    } else {
                        current.push('\\');
                        current.push(next);
                    }
                }
                _ => current.push(character),
            },
            Some(_) => unreachable!("quote state is set only to a single or double quote"),
            None => match character {
                '\'' | '"' => {
                    quote = Some(character);
                    started = true;
                }
                '\\' => {
                    let Some(next) = chars.next() else {
                        return Err("No escaped character".to_owned());
                    };
                    if next != '\n' {
                        current.push(next);
                    }
                    started = true;
                }
                character if character.is_whitespace() => {
                    if started {
                        words.push(std::mem::take(&mut current));
                        started = false;
                    }
                }
                _ => {
                    current.push(character);
                    started = true;
                }
            },
        }
    }
    if quote.is_some() {
        return Err("No closing quotation".to_owned());
    }
    if started {
        words.push(current);
    }
    Ok(words)
}

fn parse_cli(args: &[String]) -> Result<ParsedCli, String> {
    if args.is_empty() {
        return Err("the following arguments are required: command".to_owned());
    }
    if matches!(args[0].as_str(), "-h" | "--help") {
        return Ok(ParsedCli::Help);
    }
    if args[0] != "analyze" {
        return Err(format!(
            "argument command: invalid choice: '{}' (choose from 'analyze')",
            args[0]
        ));
    }
    let mut root = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut files = None;
    let mut servers = Vec::new();
    let mut timeout = DEFAULT_TIMEOUT;
    let mut json_output = true;
    let mut unknown = Vec::new();
    let mut index = 1;
    let mut positional_only = false;
    while index < args.len() {
        let argument = &args[index];
        if !positional_only && matches!(argument.as_str(), "-h" | "--help") {
            return Ok(ParsedCli::Help);
        }
        if !positional_only && argument == "--" {
            positional_only = true;
            index += 1;
            continue;
        }
        if !positional_only && argument.starts_with('-') {
            let (name, inline_value) = argument
                .split_once('=')
                .map_or((argument.as_str(), None), |(name, value)| {
                    (name, Some(value))
                });
            match name {
                "--root" | "--server" | "--timeout" | "--format" => {
                    let value = match inline_value {
                        Some(value) => value.to_owned(),
                        None => {
                            let next = args
                                .get(index + 1)
                                .ok_or_else(|| format!("argument {name}: expected one argument"))?;
                            if next.starts_with('-') && next != "-" {
                                return Err(format!("argument {name}: expected one argument"));
                            }
                            index += 1;
                            next.clone()
                        }
                    };
                    match name {
                        "--root" => root = PathBuf::from(value),
                        "--server" => servers.push(value),
                        "--timeout" => {
                            let seconds = value.parse::<f64>().map_err(|_| {
                                format!("argument --timeout: invalid float value: '{value}'")
                            })?;
                            timeout =
                                Duration::try_from_secs_f64(seconds).unwrap_or(Duration::ZERO);
                        }
                        "--format" => {
                            json_output = match value.as_str() {
                                "json" => true,
                                "text" => false,
                                _ => {
                                    return Err(format!(
                                        "argument --format: invalid choice: '{value}' (choose from 'json', 'text')"
                                    ));
                                }
                            };
                        }
                        _ => unreachable!(),
                    }
                }
                "--files" => {
                    let mut selected = Vec::new();
                    if let Some(value) = inline_value {
                        selected.push(value.to_owned());
                    }
                    while let Some(value) = args.get(index + 1) {
                        if value.starts_with('-') && value != "-" {
                            break;
                        }
                        index += 1;
                        selected.push(value.clone());
                    }
                    files = Some(selected.into_iter().map(PathBuf::from).collect());
                }
                _ => unknown.push(argument.clone()),
            }
        } else {
            unknown.push(argument.clone());
        }
        index += 1;
    }
    if !unknown.is_empty() {
        return Err(format!("unrecognized arguments: {}", unknown.join(" ")));
    }
    Ok(ParsedCli::Analyze(CliOptions {
        root,
        files,
        servers,
        timeout,
        json: json_output,
    }))
}

fn argument_error(message: &str) -> i32 {
    eprintln!("usage: agent-canon lsp-code-analysis analyze [options]");
    eprintln!("agent-canon lsp-code-analysis: error: {message}");
    2
}

fn help_text() -> &'static str {
    "usage: agent-canon lsp-code-analysis analyze [options]\n\nRun one bounded point-LSP code analysis request.\n\noptions:\n  -h, --help\n  --root ROOT\n  --files [FILES ...]\n  --server LANGUAGE=COMMAND\n  --timeout SECONDS\n  --format {json,text}\n"
}

fn unique_symbols(items: impl IntoIterator<Item = CodeSymbol>) -> Vec<CodeSymbol> {
    let mut seen = HashSet::new();
    let mut result = Vec::new();
    for item in items {
        let key = json!({
            "uri": item.uri,
            "name": item.name,
            "kind": item.kind,
            "range": item.range.as_json(),
            "selectionRange": item.selection_range.as_json(),
            "container": item.container,
        })
        .to_string();
        if seen.insert(key) {
            result.push(item);
        }
    }
    result.sort_by(|left, right| {
        (
            &left.uri,
            &left.name,
            left.range.start.line,
            left.range.start.character,
        )
            .cmp(&(
                &right.uri,
                &right.name,
                right.range.start.line,
                right.range.start.character,
            ))
    });
    result
}

fn unique_relations(items: impl IntoIterator<Item = CodeRelation>) -> Vec<CodeRelation> {
    let mut seen = HashSet::new();
    let mut result = Vec::new();
    for item in items {
        let key = item.as_json().to_string();
        if seen.insert(key) {
            result.push(item);
        }
    }
    result.sort_by(|left, right| {
        (
            &left.orientation,
            &left.source,
            &left.target,
            position_json_sort_key(left.position.as_ref()),
        )
            .cmp(&(
                &right.orientation,
                &right.source,
                &right.target,
                position_json_sort_key(right.position.as_ref()),
            ))
    });
    result
}

fn position_json_sort_key(position: Option<&Position>) -> String {
    match position {
        Some(position) => format!(
            "{{\"character\":{},\"line\":{}}}",
            position.character, position.line
        ),
        None => "null".to_owned(),
    }
}

fn unique_diagnostics(items: impl IntoIterator<Item = CodeDiagnostic>) -> Vec<CodeDiagnostic> {
    let root = Path::new("/");
    let mut seen = HashSet::new();
    let mut result = Vec::new();
    for item in items {
        let key = item
            .as_json(root)
            .map(|value| value.to_string())
            .unwrap_or_default();
        if seen.insert(key) {
            result.push(item);
        }
    }
    result.sort_by(|left, right| {
        (
            &left.uri,
            left.range.start.line,
            left.range.start.character,
            &left.message,
        )
            .cmp(&(
                &right.uri,
                right.range.start.line,
                right.range.start.character,
                &right.message,
            ))
    });
    result
}

fn json_truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => false,
        Some(Value::Bool(value)) => *value,
        Some(Value::Number(value)) => value.as_f64().unwrap_or(1.0) != 0.0,
        Some(Value::String(value)) => !value.is_empty(),
        Some(Value::Array(value)) => !value.is_empty(),
        Some(Value::Object(value)) => !value.is_empty(),
    }
}

fn json_truthy_value(value: &Value) -> bool {
    json_truthy(Some(value))
}

fn position(value: Option<&Value>) -> Result<Position, AnalysisFailure> {
    let value = value
        .and_then(Value::as_object)
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "position must be an object"))?;
    let line = value
        .get("line")
        .and_then(Value::as_u64)
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "invalid UTF-16 position"))?;
    let character = value
        .get("character")
        .and_then(Value::as_u64)
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "invalid UTF-16 position"))?;
    Ok(Position { line, character })
}

fn lsp_range(value: Option<&Value>) -> Result<LspRange, AnalysisFailure> {
    let value = value
        .and_then(Value::as_object)
        .ok_or_else(|| AnalysisFailure::new("malformed-response", "range must be an object"))?;
    let start = position(value.get("start"))?;
    let end = position(value.get("end"))?;
    if (end.line, end.character) < (start.line, start.character) {
        return Err(AnalysisFailure::new(
            "malformed-response",
            "range end precedes range start",
        ));
    }
    Ok(LspRange { start, end })
}

fn uri_scheme(uri: &str) -> Option<(&str, &str)> {
    let colon = uri.find(':')?;
    let boundary = uri.find(['/', '?', '#']).unwrap_or(uri.len());
    if colon >= boundary {
        return None;
    }
    let scheme = &uri[..colon];
    let mut chars = scheme.chars();
    let first = chars.next()?;
    if !first.is_ascii_alphabetic()
        || !chars.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '+' | '.' | '-')
        })
    {
        return None;
    }
    Some((scheme, &uri[colon + 1..]))
}

fn uri_path(root: &Path, uri: &str) -> Result<String, AnalysisFailure> {
    let uri_parts = uri_scheme(uri);
    if let Some((scheme, _)) = uri_parts {
        if !scheme.eq_ignore_ascii_case("file") {
            return Ok(format!("external:unknown:{uri}"));
        }
    }
    let raw = if let Some((scheme, rest)) = uri_parts {
        if scheme.eq_ignore_ascii_case("file") {
            let without_authority = if let Some(authority) = rest.strip_prefix("//") {
                if cfg!(windows) {
                    rest
                } else {
                    authority
                        .find('/')
                        .map(|index| &authority[index..])
                        .unwrap_or("")
                }
            } else {
                rest
            };
            without_authority
        } else {
            uri
        }
    } else {
        uri
    };
    let raw_path = raw.split(['?', '#']).next().unwrap_or_default();
    let path = uri_path_buf(raw_path);
    let candidate = if path.is_absolute() {
        path
    } else {
        root.join(path)
    };
    let resolved = resolve_weakly(&candidate).map_err(|error| {
        AnalysisFailure::new(
            "path-escape",
            format!("URI path could not be resolved: {error}"),
        )
    })?;
    relative_to_root(root, &resolved).ok_or_else(|| {
        AnalysisFailure::new("path-escape", format!("URI outside analysis root: {uri}"))
    })
}

/// Decode a URI path component using the host path syntax.
pub(crate) fn uri_path_buf(raw_path: &str) -> PathBuf {
    let decoded = percent_decode(raw_path);
    let drive_path = decoded.trim_start_matches('/');
    if cfg!(windows)
        && decoded.starts_with('/')
        && drive_path.len() >= 2
        && drive_path.as_bytes()[0].is_ascii_alphabetic()
        && drive_path.as_bytes()[1] == b':'
    {
        PathBuf::from(drive_path)
    } else {
        PathBuf::from(decoded)
    }
}

fn percent_decode(value: &str) -> String {
    fn hex_value(byte: u8) -> Option<u8> {
        match byte {
            b'0'..=b'9' => Some(byte - b'0'),
            b'a'..=b'f' => Some(byte - b'a' + 10),
            b'A'..=b'F' => Some(byte - b'A' + 10),
            _ => None,
        }
    }
    let bytes = value.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' && index + 2 < bytes.len() {
            if let (Some(high), Some(low)) =
                (hex_value(bytes[index + 1]), hex_value(bytes[index + 2]))
            {
                decoded.push((high << 4) | low);
                index += 3;
                continue;
            }
        }
        decoded.push(bytes[index]);
        index += 1;
    }
    String::from_utf8_lossy(&decoded).into_owned()
}

/// Encode a source path as a standard file URI.
pub fn file_uri(path: &Path) -> String {
    let path = resolve_weakly(path).unwrap_or_else(|_| path.to_path_buf());
    let mut value = path_as_posix(&path);
    if cfg!(windows) {
        if let Some(unc) = value.strip_prefix("//?/UNC/") {
            value = format!("//{unc}");
        } else if let Some(drive_path) = value.strip_prefix("//?/") {
            value = drive_path.to_owned();
        }
    }
    let windows_drive = cfg!(windows)
        && value.len() >= 2
        && value.as_bytes()[0].is_ascii_alphabetic()
        && value.as_bytes()[1] == b':';
    let windows_unc = cfg!(windows) && value.starts_with("//");
    let value = if windows_unc {
        value.trim_start_matches('/')
    } else {
        value.as_str()
    };
    let mut encoded = String::with_capacity(value.len());
    for (index, byte) in value.bytes().enumerate() {
        if byte.is_ascii_alphanumeric()
            || matches!(byte, b'/' | b'-' | b'.' | b'_' | b'~')
            || (windows_drive && index == 1 && byte == b':')
        {
            encoded.push(char::from(byte));
        } else {
            use std::fmt::Write as _;
            write!(encoded, "%{byte:02X}").expect("write URI escape to String");
        }
    }
    if windows_drive {
        format!("file:///{encoded}")
    } else {
        format!("file://{encoded}")
    }
}

fn path_as_posix(path: &Path) -> String {
    let value = path.to_string_lossy().into_owned();
    if cfg!(windows) {
        value.replace('\\', "/")
    } else {
        value
    }
}

fn relative_to_root(root: &Path, path: &Path) -> Option<String> {
    let relative = path.strip_prefix(root).ok()?;
    let value = path_as_posix(relative);
    Some(if value.is_empty() {
        ".".to_owned()
    } else {
        value
    })
}

fn resolve_weakly(path: &Path) -> std::io::Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()?.join(path)
    };
    let components = absolute.components().collect::<Vec<_>>();
    let mut current = PathBuf::new();
    let mut missing = false;
    for component in components {
        match component {
            Component::Prefix(prefix) => current.push(prefix.as_os_str()),
            Component::RootDir => current.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                current.pop();
                if missing && current.exists() {
                    current = fs::canonicalize(&current)?;
                    missing = false;
                }
            }
            Component::Normal(name) => {
                current.push(name);
                if !missing {
                    match fs::canonicalize(&current) {
                        Ok(canonical) => current = canonical,
                        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                            missing = true
                        }
                        Err(error) => return Err(error),
                    }
                }
            }
        }
    }
    Ok(current)
}

fn has_symlink_component(path: &Path, root: &Path) -> bool {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        root.join(path)
    };
    let Ok(relative) = absolute.strip_prefix(root) else {
        return false;
    };
    let mut current = root.to_path_buf();
    for component in relative.components() {
        match component {
            Component::ParentDir => return true,
            Component::CurDir | Component::RootDir | Component::Prefix(_) => {}
            Component::Normal(name) => {
                current.push(name);
                if fs::symlink_metadata(&current)
                    .is_ok_and(|metadata| metadata.file_type().is_symlink())
                {
                    return true;
                }
            }
        }
    }
    false
}

fn has_excluded_component(relative: &str) -> bool {
    Path::new(relative).components().any(|component| {
        component
            .as_os_str()
            .to_str()
            .is_some_and(|part| EXCLUDED_PARTS.contains(&part))
    })
}

fn glob_component_matches(value: &str, pattern: &str) -> bool {
    fn class_match(pattern: &[char], start: usize, value: char) -> Option<(bool, usize)> {
        let mut cursor = start + 1;
        let mut negate = false;
        if pattern.get(cursor) == Some(&'!') {
            negate = true;
            cursor += 1;
        }
        let mut members = Vec::new();
        if pattern.get(cursor) == Some(&']') {
            members.push(']');
            cursor += 1;
        }
        let class_start = cursor;
        while cursor < pattern.len() && pattern[cursor] != ']' {
            cursor += 1;
        }
        if cursor == pattern.len() {
            return None;
        }
        let mut index = class_start;
        while index < cursor {
            if index + 2 < cursor && pattern[index + 1] == '-' {
                let first = pattern[index] as u32;
                let last = pattern[index + 2] as u32;
                if first <= value as u32 && value as u32 <= last {
                    members.push(value);
                }
                index += 3;
            } else {
                members.push(pattern[index]);
                index += 1;
            }
        }
        let matched = members.contains(&value);
        Some((if negate { !matched } else { matched }, cursor + 1))
    }

    fn match_from(
        value: &[char],
        pattern: &[char],
        value_index: usize,
        pattern_index: usize,
        memo: &mut [Vec<Option<bool>>],
    ) -> bool {
        if let Some(result) = memo[pattern_index][value_index] {
            return result;
        }
        let matched = if pattern_index == pattern.len() {
            value_index == value.len()
        } else {
            match pattern[pattern_index] {
                '*' => {
                    match_from(value, pattern, value_index, pattern_index + 1, memo)
                        || (value_index < value.len()
                            && match_from(value, pattern, value_index + 1, pattern_index, memo))
                }
                '?' => {
                    value_index < value.len()
                        && match_from(value, pattern, value_index + 1, pattern_index + 1, memo)
                }
                '[' => {
                    if let Some((in_class, next_pattern)) = class_match(
                        pattern,
                        pattern_index,
                        *value.get(value_index).unwrap_or(&'\0'),
                    ) {
                        value_index < value.len()
                            && in_class
                            && match_from(value, pattern, value_index + 1, next_pattern, memo)
                    } else {
                        value_index < value.len()
                            && value[value_index] == '['
                            && match_from(value, pattern, value_index + 1, pattern_index + 1, memo)
                    }
                }
                literal => {
                    value_index < value.len()
                        && value[value_index] == literal
                        && match_from(value, pattern, value_index + 1, pattern_index + 1, memo)
                }
            }
        };
        memo[pattern_index][value_index] = Some(matched);
        matched
    }

    let value = value.chars().collect::<Vec<_>>();
    let pattern = pattern.chars().collect::<Vec<_>>();
    let mut memo = vec![vec![None; value.len() + 1]; pattern.len() + 1];
    match_from(&value, &pattern, 0, 0, &mut memo)
}

fn path_matches_pattern(relative: &str, pattern: &str) -> bool {
    let path_parts = relative.split('/').collect::<Vec<_>>();
    let pattern_parts = pattern
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect::<Vec<_>>();
    if pattern_parts.is_empty() || pattern_parts.len() > path_parts.len() {
        return false;
    }
    path_parts[path_parts.len() - pattern_parts.len()..]
        .iter()
        .zip(pattern_parts)
        .all(|(path_part, pattern_part)| glob_component_matches(path_part, pattern_part))
}

fn matches_exclude(relative: &str, excludes: &[String]) -> bool {
    let parts = Path::new(relative)
        .components()
        .filter_map(|component| component.as_os_str().to_str())
        .collect::<HashSet<_>>();
    excludes.iter().any(|raw| {
        let exclude = raw.trim_matches('/');
        !exclude.is_empty()
            && (relative == exclude
                || relative.starts_with(&format!("{exclude}/"))
                || parts.contains(exclude)
                || path_matches_pattern(relative, exclude))
    })
}

fn relative_safe(root: &Path, path: &Path) -> Option<String> {
    let resolved = resolve_weakly(path).ok()?;
    relative_to_root(root, &resolved)
}

fn accepted_source_file(root: &Path, path: &Path, excludes: &[String]) -> bool {
    if has_symlink_component(path, root) {
        return false;
    }
    let Ok(metadata) = fs::symlink_metadata(path) else {
        return false;
    };
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return false;
    }
    let Some(relative) = relative_safe(root, path) else {
        return false;
    };
    language_for_path(path).is_some()
        && !has_excluded_component(&relative)
        && !is_retired_legacy_tool_path(&relative)
        && !matches_exclude(&relative, excludes)
}

/// Discover bounded source files without following symlinked components.
pub fn discover_lsp_files(
    root: &Path,
    requested_surfaces: &[String],
    excludes: &[String],
) -> Result<Vec<PathBuf>, LspAnalysisError> {
    let root = resolve_path(root);
    let surfaces = if requested_surfaces.is_empty() {
        DEFAULT_SURFACES
            .iter()
            .map(|surface| (*surface).to_owned())
            .collect::<Vec<_>>()
    } else {
        requested_surfaces.to_vec()
    };
    let mut discovered = BTreeMap::<String, PathBuf>::new();
    for surface in surfaces {
        let path = PathBuf::from(surface);
        let path = if path.is_absolute() {
            path
        } else {
            root.join(path)
        };
        if has_symlink_component(&path, &root) {
            continue;
        }
        let Some(relative) = relative_safe(&root, &path) else {
            continue;
        };
        if fs::symlink_metadata(&path).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
            continue;
        }
        if fs::metadata(&path).is_ok_and(|metadata| metadata.is_file()) {
            if accepted_source_file(&root, &path, excludes) {
                discovered.insert(relative, path);
            }
            continue;
        }
        if !fs::metadata(&path).is_ok_and(|metadata| metadata.is_dir()) {
            continue;
        }
        let mut stack = vec![path];
        while let Some(current) = stack.pop() {
            let Ok(entries) = fs::read_dir(&current) else {
                continue;
            };
            let mut entries = entries.filter_map(Result::ok).collect::<Vec<_>>();
            entries.sort_by_key(|entry| entry.file_name());
            let mut directories = Vec::new();
            for entry in entries {
                let candidate = entry.path();
                let Ok(file_type) = entry.file_type() else {
                    continue;
                };
                if file_type.is_symlink() || has_symlink_component(&candidate, &root) {
                    continue;
                }
                let Some(relative) = relative_safe(&root, &candidate) else {
                    continue;
                };
                if has_excluded_component(&relative)
                    || is_retired_legacy_tool_path(&relative)
                    || matches_exclude(&relative, excludes)
                {
                    continue;
                }
                if file_type.is_dir() {
                    directories.push(candidate);
                } else if file_type.is_file() && accepted_source_file(&root, &candidate, excludes) {
                    discovered.insert(relative, candidate);
                }
            }
            directories.sort();
            stack.extend(directories.into_iter().rev());
        }
    }
    Ok(discovered.into_values().collect())
}
