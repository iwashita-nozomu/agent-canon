// @dependency-start
// contract implementation
// responsibility Dispatches versioned AgentCanon catalog entries through typed tool execution without shell evaluation.
// upstream design ../../../../../documents/design/agent-canon-bootstrap-tool-runtime.md typed catalog and runtime boundary
// upstream design ../../../../catalog.yaml typed runtime catalog
// upstream implementation catalog/tool_catalog.rs owns YAML catalog parsing and shared catalog projections
// upstream implementation runtime_boundary.rs owns shared path resolution and runtime capabilities
// downstream implementation ../../../../bin/agent-canon owns the stable CLI namespace
// downstream implementation ../../../../../tests/agent_tools/test_tool_dispatch.py dispatcher contract harness
// @dependency-end

//! Typed runtime dispatch for AgentCanon catalog entries.
//!
//! Catalog command strings are documentation only. Every executable invocation
//! is built from a descriptor-owned argument vector and child arguments remain
//! separate operating-system arguments throughout dispatch.

use crate::catalog::tool_catalog;
use crate::path_resolution::resolve_non_strict;
use serde_json::{json, Value as JsonValue};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fmt;
use std::fs;
use std::fs::OpenOptions;
use std::io::{self, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};
use yaml_rust2::Yaml;

pub const SCHEMA_VERSION: i64 = 2;
pub const CONTAINER_MARKER: &[u8] = b"agent-canon-tool-container/v1\n";
pub const RUNTIME_MARKER: &[u8] = b"agent-canon-runtime/v1\n";
pub const CONTAINER_MARKER_NAME: &str = ".agent-canon-tool-container";
pub const RUNTIME_MARKER_NAME: &str = ".agent-canon-runtime";
pub const CATALOG_RELATIVE: &str = "tools/catalog.yaml";

const ID_CHARS: &str = "abcdefghijklmnopqrstuvwxyz0123456789-";
const ALLOWED_RUNTIMES: &[&str] = &["python", "rust", "native"];
const ALLOWED_PLANES: &[&str] = &["tool-container"];
const ALLOWED_CWDS: &[&str] = &["source-root", "target-root", "task-root", "explicit"];
const ALLOWED_ENVS: &[&str] = &["allowlisted", "clean"];
const ALLOWED_IO: &[&str] = &["inherited", "captured"];
const ALLOWED_EXITS: &[&str] = &["propagate", "normalize-signal"];
const ALLOWED_SIGNALS: &[&str] = &["propagate", "normalize-signal"];
const ALLOWED_EFFECTS: &[&str] = &["read-only", "external-artifact", "explicit-target-write"];
const ALLOWED_OUTPUT_ROOTS: &[&str] = &["none", "external-runtime", "explicit-target"];
#[cfg(windows)]
const PATH_SEPARATOR: char = ';';
#[cfg(not(windows))]
const PATH_SEPARATOR: char = ':';

const ISSUE_SYNC_RECEIPT_OPTIONS: &[&str] = &[
    "--help",
    "--receipt-preflight",
    "--stage-publication-receipt",
    "--record-publication-receipt",
    "--repo",
    "--receipt-number",
    "--receipt-url",
    "--receipt-state",
    "--receipt-action",
    "--receipt-responsibility",
    "--receipt-occurrence-location",
    "--receipt-source-finding-kind",
    "--receipt-timestamp",
    "--checkout-head",
    "--checkout-repository",
];
const ISSUE_SYNC_OPERATIONS: &[&str] = &[
    "--receipt-preflight",
    "--stage-publication-receipt",
    "--record-publication-receipt",
    "--help",
];

const ENV_ALLOWLIST: &[&str] = &[
    "PATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "TZ",
    "TMPDIR",
    "RUST_BACKTRACE",
    "CARGO_TERM_COLOR",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_DISPATCH_ENTRY_ID",
    "AGENT_CANON_DISPATCH_RUNTIME",
    "AGENT_CANON_OUTPUT_ROOT",
    "AGENT_CANON_CONTROL_PARENT_ROOT",
    "AGENT_CANON_RUNTIME_ROOT",
    "AGENT_CANON_TASK_ROOT",
    "AGENT_CANON_TARGET_ROOT",
    "AGENT_CANON_EXPLICIT_CWD",
    "AGENT_CANON_MOUNT_REGISTRY",
    "AGENT_CANON_HOOK_ARCHIVE_DIR",
    "AGENT_CANON_LOG_ROOT",
];
const BOOTSTRAP_EXEC_ENV: &[&str] = &[
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TZ", "TMPDIR",
];

/// Stable, machine-readable catalog and dispatcher failure.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DispatchError {
    pub code: String,
    pub detail: String,
}

impl DispatchError {
    fn new(code: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            detail: detail.into(),
        }
    }
}

impl fmt::Display for DispatchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "TOOL_DISPATCH_ERROR={}:{}",
            self.code, self.detail
        )
    }
}

impl std::error::Error for DispatchError {}

/// Normalized execution contract for one public tool.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ToolSpec {
    pub tool_id: String,
    pub path: String,
    pub runtime: String,
    pub argv: Vec<String>,
    pub execution_plane: String,
    pub cwd_policy: String,
    pub env_policy: String,
    pub stdin_policy: String,
    pub stdout_policy: String,
    pub stderr_policy: String,
    pub exit_policy: String,
    pub signal_policy: String,
    pub side_effect_policy: String,
    pub output_root: String,
    pub written_paths: Vec<String>,
}

impl ToolSpec {
    /// Project the stable inventory row used by CLI and Rust controller callers.
    pub fn inventory_row(&self) -> JsonValue {
        json!({
            "id": self.tool_id,
            "path": self.path,
            "runtime": self.runtime,
            "argv": self.argv,
            "execution_plane": self.execution_plane,
            "cwd": self.cwd_policy,
            "env": self.env_policy,
            "stdin": self.stdin_policy,
            "stdout": self.stdout_policy,
            "stderr": self.stderr_policy,
            "exit": self.exit_policy,
            "signal": self.signal_policy,
            "side_effect": self.side_effect_policy,
            "output_root": self.output_root,
            "written_paths": self.written_paths,
        })
    }
}

/// Validated runtime portion of the versioned catalog.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ToolCatalog {
    pub root: PathBuf,
    pub schema_version: i64,
    pub specs: BTreeMap<String, ToolSpec>,
}

impl ToolCatalog {
    /// Return the versioned, deterministically ordered JSON inventory.
    pub fn inventory(&self) -> JsonValue {
        let entries = self
            .specs
            .values()
            .map(ToolSpec::inventory_row)
            .collect::<Vec<_>>();
        json!({
            "schema": "agent-canon-tool-inventory/v1",
            "catalog_runtime_schema": self.schema_version,
            "entries": entries,
        })
    }
}

/// Load and validate the runtime descriptors in `tools/catalog.yaml`.
pub fn load_tool_catalog(root: &Path) -> Result<ToolCatalog, DispatchError> {
    let root =
        resolve_non_strict(root).map_err(|error| DispatchError::new("invalid-catalog", error))?;
    let catalog_path = root.join(CATALOG_RELATIVE);
    if !catalog_path.is_file() {
        return Err(DispatchError::new(
            "missing-catalog",
            catalog_path.display().to_string(),
        ));
    }
    let raw = tool_catalog::load_yaml_document(&catalog_path)
        .map_err(|error| DispatchError::new("invalid-catalog", error))?;
    let catalog = mapping(&raw, "catalog")?;
    let schema_value = mapping_field(&catalog, "runtime_schema")
        .ok_or_else(|| DispatchError::new("invalid-type", "runtime_schema"))?;
    let schema = mapping(schema_value, "runtime_schema")?;
    let raw_version = mapping_field(&schema, "version");
    let version = raw_version.and_then(Yaml::as_i64);
    if version != Some(SCHEMA_VERSION) {
        return Err(DispatchError::new(
            "unsupported-schema",
            raw_version.map_or_else(|| "None".to_owned(), yaml_python_string),
        ));
    }

    let entries_value = mapping_field(&catalog, "entries")
        .ok_or_else(|| DispatchError::new("invalid-entries", "entries"))?;
    let entries = tool_catalog::as_sequence(entries_value)
        .ok_or_else(|| DispatchError::new("invalid-entries", "entries"))?;
    let mut specs = BTreeMap::new();
    for (index, raw_entry) in entries.iter().enumerate() {
        let entry = mapping(raw_entry, &format!("entries[{}]", index + 1))?;
        if let Some(spec) = spec_from_entry(entry, None)? {
            if specs.contains_key(&spec.tool_id) {
                return Err(DispatchError::new("duplicate-id", &spec.tool_id));
            }
            specs.insert(spec.tool_id.clone(), spec);
        }
    }

    let rust_commands = match mapping_field(&schema, "rust_public_commands") {
        None | Some(Yaml::Null) => &[][..],
        Some(value) => tool_catalog::as_sequence(value).ok_or_else(|| {
            DispatchError::new(
                "invalid-rust-inventory",
                "runtime_schema.rust_public_commands",
            )
        })?,
    };
    for (index, raw_command) in rust_commands.iter().enumerate() {
        let command = mapping(raw_command, &format!("rust_public_commands[{}]", index + 1))?;
        let identifier = required_string(
            mapping_field(&command, "id"),
            &format!("rust_public_commands[{}].id", index + 1),
        )?;
        let selector = required_string(
            mapping_field(&command, "selector"),
            &format!("rust_public_commands[{}].selector", index + 1),
        )?;
        if selector.chars().any(char::is_whitespace) {
            return Err(DispatchError::new("invalid-rust-selector", identifier));
        }
        let generated_argv = vec!["tools/bin/agent-canon".to_owned(), selector];
        let spec = spec_from_entry(
            command,
            Some(GeneratedDispatch {
                runtime: "rust",
                argv: generated_argv,
            }),
        )?
        .ok_or_else(|| DispatchError::new("invalid-rust-inventory", identifier.clone()))?;
        if specs.contains_key(&spec.tool_id) {
            return Err(DispatchError::new("duplicate-id", &spec.tool_id));
        }
        specs.insert(spec.tool_id.clone(), spec);
    }
    if specs.is_empty() {
        return Err(DispatchError::new(
            "empty-inventory",
            "catalog runtime commands",
        ));
    }
    Ok(ToolCatalog {
        root,
        schema_version: SCHEMA_VERSION,
        specs,
    })
}

/// Build the public inventory projection for one repository root.
pub fn inventory(root: &Path) -> Result<JsonValue, DispatchError> {
    Ok(load_tool_catalog(root)?.inventory())
}

struct GeneratedDispatch {
    runtime: &'static str,
    argv: Vec<String>,
}

fn mapping<'a>(value: &'a Yaml, field: &str) -> Result<Vec<(&'a str, &'a Yaml)>, DispatchError> {
    tool_catalog::as_mapping(value).ok_or_else(|| DispatchError::new("invalid-type", field))
}

fn mapping_field<'a>(mapping: &'a [(&str, &'a Yaml)], field: &str) -> Option<&'a Yaml> {
    mapping
        .iter()
        .find_map(|(key, value)| (*key == field).then_some(*value))
}

fn yaml_python_string(value: &Yaml) -> String {
    match value {
        Yaml::Null => "None".to_owned(),
        Yaml::Boolean(value) => if *value { "True" } else { "False" }.to_owned(),
        Yaml::Integer(value) => value.to_string(),
        Yaml::Real(value) | Yaml::String(value) => value.clone(),
        _ => format!("{value:?}"),
    }
}

fn required_string(value: Option<&Yaml>, field: &str) -> Result<String, DispatchError> {
    let Some(Yaml::String(value)) = value else {
        return Err(DispatchError::new("invalid-type", field));
    };
    if python_strip(value).is_empty() {
        return Err(DispatchError::new("invalid-type", field));
    }
    Ok(value.clone())
}

fn enum_value(
    value: Option<&Yaml>,
    allowed: &[&str],
    field: &str,
) -> Result<String, DispatchError> {
    let result = required_string(value, field)?;
    if !allowed.contains(&result.as_str()) {
        return Err(DispatchError::new(
            "invalid-value",
            format!("{field}={result}"),
        ));
    }
    Ok(result)
}

fn string_list(value: Option<&Yaml>, field: &str) -> Result<Vec<String>, DispatchError> {
    let Some(Yaml::Array(items)) = value else {
        return Err(DispatchError::new("shell-string-rejected", field));
    };
    if items.is_empty()
        || items.iter().any(|item| {
            !matches!(item, Yaml::String(value) if !value.is_empty() && !value.contains('\0'))
        })
    {
        return Err(DispatchError::new("invalid-argv", field));
    }
    Ok(items
        .iter()
        .map(|item| item.as_str().expect("validated string argument").to_owned())
        .collect())
}

fn safe_relative(value: &str, field: &str) -> Result<String, DispatchError> {
    let path = Path::new(value);
    if path.is_absolute()
        || path
            .components()
            .any(|component| component == Component::ParentDir)
    {
        return Err(DispatchError::new(
            "unsafe-path",
            format!("{field}={value}"),
        ));
    }
    Ok(value.to_owned())
}

fn relative_list(value: Option<&Yaml>, field: &str) -> Result<Vec<String>, DispatchError> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    if matches!(value, Yaml::Null) {
        return Ok(Vec::new());
    }
    let Some(items) = tool_catalog::as_sequence(value) else {
        return Err(DispatchError::new("invalid-written-paths", field));
    };
    let mut paths = Vec::with_capacity(items.len());
    for item in items {
        let Some(item) = item.as_str() else {
            return Err(DispatchError::new("invalid-written-paths", field));
        };
        if item.is_empty() || item.contains('*') {
            return Err(DispatchError::new("invalid-written-paths", field));
        }
        paths.push(safe_relative(item, field)?);
    }
    Ok(paths)
}

fn is_public_path(path: &str) -> bool {
    path.ends_with(".py") || path.ends_with(".rs") || path == "tools/bin/agent-canon"
}

fn runtime_for(path: &str) -> &'static str {
    if path.ends_with(".rs") || path == "tools/bin/agent-canon" {
        "rust"
    } else {
        "python"
    }
}

fn spec_from_entry(
    entry: Vec<(&str, &Yaml)>,
    generated: Option<GeneratedDispatch>,
) -> Result<Option<ToolSpec>, DispatchError> {
    let raw_id = mapping_field(&entry, "id");
    let tool_id = match raw_id {
        Some(Yaml::String(value)) if !value.is_empty() => value.clone(),
        Some(value) => return Err(DispatchError::new("invalid-id", yaml_python_string(value))),
        None => return Err(DispatchError::new("invalid-id", "None")),
    };
    if !tool_id
        .chars()
        .all(|character| ID_CHARS.contains(character))
    {
        return Err(DispatchError::new("invalid-id", &tool_id));
    }
    let raw_path = mapping_field(&entry, "path");
    let Some(Yaml::String(raw_path)) = raw_path else {
        return Err(DispatchError::new("invalid-path", &tool_id));
    };
    let path = safe_relative(raw_path, &format!("entry:{tool_id}:path"))?;

    let raw_dispatch = mapping_field(&entry, "dispatch");
    let runtime_override = generated.as_ref().map(|dispatch| dispatch.runtime);
    if !is_public_path(&path) {
        let is_native = raw_dispatch
            .filter(|value| !matches!(value, Yaml::Null))
            .and_then(Yaml::as_hash)
            .and_then(|dispatch| {
                dispatch
                    .iter()
                    .find_map(|(key, value)| (key.as_str() == Some("runtime")).then_some(value))
            })
            .and_then(Yaml::as_str)
            == Some("native");
        if runtime_override.is_none() && !is_native {
            return Ok(None);
        }
    }
    if runtime_override.is_none() && raw_dispatch.is_none_or(|value| matches!(value, Yaml::Null)) {
        return Err(DispatchError::new("missing-dispatch", &tool_id));
    }
    let dispatch = match raw_dispatch.filter(|_| runtime_override.is_none()) {
        Some(value) => Some(mapping(value, &format!("entry:{tool_id}:dispatch"))?),
        None => None,
    };
    let dispatch_value = |field: &str| {
        dispatch
            .as_deref()
            .and_then(|values| mapping_field(values, field))
    };
    let runtime = if let Some(runtime) = runtime_override {
        runtime.to_owned()
    } else {
        enum_value(
            dispatch_value("runtime"),
            ALLOWED_RUNTIMES,
            &format!("entry:{tool_id}:runtime"),
        )
        .or_else(|error| {
            if dispatch_value("runtime").is_none() {
                Ok(runtime_for(&path).to_owned())
            } else {
                Err(error)
            }
        })?
    };
    if !ALLOWED_RUNTIMES.contains(&runtime.as_str()) {
        return Err(DispatchError::new(
            "invalid-value",
            format!("entry:{tool_id}:runtime={runtime}"),
        ));
    }
    let argv = if let Some(generated) = generated {
        if generated.argv.is_empty()
            || generated
                .argv
                .iter()
                .any(|item| item.is_empty() || item.contains('\0'))
        {
            return Err(DispatchError::new(
                "invalid-argv",
                format!("entry:{tool_id}:argv"),
            ));
        }
        generated.argv
    } else {
        string_list(dispatch_value("argv"), &format!("entry:{tool_id}:argv"))?
    };
    let default = |field: &str, value: &str| {
        dispatch_value(field)
            .cloned()
            .unwrap_or_else(|| Yaml::String(value.to_owned()))
    };
    let execution_plane = enum_value(
        Some(&default("execution_plane", "tool-container")),
        ALLOWED_PLANES,
        &format!("entry:{tool_id}:execution_plane"),
    )?;
    let cwd_policy = enum_value(
        Some(&default("cwd", "source-root")),
        ALLOWED_CWDS,
        &format!("entry:{tool_id}:cwd"),
    )?;
    let env_policy = enum_value(
        Some(&default("env", "allowlisted")),
        ALLOWED_ENVS,
        &format!("entry:{tool_id}:env"),
    )?;
    let stdin_policy = enum_value(
        Some(&default("stdin", "inherited")),
        ALLOWED_IO,
        &format!("entry:{tool_id}:stdin"),
    )?;
    let stdout_policy = enum_value(
        Some(&default("stdout", "inherited")),
        ALLOWED_IO,
        &format!("entry:{tool_id}:stdout"),
    )?;
    let stderr_policy = enum_value(
        Some(&default("stderr", "inherited")),
        ALLOWED_IO,
        &format!("entry:{tool_id}:stderr"),
    )?;
    let exit_policy = enum_value(
        Some(&default("exit", "propagate")),
        ALLOWED_EXITS,
        &format!("entry:{tool_id}:exit"),
    )?;
    let signal_policy = enum_value(
        Some(&default("signal", "propagate")),
        ALLOWED_SIGNALS,
        &format!("entry:{tool_id}:signal"),
    )?;
    let writes = mapping_field(&entry, "writes").and_then(Yaml::as_bool) == Some(true);
    let side_effect_policy = enum_value(
        Some(&default(
            "side_effect",
            if writes {
                "external-artifact"
            } else {
                "read-only"
            },
        )),
        ALLOWED_EFFECTS,
        &format!("entry:{tool_id}:side_effect"),
    )?;
    let output_root = enum_value(
        Some(&default(
            "output_root",
            if writes { "external-runtime" } else { "none" },
        )),
        ALLOWED_OUTPUT_ROOTS,
        &format!("entry:{tool_id}:output_root"),
    )?;
    let written_paths = relative_list(
        dispatch_value("written_paths").or_else(|| mapping_field(&entry, "written_paths")),
        &format!("entry:{tool_id}:written_paths"),
    )?;
    if side_effect_policy == "read-only" && !written_paths.is_empty() {
        return Err(DispatchError::new("read-only-written-paths", &tool_id));
    }
    if (side_effect_policy == "external-artifact" && output_root != "external-runtime")
        || (side_effect_policy == "explicit-target-write" && output_root != "explicit-target")
        || (side_effect_policy == "read-only" && output_root != "none")
    {
        return Err(DispatchError::new("output-root-mismatch", &tool_id));
    }
    Ok(Some(ToolSpec {
        tool_id,
        path,
        runtime,
        argv,
        execution_plane,
        cwd_policy,
        env_policy,
        stdin_policy,
        stdout_policy,
        stderr_policy,
        exit_policy,
        signal_policy,
        side_effect_policy,
        output_root,
        written_paths,
    }))
}

fn python_strip(value: &str) -> &str {
    value.trim_matches(|character: char| {
        character.is_whitespace() || matches!(character, '\u{001c}'..='\u{001f}')
    })
}

fn validate_child_route(spec: &ToolSpec, args: &[String]) -> Result<(), DispatchError> {
    if spec.tool_id != "issue-sync" {
        return Ok(());
    }
    let options = args
        .iter()
        .filter(|token| token.starts_with("--"))
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let unsupported = options
        .iter()
        .filter(|option| !ISSUE_SYNC_RECEIPT_OPTIONS.contains(option))
        .copied()
        .collect::<Vec<_>>();
    if !unsupported.is_empty() {
        return Err(DispatchError::new(
            "container-route-restricted",
            format!(
                "issue-sync accepts receipt-only inputs; rejected={}",
                unsupported.join(",")
            ),
        ));
    }
    let operations = options
        .iter()
        .filter(|option| ISSUE_SYNC_OPERATIONS.contains(option))
        .count();
    if operations != 1 {
        return Err(DispatchError::new(
            "container-route-restricted",
            "issue-sync requires exactly one receipt preflight, stage, or help operation",
        ));
    }
    Ok(())
}

fn under(path: &Path, root: &Path) -> bool {
    path.starts_with(root)
}

fn nonempty_env(key: &str) -> Option<std::ffi::OsString> {
    env::var_os(key).filter(|value| !value.is_empty())
}

fn registered_roots(runtime: &Path) -> Result<Vec<PathBuf>, DispatchError> {
    if let Some(registry_value) = nonempty_env("AGENT_CANON_MOUNT_REGISTRY") {
        let registry = PathBuf::from(registry_value);
        let metadata = fs::symlink_metadata(&registry).map_err(|_| {
            DispatchError::new("invalid-mount-registry", registry.display().to_string())
        })?;
        if metadata.file_type().is_symlink()
            || !metadata.is_file()
            || write_accessible(&registry, &metadata)
        {
            return Err(DispatchError::new(
                "invalid-mount-registry",
                registry.display().to_string(),
            ));
        }
        let text = fs::read_to_string(&registry).map_err(|_| {
            DispatchError::new("invalid-mount-registry", registry.display().to_string())
        })?;
        let document = text.parse::<toml_edit::DocumentMut>().map_err(|_| {
            DispatchError::new("invalid-mount-registry", registry.display().to_string())
        })?;
        if document.get("schema").and_then(toml_edit::Item::as_str)
            != Some("agent-canon.mount-registry.v2")
        {
            return Err(DispatchError::new("invalid-mount-registry", "schema"));
        }
        let Some(targets) = document.get("targets") else {
            return Ok(Vec::new());
        };
        let targets = targets
            .as_table()
            .ok_or_else(|| DispatchError::new("invalid-mount-registry", "targets"))?;
        let mut roots = Vec::new();
        for (digest, record) in targets.iter() {
            let has_root = record
                .as_table()
                .and_then(|table| table.get("root"))
                .and_then(toml_edit::Item::as_str)
                .is_some();
            if !has_root {
                continue;
            }
            if !digest
                .chars()
                .all(|character| character.is_ascii_digit() || ('a'..='f').contains(&character))
            {
                return Err(DispatchError::new(
                    "invalid-mount-registry",
                    "target digest",
                ));
            }
            roots.push(PathBuf::from(format!("/targets/{digest}")));
        }
        return Ok(roots);
    }

    let state_path = runtime.join("state.json");
    if !state_path.is_file() {
        return Ok(Vec::new());
    }
    let text = fs::read_to_string(&state_path).map_err(|_| {
        DispatchError::new("invalid-runtime-state", state_path.display().to_string())
    })?;
    let state: JsonValue = serde_json::from_str(&text).map_err(|_| {
        DispatchError::new("invalid-runtime-state", state_path.display().to_string())
    })?;
    let Some(state) = state.as_object() else {
        return Ok(Vec::new());
    };
    let Some(targets) = state.get("targets") else {
        return Ok(Vec::new());
    };
    let Some(targets) = targets.as_object() else {
        return Err(DispatchError::new("invalid-runtime-state", "targets"));
    };
    let mut roots = Vec::new();
    for record in targets.values() {
        let Some(root) = record.as_object().and_then(|record| record.get("root")) else {
            continue;
        };
        let Some(root) = root.as_str() else {
            continue;
        };
        roots.push(
            resolve_non_strict(Path::new(root))
                .map_err(|error| DispatchError::new("invalid-runtime-state", error))?,
        );
    }
    Ok(roots)
}

fn is_writable(metadata: &fs::Metadata) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o222 != 0
    }
    #[cfg(not(unix))]
    {
        !metadata.permissions().readonly()
    }
}

fn write_accessible(path: &Path, metadata: &fs::Metadata) -> bool {
    if !metadata.is_file() {
        return false;
    }
    OpenOptions::new().write(true).open(path).is_ok()
}

fn cwd_for(root: &Path, spec: &ToolSpec, runtime: &Path) -> Result<PathBuf, DispatchError> {
    let value = match spec.cwd_policy.as_str() {
        "source-root" => {
            let cwd = resolve_non_strict(root)
                .map_err(|error| DispatchError::new("invalid-cwd", error))?;
            if !cwd.is_dir() {
                return Err(DispatchError::new("invalid-cwd", cwd.display().to_string()));
            }
            return Ok(cwd);
        }
        "target-root" => nonempty_env("AGENT_CANON_TARGET_ROOT")
            .ok_or_else(|| DispatchError::new("missing-target-root", &spec.tool_id))?,
        "task-root" => nonempty_env("AGENT_CANON_TASK_ROOT")
            .ok_or_else(|| DispatchError::new("missing-task-root", &spec.tool_id))?,
        _ => nonempty_env("AGENT_CANON_EXPLICIT_CWD")
            .ok_or_else(|| DispatchError::new("missing-explicit-cwd", &spec.tool_id))?,
    };
    let cwd = resolve_non_strict(Path::new(&value))
        .map_err(|error| DispatchError::new("invalid-cwd", error))?;
    let registered = registered_roots(runtime)?;
    let tasks = runtime.join("tasks");
    if !registered.iter().any(|target| under(&cwd, target)) && !under(&cwd, &tasks) {
        return Err(DispatchError::new(
            "unregistered-cwd",
            cwd.display().to_string(),
        ));
    }
    if !cwd.is_dir() {
        return Err(DispatchError::new("invalid-cwd", cwd.display().to_string()));
    }
    Ok(cwd)
}

fn output_root(
    spec: &ToolSpec,
    source: &Path,
    runtime: &Path,
    registered: &[PathBuf],
) -> Result<Option<PathBuf>, DispatchError> {
    if spec.output_root == "none" {
        if nonempty_env("AGENT_CANON_OUTPUT_ROOT").is_some() {
            return Err(DispatchError::new("unexpected-output-root", &spec.tool_id));
        }
        return Ok(None);
    }
    let value = nonempty_env("AGENT_CANON_OUTPUT_ROOT")
        .ok_or_else(|| DispatchError::new("missing-output-root", &spec.tool_id))?;
    let output = resolve_non_strict(Path::new(&value))
        .map_err(|error| DispatchError::new("output-root-escape", error))?;
    if spec.output_root == "external-runtime" {
        if !under(&output, runtime) || output == runtime {
            return Err(DispatchError::new(
                "output-root-escape",
                output.display().to_string(),
            ));
        }
        crate::runtime_boundary::validate_external_target(
            source,
            runtime,
            &output,
            "tool output root",
        )
        .map_err(|_| DispatchError::new("output-root-escape", output.display().to_string()))?;
    } else if !registered.iter().any(|target| under(&output, target)) {
        return Err(DispatchError::new(
            "output-root-unregistered",
            output.display().to_string(),
        ));
    }
    Ok(Some(output))
}

fn immutable_file(path: &Path, expected: &[u8], field: &str) -> Result<String, DispatchError> {
    let metadata = fs::metadata(path).map_err(|_| {
        DispatchError::new(
            "container-marker-missing",
            format!("{field}:{}", path.display()),
        )
    })?;
    let content = fs::read(path).map_err(|_| {
        DispatchError::new(
            "container-marker-missing",
            format!("{field}:{}", path.display()),
        )
    })?;
    if is_writable(&metadata) {
        return Err(DispatchError::new(
            "container-marker-writable",
            format!("{field}:{}", path.display()),
        ));
    }
    if content != expected {
        return Err(DispatchError::new("container-marker-invalid", field));
    }
    Ok(sha256_hex(&content))
}

fn validate_container_context(root: &Path) -> Result<(), DispatchError> {
    if env::var("AGENT_CANON_EXECUTION_PLANE").ok().as_deref() != Some("tool-container") {
        return Err(DispatchError::new(
            "container-exec-not-authorized",
            "AGENT_CANON_EXECUTION_PLANE",
        ));
    }
    let image_root_value = required_env("AGENT_CANON_IMAGE_ROOT")?;
    let image_deps_value = required_env("AGENT_CANON_IMAGE_DEPENDENCIES_ROOT")?;
    let tools_root_value = required_env("AGENT_CANON_RUNTIME_TOOLS_ROOT")?;
    let marker_digest = env::var("AGENT_CANON_IMAGE_MARKER_DIGEST").unwrap_or_default();
    let runtime_digest = env::var("AGENT_CANON_RUNTIME_MARKER_DIGEST").unwrap_or_default();
    let image_root = resolve_non_strict(Path::new(&image_root_value))
        .map_err(|error| DispatchError::new("container-runtime-root-invalid", error))?;
    let image_deps = resolve_non_strict(Path::new(&image_deps_value))
        .map_err(|error| DispatchError::new("container-dependency-root-invalid", error))?;
    let tools_root = resolve_non_strict(Path::new(&tools_root_value))
        .map_err(|error| DispatchError::new("container-runtime-root-invalid", error))?;
    let source = resolve_non_strict(root)
        .map_err(|error| DispatchError::new("container-runtime-root-invalid", error))?;
    if source != tools_root || source == image_root {
        return Err(DispatchError::new(
            "container-runtime-root-invalid",
            source.display().to_string(),
        ));
    }
    if image_deps != image_root.join("image-dependencies") {
        return Err(DispatchError::new(
            "container-dependency-root-invalid",
            image_deps.display().to_string(),
        ));
    }
    let observed_image_digest = immutable_file(
        &image_root.join(CONTAINER_MARKER_NAME),
        CONTAINER_MARKER,
        "image",
    )?;
    let observed_runtime_digest = immutable_file(
        &image_root.join("runtime").join(RUNTIME_MARKER_NAME),
        RUNTIME_MARKER,
        "runtime",
    )?;
    if marker_digest != format!("sha256:{observed_image_digest}") {
        return Err(DispatchError::new(
            "container-marker-digest-mismatch",
            "image",
        ));
    }
    if runtime_digest != format!("sha256:{observed_runtime_digest}") {
        return Err(DispatchError::new(
            "container-marker-digest-mismatch",
            "runtime",
        ));
    }
    let dependencies = image_deps.join("plan.json");
    let metadata = fs::metadata(&dependencies).map_err(|_| {
        DispatchError::new(
            "container-dependency-plan-invalid",
            dependencies.display().to_string(),
        )
    })?;
    if is_writable(&metadata) {
        return Err(DispatchError::new(
            "container-dependency-plan-writable",
            dependencies.display().to_string(),
        ));
    }
    let text = fs::read_to_string(&dependencies).map_err(|_| {
        DispatchError::new(
            "container-dependency-plan-invalid",
            dependencies.display().to_string(),
        )
    })?;
    let plan: JsonValue = serde_json::from_str(&text).map_err(|_| {
        DispatchError::new(
            "container-dependency-plan-invalid",
            dependencies.display().to_string(),
        )
    })?;
    if !plan
        .as_object()
        .and_then(|plan| plan.get("schema"))
        .is_some_and(json_truthy)
    {
        return Err(DispatchError::new(
            "container-dependency-plan-invalid",
            dependencies.display().to_string(),
        ));
    }
    Ok(())
}

fn json_truthy(value: &JsonValue) -> bool {
    match value {
        JsonValue::Null => false,
        JsonValue::Bool(value) => *value,
        JsonValue::Number(value) => {
            value.as_i64().is_some_and(|number| number != 0)
                || value.as_u64().is_some_and(|number| number != 0)
                || value.as_f64().is_some_and(|number| number != 0.0)
        }
        JsonValue::String(value) => !value.is_empty(),
        JsonValue::Array(value) => !value.is_empty(),
        JsonValue::Object(value) => !value.is_empty(),
    }
}

fn required_env(key: &str) -> Result<String, DispatchError> {
    env::var(key)
        .ok()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            DispatchError::new(
                "container-marker-missing",
                "AGENT_CANON_IMAGE_ROOT, AGENT_CANON_IMAGE_DEPENDENCIES_ROOT, AGENT_CANON_RUNTIME_TOOLS_ROOT",
            )
        })
}

fn resolve_container_argv(
    root: &Path,
    spec: &ToolSpec,
    args: &[String],
) -> Result<Vec<String>, DispatchError> {
    if args.iter().any(|item| item.contains('\0')) {
        return Err(DispatchError::new("invalid-argv", &spec.tool_id));
    }
    let mut command = spec.argv.clone();
    command.extend_from_slice(args);
    let cache_root = nonempty_env("AGENT_CANON_CACHE_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/var/lib/agent-canon/cache"));
    for (index, value) in command.iter_mut().take(spec.argv.len()).enumerate() {
        if index == 0 && matches!(value.as_str(), "python" | "python3") {
            *value = find_executable("python3")
                .map(|path| path.display().to_string())
                .unwrap_or_else(|| "python3".to_owned());
            continue;
        }
        if value == "tools/bin/agent-canon" {
            *value = cache_root
                .join("bin")
                .join("agent-canon")
                .display()
                .to_string();
        } else if value.starts_with("tools/") && root.join(&*value).is_file() {
            *value = root.join(&*value).display().to_string();
        }
    }
    Ok(command)
}

fn find_executable(name: &str) -> Option<PathBuf> {
    let path_value = env::var_os("PATH")?;
    env::split_paths(&path_value)
        .map(|directory| directory.join(name))
        .find(|candidate| is_executable_file(candidate))
}

fn environment(
    root: &Path,
    spec: &ToolSpec,
    runtime: &Path,
    output: Option<&Path>,
) -> Result<BTreeMap<String, String>, DispatchError> {
    let mut result = BTreeMap::new();
    if spec.env_policy == "allowlisted" {
        for key in ENV_ALLOWLIST {
            if let Ok(value) = env::var(key) {
                result.insert((*key).to_owned(), value);
            }
        }
    }
    let source_root = root.display().to_string();
    result.insert("AGENT_CANON_SOURCE_ROOT".to_owned(), source_root.clone());
    result.insert("AGENT_CANON_ROOT".to_owned(), source_root.clone());
    result.insert(
        "AGENT_CANON_DISPATCH_ENTRY_ID".to_owned(),
        spec.tool_id.clone(),
    );
    result.insert(
        "AGENT_CANON_DISPATCH_RUNTIME".to_owned(),
        spec.runtime.clone(),
    );
    result.insert(
        "AGENT_CANON_RUNTIME_ROOT".to_owned(),
        runtime.display().to_string(),
    );
    let inherited_pythonpath = result.get("PYTHONPATH").cloned().unwrap_or_default();
    let source_path = resolve_non_strict(root)
        .map_err(|error| DispatchError::new("invalid-catalog", error))?
        .display()
        .to_string();
    let mut pythonpath = vec![source_path.clone()];
    pythonpath.extend(
        inherited_pythonpath
            .split(PATH_SEPARATOR)
            .filter(|entry| !entry.is_empty() && *entry != source_path)
            .map(str::to_owned),
    );
    result.insert(
        "PYTHONPATH".to_owned(),
        pythonpath.join(&PATH_SEPARATOR.to_string()),
    );
    if let Some(output) = output {
        result.insert(
            "AGENT_CANON_OUTPUT_ROOT".to_owned(),
            output.display().to_string(),
        );
    }
    for key in [
        "AGENT_CANON_CONTROL_PARENT_ROOT",
        "AGENT_CANON_TASK_ROOT",
        "AGENT_CANON_TARGET_ROOT",
        "AGENT_CANON_EXPLICIT_CWD",
    ] {
        if let Ok(value) = env::var(key) {
            if !value.is_empty() {
                result.insert(key.to_owned(), value);
            }
        }
    }
    if let Some(target_root) = result
        .get("AGENT_CANON_TARGET_ROOT")
        .filter(|target_root| !target_root.is_empty())
    {
        let target_root = resolve_non_strict(Path::new(target_root))
            .map_err(|error| DispatchError::new("invalid-cwd", error))?;
        result.insert("GIT_CONFIG_COUNT".to_owned(), "1".to_owned());
        result.insert("GIT_CONFIG_KEY_0".to_owned(), "safe.directory".to_owned());
        result.insert(
            "GIT_CONFIG_VALUE_0".to_owned(),
            target_root.display().to_string(),
        );
    }
    Ok(result)
}

fn require_external_runtime(root: &Path) -> Result<(PathBuf, PathBuf), DispatchError> {
    let control_value = nonempty_env("AGENT_CANON_CONTROL_PARENT_ROOT").ok_or_else(|| {
        DispatchError::new(
            "runtime-root-required",
            "AGENT_CANON_CONTROL_PARENT_ROOT and AGENT_CANON_RUNTIME_ROOT",
        )
    })?;
    let runtime_value = nonempty_env("AGENT_CANON_RUNTIME_ROOT").ok_or_else(|| {
        DispatchError::new(
            "runtime-root-required",
            "AGENT_CANON_CONTROL_PARENT_ROOT and AGENT_CANON_RUNTIME_ROOT",
        )
    })?;
    let control = resolve_non_strict(Path::new(&control_value))
        .map_err(|error| DispatchError::new("runtime-root-missing", error))?;
    let runtime = resolve_non_strict(Path::new(&runtime_value))
        .map_err(|error| DispatchError::new("runtime-root-missing", error))?;
    let source = resolve_non_strict(root)
        .map_err(|error| DispatchError::new("runtime-root-inside-source", error))?;
    if !control.is_dir() || !runtime.is_dir() {
        return Err(DispatchError::new(
            "runtime-root-missing",
            format!("{}:{}", control.display(), runtime.display()),
        ));
    }
    if runtime == source || runtime.starts_with(&source) {
        return Err(DispatchError::new(
            "runtime-root-inside-source",
            runtime.display().to_string(),
        ));
    }
    if runtime != control && !runtime.starts_with(&control) {
        return Err(DispatchError::new(
            "runtime-root-outside-control",
            runtime.display().to_string(),
        ));
    }
    Ok((control, runtime))
}

fn bootstrap_command(
    root: &Path,
    runtime: &Path,
    spec: &ToolSpec,
    args: &[String],
    cwd: &Path,
    output: Option<&Path>,
) -> Result<(Vec<String>, BTreeMap<String, String>), DispatchError> {
    let bootstrap = root.join("bootstrap.sh");
    if !is_executable_file(&bootstrap) {
        return Err(DispatchError::new(
            "bootstrap-unavailable",
            bootstrap.display().to_string(),
        ));
    }
    let control_value = nonempty_env("AGENT_CANON_CONTROL_PARENT_ROOT").ok_or_else(|| {
        DispatchError::new("runtime-root-required", "AGENT_CANON_CONTROL_PARENT_ROOT")
    })?;
    let control = resolve_non_strict(Path::new(&control_value))
        .map_err(|error| DispatchError::new("runtime-root-missing", error))?;
    let registered = registered_roots(runtime)?;
    let target_root = if let Some(target_value) = nonempty_env("AGENT_CANON_TARGET_ROOT") {
        let target = resolve_non_strict(Path::new(&target_value))
            .map_err(|error| DispatchError::new("target-root-unregistered", error))?;
        if !registered.contains(&target) {
            return Err(DispatchError::new(
                "target-root-unregistered",
                target.display().to_string(),
            ));
        }
        target
    } else if registered.len() == 1 {
        registered[0].clone()
    } else {
        return Err(DispatchError::new(
            "target-root-required",
            "set AGENT_CANON_TARGET_ROOT when zero or multiple targets are registered",
        ));
    };
    let target_digest = sha256_hex(target_root.to_string_lossy().as_bytes());
    let source_root =
        resolve_non_strict(root).map_err(|error| DispatchError::new("invalid-catalog", error))?;
    let child_environment = environment(&source_root, spec, runtime, output)?;
    let request = json!({
        "schema": "agent-canon.tool-exec-request.v1",
        "tool_id": spec.tool_id,
        "argv": spec.argv.iter().chain(args).collect::<Vec<_>>(),
        "source_root": source_root.display().to_string(),
        "cwd": cwd.display().to_string(),
        "cwd_policy": spec.cwd_policy,
        "target_root": target_root.display().to_string(),
        "child_args": args,
        "environment": child_environment,
        "stdin": spec.stdin_policy,
        "stdout": spec.stdout_policy,
        "stderr": spec.stderr_policy,
        "exit": spec.exit_policy,
        "signal": spec.signal_policy,
        "side_effect": spec.side_effect_policy,
        "output_root": output.map(|path| path.display().to_string()),
        "written_paths": spec.written_paths,
    });
    let request_json = serde_json::to_string(&request)
        .map_err(|error| DispatchError::new("request-serialization-failed", error.to_string()))?;
    let command = vec![
        bootstrap.display().to_string(),
        "--repository-root".to_owned(),
        source_root.display().to_string(),
        "--control-parent-root".to_owned(),
        control.display().to_string(),
        "--runtime-root".to_owned(),
        runtime.display().to_string(),
        "exec".to_owned(),
        "--target-digest".to_owned(),
        target_digest,
        "--request-json".to_owned(),
        request_json,
    ];
    let mut command_environment = BTreeMap::new();
    for key in BOOTSTRAP_EXEC_ENV {
        if let Ok(value) = env::var(key) {
            command_environment.insert((*key).to_owned(), value);
        }
    }
    command_environment.insert(
        "AGENT_CANON_CONTROL_PARENT_ROOT".to_owned(),
        control.display().to_string(),
    );
    command_environment.insert(
        "AGENT_CANON_RUNTIME_ROOT".to_owned(),
        runtime.display().to_string(),
    );
    Ok((command, command_environment))
}

fn is_executable_file(path: &Path) -> bool {
    let Ok(metadata) = fs::metadata(path) else {
        return false;
    };
    if !metadata.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        true
    }
}

fn sha256_hex(value: &[u8]) -> String {
    let digest = Sha256::digest(value);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn run_process(
    argv: &[String],
    cwd: &Path,
    environment: &BTreeMap<String, String>,
    stream_policies: [&str; 3],
    error_code: &str,
    tool_id: &str,
) -> Result<i32, DispatchError> {
    let [stdin_policy, stdout_policy, stderr_policy] = stream_policies;
    let Some(program) = argv.first() else {
        return Err(DispatchError::new("invalid-argv", tool_id));
    };
    if argv.iter().any(|value| value.contains('\0')) {
        return Err(DispatchError::new("invalid-argv", tool_id));
    }
    let mut command = Command::new(program);
    command
        .args(&argv[1..])
        .current_dir(cwd)
        .env_clear()
        .envs(environment);
    command.stdin(if stdin_policy == "captured" {
        Stdio::piped()
    } else {
        Stdio::inherit()
    });
    command.stdout(if stdout_policy == "captured" {
        Stdio::piped()
    } else {
        Stdio::inherit()
    });
    command.stderr(if stderr_policy == "captured" {
        Stdio::piped()
    } else {
        Stdio::inherit()
    });
    let mut child = command
        .spawn()
        .map_err(|error| DispatchError::new(error_code, format!("{tool_id}:{error}")))?;
    if stdout_policy == "captured" || stderr_policy == "captured" || stdin_policy == "captured" {
        let output = child
            .wait_with_output()
            .map_err(|error| DispatchError::new(error_code, format!("{tool_id}:{error}")))?;
        if stdout_policy == "captured" {
            io::stdout()
                .write_all(&output.stdout)
                .and_then(|()| io::stdout().flush())
                .map_err(|error| {
                    DispatchError::new("process-output-forward-failed", error.to_string())
                })?;
        }
        if stderr_policy == "captured" {
            io::stderr()
                .write_all(&output.stderr)
                .and_then(|()| io::stderr().flush())
                .map_err(|error| {
                    DispatchError::new("process-output-forward-failed", error.to_string())
                })?;
        }
        Ok(status_code(output.status))
    } else {
        let status = child
            .wait()
            .map_err(|error| DispatchError::new(error_code, format!("{tool_id}:{error}")))?;
        Ok(status_code(status))
    }
}

fn status_code(status: ExitStatus) -> i32 {
    if let Some(code) = status.code() {
        return code;
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        128 + status.signal().unwrap_or(0)
    }
    #[cfg(not(unix))]
    {
        1
    }
}

fn run_container_spec(root: &Path, spec: &ToolSpec, args: &[String]) -> Result<i32, DispatchError> {
    validate_container_context(root)?;
    let runtime_value = nonempty_env("AGENT_CANON_RUNTIME_ROOT")
        .ok_or_else(|| DispatchError::new("runtime-root-required", "AGENT_CANON_RUNTIME_ROOT"))?;
    let runtime = resolve_non_strict(Path::new(&runtime_value))
        .map_err(|error| DispatchError::new("runtime-root-required", error))?;
    let registered = registered_roots(&runtime)?;
    let cwd = cwd_for(root, spec, &runtime)?;
    let output = output_root(spec, root, &runtime, &registered)?;
    if let Some(output) = output
        .as_ref()
        .filter(|_| spec.output_root == "external-runtime")
    {
        let relative_output = output.strip_prefix(&runtime).map_err(|_| {
            DispatchError::new(
                "output-root-unavailable",
                format!("{}:{}", spec.tool_id, output.display()),
            )
        })?;
        let boundary = crate::runtime_boundary::RuntimeArtifactBoundary::for_source(
            root,
            Some(&runtime),
            false,
        )
        .map_err(|_| {
            DispatchError::new(
                "output-root-unavailable",
                format!("{}:{}", spec.tool_id, output.display()),
            )
        })?;
        boundary.ensure_directory(relative_output).map_err(|_| {
            DispatchError::new(
                "output-root-unavailable",
                format!("{}:{}", spec.tool_id, output.display()),
            )
        })?;
    }
    let command = resolve_container_argv(root, spec, args)?;
    let child_environment = environment(root, spec, &runtime, output.as_deref())?;
    run_process(
        &command,
        &cwd,
        &child_environment,
        [&spec.stdin_policy, &spec.stdout_policy, &spec.stderr_policy],
        "container-exec-failed",
        &spec.tool_id,
    )
}

fn run_spec(
    root: &Path,
    spec: &ToolSpec,
    args: &[String],
    container_exec: bool,
) -> Result<i32, DispatchError> {
    validate_child_route(spec, args)?;
    if container_exec {
        return run_container_spec(root, spec, args);
    }
    let runtime_value = nonempty_env("AGENT_CANON_RUNTIME_ROOT")
        .ok_or_else(|| DispatchError::new("runtime-root-required", "AGENT_CANON_RUNTIME_ROOT"))?;
    let runtime = resolve_non_strict(Path::new(&runtime_value))
        .map_err(|error| DispatchError::new("runtime-root-required", error))?;
    let registered = registered_roots(&runtime)?;
    let cwd = cwd_for(root, spec, &runtime)?;
    let output = output_root(spec, root, &runtime, &registered)?;
    let (command, child_environment) =
        bootstrap_command(root, &runtime, spec, args, &cwd, output.as_deref())?;
    run_process(
        &command,
        root,
        &child_environment,
        ["inherited", "inherited", "inherited"],
        "bootstrap-exec-failed",
        &spec.tool_id,
    )
}

/// Ask bootstrap to execute one typed catalog entry.
pub fn run_tool(root: &Path, spec: &ToolSpec, args: &[String]) -> Result<i32, DispatchError> {
    run_spec(root, spec, args, false)
}

/// Run one typed catalog entry inside the authenticated tool container.
pub fn run_container_tool(
    root: &Path,
    spec: &ToolSpec,
    args: &[String],
) -> Result<i32, DispatchError> {
    run_spec(root, spec, args, true)
}

fn run_rust_cli(root: &Path, args: &[String]) -> Result<i32, DispatchError> {
    let runtime_value = nonempty_env("AGENT_CANON_RUNTIME_ROOT")
        .ok_or_else(|| DispatchError::new("runtime-root-required", "AGENT_CANON_RUNTIME_ROOT"))?;
    let control_value = nonempty_env("AGENT_CANON_CONTROL_PARENT_ROOT").ok_or_else(|| {
        DispatchError::new("runtime-root-required", "AGENT_CANON_CONTROL_PARENT_ROOT")
    })?;
    let runtime = resolve_non_strict(Path::new(&runtime_value))
        .map_err(|error| DispatchError::new("runtime-root-required", error))?;
    let control = resolve_non_strict(Path::new(&control_value))
        .map_err(|error| DispatchError::new("runtime-root-required", error))?;
    let registered = registered_roots(&runtime)?;
    let target = if let Some(target_value) = nonempty_env("AGENT_CANON_TARGET_ROOT") {
        let target = resolve_non_strict(Path::new(&target_value))
            .map_err(|error| DispatchError::new("target-root-unregistered", error))?;
        if !registered.contains(&target) {
            return Err(DispatchError::new(
                "target-root-unregistered",
                target.display().to_string(),
            ));
        }
        target
    } else if registered.len() == 1 {
        registered[0].clone()
    } else {
        return Err(DispatchError::new(
            "target-root-required",
            "select one registered target",
        ));
    };
    let mut command = vec![
        root.join("bootstrap.sh").display().to_string(),
        "--control-parent-root".to_owned(),
        control.display().to_string(),
        "--runtime-root".to_owned(),
        runtime.display().to_string(),
        "exec".to_owned(),
        "--root".to_owned(),
        target.display().to_string(),
        "--".to_owned(),
        "agent-canon".to_owned(),
    ];
    command.extend_from_slice(args);
    let mut child_environment = BTreeMap::new();
    for key in BOOTSTRAP_EXEC_ENV {
        if let Ok(value) = env::var(key) {
            child_environment.insert((*key).to_owned(), value);
        }
    }
    run_process(
        &command,
        root,
        &child_environment,
        ["inherited", "inherited", "inherited"],
        "bootstrap-exec-failed",
        "rust-cli",
    )
}

fn parse_run(args: &[String]) -> Result<(PathBuf, String, Vec<String>), DispatchError> {
    let mut root =
        env::current_dir().map_err(|error| DispatchError::new("invalid-cwd", error.to_string()))?;
    let mut index = 0;
    while index < args.len() && args[index] != "--" {
        let token = &args[index];
        if token == "--root" {
            if index + 1 >= args.len() {
                return Err(DispatchError::new("missing-option-value", "--root"));
            }
            root = PathBuf::from(&args[index + 1]);
            index += 2;
            continue;
        }
        if token.starts_with('-') {
            return Err(DispatchError::new("unknown-option", token));
        }
        break;
    }
    if index >= args.len() || args[index] == "--" {
        return Err(DispatchError::new(
            "missing-catalog-id",
            "run <catalog-id> -- <args...>",
        ));
    }
    let tool_id = args[index].clone();
    if tool_id.is_empty()
        || !tool_id
            .chars()
            .all(|character| ID_CHARS.contains(character))
    {
        return Err(DispatchError::new("invalid-id", &tool_id));
    }
    index += 1;
    if index >= args.len() || args[index] != "--" {
        return Err(DispatchError::new("missing-argument-delimiter", &tool_id));
    }
    Ok((root, tool_id, args[index + 1..].to_vec()))
}

fn parse_inventory(args: &[String]) -> Result<(PathBuf, bool), DispatchError> {
    let mut root =
        env::current_dir().map_err(|error| DispatchError::new("invalid-cwd", error.to_string()))?;
    let mut as_json = false;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => {
                if index + 1 >= args.len() {
                    return Err(DispatchError::new("missing-option-value", "--root"));
                }
                root = PathBuf::from(&args[index + 1]);
                index += 2;
            }
            "--json" => {
                as_json = true;
                index += 1;
            }
            token => return Err(DispatchError::new("unknown-option", token)),
        }
    }
    Ok((root, as_json))
}

fn print_error(error: DispatchError) -> i32 {
    eprintln!("{error}");
    2
}

/// Execute the stable `agent-canon tool` CLI route.
pub fn run_cli(args: &[String]) -> i32 {
    if args.is_empty() {
        eprintln!("usage: agent-canon tool <run|inventory|rust-cli> [options]");
        return 2;
    }
    let mut arguments = args.to_vec();
    let prefix_end = arguments
        .iter()
        .position(|argument| argument == "--")
        .unwrap_or(arguments.len());
    let mut container_exec = false;
    if let Some(index) = arguments[..prefix_end]
        .iter()
        .position(|argument| argument == "--container-exec")
    {
        container_exec = true;
        arguments.remove(index);
    }
    if arguments
        .first()
        .is_some_and(|argument| argument == "--root")
    {
        if arguments.len() < 3 {
            return print_error(DispatchError::new("missing-option-value", "--root"));
        }
        let command = arguments[2].clone();
        let root = arguments[1].clone();
        arguments.drain(..3);
        arguments.insert(0, command);
        arguments.insert(1, "--root".to_owned());
        arguments.insert(2, root);
    }
    if container_exec
        && !arguments
            .first()
            .is_some_and(|argument| argument == "--root" || argument == "run")
    {
        return print_error(DispatchError::new(
            "container-exec-command-invalid",
            arguments.first().map_or("".to_owned(), Clone::clone),
        ));
    }
    if arguments
        .first()
        .is_some_and(|argument| argument == "inventory")
    {
        let (root, as_json) = match parse_inventory(&arguments[1..]) {
            Ok(parsed) => parsed,
            Err(error) => return print_error(error),
        };
        let inventory = match inventory(&root) {
            Ok(value) => value,
            Err(error) => return print_error(error),
        };
        if as_json {
            match serde_json::to_string(&inventory) {
                Ok(value) => println!("{value}"),
                Err(error) => {
                    return print_error(DispatchError::new(
                        "inventory-serialization-failed",
                        error.to_string(),
                    ))
                }
            }
        } else if let Some(entries) = inventory.get("entries").and_then(JsonValue::as_array) {
            for entry in entries {
                if let Some(tool_id) = entry.get("id").and_then(JsonValue::as_str) {
                    println!("{tool_id}");
                }
            }
        }
        return 0;
    }
    if arguments
        .first()
        .is_some_and(|argument| argument == "rust-cli")
    {
        let result = (|| {
            let mut root = env::current_dir()
                .map_err(|error| DispatchError::new("invalid-cwd", error.to_string()))?;
            let mut index = 1;
            if arguments
                .get(index)
                .is_some_and(|argument| argument == "--root")
            {
                if index + 1 >= arguments.len() {
                    return Err(DispatchError::new("missing-option-value", "--root"));
                }
                root = PathBuf::from(&arguments[index + 1]);
                index += 2;
            }
            if index >= arguments.len() || arguments[index] != "--" {
                return Err(DispatchError::new("missing-argument-delimiter", "rust-cli"));
            }
            require_external_runtime(&root)?;
            if container_exec {
                return Err(DispatchError::new(
                    "container-exec-command-invalid",
                    "rust-cli",
                ));
            }
            run_rust_cli(&root, &arguments[index + 1..])
        })();
        return result.unwrap_or_else(print_error);
    }
    if !arguments.first().is_some_and(|argument| argument == "run") {
        return print_error(DispatchError::new(
            "unknown-command",
            arguments.first().map_or("".to_owned(), Clone::clone),
        ));
    }
    let result = (|| {
        let (root, tool_id, child_args) = parse_run(&arguments[1..])?;
        require_external_runtime(&root)?;
        let catalog = load_tool_catalog(&root)?;
        let spec = catalog
            .specs
            .get(&tool_id)
            .ok_or_else(|| DispatchError::new("unknown-id", &tool_id))?;
        let root = resolve_non_strict(&root)
            .map_err(|error| DispatchError::new("invalid-catalog", error))?;
        if container_exec {
            run_container_tool(&root, spec, &child_args)
        } else {
            run_tool(&root, spec, &child_args)
        }
    })();
    match result {
        Ok(status) => status,
        Err(error) => print_error(error),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temporary_directory() -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock is after the Unix epoch")
            .as_nanos();
        let directory = env::temp_dir().join(format!(
            "agent-canon-tool-dispatch-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&directory).expect("create temporary test directory");
        directory
    }

    #[test]
    fn marker_contract_is_stable() {
        assert_eq!(CONTAINER_MARKER, b"agent-canon-tool-container/v1\n");
        assert_eq!(RUNTIME_MARKER, b"agent-canon-runtime/v1\n");
        assert_eq!(CONTAINER_MARKER_NAME, ".agent-canon-tool-container");
        assert_eq!(RUNTIME_MARKER_NAME, ".agent-canon-runtime");
    }

    #[test]
    fn immutable_marker_requires_exact_read_only_bytes() {
        let directory = temporary_directory();
        let marker = directory.join(CONTAINER_MARKER_NAME);
        fs::write(&marker, CONTAINER_MARKER).expect("write marker fixture");
        let mut permissions = fs::metadata(&marker)
            .expect("read marker metadata")
            .permissions();
        permissions.set_readonly(true);
        fs::set_permissions(&marker, permissions).expect("make marker read-only");
        assert_eq!(
            immutable_file(&marker, CONTAINER_MARKER, "image").expect("valid marker"),
            sha256_hex(CONTAINER_MARKER)
        );
        fs::remove_dir_all(directory).expect("remove marker fixture");
    }

    #[test]
    fn immutable_marker_rejects_writable_or_changed_files() {
        let directory = temporary_directory();
        let marker = directory.join(RUNTIME_MARKER_NAME);
        fs::write(&marker, RUNTIME_MARKER).expect("write marker fixture");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut permissions = fs::metadata(&marker)
                .expect("read marker metadata")
                .permissions();
            permissions.set_mode(0o644);
            fs::set_permissions(&marker, permissions).expect("make marker writable");
        }
        assert_eq!(
            immutable_file(&marker, RUNTIME_MARKER, "runtime")
                .expect_err("writable marker is rejected")
                .code,
            "container-marker-writable"
        );
        let mut permissions = fs::metadata(&marker)
            .expect("read marker metadata")
            .permissions();
        permissions.set_readonly(true);
        fs::set_permissions(&marker, permissions).expect("make marker read-only");
        assert_eq!(
            immutable_file(&marker, CONTAINER_MARKER, "runtime")
                .expect_err("changed marker is rejected")
                .code,
            "container-marker-invalid"
        );
        fs::remove_dir_all(directory).expect("remove marker fixture");
    }

    #[test]
    fn inventory_rows_keep_the_legacy_field_projection() {
        let spec = ToolSpec {
            tool_id: "echo".to_owned(),
            path: "tools/echo.py".to_owned(),
            runtime: "python".to_owned(),
            argv: vec!["python3".to_owned(), "tools/echo.py".to_owned()],
            execution_plane: "tool-container".to_owned(),
            cwd_policy: "source-root".to_owned(),
            env_policy: "allowlisted".to_owned(),
            stdin_policy: "inherited".to_owned(),
            stdout_policy: "inherited".to_owned(),
            stderr_policy: "inherited".to_owned(),
            exit_policy: "propagate".to_owned(),
            signal_policy: "propagate".to_owned(),
            side_effect_policy: "read-only".to_owned(),
            output_root: "none".to_owned(),
            written_paths: Vec::new(),
        };
        let row = spec.inventory_row();
        assert_eq!(row["id"], "echo");
        assert_eq!(row["cwd"], "source-root");
        assert_eq!(row["env"], "allowlisted");
        assert_eq!(row["argv"][0], "python3");
        assert!(row.get("cwd_policy").is_none());
    }
}
