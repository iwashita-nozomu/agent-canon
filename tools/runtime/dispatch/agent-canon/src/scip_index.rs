// @dependency-start
// contract implementation
// responsibility Verifies native SCIP producers, writes external index artifacts, and projects bounded facts from official SCIP indexes.
// upstream implementation environment_dependencies.rs owns verified executable resolution
// upstream implementation path_expansion.rs owns Python-compatible user-home expansion
// upstream implementation path_resolution.rs owns non-strict path resolution
// upstream implementation runtime_boundary.rs owns external artifact paths and root capabilities
// downstream implementation git_dependency_diff_summary.rs consumes bounded SCIP impact
// downstream design ../../../../../documents/tools/scip_index.md documents the native command
// @dependency-end

use crate::environment_dependencies::resolve_verified_executable;
use crate::path_expansion::{
    native_home_lookup, HomeLookupRequest, PathExpansionEnvironment, PathPlatform,
};
use crate::python_text::python_strip;
use crate::runtime_boundary::{root_capability_environment, RuntimeArtifactBoundary};
use protobuf::Message;
use rustpython_ast::bigint::BigInt;
use scip::types::{occurrence::Typed_range, Index, Occurrence, SymbolInformation};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

pub const DEFAULT_RESULT_LIMIT: usize = 200;
pub const MAX_RESULT_LIMIT: usize = 1000;

const DEFINITION_ROLE: i32 = 0x1;
const ROLE_NAMES: &[(i32, &str)] = &[
    (0x1, "definition"),
    (0x2, "import"),
    (0x4, "write-access"),
    (0x8, "read-access"),
    (0x10, "generated"),
    (0x20, "test"),
    (0x40, "forward-definition"),
];
const IMAGE_RECEIPT_ROOT: &str = "/usr/local/share/agent-canon/image-dependencies/receipts";
const IMAGE_MANIFEST_ROOT: &str = "/usr/local/share/agent-canon/runtime";
const INDEXERS: &[(&str, &str, &str)] = &[
    ("python", "scip-python", "scip-python"),
    ("cpp", "scip-clang", "scip-clang"),
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ScipErrorKind {
    UnsupportedCapability,
    RequiredProjectInput,
    Failure,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ScipError {
    pub(crate) kind: ScipErrorKind,
    pub(crate) message: String,
    pub(crate) language: Option<String>,
}

impl ScipError {
    fn failure(message: impl Into<String>) -> Self {
        Self {
            kind: ScipErrorKind::Failure,
            message: message.into(),
            language: None,
        }
    }

    fn unsupported(language: &str, message: impl Into<String>) -> Self {
        Self {
            kind: ScipErrorKind::UnsupportedCapability,
            message: message.into(),
            language: Some(language.to_string()),
        }
    }

    fn required_input(language: &str, message: impl Into<String>) -> Self {
        Self {
            kind: ScipErrorKind::RequiredProjectInput,
            message: message.into(),
            language: Some(language.to_string()),
        }
    }
}

impl fmt::Display for ScipError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for ScipError {}

#[derive(Debug, Clone)]
pub(crate) struct IndexRequest {
    pub(crate) root: PathBuf,
    pub(crate) runtime_root: PathBuf,
    pub(crate) output: PathBuf,
    pub(crate) language: String,
    pub(crate) project_name: Option<String>,
    pub(crate) project_version: Option<String>,
    pub(crate) python_environment: Option<PathBuf>,
    pub(crate) compile_database: Option<PathBuf>,
}

#[derive(Debug, Clone)]
pub(crate) struct QueryRequest {
    pub(crate) root: PathBuf,
    pub(crate) runtime_root: PathBuf,
    pub(crate) indexes: Vec<PathBuf>,
    pub(crate) paths: Vec<String>,
    pub(crate) symbols: Vec<String>,
    pub(crate) limit: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct IndexReport {
    pub(crate) payload: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct QueryReport {
    pub(crate) payload: Value,
}

#[derive(Debug, Clone)]
struct VerifiedTool {
    executable: PathBuf,
    record_id: String,
    version: String,
}

#[derive(Debug, Clone)]
struct CommandOutput {
    returncode: i32,
    stdout: String,
    stderr: String,
}

#[derive(Debug, Clone)]
struct IndexDocument {
    path: String,
    language: String,
    occurrences: Vec<Occurrence>,
    symbols: Vec<SymbolInformation>,
}

#[derive(Debug, Clone)]
struct LoadedIndex {
    path: PathBuf,
    digest: String,
    project_root: PathBuf,
    tool_name: String,
    tool_version: String,
    text_encoding: String,
    documents: Vec<IndexDocument>,
    external_symbols: Vec<SymbolInformation>,
}

#[derive(Debug, Clone)]
struct OccurrenceRow {
    path: String,
    symbol: String,
    symbol_roles: i32,
    value: Value,
}

fn source_repository_root() -> Result<PathBuf, ScipError> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .map(Path::to_path_buf)
        .ok_or_else(|| ScipError::failure("native SCIP source root is unavailable"))
}

fn expand_config_override_path_with<F>(
    path: &Path,
    label: &str,
    platform: PathPlatform,
    environment: &PathExpansionEnvironment,
    home_lookup: F,
) -> Result<PathBuf, ScipError>
where
    F: FnMut(HomeLookupRequest) -> Result<Option<PathBuf>, String>,
{
    crate::path_expansion::expand_user_path_with(path, platform, environment, home_lookup)
        .map_err(|error| ScipError::failure(format!("unable to expand {label} path: {error}")))
}

fn manifest_and_receipts() -> Result<(PathBuf, PathBuf), ScipError> {
    let repository_root = source_repository_root()?;
    let path_environment = PathExpansionEnvironment::from_process();
    let manifest_override = env::var_os("AGENT_CANON_DEPENDENCY_MANIFEST").and_then(|value| {
        let value = value.to_string_lossy();
        let value = python_strip(&value);
        (!value.is_empty()).then(|| PathBuf::from(value))
    });
    let manifest = if let Some(manifest) = manifest_override {
        let manifest = expand_config_override_path_with(
            &manifest,
            "shared tool dependency manifest",
            PathPlatform::native(),
            &path_environment,
            native_home_lookup,
        )?;
        fs::canonicalize(&manifest).map_err(|_| {
            ScipError::failure(format!(
                "shared tool dependency manifest is unavailable: {}",
                manifest.display()
            ))
        })?
    } else {
        let source_manifest = repository_root.join("bootstrap/container/image/dependencies.toml");
        if source_manifest.is_file() {
            source_manifest
        } else {
            PathBuf::from(IMAGE_MANIFEST_ROOT).join("dependencies.toml")
        }
    };
    if !manifest.is_file() {
        return Err(ScipError::failure(
            "shared tool dependency manifest is unavailable; start bootstrap.sh",
        ));
    }
    let image_receipts = PathBuf::from(IMAGE_RECEIPT_ROOT);
    let receipts = if image_receipts.is_dir() {
        image_receipts
    } else {
        let receipts = env::var_os("AGENT_CANON_DEPENDENCY_RECEIPTS").and_then(|value| {
            let value = value.to_string_lossy();
            let value = python_strip(&value);
            (!value.is_empty()).then(|| PathBuf::from(value))
        });
        let Some(receipts) = receipts else {
            return Err(ScipError::failure(
                "shared tool dependency receipts are unavailable; start bootstrap.sh",
            ));
        };
        expand_config_override_path_with(
            &receipts,
            "shared tool dependency receipts",
            PathPlatform::native(),
            &path_environment,
            native_home_lookup,
        )?
    };
    Ok((manifest, receipts))
}

fn manifest_workspace(manifest: &Path) -> Result<PathBuf, ScipError> {
    manifest
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| ScipError::failure("SCIP dependency manifest has no workspace root"))
}

fn resolve_verified_tool(language_or_tool: &str) -> Result<VerifiedTool, ScipError> {
    let selection = INDEXERS
        .iter()
        .find_map(|(language, record, executable)| {
            (*language == language_or_tool).then_some((*record, *executable))
        })
        .or_else(|| (language_or_tool == "scip").then_some(("scip-cli", "scip")))
        .ok_or_else(|| {
            ScipError::failure(format!(
                "no verified SCIP executable for {language_or_tool}"
            ))
        })?;
    let (manifest, receipts) = manifest_and_receipts()?;
    let workspace = manifest_workspace(&manifest)?;
    let verified = resolve_verified_executable(
        &workspace,
        &receipts,
        selection.0,
        selection.1,
        Some(&manifest),
    )
    .map_err(|error| {
        ScipError::failure(format!(
            "verified executable resolution failed for {}: {error}",
            selection.0
        ))
    })?;
    Ok(VerifiedTool {
        executable: verified.absolute_path,
        record_id: verified.record_id,
        version: verified.manifest_version,
    })
}

fn run_native_command(
    command: &[String],
    cwd: &Path,
    environment: &BTreeMap<String, String>,
) -> Result<CommandOutput, ScipError> {
    let Some(executable) = command.first() else {
        return Err(ScipError::failure("native SCIP command is empty"));
    };
    let output = Command::new(executable)
        .args(command.iter().skip(1))
        .current_dir(cwd)
        .env_clear()
        .envs(environment)
        .output()
        .map_err(|error| ScipError::failure(format!("unable to execute {executable}: {error}")))?;
    let returncode = match output.status.code() {
        Some(code) => code,
        None => {
            #[cfg(unix)]
            {
                use std::os::unix::process::ExitStatusExt;
                output.status.signal().map_or(1, |signal| -signal)
            }
            #[cfg(not(unix))]
            {
                1
            }
        }
    };
    Ok(CommandOutput {
        returncode,
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
    })
}

fn require_success(result: &CommandOutput, command: &[String]) -> Result<(), ScipError> {
    if result.returncode == 0 {
        return Ok(());
    }
    let detail = if !python_strip(&result.stderr).is_empty() {
        python_strip(&result.stderr)
    } else {
        python_strip(&result.stdout)
    };
    let executable = command
        .first()
        .map(|value| {
            Path::new(value)
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
        })
        .unwrap_or_default();
    Err(ScipError::failure(format!(
        "{executable} exited {}{}",
        result.returncode,
        if detail.is_empty() {
            String::new()
        } else {
            format!(": {detail}")
        }
    )))
}

fn regular_project_input(root: &Path, value: &Path, label: &str) -> Result<PathBuf, ScipError> {
    let candidate = if value.is_absolute() {
        value.to_path_buf()
    } else {
        root.join(value)
    };
    let resolved = fs::canonicalize(&candidate).map_err(|_| {
        ScipError::failure(format!("unable to read {label}: {}", candidate.display()))
    })?;
    if !resolved.is_file() {
        return Err(ScipError::failure(format!(
            "{label} must be a regular file: {}",
            candidate.display()
        )));
    }
    Ok(resolved)
}

fn verified_output_path(
    source_root: &Path,
    runtime_root: &Path,
    output: &Path,
) -> Result<(RuntimeArtifactBoundary, PathBuf), ScipError> {
    let boundary = RuntimeArtifactBoundary::for_source(source_root, Some(runtime_root), true)
        .map_err(ScipError::failure)?;
    let destination = boundary.resolve(output).map_err(ScipError::failure)?;
    if destination.exists() || fs::symlink_metadata(&destination).is_ok() {
        return Err(ScipError::failure(format!(
            "index output already exists: {}",
            destination.display()
        )));
    }
    let parent = destination
        .parent()
        .ok_or_else(|| ScipError::failure("SCIP output has no parent directory"))?;
    let relative_parent = parent
        .strip_prefix(boundary.root())
        .map_err(|_| ScipError::failure("SCIP output parent escapes runtime root"))?;
    let create_path = if relative_parent.as_os_str().is_empty() {
        Path::new(".")
    } else {
        relative_parent
    };
    boundary
        .ensure_directory(create_path)
        .map_err(ScipError::failure)?;
    Ok((boundary, destination))
}

fn producer_command(
    request: &IndexRequest,
    output: &Path,
    supplementary_output: &Path,
    tool: &VerifiedTool,
    python_environment: Option<&Path>,
    compile_database: Option<&Path>,
) -> Result<Vec<String>, ScipError> {
    let mut command = vec![tool.executable.to_string_lossy().into_owned()];
    match request.language.as_str() {
        "python" => {
            command.extend([
                "index".to_string(),
                ".".to_string(),
                format!(
                    "--project-name={}",
                    request.project_name.as_deref().unwrap_or_default()
                ),
                format!(
                    "--project-version={}",
                    request.project_version.as_deref().unwrap_or_default()
                ),
                format!(
                    "--environment={}",
                    python_environment.unwrap_or(Path::new("")).display()
                ),
                format!("--output={}", output.display()),
            ]);
        }
        "cpp" => {
            command.extend([
                format!(
                    "--compdb-path={}",
                    compile_database.unwrap_or(Path::new("")).display()
                ),
                format!("--index-output-path={}", output.display()),
                format!(
                    "--supplementary-output-dir={}",
                    supplementary_output.display()
                ),
            ]);
        }
        language => {
            return Err(ScipError::unsupported(
                language,
                format!("no qualified native SCIP producer for {language}"),
            ));
        }
    }
    Ok(command)
}

fn run_command<F>(
    runner: &mut F,
    command: &[String],
    cwd: &Path,
    environment: &BTreeMap<String, String>,
) -> Result<CommandOutput, ScipError>
where
    F: FnMut(&[String], &Path, &BTreeMap<String, String>) -> Result<CommandOutput, ScipError>,
{
    runner(command, cwd, environment)
}

fn inspect_index<F>(
    source_root: &Path,
    boundary: &RuntimeArtifactBoundary,
    index_path: &Path,
    environment: &BTreeMap<String, String>,
    resolve_tool: &mut F,
    runner: &mut impl FnMut(
        &[String],
        &Path,
        &BTreeMap<String, String>,
    ) -> Result<CommandOutput, ScipError>,
) -> Result<(VerifiedTool, CommandOutput), ScipError>
where
    F: FnMut(&str) -> Result<VerifiedTool, ScipError>,
{
    let target = boundary.resolve(index_path).map_err(ScipError::failure)?;
    let metadata = fs::symlink_metadata(&target).map_err(|_| {
        ScipError::failure(format!(
            "SCIP index is not a regular runtime artifact: {}",
            target.display()
        ))
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(ScipError::failure(format!(
            "SCIP index is not a regular runtime artifact: {}",
            target.display()
        )));
    }
    let scip = resolve_tool("scip")?;
    let command = vec![
        scip.executable.to_string_lossy().into_owned(),
        "stats".to_string(),
        "--from".to_string(),
        target.to_string_lossy().into_owned(),
    ];
    let result = run_command(runner, &command, source_root, environment)?;
    require_success(&result, &command)?;
    Ok((scip, result))
}

/// Write a native SCIP index under the explicit external runtime root.
pub(crate) fn index_project(request: &IndexRequest) -> Result<IndexReport, ScipError> {
    index_project_with(request, &mut resolve_verified_tool, &mut run_native_command)
}

fn index_project_with<R, F>(
    request: &IndexRequest,
    resolve_tool: &mut R,
    runner: &mut F,
) -> Result<IndexReport, ScipError>
where
    R: FnMut(&str) -> Result<VerifiedTool, ScipError>,
    F: FnMut(&[String], &Path, &BTreeMap<String, String>) -> Result<CommandOutput, ScipError>,
{
    if !matches!(request.language.as_str(), "python" | "cpp") {
        return Err(ScipError::unsupported(
            &request.language,
            format!("no qualified native SCIP producer for {}", request.language),
        ));
    }
    if request.language == "python"
        && (request.project_name.as_deref().is_none_or(str::is_empty)
            || request.project_version.as_deref().is_none_or(str::is_empty)
            || request.python_environment.is_none())
    {
        return Err(ScipError::required_input(
            &request.language,
            "Python indexing requires --project-name, --project-version, and --python-environment from the project environment owner",
        ));
    }
    if request.language == "cpp" && request.compile_database.is_none() {
        return Err(ScipError::required_input(
            &request.language,
            "C/C++ indexing requires --compile-database from the project build owner",
        ));
    }
    let source_root = fs::canonicalize(&request.root).map_err(|error| {
        ScipError::failure(format!(
            "source root is unavailable: {}: {error}",
            request.root.display()
        ))
    })?;
    let python_environment = if request.language == "python" {
        Some(regular_project_input(
            &source_root,
            request
                .python_environment
                .as_deref()
                .expect("checked Python environment"),
            "Python environment file",
        )?)
    } else {
        None
    };
    let compile_database = if request.language == "cpp" {
        let compile_database = request
            .compile_database
            .as_deref()
            .expect("checked compile database");
        Some(regular_project_input(
            &source_root,
            compile_database,
            "compile database",
        )?)
    } else {
        None
    };
    let (boundary, destination) =
        verified_output_path(&source_root, &request.runtime_root, &request.output)?;
    let environment =
        root_capability_environment(&source_root, boundary.root(), None, Some(&source_root))
            .map_err(ScipError::failure)?;
    let supplementary_output = destination
        .parent()
        .ok_or_else(|| ScipError::failure("SCIP output has no parent directory"))?
        .join("scip-clang-supplementary-output");
    if request.language == "cpp" {
        let relative = supplementary_output
            .strip_prefix(boundary.root())
            .map_err(|_| ScipError::failure("SCIP supplementary output escapes runtime root"))?;
        boundary
            .ensure_directory(relative)
            .map_err(ScipError::failure)?;
    }
    let tool = resolve_tool(&request.language)?;
    let command = producer_command(
        request,
        &destination,
        &supplementary_output,
        &tool,
        python_environment.as_deref(),
        compile_database.as_deref(),
    )?;
    let produced = run_command(runner, &command, &source_root, &environment)?;
    require_success(&produced, &command)?;
    let (scip, stats) = inspect_index(
        &source_root,
        &boundary,
        &destination,
        &environment,
        resolve_tool,
        runner,
    )?;
    let artifact_path = relative_posix(&destination, boundary.root())?;
    let mut capabilities = serde_json::Map::new();
    capabilities.insert(
        request.language.clone(),
        Value::String("index-written".to_string()),
    );
    capabilities.insert(
        "source_freshness".to_string(),
        Value::String("unverified".to_string()),
    );
    Ok(IndexReport {
        payload: json!({
            "status": "written",
            "language": request.language,
            "index": {
                "path": artifact_path,
                "sha256": boundary.digest(&destination).map_err(ScipError::failure)?
            },
            "indexer": {"id": tool.record_id, "version": tool.version},
            "scip": {"version": scip.version, "stats": python_strip(&stats.stdout)},
            "capabilities": capabilities,
            "stdout": python_strip(&produced.stdout),
            "stderr": python_strip(&produced.stderr)
        }),
    })
}

fn relative_posix(path: &Path, root: &Path) -> Result<String, ScipError> {
    let relative = path
        .strip_prefix(root)
        .map_err(|_| ScipError::failure(format!("path escapes root: {}", path.display())))?;
    Ok(path_as_posix(relative))
}

fn path_as_posix(path: &Path) -> String {
    let value = path.to_string_lossy().into_owned();
    #[cfg(windows)]
    {
        value.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        value
    }
}

fn uri_scheme(value: &str) -> Option<(&str, &str)> {
    let colon = value.find(':')?;
    let scheme = &value[..colon];
    let mut characters = scheme.chars();
    if !characters.next()?.is_ascii_alphabetic()
        || characters.any(|character| {
            !character.is_ascii_alphanumeric() && !matches!(character, '+' | '.' | '-')
        })
    {
        return None;
    }
    Some((scheme, &value[colon + 1..]))
}

fn uri_components(value: &str) -> (&str, &str, &str) {
    let (before_fragment, fragment) = value.split_once('#').unwrap_or((value, ""));
    let (path, query) = before_fragment
        .split_once('?')
        .unwrap_or((before_fragment, ""));
    (path, query, fragment)
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

fn index_project_root(value: &str) -> Result<PathBuf, ScipError> {
    if value.is_empty() {
        return Err(ScipError::failure(
            "SCIP index is missing metadata.project_root",
        ));
    }
    let path_text = match uri_scheme(value) {
        Some((scheme, _)) if !scheme.eq_ignore_ascii_case("file") => {
            return Err(ScipError::failure(format!(
                "unsupported SCIP project-root URI: {value}"
            )))
        }
        Some((_, rest)) => {
            let (path, query, fragment) = uri_components(rest);
            if !query.is_empty() || !fragment.is_empty() {
                return Err(ScipError::failure(format!(
                    "unsupported SCIP project-root URI: {value}"
                )));
            }
            let path_text = if let Some(authority_path) = path.strip_prefix("//") {
                let (authority, path) = authority_path
                    .split_once('/')
                    .unwrap_or((authority_path, ""));
                if !authority.is_empty() {
                    return Err(ScipError::failure(format!(
                        "unsupported SCIP project-root URI: {value}"
                    )));
                }
                if path.is_empty() {
                    String::new()
                } else {
                    format!("/{path}")
                }
            } else {
                path.to_string()
            };
            percent_decode(&path_text)
        }
        None => value.to_string(),
    };
    let path = PathBuf::from(path_text);
    if !path.is_absolute() {
        return Err(ScipError::failure(format!(
            "SCIP project root is not absolute: {value}"
        )));
    }
    crate::path_resolution::resolve_non_strict(&path).map_err(ScipError::failure)
}

fn relative_source_path(value: &str) -> Result<String, ScipError> {
    if value.is_empty() {
        return Err(ScipError::failure("SCIP document has no relative_path"));
    }
    if value.starts_with('/')
        || value.contains('\\')
        || value.contains("//")
        || value.split('/').any(|part| matches!(part, "" | "." | ".."))
    {
        return Err(ScipError::failure(format!(
            "SCIP document path is not canonical: {value}"
        )));
    }
    Ok(value.to_string())
}

fn scip_range(occurrence: &Occurrence) -> Option<Value> {
    if let Some(typed_range) = &occurrence.typed_range {
        match typed_range {
            Typed_range::SingleLineRange(range) => {
                return Some(json!({
                    "start": {"line": range.line, "character": range.start_character},
                    "end": {"line": range.line, "character": range.end_character}
                }));
            }
            Typed_range::MultiLineRange(range) => {
                return Some(json!({
                    "start": {"line": range.start_line, "character": range.start_character},
                    "end": {"line": range.end_line, "character": range.end_character}
                }));
            }
            _ => {}
        }
    }
    match occurrence.range.as_slice() {
        [start_line, start_character, end_character] => Some(json!({
            "start": {"line": start_line, "character": start_character},
            "end": {"line": start_line, "character": end_character}
        })),
        [start_line, start_character, end_line, end_character] => Some(json!({
            "start": {"line": start_line, "character": start_character},
            "end": {"line": end_line, "character": end_character}
        })),
        _ => None,
    }
}

fn occurrence_rows(
    index: &LoadedIndex,
    source_root: &Path,
) -> Result<Vec<OccurrenceRow>, ScipError> {
    let prefix = index.project_root.strip_prefix(source_root).map_err(|_| {
        ScipError::failure(format!(
            "SCIP project root is outside requested root: {}",
            index.project_root.display()
        ))
    })?;
    let prefix = if prefix == Path::new(".") {
        String::new()
    } else {
        path_as_posix(prefix)
    };
    let mut rows = Vec::new();
    for document in &index.documents {
        let path = if prefix.is_empty() {
            document.path.clone()
        } else {
            format!("{prefix}/{}", document.path)
        };
        for occurrence in &document.occurrences {
            if occurrence.symbol.is_empty() {
                continue;
            }
            if occurrence.symbol_roles < 0 {
                return Err(ScipError::failure(format!(
                    "invalid symbol_roles for {path}: {}",
                    occurrence.symbol_roles
                )));
            }
            let roles = ROLE_NAMES
                .iter()
                .filter_map(|(bit, name)| (occurrence.symbol_roles & *bit != 0).then_some(*name))
                .collect::<Vec<_>>();
            let value = json!({
                "path": path,
                "range": scip_range(occurrence),
                "symbol": occurrence.symbol,
                "symbol_roles": occurrence.symbol_roles,
                "roles": roles,
                "language": document.language,
                "text_encoding": index.text_encoding
            });
            rows.push(OccurrenceRow {
                path: path.clone(),
                symbol: occurrence.symbol.clone(),
                symbol_roles: occurrence.symbol_roles,
                value,
            });
        }
    }
    Ok(rows)
}

fn load_index(
    source_root: &Path,
    boundary: &RuntimeArtifactBoundary,
    index_path: &Path,
) -> Result<LoadedIndex, ScipError> {
    let target = boundary.resolve(index_path).map_err(ScipError::failure)?;
    let metadata = fs::symlink_metadata(&target).map_err(|_| {
        ScipError::failure(format!(
            "SCIP index is not a regular runtime artifact: {}",
            target.display()
        ))
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(ScipError::failure(format!(
            "SCIP index is not a regular runtime artifact: {}",
            target.display()
        )));
    }
    let bytes = fs::read(&target).map_err(|error| {
        ScipError::failure(format!(
            "SCIP index is unreadable: {}: {error}",
            target.display()
        ))
    })?;
    let index = Index::parse_from_bytes(&bytes)
        .map_err(|error| ScipError::failure(format!("SCIP index is invalid: {error}")))?;
    let metadata = index
        .metadata
        .as_ref()
        .ok_or_else(|| ScipError::failure("SCIP index is missing metadata"))?;
    if metadata.project_root.is_empty() {
        return Err(ScipError::failure(
            "SCIP index is missing metadata.project_root",
        ));
    }
    let project_root = index_project_root(&metadata.project_root)?;
    if project_root.strip_prefix(source_root).is_err() {
        return Err(ScipError::failure(format!(
            "SCIP project root is outside requested root: {}",
            project_root.display()
        )));
    }
    let (tool_name, tool_version) = metadata
        .tool_info
        .as_ref()
        .map(|info| (info.name.clone(), info.version.clone()))
        .unwrap_or_default();
    let documents = index
        .documents
        .into_iter()
        .map(|document| {
            Ok(IndexDocument {
                path: relative_source_path(&document.relative_path)?,
                language: document.language,
                occurrences: document.occurrences,
                symbols: document.symbols,
            })
        })
        .collect::<Result<Vec<_>, ScipError>>()?;
    Ok(LoadedIndex {
        path: target.clone(),
        digest: boundary.digest(&target).map_err(ScipError::failure)?,
        project_root,
        tool_name,
        tool_version,
        text_encoding: metadata.text_document_encoding.value().to_string(),
        documents,
        external_symbols: index.external_symbols,
    })
}

fn path_selection(path: &str) -> Result<String, ScipError> {
    if path == "." {
        return Ok(".".to_string());
    }
    if path.is_empty() || path.starts_with('/') || path.contains('\\') || path.contains("//") {
        return Err(ScipError::failure(format!(
            "target path must be root-relative and canonical: {path}"
        )));
    }
    if path.split('/').any(|part| matches!(part, "." | "..")) {
        return Err(ScipError::failure(format!(
            "target path must be root-relative and canonical: {path}"
        )));
    }
    let normalized = path.trim_end_matches('/');
    if normalized.starts_with("./") || normalized.contains("//") {
        return Err(ScipError::failure(format!(
            "target path must be canonical: {path}"
        )));
    }
    Ok(normalized.to_string())
}

fn matches_target(document_path: &str, target: &str) -> bool {
    target == "." || document_path == target || document_path.starts_with(&format!("{target}/"))
}

fn implementation_targets(indexes: &[LoadedIndex]) -> BTreeMap<String, BTreeSet<String>> {
    let mut implementations = BTreeMap::<String, BTreeSet<String>>::new();
    for index in indexes {
        for information in index.external_symbols.iter().chain(
            index
                .documents
                .iter()
                .flat_map(|document| &document.symbols),
        ) {
            if information.symbol.is_empty() {
                continue;
            }
            for relationship in &information.relationships {
                if relationship.is_implementation && !relationship.symbol.is_empty() {
                    implementations
                        .entry(relationship.symbol.clone())
                        .or_default()
                        .insert(information.symbol.clone());
                }
            }
        }
    }
    implementations
}

/// Project bounded definitions, references, and declared implementation relationships.
pub(crate) fn query_indexes(request: &QueryRequest) -> Result<QueryReport, ScipError> {
    if request.indexes.is_empty() {
        return Err(ScipError::failure("at least one --index is required"));
    }
    if request.limit == 0 {
        return Err(ScipError::failure("--limit must be positive"));
    }
    if request.limit > MAX_RESULT_LIMIT {
        return Err(ScipError::failure(format!(
            "--limit must not exceed {MAX_RESULT_LIMIT}"
        )));
    }
    let source_root = fs::canonicalize(&request.root).map_err(|error| {
        ScipError::failure(format!(
            "source root is unavailable: {}: {error}",
            request.root.display()
        ))
    })?;
    let boundary =
        RuntimeArtifactBoundary::for_source(&source_root, Some(&request.runtime_root), false)
            .map_err(ScipError::failure)?;
    let indexes = request
        .indexes
        .iter()
        .map(|index_path| load_index(&source_root, &boundary, index_path))
        .collect::<Result<Vec<_>, _>>()?;
    let targets = request
        .paths
        .iter()
        .map(|path| path_selection(path))
        .collect::<Result<Vec<_>, _>>()?;
    let requested_symbols = request.symbols.iter().cloned().collect::<BTreeSet<_>>();
    let mut selected_symbols = requested_symbols.clone();
    let mut target_documents = BTreeSet::new();
    let mut all_occurrences = Vec::new();
    let mut index_refs = Vec::with_capacity(indexes.len());
    for index in &indexes {
        let project_root = index.project_root.strip_prefix(&source_root).map_err(|_| {
            ScipError::failure(format!(
                "SCIP project root is outside requested root: {}",
                index.project_root.display()
            ))
        })?;
        let project_root_value =
            if project_root.as_os_str().is_empty() || project_root == Path::new(".") {
                ".".to_string()
            } else {
                path_as_posix(project_root)
            };
        let project_prefix = if project_root_value == "." {
            String::new()
        } else {
            project_root_value.clone()
        };
        for document in &index.documents {
            let path = if project_prefix.is_empty() {
                document.path.clone()
            } else {
                format!("{project_prefix}/{}", document.path)
            };
            if targets.iter().any(|target| matches_target(&path, target)) {
                target_documents.insert(path);
            }
        }
        all_occurrences.extend(occurrence_rows(index, &source_root)?);
        index_refs.push(json!({
            "path": relative_posix(&index.path, boundary.root())?,
            "sha256": index.digest,
            "tool": index.tool_name,
            "version": index.tool_version,
            "project_root": project_root_value,
            "text_encoding": index.text_encoding
        }));
    }
    if !targets.is_empty() {
        selected_symbols.extend(
            all_occurrences
                .iter()
                .filter(|occurrence| target_documents.contains(&occurrence.path))
                .map(|occurrence| occurrence.symbol.clone()),
        );
    }
    if targets.is_empty() && requested_symbols.is_empty() {
        return Err(ScipError::failure(
            "query requires at least one --path or --symbol",
        ));
    }
    let definitions = all_occurrences
        .iter()
        .filter(|occurrence| {
            selected_symbols.contains(&occurrence.symbol)
                && occurrence.symbol_roles & DEFINITION_ROLE != 0
        })
        .map(|occurrence| occurrence.value.clone())
        .collect::<Vec<_>>();
    let references = all_occurrences
        .iter()
        .filter(|occurrence| {
            selected_symbols.contains(&occurrence.symbol)
                && occurrence.symbol_roles & DEFINITION_ROLE == 0
        })
        .map(|occurrence| occurrence.value.clone())
        .collect::<Vec<_>>();
    let implementations_by_target = implementation_targets(&indexes);
    let implementation_symbols = selected_symbols
        .iter()
        .flat_map(|symbol| implementations_by_target.get(symbol).into_iter().flatten())
        .cloned()
        .collect::<BTreeSet<_>>();
    let implementations = all_occurrences
        .iter()
        .filter(|occurrence| {
            implementation_symbols.contains(&occurrence.symbol)
                && occurrence.symbol_roles & DEFINITION_ROLE != 0
        })
        .map(|occurrence| occurrence.value.clone())
        .collect::<Vec<_>>();
    let unindexed_targets = targets
        .iter()
        .filter(|target| {
            !target_documents
                .iter()
                .any(|path| matches_target(path, target))
        })
        .cloned()
        .collect::<Vec<_>>();
    let directory_targets = targets
        .iter()
        .filter(|target| *target == "." || source_root.join(Path::new(target.as_str())).is_dir())
        .cloned()
        .collect::<BTreeSet<_>>();
    let status = if !targets.is_empty() && target_documents.is_empty() {
        "unindexed-target"
    } else if !unindexed_targets.is_empty() {
        "partial-target"
    } else if !requested_symbols.is_empty() && definitions.is_empty() && references.is_empty() {
        "symbol-not-indexed"
    } else if selected_symbols.is_empty() {
        "no-indexed-symbols"
    } else {
        "projected"
    };
    let limit = request.limit.min(MAX_RESULT_LIMIT);
    let requested_symbol_list = requested_symbols.into_iter().collect::<Vec<_>>();
    let selected_symbol_list = selected_symbols.into_iter().collect::<Vec<_>>();
    let references_projected = all_occurrences.iter().any(|occurrence| {
        selected_symbol_list
            .binary_search(&occurrence.symbol)
            .is_ok()
    });
    let implementations_declared = selected_symbol_list.iter().any(|symbol| {
        implementations_by_target
            .get(symbol)
            .is_some_and(|values| !values.is_empty())
    });
    let truncated = definitions.len() > limit
        || references.len() > limit
        || implementations.len() > limit
        || targets.len() > limit
        || requested_symbol_list.len() > limit
        || selected_symbol_list.len() > limit
        || unindexed_targets.len() > limit
        || index_refs.len() > limit;
    Ok(QueryReport {
        payload: json!({
            "status": status,
            "requested_target": {
                "paths": targets.iter().take(limit).cloned().collect::<Vec<_>>(),
                "symbols": requested_symbol_list.iter().take(limit).cloned().collect::<Vec<_>>()
            },
            "symbols": selected_symbol_list.iter().take(limit).cloned().collect::<Vec<_>>(),
            "unindexed_targets": unindexed_targets.iter().take(limit).cloned().collect::<Vec<_>>(),
            "index_refs": index_refs.iter().take(limit).cloned().collect::<Vec<_>>(),
            "definitions": definitions.iter().take(limit).cloned().collect::<Vec<_>>(),
            "references": references.iter().take(limit).cloned().collect::<Vec<_>>(),
            "implementations": implementations.iter().take(limit).cloned().collect::<Vec<_>>(),
            "counts": {
                "definitions": definitions.len(),
                "references": references.len(),
                "implementations": implementations.len()
            },
            "truncated": truncated,
            "capabilities": {
                "scip": "available",
                "references": if references_projected {"projected"} else {"unverified"},
                "target_paths": if targets.is_empty() {
                    "not-selected"
                } else if !unindexed_targets.is_empty() || !directory_targets.is_empty() {
                    "partial"
                } else {
                    "indexed"
                },
                "source_freshness": "unverified",
                "implementations": if implementations_declared {"declared"} else {"not-represented"},
                "callers": "not-represented",
                "callees": "not-represented"
            }
        }),
    })
}

const USAGE: &str = "usage: agent-canon scip-index <index|query> [options]\n\n\
index: --root ROOT --runtime-root ROOT --output PATH --language LANGUAGE\n\
       [--project-name NAME] [--project-version VERSION] [--python-environment PATH]\n\
       [--compile-database PATH]\n\
query: --root ROOT --runtime-root ROOT --index PATH... [--path PATH...]\n\
       [--symbol SYMBOL...] [--limit N]\n\
Use --help for this help message.";

enum CliOperation {
    Index(IndexRequest),
    Query(QueryRequest),
}

fn take_option_value(
    args: &[String],
    index: &mut usize,
    option: &str,
    inline: Option<&str>,
) -> Result<String, String> {
    if let Some(value) = inline {
        return Ok(value.to_string());
    }
    let Some(value) = args.get(*index + 1) else {
        return Err(format!("argument {option}: expected one argument"));
    };
    if value.starts_with('-')
        && !(option == "--limit" && crate::python_cli_integer::is_argparse_negative_number(value))
    {
        return Err(format!("argument {option}: expected one argument"));
    }
    *index += 1;
    Ok(value.clone())
}

fn parse_cli(args: &[String]) -> Result<CliOperation, String> {
    let Some(operation) = args.first().map(String::as_str) else {
        return Err("the following arguments are required: operation".to_string());
    };
    if !matches!(operation, "index" | "query") {
        return Err(format!(
            "invalid choice: '{operation}' (choose from 'index', 'query')"
        ));
    }
    let root = env::current_dir().map_err(|error| error.to_string())?;
    let mut root = root;
    let mut runtime_root = None;
    let mut output = None;
    let mut language = None;
    let mut project_name = None;
    let mut project_version = None;
    let mut python_environment = None;
    let mut compile_database = None;
    let mut indexes = Vec::new();
    let mut paths = Vec::new();
    let mut symbols = Vec::new();
    let mut limit = BigInt::from(DEFAULT_RESULT_LIMIT);
    let mut index = 1;
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "-h" | "--help") {
            return Err("__help__".to_string());
        }
        let (option, inline) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        let shared_option = matches!(option, "--root" | "--runtime-root");
        let operation_option = if operation == "index" {
            matches!(
                option,
                "--output"
                    | "--language"
                    | "--project-name"
                    | "--project-version"
                    | "--python-environment"
                    | "--compile-database"
            )
        } else {
            matches!(option, "--index" | "--path" | "--symbol" | "--limit")
        };
        if !shared_option && !operation_option {
            return Err(format!("unrecognized argument: {argument}"));
        }
        let value = take_option_value(args, &mut index, option, inline)?;
        match option {
            "--root" => root = PathBuf::from(value),
            "--runtime-root" => runtime_root = Some(PathBuf::from(value)),
            "--output" => output = Some(PathBuf::from(value)),
            "--language" => language = Some(value),
            "--project-name" => project_name = Some(value),
            "--project-version" => project_version = Some(value),
            "--python-environment" => python_environment = Some(PathBuf::from(value)),
            "--compile-database" => compile_database = Some(PathBuf::from(value)),
            "--index" => indexes.push(PathBuf::from(value)),
            "--path" => paths.push(value),
            "--symbol" => symbols.push(value),
            "--limit" => {
                limit = crate::python_cli_integer::parse(&value)
                    .ok_or_else(|| format!("invalid int value: '{value}'"))?;
            }
            _ => unreachable!("matched SCIP option remains handled"),
        }
        index += 1;
    }
    let runtime_root = runtime_root
        .ok_or_else(|| "the following arguments are required: --runtime-root".to_string())?;
    if operation == "index" {
        let output =
            output.ok_or_else(|| "the following arguments are required: --output".to_string())?;
        let language = language
            .ok_or_else(|| "the following arguments are required: --language".to_string())?;
        return Ok(CliOperation::Index(IndexRequest {
            root,
            runtime_root,
            output,
            language,
            project_name,
            project_version,
            python_environment,
            compile_database,
        }));
    }
    if indexes.is_empty() {
        return Err("the following arguments are required: --index".to_string());
    }
    let limit = if limit <= BigInt::from(0) {
        0
    } else if limit > BigInt::from(MAX_RESULT_LIMIT) {
        MAX_RESULT_LIMIT + 1
    } else {
        limit.to_string().parse::<usize>().unwrap_or(usize::MAX)
    };
    Ok(CliOperation::Query(QueryRequest {
        root,
        runtime_root,
        indexes,
        paths,
        symbols,
        limit,
    }))
}

fn print_json(payload: &Value) {
    println!(
        "{}",
        serde_json::to_string(payload).unwrap_or_else(|_| "{}".to_string())
    );
}

fn print_error(error: ScipError) -> i32 {
    match error.kind {
        ScipErrorKind::UnsupportedCapability => {
            let language = error.language.unwrap_or_default();
            let mut capabilities = serde_json::Map::new();
            capabilities.insert(language.clone(), Value::String("unsupported".to_string()));
            print_json(&json!({
                "status": "unsupported",
                "language": language,
                "reason": error.message,
                "capabilities": capabilities
            }));
            0
        }
        ScipErrorKind::RequiredProjectInput => {
            let language = error.language.unwrap_or_default();
            let mut capabilities = serde_json::Map::new();
            capabilities.insert(
                language.clone(),
                Value::String("input-required".to_string()),
            );
            print_json(&json!({
                "status": "input-required",
                "language": language,
                "reason": error.message,
                "capabilities": capabilities
            }));
            0
        }
        ScipErrorKind::Failure => {
            eprintln!("{}", json!({"status": "failed", "error": error.message}));
            1
        }
    }
}

/// Run the shared `scip-index index|query` command family.
pub fn run(args: &[String]) -> i32 {
    let command = match parse_cli(args) {
        Ok(command) => command,
        Err(error) if error == "__help__" => {
            println!("{USAGE}");
            return 0;
        }
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon scip-index: {error}");
            return 2;
        }
    };
    match command {
        CliOperation::Index(request) => {
            if !matches!(request.language.as_str(), "python" | "cpp") {
                let language = request.language;
                let mut capabilities = serde_json::Map::new();
                capabilities.insert(language.clone(), Value::String("unsupported".to_string()));
                print_json(&json!({
                    "status": "unsupported",
                    "language": language,
                    "capabilities": capabilities
                }));
                return 0;
            }
            match index_project(&request) {
                Ok(report) => {
                    print_json(&report.payload);
                    0
                }
                Err(error) => print_error(error),
            }
        }
        CliOperation::Query(request) => match query_indexes(&request) {
            Ok(report) => {
                print_json(&report.payload);
                0
            }
            Err(error) => print_error(error),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use protobuf::{Message as _, MessageField};
    use scip::types::Metadata;
    use std::cell::RefCell;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

    struct Fixture(PathBuf);

    impl Fixture {
        fn new() -> Self {
            let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
            let timestamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock is after the Unix epoch")
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "agent-canon-scip-index-{}-{timestamp}-{sequence}",
                std::process::id(),
            ));
            fs::create_dir(&path).expect("create unique SCIP fixture root");
            Self(fs::canonicalize(path).expect("resolve SCIP fixture root"))
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
            let runtime = self.0.with_file_name(format!(
                ".{}.agent-canon-runtime",
                self.0
                    .file_name()
                    .and_then(|name| name.to_str())
                    .unwrap_or_default()
            ));
            let _ = fs::remove_dir_all(runtime);
        }
    }

    fn valid_index_bytes(root: &Path) -> Vec<u8> {
        let mut metadata = Metadata::new();
        metadata.project_root = format!("file://{}", root.display());
        let mut index = Index::new();
        index.metadata = MessageField::some(metadata);
        index
            .write_to_bytes()
            .expect("official SCIP index serializes")
    }

    #[test]
    fn manifest_override_expands_named_user_from_injected_account_lookup() {
        let environment = PathExpansionEnvironment {
            home: Some("/home/current-user".into()),
            ..PathExpansionEnvironment::default()
        };
        let home = PathBuf::from("/home/scip-manifest-owner");
        let requests = RefCell::new(Vec::new());

        let expanded = expand_config_override_path_with(
            Path::new("~scip-manifest-owner/bootstrap/container/image/dependencies.toml"),
            "shared tool dependency manifest",
            PathPlatform::Posix,
            &environment,
            |request| {
                requests.borrow_mut().push(request.clone());
                match request {
                    HomeLookupRequest::NamedUser(username) if username == "scip-manifest-owner" => {
                        Ok(Some(home.clone()))
                    }
                    _ => panic!("manifest expansion requests its named account"),
                }
            },
        )
        .expect("named-user manifest override expands");

        assert_eq!(
            expanded,
            home.join("bootstrap/container/image/dependencies.toml")
        );
        assert_eq!(
            requests.borrow().as_slice(),
            &[HomeLookupRequest::NamedUser(
                "scip-manifest-owner".to_string()
            )]
        );
    }

    #[test]
    fn receipts_override_expands_named_user_from_injected_account_lookup() {
        let environment = PathExpansionEnvironment {
            home: Some("/home/current-user".into()),
            ..PathExpansionEnvironment::default()
        };
        let home = PathBuf::from("/home/scip-receipt-owner");
        let requests = RefCell::new(Vec::new());

        let expanded = expand_config_override_path_with(
            Path::new("~scip-receipt-owner/tool-receipts"),
            "shared tool dependency receipts",
            PathPlatform::Posix,
            &environment,
            |request| {
                requests.borrow_mut().push(request.clone());
                match request {
                    HomeLookupRequest::NamedUser(username) if username == "scip-receipt-owner" => {
                        Ok(Some(home.clone()))
                    }
                    _ => panic!("receipt expansion requests its named account"),
                }
            },
        )
        .expect("named-user receipt override expands");

        assert_eq!(expanded, home.join("tool-receipts"));
        assert_eq!(
            requests.borrow().as_slice(),
            &[HomeLookupRequest::NamedUser(
                "scip-receipt-owner".to_string()
            )]
        );
    }

    #[test]
    fn cpp_index_writes_only_to_the_external_runtime_and_preserves_provider_argv() {
        let fixture = Fixture::new();
        let runtime_root = fixture.0.with_file_name(format!(
            ".{}.agent-canon-runtime",
            fixture
                .0
                .file_name()
                .and_then(|name| name.to_str())
                .expect("fixture directory name is UTF-8")
        ));
        let compile_database = fixture.0.join("compile_commands.json");
        fs::write(&compile_database, "[]\n").expect("write compile database input");
        let expected_bytes = valid_index_bytes(&fixture.0);
        let request = IndexRequest {
            root: fixture.0.clone(),
            runtime_root: runtime_root.clone(),
            output: PathBuf::from("runs/cpp/index.scip"),
            language: "cpp".to_string(),
            project_name: None,
            project_version: None,
            python_environment: None,
            compile_database: Some(PathBuf::from("compile_commands.json")),
        };
        let resolved = RefCell::new(Vec::new());
        let commands = RefCell::new(Vec::<Vec<String>>::new());
        let mut resolve_tool = |language: &str| {
            resolved.borrow_mut().push(language.to_string());
            let (executable, record_id, version) = if language == "cpp" {
                ("/fixture/scip-clang", "scip-clang-record", "0.4.0")
            } else {
                ("/fixture/scip", "scip-cli-record", "0.10.0")
            };
            Ok(VerifiedTool {
                executable: PathBuf::from(executable),
                record_id: record_id.to_string(),
                version: version.to_string(),
            })
        };
        let mut run_command =
            |command: &[String], cwd: &Path, environment: &BTreeMap<String, String>| {
                commands.borrow_mut().push(command.to_vec());
                assert_eq!(cwd, fixture.0.as_path());
                assert!(!environment.contains_key("AGENT_CANON_CONTROL_PARENT_ROOT"));
                if Path::new(&command[0])
                    .file_name()
                    .and_then(|name| name.to_str())
                    == Some("scip-clang")
                {
                    let output = command
                        .iter()
                        .find_map(|argument| argument.strip_prefix("--index-output-path="))
                        .expect("SCIP-Clang receives the external index output");
                    fs::write(output, &expected_bytes).map_err(|error| {
                        ScipError::failure(format!("fake indexer cannot write output: {error}"))
                    })?;
                    return Ok(CommandOutput {
                        returncode: 0,
                        stdout: "indexer output\n".to_string(),
                        stderr: String::new(),
                    });
                }
                assert_eq!(
                    Path::new(&command[0])
                        .file_name()
                        .and_then(|name| name.to_str()),
                    Some("scip")
                );
                assert_eq!(command.len(), 4);
                assert_eq!(command[1], "stats");
                assert_eq!(command[2], "--from");
                Ok(CommandOutput {
                    returncode: 0,
                    stdout: "Documents: 1\n".to_string(),
                    stderr: String::new(),
                })
            };

        let report = index_project_with(&request, &mut resolve_tool, &mut run_command)
            .expect("C/C++ index writes to the selected runtime root");

        let output = runtime_root.join("runs/cpp/index.scip");
        assert_eq!(report.payload["status"], "written");
        assert_eq!(report.payload["index"]["path"], "runs/cpp/index.scip");
        assert_eq!(
            report.payload["index"]["sha256"].as_str().unwrap().len(),
            64
        );
        assert_eq!(report.payload["stdout"], "indexer output");
        assert_eq!(report.payload["scip"]["stats"], "Documents: 1");
        assert!(output.is_file());
        assert_eq!(fs::read(&output).unwrap(), expected_bytes);
        assert!(!fixture.0.join("index.scip").exists());
        assert!(runtime_root
            .join("runs/cpp/scip-clang-supplementary-output")
            .is_dir());
        assert_eq!(
            resolved.borrow().clone(),
            vec!["cpp".to_string(), "scip".to_string()]
        );
        let commands = commands.borrow();
        assert!(commands[0].contains(&format!("--compdb-path={}", compile_database)));
        assert!(commands[0].contains(&format!("--index-output-path={output}")));
        assert!(commands[0].contains(&format!(
            "--supplementary-output-dir={}",
            output
                .parent()
                .unwrap()
                .join("scip-clang-supplementary-output")
        )));
        assert_eq!(commands[1][1], "stats");
        assert_eq!(commands[1][2], "--from");
        assert_eq!(commands[1][3], output.to_string_lossy().as_ref());
    }
}
