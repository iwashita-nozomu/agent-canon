//! Shared writer-target parsing and read-only packet validation.
// @dependency-start
// contract implementation
// responsibility Validates prepared checkout targets, identities, and static writer packets.
// upstream implementation path_resolution.rs owns non-strict physical path resolution
// upstream implementation path_expansion.rs owns Python-compatible user-home expansion
// upstream implementation python_json.rs owns Python-compatible JSON strings and canonical bytes
// downstream implementation mutation_authority.rs mutation decision consumes the validated packet
// downstream implementation ../tests/writer_target_native.rs compares the frozen CPython oracle
// @dependency-end

use crate::path_expansion::expand_user_path;
use crate::path_resolution::resolve_non_strict;
use crate::python_json::{
    canonical_json_ascii_bytes, JsonArray, JsonObject, JsonString, JsonValue,
};
use crate::python_text::is_python_whitespace;
use icu_casemap::CaseMapper;
use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::path::{Component, Path, PathBuf};

pub const WRITER_TARGET_SCHEMA: &str = "agent-canon.writer-target.v1";
pub const WRITER_TARGET_PACKET_SCHEMA: &str = "agent-canon.writer-target-packet.v1";
pub const WRITER_TARGET_PACKET_RELATIVE: &str = ".agent-canon/writer-target.json";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WriterTargetError {
    code: String,
}

impl WriterTargetError {
    fn new(code: impl Into<String>) -> Self {
        Self { code: code.into() }
    }

    pub fn code(&self) -> &str {
        &self.code
    }
}

impl fmt::Display for WriterTargetError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.code)
    }
}

impl std::error::Error for WriterTargetError {}

/// One validated writer target, preserving its input spelling for projections.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WriterTarget {
    checkout_root: JsonString,
    branch: JsonString,
    remote: JsonString,
    allowed_paths: Vec<JsonString>,
}

impl WriterTarget {
    /// Construct one target with the old dataclass's field-validation order.
    pub fn new(
        checkout_root: JsonString,
        branch: JsonString,
        remote: JsonString,
        allowed_paths: Vec<JsonString>,
    ) -> Result<Self, WriterTargetError> {
        let expanded_root = expand_path(&checkout_root)?;
        if !expanded_root.is_absolute() {
            return Err(WriterTargetError::new(
                "writer_target:checkout_root_must_be_absolute",
            ));
        }
        if branch.is_empty()
            || has_python_edge_whitespace(&branch)
            || branch.0.contains(&u32::from('\n'))
        {
            return Err(WriterTargetError::new("writer_target:branch_must_be_named"));
        }
        if !remote_is_owner_repository(&remote) {
            return Err(WriterTargetError::new(
                "writer_target:remote_must_be_owner_repository",
            ));
        }
        validate_allowed_paths(&allowed_paths)?;
        Ok(Self {
            checkout_root,
            branch,
            remote,
            allowed_paths,
        })
    }

    pub fn checkout_root(&self) -> &JsonString {
        &self.checkout_root
    }

    pub fn branch(&self) -> &JsonString {
        &self.branch
    }

    pub fn remote(&self) -> &JsonString {
        &self.remote
    }

    pub fn allowed_paths(&self) -> &[JsonString] {
        &self.allowed_paths
    }

    /// Return the expanded, non-strict physical checkout path.
    pub fn normalized_root(&self) -> Result<JsonString, WriterTargetError> {
        let expanded = expand_path(&self.checkout_root)?;
        let resolved = resolve_non_strict(&expanded).map_err(WriterTargetError::new)?;
        Ok(JsonString::from_text(&resolved.to_string_lossy()))
    }

    /// Return Python-compatible Unicode casefolding for the remote identifier.
    pub fn normalized_remote(&self) -> JsonString {
        casefold(&self.remote)
    }

    /// Return the existing handoff projection.
    pub fn as_dict(&self) -> Result<JsonValue, WriterTargetError> {
        Ok(JsonValue::Object(JsonObject(vec![
            (
                JsonString::from_text("schema"),
                JsonValue::String(JsonString::from_text(WRITER_TARGET_SCHEMA)),
            ),
            (
                JsonString::from_text("checkout_root"),
                JsonValue::String(self.normalized_root()?),
            ),
            (
                JsonString::from_text("branch"),
                JsonValue::String(self.branch.clone()),
            ),
            (
                JsonString::from_text("remote"),
                JsonValue::String(self.normalized_remote()),
            ),
            (
                JsonString::from_text("allowed_paths"),
                JsonValue::Array(JsonArray(
                    self.allowed_paths
                        .iter()
                        .cloned()
                        .map(JsonValue::String)
                        .collect(),
                )),
            ),
        ])))
    }

    /// Return the structured PreToolUse environment projection.
    pub fn environment(&self) -> Result<BTreeMap<String, JsonString>, WriterTargetError> {
        let paths = JsonValue::Array(JsonArray(
            self.allowed_paths
                .iter()
                .cloned()
                .map(JsonValue::String)
                .collect(),
        ));
        let allowed_paths = canonical_json_ascii_bytes(&paths).map_err(WriterTargetError::new)?;
        let allowed_paths = String::from_utf8(allowed_paths).map_err(|_| {
            WriterTargetError::new("writer_target:allowed_paths_serialization_failed")
        })?;
        Ok(BTreeMap::from([
            (
                "AGENT_CANON_CHECKOUT_ROOT".to_owned(),
                self.normalized_root()?,
            ),
            (
                "AGENT_CANON_CHECKOUT_BRANCH".to_owned(),
                self.branch.clone(),
            ),
            (
                "AGENT_CANON_WRITER_ALLOWED_PATHS".to_owned(),
                JsonString::from_text(&allowed_paths),
            ),
        ]))
    }
}

/// Parse one typed writer target from shared Python-compatible JSON values.
pub fn parse_writer_target(value: &JsonValue) -> Result<WriterTarget, WriterTargetError> {
    let JsonValue::Object(object) = value else {
        return Err(WriterTargetError::new("writer_target:must_be_mapping"));
    };
    let mut unknown = object
        .0
        .iter()
        .filter(|(key, _)| !writer_target_field(key))
        .map(|(key, _)| key.clone())
        .collect::<Vec<_>>();
    unknown.sort();
    unknown.dedup();
    if !unknown.is_empty() {
        let names = unknown
            .iter()
            .map(|key| key.to_text().unwrap_or_else(|| "�".to_owned()))
            .collect::<Vec<_>>();
        return Err(WriterTargetError::new(format!(
            "writer_target:unknown_fields:{}",
            names.join(",")
        )));
    }
    if let Some(schema) = object_value(value, "schema") {
        if !matches!(schema, JsonValue::String(schema) if schema.equals_text(WRITER_TARGET_SCHEMA))
        {
            return Err(WriterTargetError::new("writer_target:schema_mismatch"));
        }
    }

    // The old parser checks this required field before evaluating constructor fields.
    let remote = casefold(&required_string(object_value(value, "remote"), "remote")?);
    let checkout_root = required_string(object_value(value, "checkout_root"), "checkout_root")?;
    let branch = required_string(object_value(value, "branch"), "branch")?;
    let allowed_paths = relative_paths(object_value(value, "allowed_paths"))?;
    WriterTarget::new(checkout_root, branch, remote, allowed_paths)
}

/// Require the observed checkout identity to match one parsed target.
pub fn validate_writer_target_identity(
    target: &WriterTarget,
    checkout_identity: &JsonValue,
) -> Result<WriterTarget, WriterTargetError> {
    if !matches!(checkout_identity, JsonValue::Object(_)) {
        return Err(WriterTargetError::new(
            "writer_target:checkout_identity_required",
        ));
    }
    let normalized_root = target.normalized_root()?;
    for field in ["git_root", "cwd"] {
        let Some(value) = object_value(checkout_identity, field).and_then(json_string_text) else {
            return Err(WriterTargetError::new(
                "writer_target:checkout_root_identity_mismatch",
            ));
        };
        let resolved = resolve_non_strict(&PathBuf::from(value))
            .map_err(|_| WriterTargetError::new("writer_target:checkout_root_identity_mismatch"))?;
        if resolved.to_string_lossy() != normalized_root.to_text().unwrap_or_default() {
            return Err(WriterTargetError::new(
                "writer_target:checkout_root_identity_mismatch",
            ));
        }
    }
    if object_string(checkout_identity, "branch") != Some(&target.branch) {
        return Err(WriterTargetError::new(
            "writer_target:branch_identity_mismatch",
        ));
    }
    if object_string(checkout_identity, "remote") != Some(&target.normalized_remote()) {
        return Err(WriterTargetError::new(
            "writer_target:remote_identity_mismatch",
        ));
    }
    Ok(target.clone())
}

/// Read and validate the existing static writer-target packet without mutation.
pub fn read_writer_target_packet(
    checkout_root: &Path,
) -> Result<(WriterTarget, JsonValue), WriterTargetError> {
    let expanded_root = expand_user_path(checkout_root)
        .map_err(|error| WriterTargetError::new(error.to_string()))?;
    let root = resolve_path(&expanded_root)?;
    let path = writer_target_packet_path(&root)?;
    let content = match fs::read_to_string(&path) {
        Ok(content) => content,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Err(WriterTargetError::new("writer_target_packet_missing"));
        }
        Err(_) => return Err(WriterTargetError::new("writer_target_packet_invalid")),
    };
    let packet = crate::python_json::parse_json(&content)
        .map_err(|_| WriterTargetError::new("writer_target_packet_invalid"))?;
    let JsonValue::Object(mut entries) = packet else {
        return Err(WriterTargetError::new("writer_target_packet_invalid"));
    };
    let schema = entries
        .0
        .iter()
        .rev()
        .find(|(key, _)| key.equals_text("schema"))
        .map(|(_, value)| value);
    if !matches!(schema, Some(JsonValue::String(schema)) if schema.equals_text(WRITER_TARGET_PACKET_SCHEMA))
    {
        return Err(WriterTargetError::new("writer_target_packet_invalid"));
    }
    let identity_is_object = entries
        .0
        .iter()
        .rev()
        .find(|(key, _)| key.equals_text("checkout_identity"))
        .is_some_and(|(_, value)| matches!(value, JsonValue::Object(_)));
    if !identity_is_object {
        return Err(WriterTargetError::new("writer_target_packet_invalid"));
    }

    let mut target_entries = Vec::new();
    let mut identity = None;
    for (key, value) in std::mem::take(&mut entries.0) {
        if key.equals_text("schema") {
            continue;
        }
        if key.equals_text("checkout_identity") {
            identity = Some(value);
        } else {
            target_entries.push((key, value));
        }
    }
    let target_value = JsonValue::Object(JsonObject(target_entries));
    let target = parse_writer_target(&target_value)
        .map_err(|_| WriterTargetError::new("writer_target_packet_invalid"))?;
    let identity = identity.expect("checked packet identity remains present");
    validate_writer_target_identity(&target, &identity)
        .map_err(|_| WriterTargetError::new("writer_target_packet_identity_mismatch"))?;
    if target.normalized_root()? != JsonString::from_text(&root.to_string_lossy()) {
        return Err(WriterTargetError::new(
            "writer_target_packet_identity_mismatch",
        ));
    }
    Ok((target, identity))
}

fn writer_target_field(key: &JsonString) -> bool {
    [
        "schema",
        "checkout_root",
        "branch",
        "remote",
        "allowed_paths",
    ]
    .iter()
    .any(|field| key.equals_text(field))
}

fn object_value<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(JsonObject(entries)) = value else {
        return None;
    };
    entries
        .iter()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
        .map(|(_, value)| value)
}

fn object_string<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonString> {
    match object_value(value, key)? {
        JsonValue::String(value) => Some(value),
        _ => None,
    }
}

fn json_string_text(value: &JsonValue) -> Option<String> {
    match value {
        JsonValue::String(value) => value.to_text(),
        _ => None,
    }
}

fn required_string(
    value: Option<&JsonValue>,
    field: &str,
) -> Result<JsonString, WriterTargetError> {
    let Some(JsonValue::String(value)) = value else {
        return Err(WriterTargetError::new(format!(
            "writer_target:{field}_required"
        )));
    };
    if json_string_strip_empty(value) {
        Err(WriterTargetError::new(format!(
            "writer_target:{field}_required"
        )))
    } else {
        Ok(value.clone())
    }
}

fn relative_paths(value: Option<&JsonValue>) -> Result<Vec<JsonString>, WriterTargetError> {
    let Some(JsonValue::Array(JsonArray(paths))) = value else {
        return Err(WriterTargetError::new(
            "writer_target:allowed_paths_required",
        ));
    };
    if paths.is_empty() {
        return Err(WriterTargetError::new(
            "writer_target:allowed_paths_required",
        ));
    }
    paths
        .iter()
        .map(|path| {
            let JsonValue::String(path) = path else {
                return Err(WriterTargetError::new(
                    "writer_target:allowed_path_required",
                ));
            };
            if json_string_strip_empty(path) {
                return Err(WriterTargetError::new(
                    "writer_target:allowed_path_required",
                ));
            }
            validate_relative_allowed_path(path)?;
            Ok(path.clone())
        })
        .collect()
}

fn validate_relative_allowed_path(path: &JsonString) -> Result<(), WriterTargetError> {
    let Some(path_text) = path.to_text() else {
        return Err(WriterTargetError::new(
            "writer_target:allowed_path_unrepresentable",
        ));
    };
    let candidate = Path::new(&path_text);
    if candidate.is_absolute()
        || candidate
            .components()
            .any(|component| matches!(component, Component::ParentDir))
        || path_text.contains('\\')
        || path_text.contains("//")
    {
        return Err(WriterTargetError::new(format!(
            "writer_target:allowed_path_not_relative:{path_text}"
        )));
    }
    Ok(())
}

fn validate_allowed_paths(paths: &[JsonString]) -> Result<(), WriterTargetError> {
    if paths.is_empty() {
        return Err(WriterTargetError::new(
            "writer_target:allowed_paths_required",
        ));
    }
    for path in paths {
        if path.is_empty() {
            let text = path.to_text().unwrap_or_default();
            return Err(WriterTargetError::new(format!(
                "writer_target:allowed_path_not_relative:{text}"
            )));
        }
        validate_relative_allowed_path(path)?;
    }
    Ok(())
}

fn remote_is_owner_repository(remote: &JsonString) -> bool {
    let mut slash = None;
    for (index, codepoint) in remote.0.iter().copied().enumerate() {
        if codepoint_is_python_whitespace(codepoint) {
            return false;
        }
        if codepoint == u32::from('/') {
            if slash.is_some() {
                return false;
            }
            slash = Some(index);
        }
    }
    slash.is_some_and(|index| index > 0 && index + 1 < remote.0.len())
}

fn json_string_strip_empty(value: &JsonString) -> bool {
    value
        .0
        .iter()
        .all(|codepoint| codepoint_is_python_whitespace(*codepoint))
}

fn has_python_edge_whitespace(value: &JsonString) -> bool {
    value
        .0
        .first()
        .is_some_and(|codepoint| codepoint_is_python_whitespace(*codepoint))
        || value
            .0
            .last()
            .is_some_and(|codepoint| codepoint_is_python_whitespace(*codepoint))
}

fn codepoint_is_python_whitespace(codepoint: u32) -> bool {
    char::from_u32(codepoint).is_some_and(is_python_whitespace)
}

fn casefold(value: &JsonString) -> JsonString {
    let mapper = CaseMapper::new();
    let mut output = Vec::new();
    let mut text = String::new();
    for codepoint in &value.0 {
        if let Some(character) = char::from_u32(*codepoint) {
            text.push(character);
        } else {
            output.extend(mapper.fold_string(&text).chars().map(u32::from));
            text.clear();
            output.push(*codepoint);
        }
    }
    output.extend(mapper.fold_string(&text).chars().map(u32::from));
    JsonString(output)
}

fn expand_path(path: &JsonString) -> Result<PathBuf, WriterTargetError> {
    let text = path
        .to_text()
        .ok_or_else(|| WriterTargetError::new("writer_target:path_unrepresentable"))?;
    expand_user_path(Path::new(&text)).map_err(|error| WriterTargetError::new(error.to_string()))
}

fn resolve_path(path: &Path) -> Result<PathBuf, WriterTargetError> {
    resolve_non_strict(path).map_err(WriterTargetError::new)
}

fn writer_target_packet_path(root: &Path) -> Result<PathBuf, WriterTargetError> {
    let path = root.join(WRITER_TARGET_PACKET_RELATIVE);
    let parent = path
        .parent()
        .expect("writer-target packet path always has a parent");
    match fs::symlink_metadata(parent) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
            return Err(WriterTargetError::new("writer_target_packet_path_unsafe"));
        }
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => return Err(WriterTargetError::new("writer_target_packet_path_unsafe")),
    }
    match fs::symlink_metadata(&path) {
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
            Err(WriterTargetError::new("writer_target_packet_path_unsafe"))
        }
        Ok(_) => Ok(path),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(path),
        Err(_) => Err(WriterTargetError::new("writer_target_packet_path_unsafe")),
    }
}
