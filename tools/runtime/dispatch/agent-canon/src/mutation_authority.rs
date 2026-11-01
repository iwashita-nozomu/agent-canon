//! Read-only PreToolUse mutation classification and child-scope admission.
// @dependency-start
// contract implementation
// responsibility Classifies repository write requests and admits only authenticated child writes within the active writer target.
// upstream implementation writer_target.rs owns static checkout target validation
// upstream implementation path_resolution.rs owns non-strict filesystem path resolution
// upstream implementation path_expansion.rs owns user-home expansion
// downstream test ../tests/mutation_authority_native.rs compares full decisions with frozen Python cases
// @dependency-end

use crate::path_expansion::expand_user_path;
use crate::path_resolution::resolve_non_strict;
use crate::python_json::{
    canonical_json_ascii_bytes, JsonArray, JsonObject, JsonString, JsonValue,
};
use crate::python_text::is_python_whitespace;
use crate::writer_target::{
    read_writer_target_packet, WriterTarget, WRITER_TARGET_PACKET_RELATIVE,
};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

pub const IDENTITY_SCHEMA: &str = "agent-canon.runtime-agent-identity.v1";
pub const MUTATION_DECISION_SCHEMA: &str = "agent-canon.mutation-authority.v1";
pub const RUNTIME_AGENT_ID_ENV: &str = "AGENT_CANON_RUNTIME_AGENT_ID";
pub const RUNTIME_ROLE_ID_ENV: &str = "AGENT_CANON_RUNTIME_ROLE_ID";
pub const RUNTIME_PARENT_AGENT_ID_ENV: &str = "AGENT_CANON_RUNTIME_PARENT_AGENT_ID";
pub const WRITER_CHECKOUT_ROOT_ENV: &str = "AGENT_CANON_CHECKOUT_ROOT";
pub const WRITER_BRANCH_ENV: &str = "AGENT_CANON_CHECKOUT_BRANCH";
pub const WRITER_ALLOWED_PATHS_ENV: &str = "AGENT_CANON_WRITER_ALLOWED_PATHS";
pub const IDENTITY_RECEIPT_RELATIVE: &str = "runtime/agent_identity.json";
pub const UNRESOLVED_SHELL_PATH: &str = "/__agent_canon_unresolved_shell_path__";

const PARENT_ROLE_IDS: &[&str] = &["parent", "sol_parent", "manager", "manager_reviewer"];
const READONLY_COMMANDS: &[&str] = &[
    "cat", "find", "git", "head", "ls", "pwd", "rg", "sed", "tail", "type", "which",
];
const READONLY_GIT_SUBCOMMANDS: &[&str] = &[
    "branch",
    "diff",
    "log",
    "ls-files",
    "remote",
    "rev-parse",
    "show",
    "status",
];
const MUTATING_COMMANDS: &[&str] = &[
    "apply_patch",
    "cargo",
    "chmod",
    "cp",
    "docker",
    "make",
    "mkdir",
    "mv",
    "perl",
    "pytest",
    "python",
    "python3",
    "rm",
    "sed",
    "tee",
    "touch",
];
const SHELL_CONTROL_TOKENS: &[&str] = &[";", "&&", "||", "|", "&", "(", ")", ";;", ";&", ";;&"];
const SHELL_COMMAND_PREFIXES: &[&str] = &["env", "command", "sudo", "exec", "builtin", "time", "!"];
const OPAQUE_SHELL_COMMANDS: &[&str] = &[".", "source", "eval", "xargs"];
const SHELL_ASSIGNMENT_START: &str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_";
const SHELL_ASSIGNMENT_CONTINUE: &str =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789";
const GIT_NON_PATH_VALUE_OPTIONS: &[&str] = &[
    "-C",
    "-c",
    "-F",
    "-t",
    "-m",
    "--message",
    "--author",
    "--cleanup",
    "--reuse-message",
    "--reedit-message",
    "--fixup",
    "--squash",
    "--format",
    "--pretty",
    "--date",
    "--output",
    "--file",
    "--template",
    "--trailer",
];
const GIT_SHORT_VALUE_OPTIONS: &[char] = &['C', 'F', 'c', 'm', 't'];
const GIT_COMMIT_PATHSPEC_FILE_OPTIONS: &[&str] = &["--pathspec-from-file", "--pathspec-file-nul"];
const GIT_COMMIT_REPOSITORY_REDIRECT_ENV: &[&str] = &[
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_WORK_TREE",
];
const GIT_OUTPUT_SUBCOMMANDS: &[&str] = &["archive", "diff", "log", "show"];
const SHELL_ANALYSIS_MAX_DEPTH: usize = 32;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MutationAuthorityDecision {
    pub status: String,
    pub reason: String,
    pub mutation: bool,
    pub actor_id: JsonString,
    pub role_id: JsonString,
    pub parent_agent_id: JsonString,
    pub scope_digest: JsonString,
    pub mutation_paths: Vec<JsonString>,
    pub evidence_ref: JsonString,
    pub command_sha256: String,
}

impl MutationAuthorityDecision {
    pub fn as_dict(&self) -> JsonValue {
        JsonValue::Object(JsonObject(vec![
            (text_key("schema"), text_value(MUTATION_DECISION_SCHEMA)),
            (text_key("status"), text_value(&self.status)),
            (text_key("reason"), text_value(&self.reason)),
            (text_key("mutation"), JsonValue::Bool(self.mutation)),
            (
                text_key("actor_id"),
                JsonValue::String(self.actor_id.clone()),
            ),
            (text_key("role_id"), JsonValue::String(self.role_id.clone())),
            (
                text_key("parent_agent_id"),
                JsonValue::String(self.parent_agent_id.clone()),
            ),
            (
                text_key("scope_digest"),
                JsonValue::String(self.scope_digest.clone()),
            ),
            (
                text_key("mutation_paths"),
                JsonValue::Array(JsonArray(
                    self.mutation_paths
                        .iter()
                        .cloned()
                        .map(JsonValue::String)
                        .collect(),
                )),
            ),
            (
                text_key("evidence_ref"),
                JsonValue::String(self.evidence_ref.clone()),
            ),
            (text_key("command_sha256"), text_value(&self.command_sha256)),
        ]))
    }
}

pub struct MutationAuthorityContext<'a> {
    pub report_dir: Option<&'a Path>,
    pub active_root: &'a Path,
    pub environment: &'a BTreeMap<String, String>,
    pub hook_spool_root: Option<&'a Path>,
}

struct IdentityReceipt {
    agent_id: JsonString,
    role_id: JsonString,
    parent_agent_id: JsonString,
    scope_digest: JsonString,
    original: JsonValue,
}

/// Return the generic Hook block payload without command or patch contents.
pub fn mutation_block_payload(decision: &MutationAuthorityDecision) -> JsonValue {
    JsonValue::Object(JsonObject(vec![
        (text_key("decision"), text_value("block")),
        (
            text_key("reason"),
            text_value(
                "Repository mutation is restricted to an authenticated write-capable child scope.",
            ),
        ),
        (
            text_key("next_action"),
            text_value("launch_or_resume_write_capable_child_with_runtime_identity_receipt"),
        ),
        (text_key("mutation_authority"), text_value(&decision.reason)),
    ]))
}

/// Classify one PreToolUse payload against authenticated receipt and target inputs.
pub fn evaluate_mutation_authority(
    payload: &JsonValue,
    context: &MutationAuthorityContext<'_>,
) -> MutationAuthorityDecision {
    let JsonValue::Object(_) = payload else {
        return decision(
            "not_applicable",
            "payload_not_mapping",
            false,
            None,
            &[],
            "",
            "",
        );
    };
    let Some(tool_name) = object_string(payload, "tool_name") else {
        return decision("blocked", "tool_identity_missing", true, None, &[], "", "");
    };
    let Some(tool_input) =
        object_member(payload, "tool_input").filter(|value| matches!(value, JsonValue::Object(_)))
    else {
        return decision("blocked", "tool_identity_missing", true, None, &[], "", "");
    };
    let tool_name = tool_name.to_text().unwrap_or_default();
    let (mutation, paths, reason, command_sha) =
        mutation_request(&tool_name, tool_input, context.active_root);

    if reason == "git_commit"
        && GIT_COMMIT_REPOSITORY_REDIRECT_ENV.iter().any(|name| {
            context
                .environment
                .get(*name)
                .is_some_and(|value| !python_strip(value).is_empty())
        })
    {
        return decision(
            "blocked",
            "git_commit_repository_input_redirect_forbidden",
            true,
            None,
            &paths,
            "",
            &command_sha,
        );
    }
    if !mutation {
        return decision("not_applicable", &reason, false, None, &[], "", "");
    }

    let command_value = if matches!(tool_name.as_str(), "Bash" | "bash") {
        match object_member(tool_input, "command") {
            Some(JsonValue::String(command)) => command.to_text().unwrap_or_default(),
            Some(_) => String::new(),
            None => object_string(tool_input, "cmd")
                .and_then(JsonString::to_text)
                .unwrap_or_default(),
        }
    } else {
        String::new()
    };
    let Some(report_dir) = context.report_dir else {
        return decision(
            "blocked",
            "blocked_authority_required",
            true,
            None,
            &paths,
            "",
            &command_sha,
        );
    };
    let Some((identity, evidence_ref)) = read_identity(report_dir) else {
        return decision(
            "blocked",
            "blocked_authority_required",
            true,
            None,
            &paths,
            &format!("{}", report_dir.join(IDENTITY_RECEIPT_RELATIVE).display()),
            &command_sha,
        );
    };
    let identity_strings = [
        (RUNTIME_AGENT_ID_ENV, &identity.agent_id),
        (RUNTIME_ROLE_ID_ENV, &identity.role_id),
        (RUNTIME_PARENT_AGENT_ID_ENV, &identity.parent_agent_id),
    ];
    if identity_strings.iter().any(|(name, expected)| {
        context.environment.get(*name).map(String::as_str) != expected.to_text().as_deref()
    }) {
        return decision(
            "blocked",
            "runtime_identity_mismatch",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    if PARENT_ROLE_IDS
        .iter()
        .any(|role| identity.role_id.equals_text(role))
        || object_string(&identity.original, "authority")
            .is_none_or(|value| !value.equals_text("write_capable_child"))
    {
        return decision(
            "blocked",
            "parent_mutation_forbidden",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }

    let (writer_target, _packet_identity, packet_error) =
        read_validated_writer_target(context.active_root, context.environment);
    if let Some(error) = packet_error {
        return decision(
            "blocked",
            &error,
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    let target_violation = writer_target_violation(
        context.environment,
        context.active_root,
        &reason,
        &command_value,
        writer_target.as_ref(),
    );
    if let Some(reason) = target_violation {
        return decision(
            "blocked",
            &reason,
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    if matches!(reason.as_str(), "git_merge" | "git_rebase") {
        return decision(
            "blocked",
            "raw_git_merge_or_rebase_forbidden",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    let canonical_lifecycle = matches!(
        reason.as_str(),
        "repository_topic_clone_merge_main"
            | "repository_topic_clone_resume_merge"
            | "repository_topic_clone_finalize_merge"
    );
    if reason == "repository_topic_clone_compound" {
        return decision(
            "blocked",
            "repository_topic_clone_compound",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    if canonical_lifecycle && !identity.role_id.equals_text("integration_executor") {
        return decision(
            "blocked",
            "repository_topic_clone_lifecycle_requires_integration_executor",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    if !has_spawn_event(
        context.hook_spool_root,
        &identity.agent_id,
        &identity.role_id,
        &identity.scope_digest,
    ) {
        return decision(
            "blocked",
            "child_spawn_evidence_missing",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    let Some(writer_target) = writer_target else {
        return decision(
            "blocked",
            "writer_target_packet_missing",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    };
    let (allowed_files, allowed_directories) = target_paths(&writer_target);
    if command_value
        .replace('\\', "/")
        .contains(WRITER_TARGET_PACKET_RELATIVE)
        || paths
            .iter()
            .any(|path| path.replace('\\', "/") == WRITER_TARGET_PACKET_RELATIVE)
    {
        return decision(
            "blocked",
            "writer_target_packet_mutation_forbidden",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    if paths.iter().any(|path| path == UNRESOLVED_SHELL_PATH) {
        return decision(
            "blocked",
            "writer_target_unresolved_shell_path",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    if let Some(explicit_paths) = context.environment.get(WRITER_ALLOWED_PATHS_ENV) {
        if !python_strip(explicit_paths).is_empty() {
            match crate::python_json::parse_json(explicit_paths) {
                Ok(JsonValue::Array(JsonArray(ref values))) => {
                    let parsed = values
                        .iter()
                        .map(json_value_text)
                        .collect::<Option<Vec<_>>>();
                    let packet_paths = writer_target
                        .allowed_paths()
                        .iter()
                        .map(|path| path.to_text().unwrap_or_default())
                        .collect::<Vec<_>>();
                    if parsed.as_deref() != Some(packet_paths.as_slice()) {
                        return decision(
                            "blocked",
                            "writer_target_allowed_paths_mismatch",
                            true,
                            Some(&identity),
                            &paths,
                            &evidence_ref,
                            &command_sha,
                        );
                    }
                }
                _ => {
                    return decision(
                        "blocked",
                        "writer_target_allowed_paths_mismatch",
                        true,
                        Some(&identity),
                        &paths,
                        &evidence_ref,
                        &command_sha,
                    )
                }
            }
        }
    }
    if !canonical_lifecycle
        && (paths.is_empty()
            || !paths
                .iter()
                .all(|path| allowed_path(path, &allowed_files, &allowed_directories)))
    {
        return decision(
            "blocked",
            "mutation_scope_outside_child_receipt",
            true,
            Some(&identity),
            &paths,
            &evidence_ref,
            &command_sha,
        );
    }
    decision(
        "allowed",
        "child_scope_verified",
        true,
        Some(&identity),
        &paths,
        &evidence_ref,
        &command_sha,
    )
}

fn decision(
    status: &str,
    reason: &str,
    mutation: bool,
    identity: Option<&IdentityReceipt>,
    paths: &[String],
    evidence_ref: &str,
    command_sha256: &str,
) -> MutationAuthorityDecision {
    MutationAuthorityDecision {
        status: status.to_owned(),
        reason: reason.to_owned(),
        mutation,
        actor_id: identity
            .map(|identity| identity.agent_id.clone())
            .unwrap_or_default(),
        role_id: identity
            .map(|identity| identity.role_id.clone())
            .unwrap_or_default(),
        parent_agent_id: identity
            .map(|identity| identity.parent_agent_id.clone())
            .unwrap_or_default(),
        scope_digest: identity
            .map(|identity| identity.scope_digest.clone())
            .unwrap_or_default(),
        mutation_paths: paths
            .iter()
            .map(|path| JsonString::from_text(path))
            .collect(),
        evidence_ref: JsonString::from_text(evidence_ref),
        command_sha256: command_sha256.to_owned(),
    }
}

fn read_identity(report_dir: &Path) -> Option<(IdentityReceipt, String)> {
    let path = report_dir.join(IDENTITY_RECEIPT_RELATIVE);
    let evidence_ref = path.to_string_lossy().into_owned();
    let content = fs::read_to_string(&path).ok()?;
    let value = crate::python_json::parse_json(&content).ok()?;
    let JsonValue::Object(object) = &value else {
        return None;
    };
    let expected = [
        "schema",
        "run_id",
        "agent_id",
        "role_id",
        "parent_agent_id",
        "authority",
        "allowed_files",
        "allowed_directories",
        "scope_digest",
        "status",
        "receipt_sha256",
    ]
    .into_iter()
    .map(JsonString::from_text)
    .collect::<BTreeSet<_>>();
    let actual = object
        .0
        .iter()
        .map(|(key, _)| key.clone())
        .collect::<BTreeSet<_>>();
    if actual != expected
        || !object_string(&value, "schema").is_some_and(|field| field.equals_text(IDENTITY_SCHEMA))
        || !object_string(&value, "status").is_some_and(|field| field.equals_text("active"))
    {
        return None;
    }
    let allowed_files = identity_relative_paths(object_member(&value, "allowed_files"))?;
    let allowed_directories =
        identity_relative_paths(object_member(&value, "allowed_directories"))?;
    let scope_digest = object_string(&value, "scope_digest")?;
    let receipt_sha256 = object_string(&value, "receipt_sha256")?;

    let scope_value = JsonValue::Object(JsonObject(vec![
        (
            JsonString::from_text("allowed_files"),
            JsonValue::Array(JsonArray(
                allowed_files
                    .iter()
                    .cloned()
                    .map(JsonValue::String)
                    .collect(),
            )),
        ),
        (
            JsonString::from_text("allowed_directories"),
            JsonValue::Array(JsonArray(
                allowed_directories
                    .iter()
                    .cloned()
                    .map(JsonValue::String)
                    .collect(),
            )),
        ),
    ]));
    if canonical_sha256(&scope_value)
        .ok()
        .is_none_or(|digest| digest.as_str() != scope_digest.to_text().as_deref().unwrap_or(""))
    {
        return None;
    }
    if canonical_object_without(&value, "receipt_sha256")
        .ok()
        .map(|canonical| sha256_hex(canonical.as_bytes()))
        .is_none_or(|digest| digest != receipt_sha256.to_text().unwrap_or_default())
    {
        return None;
    }

    Some((
        IdentityReceipt {
            agent_id: object_string(&value, "agent_id")
                .cloned()
                .unwrap_or_default(),
            role_id: object_string(&value, "role_id")
                .cloned()
                .unwrap_or_default(),
            parent_agent_id: object_string(&value, "parent_agent_id")
                .cloned()
                .unwrap_or_default(),
            scope_digest: scope_digest.clone(),
            original: value,
        },
        evidence_ref,
    ))
}

fn identity_relative_paths(value: Option<&JsonValue>) -> Option<Vec<JsonString>> {
    let JsonValue::Array(JsonArray(values)) = value? else {
        return None;
    };
    let mut paths = Vec::with_capacity(values.len());
    for value in values {
        let JsonValue::String(path) = value else {
            return None;
        };
        if path.is_empty() {
            return None;
        }
        let text = path.to_text()?;
        let candidate = Path::new(&text);
        if candidate.is_absolute()
            || candidate
                .components()
                .any(|component| matches!(component, Component::ParentDir))
        {
            return None;
        }
        paths.push(path.clone());
    }
    Some(paths)
}

fn canonical_sha256(value: &JsonValue) -> Result<String, String> {
    Ok(format!(
        "{:x}",
        Sha256::digest(canonical_json_ascii_bytes(value)?)
    ))
}

fn canonical_object_without(value: &JsonValue, excluded_key: &str) -> Result<String, String> {
    let JsonValue::Object(JsonObject(entries)) = value else {
        return Err("canonical value is not an object".to_owned());
    };
    let mut sorted = BTreeMap::<JsonString, &JsonValue>::new();
    for (key, item) in entries {
        if !key.equals_text(excluded_key) {
            sorted.insert(key.clone(), item);
        }
    }
    let mut bytes = Vec::from(b"{" as &[u8]);
    for (index, (key, item)) in sorted.iter().enumerate() {
        if index > 0 {
            bytes.push(b',');
        }
        let key = canonical_json_ascii_bytes(&JsonValue::String(key.clone()))?;
        let item = canonical_json_ascii_bytes(item)?;
        bytes.extend_from_slice(&key);
        bytes.push(b':');
        bytes.extend_from_slice(&item);
    }
    bytes.push(b'}');
    String::from_utf8(bytes).map_err(|error| error.to_string())
}

fn text_key(value: &str) -> JsonString {
    JsonString::from_text(value)
}

fn text_value(value: &str) -> JsonValue {
    JsonValue::String(JsonString::from_text(value))
}

fn object_member<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
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
    match object_member(value, key)? {
        JsonValue::String(value) => Some(value),
        _ => None,
    }
}

fn json_value_text(value: &JsonValue) -> Option<String> {
    match value {
        JsonValue::String(value) => value.to_text(),
        _ => None,
    }
}

fn read_validated_writer_target(
    active_root: &Path,
    environment: &BTreeMap<String, String>,
) -> (Option<WriterTarget>, Option<JsonValue>, Option<String>) {
    let (target, identity) = match read_writer_target_packet(active_root) {
        Ok(value) => value,
        Err(error) => return (None, None, Some(error.code().to_owned())),
    };
    let declared_root = environment
        .get(WRITER_CHECKOUT_ROOT_ENV)
        .map(|value| python_strip(value))
        .unwrap_or("");
    let declared_branch = environment
        .get(WRITER_BRANCH_ENV)
        .map(|value| python_strip(value))
        .unwrap_or("");
    if !declared_root.is_empty() {
        let Ok(path) = expand_user_path(Path::new(declared_root)) else {
            return (
                None,
                None,
                Some("writer_target_packet_identity_mismatch".to_owned()),
            );
        };
        let Ok(path) = resolve_non_strict(&path) else {
            return (
                None,
                None,
                Some("writer_target_packet_identity_mismatch".to_owned()),
            );
        };
        if target
            .normalized_root()
            .ok()
            .and_then(|root| root.to_text())
            != Some(path.to_string_lossy().into_owned())
        {
            return (
                None,
                None,
                Some("writer_target_packet_identity_mismatch".to_owned()),
            );
        }
    }
    if !declared_branch.is_empty() && target.branch().to_text().as_deref() != Some(declared_branch)
    {
        return (
            None,
            None,
            Some("writer_target_packet_identity_mismatch".to_owned()),
        );
    }
    (Some(target), Some(identity), None)
}

fn writer_target_violation(
    environment: &BTreeMap<String, String>,
    active_root: &Path,
    reason: &str,
    command: &str,
    target: Option<&WriterTarget>,
) -> Option<String> {
    let declared_root = environment
        .get(WRITER_CHECKOUT_ROOT_ENV)
        .map(|value| python_strip(value))
        .unwrap_or("");
    let declared_branch = environment
        .get(WRITER_BRANCH_ENV)
        .map(|value| python_strip(value))
        .unwrap_or("");
    let declared_paths = environment
        .get(WRITER_ALLOWED_PATHS_ENV)
        .map(|value| python_strip(value))
        .unwrap_or("");
    let target_root = target
        .and_then(|target| target.normalized_root().ok())
        .and_then(|root| root.to_text())
        .unwrap_or_default();
    let target_branch = target
        .and_then(|target| target.branch().to_text())
        .unwrap_or_default();
    if declared_root.is_empty()
        && declared_branch.is_empty()
        && declared_paths.is_empty()
        && target_root.is_empty()
    {
        return None;
    }
    let declared_root: &str = if declared_root.is_empty() {
        &target_root
    } else {
        declared_root
    };
    let declared_branch: &str = if declared_branch.is_empty() {
        &target_branch
    } else {
        declared_branch
    };
    if declared_root.is_empty() || declared_branch.is_empty() {
        return Some("writer_target_required".to_owned());
    }
    if !declared_paths.is_empty() {
        let Ok(paths) = crate::python_json::parse_json(declared_paths) else {
            return Some("writer_target_allowed_paths_invalid".to_owned());
        };
        let JsonValue::Array(JsonArray(paths)) = &paths else {
            return Some("writer_target_allowed_paths_invalid".to_owned());
        };
        if paths.is_empty()
            || paths.iter().any(|path| {
                let Some(path) = json_value_text(path) else {
                    return true;
                };
                invalid_runtime_allowed_path(&path)
            })
        {
            return Some("writer_target_allowed_paths_invalid".to_owned());
        }
    }
    let Ok(declared_root_path) = expand_user_path(Path::new(declared_root)) else {
        return Some("writer_target_checkout_root_not_absolute".to_owned());
    };
    if !declared_root_path.is_absolute() {
        return Some("writer_target_checkout_root_not_absolute".to_owned());
    }
    let Ok(declared_root_path) = resolve_non_strict(&declared_root_path) else {
        return Some("writer_target_checkout_root_mismatch".to_owned());
    };
    let Ok(active_root) = resolve_non_strict(active_root) else {
        return Some("writer_target_checkout_root_mismatch".to_owned());
    };
    if declared_root_path != active_root {
        return Some("writer_target_checkout_root_mismatch".to_owned());
    }
    if matches!(
        reason,
        "git_checkout" | "git_switch" | "git_worktree" | "git_branch"
    ) {
        return Some("writer_target_branch_switch_forbidden".to_owned());
    }
    if reason.contains("git_repository_redirect") {
        return Some("writer_target_git_repository_redirect_forbidden".to_owned());
    }
    if reason.contains("cd_outside_checkout") || reason == "shell_cd_unresolved" {
        return Some("writer_target_checkout_root_mismatch".to_owned());
    }
    for segment in command_segments(command) {
        if segment.len() > 1 && segment[0] == "cd" {
            let candidate = PathBuf::from(segment[1].as_str());
            let candidate = if candidate.is_absolute() {
                candidate
            } else {
                declared_root_path.join(candidate)
            };
            if resolve_non_strict(&candidate).ok().as_ref() != Some(&declared_root_path) {
                return Some("writer_target_checkout_root_mismatch".to_owned());
            }
        }
        if segment.first().is_some_and(|verb| verb == "git") {
            for index in 0..segment.len().saturating_sub(1) {
                if segment[index] == "-C" {
                    let candidate = PathBuf::from(segment[index + 1].as_str());
                    let candidate = if candidate.is_absolute() {
                        candidate
                    } else {
                        declared_root_path.join(candidate)
                    };
                    if resolve_non_strict(&candidate).ok().as_ref() != Some(&declared_root_path) {
                        return Some("writer_target_checkout_root_mismatch".to_owned());
                    }
                }
            }
        }
    }
    None
}

fn invalid_runtime_allowed_path(path: &str) -> bool {
    Path::new(path).is_absolute()
        || Path::new(path)
            .components()
            .any(|component| matches!(component, Component::ParentDir))
        || path.contains('\\')
        || path.contains("//")
        || path.is_empty()
}

fn target_paths(target: &WriterTarget) -> (Vec<String>, Vec<String>) {
    let mut files = Vec::new();
    let mut directories = Vec::new();
    for path in target.allowed_paths() {
        let path = path.to_text().unwrap_or_default();
        if path.ends_with('/') {
            directories.push(path.trim_end_matches('/').to_owned());
        } else {
            files.push(path);
        }
    }
    (files, directories)
}

fn allowed_path(path: &str, allowed_files: &[String], allowed_directories: &[String]) -> bool {
    let candidate = Path::new(path);
    if candidate.is_absolute()
        || candidate
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return false;
    }
    let normalized = path_to_posix(candidate);
    if normalized == "." && allowed_files.iter().any(|allowed| allowed == ".") {
        return true;
    }
    if allowed_files.iter().any(|allowed| allowed == ".") {
        return true;
    }
    if allowed_files.iter().any(|allowed| allowed == &normalized) {
        return true;
    }
    allowed_directories.iter().any(|directory| {
        normalized == *directory
            || normalized.starts_with(&format!("{}/", directory.trim_end_matches('/')))
    })
}

fn path_to_posix(path: &Path) -> String {
    let components = path
        .components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    if components.is_empty() {
        ".".to_owned()
    } else {
        components.join("/")
    }
}

fn python_strip(value: &str) -> &str {
    value.trim_matches(is_python_whitespace)
}

fn mutation_request(
    tool_name: &str,
    tool_input: &JsonValue,
    active_root: &Path,
) -> (bool, Vec<String>, String, String) {
    match tool_name {
        "apply_patch" => {
            let Some(JsonValue::String(patch)) = object_member(tool_input, "patch") else {
                return (
                    true,
                    Vec::new(),
                    "patch_payload_missing".to_owned(),
                    String::new(),
                );
            };
            let Some(patch) = patch.to_text() else {
                return (
                    true,
                    Vec::new(),
                    "patch_payload_missing".to_owned(),
                    String::new(),
                );
            };
            let paths = patch
                .lines()
                .filter_map(|line| {
                    let suffix = line.strip_prefix("***")?;
                    let directive = suffix.trim_start_matches(is_python_whitespace);
                    if directive.len() == suffix.len() {
                        return None;
                    }
                    ["Update File:", "Add File:", "Delete File:"]
                        .iter()
                        .find_map(|prefix| directive.strip_prefix(prefix))
                        .map(|path| python_strip(path).to_owned())
                        .filter(|path| !path.is_empty())
                })
                .collect();
            let digest = sha256_hex(patch.as_bytes());
            (true, paths, "apply_patch".to_owned(), digest)
        }
        "python" | "python3" => (
            true,
            Vec::new(),
            "python_execution".to_owned(),
            String::new(),
        ),
        "Bash" | "bash" => {
            let candidate = match object_member(tool_input, "command") {
                Some(value) => Some(value),
                None => object_member(tool_input, "cmd"),
            };
            let Some(JsonValue::String(command)) = candidate else {
                return (
                    true,
                    Vec::new(),
                    "bash_command_missing".to_owned(),
                    String::new(),
                );
            };
            let Some(command) = command.to_text() else {
                return (
                    true,
                    Vec::new(),
                    "bash_command_missing".to_owned(),
                    String::new(),
                );
            };
            let (mutation, mut paths, reason) = bash_mutation(&command, active_root);
            let lifecycle = repository_topic_clone_operation(&command);
            let reason = match lifecycle {
                Some(operation) if operation != "repository_topic_clone_compound" => {
                    paths.clear();
                    operation
                }
                Some(operation) => operation,
                None => reason,
            };
            (mutation, paths, reason, sha256_hex(command.as_bytes()))
        }
        _ => (
            false,
            Vec::new(),
            "not_mutating_tool".to_owned(),
            String::new(),
        ),
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn command_segments(command: &str) -> Vec<Vec<String>> {
    let Some(tokens) = shell_tokens(command) else {
        return Vec::new();
    };
    let mut segments = Vec::<Vec<String>>::new();
    let mut current = Vec::new();
    for token in tokens {
        if SHELL_CONTROL_TOKENS.contains(&token.as_str()) {
            if !current.is_empty() {
                segments.push(std::mem::take(&mut current));
            }
        } else {
            current.push(token);
        }
    }
    if !current.is_empty() {
        segments.push(current);
    }
    segments
}

fn shell_tokens(command: &str) -> Option<Vec<String>> {
    let mut tokens = Vec::new();
    let mut input = command.chars().collect::<VecDeque<_>>();
    let mut token = String::new();
    let mut state = ' ';
    let mut escaped_state = ' ';
    let mut quoted = false;
    while let Some(character) = input.pop_front() {
        match state {
            ' ' => {
                if shlex_whitespace(character) {
                    continue;
                }
                if character == '#' {
                    discard_shell_comment(&mut input);
                } else if character == '\\' {
                    escaped_state = 'a';
                    state = '\\';
                } else if shlex_word_character(character) {
                    token.push(character);
                    state = 'a';
                } else if shlex_punctuation(character) {
                    token.push(character);
                    state = 'c';
                } else if matches!(character, '\'' | '"') {
                    state = character;
                } else {
                    tokens.push(character.to_string());
                }
            }
            'a' => {
                if shlex_whitespace(character) {
                    state = ' ';
                    if !token.is_empty() || quoted {
                        tokens.push(std::mem::take(&mut token));
                        quoted = false;
                    }
                } else if character == '#' {
                    discard_shell_comment(&mut input);
                    state = ' ';
                    if !token.is_empty() || quoted {
                        tokens.push(std::mem::take(&mut token));
                        quoted = false;
                    }
                } else if matches!(character, '\'' | '"') {
                    state = character;
                } else if character == '\\' {
                    escaped_state = 'a';
                    state = '\\';
                } else if shlex_word_character(character) {
                    token.push(character);
                } else {
                    input.push_front(character);
                    state = ' ';
                    if !token.is_empty() || quoted {
                        tokens.push(std::mem::take(&mut token));
                        quoted = false;
                    }
                }
            }
            'c' => {
                if shlex_whitespace(character) {
                    state = ' ';
                    tokens.push(std::mem::take(&mut token));
                } else if character == '#' {
                    discard_shell_comment(&mut input);
                    state = ' ';
                    tokens.push(std::mem::take(&mut token));
                } else if shlex_punctuation(character) {
                    token.push(character);
                } else {
                    input.push_front(character);
                    state = ' ';
                    tokens.push(std::mem::take(&mut token));
                }
            }
            '\'' => {
                quoted = true;
                if character == '\'' {
                    state = 'a';
                } else {
                    token.push(character);
                }
            }
            '"' => {
                quoted = true;
                if character == '"' {
                    state = 'a';
                } else if character == '\\' {
                    escaped_state = '"';
                    state = '\\';
                } else {
                    token.push(character);
                }
            }
            '\\' => {
                if escaped_state == '"' && character != '"' && character != '\\' {
                    token.push('\\');
                }
                token.push(character);
                state = escaped_state;
            }
            _ => unreachable!("the shlex-compatible state set is closed"),
        }
    }
    if matches!(state, '\'' | '"' | '\\') {
        return None;
    }
    if !token.is_empty() || quoted {
        tokens.push(token);
    }
    Some(tokens)
}

fn shlex_whitespace(character: char) -> bool {
    matches!(character, ' ' | '\t' | '\r' | '\n')
}

fn shlex_punctuation(character: char) -> bool {
    ";&|()<>".contains(character)
}

fn shlex_word_character(character: char) -> bool {
    character.is_ascii_alphanumeric()
        || character == '_'
        || "ßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÝÞ~-./*?="
            .contains(character)
}

fn discard_shell_comment(input: &mut VecDeque<char>) {
    while let Some(character) = input.pop_front() {
        if character == '\n' {
            break;
        }
    }
}

fn command_index(segment: &[String]) -> Option<usize> {
    let mut index = 0;
    while index < segment.len() {
        let token = &segment[index];
        if shell_assignment(token) {
            index += 1;
            continue;
        }
        if SHELL_COMMAND_PREFIXES.contains(&token.as_str()) {
            index += 1;
            if token == "env" {
                while index < segment.len() && shell_assignment(&segment[index]) {
                    index += 1;
                }
            }
            continue;
        }
        return Some(index);
    }
    None
}

fn shell_assignment(token: &str) -> bool {
    let Some((name, _)) = token.split_once('=') else {
        return false;
    };
    let mut characters = name.chars();
    let Some(first) = characters.next() else {
        return false;
    };
    SHELL_ASSIGNMENT_START.contains(first)
        && characters.all(|character| SHELL_ASSIGNMENT_CONTINUE.contains(character))
}

fn command_basename(token: &str) -> String {
    Path::new(token)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .to_owned()
}

fn shell_path(value: &str, cwd: &Path, active_root: &Path) -> (String, bool) {
    if value.is_empty()
        || value.starts_with('~')
        || ["$", "`", "*", "?", "[", "]", "<(", ">("]
            .iter()
            .any(|marker| value.contains(marker))
    {
        return (UNRESOLVED_SHELL_PATH.to_owned(), true);
    }
    let Ok(expanded) = expand_user_path(Path::new(value)) else {
        return (UNRESOLVED_SHELL_PATH.to_owned(), true);
    };
    let candidate = if expanded.is_absolute() {
        expanded
    } else {
        cwd.join(expanded)
    };
    let Ok(resolved) = resolve_non_strict(&candidate) else {
        return (UNRESOLVED_SHELL_PATH.to_owned(), true);
    };
    let Ok(root) = resolve_non_strict(active_root) else {
        return (UNRESOLVED_SHELL_PATH.to_owned(), true);
    };
    match resolved.strip_prefix(&root) {
        Ok(relative) => {
            let normalized = path_to_posix(relative);
            (normalized, false)
        }
        Err(_) => (resolved.to_string_lossy().into_owned(), true),
    }
}

fn bash_mutation(command: &str, active_root: &Path) -> (bool, Vec<String>, String) {
    let root = resolve_non_strict(active_root).unwrap_or_else(|_| active_root.to_path_buf());
    bash_mutation_inner(command, &root, &root, 0, &BTreeMap::new())
}

fn bash_mutation_inner(
    command: &str,
    active_root: &Path,
    initial_cwd: &Path,
    depth: usize,
    inherited_env: &BTreeMap<String, Option<String>>,
) -> (bool, Vec<String>, String) {
    if depth > SHELL_ANALYSIS_MAX_DEPTH {
        return (
            true,
            Vec::new(),
            "shell_wrapper_unparseable_depth".to_owned(),
        );
    }
    let segments = command_segments(command);
    if segments.is_empty() {
        return (true, Vec::new(), "command_unparseable".to_owned());
    }
    let mut cwd = initial_cwd.to_path_buf();
    let mut mutation = false;
    let mut paths = Vec::new();
    let mut reasons = Vec::new();
    let mut env_overrides = inherited_env.clone();
    for (start, body) in backtick_bodies(command) {
        let before = git_environment_before_backtick(&command[..start], &env_overrides);
        let inherited = before.as_ref().unwrap_or(&env_overrides);
        let (nested_mutation, nested_paths, nested_reason) =
            bash_mutation_inner(&body, active_root, initial_cwd, depth + 1, inherited);
        mutation |= nested_mutation;
        paths.extend(nested_paths);
        if nested_mutation {
            reasons.push(if before.is_some() {
                format!("shell_substitution_{nested_reason}")
            } else {
                paths.push(UNRESOLVED_SHELL_PATH.to_owned());
                "shell_substitution_environment_unresolved".to_owned()
            });
        }
    }
    for segment in segments {
        if segment
            .iter()
            .any(|token| matches!(token.as_str(), ">" | ">>"))
        {
            mutation = true;
            reasons.push("shell_redirection".to_owned());
            for index in 0..segment.len().saturating_sub(1) {
                if matches!(segment[index].as_str(), ">" | ">>") {
                    paths.push(shell_path(&segment[index + 1], &cwd, active_root).0);
                }
            }
        } else if segment.iter().any(|token| token == "<") {
            mutation = true;
            reasons.push("shell_redirection".to_owned());
        }
        let Some(index) = command_index(&segment) else {
            if !segment
                .iter()
                .any(|token| SHELL_CONTROL_TOKENS.contains(&token.as_str()))
            {
                mutation = true;
                reasons.push("command_missing".to_owned());
            }
            continue;
        };
        let verb = segment[index].clone();
        let mut command_env = env_overrides.clone();
        for token in &segment[..index] {
            if let Some((key, value)) = token.split_once('=') {
                if shell_assignment(token) {
                    command_env.insert(key.to_owned(), Some(value.to_owned()));
                }
            }
        }
        if verb.starts_with('-')
            && segment[..index]
                .iter()
                .any(|token| command_basename(token) == "env")
        {
            let git_index = segment[index + 1..]
                .iter()
                .position(|token| command_basename(token) == "git")
                .map(|position| index + 1 + position);
            let Some(git_index) = git_index else {
                mutation = true;
                paths.push(UNRESOLVED_SHELL_PATH.to_owned());
                reasons.push("shell_wrapper_unparseable_env".to_owned());
                continue;
            };
            let (_, git_verb, _) = git_subcommand(&segment[git_index + 1..]);
            if !READONLY_GIT_SUBCOMMANDS.contains(&git_verb.as_str())
                || ["branch", "stash", "worktree"].contains(&git_verb.as_str())
            {
                mutation = true;
                paths.push(UNRESOLVED_SHELL_PATH.to_owned());
                reasons.push("shell_wrapper_unparseable_env".to_owned());
                continue;
            }
        }
        if verb == "export" {
            for token in &segment[index + 1..] {
                if let Some((key, value)) = token.split_once('=') {
                    if shell_assignment(token) {
                        env_overrides.insert(key.to_owned(), Some(value.to_owned()));
                    }
                }
            }
            continue;
        }
        if verb == "unset" {
            for token in &segment[index + 1..] {
                if shell_assignment(&format!("{token}=")) {
                    env_overrides.insert(token.clone(), None);
                }
            }
            continue;
        }
        if verb == "cd" {
            let operands = segment[index + 1..]
                .iter()
                .filter(|token| *token != "--")
                .collect::<Vec<_>>();
            if operands.len() != 1 || operands[0].starts_with('-') {
                mutation = true;
                reasons.push("shell_cd_unresolved".to_owned());
                continue;
            }
            let (normalized, outside) = shell_path(operands[0], &cwd, active_root);
            if outside {
                mutation = true;
                paths.push(normalized);
                reasons.push("shell_cd_outside_checkout".to_owned());
            } else {
                cwd = if normalized == "." {
                    active_root.to_path_buf()
                } else {
                    active_root.join(normalized)
                };
            }
            continue;
        }
        if verb == "git" {
            let (global_options, subcommand, sub_args) = git_subcommand(&segment[index + 1..]);
            if let Some((redirect_paths, redirect_reason)) = git_repository_redirect(
                &global_options,
                &subcommand,
                &cwd,
                active_root,
                &command_env,
            ) {
                mutation = true;
                paths.extend(redirect_paths);
                reasons.push(redirect_reason);
                continue;
            }
            let (output_paths, output_reason) =
                git_output_paths(&subcommand, &sub_args, &cwd, active_root);
            if let Some(reason) = output_reason {
                mutation = true;
                paths.extend(output_paths);
                reasons.push(reason);
                continue;
            }
            if subcommand == "archive" {
                continue;
            }
            if subcommand == "worktree" || subcommand == "stash" {
                let nested = sub_args
                    .iter()
                    .find(|token| !token.starts_with('-'))
                    .map(String::as_str)
                    .unwrap_or("");
                if (subcommand == "worktree" && ["list", "lock", "unlock"].contains(&nested))
                    || (subcommand == "stash" && ["list", "show"].contains(&nested))
                {
                    continue;
                }
            }
            if subcommand == "clean"
                && sub_args.iter().any(|token| {
                    token == "-n"
                        || token == "--dry-run"
                        || (token.starts_with('-') && token[1..].contains('n'))
                })
            {
                continue;
            }
            if ["switch", "checkout"].contains(&subcommand.as_str())
                && sub_args
                    .iter()
                    .any(|token| token == "-h" || token == "--help")
            {
                continue;
            }
            if READONLY_GIT_SUBCOMMANDS.contains(&subcommand.as_str())
                && !["branch", "worktree", "stash"].contains(&subcommand.as_str())
            {
                continue;
            }
            if subcommand == "branch"
                && (sub_args.is_empty()
                    || sub_args.iter().any(|token| {
                        [
                            "--list",
                            "-a",
                            "-r",
                            "-v",
                            "-vv",
                            "--show-current",
                            "--edit-description",
                            "--set-upstream-to",
                            "--unset-upstream",
                            "-u",
                        ]
                        .contains(&token.as_str())
                            || token.starts_with("--set-upstream-to=")
                            || token.starts_with("-u")
                    }))
            {
                continue;
            }
            mutation = true;
            paths.extend(git_mutation_paths(
                &subcommand,
                &global_options,
                &sub_args,
                &cwd,
                active_root,
                &command_env,
            ));
            reasons.push(format!(
                "git_{}",
                if subcommand.is_empty() {
                    "unknown"
                } else {
                    &subcommand
                }
            ));
            continue;
        }
        if ["bash", "sh", "zsh"].contains(&verb.as_str()) {
            let wrapper_args = &segment[index + 1..];
            let Some(flag) = wrapper_args
                .iter()
                .position(|token| ["-c", "-lc", "--command"].contains(&token.as_str()))
            else {
                mutation = true;
                reasons.push("shell_wrapper_unresolved".to_owned());
                continue;
            };
            let Some(inner) = wrapper_args.get(flag + 1) else {
                mutation = true;
                reasons.push("shell_wrapper_unresolved".to_owned());
                continue;
            };
            if shell_dynamic_expansion(inner) {
                mutation = true;
                reasons.push("shell_wrapper_unparseable_expansion".to_owned());
                continue;
            }
            let (nested_mutation, nested_paths, nested_reason) =
                bash_mutation_inner(inner, active_root, &cwd, depth + 1, &command_env);
            mutation |= nested_mutation;
            paths.extend(nested_paths);
            if nested_mutation {
                reasons.push(format!("{verb}_wrapper_{nested_reason}"));
            }
            continue;
        }
        if OPAQUE_SHELL_COMMANDS.contains(&verb.as_str()) {
            mutation = true;
            reasons.push("shell_opaque_command".to_owned());
            continue;
        }
        if MUTATING_COMMANDS.contains(&verb.as_str()) {
            let mut operands = segment[index + 1..]
                .iter()
                .filter(|token| !token.starts_with('-'))
                .collect::<Vec<_>>();
            if ["cp", "mv"].contains(&verb.as_str()) && operands.len() > 1 {
                operands = operands.split_off(operands.len() - 1);
            }
            mutation = true;
            paths.extend(
                operands
                    .into_iter()
                    .map(|token| shell_path(token, &cwd, active_root).0),
            );
            reasons.push(format!("command_{verb}"));
            continue;
        }
        if READONLY_COMMANDS.contains(&verb.as_str()) {
            continue;
        }
    }
    (mutation, paths, analysis_reason(&reasons))
}

fn shell_dynamic_expansion(value: &str) -> bool {
    let mut single_quoted = false;
    let mut escaped = false;
    let characters = value.chars().collect::<Vec<_>>();
    for (index, character) in characters.iter().copied().enumerate() {
        if escaped {
            escaped = false;
            continue;
        }
        if character == '\\' && !single_quoted {
            escaped = true;
            continue;
        }
        if character == '\'' {
            single_quoted = !single_quoted;
            continue;
        }
        if !single_quoted
            && character == '$'
            && characters
                .get(index + 1)
                .is_some_and(|next| next.is_alphabetic() || *next == '_' || *next == '{')
        {
            return true;
        }
    }
    false
}

fn backtick_bodies(command: &str) -> Vec<(usize, String)> {
    let mut bodies = Vec::new();
    let mut current = None::<String>;
    let mut start = 0;
    let mut single_quoted = false;
    let mut escaped = false;
    for (offset, character) in command.char_indices() {
        if escaped {
            if let Some(body) = &mut current {
                body.push(character);
            }
            escaped = false;
            continue;
        }
        if character == '\\' && !single_quoted {
            escaped = true;
            if let Some(body) = &mut current {
                body.push(character);
            }
            continue;
        }
        if character == '\'' && current.is_none() {
            single_quoted = !single_quoted;
            continue;
        }
        if character == '#' && current.is_none() && !single_quoted {
            break;
        }
        if character == '`' && !single_quoted {
            if let Some(body) = current.take() {
                bodies.push((start, body));
            } else {
                current = Some(String::new());
                start = offset;
            }
            continue;
        }
        if let Some(body) = &mut current {
            body.push(character);
        }
    }
    bodies
}

fn git_environment_before_backtick(
    prefix: &str,
    inherited: &BTreeMap<String, Option<String>>,
) -> Option<BTreeMap<String, Option<String>>> {
    let mut result = inherited.clone();
    if python_strip(prefix).is_empty() {
        return Some(result);
    }
    let probe = command_segments(&format!("{prefix} __agent_canon_env_probe__"));
    let segments = command_segments(prefix);
    if probe.is_empty() || (!python_strip(prefix).is_empty() && segments.is_empty()) {
        return None;
    }
    let ends_after_separator = probe
        .last()
        .is_some_and(|segment| segment.len() == 1 && segment[0] == "__agent_canon_env_probe__");
    for (index, segment) in segments.iter().enumerate() {
        let Some(command_index) = command_index(segment) else {
            if segment
                .iter()
                .any(|token| !SHELL_CONTROL_TOKENS.contains(&token.as_str()))
            {
                return None;
            }
            continue;
        };
        let verb = command_basename(&segment[command_index]);
        let is_current = index + 1 == segments.len() && !ends_after_separator;
        if is_current {
            add_assignments(&mut result, &segment[..command_index]);
        } else if verb == "export" {
            add_assignments(&mut result, &segment[command_index + 1..]);
        } else if verb == "unset" {
            for token in &segment[command_index + 1..] {
                if shell_assignment(&format!("{token}=")) {
                    result.insert(token.clone(), None);
                }
            }
        }
    }
    Some(result)
}

fn add_assignments(target: &mut BTreeMap<String, Option<String>>, tokens: &[String]) {
    for token in tokens {
        if let Some((name, value)) = token.split_once('=') {
            if shell_assignment(token) {
                target.insert(name.to_owned(), Some(value.to_owned()));
            }
        }
    }
}

fn analysis_reason(reasons: &[String]) -> String {
    if reasons.is_empty() {
        return "read_only_command".to_owned();
    }
    for marker in [
        "unparseable",
        "unresolved",
        "repository_redirect",
        "cd_outside_checkout",
        "checkout_root_mismatch",
        "shell_redirection",
        "opaque",
    ] {
        if let Some(reason) = reasons.iter().find(|reason| reason.contains(marker)) {
            return reason.clone();
        }
    }
    reasons
        .last()
        .cloned()
        .unwrap_or_else(|| "read_only_command".to_owned())
}

fn git_subcommand(arguments: &[String]) -> (Vec<String>, String, Vec<String>) {
    let value_options = [
        "-C",
        "--config-env",
        "--exec-path",
        "--git-dir",
        "--namespace",
        "--work-tree",
        "-c",
    ];
    let mut options = Vec::new();
    let mut index = 0;
    while index < arguments.len() {
        let token = &arguments[index];
        if token == "--" {
            options.push(token.clone());
            index += 1;
            break;
        }
        if value_options.contains(&token.as_str()) {
            if index + 1 >= arguments.len() {
                options.push(token.clone());
                return (options, String::new(), Vec::new());
            }
            options.push(token.clone());
            options.push(arguments[index + 1].clone());
            index += 2;
            continue;
        }
        if value_options
            .iter()
            .any(|option| option.starts_with("--") && token.starts_with(&format!("{option}=")))
        {
            options.push(token.clone());
            index += 1;
            continue;
        }
        if (token.starts_with("-C") || token.starts_with("-c")) && token.len() > 2 {
            options.push(token.clone());
            index += 1;
            continue;
        }
        if token.starts_with('-') {
            options.push(token.clone());
            index += 1;
            continue;
        }
        break;
    }
    if index >= arguments.len() {
        return (options, String::new(), Vec::new());
    }
    (
        options,
        arguments[index].clone(),
        arguments[index + 1..].to_vec(),
    )
}

fn run_git(
    args: &[String],
    cwd: &Path,
    overrides: &BTreeMap<String, Option<String>>,
) -> Option<std::process::Output> {
    let mut command = Command::new("git");
    command.args(args).current_dir(cwd);
    for (key, value) in overrides {
        match value {
            Some(value) => {
                command.env(key, value);
            }
            None => {
                command.env_remove(key);
            }
        }
    }
    command.output().ok()
}

fn git_repository_redirect(
    options: &[String],
    subcommand: &str,
    cwd: &Path,
    active_root: &Path,
    overrides: &BTreeMap<String, Option<String>>,
) -> Option<(Vec<String>, String)> {
    let needs_binding = subcommand == "commit"
        || options.iter().any(|token| {
            token == "-C"
                || token == "--config-env"
                || token == "--git-dir"
                || token == "--namespace"
                || token == "--work-tree"
                || token == "-c"
                || (token.starts_with("-C") && token.len() > 2)
                || (token.starts_with("-c") && token.len() > 2)
                || [
                    "--config-env=",
                    "--git-dir=",
                    "--namespace=",
                    "--work-tree=",
                ]
                .iter()
                .any(|prefix| token.starts_with(prefix))
        });
    if !needs_binding {
        return None;
    }
    let mut index = 0;
    while index < options.len() {
        let token = &options[index];
        let value = if token == "-C" {
            if index + 1 >= options.len() {
                return Some((
                    vec![UNRESOLVED_SHELL_PATH.to_owned()],
                    "git_repository_redirect_unresolved".to_owned(),
                ));
            }
            index += 1;
            Some(options[index].as_str())
        } else if token.starts_with("-C") && token.len() > 2 {
            Some(&token[2..])
        } else if token == "--git-dir" || token == "--work-tree" {
            if index + 1 >= options.len() {
                return Some((
                    vec![UNRESOLVED_SHELL_PATH.to_owned()],
                    "git_repository_redirect_unresolved".to_owned(),
                ));
            }
            if options[index + 1].is_empty() {
                return Some((
                    vec![UNRESOLVED_SHELL_PATH.to_owned()],
                    "git_repository_redirect_unresolved".to_owned(),
                ));
            }
            return Some((
                vec![shell_path(&options[index + 1], cwd, active_root).0],
                "git_repository_redirect".to_owned(),
            ));
        } else if token.starts_with("--git-dir=") || token.starts_with("--work-tree=") {
            let value = token.split_once('=').map(|(_, value)| value).unwrap_or("");
            if value.is_empty() {
                return Some((
                    vec![UNRESOLVED_SHELL_PATH.to_owned()],
                    "git_repository_redirect_unresolved".to_owned(),
                ));
            }
            return Some((
                vec![shell_path(value, cwd, active_root).0],
                "git_repository_redirect".to_owned(),
            ));
        } else if ["--config-env", "--exec-path", "--namespace", "-c"].contains(&token.as_str()) {
            index += 1;
            None
        } else {
            None
        };
        index += 1;
        if let Some(value) = value {
            if value.is_empty() {
                return Some((
                    vec![UNRESOLVED_SHELL_PATH.to_owned()],
                    "git_repository_redirect_unresolved".to_owned(),
                ));
            }
            let (normalized, outside) = shell_path(value, cwd, active_root);
            if outside || normalized != "." {
                return Some((vec![normalized], "git_repository_redirect".to_owned()));
            }
        }
    }
    let args = options
        .iter()
        .cloned()
        .chain(["rev-parse".to_owned(), "--show-toplevel".to_owned()])
        .collect::<Vec<_>>();
    let Some(output) = run_git(&args, cwd, overrides) else {
        return Some((
            vec![UNRESOLVED_SHELL_PATH.to_owned()],
            "git_repository_redirect_unresolved".to_owned(),
        ));
    };
    if !output.status.success() {
        return Some((
            vec![UNRESOLVED_SHELL_PATH.to_owned()],
            "git_repository_redirect_unresolved".to_owned(),
        ));
    }
    let observed = String::from_utf8_lossy(&output.stdout)
        .trim_end_matches('\n')
        .to_owned();
    let expected = resolve_non_strict(active_root)
        .ok()
        .map(|path| path.to_string_lossy().into_owned());
    if expected.as_deref() != Some(observed.as_str()) {
        return Some((vec![observed], "git_repository_redirect".to_owned()));
    }
    None
}

fn git_output_paths(
    subcommand: &str,
    args: &[String],
    cwd: &Path,
    active_root: &Path,
) -> (Vec<String>, Option<String>) {
    if !GIT_OUTPUT_SUBCOMMANDS.contains(&subcommand) {
        return (Vec::new(), None);
    }
    let mut paths = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        let value = if token == "-o" || token == "--output" {
            if index + 1 >= args.len() {
                return (paths, Some("git_output_path_unresolved".to_owned()));
            }
            index += 1;
            Some(args[index].as_str())
        } else if let Some(value) = token.strip_prefix("--output=") {
            Some(value)
        } else if token.starts_with("-o") && token != "-o" {
            Some(&token[2..])
        } else {
            None
        };
        index += 1;
        if let Some(value) = value {
            if value == "-" {
                continue;
            }
            if value.is_empty() {
                return (paths, Some("git_output_path_unresolved".to_owned()));
            }
            paths.push(shell_path(value, cwd, active_root).0);
        }
    }
    let reason = (!paths.is_empty()).then(|| "git_output_path".to_owned());
    (paths, reason)
}

fn git_mutation_paths(
    subcommand: &str,
    options: &[String],
    args: &[String],
    cwd: &Path,
    active_root: &Path,
    overrides: &BTreeMap<String, Option<String>>,
) -> Vec<String> {
    if subcommand == "commit" {
        if overrides.iter().any(|(key, value)| {
            value.is_some() && GIT_COMMIT_REPOSITORY_REDIRECT_ENV.contains(&key.as_str())
        }) {
            return vec![UNRESOLVED_SHELL_PATH.to_owned()];
        }
        if GIT_COMMIT_PATHSPEC_FILE_OPTIONS
            .iter()
            .any(|option| git_has_option(args, option, None))
        {
            return vec![UNRESOLVED_SHELL_PATH.to_owned()];
        }
        let path_args = git_argument_paths(args, cwd, active_root);
        if path_args.iter().any(|path| path == UNRESOLVED_SHELL_PATH) {
            return path_args;
        }
        let amend = git_has_option(args, "--amend", None);
        let include_all = [
            ("--all", Some('a')),
            ("--include", Some('i')),
            ("--interactive", Some('i')),
            ("--patch", Some('p')),
        ]
        .iter()
        .any(|(long, short)| git_has_option(args, long, *short));
        if !path_args.is_empty() && !include_all && !amend {
            return deduplicate(path_args);
        }
        let staged = git_name_only_paths(
            options,
            cwd,
            active_root,
            overrides,
            true,
            amend.then_some("HEAD^"),
        );
        let mut paths = staged;
        paths.extend(path_args);
        if include_all {
            paths.extend(git_name_only_paths(
                options,
                cwd,
                active_root,
                overrides,
                false,
                None,
            ));
        }
        return deduplicate(paths);
    }
    git_argument_paths(args, cwd, active_root)
}

fn git_argument_paths(args: &[String], cwd: &Path, active_root: &Path) -> Vec<String> {
    let mut paths = Vec::new();
    let mut skip_value = false;
    let mut after_separator = false;
    for token in args {
        if skip_value {
            skip_value = false;
            continue;
        }
        if after_separator {
            paths.push(shell_path(token, cwd, active_root).0);
            continue;
        }
        if token == "--" {
            after_separator = true;
            continue;
        }
        if GIT_NON_PATH_VALUE_OPTIONS.contains(&token.as_str()) {
            skip_value = true;
            continue;
        }
        if GIT_NON_PATH_VALUE_OPTIONS
            .iter()
            .any(|option| token.starts_with(&format!("{option}=")))
        {
            continue;
        }
        if token.starts_with('-') && token != "-" {
            let shorts = token[1..].chars().collect::<Vec<_>>();
            if shorts
                .iter()
                .position(|option| GIT_SHORT_VALUE_OPTIONS.contains(option))
                .is_some_and(|position| position + 1 == shorts.len())
            {
                skip_value = true;
            }
            continue;
        }
        paths.push(shell_path(token, cwd, active_root).0);
    }
    paths
}

fn git_has_option(args: &[String], long: &str, short: Option<char>) -> bool {
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if token == "--" {
            return false;
        }
        if GIT_NON_PATH_VALUE_OPTIONS.contains(&token.as_str()) {
            index += 2;
            continue;
        }
        if token.starts_with("--") {
            if token == long || token.starts_with(&format!("{long}=")) {
                return true;
            }
            index += 1;
            continue;
        }
        if token.starts_with('-') && token != "-" {
            let chars = token[1..].chars().collect::<Vec<_>>();
            let mut consumed = false;
            for (offset, flag) in chars.iter().enumerate() {
                if Some(*flag) == short {
                    return true;
                }
                if GIT_SHORT_VALUE_OPTIONS.contains(flag) {
                    index += if offset + 1 == chars.len() { 2 } else { 1 };
                    consumed = true;
                    break;
                }
            }
            if !consumed {
                index += 1;
            }
            continue;
        }
        index += 1;
    }
    false
}

fn git_name_only_paths(
    options: &[String],
    cwd: &Path,
    active_root: &Path,
    overrides: &BTreeMap<String, Option<String>>,
    cached: bool,
    base: Option<&str>,
) -> Vec<String> {
    let mut args = options.to_vec();
    args.push("diff".to_owned());
    if cached {
        args.push("--cached".to_owned());
    }
    if let Some(base) = base {
        args.push(base.to_owned());
    }
    args.extend([
        "--name-only".to_owned(),
        "-z".to_owned(),
        "--no-renames".to_owned(),
        "--no-relative".to_owned(),
    ]);
    let Some(output) = run_git(&args, cwd, overrides) else {
        return vec![UNRESOLVED_SHELL_PATH.to_owned()];
    };
    if !output.status.success() {
        return vec![UNRESOLVED_SHELL_PATH.to_owned()];
    }
    String::from_utf8_lossy(&output.stdout)
        .split('\0')
        .filter(|path| !path.is_empty())
        .map(|path| shell_path(path, active_root, active_root).0)
        .collect()
}

fn deduplicate(paths: Vec<String>) -> Vec<String> {
    let mut result = Vec::new();
    for path in paths {
        if !result.contains(&path) {
            result.push(path);
        }
    }
    result
}

fn repository_topic_clone_operation(command: &str) -> Option<String> {
    let segments = command_segments(command);
    for segment in &segments {
        let Some(interpreter) = segment
            .iter()
            .position(|token| token == "python" || token == "python3")
        else {
            continue;
        };
        let args = &segment[interpreter + 1..];
        let script = args.iter().position(|token| {
            Path::new(token).file_name().and_then(|name| name.to_str())
                == Some("repository_topic_clone.py")
        });
        let Some(script) = script else {
            continue;
        };
        let Some(operation) = args.get(script + 1) else {
            continue;
        };
        if operation != "merge-main" && operation != "finalize-merge" {
            continue;
        }
        if segments.len() != 1 {
            return Some("repository_topic_clone_compound".to_owned());
        }
        return Some(format!(
            "repository_topic_clone_{}",
            operation.replace('-', "_")
        ));
    }
    None
}

fn has_spawn_event(
    root: Option<&Path>,
    actor_id: &JsonString,
    role_id: &JsonString,
    scope_digest: &JsonString,
) -> bool {
    let Some(root) = root else {
        return false;
    };
    let (Some(actor_id), Some(role_id), Some(scope_digest)) = (
        actor_id.to_text(),
        role_id.to_text(),
        scope_digest.to_text(),
    ) else {
        return false;
    };
    let mut pending = vec![root.to_path_buf()];
    while let Some(directory) = pending.pop() {
        let Ok(entries) = fs::read_dir(directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Ok(metadata) = fs::symlink_metadata(&path) else {
                continue;
            };
            if metadata.file_type().is_dir() {
                pending.push(path);
                continue;
            }
            if !metadata.file_type().is_file()
                || path.extension().and_then(|extension| extension.to_str()) != Some("json")
            {
                continue;
            }
            let Ok(text) = fs::read_to_string(&path) else {
                continue;
            };
            let Ok(value) = crate::python_json::parse_json(&text) else {
                continue;
            };
            if object_string(&value, "subagent_event_kind")
                .is_some_and(|value| value.equals_text("spawn"))
                && object_string(&value, "subagent_target")
                    .is_some_and(|value| value.equals_text(&actor_id))
                && object_string(&value, "mutation_scope_digest")
                    .is_some_and(|value| value.equals_text(&scope_digest))
                && object_string(&value, "subagent_agent_type").is_some_and(|value| {
                    value.equals_text(&role_id)
                        || value.equals_text("worker")
                        || value.equals_text("spark_worker")
                })
            {
                return true;
            }
        }
    }
    false
}
