// @dependency-start
// contract implementation
// responsibility Resolves the native eval checker's read-only mounted archive and family search paths.
// upstream design ../../../../../documents/runtime/runtime-log-archive.md owns archive root and family layout
// upstream reference ../../../../../tools/runtime/archive/runtime_log_paths.py shows archive path behavior that remains active for Python producers
// upstream implementation runtime_boundary.rs owns external runtime path containment and no-create resolution
// upstream implementation log_repository_identity.rs owns stable source repository keys
// upstream implementation path_expansion.rs expands explicit user paths
// upstream implementation path_resolution.rs resolves the declared private-log root
// upstream implementation python_text.rs provides Python-compatible environment trimming
// downstream implementation eval_accumulation_check.rs reads accumulated hook and eval results
// @dependency-end

//! Read-only archive paths used by the native eval accumulation checker.

use crate::log_repository_identity::{
    repo_log_key, SOURCE_REMOTE_ENV, SOURCE_REMOTE_NAME_ENV, STABLE_ID_ENV,
};
use crate::python_text::python_strip;
use crate::runtime_boundary::{resolve_external_artifact_path, RuntimeArtifactBoundary};
use std::collections::{BTreeMap, HashSet};
use std::env;
use std::path::{Path, PathBuf};

pub const HOOK_SPOOL_INDEX_NAME: &str = ".spool-index.jsonl";
pub const HOOK_ARCHIVE_DIR_ENV: &str = "AGENT_CANON_HOOK_ARCHIVE_DIR";
pub const PRIVATE_LOG_ROOT_ENV: &str = "AGENT_CANON_LOG_ROOT";
pub const LOG_ARCHIVE_PARENT: &str = "archive/agent-canon-log";

fn source_identity_environment() -> BTreeMap<String, String> {
    [SOURCE_REMOTE_ENV, SOURCE_REMOTE_NAME_ENV, STABLE_ID_ENV]
        .into_iter()
        .filter_map(|name| env::var(name).ok().map(|value| (name.to_owned(), value)))
        .collect()
}

fn log_archive_root(canon_root: &Path, runtime_root: Option<&Path>) -> Result<PathBuf, String> {
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

/// Resolve the existing active report family for a native Eval producer.
pub(crate) fn eval_results_dir(
    canon_root: &Path,
    family: &str,
    runtime_root: Option<&Path>,
) -> Result<PathBuf, String> {
    let canon_root = agent_canon_root(canon_root)?;
    Ok(log_archive_root(&canon_root, runtime_root)?
        .join("eval-results")
        .join(archive_safe_slug(family)))
}

/// Preserve the archive owner's declared marker-to-checkout mapping.
pub(crate) fn agent_canon_root(root: &Path) -> Result<PathBuf, String> {
    let resolved = crate::path_resolution::resolve_non_strict(root)?;
    for (marker, depth) in [
        ("tools/runtime/archive/runtime_log_paths.py", 3),
        ("eval/definitions/README.md", 2),
        ("documents/runtime-log-archive.md", 1),
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
            "tools/runtime/archive/runtime_log_paths.py",
            "eval/definitions/README.md",
            "documents/runtime-log-archive.md",
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
}
