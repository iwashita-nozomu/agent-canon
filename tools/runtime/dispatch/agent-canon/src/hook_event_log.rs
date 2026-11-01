//! Canon-owned append-only hook event paths and per-event publication.

// @dependency-start
// contract implementation
// responsibility Owns canonical hook event bytes, local spool paths, and no-replace publication.
// upstream implementation authority/mod.rs owns the attested parent no-replace capability
// upstream implementation runtime_boundary.rs owns explicit runtime spool paths
// downstream test ../tests/hook_event_log_native.rs checks Python bytes and append behavior
// @dependency-end

use crate::authority::{AttestedParent, NonEmptyTrimmedString, ParentOwnedNoReplaceOutcome};
use crate::log_repository_identity::repo_log_key;
use crate::path_resolution::resolve_non_strict;
use crate::python_json::{
    canonical_json_ascii_bytes, canonical_json_ascii_bytes_reject_nonfinite, JsonObject,
    JsonString, JsonValue,
};
use crate::python_text::python_strip;
use crate::runtime_boundary::{RuntimeSpoolBoundary, RUNTIME_ROOT_ENV};
use regex::Regex;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use time::OffsetDateTime;

pub const HOOK_RESULTS_DIR_ENV: &str = "AGENT_CANON_HOOK_RESULTS_DIR";
pub const HOOK_RUN_NAMESPACE_ENV: &str = "AGENT_CANON_HOOK_RUN_NAMESPACE";
pub const HOOK_SOURCE_ROOT_ENV: &str = "AGENT_CANON_HOOK_SOURCE_ROOT";
pub const HOOK_EVENT_SPOOL_DIR_ENV: &str = "AGENT_CANON_HOOK_EVENT_SPOOL_DIR";
pub const FINGERPRINT_HEX_LENGTH: usize = 12;
pub const RUN_ID_DIGEST_LENGTH: usize = 10;
pub const RUN_ID_NONCE_LENGTH: usize = 10;
pub const NAMESPACE_HASH_LENGTH: usize = 8;
pub const MAX_NAMESPACE_LENGTH: usize = 80;
const PARENT_EVENT_PURPOSE: &str = "hook-event-spool";
const CODEX_TRACE_ENV_NAMES: [&str; 3] = [
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
    "CODEX_CONVERSATION_ID",
];

/// Describe the local no-replace result for one hook event.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HookAppendResult {
    pub status: String,
    pub hook_run_id: String,
    pub spool_path: PathBuf,
    pub event_sha256: String,
    pub error_code: String,
}

/// Context for resolving one hook's local event destination.
///
/// `environment` is the caller-supplied process environment snapshot; the
/// active root, hook name, and override path match the Python owner fields.
#[derive(Clone, Debug)]
pub struct HookLogContext {
    pub active_root: PathBuf,
    pub hook_name: String,
    pub override_path: String,
    pub environment: BTreeMap<String, String>,
}

impl HookLogContext {
    pub fn source_root(&self) -> Result<PathBuf, String> {
        let override_root = env_value(&self.environment, HOOK_SOURCE_ROOT_ENV);
        let root = if override_root.is_empty() {
            self.active_root.as_path()
        } else {
            Path::new(&override_root)
        };
        resolve_non_strict(root)
    }

    pub fn explicit_log_sink(&self) -> bool {
        !self.override_path.is_empty()
            || !env_value(&self.environment, HOOK_RESULTS_DIR_ENV).is_empty()
    }

    pub fn spool_root(&self) -> Result<PathBuf, String> {
        if !self.override_path.is_empty() {
            let override_path = PathBuf::from(&self.override_path);
            if override_path
                .extension()
                .and_then(|extension| extension.to_str())
                .is_some_and(|extension| extension.eq_ignore_ascii_case("jsonl"))
            {
                let mut path = override_path.into_os_string();
                path.push(".events");
                return Ok(PathBuf::from(path));
            }
            return Ok(override_path);
        }
        let legacy_results_dir = env_value(&self.environment, HOOK_RESULTS_DIR_ENV);
        if !legacy_results_dir.is_empty() {
            return Ok(PathBuf::from(legacy_results_dir).join(".event-spool"));
        }

        let source_root = self.source_root()?;
        let runtime_root = env_value(&self.environment, RUNTIME_ROOT_ENV);
        if runtime_root.is_empty() {
            return Err(format!(
                "explicit runtime root required; pass --runtime-root or set {RUNTIME_ROOT_ENV}"
            ));
        }
        let boundary =
            RuntimeSpoolBoundary::for_source(&source_root, Some(Path::new(&runtime_root)), false)?;
        let repository_key = repo_log_key(&source_root, &self.environment)
            .map_err(|error| format!("cannot resolve source repository key: {error}"))?;
        let override_root = env_value(&self.environment, HOOK_EVENT_SPOOL_DIR_ENV);
        let candidate = if override_root.is_empty() {
            PathBuf::from("spool")
                .join("hook-events")
                .join(repository_key)
        } else {
            PathBuf::from(override_root).join(repository_key)
        };
        boundary.resolve(&candidate)
    }

    pub fn event_path(&self, hook_run_id: &str) -> Result<PathBuf, String> {
        let path = Path::new(hook_run_id);
        if hook_run_id.is_empty()
            || matches!(hook_run_id, "." | "..")
            || path.file_name().and_then(|name| name.to_str()) != Some(hook_run_id)
        {
            return Err("event_schema_invalid".to_owned());
        }
        Ok(self
            .spool_root()?
            .join(self.runtime_namespace())
            .join(safe_slug(&self.hook_name))
            .join(format!("{hook_run_id}.json")))
    }

    pub fn results_dir(&self) -> Result<PathBuf, String> {
        let override_dir = env_value(&self.environment, HOOK_RESULTS_DIR_ENV);
        if !override_dir.is_empty() {
            return Ok(PathBuf::from(override_dir));
        }
        self.spool_root()
    }

    pub fn result_path(&self) -> Result<PathBuf, String> {
        if !self.override_path.is_empty() {
            return Ok(PathBuf::from(&self.override_path));
        }
        Ok(self
            .spool_root()?
            .join(self.runtime_namespace())
            .join(safe_slug(&self.hook_name)))
    }

    pub fn runtime_namespace(&self) -> String {
        let explicit = env_value(&self.environment, HOOK_RUN_NAMESPACE_ENV);
        if !explicit.is_empty() {
            return safe_slug(&explicit);
        }
        for env_name in ["DEVCONTAINER_PROJECT_NAME", "COMPOSE_PROJECT_NAME"] {
            let value = env_value(&self.environment, env_name);
            if !value.is_empty() {
                return safe_slug(&value);
            }
        }
        if !self.override_path.is_empty() {
            "direct-log-override".to_owned()
        } else {
            "unknown-runtime".to_owned()
        }
    }

    pub fn run_id(&self, timestamp: &str, payload_fingerprint: &str) -> Result<String, String> {
        let mut random = [0_u8; 5];
        getrandom::getrandom(&mut random)
            .map_err(|error| format!("hook run id nonce unavailable: {error}"))?;
        let nonce = encode_hex(&random);
        let digest = fingerprint_json(&string_object([
            ("hook_name", self.hook_name.as_str()),
            ("payload_fingerprint", payload_fingerprint),
            ("timestamp", timestamp),
        ]))?;
        Ok(format!(
            "hook-{}-{}-{}",
            compact_timestamp(timestamp),
            &digest[..RUN_ID_DIGEST_LENGTH],
            &nonce[..RUN_ID_NONCE_LENGTH]
        ))
    }

    pub fn append(
        &self,
        mut entry: JsonValue,
        parent: Option<&AttestedParent>,
    ) -> HookAppendResult {
        let raw_hook_run_id = match &entry {
            JsonValue::Object(object) => object_value(object, "hook_run_id"),
            _ => None,
        };
        let Some(JsonValue::String(raw_hook_run_id)) = raw_hook_run_id else {
            return failed_result("", "event_identity_missing");
        };
        let Some(raw_hook_run_id) = raw_hook_run_id.to_text() else {
            return failed_result("", "event_schema_invalid");
        };
        let hook_run_id = python_strip(&raw_hook_run_id).to_owned();
        if hook_run_id.is_empty() {
            return failed_result("", "event_identity_missing");
        }
        if hook_run_id != raw_hook_run_id {
            return HookAppendResult {
                status: "failed".to_owned(),
                hook_run_id,
                spool_path: PathBuf::new(),
                event_sha256: String::new(),
                error_code: "event_schema_invalid".to_owned(),
            };
        }

        let JsonValue::Object(event) = &mut entry else {
            return failed_result(&hook_run_id, "event_schema_invalid");
        };
        let source_root = match self.source_root() {
            Ok(root) => root,
            Err(_) => return failed_result(&hook_run_id, "spool_unavailable"),
        };
        let source_key = match repo_log_key(&source_root, &self.environment) {
            Ok(key) => key,
            Err(_) => return failed_result(&hook_run_id, "spool_unavailable"),
        };
        object_set(event, "source_repo_key", string_value(&source_key));

        let trace_key = codex_trace_key(&self.environment);
        if !trace_key.is_empty() {
            object_setdefault(event, "codex_trace_key", string_value(&trace_key));
            object_setdefault(event, "codex_thread_id", string_value(&trace_key));
        }
        let namespace = self.runtime_namespace();
        object_set(event, "hook_log_namespace", string_value(&namespace));

        let payload = match canonical_hook_event_bytes(&entry) {
            Ok(bytes) => bytes,
            Err(_) => return failed_result(&hook_run_id, "event_schema_invalid"),
        };
        let event_sha256 = sha256_hex(&payload);
        let path = match self.event_path(&hook_run_id) {
            Ok(path) => path,
            Err(error) if error == "event_schema_invalid" => {
                return failed_result(&hook_run_id, "event_schema_invalid");
            }
            Err(_) => return failed_result(&hook_run_id, "spool_unavailable"),
        };
        let Some(parent) = parent else {
            return HookAppendResult {
                status: "failed".to_owned(),
                hook_run_id,
                spool_path: path,
                event_sha256,
                error_code: "parent_unattested".to_owned(),
            };
        };
        let purpose = NonEmptyTrimmedString::new(PARENT_EVENT_PURPOSE)
            .expect("static parent-owned purpose is non-empty");
        let (status, error_code) =
            match parent.publish_parent_owned_file_noreplace(&path, &payload, purpose) {
                Ok(ParentOwnedNoReplaceOutcome::Published(_)) => ("spooled", ""),
                Ok(ParentOwnedNoReplaceOutcome::Duplicate(_)) => ("duplicate", ""),
                Ok(ParentOwnedNoReplaceOutcome::Conflict(_)) => ("failed", "spool_conflict"),
                Err(_) => ("failed", "parent_unattested"),
            };
        HookAppendResult {
            status: status.to_owned(),
            hook_run_id,
            spool_path: path,
            event_sha256,
            error_code: error_code.to_owned(),
        }
    }
}

pub fn safe_slug(value: &str) -> String {
    static INVALID_SEGMENT: OnceLock<Regex> = OnceLock::new();
    let invalid = INVALID_SEGMENT.get_or_init(|| {
        Regex::new(r"[^A-Za-z0-9_.-]+").expect("constant slug expression is valid")
    });
    let replaced = invalid.replace_all(value, "-");
    let slug = replaced
        .trim_matches(|character| matches!(character, '.' | '_' | '-'))
        .to_ascii_lowercase();
    let slug = slug.chars().take(MAX_NAMESPACE_LENGTH).collect::<String>();
    let slug = slug.trim_matches(|character| matches!(character, '.' | '_' | '-'));
    if slug.is_empty() {
        "unknown-runtime".to_owned()
    } else {
        slug.to_owned()
    }
}

pub fn utc_now() -> String {
    let now = OffsetDateTime::now_utc();
    let mut timestamp = format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        now.year(),
        now.month().number_from_month(),
        now.day(),
        now.hour(),
        now.minute(),
        now.second()
    );
    let microseconds = now.nanosecond() / 1_000;
    if microseconds > 0 {
        timestamp.push_str(&format!(".{microseconds:06}"));
    }
    timestamp.push('Z');
    timestamp
}

pub fn compact_timestamp(timestamp: &str) -> String {
    timestamp
        .replace('-', "")
        .replace(':', "")
        .replace("+00:00", "Z")
        .replace('.', "")
}

pub fn fingerprint_json(value: &JsonValue) -> Result<String, String> {
    let payload = canonical_json_ascii_bytes(value)?;
    Ok(sha256_hex(&payload)[..FINGERPRINT_HEX_LENGTH].to_owned())
}

pub fn short_hash(value: &str) -> String {
    sha256_hex(value.as_bytes())[..NAMESPACE_HASH_LENGTH].to_owned()
}

pub fn canonical_hook_event_bytes(entry: &JsonValue) -> Result<Vec<u8>, String> {
    let JsonValue::Object(object) = entry else {
        return Err("event_schema_invalid".to_owned());
    };
    for key in [
        "hook_run_id",
        "timestamp",
        "payload_fingerprint",
        "status",
        "source_repo_key",
        "hook_log_namespace",
    ] {
        let Some(JsonValue::String(value)) = object_value(object, key) else {
            return Err(key.to_owned());
        };
        let text = value.to_text();
        if text
            .as_deref()
            .is_some_and(|text| python_strip(text).is_empty())
        {
            return Err(key.to_owned());
        }
    }
    let mut bytes = canonical_json_ascii_bytes_reject_nonfinite(entry)
        .map_err(|_| "event_schema_invalid".to_owned())?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn string_object<const N: usize>(values: [(&str, &str); N]) -> JsonValue {
    JsonValue::Object(JsonObject(
        values
            .into_iter()
            .map(|(key, value)| (JsonString::from_text(key), string_value(value)))
            .collect(),
    ))
}

fn string_value(value: &str) -> JsonValue {
    JsonValue::String(JsonString::from_text(value))
}

fn object_value<'a>(object: &'a JsonObject, key: &str) -> Option<&'a JsonValue> {
    object
        .0
        .iter()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
        .map(|(_, value)| value)
}

fn object_set(object: &mut JsonObject, key: &str, value: JsonValue) {
    if let Some((_, previous)) = object
        .0
        .iter_mut()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
    {
        *previous = value;
    } else {
        object.0.push((JsonString::from_text(key), value));
    }
}

fn object_setdefault(object: &mut JsonObject, key: &str, value: JsonValue) {
    if object_value(object, key).is_none() {
        object.0.push((JsonString::from_text(key), value));
    }
}

fn codex_trace_key(environment: &BTreeMap<String, String>) -> String {
    CODEX_TRACE_ENV_NAMES
        .iter()
        .find_map(|name| nonempty_env_value(environment, name))
        .unwrap_or_default()
}

fn env_value(environment: &BTreeMap<String, String>, name: &str) -> String {
    environment
        .get(name)
        .map(|value| python_strip(value).to_owned())
        .unwrap_or_default()
}

fn nonempty_env_value(environment: &BTreeMap<String, String>, name: &str) -> Option<String> {
    let value = env_value(environment, name);
    (!value.is_empty()).then_some(value)
}

fn encode_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut encoded = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        encoded.push(HEX[(byte >> 4) as usize] as char);
        encoded.push(HEX[(byte & 0x0f) as usize] as char);
    }
    encoded
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn failed_result(hook_run_id: &str, error_code: &str) -> HookAppendResult {
    HookAppendResult {
        status: "failed".to_owned(),
        hook_run_id: hook_run_id.to_owned(),
        spool_path: PathBuf::new(),
        event_sha256: String::new(),
        error_code: error_code.to_owned(),
    }
}
