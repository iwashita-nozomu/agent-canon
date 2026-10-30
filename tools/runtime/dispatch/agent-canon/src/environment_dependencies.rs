//! Full environment-dependency plan identity and read-only executable receipts.
// @dependency-start
// contract implementation
// responsibility Validates complete environment dependency plans and resolves receipt-bound executable capabilities.
// upstream implementation artifacts/artifact_identity.rs owns canonical ASCII JSON bytes
// upstream implementation ../artifacts/artifact_identity.rs provides SHA-256-compatible JSON bytes
// upstream design ../../../../../../tools/runtime/container/devcontainer_dependencies.py owns manifest and receipt semantics
// downstream implementation ../main.rs and future LSP/SCIP consumers use verified executable paths
// downstream test ../../tests/environment_dependencies_native.rs validates plan and executable receipt behavior
// @dependency-end

use crate::artifacts::artifact_identity::canonical_json_ascii_bytes;
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
        let normalized = normalized_string(item, field)?;
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

#[derive(Debug, Clone)]
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
    Ok(CommandOutput { stdout, stderr })
}

#[derive(Debug, Clone)]
struct CommandOutput {
    stdout: String,
    stderr: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CommandInvocation {
    argv: Vec<String>,
    workspace: PathBuf,
    path: Option<String>,
    cargo_home: Option<String>,
    clear_rustup_overrides: bool,
    operation: String,
    record_id: String,
}

#[cfg(test)]
#[derive(Debug, Default)]
struct FakeCommandRunner {
    responses: std::cell::RefCell<BTreeMap<Vec<String>, VecDeque<CommandOutput>>>,
    invocations: std::cell::RefCell<Vec<CommandInvocation>>,
}

#[cfg(test)]
impl FakeCommandRunner {
    fn with_responses(responses: impl IntoIterator<Item = (Vec<String>, CommandOutput)>) -> Self {
        let mut response_map = BTreeMap::<Vec<String>, VecDeque<CommandOutput>>::new();
        for (argv, output) in responses {
            response_map.entry(argv).or_default().push_back(output);
        }
        Self {
            responses: std::cell::RefCell::new(response_map),
            invocations: std::cell::RefCell::new(Vec::new()),
        }
    }
}

enum CommandRunner {
    System,
    #[cfg(test)]
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
        let Ok(metadata) = fs::metadata(physical) else {
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
        #[cfg(windows)]
        {
            path.extension()
                .and_then(|value| value.to_str())
                .is_some_and(|value| {
                    matches!(
                        value.to_ascii_lowercase().as_str(),
                        "exe" | "com" | "bat" | "cmd"
                    )
                })
        }
        #[cfg(not(any(unix, windows)))]
        {
            false
        }
    }

    fn execute(&self, invocation: &CommandInvocation) -> Result<CommandOutput> {
        match &self.command_runner {
            CommandRunner::System => {
                let mut process = Command::new(&invocation.argv[0]);
                process
                    .args(&invocation.argv[1..])
                    .current_dir(&invocation.workspace);
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
                let output = process.output().map_err(|error| {
                    DependencyError::new(format!(
                        "{}: {} command failed to start: {error}",
                        invocation.record_id, invocation.operation
                    ))
                })?;
                command_output(output, &invocation.record_id, &invocation.operation)
            }
            #[cfg(test)]
            CommandRunner::Fake(runner) => {
                runner.invocations.borrow_mut().push(invocation.clone());
                runner
                    .responses
                    .borrow_mut()
                    .get_mut(&invocation.argv)
                    .and_then(VecDeque::pop_front)
                    .ok_or_else(|| {
                        DependencyError::new(format!(
                            "{}: unexpected test provider command for {}",
                            invocation.record_id, invocation.operation
                        ))
                    })
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

#[cfg(test)]
mod tests {
    use super::*;
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
            Self(path)
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

    fn receipt_binding(name: &str, path: &str, output: &str) -> Value {
        json!({
            "provided": name,
            "lexical_path": path,
            "absolute_path": path,
            "verification_output": output,
        })
    }

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

    fn command_output_fixture(stdout: &str) -> CommandOutput {
        CommandOutput {
            stdout: stdout.to_string(),
            stderr: String::new(),
        }
    }

    fn fixture_invocations(probe: &ProbeEnvironment) -> Vec<CommandInvocation> {
        let CommandRunner::Fake(runner) = &probe.command_runner else {
            panic!("test resolver uses only the per-test fake command runner")
        };
        runner.invocations.borrow().clone()
    }

    fn assert_fake_responses_consumed(probe: &ProbeEnvironment) {
        let CommandRunner::Fake(runner) = &probe.command_runner else {
            panic!("test resolver uses only the per-test fake command runner")
        };
        assert!(runner
            .responses
            .borrow()
            .values()
            .all(|responses| responses.is_empty()));
    }

    fn write_success_manifest(root: &TempRoot, text: &str) -> PathBuf {
        root.write_manifest("workspace/dependencies.toml", text)
    }

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
        // Frozen independently from the pre-migration Python build_plan owner.
        let manifest = root.join("bootstrap/container/image/dependencies.toml");
        let manifest_bytes = fs::read(&manifest).expect("canonical manifest bytes are readable");
        assert_eq!(
            sha256_hex(&manifest_bytes),
            "2ad12d007239bc2fff90ba3c8c81ca9270610c69ba38b588980459f4b6b9c52a"
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
        let expected_fingerprint = match env::consts::ARCH {
            "x86_64" | "amd64" => {
                "69f80ebba0abca46cfd219a4174a8dc3a6a534fb336e2d71da5a7e4fa4ba0d85"
            }
            "aarch64" | "arm64" => {
                "9eba38a548d37d212b7c5d03fc90a9aac6d073a62a1701a7469a0506dd4b89de"
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
    fn provider_closure_and_stable_order_include_every_record_payload() {
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
deps = ["provider-capability"]
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
provides = ["provider-capability"]
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
}
