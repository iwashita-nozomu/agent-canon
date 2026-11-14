//! Native resident controller for the AgentCanon shared tool runtime.
// @dependency-start
// contract implementation
// responsibility Owns resident lifecycle state, registered target control, bounded tool execution, template export, and eval spool operations after the Host performs Docker changes.
// upstream implementation ../../../../../bootstrap/host/lifecycle/entrypoint.sh dispatches native controller operations
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/runtime_boundary.rs owns no-follow external runtime boundaries
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/tool_dispatch.rs owns catalog command execution
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/log_repository_identity.rs owns canonical source identity
// downstream test ../tests/bootstrap_runtime_native.rs validates native controller lifecycle and command behavior
// @dependency-end

use crate::log_repository_identity::{normalize_remote, stable_source_repository_id};
use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt};
use cap_std::ambient_authority;
use cap_std::fs::{Dir, DirBuilder, OpenOptions};
#[cfg(unix)]
use cap_std::fs::{DirBuilderExt, OpenOptionsExt, Permissions, PermissionsExt};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::ffi::OsString;
use std::fs;
use std::io::{Read, Write};
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt as StdPermissionsExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const SCHEMA_STATE: &str = "agent-canon.bootstrap-state.v2";
const SCHEMA_RECEIPT: &str = "agent-canon.bootstrap-receipt.v2";
const SCHEMA_MOUNTS: &str = "agent-canon.mount-registry.v2";
const STATE_FILE: &str = "state.json";
const OWNER_FILE: &str = "owner.json";
const RECEIPT_DIR: &str = "receipts";
const GENERATION_DIR: &str = "generations";
const TASK_DIR: &str = "tasks";
const CONTAINER_RUNTIME_DIR: &str = "container-runtime";
const CONTAINER_RUNTIME_DESTINATION: &str = "/var/lib/agent-canon/runtime";
const RUFF_CACHE_DESTINATION: &str = "/var/lib/agent-canon/cache/ruff";
const NATIVE_CLI_DESTINATION: &str = "/var/lib/agent-canon/cache/bin/agent-canon";
const PRIVATE_LOG_DESTINATION: &str = "/var/lib/agent-canon/private-log";
const REGISTRY_DESTINATION: &str = "/var/lib/agent-canon/mount-registry.toml";
const TOOL_SOURCE_DESTINATION: &str = "/opt/agent-canon/source";
const CODEX_SESSION_ROOT_ENV: &str = "AGENT_CANON_CODEX_SESSION_ROOT";
const REQUIRED_LABELS: [&str; 2] = [
    "io.agent-canon.runtime=shared-v1",
    "io.agent-canon.control-root-digest",
];

const TOOL_ENVIRONMENT_KEYS: &[&str] = &[
    "PATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "RUST_BACKTRACE",
    "CARGO_TERM_COLOR",
    "RUFF_CACHE_DIR",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_DISPATCH_ENTRY_ID",
    "AGENT_CANON_DISPATCH_RUNTIME",
    "AGENT_CANON_RUNTIME_ROOT",
    "AGENT_CANON_CONTROL_PARENT_ROOT",
    "AGENT_CANON_TASK_ROOT",
    "AGENT_CANON_TARGET_ROOT",
    "AGENT_CANON_EXPLICIT_CWD",
    "AGENT_CANON_OUTPUT_ROOT",
    "AGENT_CANON_MOUNT_REGISTRY",
    "AGENT_CANON_HOOK_ARCHIVE_DIR",
    "AGENT_CANON_LOG_ROOT",
    CODEX_SESSION_ROOT_ENV,
    "AGENT_CANON_PRIVATE_LOG_ROOT",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_KEY_0",
    "GIT_CONFIG_VALUE_0",
];

const TOOL_PATH_ENVIRONMENT_KEYS: &[&str] = &[
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_RUNTIME_TOOLS_ROOT",
    "AGENT_CANON_RUNTIME_ROOT",
    "AGENT_CANON_CONTROL_PARENT_ROOT",
    "AGENT_CANON_TASK_ROOT",
    "AGENT_CANON_TARGET_ROOT",
    "AGENT_CANON_EXPLICIT_CWD",
    "AGENT_CANON_OUTPUT_ROOT",
    "AGENT_CANON_MOUNT_REGISTRY",
    "AGENT_CANON_HOOK_ARCHIVE_DIR",
    "AGENT_CANON_LOG_ROOT",
    CODEX_SESSION_ROOT_ENV,
    "AGENT_CANON_HOST_INSTALL_ROOT",
    "AGENT_CANON_HOST_SPOOL_ROOT",
    "AGENT_CANON_HOST_ARCHIVE_ROOT",
    "AGENT_CANON_HOST_CACHE_ROOT",
    "AGENT_CANON_HOST_CODEX_HOME_ROOT",
    "AGENT_CANON_TARGET_HOST_ROOT",
    "AGENT_CANON_TARGET_CONTAINER_ROOT",
    "AGENT_CANON_RESTORE_TARGETS_FILE",
    "AGENT_CANON_ROLLBACK_MOUNTS_FILE",
];

#[derive(Debug)]
struct BootstrapError {
    code: String,
    detail: String,
    evidence: Value,
}

type Result<T> = std::result::Result<T, BootstrapError>;

impl BootstrapError {
    fn new(code: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            detail: detail.into(),
            evidence: json!({}),
        }
    }

    fn with_evidence(mut self, evidence: Value) -> Self {
        self.evidence = evidence;
        self
    }

    fn payload(&self) -> Value {
        json!({
            "schema": SCHEMA_RECEIPT,
            "status": "error",
            "code": self.code,
            "detail": self.detail,
            "evidence": self.evidence,
        })
    }
}

#[derive(Debug, Clone)]
struct CliArgs {
    repository_root: PathBuf,
    control_parent_root: PathBuf,
    runtime_root: Option<PathBuf>,
    manifest: Option<PathBuf>,
    operation: String,
    options: BTreeMap<String, String>,
    flags: BTreeSet<String>,
    remainder: Vec<String>,
}

struct ParsedOperationArgs {
    options: BTreeMap<String, String>,
    flags: BTreeSet<String>,
    remainder: Vec<String>,
}

/// Physical view of mounted paths for one controller process.
/// The resident uses the default empty map; test-only namespace adapters supply
/// host paths for target, control, and runtime mounts.
#[derive(Debug, Clone, Default)]
pub struct TargetNamespace {
    mounts: BTreeMap<PathBuf, PathBuf>,
}

impl TargetNamespace {
    /// Build a namespace from read-only container mount destinations and sources.
    pub fn from_readonly_mounts(
        mounts: impl IntoIterator<Item = (PathBuf, PathBuf)>,
    ) -> std::result::Result<Self, String> {
        let mut mapped = BTreeMap::new();
        for (logical, physical) in mounts {
            let Some(digest) = logical
                .strip_prefix("/targets/")
                .ok()
                .and_then(|path| path.to_str())
            else {
                return Err(format!(
                    "target mount destination is invalid: {}",
                    logical.display()
                ));
            };
            validate_safe_id(digest, "target_mount_invalid").map_err(|error| error.detail)?;
            let canonical = existing_directory(&physical, "target mount source")
                .map_err(|error| error.detail)?;
            if mapped.insert(logical, canonical).is_some() {
                return Err("duplicate target mount destination".to_string());
            }
        }
        Ok(Self { mounts: mapped })
    }

    /// Add the resident control and runtime roots for a test host namespace.
    pub fn with_runtime_roots(
        mut self,
        control_root: &Path,
        runtime_root: &Path,
    ) -> std::result::Result<Self, String> {
        let control = existing_directory(control_root, "control mount source")
            .map_err(|error| error.detail)?;
        let runtime = existing_directory(runtime_root, "runtime mount source")
            .map_err(|error| error.detail)?;
        if runtime != control && !runtime.starts_with(&control) {
            return Err("runtime mount source must be inside its control mount".to_string());
        }
        self.mounts
            .insert(PathBuf::from("/var/lib/agent-canon"), control);
        self.mounts
            .insert(PathBuf::from("/var/lib/agent-canon/runtime"), runtime);
        Ok(self)
    }

    /// Add the read-only source bind root used by the fake host namespace.
    pub fn with_source_root(mut self, source_root: &Path) -> std::result::Result<Self, String> {
        let source =
            existing_directory(source_root, "source mount source").map_err(|error| error.detail)?;
        self.mounts
            .insert(PathBuf::from("/opt/agent-canon/source"), source);
        Ok(self)
    }

    fn physical_path(&self, logical: &Path) -> PathBuf {
        self.mounts
            .get(logical)
            .cloned()
            .unwrap_or_else(|| logical.to_path_buf())
    }

    pub fn map_process_path(&self, value: &str) -> String {
        let path = Path::new(value);
        // Test namespaces can use host paths that happen to be lexically below a
        // container mount destination (for example, a workspace mounted under
        // /var/lib/agent-canon/runtime/tasks). Keep already-physical paths intact
        // before translating container paths through the mount table.
        if self
            .mounts
            .values()
            .any(|physical| path == physical || path.starts_with(physical))
        {
            return value.to_string();
        }
        for (logical, physical) in self.mounts.iter().rev() {
            if let Ok(relative) = path.strip_prefix(logical) {
                return physical.join(relative).to_string_lossy().to_string();
            }
        }
        value.to_string()
    }

    pub fn map_process_argv(&self, argv: &[String]) -> Vec<String> {
        argv.iter()
            .map(|value| self.map_process_path(value))
            .collect()
    }

    pub fn map_process_environment(
        &self,
        environment: &BTreeMap<String, String>,
    ) -> BTreeMap<String, String> {
        environment
            .iter()
            .map(|(key, value)| {
                let mapped = if TOOL_PATH_ENVIRONMENT_KEYS.contains(&key.as_str())
                    || key == "GIT_CONFIG_VALUE_0"
                {
                    self.map_process_path(value)
                } else {
                    value.clone()
                };
                (key.clone(), mapped)
            })
            .collect()
    }
}

fn parse_cli(args: &[String]) -> Result<Option<CliArgs>> {
    let mut repository_root = None;
    let mut control_parent_root = None;
    let mut runtime_root = None;
    let mut manifest = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--help" | "-h" => return Ok(None),
            "--repository-root" | "--control-parent-root" | "--runtime-root" | "--manifest" => {
                let option = args[index].as_str().to_owned();
                let value = args.get(index + 1).ok_or_else(|| {
                    BootstrapError::new("invalid_arguments", format!("missing value for {option}"))
                })?;
                match option.as_str() {
                    "--repository-root" => repository_root = Some(PathBuf::from(value)),
                    "--control-parent-root" => control_parent_root = Some(PathBuf::from(value)),
                    "--runtime-root" => runtime_root = Some(PathBuf::from(value)),
                    "--manifest" => manifest = Some(PathBuf::from(value)),
                    _ => unreachable!(),
                }
                index += 2;
            }
            _ => break,
        }
    }
    let operation = args
        .get(index)
        .ok_or_else(|| BootstrapError::new("invalid_arguments", "operation is required"))?
        .clone();
    index += 1;
    let ParsedOperationArgs {
        options,
        flags,
        remainder,
    } = parse_operation_args(&operation, &args[index..])?;
    let repository_root = repository_root
        .ok_or_else(|| BootstrapError::new("invalid_arguments", "--repository-root is required"))?;
    let control_parent_root = control_parent_root.ok_or_else(|| {
        BootstrapError::new("invalid_arguments", "--control-parent-root is required")
    })?;
    Ok(Some(CliArgs {
        repository_root,
        control_parent_root,
        runtime_root,
        manifest,
        operation,
        options,
        flags,
        remainder,
    }))
}

fn parse_operation_args(operation: &str, args: &[String]) -> Result<ParsedOperationArgs> {
    let mut options = BTreeMap::new();
    let mut flags = BTreeSet::new();
    let mut remainder = Vec::new();
    let (suboperation, start, positional_count) = match operation {
        "target" | "tool" | "template" | "eval" | "task" | "codex" => {
            let value = args.first().map(String::as_str).unwrap_or_default();
            let valid = match operation {
                "target" => ["add", "remove"].contains(&value),
                "tool" => value == "run",
                "template" => value == "export",
                "eval" => ["collect", "sync"].contains(&value),
                "task" => ["admit", "release"].contains(&value),
                "codex" => ["prepare", "launch", "hook", "hook-admission"].contains(&value),
                _ => false,
            };
            if !valid {
                return Err(BootstrapError::new(
                    "invalid_arguments",
                    format!("unsupported {operation} operation: {value}"),
                ));
            }
            options.insert(format!("--{operation}-operation"), value.to_string());
            (Some(value), 1, if operation == "tool" { 1 } else { 0 })
        }
        _ => (None, 0, 0),
    };
    let mut index = start;
    let mut positional = Vec::new();
    while index < args.len() {
        let token = &args[index];
        if token == "--" {
            remainder.extend(args[index + 1..].iter().cloned());
            break;
        }
        if !token.starts_with('-') {
            positional.push(token.clone());
            index += 1;
            continue;
        }
        if let Some((name, value)) = token.split_once('=') {
            options.insert(name.to_string(), value.to_string());
            index += 1;
            continue;
        }
        match token.as_str() {
            "--dry-run" => {
                flags.insert(token.clone());
                index += 1;
            }
            "--root" | "--request-json" | "--target-digest" | "--mode" | "--image-ref"
            | "--remote" | "--repository-id" | "--project-root" | "--event" | "--profile"
            | "--output" | "--run-id" | "--task-id" | "--outcome" => {
                let value = args.get(index + 1).ok_or_else(|| {
                    BootstrapError::new("invalid_arguments", format!("missing value for {token}"))
                })?;
                options.insert(token.clone(), value.clone());
                index += 2;
            }
            _ => {
                return Err(BootstrapError::new(
                    "invalid_arguments",
                    format!("unrecognized argument: {token}"),
                ));
            }
        }
    }
    if operation == "tool" {
        if positional.len() != positional_count {
            return Err(BootstrapError::new(
                "invalid_arguments",
                "tool run requires one catalog ID",
            ));
        }
        options.insert("--catalog-id".to_string(), positional[0].clone());
    } else if !positional.is_empty() {
        return Err(BootstrapError::new(
            "invalid_arguments",
            format!("unexpected positional argument: {}", positional[0]),
        ));
    }
    let _ = suboperation;
    Ok(ParsedOperationArgs {
        options,
        flags,
        remainder,
    })
}

fn usage() -> &'static str {
    "usage: agent-canon bootstrap-runtime --repository-root ROOT --control-parent-root ROOT [--runtime-root ROOT] [--manifest PATH] <operation>"
}

/// Run the resident lifecycle controller. Host Docker transitions remain in the Shell adapter.
pub fn run(args: &[String]) -> i32 {
    run_with_target_namespace(args, TargetNamespace::default())
}

/// Run the same native controller with an explicit read-only target namespace.
/// The shipped CLI calls [`run`] with the real resident mount namespace.
pub fn run_with_target_namespace(args: &[String], target_namespace: TargetNamespace) -> i32 {
    if !cfg!(unix) {
        eprintln!(
            "{}",
            json!({"schema":SCHEMA_RECEIPT,"status":"error","code":"unsupported_platform","detail":"bootstrap-runtime runs inside the Unix resident container"})
        );
        return 2;
    }
    match parse_cli(args) {
        Ok(None) => {
            println!("{}", usage());
            0
        }
        Ok(Some(args)) => {
            if args.operation == "codex" {
                match args.options.get("--codex-operation").map(String::as_str) {
                    Some("hook-admission") => return finish_status(hook_admission()),
                    Some("hook") => {
                        let event = match required_option(&args.options, "--event") {
                            Ok(event) => event,
                            Err(error) => return finish_status(Err(error)),
                        };
                        return finish_status(run_codex_hook(event));
                    }
                    _ => {}
                }
            }
            match run_operation(args, target_namespace) {
                Ok(payload) => match serde_json::to_string(&payload) {
                    Ok(serialized) => {
                        println!("{serialized}");
                        0
                    }
                    Err(error) => {
                        eprintln!(
                            "{}",
                            BootstrapError::new("serialization_failed", error.to_string())
                                .payload()
                        );
                        2
                    }
                },
                Err(error) => {
                    let code = error.code.clone();
                    eprintln!("{}", error.payload());
                    if code == "tool_failed" {
                        if let Some(exit) = error.evidence.get("exit").and_then(Value::as_i64) {
                            if (1..=125).contains(&exit) {
                                return exit as i32;
                            }
                        }
                    }
                    2
                }
            }
        }
        Err(error) => {
            eprintln!("{}", usage());
            eprintln!("{}", error.payload());
            2
        }
    }
}

fn finish_status(result: Result<i32>) -> i32 {
    match result {
        Ok(status) => status,
        Err(error) => {
            eprintln!("{}", error.payload());
            2
        }
    }
}

fn run_operation(args: CliArgs, target_namespace: TargetNamespace) -> Result<Value> {
    if args.operation == "source-identity" {
        return source_identity(&args.options);
    }
    let mut runtime = BootstrapRuntime::new(&args, target_namespace)?;
    runtime.run(args)
}

fn required_option<'a>(options: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str> {
    options
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| BootstrapError::new("invalid_arguments", format!("{key} is required")))
}

fn request_string<'a>(request: &'a Value, key: &str) -> Result<&'a str> {
    request
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty() && !value.chars().any(char::is_control))
        .ok_or_else(|| {
            BootstrapError::new(
                "invalid_exec_request",
                format!("request field is invalid: {key}"),
            )
        })
}

fn sha256_bytes(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn sha256_text(value: &str) -> String {
    sha256_bytes(value.as_bytes())
}

fn now() -> Result<String> {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| BootstrapError::new("clock_invalid", error.to_string()))?
        .as_secs();
    let datetime = time::OffsetDateTime::from_unix_timestamp(seconds as i64)
        .map_err(|error| BootstrapError::new("clock_invalid", error.to_string()))?;
    datetime
        .format(&time::format_description::well_known::Rfc3339)
        .map_err(|error| BootstrapError::new("clock_invalid", error.to_string()))
}

fn random_hex(bytes: usize) -> Result<String> {
    let mut random = vec![0_u8; bytes];
    getrandom::getrandom(&mut random)
        .map_err(|error| BootstrapError::new("random_unavailable", error.to_string()))?;
    Ok(crate::authority::encode_hex(&random))
}

fn path_parts(path: &Path) -> Result<Vec<OsString>> {
    if !path.is_absolute() {
        return Err(BootstrapError::new(
            "path_invalid",
            format!("path must be absolute: {}", path.display()),
        ));
    }
    let mut parts = Vec::new();
    for component in path.components() {
        match component {
            Component::RootDir => {}
            Component::Normal(value) => parts.push(value.to_os_string()),
            _ => {
                return Err(BootstrapError::new(
                    "path_invalid",
                    format!("path contains an unsafe component: {}", path.display()),
                ));
            }
        }
    }
    Ok(parts)
}

#[cfg(unix)]
fn private_permissions(mode: u32) -> Permissions {
    Permissions::from_mode(mode)
}

struct RuntimeFs {
    root: Dir,
}

impl RuntimeFs {
    fn new() -> Result<Self> {
        let root = Dir::open_ambient_dir(Path::new("/"), ambient_authority())
            .map_err(|error| BootstrapError::new("runtime_directory_invalid", error.to_string()))?;
        Ok(Self { root })
    }

    fn open_dir(&self, path: &Path, create: bool, mode: u32) -> Result<Dir> {
        #[cfg(not(unix))]
        let _ = mode;
        let parts = path_parts(path)?;
        let mut directory = self
            .root
            .try_clone()
            .map_err(|error| BootstrapError::new("runtime_directory_invalid", error.to_string()))?;
        for name in parts {
            match directory.open_dir_nofollow(&name) {
                Ok(next) => directory = next,
                Err(error) if create && error.kind() == std::io::ErrorKind::NotFound => {
                    let builder = DirBuilder::new();
                    #[cfg(unix)]
                    let builder = {
                        let mut builder = builder;
                        builder.mode(mode);
                        builder
                    };
                    directory
                        .create_dir_with(&name, &builder)
                        .map_err(|error| {
                            BootstrapError::new(
                                "runtime_directory_invalid",
                                format!("cannot create {}: {error}", path.display()),
                            )
                        })?;
                    directory = directory.open_dir_nofollow(&name).map_err(|error| {
                        BootstrapError::new(
                            "runtime_directory_invalid",
                            format!("cannot open {}: {error}", path.display()),
                        )
                    })?;
                }
                Err(error) => {
                    return Err(BootstrapError::new(
                        "symlink_path_rejected",
                        format!("unsafe directory {}: {error}", path.display()),
                    ));
                }
            }
        }
        Ok(directory)
    }

    fn ensure_directory(&self, path: &Path, mode: u32) -> Result<()> {
        let directory = self.open_dir(path, true, mode)?;
        #[cfg(unix)]
        directory
            .set_permissions(".", private_permissions(mode))
            .map_err(|error| {
                BootstrapError::new(
                    "runtime_directory_invalid",
                    format!("cannot protect directory {}: {error}", path.display()),
                )
            })?;
        #[cfg(not(unix))]
        let _ = directory;
        Ok(())
    }

    fn parent(&self, path: &Path, create: bool) -> Result<(Dir, OsString)> {
        let parts = path_parts(path)?;
        let (leaf, parent_parts) = parts.split_last().ok_or_else(|| {
            BootstrapError::new("path_invalid", "filesystem path does not name a child")
        })?;
        let mut parent = self
            .root
            .try_clone()
            .map_err(|error| BootstrapError::new("runtime_directory_invalid", error.to_string()))?;
        for name in parent_parts {
            match parent.open_dir_nofollow(name) {
                Ok(next) => parent = next,
                Err(error) if create && error.kind() == std::io::ErrorKind::NotFound => {
                    let builder = DirBuilder::new();
                    #[cfg(unix)]
                    let builder = {
                        let mut builder = builder;
                        builder.mode(0o700);
                        builder
                    };
                    parent.create_dir_with(name, &builder).map_err(|error| {
                        BootstrapError::new("runtime_directory_invalid", error.to_string())
                    })?;
                    parent = parent.open_dir_nofollow(name).map_err(|error| {
                        BootstrapError::new("runtime_directory_invalid", error.to_string())
                    })?;
                }
                Err(error) => {
                    return Err(BootstrapError::new(
                        "symlink_path_rejected",
                        format!("unsafe parent for {}: {error}", path.display()),
                    ));
                }
            }
        }
        Ok((parent, leaf.clone()))
    }

    fn read(&self, path: &Path, field: &str) -> Result<Option<Vec<u8>>> {
        let (parent, leaf) = self.parent(path, false)?;
        let metadata = match parent.symlink_metadata(&leaf) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => {
                return Err(BootstrapError::new(
                    "path_unresolvable",
                    format!("cannot inspect {field}: {}: {error}", path.display()),
                ));
            }
        };
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(BootstrapError::new(
                "symlink_path_rejected",
                format!("unsafe {field}: {}", path.display()),
            ));
        }
        let mut options = OpenOptions::new();
        options.read(true).follow(FollowSymlinks::No);
        let mut file = parent.open_with(&leaf, &options).map_err(|error| {
            BootstrapError::new(
                "symlink_path_rejected",
                format!("cannot safely open {field}: {}: {error}", path.display()),
            )
        })?;
        let opened = file.metadata().map_err(|error| {
            BootstrapError::new(
                "path_unresolvable",
                format!("cannot inspect {field}: {error}"),
            )
        })?;
        if !opened.is_file() || opened.file_type().is_symlink() {
            return Err(BootstrapError::new(
                "symlink_path_rejected",
                format!("unsafe {field}: {}", path.display()),
            ));
        }
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes).map_err(|error| {
            BootstrapError::new("path_unresolvable", format!("cannot read {field}: {error}"))
        })?;
        Ok(Some(bytes))
    }

    fn create_file(&self, path: &Path, mode: u32) -> Result<cap_std::fs::File> {
        #[cfg(not(unix))]
        let _ = mode;
        let (parent, leaf) = self.parent(path, true)?;
        let mut options = OpenOptions::new();
        options
            .read(true)
            .write(true)
            .create_new(true)
            .follow(FollowSymlinks::No);
        #[cfg(unix)]
        options.mode(mode);
        parent.open_with(&leaf, &options).map_err(|error| {
            BootstrapError::new(
                "state_write_failed",
                format!("cannot create {}: {error}", path.display()),
            )
        })
    }

    fn open_file(&self, path: &Path) -> Result<cap_std::fs::File> {
        let (parent, leaf) = self.parent(path, false)?;
        let metadata = parent.symlink_metadata(&leaf).map_err(|error| {
            BootstrapError::new(
                "path_missing",
                format!("file is unavailable: {}: {error}", path.display()),
            )
        })?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(BootstrapError::new(
                "symlink_path_rejected",
                format!("unsafe file: {}", path.display()),
            ));
        }
        let mut options = OpenOptions::new();
        options.read(true).write(true).follow(FollowSymlinks::No);
        parent.open_with(&leaf, &options).map_err(|error| {
            BootstrapError::new(
                "symlink_path_rejected",
                format!("cannot safely open {}: {error}", path.display()),
            )
        })
    }

    fn atomic_write(&self, path: &Path, bytes: &[u8], mode: u32) -> Result<()> {
        #[cfg(not(unix))]
        let _ = mode;
        let parent_path = path
            .parent()
            .ok_or_else(|| BootstrapError::new("path_invalid", "state path has no parent"))?;
        self.ensure_directory(parent_path, 0o700)?;
        let (parent, leaf) = self.parent(path, false)?;
        if let Ok(metadata) = parent.symlink_metadata(&leaf) {
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                return Err(BootstrapError::new(
                    "symlink_path_rejected",
                    format!("refusing to replace unsafe state path: {}", path.display()),
                ));
            }
        }
        let temporary = OsString::from(format!(
            ".{}.{}.{}.tmp",
            leaf.to_string_lossy(),
            std::process::id(),
            random_hex(8)?
        ));
        let mut options = OpenOptions::new();
        options
            .write(true)
            .create_new(true)
            .follow(FollowSymlinks::No);
        #[cfg(unix)]
        options.mode(mode);
        let operation = (|| {
            let mut file = parent
                .open_with(&temporary, &options)
                .map_err(|error| BootstrapError::new("state_write_failed", error.to_string()))?;
            file.write_all(bytes)
                .map_err(|error| BootstrapError::new("state_write_failed", error.to_string()))?;
            file.sync_all()
                .map_err(|error| BootstrapError::new("state_write_failed", error.to_string()))?;
            #[cfg(unix)]
            file.set_permissions(private_permissions(mode))
                .map_err(|error| BootstrapError::new("state_write_failed", error.to_string()))?;
            drop(file);
            if let Ok(metadata) = parent.symlink_metadata(&leaf) {
                if metadata.file_type().is_symlink() || !metadata.is_file() {
                    return Err(BootstrapError::new(
                        "symlink_path_rejected",
                        format!("refusing to replace unsafe state path: {}", path.display()),
                    ));
                }
            }
            parent.rename(&temporary, &parent, &leaf).map_err(|error| {
                BootstrapError::new(
                    "state_write_failed",
                    format!("cannot replace {}: {error}", path.display()),
                )
            })?;
            let mut sync_options = OpenOptions::new();
            sync_options.read(true).follow(FollowSymlinks::No);
            let directory = parent
                .open_with(".", &sync_options)
                .map_err(|error| BootstrapError::new("state_write_failed", error.to_string()))?;
            directory
                .sync_all()
                .map_err(|error| BootstrapError::new("state_write_failed", error.to_string()))?;
            Ok(())
        })();
        if operation.is_err() {
            let _ = parent.remove_file(&temporary);
        }
        operation
    }

    fn ensure_new_file(&self, path: &Path, mode: u32) -> Result<()> {
        #[cfg(not(unix))]
        let _ = mode;
        let (parent, leaf) = self.parent(path, true)?;
        match parent.symlink_metadata(&leaf) {
            Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
                return Err(BootstrapError::new(
                    "symlink_path_rejected",
                    format!("unsafe file path: {}", path.display()),
                ));
            }
            Ok(_) => return Ok(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(BootstrapError::new("path_unresolvable", error.to_string()));
            }
        }
        let mut options = OpenOptions::new();
        options
            .write(true)
            .create_new(true)
            .follow(FollowSymlinks::No);
        #[cfg(unix)]
        options.mode(mode);
        match parent.open_with(&leaf, &options) {
            Ok(file) => {
                file.sync_all().map_err(|error| {
                    BootstrapError::new("state_write_failed", error.to_string())
                })?;
                Ok(())
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => Ok(()),
            Err(error) => Err(BootstrapError::new("state_write_failed", error.to_string())),
        }
    }

    fn remove_file(&self, path: &Path) -> Result<()> {
        let (parent, leaf) = self.parent(path, false)?;
        match parent.symlink_metadata(&leaf) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(BootstrapError::new("path_unresolvable", error.to_string())),
            Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
                Err(BootstrapError::new(
                    "symlink_path_rejected",
                    format!("refusing to remove unsafe file: {}", path.display()),
                ))
            }
            Ok(_) => parent.remove_file(&leaf).map_err(|error| {
                BootstrapError::new(
                    "state_write_failed",
                    format!("cannot remove {}: {error}", path.display()),
                )
            }),
        }
    }

    fn remove_entry(&self, path: &Path) -> Result<()> {
        let (parent, leaf) = self.parent(path, false)?;
        match parent.symlink_metadata(&leaf) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(BootstrapError::new("path_unresolvable", error.to_string())),
            Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
                Err(BootstrapError::new(
                    "path_not_file",
                    format!("directory cannot be removed as a file: {}", path.display()),
                ))
            }
            Ok(_) => parent.remove_file(&leaf).map_err(|error| {
                BootstrapError::new(
                    "state_write_failed",
                    format!("cannot remove {}: {error}", path.display()),
                )
            }),
        }
    }

    fn remove_dir(&self, path: &Path) -> Result<()> {
        let (parent, leaf) = self.parent(path, false)?;
        let metadata = parent.symlink_metadata(&leaf).map_err(|error| {
            BootstrapError::new(
                "path_unresolvable",
                format!("cannot inspect {}: {error}", path.display()),
            )
        })?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(BootstrapError::new(
                "symlink_path_rejected",
                format!("unsafe directory: {}", path.display()),
            ));
        }
        parent.remove_dir(&leaf).map_err(|error| {
            BootstrapError::new(
                "state_write_failed",
                format!("cannot remove directory {}: {error}", path.display()),
            )
        })
    }

    fn entries(&self, path: &Path) -> Result<Vec<OsString>> {
        let directory = self.open_dir(path, false, 0o700)?;
        directory
            .read_dir(".")
            .map_err(|error| BootstrapError::new("path_unresolvable", error.to_string()))?
            .map(|entry| {
                entry
                    .map(|entry| entry.file_name())
                    .map_err(|error| BootstrapError::new("path_unresolvable", error.to_string()))
            })
            .collect()
    }
}

struct LifecycleLock {
    #[cfg(unix)]
    file: cap_std::fs::File,
}

impl LifecycleLock {
    fn acquire(file: cap_std::fs::File) -> Result<Self> {
        #[cfg(unix)]
        {
            rustix::fs::flock(&file, rustix::fs::FlockOperation::LockExclusive)
                .map_err(|error| BootstrapError::new("lifecycle_lock_failed", error.to_string()))?;
            Ok(Self { file })
        }
        #[cfg(not(unix))]
        {
            let _ = file;
            Err(BootstrapError::new(
                "unsupported_platform",
                "resident lifecycle locking requires a Unix platform",
            ))
        }
    }
}

impl Drop for LifecycleLock {
    fn drop(&mut self) {
        #[cfg(unix)]
        {
            let _ = rustix::fs::flock(&self.file, rustix::fs::FlockOperation::Unlock);
        }
    }
}

#[derive(Debug, Clone)]
struct RuntimePaths {
    control_parent_root: PathBuf,
    runtime_root: PathBuf,
    repository_root: PathBuf,
    state: PathBuf,
    owner: PathBuf,
    lock: PathBuf,
    receipts: PathBuf,
    generations: PathBuf,
    tasks: PathBuf,
    codex_home: PathBuf,
    spool: PathBuf,
    archive: PathBuf,
    cache: PathBuf,
    container_runtime: PathBuf,
    private_log: PathBuf,
}

impl RuntimePaths {
    fn new(control_parent_root: PathBuf, runtime_root: PathBuf, repository_root: PathBuf) -> Self {
        let host = |name: &str| {
            env::var_os(format!("AGENT_CANON_HOST_{name}_ROOT"))
                .filter(|value| !value.is_empty())
                .map(PathBuf::from)
        };
        let codex_home = host("CODEX_HOME").unwrap_or_else(|| runtime_root.join("codex-home"));
        let spool = host("SPOOL").unwrap_or_else(|| runtime_root.join("spool"));
        let archive = host("ARCHIVE").unwrap_or_else(|| runtime_root.join("archive"));
        let cache = host("CACHE").unwrap_or_else(|| runtime_root.join("cache"));
        let container_runtime = env::var_os("AGENT_CANON_EXCHANGE_ROOT")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| runtime_root.join(CONTAINER_RUNTIME_DIR));
        let private_log = env::var_os("AGENT_CANON_PRIVATE_LOG_ROOT")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(PRIVATE_LOG_DESTINATION));
        Self {
            control_parent_root,
            runtime_root: runtime_root.clone(),
            repository_root,
            state: runtime_root.join(STATE_FILE),
            owner: runtime_root.join(OWNER_FILE),
            lock: runtime_root.join("lifecycle.lock"),
            receipts: runtime_root.join(RECEIPT_DIR),
            generations: runtime_root.join(GENERATION_DIR),
            tasks: runtime_root.join(TASK_DIR),
            codex_home,
            spool,
            archive,
            cache,
            container_runtime,
            private_log,
        }
    }
}

struct BootstrapRuntime {
    paths: RuntimePaths,
    fs: RuntimeFs,
    target_namespace: TargetNamespace,
    manifest: Value,
    manifest_digest: String,
    control_digest: String,
}

impl BootstrapRuntime {
    fn new(args: &CliArgs, target_namespace: TargetNamespace) -> Result<Self> {
        let repository_root = existing_directory(&args.repository_root, "repository-root")?;
        let control_parent_root =
            existing_directory(&args.control_parent_root, "control-parent-root")?;
        let runtime_input = args
            .runtime_root
            .clone()
            .unwrap_or_else(|| repository_root.join(".runtime"));
        let runtime_root = absolute_path(&runtime_input)?;
        validate_runtime_roots(&control_parent_root, &runtime_root)?;
        let manifest_path = args
            .manifest
            .clone()
            .unwrap_or_else(|| repository_root.join("bootstrap/host/manifest.toml"));
        let manifest_path = absolute_path(&manifest_path)?;
        let (manifest, manifest_digest) = load_manifest(&manifest_path)?;
        let control_digest = env::var("AGENT_CANON_CONTROL_ROOT_DIGEST")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| sha256_text(&control_parent_root.to_string_lossy()));
        let paths = RuntimePaths::new(control_parent_root, runtime_root, repository_root);
        let fs = RuntimeFs::new()?;
        Ok(Self {
            paths,
            fs,
            target_namespace,
            manifest,
            manifest_digest,
            control_digest,
        })
    }

    fn ensure_layout(&self) -> Result<()> {
        for path in [
            &self.paths.runtime_root,
            &self.paths.receipts,
            &self.paths.generations,
            &self.paths.tasks,
            &self.paths.spool,
            &self.paths.archive,
            &self.paths.cache,
            &self.paths.codex_home,
            &self.paths.container_runtime,
        ] {
            self.fs.ensure_directory(path, 0o700)?;
        }
        #[cfg(unix)]
        {
            let metadata =
                fs::symlink_metadata(&self.paths.container_runtime).map_err(|error| {
                    BootstrapError::new("exchange_directory_invalid", error.to_string())
                })?;
            if metadata.permissions().mode() & 0o777 != 0o700 {
                return Err(BootstrapError::new(
                    "exchange_directory_invalid",
                    "container runtime exchange mode is not 0700",
                ));
            }
        }
        self.fs.ensure_new_file(&self.paths.lock, 0o600)?;
        if let Ok(metadata) = fs::symlink_metadata(&self.paths.private_log) {
            if metadata.file_type().is_symlink() {
                return Err(BootstrapError::new(
                    "symlink_path_rejected",
                    "private log checkout is a symlink",
                ));
            }
        } else {
            return Err(BootstrapError::new(
                "private_log_mount_invalid",
                "resident container is missing the host-owned private log mount",
            ));
        }
        Ok(())
    }

    fn locked<T>(&self, action: impl FnOnce() -> Result<T>) -> Result<T> {
        self.ensure_layout()?;
        let (parent, leaf) = self.fs.parent(&self.paths.lock, false)?;
        let mut options = OpenOptions::new();
        options.read(true).write(true).follow(FollowSymlinks::No);
        let file = parent.open_with(&leaf, &options).map_err(|error| {
            BootstrapError::new(
                "symlink_path_rejected",
                format!("cannot open lifecycle lock: {error}"),
            )
        })?;
        let _guard = LifecycleLock::acquire(file)?;
        action()
    }

    fn new_state(&self) -> Value {
        json!({
            "schema": SCHEMA_STATE,
            "control_parent_root": self.paths.control_parent_root,
            "runtime_root": self.paths.runtime_root,
            "repository_root": self.paths.repository_root,
            "control_root_digest": self.control_digest,
            "manifest_digest": self.manifest_digest,
            "state": "uninstalled",
            "active_task_count": 0,
            "current_generation": null,
            "rollback_generation": null,
            "generation_counter": 0,
            "targets": {},
            "generations": {},
            "tasks": {},
            "resources": {},
            "managed_paths": [],
            "managed_links": [],
            "updated_at": now().unwrap_or_default(),
        })
    }

    fn read_state(&self) -> Result<Value> {
        let Some(bytes) = self.fs.read(&self.paths.state, "state")? else {
            if self.fs.read(&self.paths.owner, "owner")?.is_none() {
                return Ok(self.new_state());
            }
            return Err(BootstrapError::new(
                "state_missing",
                "runtime owner exists but lifecycle state is missing",
            ));
        };
        let state: Value = serde_json::from_slice(&bytes)
            .map_err(|_| BootstrapError::new("state_invalid", "runtime state is not valid JSON"))?;
        let schema = state
            .get("schema")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if schema != SCHEMA_STATE && schema != "agent-canon.bootstrap-state.v1" {
            return Err(BootstrapError::new(
                "state_invalid",
                "runtime state schema is unsupported",
            ));
        }
        let owner = state
            .get("control_root_digest")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if owner != self.control_digest {
            return Err(BootstrapError::new(
                "shared_runtime_owned_elsewhere",
                "runtime is owned by another control root",
            )
            .with_evidence(json!({
                "owner_control_root_digest": owner,
                "requested_control_root_digest": self.control_digest,
            })));
        }
        Ok(state)
    }

    fn write_state(&self, state: &mut Value) -> Result<()> {
        let object = state.as_object_mut().ok_or_else(|| {
            BootstrapError::new("state_invalid", "runtime state is not an object")
        })?;
        object.insert(
            "schema".to_string(),
            Value::String(SCHEMA_STATE.to_string()),
        );
        object.insert("updated_at".to_string(), Value::String(now()?));
        object.insert(
            "repository_root".to_string(),
            Value::String(self.paths.repository_root.to_string_lossy().to_string()),
        );
        self.atomic_json(&self.paths.state, state, 0o600)?;
        self.atomic_json(
            &self.paths.owner,
            &json!({
                "schema": "agent-canon.bootstrap-owner.v1",
                "control_root_digest": self.control_digest,
                "control_parent_root": self.paths.control_parent_root,
                "runtime_root": self.paths.runtime_root,
                "repository_root": self.paths.repository_root,
                "manifest_digest": state.get("manifest_digest").unwrap_or(&Value::Null),
            }),
            0o600,
        )
    }

    fn atomic_json(&self, path: &Path, value: &Value, mode: u32) -> Result<()> {
        let mut bytes = serde_json::to_vec(value)
            .map_err(|error| BootstrapError::new("serialization_failed", error.to_string()))?;
        bytes.push(b'\n');
        self.fs.atomic_write(path, &bytes, mode)
    }

    fn resource_records(&self) -> Value {
        let image_tag = env::var("AGENT_CANON_IMAGE_REF")
            .ok()
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| {
                format!(
                    "agent-canon-tools:{}-{}",
                    &self.control_digest[..16],
                    &self.manifest_digest[..16]
                )
            });
        let container_name = env::var("AGENT_CANON_CONTAINER_NAME")
            .ok()
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| {
                self.manifest
                    .pointer("/container/name_template")
                    .and_then(Value::as_str)
                    .unwrap_or("agent-canon-tools")
                    .replace("<effective-uid>", &self.control_digest[..16])
            });
        json!({
            "image": {"id": null, "tag": image_tag, "owned": true, "state": "absent"},
            "container": {
                "id": null,
                "name": container_name,
                "owned": true,
                "labels": {
                    "io.agent-canon.runtime": "shared-v1",
                    "io.agent-canon.control-root-digest": self.control_digest,
                },
                "state": "absent",
            }
        })
    }

    fn container_resource_state(&self) -> Value {
        let mut resources = self.resource_records();
        if let Some(image_id) = env::var("AGENT_CANON_IMAGE_ID")
            .ok()
            .filter(|value| !value.is_empty())
        {
            if let Some(image) = resources.get_mut("image").and_then(Value::as_object_mut) {
                image.insert("id".to_string(), Value::String(image_id));
                image.insert("state".to_string(), Value::String("present".to_string()));
                image.insert("owned".to_string(), Value::Bool(true));
            }
        }
        if let Some(container_id) = env::var("AGENT_CANON_CONTAINER_ID")
            .ok()
            .filter(|value| !value.is_empty())
        {
            if let Some(container) = resources
                .get_mut("container")
                .and_then(Value::as_object_mut)
            {
                container.insert("id".to_string(), Value::String(container_id));
                container.insert("state".to_string(), Value::String("running".to_string()));
                container.insert("owned".to_string(), Value::Bool(true));
            }
        }
        resources
    }

    fn receipt(
        &self,
        operation: &str,
        status: &str,
        code: &str,
        transition: (Option<&str>, Option<&str>),
        details: Value,
        state: Option<&Value>,
    ) -> Value {
        let resources = state
            .and_then(|value| value.get("resources"))
            .cloned()
            .unwrap_or_else(|| self.resource_records());
        json!({
            "schema": SCHEMA_RECEIPT,
            "operation": operation,
            "status": status,
            "code": code,
            "control_root_digest": self.control_digest,
            "manifest_digest": state
                .and_then(|value| value.get("manifest_digest"))
                .cloned()
                .unwrap_or_else(|| json!(self.manifest_digest)),
            "before_state": transition.0,
            "after_state": transition.1,
            "resource_ids": resources,
            "created_at": now().unwrap_or_default(),
            "nonce": random_hex(16).unwrap_or_default(),
            "details": details,
        })
    }

    fn result(&self, mut receipt: Value) -> Result<Value> {
        let timestamp = receipt
            .get("created_at")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .replace([':', '-'], "");
        let operation = receipt
            .get("operation")
            .and_then(Value::as_str)
            .unwrap_or("operation");
        let nonce = receipt
            .get("nonce")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let name = format!("{timestamp}-{operation}-{nonce}.json");
        let path = self.paths.receipts.join(name);
        self.atomic_json(&path, &receipt, 0o600)?;
        receipt["receipt_path"] = Value::String(path.to_string_lossy().to_string());
        Ok(receipt)
    }

    fn state_summary(&self, state: &Value) -> Value {
        let resources = state.get("resources").cloned().unwrap_or_else(|| json!({}));
        let image = resources.get("image").cloned().unwrap_or_else(|| json!({}));
        let container = resources
            .get("container")
            .cloned()
            .unwrap_or_else(|| json!({}));
        let target_digests = state
            .get("targets")
            .and_then(Value::as_object)
            .map(|targets| targets.keys().cloned().collect::<Vec<_>>())
            .unwrap_or_default();
        let mut generations = Map::new();
        if let Some(values) = state.get("generations").and_then(Value::as_object) {
            for (key, generation) in values {
                let target_digests = generation
                    .get("targets")
                    .and_then(Value::as_object)
                    .map(|targets| targets.keys().cloned().collect::<Vec<_>>())
                    .unwrap_or_default();
                generations.insert(
                    key.clone(),
                    json!({
                        "state": generation.get("state"),
                        "target_digests": target_digests,
                        "failure": generation.get("failure"),
                    }),
                );
            }
        }
        json!({
            "state": state.get("state"),
            "active_task_count": state.get("active_task_count").unwrap_or(&Value::Null),
            "current_generation": state.get("current_generation"),
            "rollback_generation": state.get("rollback_generation"),
            "target_digests": target_digests,
            "generations": generations,
            "resources": {
                "image": {
                    "id": image.get("id"),
                    "tag": image.get("tag"),
                    "owned": image.get("owned"),
                    "state": image.get("state"),
                },
                "container": {
                    "id": container.get("id"),
                    "name": container.get("name"),
                    "owned": container.get("owned"),
                    "state": container.get("state"),
                },
            },
        })
    }

    fn write_mounts(&self, state: &Value) -> Result<()> {
        let mut lines = vec![
            format!("schema = {}", toml_quote(SCHEMA_MOUNTS)),
            String::new(),
        ];
        if let Some(targets) = state.get("targets").and_then(Value::as_object) {
            for (digest, record) in targets {
                let root = record
                    .get("root")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                let mode = record
                    .get("mode")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                lines.extend([
                    format!("[targets.{digest}]"),
                    format!("root = {}", toml_quote(root)),
                    format!("mode = {}", toml_quote(mode)),
                    format!("digest = {}", toml_quote(digest)),
                    String::new(),
                ]);
            }
        }
        self.fs.atomic_write(
            &self.paths.container_runtime.join("mounts.toml"),
            lines.join("\n").as_bytes(),
            0o444,
        )
    }

    fn write_mount_manifest(&self, state: &Value) -> Result<()> {
        let mut lines = Vec::new();
        if let Some(targets) = state.get("targets").and_then(Value::as_object) {
            for (digest, record) in targets {
                let Some(source) = record.get("host_root").and_then(Value::as_str) else {
                    continue;
                };
                let mode = record
                    .get("mode")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                if source
                    .chars()
                    .any(|character| matches!(character, '\t' | '\n' | '\r'))
                    || digest
                        .chars()
                        .any(|character| matches!(character, '\t' | '\n' | '\r'))
                {
                    return Err(BootstrapError::new(
                        "mount_manifest_invalid",
                        "target mount contains a control character",
                    ));
                }
                if mode != "read-only" {
                    return Err(BootstrapError::new(
                        "mount_manifest_invalid",
                        "only read-only targets may be projected into the resident mount manifest",
                    ));
                }
                lines.push(format!(
                    "target\t{digest}\t{source}\t/targets/{digest}\tread-only"
                ));
            }
        }
        let mut contents = lines.join("\n");
        if !contents.is_empty() {
            contents.push('\n');
        }
        self.fs.atomic_write(
            &self.paths.container_runtime.join("mounts.tsv"),
            contents.as_bytes(),
            0o444,
        )
    }

    fn run(&mut self, args: CliArgs) -> Result<Value> {
        match args.operation.as_str() {
            "install" | "update" | "start" | "stop" | "uninstall" => {
                self.transition(&args.operation)
            }
            "status" => self.status(),
            "rollback" => self.rollback(),
            "restore" => self.restore(),
            "target" => match args.options.get("--target-operation").map(String::as_str) {
                Some("add") => self.target_add(&args.options),
                Some("remove") => self.target_remove(&args.options),
                _ => Err(BootstrapError::new(
                    "invalid_arguments",
                    "target operation is required",
                )),
            },
            "exec" => self.exec(&args),
            "tool" => self.tool_run(&args),
            "template" => self.template_export(&args.options),
            "eval" => match args.options.get("--eval-operation").map(String::as_str) {
                Some("collect") => self.eval_collect(&args.options),
                Some("sync") => self.eval_sync_prepare(&args.options),
                _ => Err(BootstrapError::new(
                    "invalid_arguments",
                    "eval operation is required",
                )),
            },
            "task" => match args.options.get("--task-operation").map(String::as_str) {
                Some("admit") => self.admit_task(&args.options),
                Some("release") => self.release_task(&args.options),
                _ => Err(BootstrapError::new(
                    "invalid_arguments",
                    "task operation is required",
                )),
            },
            "gc" => self.gc(args.flags.contains("--dry-run")),
            "codex" => match args.options.get("--codex-operation").map(String::as_str) {
                Some("prepare") => self.codex_prepare(),
                Some("launch") => self.codex_launch(&args.options),
                _ => Err(BootstrapError::new(
                    "container_control_unsupported",
                    "unsupported Codex operation in resident controller",
                )),
            },
            other => Err(BootstrapError::new(
                "container_control_unsupported",
                format!("{other} requires host-owned Docker or a project execution plane"),
            )),
        }
    }

    fn transition(&self, operation: &str) -> Result<Value> {
        let result = self.locked(|| {
            let mut state = self.read_state()?;
            let before = state
                .get("state")
                .and_then(Value::as_str)
                .unwrap_or("uninstalled")
                .to_string();
            let current_resources = self.container_resource_state();
            let resources = state
                .as_object_mut()
                .ok_or_else(|| {
                    BootstrapError::new("state_invalid", "runtime state is not an object")
                })?
                .entry("resources")
                .or_insert_with(|| json!({}));
            if let (Some(resources), Some(current)) =
                (resources.as_object_mut(), current_resources.as_object())
            {
                for (key, value) in current {
                    resources.insert(key.clone(), value.clone());
                }
            }
            match operation {
                "install" => {
                    for directory in [&self.paths.generations, &self.paths.tasks] {
                        clear_directory(&self.fs, directory)?;
                    }
                    state["targets"] = json!({});
                    state["generations"] = json!({});
                    state["current_generation"] = Value::Null;
                    state["rollback_generation"] = Value::Null;
                    state["generation_counter"] = json!(0);
                    state["active_task_count"] = json!(0);
                    state["tasks"] = json!({});
                    state["state"] = json!("ready");
                    state["managed_paths"] = json!([
                        STATE_FILE,
                        OWNER_FILE,
                        "mounts.toml",
                        "mounts.tsv",
                        RECEIPT_DIR,
                        GENERATION_DIR,
                        TASK_DIR,
                        "spool",
                        "archive",
                        "cache",
                        "codex-home",
                        CONTAINER_RUNTIME_DIR,
                    ]);
                }
                "update" => {
                    self.prune_stale_targets(&mut state)?;
                    state["state"] = json!("ready");
                    if let Ok(previous_image_id) = env::var("AGENT_CANON_PREVIOUS_IMAGE_ID") {
                        state["previous_image_id"] = json!(previous_image_id);
                        let resources =
                            state.get("resources").cloned().unwrap_or_else(|| json!({}));
                        let current_image =
                            resources.get("image").cloned().unwrap_or_else(|| json!({}));
                        let current_image_id = current_image
                            .get("id")
                            .and_then(Value::as_str)
                            .ok_or_else(|| {
                                BootstrapError::new(
                                    "container_control_missing_identity",
                                    "updated image ID is unavailable",
                                )
                            })?;
                        let current_generation =
                            format!("generation-{}", image_suffix(current_image_id));
                        let previous_generation = state
                            .get("current_generation")
                            .and_then(Value::as_str)
                            .map(str::to_string)
                            .unwrap_or_else(|| {
                                format!("generation-{}", image_suffix(&previous_image_id))
                            });
                        let targets = state.get("targets").cloned().unwrap_or_else(|| json!({}));
                        if !state.get("generations").is_some_and(Value::is_object) {
                            state["generations"] = json!({});
                        }
                        let generations =
                            state["generations"].as_object_mut().ok_or_else(|| {
                                BootstrapError::new("state_invalid", "generation map is invalid")
                            })?;
                        generations.insert(
                            previous_generation.clone(),
                            json!({
                                "image_id": previous_image_id,
                                "image_ref": env::var("AGENT_CANON_PREVIOUS_IMAGE_REF").ok(),
                                "targets": targets,
                                "state": "rollback",
                            }),
                        );
                        generations.insert(
                            current_generation.clone(),
                            json!({
                                "image_id": current_image_id,
                                "image_ref": current_image.get("tag"),
                                "state": "current",
                            }),
                        );
                        state["rollback_generation"] = json!(previous_generation);
                        state["current_generation"] = json!(current_generation);
                        state["active_task_count"] = json!(0);
                        state["tasks"] = json!({});
                    }
                    state["manifest_digest"] = json!(self.manifest_digest);
                }
                "start" => state["state"] = json!("ready"),
                "stop" => {
                    state["state"] = json!("stopped");
                    state["resources"]["container"]["id"] = Value::Null;
                    state["resources"]["container"]["state"] = json!("absent");
                }
                "uninstall" => {
                    state["state"] = json!("uninstalled");
                    if let Some(resources) =
                        state.get_mut("resources").and_then(Value::as_object_mut)
                    {
                        for resource in resources.values_mut() {
                            if let Some(resource) = resource.as_object_mut() {
                                resource.insert("id".to_string(), Value::Null);
                                resource.insert("state".to_string(), json!("absent"));
                            }
                        }
                    }
                }
                _ => {
                    return Err(BootstrapError::new(
                        "container_control_unsupported",
                        operation,
                    ))
                }
            }
            self.write_mounts(&state)?;
            self.write_mount_manifest(&state)?;
            self.write_state(&mut state)?;
            if operation == "install" || operation == "update" {
                self.materialize_rollback_plan(&state)?;
            }
            let code = match operation {
                "install" => "installed",
                "update" => "updated",
                "start" => "ready",
                "stop" => "stopped",
                _ => "owned_resources_released",
            };
            self.result(self.receipt(
                operation,
                "ok",
                code,
                (Some(&before), state.get("state").and_then(Value::as_str)),
                json!({}),
                Some(&state),
            ))
        })?;
        if operation == "install" {
            let _ = self.codex_prepare()?;
        }
        Ok(result)
    }

    fn status(&self) -> Result<Value> {
        self.locked(|| {
            let state = self.read_state()?;
            let current = state
                .get("state")
                .and_then(Value::as_str)
                .unwrap_or("uninstalled");
            self.result(self.receipt(
                "status",
                "ok",
                "status",
                (Some(current), Some(current)),
                json!({"state": self.state_summary(&state)}),
                Some(&state),
            ))
        })
    }

    fn rollback(&self) -> Result<Value> {
        self.locked(|| {
            let mut state = self.read_state()?;
            let before = state.get("state").and_then(Value::as_str).unwrap_or("uninstalled").to_string();
            let restored_image_id = env::var("AGENT_CANON_RESTORE_IMAGE_ID")
                .ok()
                .filter(|value| !value.is_empty())
                .ok_or_else(|| BootstrapError::new("rollback_image_missing", "host did not provide a rollback image ID"))?;
            let resources = state.get("resources").cloned().unwrap_or_else(|| json!({}));
            let current_image_id = env::var("AGENT_CANON_CURRENT_IMAGE_ID")
                .ok()
                .or_else(|| resources.pointer("/image/id").and_then(Value::as_str).map(str::to_string))
                .unwrap_or_else(|| restored_image_id.clone());
            let previous_targets = self.previous_target_manifest()?;
            let current_targets = state.get("targets").cloned().unwrap_or_else(|| json!({}));
            if !state.get("resources").is_some_and(Value::is_object) {
                state["resources"] = self.container_resource_state();
            }
            if !state["resources"].get("image").is_some_and(Value::is_object) {
                state["resources"]["image"] = json!({});
            }
            state["resources"]["image"]["id"] = json!(restored_image_id);
            state["resources"]["image"]["tag"] = json!(
                env::var("AGENT_CANON_RESTORE_IMAGE_REF").unwrap_or_else(|_| restored_image_id.clone())
            );
            state["resources"]["image"]["owned"] = json!(true);
            state["resources"]["image"]["state"] = json!("present");
            let previous_generation = state
                .get("rollback_generation")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| format!("generation-{}", image_suffix(&restored_image_id)));
            let rollback_generation = state
                .get("current_generation")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| format!("generation-{}", image_suffix(&current_image_id)));
            if previous_generation == rollback_generation {
                return Err(BootstrapError::new(
                    "rollback_generation_invalid",
                    "current and rollback generations are not distinct",
                ));
            }
            if !state.get("generations").is_some_and(Value::is_object) {
                state["generations"] = json!({});
            }
            state["generations"][&previous_generation] = json!({
                "image_id": restored_image_id,
                "image_ref": env::var("AGENT_CANON_RESTORE_IMAGE_REF").unwrap_or_else(|_| restored_image_id.clone()),
                "targets": previous_targets,
                "state": "current",
            });
            state["generations"][&rollback_generation] = json!({
                "image_id": current_image_id,
                "image_ref": env::var("AGENT_CANON_CURRENT_IMAGE_REF").unwrap_or_else(|_| current_image_id.clone()),
                "targets": current_targets,
                "state": "rollback",
            });
            state["targets"] = previous_targets;
            state["rollback_generation"] = json!(rollback_generation);
            state["current_generation"] = json!(previous_generation);
            state["previous_image_id"] = Value::Null;
            state["state"] = json!("ready");
            self.write_mounts(&state)?;
            self.write_mount_manifest(&state)?;
            self.write_state(&mut state)?;
            self.materialize_rollback_plan(&state)?;
            self.result(self.receipt(
                "rollback",
                "ok",
                "previous_generation_restored",
                (Some(&before), Some("ready")),
                json!({}),
                Some(&state),
            ))
        })
    }

    fn restore(&self) -> Result<Value> {
        self.locked(|| {
            let mut state = self.read_state()?;
            let before = state
                .get("state")
                .and_then(Value::as_str)
                .unwrap_or("uninstalled")
                .to_string();
            let restored_image_id = env::var("AGENT_CANON_RESTORE_IMAGE_ID")
                .ok()
                .filter(|value| !value.is_empty())
                .ok_or_else(|| {
                    BootstrapError::new(
                        "restore_image_missing",
                        "host did not provide the previous image ID",
                    )
                })?;
            let resources = state.get("resources").cloned().unwrap_or_else(|| json!({}));
            let candidate_image_id = resources
                .pointer("/image/id")
                .and_then(Value::as_str)
                .unwrap_or(&restored_image_id)
                .to_string();
            let candidate_targets = state.get("targets").cloned().unwrap_or_else(|| json!({}));
            let restored_targets = self.restore_target_manifest()?;
            if let Some(targets) = restored_targets {
                state["targets"] = targets;
            }
            if !state.get("resources").is_some_and(Value::is_object) {
                state["resources"] = self.container_resource_state();
            }
            if !state["resources"]
                .get("image")
                .is_some_and(Value::is_object)
            {
                state["resources"]["image"] = json!({});
            }
            state["resources"]["image"]["id"] = json!(restored_image_id);
            state["resources"]["image"]["tag"] = json!(restored_image_id);
            state["resources"]["image"]["owned"] = json!(true);
            state["resources"]["image"]["state"] = json!("present");
            let restored_generation = format!("generation-{}", image_suffix(&restored_image_id));
            let candidate_generation = format!("generation-{}", image_suffix(&candidate_image_id));
            if !state.get("generations").is_some_and(Value::is_object) {
                state["generations"] = json!({});
            }
            let restored_targets = state.get("targets").cloned().unwrap_or_else(|| json!({}));
            state["generations"][&restored_generation] = json!({
                "image_id": restored_image_id,
                "targets": restored_targets,
                "state": "current",
            });
            if candidate_generation != restored_generation {
                state["generations"][&candidate_generation] = json!({
                    "image_id": candidate_image_id,
                    "targets": candidate_targets,
                    "state": "rollback",
                });
                state["rollback_generation"] = json!(candidate_generation);
            }
            state["current_generation"] = json!(restored_generation);
            state["previous_image_id"] = Value::Null;
            state["state"] = json!("ready");
            self.write_mounts(&state)?;
            self.write_mount_manifest(&state)?;
            self.write_state(&mut state)?;
            self.materialize_rollback_plan(&state)?;
            self.result(self.receipt(
                "restore",
                "ok",
                "previous_generation_restored",
                (Some(&before), Some("ready")),
                json!({}),
                Some(&state),
            ))
        })
    }

    fn previous_target_manifest(&self) -> Result<Value> {
        let path = env::var_os("AGENT_CANON_ROLLBACK_MOUNTS_FILE")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| self.paths.runtime_root.join("rollback-mounts.tsv"));
        match read_target_manifest(
            &self.fs,
            &path,
            "rollback_target_manifest_missing",
            "rollback_target_manifest_invalid",
        ) {
            Ok(value) => Ok(value),
            Err(error) if error.code == "rollback_target_manifest_missing" && !path.exists() => {
                Ok(json!({}))
            }
            Err(error) => Err(error),
        }
    }

    fn restore_target_manifest(&self) -> Result<Option<Value>> {
        let Some(path) = env::var_os("AGENT_CANON_RESTORE_TARGETS_FILE")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
        else {
            return Ok(None);
        };
        read_target_manifest(
            &self.fs,
            &path,
            "restore_target_manifest_missing",
            "restore_target_manifest_invalid",
        )
        .map(Some)
    }

    fn prune_stale_targets(&self, state: &mut Value) -> Result<Vec<String>> {
        let Some(targets) = state.get("targets").and_then(Value::as_object).cloned() else {
            return Ok(Vec::new());
        };
        let mut stale = Vec::new();
        let mut retained = Map::new();
        for (digest, record) in targets {
            let root = record
                .get("root")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let physical_root = self.target_namespace.physical_path(Path::new(root));
            if let Some(mapped) = self.target_namespace.mounts.get(Path::new(root)) {
                let host_root =
                    record
                        .get("host_root")
                        .and_then(Value::as_str)
                        .ok_or_else(|| {
                            BootstrapError::new(
                                "target_mount_invalid",
                                "mapped target is missing its host binding",
                            )
                        })?;
                let canonical_host = existing_directory(Path::new(host_root), "target host root")?;
                if &canonical_host != mapped {
                    return Err(BootstrapError::new(
                        "target_mount_invalid",
                        "target host binding differs from the Docker mount source",
                    ));
                }
            }
            let metadata = fs::symlink_metadata(&physical_root);
            if metadata.as_ref().is_err()
                || metadata
                    .as_ref()
                    .is_ok_and(|value| value.file_type().is_symlink() || !value.is_dir())
            {
                stale.push(digest);
            } else {
                retained.insert(digest, record);
            }
        }
        if stale.is_empty() {
            return Ok(stale);
        }
        state["targets"] = Value::Object(retained);
        if let Some(generations) = state.get_mut("generations").and_then(Value::as_object_mut) {
            for generation in generations.values_mut() {
                if let Some(targets) = generation.get_mut("targets").and_then(Value::as_object_mut)
                {
                    for digest in &stale {
                        targets.remove(digest);
                    }
                }
            }
        }
        Ok(stale)
    }

    fn target_record(&self, root: &Path, mode: &str) -> Result<Value> {
        if mode != "read-only" {
            return Err(BootstrapError::new(
                "invalid_target_mode",
                format!("unsupported target mode: {mode}"),
            ));
        }
        let host_root = env::var("AGENT_CANON_TARGET_HOST_ROOT").ok();
        let host_digest = env::var("AGENT_CANON_TARGET_DIGEST").ok();
        if let Some(host_root) = host_root {
            if !host_root.starts_with('/')
                || host_root
                    .chars()
                    .any(|value| matches!(value, '\0' | '\n' | '\r' | '\t' | '\\' | '"'))
            {
                return Err(BootstrapError::new(
                    "target_host_root_invalid",
                    "host target root is invalid",
                ));
            }
            let digest = host_digest.ok_or_else(|| {
                BootstrapError::new("target_digest_invalid", "host target digest is missing")
            })?;
            validate_safe_id(&digest, "target_digest_invalid")?;
            let expected = PathBuf::from("/targets").join(&digest);
            let actual = absolute_path(root)?;
            if actual != expected {
                return Err(BootstrapError::new(
                    "target_mount_invalid",
                    "target request does not name its declared container mount",
                ));
            }
            let physical = self.target_namespace.physical_path(&actual);
            let canonical = existing_directory(&physical, "mounted target root")?;
            if let Some(mapped) = self.target_namespace.mounts.get(&actual) {
                let canonical_host = existing_directory(Path::new(&host_root), "target host root")?;
                if &canonical_host != mapped || canonical != *mapped {
                    return Err(BootstrapError::new(
                        "target_mount_invalid",
                        "target host binding differs from the Docker mount source",
                    ));
                }
            }
            return Ok(json!({
                "root": actual.to_string_lossy(),
                "host_root": host_root,
                "mode": mode,
                "digest": digest,
            }));
        }
        if let Some(digest) = host_digest {
            validate_safe_id(&digest, "target_digest_invalid")?;
            let expected = PathBuf::from("/targets").join(&digest);
            let actual = absolute_path(root)?;
            if actual != expected {
                return Err(BootstrapError::new(
                    "target_mount_invalid",
                    "target request does not name its registered container mount",
                ));
            }
            let physical = self.target_namespace.physical_path(&actual);
            existing_directory(&physical, "mounted target root")?;
            return Ok(json!({
                "root": actual.to_string_lossy(),
                "mode": mode,
                "digest": digest,
            }));
        }
        let canonical = existing_directory(root, "target root")?;
        let digest = sha256_text(&canonical.to_string_lossy());
        Ok(json!({
            "root": canonical.to_string_lossy(),
            "mode": mode,
            "digest": digest,
        }))
    }

    fn verify_target_namespace_binding(&self, target: &Value, requested_root: &Path) -> Result<()> {
        let actual = absolute_path(requested_root)?;
        let Some(mapped) = self.target_namespace.mounts.get(&actual) else {
            return Ok(());
        };
        if target.get("root").and_then(Value::as_str) != actual.to_str()
            || target.get("mode").and_then(Value::as_str) != Some("read-only")
        {
            return Err(BootstrapError::new(
                "target_mount_invalid",
                "registered target does not match its mounted logical root",
            ));
        }
        let host_root = target
            .get("host_root")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                BootstrapError::new(
                    "target_mount_invalid",
                    "registered mounted target is missing its host binding",
                )
            })?;
        let canonical_host = existing_directory(Path::new(host_root), "target host root")?;
        let canonical_mount = existing_directory(mapped, "mounted target root")?;
        if &canonical_host != mapped || &canonical_mount != mapped {
            return Err(BootstrapError::new(
                "target_mount_invalid",
                "target host binding differs from the Docker mount source",
            ));
        }
        Ok(())
    }

    fn task_process_lease_path(&self, task_id: &str) -> PathBuf {
        self.paths
            .tasks
            .join(task_id)
            .join("locks")
            .join("process-lease.lock")
    }

    fn open_task_process_lease(
        &self,
        task_id: &str,
        create: bool,
    ) -> Result<Option<cap_std::fs::File>> {
        validate_safe_id(task_id, "invalid_identifier")?;
        let path = self.task_process_lease_path(task_id);
        if create {
            self.fs.ensure_directory(
                path.parent()
                    .and_then(Path::parent)
                    .unwrap_or(&self.paths.tasks),
                0o700,
            )?;
            self.fs
                .ensure_directory(path.parent().unwrap_or(&self.paths.tasks), 0o700)?;
        }
        let file = if create {
            self.fs.create_file(&path, 0o600).map_err(|error| {
                if error.detail.contains("File exists") || error.detail.contains("already exists") {
                    BootstrapError::new(
                        "task_lease_exists",
                        "process-owned task lease already exists",
                    )
                } else {
                    error
                }
            })?
        } else {
            self.fs.open_file(&path).map_err(|error| {
                if error.code == "path_missing" {
                    BootstrapError::new(
                        "task_lease_missing",
                        "process-owned task lease file is missing",
                    )
                } else {
                    BootstrapError::new("task_lease_invalid", error.detail)
                }
            })?
        };
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            #[allow(deprecated)]
            match nix::fcntl::flock(
                file.as_raw_fd(),
                nix::fcntl::FlockArg::LockExclusiveNonblock,
            ) {
                Ok(()) => Ok(Some(file)),
                Err(nix::errno::Errno::EWOULDBLOCK) if !create => Ok(None),
                Err(error) if !create && error == nix::errno::Errno::EAGAIN => Ok(None),
                Err(error) => Err(BootstrapError::new(
                    if create {
                        "task_lease_lock_failed"
                    } else {
                        "task_lease_invalid"
                    },
                    format!("cannot lock process-owned task lease: {error}"),
                )),
            }
        }
        #[cfg(not(unix))]
        {
            let _ = file;
            Err(BootstrapError::new(
                "unsupported_platform",
                "process-owned task leases require Unix file locks",
            ))
        }
    }

    fn reconcile_process_task_leases(&self, state: &mut Value) -> Result<()> {
        let tasks = state
            .get("tasks")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        for (task_id, task) in tasks {
            if task.get("state").and_then(Value::as_str) != Some("active")
                || task.get("lease_kind").and_then(Value::as_str) != Some("process")
            {
                continue;
            }
            if let Some(_lease) = self.open_task_process_lease(&task_id, false)? {
                self.release_task_locked(state, &task_id, "terminated")?;
            }
        }
        Ok(())
    }

    fn admit_task_locked(
        &self,
        state: &mut Value,
        task_id: &str,
        target_root: Option<&Path>,
        process_owned: bool,
    ) -> Result<(Value, Option<cap_std::fs::File>)> {
        validate_safe_id(task_id, "invalid_identifier")?;
        let state_name = state
            .get("state")
            .and_then(Value::as_str)
            .unwrap_or("uninstalled");
        if !["ready", "running"].contains(&state_name) {
            return Err(BootstrapError::new(
                "task_admission_closed",
                format!("runtime state is {state_name}"),
            ));
        }
        self.reconcile_process_task_leases(state)?;
        let tasks = state
            .get("tasks")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        if tasks.contains_key(task_id) {
            return Err(BootstrapError::new(
                "task_already_exists",
                format!("task already exists: {task_id}"),
            ));
        }
        let active = state
            .get("active_task_count")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let capacity = self
            .manifest
            .pointer("/container/max_parallel_tasks")
            .and_then(Value::as_u64)
            .unwrap_or(1);
        if active >= capacity {
            return Err(BootstrapError::new(
                "task_capacity_exhausted",
                "max parallel task slots are reserved",
            ));
        }
        let target = target_root
            .map(|root| self.target_record(root, "read-only"))
            .transpose()?;
        let target = if let Some(mut target) = target {
            if let Ok(digest) = env::var("AGENT_CANON_TARGET_DIGEST") {
                if let Some(existing) = state
                    .get("targets")
                    .and_then(Value::as_object)
                    .and_then(|targets| targets.get(&digest))
                {
                    target = existing.clone();
                }
            }
            let digest = target
                .get("digest")
                .and_then(Value::as_str)
                .unwrap_or_default();
            if state
                .get("targets")
                .and_then(Value::as_object)
                .is_none_or(|targets| !targets.contains_key(digest))
            {
                return Err(BootstrapError::new(
                    "target_not_registered",
                    "task target is not in the active mount generation",
                ));
            }
            if let Some(root) = target_root {
                self.verify_target_namespace_binding(&target, root)?;
            }
            if tasks.values().any(|task| {
                task.get("state").and_then(Value::as_str) == Some("active")
                    && task.pointer("/target/digest").and_then(Value::as_str) == Some(digest)
            }) {
                return Err(BootstrapError::new(
                    "target_busy",
                    "target is already reserved by an active task",
                ));
            }
            Some(target)
        } else {
            None
        };
        let task_path = self.paths.tasks.join(task_id);
        self.fs.ensure_directory(&task_path, 0o700)?;
        for child in ["tmp", "locks", "reports", "logs", "receipts"] {
            self.fs.ensure_directory(&task_path.join(child), 0o700)?;
        }
        let lease = if process_owned {
            Some(
                self.open_task_process_lease(task_id, true)?
                    .ok_or_else(|| {
                        BootstrapError::new(
                            "task_lease_lock_failed",
                            "cannot hold process-owned task lease",
                        )
                    })?,
            )
        } else {
            None
        };
        let mut task = json!({
            "id": task_id,
            "state": "active",
            "generation": state.get("current_generation"),
            "target": target,
            "started_at": now()?,
            "pinned": true,
        });
        if process_owned {
            task["lease_kind"] = json!("process");
        }
        if !state.get("tasks").is_some_and(Value::is_object) {
            state["tasks"] = json!({});
        }
        state["tasks"][task_id] = task.clone();
        state["active_task_count"] = json!(active + 1);
        state["state"] = json!("running");
        self.write_state(state)?;
        Ok((task, lease))
    }

    fn release_task_locked(
        &self,
        state: &mut Value,
        task_id: &str,
        outcome: &str,
    ) -> Result<Value> {
        let task = state
            .get_mut("tasks")
            .and_then(Value::as_object_mut)
            .and_then(|tasks| tasks.get_mut(task_id))
            .filter(|task| task.get("state").and_then(Value::as_str) == Some("active"))
            .ok_or_else(|| {
                BootstrapError::new("task_not_active", format!("task is not active: {task_id}"))
            })?;
        task["state"] = json!(if outcome == "completed" {
            "completed"
        } else {
            "cancelled"
        });
        task["outcome"] = json!(outcome);
        task["finished_at"] = json!(now()?);
        task["pinned"] = json!(false);
        let active = state
            .get("active_task_count")
            .and_then(Value::as_u64)
            .unwrap_or(0)
            .saturating_sub(1);
        state["active_task_count"] = json!(active);
        state["state"] = json!(if active == 0 { "ready" } else { "running" });
        let completed = state
            .get("tasks")
            .and_then(Value::as_object)
            .and_then(|tasks| tasks.get(task_id))
            .cloned()
            .unwrap_or(Value::Null);
        self.write_state(state)?;
        Ok(completed)
    }

    fn target_add(&self, options: &BTreeMap<String, String>) -> Result<Value> {
        let root = match env::var_os("AGENT_CANON_TARGET_CONTAINER_ROOT")
            .filter(|value| !value.is_empty())
        {
            Some(value) => PathBuf::from(value),
            None => PathBuf::from(required_option(options, "--root")?),
        };
        let mode = options
            .get("--mode")
            .map(String::as_str)
            .unwrap_or("read-only");
        self.locked(|| {
            let mut state = self.read_state()?;
            let stale = self.prune_stale_targets(&mut state)?;
            let target = self.target_record(&root, mode)?;
            let digest = target
                .get("digest")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string();
            let existing = state
                .get("targets")
                .and_then(Value::as_object)
                .and_then(|targets| targets.get(&digest))
                .cloned();
            if stale.is_empty()
                && existing
                    .as_ref()
                    .is_some_and(|value| same_target_record(value, &target))
            {
                self.write_mounts(&state)?;
                self.write_mount_manifest(&state)?;
                self.write_state(&mut state)?;
                return self.result(self.receipt(
                    "target_add",
                    "ok",
                    "target_unchanged",
                    (
                        state.get("state").and_then(Value::as_str),
                        state.get("state").and_then(Value::as_str),
                    ),
                    json!({"target": existing, "changed": false}),
                    Some(&state),
                ));
            }
            let mut targets = state
                .get("targets")
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default();
            targets.insert(digest, target.clone());
            target_generation(&mut state, Value::Object(targets));
            state["state"] = json!("ready");
            self.write_mounts(&state)?;
            self.write_mount_manifest(&state)?;
            self.write_state(&mut state)?;
            self.materialize_rollback_plan(&state)?;
            self.result(self.receipt(
                "target_add",
                "ok",
                "target_registered",
                (Some("ready"), Some("ready")),
                json!({"target": target}),
                Some(&state),
            ))
        })
    }

    fn target_remove(&self, options: &BTreeMap<String, String>) -> Result<Value> {
        let root = match env::var_os("AGENT_CANON_TARGET_CONTAINER_ROOT")
            .filter(|value| !value.is_empty())
        {
            Some(value) => PathBuf::from(value),
            None => PathBuf::from(required_option(options, "--root")?),
        };
        let mode = options
            .get("--mode")
            .map(String::as_str)
            .unwrap_or("read-only");
        self.locked(|| {
            let mut state = self.read_state()?;
            let mut targets = state
                .get("targets")
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default();
            let host_digest = env::var("AGENT_CANON_TARGET_DIGEST").ok();
            if let Some(digest) = host_digest.as_deref() {
                if !targets.contains_key(digest) {
                    return Err(BootstrapError::new(
                        "target_not_registered",
                        "target root is not registered",
                    ));
                }
            }
            let target = self.target_record(&root, mode)?;
            let digest = host_digest.unwrap_or_else(|| {
                target
                    .get("digest")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string()
            });
            if !targets.contains_key(&digest) {
                return Err(BootstrapError::new(
                    "target_not_registered",
                    "target root is not registered",
                ));
            }
            targets.remove(&digest);
            target_generation(&mut state, Value::Object(targets));
            self.write_mounts(&state)?;
            self.write_mount_manifest(&state)?;
            self.write_state(&mut state)?;
            self.materialize_rollback_plan(&state)?;
            self.result(self.receipt(
                "target_remove",
                "ok",
                "target_removed",
                (Some("ready"), Some("ready")),
                json!({"target_digest": digest}),
                Some(&state),
            ))
        })
    }

    fn admit_task(&self, options: &BTreeMap<String, String>) -> Result<Value> {
        let task_id = required_option(options, "--task-id")?;
        let target_root = options
            .get("--root")
            .map(|value| PathBuf::from(value.as_str()));
        self.locked(|| {
            let mut state = self.read_state()?;
            let before = state
                .get("state")
                .and_then(Value::as_str)
                .unwrap_or("uninstalled")
                .to_string();
            let (task, lease) =
                self.admit_task_locked(&mut state, task_id, target_root.as_deref(), false)?;
            if lease.is_some() {
                return Err(BootstrapError::new(
                    "task_lease_scope_invalid",
                    "manual task admission cannot own a process lease",
                ));
            }
            self.result(self.receipt(
                "task_admit",
                "ok",
                "task_reserved",
                (Some(&before), Some("running")),
                json!({"task": task}),
                Some(&state),
            ))
        })
    }

    fn release_task(&self, options: &BTreeMap<String, String>) -> Result<Value> {
        let task_id = required_option(options, "--task-id")?;
        let outcome = options
            .get("--outcome")
            .map(String::as_str)
            .unwrap_or("completed");
        self.locked(|| {
            let mut state = self.read_state()?;
            let before = state
                .get("state")
                .and_then(Value::as_str)
                .unwrap_or("uninstalled")
                .to_string();
            let task_record = state
                .get("tasks")
                .and_then(Value::as_object)
                .and_then(|tasks| tasks.get(task_id))
                .cloned()
                .unwrap_or(Value::Null);
            let lease = if task_record.get("state").and_then(Value::as_str) == Some("active")
                && task_record.get("lease_kind").and_then(Value::as_str) == Some("process")
            {
                let lease = self.open_task_process_lease(task_id, false)?;
                if lease.is_none() {
                    return Err(BootstrapError::new(
                        "task_process_active",
                        "cannot release a process-owned task while its worker is live",
                    ));
                }
                lease
            } else {
                None
            };
            let task = self.release_task_locked(&mut state, task_id, outcome)?;
            drop(lease);
            let after = state
                .get("state")
                .and_then(Value::as_str)
                .unwrap_or("ready")
                .to_string();
            self.result(self.receipt(
                "task_release",
                "ok",
                "task_released",
                (Some(&before), Some(&after)),
                json!({"task": task}),
                Some(&state),
            ))
        })
    }

    fn execution_request(
        &self,
        args: &CliArgs,
    ) -> Result<(PathBuf, Vec<String>, BTreeMap<String, String>)> {
        let Some(raw) = args.options.get("--request-json") else {
            let root = args
                .options
                .get("--root")
                .map(|value| PathBuf::from(value.as_str()))
                .ok_or_else(|| {
                    BootstrapError::new(
                        "invalid_arguments",
                        "exec requires --root or --request-json",
                    )
                })?;
            let environment = args
                .options
                .iter()
                .filter_map(|(key, value)| {
                    key.strip_prefix("--env-")
                        .map(|name| (name.to_string(), value.clone()))
                })
                .collect();
            return Ok((root, args.remainder.clone(), environment));
        };
        let request: Value = serde_json::from_str(raw)
            .map_err(|_| BootstrapError::new("invalid_exec_request", "request is not JSON"))?;
        let allowed = [
            "schema",
            "tool_id",
            "argv",
            "child_args",
            "source_root",
            "cwd",
            "cwd_policy",
            "target_root",
            "environment",
            "stdin",
            "stdout",
            "stderr",
            "exit",
            "signal",
            "side_effect",
            "output_root",
            "written_paths",
        ];
        let object = request.as_object().ok_or_else(|| {
            BootstrapError::new("invalid_exec_request", "request must be an object")
        })?;
        if object.keys().any(|key| !allowed.contains(&key.as_str()))
            || request.get("schema").and_then(Value::as_str)
                != Some("agent-canon.tool-exec-request.v1")
        {
            return Err(BootstrapError::new(
                "invalid_exec_request",
                "request fields or schema are invalid",
            ));
        }
        let tool_id = request_string(&request, "tool_id")?;
        validate_safe_id(tool_id, "invalid_exec_request")?;
        let child_args = request
            .get("child_args")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                BootstrapError::new("invalid_exec_request", "child_args must be an array")
            })?;
        let child_args = child_args
            .iter()
            .map(|value| {
                value
                    .as_str()
                    .filter(|value| !value.contains('\0'))
                    .map(str::to_string)
                    .ok_or_else(|| {
                        BootstrapError::new("invalid_exec_request", "child argument is invalid")
                    })
            })
            .collect::<Result<Vec<_>>>()?;
        let descriptor_argv = request
            .get("argv")
            .and_then(Value::as_array)
            .ok_or_else(|| BootstrapError::new("invalid_exec_request", "argv must be an array"))?;
        if descriptor_argv
            .iter()
            .any(|value| value.as_str().is_none_or(|value| value.contains('\0')))
        {
            return Err(BootstrapError::new(
                "invalid_exec_request",
                "descriptor argv is invalid",
            ));
        }
        let target_digest = env::var("AGENT_CANON_TARGET_DIGEST").unwrap_or_default();
        validate_safe_id(&target_digest, "invalid_exec_request")?;
        if args.options.get("--target-digest").map(String::as_str) != Some(target_digest.as_str()) {
            return Err(BootstrapError::new(
                "invalid_exec_request",
                "target digest handoff is invalid",
            ));
        }
        let target = self
            .read_state()?
            .get("targets")
            .and_then(Value::as_object)
            .and_then(|targets| targets.get(&target_digest))
            .cloned()
            .ok_or_else(|| {
                BootstrapError::new("target_not_registered", "request target is not registered")
            })?;
        let host_target = absolute_path(Path::new(request_string(&request, "target_root")?))?;
        let host_root = target
            .get("host_root")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                BootstrapError::new(
                    "invalid_exec_request",
                    "registered target host root is unavailable",
                )
            })?;
        let container_root = format!("/targets/{target_digest}");
        if absolute_path(Path::new(host_root))? != host_target
            || target.get("root").and_then(Value::as_str) != Some(container_root.as_str())
        {
            return Err(BootstrapError::new(
                "invalid_exec_request",
                "request target does not match its registered mount",
            ));
        }
        let source_root = absolute_path(Path::new(request_string(&request, "source_root")?))?;
        let raw_environment = request
            .get("environment")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                BootstrapError::new(
                    "invalid_exec_request",
                    "request environment must be a mapping",
                )
            })?;
        let runtime_root = absolute_path(Path::new(
            raw_environment
                .get("AGENT_CANON_RUNTIME_ROOT")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    BootstrapError::new("invalid_exec_request", "runtime root is required")
                })?,
        ))?;
        let control_root = absolute_path(Path::new(
            raw_environment
                .get("AGENT_CANON_CONTROL_PARENT_ROOT")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    BootstrapError::new("invalid_exec_request", "control root is required")
                })?,
        ))?;
        let private_log = env::var("AGENT_CANON_PRIVATE_LOG_ROOT")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .map(|value| absolute_path(Path::new(&value)))
            .transpose()?;
        let mut environment = BTreeMap::new();
        for (key, raw_value) in raw_environment {
            let value = raw_value
                .as_str()
                .filter(|value| !value.chars().any(char::is_control))
                .ok_or_else(|| {
                    BootstrapError::new(
                        "invalid_exec_request",
                        format!("request environment key is not allowlisted: {key}"),
                    )
                })?;
            if !TOOL_ENVIRONMENT_KEYS.contains(&key.as_str()) {
                return Err(BootstrapError::new(
                    "invalid_exec_request",
                    format!("request environment key is not allowlisted: {key}"),
                ));
            }
            if TOOL_PATH_ENVIRONMENT_KEYS.contains(&key.as_str()) {
                let mapped = match key.as_str() {
                    "AGENT_CANON_SOURCE_ROOT" | "AGENT_CANON_ROOT" => {
                        if absolute_path(Path::new(value))? != source_root {
                            return Err(BootstrapError::new(
                                "invalid_exec_request",
                                format!("source path does not match request: {key}"),
                            ));
                        }
                        TOOL_SOURCE_DESTINATION.to_string()
                    }
                    "AGENT_CANON_RUNTIME_ROOT" => {
                        if absolute_path(Path::new(value))? != runtime_root
                            || runtime_root != self.paths.runtime_root
                        {
                            return Err(BootstrapError::new(
                                "invalid_exec_request",
                                "runtime path does not match request",
                            ));
                        }
                        CONTAINER_RUNTIME_DESTINATION.to_string()
                    }
                    "AGENT_CANON_CONTROL_PARENT_ROOT" => {
                        if absolute_path(Path::new(value))? != control_root
                            || control_root != self.paths.control_parent_root
                        {
                            return Err(BootstrapError::new(
                                "invalid_exec_request",
                                "control path does not match request",
                            ));
                        }
                        "/var/lib/agent-canon".to_string()
                    }
                    "AGENT_CANON_TARGET_ROOT" | "AGENT_CANON_TASK_ROOT" => {
                        if absolute_path(Path::new(value))? != host_target {
                            return Err(BootstrapError::new(
                                "invalid_exec_request",
                                format!("target path does not match request: {key}"),
                            ));
                        }
                        container_root.clone()
                    }
                    "AGENT_CANON_MOUNT_REGISTRY" => REGISTRY_DESTINATION.to_string(),
                    "AGENT_CANON_HOOK_ARCHIVE_DIR" | "AGENT_CANON_LOG_ROOT" => {
                        if private_log.as_ref().is_none_or(|root| {
                            absolute_path(Path::new(value)).ok().as_ref() != Some(root)
                        }) {
                            return Err(BootstrapError::new(
                                "invalid_exec_request",
                                format!("archive path does not match private log mount: {key}"),
                            ));
                        }
                        PRIVATE_LOG_DESTINATION.to_string()
                    }
                    _ => {
                        let candidate = absolute_path(Path::new(value))?;
                        if candidate == source_root {
                            TOOL_SOURCE_DESTINATION.to_string()
                        } else if candidate == host_target || candidate.starts_with(&host_target) {
                            let relative = candidate.strip_prefix(&host_target).map_err(|_| {
                                BootstrapError::new(
                                    "invalid_exec_request",
                                    "target path mapping failed",
                                )
                            })?;
                            Path::new(&container_root)
                                .join(relative)
                                .to_string_lossy()
                                .to_string()
                        } else if candidate == runtime_root || candidate.starts_with(&runtime_root)
                        {
                            let relative = candidate.strip_prefix(&runtime_root).map_err(|_| {
                                BootstrapError::new(
                                    "invalid_exec_request",
                                    "runtime path mapping failed",
                                )
                            })?;
                            Path::new(CONTAINER_RUNTIME_DESTINATION)
                                .join(relative)
                                .to_string_lossy()
                                .to_string()
                        } else if candidate == control_root {
                            "/var/lib/agent-canon".to_string()
                        } else {
                            return Err(BootstrapError::new(
                                "invalid_exec_request",
                                format!(
                                    "path-valued environment escapes registered mounts: {value}"
                                ),
                            ));
                        }
                    }
                };
                environment.insert(key.clone(), mapped);
            } else {
                environment.insert(key.clone(), value.to_string());
            }
        }
        match (
            request.get("output_root"),
            raw_environment.get("AGENT_CANON_OUTPUT_ROOT"),
        ) {
            (None, None) => {}
            (Some(output), Some(environment_output))
                if output.as_str() == environment_output.as_str() => {}
            _ => {
                return Err(BootstrapError::new(
                    "invalid_exec_request",
                    "output_root and output environment differ",
                ))
            }
        }
        let mut argv = vec![
            "agent-canon-tool".to_string(),
            "tool".to_string(),
            "run".to_string(),
            tool_id.to_string(),
            "--".to_string(),
        ];
        argv.extend(child_args);
        Ok((PathBuf::from(container_root), argv, environment))
    }

    fn exec(&self, args: &CliArgs) -> Result<Value> {
        let (root, argv, mut environment) = self.execution_request(args)?;
        if argv.is_empty() {
            return Err(BootstrapError::new(
                "argv_required",
                "exec requires a command after --",
            ));
        }
        validate_tool_argv(&argv)?;
        self.locked(|| {
        let requested = self.target_record(&root, "read-only")?;
        let mut state = self.read_state()?;
        let target_digest = env::var("AGENT_CANON_TARGET_DIGEST").ok();
        let target = target_digest
            .as_ref()
            .and_then(|digest| state.get("targets").and_then(Value::as_object).and_then(|targets| targets.get(digest)))
            .cloned()
            .unwrap_or(requested);
        let digest = target.get("digest").and_then(Value::as_str).ok_or_else(|| {
            BootstrapError::new("target_not_registered", "exec root is not registered")
        })?.to_string();
        let registered = state.get("targets").and_then(Value::as_object).and_then(|targets| targets.get(&digest)).cloned().ok_or_else(|| {
            BootstrapError::new("target_not_registered", "exec root is not registered")
        })?;
        let task_id = format!("exec-{}", random_hex(6)?);
        let before = state.get("state").and_then(Value::as_str).unwrap_or("ready").to_string();
        let (_task, lease) = self.admit_task_locked(&mut state, &task_id, Some(&root), true)?;
        let lease = lease.ok_or_else(|| BootstrapError::new("task_lease_scope_invalid", "exec admission did not return its process lease"))?;
        let container_id = env::var("AGENT_CANON_CONTAINER_ID").ok().filter(|value| !value.is_empty()).ok_or_else(|| {
            BootstrapError::new("container_control_missing_identity", "resident container identity was not provided")
        })?;
        environment.extend(BTreeMap::from([
            ("AGENT_CANON_TARGET_ROOT".to_string(), format!("/targets/{digest}")),
            ("AGENT_CANON_TASK_ROOT".to_string(), format!("/targets/{digest}")),
            ("AGENT_CANON_MOUNT_REGISTRY".to_string(), REGISTRY_DESTINATION.to_string()),
            ("AGENT_CANON_HOOK_ARCHIVE_DIR".to_string(), PRIVATE_LOG_DESTINATION.to_string()),
            ("AGENT_CANON_LOG_ROOT".to_string(), PRIVATE_LOG_DESTINATION.to_string()),
            ("AGENT_CANON_RUNTIME_ROOT".to_string(), CONTAINER_RUNTIME_DESTINATION.to_string()),
            ("TMPDIR".to_string(), format!("{CONTAINER_RUNTIME_DESTINATION}/tasks/{task_id}/tmp")),
            ("RUFF_CACHE_DIR".to_string(), RUFF_CACHE_DESTINATION.to_string()),
            ("AGENT_CANON_CONTAINER_ID".to_string(), container_id),
        ]));
        environment.insert("GIT_CONFIG_COUNT".to_string(), "1".to_string());
        environment.insert("GIT_CONFIG_KEY_0".to_string(), "safe.directory".to_string());
        environment.insert("GIT_CONFIG_VALUE_0".to_string(), format!("/targets/{digest}"));
        if let Some(host_root) = registered.get("host_root").and_then(Value::as_str) {
            environment.insert("AGENT_CANON_TARGET_HOST_ROOT".to_string(), host_root.to_string());
        }
        let timeout = self.manifest.pointer("/container/task_timeout_seconds").and_then(Value::as_u64).unwrap_or(3600);
        let logical_cwd = PathBuf::from(format!("/targets/{digest}"));
        let physical_cwd = self.target_namespace.physical_path(&logical_cwd);
        let process_argv = self.target_namespace.map_process_argv(&argv);
        let process_environment = self.target_namespace.map_process_environment(&environment);
        let command_result = run_tool_process(
            &process_argv,
            &physical_cwd,
            &process_environment,
            Duration::from_secs(timeout),
            &lease,
        );
        let result = match command_result {
            Ok(output) => output,
            Err(error) => {
                let _ = self.release_task_locked(&mut state, &task_id, "failed");
                return Err(error);
            }
        };
        let stdout = String::from_utf8_lossy(&result.stdout).into_owned();
        let stderr = String::from_utf8_lossy(&result.stderr).into_owned();
        let redacted_stdout = redact_output(&stdout);
        let redacted_stderr = redact_output(&stderr);
        let stdout_bytes = redacted_stdout.as_bytes();
        let stderr_bytes = redacted_stderr.as_bytes();
        let quota = self.manifest.pointer("/container/task_log_quota_bytes").and_then(Value::as_u64).unwrap_or(0);
        if quota > 0 && (stdout_bytes.len() + stderr_bytes.len()) as u64 > quota {
            let _ = self.release_task_locked(&mut state, &task_id, "failed");
            return Err(BootstrapError::new("task_log_quota_exceeded", "command streams exceed the configured task log quota"));
        }
        for (name, bytes) in [("stdout.log", stdout_bytes), ("stderr.log", stderr_bytes)] {
            self.fs.atomic_write(&self.paths.tasks.join(&task_id).join("logs").join(name), bytes, 0o600)?;
        }
        let exit = result.status.code().unwrap_or(128);
        let io = json!({
            "stdout_log": self.paths.tasks.join(&task_id).join("logs/stdout.log"),
            "stdout_digest": sha256_bytes(stdout_bytes),
            "stdout_bytes": stdout_bytes.len(),
            "stdout_preview": bounded_preview(&redacted_stdout, 512),
            "stdout_truncated": redacted_stdout.chars().count() > 512,
            "stderr_log": self.paths.tasks.join(&task_id).join("logs/stderr.log"),
            "stderr_digest": sha256_bytes(stderr_bytes),
            "stderr_bytes": stderr_bytes.len(),
            "stderr_preview": bounded_preview(&redacted_stderr, 512),
            "stderr_truncated": redacted_stderr.chars().count() > 512,
        });
        if let Some(task) = state.get_mut("tasks").and_then(Value::as_object_mut).and_then(|tasks| tasks.get_mut(&task_id)) {
            task["io"] = io.clone();
        }
        let details = json!({
            "argv": redact_argv(&argv),
            "cwd": root,
            "exit": exit,
            "execution_plane": "agentcanon_tool_container",
            "container_id": env::var("AGENT_CANON_CONTAINER_ID").ok(),
            "stdout_log": io["stdout_log"],
            "stdout_digest": io["stdout_digest"],
            "stdout_bytes": io["stdout_bytes"],
            "stdout_preview": io["stdout_preview"],
            "stdout_truncated": io["stdout_truncated"],
            "stderr_log": io["stderr_log"],
            "stderr_digest": io["stderr_digest"],
            "stderr_bytes": io["stderr_bytes"],
            "stderr_preview": io["stderr_preview"],
            "stderr_truncated": io["stderr_truncated"],
        });
        let release = self.release_task_locked(&mut state, &task_id, if exit == 0 { "completed" } else { "failed" });
        release?;
        let after = state.get("state").and_then(Value::as_str).unwrap_or("ready").to_string();
        if exit != 0 {
            let receipt = self.result(self.receipt("exec", "error", "tool_failed", (Some("running"), Some("running")), details, Some(&state)))?;
            return Err(BootstrapError::new("tool_failed", format!("command exited with {exit}"))
                .with_evidence(json!({"exit": exit, "receipt_path": receipt["receipt_path"], "stdout_digest": io["stdout_digest"], "stderr_digest": io["stderr_digest"]})));
        }
        self.result(self.receipt("exec", "ok", "completed", (Some(&before), Some(&after)), details, Some(&state)))
        })
    }

    fn tool_run(&self, args: &CliArgs) -> Result<Value> {
        let catalog_id = required_option(&args.options, "--catalog-id")?;
        validate_safe_id(catalog_id, "invalid_identifier")?;
        let targets = self
            .read_state()?
            .get("targets")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        let target = if let Some(root) = args.options.get("--root") {
            let container_root = env::var("AGENT_CANON_TARGET_CONTAINER_ROOT")
                .ok()
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| root.clone());
            let requested = self.target_record(Path::new(&container_root), "read-only")?;
            let digest = env::var("AGENT_CANON_TARGET_DIGEST").unwrap_or_else(|_| {
                requested
                    .get("digest")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string()
            });
            targets.get(&digest).cloned().ok_or_else(|| {
                BootstrapError::new("target_not_registered", "tool run root is not registered")
            })?
        } else if targets.len() == 1 {
            targets.values().next().cloned().unwrap_or(Value::Null)
        } else if targets.is_empty() {
            return Err(BootstrapError::new(
                "target_not_registered",
                "tool run requires a registered target",
            ));
        } else {
            return Err(BootstrapError::new(
                "target_root_required",
                "tool run requires --root when multiple targets are registered",
            ));
        };
        if args.remainder.is_empty() {
            return Err(BootstrapError::new(
                "argv_required",
                "tool run requires a command after --",
            ));
        }
        let mut nested = args.clone();
        nested.operation = "exec".to_string();
        nested.options.insert(
            "--root".to_string(),
            target
                .get("root")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
        );
        if !args.options.contains_key("--request-json")
            && !args.options.contains_key("--env-AGENT_CANON_OUTPUT_ROOT")
        {
            let cli = env::var("AGENT_CANON_NATIVE_BIN")
                .unwrap_or_else(|_| NATIVE_CLI_DESTINATION.to_string());
            let inventory = Command::new(cli)
                .args([
                    "tool",
                    "inventory",
                    "--root",
                    self.paths.repository_root.to_string_lossy().as_ref(),
                    "--json",
                ])
                .current_dir(&self.paths.repository_root)
                .env_clear()
                .output()
                .map_err(|_| {
                    BootstrapError::new(
                        "tool_catalog_invalid",
                        "cannot resolve tool output capability",
                    )
                })?;
            if !inventory.status.success() {
                return Err(BootstrapError::new(
                    "tool_catalog_invalid",
                    "cannot resolve tool output capability",
                ));
            }
            let payload: Value = serde_json::from_slice(&inventory.stdout).map_err(|_| {
                BootstrapError::new("tool_catalog_invalid", "native tool inventory is invalid")
            })?;
            let entries = payload
                .get("entries")
                .and_then(Value::as_array)
                .ok_or_else(|| {
                    BootstrapError::new(
                        "tool_catalog_invalid",
                        "native tool inventory entries are invalid",
                    )
                })?;
            let output_root = entries
                .iter()
                .find(|entry| entry.get("id").and_then(Value::as_str) == Some(catalog_id))
                .and_then(|entry| entry.get("output_root"))
                .and_then(Value::as_str);
            match output_root {
                Some("external-runtime") => {
                    nested.options.insert(
                        "--env-AGENT_CANON_OUTPUT_ROOT".to_string(),
                        format!("{CONTAINER_RUNTIME_DESTINATION}/tool-output"),
                    );
                }
                Some("explicit-target") => {
                    nested.options.insert(
                        "--env-AGENT_CANON_OUTPUT_ROOT".to_string(),
                        target
                            .get("root")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .to_string(),
                    );
                }
                _ => {}
            }
        }
        nested.remainder = vec![
            "agent-canon-tool".to_string(),
            "tool".to_string(),
            "run".to_string(),
            catalog_id.to_string(),
            "--".to_string(),
        ];
        nested.remainder.extend(args.remainder.iter().cloned());
        self.exec(&nested)
    }

    fn template_export(&self, options: &BTreeMap<String, String>) -> Result<Value> {
        let root = required_option(options, "--root")?;
        let profile = required_option(options, "--profile")?;
        let output = required_option(options, "--output")?;
        validate_safe_id(profile, "invalid_identifier")?;
        let relative = Path::new(output);
        if relative.is_absolute()
            || relative
                .components()
                .any(|component| !matches!(component, Component::Normal(_)))
        {
            return Err(BootstrapError::new(
                "template_output_invalid",
                "output must be runtime-relative",
            ));
        }
        let host_output = self
            .paths
            .runtime_root
            .join("template-exports")
            .join(relative);
        if host_output.exists() || host_output.symlink_metadata().is_ok() {
            return Err(BootstrapError::new(
                "template_output_exists",
                host_output.display().to_string(),
            ));
        }
        let nested = CliArgs {
            repository_root: self.paths.repository_root.clone(),
            control_parent_root: self.paths.control_parent_root.clone(),
            runtime_root: Some(self.paths.runtime_root.clone()),
            manifest: None,
            operation: "tool".to_string(),
            options: BTreeMap::from([
                ("--catalog-id".to_string(), "template-bundle".to_string()),
                ("--root".to_string(), root.to_string()),
                ("--output".to_string(), output.to_string()),
                ("--profile".to_string(), profile.to_string()),
                (
                    "--env-AGENT_CANON_OUTPUT_ROOT".to_string(),
                    format!("{CONTAINER_RUNTIME_DESTINATION}/template-exports/{output}"),
                ),
            ]),
            flags: BTreeSet::new(),
            remainder: vec![
                "export".to_string(),
                "--profile".to_string(),
                profile.to_string(),
                "--output".to_string(),
                format!("{CONTAINER_RUNTIME_DESTINATION}/template-exports/{output}"),
            ],
        };
        self.tool_run(&nested)
    }

    fn eval_sync_prepare(&self, options: &BTreeMap<String, String>) -> Result<Value> {
        let run_id = required_option(options, "--run-id")?;
        validate_safe_id(run_id, "eval_collection_invalid")?;
        self.locked(|| {
            let state = self.read_state()?;
            let spool = self.paths.spool.join(run_id);
            let Some(collection_bytes) = self.fs.read(&spool.join("collection.json"), "eval collection")? else {
                return Err(BootstrapError::new("eval_spool_missing", format!("eval spool does not exist: {run_id}")));
            };
            let collection: Value = serde_json::from_slice(&collection_bytes).map_err(|_| BootstrapError::new("eval_collection_invalid", format!("invalid eval collection: {run_id}")))?;
            if collection.get("run_id").and_then(Value::as_str) != Some(run_id) {
                return Err(BootstrapError::new("eval_collection_invalid", "eval collection run id mismatch"));
            }
            if collection.get("status").and_then(Value::as_str) != Some("collected") || collection.get("source_tree_unchanged").and_then(Value::as_bool) != Some(true) {
                return Err(BootstrapError::new("eval_collection_failed", "only a successful source-unchanged collection may be published"));
            }
            if collection.get("manifest_digest") != state.get("manifest_digest") {
                return Err(BootstrapError::new("eval_collection_generation_mismatch", "eval collection is not bound to the installed runtime generation"));
            }
            let source_root = collection.get("source_repository").and_then(Value::as_str).filter(|value| value.starts_with('/') && !value.chars().any(|ch| matches!(ch, '\0' | '\t' | '\n' | '\r'))).ok_or_else(|| BootstrapError::new("eval_collection_invalid", "eval source root is not an absolute safe path"))?;
            let mut target_digest = env::var("AGENT_CANON_TARGET_DIGEST").unwrap_or_default();
            if target_digest.is_empty() && source_root.starts_with("/targets/") {
                target_digest = source_root.trim_start_matches("/targets/").to_string();
            }
            if !target_digest.is_empty() { validate_safe_id(&target_digest, "eval_collection_invalid")?; }
            let request = spool.join("sync-request.tsv");
            if self.fs.read(&request, "eval sync request")?.is_some() {
                return Err(BootstrapError::new("eval_sync_request_exists", "eval sync request already exists"));
            }
            if source_root.chars().any(char::is_control) || !Path::new(&source_root).is_absolute() {
                return Err(BootstrapError::new("eval_sync_request_invalid", "source root is not a safe absolute path"));
            }
            let lines = format!("schema\tagent-canon.eval-sync-request.v1\noperation\tsync\nexecution-plane\tagentcanon_tool_container\nrun-id\t{run_id}\ntarget-digest\t{target_digest}\nsource-root\t{source_root}\n");
            self.fs.atomic_write(&request, lines.as_bytes(), 0o600)?;
            self.result(self.receipt("eval_sync", "ok", "host_archive_requested", (None, None), json!({"execution_plane":"host_archive_adapter", "status":"requested", "run_id":run_id}), Some(&state)))
        })
    }

    fn eval_collect(&self, options: &BTreeMap<String, String>) -> Result<Value> {
        let root_arg = required_option(options, "--root")?;
        let run_id = required_option(options, "--run-id")?;
        validate_safe_id(run_id, "eval_collection_invalid")?;
        let spool = self.paths.spool.join(run_id);
        if fs::symlink_metadata(&spool).is_ok() {
            return Err(BootstrapError::new(
                "eval_spool_exists",
                format!("eval spool already exists: {run_id}"),
            ));
        }
        let task_id = format!("eval-{run_id}");
        let exchange_nonce = random_hex(16)?;
        let exchange_task = self
            .paths
            .runtime_root
            .join("exchange/tasks")
            .join(&task_id);
        let exchange = exchange_task.join(&exchange_nonce);
        let exchange_runtime =
            format!("{CONTAINER_RUNTIME_DESTINATION}/exchange/tasks/{task_id}/{exchange_nonce}");
        let target_root = env::var("AGENT_CANON_TARGET_CONTAINER_ROOT")
            .ok()
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| root_arg.to_string());
        let target_path = PathBuf::from(target_root);
        self.locked(|| {
            if fs::symlink_metadata(&spool).is_ok() {
                return Err(BootstrapError::new("eval_spool_exists", format!("eval spool already exists: {run_id}")));
            }
            let mut state = self.read_state()?;
            let before_state = state.get("state").and_then(Value::as_str).unwrap_or("ready").to_string();
            let mut target = self.target_record(&target_path, "read-only")?;
            let declared_digest = env::var("AGENT_CANON_TARGET_DIGEST").ok();
            if let Some(digest) = declared_digest.as_deref() {
                if let Some(existing) = state.get("targets").and_then(Value::as_object).and_then(|targets| targets.get(digest)) { target = existing.clone(); }
            }
            let digest = target.get("digest").and_then(Value::as_str).ok_or_else(|| BootstrapError::new("target_not_registered", "eval root is not registered"))?.to_string();
            let registered = state.get("targets").and_then(Value::as_object).and_then(|targets| targets.get(&digest)).cloned().ok_or_else(|| BootstrapError::new("target_not_registered", "eval root is not registered"))?;
            if registered.get("root").and_then(Value::as_str) != Some(target_path.to_string_lossy().as_ref()) || registered.get("mode").and_then(Value::as_str) != Some("read-only") {
                return Err(BootstrapError::new("eval_target_not_read_only", "eval root is not registered read-only"));
            }
            let source = PathBuf::from(registered.get("root").and_then(Value::as_str).unwrap_or_default());
            let source_filesystem_root = self.target_namespace.physical_path(&source);
            let before_source = source_snapshot(&source_filesystem_root)?;
            let (_task, lease) = self.admit_task_locked(&mut state, &task_id, Some(&source), true)?;
            let lease = lease.ok_or_else(|| BootstrapError::new("task_lease_scope_invalid", "eval admission did not return its process lease"))?;
            self.fs.ensure_directory(&spool, 0o700)?;
            for directory in [&self.paths.runtime_root.join("exchange"), &self.paths.runtime_root.join("exchange/tasks"), &exchange_task, &exchange] {
                self.fs.ensure_directory(directory, 0o1733)?;
            }
            let canon_root = TOOL_SOURCE_DESTINATION;
            let target_container = registered.get("root").and_then(Value::as_str).unwrap_or_default();
            let log_root = format!("{exchange_runtime}/tasks/{run_id}/logs");
            let argv = vec![
                "python3".to_string(),
                format!("{TOOL_SOURCE_DESTINATION}/eval/producers/run_accumulated_agent_evals.py"),
                "--root".to_string(), canon_root.to_string(),
                "--target-root".to_string(), target_container.to_string(),
                "--runtime-root".to_string(), exchange_runtime.clone(),
                "--run-id".to_string(), run_id.to_string(),
                "--log-dir".to_string(), log_root.clone(),
            ];
            let environment = BTreeMap::from([
                ("AGENT_CANON_TARGET_ROOT".to_string(), target_container.to_string()),
                ("AGENT_CANON_TASK_ROOT".to_string(), target_container.to_string()),
                ("AGENT_CANON_NATIVE_BIN".to_string(), env::var("AGENT_CANON_NATIVE_BIN").unwrap_or_else(|_| NATIVE_CLI_DESTINATION.to_string())),
                ("GIT_CONFIG_COUNT".to_string(), "1".to_string()),
                ("GIT_CONFIG_KEY_0".to_string(), "safe.directory".to_string()),
                ("GIT_CONFIG_VALUE_0".to_string(), target_container.to_string()),
            ]);
            let timeout = self.manifest.pointer("/container/task_timeout_seconds").and_then(Value::as_u64).unwrap_or(3600);
            let process_argv = self.target_namespace.map_process_argv(&argv);
            let process_environment = self.target_namespace.map_process_environment(&environment);
            let command = run_tool_process(&process_argv, Path::new(canon_root), &process_environment, Duration::from_secs(timeout), &lease);
            let (stdout, stderr, exit) = match command {
                Ok(output) => (String::from_utf8_lossy(&output.stdout).into_owned(), String::from_utf8_lossy(&output.stderr).into_owned(), output.status.code().unwrap_or(128)),
                Err(error) => {
                    let _ = self.release_task_locked(&mut state, &task_id, "failed");
                    return Err(error);
                }
            };
            let stdout = redact_output(&stdout);
            let stderr = redact_output(&stderr);
            let stdout_bytes = stdout.as_bytes();
            let stderr_bytes = stderr.as_bytes();
            let log_quota = self.manifest.pointer("/container/task_log_quota_bytes").and_then(Value::as_u64).unwrap_or(0);
            if log_quota > 0 && (stdout_bytes.len() + stderr_bytes.len()) as u64 > log_quota {
                let _ = self.release_task_locked(&mut state, &task_id, "failed");
                return Err(BootstrapError::new("task_log_quota_exceeded", "eval producer streams exceed the configured task log quota"));
            }
            let task_path = self.paths.tasks.join(&task_id);
            let stdout_path = task_path.join("logs/stdout.log");
            let stderr_path = task_path.join("logs/stderr.log");
            self.fs.atomic_write(&stdout_path, stdout_bytes, 0o600)?;
            self.fs.atomic_write(&stderr_path, stderr_bytes, 0o600)?;
            let io = json!({"stdout_log":stdout_path,"stdout_digest":sha256_bytes(stdout_bytes),"stdout_bytes":stdout_bytes.len(),"stdout_preview":bounded_preview(&stdout,512),"stdout_truncated":stdout.chars().count()>512,"stderr_log":stderr_path,"stderr_digest":sha256_bytes(stderr_bytes),"stderr_bytes":stderr_bytes.len(),"stderr_preview":bounded_preview(&stderr,512),"stderr_truncated":stderr.chars().count()>512});
            let (mut matrix, mut metrics) = eval_producer_matrix(&stdout);
            metrics.insert("runner_exit".to_string(), json!(exit));
            metrics.insert("stdout_bytes".to_string(), json!(stdout_bytes.len()));
            metrics.insert("stderr_bytes".to_string(), json!(stderr_bytes.len()));
            let mut family_status = Map::new();
            for producer in &matrix {
                if let (Some(name), Some(status)) = (producer.get("name").and_then(Value::as_str), producer.get("status")) { family_status.insert(name.to_string(), status.clone()); }
            }
            let eval_export_source = exchange.join("eval-results");
            let logs_export_source = exchange.join("tasks").join(run_id).join("logs");
            let eval_export = spool.join("eval-results");
            let logs_export = spool.join("producer-logs");
            let eval_files = if fs::symlink_metadata(&eval_export_source).is_ok() { copy_tree(&self.fs, &eval_export_source, &eval_export)? } else { 0 };
            let log_files = if fs::symlink_metadata(&logs_export_source).is_ok() { copy_tree(&self.fs, &logs_export_source, &logs_export)? } else { 0 };
            for producer in &mut matrix {
                for stream in ["stdout", "stderr"] {
                    if let Some(path) = producer.get(stream).and_then(Value::as_str) {
                        let basename = Path::new(path).file_name().unwrap_or_default().to_string_lossy();
                        producer[stream] = json!(format!("eval-results/runs/{run_id}/producer-logs/{basename}"));
                    }
                }
            }
            let eval_bytes = if fs::symlink_metadata(&eval_export).is_ok() { directory_bytes(&eval_export)? } else { 0 };
            let log_bytes = if fs::symlink_metadata(&logs_export).is_ok() { directory_bytes(&logs_export)? } else { 0 };
            let exported_bytes = eval_bytes.saturating_add(log_bytes);
            let state_quota = self.manifest.pointer("/container/task_state_quota_bytes").and_then(Value::as_u64).unwrap_or(0);
            let source_after = source_snapshot(&source_filesystem_root)?;
            let unchanged = before_source == source_after;
            let mut collection = json!({
                "schema":"agent_canon.eval_collection.v1","run_id":run_id,"task_id":run_id,
                "source_repository":source,"source_head_before":before_source["head"],"source_git_status_before":before_source["git_status"],"source_tree_digest_before":before_source["tree_digest"],
                "agent_canon_commit":env::var("AGENT_CANON_SOURCE_HEAD").ok().or_else(|| source_snapshot(&self.paths.repository_root).ok().and_then(|value|value.get("head").and_then(Value::as_str).map(str::to_string))),
                "manifest_digest":self.manifest_digest,"tool_image_digest":state.pointer("/resources/image/id"),"exchange_nonce":exchange_nonce,
                "request_digest":sha256_text(&format!("{run_id}:{}:{exchange_nonce}:{}",source.display(),self.manifest_digest)),
                "capabilities":["target-read-only","producer-definitions-image-owned","tool-container-execution","external-runtime-write","no-network"],
                "family_status":family_status,"producer_matrix":matrix.clone(),"metrics":metrics,"timestamp":now()?,
                "source_head_after":source_after["head"],"source_git_status_after":source_after["git_status"],"source_tree_digest_after":source_after["tree_digest"],
                "source_tree_unchanged":unchanged,"status":"running"
            });
            let mut failure = None;
            if exit != 0 || matrix.is_empty() || matrix.iter().any(|item| item.get("status").and_then(Value::as_str) != Some("pass")) {
                collection["status"] = json!("failed");
                collection["failure"] = json!(if matrix.is_empty() { "eval_producer_protocol" } else { "eval_producer_failed" });
                failure = Some(BootstrapError::new("eval_producer_failed", "eval producer collection failed; spool retained"));
            } else if !unchanged {
                collection["status"] = json!("failed");
                collection["failure"] = json!("source_tree_changed");
                failure = Some(BootstrapError::new("source_tree_changed", "eval producer changed the registered source tree"));
            } else if state_quota > 0 && exported_bytes > state_quota {
                collection["status"] = json!("failed");
                collection["failure"] = json!("task_state_quota_exceeded");
                failure = Some(BootstrapError::new("task_state_quota_exceeded", format!("eval export requires {exported_bytes} bytes; quota is {state_quota}")));
            } else {
                collection["status"] = json!("collected");
            }
            collection["exported_files"] = json!({"eval_results":eval_files,"producer_logs":log_files});
            collection["metrics"]["exported_bytes"] = json!(exported_bytes);
            self.atomic_json(&spool.join("collection.json"), &collection, 0o600)?;
            if let Some(task) = state.get_mut("tasks").and_then(Value::as_object_mut).and_then(|tasks|tasks.get_mut(&task_id)) {
                task["eval"] = json!({"run_id":run_id,"collection":spool.join("collection.json"),"producer_matrix":collection["producer_matrix"],"io":io});
            }
            self.release_task_locked(&mut state, &task_id, if failure.is_none() { "completed" } else { "failed" })?;
            if failure.is_none() {
                clear_directory(&self.fs, &exchange)?;
                self.fs.remove_dir(&exchange)?;
            }
            let receipt = self.result(self.receipt("eval_collect", if failure.is_none() { "ok" } else { "error" }, if failure.is_none() { "eval_spooled" } else { "eval_failed" }, (Some(&before_state), state.get("state").and_then(Value::as_str)), json!({"spool":spool,"collection":collection,"io":io}), Some(&state)))?;
            if let Some(mut error) = failure {
                error.evidence = json!({"spool":spool,"collection":spool.join("collection.json"),"producer_matrix":collection["producer_matrix"],"source_tree_unchanged":collection["source_tree_unchanged"],"exit":exit,"receipt_path":receipt["receipt_path"]});
                return Err(error);
            }
            Ok(receipt)
        })
    }

    fn codex_prepare(&self) -> Result<Value> {
        self.locked(|| {
            let mut state = self.read_state()?;
            self.fs.ensure_directory(&self.paths.codex_home, 0o700)?;
            let skills = self.paths.repository_root.join(".codex/personal/skills");
            let skills_meta = fs::symlink_metadata(&skills).map_err(|_| BootstrapError::new("skill_source_missing", skills.display().to_string()))?;
            if skills_meta.file_type().is_symlink() || !skills_meta.is_dir() {
                return Err(BootstrapError::new("skill_source_missing", skills.display().to_string()));
            }
            let projection_root = env::var("AGENT_CANON_HOST_INSTALL_ROOT").ok().filter(|value| !value.trim().is_empty()).map(|value| {
                if !Path::new(&value).is_absolute() || value.chars().any(char::is_control) {
                    Err(BootstrapError::new("codex_projection_root_invalid", "host install root must be an absolute path without controls"))
                } else { Ok(PathBuf::from(value)) }
            }).transpose()?;
            let link_source = |source: &Path| {
                if let (Some(projection), Ok(relative)) = (&projection_root, source.strip_prefix(&self.paths.repository_root)) {
                    projection.join(relative)
                } else { source.to_path_buf() }
            };
            let mut desired = vec![("skills".to_string(), "agent-canon".to_string(), skills.clone(), link_source(&skills))];
            for (surface, source) in [
                ("agents", self.paths.repository_root.join(".codex/agents")),
                ("hooks", self.paths.repository_root.join(".codex/hooks")),
                ("config", self.paths.repository_root.join(".codex/config.toml")),
            ] {
                if fs::symlink_metadata(&source).is_ok() {
                    let metadata = fs::symlink_metadata(&source).map_err(|error| BootstrapError::new("codex_source_invalid", error.to_string()))?;
                    if metadata.file_type().is_symlink() {
                        return Err(BootstrapError::new("symlink_path_rejected", format!("Codex source is a symlink: {}", source.display())));
                    }
                    desired.push((surface.to_string(), source.file_name().unwrap_or_default().to_string_lossy().to_string(), source.clone(), link_source(&source)));
                }
            }
            let private_skills = self.paths.runtime_root.join("private-skills");
            if fs::symlink_metadata(&private_skills).is_ok_and(|metadata| metadata.is_dir() && !metadata.file_type().is_symlink()) {
                let mut private_files = Vec::new();
                collect_regular_files(&private_skills, &private_skills, &mut private_files)?;
                private_files.sort();
                for source in private_files {
                    let relative = source.strip_prefix(&private_skills).map_err(|error| BootstrapError::new("codex_source_invalid", error.to_string()))?.to_string_lossy().to_string();
                    desired.push(("skills".to_string(), relative, source.clone(), source));
                }
            }
            let desired_targets = desired.iter().map(|(surface, relative, _, _)| {
                if surface == "config" {
                    self.paths.codex_home.join(relative)
                } else {
                    self.paths.codex_home.join(surface).join(relative)
                }
            }).collect::<BTreeSet<_>>();
            let previous_manifest = self.paths.codex_home.join("manifest.json");
            let previous_entries = if let Some(bytes) = self.fs.read(&previous_manifest, "Codex manifest")? {
                let manifest: Value = serde_json::from_slice(&bytes).map_err(|_| BootstrapError::new("codex_manifest_invalid", "runtime-local Codex manifest is invalid"))?;
                manifest.get("links").and_then(Value::as_array).cloned().unwrap_or_default()
            } else { Vec::new() };
            let mut stale_links = Vec::new();
            for entry in previous_entries {
                if entry.get("managed").and_then(Value::as_bool) != Some(true) { continue; }
                let Some(target_value) = entry.get("target").and_then(Value::as_str) else { continue; };
                let target = PathBuf::from(target_value);
                if desired_targets.contains(&target) || !target.starts_with(&self.paths.codex_home) { continue; }
                let Some(source_value) = entry.get("source").and_then(Value::as_str) else { continue; };
                if let Ok(metadata) = fs::symlink_metadata(&target) {
                    if metadata.file_type().is_symlink() {
                        let existing = fs::read_link(&target).map_err(|error| BootstrapError::new("codex_manifest_invalid", error.to_string()))?;
                        let actual = if existing.is_absolute() { existing } else { target.parent().unwrap_or(&self.paths.codex_home).join(existing) };
                        if actual.as_path() == Path::new(source_value) {
                            self.fs.remove_entry(&target)?;
                            stale_links.push(target.to_string_lossy().to_string());
                        }
                    }
                }
            }
            let mut links = Vec::new();
            for (surface, relative, source, published_source) in desired {
                let target = if surface == "config" { self.paths.codex_home.join(&relative) } else { self.paths.codex_home.join(&surface).join(&relative) };
                if let Some(parent) = target.parent() { self.fs.ensure_directory(parent, 0o700)?; }
                #[cfg(unix)]
                let mut created = false;
                #[cfg(not(unix))]
                let created = false;
                match fs::symlink_metadata(&target) {
                    Ok(metadata) if metadata.file_type().is_symlink() => {
                        let existing = fs::read_link(&target).map_err(|error| BootstrapError::new("skill_collision", error.to_string()))?;
                        let expected = published_source.clone();
                        let actual = if existing.is_absolute() { existing } else { target.parent().unwrap_or(&self.paths.codex_home).join(existing) };
                        if actual != expected { return Err(BootstrapError::new("skill_collision", format!("managed Codex target already exists: {}", target.display()))); }
                    }
                    Ok(_) => return Err(BootstrapError::new("skill_collision", format!("managed Codex target already exists: {}", target.display()))),
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                        #[cfg(unix)]
                        std::os::unix::fs::symlink(&published_source, &target).map_err(|error| BootstrapError::new("skill_link_failed", error.to_string()))?;
                        #[cfg(not(unix))]
                        return Err(BootstrapError::new("skill_link_failed", "Codex skill links require a symlink-capable platform"));
                        #[cfg(unix)]
                        {created = true;}
                    }
                    Err(error) => return Err(BootstrapError::new("skill_link_failed", error.to_string())),
                }
                links.push(json!({"surface":surface,"source":published_source,"validation_source":source,"relative":relative,"target":target,"created":created,"managed":true}));
            }
            self.atomic_json(&previous_manifest, &json!({"schema":"agent-canon.managed-codex-home.v1","source_root":projection_root.as_ref().unwrap_or(&self.paths.repository_root),"manifest_digest":self.manifest_digest,"stale_links_removed":stale_links,"links":links}), 0o600)?;
            state["managed_links"] = Value::Array(links.clone());
            self.write_state(&mut state)?;
            let current = state.get("state").and_then(Value::as_str).unwrap_or("uninstalled").to_string();
            self.result(self.receipt("codex_prepare", "ok", "codex_home_ready", (Some(&current), Some(&current)), json!({"codex_home":self.paths.codex_home,"links":links,"requires_new_session":true}), Some(&state)))
        })
    }

    fn codex_launch(&self, options: &BTreeMap<String, String>) -> Result<Value> {
        let project = existing_directory(
            Path::new(required_option(options, "--project-root")?),
            "Codex project root",
        )?;
        let prepared = self.codex_prepare()?;
        let sessions = self.paths.codex_home.join("sessions");
        self.fs.ensure_directory(&sessions, 0o700)?;
        let executable = env::var("AGENT_CANON_CODEX").unwrap_or_else(|_| "codex".to_string());
        let status = Command::new(executable)
            .arg("--project-root")
            .arg(&project)
            .current_dir(&project)
            .env("CODEX_HOME", &self.paths.codex_home)
            .env(
                "AGENT_CANON_CONTROL_PARENT_ROOT",
                &self.paths.control_parent_root,
            )
            .env("AGENT_CANON_RUNTIME_ROOT", &self.paths.runtime_root)
            .env(CODEX_SESSION_ROOT_ENV, &sessions)
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .status()
            .map_err(|_| {
                BootstrapError::new("codex_unavailable", "Codex executable is unavailable")
            })?;
        if !status.success() {
            return Err(BootstrapError::new(
                "codex_failed",
                format!("Codex exited with {}", status.code().unwrap_or(128)),
            ));
        }
        Ok(prepared)
    }

    fn gc(&self, dry_run: bool) -> Result<Value> {
        self.locked(|| {
            let mut state = self.read_state()?;
            let current = state.get("current_generation").cloned().unwrap_or(Value::Null);
            let rollback = state.get("rollback_generation").cloned().unwrap_or(Value::Null);
            let quota = self.manifest.pointer("/container/runtime_quota_bytes").and_then(Value::as_u64).unwrap_or(0);
            let cache_quota = self.manifest.pointer("/container/cache_quota_bytes").and_then(Value::as_u64).unwrap_or(0);
            let archive_quota = self.manifest.pointer("/container/archive_lease_quota_bytes").and_then(Value::as_u64).unwrap_or(0);
            let runtime_bytes = directory_bytes(&self.paths.runtime_root)?;
            let cache_bytes = directory_bytes(&self.paths.cache)?;
            let archive_bytes = directory_bytes(&self.paths.archive)?;
            let high_water = quota > 0 && runtime_bytes >= quota.saturating_mul(8) / 10;
            let cache_high_water = cache_quota > 0 && cache_bytes >= cache_quota.saturating_mul(8) / 10;
            let archive_high_water = archive_quota > 0 && archive_bytes >= archive_quota.saturating_mul(8) / 10;
            let tasks = state.get("tasks").and_then(Value::as_object).cloned().unwrap_or_default();
            let mut completed_tasks = tasks.iter().filter(|(_, task)| ["completed", "cancelled"].contains(&task.get("state").and_then(Value::as_str).unwrap_or_default()) && task.get("pinned").and_then(Value::as_bool) != Some(true)).map(|(id, task)| (id.clone(), task.get("finished_at").and_then(Value::as_str).unwrap_or_default().to_string())).collect::<Vec<_>>();
            completed_tasks.sort_by(|left, right| left.1.cmp(&right.1));
            let generations = state.get("generations").and_then(Value::as_object).cloned().unwrap_or_default();
            let stale_generations = generations.iter().filter(|(id, generation)| current.as_str() != Some(id.as_str()) && rollback.as_str() != Some(id.as_str()) && !["in-use", "pinned"].contains(&generation.get("state").and_then(Value::as_str).unwrap_or_default())).map(|(id, _)| id.clone()).collect::<Vec<_>>();
            let candidates = completed_tasks.iter().map(|(id, _)| format!("task:{id}")).chain(stale_generations.iter().map(|id| format!("generation:{id}"))).collect::<Vec<_>>();
            let mut deleted = Vec::new();
            let mut archive_cleanup_blocked_by_spool = false;
            if !dry_run && (high_water || cache_high_water || archive_high_water) {
                if cache_high_water && state.get("active_task_count").and_then(Value::as_u64).unwrap_or(0) == 0 {
                    clear_directory_reject_symlinks(&self.fs, &self.paths.cache)?;
                    deleted.push("cache".to_string());
                }
                if archive_high_water && state.get("active_task_count").and_then(Value::as_u64).unwrap_or(0) == 0 {
                    let spool_has_entries = !self.fs.entries(&self.paths.spool)?.is_empty();
                    if spool_has_entries {
                        archive_cleanup_blocked_by_spool = true;
                    } else {
                        clear_directory_reject_symlinks(&self.fs, &self.paths.archive)?;
                        deleted.push("archive".to_string());
                    }
                }
                if high_water {
                    for (id, _) in &completed_tasks {
                        let path = self.paths.tasks.join(id);
                        if let Ok(metadata) = fs::symlink_metadata(&path) {
                            if metadata.file_type().is_symlink() {
                                return Err(BootstrapError::new("symlink_path_rejected", format!("task path is a symlink: {}", path.display())));
                            }
                            if metadata.is_dir() {
                                clear_directory_reject_symlinks(&self.fs, &path)?;
                                self.fs.remove_dir(&path)?;
                            }
                        }
                        if let Some(tasks) = state.get_mut("tasks").and_then(Value::as_object_mut) { tasks.remove(id); }
                        deleted.push(format!("task:{id}"));
                    }
                    for id in &stale_generations {
                        let path = self.paths.generations.join(id);
                        if let Ok(metadata) = fs::symlink_metadata(&path) {
                            if metadata.file_type().is_symlink() {
                                return Err(BootstrapError::new("symlink_path_rejected", format!("generation path is a symlink: {}", path.display())));
                            }
                            if metadata.is_dir() {
                                clear_directory_reject_symlinks(&self.fs, &path)?;
                                self.fs.remove_dir(&path)?;
                            }
                        }
                        if let Some(generations) = state.get_mut("generations").and_then(Value::as_object_mut) { generations.remove(id); }
                        deleted.push(format!("generation:{id}"));
                    }
                }
                self.write_state(&mut state)?;
            }
            self.result(self.receipt("gc", "ok", if dry_run { "gc_plan" } else { "gc_complete" }, (state.get("state").and_then(Value::as_str), state.get("state").and_then(Value::as_str)), json!({"dry_run":dry_run,"high_water":high_water,"cache_high_water":cache_high_water,"archive_high_water":archive_high_water,"archive_cleanup_blocked_by_spool":archive_cleanup_blocked_by_spool,"candidates":candidates,"preserved":{"current_generation":current,"rollback_generation":rollback,"active_task_count":state.get("active_task_count").unwrap_or(&Value::Null),"unpublished_spool":true},"deleted":deleted}), Some(&state)))
        })
    }

    fn materialize_rollback_plan(&self, state: &Value) -> Result<()> {
        let path = self.paths.container_runtime.join("rollback-plan.tsv");
        let rollback_id = state.get("rollback_generation").and_then(Value::as_str);
        let Some(rollback_id) = rollback_id else {
            return self.fs.remove_file(&path);
        };
        let generation = state
            .get("generations")
            .and_then(Value::as_object)
            .and_then(|items| items.get(rollback_id))
            .ok_or_else(|| {
                BootstrapError::new(
                    "rollback_plan_invalid",
                    "rollback generation is unavailable",
                )
            })?;
        let resources = state.get("resources").cloned().unwrap_or_else(|| json!({}));
        let image = resources.get("image").cloned().unwrap_or_else(|| json!({}));
        let image_id = generation
            .get("image_id")
            .and_then(Value::as_str)
            .or_else(|| image.get("id").and_then(Value::as_str))
            .ok_or_else(|| {
                BootstrapError::new(
                    "rollback_plan_invalid",
                    "rollback image identity is incomplete",
                )
            })?;
        let image_ref = generation
            .get("image_ref")
            .and_then(Value::as_str)
            .or_else(|| image.get("tag").and_then(Value::as_str))
            .unwrap_or(image_id);
        if !image_id.starts_with("sha256:")
            || image_ref.is_empty()
            || image_ref.chars().any(char::is_control)
        {
            return Err(BootstrapError::new(
                "rollback_plan_invalid",
                "rollback image identity is incomplete",
            ));
        }
        let targets = generation.get("targets").or_else(|| state.get("targets"));
        let targets = targets.and_then(Value::as_object).ok_or_else(|| {
            BootstrapError::new(
                "rollback_plan_invalid",
                "rollback target snapshot is invalid",
            )
        })?;
        let mut lines = vec![
            "schema\tagent-canon.rollback-plan.v1".to_string(),
            format!("image-id\t{image_id}"),
            format!("image-ref\t{image_ref}"),
        ];
        for (digest, target) in targets {
            validate_safe_id(digest, "rollback_plan_invalid")?;
            let source = target
                .get("host_root")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    BootstrapError::new(
                        "rollback_plan_invalid",
                        "rollback target source is invalid",
                    )
                })?;
            let destination = target.get("root").and_then(Value::as_str).unwrap_or("");
            let mode = target.get("mode").and_then(Value::as_str).unwrap_or("");
            if !source.starts_with('/')
                || source.chars().any(char::is_control)
                || destination != format!("/targets/{digest}")
                || mode != "read-only"
            {
                return Err(BootstrapError::new(
                    "rollback_plan_invalid",
                    "rollback target mount is invalid",
                ));
            }
            lines.push(format!("mount\tmount\t{source}\t{destination}\ttrue"));
        }
        lines.push(String::new());
        self.fs
            .atomic_write(&path, lines.join("\n").as_bytes(), 0o444)
    }
}

fn validate_safe_id(value: &str, code: &str) -> Result<()> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_.-".contains(&byte))
        || !value.as_bytes()[0].is_ascii_alphanumeric()
    {
        return Err(BootstrapError::new(
            code,
            format!("identifier is not safe: {value:?}"),
        ));
    }
    Ok(())
}

fn validate_tool_argv(argv: &[String]) -> Result<()> {
    if argv.is_empty() || argv.iter().any(|value| value.contains('\0')) {
        return Err(BootstrapError::new(
            "argv_required",
            "exec requires a non-empty argv list",
        ));
    }
    let executable = argv[0].as_str();
    let agent_canon_script = argv.get(1).is_some_and(|script| {
        script.starts_with("/opt/agent-canon/source/tools/")
            || script == "/opt/agent-canon/source/eval/producers/run_accumulated_agent_evals.py"
    });
    if ["agent-canon", "agent-canon-tool"].contains(&executable)
        || (["python3", "bash"].contains(&executable) && agent_canon_script)
    {
        return Ok(());
    }
    Err(BootstrapError::new(
        "tool_plane_command_rejected",
        "exec accepts AgentCanon tools only; project commands use the project execution environment",
    ).with_evidence(json!({"argv": redact_argv(argv)})))
}

fn run_tool_process(
    argv: &[String],
    cwd: &Path,
    environment: &BTreeMap<String, String>,
    timeout: Duration,
    lease: &cap_std::fs::File,
) -> Result<Output> {
    #[cfg(not(unix))]
    let _ = lease;
    let mut command = Command::new(&argv[0]);
    command
        .args(&argv[1..])
        .current_dir(cwd)
        .env_remove("AGENT_CANON_TARGET_HOST_ROOT")
        .envs(environment)
        .stdin(Stdio::inherit())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    let spawn = {
        use nix::fcntl::{fcntl, FcntlArg, FdFlag};
        let original_flags = fcntl(lease, FcntlArg::F_GETFD)
            .map_err(|error| BootstrapError::new("task_lease_lock_failed", error.to_string()))?;
        let original_flags = FdFlag::from_bits_truncate(original_flags);
        fcntl(
            lease,
            FcntlArg::F_SETFD(original_flags & !FdFlag::FD_CLOEXEC),
        )
        .map_err(|error| BootstrapError::new("task_lease_lock_failed", error.to_string()))?;
        let child = command.spawn();
        let restored = fcntl(lease, FcntlArg::F_SETFD(original_flags));
        restored
            .map_err(|error| BootstrapError::new("task_lease_lock_failed", error.to_string()))?;
        child
    };
    #[cfg(not(unix))]
    let spawn = command.spawn();
    let mut child = spawn.map_err(|_| {
        BootstrapError::new(
            "tool_execution_failed",
            "container tool execution is unavailable",
        )
    })?;
    let mut stdout = child.stdout.take().ok_or_else(|| {
        BootstrapError::new(
            "tool_execution_failed",
            "command stdout pipe is unavailable",
        )
    })?;
    let mut stderr = child.stderr.take().ok_or_else(|| {
        BootstrapError::new(
            "tool_execution_failed",
            "command stderr pipe is unavailable",
        )
    })?;
    let stdout_reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        let _ = stdout.read_to_end(&mut bytes);
        bytes
    });
    let stderr_reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        let _ = stderr.read_to_end(&mut bytes);
        bytes
    });
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if started.elapsed() <= timeout => {
                std::thread::sleep(Duration::from_millis(20))
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = stdout_reader.join();
                let _ = stderr_reader.join();
                return Err(BootstrapError::new(
                    "docker_command_timeout",
                    "container tool execution timed out",
                ));
            }
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(BootstrapError::new(
                    "tool_execution_failed",
                    format!("cannot wait for tool process: {error}"),
                ));
            }
        }
    };
    let stdout = stdout_reader
        .join()
        .map_err(|_| BootstrapError::new("tool_execution_failed", "stdout collector failed"))?;
    let stderr = stderr_reader
        .join()
        .map_err(|_| BootstrapError::new("tool_execution_failed", "stderr collector failed"))?;
    Ok(Output {
        status,
        stdout,
        stderr,
    })
}

fn redact_output(value: &str) -> String {
    let secret = regex::Regex::new(
        r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|authorization)\b\s*[=:]\s*)([^\s,;]+)",
    )
    .expect("static redaction pattern");
    let bearer = regex::Regex::new(r"(?i)\bBearer\s+[^\s,;]+").expect("static bearer pattern");
    bearer
        .replace_all(
            &secret.replace_all(value, "$1<redacted>"),
            "Bearer <redacted>",
        )
        .into_owned()
}

fn redact_argv(argv: &[String]) -> Vec<String> {
    let mut hide_next = false;
    argv.iter()
        .map(|value| {
            if hide_next {
                hide_next = false;
                return "<redacted>".to_string();
            }
            let lower = value.to_ascii_lowercase();
            if value.starts_with('-')
                && [
                    "token",
                    "password",
                    "secret",
                    "api-key",
                    "api_key",
                    "authorization",
                ]
                .iter()
                .any(|key| lower.contains(key))
            {
                if let Some((name, _)) = value.split_once('=') {
                    return format!("{name}=<redacted>");
                }
                hide_next = true;
                return value.clone();
            }
            redact_output(value)
        })
        .collect()
}

fn bounded_preview(value: &str, limit: usize) -> String {
    let characters = value.chars().collect::<Vec<_>>();
    if characters.len() <= limit {
        return value.to_string();
    }
    let separator = "\n...<truncated>...\n";
    let available = limit.saturating_sub(separator.len());
    let prefix = available / 2;
    let suffix = available - prefix;
    let beginning = characters.iter().take(prefix).copied().collect::<String>();
    let ending = characters
        .iter()
        .skip(characters.len() - suffix)
        .copied()
        .collect::<String>();
    format!("{beginning}{separator}{ending}")
}

fn directory_bytes(path: &Path) -> Result<u64> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        BootstrapError::new(
            "path_unresolvable",
            format!("cannot inspect {}: {error}", path.display()),
        )
    })?;
    // Quota measurement follows the established runtime contract: symlinks
    // contribute no bytes and are never traversed. Destructive GC separately
    // rejects symlink entries before removing their containing directories.
    if metadata.file_type().is_symlink() {
        return Ok(0);
    }
    if metadata.is_file() {
        return Ok(metadata.len());
    }
    if !metadata.is_dir() {
        return Ok(0);
    }
    let mut bytes = 0u64;
    for entry in fs::read_dir(path)
        .map_err(|error| BootstrapError::new("path_unresolvable", error.to_string()))?
    {
        let entry =
            entry.map_err(|error| BootstrapError::new("path_unresolvable", error.to_string()))?;
        bytes = bytes.saturating_add(directory_bytes(&entry.path())?);
    }
    Ok(bytes)
}

fn same_target_record(left: &Value, right: &Value) -> bool {
    [
        "root",
        "mode",
        "digest",
        "allowed_paths",
        "purpose",
        "authority",
    ]
    .iter()
    .all(|key| left.get(*key) == right.get(*key))
}

fn target_generation(state: &mut Value, targets: Value) {
    let image = state
        .get("resources")
        .and_then(|resources| resources.get("image"))
        .cloned()
        .unwrap_or_else(|| json!({}));
    let image_snapshot = json!({
        "image_id": image.get("id"),
        "image_ref": image.get("tag"),
    });
    let old_generation = state
        .get("current_generation")
        .and_then(Value::as_str)
        .map(str::to_string);
    let counter = state
        .get("generation_counter")
        .and_then(Value::as_u64)
        .unwrap_or(0)
        + 1;
    state["generation_counter"] = json!(counter);
    let generation = format!("generation-{counter}");
    if let Some(old_generation) = &old_generation {
        let previous_targets = state.get("targets").cloned().unwrap_or_else(|| json!({}));
        if !state.get("generations").is_some_and(Value::is_object) {
            state["generations"] = json!({});
        }
        state["generations"][old_generation] = json!({
            "image_id": image_snapshot["image_id"],
            "image_ref": image_snapshot["image_ref"],
            "targets": previous_targets,
            "state": "rollback",
        });
    }
    if !state.get("generations").is_some_and(Value::is_object) {
        state["generations"] = json!({});
    }
    state["generations"][&generation] = json!({
        "image_id": image_snapshot["image_id"],
        "image_ref": image_snapshot["image_ref"],
        "targets": targets.clone(),
        "state": "current",
    });
    state["targets"] = targets;
    state["current_generation"] = json!(generation);
    state["rollback_generation"] = old_generation.map_or(Value::Null, Value::String);
}

fn clear_directory(filesystem: &RuntimeFs, directory: &Path) -> Result<()> {
    let entries = filesystem.entries(directory)?;
    for name in entries {
        let path = directory.join(name);
        let metadata = fs::symlink_metadata(&path).map_err(|error| {
            BootstrapError::new(
                "path_unresolvable",
                format!("cannot inspect {}: {error}", path.display()),
            )
        })?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            filesystem.remove_entry(&path)?;
        } else {
            clear_directory(filesystem, &path)?;
            filesystem.remove_dir(&path)?;
        }
    }
    Ok(())
}

fn clear_directory_reject_symlinks(filesystem: &RuntimeFs, directory: &Path) -> Result<()> {
    for name in filesystem.entries(directory)? {
        let path = directory.join(name);
        let metadata = fs::symlink_metadata(&path).map_err(|error| {
            BootstrapError::new(
                "path_unresolvable",
                format!("cannot inspect {}: {error}", path.display()),
            )
        })?;
        if metadata.file_type().is_symlink() {
            return Err(BootstrapError::new(
                "symlink_path_rejected",
                format!("cleanup path is a symlink: {}", path.display()),
            ));
        }
        if metadata.is_dir() {
            clear_directory_reject_symlinks(filesystem, &path)?;
            filesystem.remove_dir(&path)?;
        } else if metadata.is_file() {
            filesystem.remove_file(&path)?;
        }
    }
    Ok(())
}

fn copy_tree(filesystem: &RuntimeFs, source: &Path, destination: &Path) -> Result<u64> {
    let metadata = fs::symlink_metadata(source).map_err(|error| {
        BootstrapError::new(
            "eval_export_invalid",
            format!("cannot inspect {}: {error}", source.display()),
        )
    })?;
    if metadata.file_type().is_symlink() {
        return Err(BootstrapError::new(
            "eval_exchange_symlink",
            format!("exchange contains a symlink: {}", source.display()),
        ));
    }
    if metadata.is_file() {
        let bytes = filesystem.read(source, "eval export")?.ok_or_else(|| {
            BootstrapError::new(
                "eval_export_invalid",
                format!("export disappeared: {}", source.display()),
            )
        })?;
        filesystem.atomic_write(destination, &bytes, 0o600)?;
        return Ok(1);
    }
    if !metadata.is_dir() {
        return Ok(0);
    }
    filesystem.ensure_directory(destination, 0o700)?;
    let mut count = 0;
    for name in filesystem.entries(source)? {
        count += copy_tree(filesystem, &source.join(&name), &destination.join(name))?;
    }
    Ok(count)
}

fn collect_regular_files(root: &Path, directory: &Path, output: &mut Vec<PathBuf>) -> Result<()> {
    let metadata = fs::symlink_metadata(directory)
        .map_err(|error| BootstrapError::new("codex_source_invalid", error.to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(BootstrapError::new(
            "codex_source_invalid",
            format!("unsafe Codex source directory: {}", directory.display()),
        ));
    }
    for entry in fs::read_dir(directory)
        .map_err(|error| BootstrapError::new("codex_source_invalid", error.to_string()))?
    {
        let path = entry
            .map_err(|error| BootstrapError::new("codex_source_invalid", error.to_string()))?
            .path();
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| BootstrapError::new("codex_source_invalid", error.to_string()))?;
        if metadata.file_type().is_symlink() {
            continue;
        }
        if metadata.is_dir() {
            collect_regular_files(root, &path, output)?;
        } else if metadata.is_file() {
            if !path.starts_with(root) {
                return Err(BootstrapError::new(
                    "codex_source_invalid",
                    "Codex source escaped its owner directory",
                ));
            }
            output.push(path);
        }
    }
    Ok(())
}

fn eval_producer_matrix(stdout: &str) -> (Vec<Value>, Map<String, Value>) {
    let producer_line = regex::Regex::new(
        r"^ACCUMULATED_AGENT_EVAL_PRODUCER=([^:]+):(pass|fail):stdout=([^:]*):stderr=(.*)$",
    )
    .expect("static eval producer pattern");
    let mut matrix = Vec::new();
    let mut metrics = Map::new();
    for line in stdout.lines() {
        if let Some(captures) = producer_line.captures(line.trim()) {
            let status = captures
                .get(2)
                .map(|value| value.as_str())
                .unwrap_or_default();
            matrix.push(json!({
                "name": captures.get(1).map(|value| value.as_str()).unwrap_or_default(),
                "status": status,
                "stdout": captures.get(3).map(|value| value.as_str()).unwrap_or_default(),
                "stderr": captures.get(4).map(|value| value.as_str()).unwrap_or_default(),
                "exit": if status == "pass" { 0 } else { 1 },
            }));
        } else if let Some(value) = line.strip_prefix("ACCUMULATED_AGENT_EVAL_PRODUCERS=") {
            if let Ok(count) = value.parse::<u64>() {
                metrics.insert("producer_count".to_string(), json!(count));
            }
        } else if let Some(value) = line.strip_prefix("ACCUMULATED_AGENT_EVAL_FAILED=") {
            metrics.insert("failed".to_string(), json!(value));
        } else if let Some(value) = line.strip_prefix("ACCUMULATED_AGENT_EVAL=") {
            metrics.insert("overall".to_string(), json!(value));
        }
    }
    if !matrix.is_empty() {
        metrics
            .entry("producer_count".to_string())
            .or_insert_with(|| json!(matrix.len()));
        metrics.insert(
            "failed_count".to_string(),
            json!(matrix
                .iter()
                .filter(|item| item.get("status").and_then(Value::as_str) != Some("pass"))
                .count()),
        );
    }
    (matrix, metrics)
}

fn source_snapshot(root: &Path) -> Result<Value> {
    let safe_directory = absolute_path(root)?;
    let run_git = |arguments: &[&str]| {
        Command::new("git")
            .arg("-C")
            .arg(root)
            .args(arguments)
            .env("GIT_CONFIG_COUNT", "1")
            .env("GIT_CONFIG_KEY_0", "safe.directory")
            .env("GIT_CONFIG_VALUE_0", safe_directory.as_os_str())
            .output()
    };
    let status =
        run_git(&["status", "--porcelain=v1", "--untracked-files=all"]).map_err(|error| {
            BootstrapError::new(
                "source_snapshot_failed",
                format!("cannot read Git status: {error}"),
            )
        })?;
    let head = run_git(&["rev-parse", "--verify", "HEAD"]).map_err(|error| {
        BootstrapError::new(
            "source_snapshot_failed",
            format!("cannot read Git HEAD: {error}"),
        )
    })?;
    let inventory = run_git(&[
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    ])
    .map_err(|error| {
        BootstrapError::new(
            "source_snapshot_failed",
            format!("cannot enumerate Git paths: {error}"),
        )
    })?;
    if !status.status.success() || !head.status.success() || !inventory.status.success() {
        return Err(BootstrapError::new(
            "source_snapshot_failed",
            "eval source must be a readable Git checkout",
        ));
    }
    let status_text = String::from_utf8_lossy(&status.stdout).into_owned();
    let head_text = String::from_utf8_lossy(&head.stdout).trim().to_string();
    let mut paths = inventory
        .stdout
        .split(|byte| *byte == 0)
        .filter(|path| !path.is_empty())
        .map(|bytes| {
            #[cfg(unix)]
            {
                use std::os::unix::ffi::OsStringExt;
                PathBuf::from(OsString::from_vec(bytes.to_vec()))
            }
            #[cfg(not(unix))]
            {
                PathBuf::from(String::from_utf8_lossy(bytes).into_owned())
            }
        })
        .collect::<Vec<_>>();
    paths.sort();
    let mut digest = Sha256::new();
    let mut file_count = 0u64;
    for relative in paths {
        if relative.is_absolute()
            || relative.components().any(|component| {
                matches!(
                    component,
                    Component::ParentDir | Component::RootDir | Component::Prefix(_)
                )
            })
        {
            return Err(BootstrapError::new(
                "source_snapshot_failed",
                format!("unsafe Git inventory path: {}", relative.display()),
            ));
        }
        let path = root.join(&relative);
        let metadata = fs::symlink_metadata(&path).map_err(|error| {
            BootstrapError::new(
                "source_snapshot_failed",
                format!(
                    "source changed while being read: {}: {error}",
                    path.display()
                ),
            )
        })?;
        let (kind, payload) = if metadata.file_type().is_symlink() {
            let target = fs::read_link(&path).map_err(|error| {
                BootstrapError::new(
                    "source_snapshot_failed",
                    format!("cannot read source symlink: {error}"),
                )
            })?;
            (
                b"symlink".as_slice(),
                target.to_string_lossy().as_bytes().to_vec(),
            )
        } else if metadata.is_file() {
            (
                b"file".as_slice(),
                fs::read(&path).map_err(|error| {
                    BootstrapError::new(
                        "source_snapshot_failed",
                        format!("source changed while being read: {path:?}: {error}"),
                    )
                })?,
            )
        } else {
            continue;
        };
        let relative_text = relative.to_string_lossy();
        digest.update(kind);
        digest.update([0]);
        digest.update(relative_text.as_bytes());
        digest.update([0]);
        digest.update(Sha256::digest(payload));
        digest.update([0]);
        file_count += 1;
    }
    let tree_digest = digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    Ok(json!({
        "head": head_text,
        "git_status": status_text,
        "git_status_digest": sha256_text(&status_text),
        "tree_digest": tree_digest,
        "file_count": file_count,
    }))
}

fn image_suffix(image_id: &str) -> String {
    image_id.chars().skip(7).take(12).collect()
}

fn read_target_manifest(
    filesystem: &RuntimeFs,
    path: &Path,
    missing_code: &str,
    invalid_code: &str,
) -> Result<Value> {
    let Some(bytes) = filesystem.read(path, "target mount manifest")? else {
        return Err(BootstrapError::new(
            missing_code,
            "host did not provide the requested target mount manifest",
        ));
    };
    let text = std::str::from_utf8(&bytes)
        .map_err(|_| BootstrapError::new(invalid_code, "target mount manifest is not UTF-8"))?;
    let mut targets = Map::new();
    for (index, line) in text.lines().enumerate() {
        let fields = line.split('\t').collect::<Vec<_>>();
        if fields.len() != 5 {
            return Err(BootstrapError::new(
                invalid_code,
                format!("previous target mount row {} is not TSV", index + 1),
            ));
        }
        let (kind, digest, source, destination, mode) =
            (fields[0], fields[1], fields[2], fields[3], fields[4]);
        if kind != "target"
            || validate_safe_id(digest, invalid_code).is_err()
            || !source.starts_with('/')
            || source.chars().any(char::is_control)
            || destination != format!("/targets/{digest}")
            || mode != "read-only"
            || targets.contains_key(digest)
        {
            return Err(BootstrapError::new(
                invalid_code,
                format!("previous target mount row {} is invalid", index + 1),
            ));
        }
        targets.insert(
            digest.to_string(),
            json!({
                "digest": digest,
                "host_root": source,
                "root": destination,
                "mode": mode,
            }),
        );
    }
    Ok(Value::Object(targets))
}

fn toml_quote(value: &str) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "\"\"".to_string())
}

fn absolute_path(path: &Path) -> Result<PathBuf> {
    if !path.is_absolute() {
        return Err(BootstrapError::new(
            "path_invalid",
            format!("path must be absolute: {}", path.display()),
        ));
    }
    let normalized = crate::path_resolution::resolve_non_strict(path)
        .map_err(|error| BootstrapError::new("path_unresolvable", error.to_string()))?;
    Ok(normalized)
}

fn existing_directory(path: &Path, field: &str) -> Result<PathBuf> {
    if !path.is_absolute() {
        return Err(BootstrapError::new(
            "path_invalid",
            format!("{field} must be absolute: {}", path.display()),
        ));
    }
    let mut current = PathBuf::from("/");
    for component in path.components().skip(1) {
        let Component::Normal(name) = component else {
            return Err(BootstrapError::new(
                "path_invalid",
                format!("{field} contains an unsafe component: {}", path.display()),
            ));
        };
        current.push(name);
        let metadata = fs::symlink_metadata(&current).map_err(|error| {
            BootstrapError::new(
                "path_missing",
                format!("{field} is unavailable: {}: {error}", path.display()),
            )
        })?;
        if metadata.file_type().is_symlink() {
            return Err(BootstrapError::new(
                "symlink_path_rejected",
                format!("{field} contains a symlink: {}", current.display()),
            ));
        }
        if !metadata.is_dir() {
            return Err(BootstrapError::new(
                "path_not_directory",
                format!("{field} is not a directory: {}", current.display()),
            ));
        }
    }
    fs::canonicalize(path).map_err(|error| {
        BootstrapError::new(
            "path_unresolvable",
            format!("cannot resolve {field}: {}: {error}", path.display()),
        )
    })
}

fn validate_runtime_roots(control: &Path, runtime: &Path) -> Result<()> {
    if !runtime.starts_with(control) || runtime == control {
        return Err(BootstrapError::new(
            "runtime_root_escape",
            format!("runtime-root must be beneath {}", control.display()),
        ));
    }
    let mut current = PathBuf::from("/");
    for component in runtime.components().skip(1) {
        let Component::Normal(name) = component else {
            return Err(BootstrapError::new(
                "path_invalid",
                format!(
                    "runtime-root contains an unsafe component: {}",
                    runtime.display()
                ),
            ));
        };
        current.push(name);
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(BootstrapError::new(
                    "symlink_path_rejected",
                    format!("runtime-root contains a symlink: {}", current.display()),
                ));
            }
            Ok(metadata) if !metadata.is_dir() => {
                return Err(BootstrapError::new(
                    "path_not_directory",
                    format!(
                        "runtime-root component is not a directory: {}",
                        current.display()
                    ),
                ));
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => break,
            Err(error) => {
                return Err(BootstrapError::new("path_unresolvable", error.to_string()));
            }
        }
    }
    Ok(())
}

fn load_manifest(path: &Path) -> Result<(Value, String)> {
    let raw = RuntimeFs::new()?.read(path, "manifest")?.ok_or_else(|| {
        BootstrapError::new(
            "manifest_missing",
            format!("manifest is unavailable: {}", path.display()),
        )
    })?;
    let text = std::str::from_utf8(&raw)
        .map_err(|_| BootstrapError::new("manifest_invalid", "manifest is not UTF-8"))?;
    let payload: Value = toml_edit::de::from_str(text).map_err(|_| {
        BootstrapError::new(
            "manifest_invalid",
            format!("cannot parse manifest: {}", path.display()),
        )
    })?;
    let container = payload
        .get("container")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            BootstrapError::new("manifest_invalid", "manifest.container must be a table")
        })?;
    let labels = container
        .get("labels")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            BootstrapError::new(
                "manifest_invalid",
                "manifest.container.labels must be an array",
            )
        })?
        .iter()
        .filter_map(Value::as_str)
        .collect::<BTreeSet<_>>();
    if REQUIRED_LABELS.iter().any(|label| !labels.contains(label)) {
        return Err(BootstrapError::new(
            "manifest_invalid",
            "manifest is missing required ownership labels",
        ));
    }
    if container.get("max_instances").and_then(Value::as_i64) != Some(1)
        || container.get("network").and_then(Value::as_str) != Some("none")
    {
        return Err(BootstrapError::new(
            "manifest_invalid",
            "shared runtime requires one network=none container",
        ));
    }
    for key in [
        "cpus",
        "memory_bytes",
        "pids_limit",
        "max_parallel_tasks",
        "task_state_quota_bytes",
        "task_log_quota_bytes",
    ] {
        if container
            .get(key)
            .and_then(Value::as_i64)
            .is_none_or(|value| value <= 0)
        {
            return Err(BootstrapError::new(
                "manifest_invalid",
                format!("container.{key} must be a positive integer"),
            ));
        }
    }
    for key in [
        "health_start_period_seconds",
        "health_timeout_seconds",
        "health_poll_interval_seconds",
    ] {
        if container
            .get(key)
            .and_then(Value::as_f64)
            .is_none_or(|value| value <= 0.0)
        {
            return Err(BootstrapError::new(
                "manifest_invalid",
                format!("container.{key} must be positive"),
            ));
        }
    }
    Ok((payload, sha256_bytes(&raw)))
}

fn source_identity(options: &BTreeMap<String, String>) -> Result<Value> {
    let remote = required_option(options, "--remote")?;
    let mode = options
        .get("--mode")
        .map(String::as_str)
        .unwrap_or("source");
    let repository_id = options
        .get("--repository-id")
        .map(String::as_str)
        .unwrap_or_default();
    let normalized = normalize_remote(remote).map_err(|error| {
        BootstrapError::new("source_repository_identity_unavailable", error.to_string())
    })?;
    if mode == "remote" {
        if !repository_id.is_empty() {
            return Err(BootstrapError::new(
                "source_repository_id_invalid",
                "generic remote identity does not accept a source override",
            ));
        }
        return Ok(json!({
            "schema": "agent-canon.remote-identity.v1",
            "normalized_remote": normalized,
        }));
    }
    if mode != "source" {
        return Err(BootstrapError::new(
            "source_repository_identity_unavailable",
            "identity mode is invalid",
        ));
    }
    let derived = stable_source_repository_id(remote).map_err(|error| {
        BootstrapError::new("source_repository_identity_unavailable", error.to_string())
    })?;
    if !repository_id.is_empty() {
        if repository_id.len() > 96
            || !repository_id.bytes().all(|byte| {
                byte.is_ascii_lowercase() || byte.is_ascii_digit() || b".-".contains(&byte)
            })
            || !repository_id.as_bytes()[0].is_ascii_lowercase()
                && !repository_id.as_bytes()[0].is_ascii_digit()
        {
            return Err(BootstrapError::new(
                "source_repository_id_invalid",
                "source repository identity override is invalid",
            ));
        }
        if repository_id != derived {
            return Err(BootstrapError::new(
                "source_repository_id_mismatch",
                "source repository identity override does not match its remote",
            ));
        }
    }
    let repository_id = if repository_id.is_empty() {
        &derived
    } else {
        repository_id
    };
    Ok(json!({
        "schema": "agent-canon.source-identity.v1",
        "normalized_remote": normalized,
        "repository_id": repository_id,
        "stable_branch": format!("logs/{repository_id}"),
    }))
}

fn hook_admission() -> Result<i32> {
    let mut input = Vec::new();
    std::io::stdin()
        .read_to_end(&mut input)
        .map_err(|error| BootstrapError::new("hook_input_invalid", error.to_string()))?;
    let Some(separator) = input.iter().position(|byte| *byte == 0) else {
        println!("untrusted");
        return Ok(0);
    };
    if input[separator + 1..].contains(&0) {
        println!("untrusted");
        return Ok(0);
    }
    let config_text = match std::str::from_utf8(&input[..separator]) {
        Ok(value) => value,
        Err(_) => {
            println!("untrusted");
            return Ok(0);
        }
    };
    let request: Value = match serde_json::from_slice(&input[separator + 1..]) {
        Ok(value) => value,
        Err(_) => {
            println!("untrusted");
            return Ok(0);
        }
    };
    let config: Value = match toml_edit::de::from_str(config_text) {
        Ok(value) => value,
        Err(_) => {
            println!("untrusted");
            return Ok(0);
        }
    };
    let project_root = request
        .get("cwd")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !project_root.starts_with('/') || project_root.chars().any(|c| c.is_control()) {
        println!("untrusted");
        return Ok(0);
    }
    let trusted = config
        .get("projects")
        .and_then(Value::as_object)
        .and_then(|projects| projects.get(project_root))
        .and_then(Value::as_object)
        .and_then(|project| project.get("trust_level"))
        .and_then(Value::as_str)
        == Some("trusted");
    if trusted {
        println!("trusted\t{project_root}");
        Ok(0)
    } else {
        println!("untrusted");
        Ok(0)
    }
}

fn run_codex_hook(event: &str) -> Result<i32> {
    if !["UserPromptSubmit", "PreToolUse", "PostToolUse"].contains(&event) {
        return Err(BootstrapError::new(
            "invalid_event",
            "unsupported Codex hook event",
        ));
    }
    let mut input = Vec::new();
    std::io::stdin()
        .read_to_end(&mut input)
        .map_err(|error| BootstrapError::new("hook_input_invalid", error.to_string()))?;
    let output = Command::new("agent-canon")
        .args(["codex-hook", event])
        .stdin(Stdio::piped())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .and_then(|mut child| {
            if let Some(mut stdin) = child.stdin.take() {
                stdin.write_all(&input)?;
            }
            child.wait()
        })
        .map_err(|error| BootstrapError::new("codex_hook_source_missing", error.to_string()))?;
    Ok(output.code().unwrap_or(1))
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    #[cfg(unix)]
    use std::os::unix::fs::MetadataExt as StdMetadataExt;
    use std::sync::{Mutex, MutexGuard};

    static ENV_LOCK: Mutex<()> = Mutex::new(());
    const TEST_ENV: &[&str] = &[
        "AGENT_CANON_PRIVATE_LOG_ROOT",
        "AGENT_CANON_HOST_CODEX_HOME_ROOT",
        "AGENT_CANON_HOST_SPOOL_ROOT",
        "AGENT_CANON_HOST_ARCHIVE_ROOT",
        "AGENT_CANON_HOST_CACHE_ROOT",
        "AGENT_CANON_EXCHANGE_ROOT",
        "AGENT_CANON_CONTROL_ROOT_DIGEST",
        "AGENT_CANON_HOST_INSTALL_ROOT",
        "AGENT_CANON_CODEX",
        "AGENT_CANON_CONTAINER_ID",
        "AGENT_CANON_IMAGE_ID",
        "AGENT_CANON_IMAGE_REF",
        "AGENT_CANON_TARGET_DIGEST",
        "AGENT_CANON_TARGET_HOST_ROOT",
        "AGENT_CANON_TARGET_CONTAINER_ROOT",
        "AGENT_CANON_PREVIOUS_IMAGE_ID",
        "AGENT_CANON_PREVIOUS_IMAGE_REF",
        "AGENT_CANON_RESTORE_IMAGE_ID",
        "AGENT_CANON_RESTORE_IMAGE_REF",
        "AGENT_CANON_CURRENT_IMAGE_ID",
        "AGENT_CANON_CURRENT_IMAGE_REF",
        "AGENT_CANON_ROLLBACK_MOUNTS_FILE",
        "AGENT_CANON_RESTORE_TARGETS_FILE",
    ];

    struct EnvGuard {
        _lock: MutexGuard<'static, ()>,
        saved: Vec<(&'static str, Option<std::ffi::OsString>)>,
    }

    impl EnvGuard {
        fn new() -> Self {
            let lock = ENV_LOCK
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            let saved = TEST_ENV
                .iter()
                .map(|key| (*key, env::var_os(key)))
                .collect();
            for key in TEST_ENV {
                env::remove_var(key);
            }
            Self { _lock: lock, saved }
        }
    }

    impl Drop for EnvGuard {
        fn drop(&mut self) {
            for (key, value) in &self.saved {
                if let Some(value) = value {
                    env::set_var(key, value);
                } else {
                    env::remove_var(key);
                }
            }
        }
    }

    #[test]
    fn test_namespace_maps_host_surface_path_environment() {
        let temporary = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("namespace fixture");
        let control = temporary.path().join("control");
        let runtime = control.join("runtime");
        let source = temporary.path().join("source");
        fs::create_dir_all(&runtime).expect("runtime root");
        fs::create_dir_all(&source).expect("source root");
        let namespace = TargetNamespace::default()
            .with_runtime_roots(&control, &runtime)
            .expect("runtime namespace")
            .with_source_root(&source)
            .expect("source namespace");
        let environment = BTreeMap::from([
            (
                "AGENT_CANON_HOST_INSTALL_ROOT".to_string(),
                TOOL_SOURCE_DESTINATION.to_string(),
            ),
            (
                "AGENT_CANON_HOST_SPOOL_ROOT".to_string(),
                "/var/lib/agent-canon/spool".to_string(),
            ),
            (
                "AGENT_CANON_HOST_ARCHIVE_ROOT".to_string(),
                "/var/lib/agent-canon/archive".to_string(),
            ),
            (
                "AGENT_CANON_HOST_CACHE_ROOT".to_string(),
                "/var/lib/agent-canon/cache".to_string(),
            ),
            (
                "AGENT_CANON_HOST_CODEX_HOME_ROOT".to_string(),
                "/var/lib/agent-canon/codex-home".to_string(),
            ),
        ]);
        let mapped = namespace.map_process_environment(&environment);
        assert_eq!(mapped["AGENT_CANON_HOST_INSTALL_ROOT"], source);
        assert_eq!(mapped["AGENT_CANON_HOST_SPOOL_ROOT"], control.join("spool"));
        assert_eq!(
            mapped["AGENT_CANON_HOST_ARCHIVE_ROOT"],
            control.join("archive")
        );
        assert_eq!(mapped["AGENT_CANON_HOST_CACHE_ROOT"], control.join("cache"));
        assert_eq!(
            mapped["AGENT_CANON_HOST_CODEX_HOME_ROOT"],
            control.join("codex-home")
        );
    }

    struct Fixture {
        _temporary: tempfile::TempDir,
        _environment: EnvGuard,
        runtime: BootstrapRuntime,
    }

    impl Fixture {
        fn new() -> Self {
            Self::new_with_target_mounts([])
        }

        fn new_with_target_mounts(mounts: impl IntoIterator<Item = (PathBuf, PathBuf)>) -> Self {
            let environment = EnvGuard::new();
            let temporary = tempfile::tempdir_in(
                std::env::temp_dir()
                    .canonicalize()
                    .expect("canonical temporary parent"),
            )
            .expect("controller fixture root");
            let control = temporary.path().join("control");
            let runtime_root = control.join("runtime");
            let private_log = temporary.path().join("private-log");
            let codex_home = temporary.path().join("codex-home");
            fs::create_dir_all(&control).expect("control root");
            fs::create_dir_all(&private_log).expect("private log root");
            env::set_var("AGENT_CANON_PRIVATE_LOG_ROOT", &private_log);
            env::set_var("AGENT_CANON_HOST_CODEX_HOME_ROOT", &codex_home);
            let repository = Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../../../")
                .canonicalize()
                .expect("repository root");
            let args = CliArgs {
                repository_root: repository.clone(),
                control_parent_root: control,
                runtime_root: Some(runtime_root),
                manifest: Some(repository.join("bootstrap/host/manifest.toml")),
                operation: "status".to_string(),
                options: BTreeMap::new(),
                flags: BTreeSet::new(),
                remainder: Vec::new(),
            };
            let namespace =
                TargetNamespace::from_readonly_mounts(mounts).expect("target namespace");
            let runtime = BootstrapRuntime::new(&args, namespace).expect("controller initializes");
            Self {
                _temporary: temporary,
                _environment: environment,
                runtime,
            }
        }

        fn install(&self) -> Value {
            self.runtime
                .transition("install")
                .expect("install state transition")
        }
    }

    #[cfg(unix)]
    #[test]
    fn exchange_directory_keeps_the_requested_sticky_permissions() {
        let temporary = tempfile::tempdir().unwrap();
        let exchange = temporary.path().canonicalize().unwrap().join("exchange");
        RuntimeFs::new()
            .unwrap()
            .ensure_directory(&exchange, 0o1733)
            .unwrap();
        assert_eq!(
            fs::metadata(exchange).unwrap().permissions().mode() & 0o7777,
            0o1733
        );
    }

    #[test]
    fn install_update_and_status_keep_one_owned_state_record() {
        let fixture = Fixture::new();
        let installed = fixture.install();
        assert_eq!(installed["code"], "installed");
        env::set_var("AGENT_CANON_IMAGE_ID", format!("sha256:{}", "b".repeat(64)));
        env::set_var(
            "AGENT_CANON_PREVIOUS_IMAGE_ID",
            format!("sha256:{}", "a".repeat(64)),
        );
        env::set_var(
            "AGENT_CANON_PREVIOUS_IMAGE_REF",
            "agent-canon-tools:previous",
        );
        let updated = fixture
            .runtime
            .transition("update")
            .expect("update transition");
        assert_eq!(updated["code"], "updated");
        let state = fixture.runtime.read_state().expect("state readback");
        assert_eq!(state["state"], "ready");
        assert_eq!(
            state["resources"]["image"]["id"],
            format!("sha256:{}", "b".repeat(64))
        );
        let status = fixture.runtime.status().expect("status readback");
        assert_eq!(status["operation"], "status");
        env::set_var(
            "AGENT_CANON_RESTORE_IMAGE_ID",
            format!("sha256:{}", "a".repeat(64)),
        );
        env::set_var(
            "AGENT_CANON_CURRENT_IMAGE_ID",
            format!("sha256:{}", "b".repeat(64)),
        );
        env::set_var(
            "AGENT_CANON_RESTORE_IMAGE_REF",
            "agent-canon-tools:previous",
        );
        let rolled_back = fixture.runtime.rollback().expect("rollback transition");
        assert_eq!(rolled_back["code"], "previous_generation_restored");
        let restored = fixture
            .runtime
            .read_state()
            .expect("rollback state readback");
        assert_eq!(
            restored["resources"]["image"]["id"],
            format!("sha256:{}", "a".repeat(64))
        );
        assert_eq!(restored["state"], "ready");
        assert!(fixture.runtime.paths.owner.is_file());
    }

    #[test]
    fn target_removal_keeps_the_previous_mount_generation_reversible() {
        let targets_root = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("target namespace fixture");
        let first = targets_root.path().join("first-target");
        let second = targets_root.path().join("second-target");
        fs::create_dir_all(&first).expect("first target root");
        fs::create_dir_all(&second).expect("second target root");
        let first_digest = sha256_text(&first.canonicalize().unwrap().to_string_lossy());
        let second_digest = sha256_text(&second.canonicalize().unwrap().to_string_lossy());
        let first_logical = PathBuf::from("/targets").join(&first_digest);
        let second_logical = PathBuf::from("/targets").join(&second_digest);
        let first_options = BTreeMap::from([
            (
                "--root".to_string(),
                first_logical.to_string_lossy().to_string(),
            ),
            ("--mode".to_string(), "read-only".to_string()),
        ]);
        let fixture = Fixture::new_with_target_mounts([
            (first_logical, first.clone()),
            (second_logical, second.clone()),
        ]);
        fixture.install();
        env::set_var("AGENT_CANON_IMAGE_ID", format!("sha256:{}", "a".repeat(64)));
        let mut targets = Map::new();
        targets.insert(first_digest.clone(), json!({"digest":first_digest,"host_root":first.to_string_lossy(),"root":format!("/targets/{first_digest}"),"mode":"read-only"}));
        targets.insert(second_digest.clone(), json!({"digest":second_digest,"host_root":second.to_string_lossy(),"root":format!("/targets/{second_digest}"),"mode":"read-only"}));
        let mut state = fixture.runtime.read_state().expect("state");
        state["state"] = json!("ready");
        state["resources"]["image"]["id"] = json!(format!("sha256:{}", "a".repeat(64)));
        state["resources"]["image"]["tag"] = json!("agent-canon-tools:fixture");
        state["current_generation"] = json!("generation-2");
        state["generation_counter"] = json!(2);
        state["targets"] = Value::Object(targets.clone());
        state["generations"]["generation-2"] = json!({
            "image_id":state["resources"]["image"]["id"],
            "image_ref":state["resources"]["image"]["tag"],
            "targets":targets,
            "state":"current",
        });
        fixture
            .runtime
            .write_state(&mut state)
            .expect("registered mount state");
        env::set_var("AGENT_CANON_TARGET_DIGEST", &first_digest);
        let removed = fixture
            .runtime
            .target_remove(&first_options)
            .expect("target remove");
        assert_eq!(removed["code"], "target_removed");
        let state = fixture.runtime.read_state().expect("updated state");
        assert!(!state["targets"]
            .as_object()
            .unwrap()
            .contains_key(&first_digest));
        let rollback = state["rollback_generation"].as_str().unwrap();
        assert!(state["generations"][rollback]["targets"]
            .get(&first_digest)
            .is_some());
        assert!(fixture
            .runtime
            .paths
            .container_runtime
            .join("rollback-plan.tsv")
            .is_file());
        assert!(second.exists());
    }

    #[test]
    fn runtime_paths_reject_symlink_state_without_following_it() {
        let fixture = Fixture::new();
        fixture.install();
        let state_path = &fixture.runtime.paths.state;
        let saved = fixture._temporary.path().join("saved-state.json");
        fs::rename(state_path, &saved).expect("move state aside");
        #[cfg(unix)]
        std::os::unix::fs::symlink(&saved, state_path).expect("replace state with link");
        let error = fixture
            .runtime
            .status()
            .expect_err("state symlink is refused");
        assert_eq!(error.code, "symlink_path_rejected");
    }

    #[test]
    fn process_lease_blocks_manual_release_until_worker_finishes() {
        let fixture = Fixture::new();
        fixture.install();
        fixture
            .runtime
            .locked(|| {
                let mut state = fixture.runtime.read_state()?;
                let (task, worker_lease) =
                    fixture
                        .runtime
                        .admit_task_locked(&mut state, "worker-task", None, true)?;
                assert_eq!(task["state"], "active");
                assert!(worker_lease.is_some());
                assert!(fixture
                    .runtime
                    .open_task_process_lease("worker-task", false)?
                    .is_none());
                drop(worker_lease);
                let completed_lease = fixture
                    .runtime
                    .open_task_process_lease("worker-task", false)?;
                assert!(completed_lease.is_some());
                drop(completed_lease);
                fixture
                    .runtime
                    .release_task_locked(&mut state, "worker-task", "completed")?;
                Ok(())
            })
            .expect("lease state transition");
    }

    #[test]
    fn structured_exec_maps_registered_mounts_and_rejects_unallowlisted_environment() {
        let fixture = Fixture::new();
        fixture.install();
        let host_target = fixture._temporary.path().join("host-target");
        fs::create_dir_all(&host_target).expect("host target fixture");
        let digest = "registered-target";
        let mut state = fixture.runtime.read_state().expect("state");
        state["targets"][digest] = json!({"digest":digest,"host_root":host_target,"root":format!("/targets/{digest}"),"mode":"read-only"});
        fixture
            .runtime
            .write_state(&mut state)
            .expect("registered target");
        env::set_var("AGENT_CANON_TARGET_DIGEST", digest);
        let source = fixture.runtime.paths.repository_root.clone();
        let output = fixture.runtime.paths.runtime_root.join("eval/output");
        let private_log = env::var("AGENT_CANON_PRIVATE_LOG_ROOT").unwrap();
        let request = json!({
            "schema":"agent-canon.tool-exec-request.v1","tool_id":"fixture-tool",
            "argv":["agent-canon-tool","tool","run","fixture-tool"],"child_args":["--help"],
            "source_root":source,"cwd":host_target,"cwd_policy":"target-root","target_root":host_target,
            "environment":{
                "AGENT_CANON_SOURCE_ROOT":source,"AGENT_CANON_ROOT":source,
                "AGENT_CANON_RUNTIME_ROOT":fixture.runtime.paths.runtime_root,
                "AGENT_CANON_CONTROL_PARENT_ROOT":fixture.runtime.paths.control_parent_root,
                "AGENT_CANON_TARGET_ROOT":host_target,"AGENT_CANON_TASK_ROOT":host_target,
                "AGENT_CANON_OUTPUT_ROOT":output,"AGENT_CANON_HOOK_ARCHIVE_DIR":private_log,
                "AGENT_CANON_LOG_ROOT":private_log,
            },
            "stdin":"inherited","stdout":"inherited","stderr":"inherited","exit":"propagate",
            "signal":"propagate","side_effect":"external-artifact","output_root":output,"written_paths":[]
        });
        let mut options = BTreeMap::new();
        options.insert("--target-digest".to_string(), digest.to_string());
        options.insert(
            "--request-json".to_string(),
            serde_json::to_string(&request).unwrap(),
        );
        let args = CliArgs {
            repository_root: source.clone(),
            control_parent_root: fixture.runtime.paths.control_parent_root.clone(),
            runtime_root: Some(fixture.runtime.paths.runtime_root.clone()),
            manifest: None,
            operation: "exec".to_string(),
            options,
            flags: BTreeSet::new(),
            remainder: Vec::new(),
        };
        let (root, argv, mapped) = fixture
            .runtime
            .execution_request(&args)
            .expect("valid request mapping");
        assert_eq!(root, PathBuf::from(format!("/targets/{digest}")));
        assert_eq!(argv[0], "agent-canon-tool");
        assert_eq!(mapped["AGENT_CANON_SOURCE_ROOT"], TOOL_SOURCE_DESTINATION);
        assert_eq!(
            mapped["AGENT_CANON_TARGET_ROOT"],
            format!("/targets/{digest}")
        );
        assert_eq!(
            mapped["AGENT_CANON_OUTPUT_ROOT"],
            format!("{CONTAINER_RUNTIME_DESTINATION}/eval/output")
        );
        assert_eq!(
            mapped["AGENT_CANON_HOOK_ARCHIVE_DIR"],
            PRIVATE_LOG_DESTINATION
        );

        let mut invalid = request;
        invalid["environment"]["AWS_SECRET_ACCESS_KEY"] = json!("fixture-secret");
        let mut options = BTreeMap::new();
        options.insert("--target-digest".to_string(), digest.to_string());
        options.insert(
            "--request-json".to_string(),
            serde_json::to_string(&invalid).unwrap(),
        );
        let args = CliArgs { options, ..args };
        let error = fixture
            .runtime
            .execution_request(&args)
            .expect_err("unallowlisted credential is refused");
        assert_eq!(error.code, "invalid_exec_request");
    }

    #[cfg(unix)]
    #[test]
    fn worker_timeout_and_output_redaction_keep_failure_context_bounded() {
        let _environment = EnvGuard::new();
        let temporary = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("worker fixture");
        let fs = RuntimeFs::new().expect("rooted filesystem");
        let lease_path = temporary.path().join("lease.lock");
        let lease = fs.create_file(&lease_path, 0o600).expect("lease file");
        let output = run_tool_process(
            &[
                "sh".into(),
                "-c".into(),
                "printf 'password=canary\\n'".into(),
            ],
            Path::new("/"),
            &BTreeMap::new(),
            Duration::from_secs(1),
            &lease,
        )
        .expect("worker output");
        assert!(output.status.success());
        assert_eq!(
            redact_output(&String::from_utf8_lossy(&output.stdout)),
            "password=<redacted>\n"
        );
        let timeout = run_tool_process(
            &["sh".into(), "-c".into(), "exec sleep 5".into()],
            Path::new("/"),
            &BTreeMap::new(),
            Duration::from_millis(20),
            &lease,
        )
        .expect_err("worker timeout");
        assert_eq!(timeout.code, "docker_command_timeout");
        let redacted = redact_output("password=canary Bearer secret-value");
        assert_eq!(redacted, "password=<redacted> Bearer <redacted>");
        assert!(bounded_preview(&"あ".repeat(600), 512).chars().count() <= 512);
    }

    #[cfg(unix)]
    #[test]
    fn codex_prepare_uses_one_directory_link_and_preserves_link_identity() {
        let fixture = Fixture::new();
        fixture.install();
        let first = fixture.runtime.codex_prepare().expect("prepare Codex home");
        assert_eq!(first["code"], "codex_home_ready");
        let link = fixture.runtime.paths.codex_home.join("skills/agent-canon");
        let expected = fixture
            .runtime
            .paths
            .repository_root
            .join(".codex/personal/skills");
        assert_eq!(fs::read_link(&link).expect("skills link"), expected);
        let before = fs::symlink_metadata(&link).expect("link identity");
        fixture
            .runtime
            .codex_prepare()
            .expect("repeat Codex preparation");
        let after = fs::symlink_metadata(&link).expect("link readback");
        assert_eq!(before.ino(), after.ino());
    }

    #[cfg(unix)]
    #[test]
    fn codex_prepare_removes_only_stale_manifest_owned_links() {
        let fixture = Fixture::new();
        fixture.install();
        let codex_home = &fixture.runtime.paths.codex_home;
        let stale_source = fixture
            .runtime
            .paths
            .repository_root
            .join(".codex/personal/skills/integration/SKILL.md");
        let stale_target = codex_home.join("skills/integration/SKILL.md");
        fs::create_dir_all(stale_target.parent().unwrap()).expect("stale link parent");
        std::os::unix::fs::symlink(&stale_source, &stale_target).expect("old managed file link");
        let foreign = codex_home.join("skills/foreign/SKILL.md");
        fs::create_dir_all(foreign.parent().unwrap()).expect("foreign link parent");
        fs::write(&foreign, "user-owned skill\n").expect("foreign file");
        let manifest_path = codex_home.join("manifest.json");
        let mut manifest: Value = serde_json::from_slice(
            &fixture
                .runtime
                .fs
                .read(&manifest_path, "Codex manifest")
                .unwrap()
                .unwrap(),
        )
        .unwrap();
        let links = manifest["links"].as_array_mut().unwrap();
        links.push(
            json!({"surface":"skills","source":stale_source,"target":stale_target,"managed":true}),
        );
        fixture
            .runtime
            .atomic_json(&manifest_path, &manifest, 0o600)
            .expect("prior manifest");

        fixture
            .runtime
            .codex_prepare()
            .expect("reconcile Codex links");
        assert!(!stale_target.is_symlink());
        assert_eq!(fs::read_to_string(&foreign).unwrap(), "user-owned skill\n");
        assert_eq!(
            fs::read_link(codex_home.join("skills/agent-canon")).unwrap(),
            fixture
                .runtime
                .paths
                .repository_root
                .join(".codex/personal/skills")
        );
    }

    #[test]
    fn eval_sync_requires_matching_success_and_writes_only_a_body_free_request() {
        let fixture = Fixture::new();
        fixture.install();
        let state = fixture.runtime.read_state().expect("state");
        let spool = fixture.runtime.paths.spool.join("eval-sync-test");
        fixture
            .runtime
            .fs
            .ensure_directory(&spool, 0o700)
            .expect("spool");
        fixture.runtime.atomic_json(&spool.join("collection.json"), &json!({
            "run_id":"eval-sync-test","status":"collected","source_tree_unchanged":true,
            "manifest_digest":state["manifest_digest"],"source_repository":"/targets/fixture",
        }), 0o600).expect("collection fixture");
        env::set_var("AGENT_CANON_TARGET_DIGEST", "fixture");
        let options = BTreeMap::from([("--run-id".to_string(), "eval-sync-test".to_string())]);
        let result = fixture
            .runtime
            .eval_sync_prepare(&options)
            .expect("sync request");
        assert_eq!(result["code"], "host_archive_requested");
        let request = fs::read_to_string(spool.join("sync-request.tsv")).expect("request content");
        assert!(request.contains("schema\tagent-canon.eval-sync-request.v1\n"));
        assert!(request.contains("target-digest\tfixture\n"));
        assert!(!request.contains("producer_matrix"));
    }

    #[test]
    fn source_snapshot_and_producer_matrix_keep_independent_eval_evidence() {
        let _environment = EnvGuard::new();
        let temporary = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("eval fixture");
        Command::new("git")
            .args(["init", "--quiet", temporary.path().to_str().unwrap()])
            .status()
            .expect("git init");
        fs::write(temporary.path().join("source.txt"), "before\n").expect("source file");
        Command::new("git")
            .args([
                "-C",
                temporary.path().to_str().unwrap(),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "add",
                "source.txt",
            ])
            .status()
            .expect("git add");
        Command::new("git")
            .args([
                "-C",
                temporary.path().to_str().unwrap(),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "fixture source",
            ])
            .status()
            .expect("git commit");
        let before = source_snapshot(temporary.path()).expect("source snapshot");
        fs::write(temporary.path().join("source.txt"), "after\n").expect("source update");
        let after = source_snapshot(temporary.path()).expect("second source snapshot");
        assert_ne!(before["tree_digest"], after["tree_digest"]);
        let (matrix, metrics) = eval_producer_matrix("ACCUMULATED_AGENT_EVAL_PRODUCER=one:pass:stdout=one.log:stderr=\nACCUMULATED_AGENT_EVAL_PRODUCERS=1\nACCUMULATED_AGENT_EVAL=pass\n");
        assert_eq!(matrix.len(), 1);
        assert_eq!(matrix[0]["name"], "one");
        assert_eq!(metrics["overall"], "pass");
    }

    #[test]
    fn eval_exchange_copy_rejects_symlinks_and_preserves_regular_files() {
        let _environment = EnvGuard::new();
        let temporary = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("exchange fixture");
        let filesystem = RuntimeFs::new().expect("rooted filesystem");
        let source = temporary.path().join("source");
        let destination = temporary.path().join("destination");
        fs::create_dir_all(&source).expect("exchange source");
        fs::write(source.join("producer.txt"), "producer evidence\n").expect("producer file");
        assert_eq!(
            copy_tree(&filesystem, &source, &destination).expect("copy safe tree"),
            1
        );
        assert_eq!(
            fs::read_to_string(destination.join("producer.txt")).unwrap(),
            "producer evidence\n"
        );
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(source.join("producer.txt"), source.join("linked.txt"))
                .expect("exchange symlink");
            let error = copy_tree(&filesystem, &source, &temporary.path().join("rejected"))
                .expect_err("symlink export refused");
            assert_eq!(error.code, "eval_exchange_symlink");
        }
    }

    #[test]
    fn eval_sync_refuses_failed_source_snapshot_and_other_generation() {
        let fixture = Fixture::new();
        fixture.install();
        let state = fixture.runtime.read_state().expect("state");
        let spool = fixture.runtime.paths.spool.join("failed-eval");
        fixture
            .runtime
            .fs
            .ensure_directory(&spool, 0o700)
            .expect("spool");
        fixture.runtime.atomic_json(&spool.join("collection.json"), &json!({
            "run_id":"failed-eval","status":"failed","source_tree_unchanged":false,
            "manifest_digest":state["manifest_digest"],"source_repository":"/targets/fixture",
        }), 0o600).expect("failed collection fixture");
        let options = BTreeMap::from([("--run-id".to_string(), "failed-eval".to_string())]);
        let error = fixture
            .runtime
            .eval_sync_prepare(&options)
            .expect_err("failed eval is not publishable");
        assert_eq!(error.code, "eval_collection_failed");
        assert!(!spool.join("sync-request.tsv").exists());
    }

    #[test]
    fn gc_preserves_current_rollback_and_pending_spool_while_cleaning_unpinned_state() {
        let mut fixture = Fixture::new();
        fixture.install();
        let mut state = fixture.runtime.read_state().expect("state");
        state["current_generation"] = json!("current");
        state["rollback_generation"] = json!("rollback");
        state["generations"] = json!({"current":{"state":"current"},"rollback":{"state":"rollback"},"stale":{"state":"old"}});
        state["tasks"] = json!({"finished":{"state":"completed","pinned":false,"finished_at":"2026-01-01T00:00:00Z"}});
        state["active_task_count"] = json!(0);
        fixture
            .runtime
            .write_state(&mut state)
            .expect("state fixture");
        fixture.runtime.manifest["container"]["runtime_quota_bytes"] = json!(1);
        fixture.runtime.manifest["container"]["cache_quota_bytes"] = json!(1);
        fixture.runtime.manifest["container"]["archive_lease_quota_bytes"] = json!(1);
        fixture
            .runtime
            .fs
            .ensure_directory(&fixture.runtime.paths.spool.join("pending"), 0o700)
            .expect("pending spool");
        fs::write(fixture.runtime.paths.cache.join("cache-entry"), b"cache")
            .expect("cache fixture");
        fs::write(
            fixture.runtime.paths.archive.join("archive-entry"),
            b"archive",
        )
        .expect("archive fixture");
        fs::create_dir_all(fixture.runtime.paths.tasks.join("finished/logs"))
            .expect("task log directory");
        fs::write(
            fixture.runtime.paths.tasks.join("finished/logs/stdout.log"),
            b"old",
        )
        .expect("task fixture");
        let result = fixture.runtime.gc(false).expect("GC");
        assert_eq!(result["details"]["archive_cleanup_blocked_by_spool"], true);
        let state = fixture.runtime.read_state().expect("GC state");
        assert!(state["generations"].get("current").is_some());
        assert!(state["generations"].get("rollback").is_some());
        assert!(state["generations"].get("stale").is_none());
        assert!(state["tasks"].get("finished").is_none());
        assert!(fixture
            .runtime
            .paths
            .archive
            .join("archive-entry")
            .is_file());
        assert!(!fixture.runtime.paths.cache.join("cache-entry").exists());
    }
}
