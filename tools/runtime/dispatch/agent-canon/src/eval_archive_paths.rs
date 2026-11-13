// @dependency-start
// contract implementation
// responsibility Resolves the native eval checker's read-only mounted archive and family search paths.
// upstream design ../../../../../documents/runtime/runtime-log-archive.md owns archive root and family layout
// upstream implementation log_repository_identity.rs owns stable repository identities after the archive path migration
// upstream implementation runtime_boundary.rs owns external runtime path containment and no-create resolution
// upstream implementation log_repository_identity.rs owns stable source repository keys
// upstream implementation path_expansion.rs expands explicit user paths
// upstream implementation path_resolution.rs resolves the declared private-log root
// upstream implementation python_text.rs provides Python-compatible environment trimming
// downstream implementation eval_accumulation_check.rs reads accumulated hook and eval results
// @dependency-end

//! Read-only archive paths used by the native eval accumulation checker.

use crate::log_repository_identity::{
    SOURCE_REMOTE_ENV, SOURCE_REMOTE_NAME_ENV, STABLE_ID_ENV, repo_log_key,
};
use crate::python_text::python_strip;
use crate::runtime_boundary::RuntimeSpoolBoundary;
use crate::runtime_boundary::{RuntimeArtifactBoundary, resolve_external_artifact_path};
use std::collections::{BTreeMap, HashSet};
use std::env;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use icu_casemap::CaseMapper;
use sha2::{Digest, Sha256};

pub const HOOK_SPOOL_INDEX_NAME: &str = ".spool-index.jsonl";
pub const HOOK_ARCHIVE_DIR_ENV: &str = "AGENT_CANON_HOOK_ARCHIVE_DIR";
pub const HOOK_EVENT_SPOOL_DIR_ENV: &str = "AGENT_CANON_HOOK_EVENT_SPOOL_DIR";
pub const PRIVATE_LOG_ROOT_ENV: &str = "AGENT_CANON_LOG_ROOT";
pub const LOG_ENV_ENV: &str = "AGENT_CANON_LOG_ENV";
pub const LOG_ARCHIVE_PARENT: &str = "archive/agent-canon-log";
pub const CODEX_RUNTIME_CHAT_DIR_NAME: &str = "chats";
pub const CODEX_RUNTIME_INDEX_FILE: &str = "index.jsonl";
pub const NAMESPACE_HASH_LENGTH: usize = 8;
pub const MAX_KEY_LENGTH: usize = 80;
pub const GIT_COMMIT_KEY_LENGTH: usize = 12;
const GIT_HEAD_TIMEOUT: Duration = Duration::from_secs(5);

fn source_identity_environment() -> BTreeMap<String, String> {
    [SOURCE_REMOTE_ENV, SOURCE_REMOTE_NAME_ENV, STABLE_ID_ENV]
        .into_iter()
        .filter_map(|name| env::var(name).ok().map(|value| (name.to_owned(), value)))
        .collect()
}

pub fn log_archive_root(canon_root: &Path, runtime_root: Option<&Path>) -> Result<PathBuf, String> {
    if let Some(override_value) = env::var_os(HOOK_ARCHIVE_DIR_ENV) {
        let override_value = override_value.to_string_lossy();
        let override_value = python_strip(&override_value);
        if !override_value.is_empty() {
            let candidate = crate::path_expansion::expand_user_path(Path::new(override_value))
                .map_err(|error| format!("explicit archive root is unavailable: {error}"))?;
            if candidate.is_absolute() {
                let resolved = resolve_external_artifact_path(canon_root, &candidate)?;
                let declared = env::var_os(PRIVATE_LOG_ROOT_ENV)
                    .map(|value| value.to_string_lossy().into_owned())
                    .map(|value| python_strip(&value).to_owned())
                    .unwrap_or_default();
                if declared.is_empty() {
                    return Err(
                        "absolute archive override must equal the declared private-log mount root"
                            .to_owned(),
                    );
                }
                let declared = crate::path_expansion::expand_user_path(Path::new(&declared))
                    .map_err(|error| format!("explicit archive root is unavailable: {error}"))?;
                let declared = crate::path_resolution::resolve_non_strict(&declared)
                    .map_err(|_| "explicit archive root is unavailable".to_owned())?;
                if declared != resolved {
                    return Err(
                        "absolute archive override must equal the declared private-log mount root"
                            .to_owned(),
                    );
                }
                return Ok(resolved);
            }
            return RuntimeArtifactBoundary::resolve_read_path(
                canon_root,
                runtime_root,
                &candidate,
            );
        }
    }

    let mounted = RuntimeArtifactBoundary::resolve_read_path(
        canon_root,
        runtime_root,
        Path::new(LOG_ARCHIVE_PARENT),
    )?;
    if mounted.is_dir()
        || runtime_root.is_some()
        || env::var_os(crate::runtime_boundary::RUNTIME_ROOT_ENV)
            .is_some_and(|value| !value.is_empty())
    {
        return Ok(mounted);
    }
    Err(format!(
        "AgentCanon log archive root is required; set {HOOK_ARCHIVE_DIR_ENV} or configure {}",
        crate::runtime_boundary::RUNTIME_ROOT_ENV
    ))
}

/// Return the mounted external archive root without creating the runtime root.
pub fn mounted_log_archive_root(
    canon_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    RuntimeArtifactBoundary::resolve_read_path(
        canon_root,
        runtime_root,
        Path::new(LOG_ARCHIVE_PARENT),
    )
}

/// Resolve the writable archive root under the selected external runtime.
///
/// The absolute legacy override remains valid only when it is the declared
/// private-log mount. Runtime creation and no-follow path checks stay owned by
/// `RuntimeArtifactBoundary`.
pub fn writable_log_archive_root(
    canon_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    let override_value = env::var_os(HOOK_ARCHIVE_DIR_ENV)
        .map(|value| value.to_string_lossy().into_owned())
        .map(|value| python_strip(&value).to_owned())
        .filter(|value| !value.is_empty());
    if let Some(override_value) = override_value {
        let candidate = crate::path_expansion::expand_user_path(Path::new(&override_value))
            .map_err(|error| error.to_string())?;
        if candidate.is_absolute() {
            let resolved = resolve_external_artifact_path(canon_root, &candidate)?;
            let declared = env::var_os(PRIVATE_LOG_ROOT_ENV)
                .map(|value| value.to_string_lossy().into_owned())
                .map(|value| python_strip(&value).to_owned())
                .filter(|value| !value.is_empty())
                .ok_or_else(|| {
                    "absolute archive override must equal the declared private-log mount root"
                        .to_owned()
                })?;
            let declared = crate::path_expansion::expand_user_path(Path::new(&declared))
                .map_err(|error| error.to_string())?;
            let declared = crate::path_resolution::resolve_non_strict(&declared)?;
            if declared != resolved {
                return Err(
                    "absolute archive override must equal the declared private-log mount root"
                        .to_owned(),
                );
            }
            return Ok(resolved);
        }
        let boundary = RuntimeArtifactBoundary::for_source(canon_root, runtime_root, true)?;
        let resolved = boundary.resolve(Path::new(&override_value))?;
        boundary.ensure_directory(Path::new(&override_value))?;
        return Ok(resolved);
    }
    let boundary = RuntimeArtifactBoundary::for_source(canon_root, runtime_root, true)?;
    let resolved = boundary.resolve(Path::new(LOG_ARCHIVE_PARENT))?;
    boundary.ensure_directory(Path::new(LOG_ARCHIVE_PARENT))?;
    Ok(resolved)
}

/// Return the external runtime boundary used by native archive callers.
pub fn archive_runtime_boundary(
    source_root: &Path,
    runtime_root: Option<&Path>,
    create: bool,
) -> Result<RuntimeArtifactBoundary, String> {
    RuntimeArtifactBoundary::for_source(source_root, runtime_root, create)
}

/// Return the restricted host hook-event spool root for one source repository.
pub fn hook_event_spool_root(
    active_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    let boundary = RuntimeSpoolBoundary::for_source(active_root, runtime_root, false)?;
    let repository_key = repo_log_key(active_root, &source_identity_environment())
        .map_err(|error| format!("source repository key is unavailable: {error}"))?;
    let relative = env::var_os(HOOK_EVENT_SPOOL_DIR_ENV)
        .map(|value| PathBuf::from(value.to_string_lossy().into_owned()))
        .filter(|value| !value.as_os_str().is_empty())
        .map(|value| value.join(&repository_key))
        .unwrap_or_else(|| PathBuf::from("spool/hook-events").join(&repository_key));
    boundary.resolve(&relative)
}

/// Return the source-local publication outcome spool root.
pub fn runtime_event_publication_outcome_spool_root(
    active_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    RuntimeSpoolBoundary::for_source(active_root, runtime_root, false)?
        .resolve(Path::new("spool/publication-outcome"))
}

/// Return the default PostToolUse spool path.
pub fn post_tooluse_spool_path(
    root: &Path,
    hook_run_id: &str,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    let boundary = RuntimeSpoolBoundary::for_source(root, runtime_root, false)?;
    let repository_key = repo_log_key(root, &source_identity_environment())
        .map_err(|error| format!("source repository key is unavailable: {error}"))?;
    let spool_root = env::var_os(HOOK_EVENT_SPOOL_DIR_ENV)
        .map(|value| PathBuf::from(value.to_string_lossy().into_owned()))
        .filter(|value| !value.as_os_str().is_empty())
        .map(|value| value.join(&repository_key))
        .unwrap_or_else(|| PathBuf::from("spool/hook-events").join(&repository_key));
    boundary.resolve(
        &spool_root
            .join("post-tool-use/hook")
            .join(format!("{hook_run_id}.json")),
    )
}

/// Return the deterministic local environment key used by legacy archive paths.
pub fn log_environment_key(root: &Path) -> String {
    let configured = env::var(LOG_ENV_ENV).unwrap_or_default();
    if !python_strip(&configured).is_empty() {
        return safe_slug(python_strip(&configured));
    }
    for name in [
        "DEVCONTAINER_PROJECT_NAME",
        "COMPOSE_PROJECT_NAME",
        "CODESPACE_NAME",
        "HOSTNAME",
    ] {
        if let Ok(value) = env::var(name) {
            if !python_strip(&value).is_empty() {
                return safe_slug(python_strip(&value));
            }
        }
    }
    let canonical =
        crate::path_resolution::resolve_non_strict(root).unwrap_or_else(|_| root.into());
    safe_slug(
        canonical
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("agent-canon"),
    )
}

/// Return a source-compatible lowercase path segment.
pub fn safe_slug(value: &str) -> String {
    static INVALID: OnceLock<regex::Regex> = OnceLock::new();
    let invalid = INVALID
        .get_or_init(|| regex::Regex::new(r"[^A-Za-z0-9_.-]+").expect("static slug pattern"));
    let folded = CaseMapper::new().fold_string(&invalid.replace_all(value, "-"));
    let slug = folded.trim_matches(['.', '_', '-']);
    let slug = slug.chars().take(MAX_KEY_LENGTH).collect::<String>();
    let slug = slug.trim_matches(['.', '_', '-']);
    if slug.is_empty() {
        "unknown".to_owned()
    } else {
        slug.to_owned()
    }
}

pub fn short_hash(value: &str) -> String {
    Sha256::digest(value.as_bytes())[..NAMESPACE_HASH_LENGTH / 2]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// Return the active Codex chat/session trace identifier when one is supplied.
pub fn codex_trace_key() -> String {
    [
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
        "CODEX_CONVERSATION_ID",
    ]
    .iter()
    .find_map(|name| {
        env::var(name)
            .ok()
            .map(|value| python_strip(&value).to_owned())
            .filter(|value| !value.is_empty())
    })
    .unwrap_or_default()
}

/// Return the privacy-preserving local chat metadata key.
pub fn log_chat_key(source_root: &Path) -> String {
    let trace = codex_trace_key();
    if !trace.is_empty() {
        safe_slug(&trace)
    } else {
        format!(
            "no-chat-{}",
            repo_log_key(source_root, &source_identity_environment())
                .unwrap_or_else(|_| "unidentified-source".to_owned())
        )
    }
}

/// Return the stable source repository ID used as the archive branch key.
pub fn log_branch_key(source_root: &Path) -> Result<String, String> {
    let identity = crate::log_repository_identity::stable_source_id_from_runtime_env(
        Some(source_root),
        &source_identity_environment(),
    )
    .map_err(|error| error.to_string())?;
    if identity == crate::log_repository_identity::UNIDENTIFIED_SOURCE {
        return Err("source remote identity is unavailable".to_owned());
    }
    Ok(identity)
}

/// Return Git HEAD only when the requested directory is the Git toplevel.
pub fn source_git_head(source_root: &Path) -> String {
    let mut child = match Command::new("git")
        .arg("-C")
        .arg(source_root)
        .args(["rev-parse", "--show-toplevel", "--verify", "HEAD"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(_) => return String::new(),
    };
    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                if !status.success() {
                    return String::new();
                }
                let output = match child.wait_with_output() {
                    Ok(output) => output,
                    Err(_) => return String::new(),
                };
                let text = String::from_utf8_lossy(&output.stdout);
                let mut lines = text.lines();
                let Some(discovered) = lines.next() else {
                    return String::new();
                };
                let Some(head) = lines.next() else {
                    return String::new();
                };
                if lines.next().is_some() {
                    return String::new();
                }
                let requested = crate::path_resolution::resolve_non_strict(source_root)
                    .unwrap_or_else(|_| source_root.to_path_buf());
                let discovered = crate::path_resolution::resolve_non_strict(Path::new(discovered))
                    .unwrap_or_else(|_| PathBuf::from(discovered));
                return if discovered == requested {
                    head.trim().to_owned()
                } else {
                    String::new()
                };
            }
            Ok(None) if started.elapsed() < GIT_HEAD_TIMEOUT => {
                std::thread::sleep(Duration::from_millis(10))
            }
            Ok(None) | Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                return String::new();
            }
        }
    }
}

/// Return the AgentCanon source commit key used in hook and runtime filenames.
pub fn agent_canon_git_commit_key(canon_root: &Path) -> String {
    let head = source_git_head(canon_root);
    if head.is_empty() {
        "no-git-head".to_owned()
    } else {
        safe_slug(&head.chars().take(GIT_COMMIT_KEY_LENGTH).collect::<String>())
    }
}

pub fn hook_log_file_name(hook_name: &str, canon_root: &Path) -> String {
    format!(
        "{}-{}.jsonl",
        safe_slug(hook_name),
        agent_canon_git_commit_key(canon_root)
    )
}

pub fn codex_runtime_summary_file(canon_root: &Path) -> String {
    format!("summary-{}.jsonl", agent_canon_git_commit_key(canon_root))
}

pub fn agent_report_archive_dir(
    active_root: &Path,
    canon_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    let source_key = repo_log_key(active_root, &source_identity_environment())
        .map_err(|error| format!("source repository key is unavailable: {error}"))?;
    Ok(log_archive_root(canon_root, runtime_root)?
        .join("agent-reports")
        .join(source_key))
}

pub fn codex_runtime_summary_dir(
    active_root: &Path,
    canon_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    let source_key = repo_log_key(active_root, &source_identity_environment())
        .map_err(|error| format!("source repository key is unavailable: {error}"))?;
    Ok(log_archive_root(canon_root, runtime_root)?
        .join("codex-runtime")
        .join(source_key))
}

pub fn codex_runtime_chat_dir(
    active_root: &Path,
    canon_root: &Path,
    conversation_id: &str,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    Ok(
        codex_runtime_summary_dir(active_root, canon_root, runtime_root)?
            .join(CODEX_RUNTIME_CHAT_DIR_NAME)
            .join(safe_slug(conversation_id)),
    )
}

pub fn codex_runtime_summary_path(
    active_root: &Path,
    canon_root: &Path,
    conversation_id: &str,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    Ok(
        codex_runtime_chat_dir(active_root, canon_root, conversation_id, runtime_root)?
            .join(codex_runtime_summary_file(canon_root)),
    )
}

pub fn codex_runtime_index_path(
    active_root: &Path,
    canon_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    Ok(
        codex_runtime_summary_dir(active_root, canon_root, runtime_root)?
            .join(CODEX_RUNTIME_INDEX_FILE),
    )
}

/// Resolve the existing active report family for a native Eval producer.
pub fn eval_results_dir(
    canon_root: &Path,
    family: &str,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    let canon_root = agent_canon_root(canon_root)?;
    Ok(log_archive_root(&canon_root, runtime_root)?
        .join("eval-results")
        .join(archive_safe_slug(family)))
}

/// Return the hook JSONL directory for one source repository.
pub fn hook_results_dir(
    active_root: &Path,
    canon_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    let source_key = repo_log_key(active_root, &source_identity_environment())
        .map_err(|error| format!("source repository key is unavailable: {error}"))?;
    Ok(log_archive_root(canon_root, runtime_root)?
        .join("hook-runs")
        .join(source_key))
}

/// Preserve the archive owner's declared marker-to-checkout mapping.
pub fn agent_canon_root(root: &Path) -> Result<PathBuf, String> {
    let resolved = crate::path_resolution::resolve_non_strict(root)?;
    for (marker, depth) in [
        (
            "tools/runtime/dispatch/agent-canon/src/log_repository_identity.rs",
            5,
        ),
        ("eval/definitions/README.md", 2),
        ("documents/runtime/runtime-log-archive.md", 2),
    ] {
        let marker = resolved.join(marker);
        if marker.is_file() {
            let marker = crate::path_resolution::resolve_non_strict(&marker)?;
            return marker
                .ancestors()
                .nth(depth + 1)
                .map(Path::to_path_buf)
                .ok_or_else(|| "archive source marker has insufficient parents".to_owned());
        }
    }
    Ok(resolved)
}

/// Return whether one path contains a declared AgentCanon source marker.
pub fn is_agent_canon_root(root: &Path) -> bool {
    [
        "tools/runtime/dispatch/agent-canon/src/log_repository_identity.rs",
        "eval/definitions/README.md",
        "documents/runtime-log-archive.md",
    ]
    .iter()
    .any(|marker| root.join(marker).is_file())
}

/// Resolve a declared source marker back to its owning checkout.
pub fn marker_resolved_root(root: &Path) -> Result<Option<PathBuf>, String> {
    let resolved = crate::path_resolution::resolve_non_strict(root)?;
    for (marker, depth) in [
        (
            "tools/runtime/dispatch/agent-canon/src/log_repository_identity.rs",
            5,
        ),
        ("eval/definitions/README.md", 2),
        ("documents/runtime/runtime-log-archive.md", 2),
    ] {
        let marker = resolved.join(marker);
        if marker.is_file() {
            let marker = crate::path_resolution::resolve_non_strict(&marker)?;
            return marker
                .ancestors()
                .nth(depth + 1)
                .map(Path::to_path_buf)
                .map(Some)
                .ok_or_else(|| "archive source marker has insufficient parents".to_owned());
        }
    }
    Ok(None)
}

/// Return the marker-owned checkout, or the resolved unmarked root.
pub fn canonical_source_root(root: &Path) -> Result<PathBuf, String> {
    let resolved = crate::path_resolution::resolve_non_strict(root)?;
    Ok(marker_resolved_root(&resolved)?.unwrap_or(resolved))
}

/// Return the active and legacy-import eval directories for one family.
pub fn eval_result_search_dirs(
    canon_root: &Path,
    family: &str,
    runtime_root: Option<&Path>,
) -> Result<Vec<PathBuf>, String> {
    let family_slug = archive_safe_slug(family);
    let archive_root = log_archive_root(canon_root, runtime_root)?;
    Ok(unique_paths([
        archive_root.join("eval-results").join(&family_slug),
        archive_root
            .join("eval-results")
            .join("legacy-import")
            .join(family_slug),
    ]))
}

/// Return repository-scoped, legacy-import, and unscoped hook result directories.
pub fn hook_result_search_dirs(
    requested_root: &Path,
    canon_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<Vec<PathBuf>, String> {
    let archive_root = log_archive_root(canon_root, runtime_root)?;
    let source_key = repo_log_key(requested_root, &source_identity_environment())
        .map_err(|error| format!("source repository key is unavailable: {error}"))?;
    Ok(unique_paths([
        archive_root.join("hook-runs").join(source_key),
        archive_root.join("hook-runs").join("legacy-import"),
        archive_root.join("hook-runs"),
    ]))
}

fn unique_paths<const N: usize>(paths: [PathBuf; N]) -> Vec<PathBuf> {
    let mut seen = HashSet::new();
    paths
        .into_iter()
        .filter(|path| seen.insert(path.clone()))
        .collect()
}

fn archive_safe_slug(value: &str) -> String {
    let mut slug = String::with_capacity(value.len().min(80));
    let mut replacing = false;
    for character in value.chars() {
        if character.is_ascii_alphanumeric() || matches!(character, '_' | '.' | '-') {
            slug.push(character.to_ascii_lowercase());
            replacing = false;
        } else if !replacing {
            slug.push('-');
            replacing = true;
        }
    }
    let slug = slug.trim_matches(['.', '_', '-']);
    let slug = slug.chars().take(80).collect::<String>();
    let slug = slug.trim_matches(['.', '_', '-']);
    if slug.is_empty() {
        "unknown".to_owned()
    } else {
        slug.to_owned()
    }
}
#[cfg(test)]
mod source_root_tests {
    use super::agent_canon_root;
    use std::fs;

    #[test]
    fn each_declared_marker_maps_to_the_source_checkout() {
        for marker in [
            "tools/runtime/dispatch/agent-canon/src/log_repository_identity.rs",
            "eval/definitions/README.md",
            "documents/runtime/runtime-log-archive.md",
        ] {
            let temporary = tempfile::tempdir().unwrap();
            let source = fs::canonicalize(temporary.path()).unwrap();
            let path = source.join(marker);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, "marker\n").unwrap();
            assert_eq!(agent_canon_root(&source).unwrap(), source);
        }
    }

    #[test]
    fn consumer_root_is_retained_without_searching_vendor() {
        let temporary = tempfile::tempdir().unwrap();
        let source = fs::canonicalize(temporary.path()).unwrap();
        let nested = source.join("vendor/agent-canon/eval/definitions");
        fs::create_dir_all(&nested).unwrap();
        fs::write(nested.join("README.md"), "marker\n").unwrap();
        assert_eq!(agent_canon_root(&source).unwrap(), source);
    }

    #[cfg(unix)]
    #[test]
    fn resolved_marker_identity_selects_the_actual_checkout() {
        let temporary = tempfile::tempdir().unwrap();
        let base = fs::canonicalize(temporary.path()).unwrap();
        let source = base.join("source");
        let alias = base.join("alias");
        let relative = "eval/definitions/README.md";
        fs::create_dir_all(source.join("eval/definitions")).unwrap();
        fs::create_dir_all(alias.join("eval/definitions")).unwrap();
        fs::write(source.join(relative), "marker\n").unwrap();
        std::os::unix::fs::symlink(source.join(relative), alias.join(relative)).unwrap();
        assert_eq!(agent_canon_root(&alias).unwrap(), source);
    }

    #[test]
    fn migrated_path_owner_preserves_repository_and_runtime_layouts() {
        let temporary = tempfile::tempdir().unwrap();
        let source = temporary.path().join("consumer");
        let canon = temporary.path().join("agent-canon");
        let runtime = temporary.path().join("runtime");
        std::fs::create_dir_all(source.join(".git")).unwrap();
        std::fs::create_dir_all(&canon).unwrap();
        std::fs::create_dir_all(&runtime).unwrap();
        std::fs::write(
            source.join(".git/config"),
            "[remote \"origin\"]\nurl = https://github.com/example/consumer.git\n",
        )
        .unwrap();

        let environment = source_identity_environment();
        let key = repo_log_key(&source, &environment).unwrap();
        assert_eq!(
            key,
            crate::log_repository_identity::stable_source_repository_id(
                "https://github.com/example/consumer.git"
            )
            .unwrap()
        );
        let archive = mounted_log_archive_root(&canon, Some(&runtime)).unwrap();
        assert_eq!(archive, runtime.join("archive/agent-canon-log"));
        assert_eq!(
            hook_result_search_dirs(&source, &canon, Some(&runtime)).unwrap(),
            vec![
                archive.join("hook-runs").join(&key),
                archive.join("hook-runs/legacy-import"),
                archive.join("hook-runs"),
            ]
        );
        assert_eq!(
            eval_result_search_dirs(&canon, "workflow-selection", Some(&runtime)).unwrap(),
            vec![
                archive.join("eval-results/workflow-selection"),
                archive.join("eval-results/legacy-import/workflow-selection"),
            ]
        );
        assert_eq!(
            hook_event_spool_root(&source, Some(&runtime)).unwrap(),
            runtime.join("spool/hook-events").join(key)
        );
        assert_eq!(
            runtime_event_publication_outcome_spool_root(&source, Some(&runtime)).unwrap(),
            runtime.join("spool/publication-outcome")
        );
        assert_eq!(
            agent_report_archive_dir(&source, &canon, Some(&runtime)).unwrap(),
            archive.join("agent-reports").join(&key)
        );
        assert_eq!(
            codex_runtime_index_path(&source, &canon, Some(&runtime)).unwrap(),
            archive.join("codex-runtime").join(&key).join("index.jsonl")
        );
        assert_eq!(
            codex_runtime_summary_path(&source, &canon, "conversation-1", Some(&runtime),).unwrap(),
            archive
                .join("codex-runtime")
                .join(&key)
                .join("chats/conversation-1/summary-no-git-head.jsonl")
        );
        assert_eq!(
            hook_log_file_name("SessionStart", &canon),
            "sessionstart-no-git-head.jsonl"
        );
        assert_eq!(safe_slug("  Team / Project  "), "team-project");
        assert_eq!(safe_slug("---"), "unknown");
        assert_eq!(short_hash("archive"), "0eb3e36b");
    }
}
