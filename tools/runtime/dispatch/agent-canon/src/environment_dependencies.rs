//! Full environment-dependency plan identity and read-only executable receipts.
// @dependency-start
// contract implementation
// responsibility Validates complete environment dependency plans and resolves receipt-bound executable capabilities.
// upstream implementation artifacts/artifact_identity.rs owns canonical ASCII JSON bytes
// upstream implementation ../artifacts/artifact_identity.rs provides SHA-256-compatible JSON bytes
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md requires native ownership of AgentCanon tools
// upstream input ../../../../../bootstrap/container/image/dependencies.toml declares the shared dependency plan
// downstream implementation ../main.rs dispatches the environment-dependencies command
// downstream test ../../tests/environment_dependencies_native.rs validates plan and executable receipt behavior
// @dependency-end

use crate::artifacts::artifact_identity::canonical_json_ascii_bytes;
use crate::authority::{
    AttestationRequest, AttestedParent, NonEmptyTrimmedString, Nonce128, ParentRootAttestor,
};
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::env;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const SCHEMA: &str = "agent-canon.tool-dependencies";
const SCHEMA_VERSION: u64 = 2;
const RECEIPT_SCHEMA: &str = "agent-canon.tool-dependency-receipt";
const STRUCTURAL_BINDING_OUTPUT_PREFIX: &str = "agent-canon.executable-binding.structural.v1";
const ACTIVE_SOURCE_IDENTITY: &str = "active-source";
const CANONICAL_SNAPSHOT_IDENTITY: &str = "canonical-snapshot";
const IMAGE_DEPENDENCIES_ROOT: &str = "/usr/local/share/agent-canon/image-dependencies";
const IMAGE_PLAN_SCHEMA: &str = "agent-canon.image-dependencies";
const IMAGE_PLAN_SCHEMA_VERSION: u64 = 1;
const IMAGE_DIRECTORY_MODE: u32 = 0o555;
const IMAGE_FILE_MODE: u32 = 0o444;
const NPM_GLOBAL_PREFIX: &str = "/usr/local";
const NPM_ENV_EXECUTABLE: &str = "/usr/bin/env";
const RUSTUP_INIT_VERSION: &str = "1.28.2";
const RUSTUP_INIT_SHA256: &str = "20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c";
const CANONICAL_RUST_SOURCE_FILES: &[&str] = &[
    "Cargo.lock",
    "Cargo.toml",
    "src/dependency_manifest.rs",
    "src/docs.rs",
    "src/graph.rs",
    "src/jit_ir_to_lean.rs",
    "src/main.rs",
    "src/migration_audit.rs",
    "src/python_algorithm_contract.rs",
    "src/python_module_groups.rs",
    "src/python_structure_hash.rs",
    "src/python_structure_hash_impact.rs",
    "src/python_structure_hash_report.rs",
    "src/python_structure_hash_scope_plan.rs",
    "src/runtime_boundary.rs",
    "src/rust_migration_plan.rs",
    "src/semantic_index/args.rs",
    "src/semantic_index/cli.rs",
    "src/semantic_index/embedding.rs",
    "src/semantic_index/eval.rs",
    "src/semantic_index/mod.rs",
    "src/semantic_index/model.rs",
    "src/semantic_index/pipeline.rs",
    "src/semantic_index/query.rs",
    "src/semantic_index/relations.rs",
    "src/semantic_index/report.rs",
    "src/semantic_index/source.rs",
    "src/semantic_index/storage.rs",
    "src/semantic_index/tests.rs",
    "src/structured_analysis.rs",
    "src/test_design.rs",
    "src/private_feedback.rs",
    "tests/python_algorithm_contract_cli.rs",
];
const IMAGE_INSTALL_METHODS: [Method; 7] = [
    Method::AptPackage,
    Method::AptRepository,
    Method::NpmGlobal,
    Method::Pipx,
    Method::ReleaseAsset,
    Method::RustToolchain,
    Method::CargoSourceBuild,
];
const NPM_PREFIX: &str = "/usr/local";
const NPM_SYSTEM_PATH: &str = "/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin";
const NPM_TRUSTED_DIRS: [&str; 6] = [
    "/usr/local/bin",
    "/usr/local/sbin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
];
const BASE_CAPABILITIES: [&str; 16] = [
    "build-essential",
    "ca-certificates",
    "curl",
    "git",
    "gnupg",
    "ninja-build",
    "node",
    "npm",
    "pipx",
    "python3",
    "python3-packaging",
    "tar",
    "tomli",
    "tomllib",
    "rustup-init",
    "xz-utils",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DependencyError {
    detail: String,
}

impl DependencyError {
    fn new(detail: impl Into<String>) -> Self {
        Self {
            detail: detail.into(),
        }
    }
}

impl fmt::Display for DependencyError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.detail)
    }
}

impl std::error::Error for DependencyError {}

type Result<T> = std::result::Result<T, DependencyError>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ManifestRole {
    Canonical,
    ParentOverlay,
}

impl ManifestRole {
    fn as_str(self) -> &'static str {
        match self {
            Self::Canonical => "canonical",
            Self::ParentOverlay => "parent-overlay",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Method {
    AptPackage,
    AptRepository,
    NpmGlobal,
    Pipx,
    ReleaseAsset,
    RustToolchain,
    LeanToolchain,
    CargoSourceBuild,
    BrowserInstall,
}

impl Method {
    fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "apt-package" => Self::AptPackage,
            "apt-repository" => Self::AptRepository,
            "npm-global" => Self::NpmGlobal,
            "pipx" => Self::Pipx,
            "release-asset" => Self::ReleaseAsset,
            "rust-toolchain" => Self::RustToolchain,
            "lean-toolchain" => Self::LeanToolchain,
            "cargo-source-build" => Self::CargoSourceBuild,
            "browser-install" => Self::BrowserInstall,
            _ => return None,
        })
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::AptPackage => "apt-package",
            Self::AptRepository => "apt-repository",
            Self::NpmGlobal => "npm-global",
            Self::Pipx => "pipx",
            Self::ReleaseAsset => "release-asset",
            Self::RustToolchain => "rust-toolchain",
            Self::LeanToolchain => "lean-toolchain",
            Self::CargoSourceBuild => "cargo-source-build",
            Self::BrowserInstall => "browser-install",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum VerificationKind {
    AptPackage,
    AptRepository,
    NpmPackage,
    PipxPackage,
    AbsoluteExecutable,
    RustToolchain,
    LeanToolchain,
    CargoBinary,
    BrowserExecutable,
}

impl VerificationKind {
    fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "apt-package" => Self::AptPackage,
            "apt-repository" => Self::AptRepository,
            "npm-package" => Self::NpmPackage,
            "pipx-package" => Self::PipxPackage,
            "absolute-executable" => Self::AbsoluteExecutable,
            "rust-toolchain" => Self::RustToolchain,
            "lean-toolchain" => Self::LeanToolchain,
            "cargo-binary" => Self::CargoBinary,
            "browser-executable" => Self::BrowserExecutable,
            _ => return None,
        })
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::AptPackage => "apt-package",
            Self::AptRepository => "apt-repository",
            Self::NpmPackage => "npm-package",
            Self::PipxPackage => "pipx-package",
            Self::AbsoluteExecutable => "absolute-executable",
            Self::RustToolchain => "rust-toolchain",
            Self::LeanToolchain => "lean-toolchain",
            Self::CargoBinary => "cargo-binary",
            Self::BrowserExecutable => "browser-executable",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct VerificationSpec {
    kind: VerificationKind,
    executable: Option<String>,
    path: Option<String>,
    args: Vec<String>,
    output_contains: Option<String>,
    executable_globs: Vec<String>,
}

impl VerificationSpec {
    fn payload(&self) -> Value {
        json!({
            "kind": self.kind.as_str(),
            "executable": self.executable,
            "path": self.path,
            "args": self.args,
            "output_contains": self.output_contains,
            "executable_globs": self.executable_globs,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct DependencyRecord {
    id: String,
    package: String,
    method: Method,
    version: Option<String>,
    source: String,
    verification: VerificationSpec,
    deps: Vec<String>,
    provides: Vec<String>,
    failure_policy: String,
    platform: Option<String>,
    platforms: Vec<String>,
    key_fingerprint: Option<String>,
    key_url: Option<String>,
    repository_suite: Option<String>,
    repository_components: Vec<String>,
    repository_packages_sha256: Option<String>,
    repository_package_url: Option<String>,
    repository_package_sha256: Option<String>,
    repository_packages_sha256s: Vec<(String, String)>,
    repository_package_urls: Vec<(String, String)>,
    repository_package_sha256s: Vec<(String, String)>,
    checksum: Option<String>,
    checksums: Vec<(String, String)>,
    asset: Option<String>,
    assets: Vec<(String, String)>,
    archive_format: Option<String>,
    extract: Option<String>,
    destination: Option<String>,
    executable_owner_packages: Vec<String>,
    repo: Option<String>,
    commit: Option<String>,
    source_identity: Option<String>,
    source_tree_sha256: Option<String>,
    cargo_lock_sha256: Option<String>,
    locked: Option<bool>,
    browser: Option<String>,
    browser_cache_path: Option<String>,
    components: Vec<String>,
}

impl DependencyRecord {
    fn payload(&self) -> Value {
        json!({
            "id": self.id,
            "package": self.package,
            "method": self.method.as_str(),
            "version": self.version,
            "source": self.source,
            "verification": self.verification.payload(),
            "deps": self.deps,
            "provides": self.provides,
            "failure_policy": self.failure_policy,
            "platform": self.platform,
            "platforms": self.platforms,
            "key_fingerprint": self.key_fingerprint,
            "key_url": self.key_url,
            "repository_suite": self.repository_suite,
            "repository_components": self.repository_components,
            "repository_packages_sha256": self.repository_packages_sha256,
            "repository_package_url": self.repository_package_url,
            "repository_package_sha256": self.repository_package_sha256,
            "repository_packages_sha256s": self.repository_packages_sha256s,
            "repository_package_urls": self.repository_package_urls,
            "repository_package_sha256s": self.repository_package_sha256s,
            "checksum": self.checksum,
            "checksums": self.checksums,
            "asset": self.asset,
            "assets": self.assets,
            "archive_format": self.archive_format,
            "extract": self.extract,
            "destination": self.destination,
            "executable_owner_packages": self.executable_owner_packages,
            "repo": self.repo,
            "commit": self.commit,
            "source_identity": self.source_identity,
            "source_tree_sha256": self.source_tree_sha256,
            "cargo_lock_sha256": self.cargo_lock_sha256,
            "locked": self.locked,
            "browser": self.browser,
            "browser_cache_path": self.browser_cache_path,
            "components": self.components,
        })
    }

    fn fingerprint(&self) -> Result<String> {
        Ok(sha256_hex(&canonical_bytes(&self.payload())?))
    }
}

#[derive(Debug, Clone)]
struct ManifestSource {
    path: PathBuf,
    role: ManifestRole,
}

#[derive(Debug, Clone)]
struct LoadedManifest {
    source: ManifestSource,
    records: Vec<DependencyRecord>,
}

#[derive(Debug, Clone)]
struct DependencyPlan {
    records: Vec<DependencyRecord>,
    order: Vec<String>,
    sources: Vec<PathBuf>,
    dependency_providers: Vec<(String, Vec<String>)>,
    fingerprint: String,
    source_roles: Vec<String>,
}

impl DependencyPlan {
    fn by_id(&self, record_id: &str) -> Option<&DependencyRecord> {
        self.records.iter().find(|record| record.id == record_id)
    }
}

/// A verified executable path and the plan/record identities that authorize it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedExecutable {
    pub record_id: String,
    pub manifest_version: String,
    pub executable: String,
    pub absolute_path: PathBuf,
    pub record_fingerprint: String,
    pub plan_fingerprint: String,
    pub verification_output: String,
}

fn canonical_bytes(value: &Value) -> Result<Vec<u8>> {
    canonical_json_ascii_bytes(value).map_err(|error| DependencyError::new(error.to_string()))
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn object<'a>(value: &'a Value, field: &str) -> Result<&'a Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| DependencyError::new(format!("{field} must be a table")))
}

fn reject_unknown_fields(object: &Map<String, Value>, allowed: &[&str], field: &str) -> Result<()> {
    let unknown = object
        .keys()
        .filter(|key| !allowed.contains(&key.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    if unknown.is_empty() {
        Ok(())
    } else {
        Err(DependencyError::new(format!(
            "{field} unknown fields: {}",
            unknown.join(", ")
        )))
    }
}

fn has_control(value: &str) -> bool {
    value
        .chars()
        .any(|ch| (ch as u32) <= 0x1f || ch == '\u{7f}')
}

fn normalized_string(value: &Value, field: &str) -> Result<String> {
    let raw = value
        .as_str()
        .ok_or_else(|| DependencyError::new(format!("{field} must be a non-empty string")))?;
    let normalized = raw.trim();
    if normalized.is_empty() {
        return Err(DependencyError::new(format!(
            "{field} must be a non-empty string"
        )));
    }
    if has_control(normalized) {
        return Err(DependencyError::new(format!(
            "{field} must not contain control characters"
        )));
    }
    if normalized.starts_with('-') {
        return Err(DependencyError::new(format!(
            "{field} must not be an option"
        )));
    }
    Ok(normalized.to_string())
}

fn optional_string(object: &Map<String, Value>, key: &str, field: &str) -> Result<Option<String>> {
    object
        .get(key)
        .filter(|value| !value.is_null())
        .map(|value| normalized_string(value, field))
        .transpose()
}

fn required_string(object: &Map<String, Value>, key: &str, field: &str) -> Result<String> {
    let value = object
        .get(key)
        .ok_or_else(|| DependencyError::new(format!("{field} is required")))?;
    normalized_string(value, field)
}

fn string_list_value(value: Option<&Value>, field: &str, allow_empty: bool) -> Result<Vec<String>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let list = value
        .as_array()
        .ok_or_else(|| DependencyError::new(format!("{field} must be a string array")))?;
    let mut result = Vec::with_capacity(list.len());
    let mut seen = BTreeSet::new();
    for item in list {
        let raw = item
            .as_str()
            .ok_or_else(|| DependencyError::new(format!("{field} must be a string array")))?;
        let normalized = raw.trim().to_string();
        if normalized.is_empty() {
            return Err(DependencyError::new(format!(
                "{field} cannot contain empty strings"
            )));
        }
        if !seen.insert(normalized.clone()) {
            return Err(DependencyError::new(format!(
                "{field} must not contain duplicates"
            )));
        }
        result.push(normalized);
    }
    if !allow_empty && result.is_empty() {
        return Err(DependencyError::new(format!("{field} must not be empty")));
    }
    Ok(result)
}

fn argv_args(object: &Map<String, Value>, field: &str) -> Result<Vec<String>> {
    let Some(value) = object.get("args") else {
        return Ok(Vec::new());
    };
    let list = value
        .as_array()
        .filter(|list| !list.is_empty())
        .ok_or_else(|| DependencyError::new(format!("{field} must be a non-empty argv array")))?;
    list.iter()
        .map(|item| {
            let argument = item.as_str().ok_or_else(|| {
                DependencyError::new(format!("{field} must contain non-empty argv-safe strings"))
            })?;
            if argument.is_empty() || argument.trim() != argument || has_control(argument) {
                return Err(DependencyError::new(format!(
                    "{field} must contain non-empty argv-safe strings"
                )));
            }
            Ok(argument.to_string())
        })
        .collect()
}

fn sorted_string_map(value: &Value, field: &str) -> Result<Vec<(String, String)>> {
    let map = object(value, field)?;
    if map.is_empty() {
        return Err(DependencyError::new(format!(
            "{field} must be a non-empty string map"
        )));
    }
    map.iter()
        .map(|(key, value)| {
            let key = normalized_string(&Value::String(key.clone()), &format!("{field} key"))?;
            let value = normalized_string(value, &format!("{field}[{key}]"))?;
            Ok((key, value))
        })
        .collect()
}

fn checksums(value: &Value, field: &str) -> Result<Vec<(String, String)>> {
    if let Some(checksum) = value.as_str() {
        if !is_hex(checksum, 64) {
            return Err(DependencyError::new(format!(
                "{field} must be a 64-character SHA256"
            )));
        }
        return Ok(vec![("default".to_string(), checksum.to_ascii_lowercase())]);
    }
    let map = object(value, field)?;
    if map.is_empty() {
        return Err(DependencyError::new(format!(
            "{field} must be a SHA256 string or architecture map"
        )));
    }
    let mut result = Vec::with_capacity(map.len());
    for (architecture, checksum) in map {
        let architecture = normalized_string(
            &Value::String(architecture.clone()),
            "checksum architecture",
        )?;
        let checksum = normalized_string(checksum, &format!("{field}[{architecture}]"))?;
        if !is_hex(&checksum, 64) {
            return Err(DependencyError::new(format!(
                "{field}[{architecture}] must be a 64-character SHA256"
            )));
        }
        result.push((architecture, checksum.to_ascii_lowercase()));
    }
    Ok(result)
}

fn is_hex(value: &str, expected_len: usize) -> bool {
    value.len() == expected_len && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn is_pep440_version(value: &str) -> bool {
    matches(
        r"^(?:v)?(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:(?:[-_.]?(?:alpha|a|beta|b|preview|pre|c|rc))[-_.]?[0-9]*)?(?:(?:-[0-9]+)|(?:[-_.]?(?:post|rev|r)[-_.]?[0-9]*))?(?:[-_.]?dev[-_.]?[0-9]*)?(?:\+[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)*)?$",
        &value.to_ascii_lowercase(),
    )
}

fn matches(pattern: &str, value: &str) -> bool {
    regex::Regex::new(pattern)
        .expect("static validation regex")
        .is_match(value)
}

fn validate_url(value: &str, field: &str, https_only: bool) -> Result<()> {
    let (scheme, rest) = value
        .split_once("://")
        .ok_or_else(|| DependencyError::new(format!("{field} must be an https or file URL")))?;
    let valid_scheme = if https_only {
        scheme == "https"
    } else {
        scheme == "https" || scheme == "file"
    };
    let host_and_path = rest.split(['?', '#']).next().unwrap_or_default();
    let authority = host_and_path.split('/').next().unwrap_or_default();
    if !valid_scheme
        || (scheme == "https" && authority.is_empty())
        || value.contains('?')
        || value.contains('#')
        || has_parent_segment(rest)
    {
        return Err(DependencyError::new(format!(
            "{field} must be an https or file URL"
        )));
    }
    Ok(())
}

fn has_parent_segment(value: &str) -> bool {
    value.split(['/', '\\']).any(|part| part == "..")
}

fn safe_absolute_path(value: &str, field: &str, prefix: &str) -> Result<()> {
    if !value.starts_with('/')
        || has_parent_segment(value)
        || posix_normalize(value) != value
        || !value.starts_with(&format!("{prefix}/"))
    {
        return Err(DependencyError::new(format!(
            "{field} must be an absolute path below {prefix}"
        )));
    }
    Ok(())
}

fn normalized_absolute_path(value: &str, field: &str) -> Result<()> {
    if !value.starts_with('/') || has_parent_segment(value) || posix_normalize(value) != value {
        return Err(DependencyError::new(format!(
            "{field} must be a normalized absolute executable path"
        )));
    }
    Ok(())
}

fn posix_normalize(value: &str) -> String {
    let mut components = Vec::new();
    for part in value.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                components.pop();
            }
            other => components.push(other),
        }
    }
    format!("/{}", components.join("/"))
}

fn safe_relative_path(value: &str) -> bool {
    !value.starts_with('/')
        && relative_normalize(value) == value
        && !has_parent_segment(value)
        && !value.split('/').any(|part| part.is_empty() || part == ".")
}

fn validate_asset_path(value: &str, field: &str) -> Result<()> {
    let safe = |part: &str| matches(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", part);
    if value.starts_with('/')
        || relative_normalize(value) != value
        || has_parent_segment(value)
        || value.split('/').any(|part| !safe(part))
    {
        return Err(DependencyError::new(format!(
            "{field} must be a safe relative asset path"
        )));
    }
    Ok(())
}

fn validate_safe_member(value: &str) -> Result<()> {
    if value != "none"
        && (value.contains('/')
            || value.contains('\\')
            || has_parent_segment(value)
            || !matches(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", value))
    {
        return Err(DependencyError::new(
            "extract must be one safe archive member name",
        ));
    }
    Ok(())
}

fn method_verification_kind(method: Method) -> VerificationKind {
    match method {
        Method::AptPackage => VerificationKind::AptPackage,
        Method::AptRepository => VerificationKind::AptRepository,
        Method::NpmGlobal => VerificationKind::NpmPackage,
        Method::Pipx => VerificationKind::PipxPackage,
        Method::ReleaseAsset => VerificationKind::AbsoluteExecutable,
        Method::RustToolchain => VerificationKind::RustToolchain,
        Method::LeanToolchain => VerificationKind::LeanToolchain,
        Method::CargoSourceBuild => VerificationKind::CargoBinary,
        Method::BrowserInstall => VerificationKind::BrowserExecutable,
    }
}

fn parse_verification(value: &Value, record_id: &str, method: Method) -> Result<VerificationSpec> {
    let object = object(value, &format!("{record_id}.verification"))?;
    if object.is_empty() {
        return Err(DependencyError::new(format!(
            "{record_id}.verification must be a non-empty table"
        )));
    }
    let kind = VerificationKind::parse(&required_string(
        object,
        "kind",
        &format!("{record_id}.verification.kind"),
    )?)
    .ok_or_else(|| DependencyError::new(format!("{record_id}.verification: unsupported kind")))?;
    let expected = method_verification_kind(method);
    if kind != expected {
        return Err(DependencyError::new(format!(
            "{record_id}.verification.kind {} is incompatible with method {}; expected {}",
            kind.as_str(),
            method.as_str(),
            expected.as_str()
        )));
    }
    let permitted: &[&str] = match kind {
        VerificationKind::AptPackage
        | VerificationKind::AptRepository
        | VerificationKind::NpmPackage
        | VerificationKind::PipxPackage
        | VerificationKind::RustToolchain => &["kind", "executable", "args", "output_contains"],
        VerificationKind::AbsoluteExecutable | VerificationKind::CargoBinary => {
            &["kind", "path", "args", "output_contains"]
        }
        VerificationKind::LeanToolchain => &["kind"],
        VerificationKind::BrowserExecutable => {
            &["kind", "args", "output_contains", "executable_globs"]
        }
    };
    reject_unknown_fields(
        object,
        permitted,
        &format!("{record_id}.verification unsupported fields:"),
    )?;
    let executable = optional_string(
        object,
        "executable",
        &format!("{record_id}.verification.executable"),
    )?;
    let path = optional_string(object, "path", &format!("{record_id}.verification.path"))?;
    let output_contains = optional_string(
        object,
        "output_contains",
        &format!("{record_id}.verification.output_contains"),
    )?;
    let args = argv_args(object, &format!("{record_id}.verification.args"))?;
    let executable_globs = string_list_value(
        object.get("executable_globs"),
        &format!("{record_id}.verification.executable_globs"),
        false,
    )?;
    let require_executable = |label: &str| -> Result<()> {
        if executable.as_ref().is_none_or(|value| {
            Path::new(value).file_name().and_then(|name| name.to_str()) != Some(value.as_str())
                || ["bash", "dash", "fish", "ksh", "sh", "tcsh", "zsh", "eval"]
                    .contains(&value.as_str())
        }) || args.is_empty()
            || output_contains.is_none()
        {
            return Err(DependencyError::new(format!(
                "{record_id}.verification requires executable, args, and output_contains ({label})"
            )));
        }
        Ok(())
    };
    match kind {
        VerificationKind::AptPackage | VerificationKind::AptRepository => {
            let present = ["executable", "args", "output_contains"]
                .into_iter()
                .filter(|key| object.contains_key(*key))
                .count();
            if present != 0 && present != 3 {
                return Err(DependencyError::new(format!(
                    "{record_id}.verification requires executable, args, and output_contains"
                )));
            }
            if present == 3 {
                require_executable("apt")?;
            }
        }
        VerificationKind::NpmPackage | VerificationKind::PipxPackage => {
            require_executable("package")?;
        }
        VerificationKind::RustToolchain => {
            let present = ["executable", "args", "output_contains"]
                .into_iter()
                .filter(|key| object.contains_key(*key))
                .count();
            if present != 0 && present != 3 {
                return Err(DependencyError::new(format!(
                    "{record_id}.verification requires executable, args, and output_contains"
                )));
            }
            if present == 3 {
                require_executable("rust")?;
            }
        }
        VerificationKind::AbsoluteExecutable => {
            let path = path.as_deref().ok_or_else(|| {
                DependencyError::new(format!(
                    "{record_id}.verification requires path, args, and output_contains"
                ))
            })?;
            normalized_absolute_path(path, &format!("{record_id}.verification.path"))?;
            if args.is_empty() || output_contains.is_none() {
                return Err(DependencyError::new(format!(
                    "{record_id}.verification requires path, args, and output_contains"
                )));
            }
        }
        VerificationKind::CargoBinary => {
            let path = path.as_deref().ok_or_else(|| {
                DependencyError::new(format!(
                    "{record_id}.verification requires path, args, and output_contains"
                ))
            })?;
            if !safe_relative_path(path) || args.is_empty() || output_contains.is_none() {
                return Err(DependencyError::new(format!(
                    "{record_id}.verification.path must be a safe relative cargo binary path"
                )));
            }
        }
        VerificationKind::BrowserExecutable => {
            if executable_globs.is_empty() || args.is_empty() || output_contains.is_none() {
                return Err(DependencyError::new(format!(
                    "{record_id}.verification requires executable_globs, args, and output_contains"
                )));
            }
            for glob in &executable_globs {
                if glob.starts_with('/')
                    || has_parent_segment(glob)
                    || relative_normalize(glob) != glob.as_str()
                    || glob
                        .split('/')
                        .any(|part| part.is_empty() || !matches(r"^[A-Za-z0-9._*?\[\]-]+$", part))
                {
                    return Err(DependencyError::new(format!(
                        "{record_id}.verification.executable_globs must be safe relative cache globs"
                    )));
                }
            }
        }
        VerificationKind::LeanToolchain => {
            if executable.is_some()
                || path.is_some()
                || !args.is_empty()
                || output_contains.is_some()
                || !executable_globs.is_empty()
            {
                return Err(DependencyError::new(format!(
                    "{record_id}.verification does not permit executable fields for {}",
                    kind.as_str()
                )));
            }
        }
    }
    Ok(VerificationSpec {
        kind,
        executable,
        path,
        args,
        output_contains,
        executable_globs,
    })
}

fn parse_record(raw: &Value, path: &Path, index: usize) -> Result<DependencyRecord> {
    let object = object(raw, &format!("{}: records[{index}]", path.display()))?;
    const ALLOWED: &[&str] = &[
        "id",
        "package",
        "method",
        "version",
        "source",
        "platform",
        "platforms",
        "verification",
        "deps",
        "provides",
        "failure_policy",
        "key_fingerprint",
        "key_url",
        "repository_suite",
        "repository_components",
        "repository_packages_sha256",
        "repository_package_url",
        "repository_package_sha256",
        "repository_packages_sha256s",
        "repository_package_urls",
        "repository_package_sha256s",
        "checksum",
        "checksums",
        "asset",
        "assets",
        "archive_format",
        "extract",
        "destination",
        "repo",
        "commit",
        "source_identity",
        "source_tree_sha256",
        "cargo_lock_sha256",
        "locked",
        "browser",
        "browser_cache_path",
        "components",
        "executable_owner_packages",
    ];
    reject_unknown_fields(
        object,
        ALLOWED,
        &format!("{}: records[{index}]", path.display()),
    )?;
    for required in [
        "id",
        "package",
        "method",
        "source",
        "verification",
        "deps",
        "provides",
        "failure_policy",
    ] {
        if !object.contains_key(required) {
            return Err(DependencyError::new(format!(
                "{}: records[{index}] missing fields: {required}",
                path.display()
            )));
        }
    }
    let id = required_string(object, "id", "id")?;
    if !matches(r"^[a-z0-9][a-z0-9._-]*$", &id) {
        return Err(DependencyError::new(format!(
            "{}: {id}: invalid id",
            path.display()
        )));
    }
    let method_text = required_string(object, "method", &format!("{id}.method"))?;
    let method = Method::parse(&method_text).ok_or_else(|| {
        DependencyError::new(format!(
            "{}: {id}: unsupported method {method_text}",
            path.display()
        ))
    })?;
    let version = optional_string(object, "version", &format!("{id}.version"))?;
    if version.is_none() && method != Method::AptPackage {
        return Err(DependencyError::new(format!(
            "{}: {id}: version is required",
            path.display()
        )));
    }
    let package = required_string(object, "package", &format!("{id}.package"))?;
    let source = required_string(object, "source", &format!("{id}.source"))?;
    let failure_policy =
        required_string(object, "failure_policy", &format!("{id}.failure_policy"))?;
    if !["fail", "warn"].contains(&failure_policy.as_str()) {
        return Err(DependencyError::new(format!(
            "{id}: unsupported failure policy {failure_policy}"
        )));
    }
    let verification = parse_verification(&object["verification"], &id, method)?;
    let deps = string_list_value(object.get("deps"), &format!("{id}.deps"), true)?;
    let provides = string_list_value(object.get("provides"), &format!("{id}.provides"), false)?;
    let is_apt = matches!(method, Method::AptPackage | Method::AptRepository);
    let platform = optional_string(object, "platform", &format!("{id}.platform"))?;
    let platforms = string_list_value(object.get("platforms"), &format!("{id}.platforms"), true)?;
    let mut key_fingerprint =
        optional_string(object, "key_fingerprint", &format!("{id}.key_fingerprint"))?;
    if let Some(value) = &mut key_fingerprint {
        let normalized: String = value
            .chars()
            .filter(|ch| !ch.is_whitespace() && *ch != ':')
            .collect::<String>()
            .to_ascii_uppercase();
        if normalized.len() != 40 || !normalized.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(DependencyError::new(format!(
                "{id}.key_fingerprint must be a full 40-digit hex fingerprint"
            )));
        }
        *value = normalized;
    }
    let repository_suite = optional_string(
        object,
        "repository_suite",
        &format!("{id}.repository_suite"),
    )?
    .or_else(|| (method == Method::AptRepository).then(|| "stable".to_string()));
    let repository_components = if object.contains_key("repository_components") {
        string_list_value(
            object.get("repository_components"),
            &format!("{id}.repository_components"),
            method != Method::AptRepository,
        )?
    } else if method == Method::AptRepository {
        vec!["main".to_string()]
    } else {
        Vec::new()
    };
    let repository_packages_sha256 = optional_string(
        object,
        "repository_packages_sha256",
        &format!("{id}.repository_packages_sha256"),
    )?;
    let repository_package_url = optional_string(
        object,
        "repository_package_url",
        &format!("{id}.repository_package_url"),
    )?;
    let mut repository_package_sha256 = optional_string(
        object,
        "repository_package_sha256",
        &format!("{id}.repository_package_sha256"),
    )?;
    if let Some(value) = &mut repository_package_sha256 {
        if !is_hex(value, 64) {
            return Err(DependencyError::new(format!(
                "{id}.repository_package_sha256 must be a 64-character SHA256"
            )));
        }
        *value = value.to_ascii_lowercase();
    }
    let mut repository_packages_sha256 = repository_packages_sha256;
    if let Some(value) = &mut repository_packages_sha256 {
        if !is_hex(value, 64) {
            return Err(DependencyError::new(format!(
                "{id}.repository_packages_sha256 must be a 64-character SHA256"
            )));
        }
        *value = value.to_ascii_lowercase();
    }
    let repository_packages_sha256s = object
        .get("repository_packages_sha256s")
        .map(|value| checksums(value, &format!("{id}.repository_packages_sha256s")))
        .transpose()?
        .unwrap_or_default();
    let repository_package_urls = object
        .get("repository_package_urls")
        .map(|value| sorted_string_map(value, &format!("{id}.repository_package_urls")))
        .transpose()?
        .unwrap_or_default();
    let repository_package_sha256s = object
        .get("repository_package_sha256s")
        .map(|value| checksums(value, &format!("{id}.repository_package_sha256s")))
        .transpose()?
        .unwrap_or_default();
    let checksum = optional_string(object, "checksum", &format!("{id}.checksum"))?;
    let checksums_value = object
        .get("checksums")
        .map(|value| checksums(value, &format!("{id}.checksums")))
        .transpose()?
        .unwrap_or_default();
    let asset = optional_string(object, "asset", &format!("{id}.asset"))?;
    let assets = object
        .get("assets")
        .map(|value| sorted_string_map(value, &format!("{id}.assets")))
        .transpose()?
        .unwrap_or_default();
    let archive_format =
        optional_string(object, "archive_format", &format!("{id}.archive_format"))?;
    let extract = optional_string(object, "extract", &format!("{id}.extract"))?;
    let destination = optional_string(object, "destination", &format!("{id}.destination"))?;
    let executable_owner_packages = if object.contains_key("executable_owner_packages") {
        string_list_value(
            object.get("executable_owner_packages"),
            &format!("{id}.executable_owner_packages"),
            !is_apt,
        )?
    } else if is_apt {
        vec![package.clone()]
    } else {
        Vec::new()
    };
    let repo = optional_string(object, "repo", &format!("{id}.repo"))?;
    let commit = optional_string(object, "commit", &format!("{id}.commit"))?;
    let source_identity =
        optional_string(object, "source_identity", &format!("{id}.source_identity"))?;
    let source_tree_sha256 = optional_string(
        object,
        "source_tree_sha256",
        &format!("{id}.source_tree_sha256"),
    )?;
    let cargo_lock_sha256 = optional_string(
        object,
        "cargo_lock_sha256",
        &format!("{id}.cargo_lock_sha256"),
    )?;
    let locked = object
        .get("locked")
        .map(|value| {
            value
                .as_bool()
                .ok_or_else(|| DependencyError::new(format!("{id}.locked must be a boolean")))
        })
        .transpose()?;
    let browser = optional_string(object, "browser", &format!("{id}.browser"))?;
    let browser_cache_path = optional_string(
        object,
        "browser_cache_path",
        &format!("{id}.browser_cache_path"),
    )?;
    let components =
        string_list_value(object.get("components"), &format!("{id}.components"), true)?;
    let record = DependencyRecord {
        id,
        package,
        method,
        version,
        source,
        verification,
        deps,
        provides,
        failure_policy,
        platform,
        platforms,
        key_fingerprint,
        key_url: optional_string(object, "key_url", "key_url")?,
        repository_suite,
        repository_components,
        repository_packages_sha256,
        repository_package_url,
        repository_package_sha256,
        repository_packages_sha256s,
        repository_package_urls,
        repository_package_sha256s,
        checksum,
        checksums: checksums_value,
        asset,
        assets,
        archive_format,
        extract,
        destination,
        executable_owner_packages,
        repo,
        commit,
        source_identity,
        source_tree_sha256,
        cargo_lock_sha256,
        locked,
        browser,
        browser_cache_path,
        components,
    };
    validate_method_fields(&record, object)?;
    validate_record_values(&record)?;
    Ok(record)
}

fn relative_normalize(value: &str) -> String {
    let mut components = Vec::new();
    for part in value.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                components.pop();
            }
            other => components.push(other),
        }
    }
    components.join("/")
}

fn validate_method_fields(record: &DependencyRecord, raw: &Map<String, Value>) -> Result<()> {
    let common = [
        "id",
        "package",
        "method",
        "version",
        "source",
        "platform",
        "platforms",
        "verification",
        "deps",
        "provides",
        "failure_policy",
    ];
    let method_fields: &[&str] = match record.method {
        Method::AptPackage => &["executable_owner_packages"],
        Method::AptRepository => &[
            "key_fingerprint",
            "key_url",
            "repository_suite",
            "repository_components",
            "repository_packages_sha256",
            "repository_package_url",
            "repository_package_sha256",
            "repository_packages_sha256s",
            "repository_package_urls",
            "repository_package_sha256s",
            "executable_owner_packages",
        ],
        Method::NpmGlobal | Method::Pipx | Method::LeanToolchain => &[],
        Method::ReleaseAsset => &[
            "checksum",
            "checksums",
            "asset",
            "assets",
            "archive_format",
            "extract",
            "destination",
        ],
        Method::RustToolchain => &["components", "checksums"],
        Method::CargoSourceBuild => &[
            "repo",
            "commit",
            "source_identity",
            "locked",
            "source_tree_sha256",
            "cargo_lock_sha256",
        ],
        Method::BrowserInstall => &["browser", "browser_cache_path"],
    };
    let unsupported = raw
        .keys()
        .filter(|key| !common.contains(&key.as_str()) && !method_fields.contains(&key.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    if unsupported.is_empty() {
        Ok(())
    } else {
        Err(DependencyError::new(format!(
            "{}: unsupported fields for {}: {}",
            record.id,
            record.method.as_str(),
            unsupported.join(", ")
        )))
    }
}

fn validate_record_values(record: &DependencyRecord) -> Result<()> {
    let id = &record.id;
    if record
        .platform
        .as_ref()
        .is_some_and(|platform| !matches(r"^linux/(?:amd64|arm64)$", platform))
        || record
            .platforms
            .iter()
            .any(|platform| !matches(r"^linux/(?:amd64|arm64)$", platform))
        || record.platforms.len() != record.platforms.iter().collect::<BTreeSet<_>>().len()
        || record.platform.as_ref().is_some_and(|platform| {
            !record.platforms.is_empty() && !record.platforms.contains(platform)
        })
    {
        return Err(DependencyError::new(format!(
            "{id}.platforms has an unsupported or incompatible platform"
        )));
    }
    if let Some(url) = &record.key_url {
        validate_url(url, &format!("{id}.key_url"), false)?;
    }
    match record.method {
        Method::AptPackage | Method::AptRepository => {
            if !matches(r"^[a-z0-9][a-z0-9+.-]*$", &record.package) {
                return Err(DependencyError::new(format!(
                    "{id}.package is not an apt package name"
                )));
            }
            if record.executable_owner_packages.is_empty()
                || record
                    .executable_owner_packages
                    .iter()
                    .any(|name| !matches(r"^[a-z0-9][a-z0-9+.-]*$", name))
            {
                return Err(DependencyError::new(format!(
                    "{id}.executable_owner_packages is invalid"
                )));
            }
            if record
                .version
                .as_ref()
                .is_some_and(|version| !matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", version))
            {
                return Err(DependencyError::new(format!(
                    "{id}.version has an unsupported apt value"
                )));
            }
            if record.method == Method::AptRepository {
                let version = record.version.as_deref().ok_or_else(|| {
                    DependencyError::new(format!(
                        "{id}.version is required for apt-repository packages"
                    ))
                })?;
                if !matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", version) {
                    return Err(DependencyError::new(format!(
                        "{id}.version has an unsupported apt value"
                    )));
                }
                validate_url(&record.source, &format!("{id}.source"), true)?;
                if record
                    .repository_suite
                    .as_deref()
                    .is_none_or(|suite| !matches(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$", suite))
                    || record.repository_components.is_empty()
                    || record
                        .repository_components
                        .iter()
                        .any(|value| !matches(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$", value))
                {
                    return Err(DependencyError::new(format!(
                        "{id}: apt repository suite/components are invalid"
                    )));
                }
                if record.repository_packages_sha256.is_some()
                    && (record.platform.is_none()
                        || record.repository_components.len() != 1
                        || !record
                            .repository_packages_sha256
                            .as_ref()
                            .is_some_and(|value| is_hex(value, 64)))
                {
                    return Err(DependencyError::new(format!(
                        "{id}.repository_packages_sha256 is invalid"
                    )));
                }
                for (field, values) in [
                    (
                        "repository_packages_sha256s",
                        &record.repository_packages_sha256s,
                    ),
                    ("repository_package_urls", &record.repository_package_urls),
                    (
                        "repository_package_sha256s",
                        &record.repository_package_sha256s,
                    ),
                ] {
                    for (arch, value) in values {
                        if !["amd64", "arm64"].contains(&arch.as_str())
                            || (field != "repository_package_urls" && !is_hex(value, 64))
                        {
                            return Err(DependencyError::new(format!(
                                "{id}.{field} has an invalid architecture or value"
                            )));
                        }
                        if field == "repository_package_urls" {
                            validate_url(value, &format!("{id}.{field}[{arch}]"), true)?;
                            if !value.to_ascii_lowercase().ends_with(".deb") {
                                return Err(DependencyError::new(format!(
                                    "{id}.{field}[{arch}] must name a .deb artifact"
                                )));
                            }
                        }
                    }
                }
                let url_arches = record
                    .repository_package_urls
                    .iter()
                    .map(|(arch, _)| arch.clone())
                    .collect::<BTreeSet<_>>();
                let sha_arches = record
                    .repository_package_sha256s
                    .iter()
                    .map(|(arch, _)| arch.clone())
                    .collect::<BTreeSet<_>>();
                if url_arches != sha_arches {
                    return Err(DependencyError::new(format!(
                        "{id}: repository package URL/checksum architecture maps differ"
                    )));
                }
                if !record.platforms.is_empty()
                    && !url_arches.is_empty()
                    && record
                        .platforms
                        .iter()
                        .map(|value| value.split('/').nth(1).unwrap_or_default().to_string())
                        .collect::<BTreeSet<_>>()
                        != url_arches
                {
                    return Err(DependencyError::new(format!(
                        "{id}: repository package map does not cover declared platforms"
                    )));
                }
                if record.repository_package_url.is_some()
                    != record.repository_package_sha256.is_some()
                {
                    return Err(DependencyError::new(format!("{id}: repository_package_url and repository_package_sha256 must be provided together")));
                }
                if let Some(url) = &record.repository_package_url {
                    validate_url(url, &format!("{id}.repository_package_url"), true)?;
                    if !url.to_ascii_lowercase().ends_with(".deb")
                        || !record
                            .repository_package_sha256
                            .as_ref()
                            .is_some_and(|value| is_hex(value, 64))
                    {
                        return Err(DependencyError::new(format!(
                            "{id}.repository_package_url/checksum is invalid"
                        )));
                    }
                }
                if record.repository_package_url.is_some()
                    || !record.repository_package_urls.is_empty()
                {
                    let selected_url = if record.repository_package_urls.is_empty() {
                        record.repository_package_url.as_deref()
                    } else {
                        let architecture = runtime_architecture()?;
                        record
                            .repository_package_urls
                            .iter()
                            .find(|(key, _)| key == &architecture)
                            .map(|(_, value)| value.as_str())
                    }
                    .ok_or_else(|| {
                        DependencyError::new(format!(
                            "{id}: immutable apt package URL is not declared"
                        ))
                    })?;
                    let filename = selected_url.rsplit('/').next().unwrap_or_default();
                    if !matches(r"^[A-Za-z0-9][A-Za-z0-9.+_~-]*\.deb$", filename) {
                        return Err(DependencyError::new(format!(
                            "{id}: immutable apt package URL has an unsafe filename"
                        )));
                    }
                }
            } else if !matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", &record.source)
                && !record.source.starts_with("https://")
            {
                return Err(DependencyError::new(format!(
                    "{id}.source has an unsupported apt value"
                )));
            }
        }
        Method::NpmGlobal => {
            if !matches(
                r"^(?:@[a-z0-9._~-]+/[a-z0-9._~-]+|[a-z0-9._~-]+)$",
                &record.package,
            ) {
                return Err(DependencyError::new(format!(
                    "{id}.package has an unsupported registry name"
                )));
            }
            let version = record.version.as_deref().unwrap_or_default();
            if !matches(
                r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$",
                version,
            ) {
                return Err(DependencyError::new(format!(
                    "{id}.version must be an exact version"
                )));
            }
            validate_url(&record.source, &format!("{id}.source"), true)?;
        }
        Method::Pipx => {
            if !matches(
                r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$",
                &record.package,
            ) {
                return Err(DependencyError::new(format!(
                    "{id}.package has an unsupported registry name"
                )));
            }
            let version = record.version.as_deref().unwrap_or_default();
            if !is_pep440_version(version) {
                return Err(DependencyError::new(format!(
                    "{id}.version must be an exact PEP 440 version"
                )));
            }
            validate_url(&record.source, &format!("{id}.source"), true)?;
        }
        Method::ReleaseAsset => {
            let version = record.version.as_deref().unwrap_or_default();
            if !matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", version) {
                return Err(DependencyError::new(format!(
                    "{id}.version has an unsupported release value"
                )));
            }
            validate_url(&record.source, &format!("{id}.source"), true)?;
            if record.checksum.is_none() && record.checksums.is_empty() {
                return Err(DependencyError::new(format!(
                    "{id}: release-asset requires checksum"
                )));
            }
            if record
                .checksum
                .as_ref()
                .is_some_and(|value| !is_hex(value, 64))
            {
                return Err(DependencyError::new(format!(
                    "{id}.checksum must be a 64-character SHA256"
                )));
            }
            if record.asset.is_none() && record.assets.is_empty() {
                return Err(DependencyError::new(format!(
                    "{id}: release-asset requires asset or architecture assets"
                )));
            }
            for asset in record
                .asset
                .iter()
                .chain(record.assets.iter().map(|(_, value)| value))
            {
                validate_asset_path(asset, &format!("{id}.asset"))?;
                if record.archive_format.as_deref() == Some("deb") && !asset.ends_with(".deb") {
                    return Err(DependencyError::new(format!(
                        "{id}.asset must name a .deb file"
                    )));
                }
            }
            if record
                .assets
                .iter()
                .any(|(arch, _)| !["x86_64", "aarch64"].contains(&arch.as_str()))
            {
                return Err(DependencyError::new(format!(
                    "{id}.assets has an unsupported architecture"
                )));
            }
            if !["binary", "deb", "tar.gz", "tar.xz", "tar", "zip"]
                .contains(&record.archive_format.as_deref().unwrap_or_default())
            {
                return Err(DependencyError::new(format!(
                    "{id}.archive_format is unsupported"
                )));
            }
            let extract = record.extract.as_deref().ok_or_else(|| {
                DependencyError::new(format!(
                    "{id}: release-asset requires extract and destination"
                ))
            })?;
            validate_safe_member(extract)?;
            if (["binary", "deb"].contains(&record.archive_format.as_deref().unwrap_or_default()))
                != (extract == "none")
            {
                return Err(DependencyError::new(format!(
                    "{id}: binary and .deb release assets require extract=none"
                )));
            }
            safe_absolute_path(
                record.destination.as_deref().ok_or_else(|| {
                    DependencyError::new(format!("{id}: release-asset destination is required"))
                })?,
                &format!("{id}.destination"),
                "/usr/local/bin",
            )?;
        }
        Method::RustToolchain => {
            let version = record.version.as_deref().unwrap_or_default();
            if !matches(r"^[0-9]+\.[0-9]+\.[0-9]+$", version) {
                return Err(DependencyError::new(format!(
                    "{id}.version must be an exact Rust version"
                )));
            }
            validate_url(&record.source, &format!("{id}.source"), true)?;
            if record.components.iter().any(|component| {
                !["rust-src", "rustfmt", "clippy", "rust-analyzer"].contains(&component.as_str())
            }) {
                return Err(DependencyError::new(format!(
                    "{id}.components contains an unsupported component"
                )));
            }
        }
        Method::LeanToolchain => {
            if !matches(
                r"^leanprover/lean4:v[0-9]+\.[0-9]+\.[0-9]+$",
                record.version.as_deref().unwrap_or_default(),
            ) {
                return Err(DependencyError::new(format!(
                    "{id}.version must be an exact Lean toolchain"
                )));
            }
            validate_url(&record.source, &format!("{id}.source"), true)?;
        }
        Method::CargoSourceBuild => {
            if !safe_relative_path(&record.source)
                || record.repo.is_none()
                || record.locked != Some(true)
                || record.commit.is_some() == record.source_identity.is_some()
            {
                return Err(DependencyError::new(format!("{id}: cargo-source-build requires repo, exactly one of commit or source_identity, and locked=true")));
            }
            validate_url(
                record.repo.as_deref().unwrap_or_default(),
                &format!("{id}.repo"),
                true,
            )?;
            if record
                .commit
                .as_ref()
                .is_some_and(|value| !is_hex(value, 40))
            {
                return Err(DependencyError::new(format!(
                    "{id}.commit must be a full 40-hex commit"
                )));
            }
            if record
                .source_identity
                .as_deref()
                .is_some_and(|value| !["active-source", "canonical-snapshot"].contains(&value))
            {
                return Err(DependencyError::new(format!(
                    "{id}.source_identity must be active-source or canonical-snapshot"
                )));
            }
            if record.source_identity.as_deref() == Some("canonical-snapshot") {
                if record
                    .source_tree_sha256
                    .as_ref()
                    .is_some_and(|value| !is_hex(value, 64))
                    || !record
                        .cargo_lock_sha256
                        .as_ref()
                        .is_some_and(|value| is_hex(value, 64))
                {
                    return Err(DependencyError::new(format!(
                        "{id}: canonical-snapshot source digests are invalid"
                    )));
                }
            } else if record.source_tree_sha256.is_some() || record.cargo_lock_sha256.is_some() {
                return Err(DependencyError::new(format!(
                    "{id}: source snapshot digests require canonical-snapshot"
                )));
            }
        }
        Method::BrowserInstall => {
            if !["chromium", "firefox", "webkit"].contains(&record.package.as_str())
                || !["chromium", "firefox", "webkit"]
                    .contains(&record.browser.as_deref().unwrap_or_default())
                || !matches(
                    r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$",
                    record.version.as_deref().unwrap_or_default(),
                )
            {
                return Err(DependencyError::new(format!(
                    "{id}: browser/version is unsupported"
                )));
            }
            validate_url(&record.source, &format!("{id}.source"), true)?;
            safe_absolute_path(
                record.browser_cache_path.as_deref().unwrap_or_default(),
                &format!("{id}.browser_cache_path"),
                "/usr/local/share",
            )?;
        }
    }
    if !matches!(
        record.method,
        Method::AptPackage
            | Method::AptRepository
            | Method::NpmGlobal
            | Method::Pipx
            | Method::BrowserInstall
    ) && !matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", &record.package)
    {
        return Err(DependencyError::new(format!(
            "{id}.package has an unsupported value"
        )));
    }
    if record.method == Method::AptRepository
        && (record.key_fingerprint.is_none() || record.key_url.is_none())
    {
        return Err(DependencyError::new(format!(
            "{id}: apt-repository requires key_url and key_fingerprint"
        )));
    }
    if record.method == Method::AptPackage
        && !matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", &record.source)
        && !record.source.starts_with("https://")
    {
        return Err(DependencyError::new(format!(
            "{id}.source has an unsupported apt value"
        )));
    }
    if record.method == Method::ReleaseAsset && record.verification.path != record.destination {
        return Err(DependencyError::new(format!(
            "{id}: release verification path must equal destination"
        )));
    }
    if record.method == Method::CargoSourceBuild && record.verification.path.is_none() {
        return Err(DependencyError::new(format!(
            "{id}: cargo verification path is required"
        )));
    }
    if record.method == Method::BrowserInstall && record.verification.executable_globs.is_empty() {
        return Err(DependencyError::new(format!(
            "{id}: browser executable glob is required"
        )));
    }
    Ok(())
}

fn manifest_sources(workspace: &Path, manifest: Option<&Path>) -> Result<Vec<ManifestSource>> {
    if let Some(manifest) = manifest {
        let path = fs::canonicalize(manifest).map_err(|_| {
            DependencyError::new(format!("manifest not found: {}", manifest.display()))
        })?;
        if !path.is_file() {
            return Err(DependencyError::new(format!(
                "manifest not found: {}",
                path.display()
            )));
        }
        return Ok(vec![ManifestSource {
            path,
            role: ManifestRole::Canonical,
        }]);
    }
    let workspace = fs::canonicalize(workspace).map_err(|error| {
        DependencyError::new(format!(
            "cannot resolve workspace {}: {error}",
            workspace.display()
        ))
    })?;
    let path = workspace.join("bootstrap/container/image/dependencies.toml");
    if path.is_file() {
        let path = fs::canonicalize(&path).map_err(|error| {
            DependencyError::new(format!(
                "cannot resolve manifest {}: {error}",
                path.display()
            ))
        })?;
        Ok(vec![ManifestSource {
            path,
            role: ManifestRole::Canonical,
        }])
    } else {
        Ok(Vec::new())
    }
}

fn load_manifest(source: ManifestSource) -> Result<LoadedManifest> {
    let text = fs::read_to_string(&source.path).map_err(|error| {
        DependencyError::new(format!(
            "cannot parse manifest {}: {error}",
            source.path.display()
        ))
    })?;
    let raw: Value = toml_edit::de::from_str(&text).map_err(|error| {
        DependencyError::new(format!(
            "cannot parse manifest {}: {error}",
            source.path.display()
        ))
    })?;
    let root = object(&raw, &format!("{}: manifest", source.path.display()))?;
    reject_unknown_fields(
        root,
        &["schema", "schema_version", "records", "container"],
        &format!("{}: manifest", source.path.display()),
    )?;
    if root.get("schema").and_then(Value::as_str) != Some(SCHEMA)
        || root.get("schema_version").and_then(Value::as_u64) != Some(SCHEMA_VERSION)
    {
        return Err(DependencyError::new(format!(
            "{}: schema must be {SCHEMA:?} version {SCHEMA_VERSION}",
            source.path.display()
        )));
    }
    if let Some(container) = root.get("container") {
        let container = object(container, &format!("{}: container", source.path.display()))?;
        reject_unknown_fields(
            container,
            &["platform", "uid", "gid"],
            &format!("{}: container", source.path.display()),
        )?;
        if container.get("platform").and_then(Value::as_str) != Some("linux/amd64") {
            return Err(DependencyError::new(format!(
                "{}: container.platform must be linux/amd64",
                source.path.display()
            )));
        }
        for key in ["uid", "gid"] {
            if container
                .get(key)
                .and_then(Value::as_i64)
                .is_none_or(|value| value <= 0)
            {
                return Err(DependencyError::new(format!(
                    "{}: container.{key} must be a positive integer",
                    source.path.display()
                )));
            }
        }
    }
    let raw_records = root
        .get("records")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            DependencyError::new(format!(
                "{}: records must be an array of tables",
                source.path.display()
            ))
        })?;
    if raw_records.is_empty() && source.role != ManifestRole::ParentOverlay {
        return Err(DependencyError::new(format!(
            "{}: records must be a non-empty array of tables",
            source.path.display()
        )));
    }
    let mut ids = BTreeSet::new();
    let mut records = Vec::with_capacity(raw_records.len());
    for (index, raw) in raw_records.iter().enumerate() {
        let record = parse_record(raw, &source.path, index)?;
        if !ids.insert(record.id.clone()) {
            return Err(DependencyError::new(format!(
                "{}: record ids must be unique",
                source.path.display()
            )));
        }
        records.push(record);
    }
    Ok(LoadedManifest { source, records })
}

fn merge_option<T: Clone + PartialEq>(
    left: &Option<T>,
    right: &Option<T>,
    field: &str,
    record_id: &str,
) -> Result<Option<T>> {
    match (left, right) {
        (None, Some(value)) => Ok(Some(value.clone())),
        (Some(value), None) => Ok(Some(value.clone())),
        (None, None) => Ok(None),
        (Some(left), Some(right)) if left == right => Ok(Some(left.clone())),
        _ => Err(DependencyError::new(format!(
            "incompatible duplicate {record_id}: {field}"
        ))),
    }
}

fn merge_required<T: Clone + PartialEq>(
    left: &T,
    right: &T,
    field: &str,
    record_id: &str,
) -> Result<T> {
    if left == right {
        Ok(left.clone())
    } else {
        Err(DependencyError::new(format!(
            "incompatible duplicate {record_id}: {field}"
        )))
    }
}

fn ordered_union(left: &[String], right: &[String]) -> Vec<String> {
    let mut values = left.to_vec();
    for value in right {
        if !values.contains(value) {
            values.push(value.clone());
        }
    }
    values
}

fn union_map(
    left: &[(String, String)],
    right: &[(String, String)],
    field: &str,
    record_id: &str,
) -> Result<Vec<(String, String)>> {
    let mut values = left.iter().cloned().collect::<BTreeMap<_, _>>();
    for (key, value) in right {
        if values.get(key).is_some_and(|previous| previous != value) {
            return Err(DependencyError::new(format!(
                "incompatible duplicate {record_id}: {field}[{key}]"
            )));
        }
        values.insert(key.clone(), value.clone());
    }
    Ok(values.into_iter().collect())
}

fn overwrite_map(left: &[(String, String)], right: &[(String, String)]) -> Vec<(String, String)> {
    let mut values = left.iter().cloned().collect::<BTreeMap<_, _>>();
    values.extend(right.iter().cloned());
    values.into_iter().collect()
}

fn merge_duplicate(
    current: &DependencyRecord,
    incoming: &DependencyRecord,
) -> Result<DependencyRecord> {
    let id = &current.id;
    if current.id != incoming.id {
        return Err(DependencyError::new(
            "internal dependency merge id mismatch",
        ));
    }
    Ok(DependencyRecord {
        id: current.id.clone(),
        package: merge_required(&current.package, &incoming.package, "package", id)?,
        method: merge_required(&current.method, &incoming.method, "method", id)?,
        version: merge_option(&current.version, &incoming.version, "version", id)?,
        source: merge_required(&current.source, &incoming.source, "source", id)?,
        verification: merge_required(
            &current.verification,
            &incoming.verification,
            "verification",
            id,
        )?,
        deps: ordered_union(&current.deps, &incoming.deps),
        provides: ordered_union(&current.provides, &incoming.provides),
        failure_policy: merge_required(
            &current.failure_policy,
            &incoming.failure_policy,
            "failure_policy",
            id,
        )?,
        platform: merge_option(&current.platform, &incoming.platform, "platform", id)?,
        platforms: ordered_union(&current.platforms, &incoming.platforms),
        key_fingerprint: merge_option(
            &current.key_fingerprint,
            &incoming.key_fingerprint,
            "key_fingerprint",
            id,
        )?,
        key_url: merge_option(&current.key_url, &incoming.key_url, "key_url", id)?,
        repository_suite: merge_option(
            &current.repository_suite,
            &incoming.repository_suite,
            "repository_suite",
            id,
        )?,
        repository_components: merge_required(
            &current.repository_components,
            &incoming.repository_components,
            "repository_components",
            id,
        )?,
        repository_packages_sha256: merge_option(
            &current.repository_packages_sha256,
            &incoming.repository_packages_sha256,
            "repository_packages_sha256",
            id,
        )?,
        repository_package_url: merge_option(
            &current.repository_package_url,
            &incoming.repository_package_url,
            "repository_package_url",
            id,
        )?,
        repository_package_sha256: merge_option(
            &current.repository_package_sha256,
            &incoming.repository_package_sha256,
            "repository_package_sha256",
            id,
        )?,
        repository_packages_sha256s: overwrite_map(
            &current.repository_packages_sha256s,
            &incoming.repository_packages_sha256s,
        ),
        repository_package_urls: overwrite_map(
            &current.repository_package_urls,
            &incoming.repository_package_urls,
        ),
        repository_package_sha256s: overwrite_map(
            &current.repository_package_sha256s,
            &incoming.repository_package_sha256s,
        ),
        checksum: merge_option(&current.checksum, &incoming.checksum, "checksum", id)?,
        checksums: union_map(&current.checksums, &incoming.checksums, "checksums", id)?,
        asset: merge_option(&current.asset, &incoming.asset, "asset", id)?,
        assets: union_map(&current.assets, &incoming.assets, "assets", id)?,
        archive_format: merge_option(
            &current.archive_format,
            &incoming.archive_format,
            "archive_format",
            id,
        )?,
        extract: merge_option(&current.extract, &incoming.extract, "extract", id)?,
        destination: merge_option(
            &current.destination,
            &incoming.destination,
            "destination",
            id,
        )?,
        executable_owner_packages: merge_required(
            &current.executable_owner_packages,
            &incoming.executable_owner_packages,
            "executable_owner_packages",
            id,
        )?,
        repo: merge_option(&current.repo, &incoming.repo, "repo", id)?,
        commit: merge_option(&current.commit, &incoming.commit, "commit", id)?,
        source_identity: merge_option(
            &current.source_identity,
            &incoming.source_identity,
            "source_identity",
            id,
        )?,
        source_tree_sha256: merge_option(
            &current.source_tree_sha256,
            &incoming.source_tree_sha256,
            "source_tree_sha256",
            id,
        )?,
        cargo_lock_sha256: merge_option(
            &current.cargo_lock_sha256,
            &incoming.cargo_lock_sha256,
            "cargo_lock_sha256",
            id,
        )?,
        locked: merge_option(&current.locked, &incoming.locked, "locked", id)?,
        browser: merge_option(&current.browser, &incoming.browser, "browser", id)?,
        browser_cache_path: merge_option(
            &current.browser_cache_path,
            &incoming.browser_cache_path,
            "browser_cache_path",
            id,
        )?,
        components: ordered_union(&current.components, &incoming.components),
    })
}

fn merge_records(manifests: &[LoadedManifest]) -> Result<Vec<DependencyRecord>> {
    let mut records = Vec::<DependencyRecord>::new();
    let mut positions = BTreeMap::<String, usize>::new();
    for manifest in manifests {
        for incoming in &manifest.records {
            if let Some(index) = positions.get(&incoming.id).copied() {
                records[index] = merge_duplicate(&records[index], incoming)?;
            } else {
                positions.insert(incoming.id.clone(), records.len());
                records.push(incoming.clone());
            }
        }
    }
    Ok(records)
}

fn runtime_platform() -> String {
    let architecture = match env::consts::ARCH {
        "x86_64" | "amd64" => "amd64",
        "aarch64" | "arm64" => "arm64",
        other => other,
    };
    format!("linux/{architecture}")
}

fn build_plan(manifests: &[LoadedManifest]) -> Result<DependencyPlan> {
    let all_records = merge_records(manifests)?;
    if all_records.is_empty() {
        return Err(DependencyError::new(
            "merged dependency plan must contain at least one record",
        ));
    }
    let platform = runtime_platform();
    let mut records = Vec::new();
    for record in all_records {
        if record
            .platform
            .as_deref()
            .is_some_and(|required| required != platform)
        {
            return Err(DependencyError::new(format!(
                "dependency record {} requires {}, but runtime platform is {}; no compatibility fallback is defined",
                record.id,
                record.platform.as_deref().unwrap_or_default(),
                platform
            )));
        }
        if !record.platforms.is_empty() && !record.platforms.contains(&platform) {
            continue;
        }
        records.push(record);
    }
    if records.is_empty() {
        return Err(DependencyError::new(format!(
            "no dependency records support runtime platform {platform}"
        )));
    }
    let ids = records
        .iter()
        .map(|record| record.id.clone())
        .collect::<BTreeSet<_>>();
    let mut providers = BTreeMap::<String, Vec<String>>::new();
    for record in &records {
        for capability in &record.provides {
            providers
                .entry(capability.clone())
                .or_default()
                .push(record.id.clone());
        }
    }
    let ambiguous = providers
        .iter()
        .filter(|(_, ids)| ids.len() > 1)
        .map(|(capability, ids)| format!("{capability}={ids:?}"))
        .collect::<Vec<_>>();
    if !ambiguous.is_empty() {
        return Err(DependencyError::new(format!(
            "provider ambiguity: {}",
            ambiguous.join(", ")
        )));
    }
    let base = BASE_CAPABILITIES
        .iter()
        .map(|value| value.to_string())
        .collect::<BTreeSet<_>>();
    let index = records
        .iter()
        .enumerate()
        .map(|(i, record)| (record.id.clone(), i))
        .collect::<BTreeMap<_, _>>();
    let mut graph = records
        .iter()
        .map(|record| (record.id.clone(), BTreeSet::<String>::new()))
        .collect::<BTreeMap<_, _>>();
    let mut indegree = records
        .iter()
        .map(|record| (record.id.clone(), 0usize))
        .collect::<BTreeMap<_, _>>();
    let mut dependency_providers = records
        .iter()
        .map(|record| (record.id.clone(), Vec::<String>::new()))
        .collect::<BTreeMap<_, _>>();
    for record in &records {
        for dependency in &record.deps {
            let provider = if ids.contains(dependency) {
                dependency.clone()
            } else if base.contains(dependency) {
                continue;
            } else if let Some(candidates) = providers.get(dependency) {
                if candidates.len() != 1 {
                    return Err(DependencyError::new(format!(
                        "provider ambiguity: {} -> {dependency}",
                        record.id
                    )));
                }
                candidates[0].clone()
            } else {
                return Err(DependencyError::new(format!(
                    "missing dependency: {} -> {dependency}",
                    record.id
                )));
            };
            if provider == record.id {
                return Err(DependencyError::new(format!(
                    "dependency cycle: {} -> {provider}",
                    record.id
                )));
            }
            let required = dependency_providers
                .get_mut(&record.id)
                .expect("record provider vector");
            if !required.contains(&provider) {
                required.push(provider.clone());
            }
            if graph
                .get_mut(&provider)
                .expect("provider graph node")
                .insert(record.id.clone())
            {
                *indegree.get_mut(&record.id).expect("record indegree") += 1;
            }
        }
    }
    let mut ready = VecDeque::new();
    for record in &records {
        if indegree[&record.id] == 0 {
            ready.push_back(record.id.clone());
        }
    }
    let mut order = Vec::with_capacity(records.len());
    while let Some(current) = ready.pop_front() {
        order.push(current.clone());
        let mut dependents = graph[&current].iter().cloned().collect::<Vec<_>>();
        dependents.sort_by_key(|id| index[id]);
        for dependent in dependents {
            let remaining = indegree.get_mut(&dependent).expect("dependent indegree");
            *remaining -= 1;
            if *remaining == 0 {
                ready.push_back(dependent);
            }
        }
    }
    if order.len() != records.len() {
        let ordered = order.iter().cloned().collect::<BTreeSet<_>>();
        let remaining = records
            .iter()
            .filter(|record| !ordered.contains(&record.id))
            .map(|record| record.id.clone())
            .collect::<Vec<_>>();
        return Err(DependencyError::new(format!(
            "dependency cycle: {}",
            remaining.join(", ")
        )));
    }
    let provider_rows = records
        .iter()
        .map(|record| {
            (
                record.id.clone(),
                dependency_providers
                    .get(&record.id)
                    .cloned()
                    .unwrap_or_default(),
            )
        })
        .collect::<Vec<_>>();
    let sources = manifests
        .iter()
        .map(|manifest| manifest.source.path.clone())
        .collect::<Vec<_>>();
    let source_roles = manifests
        .iter()
        .map(|manifest| manifest.source.role.as_str().to_string())
        .collect::<Vec<_>>();
    let payload = json!({
        "source_roles": source_roles.clone(),
        "records": records.iter().map(DependencyRecord::payload).collect::<Vec<_>>(),
        "order": order.clone(),
        "dependency_providers": provider_rows.iter().map(|(record_id, providers)| json!([record_id, providers])).collect::<Vec<_>>(),
    });
    let fingerprint = sha256_hex(&canonical_bytes(&payload)?);
    Ok(DependencyPlan {
        records,
        order,
        sources,
        dependency_providers: provider_rows,
        fingerprint,
        source_roles,
    })
}

fn load_plan(workspace: &Path, manifest: Option<&Path>) -> Result<DependencyPlan> {
    let sources = manifest_sources(workspace, manifest)?;
    if sources.is_empty() {
        return Err(DependencyError::new(
            "no AgentCanon tool dependency manifest found",
        ));
    }
    let manifests = sources
        .into_iter()
        .map(load_manifest)
        .collect::<Result<Vec<_>>>()?;
    build_plan(&manifests)
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ExecutableBinding {
    provided: String,
    lexical_path: String,
    absolute_path: String,
    verification_output: String,
}

impl ExecutableBinding {
    fn from_receipt(value: &Value, name: &str) -> Result<Self> {
        let object = object(value, "executable receipt binding")?;
        let provided = object
            .get("provided")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let lexical_path = object
            .get("lexical_path")
            .and_then(Value::as_str)
            .ok_or_else(|| DependencyError::new("executable receipt binding is stale"))?;
        let absolute_path = object
            .get("absolute_path")
            .and_then(Value::as_str)
            .ok_or_else(|| DependencyError::new("executable receipt binding is stale"))?;
        let verification_output = object
            .get("verification_output")
            .and_then(Value::as_str)
            .ok_or_else(|| DependencyError::new("executable receipt binding is stale"))?;
        if provided != name
            || normalized_absolute_path(lexical_path, "lexical_path").is_err()
            || normalized_absolute_path(absolute_path, "absolute_path").is_err()
            || verification_output.is_empty()
        {
            return Err(DependencyError::new("executable receipt binding is stale"));
        }
        Ok(Self {
            provided: provided.to_string(),
            lexical_path: lexical_path.to_string(),
            absolute_path: absolute_path.to_string(),
            verification_output: verification_output.to_string(),
        })
    }
}

fn executable_binding_names(record: &DependencyRecord, image_owned: bool) -> Vec<String> {
    match record.method {
        Method::NpmGlobal | Method::Pipx if record.method == Method::NpmGlobal || image_owned => {
            let mut names = record
                .provides
                .iter()
                .filter(|name| matches(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", name))
                .cloned()
                .collect::<Vec<_>>();
            if let Some(executable) = &record.verification.executable {
                if !names.contains(executable) {
                    names.insert(0, executable.clone());
                }
            }
            names
        }
        Method::AptPackage | Method::AptRepository => {
            record.verification.executable.iter().cloned().collect()
        }
        Method::RustToolchain => {
            let mut names = Vec::new();
            if image_owned && record.provides.iter().any(|value| value == "cargo") {
                names.push("cargo".to_string());
            }
            if image_owned {
                if let Some(executable) = &record.verification.executable {
                    names.push(executable.clone());
                }
            }
            if record
                .components
                .iter()
                .any(|component| component == "rust-analyzer")
            {
                names.push("rust-analyzer".to_string());
            }
            names.dedup();
            names
        }
        _ => Vec::new(),
    }
}

fn configured_executable_path(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    executable: &str,
    image_owned: bool,
) -> Result<PathBuf> {
    if !executable_binding_names(record, image_owned)
        .iter()
        .any(|value| value == executable)
    {
        return Err(DependencyError::new(format!(
            "{}: executable is not provided by the manifest record: {executable}",
            record.id
        )));
    }
    match record.method {
        Method::NpmGlobal => Ok(probe.npm_prefix.join("bin").join(executable)),
        Method::Pipx if image_owned => Ok(probe.npm_prefix.join("bin").join(executable)),
        Method::AptPackage | Method::AptRepository => Ok(probe.apt_bin_dir.join(executable)),
        Method::RustToolchain => Ok(probe.cargo_home()?.join("bin").join(executable)),
        _ => Err(DependencyError::new(format!(
            "{}: executable binding method is unsupported",
            record.id
        ))),
    }
}

#[allow(deprecated)]
fn home_directory() -> Result<PathBuf> {
    let home = env::var_os("HOME")
        .map(PathBuf::from)
        .or_else(env::home_dir)
        .ok_or_else(|| {
            DependencyError::new("home directory unavailable for rust-toolchain executable binding")
        })?;
    if !home.is_absolute() {
        return Err(DependencyError::new(
            "home directory for rust-toolchain executable binding must be absolute",
        ));
    }
    Ok(home)
}

fn normalize_existing_executable(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    executable: &str,
    workspace: &Path,
) -> Result<(PathBuf, PathBuf)> {
    if matches!(record.method, Method::AptPackage | Method::AptRepository) {
        return resolve_apt_executable(probe, record, executable, workspace);
    }
    let lexical = configured_executable_path(probe, record, executable, false)?;
    let resolved = probe.canonicalize(&lexical).map_err(|_| {
        DependencyError::new(format!(
            "{}: executable is missing: {}",
            record.id,
            lexical.display()
        ))
    })?;
    if !probe.is_regular_executable(&resolved) {
        return Err(DependencyError::new(format!(
            "{}: executable is not executable: {}",
            record.id,
            lexical.display()
        )));
    }
    let root = match record.method {
        Method::NpmGlobal => probe.canonicalize(&probe.npm_prefix)?,
        Method::Pipx => probe.canonicalize(&probe.npm_prefix.join("bin"))?,
        Method::RustToolchain => probe.canonicalize(&probe.cargo_home()?)?,
        _ => {
            return Err(DependencyError::new(format!(
                "{}: executable binding method is unsupported",
                record.id
            )))
        }
    };
    if !resolved.starts_with(&root) {
        return Err(DependencyError::new(format!(
            "{}: executable escapes its method-owned root: {}",
            record.id,
            resolved.display()
        )));
    }
    Ok((resolved.clone(), resolved))
}

fn resolve_apt_executable(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    executable: &str,
    workspace: &Path,
) -> Result<(PathBuf, PathBuf)> {
    let lexical = configured_executable_path(probe, record, executable, false)?;
    let dpkg_query = probe
        .dpkg_query
        .to_str()
        .ok_or_else(|| DependencyError::new("dpkg-query executable path is not valid Unicode"))?;
    let mut owned = BTreeSet::new();
    for owner in &record.executable_owner_packages {
        let output = run_command(
            probe,
            &[dpkg_query, "--listfiles", owner],
            workspace,
            None,
            "verify-apt-executable-owner",
            &record.id,
        )?;
        owned.extend(parse_dpkg_owned_paths(&output.stdout, &record.id)?);
    }
    if owned.is_empty() {
        return Err(DependencyError::new(format!(
            "{}: executable ownership union is empty",
            record.id
        )));
    }
    let lexical_text = lexical.to_string_lossy().to_string();
    if !owned.contains(&lexical_text) {
        return Err(DependencyError::new(format!(
            "{}: lexical executable is not owned by declared packages: {lexical_text}",
            record.id
        )));
    }
    let resolved = probe.canonicalize(&lexical).map_err(|_| {
        DependencyError::new(format!(
            "{}: lexical executable target is missing: {}",
            record.id,
            lexical.display()
        ))
    })?;
    let resolved_text = resolved.to_string_lossy().to_string();
    if !owned.contains(&resolved_text) {
        return Err(DependencyError::new(format!(
            "{}: resolved executable is not owned by declared packages: {resolved_text}",
            record.id
        )));
    }
    if !probe.is_regular_executable(&resolved) {
        return Err(DependencyError::new(format!(
            "{}: resolved executable is not a regular executable: {}",
            record.id,
            resolved.display()
        )));
    }
    Ok((lexical, resolved))
}

fn parse_dpkg_owned_paths(output: &str, record_id: &str) -> Result<BTreeSet<String>> {
    let mut paths = BTreeSet::new();
    for line in output.lines() {
        if line.is_empty()
            || line.contains('\0')
            || line.starts_with("//")
            || !line.starts_with('/')
            || posix_normalize(line) != line
        {
            return Err(DependencyError::new(format!(
                "{record_id}: dpkg ownership output contains an unsafe path"
            )));
        }
        paths.insert(line.to_string());
    }
    if paths.is_empty() {
        return Err(DependencyError::new(format!(
            "{record_id}: dpkg ownership listing is empty"
        )));
    }
    Ok(paths)
}

fn run_command(
    probe: &ProbeEnvironment,
    argv: &[&str],
    workspace: &Path,
    path_override: Option<&str>,
    operation: &str,
    record_id: &str,
) -> Result<CommandOutput> {
    if argv.is_empty()
        || argv
            .iter()
            .any(|argument| argument.is_empty() || has_control(argument))
    {
        return Err(DependencyError::new(
            "command argv contains an empty or control-character token",
        ));
    }
    let command = Path::new(argv[0])
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or_default();
    if ["bash", "dash", "fish", "ksh", "sh", "tcsh", "zsh", "eval"].contains(&command) {
        return Err(DependencyError::new(format!(
            "{record_id}: shell execution is forbidden in {operation}"
        )));
    }
    probe.execute(&CommandInvocation {
        argv: argv.iter().map(|argument| argument.to_string()).collect(),
        workspace: workspace.to_path_buf(),
        path: path_override.map(str::to_string),
        cargo_home: None,
        clear_rustup_overrides: false,
        environment: BTreeMap::new(),
        clear_environment: false,
        privileged: false,
        capture: true,
        operation: operation.to_string(),
        record_id: record_id.to_string(),
    })
}

fn command_output(output: Output, record_id: &str, operation: &str) -> Result<CommandOutput> {
    let stdout = String::from_utf8(output.stdout).map_err(|error| {
        DependencyError::new(format!(
            "{record_id}: {operation} stdout is not UTF-8: {error}"
        ))
    })?;
    let stderr = String::from_utf8(output.stderr).map_err(|error| {
        DependencyError::new(format!(
            "{record_id}: {operation} stderr is not UTF-8: {error}"
        ))
    })?;
    if !output.status.success() {
        return Err(DependencyError::new(format!(
            "{record_id}: {operation} command failed with {}: {}",
            output.status,
            stderr.trim()
        )));
    }
    Ok(CommandOutput {
        stdout,
        stderr,
        #[cfg(all(test, unix))]
        success: true,
    })
}

#[derive(Debug, Clone)]
struct CommandOutput {
    stdout: String,
    stderr: String,
    #[cfg(all(test, unix))]
    success: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum CommandCapability {
    Argv,
    ShellEvaluation,
    DynamicInterpreter,
    PackageInstall,
    NetworkFetch,
    PrivilegeEscalation,
    ReadOnlyQuery,
    ExecutableVerification,
    Unknown,
}

impl CommandCapability {
    fn as_str(self) -> &'static str {
        match self {
            Self::Argv => "argv",
            Self::ShellEvaluation => "shell-evaluation",
            Self::DynamicInterpreter => "dynamic-interpreter",
            Self::PackageInstall => "package-install",
            Self::NetworkFetch => "network-fetch",
            Self::PrivilegeEscalation => "privilege-escalation",
            Self::ReadOnlyQuery => "read-only-query",
            Self::ExecutableVerification => "executable-verification",
            Self::Unknown => "unknown",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CommandInvocation {
    argv: Vec<String>,
    workspace: PathBuf,
    path: Option<String>,
    cargo_home: Option<String>,
    clear_rustup_overrides: bool,
    environment: BTreeMap<String, String>,
    clear_environment: bool,
    privileged: bool,
    capture: bool,
    operation: String,
    record_id: String,
}

struct DependencyCommandContext<'a> {
    workspace: &'a Path,
    method: Option<Method>,
    variables: &'a BTreeMap<String, String>,
    privileged: bool,
    capture: bool,
    clear_environment: bool,
    record_id: &'a str,
    operation: &'a str,
}

#[cfg(all(test, unix))]
#[derive(Debug, Default)]
struct FakeCommandRunner {
    responses: std::cell::RefCell<BTreeMap<Vec<String>, VecDeque<CommandOutput>>>,
    program_responses: std::cell::RefCell<BTreeMap<String, VecDeque<CommandOutput>>>,
    downloads: std::cell::RefCell<VecDeque<Vec<u8>>>,
    invocations: std::cell::RefCell<Vec<CommandInvocation>>,
}

#[cfg(all(test, unix))]
impl FakeCommandRunner {
    fn with_responses(responses: impl IntoIterator<Item = (Vec<String>, CommandOutput)>) -> Self {
        let mut response_map = BTreeMap::<Vec<String>, VecDeque<CommandOutput>>::new();
        for (argv, output) in responses {
            response_map.entry(argv).or_default().push_back(output);
        }
        Self {
            responses: std::cell::RefCell::new(response_map),
            program_responses: std::cell::RefCell::new(BTreeMap::new()),
            downloads: std::cell::RefCell::new(VecDeque::new()),
            invocations: std::cell::RefCell::new(Vec::new()),
        }
    }

    fn with_program_responses(
        responses: impl IntoIterator<Item = (String, CommandOutput)>,
        downloads: impl IntoIterator<Item = Vec<u8>>,
    ) -> Self {
        let mut response_map = BTreeMap::<String, VecDeque<CommandOutput>>::new();
        for (program, output) in responses {
            response_map.entry(program).or_default().push_back(output);
        }
        Self {
            responses: std::cell::RefCell::new(BTreeMap::new()),
            program_responses: std::cell::RefCell::new(response_map),
            downloads: std::cell::RefCell::new(downloads.into_iter().collect()),
            invocations: std::cell::RefCell::new(Vec::new()),
        }
    }
}

enum CommandRunner {
    System,
    #[cfg(all(test, unix))]
    Fake(FakeCommandRunner),
}

struct ProbeEnvironment {
    npm_prefix: PathBuf,
    npm_system_path: String,
    npm_trusted_dirs: Vec<PathBuf>,
    npm_env_launcher: PathBuf,
    apt_bin_dir: PathBuf,
    dpkg_query: PathBuf,
    home: Option<PathBuf>,
    cargo_home: Option<PathBuf>,
    inherited_path: Option<String>,
    filesystem_roots: Vec<(PathBuf, PathBuf)>,
    command_runner: CommandRunner,
}

impl ProbeEnvironment {
    fn system() -> Self {
        Self {
            npm_prefix: PathBuf::from(NPM_PREFIX),
            npm_system_path: NPM_SYSTEM_PATH.to_string(),
            npm_trusted_dirs: NPM_TRUSTED_DIRS.iter().map(PathBuf::from).collect(),
            npm_env_launcher: PathBuf::from("/usr/bin/env"),
            apt_bin_dir: PathBuf::from("/usr/bin"),
            dpkg_query: PathBuf::from("/usr/bin/dpkg-query"),
            home: None,
            cargo_home: None,
            inherited_path: None,
            filesystem_roots: Vec::new(),
            command_runner: CommandRunner::System,
        }
    }

    fn home_directory(&self) -> Result<PathBuf> {
        self.home.clone().map_or_else(home_directory, Ok)
    }

    fn cargo_home(&self) -> Result<PathBuf> {
        let path = if let Some(path) = &self.cargo_home {
            path.clone()
        } else {
            env::var_os("CARGO_HOME")
                .map(PathBuf::from)
                .unwrap_or(self.home_directory()?.join(".cargo"))
        };
        let path_text = path.to_string_lossy();
        if !path.is_absolute() || posix_normalize(path_text.as_ref()) != path_text.as_ref() {
            return Err(DependencyError::new(
                "CARGO_HOME must be an absolute normalized path",
            ));
        }
        Ok(path)
    }

    fn inherited_path(&self) -> String {
        self.inherited_path
            .clone()
            .or_else(|| env::var("PATH").ok())
            .unwrap_or_default()
    }

    fn filesystem_path(&self, logical: &Path) -> PathBuf {
        self.filesystem_roots
            .iter()
            .filter_map(|(logical_root, physical_root)| {
                logical
                    .strip_prefix(logical_root)
                    .ok()
                    .map(|relative| (logical_root.components().count(), physical_root, relative))
            })
            .max_by_key(|(length, _, _)| *length)
            .map(|(_, physical_root, relative)| physical_root.join(relative))
            .unwrap_or_else(|| logical.to_path_buf())
    }

    fn logical_path(&self, physical: &Path) -> PathBuf {
        self.filesystem_roots
            .iter()
            .filter_map(|(logical_root, physical_root)| {
                physical
                    .strip_prefix(physical_root)
                    .ok()
                    .map(|relative| (physical_root.components().count(), logical_root, relative))
            })
            .max_by_key(|(length, _, _)| *length)
            .map(|(_, logical_root, relative)| logical_root.join(relative))
            .unwrap_or_else(|| physical.to_path_buf())
    }

    fn canonicalize(&self, path: &Path) -> Result<PathBuf> {
        let physical = self.filesystem_path(path);
        let canonical = fs::canonicalize(&physical).map_err(|error| {
            DependencyError::new(format!("cannot resolve {}: {error}", path.display()))
        })?;
        Ok(self.logical_path(&canonical))
    }

    fn is_regular_executable(&self, path: &Path) -> bool {
        let physical = self.filesystem_path(path);
        let Ok(metadata) = fs::metadata(&physical) else {
            return false;
        };
        if !metadata.is_file() {
            return false;
        }
        #[cfg(unix)]
        {
            use cap_fs_ext::{AccessType, DirExt};
            use cap_primitives::fs::AccessModes;

            let Ok(relative) = physical.strip_prefix("/") else {
                return false;
            };
            let Ok(root) =
                cap_std::fs::Dir::open_ambient_dir(Path::new("/"), cap_std::ambient_authority())
            else {
                return false;
            };
            root.access(
                relative,
                AccessType::Access(AccessModes {
                    readable: false,
                    writable: false,
                    executable: true,
                }),
            )
            .is_ok()
        }
        #[cfg(windows)]
        {
            // Python's Windows os.access(X_OK) follows file existence rather
            // than an executable-mode or filename-suffix convention.
            true
        }
        #[cfg(not(any(unix, windows)))]
        {
            false
        }
    }

    fn execute(&self, invocation: &CommandInvocation) -> Result<CommandOutput> {
        match &self.command_runner {
            CommandRunner::System => {
                let (program, arguments) = if invocation.privileged && !current_user_is_root() {
                    if !command_exists("sudo") {
                        return Err(DependencyError::new(
                            "privileged dependency action requires root or sudo",
                        ));
                    }
                    let mut arguments = vec![invocation.argv[0].clone()];
                    arguments.extend(invocation.argv.iter().skip(1).cloned());
                    ("sudo", arguments)
                } else {
                    (
                        invocation.argv[0].as_str(),
                        invocation.argv.iter().skip(1).cloned().collect(),
                    )
                };
                let mut process = Command::new(program);
                process.args(&arguments).current_dir(&invocation.workspace);
                if invocation.clear_environment {
                    process.env_clear();
                }
                process.envs(&invocation.environment);
                if let Some(path) = &invocation.path {
                    process.env("PATH", path);
                }
                if let Some(cargo_home) = &invocation.cargo_home {
                    process.env("CARGO_HOME", cargo_home);
                }
                if invocation.clear_rustup_overrides {
                    process.env_remove("RUSTUP_TOOLCHAIN");
                    process.env_remove("ELAN_TOOLCHAIN");
                }
                if !invocation.capture {
                    let status = process.status().map_err(|error| {
                        DependencyError::new(format!(
                            "{}: {} command failed to start: {error}",
                            invocation.record_id, invocation.operation
                        ))
                    })?;
                    if !status.success() {
                        return Err(DependencyError::new(format!(
                            "{}: {} command failed with {status}",
                            invocation.record_id, invocation.operation
                        )));
                    }
                    return Ok(CommandOutput {
                        stdout: String::new(),
                        stderr: String::new(),
                        #[cfg(all(test, unix))]
                        success: true,
                    });
                }
                let output = process.output().map_err(|error| {
                    DependencyError::new(format!(
                        "{}: {} command failed to start: {error}",
                        invocation.record_id, invocation.operation
                    ))
                })?;
                command_output(output, &invocation.record_id, &invocation.operation)
            }
            #[cfg(all(test, unix))]
            CommandRunner::Fake(runner) => {
                runner.invocations.borrow_mut().push(invocation.clone());
                let program = Path::new(&invocation.argv[0])
                    .file_name()
                    .and_then(|value| value.to_str())
                    .unwrap_or_default();
                if program == "curl" {
                    if let Some(bytes) = runner.downloads.borrow_mut().pop_front() {
                        let output_path = invocation
                            .argv
                            .windows(2)
                            .find(|pair| pair[0] == "--output")
                            .map(|pair| PathBuf::from(&pair[1]))
                            .ok_or_else(|| {
                                DependencyError::new(format!(
                                    "{}: curl fixture has no output path",
                                    invocation.record_id
                                ))
                            })?;
                        fs::write(&output_path, bytes).map_err(|error| {
                            DependencyError::new(format!(
                                "{}: curl fixture could not write output: {error}",
                                invocation.record_id
                            ))
                        })?;
                    }
                }
                let output = runner
                    .responses
                    .borrow_mut()
                    .get_mut(&invocation.argv)
                    .and_then(VecDeque::pop_front)
                    .or_else(|| {
                        runner
                            .program_responses
                            .borrow_mut()
                            .get_mut(program)
                            .and_then(VecDeque::pop_front)
                    })
                    .ok_or_else(|| {
                        DependencyError::new(format!(
                            "{}: unexpected test provider command for {}",
                            invocation.record_id, invocation.operation
                        ))
                    })?;
                if !output.success {
                    return Err(DependencyError::new(format!(
                        "{}: {} command failed: {}",
                        invocation.record_id,
                        invocation.operation,
                        output.stderr.trim()
                    )));
                }
                Ok(output)
            }
        }
    }
}

fn require_output(output: &CommandOutput, token: &str, record_id: &str) -> Result<()> {
    if !format!("{}\n{}", output.stdout, output.stderr).contains(token) {
        return Err(DependencyError::new(format!(
            "{record_id}: verification output lacks required token {token:?}"
        )));
    }
    Ok(())
}

fn verification_output(output: &CommandOutput, record_id: &str) -> Result<String> {
    let value = format!("{}\n{}", output.stdout, output.stderr);
    let value = value.trim();
    if value.is_empty() {
        return Err(DependencyError::new(format!(
            "{record_id}: executable verification output is empty"
        )));
    }
    Ok(value.to_string())
}

fn reject_known_network_or_shell_probe(
    record: &DependencyRecord,
    executable: &str,
    args: &[String],
) -> Result<()> {
    let name = Path::new(executable)
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or_default();
    if ["bash", "dash", "fish", "ksh", "sh", "tcsh", "zsh", "eval"].contains(&name) {
        return Err(DependencyError::new(format!(
            "{}: shell execution is forbidden in executable verification",
            record.id
        )));
    }
    let interpreter_probe = match name {
        "python" | "python3" | "pypy" | "perl" | "ruby" => {
            args.len() == 1 && ["--version", "-V", "--help"].contains(&args[0].as_str())
        }
        "node" | "nodejs" => {
            args.len() == 1 && ["--version", "-v", "--help"].contains(&args[0].as_str())
        }
        _ => true,
    };
    if !interpreter_probe {
        return Err(DependencyError::new(format!(
            "{}: declared verification command is not a fixed executable probe",
            record.id
        )));
    }
    if name == "npm"
        && !(args.len() == 1 && args[0] == "--version")
        && !(args.first().is_some_and(|value| value == "ls")
            && args.get(1).is_some_and(|value| value == "--global")
            && args.iter().any(|value| value == "--json")
            && args.iter().any(|value| value == "--depth=0"))
    {
        return Err(DependencyError::new(format!(
            "{}: declared npm verification command is not read-only",
            record.id
        )));
    }
    if name == "rustup"
        && !((args.len() == 3 && args[0] == "show" && args[1] == "active-toolchain")
            || (args.len() == 2 && args[0] == "toolchain" && args[1] == "list")
            || (args.len() >= 2 && args[0] == "component" && args[1] == "list")
            || (args.first().is_some_and(|value| value == "run")
                && args.len() == 4
                && args.last().is_some_and(|value| value == "--version")))
    {
        return Err(DependencyError::new(format!(
            "{}: declared rustup verification command is not read-only",
            record.id
        )));
    }
    if ["curl", "wget", "aria2c"].contains(&name)
        && !(args.len() == 1 && ["--version", "-V", "--help"].contains(&args[0].as_str()))
    {
        return Err(DependencyError::new(format!(
            "{}: declared network utility probe is not read-only",
            record.id
        )));
    }
    if [
        "apt",
        "apt-get",
        "aptitude",
        "pip",
        "cargo",
        "playwright",
        "install",
        "rm",
        "sudo",
        "doas",
        "su",
        "runuser",
        "timeout",
        "nice",
        "stdbuf",
        "xargs",
        "find",
        "command",
    ]
    .contains(&name)
        || (name == "pipx" && !(args.len() >= 4 && args[0] == "runpip" && args[2] == "show"))
        || (name == "git"
            && !((args.len() == 1 && args[0] == "--version")
                || (args.len() == 5
                    && args[0] == "-C"
                    && args[2] == "rev-parse"
                    && args[3] == "--verify"
                    && args[4] == "HEAD")))
        || (name == "gpg"
            && !(args.len() >= 2 && args[0] == "--show-keys" && args[1] == "--with-colons"))
    {
        return Err(DependencyError::new(format!(
            "{}: declared verification command is not read-only",
            record.id
        )));
    }
    Ok(())
}

fn verify_absolute_executable(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    workspace: &Path,
) -> Result<String> {
    let spec = &record.verification;
    let path = spec.path.as_deref().ok_or_else(|| {
        DependencyError::new(format!("{}: executable path is missing", record.id))
    })?;
    let output_contains = spec.output_contains.as_deref().ok_or_else(|| {
        DependencyError::new(format!(
            "{}: executable output contract is missing",
            record.id
        ))
    })?;
    let executable = Path::new(path);
    if !probe.is_regular_executable(executable) {
        return Err(DependencyError::new(format!(
            "{}: executable is missing or not executable: {path}",
            record.id
        )));
    }
    reject_known_network_or_shell_probe(record, path, &spec.args)?;
    let argv = std::iter::once(path)
        .chain(spec.args.iter().map(String::as_str))
        .collect::<Vec<_>>();
    let output = run_command(
        probe,
        &argv,
        workspace,
        None,
        "verify-declared-executable",
        &record.id,
    )?;
    require_output(&output, output_contains, &record.id)?;
    verification_output(&output, &record.id)
}

fn apt_package_version(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    expected_resolved_version: Option<&str>,
    workspace: &Path,
    verify_executable: bool,
) -> Result<String> {
    let dpkg_query = probe
        .dpkg_query
        .to_str()
        .ok_or_else(|| DependencyError::new("dpkg-query executable path is not valid Unicode"))?;
    let output = run_command(
        probe,
        &[
            dpkg_query,
            "--show",
            "--showformat=${Status}\\t${Version}\\t${Package}\\n",
            &record.package,
        ],
        workspace,
        None,
        "verify-apt-package",
        &record.id,
    )?;
    let fields = output.stdout.trim().split('\t').collect::<Vec<_>>();
    let observed_package = fields
        .get(2)
        .copied()
        .unwrap_or_default()
        .split(':')
        .next()
        .unwrap_or_default();
    let observed_version = fields.get(1).copied().unwrap_or_default();
    if fields.len() != 3
        || fields[0] != "install ok installed"
        || observed_package != record.package
        || record
            .version
            .as_deref()
            .is_some_and(|version| version != observed_version)
        || expected_resolved_version.is_some_and(|version| version != observed_version)
    {
        return Err(DependencyError::new(format!(
            "{}: dpkg package/version/owned state mismatch",
            record.id
        )));
    }
    if verify_executable {
        if let (Some(executable), Some(output_contains)) = (
            &record.verification.executable,
            &record.verification.output_contains,
        ) {
            reject_known_network_or_shell_probe(record, executable, &record.verification.args)?;
            let (_lexical, resolved) =
                resolve_apt_executable(probe, record, executable, workspace)?;
            let argv = std::iter::once(resolved.to_string_lossy().to_string())
                .chain(record.verification.args.iter().cloned())
                .collect::<Vec<_>>();
            let argv_refs = argv.iter().map(String::as_str).collect::<Vec<_>>();
            let output = run_command(
                probe,
                &argv_refs,
                workspace,
                None,
                "verify-declared-executable",
                &record.id,
            )?;
            require_output(&output, output_contains, &record.id)?;
        }
    }
    Ok(observed_version.to_string())
}

fn resolve_npm_toolchain(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    workspace: &Path,
) -> Result<(PathBuf, String)> {
    if !probe.is_regular_executable(&probe.npm_env_launcher) {
        return Err(DependencyError::new(format!(
            "npm-global requires executable launcher: {}",
            probe.npm_env_launcher.display()
        )));
    }
    let workspace =
        fs::canonicalize(workspace).map_err(|error| DependencyError::new(error.to_string()))?;
    for executable in ["node", "npm"] {
        let mut selected = None;
        for directory in &probe.npm_trusted_dirs {
            let candidate = directory.join(executable);
            if probe.is_regular_executable(&candidate) {
                selected = Some(candidate);
                break;
            }
        }
        let candidate = selected.ok_or_else(|| {
            DependencyError::new(format!(
                "npm-global requires a trusted {executable} executable"
            ))
        })?;
        let resolved = probe.canonicalize(&candidate).map_err(|error| {
            DependencyError::new(format!(
                "npm-global {executable} executable cannot be resolved: {error}"
            ))
        })?;
        if resolved.starts_with(&workspace) {
            return Err(DependencyError::new(format!(
                "npm-global {executable} executable is inside workspace: {}",
                candidate.display()
            )));
        }
        let parent = candidate
            .parent()
            .and_then(Path::to_str)
            .unwrap_or_default();
        if !probe
            .npm_trusted_dirs
            .iter()
            .any(|directory| directory.to_str() == Some(parent))
        {
            return Err(DependencyError::new(format!(
                "npm-global {executable} executable is outside trusted Node/system directories"
            )));
        }
        let allowed_root = if Path::new(parent).starts_with(&probe.npm_prefix) {
            probe.npm_prefix.clone()
        } else {
            PathBuf::from("/usr")
        };
        let allowed_root = probe.canonicalize(&allowed_root)?;
        if !resolved.starts_with(&allowed_root) {
            return Err(DependencyError::new(format!(
                "npm-global {executable} resolved path escapes trusted system root: {}",
                resolved.display()
            )));
        }
    }
    let npm = probe
        .npm_trusted_dirs
        .iter()
        .map(|directory| directory.join("npm"))
        .find(|candidate| probe.is_regular_executable(candidate))
        .ok_or_else(|| {
            DependencyError::new(format!("{}: npm executable is unavailable", record.id))
        })?;
    Ok((npm, probe.npm_system_path.clone()))
}

fn verify_npm_package(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    workspace: &Path,
) -> Result<()> {
    let version = record
        .version
        .as_deref()
        .ok_or_else(|| DependencyError::new(format!("{}: npm version is required", record.id)))?;
    let (npm, trusted_path) = resolve_npm_toolchain(probe, record, workspace)?;
    let argv = [
        npm.to_string_lossy().to_string(),
        "ls".to_string(),
        "--global".to_string(),
        "--prefix".to_string(),
        probe.npm_prefix.to_string_lossy().to_string(),
        "--json".to_string(),
        "--depth=0".to_string(),
        record.package.clone(),
    ];
    let argv_refs = argv.iter().map(String::as_str).collect::<Vec<_>>();
    let output = run_command(
        probe,
        &argv_refs,
        workspace,
        Some(&trusted_path),
        "verify-npm-package",
        &record.id,
    )?;
    let value: Value = serde_json::from_str(&output.stdout).map_err(|_| {
        DependencyError::new(format!("{}: npm global JSON is missing package", record.id))
    })?;
    let observed = value
        .get("dependencies")
        .and_then(|value| value.get(&record.package))
        .and_then(|value| value.get("version"))
        .and_then(Value::as_str)
        .ok_or_else(|| {
            DependencyError::new(format!("{}: npm global JSON is missing package", record.id))
        })?;
    if observed != version {
        return Err(DependencyError::new(format!(
            "{}: npm version mismatch {observed:?}!={version:?}",
            record.id
        )));
    }
    let executable = record.verification.executable.as_deref().ok_or_else(|| {
        DependencyError::new(format!("{}: npm verifier executable is missing", record.id))
    })?;
    let output_contains = record
        .verification
        .output_contains
        .as_deref()
        .ok_or_else(|| {
            DependencyError::new(format!(
                "{}: npm verifier output contract is missing",
                record.id
            ))
        })?;
    let (_, resolved) = normalize_existing_executable(probe, record, executable, workspace)?;
    reject_known_network_or_shell_probe(record, executable, &record.verification.args)?;
    let argv = std::iter::once(resolved.to_string_lossy().to_string())
        .chain(record.verification.args.iter().cloned())
        .collect::<Vec<_>>();
    let argv_refs = argv.iter().map(String::as_str).collect::<Vec<_>>();
    let output = run_command(
        probe,
        &argv_refs,
        workspace,
        Some(&trusted_path),
        "verify-declared-executable",
        &record.id,
    )?;
    require_output(&output, output_contains, &record.id)
}

fn rust_path_environment(probe: &ProbeEnvironment) -> Result<(String, String)> {
    let home = probe.home_directory()?;
    let cargo_home = probe.cargo_home()?;
    let inherited = probe.inherited_path();
    let mut entries = vec![
        cargo_home.join("bin").to_string_lossy().to_string(),
        home.join(".elan/bin").to_string_lossy().to_string(),
        home.join(".local/bin").to_string_lossy().to_string(),
    ];
    entries.extend(
        inherited
            .split(':')
            .filter(|part| !part.is_empty())
            .map(str::to_string),
    );
    Ok((entries.join(":"), cargo_home.to_string_lossy().to_string()))
}

fn verify_rust_toolchain(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    workspace: &Path,
) -> Result<()> {
    let version = record.version.as_deref().ok_or_else(|| {
        DependencyError::new(format!("{}: Rust toolchain version is missing", record.id))
    })?;
    let (path, cargo_home) = rust_path_environment(probe)?;
    let run = |argv: &[&str], operation: &str| {
        run_rust_command(
            probe,
            argv,
            workspace,
            &path,
            &cargo_home,
            operation,
            &record.id,
        )
    };
    let active = run(
        &["rustup", "show", "active-toolchain"],
        "verify-rust-active",
    )?;
    if !active.stdout.trim().starts_with(version) {
        return Err(DependencyError::new(format!(
            "{}: Rust default toolchain is stale",
            record.id
        )));
    }
    let installed = run(&["rustup", "toolchain", "list"], "verify-rust-installed")?;
    if !installed
        .stdout
        .lines()
        .filter(|line| !line.trim().is_empty())
        .any(|line| {
            let installed = line.split_whitespace().next().unwrap_or_default();
            installed == version || installed.starts_with(&format!("{version}-"))
        })
    {
        return Err(DependencyError::new(format!(
            "{}: Rust toolchain is not installed",
            record.id
        )));
    }
    let components = run(
        &["rustup", "component", "list", "--toolchain", version],
        "verify-rust-components",
    )?
    .stdout;
    for component in &record.components {
        if !components
            .lines()
            .any(|line| line.starts_with(component) && line.contains("(installed)"))
        {
            return Err(DependencyError::new(format!(
                "{}: Rust component is stale: {component}",
                record.id
            )));
        }
    }
    let mut tools = vec!["rustc", "cargo"];
    for component in &record.components {
        match component.as_str() {
            "rustfmt" => tools.push("rustfmt"),
            "clippy" => tools.push("clippy-driver"),
            "rust-analyzer" => tools.push("rust-analyzer"),
            _ => {}
        }
    }
    for tool in tools {
        let output = run(
            &["rustup", "run", version, tool, "--version"],
            "verify-rust-tool-version",
        )?;
        if tool == "rust-analyzer" {
            require_output(&output, &format!("rust-analyzer {version}"), &record.id)?;
        }
    }
    Ok(())
}

fn run_rust_command(
    probe: &ProbeEnvironment,
    argv: &[&str],
    workspace: &Path,
    path: &str,
    cargo_home: &str,
    operation: &str,
    record_id: &str,
) -> Result<CommandOutput> {
    if argv.is_empty()
        || argv
            .iter()
            .any(|argument| argument.is_empty() || has_control(argument))
    {
        return Err(DependencyError::new(
            "command argv contains an empty or control-character token",
        ));
    }
    probe.execute(&CommandInvocation {
        argv: argv.iter().map(|argument| argument.to_string()).collect(),
        workspace: workspace.to_path_buf(),
        path: Some(path.to_string()),
        cargo_home: Some(cargo_home.to_string()),
        clear_rustup_overrides: true,
        environment: BTreeMap::new(),
        clear_environment: false,
        privileged: false,
        capture: true,
        operation: operation.to_string(),
        record_id: record_id.to_string(),
    })
}

fn executable_bindings(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    image_owned: bool,
    workspace: &Path,
) -> Result<BTreeMap<String, ExecutableBinding>> {
    let mut bindings = BTreeMap::new();
    for executable in executable_binding_names(record, image_owned) {
        let (lexical, absolute) =
            if matches!(record.method, Method::AptPackage | Method::AptRepository) {
                resolve_apt_executable(probe, record, &executable, workspace)?
            } else {
                normalize_existing_executable(probe, record, &executable, workspace)?
            };
        let output = if record.verification.executable.as_deref() == Some(executable.as_str()) {
            reject_known_network_or_shell_probe(record, &executable, &record.verification.args)?;
            let token = record
                .verification
                .output_contains
                .as_deref()
                .ok_or_else(|| {
                    DependencyError::new(format!(
                        "{}: executable output contract is missing",
                        record.id
                    ))
                })?;
            let argv = std::iter::once(absolute.to_string_lossy().to_string())
                .chain(record.verification.args.iter().cloned())
                .collect::<Vec<_>>();
            let argv_refs = argv.iter().map(String::as_str).collect::<Vec<_>>();
            let output = run_command(
                probe,
                &argv_refs,
                workspace,
                Some(&probe.npm_system_path),
                "verify-declared-executable",
                &record.id,
            )?;
            require_output(&output, token, &record.id)?;
            verification_output(&output, &record.id)?
        } else {
            format!(
                "{STRUCTURAL_BINDING_OUTPUT_PREFIX}:{}:{executable}",
                record.method.as_str()
            )
        };
        bindings.insert(
            executable.clone(),
            ExecutableBinding {
                provided: executable.clone(),
                lexical_path: lexical.to_string_lossy().to_string(),
                absolute_path: absolute.to_string_lossy().to_string(),
                verification_output: output,
            },
        );
    }
    Ok(bindings)
}

fn verify_installed_receipt(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    payload: &Value,
    bindings: &BTreeMap<String, ExecutableBinding>,
    workspace: &Path,
) -> Result<Option<String>> {
    let expected_resolved_version =
        if record.method == Method::AptPackage && record.version.is_none() {
            let value = payload
                .get("resolved_package_version")
                .and_then(Value::as_str)
                .filter(|value| matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", value))
                .ok_or_else(|| {
                    DependencyError::new(format!(
                        "{}: resolved dpkg package version is missing or invalid",
                        record.id
                    ))
                })?;
            Some(value.to_string())
        } else {
            None
        };
    if expected_resolved_version.is_some() {
        apt_package_version(
            probe,
            record,
            expected_resolved_version.as_deref(),
            workspace,
            false,
        )?;
    }
    for name in executable_binding_names(record, true) {
        let binding = bindings.get(&name).ok_or_else(|| {
            DependencyError::new(format!(
                "{}: installed executable binding is missing: {name}",
                record.id
            ))
        })?;
        let expected = configured_executable_path(probe, record, &name, true)?;
        let expected = expected.to_string_lossy().to_string();
        if binding.lexical_path != expected || binding.absolute_path != expected {
            return Err(DependencyError::new(format!(
                "{}: installed executable binding is stale: {name}",
                record.id
            )));
        }
        if !probe.is_regular_executable(Path::new(&expected)) {
            return Err(DependencyError::new(format!(
                "{}: installed executable is missing or not executable: {name}",
                record.id
            )));
        }
    }
    if record.verification.kind == VerificationKind::AbsoluteExecutable {
        return verify_absolute_executable(probe, record, workspace).map(Some);
    }
    if record.verification.kind == VerificationKind::CargoBinary {
        return Err(DependencyError::new(format!("{}: cargo-source-build receipt verification is not supported by the native executable resolver", record.id)));
    }
    let Some(executable) = record.verification.executable.as_deref() else {
        return Ok(None);
    };
    let binding = bindings.get(executable).ok_or_else(|| {
        DependencyError::new(format!(
            "{}: installed executable binding is missing",
            record.id
        ))
    })?;
    let output = run_command(
        probe,
        &std::iter::once(binding.absolute_path.as_str())
            .chain(record.verification.args.iter().map(String::as_str))
            .collect::<Vec<_>>(),
        workspace,
        Some(&probe.npm_system_path),
        "verify-declared-executable",
        &record.id,
    )?;
    if let Some(token) = &record.verification.output_contains {
        require_output(&output, token, &record.id)?;
    }
    verification_output(&output, &record.id).map(Some)
}

fn verify_pass_receipt(
    probe: &ProbeEnvironment,
    record: &DependencyRecord,
    expected_bindings: &BTreeMap<String, ExecutableBinding>,
    executable: &str,
    expected_resolved_version: Option<&str>,
    workspace: &Path,
) -> Result<()> {
    match record.method {
        Method::NpmGlobal => verify_npm_package(probe, record, workspace)?,
        Method::AptPackage => {
            apt_package_version(probe, record, expected_resolved_version, workspace, true)?;
        }
        Method::RustToolchain => verify_rust_toolchain(probe, record, workspace)?,
        Method::ReleaseAsset => {
            verify_absolute_executable(probe, record, workspace)?;
            return Ok(());
        }
        _ => {
            return Err(DependencyError::new(format!(
                "{}: native read-only verification is not implemented for {}",
                record.id,
                record.method.as_str()
            )))
        }
    }
    let live_bindings = executable_bindings(probe, record, false, workspace)?;
    let live = live_bindings.get(executable).ok_or_else(|| {
        DependencyError::new(format!(
            "{}: executable binding is unavailable: {executable}",
            record.id
        ))
    })?;
    let expected = expected_bindings.get(executable).ok_or_else(|| {
        DependencyError::new(format!(
            "{}: executable receipt binding is stale",
            record.id
        ))
    })?;
    if live.lexical_path != expected.lexical_path
        || live.provided != expected.provided
        || live.absolute_path != expected.absolute_path
        || live.verification_output != expected.verification_output
    {
        return Err(DependencyError::new(format!(
            "{}: executable receipt path or output drift",
            record.id
        )));
    }
    Ok(())
}

fn repository_package_payload(record: &DependencyRecord) -> Result<Value> {
    let architecture = runtime_architecture()?;
    let (url, checksum) = if !record.repository_package_urls.is_empty() {
        (
            record
                .repository_package_urls
                .iter()
                .find(|(key, _)| key == &architecture)
                .map(|(_, value)| value.clone()),
            record
                .repository_package_sha256s
                .iter()
                .find(|(key, _)| key == &architecture)
                .map(|(_, value)| value.clone()),
        )
    } else {
        (
            record.repository_package_url.clone(),
            record.repository_package_sha256.clone(),
        )
    };
    match (url, checksum) {
        (Some(url), Some(checksum)) => Ok(json!({"url": url, "sha256": checksum})),
        (None, None) => Ok(Value::Null),
        _ => Err(DependencyError::new(format!(
            "{}: repository package URL/SHA pair is incomplete",
            record.id
        ))),
    }
}

fn repository_packages_payload(record: &DependencyRecord) -> Result<Value> {
    let architecture = runtime_architecture()?;
    let checksum = if !record.repository_packages_sha256s.is_empty() {
        record
            .repository_packages_sha256s
            .iter()
            .find(|(key, _)| key == &architecture)
            .map(|(_, value)| value.clone())
    } else {
        record.repository_packages_sha256.clone()
    };
    let Some(checksum) = checksum else {
        return Ok(Value::Null);
    };
    let suite = record.repository_suite.as_deref().ok_or_else(|| {
        DependencyError::new(format!("{}: repository suite is missing", record.id))
    })?;
    let component = record.repository_components.first().ok_or_else(|| {
        DependencyError::new(format!("{}: repository component is missing", record.id))
    })?;
    let url = format!(
        "{}/dists/{suite}/{component}/binary-{architecture}/Packages",
        record.source.trim_end_matches('/')
    );
    Ok(json!({"url": url, "sha256": checksum}))
}

fn runtime_architecture() -> Result<String> {
    match env::consts::ARCH {
        "x86_64" | "amd64" => Ok("amd64".to_string()),
        "aarch64" | "arm64" => Ok("arm64".to_string()),
        other => Err(DependencyError::new(format!(
            "unsupported target architecture: {other}"
        ))),
    }
}

fn release_asset_architecture() -> String {
    match env::consts::ARCH {
        "amd64" => "x86_64".to_string(),
        "arm64" => "aarch64".to_string(),
        other => other.to_string(),
    }
}

/// Resolve one manifest-declared executable from a matching read-only receipt.
///
/// This validates the complete selected plan and receipt identity before any
/// command is run. It never searches PATH for the requested executable and
/// never installs software, performs provider/network operations, or writes
/// receipts. Live checks are the record-declared verifier and local metadata
/// queries used by the existing read-only owner.
pub fn resolve_verified_executable(
    workspace: &Path,
    receipts: &Path,
    record_id: &str,
    executable: &str,
    manifest: Option<&Path>,
) -> Result<VerifiedExecutable> {
    let probe = ProbeEnvironment::system();
    resolve_verified_executable_with_provider(
        &probe, workspace, receipts, record_id, executable, manifest,
    )
}

// Public resolution delegates here. Tests substitute only the external command
// and fixed-root provider; manifest, receipt, and binding validation stay real.
fn resolve_verified_executable_with_provider(
    probe: &ProbeEnvironment,
    workspace: &Path,
    receipts: &Path,
    record_id: &str,
    executable: &str,
    manifest: Option<&Path>,
) -> Result<VerifiedExecutable> {
    if executable.is_empty()
        || Path::new(executable)
            .file_name()
            .and_then(|value| value.to_str())
            != Some(executable)
        || executable.contains('/')
        || executable.contains('\\')
    {
        return Err(DependencyError::new(format!(
            "requested executable must be one command name: {executable:?}"
        )));
    }
    if !matches(r"^[a-z0-9][a-z0-9._-]*$", record_id) {
        return Err(DependencyError::new(format!(
            "invalid receipt record id: {record_id}"
        )));
    }
    let plan = load_plan(workspace, manifest)?;
    let record = plan.by_id(record_id).ok_or_else(|| {
        DependencyError::new(format!("dependency record is not present: {record_id}"))
    })?;
    if !matches!(
        record.method,
        Method::NpmGlobal | Method::AptPackage | Method::RustToolchain | Method::ReleaseAsset
    ) {
        return Err(DependencyError::new(format!(
            "{}: native read-only verification is not implemented for {}",
            record.id,
            record.method.as_str()
        )));
    }
    if plan.sources.len() != plan.source_roles.len()
        || plan.order.len() != plan.records.len()
        || plan.dependency_providers.len() != plan.records.len()
    {
        return Err(DependencyError::new(
            "dependency plan identity is incomplete",
        ));
    }
    let receipt_path = receipts.join(format!("{record_id}.json"));
    let receipt_bytes = fs::read(&receipt_path).map_err(|_| {
        DependencyError::new(format!("{record_id}: executable receipt is unreadable"))
    })?;
    let payload: Value = serde_json::from_slice(&receipt_bytes).map_err(|_| {
        DependencyError::new(format!("{record_id}: executable receipt is unreadable"))
    })?;
    let payload_object = object(&payload, "executable receipt").map_err(|_| {
        DependencyError::new(format!("{record_id}: executable receipt binding is stale"))
    })?;
    let status = payload_object
        .get("status")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            DependencyError::new(format!("{record_id}: executable receipt binding is stale"))
        })?;
    let image_owned = status == "installed";
    if status != "installed" && status != "pass" {
        return Err(DependencyError::new(format!(
            "{record_id}: executable receipt binding is stale"
        )));
    }
    let release_asset_path = if record.method == Method::ReleaseAsset {
        let path = record.verification.path.as_deref();
        if record.verification.kind != VerificationKind::AbsoluteExecutable
            || path.is_none()
            || path != record.destination.as_deref()
            || Path::new(path.unwrap_or_default())
                .file_name()
                .and_then(|value| value.to_str())
                != Some(executable)
        {
            return Err(DependencyError::new(format!(
                "{record_id}: requested executable does not match its declared absolute path"
            )));
        }
        Some(path.unwrap_or_default().to_string())
    } else {
        let allowed = executable_binding_names(record, image_owned);
        if !allowed.iter().any(|value| value == executable) {
            return Err(DependencyError::new(format!(
                "{record_id}: requested executable is not manifest-provided: {executable}"
            )));
        }
        None
    };
    let raw_bindings = payload_object
        .get("executable_bindings")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            DependencyError::new(format!("{record_id}: executable receipt binding is stale"))
        })?;
    let expected_names = if release_asset_path.is_some() {
        Vec::new()
    } else {
        executable_binding_names(record, image_owned)
    };
    let expected = expected_names.iter().cloned().collect::<BTreeSet<_>>();
    let actual = raw_bindings.keys().cloned().collect::<BTreeSet<_>>();
    if expected != actual {
        return Err(DependencyError::new(format!(
            "{record_id}: executable receipt binding is stale"
        )));
    }
    let mut bindings = BTreeMap::new();
    for name in &expected_names {
        let raw = raw_bindings.get(name).ok_or_else(|| {
            DependencyError::new(format!("{record_id}: executable receipt binding is stale"))
        })?;
        bindings.insert(
            name.clone(),
            ExecutableBinding::from_receipt(raw, name).map_err(|_| {
                DependencyError::new(format!("{record_id}: executable receipt binding is stale"))
            })?,
        );
    }
    let expected_manifest_version = record
        .version
        .as_ref()
        .map(|value| Value::String(value.clone()))
        .unwrap_or(Value::Null);
    let expected_record_fingerprint = record.fingerprint()?;
    let expected_verification = record.verification.payload();
    let expected_repository_packages = repository_packages_payload(record)?;
    let expected_repository_package = repository_package_payload(record)?;
    if payload_object.get("schema").and_then(Value::as_str) != Some(RECEIPT_SCHEMA)
        || payload_object.get("status").and_then(Value::as_str) != Some(status)
        || payload_object.get("record_id").and_then(Value::as_str) != Some(record_id)
        || payload_object.get("manifest_version") != Some(&expected_manifest_version)
        || payload_object
            .get("plan_fingerprint")
            .and_then(Value::as_str)
            != Some(plan.fingerprint.as_str())
        || payload_object
            .get("record_fingerprint")
            .and_then(Value::as_str)
            != Some(expected_record_fingerprint.as_str())
        || payload_object.get("verification") != Some(&expected_verification)
        || payload_object.get("repository_packages") != Some(&expected_repository_packages)
        || payload_object.get("repository_package") != Some(&expected_repository_package)
    {
        return Err(DependencyError::new(format!(
            "{record_id}: executable receipt binding is stale"
        )));
    }
    let manifest_version = record.version.clone().or_else(|| {
        payload_object
            .get("resolved_package_version")
            .and_then(Value::as_str)
            .map(str::to_string)
    });
    let version_valid = manifest_version
        .as_deref()
        .is_some_and(|value| matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", value));
    if record.version.is_none() && !version_valid {
        return Err(DependencyError::new(format!(
            "{record_id}: executable receipt lacks its resolved package version"
        )));
    }
    let manifest_version = manifest_version.expect("validated manifest or resolved version");
    if let Some(path) = release_asset_path {
        let output = verify_absolute_executable(probe, record, workspace)?;
        return Ok(VerifiedExecutable {
            record_id: record.id.clone(),
            manifest_version,
            executable: executable.to_string(),
            absolute_path: PathBuf::from(path),
            record_fingerprint: expected_record_fingerprint,
            plan_fingerprint: plan.fingerprint.clone(),
            verification_output: output,
        });
    }
    if image_owned {
        let output = verify_installed_receipt(probe, record, &payload, &bindings, workspace)?;
        let binding = bindings
            .get(executable)
            .expect("validated requested binding");
        return Ok(VerifiedExecutable {
            record_id: record.id.clone(),
            manifest_version,
            executable: executable.to_string(),
            absolute_path: PathBuf::from(binding.absolute_path.as_str()),
            record_fingerprint: expected_record_fingerprint,
            plan_fingerprint: plan.fingerprint.clone(),
            verification_output: if record.verification.executable.as_deref() == Some(executable) {
                output.unwrap_or_else(|| binding.verification_output.clone())
            } else {
                binding.verification_output.clone()
            },
        });
    }
    verify_pass_receipt(
        probe,
        record,
        &bindings,
        executable,
        record
            .version
            .is_none()
            .then_some(manifest_version.as_str()),
        workspace,
    )?;
    let binding = bindings.get(executable).ok_or_else(|| {
        DependencyError::new(format!(
            "{record_id}: executable binding is unavailable: {executable}"
        ))
    })?;
    Ok(VerifiedExecutable {
        record_id: record.id.clone(),
        manifest_version,
        executable: executable.to_string(),
        absolute_path: PathBuf::from(binding.absolute_path.as_str()),
        record_fingerprint: expected_record_fingerprint,
        plan_fingerprint: plan.fingerprint.clone(),
        verification_output: binding.verification_output.clone(),
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DependencyCommand {
    Validate,
    DryRun,
    Install,
    Boundary,
    ProjectInstall,
    ImageInstall,
    ImageVerify,
}

impl DependencyCommand {
    fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "validate" => Self::Validate,
            "dry-run" => Self::DryRun,
            "install" => Self::Install,
            "boundary" => Self::Boundary,
            "project-install" => Self::ProjectInstall,
            "image-install" => Self::ImageInstall,
            "image-verify" => Self::ImageVerify,
            _ => return None,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DependencyOption {
    Workspace,
    Manifest,
    Receipts,
    FinalBinaryDir,
    Extras,
    Records,
    Format,
}

const DEPENDENCY_OPTIONS: [(&str, DependencyOption); 7] = [
    ("--workspace", DependencyOption::Workspace),
    ("--manifest", DependencyOption::Manifest),
    ("--receipts", DependencyOption::Receipts),
    ("--final-binary-dir", DependencyOption::FinalBinaryDir),
    ("--extras", DependencyOption::Extras),
    ("--records", DependencyOption::Records),
    ("--format", DependencyOption::Format),
];

#[derive(Debug, Clone)]
struct DependencyCliArgs {
    command: DependencyCommand,
    workspace: PathBuf,
    manifest: Option<PathBuf>,
    receipts: Option<PathBuf>,
    final_binary_dir: Option<PathBuf>,
    extras: String,
    records: Option<Vec<String>>,
    format: String,
}

enum ParsedDependencyCli {
    Help,
    Arguments(Box<DependencyCliArgs>),
}

const DEPENDENCY_USAGE: &str = "usage: agent-canon environment-dependencies [-h] [--workspace WORKSPACE] [--manifest MANIFEST] [--receipts RECEIPTS] [--final-binary-dir FINAL_BINARY_DIR] [--extras EXTRAS] [--records RECORDS [RECORDS ...]] [--format {text,json}] {validate,dry-run,install,boundary,project-install,image-install,image-verify}";

fn parse_dependency_option(value: &str) -> std::result::Result<DependencyOption, String> {
    resolve_long_option_prefix(value, &DEPENDENCY_OPTIONS).map_err(|error| match error {
        LongOptionError::Unrecognized => format!("unrecognized arguments: {value}"),
        LongOptionError::Ambiguous(options) => format!(
            "ambiguous option: {value} could match {}",
            options.join(", ")
        ),
    })
}

fn parse_dependency_cli(args: &[String]) -> std::result::Result<ParsedDependencyCli, String> {
    if args.is_empty() {
        return Err("the following arguments are required: command".to_string());
    }
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        return Ok(ParsedDependencyCli::Help);
    }
    let mut parsed = DependencyCliArgs {
        command: DependencyCommand::Validate,
        workspace: PathBuf::from("."),
        manifest: None,
        receipts: None,
        final_binary_dir: None,
        extras: String::new(),
        records: None,
        format: "text".to_string(),
    };
    let mut command = None;
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        let Some(option_token) = token.strip_prefix("--") else {
            if command.is_none() && !token.starts_with('-') {
                command = Some(DependencyCommand::parse(token).ok_or_else(|| {
                    format!(
                        "argument command: invalid choice: {:?} (choose from 'validate', 'dry-run', 'install', 'boundary', 'project-install', 'image-install', 'image-verify')",
                        token
                    )
                })?);
                index += 1;
                continue;
            }
            return Err(format!("unrecognized arguments: {token}"));
        };
        let (option_name, inline_value) = option_token
            .split_once('=')
            .map_or((format!("--{option_token}"), None), |(name, value)| {
                (format!("--{name}"), Some(value.to_string()))
            });
        let option = parse_dependency_option(&option_name)?;
        index += 1;
        if option == DependencyOption::Records {
            let mut group = Vec::new();
            if let Some(value) = inline_value {
                group.push(value);
            } else {
                while index < args.len() && !args[index].starts_with('-') {
                    group.push(args[index].clone());
                    index += 1;
                }
            }
            if group.is_empty() {
                return Err(format!(
                    "argument {option_name}: expected at least one argument"
                ));
            }
            parsed.records.get_or_insert_with(Vec::new).extend(group);
            continue;
        }
        let value = if let Some(value) = inline_value {
            value
        } else {
            let value = args
                .get(index)
                .ok_or_else(|| format!("argument {option_name}: expected one argument"))?
                .clone();
            index += 1;
            value
        };
        match option {
            DependencyOption::Workspace => parsed.workspace = PathBuf::from(value),
            DependencyOption::Manifest => parsed.manifest = Some(PathBuf::from(value)),
            DependencyOption::Receipts => parsed.receipts = Some(PathBuf::from(value)),
            DependencyOption::FinalBinaryDir => {
                parsed.final_binary_dir = Some(PathBuf::from(value))
            }
            DependencyOption::Extras => parsed.extras = value,
            DependencyOption::Format if value == "text" || value == "json" => parsed.format = value,
            DependencyOption::Format => {
                return Err(format!(
                    "argument {option_name}: invalid choice: {:?} (choose from 'text', 'json')",
                    value
                ))
            }
            DependencyOption::Records => unreachable!("records are parsed above"),
        }
    }
    parsed.command =
        command.ok_or_else(|| "the following arguments are required: command".to_string())?;
    Ok(ParsedDependencyCli::Arguments(Box::new(parsed)))
}

fn dependency_cli_help() -> String {
    format!(
        "Typed environment dependency planner and installer.\n\n{DEPENDENCY_USAGE}\n\nValidate, inspect, or install the selected shared-tool dependency plan.\n"
    )
}

fn canonical_python_extra(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut separator = false;
    for character in value.chars() {
        if matches!(character, '-' | '_' | '.') {
            if !separator {
                output.push('-');
            }
            separator = true;
        } else {
            output.push(character.to_ascii_lowercase());
            separator = false;
        }
    }
    output
}

fn parse_python_extras(raw: &str) -> Result<Vec<String>> {
    let mut extras = Vec::new();
    let mut seen = BTreeSet::new();
    for value in raw.split(',') {
        if value.is_empty()
            || value.trim() != value
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || b"._-".contains(&byte))
            || !value.as_bytes()[0].is_ascii_alphanumeric()
        {
            return Err(DependencyError::new(
                "Python extras must be non-empty names without surrounding whitespace",
            ));
        }
        let canonical = canonical_python_extra(value);
        if !seen.insert(canonical) {
            return Err(DependencyError::new(format!(
                "duplicate Python extra: {value}"
            )));
        }
        extras.push(value.to_string());
    }
    Ok(extras)
}

fn validate_project_extras(workspace: &Path, extras: &[String]) -> Result<Vec<String>> {
    let extras = parse_python_extras(&extras.join(","))?;
    let pyproject = workspace.join("pyproject.toml");
    let source = fs::read_to_string(&pyproject).map_err(|_| {
        DependencyError::new(format!(
            "project packaging manifest is missing: {}",
            pyproject.display()
        ))
    })?;
    let document = source.parse::<toml_edit::DocumentMut>().map_err(|_| {
        DependencyError::new(format!(
            "cannot parse project packaging manifest: {}",
            pyproject.display()
        ))
    })?;
    let optional = document
        .get("project")
        .and_then(toml_edit::Item::as_table)
        .and_then(|project| project.get("optional-dependencies"))
        .and_then(toml_edit::Item::as_table)
        .ok_or_else(|| {
            DependencyError::new(format!(
                "project.optional-dependencies is missing: {}",
                pyproject.display()
            ))
        })?;
    let available = optional
        .iter()
        .filter(|(name, _)| {
            !name.is_empty()
                && name
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"._-".contains(&byte))
                && name.as_bytes()[0].is_ascii_alphanumeric()
        })
        .map(|(name, _)| canonical_python_extra(name))
        .collect::<BTreeSet<_>>();
    let missing = extras
        .iter()
        .filter(|extra| !available.contains(&canonical_python_extra(extra)))
        .cloned()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(DependencyError::new(format!(
            "project extras are not declared in pyproject.toml: {}",
            missing.join(", ")
        )));
    }
    Ok(extras)
}

fn select_record_ids(plan: &DependencyPlan, requested: Option<&[String]>) -> Result<Vec<String>> {
    let Some(requested) = requested else {
        return Ok(plan.order.clone());
    };
    if requested.is_empty() {
        return Err(DependencyError::new(
            "--records must select at least one record",
        ));
    }
    let by_id = plan
        .records
        .iter()
        .map(|record| (record.id.as_str(), record))
        .collect::<BTreeMap<_, _>>();
    let mut selected = BTreeSet::new();
    let mut pending = VecDeque::new();
    for raw in requested {
        for value in raw.split(',') {
            let record_id = value.trim();
            if record_id.is_empty() {
                return Err(DependencyError::new(
                    "--records must not contain empty record IDs",
                ));
            }
            if !by_id.contains_key(record_id) {
                return Err(DependencyError::new(format!(
                    "unknown dependency record: {record_id}"
                )));
            }
            if selected.insert(record_id.to_string()) {
                pending.push_back(record_id.to_string());
            }
        }
    }
    while let Some(record_id) = pending.pop_front() {
        if let Some((_, providers)) = plan
            .dependency_providers
            .iter()
            .find(|(candidate, _)| candidate == &record_id)
        {
            for provider in providers {
                if selected.insert(provider.clone()) {
                    pending.push_back(provider.clone());
                }
            }
        }
    }
    Ok(plan
        .order
        .iter()
        .filter(|record_id| selected.contains(*record_id))
        .cloned()
        .collect())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RuntimeIdentity {
    os_id: String,
    version_id: String,
    platform: String,
}

fn read_runtime_identity() -> Result<RuntimeIdentity> {
    let os_release = Path::new("/etc/os-release");
    let text = fs::read_to_string(os_release).map_err(|error| {
        DependencyError::new(format!(
            "runtime identity cannot read {}: {error}",
            os_release.display()
        ))
    })?;
    let mut values = BTreeMap::new();
    for line in text.lines() {
        let Some((name, value)) = line.split_once('=') else {
            continue;
        };
        if name == "ID" || name == "VERSION_ID" {
            values.insert(name, value.trim().trim_matches(['"', '\'']).to_string());
        }
    }
    let os_id = values.get("ID").cloned().unwrap_or_default();
    let version_id = values.get("VERSION_ID").cloned().unwrap_or_default();
    let architecture = match env::consts::ARCH {
        "x86_64" | "amd64" => "amd64",
        "aarch64" | "arm64" => "arm64",
        other => other,
    };
    let platform = format!("linux/{architecture}");
    if os_id.is_empty() || version_id.is_empty() || platform == "linux/" {
        return Err(DependencyError::new(format!(
            "runtime identity is incomplete: ID={os_id:?} VERSION_ID={version_id:?} platform={platform:?}"
        )));
    }
    Ok(RuntimeIdentity {
        os_id,
        version_id,
        platform,
    })
}

fn validate_runtime_identity(plan: &DependencyPlan) -> Result<RuntimeIdentity> {
    let identity = read_runtime_identity()?;
    validate_runtime_identity_for(plan, identity)
}

fn validate_runtime_identity_for(
    plan: &DependencyPlan,
    identity: RuntimeIdentity,
) -> Result<RuntimeIdentity> {
    if identity.os_id != "ubuntu" || !["22.04", "24.04"].contains(&identity.version_id.as_str()) {
        return Err(DependencyError::new(format!(
            "runtime identity requires Ubuntu 22.04 or 24.04: ID={} VERSION_ID={}",
            identity.os_id, identity.version_id
        )));
    }
    if !["linux/amd64", "linux/arm64"].contains(&identity.platform.as_str()) {
        return Err(DependencyError::new(format!(
            "runtime identity requires linux/amd64 or linux/arm64: platform={}",
            identity.platform
        )));
    }
    for record in &plan.records {
        if let Some(platform) = &record.platform {
            if platform != &identity.platform {
                return Err(DependencyError::new(format!(
                    "dependency record {} requires {}, but runtime platform is {}; no compatibility fallback is defined",
                    record.id, platform, identity.platform
                )));
            }
        }
        if !record.platforms.is_empty() && !record.platforms.contains(&identity.platform) {
            return Err(DependencyError::new(format!(
                "dependency record {} does not support {}",
                record.id, identity.platform
            )));
        }
        if matches!(record.method, Method::AptPackage | Method::AptRepository)
            && record.source.starts_with("ubuntu:")
            && record.source != format!("ubuntu:{}", identity.version_id)
        {
            return Err(DependencyError::new(format!(
                "dependency record {} requires canonical source ubuntu:{}, got {}",
                record.id, identity.version_id, record.source
            )));
        }
    }
    Ok(identity)
}

fn image_dependencies_root() -> String {
    IMAGE_DEPENDENCIES_ROOT.to_string()
}

#[cfg(unix)]
fn image_owner_is_root() -> bool {
    nix::unistd::geteuid().as_raw() == 0
}

#[cfg(not(unix))]
fn image_owner_is_root() -> bool {
    false
}

fn image_plan_payload(plan: &DependencyPlan, selected_ids: &[String]) -> Result<Value> {
    let mut records = Vec::new();
    let mut provider_closure = Vec::new();
    let mut receipts = Vec::new();
    for record_id in selected_ids {
        let record = plan.by_id(record_id).ok_or_else(|| {
            DependencyError::new(format!("unknown dependency record: {record_id}"))
        })?;
        let providers = plan
            .dependency_providers
            .iter()
            .find(|(candidate, _)| candidate == record_id)
            .map(|(_, providers)| providers.clone())
            .unwrap_or_default();
        records.push(record.payload());
        provider_closure.push(json!([record_id, providers]));
        receipts.push(format!("receipts/{record_id}.json"));
    }
    Ok(json!({
        "schema": IMAGE_PLAN_SCHEMA,
        "schema_version": IMAGE_PLAN_SCHEMA_VERSION,
        "owner": "image-installer",
        "phase": "image-install",
        "plan_fingerprint": plan.fingerprint,
        "source_roles": plan.source_roles,
        "order": selected_ids,
        "records": records,
        "provider_closure": provider_closure,
        "receipts": receipts,
    }))
}

fn image_record_is_safe(record: &DependencyRecord) -> bool {
    if !IMAGE_INSTALL_METHODS.contains(&record.method) {
        return false;
    }
    if record.method == Method::CargoSourceBuild {
        return record.locked == Some(true)
            && record.source_identity.as_deref() == Some(CANONICAL_SNAPSHOT_IDENTITY)
            && record
                .cargo_lock_sha256
                .as_deref()
                .is_some_and(|value| is_hex(value, 64));
    }
    true
}

fn image_lstat(path: &Path, description: &str) -> Result<fs::Metadata> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        DependencyError::new(format!(
            "{description} is unreadable: {}: {error}",
            path.display()
        ))
    })?;
    if metadata.file_type().is_symlink() {
        return Err(DependencyError::new(format!(
            "{description} must not be a symlink: {}",
            path.display()
        )));
    }
    Ok(metadata)
}

fn image_node_kind(metadata: &fs::Metadata, directory: bool) -> bool {
    if directory {
        metadata.is_dir()
    } else {
        metadata.is_file()
    }
}

#[cfg(unix)]
fn image_owner(production: bool) -> (u32, u32) {
    if production {
        (0, 0)
    } else {
        use std::os::unix::fs::MetadataExt;
        fs::metadata(".")
            .map(|metadata| (metadata.uid(), metadata.gid()))
            .unwrap_or((0, 0))
    }
}

#[cfg(not(unix))]
fn image_owner(_production: bool) -> (u32, u32) {
    (0, 0)
}

#[cfg(unix)]
fn set_image_owner(path: &Path, uid: u32, gid: u32) -> Result<()> {
    use nix::unistd::{chown, Gid, Uid};
    chown(path, Some(Uid::from_raw(uid)), Some(Gid::from_raw(gid))).map_err(|error| {
        DependencyError::new(format!(
            "image ownership update failed: {}: {error}",
            path.display()
        ))
    })
}

#[cfg(not(unix))]
fn set_image_owner(_path: &Path, _uid: u32, _gid: u32) -> Result<()> {
    Ok(())
}

fn set_image_mode(path: &Path, mode: u32) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(mode)).map_err(|error| {
            DependencyError::new(format!(
                "image mode update failed: {}: {error}",
                path.display()
            ))
        })
    }
    #[cfg(not(unix))]
    {
        let _ = (path, mode);
        Ok(())
    }
}

fn validate_image_parent_chain(
    target: &Path,
    production: bool,
    create: bool,
    owner: (u32, u32),
) -> Result<()> {
    let parent = target
        .parent()
        .ok_or_else(|| DependencyError::new("image target has no parent"))?;
    if production && !parent.starts_with("/usr/local/") {
        return Err(DependencyError::new(format!(
            "image target escaped canonical root: {}",
            target.display()
        )));
    }
    let mut current = PathBuf::from("/");
    for component in parent.components().skip(1) {
        current.push(component.as_os_str());
        let metadata = match image_lstat(&current, "image parent") {
            Ok(metadata) => metadata,
            Err(_error) if create && !current.exists() => {
                fs::create_dir(&current).map_err(|create_error| {
                    DependencyError::new(format!(
                        "image parent cannot be created safely: {}: {create_error}",
                        current.display()
                    ))
                })?;
                set_image_owner(&current, owner.0, owner.1)?;
                set_image_mode(&current, 0o755)?;
                image_lstat(&current, "image parent")?
            }
            Err(error) => return Err(error),
        };
        if !metadata.is_dir() {
            return Err(DependencyError::new(format!(
                "image parent must be a directory: {}",
                current.display()
            )));
        }
        #[cfg(unix)]
        if production {
            use std::os::unix::fs::MetadataExt;
            if metadata.uid() != owner.0
                || metadata.gid() != owner.1
                || metadata.mode() & 0o022 != 0
            {
                return Err(DependencyError::new(format!(
                    "image parent ownership or mode is unsafe: {}",
                    current.display()
                )));
            }
        }
    }
    Ok(())
}

fn freeze_image_tree(root: &Path, owner: (u32, u32)) -> Result<()> {
    let mut pending = vec![root.to_path_buf()];
    let mut nodes = Vec::<(PathBuf, bool)>::new();
    while let Some(path) = pending.pop() {
        let metadata = image_lstat(&path, "image staging path")?;
        if metadata.is_dir() {
            for child in fs::read_dir(&path).map_err(|error| {
                DependencyError::new(format!(
                    "image staging directory is unreadable: {}: {error}",
                    path.display()
                ))
            })? {
                pending.push(
                    child
                        .map_err(|error| DependencyError::new(error.to_string()))?
                        .path(),
                );
            }
        } else if !metadata.is_file() {
            return Err(DependencyError::new(format!(
                "image staging node is not regular: {}",
                path.display()
            )));
        }
        nodes.push((path, metadata.is_dir()));
    }
    nodes.sort_by_key(|(path, _)| std::cmp::Reverse(path.components().count()));
    for (path, directory) in nodes {
        set_image_owner(&path, owner.0, owner.1)?;
        set_image_mode(
            &path,
            if directory {
                IMAGE_DIRECTORY_MODE
            } else {
                IMAGE_FILE_MODE
            },
        )?;
    }
    Ok(())
}

fn assert_frozen_image_node(
    path: &Path,
    directory: bool,
    owner: (u32, u32),
    description: &str,
) -> Result<()> {
    let metadata = image_lstat(path, description)?;
    if !image_node_kind(&metadata, directory) {
        return Err(DependencyError::new(format!(
            "{description} has the wrong type: {}",
            path.display()
        )));
    }
    #[cfg(not(unix))]
    let _ = owner;
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        let expected_mode = if directory {
            IMAGE_DIRECTORY_MODE
        } else {
            IMAGE_FILE_MODE
        };
        if metadata.uid() != owner.0
            || metadata.gid() != owner.1
            || metadata.mode() & 0o7777 != expected_mode
        {
            return Err(DependencyError::new(format!(
                "{description} ownership or mode is unsafe: {}",
                path.display()
            )));
        }
    }
    Ok(())
}

fn image_target() -> (PathBuf, bool) {
    (PathBuf::from(IMAGE_DEPENDENCIES_ROOT), true)
}

fn image_target_exists(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok()
}

struct ImageInstallContext<'a> {
    target: &'a Path,
    production: bool,
    runtime_identity: Option<RuntimeIdentity>,
}

fn image_receipt_path(receipts: &Path, record_id: &str) -> Result<PathBuf> {
    if !matches(r"^[a-z0-9][a-z0-9._-]*$", record_id) {
        return Err(DependencyError::new(format!(
            "invalid receipt record id: {record_id}"
        )));
    }
    Ok(receipts.join(format!("{record_id}.json")))
}

fn current_user_is_root() -> bool {
    #[cfg(unix)]
    {
        nix::unistd::geteuid().as_raw() == 0
    }
    #[cfg(not(unix))]
    {
        false
    }
}

fn dependency_tool_environment(
    workspace: &Path,
    image_owned: bool,
    parent_root: Option<&Path>,
    extra: &BTreeMap<String, String>,
) -> Result<BTreeMap<String, String>> {
    let mut environment = if image_owned {
        env::vars().collect::<BTreeMap<_, _>>()
    } else {
        let parent_root = parent_root
            .ok_or_else(|| DependencyError::new("parent-root-attestation is required"))?;
        let runtime = env::var_os("AGENT_CANON_RUNTIME_ROOT")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .ok_or_else(|| DependencyError::new("dependency-install: runtime_root_required"))?;
        crate::runtime_boundary::root_capability_environment(
            workspace,
            &runtime,
            None,
            Some(parent_root),
        )
        .map_err(|error| {
            DependencyError::new(format!("dependency-install: runtime_root_invalid:{error}"))
        })?
    };
    let home = environment
        .get("HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(PathBuf::from))
        .unwrap_or_else(|| home_directory().unwrap_or_else(|_| PathBuf::from("/")));
    let cargo_home = environment
        .get("CARGO_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            parent_root
                .map(|root| root.join(".agent-canon/cargo-home"))
                .unwrap_or_else(|| home.join(".cargo"))
        });
    let rustup_home = environment
        .get("RUSTUP_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            parent_root
                .map(|root| root.join(".agent-canon/rustup-home"))
                .unwrap_or_else(|| home.join(".rustup"))
        });
    let elan_home = environment
        .get("ELAN_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            parent_root
                .map(|root| root.join(".agent-canon/elan-home"))
                .unwrap_or_else(|| home.join(".elan"))
        });
    let local_bin = parent_root
        .map(|root| root.join(".agent-canon/local-bin"))
        .unwrap_or_else(|| home.join(".local/bin"));
    let mut path = vec![
        cargo_home.join("bin").to_string_lossy().to_string(),
        elan_home.join("bin").to_string_lossy().to_string(),
        local_bin.to_string_lossy().to_string(),
    ];
    let inherited_path = environment
        .get("PATH")
        .map(|value| PathBuf::from(value.as_str()))
        .or_else(|| env::var_os("PATH").map(PathBuf::from));
    if let Some(inherited) = inherited_path {
        // PATH is already a list. Split it before joining so each directory
        // remains one segment and Unix does not reject the separator.
        path.extend(env::split_paths(&inherited).map(|entry| entry.to_string_lossy().into_owned()));
    }
    environment.remove("CARGO_TARGET_DIR");
    environment.insert("HOME".to_string(), home.to_string_lossy().to_string());
    environment.insert(
        "CARGO_HOME".to_string(),
        cargo_home.to_string_lossy().to_string(),
    );
    environment.insert(
        "RUSTUP_HOME".to_string(),
        rustup_home.to_string_lossy().to_string(),
    );
    environment.insert(
        "ELAN_HOME".to_string(),
        elan_home.to_string_lossy().to_string(),
    );
    let joined_path = env::join_paths(path.iter()).map_err(|error| {
        DependencyError::new(format!("dependency PATH cannot be joined: {error}"))
    })?;
    environment.insert(
        "PATH".to_string(),
        joined_path.to_string_lossy().to_string(),
    );
    environment.remove("RUSTUP_TOOLCHAIN");
    environment.remove("ELAN_TOOLCHAIN");
    environment.extend(extra.clone());
    Ok(environment)
}

fn dependency_command(
    probe: &ProbeEnvironment,
    argv: &[String],
    context: &DependencyCommandContext<'_>,
) -> Result<Option<CommandOutput>> {
    let phase = if context.operation.starts_with("verify-") {
        "image-verify"
    } else {
        "image-install"
    };
    let owner = if phase == "image-verify" {
        "typed-verifier"
    } else {
        "image-installer"
    };
    classify_dependency_command(
        argv,
        phase,
        owner,
        context.operation,
        context.method,
        context.privileged,
    )
    .map_err(|(capability, detail)| {
        DependencyError::new(format!(
            "command-boundary-{}: {detail}",
            capability.as_str()
        ))
    })?;
    let path = context.variables.get("PATH").cloned();
    let cargo_home = context.variables.get("CARGO_HOME").cloned();
    let output = probe.execute(&CommandInvocation {
        argv: argv.to_vec(),
        workspace: context.workspace.to_path_buf(),
        path,
        cargo_home,
        clear_rustup_overrides: true,
        environment: context.variables.clone(),
        clear_environment: context.clear_environment,
        privileged: context.privileged,
        capture: context.capture,
        operation: context.operation.to_string(),
        record_id: context.record_id.to_string(),
    })?;
    if context.capture {
        Ok(Some(output))
    } else {
        Ok(None)
    }
}

fn classify_dependency_command(
    argv: &[String],
    phase: &str,
    owner: &str,
    operation: &str,
    method: Option<Method>,
    privileged: bool,
) -> std::result::Result<BTreeSet<CommandCapability>, (CommandCapability, String)> {
    let fail = |capability, detail: &str| Err((capability, detail.to_string()));
    if !matches!(phase, "image-install" | "image-verify")
        || !matches!(owner, "image-installer" | "typed-verifier")
        || operation.is_empty()
    {
        return fail(CommandCapability::Unknown, "invalid command provenance");
    }
    if (phase == "image-install" && owner != "image-installer")
        || (phase == "image-verify" && owner != "typed-verifier")
    {
        return fail(
            CommandCapability::Unknown,
            "command phase and owner disagree",
        );
    }
    let method_matches = match operation {
        "install-apt-package" => matches!(method, Some(Method::AptPackage)),
        "install-apt-repository"
        | "install-apt-repository-key"
        | "install-apt-repository-source"
        | "download-apt-key"
        | "download-apt-package"
        | "download-packages-index"
        | "verify-apt-repository-key" => matches!(method, Some(Method::AptRepository)),
        "verify-apt-package" => matches!(method, Some(Method::AptPackage | Method::AptRepository)),
        "install-npm-global" | "verify-npm-package" => matches!(method, Some(Method::NpmGlobal)),
        "install-pipx" | "verify-pipx-package" | "verify-pipx-executable" => {
            matches!(method, Some(Method::Pipx))
        }
        "install-release-asset" | "download-release-asset" => {
            matches!(method, Some(Method::ReleaseAsset))
        }
        "install-rust-toolchain"
        | "verify-rust-active"
        | "verify-rust-installed"
        | "verify-rust-components"
        | "verify-rust-tool-version" => matches!(method, Some(Method::RustToolchain)),
        "install-lean-toolchain"
        | "verify-lean-active"
        | "verify-lean-installed"
        | "verify-lean-toolchain"
        | "verify-lean-tool-version" => matches!(method, Some(Method::LeanToolchain)),
        "install-cargo-source-build" | "verify-cargo-binary" | "verify-cargo-source-identity" => {
            matches!(method, Some(Method::CargoSourceBuild))
        }
        "install-browser" | "verify-browser-executable" => {
            matches!(method, Some(Method::BrowserInstall))
        }
        _ => true,
    };
    if !method_matches && method.is_some() {
        return fail(
            CommandCapability::Unknown,
            "operation and method provenance disagree",
        );
    }
    if phase == "image-verify" && !operation.starts_with("verify-") {
        return fail(
            CommandCapability::Unknown,
            "image verification operation is not a verifier operation",
        );
    }
    if phase == "image-install"
        && !(operation.starts_with("install-")
            || operation.starts_with("download-")
            || operation.starts_with("verify-"))
    {
        return fail(
            CommandCapability::Unknown,
            "image install operation is not owner-declared",
        );
    }
    if argv.is_empty()
        || argv
            .iter()
            .any(|argument| argument.is_empty() || has_control(argument))
    {
        return fail(
            CommandCapability::Unknown,
            "argv contains an empty or control-character token",
        );
    }
    let mut effective = argv;
    if basename(&effective[0]) == "env" {
        let mut index = 1;
        while index < effective.len()
            && effective[index].contains('=')
            && !effective[index].starts_with('-')
        {
            index += 1;
        }
        if index >= effective.len() || effective[index] == "-S" {
            return fail(CommandCapability::Unknown, "env child selection is dynamic");
        }
        if effective[index] == "--" {
            index += 1;
        }
        if index >= effective.len() {
            return fail(CommandCapability::Unknown, "env has no command target");
        }
        effective = &effective[index..];
        let mut capabilities =
            classify_dependency_command(effective, phase, owner, operation, method, privileged)?;
        if privileged {
            capabilities.insert(CommandCapability::PrivilegeEscalation);
        }
        return validate_dependency_capabilities(capabilities, phase);
    }
    let executable = basename(&effective[0]);
    let args = &effective[1..];
    let mut capabilities = BTreeSet::from([CommandCapability::Argv]);
    if ["bash", "dash", "fish", "ksh", "sh", "tcsh", "zsh"].contains(&executable) {
        return fail(
            CommandCapability::ShellEvaluation,
            "shell executable is an execution boundary",
        );
    }
    if ["sudo", "doas", "su", "runuser"].contains(&executable) {
        return fail(
            CommandCapability::PrivilegeEscalation,
            "explicit privilege wrapper is not an owned command",
        );
    }
    if executable == "eval" {
        return fail(
            CommandCapability::DynamicInterpreter,
            "eval is a dynamic child-command edge",
        );
    }
    let interpreter_probes: &[(&str, &[&str])] = &[
        ("python", &["--version", "-V", "--help"]),
        ("python3", &["--version", "-V", "--help"]),
        ("pypy", &["--version", "-V", "--help"]),
        ("node", &["--version", "-v", "--help"]),
        ("nodejs", &["--version", "-v", "--help"]),
        ("perl", &["--version", "-v", "--help"]),
        ("ruby", &["--version", "-v", "--help"]),
    ];
    if let Some((_, probes)) = interpreter_probes
        .iter()
        .find(|(name, _)| *name == executable)
    {
        if args.len() == 1 && probes.contains(&args[0].as_str()) {
            capabilities.insert(CommandCapability::ReadOnlyQuery);
        } else {
            let dynamic = args.iter().any(|argument| {
                ["-c", "-e", "-E", "-m", "-p", "--eval", "--print", "-"]
                    .contains(&argument.as_str())
            });
            return fail(
                if dynamic {
                    CommandCapability::DynamicInterpreter
                } else {
                    CommandCapability::Unknown
                },
                "interpreter command graph is not a fixed identity probe",
            );
        }
    } else if executable == "xargs"
        || executable == "find"
            && args
                .iter()
                .any(|argument| ["-exec", "-execdir"].contains(&argument.as_str()))
    {
        return fail(
            CommandCapability::DynamicInterpreter,
            "child-command selector is dynamic",
        );
    } else if ["timeout", "nice", "stdbuf"].contains(&executable) {
        return fail(
            CommandCapability::Unknown,
            "wrapper grammar is not declared by the owner operation",
        );
    } else if [
        "apt",
        "apt-get",
        "aptitude",
        "pip",
        "pipx",
        "cargo",
        "playwright",
    ]
    .contains(&executable)
    {
        let mutations = [
            "install",
            "update",
            "upgrade",
            "remove",
            "uninstall",
            "purge",
            "add",
            "default",
            "build",
            "fetch",
            "sync",
            "download",
            "init",
        ];
        if executable == "pipx"
            && args.first().is_some_and(|value| value == "runpip")
            && args.len() >= 4
            && args[2] == "show"
        {
            capabilities.insert(CommandCapability::ReadOnlyQuery);
        } else if args.iter().any(|value| mutations.contains(&value.as_str())) {
            capabilities.insert(CommandCapability::PackageInstall);
            capabilities.insert(CommandCapability::NetworkFetch);
        } else {
            return fail(
                CommandCapability::Unknown,
                "package-manager command shape is not owner-declared",
            );
        }
    } else if executable == "npm" {
        if argv_starts_with(args, &["ls", "--global"])
            && argv_contains(args, "--json")
            && argv_contains(args, "--depth=0")
        {
            capabilities.insert(CommandCapability::ReadOnlyQuery);
        } else if args.first().is_some_and(|value| {
            ["install", "update", "uninstall", "exec", "publish"].contains(&value.as_str())
        }) {
            capabilities.insert(CommandCapability::PackageInstall);
            capabilities.insert(CommandCapability::NetworkFetch);
        } else if argv_equals(args, &["--version"]) {
            capabilities.insert(CommandCapability::ReadOnlyQuery);
        } else {
            return fail(
                CommandCapability::Unknown,
                "npm command shape is not owner-declared",
            );
        }
    } else if ["rustup", "elan"].contains(&executable) {
        let read_only = if executable == "rustup" {
            argv_starts_with(args, &["show", "active-toolchain"])
                || argv_starts_with(args, &["toolchain", "list"])
                || argv_starts_with(args, &["component", "list"])
                || args.first().is_some_and(|value| value == "run")
                    && args.len() == 4
                    && args.last().is_some_and(|value| value == "--version")
        } else {
            args.first().is_some_and(|value| value == "show")
                || argv_starts_with(args, &["toolchain", "list"])
                || args.first().is_some_and(|value| value == "run")
                    && args.len() == 4
                    && args.last().is_some_and(|value| value == "--version")
        };
        if read_only {
            capabilities.insert(CommandCapability::ReadOnlyQuery);
        } else if args
            .iter()
            .any(|value| ["install", "uninstall", "add", "default"].contains(&value.as_str()))
        {
            capabilities.insert(CommandCapability::PackageInstall);
            capabilities.insert(CommandCapability::NetworkFetch);
        } else {
            return fail(
                CommandCapability::Unknown,
                "toolchain command shape is not owner-declared",
            );
        }
    } else if executable == "gpg" {
        if argv_starts_with(args, &["--show-keys", "--with-colons"]) {
            capabilities.insert(CommandCapability::ReadOnlyQuery);
        } else {
            capabilities.insert(CommandCapability::PackageInstall);
        }
    } else if ["curl", "wget", "aria2c"].contains(&executable) {
        if argv_equals(args, &["--version"])
            || argv_equals(args, &["-V"])
            || argv_equals(args, &["--help"])
        {
            capabilities.insert(CommandCapability::ReadOnlyQuery);
        } else {
            capabilities.insert(CommandCapability::NetworkFetch);
        }
    } else if executable == "install" || executable == "rustup-init" || executable == "elan-init" {
        capabilities.insert(CommandCapability::PackageInstall);
    } else if executable == "dpkg-query" {
        if args
            .first()
            .is_some_and(|value| ["--show", "--listfiles"].contains(&value.as_str()))
        {
            capabilities.insert(CommandCapability::ReadOnlyQuery);
        } else {
            return fail(
                CommandCapability::Unknown,
                "dpkg-query command shape is not owner-declared",
            );
        }
    } else if executable == "xz" && argv_starts_with(args, &["--decompress", "--stdout"]) {
        capabilities.insert(CommandCapability::ReadOnlyQuery);
    } else {
        capabilities.insert(CommandCapability::ExecutableVerification);
    }
    if privileged {
        capabilities.insert(CommandCapability::PrivilegeEscalation);
    }
    validate_dependency_capabilities(capabilities, phase)
}

fn validate_dependency_capabilities(
    capabilities: BTreeSet<CommandCapability>,
    phase: &str,
) -> std::result::Result<BTreeSet<CommandCapability>, (CommandCapability, String)> {
    let denied = if phase == "image-verify" {
        [
            CommandCapability::ShellEvaluation,
            CommandCapability::DynamicInterpreter,
            CommandCapability::Unknown,
            CommandCapability::PackageInstall,
            CommandCapability::NetworkFetch,
            CommandCapability::PrivilegeEscalation,
        ]
        .into_iter()
        .collect::<BTreeSet<_>>()
    } else {
        [
            CommandCapability::ShellEvaluation,
            CommandCapability::DynamicInterpreter,
            CommandCapability::Unknown,
        ]
        .into_iter()
        .collect::<BTreeSet<_>>()
    };
    let Some(capability) = [
        CommandCapability::ShellEvaluation,
        CommandCapability::DynamicInterpreter,
        CommandCapability::PackageInstall,
        CommandCapability::NetworkFetch,
        CommandCapability::PrivilegeEscalation,
        CommandCapability::Unknown,
    ]
    .into_iter()
    .find(|capability| denied.contains(capability) && capabilities.contains(capability)) else {
        return Ok(capabilities);
    };
    Err((
        capability,
        format!("{} is not allowed in {phase}", capability.as_str()),
    ))
}

fn basename(value: &str) -> &str {
    value.rsplit('/').next().unwrap_or(value)
}

fn argv_starts_with(argv: &[String], prefix: &[&str]) -> bool {
    argv.len() >= prefix.len()
        && argv
            .iter()
            .zip(prefix)
            .all(|(actual, expected)| actual.as_str() == *expected)
}

fn argv_contains(argv: &[String], value: &str) -> bool {
    argv.iter().any(|argument| argument.as_str() == value)
}

fn argv_equals(argv: &[String], expected: &[&str]) -> bool {
    argv.len() == expected.len()
        && argv
            .iter()
            .zip(expected)
            .all(|(actual, expected)| actual.as_str() == *expected)
}

fn install_project_extras(workspace: &Path, raw_extras: &str) -> Result<Vec<String>> {
    let extras = validate_project_extras(workspace, &[raw_extras.to_string()])?;
    let requirement = format!("{}[{}]", workspace.display(), extras.join(","));
    for arguments in [
        vec!["-m", "pip", "install", "--editable", requirement.as_str()],
        vec!["-m", "pip", "check"],
    ] {
        let status = Command::new("python3")
            .args(arguments.iter())
            .current_dir(workspace)
            .status()
            .map_err(|error| {
                DependencyError::new(format!("project extras command failed to start: {error}"))
            })?;
        if !status.success() {
            return Err(DependencyError::new(format!(
                "project extras command failed with {status}"
            )));
        }
    }
    Ok(extras)
}

fn command_exists(executable: &str) -> bool {
    let path = env::var_os("PATH").unwrap_or_default();
    env::split_paths(&path)
        .map(|directory| directory.join(executable))
        .any(|path| path.is_file())
}

fn attest_dependency_parent(workspace: &Path) -> Result<AttestedParent> {
    let purpose = NonEmptyTrimmedString::new("dependency-install").map_err(|error| {
        DependencyError::new(format!(
            "parent-root-attestation:{}:{}",
            error.reject,
            error.detail()
        ))
    })?;
    let nonce = Nonce128::generate().map_err(|error| {
        DependencyError::new(format!(
            "parent-root-attestation:{}:{}",
            error.reject,
            error.detail()
        ))
    })?;
    let request = AttestationRequest {
        cwd: workspace.to_path_buf(),
        explicit_root: Some(workspace.to_path_buf()),
        source_root: None,
        clone_root: None,
        topic_marker: None,
        gitmodules: None,
        owner_evidence: None,
        expected_remote: None,
        expected_module_digest: None,
        child_handoff_token: None,
        purpose,
        nonce,
    };
    ParentRootAttestor::new().attest(&request).map_err(|error| {
        DependencyError::new(format!(
            "parent-root-attestation:{}:{}",
            error.reject,
            error.detail()
        ))
    })
}

struct Installer {
    image_owned: bool,
    image_owned_root: Option<PathBuf>,
    parent_attestation: Option<AttestedParent>,
    install_workspace: Option<PathBuf>,
    resolved_package_versions: BTreeMap<String, String>,
    probe: ProbeEnvironment,
    active_method: Option<Method>,
}

impl Installer {
    fn new(image_owned: bool, image_owned_root: Option<PathBuf>) -> Self {
        Self {
            image_owned,
            image_owned_root,
            parent_attestation: None,
            install_workspace: None,
            resolved_package_versions: BTreeMap::new(),
            probe: ProbeEnvironment::system(),
            active_method: None,
        }
    }

    #[cfg(all(test, unix))]
    fn with_probe(
        image_owned: bool,
        image_owned_root: Option<PathBuf>,
        probe: ProbeEnvironment,
    ) -> Self {
        Self {
            image_owned,
            image_owned_root,
            parent_attestation: None,
            install_workspace: None,
            resolved_package_versions: BTreeMap::new(),
            probe,
            active_method: None,
        }
    }

    fn install(
        &mut self,
        plan: &DependencyPlan,
        workspace: &Path,
        receipts: &Path,
        requested: Option<&[String]>,
        final_binary_dir: Option<&Path>,
    ) -> Result<Vec<String>> {
        self.install_workspace = Some(workspace.to_path_buf());
        if self.image_owned {
            let image_root = self.image_owned_root.as_deref().ok_or_else(|| {
                DependencyError::new("image-owned install requires an image root")
            })?;
            let receipt_root =
                crate::path_resolution::resolve_non_strict(receipts).map_err(|error| {
                    DependencyError::new(format!("image receipt path is invalid: {error}"))
                })?;
            if !receipt_root.starts_with(image_root) {
                return Err(DependencyError::new(
                    "image-owned receipts must remain under the image root",
                ));
            }
            fs::create_dir_all(&receipt_root).map_err(|error| {
                DependencyError::new(format!("image receipt directory is unavailable: {error}"))
            })?;
        } else {
            self.parent_attestation = Some(attest_dependency_parent(workspace)?);
        }
        let selected = select_record_ids(plan, requested)?;
        let by_id = plan
            .records
            .iter()
            .map(|record| (record.id.as_str(), record))
            .collect::<BTreeMap<_, _>>();
        let unknown = selected
            .iter()
            .filter(|record_id| !by_id.contains_key(record_id.as_str()))
            .cloned()
            .collect::<Vec<_>>();
        if !unknown.is_empty() {
            return Err(DependencyError::new(format!(
                "selected dependency records are not in the plan: {}",
                unknown.join(", ")
            )));
        }
        if self.image_owned
            && final_binary_dir.is_none()
            && selected.iter().any(|record_id| {
                by_id
                    .get(record_id.as_str())
                    .is_some_and(|record| record.method == Method::CargoSourceBuild)
            })
        {
            return Err(DependencyError::new(
                "image-owned Cargo install requires a final binary directory",
            ));
        }
        let mut completed = Vec::new();
        let mut unavailable = BTreeSet::new();
        for record_id in &selected {
            let record = by_id
                .get(record_id.as_str())
                .copied()
                .expect("selected record was checked");
            self.active_method = Some(record.method);
            self.resolved_package_versions.remove(record_id);
            let receipt = image_receipt_path(receipts, record_id)?;
            let active_source = record.method == Method::CargoSourceBuild
                && record.source_identity.as_deref() == Some(ACTIVE_SOURCE_IDENTITY);
            let blockers = plan
                .dependency_providers
                .iter()
                .find(|(candidate, _)| candidate == record_id)
                .map(|(_, providers)| {
                    providers
                        .iter()
                        .filter(|provider| unavailable.contains(provider.as_str()))
                        .cloned()
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            if !blockers.is_empty() {
                let error = DependencyError::new(format!(
                    "dependency unavailable: {record_id} depends on {}",
                    blockers.join(", ")
                ));
                self.remove_receipt(&receipt)?;
                unavailable.insert(record_id.clone());
                if record.failure_policy == "warn" {
                    eprintln!("DEPENDENCY_RECORD_WARN={record_id}:{error}");
                    continue;
                }
                return Err(error);
            }
            let receipt_exists = self.receipt_exists(&receipt)?;
            let cache_match = !active_source && self.receipt_matches(&receipt, plan, record)?;
            let repair = receipt_exists;
            if cache_match
                && (self.image_owned
                    || self
                        .verify_cached_receipt(&receipt, record, workspace)
                        .is_ok())
            {
                completed.push(record_id.clone());
                continue;
            }
            self.remove_receipt(&receipt)?;
            let install_result = (|| -> Result<()> {
                self.install_record(record, workspace, repair)?;
                if !self.image_owned {
                    if let Some(version) = self.verify_record(record, workspace, None, false)? {
                        self.resolved_package_versions
                            .insert(record.id.clone(), version);
                    }
                }
                let source_identity = if record.method == Method::CargoSourceBuild
                    && record.source_identity.as_deref() == Some(CANONICAL_SNAPSHOT_IDENTITY)
                {
                    Some(CANONICAL_SNAPSHOT_IDENTITY.to_string())
                } else if record.method == Method::CargoSourceBuild && record.commit.is_some() {
                    Some(self.cargo_source_identity(record, workspace)?)
                } else {
                    None
                };
                if self.image_owned
                    && record.method == Method::AptPackage
                    && record.version.is_none()
                {
                    let version = apt_package_version(&self.probe, record, None, workspace, false)?;
                    self.resolved_package_versions
                        .insert(record.id.clone(), version);
                }
                if active_source {
                    return Ok(());
                }
                let bindings = if self.image_owned {
                    self.structural_bindings(record)?
                } else {
                    executable_bindings(&self.probe, record, false, workspace)?
                };
                let final_binary = if record.method == Method::CargoSourceBuild {
                    final_binary_dir
                        .map(|directory| self.publish_final_binary(record, workspace, directory))
                        .transpose()?
                } else {
                    None
                };
                self.write_receipt(
                    &receipt,
                    plan,
                    record,
                    source_identity.as_deref(),
                    &bindings,
                    final_binary.as_deref(),
                )?;
                Ok(())
            })();
            if let Err(error) = install_result {
                self.remove_receipt(&receipt)?;
                unavailable.insert(record_id.clone());
                if record.failure_policy == "warn" {
                    eprintln!("DEPENDENCY_RECORD_WARN={record_id}:{error}");
                    continue;
                }
                return Err(DependencyError::new(format!(
                    "dependency record failed: {record_id}: {error}"
                )));
            }
            completed.push(record_id.clone());
        }
        Ok(completed)
    }

    fn receipt_exists(&self, path: &Path) -> Result<bool> {
        if self.image_owned {
            return Ok(fs::symlink_metadata(path).is_ok());
        }
        let Some(attested) = &self.parent_attestation else {
            return Ok(false);
        };
        let purpose = NonEmptyTrimmedString::new("dependency-receipt")
            .map_err(|error| DependencyError::new(error.to_string()))?;
        let receipt = attested
            .resolve_parent_owned_path(path, purpose)
            .map_err(|error| {
                DependencyError::new(format!(
                    "parent-root-receipt:{}:{}",
                    error.reject,
                    error.detail()
                ))
            })?;
        Ok(attested.read_parent_owned_file(&receipt).is_ok())
    }

    fn remove_receipt(&self, path: &Path) -> Result<()> {
        if self.image_owned {
            match fs::symlink_metadata(path) {
                Ok(metadata) if metadata.is_file() || metadata.file_type().is_symlink() => {
                    fs::remove_file(path).map_err(|error| {
                        DependencyError::new(format!(
                            "image receipt could not be removed: {}: {error}",
                            path.display()
                        ))
                    })
                }
                Ok(_) => Err(DependencyError::new(format!(
                    "image receipt is not a regular file: {}",
                    path.display()
                ))),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
                Err(error) => Err(DependencyError::new(format!(
                    "image receipt could not be inspected: {}: {error}",
                    path.display()
                ))),
            }
        } else {
            let attested = self
                .parent_attestation
                .as_ref()
                .ok_or_else(|| DependencyError::new("parent-root-attestation is required"))?;
            let purpose = NonEmptyTrimmedString::new("dependency-receipt")
                .map_err(|error| DependencyError::new(error.to_string()))?;
            let receipt = attested
                .resolve_parent_owned_path(path, purpose)
                .map_err(|error| {
                    DependencyError::new(format!(
                        "parent-root-receipt:{}:{}",
                        error.reject,
                        error.detail()
                    ))
                })?;
            attested
                .remove_parent_owned_file(&receipt)
                .map_err(|error| {
                    DependencyError::new(format!(
                        "parent-root-receipt:{}:{}",
                        error.reject,
                        error.detail()
                    ))
                })
        }
    }

    fn read_receipt(&self, path: &Path) -> Result<Vec<u8>> {
        if self.image_owned {
            return fs::read(path).map_err(|error| DependencyError::new(error.to_string()));
        }
        let attested = self
            .parent_attestation
            .as_ref()
            .ok_or_else(|| DependencyError::new("parent-root-attestation is required"))?;
        let purpose = NonEmptyTrimmedString::new("dependency-receipt")
            .map_err(|error| DependencyError::new(error.to_string()))?;
        let receipt = attested
            .resolve_parent_owned_path(path, purpose)
            .map_err(|error| {
                DependencyError::new(format!(
                    "parent-root-receipt:{}:{}",
                    error.reject,
                    error.detail()
                ))
            })?;
        attested.read_parent_owned_file(&receipt).map_err(|error| {
            DependencyError::new(format!(
                "parent-root-receipt:{}:{}",
                error.reject,
                error.detail()
            ))
        })
    }

    fn receipt_matches(
        &self,
        path: &Path,
        plan: &DependencyPlan,
        record: &DependencyRecord,
    ) -> Result<bool> {
        if record.method == Method::CargoSourceBuild
            && record.source_identity.as_deref() == Some(ACTIVE_SOURCE_IDENTITY)
        {
            return Ok(false);
        }
        let Ok(bytes) = self.read_receipt(path) else {
            return Ok(false);
        };
        let Ok(payload) = serde_json::from_slice::<Value>(&bytes) else {
            return Ok(false);
        };
        let Some(object) = payload.as_object() else {
            return Ok(false);
        };
        let status = object
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let image_owned = status == "installed";
        let expected_names = executable_binding_names(record, image_owned)
            .into_iter()
            .collect::<BTreeSet<_>>();
        let Some(bindings) = object.get("executable_bindings").and_then(Value::as_object) else {
            return Ok(false);
        };
        if bindings.keys().cloned().collect::<BTreeSet<_>>() != expected_names {
            return Ok(false);
        }
        for (name, binding) in bindings {
            let Some(binding) = binding.as_object() else {
                return Ok(false);
            };
            let lexical = binding
                .get("lexical_path")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let absolute = binding
                .get("absolute_path")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let output = binding
                .get("verification_output")
                .and_then(Value::as_str)
                .unwrap_or_default();
            if binding.get("provided").and_then(Value::as_str) != Some(name.as_str())
                || normalized_absolute_path(lexical, "lexical_path").is_err()
                || normalized_absolute_path(absolute, "absolute_path").is_err()
                || output.is_empty()
            {
                return Ok(false);
            }
        }
        let expected_resolved = match self.resolved_apt_package_version(record, &payload) {
            Ok(value) => value,
            Err(_) => return Ok(false),
        };
        let _ = expected_resolved;
        Ok(
            object.get("schema").and_then(Value::as_str) == Some(RECEIPT_SCHEMA)
                && object.get("record_id").and_then(Value::as_str) == Some(record.id.as_str())
                && (status == "installed" || status == "pass")
                && object.get("owner").and_then(Value::as_str) == Some("image-installer")
                && object.get("phase").and_then(Value::as_str) == Some("image-install")
                && object.get("manifest_version")
                    == Some(
                        &record
                            .version
                            .as_ref()
                            .map_or(Value::Null, |value| Value::String(value.clone())),
                    )
                && object.get("plan_fingerprint").and_then(Value::as_str)
                    == Some(plan.fingerprint.as_str())
                && record.fingerprint().ok().as_deref()
                    == object.get("record_fingerprint").and_then(Value::as_str)
                && object.get("verification") == Some(&record.verification.payload())
                && repository_packages_payload(record)
                    .ok()
                    .map(|value| {
                        if value.is_null() {
                            object.get("repository_packages").is_none()
                        } else {
                            object.get("repository_packages") == Some(&value)
                        }
                    })
                    .unwrap_or(false)
                && repository_package_payload(record)
                    .ok()
                    .map(|value| {
                        if value.is_null() {
                            object.get("repository_package").is_none()
                        } else {
                            object.get("repository_package") == Some(&value)
                        }
                    })
                    .unwrap_or(false)
                && (record.source_tree_sha256.is_none()
                    || object.get("source_tree_sha256").and_then(Value::as_str)
                        == record.source_tree_sha256.as_deref())
                && object.get("cargo_lock_sha256").and_then(Value::as_str)
                    == record.cargo_lock_sha256.as_deref()
                && (record.method != Method::CargoSourceBuild
                    || object
                        .get("source_identity")
                        .and_then(Value::as_str)
                        .is_some()),
        )
    }

    fn tool_paths(
        &self,
        workspace: &Path,
        extra: &BTreeMap<String, String>,
    ) -> Result<BTreeMap<String, String>> {
        let parent_root = self
            .parent_attestation
            .as_ref()
            .map(|parent| parent.parent_root().path());
        dependency_tool_environment(workspace, self.image_owned, parent_root, extra)
    }

    fn run(
        &self,
        argv: &[String],
        workspace: &Path,
        variables: &BTreeMap<String, String>,
        privileged: bool,
        record_id: &str,
        operation: &str,
    ) -> Result<()> {
        dependency_command(
            &self.probe,
            argv,
            &DependencyCommandContext {
                workspace,
                method: self.active_method,
                variables,
                privileged,
                capture: false,
                clear_environment: !self.image_owned,
                record_id,
                operation,
            },
        )?;
        Ok(())
    }

    fn capture(
        &self,
        argv: &[String],
        workspace: &Path,
        variables: &BTreeMap<String, String>,
        record_id: &str,
        operation: &str,
    ) -> Result<CommandOutput> {
        dependency_command(
            &self.probe,
            argv,
            &DependencyCommandContext {
                workspace,
                method: self.active_method,
                variables,
                privileged: false,
                capture: true,
                clear_environment: !self.image_owned,
                record_id,
                operation,
            },
        )?
        .ok_or_else(|| DependencyError::new("dependency command output was not captured"))
    }

    fn verify_cached_receipt(
        &self,
        path: &Path,
        record: &DependencyRecord,
        workspace: &Path,
    ) -> Result<()> {
        let payload: Value = serde_json::from_slice(&self.read_receipt(path)?)
            .map_err(|_| DependencyError::new(format!("{}: receipt is malformed", record.id)))?;
        let bindings = payload
            .get("executable_bindings")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                DependencyError::new(format!(
                    "{}: executable receipt bindings are stale",
                    record.id
                ))
            })?
            .iter()
            .map(|(name, value)| Ok((name.clone(), ExecutableBinding::from_receipt(value, name)?)))
            .collect::<Result<BTreeMap<_, _>>>()?;
        let resolved_version = self.resolved_apt_package_version(record, &payload)?;
        self.verify_record(record, workspace, resolved_version.as_deref(), false)?;
        if !bindings.is_empty() {
            let live = executable_bindings(&self.probe, record, false, workspace)?;
            if live != bindings {
                return Err(DependencyError::new(format!(
                    "{}: executable receipt path or output drift",
                    record.id
                )));
            }
        }
        Ok(())
    }

    fn verify_record(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        expected_resolved_version: Option<&str>,
        allow_network: bool,
    ) -> Result<Option<String>> {
        let probe = &self.probe;
        match record.method {
            Method::AptPackage => {
                apt_package_version(probe, record, expected_resolved_version, workspace, true)
                    .map(Some)
            }
            Method::AptRepository => {
                self.verify_apt_repository(record, workspace, allow_network)?;
                Ok(None)
            }
            Method::NpmGlobal => {
                verify_npm_package(probe, record, workspace)?;
                Ok(None)
            }
            Method::Pipx => {
                self.verify_pipx_package(record, workspace)?;
                Ok(None)
            }
            Method::ReleaseAsset => {
                verify_absolute_executable(probe, record, workspace).map(|_| None)
            }
            Method::RustToolchain => {
                verify_rust_toolchain(probe, record, workspace)?;
                Ok(None)
            }
            Method::LeanToolchain => {
                self.verify_lean_toolchain(record, workspace)?;
                Ok(None)
            }
            Method::CargoSourceBuild => {
                self.verify_cargo_binary(record, None, workspace)?;
                Ok(None)
            }
            Method::BrowserInstall => {
                self.verify_browser_executable(record, workspace)?;
                Ok(None)
            }
        }
    }

    fn verify_apt_repository(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        allow_network: bool,
    ) -> Result<()> {
        apt_package_version(&self.probe, record, None, workspace, true)?;
        let expected_fingerprint = record.key_fingerprint.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: apt key fingerprint is missing", record.id))
        })?;
        let keyring = PathBuf::from("/etc/apt/keyrings").join(format!("{}.gpg", record.id));
        let source_list =
            PathBuf::from("/etc/apt/sources.list.d").join(format!("{}.list", record.id));
        if !keyring.is_file()
            || fs::symlink_metadata(&keyring)
                .is_ok_and(|metadata| metadata.file_type().is_symlink())
            || !source_list.is_file()
            || fs::symlink_metadata(&source_list)
                .is_ok_and(|metadata| metadata.file_type().is_symlink())
        {
            return Err(DependencyError::new(format!(
                "{}: apt repository artifact is missing",
                record.id
            )));
        }
        let variables = self.tool_paths(workspace, &BTreeMap::new())?;
        let output = self.capture(
            &[
                "gpg".to_string(),
                "--show-keys".to_string(),
                "--with-colons".to_string(),
                keyring.to_string_lossy().to_string(),
            ],
            workspace,
            &variables,
            &record.id,
            "verify-apt-repository-key",
        )?;
        let fingerprints = output
            .stdout
            .lines()
            .filter_map(|line| {
                let fields = line.split(':').collect::<Vec<_>>();
                (fields.first() == Some(&"fpr") && fields.len() > 9)
                    .then(|| fields[9].to_ascii_uppercase())
            })
            .collect::<BTreeSet<_>>();
        if !fingerprints.contains(&expected_fingerprint.to_ascii_uppercase()) {
            return Err(DependencyError::new(format!(
                "{}: apt repository key is stale",
                record.id
            )));
        }
        let suite = record.repository_suite.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: repository suite is missing", record.id))
        })?;
        let expected_source = format!(
            "deb [signed-by={}] {} {} {}\n",
            keyring.display(),
            record.source,
            suite,
            record.repository_components.join(" ")
        );
        let observed_source = fs::read_to_string(&source_list).map_err(|_| {
            DependencyError::new(format!(
                "{}: apt repository source is unreadable",
                record.id
            ))
        })?;
        if observed_source != expected_source {
            return Err(DependencyError::new(format!(
                "{}: apt repository source is stale",
                record.id
            )));
        }
        if allow_network {
            self.verify_repository_packages_digest(
                record,
                workspace,
                &self.temporary_parent(workspace, "apt-packages")?,
            )?;
        }
        Ok(())
    }

    fn verify_pipx_package(&self, record: &DependencyRecord, workspace: &Path) -> Result<()> {
        let version = record.version.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: pipx package version is missing", record.id))
        })?;
        let variables = self.tool_paths(workspace, &BTreeMap::new())?;
        let output = self.capture(
            &[
                "pipx".to_string(),
                "runpip".to_string(),
                record.package.clone(),
                "show".to_string(),
                record.package.clone(),
            ],
            workspace,
            &variables,
            &record.id,
            "verify-pipx-package",
        )?;
        let mut name = None;
        let mut observed_version = None;
        for line in output.stdout.lines() {
            if let Some((key, value)) = line.split_once(':') {
                if key == "Name" {
                    name = Some(canonical_python_extra(value.trim()));
                }
                if key == "Version" {
                    observed_version = Some(value.trim().to_string());
                }
            }
        }
        if name.as_deref() != Some(canonical_python_extra(&record.package).as_str())
            || observed_version.as_deref() != Some(version)
        {
            return Err(DependencyError::new(format!(
                "{}: pipx package/version mismatch",
                record.id
            )));
        }
        let executable = record.verification.executable.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: pipx executable is missing", record.id))
        })?;
        let mut argv = vec![executable.to_string()];
        argv.extend(record.verification.args.iter().cloned());
        let output = self.capture(
            &argv,
            workspace,
            &variables,
            &record.id,
            "verify-pipx-executable",
        )?;
        let token = record
            .verification
            .output_contains
            .as_deref()
            .ok_or_else(|| {
                DependencyError::new(format!("{}: pipx output contract is missing", record.id))
            })?;
        require_output(&output, token, &record.id)?;
        Ok(())
    }

    fn verify_lean_toolchain(&self, record: &DependencyRecord, workspace: &Path) -> Result<()> {
        let version = record.version.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: Lean toolchain version is missing", record.id))
        })?;
        let variables = self.tool_paths(workspace, &BTreeMap::new())?;
        let active = self.capture(
            &["elan".to_string(), "show".to_string()],
            workspace,
            &variables,
            &record.id,
            "verify-lean-active",
        )?;
        let installed = self.capture(
            &[
                "elan".to_string(),
                "toolchain".to_string(),
                "list".to_string(),
            ],
            workspace,
            &variables,
            &record.id,
            "verify-lean-installed",
        )?;
        if !active.stdout.contains(version)
            || !installed
                .stdout
                .lines()
                .any(|line| line.split_whitespace().next() == Some(version))
        {
            return Err(DependencyError::new(format!(
                "{}: Lean toolchain is stale",
                record.id
            )));
        }
        for tool in ["lean", "lake"] {
            self.capture(
                &[
                    "elan".to_string(),
                    "run".to_string(),
                    version.to_string(),
                    tool.to_string(),
                    "--version".to_string(),
                ],
                workspace,
                &variables,
                &record.id,
                "verify-lean-toolchain",
            )?;
        }
        Ok(())
    }

    fn verify_browser_executable(&self, record: &DependencyRecord, workspace: &Path) -> Result<()> {
        let cache = record.browser_cache_path.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: browser cache path is missing", record.id))
        })?;
        let cache_path = Path::new(cache);
        if !cache_path.is_dir()
            || fs::symlink_metadata(cache_path)
                .is_ok_and(|metadata| metadata.file_type().is_symlink())
        {
            return Err(DependencyError::new(format!(
                "{}: browser cache is missing",
                record.id
            )));
        }
        let mut candidates = Vec::new();
        for pattern in &record.verification.executable_globs {
            let full_pattern = cache_path.join(pattern).to_string_lossy().to_string();
            let paths =
                crate::path_resolution::python_glob_paths(&full_pattern).map_err(|error| {
                    DependencyError::new(format!(
                        "{}: browser executable glob is invalid: {error}",
                        record.id
                    ))
                })?;
            for candidate in paths {
                if candidate.is_symlink() || !candidate.is_file() || !is_executable(&candidate) {
                    continue;
                }
                let resolved = fs::canonicalize(&candidate)
                    .map_err(|error| DependencyError::new(error.to_string()))?;
                let root = fs::canonicalize(cache_path)
                    .map_err(|error| DependencyError::new(error.to_string()))?;
                if resolved.starts_with(root) {
                    candidates.push(candidate);
                }
            }
        }
        candidates.sort();
        let candidate = candidates.first().ok_or_else(|| {
            DependencyError::new(format!(
                "{}: browser executable is missing from cache",
                record.id
            ))
        })?;
        let mut argv = vec![candidate.to_string_lossy().to_string()];
        argv.extend(record.verification.args.iter().cloned());
        let mut variables = self.tool_paths(workspace, &BTreeMap::new())?;
        variables.insert("PLAYWRIGHT_BROWSERS_PATH".to_string(), cache.to_string());
        let output = self.capture(
            &argv,
            workspace,
            &variables,
            &record.id,
            "verify-browser-executable",
        )?;
        let token = record
            .verification
            .output_contains
            .as_deref()
            .ok_or_else(|| {
                DependencyError::new(format!("{}: browser output contract is missing", record.id))
            })?;
        require_output(&output, token, &record.id)
    }

    fn resolved_apt_package_version(
        &self,
        record: &DependencyRecord,
        payload: &Value,
    ) -> Result<Option<String>> {
        if record.method != Method::AptPackage || record.version.is_some() {
            return Ok(None);
        }
        let value = payload
            .get("resolved_package_version")
            .and_then(Value::as_str)
            .filter(|value| matches(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$", value))
            .ok_or_else(|| {
                DependencyError::new(format!(
                    "{}: resolved dpkg package version is missing or invalid",
                    record.id
                ))
            })?;
        Ok(Some(value.to_string()))
    }

    fn structural_bindings(
        &self,
        record: &DependencyRecord,
    ) -> Result<BTreeMap<String, ExecutableBinding>> {
        let mut bindings = BTreeMap::new();
        for executable in executable_binding_names(record, true) {
            let path = configured_executable_path(&self.probe, record, &executable, true)?;
            bindings.insert(
                executable.clone(),
                ExecutableBinding {
                    provided: executable.clone(),
                    lexical_path: path.to_string_lossy().to_string(),
                    absolute_path: path.to_string_lossy().to_string(),
                    verification_output: format!(
                        "{STRUCTURAL_BINDING_OUTPUT_PREFIX}:{}:{executable}",
                        record.method.as_str()
                    ),
                },
            );
        }
        Ok(bindings)
    }

    fn cargo_source(&self, record: &DependencyRecord, workspace: &Path) -> Result<PathBuf> {
        let source = crate::path_resolution::resolve_non_strict(&workspace.join(&record.source))
            .map_err(|error| {
                DependencyError::new(format!(
                    "{}: cannot resolve Cargo source: {error}",
                    record.id
                ))
            })?;
        if !source.starts_with(workspace) {
            return Err(DependencyError::new(format!(
                "{}: cargo source escapes workspace",
                record.id
            )));
        }
        if !source.is_dir() {
            return Err(DependencyError::new(format!(
                "{}: cargo source is missing: {}",
                record.id,
                source.display()
            )));
        }
        Ok(source)
    }

    fn cargo_snapshot(&self, source: &Path) -> Result<(String, String)> {
        let expected = CANONICAL_RUST_SOURCE_FILES
            .iter()
            .copied()
            .collect::<BTreeSet<_>>();
        for relative in CANONICAL_RUST_SOURCE_FILES {
            let path = source.join(relative);
            let metadata = fs::symlink_metadata(&path).map_err(|_| {
                DependencyError::new(format!("cargo source snapshot file is missing: {relative}"))
            })?;
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                return Err(DependencyError::new(format!(
                    "cargo source snapshot file is missing: {relative}"
                )));
            }
        }
        let mut actual = BTreeSet::new();
        let mut pending = vec![source.to_path_buf()];
        while let Some(directory) = pending.pop() {
            for entry in fs::read_dir(&directory).map_err(|error| {
                DependencyError::new(format!(
                    "cargo source snapshot directory is unreadable: {}: {error}",
                    directory.display()
                ))
            })? {
                let entry = entry.map_err(|error| DependencyError::new(error.to_string()))?;
                let path = entry.path();
                let relative = path
                    .strip_prefix(source)
                    .map_err(|_| DependencyError::new("Cargo snapshot path escaped source"))?;
                let relative_text = relative.to_string_lossy().replace('\\', "/");
                if relative.components().any(|component| {
                    component.as_os_str() == "target" || component.as_os_str() == ".git"
                }) {
                    continue;
                }
                let metadata = fs::symlink_metadata(&path).map_err(|error| {
                    DependencyError::new(format!(
                        "cargo source snapshot path is unreadable: {}: {error}",
                        path.display()
                    ))
                })?;
                if metadata.file_type().is_symlink() {
                    continue;
                }
                if metadata.is_dir() {
                    pending.push(path);
                } else if metadata.is_file() {
                    actual.insert(relative_text);
                }
            }
        }
        let expected_text = expected
            .into_iter()
            .map(str::to_string)
            .collect::<BTreeSet<_>>();
        if actual != expected_text {
            let missing = expected_text
                .difference(&actual)
                .cloned()
                .collect::<Vec<_>>();
            let extra = actual
                .difference(&expected_text)
                .cloned()
                .collect::<Vec<_>>();
            return Err(DependencyError::new(format!(
                "cargo source snapshot inventory mismatch: missing={missing:?} extra={extra:?}"
            )));
        }
        let mut digest = Sha256::new();
        for relative in CANONICAL_RUST_SOURCE_FILES {
            let bytes = fs::read(source.join(relative)).map_err(|error| {
                DependencyError::new(format!(
                    "cargo source snapshot file is unreadable: {relative}: {error}"
                ))
            })?;
            let blob = sha256_hex(&bytes);
            digest.update(relative.as_bytes());
            digest.update([0]);
            digest.update(blob.as_bytes());
            digest.update([0]);
        }
        let source_digest = format!("{:x}", digest.finalize());
        let lock_digest =
            sha256_hex(&fs::read(source.join("Cargo.lock")).map_err(|error| {
                DependencyError::new(format!("Cargo.lock is unreadable: {error}"))
            })?);
        Ok((source_digest, lock_digest))
    }

    fn verify_canonical_snapshot(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
    ) -> Result<(String, String)> {
        let source = self.cargo_source(record, workspace)?;
        let (source_digest, lock_digest) = self.cargo_snapshot(&source)?;
        if record
            .source_tree_sha256
            .as_deref()
            .is_some_and(|expected| expected != source_digest)
            || record.cargo_lock_sha256.as_deref() != Some(lock_digest.as_str())
        {
            return Err(DependencyError::new(format!(
                "{}: immutable source snapshot mismatch {source_digest}!={:?} or {lock_digest}!={:?}",
                record.id, record.source_tree_sha256, record.cargo_lock_sha256
            )));
        }
        Ok((source_digest, lock_digest))
    }

    fn cargo_source_identity(&self, record: &DependencyRecord, workspace: &Path) -> Result<String> {
        let commit = record.commit.as_deref().ok_or_else(|| {
            DependencyError::new(format!(
                "{}: active-source records have no Git source identity",
                record.id
            ))
        })?;
        let source = self.cargo_source(record, workspace)?;
        let output = Command::new("git")
            .args([
                "-C",
                source.to_string_lossy().as_ref(),
                "rev-parse",
                "--verify",
                "HEAD",
            ])
            .current_dir(workspace)
            .output()
            .map_err(|error| {
                DependencyError::new(format!(
                    "{}: cannot read cargo source commit from {}: {error}",
                    record.id,
                    source.display()
                ))
            })?;
        if !output.status.success() {
            return Err(DependencyError::new(format!(
                "{}: cannot read cargo source commit from {}",
                record.id,
                source.display()
            )));
        }
        let observed = String::from_utf8(output.stdout)
            .map_err(|error| {
                DependencyError::new(format!(
                    "{}: cargo source commit is not UTF-8: {error}",
                    record.id
                ))
            })?
            .trim()
            .to_ascii_lowercase();
        if observed.is_empty() {
            return Ok(commit.to_ascii_lowercase());
        }
        if !matches(r"^[0-9a-f]{40}$", &observed) {
            return Err(DependencyError::new(format!(
                "{}: cargo source identity is not a full commit: {observed:?}",
                record.id
            )));
        }
        if observed != commit.to_ascii_lowercase() {
            return Err(DependencyError::new(format!(
                "{}: cargo source commit mismatch {observed}!={commit}",
                record.id
            )));
        }
        Ok(observed)
    }

    fn cargo_binary_path(&self, record: &DependencyRecord, source: &Path) -> Result<PathBuf> {
        let relative = record.verification.path.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: cargo verification path is missing", record.id))
        })?;
        let path = Path::new(relative);
        let components = path.components().collect::<Vec<_>>();
        if path.is_absolute()
            || components.len() < 2
            || components[0].as_os_str() != "target"
            || components.iter().any(|part| {
                matches!(
                    part,
                    std::path::Component::ParentDir | std::path::Component::CurDir
                )
            })
        {
            return Err(DependencyError::new(format!(
                "{}: cargo binary path is unsafe",
                record.id
            )));
        }
        let target_root = if self.image_owned {
            env::var_os("AGENT_CANON_CARGO_TARGET_DIR").map(PathBuf::from)
        } else {
            None
        };
        let candidate = target_root
            .unwrap_or_else(|| source.to_path_buf())
            .join(path);
        crate::path_resolution::resolve_non_strict(&candidate).map_err(|error| {
            DependencyError::new(format!(
                "{}: cargo binary path is invalid: {error}",
                record.id
            ))
        })
    }

    fn install_rust_toolchain(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        repair: bool,
        variables: &BTreeMap<String, String>,
    ) -> Result<()> {
        let version = record.version.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: rust toolchain version is missing", record.id))
        })?;
        self.run(
            &[
                "/usr/local/bin/rustup-init".to_string(),
                "-y".to_string(),
                "--default-toolchain".to_string(),
                "none".to_string(),
                "--profile".to_string(),
                "minimal".to_string(),
                "--no-modify-path".to_string(),
            ],
            workspace,
            variables,
            false,
            &record.id,
            "install-rust-toolchain",
        )?;
        if repair && !self.image_owned {
            let list = self.capture(
                &[
                    "rustup".to_string(),
                    "toolchain".to_string(),
                    "list".to_string(),
                ],
                workspace,
                variables,
                &record.id,
                "verify-rust-installed",
            )?;
            let installed = list.stdout.lines().any(|line| {
                line.split_whitespace().next().is_some_and(|value| {
                    value == version || value.starts_with(&format!("{version}-"))
                })
            });
            if installed {
                self.run(
                    &[
                        "rustup".to_string(),
                        "toolchain".to_string(),
                        "uninstall".to_string(),
                        version.to_string(),
                    ],
                    workspace,
                    variables,
                    false,
                    &record.id,
                    "install-rust-toolchain",
                )?;
            }
        }
        self.run(
            &[
                "rustup".to_string(),
                "toolchain".to_string(),
                "install".to_string(),
                version.to_string(),
                "--profile".to_string(),
                "minimal".to_string(),
            ],
            workspace,
            variables,
            false,
            &record.id,
            "install-rust-toolchain",
        )?;
        if !record.components.is_empty() {
            let mut argv = vec![
                "rustup".to_string(),
                "component".to_string(),
                "add".to_string(),
            ];
            argv.extend(record.components.iter().cloned());
            argv.extend(["--toolchain".to_string(), version.to_string()]);
            self.run(
                &argv,
                workspace,
                variables,
                false,
                &record.id,
                "install-rust-toolchain",
            )?;
        }
        self.run(
            &[
                "rustup".to_string(),
                "default".to_string(),
                version.to_string(),
            ],
            workspace,
            variables,
            false,
            &record.id,
            "install-rust-toolchain",
        )
    }

    fn install_lean_toolchain(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        repair: bool,
        variables: &BTreeMap<String, String>,
    ) -> Result<()> {
        let version = record.version.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: Lean toolchain version is missing", record.id))
        })?;
        self.run(
            &[
                "/usr/local/bin/elan-init".to_string(),
                "-y".to_string(),
                "--default-toolchain".to_string(),
                version.to_string(),
                "--no-modify-path".to_string(),
            ],
            workspace,
            variables,
            false,
            &record.id,
            "install-lean-toolchain",
        )?;
        let list = self.capture(
            &[
                "elan".to_string(),
                "toolchain".to_string(),
                "list".to_string(),
            ],
            workspace,
            variables,
            &record.id,
            "verify-lean-installed",
        )?;
        let mut has_exact = list
            .stdout
            .lines()
            .any(|line| line.split_whitespace().next() == Some(version));
        if repair && has_exact {
            self.run(
                &[
                    "elan".to_string(),
                    "toolchain".to_string(),
                    "uninstall".to_string(),
                    version.to_string(),
                ],
                workspace,
                variables,
                false,
                &record.id,
                "install-lean-toolchain",
            )?;
            has_exact = false;
        }
        if !has_exact {
            self.run(
                &[
                    "elan".to_string(),
                    "toolchain".to_string(),
                    "install".to_string(),
                    version.to_string(),
                ],
                workspace,
                variables,
                false,
                &record.id,
                "install-lean-toolchain",
            )?;
        }
        self.run(
            &[
                "elan".to_string(),
                "default".to_string(),
                version.to_string(),
            ],
            workspace,
            variables,
            false,
            &record.id,
            "install-lean-toolchain",
        )
    }

    fn install_cargo_source(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        base_env: &BTreeMap<String, String>,
    ) -> Result<()> {
        let source = self.cargo_source(record, workspace)?;
        if record.source_identity.as_deref() == Some(CANONICAL_SNAPSHOT_IDENTITY) {
            self.verify_canonical_snapshot(record, workspace)?;
        }
        let source_before = if record.commit.is_some() {
            Some(self.cargo_source_identity(record, workspace)?)
        } else {
            None
        };
        let mut variables = base_env.clone();
        let target = if self.image_owned {
            env::var_os("AGENT_CANON_CARGO_TARGET_DIR").map(PathBuf::from)
        } else {
            None
        };
        let target = target.unwrap_or_else(|| source.join("target"));
        variables.insert(
            "CARGO_TARGET_DIR".to_string(),
            target.to_string_lossy().to_string(),
        );
        self.run(
            &[
                "cargo".to_string(),
                "build".to_string(),
                "--release".to_string(),
                "--locked".to_string(),
                "--manifest-path".to_string(),
                source.join("Cargo.toml").to_string_lossy().to_string(),
            ],
            workspace,
            &variables,
            false,
            &record.id,
            "install-cargo-source-build",
        )?;
        if let Some(before) = source_before {
            let after = self.cargo_source_identity(record, workspace)?;
            if before != after {
                return Err(DependencyError::new(format!(
                    "{}: source identity changed during build {before}!={after}",
                    record.id
                )));
            }
        }
        if record.source_identity.as_deref() == Some(CANONICAL_SNAPSHOT_IDENTITY) {
            self.verify_canonical_snapshot(record, workspace)?;
        }
        Ok(())
    }

    fn install_browser(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        variables: &BTreeMap<String, String>,
    ) -> Result<()> {
        let browser = record
            .browser
            .as_deref()
            .ok_or_else(|| DependencyError::new(format!("{}: browser is missing", record.id)))?;
        let cache = record.browser_cache_path.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: browser cache path is missing", record.id))
        })?;
        let cache_path = Path::new(cache);
        if fs::symlink_metadata(cache_path)
            .is_ok_and(|metadata| metadata.file_type().is_symlink() || !metadata.is_dir())
        {
            return Err(DependencyError::new(format!(
                "{}: browser cache path is not a directory",
                record.id
            )));
        }
        self.run(
            &[
                "install".to_string(),
                "-d".to_string(),
                "-m".to_string(),
                "0775".to_string(),
                cache.to_string(),
            ],
            workspace,
            variables,
            true,
            &record.id,
            "install-browser",
        )?;
        self.run(
            &[
                "env".to_string(),
                format!("PLAYWRIGHT_BROWSERS_PATH={cache}"),
                "playwright".to_string(),
                "install".to_string(),
                "--with-deps".to_string(),
                browser.to_string(),
            ],
            workspace,
            variables,
            true,
            &record.id,
            "install-browser",
        )
    }

    fn publish_final_binary(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        final_binary_dir: &Path,
    ) -> Result<PathBuf> {
        if !self.image_owned || record.method != Method::CargoSourceBuild {
            return Err(DependencyError::new(format!(
                "{}: final binary publication is image Cargo-only",
                record.id
            )));
        }
        let final_dir =
            crate::path_resolution::resolve_non_strict(final_binary_dir).map_err(|error| {
                DependencyError::new(format!(
                    "{}: final binary directory is invalid: {error}",
                    record.id
                ))
            })?;
        if final_dir != Path::new("/usr/local/bin") {
            return Err(DependencyError::new(format!(
                "{}: final binary directory is not the image PATH",
                record.id
            )));
        }
        let source = self.cargo_source(record, workspace)?;
        let binary = self.cargo_binary_path(record, &source)?;
        if !binary.is_file() || !is_executable(&binary) {
            return Err(DependencyError::new(format!(
                "{}: Cargo build binary is missing: {}",
                record.id,
                binary.display()
            )));
        }
        let name = Path::new(record.verification.path.as_deref().unwrap_or_default())
            .file_name()
            .and_then(|value| value.to_str())
            .filter(|value| !value.is_empty() && *value != "." && *value != "..")
            .ok_or_else(|| {
                DependencyError::new(format!("{}: final binary name is unsafe", record.id))
            })?;
        let final_binary = final_dir.join(name);
        let variables = self.tool_paths(workspace, &BTreeMap::new())?;
        let argv = vec![
            "install".to_string(),
            "-m".to_string(),
            "0555".to_string(),
            binary.to_string_lossy().to_string(),
            final_binary.to_string_lossy().to_string(),
        ];
        self.run(
            &argv,
            workspace,
            &variables,
            true,
            &record.id,
            "install-cargo-source-build",
        )?;
        Ok(final_binary)
    }

    fn verify_cargo_binary(
        &self,
        record: &DependencyRecord,
        payload: Option<&Value>,
        workspace: &Path,
    ) -> Result<()> {
        if record.source_identity.as_deref() == Some(CANONICAL_SNAPSHOT_IDENTITY) {
            self.verify_canonical_snapshot(record, workspace)?;
        }
        if record.commit.is_some() {
            self.cargo_source_identity(record, workspace)?;
        }
        let source = self.cargo_source(record, workspace)?;
        let binary = self.cargo_binary_path(record, &source)?;
        let configured_target = if self.image_owned {
            env::var_os("AGENT_CANON_CARGO_TARGET_DIR").map(PathBuf::from)
        } else {
            None
        };
        let allowed_root = configured_target.unwrap_or_else(|| source.join("target"));
        if !binary.starts_with(&allowed_root) {
            return Err(DependencyError::new(format!(
                "{}: cargo binary escapes its target",
                record.id
            )));
        }
        if !binary.is_file() || !is_executable(&binary) {
            return Err(DependencyError::new(format!(
                "{}: cargo binary is missing: {}",
                record.id,
                binary.display()
            )));
        }
        if self.image_owned {
            let payload = payload.ok_or_else(|| {
                DependencyError::new(format!("{}: Cargo image receipt is missing", record.id))
            })?;
            self.verify_final_binary_receipt(payload, record)?;
        }
        let token = record
            .verification
            .output_contains
            .as_deref()
            .ok_or_else(|| {
                DependencyError::new(format!(
                    "{}: cargo executable output contract is missing",
                    record.id
                ))
            })?;
        let mut argv = vec![binary.to_string_lossy().to_string()];
        argv.extend(record.verification.args.iter().cloned());
        let variables = self.tool_paths(workspace, &BTreeMap::new())?;
        let output = self.capture(
            &argv,
            workspace,
            &variables,
            &record.id,
            "verify-cargo-binary",
        )?;
        require_output(&output, token, &record.id)
    }

    fn install_record(
        &mut self,
        record: &DependencyRecord,
        workspace: &Path,
        repair: bool,
    ) -> Result<()> {
        self.active_method = Some(record.method);
        let base_env = self.tool_paths(workspace, &BTreeMap::new())?;
        match record.method {
            Method::AptPackage => {
                let package = record.version.as_ref().map_or_else(
                    || record.package.clone(),
                    |version| format!("{}={version}", record.package),
                );
                let mut argv = vec![
                    "apt-get".to_string(),
                    "install".to_string(),
                    "-y".to_string(),
                    "--no-install-recommends".to_string(),
                    "--no-remove".to_string(),
                    package,
                ];
                if repair {
                    argv.insert(2, "--reinstall".to_string());
                }
                self.run(
                    &argv,
                    workspace,
                    &base_env,
                    true,
                    &record.id,
                    "install-apt-package",
                )?;
            }
            Method::AptRepository => {
                self.install_apt_repository(record, workspace, repair, &base_env)?;
                if repository_package_payload(record)?.is_null() {
                    let version = record.version.as_deref().ok_or_else(|| {
                        DependencyError::new(format!(
                            "{}: apt repository package version is missing",
                            record.id
                        ))
                    })?;
                    let mut argv = vec![
                        "apt-get".to_string(),
                        "install".to_string(),
                        "-y".to_string(),
                        "--no-install-recommends".to_string(),
                        "--no-remove".to_string(),
                        format!("{}={version}", record.package),
                    ];
                    if repair {
                        argv.insert(2, "--reinstall".to_string());
                    }
                    self.run(
                        &argv,
                        workspace,
                        &base_env,
                        true,
                        &record.id,
                        "install-apt-repository",
                    )?;
                }
            }
            Method::NpmGlobal => {
                let version = record.version.as_deref().ok_or_else(|| {
                    DependencyError::new(format!("{}: npm version is missing", record.id))
                })?;
                let argv = vec![
                    NPM_ENV_EXECUTABLE.to_string(),
                    format!("PATH={NPM_SYSTEM_PATH}"),
                    "/usr/bin/npm".to_string(),
                    "install".to_string(),
                    "--force".to_string(),
                    "--global".to_string(),
                    "--prefix".to_string(),
                    NPM_GLOBAL_PREFIX.to_string(),
                    format!("{}@{version}", record.package),
                ];
                self.run(
                    &argv,
                    workspace,
                    &base_env,
                    true,
                    &record.id,
                    "install-npm-global",
                )?;
            }
            Method::Pipx => {
                let version = record.version.as_deref().ok_or_else(|| {
                    DependencyError::new(format!("{}: pipx version is missing", record.id))
                })?;
                let mut argv = vec![
                    "pipx".to_string(),
                    "install".to_string(),
                    "--index-url".to_string(),
                    record.source.clone(),
                    format!("{}=={version}", record.package),
                ];
                if repair {
                    argv.insert(2, "--force".to_string());
                }
                self.run(
                    &argv,
                    workspace,
                    &base_env,
                    false,
                    &record.id,
                    "install-pipx",
                )?;
            }
            Method::ReleaseAsset => {
                self.install_release_asset(record, workspace, repair, &base_env)?
            }
            Method::RustToolchain => {
                self.install_rust_toolchain(record, workspace, repair, &base_env)?
            }
            Method::LeanToolchain => {
                self.install_lean_toolchain(record, workspace, repair, &base_env)?
            }
            Method::CargoSourceBuild => self.install_cargo_source(record, workspace, &base_env)?,
            Method::BrowserInstall => self.install_browser(record, workspace, &base_env)?,
        }
        Ok(())
    }

    fn install_apt_repository(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        repair: bool,
        variables: &BTreeMap<String, String>,
    ) -> Result<()> {
        let key_url = record.key_url.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: repository key URL is missing", record.id))
        })?;
        let expected_fingerprint = record.key_fingerprint.as_deref().ok_or_else(|| {
            DependencyError::new(format!(
                "{}: repository key fingerprint is missing",
                record.id
            ))
        })?;
        let temporary = tempfile::Builder::new()
            .prefix(&format!("agent-canon-{}-", record.id))
            .tempdir_in(self.temporary_parent(workspace, "apt-repository")?)
            .map_err(|error| {
                DependencyError::new(format!(
                    "{}: apt repository staging failed: {error}",
                    record.id
                ))
            })?;
        let raw_key = temporary.path().join("key.raw");
        let keyring = temporary.path().join(format!("{}.gpg", record.id));
        self.download(key_url, &raw_key, workspace, &record.id, "download-apt-key")?;
        let fingerprint = self.capture(
            &[
                "gpg".to_string(),
                "--show-keys".to_string(),
                "--with-colons".to_string(),
                raw_key.to_string_lossy().to_string(),
            ],
            workspace,
            variables,
            &record.id,
            "verify-apt-repository-key",
        )?;
        let observed = fingerprint
            .stdout
            .lines()
            .filter_map(|line| {
                let fields = line.split(':').collect::<Vec<_>>();
                (fields.first() == Some(&"fpr") && fields.len() > 9)
                    .then(|| fields[9].to_ascii_uppercase())
            })
            .collect::<BTreeSet<_>>();
        if !observed.contains(&expected_fingerprint.to_ascii_uppercase()) {
            return Err(DependencyError::new(format!(
                "{}: apt key fingerprint mismatch",
                record.id
            )));
        }
        self.run(
            &[
                "gpg".to_string(),
                "--dearmor".to_string(),
                "--output".to_string(),
                keyring.to_string_lossy().to_string(),
                raw_key.to_string_lossy().to_string(),
            ],
            workspace,
            variables,
            false,
            &record.id,
            "install-apt-repository-key",
        )?;
        let key_destination = PathBuf::from("/etc/apt/keyrings").join(format!("{}.gpg", record.id));
        self.run(
            &[
                "install".to_string(),
                "-D".to_string(),
                "-m".to_string(),
                "0644".to_string(),
                keyring.to_string_lossy().to_string(),
                key_destination.to_string_lossy().to_string(),
            ],
            workspace,
            variables,
            true,
            &record.id,
            "install-apt-repository-key",
        )?;
        let suite = record.repository_suite.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: repository suite is not declared", record.id))
        })?;
        let source_line = format!(
            "deb [signed-by={}] {} {} {}\n",
            key_destination.display(),
            record.source,
            suite,
            record.repository_components.join(" ")
        );
        self.verify_repository_packages_digest(record, workspace, temporary.path())?;
        let source_path = temporary.path().join("repository.list");
        fs::write(&source_path, source_line).map_err(|error| {
            DependencyError::new(format!(
                "{}: apt repository source could not be staged: {error}",
                record.id
            ))
        })?;
        let source_destination =
            PathBuf::from("/etc/apt/sources.list.d").join(format!("{}.list", record.id));
        self.run(
            &[
                "install".to_string(),
                "-D".to_string(),
                "-m".to_string(),
                "0644".to_string(),
                source_path.to_string_lossy().to_string(),
                source_destination.to_string_lossy().to_string(),
            ],
            workspace,
            variables,
            true,
            &record.id,
            "install-apt-repository-source",
        )?;
        self.run(
            &["apt-get".to_string(), "update".to_string()],
            workspace,
            variables,
            true,
            &record.id,
            "install-apt-repository",
        )?;
        if let Some((url, checksum)) = repository_package_identity(record)? {
            let filename = repository_package_filename(record, &url)?;
            let package_path = temporary.path().join(filename);
            self.download(
                &url,
                &package_path,
                workspace,
                &record.id,
                "download-apt-package",
            )?;
            let observed = sha256_hex(&fs::read(&package_path).map_err(|error| {
                DependencyError::new(format!("{}: apt package read failed: {error}", record.id))
            })?);
            if observed != checksum {
                return Err(DependencyError::new(format!(
                    "{}: immutable apt package SHA256 mismatch {observed}!={checksum}",
                    record.id
                )));
            }
            let mut argv = vec![
                "apt-get".to_string(),
                "install".to_string(),
                "-y".to_string(),
                "--no-install-recommends".to_string(),
                "--no-remove".to_string(),
                package_path.to_string_lossy().to_string(),
            ];
            if repair {
                argv.insert(2, "--reinstall".to_string());
            }
            self.run(
                &argv,
                workspace,
                variables,
                true,
                &record.id,
                "install-apt-repository",
            )?;
        }
        Ok(())
    }

    fn verify_repository_packages_digest(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        temporary: &Path,
    ) -> Result<()> {
        let payload = repository_packages_payload(record)?;
        let Some(url) = payload.get("url").and_then(Value::as_str) else {
            return Ok(());
        };
        let checksum = payload
            .get("sha256")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                DependencyError::new(format!("{}: Packages index SHA256 is missing", record.id))
            })?;
        let path = temporary.join(format!("{}-Packages", record.id));
        self.download(url, &path, workspace, &record.id, "download-packages-index")
            .map_err(|error| {
                DependencyError::new(format!(
                    "{}: Packages index download failed: {url}: {error}",
                    record.id
                ))
            })?;
        let observed = sha256_hex(&fs::read(&path).map_err(|error| {
            DependencyError::new(format!(
                "{}: Packages index read failed: {url}: {error}",
                record.id
            ))
        })?);
        let _ = fs::remove_file(&path);
        if observed != checksum {
            return Err(DependencyError::new(format!(
                "{}: Packages index SHA256 mismatch {observed}!={checksum} ({url})",
                record.id
            )));
        }
        Ok(())
    }

    fn install_release_asset(
        &self,
        record: &DependencyRecord,
        workspace: &Path,
        repair: bool,
        variables: &BTreeMap<String, String>,
    ) -> Result<()> {
        let destination = record.destination.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: release destination is missing", record.id))
        })?;
        let architecture = release_asset_architecture();
        let asset = if record.assets.is_empty() {
            record.asset.clone().ok_or_else(|| {
                DependencyError::new(format!("{}: release asset is missing", record.id))
            })?
        } else {
            record
                .assets
                .iter()
                .find(|(key, _)| key == &architecture)
                .map(|(_, value)| value.clone())
                .ok_or_else(|| {
                    DependencyError::new(format!(
                        "{}: no release asset for architecture {architecture}",
                        record.id
                    ))
                })?
        };
        validate_safe_asset_path(&asset, &format!("{}.asset", record.id))?;
        let url = if record.source.ends_with(&asset) {
            record.source.clone()
        } else {
            format!("{}/{}", record.source.trim_end_matches('/'), asset)
        };
        let temporary = tempfile::Builder::new()
            .prefix(&format!("agent-canon-{}-", record.id))
            .tempdir_in(self.temporary_parent(workspace, "release-asset")?)
            .map_err(|error| {
                DependencyError::new(format!("{}: release staging failed: {error}", record.id))
            })?;
        let archive = temporary.path().join(&asset);
        if let Some(parent) = archive.parent() {
            fs::create_dir_all(parent).map_err(|error| {
                DependencyError::new(format!("{}: release staging failed: {error}", record.id))
            })?;
        }
        self.download(
            &url,
            &archive,
            workspace,
            &record.id,
            "download-release-asset",
        )?;
        let checksum = if record.checksums.is_empty() {
            record.checksum.as_deref().ok_or_else(|| {
                DependencyError::new(format!("{}: release checksum is missing", record.id))
            })?
        } else {
            record
                .checksums
                .iter()
                .find(|(key, _)| key == &architecture)
                .map(|(_, value)| value.as_str())
                .ok_or_else(|| {
                    DependencyError::new(format!(
                        "{}: no release checksum for architecture {architecture}",
                        record.id
                    ))
                })?
        };
        let observed = sha256_hex(&fs::read(&archive).map_err(|error| {
            DependencyError::new(format!(
                "{}: release asset is unreadable: {error}",
                record.id
            ))
        })?);
        if observed != checksum {
            return Err(DependencyError::new(format!(
                "{}: release checksum mismatch",
                record.id
            )));
        }
        let candidate = if record.extract.as_deref() == Some("none") {
            archive.clone()
        } else {
            let extracted = temporary.path().join("extract");
            safe_extract_archive(
                &archive,
                &extracted,
                record.archive_format.as_deref().unwrap_or_default(),
            )?;
            let expected = extracted.join(destination.trim_start_matches('/'));
            if expected.is_file()
                && !fs::symlink_metadata(&expected)
                    .is_ok_and(|metadata| metadata.file_type().is_symlink())
            {
                expected
            } else {
                let name = Path::new(destination)
                    .file_name()
                    .and_then(|value| value.to_str())
                    .unwrap_or_default();
                let matches = find_regular_named(&extracted, name)?;
                if matches.len() != 1 {
                    return Err(DependencyError::new(format!(
                        "{}: extracted destination not found",
                        record.id
                    )));
                }
                matches[0].clone()
            }
        };
        if record.archive_format.as_deref() == Some("deb") {
            let mut argv = vec![
                "apt-get".to_string(),
                "install".to_string(),
                "-y".to_string(),
                "--no-install-recommends".to_string(),
                "--no-remove".to_string(),
                candidate.to_string_lossy().to_string(),
            ];
            if repair {
                argv.insert(2, "--reinstall".to_string());
            }
            self.run(
                &argv,
                workspace,
                variables,
                true,
                &record.id,
                "install-release-asset",
            )
        } else {
            self.run(
                &[
                    "install".to_string(),
                    "-D".to_string(),
                    "-m".to_string(),
                    "0755".to_string(),
                    candidate.to_string_lossy().to_string(),
                    destination.to_string(),
                ],
                workspace,
                variables,
                true,
                &record.id,
                "install-release-asset",
            )
        }
    }

    fn temporary_parent(&self, workspace: &Path, purpose: &str) -> Result<PathBuf> {
        if self.image_owned {
            return Ok(PathBuf::from("/tmp"));
        }
        let runtime = env::var_os("AGENT_CANON_RUNTIME_ROOT")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .ok_or_else(|| {
                DependencyError::new(format!("dependency-{purpose}: runtime_root_required"))
            })?;
        crate::runtime_boundary::RuntimeArtifactBoundary::for_source(
            workspace,
            Some(&runtime),
            true,
        )
        .map_err(|error| {
            DependencyError::new(format!(
                "dependency-{purpose}: runtime_root_invalid:{error}"
            ))
        })?
        .ensure_directory(&Path::new("tmp").join("dependencies").join(purpose))
        .map_err(|error| {
            DependencyError::new(format!(
                "dependency-{purpose}: runtime_root_invalid:{error}"
            ))
        })
    }

    fn write_receipt(
        &self,
        path: &Path,
        plan: &DependencyPlan,
        record: &DependencyRecord,
        source_identity: Option<&str>,
        bindings: &BTreeMap<String, ExecutableBinding>,
        final_binary_path: Option<&Path>,
    ) -> Result<()> {
        let bindings_payload = bindings
            .iter()
            .map(|(name, binding)| {
                (
                    name.clone(),
                    json!({
                        "provided": binding.provided,
                        "lexical_path": binding.lexical_path,
                        "absolute_path": binding.absolute_path,
                        "verification_output": binding.verification_output,
                    }),
                )
            })
            .collect::<serde_json::Map<_, _>>();
        let mut payload = json!({
            "schema": RECEIPT_SCHEMA,
            "status": if self.image_owned { "installed" } else { "pass" },
            "owner": "image-installer",
            "phase": "image-install",
            "record_id": record.id,
            "manifest_version": record.version,
            "record_fingerprint": record.fingerprint()?,
            "plan_fingerprint": plan.fingerprint,
            "verification": record.verification.payload(),
            "source_identity": source_identity,
            "executable_bindings": bindings_payload,
        });
        let fields = payload
            .as_object_mut()
            .expect("receipt payload is an object");
        if record.method == Method::AptPackage && record.version.is_none() {
            let version = self
                .resolved_package_versions
                .get(&record.id)
                .ok_or_else(|| {
                    DependencyError::new(format!(
                        "{}: unpinned apt package lacks observed dpkg version",
                        record.id
                    ))
                })?;
            fields.insert(
                "resolved_package_version".to_string(),
                Value::String(version.clone()),
            );
        }
        let repository_packages = repository_packages_payload(record)?;
        if !repository_packages.is_null() {
            fields.insert("repository_packages".to_string(), repository_packages);
        }
        let repository_package = repository_package_payload(record)?;
        if !repository_package.is_null() {
            fields.insert("repository_package".to_string(), repository_package);
        }
        if record.method == Method::CargoSourceBuild
            && record.source_identity.as_deref() == Some(CANONICAL_SNAPSHOT_IDENTITY)
        {
            let workspace = self
                .install_workspace
                .as_deref()
                .ok_or_else(|| DependencyError::new("Cargo receipt lacks an install workspace"))?;
            let source = self.cargo_source(record, workspace)?;
            let (source_digest, lock_digest) = self.cargo_snapshot(&source)?;
            let binary = self.cargo_binary_path(record, &source)?;
            let binary_path = final_binary_path.unwrap_or(&binary);
            let binary_bytes = fs::read(&binary).map_err(|error| {
                DependencyError::new(format!(
                    "{}: Cargo build binary is unreadable: {error}",
                    record.id
                ))
            })?;
            fields.insert(
                "source_tree_sha256".to_string(),
                Value::String(source_digest),
            );
            fields.insert("cargo_lock_sha256".to_string(), Value::String(lock_digest));
            fields.insert(
                "binary_path".to_string(),
                Value::String(binary_path.to_string_lossy().to_string()),
            );
            fields.insert(
                "binary_sha256".to_string(),
                Value::String(sha256_hex(&binary_bytes)),
            );
            fields.insert(
                "rustup_init_version".to_string(),
                Value::String(RUSTUP_INIT_VERSION.to_string()),
            );
            fields.insert(
                "rustup_init_sha256".to_string(),
                Value::String(RUSTUP_INIT_SHA256.to_string()),
            );
            if final_binary_path.is_some() {
                fields.insert(
                    "build_binary_path".to_string(),
                    Value::String(binary.to_string_lossy().to_string()),
                );
            }
        }
        let mut bytes = serde_json::to_vec_pretty(&payload).map_err(|error| {
            DependencyError::new(format!("serialize dependency receipt: {error}"))
        })?;
        bytes.push(b'\n');
        if self.image_owned {
            let image_root = self.image_owned_root.as_deref().ok_or_else(|| {
                DependencyError::new("image-owned receipt publication lacks an image root")
            })?;
            let parent = crate::path_resolution::resolve_non_strict(
                path.parent()
                    .ok_or_else(|| DependencyError::new("dependency receipt has no parent"))?,
            )
            .map_err(|error| {
                DependencyError::new(format!("image receipt parent is invalid: {error}"))
            })?;
            if !parent.starts_with(image_root) {
                return Err(DependencyError::new("image-owned receipt escaped its root"));
            }
            fs::create_dir_all(&parent).map_err(|error| {
                DependencyError::new(format!("image receipt directory is unavailable: {error}"))
            })?;
            fs::write(path, bytes).map_err(|error| {
                DependencyError::new(format!("image receipt could not be written: {error}"))
            })?;
            return Ok(());
        }
        let attested = self.parent_attestation.as_ref().ok_or_else(|| {
            DependencyError::new("parent-root-attestation is required before receipt publication")
        })?;
        let purpose = NonEmptyTrimmedString::new("dependency-receipt")
            .map_err(|error| DependencyError::new(error.to_string()))?;
        attested
            .write_parent_owned_file(path, &bytes, purpose)
            .map_err(|error| {
                DependencyError::new(format!(
                    "parent-root-receipt:{}:{}",
                    error.reject,
                    error.detail()
                ))
            })?;
        Ok(())
    }

    fn verify_installed_receipt(
        &self,
        record: &DependencyRecord,
        payload: &Value,
        workspace: &Path,
    ) -> Result<()> {
        let raw_bindings = payload
            .get("executable_bindings")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                DependencyError::new(format!(
                    "{}: installed executable bindings are stale",
                    record.id
                ))
            })?;
        let bindings = raw_bindings
            .iter()
            .map(|(name, value)| Ok((name.clone(), ExecutableBinding::from_receipt(value, name)?)))
            .collect::<Result<BTreeMap<_, _>>>()?;
        if record.verification.kind == VerificationKind::CargoBinary {
            self.verify_cargo_binary(record, Some(payload), workspace)?;
            return Ok(());
        }
        verify_installed_receipt(&self.probe, record, payload, &bindings, workspace)?;
        Ok(())
    }

    fn verify_final_binary_receipt(
        &self,
        payload: &Value,
        record: &DependencyRecord,
    ) -> Result<()> {
        let spec_path = record.verification.path.as_deref().ok_or_else(|| {
            DependencyError::new(format!("{}: Cargo verification path is missing", record.id))
        })?;
        let name = Path::new(spec_path)
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or_else(|| {
                DependencyError::new(format!("{}: Cargo final binary path is invalid", record.id))
            })?;
        let expected = Path::new("/usr/local/bin").join(name);
        let final_value = payload
            .get("binary_path")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                DependencyError::new(format!(
                    "{}: final binary receipt binding is malformed",
                    record.id
                ))
            })?;
        let digest = payload
            .get("binary_sha256")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                DependencyError::new(format!(
                    "{}: final binary receipt binding is malformed",
                    record.id
                ))
            })?;
        if final_value != expected.to_string_lossy() || !is_hex(digest, 64) {
            return Err(DependencyError::new(format!(
                "{}: final binary receipt binding is malformed",
                record.id
            )));
        }
        let path = Path::new(final_value);
        if !path.is_file() || !is_executable(path) {
            return Err(DependencyError::new(format!(
                "{}: final image binary is missing: {final_value}",
                record.id
            )));
        }
        let observed =
            sha256_hex(&fs::read(path).map_err(|error| DependencyError::new(error.to_string()))?);
        if observed != digest {
            return Err(DependencyError::new(format!(
                "{}: final binary digest mismatch {observed}!={digest}",
                record.id
            )));
        }
        Ok(())
    }

    fn download(
        &self,
        url: &str,
        destination: &Path,
        workspace: &Path,
        record_id: &str,
        operation: &str,
    ) -> Result<()> {
        validate_url(url, &format!("{record_id}.{operation}"), false)?;
        let variables = self.tool_paths(workspace, &BTreeMap::new())?;
        let allowed_protocol = if url.starts_with("file://") {
            "=file"
        } else {
            "=https"
        };
        let argv = vec![
            "curl".to_string(),
            "--fail".to_string(),
            "--location".to_string(),
            "--silent".to_string(),
            "--show-error".to_string(),
            "--proto".to_string(),
            allowed_protocol.to_string(),
            "--proto-redir".to_string(),
            allowed_protocol.to_string(),
            "--output".to_string(),
            destination.to_string_lossy().to_string(),
            url.to_string(),
        ];
        self.run(&argv, workspace, &variables, false, record_id, operation)
    }
}

fn repository_package_identity(record: &DependencyRecord) -> Result<Option<(String, String)>> {
    let payload = repository_package_payload(record)?;
    if payload.is_null() {
        return Ok(None);
    }
    let object = payload.as_object().ok_or_else(|| {
        DependencyError::new(format!(
            "{}: repository package identity is malformed",
            record.id
        ))
    })?;
    let url = object.get("url").and_then(Value::as_str).ok_or_else(|| {
        DependencyError::new(format!("{}: repository package URL is missing", record.id))
    })?;
    let checksum = object
        .get("sha256")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            DependencyError::new(format!(
                "{}: repository package checksum is missing",
                record.id
            ))
        })?;
    Ok(Some((url.to_string(), checksum.to_string())))
}

fn repository_package_filename(record: &DependencyRecord, url: &str) -> Result<String> {
    let path = url.split(['?', '#']).next().unwrap_or_default();
    let filename = path.rsplit('/').next().unwrap_or_default();
    if !matches(r"^[A-Za-z0-9][A-Za-z0-9.+_~-]*\.deb$", filename) {
        return Err(DependencyError::new(format!(
            "{}: immutable apt package URL has an unsafe filename",
            record.id
        )));
    }
    Ok(filename.to_string())
}

fn validate_safe_asset_path(value: &str, field: &str) -> Result<()> {
    let path = Path::new(value);
    if path.is_absolute() || value.is_empty() || value.contains('\\') || value.starts_with('/') {
        return Err(DependencyError::new(format!(
            "{field} must be a safe relative asset path"
        )));
    }
    for component in path.components() {
        let std::path::Component::Normal(component) = component else {
            return Err(DependencyError::new(format!(
                "{field} must be a safe relative asset path"
            )));
        };
        let component = component.to_string_lossy();
        if !matches(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", &component) {
            return Err(DependencyError::new(format!(
                "{field} has an unsupported asset path"
            )));
        }
    }
    Ok(())
}

fn safe_archive_target(root: &Path, member: &Path) -> Result<PathBuf> {
    let root = fs::canonicalize(root).map_err(|error| {
        DependencyError::new(format!("archive extraction root is unavailable: {error}"))
    })?;
    let candidate =
        crate::path_resolution::resolve_non_strict(&root.join(member)).map_err(|error| {
            DependencyError::new(format!("archive member path is invalid: {error}"))
        })?;
    if !candidate.starts_with(&root) {
        return Err(DependencyError::new(format!(
            "archive member escapes extraction root: {}",
            member.display()
        )));
    }
    Ok(candidate)
}

fn safe_extract_archive(archive: &Path, destination: &Path, format: &str) -> Result<()> {
    fs::create_dir_all(destination).map_err(|error| {
        DependencyError::new(format!("archive extraction root is unavailable: {error}"))
    })?;
    match format {
        "zip" => safe_extract_zip(archive, destination),
        "tar" => safe_extract_tar_reader(
            fs::File::open(archive)
                .map_err(|error| DependencyError::new(format!("archive is unreadable: {error}")))?,
            destination,
        ),
        "tar.gz" | "tar.xz" | "tar.bz2" => {
            let temp_dir = tempfile::Builder::new()
                .prefix("agent-canon-archive-")
                .tempdir_in(destination.parent().unwrap_or_else(|| Path::new("/tmp")))
                .map_err(|error| {
                    DependencyError::new(format!("archive staging is unavailable: {error}"))
                })?;
            let tar_path = temp_dir.path().join("payload.tar");
            match format {
                "tar.gz" => {
                    let source = fs::File::open(archive).map_err(|error| {
                        DependencyError::new(format!("archive is unreadable: {error}"))
                    })?;
                    let mut decoder = flate2::read::GzDecoder::new(source);
                    let mut target = fs::File::create(&tar_path).map_err(|error| {
                        DependencyError::new(format!("archive staging failed: {error}"))
                    })?;
                    std::io::copy(&mut decoder, &mut target).map_err(|error| {
                        DependencyError::new(format!("archive decompression failed: {error}"))
                    })?;
                }
                "tar.bz2" => {
                    let source = fs::File::open(archive).map_err(|error| {
                        DependencyError::new(format!("archive is unreadable: {error}"))
                    })?;
                    let mut decoder = bzip2::read::BzDecoder::new(source);
                    let mut target = fs::File::create(&tar_path).map_err(|error| {
                        DependencyError::new(format!("archive staging failed: {error}"))
                    })?;
                    std::io::copy(&mut decoder, &mut target).map_err(|error| {
                        DependencyError::new(format!("archive decompression failed: {error}"))
                    })?;
                }
                "tar.xz" => {
                    let output = fs::File::create(&tar_path).map_err(|error| {
                        DependencyError::new(format!("archive staging failed: {error}"))
                    })?;
                    let status = Command::new("xz")
                        .args(["--decompress", "--stdout"])
                        .arg(archive)
                        .stdout(std::process::Stdio::from(output))
                        .status()
                        .map_err(|error| {
                            DependencyError::new(format!("xz command failed to start: {error}"))
                        })?;
                    if !status.success() {
                        return Err(DependencyError::new(format!(
                            "xz archive decompression failed with {status}"
                        )));
                    }
                }
                _ => unreachable!(),
            }
            safe_extract_tar_reader(
                fs::File::open(&tar_path).map_err(|error| {
                    DependencyError::new(format!("archive staging is unreadable: {error}"))
                })?,
                destination,
            )
        }
        other => Err(DependencyError::new(format!(
            "unsupported archive format: {other}"
        ))),
    }
}

fn safe_extract_tar_reader<R: std::io::Read>(reader: R, destination: &Path) -> Result<()> {
    let mut archive = tar::Archive::new(reader);
    let entries = archive
        .entries()
        .map_err(|error| DependencyError::new(format!("archive is unreadable: {error}")))?;
    for entry in entries {
        let mut entry = entry.map_err(|error| {
            DependencyError::new(format!("archive member is unreadable: {error}"))
        })?;
        let member = entry
            .path()
            .map_err(|error| {
                DependencyError::new(format!("archive member path is unreadable: {error}"))
            })?
            .into_owned();
        let target = safe_archive_target(destination, &member)?;
        let kind = entry.header().entry_type();
        if kind.is_dir() {
            fs::create_dir_all(&target).map_err(|error| {
                DependencyError::new(format!("archive directory could not be created: {error}"))
            })?;
            continue;
        }
        if !kind.is_file() {
            return Err(DependencyError::new(format!(
                "unsafe archive member: {}",
                member.display()
            )));
        }
        let parent = target
            .parent()
            .ok_or_else(|| DependencyError::new("archive member has no parent"))?;
        fs::create_dir_all(parent).map_err(|error| {
            DependencyError::new(format!("archive directory could not be created: {error}"))
        })?;
        let mut output = fs::File::create(&target).map_err(|error| {
            DependencyError::new(format!("archive member could not be created: {error}"))
        })?;
        std::io::copy(&mut entry, &mut output).map_err(|error| {
            DependencyError::new(format!("archive member could not be copied: {error}"))
        })?;
        if let Ok(mode) = entry.header().mode() {
            set_image_mode(&target, mode & 0o777)?;
        }
    }
    Ok(())
}

fn safe_extract_zip(archive: &Path, destination: &Path) -> Result<()> {
    fs::create_dir_all(destination).map_err(|error| {
        DependencyError::new(format!("archive extraction root is unavailable: {error}"))
    })?;
    let file = fs::File::open(archive)
        .map_err(|error| DependencyError::new(format!("archive is unreadable: {error}")))?;
    let mut archive = zip::ZipArchive::new(file)
        .map_err(|error| DependencyError::new(format!("archive is unreadable: {error}")))?;
    for index in 0..archive.len() {
        let mut member = archive.by_index(index).map_err(|error| {
            DependencyError::new(format!("archive member is unreadable: {error}"))
        })?;
        let name = member
            .name()
            .map_err(|error| {
                DependencyError::new(format!("archive member name is unreadable: {error}"))
            })?
            .to_string();
        if name.is_empty() {
            return Err(DependencyError::new(
                "unsafe archive member: empty ZIP name",
            ));
        }
        let path = safe_archive_target(destination, Path::new(&name))?;
        let mode = member.unix_mode().unwrap_or(0);
        let file_type = mode & 0o170000;
        let allowed = if member.is_dir() {
            file_type == 0 || file_type == 0o040000
        } else {
            file_type == 0 || file_type == 0o100000
        };
        if !allowed {
            return Err(DependencyError::new(format!(
                "unsafe archive member: {name}"
            )));
        }
        if member.is_dir() {
            fs::create_dir_all(&path).map_err(|error| {
                DependencyError::new(format!("archive directory could not be created: {error}"))
            })?;
            continue;
        }
        let parent = path
            .parent()
            .ok_or_else(|| DependencyError::new("archive member has no parent"))?;
        fs::create_dir_all(parent).map_err(|error| {
            DependencyError::new(format!("archive directory could not be created: {error}"))
        })?;
        let mut output = fs::File::create(&path).map_err(|error| {
            DependencyError::new(format!("archive member could not be created: {error}"))
        })?;
        std::io::copy(&mut member, &mut output).map_err(|error| {
            DependencyError::new(format!("archive member could not be copied: {error}"))
        })?;
        if mode & 0o777 != 0 {
            set_image_mode(&path, mode & 0o777)?;
        }
    }
    Ok(())
}

fn find_regular_named(root: &Path, name: &str) -> Result<Vec<PathBuf>> {
    let mut pending = vec![root.to_path_buf()];
    let mut matches = Vec::new();
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(&directory).map_err(|error| {
            DependencyError::new(format!(
                "archive extraction directory is unreadable: {error}"
            ))
        })? {
            let entry = entry.map_err(|error| {
                DependencyError::new(format!("archive extraction entry is unreadable: {error}"))
            })?;
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path).map_err(|error| {
                DependencyError::new(format!("archive extraction entry is unreadable: {error}"))
            })?;
            if metadata.file_type().is_symlink() {
                continue;
            }
            if metadata.is_dir() {
                pending.push(path);
            } else if metadata.is_file()
                && path.file_name().and_then(|value| value.to_str()) == Some(name)
            {
                matches.push(path);
            }
        }
    }
    Ok(matches)
}

fn verify_frozen_image_layout(
    target: &Path,
    selected_ids: Option<&[String]>,
    production: bool,
    owner: (u32, u32),
) -> Result<(PathBuf, PathBuf)> {
    validate_image_parent_chain(target, production, false, owner)
        .map_err(|error| DependencyError::new(format!("image-verify rebuild-required: {error}")))?;
    assert_frozen_image_node(target, true, owner, "image dependency root")
        .map_err(|error| DependencyError::new(format!("image-verify rebuild-required: {error}")))?;
    let entries = fs::read_dir(target)
        .map_err(|error| DependencyError::new(format!("image-verify rebuild-required: {error}")))?
        .filter_map(|entry| {
            entry
                .ok()
                .map(|entry| entry.file_name().to_string_lossy().to_string())
        })
        .collect::<BTreeSet<_>>();
    if entries != BTreeSet::from(["plan.json".to_string(), "receipts".to_string()]) {
        return Err(DependencyError::new(
            "image-verify rebuild-required: image root contents mismatch",
        ));
    }
    let plan_path = target.join("plan.json");
    let receipts = target.join("receipts");
    assert_frozen_image_node(&plan_path, false, owner, "image plan")
        .map_err(|error| DependencyError::new(format!("image-verify rebuild-required: {error}")))?;
    assert_frozen_image_node(&receipts, true, owner, "image receipts")
        .map_err(|error| DependencyError::new(format!("image-verify rebuild-required: {error}")))?;
    let receipt_entries = fs::read_dir(&receipts)
        .map_err(|error| DependencyError::new(format!("image-verify rebuild-required: {error}")))?
        .map(|entry| {
            entry.map_err(|error| {
                DependencyError::new(format!("image-verify rebuild-required: {error}"))
            })
        })
        .collect::<Result<Vec<_>>>()?;
    if let Some(selected_ids) = selected_ids {
        let expected = selected_ids
            .iter()
            .map(|record_id| format!("{record_id}.json"))
            .collect::<BTreeSet<_>>();
        let actual = receipt_entries
            .iter()
            .map(|entry| entry.file_name().to_string_lossy().to_string())
            .collect::<BTreeSet<_>>();
        if actual != expected {
            return Err(DependencyError::new(
                "image-verify rebuild-required: receipt set mismatch",
            ));
        }
    }
    for entry in receipt_entries {
        assert_frozen_image_node(&entry.path(), false, owner, "image receipt").map_err(
            |error| DependencyError::new(format!("image-verify rebuild-required: {error}")),
        )?;
    }
    Ok((plan_path, receipts))
}

fn image_install_plan(
    plan: &DependencyPlan,
    workspace: &Path,
    requested: Option<&[String]>,
    final_binary_dir: Option<&Path>,
) -> Result<Vec<String>> {
    let (target, production) = image_target();
    let image_root = target
        .parent()
        .ok_or_else(|| DependencyError::new("image target has no parent"))?
        .to_path_buf();
    image_install_plan_at(
        plan,
        workspace,
        requested,
        final_binary_dir,
        Installer::new(true, Some(image_root)),
        ImageInstallContext {
            target: &target,
            production,
            runtime_identity: None,
        },
    )
}

fn image_install_plan_at(
    plan: &DependencyPlan,
    workspace: &Path,
    requested: Option<&[String]>,
    final_binary_dir: Option<&Path>,
    mut installer: Installer,
    context: ImageInstallContext<'_>,
) -> Result<Vec<String>> {
    let ImageInstallContext {
        target,
        production,
        runtime_identity,
    } = context;
    if production && !image_owner_is_root() {
        return Err(DependencyError::new("image-install requires euid=0"));
    }
    if production {
        if let Some(final_binary_dir) = final_binary_dir {
            if fs::canonicalize(final_binary_dir).ok().as_deref()
                != Some(Path::new("/usr/local/bin"))
            {
                return Err(DependencyError::new(
                    "image final binary directory is not /usr/local/bin",
                ));
            }
        }
    }
    if image_target_exists(target) {
        return Err(DependencyError::new(format!(
            "image dependency root already exists; rebuild-required: {}",
            target.display()
        )));
    }
    let selected_ids = select_record_ids(plan, requested)?;
    let by_id = plan
        .records
        .iter()
        .map(|record| (record.id.as_str(), record))
        .collect::<BTreeMap<_, _>>();
    let image_unsafe = selected_ids
        .iter()
        .filter(|record_id| {
            by_id
                .get(record_id.as_str())
                .is_none_or(|record| !image_record_is_safe(record))
        })
        .cloned()
        .collect::<Vec<_>>();
    if !image_unsafe.is_empty() {
        return Err(DependencyError::new(format!(
            "image-install contains methods outside the image-safe whitelist: {}",
            image_unsafe.join(", ")
        )));
    }
    match runtime_identity {
        Some(identity) => {
            validate_runtime_identity_for(plan, identity)?;
        }
        None => {
            validate_runtime_identity(plan)?;
        }
    }
    let owner = image_owner(production);
    validate_image_parent_chain(target, production, true, owner)?;
    let parent = target
        .parent()
        .ok_or_else(|| DependencyError::new("image target has no parent"))?;
    let staging = tempfile::Builder::new()
        .prefix(".agent-canon-image-")
        .tempdir_in(parent)
        .map_err(|error| {
            DependencyError::new(format!("image staging directory is unavailable: {error}"))
        })?;
    let receipts = staging.path().join("receipts");
    let completed = installer.install(
        plan,
        workspace,
        &receipts,
        Some(&selected_ids),
        final_binary_dir,
    )?;
    let expected = selected_ids.iter().cloned().collect::<BTreeSet<_>>();
    let actual = completed.iter().cloned().collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(DependencyError::new(format!(
            "image-install did not complete the selected record closure: expected={expected:?} completed={actual:?}"
        )));
    }
    let missing_receipts = selected_ids
        .iter()
        .filter_map(|record_id| match image_receipt_path(&receipts, record_id) {
            Ok(path) if path.is_file() => None,
            Ok(_) | Err(_) => Some(record_id.clone()),
        })
        .collect::<Vec<_>>();
    if !missing_receipts.is_empty() {
        return Err(DependencyError::new(format!(
            "image-install requires immutable receipts for: {}",
            missing_receipts.join(", ")
        )));
    }
    let contents = fs::read_dir(staging.path())
        .map_err(|error| {
            DependencyError::new(format!("image staging contents are unreadable: {error}"))
        })?
        .map(|entry| {
            entry
                .map_err(|error| DependencyError::new(error.to_string()))
                .map(|entry| entry.file_name().to_string_lossy().to_string())
        })
        .collect::<Result<BTreeSet<_>>>()?;
    if contents != BTreeSet::from(["receipts".to_string()]) {
        return Err(DependencyError::new(
            "image-install staging contents are unexpected",
        ));
    }
    let payload = image_plan_payload(plan, &selected_ids)?;
    let mut bytes = serde_json::to_vec_pretty(&payload)
        .map_err(|error| DependencyError::new(format!("serialize image plan: {error}")))?;
    bytes.push(b'\n');
    let plan_path = staging.path().join("plan.json");
    fs::write(&plan_path, bytes).map_err(|error| {
        DependencyError::new(format!("image plan could not be written: {error}"))
    })?;
    freeze_image_tree(staging.path(), owner)?;
    if image_target_exists(target) {
        return Err(DependencyError::new(format!(
            "image dependency root already exists; rebuild-required: {}",
            target.display()
        )));
    }
    fs::rename(staging.path(), target).map_err(|error| {
        DependencyError::new(format!(
            "image dependency root could not be published: {error}"
        ))
    })?;
    Ok(completed)
}

fn image_verify_plan(
    plan: &DependencyPlan,
    workspace: &Path,
    requested: Option<&[String]>,
) -> Result<Vec<String>> {
    let (target, production) = image_target();
    let image_root = target
        .parent()
        .ok_or_else(|| DependencyError::new("image target has no parent"))?
        .to_path_buf();
    image_verify_plan_at(
        plan,
        workspace,
        requested,
        &target,
        production,
        Installer::new(true, Some(image_root)),
    )
}

fn image_verify_plan_at(
    plan: &DependencyPlan,
    workspace: &Path,
    requested: Option<&[String]>,
    target: &Path,
    production: bool,
    mut installer: Installer,
) -> Result<Vec<String>> {
    let owner = image_owner(production);
    let (plan_path, _) = verify_frozen_image_layout(target, None, production, owner)?;
    let stored_bytes = fs::read(&plan_path).map_err(|error| {
        DependencyError::new(format!(
            "image-verify rebuild-required: unreadable plan: {error}"
        ))
    })?;
    let stored: Value = serde_json::from_slice(&stored_bytes).map_err(|error| {
        DependencyError::new(format!(
            "image-verify rebuild-required: unreadable plan: {error}"
        ))
    })?;
    let selected_ids = if let Some(requested) = requested {
        select_record_ids(plan, Some(requested)).map_err(|error| {
            DependencyError::new(format!(
                "image-verify rebuild-required: image selection is invalid: {error}"
            ))
        })?
    } else {
        let stored_order = stored
            .get("order")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                DependencyError::new("image-verify rebuild-required: image selection is malformed")
            })?;
        let records = stored_order
            .iter()
            .map(|value| {
                value.as_str().map(str::to_string).ok_or_else(|| {
                    DependencyError::new(
                        "image-verify rebuild-required: image selection is malformed",
                    )
                })
            })
            .collect::<Result<Vec<_>>>()?;
        select_record_ids(plan, Some(&records)).map_err(|error| {
            DependencyError::new(format!(
                "image-verify rebuild-required: image selection is invalid: {error}"
            ))
        })?
    };
    let expected = image_plan_payload(plan, &selected_ids)?;
    if stored != expected {
        return Err(DependencyError::new(
            "image-verify rebuild-required: image plan mismatch",
        ));
    }
    let (_, receipts) = verify_frozen_image_layout(target, Some(&selected_ids), production, owner)?;
    for record_id in &selected_ids {
        let path = image_receipt_path(&receipts, record_id)?;
        let bytes = fs::read(&path).map_err(|_| {
            DependencyError::new(format!(
                "image-verify rebuild-required: unreadable receipt: {record_id}"
            ))
        })?;
        let payload: Value = serde_json::from_slice(&bytes).map_err(|_| {
            DependencyError::new(format!(
                "image-verify rebuild-required: unreadable receipt: {record_id}"
            ))
        })?;
        if !payload.is_object() {
            return Err(DependencyError::new(format!(
                "image-verify rebuild-required: receipt is malformed: {record_id}"
            )));
        }
        let record = plan.by_id(record_id).expect("selected record exists");
        installer.active_method = Some(record.method);
        if payload.get("status").and_then(Value::as_str) != Some("installed")
            || !installer.receipt_matches(&path, plan, record)?
        {
            return Err(DependencyError::new(format!(
                "image-verify rebuild-required: stale or non-installed receipt: {record_id}"
            )));
        }
        installer
            .verify_installed_receipt(record, &payload, workspace)
            .map_err(|error| {
                DependencyError::new(format!(
                    "image-verify rebuild-required: live verification failed: {record_id}: {error}"
                ))
            })?;
    }
    Ok(selected_ids)
}

fn install_plan(plan: &DependencyPlan, workspace: &Path, receipts: &Path) -> Result<Vec<String>> {
    validate_runtime_identity(plan)?;
    Installer::new(false, None).install(plan, workspace, receipts, None, None)
}

#[derive(Debug, Clone)]
struct BoundaryFinding {
    category: String,
    path: String,
    detail: String,
}

impl BoundaryFinding {
    fn render(&self) -> String {
        format!(
            "AGENT_CANON_RUNTIME_BOUNDARY_FINDING={}:{}:{}",
            self.category, self.path, self.detail
        )
    }
}

fn environment_boundary_report(workspace: &Path) -> (Vec<String>, Vec<BoundaryFinding>) {
    let mut checked = Vec::new();
    let mut findings = Vec::new();
    let required = [
        ("bootstrap.sh", true),
        ("bootstrap/container/image/dependencies.toml", false),
        ("bootstrap/container/image/Dockerfile", false),
        ("bootstrap/container/lifecycle/entrypoint.sh", true),
        (
            "tools/runtime/dispatch/agent-canon/src/environment_dependencies.rs",
            false,
        ),
        (
            "tools/runtime/dispatch/agent-canon/src/bootstrap_runtime.rs",
            false,
        ),
        (
            "tools/runtime/dispatch/agent-canon/src/runtime_boundary.rs",
            false,
        ),
        ("CONTAINER_OPERATIONS.md", false),
    ];
    for (relative, executable) in required {
        checked.push(relative.to_string());
        let path = workspace.join(relative);
        if !path.is_file() {
            findings.push(BoundaryFinding {
                category: "bootstrap-runtime".to_string(),
                path: relative.to_string(),
                detail: "missing-file".to_string(),
            });
            continue;
        }
        if executable && !is_executable(&path) {
            findings.push(BoundaryFinding {
                category: "bootstrap-runtime".to_string(),
                path: relative.to_string(),
                detail: "not-executable".to_string(),
            });
        }
    }
    (checked, findings)
}

fn is_executable(path: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::metadata(path)
            .map(|metadata| metadata.permissions().mode() & 0o111 != 0)
            .unwrap_or(false)
    }
    #[cfg(not(unix))]
    {
        path.is_file()
    }
}

fn resolve_cli_workspace(path: &Path) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|error| DependencyError::new(format!("resolve workspace: {error}")))?
            .join(path)
    };
    crate::path_resolution::resolve_non_strict(&absolute).map_err(|error| {
        DependencyError::new(format!("resolve workspace {}: {error}", absolute.display()))
    })
}

fn dependency_dry_run(plan: &DependencyPlan) -> Value {
    let by_id = plan
        .records
        .iter()
        .map(|record| (record.id.as_str(), record))
        .collect::<BTreeMap<_, _>>();
    let actions = plan
        .order
        .iter()
        .filter_map(|record_id| by_id.get(record_id.as_str()))
        .map(|record| {
            let environment = if record.method == Method::BrowserInstall {
                json!({"PLAYWRIGHT_BROWSERS_PATH": record.browser_cache_path})
            } else {
                json!({})
            };
            json!({
                "id": record.id,
                "method": record.method.as_str(),
                "verification": record.verification.payload(),
                "environment": environment,
            })
        })
        .collect::<Vec<_>>();
    json!({
        "schema": "agent-canon.tool-dependency-dry-run",
        "plan_fingerprint": plan.fingerprint,
        "order": plan.order,
        "actions": actions,
    })
}

#[derive(Debug)]
struct DependencyCliOutput {
    payload: Value,
    exit_status: i32,
    sources: Option<Vec<String>>,
    order: Option<Vec<String>>,
    completed: Option<Vec<String>>,
    boundary_findings: Vec<BoundaryFinding>,
}

fn dependency_cli_output(args: &DependencyCliArgs) -> Result<DependencyCliOutput> {
    let workspace = resolve_cli_workspace(&args.workspace)?;
    if args.command != DependencyCommand::ImageInstall
        && args.command != DependencyCommand::ImageVerify
        && args.records.is_some()
    {
        return Err(DependencyError::new(
            "--records is only supported by image-install and image-verify",
        ));
    }
    if args.command == DependencyCommand::Boundary {
        let (checked, findings) = environment_boundary_report(&workspace);
        let status = if findings.is_empty() { "pass" } else { "fail" };
        return Ok(DependencyCliOutput {
            payload: json!({
                "status": status,
                "checked": checked,
                "findings": findings.iter().map(|finding| json!({
                    "category": finding.category,
                    "path": finding.path,
                    "detail": finding.detail,
                })).collect::<Vec<_>>(),
            }),
            exit_status: i32::from(!findings.is_empty()),
            sources: None,
            order: None,
            completed: None,
            boundary_findings: findings,
        });
    }
    if args.command == DependencyCommand::ProjectInstall {
        let installed = install_project_extras(&workspace, &args.extras)?;
        return Ok(DependencyCliOutput {
            payload: json!({"status": "pass", "extras": installed}),
            exit_status: 0,
            sources: None,
            order: None,
            completed: None,
            boundary_findings: Vec::new(),
        });
    }
    let plan = load_plan(&workspace, args.manifest.as_deref())?;
    match args.command {
        DependencyCommand::Validate => Ok(DependencyCliOutput {
            payload: json!({
                "status": "pass",
                "sources": plan.sources.iter().map(|source| source.display().to_string()).collect::<Vec<_>>(),
                "order": plan.order,
                "plan_fingerprint": plan.fingerprint,
            }),
            exit_status: 0,
            sources: Some(
                plan.sources
                    .iter()
                    .map(|source| source.display().to_string())
                    .collect(),
            ),
            order: Some(plan.order.clone()),
            completed: None,
            boundary_findings: Vec::new(),
        }),
        DependencyCommand::DryRun => Ok(DependencyCliOutput {
            payload: dependency_dry_run(&plan),
            exit_status: 0,
            sources: None,
            order: Some(plan.order.clone()),
            completed: None,
            boundary_findings: Vec::new(),
        }),
        DependencyCommand::Install => {
            let receipts = args
                .receipts
                .as_deref()
                .map(resolve_cli_workspace)
                .transpose()?
                .unwrap_or_else(|| workspace.join(".agent-canon/dependency-receipts"));
            let completed = install_plan(&plan, &workspace, &receipts)?;
            Ok(DependencyCliOutput {
                payload: json!({
                    "status": "pass",
                    "completed": completed,
                    "plan_fingerprint": plan.fingerprint,
                }),
                exit_status: 0,
                sources: None,
                order: None,
                completed: Some(completed),
                boundary_findings: Vec::new(),
            })
        }
        DependencyCommand::ImageInstall => {
            let records = args.records.as_deref();
            let completed =
                image_install_plan(&plan, &workspace, records, args.final_binary_dir.as_deref())?;
            Ok(DependencyCliOutput {
                payload: json!({
                    "status": "pass",
                    "completed": completed,
                    "image_root": image_dependencies_root(),
                    "plan_fingerprint": plan.fingerprint,
                }),
                exit_status: 0,
                sources: None,
                order: None,
                completed: Some(completed),
                boundary_findings: Vec::new(),
            })
        }
        DependencyCommand::ImageVerify => {
            let verified = image_verify_plan(&plan, &workspace, args.records.as_deref())?;
            Ok(DependencyCliOutput {
                payload: json!({
                    "status": "pass",
                    "verified": verified,
                    "image_root": image_dependencies_root(),
                    "plan_fingerprint": plan.fingerprint,
                }),
                exit_status: 0,
                sources: None,
                order: None,
                completed: None,
                boundary_findings: Vec::new(),
            })
        }
        DependencyCommand::Boundary | DependencyCommand::ProjectInstall => {
            unreachable!("handled before dependency plan loading")
        }
    }
}

/// Run the native CLI for typed environment dependency plans and installation.
pub fn run_cli(args: &[String]) -> i32 {
    let parsed = match parse_dependency_cli(args) {
        Ok(ParsedDependencyCli::Help) => {
            print!("{}", dependency_cli_help());
            return 0;
        }
        Ok(ParsedDependencyCli::Arguments(parsed)) => parsed,
        Err(error) => {
            eprintln!("{DEPENDENCY_USAGE}");
            eprintln!("agent-canon environment-dependencies: error: {error}");
            return 2;
        }
    };
    match dependency_cli_output(&parsed) {
        Ok(output) => {
            if parsed.format == "json" {
                match serde_json::to_string_pretty(&output.payload) {
                    Ok(value) => println!("{value}"),
                    Err(error) => {
                        eprintln!("AGENT_CANON_TOOL_DEPENDENCY_ERROR={error}");
                        return 1;
                    }
                }
            } else {
                let status = output
                    .payload
                    .get("status")
                    .and_then(Value::as_str)
                    .unwrap_or("pass");
                println!("AGENT_CANON_TOOL_DEPENDENCY={status}");
                if parsed.command == DependencyCommand::ImageInstall {
                    println!("AGENT_CANON_IMAGE_INSTALL=pass");
                }
                if parsed.command == DependencyCommand::ImageVerify {
                    println!("AGENT_CANON_IMAGE_VERIFY=pass");
                }
                for finding in &output.boundary_findings {
                    println!("{}", finding.render());
                }
                if let Some(sources) = &output.sources {
                    println!("AGENT_CANON_TOOL_DEPENDENCY_SOURCES={}", sources.join(","));
                }
                if let Some(order) = &output.order {
                    println!("AGENT_CANON_TOOL_DEPENDENCY_ORDER={}", order.join(","));
                }
                if let Some(completed) = &output.completed {
                    println!(
                        "AGENT_CANON_TOOL_DEPENDENCY_COMPLETED={}",
                        completed.join(",")
                    );
                }
            }
            output.exit_status
        }
        Err(error) => {
            if parsed.command == DependencyCommand::ImageVerify {
                if parsed.format == "json" {
                    println!(
                        "{}",
                        json!({"status": "rebuild-required", "error": error.to_string()})
                    );
                } else {
                    eprintln!("AGENT_CANON_IMAGE_VERIFY=rebuild-required");
                }
            }
            eprintln!("AGENT_CANON_TOOL_DEPENDENCY_ERROR={error}");
            1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    struct TempRoot(PathBuf);

    impl TempRoot {
        fn new() -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock is after epoch")
                .as_nanos();
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = env::temp_dir().join(format!(
                "agent-canon-environment-dependencies-{}-{sequence}-{nonce}",
                std::process::id()
            ));
            fs::create_dir_all(&path).expect("temporary root is created");
            Self(path.canonicalize().expect("temporary root is canonical"))
        }

        fn write_manifest(&self, relative: &str, text: &str) -> PathBuf {
            let path = self.0.join(relative);
            fs::create_dir_all(path.parent().expect("manifest has parent"))
                .expect("manifest parent is created");
            fs::write(&path, text).expect("manifest is written");
            path
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[cfg(unix)]
    #[cfg(target_os = "linux")]
    fn initialize_git_checkout(path: &Path) {
        fs::create_dir_all(path).expect("Git checkout directory is created");
        let init = Command::new("git")
            .args(["init", "-q", "-b", "main"])
            .arg(path)
            .output()
            .expect("Git is available for the controlled receipt fixture");
        assert!(init.status.success(), "initialize fixture Git checkout");
        let remote = Command::new("git")
            .args(["-C"])
            .arg(path)
            .args([
                "remote",
                "add",
                "origin",
                "https://example.invalid/fixture.git",
            ])
            .output()
            .expect("add fixture Git remote");
        assert!(remote.status.success(), "add fixture remote");
        let commit = Command::new("git")
            .args(["-C"])
            .arg(path)
            .args([
                "-c",
                "user.name=AgentCanon test",
                "-c",
                "user.email=agent-canon-test@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "receipt fixture",
            ])
            .output()
            .expect("commit fixture repository identity");
        assert!(commit.status.success(), "commit fixture checkout");
    }

    #[cfg(unix)]
    fn expected_record_payload(
        id: &str,
        package: &str,
        method: &str,
        version: &str,
        source: &str,
        verification: Value,
        provides: &[&str],
    ) -> Value {
        json!({
            "id": id,
            "package": package,
            "method": method,
            "version": version,
            "source": source,
            "verification": verification,
            "deps": [],
            "provides": provides,
            "failure_policy": "fail",
            "platform": null,
            "platforms": [],
            "key_fingerprint": null,
            "key_url": null,
            "repository_suite": null,
            "repository_components": [],
            "repository_packages_sha256": null,
            "repository_package_url": null,
            "repository_package_sha256": null,
            "repository_packages_sha256s": [],
            "repository_package_urls": [],
            "repository_package_sha256s": [],
            "checksum": null,
            "checksums": [],
            "asset": null,
            "assets": [],
            "archive_format": null,
            "extract": null,
            "destination": null,
            "executable_owner_packages": [],
            "repo": null,
            "commit": null,
            "source_identity": null,
            "source_tree_sha256": null,
            "cargo_lock_sha256": null,
            "locked": null,
            "browser": null,
            "browser_cache_path": null,
            "components": [],
        })
    }

    // These hashes use test-owned normalized payload values; they never call
    // DependencyRecord::fingerprint or build_plan to construct receipt identity.
    #[cfg(unix)]
    fn expected_identity(record_id: &str, record_payload: &Value) -> (String, String) {
        let record_fingerprint = sha256_hex(
            &canonical_bytes(record_payload).expect("independent record payload encodes"),
        );
        let plan_payload = json!({
            "source_roles": ["canonical"],
            "records": [record_payload],
            "order": [record_id],
            "dependency_providers": [[record_id, []]],
        });
        let plan_fingerprint =
            sha256_hex(&canonical_bytes(&plan_payload).expect("independent plan payload encodes"));
        (record_fingerprint, plan_fingerprint)
    }

    #[cfg(unix)]
    fn receipt_binding(name: &str, path: &str, output: &str) -> Value {
        json!({
            "provided": name,
            "lexical_path": path,
            "absolute_path": path,
            "verification_output": output,
        })
    }

    #[cfg(unix)]
    fn receipt_payload(
        record_id: &str,
        version: &str,
        status: &str,
        verification: Value,
        record_fingerprint: &str,
        plan_fingerprint: &str,
        executable_bindings: Value,
    ) -> Value {
        json!({
            "schema": RECEIPT_SCHEMA,
            "status": status,
            "record_id": record_id,
            "manifest_version": version,
            "record_fingerprint": record_fingerprint,
            "plan_fingerprint": plan_fingerprint,
            "verification": verification,
            "repository_packages": null,
            "repository_package": null,
            "executable_bindings": executable_bindings,
        })
    }

    #[cfg(unix)]
    fn fake_probe(
        root: &TempRoot,
        responses: impl IntoIterator<Item = (Vec<String>, CommandOutput)>,
    ) -> ProbeEnvironment {
        let fake_root = root.0.join("fake-filesystem");
        fs::create_dir_all(&fake_root).expect("fake filesystem root is created");
        let physical_root = fake_root
            .canonicalize()
            .expect("fake provider filesystem root is canonical");
        let filesystem_roots = ["/usr/local", "/usr/bin", "/home/fixture"]
            .into_iter()
            .map(|logical| {
                let logical = PathBuf::from(logical);
                let physical = physical_root.join(logical.strip_prefix("/").unwrap());
                fs::create_dir_all(&physical).expect("fake provider root is created");
                (logical, physical)
            })
            .collect();
        ProbeEnvironment {
            npm_prefix: PathBuf::from(NPM_PREFIX),
            npm_system_path: NPM_SYSTEM_PATH.to_string(),
            npm_trusted_dirs: NPM_TRUSTED_DIRS.iter().map(PathBuf::from).collect(),
            npm_env_launcher: PathBuf::from("/usr/bin/env"),
            apt_bin_dir: PathBuf::from("/usr/bin"),
            dpkg_query: PathBuf::from("/usr/bin/dpkg-query"),
            home: Some(PathBuf::from("/home/fixture")),
            cargo_home: Some(PathBuf::from("/home/fixture/.cargo")),
            inherited_path: Some("/usr/bin:/bin".to_string()),
            filesystem_roots,
            command_runner: CommandRunner::Fake(FakeCommandRunner::with_responses(responses)),
        }
    }

    #[cfg(unix)]
    fn fake_program_probe(
        root: &TempRoot,
        responses: impl IntoIterator<Item = (String, CommandOutput)>,
        downloads: impl IntoIterator<Item = Vec<u8>>,
    ) -> ProbeEnvironment {
        let mut probe = fake_probe(root, std::iter::empty::<(Vec<String>, CommandOutput)>());
        probe.command_runner = CommandRunner::Fake(FakeCommandRunner::with_program_responses(
            responses, downloads,
        ));
        probe
    }

    #[cfg(unix)]
    fn create_executable(probe: &ProbeEnvironment, logical_path: &str) {
        use std::os::unix::fs::PermissionsExt;

        let path = probe.filesystem_path(Path::new(logical_path));
        fs::create_dir_all(path.parent().expect("fixture executable has a parent"))
            .expect("fixture executable parent is created");
        fs::write(&path, b"task-owned fake executable")
            .expect("fixture executable file is written");
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755))
            .expect("fixture executable is executable");
    }

    #[cfg(unix)]
    fn command_output_fixture(stdout: &str) -> CommandOutput {
        CommandOutput {
            stdout: stdout.to_string(),
            stderr: String::new(),
            success: true,
        }
    }

    #[cfg(unix)]
    fn failed_command_output_fixture(stderr: &str) -> CommandOutput {
        CommandOutput {
            stdout: String::new(),
            stderr: stderr.to_string(),
            success: false,
        }
    }

    #[cfg(unix)]
    fn fixture_invocations(probe: &ProbeEnvironment) -> Vec<CommandInvocation> {
        let CommandRunner::Fake(runner) = &probe.command_runner else {
            panic!("test resolver uses only the per-test fake command runner")
        };
        runner.invocations.borrow().clone()
    }

    #[cfg(unix)]
    fn assert_fake_responses_consumed(probe: &ProbeEnvironment) {
        let CommandRunner::Fake(runner) = &probe.command_runner else {
            panic!("test resolver uses only the per-test fake command runner")
        };
        assert!(runner
            .responses
            .borrow()
            .values()
            .all(|responses| responses.is_empty()));
        assert!(runner
            .program_responses
            .borrow()
            .values()
            .all(|responses| responses.is_empty()));
        assert!(runner.downloads.borrow().is_empty());
    }

    #[cfg(unix)]
    #[test]
    fn executable_check_uses_os_access_for_the_current_user() {
        use std::os::unix::fs::PermissionsExt;

        let root = TempRoot::new();
        let path = root.0.join("other-execute-only");
        fs::write(&path, b"owned access fixture").expect("access fixture is written");
        fs::set_permissions(&path, fs::Permissions::from_mode(0o001))
            .expect("access fixture has only other-execute permission");
        let metadata = fs::metadata(&path).expect("access fixture metadata is available");
        assert!(metadata.is_file());
        assert_eq!(metadata.permissions().mode() & 0o777, 0o001);
        let os_access = Command::new("/bin/sh")
            .arg("-c")
            .arg("test -x \"$1\"")
            .arg("agent-canon-executable-access-oracle")
            .arg(&path)
            .status()
            .expect("POSIX shell access oracle is available")
            .success();
        assert_eq!(
            ProbeEnvironment::system().is_regular_executable(&path),
            os_access
        );
    }

    #[cfg(windows)]
    #[test]
    fn windows_executable_access_keeps_file_existence_semantics() {
        let root = TempRoot::new();
        let path = root.0.join("extensionless-tool");
        fs::write(&path, b"owned Windows access fixture").expect("file is written");
        assert!(fs::metadata(&path)
            .expect("file metadata is available")
            .is_file());
        assert!(ProbeEnvironment::system().is_regular_executable(&path));
    }

    #[cfg(unix)]
    fn write_success_manifest(root: &TempRoot, text: &str) -> PathBuf {
        root.write_manifest("workspace/dependencies.toml", text)
    }

    #[cfg(unix)]
    fn write_success_receipt(root: &TempRoot, record_id: &str, receipt: &Value) -> PathBuf {
        root.write_manifest(
            &format!("receipts/{record_id}.json"),
            &serde_json::to_string(receipt).expect("receipt serializes"),
        )
    }

    const FIXTURE: &str = r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-tool"
package = "fixture-tool"
method = "npm-global"
version = "1.2.3"
source = "https://registry.npmjs.org/fixture-tool/é"
deps = []
provides = ["fixture-tool"]
failure_policy = "fail"

[records.verification]
kind = "npm-package"
executable = "fixture-tool"
args = ["--version"]
output_contains = "1.2.3"
"#;

    #[test]
    fn complete_default_manifest_plan_retains_all_selected_records() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../../")
            .canonicalize()
            .expect("repository root exists");
        // Frozen from the pre-migration Python build_plan oracle at source SHA
        // d6e7592dddd2ea8fe9e1160742808f9f38c1d3c293608cda0921147e1a47f4c5.
        let manifest = root.join("bootstrap/container/image/dependencies.toml");
        let manifest_bytes = fs::read(&manifest).expect("canonical manifest bytes are readable");
        assert_eq!(
            sha256_hex(&manifest_bytes),
            "25cf0192adb3e7361154281a2b5b9f2a49d73e6d9de8b812b1805b5a7a4c5570"
        );
        let plan = load_plan(&root, None).expect("canonical dependency plan parses");
        let mut expected = [
            "pipx",
            "check-jsonschema",
            "yamllint",
            "ruff",
            "basedpyright",
            "pyright-language-server",
            "scip-python",
            "bash-language-server",
            "markdownlint-cli2",
            "officecli",
            "gnupg",
            "node",
            "puppeteer-fonts-liberation",
            "puppeteer-libasound2t64",
            "puppeteer-libatk-bridge2.0-0t64",
            "puppeteer-libatk1.0-0t64",
            "puppeteer-libcairo2",
            "puppeteer-libcups2t64",
            "puppeteer-libdbus-1-3",
            "puppeteer-libexpat1",
            "puppeteer-libfontconfig1",
            "puppeteer-libgbm1",
            "puppeteer-libglib2.0-0t64",
            "puppeteer-libgtk-3-0t64",
            "puppeteer-libnspr4",
            "puppeteer-libnss3",
            "puppeteer-libpango-1.0-0",
            "puppeteer-libpangocairo-1.0-0",
            "puppeteer-libx11-6",
            "puppeteer-libx11-xcb1",
            "puppeteer-libxcb1",
            "puppeteer-libxcomposite1",
            "puppeteer-libxcursor1",
            "puppeteer-libxdamage1",
            "puppeteer-libxext6",
            "puppeteer-libxfixes3",
            "puppeteer-libxi6",
            "puppeteer-libxkbcommon0",
            "puppeteer-libxrandr2",
            "puppeteer-libxrender1",
            "puppeteer-libxss1",
            "puppeteer-libxtst6",
            "puppeteer-lsb-release",
            "puppeteer-wget",
            "puppeteer-xdg-utils",
            "puppeteer-unzip",
            "jq",
            "tree",
            "clangd-language-server",
            "scip-clang",
            "scip-cli",
            "rust-toolchain",
            "shellcheck",
            "actionlint",
            "zizmor",
            "quarto",
            "vl-convert",
            "lychee",
            "puppeteer",
            "mermaid-cli",
            "python3-pytest",
            "python3-pylsp-jsonrpc",
        ]
        .into_iter()
        .map(str::to_string)
        .collect::<BTreeSet<_>>();
        if runtime_platform() != "linux/amd64" {
            expected.remove("scip-clang");
        }
        let actual = plan
            .records
            .iter()
            .map(|record| record.id.clone())
            .collect::<BTreeSet<_>>();
        assert_eq!(actual, expected);
        // Python platform.machine() was controlled for these oracle rows; the
        // aarch64 fingerprint does not claim an actual arm64 execution.
        let expected_fingerprint = match env::consts::ARCH {
            "x86_64" | "amd64" => {
                "a51cbacded9478282eb188e3be0e2f9d1cc91896c7015eac74452dc15bdfd135"
            }
            "aarch64" | "arm64" => {
                "edc6bcc252ed48b73f4eaf5eb0b8912ddafbe55ceb8261b971fa231a78101045"
            }
            other => panic!("unsupported plan-golden architecture: {other}"),
        };
        assert_eq!(plan.fingerprint, expected_fingerprint);
        assert_eq!(plan.sources.len(), plan.source_roles.len());
        assert_eq!(plan.source_roles, vec!["canonical".to_string()]);
    }

    #[test]
    fn explicit_plan_fingerprint_is_path_independent_and_role_bound() {
        let first_root = TempRoot::new();
        let second_root = TempRoot::new();
        let first_path = first_root.write_manifest("one/dependencies.toml", FIXTURE);
        let second_path = second_root.write_manifest("two/dependencies.toml", FIXTURE);
        let first = load_plan(&first_root.0, Some(&first_path)).expect("first plan parses");
        let second = load_plan(&second_root.0, Some(&second_path)).expect("second plan parses");
        assert_eq!(first.fingerprint, second.fingerprint);

        let source = manifest_sources(&first_root.0, Some(&first_path))
            .expect("explicit source resolves")
            .remove(0);
        let mut overlay = load_manifest(source).expect("standalone record parses");
        overlay.source.role = ManifestRole::ParentOverlay;
        let role_bound = build_plan(&[overlay]).expect("overlay role plan parses");
        assert_ne!(first.fingerprint, role_bound.fingerprint);
    }

    #[test]
    fn record_payload_materializes_every_contract_field_and_ascii_fingerprint_bytes() {
        let root = TempRoot::new();
        let path = root.write_manifest("dependencies.toml", FIXTURE);
        let source = ManifestSource {
            path: fs::canonicalize(path).expect("manifest path canonicalizes"),
            role: ManifestRole::Canonical,
        };
        let manifest = load_manifest(source).expect("fixture parses");
        let record = &manifest.records[0];
        let payload = record.payload();
        let keys = payload
            .as_object()
            .expect("record payload is an object")
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>();
        let expected_keys = [
            "archive_format",
            "asset",
            "assets",
            "browser",
            "browser_cache_path",
            "cargo_lock_sha256",
            "checksum",
            "checksums",
            "commit",
            "components",
            "deps",
            "destination",
            "executable_owner_packages",
            "extract",
            "failure_policy",
            "id",
            "key_fingerprint",
            "key_url",
            "locked",
            "method",
            "package",
            "platform",
            "platforms",
            "provides",
            "repo",
            "repository_components",
            "repository_package_sha256",
            "repository_package_sha256s",
            "repository_package_url",
            "repository_package_urls",
            "repository_packages_sha256",
            "repository_packages_sha256s",
            "repository_suite",
            "source",
            "source_identity",
            "source_tree_sha256",
            "verification",
            "version",
        ]
        .into_iter()
        .collect::<BTreeSet<_>>();
        assert_eq!(keys, expected_keys);
        let expected_bytes = br#"{"archive_format":null,"asset":null,"assets":[],"browser":null,"browser_cache_path":null,"cargo_lock_sha256":null,"checksum":null,"checksums":[],"commit":null,"components":[],"deps":[],"destination":null,"executable_owner_packages":[],"extract":null,"failure_policy":"fail","id":"fixture-tool","key_fingerprint":null,"key_url":null,"locked":null,"method":"npm-global","package":"fixture-tool","platform":null,"platforms":[],"provides":["fixture-tool"],"repo":null,"repository_components":[],"repository_package_sha256":null,"repository_package_sha256s":[],"repository_package_url":null,"repository_package_urls":[],"repository_packages_sha256":null,"repository_packages_sha256s":[],"repository_suite":null,"source":"https://registry.npmjs.org/fixture-tool/\u00e9","source_identity":null,"source_tree_sha256":null,"verification":{"args":["--version"],"executable":"fixture-tool","executable_globs":[],"kind":"npm-package","output_contains":"1.2.3","path":null},"version":"1.2.3"}"#;
        assert_eq!(
            canonical_bytes(&payload)
                .expect("canonical ASCII JSON succeeds")
                .as_slice(),
            expected_bytes
        );
        assert_eq!(record.fingerprint().unwrap(), sha256_hex(expected_bytes));
        let plan = build_plan(&[manifest]).expect("fixture plan is complete");
        let mut expected_plan_bytes = br#"{"dependency_providers":[["fixture-tool",[]]],"order":["fixture-tool"],"records":["#
            .to_vec();
        expected_plan_bytes.extend_from_slice(expected_bytes);
        expected_plan_bytes.extend_from_slice(br#"],"source_roles":["canonical"]}"#);
        assert_eq!(plan.fingerprint, sha256_hex(&expected_plan_bytes));
    }

    #[cfg(unix)]
    #[test]
    fn native_npm_pass_resolves_secondary_binding_without_probing_or_writing() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let record_id = "pyright-language-server";
        let manifest = write_success_manifest(
            &root,
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "pyright-language-server"
package = "pyright"
method = "npm-global"
version = "1.2.3"
source = "https://registry.npmjs.org/pyright"
deps = []
provides = ["pyright", "pyright-langserver"]
failure_policy = "fail"
[records.verification]
kind = "npm-package"
executable = "pyright"
args = ["--version"]
output_contains = "1.2.3"
"#,
        );
        let verification = json!({
            "kind": "npm-package",
            "executable": "pyright",
            "path": null,
            "args": ["--version"],
            "output_contains": "1.2.3",
            "executable_globs": [],
        });
        let record_payload = expected_record_payload(
            record_id,
            "pyright",
            "npm-global",
            "1.2.3",
            "https://registry.npmjs.org/pyright",
            verification.clone(),
            &["pyright", "pyright-langserver"],
        );
        let (record_fingerprint, plan_fingerprint) = expected_identity(record_id, &record_payload);
        let primary_output = "pyright 1.2.3";
        let structural_output =
            "agent-canon.executable-binding.structural.v1:npm-global:pyright-langserver";
        let receipt = receipt_payload(
            record_id,
            "1.2.3",
            "pass",
            verification,
            &record_fingerprint,
            &plan_fingerprint,
            json!({
                "pyright": receipt_binding("pyright", "/usr/local/bin/pyright", primary_output),
                "pyright-langserver": receipt_binding(
                    "pyright-langserver",
                    "/usr/local/bin/pyright-langserver",
                    structural_output
                ),
            }),
        );
        let receipt_path = write_success_receipt(&root, record_id, &receipt);
        let receipt_before = fs::read(&receipt_path).expect("receipt bytes are captured");
        let npm_ls = vec![
            "/usr/local/bin/npm".to_string(),
            "ls".to_string(),
            "--global".to_string(),
            "--prefix".to_string(),
            "/usr/local".to_string(),
            "--json".to_string(),
            "--depth=0".to_string(),
            "pyright".to_string(),
        ];
        let primary_probe = vec![
            "/usr/local/bin/pyright".to_string(),
            "--version".to_string(),
        ];
        let probe = fake_probe(
            &root,
            [
                (
                    npm_ls,
                    command_output_fixture(r#"{"dependencies":{"pyright":{"version":"1.2.3"}}}"#),
                ),
                (
                    primary_probe.clone(),
                    command_output_fixture(primary_output),
                ),
                (primary_probe, command_output_fixture(primary_output)),
            ],
        );
        for path in [
            "/usr/bin/env",
            "/usr/local/bin/node",
            "/usr/local/bin/npm",
            "/usr/local/bin/pyright",
            "/usr/local/bin/pyright-langserver",
        ] {
            create_executable(&probe, path);
        }
        let verified = resolve_verified_executable_with_provider(
            &probe,
            &workspace,
            receipt_path.parent().expect("receipt directory exists"),
            record_id,
            "pyright-langserver",
            Some(&manifest),
        )
        .expect("secondary language server is resolved from its receipt binding");
        assert_eq!(verified.record_id, record_id);
        assert_eq!(verified.manifest_version, "1.2.3");
        assert_eq!(verified.executable, "pyright-langserver");
        assert_eq!(
            verified.absolute_path,
            PathBuf::from("/usr/local/bin/pyright-langserver")
        );
        assert_eq!(verified.record_fingerprint, record_fingerprint);
        assert_eq!(verified.plan_fingerprint, plan_fingerprint);
        assert_eq!(verified.verification_output, structural_output);
        assert_eq!(fs::read(receipt_path).unwrap(), receipt_before);
        let calls = fixture_invocations(&probe);
        assert_eq!(calls.len(), 3);
        assert_eq!(
            calls
                .iter()
                .filter(|call| call.operation == "verify-npm-package")
                .count(),
            1
        );
        assert_eq!(
            calls
                .iter()
                .filter(|call| call.operation == "verify-declared-executable")
                .count(),
            2
        );
        assert_eq!(
            calls
                .iter()
                .filter(|call| call
                    .argv
                    .first()
                    .is_some_and(|argv| argv == "/usr/local/bin/pyright-langserver"))
                .count(),
            0
        );
        assert_fake_responses_consumed(&probe);
        assert_eq!(
            calls
                .iter()
                .filter(|call| call.argv.iter().any(|argv| argv == "--help"))
                .count(),
            0
        );
    }

    #[cfg(unix)]
    #[test]
    fn native_npm_pass_rejects_receipt_path_and_output_drift() {
        for drift in ["path", "output"] {
            let root = TempRoot::new();
            let workspace = root.0.join("workspace");
            fs::create_dir_all(&workspace).expect("workspace is created");
            let record_id = "pyright-language-server";
            let manifest = write_success_manifest(
                &root,
                r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "pyright-language-server"
package = "pyright"
method = "npm-global"
version = "1.2.3"
source = "https://registry.npmjs.org/pyright"
deps = []
provides = ["pyright", "pyright-langserver"]
failure_policy = "fail"
[records.verification]
kind = "npm-package"
executable = "pyright"
args = ["--version"]
output_contains = "1.2.3"
"#,
            );
            let verification = json!({
                "kind": "npm-package",
                "executable": "pyright",
                "path": null,
                "args": ["--version"],
                "output_contains": "1.2.3",
                "executable_globs": [],
            });
            let payload = expected_record_payload(
                record_id,
                "pyright",
                "npm-global",
                "1.2.3",
                "https://registry.npmjs.org/pyright",
                verification.clone(),
                &["pyright", "pyright-langserver"],
            );
            let (record_fingerprint, plan_fingerprint) = expected_identity(record_id, &payload);
            let primary_output = "pyright 1.2.3";
            let structural_output =
                "agent-canon.executable-binding.structural.v1:npm-global:pyright-langserver";
            let primary_path = if drift == "path" {
                "/usr/local/bin/stale-pyright"
            } else {
                "/usr/local/bin/pyright"
            };
            let receipt_primary_output = if drift == "output" {
                "pyright 1.0.0"
            } else {
                primary_output
            };
            let receipt = receipt_payload(
                record_id,
                "1.2.3",
                "pass",
                verification,
                &record_fingerprint,
                &plan_fingerprint,
                json!({
                    "pyright": receipt_binding("pyright", primary_path, receipt_primary_output),
                    "pyright-langserver": receipt_binding(
                        "pyright-langserver",
                        "/usr/local/bin/pyright-langserver",
                        structural_output
                    ),
                }),
            );
            let receipt_path = write_success_receipt(&root, record_id, &receipt);
            let npm_ls = vec![
                "/usr/local/bin/npm".to_string(),
                "ls".to_string(),
                "--global".to_string(),
                "--prefix".to_string(),
                "/usr/local".to_string(),
                "--json".to_string(),
                "--depth=0".to_string(),
                "pyright".to_string(),
            ];
            let pyright_version = vec![
                "/usr/local/bin/pyright".to_string(),
                "--version".to_string(),
            ];
            let probe = fake_probe(
                &root,
                [
                    (
                        npm_ls,
                        command_output_fixture(
                            r#"{"dependencies":{"pyright":{"version":"1.2.3"}}}"#,
                        ),
                    ),
                    (
                        pyright_version.clone(),
                        command_output_fixture(primary_output),
                    ),
                    (pyright_version, command_output_fixture(primary_output)),
                ],
            );
            for path in [
                "/usr/bin/env",
                "/usr/local/bin/node",
                "/usr/local/bin/npm",
                "/usr/local/bin/pyright",
                "/usr/local/bin/pyright-langserver",
            ] {
                create_executable(&probe, path);
            }
            let error = resolve_verified_executable_with_provider(
                &probe,
                &workspace,
                receipt_path.parent().expect("receipt directory exists"),
                record_id,
                "pyright",
                Some(&manifest),
            )
            .expect_err("receipt binding drift is rejected");
            assert!(error
                .to_string()
                .contains("executable receipt path or output drift"));
            assert_eq!(fixture_invocations(&probe).len(), 3);
            assert_fake_responses_consumed(&probe);
        }
    }

    #[cfg(unix)]
    #[test]
    fn native_apt_pass_checks_dpkg_ownership_and_compares_live_binding() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let record_id = "clangd-language-server";
        let manifest = write_success_manifest(
            &root,
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "clangd-language-server"
package = "clangd-18"
method = "apt-package"
version = "1.2.3"
source = "ubuntu:24.04"
deps = []
provides = ["clangd-18"]
failure_policy = "fail"
[records.verification]
kind = "apt-package"
executable = "clangd-18"
args = ["--version"]
output_contains = "1.2.3"
"#,
        );
        let verification = json!({
            "kind": "apt-package",
            "executable": "clangd-18",
            "path": null,
            "args": ["--version"],
            "output_contains": "1.2.3",
            "executable_globs": [],
        });
        let mut record_payload = expected_record_payload(
            record_id,
            "clangd-18",
            "apt-package",
            "1.2.3",
            "ubuntu:24.04",
            verification.clone(),
            &["clangd-18"],
        );
        record_payload["executable_owner_packages"] = json!(["clangd-18"]);
        let (record_fingerprint, plan_fingerprint) = expected_identity(record_id, &record_payload);
        let live_output = "clangd version 1.2.3";
        let receipt = receipt_payload(
            record_id,
            "1.2.3",
            "pass",
            verification,
            &record_fingerprint,
            &plan_fingerprint,
            json!({
                "clangd-18": receipt_binding("clangd-18", "/usr/bin/clangd-18", live_output),
            }),
        );
        let receipt_path = write_success_receipt(&root, record_id, &receipt);
        let package_query = vec![
            "/usr/bin/dpkg-query".to_string(),
            "--show".to_string(),
            "--showformat=${Status}\\t${Version}\\t${Package}\\n".to_string(),
            "clangd-18".to_string(),
        ];
        let owner_query = vec![
            "/usr/bin/dpkg-query".to_string(),
            "--listfiles".to_string(),
            "clangd-18".to_string(),
        ];
        let executable_probe = vec!["/usr/bin/clangd-18".to_string(), "--version".to_string()];
        let probe = fake_probe(
            &root,
            [
                (
                    package_query.clone(),
                    command_output_fixture("install ok installed\t1.2.3\tclangd-18\n"),
                ),
                (
                    owner_query.clone(),
                    command_output_fixture("/usr/bin/clangd-18\n"),
                ),
                (
                    executable_probe.clone(),
                    command_output_fixture(live_output),
                ),
                (owner_query, command_output_fixture("/usr/bin/clangd-18\n")),
                (executable_probe, command_output_fixture(live_output)),
            ],
        );
        create_executable(&probe, "/usr/bin/clangd-18");
        let verified = resolve_verified_executable_with_provider(
            &probe,
            &workspace,
            receipt_path.parent().expect("receipt directory exists"),
            record_id,
            "clangd-18",
            Some(&manifest),
        )
        .expect("apt executable resolves after package and ownership probes");
        assert_eq!(verified.record_id, record_id);
        assert_eq!(verified.manifest_version, "1.2.3");
        assert_eq!(verified.executable, "clangd-18");
        assert_eq!(verified.absolute_path, PathBuf::from("/usr/bin/clangd-18"));
        assert_eq!(verified.record_fingerprint, record_fingerprint);
        assert_eq!(verified.plan_fingerprint, plan_fingerprint);
        assert_eq!(verified.verification_output, live_output);
        let calls = fixture_invocations(&probe);
        assert_eq!(calls.len(), 5);
        assert_eq!(calls[0].argv, package_query);
        assert_eq!(calls[0].operation, "verify-apt-package");
        assert_eq!(calls[1].argv[1], "--listfiles");
        assert_eq!(calls[1].operation, "verify-apt-executable-owner");
        assert_eq!(calls[2].argv, vec!["/usr/bin/clangd-18", "--version"]);
        assert_eq!(calls[3].argv[1], "--listfiles");
        assert_eq!(calls[4].argv, vec!["/usr/bin/clangd-18", "--version"]);
        assert_fake_responses_consumed(&probe);
    }

    #[cfg(unix)]
    #[test]
    fn native_rust_pass_resolves_rust_analyzer_from_configured_cargo_home() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let record_id = "rust-toolchain";
        let manifest = write_success_manifest(
            &root,
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "rust-toolchain"
package = "rust"
method = "rust-toolchain"
version = "1.89.0"
source = "https://static.rust-lang.org"
deps = []
provides = ["cargo", "rust-analyzer"]
failure_policy = "fail"
components = ["rust-analyzer"]
[records.verification]
kind = "rust-toolchain"
"#,
        );
        let verification = json!({
            "kind": "rust-toolchain",
            "executable": null,
            "path": null,
            "args": [],
            "output_contains": null,
            "executable_globs": [],
        });
        let mut record_payload = expected_record_payload(
            record_id,
            "rust",
            "rust-toolchain",
            "1.89.0",
            "https://static.rust-lang.org",
            verification.clone(),
            &["cargo", "rust-analyzer"],
        );
        record_payload["components"] = json!(["rust-analyzer"]);
        let (record_fingerprint, plan_fingerprint) = expected_identity(record_id, &record_payload);
        let structural_output =
            "agent-canon.executable-binding.structural.v1:rust-toolchain:rust-analyzer";
        let receipt = receipt_payload(
            record_id,
            "1.89.0",
            "pass",
            verification,
            &record_fingerprint,
            &plan_fingerprint,
            json!({
                "rust-analyzer": receipt_binding(
                    "rust-analyzer",
                    "/home/fixture/.cargo/bin/rust-analyzer",
                    structural_output
                ),
            }),
        );
        let receipt_path = write_success_receipt(&root, record_id, &receipt);
        let rustup = |args: &[&str]| {
            std::iter::once("rustup".to_string())
                .chain(args.iter().map(|value| value.to_string()))
                .collect::<Vec<_>>()
        };
        let probe = fake_probe(
            &root,
            [
                (
                    rustup(&["show", "active-toolchain"]),
                    command_output_fixture("1.89.0-x86_64-unknown-linux-gnu (default)"),
                ),
                (
                    rustup(&["toolchain", "list"]),
                    command_output_fixture("1.89.0-x86_64-unknown-linux-gnu"),
                ),
                (
                    rustup(&["component", "list", "--toolchain", "1.89.0"]),
                    command_output_fixture("rust-analyzer-x86_64-unknown-linux-gnu (installed)"),
                ),
                (
                    rustup(&["run", "1.89.0", "rustc", "--version"]),
                    command_output_fixture("rustc 1.89.0"),
                ),
                (
                    rustup(&["run", "1.89.0", "cargo", "--version"]),
                    command_output_fixture("cargo 1.89.0"),
                ),
                (
                    rustup(&["run", "1.89.0", "rust-analyzer", "--version"]),
                    command_output_fixture("rust-analyzer 1.89.0"),
                ),
            ],
        );
        create_executable(&probe, "/home/fixture/.cargo/bin/rust-analyzer");
        let verified = resolve_verified_executable_with_provider(
            &probe,
            &workspace,
            receipt_path.parent().expect("receipt directory exists"),
            record_id,
            "rust-analyzer",
            Some(&manifest),
        )
        .expect("rust-analyzer resolves from CARGO_HOME");
        assert_eq!(verified.record_id, record_id);
        assert_eq!(verified.manifest_version, "1.89.0");
        assert_eq!(verified.executable, "rust-analyzer");
        assert_eq!(
            verified.absolute_path,
            PathBuf::from("/home/fixture/.cargo/bin/rust-analyzer")
        );
        assert_eq!(verified.record_fingerprint, record_fingerprint);
        assert_eq!(verified.plan_fingerprint, plan_fingerprint);
        assert_eq!(verified.verification_output, structural_output);
        let calls = fixture_invocations(&probe);
        assert_eq!(calls.len(), 6);
        assert!(calls.iter().all(|call| {
            call.path.as_deref()
                == Some("/home/fixture/.cargo/bin:/home/fixture/.elan/bin:/home/fixture/.local/bin:/usr/bin:/bin")
                && call.cargo_home.as_deref() == Some("/home/fixture/.cargo")
                && call.clear_rustup_overrides
        }));
        assert_eq!(
            calls
                .iter()
                .filter(|call| call.argv.iter().any(|arg| arg == "rust-analyzer"))
                .count(),
            1,
            "only rustup's declared version probe reaches rust-analyzer"
        );
        assert!(calls
            .iter()
            .all(|call| call.operation.starts_with("verify-rust-")));
        assert_fake_responses_consumed(&probe);
    }

    #[cfg(unix)]
    #[test]
    fn native_release_asset_installed_receipt_runs_only_declared_absolute_probe() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let record_id = "scip-clang";
        let manifest = write_success_manifest(
            &root,
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "scip-clang"
package = "scip-clang"
method = "release-asset"
version = "0.4.0"
source = "https://example.invalid/scip-clang"
checksum = "0000000000000000000000000000000000000000000000000000000000000000"
asset = "scip-clang"
archive_format = "binary"
extract = "none"
destination = "/usr/local/bin/scip-clang"
deps = []
provides = ["scip-clang"]
failure_policy = "fail"
[records.verification]
kind = "absolute-executable"
path = "/usr/local/bin/scip-clang"
args = ["--version"]
output_contains = "0.4.0"
"#,
        );
        let verification = json!({
            "kind": "absolute-executable",
            "executable": null,
            "path": "/usr/local/bin/scip-clang",
            "args": ["--version"],
            "output_contains": "0.4.0",
            "executable_globs": [],
        });
        let mut record_payload = expected_record_payload(
            record_id,
            "scip-clang",
            "release-asset",
            "0.4.0",
            "https://example.invalid/scip-clang",
            verification.clone(),
            &["scip-clang"],
        );
        record_payload["checksum"] =
            json!("0000000000000000000000000000000000000000000000000000000000000000");
        record_payload["asset"] = json!("scip-clang");
        record_payload["archive_format"] = json!("binary");
        record_payload["extract"] = json!("none");
        record_payload["destination"] = json!("/usr/local/bin/scip-clang");
        let (record_fingerprint, plan_fingerprint) = expected_identity(record_id, &record_payload);
        let live_output = "scip-clang 0.4.0";
        let receipt = receipt_payload(
            record_id,
            "0.4.0",
            "installed",
            verification,
            &record_fingerprint,
            &plan_fingerprint,
            json!({}),
        );
        let receipt_path = write_success_receipt(&root, record_id, &receipt);
        let probe = fake_probe(
            &root,
            [(
                vec![
                    "/usr/local/bin/scip-clang".to_string(),
                    "--version".to_string(),
                ],
                command_output_fixture(live_output),
            )],
        );
        create_executable(&probe, "/usr/local/bin/scip-clang");
        let verified = resolve_verified_executable_with_provider(
            &probe,
            &workspace,
            receipt_path.parent().expect("receipt directory exists"),
            record_id,
            "scip-clang",
            Some(&manifest),
        )
        .expect("release asset resolves at its declared absolute path");
        assert_eq!(verified.record_id, record_id);
        assert_eq!(verified.manifest_version, "0.4.0");
        assert_eq!(verified.executable, "scip-clang");
        assert_eq!(
            verified.absolute_path,
            PathBuf::from("/usr/local/bin/scip-clang")
        );
        assert_eq!(verified.record_fingerprint, record_fingerprint);
        assert_eq!(verified.plan_fingerprint, plan_fingerprint);
        assert_eq!(verified.verification_output, live_output);
        let calls = fixture_invocations(&probe);
        assert_eq!(calls.len(), 1);
        assert_eq!(
            calls[0].argv,
            vec!["/usr/local/bin/scip-clang", "--version"]
        );
        assert_eq!(calls[0].operation, "verify-declared-executable");
        assert_fake_responses_consumed(&probe);

        let wrong_output_probe = fake_probe(
            &root,
            [(
                vec![
                    "/usr/local/bin/scip-clang".to_string(),
                    "--version".to_string(),
                ],
                command_output_fixture("scip-clang 0.3.0"),
            )],
        );
        let error = resolve_verified_executable_with_provider(
            &wrong_output_probe,
            &workspace,
            receipt_path.parent().expect("receipt directory exists"),
            record_id,
            "scip-clang",
            Some(&manifest),
        )
        .expect_err("declared output token is mandatory");
        assert!(error
            .to_string()
            .contains("verification output lacks required token"));
        assert_fake_responses_consumed(&wrong_output_probe);
    }

    #[test]
    fn provider_closure_accepts_leading_dash_list_capabilities() {
        let root = TempRoot::new();
        let manifest = root.write_manifest(
            "dependencies.toml",
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "consumer"
package = "consumer"
method = "npm-global"
version = "1.0.0"
source = "https://registry.npmjs.org/consumer"
deps = ["-provider-capability"]
provides = ["consumer"]
failure_policy = "fail"
[records.verification]
kind = "npm-package"
executable = "consumer"
args = ["--version"]
output_contains = "1.0.0"

[[records]]
id = "provider"
package = "provider"
method = "npm-global"
version = "1.0.0"
source = "https://registry.npmjs.org/provider"
deps = []
provides = ["-provider-capability"]
failure_policy = "fail"
[records.verification]
kind = "npm-package"
executable = "provider"
args = ["--version"]
output_contains = "1.0.0"
"#,
        );
        let plan = load_plan(&root.0, Some(&manifest)).expect("provider plan parses");
        assert_eq!(
            plan.order,
            vec!["provider".to_string(), "consumer".to_string()]
        );
        assert_eq!(
            plan.dependency_providers,
            vec![
                ("consumer".to_string(), vec!["provider".to_string()]),
                ("provider".to_string(), vec![]),
            ]
        );
        assert_eq!(plan.records.len(), 2);
    }

    #[test]
    fn dependency_cli_parses_options_around_command_and_repeated_record_groups() {
        let args = [
            "--workspace".to_string(),
            "project".to_string(),
            "image-verify".to_string(),
            "--records".to_string(),
            "alpha,beta".to_string(),
            "--records=gamma".to_string(),
            "--format".to_string(),
            "json".to_string(),
        ];
        let ParsedDependencyCli::Arguments(parsed) =
            parse_dependency_cli(&args).expect("argparse-compatible options parse")
        else {
            panic!("CLI arguments should not select help");
        };
        assert_eq!(parsed.command, DependencyCommand::ImageVerify);
        assert_eq!(parsed.workspace, PathBuf::from("project"));
        assert_eq!(
            parsed.records,
            Some(vec!["alpha,beta".to_string(), "gamma".to_string()])
        );
        assert_eq!(parsed.format, "json");
    }

    #[test]
    fn command_classifier_rejects_shell_dynamic_env_and_network_verification() {
        let shell = classify_dependency_command(
            &[
                "sh".to_string(),
                "-c".to_string(),
                "apt-get install x".to_string(),
            ],
            "image-install",
            "image-installer",
            "install-apt-package",
            Some(Method::AptPackage),
            false,
        )
        .expect_err("shell process graphs are refused");
        assert_eq!(shell.0, CommandCapability::ShellEvaluation);

        let dynamic_env = classify_dependency_command(
            &[
                "env".to_string(),
                "-S".to_string(),
                "npm install x".to_string(),
            ],
            "image-install",
            "image-installer",
            "install-npm-global",
            Some(Method::NpmGlobal),
            false,
        )
        .expect_err("env string expansion is refused");
        assert_eq!(dynamic_env.0, CommandCapability::Unknown);

        let network_verify = classify_dependency_command(
            &[
                "curl".to_string(),
                "--fail".to_string(),
                "--output".to_string(),
                "/tmp/index".to_string(),
                "https://example.invalid/index".to_string(),
            ],
            "image-verify",
            "typed-verifier",
            "verify-apt-repository-key",
            Some(Method::AptRepository),
            false,
        )
        .expect_err("network fetch is refused during image verification");
        assert_eq!(network_verify.0, CommandCapability::NetworkFetch);

        assert!(classify_dependency_command(
            &["apt-get".to_string(), "update".to_string(),],
            "image-install",
            "image-installer",
            "install-apt-repository",
            Some(Method::AptRepository),
            true,
        )
        .is_ok());
    }

    #[test]
    fn project_extra_validation_uses_declared_optional_dependencies() {
        let root = TempRoot::new();
        fs::write(
            root.0.join("pyproject.toml"),
            "[project.optional-dependencies]\nDev_Test = []\n",
        )
        .expect("write declared project extra");
        assert_eq!(
            validate_project_extras(&root.0, &["dev-test".to_string()])
                .expect("PEP 503 equivalent name is declared"),
            vec!["dev-test".to_string()]
        );
        assert!(validate_project_extras(&root.0, &["missing".to_string()])
            .expect_err("undeclared extra is rejected")
            .to_string()
            .contains("project extras are not declared"));
        assert!(validate_project_extras(
            &root.0,
            &["dev-test".to_string(), "DEV_test".to_string()]
        )
        .expect_err("canonical duplicate extras are rejected")
        .to_string()
        .contains("duplicate Python extra"));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn parent_owned_install_receipt_round_trips_and_is_removed_through_authority() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        initialize_git_checkout(&workspace);
        let manifest = root.write_manifest(
            "dependencies.toml",
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2
[[records]]
id = "fixture-cli"
package = "fixture-cli"
method = "npm-global"
version = "1.2.3"
source = "https://registry.npmjs.org/fixture-cli"
deps = []
provides = ["fixture-cli"]
failure_policy = "fail"
[records.verification]
kind = "npm-package"
executable = "fixture-cli"
args = ["--version"]
output_contains = "1.2.3"
"#,
        );
        let plan = load_plan(&workspace, Some(&manifest)).expect("receipt plan parses");
        let record = plan.by_id("fixture-cli").unwrap();
        let receipt_path = workspace.join(".agent-canon/dependency-receipts/fixture-cli.json");
        let mut installer = Installer::new(false, None);
        installer.parent_attestation =
            Some(attest_dependency_parent(&workspace).expect("Git parent root attests"));
        installer
            .write_receipt(&receipt_path, &plan, record, None, &BTreeMap::new(), None)
            .expect("publish receipt through parent-owned capability");
        let payload: Value = serde_json::from_slice(
            &installer
                .read_receipt(&receipt_path)
                .expect("receipt reads through authority"),
        )
        .expect("receipt is JSON");
        assert_eq!(payload["record_id"], "fixture-cli");
        assert_eq!(payload["status"], "pass");
        installer
            .remove_receipt(&receipt_path)
            .expect("remove receipt through its captured parent identity");
        assert!(!receipt_path.exists());
    }

    #[cfg(unix)]
    #[test]
    fn image_installer_publishes_receipt_and_removes_stale_receipt_on_failure() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let manifest = root.write_manifest(
            "dependencies.toml",
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-npm"
package = "fixture-npm"
method = "npm-global"
version = "1.0.0"
source = "https://registry.npmjs.org/fixture-npm"
deps = []
provides = ["fixture-npm"]
failure_policy = "fail"
[records.verification]
kind = "npm-package"
executable = "fixture-npm"
args = ["--version"]
output_contains = "1.0.0"
"#,
        );
        let plan = load_plan(&workspace, Some(&manifest)).expect("fixture plan parses");
        let receipt_root = root.0.join("receipts");
        let receipt_path = receipt_root.join("fixture-npm.json");
        let command = vec![
            NPM_ENV_EXECUTABLE.to_string(),
            format!("PATH={NPM_SYSTEM_PATH}"),
            "/usr/bin/npm".to_string(),
            "install".to_string(),
            "--force".to_string(),
            "--global".to_string(),
            "--prefix".to_string(),
            NPM_GLOBAL_PREFIX.to_string(),
            "fixture-npm@1.0.0".to_string(),
        ];

        let probe = fake_probe(
            &root,
            [(command.clone(), command_output_fixture("installed"))],
        );
        let mut installer = Installer::with_probe(true, Some(root.0.clone()), probe);
        let completed = installer
            .install(&plan, &workspace, &receipt_root, None, None)
            .expect("image npm record installs through the selected provider");
        assert_eq!(completed, vec!["fixture-npm".to_string()]);
        let receipt: Value = serde_json::from_slice(
            &fs::read(&receipt_path).expect("successful install publishes receipt"),
        )
        .expect("receipt is valid JSON");
        assert_eq!(receipt["status"], "installed");
        assert_eq!(receipt["record_id"], "fixture-npm");
        assert_eq!(
            receipt["executable_bindings"]["fixture-npm"]["absolute_path"],
            "/usr/local/bin/fixture-npm"
        );
        assert!(installer
            .receipt_matches(&receipt_path, &plan, plan.by_id("fixture-npm").unwrap())
            .expect("receipt identity can be checked"));
        assert_fake_responses_consumed(&installer.probe);

        fs::write(&receipt_path, b"stale receipt").expect("seed stale receipt");
        let failing_probe = fake_probe(
            &root,
            [(
                command,
                failed_command_output_fixture("provider rejected install"),
            )],
        );
        let mut failing_installer =
            Installer::with_probe(true, Some(root.0.clone()), failing_probe);
        let error = failing_installer
            .install(&plan, &workspace, &receipt_root, None, None)
            .expect_err("provider failure remains fatal");
        assert!(error.to_string().contains("provider rejected install"));
        assert!(
            !receipt_path.exists(),
            "failed install leaves no stale receipt"
        );
        assert_fake_responses_consumed(&failing_installer.probe);
    }

    #[cfg(unix)]
    #[test]
    fn image_installer_runs_apt_and_pipx_providers_in_dependency_order() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let manifest = root.write_manifest(
            "dependencies.toml",
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-cli"
package = "fixture-cli"
method = "pipx"
version = "1.2.3"
source = "https://pypi.org/simple"
deps = ["pipx"]
provides = ["fixture-cli"]
failure_policy = "fail"
[records.verification]
kind = "pipx-package"
executable = "fixture-cli"
args = ["--version"]
output_contains = "1.2.3"

[[records]]
id = "pipx"
package = "pipx"
method = "apt-package"
version = "1.4.3-1"
source = "ubuntu:24.04"
deps = []
provides = ["pipx"]
failure_policy = "fail"
[records.verification]
kind = "apt-package"
"#,
        );
        let plan = load_plan(&workspace, Some(&manifest)).expect("apt and pipx plan parses");
        assert_eq!(
            plan.order,
            vec!["pipx".to_string(), "fixture-cli".to_string()]
        );
        let apt_command = vec![
            "apt-get".to_string(),
            "install".to_string(),
            "-y".to_string(),
            "--no-install-recommends".to_string(),
            "--no-remove".to_string(),
            "pipx=1.4.3-1".to_string(),
        ];
        let pipx_command = vec![
            "pipx".to_string(),
            "install".to_string(),
            "--index-url".to_string(),
            "https://pypi.org/simple".to_string(),
            "fixture-cli==1.2.3".to_string(),
        ];
        let probe = fake_probe(
            &root,
            [
                (apt_command.clone(), command_output_fixture("installed")),
                (pipx_command.clone(), command_output_fixture("installed")),
            ],
        );
        let mut installer = Installer::with_probe(true, Some(root.0.clone()), probe);
        let receipt_root = root.0.join("receipts");
        assert_eq!(
            installer
                .install(&plan, &workspace, &receipt_root, None, None)
                .expect("typed apt and pipx records install"),
            plan.order
        );
        let calls = fixture_invocations(&installer.probe);
        assert_eq!(
            calls
                .iter()
                .map(|call| call.argv.clone())
                .collect::<Vec<_>>(),
            vec![apt_command, pipx_command]
        );
        let pipx_receipt: Value = serde_json::from_slice(
            &fs::read(receipt_root.join("fixture-cli.json")).expect("pipx receipt exists"),
        )
        .expect("pipx receipt is JSON");
        assert_eq!(pipx_receipt["status"], "installed");
        assert_eq!(
            pipx_receipt["executable_bindings"]["fixture-cli"]["absolute_path"],
            "/usr/local/bin/fixture-cli"
        );
        assert_fake_responses_consumed(&installer.probe);
    }

    #[cfg(unix)]
    #[test]
    fn image_installer_receipts_the_observed_version_for_unpinned_apt_packages() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let manifest = root.write_manifest(
            "dependencies.toml",
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-apt"
package = "fixture-apt"
method = "apt-package"
source = "ubuntu:24.04"
deps = []
provides = ["fixture-apt"]
failure_policy = "fail"
[records.verification]
kind = "apt-package"
"#,
        );
        let plan = load_plan(&workspace, Some(&manifest)).expect("apt plan parses");
        let install_command = vec![
            "apt-get".to_string(),
            "install".to_string(),
            "-y".to_string(),
            "--no-install-recommends".to_string(),
            "--no-remove".to_string(),
            "fixture-apt".to_string(),
        ];
        let query_command = vec![
            "/usr/bin/dpkg-query".to_string(),
            "--show".to_string(),
            "--showformat=${Status}\\t${Version}\\t${Package}\\n".to_string(),
            "fixture-apt".to_string(),
        ];
        let probe = fake_probe(
            &root,
            [
                (install_command, command_output_fixture("installed")),
                (
                    query_command,
                    command_output_fixture("install ok installed\t2.4.6-1\tfixture-apt\n"),
                ),
            ],
        );
        let mut installer = Installer::with_probe(true, Some(root.0.clone()), probe);
        let receipt_root = root.0.join("receipts");
        installer
            .install(&plan, &workspace, &receipt_root, None, None)
            .expect("unpinned apt package installs");
        let receipt: Value = serde_json::from_slice(
            &fs::read(receipt_root.join("fixture-apt.json")).expect("apt receipt exists"),
        )
        .expect("apt receipt is JSON");
        assert_eq!(receipt["resolved_package_version"], "2.4.6-1");
        assert!(installer
            .receipt_matches(
                &receipt_root.join("fixture-apt.json"),
                &plan,
                plan.by_id("fixture-apt").unwrap()
            )
            .expect("version-bound receipt matches its plan"));
        assert_fake_responses_consumed(&installer.probe);
    }

    #[cfg(unix)]
    #[test]
    fn apt_repository_installer_checks_key_fingerprint_and_deb_checksum() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let key_bytes = b"fixture public signing key";
        let package_bytes = b"fixture deb package";
        let checksum = Sha256::digest(package_bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let fingerprint = "0123456789ABCDEF0123456789ABCDEF01234567";
        let manifest_text = |expected_checksum: &str| {
            format!(
                r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-repository"
package = "fixture-repository"
method = "apt-repository"
version = "1.0.0"
source = "https://example.invalid/apt"
key_url = "https://example.invalid/apt/key.gpg"
key_fingerprint = "{fingerprint}"
repository_suite = "stable"
repository_components = ["main"]
repository_package_url = "https://example.invalid/apt/fixture-repository.deb"
repository_package_sha256 = "{expected_checksum}"
deps = []
provides = ["fixture-repository"]
failure_policy = "fail"
[records.verification]
kind = "apt-repository"
"#
            )
        };
        let manifest = root.write_manifest("dependencies.toml", &manifest_text(&checksum));
        let plan = load_plan(&workspace, Some(&manifest)).expect("repository plan parses");
        let mut gpg_fields = vec![String::new(); 10];
        gpg_fields[0] = "fpr".to_string();
        gpg_fields[9] = fingerprint.to_string();
        let observed_fingerprint = gpg_fields.join(":");
        let responses = [
            ("curl".to_string(), command_output_fixture("downloaded key")),
            (
                "gpg".to_string(),
                command_output_fixture(&observed_fingerprint),
            ),
            ("gpg".to_string(), command_output_fixture("dearmored")),
            (
                "install".to_string(),
                command_output_fixture("installed key"),
            ),
            (
                "install".to_string(),
                command_output_fixture("installed source"),
            ),
            ("apt-get".to_string(), command_output_fixture("updated")),
            (
                "curl".to_string(),
                command_output_fixture("downloaded package"),
            ),
            (
                "apt-get".to_string(),
                command_output_fixture("installed package"),
            ),
        ];
        let probe = fake_program_probe(
            &root,
            responses,
            [key_bytes.to_vec(), package_bytes.to_vec()],
        );
        let mut installer = Installer::with_probe(true, Some(root.0.clone()), probe);
        installer
            .install_record(plan.by_id("fixture-repository").unwrap(), &workspace, false)
            .expect("valid repository key and immutable package install");
        let calls = fixture_invocations(&installer.probe);
        assert_eq!(
            calls.iter().filter(|call| call.argv[0] == "curl").count(),
            2
        );
        assert!(calls.iter().any(|call| {
            call.argv
                .first()
                .is_some_and(|program| program == "apt-get")
                && call
                    .argv
                    .iter()
                    .any(|argument| argument.ends_with("fixture-repository.deb"))
        }));
        assert_fake_responses_consumed(&installer.probe);

        let mismatch_manifest =
            root.write_manifest("checksum-mismatch.toml", &manifest_text(&"0".repeat(64)));
        let mismatch_plan = load_plan(&workspace, Some(&mismatch_manifest))
            .expect("checksum mismatch fixture plan parses");
        let mismatch_probe = fake_program_probe(
            &root,
            [
                ("curl".to_string(), command_output_fixture("downloaded key")),
                (
                    "gpg".to_string(),
                    command_output_fixture(&observed_fingerprint),
                ),
                ("gpg".to_string(), command_output_fixture("dearmored")),
                (
                    "install".to_string(),
                    command_output_fixture("installed key"),
                ),
                (
                    "install".to_string(),
                    command_output_fixture("installed source"),
                ),
                ("apt-get".to_string(), command_output_fixture("updated")),
                (
                    "curl".to_string(),
                    command_output_fixture("downloaded package"),
                ),
            ],
            [key_bytes.to_vec(), package_bytes.to_vec()],
        );
        let mut mismatch_installer =
            Installer::with_probe(true, Some(root.0.clone()), mismatch_probe);
        let error = mismatch_installer
            .install_record(
                mismatch_plan.by_id("fixture-repository").unwrap(),
                &workspace,
                false,
            )
            .expect_err("package checksum mismatch prevents installation");
        assert!(error
            .to_string()
            .contains("immutable apt package SHA256 mismatch"));
        assert!(!fixture_invocations(&mismatch_installer.probe)
            .iter()
            .any(|call| call
                .argv
                .first()
                .is_some_and(|program| program == "apt-get")
                && call.argv.iter().any(|argument| argument == "install")));
        assert_fake_responses_consumed(&mismatch_installer.probe);
    }

    #[cfg(unix)]
    #[test]
    fn rust_lean_and_browser_installers_keep_their_declared_provider_argv() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let browser_cache = PathBuf::from("/usr/local/share/agent-canon/browser-fixture");
        let manifest = root.write_manifest(
            "dependencies.toml",
            &format!(
                r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "rust-toolchain"
package = "rust"
method = "rust-toolchain"
version = "1.99.1"
source = "https://static.rust-lang.org"
components = ["rustfmt"]
verification = {{ kind = "rust-toolchain", executable = "rustc", args = ["--version"], output_contains = "rustc 1.99.1" }}
deps = []
provides = ["cargo", "rustc", "rustfmt"]
failure_policy = "fail"

[[records]]
id = "lean-toolchain"
package = "lean"
method = "lean-toolchain"
version = "leanprover/lean4:v4.30.0"
source = "https://github.com/leanprover/lean4"
verification = {{ kind = "lean-toolchain" }}
deps = []
provides = ["elan", "lean", "lake"]
failure_policy = "fail"

[[records]]
id = "browser"
package = "chromium"
method = "browser-install"
version = "1.2.3"
source = "https://playwright.example.invalid"
browser = "chromium"
browser_cache_path = "{}"
verification = {{ kind = "browser-executable", executable_globs = ["chromium-*/chrome"], args = ["--version"], output_contains = "Chromium" }}
deps = []
provides = ["chromium"]
failure_policy = "fail"
"#,
                browser_cache.display()
            ),
        );
        let plan = load_plan(&workspace, Some(&manifest)).expect("toolchain plan parses");
        let program_responses = [
            (
                "rustup-init".to_string(),
                command_output_fixture("installed"),
            ),
            ("rustup".to_string(), command_output_fixture("installed")),
            ("rustup".to_string(), command_output_fixture("installed")),
            ("rustup".to_string(), command_output_fixture("installed")),
            ("elan-init".to_string(), command_output_fixture("installed")),
            ("elan".to_string(), command_output_fixture("")),
            ("elan".to_string(), command_output_fixture("installed")),
            ("elan".to_string(), command_output_fixture("installed")),
            (
                "install".to_string(),
                command_output_fixture("created cache"),
            ),
            (
                "env".to_string(),
                command_output_fixture("installed browser"),
            ),
        ];
        let probe = fake_program_probe(&root, program_responses, std::iter::empty::<Vec<u8>>());
        let mut installer = Installer::with_probe(true, Some(root.0.clone()), probe);
        for record_id in ["rust-toolchain", "lean-toolchain", "browser"] {
            installer
                .install_record(plan.by_id(record_id).unwrap(), &workspace, false)
                .expect("declared provider command succeeds");
        }
        let calls = fixture_invocations(&installer.probe);
        let commands = calls
            .iter()
            .map(|call| call.argv.clone())
            .collect::<Vec<_>>();
        assert_eq!(
            commands[0],
            vec![
                "/usr/local/bin/rustup-init",
                "-y",
                "--default-toolchain",
                "none",
                "--profile",
                "minimal",
                "--no-modify-path",
            ]
        );
        assert_eq!(
            commands[1],
            vec![
                "rustup",
                "toolchain",
                "install",
                "1.99.1",
                "--profile",
                "minimal"
            ]
        );
        assert_eq!(
            commands[2],
            vec![
                "rustup",
                "component",
                "add",
                "rustfmt",
                "--toolchain",
                "1.99.1"
            ]
        );
        assert_eq!(commands[3], vec!["rustup", "default", "1.99.1"]);
        assert_eq!(
            commands[4],
            vec![
                "/usr/local/bin/elan-init",
                "-y",
                "--default-toolchain",
                "leanprover/lean4:v4.30.0",
                "--no-modify-path",
            ]
        );
        assert_eq!(commands[5], vec!["elan", "toolchain", "list"]);
        assert_eq!(
            commands[6],
            vec!["elan", "toolchain", "install", "leanprover/lean4:v4.30.0"]
        );
        assert_eq!(
            commands[7],
            vec!["elan", "default", "leanprover/lean4:v4.30.0"]
        );
        assert_eq!(
            commands[8],
            vec![
                "install",
                "-d",
                "-m",
                "0775",
                browser_cache.to_string_lossy().as_ref()
            ]
        );
        assert_eq!(
            commands[9],
            vec![
                "env".to_string(),
                format!("PLAYWRIGHT_BROWSERS_PATH={}", browser_cache.display()),
                "playwright".to_string(),
                "install".to_string(),
                "--with-deps".to_string(),
                "chromium".to_string(),
            ]
        );
        assert_fake_responses_consumed(&installer.probe);
    }

    #[cfg(unix)]
    #[test]
    fn cargo_source_installer_uses_locked_manifest_build_without_shell_evaluation() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        let source = workspace.join("cargo-source");
        fs::create_dir_all(&source).expect("Cargo source directory is created");
        fs::write(
            source.join("Cargo.toml"),
            "[package]\nname='fixture'\nversion='0.1.0'\n",
        )
        .expect("Cargo manifest fixture is written");
        let manifest = root.write_manifest(
            "dependencies.toml",
            r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-cargo"
package = "fixture-cargo"
method = "cargo-source-build"
version = "0.1.0"
source = "cargo-source"
repo = "https://example.invalid/fixture-cargo.git"
source_identity = "active-source"
locked = true
verification = { kind = "cargo-binary", path = "target/release/fixture", args = ["--version"], output_contains = "fixture 0.1.0" }
deps = []
provides = ["fixture-cargo"]
failure_policy = "fail"
"#,
        );
        let plan = load_plan(&workspace, Some(&manifest)).expect("Cargo record parses");
        let probe = fake_program_probe(
            &root,
            [("cargo".to_string(), command_output_fixture("built"))],
            std::iter::empty::<Vec<u8>>(),
        );
        let mut installer = Installer::with_probe(true, Some(root.0.clone()), probe);
        installer
            .install_record(plan.by_id("fixture-cargo").unwrap(), &workspace, false)
            .expect("Cargo source build starts through the provider");
        let calls = fixture_invocations(&installer.probe);
        assert_eq!(calls.len(), 1);
        assert_eq!(
            calls[0].argv,
            vec![
                "cargo",
                "build",
                "--release",
                "--locked",
                "--manifest-path",
                source.join("Cargo.toml").to_string_lossy().as_ref(),
            ]
        );
        assert!(calls[0].environment.contains_key("CARGO_TARGET_DIR"));
        assert_fake_responses_consumed(&installer.probe);
    }

    // The Ubuntu image contract freezes the tree before its atomic publication.
    #[cfg(target_os = "linux")]
    #[test]
    fn image_install_and_verify_use_frozen_plan_receipts_and_live_executable_output() {
        let root = TempRoot::new();
        let workspace = root.0.join("workspace");
        fs::create_dir_all(&workspace).expect("workspace is created");
        let payload = b"fixture release executable";
        let checksum = Sha256::digest(payload)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let manifest = root.write_manifest(
            "dependencies.toml",
            &format!(
                r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-release"
package = "fixture-release"
method = "release-asset"
version = "1.2.3"
source = "https://example.invalid/fixture-release"
checksum = "{checksum}"
asset = "fixture-release"
archive_format = "binary"
extract = "none"
destination = "/usr/local/bin/fixture-release"
deps = []
provides = ["fixture-release"]
failure_policy = "fail"
[records.verification]
kind = "absolute-executable"
path = "/usr/local/bin/fixture-release"
args = ["--version"]
output_contains = "1.2.3"
"#
            ),
        );
        let plan = load_plan(&workspace, Some(&manifest)).expect("release plan parses");
        let target = root.0.join("frozen-image");
        let installer_probe = fake_program_probe(
            &root,
            [
                ("curl".to_string(), command_output_fixture("downloaded")),
                ("install".to_string(), command_output_fixture("installed")),
            ],
            [payload.to_vec()],
        );
        let installer = Installer::with_probe(true, Some(root.0.clone()), installer_probe);
        let completed = image_install_plan_at(
            &plan,
            &workspace,
            None,
            None,
            installer,
            ImageInstallContext {
                target: &target,
                production: false,
                runtime_identity: Some(RuntimeIdentity {
                    os_id: "ubuntu".to_string(),
                    version_id: "24.04".to_string(),
                    platform: "linux/amd64".to_string(),
                }),
            },
        )
        .expect("native image installer publishes the frozen plan");
        assert_eq!(completed, vec!["fixture-release".to_string()]);
        assert_eq!(
            fs::read(target.join("plan.json"))
                .expect("frozen plan exists")
                .last(),
            Some(&b'\n')
        );
        let receipt: Value = serde_json::from_slice(
            &fs::read(target.join("receipts/fixture-release.json"))
                .expect("immutable release receipt exists"),
        )
        .expect("receipt parses");
        assert_eq!(receipt["status"], "installed");
        assert_eq!(receipt["record_id"], "fixture-release");

        let verifier_probe = fake_probe(
            &root,
            [(
                vec![
                    "/usr/local/bin/fixture-release".to_string(),
                    "--version".to_string(),
                ],
                command_output_fixture("fixture-release 1.2.3"),
            )],
        );
        create_executable(&verifier_probe, "/usr/local/bin/fixture-release");
        let verified = image_verify_plan_at(
            &plan,
            &workspace,
            None,
            &target,
            false,
            Installer::with_probe(true, Some(root.0.clone()), verifier_probe),
        )
        .expect("image verify checks the stored identity and live executable output");
        assert_eq!(verified, vec!["fixture-release".to_string()]);

        let bad_checksum_manifest = root.write_manifest(
            "bad-checksum.toml",
            &format!(
                r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2
[[records]]
id = "fixture-release"
package = "fixture-release"
method = "release-asset"
version = "1.2.3"
source = "https://example.invalid/fixture-release"
checksum = "{}"
asset = "fixture-release"
archive_format = "binary"
extract = "none"
destination = "/usr/local/bin/fixture-release"
deps = []
provides = ["fixture-release"]
failure_policy = "fail"
[records.verification]
kind = "absolute-executable"
path = "/usr/local/bin/fixture-release"
args = ["--version"]
output_contains = "1.2.3"
"#,
                "0".repeat(64)
            ),
        );
        let bad_checksum_plan =
            load_plan(&workspace, Some(&bad_checksum_manifest)).expect("failure plan parses");
        let bad_checksum_probe = fake_program_probe(
            &root,
            [("curl".to_string(), command_output_fixture("downloaded"))],
            [payload.to_vec()],
        );
        let mut bad_checksum_installer =
            Installer::with_probe(true, Some(root.0.clone()), bad_checksum_probe);
        let error = bad_checksum_installer
            .install_record(
                bad_checksum_plan.by_id("fixture-release").unwrap(),
                &workspace,
                false,
            )
            .expect_err("release checksum mismatch prevents installation");
        assert!(error.to_string().contains("release checksum mismatch"));
        assert!(!fixture_invocations(&bad_checksum_installer.probe)
            .iter()
            .any(|call| call
                .argv
                .first()
                .is_some_and(|program| program == "install")));
        assert_fake_responses_consumed(&bad_checksum_installer.probe);

        for directory in [target.join("receipts"), target.clone()] {
            fs::set_permissions(directory, fs::Permissions::from_mode(0o755))
                .expect("make frozen fixture directories removable");
        }
    }

    #[test]
    fn archive_extractors_preserve_safe_files_and_reject_parent_traversal() {
        let root = TempRoot::new();
        let archive_path = root.0.join("fixture.tar");
        let tar_bytes = |name: &str, payload: &[u8]| {
            let mut builder = tar::Builder::new(Vec::new());
            let mut header = tar::Header::new_gnu();
            header.set_size(payload.len() as u64);
            header.set_mode(0o755);
            header.set_entry_type(tar::EntryType::Regular);
            header.set_cksum();
            builder
                .append_data(&mut header, name, payload)
                .expect("write tar fixture entry");
            builder.into_inner().expect("finish tar fixture")
        };

        let safe_tar = tar_bytes("bin/fixture", b"tar payload");
        fs::write(&archive_path, &safe_tar).expect("write safe tar input");
        let tar_destination = root.0.join("tar-output");
        safe_extract_archive(&archive_path, &tar_destination, "tar")
            .expect("extract a regular tar entry");
        assert_eq!(
            fs::read(tar_destination.join("bin/fixture")).expect("read extracted tar entry"),
            b"tar payload"
        );

        let mut gzip = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
        gzip.write_all(&safe_tar).expect("compress tar fixture");
        fs::write(&archive_path, gzip.finish().expect("finish gzip fixture"))
            .expect("write gzip input");
        let gzip_destination = root.0.join("gzip-output");
        safe_extract_archive(&archive_path, &gzip_destination, "tar.gz")
            .expect("extract a gzip-compressed tar entry");
        assert_eq!(
            fs::read(gzip_destination.join("bin/fixture")).expect("read gzip payload"),
            b"tar payload"
        );

        let zip_path = root.0.join("fixture.zip");
        let file = fs::File::create(&zip_path).expect("create zip fixture");
        let mut zip = zip::ZipWriter::new(file);
        zip.start_file(
            "bin/fixture",
            zip::write::SimpleFileOptions::default().unix_permissions(0o755),
        )
        .expect("start zip fixture entry");
        zip.write_all(b"zip payload")
            .expect("write zip fixture entry");
        zip.finish().expect("finish zip fixture");
        let zip_destination = root.0.join("zip-output");
        safe_extract_archive(&zip_path, &zip_destination, "zip")
            .expect("extract a regular zip entry");
        assert_eq!(
            fs::read(zip_destination.join("bin/fixture")).expect("read extracted zip entry"),
            b"zip payload"
        );

        // Append a hostile raw header: tar::Builder::append_data rejects this
        // path before the extractor can receive and validate it.
        let mut hostile_header = tar::Header::new_gnu();
        hostile_header.set_size(b"outside".len() as u64);
        hostile_header.set_mode(0o755);
        hostile_header.set_entry_type(tar::EntryType::Regular);
        hostile_header.as_mut_bytes()[.."../escaped".len()].copy_from_slice(b"../escaped");
        hostile_header.set_cksum();
        let mut hostile_tar = hostile_header.as_bytes().to_vec();
        hostile_tar.extend_from_slice(b"outside");
        hostile_tar.resize(1024, 0);
        fs::write(&archive_path, hostile_tar).expect("write raw traversal tar input");
        let traversal_destination = root.0.join("traversal-output");
        assert!(
            safe_extract_archive(&archive_path, &traversal_destination, "tar")
                .expect_err("tar parent traversal is rejected")
                .to_string()
                .contains("escapes extraction root")
        );
        assert!(!root.0.join("escaped").exists());
    }
}
