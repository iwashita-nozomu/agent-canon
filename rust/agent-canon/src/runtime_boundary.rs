//! Common filesystem boundary checks for analysis runtime artifacts.
//!
//! Analysis reads the selected source tree, but all databases, snapshots,
//! temporary files, and reports belong to an explicitly external runtime
//! root.  Keeping this policy in one module prevents individual tools from
//! accidentally recreating the old `.agent-canon` source-tree cache.

use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

pub(crate) const RUNTIME_ROOT_ENV: &str = "AGENT_CANON_RUNTIME_ROOT";

pub(crate) fn runtime_root_is_explicit() -> bool {
    env::var_os(RUNTIME_ROOT_ENV).is_some_and(|value| !value.is_empty())
}

fn absolute(path: &Path) -> Result<PathBuf, String> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        env::current_dir()
            .map(|cwd| cwd.join(path))
            .map_err(|error| format!("resolve {}: {error}", path.display()))
    }
}

fn canonical_existing_parent(path: &Path) -> Result<PathBuf, String> {
    let mut cursor = path.to_path_buf();
    while !cursor.exists() {
        cursor = cursor
            .parent()
            .ok_or_else(|| format!("no existing parent for {}", path.display()))?
            .to_path_buf();
    }
    fs::canonicalize(&cursor).map_err(|error| format!("canonicalize {}: {error}", cursor.display()))
}

/// Resolve the process/task runtime root and prove that it is not the source.
///
/// Production callers must provide `AGENT_CANON_RUNTIME_ROOT`.  Unit tests
/// use a deterministic temporary root so that existing pure Rust fixtures can
/// continue to exercise the public command semantics without writing source.
pub(crate) fn resolve_runtime_root(source_root: &Path) -> Result<PathBuf, String> {
    let requested = env::var_os(RUNTIME_ROOT_ENV)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from);
    resolve_runtime_root_at(source_root, requested.as_deref())
}

pub(crate) fn resolve_runtime_root_at(
    source_root: &Path,
    requested: Option<&Path>,
) -> Result<PathBuf, String> {
    let source = fs::canonicalize(source_root).map_err(|error| {
        format!(
            "canonicalize source root {}: {error}",
            source_root.display()
        )
    })?;
    // The explicit match keeps the test-only fallback lazy without creating a
    // non-test closure that Clippy correctly identifies as unnecessary.
    #[allow(clippy::manual_map)]
    let raw = match requested {
        Some(requested) => Some(requested.to_path_buf()),
        None => {
            #[cfg(test)]
            {
                let digest = Sha256::digest(source.to_string_lossy().as_bytes());
                let key = digest[..8]
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect::<String>();
                Some(env::temp_dir().join(format!("agent-canon-test-runtime-{key}")))
            }
            #[cfg(not(test))]
            {
                None
            }
        }
    }
    .ok_or_else(|| {
        format!(
            "{RUNTIME_ROOT_ENV} is required; analysis artifacts must use an external runtime root"
        )
    })?;
    let raw = absolute(&raw)?;
    let mut cursor = PathBuf::new();
    for component in raw.components() {
        cursor.push(component.as_os_str());
        if cursor.exists() {
            let metadata = fs::symlink_metadata(&cursor)
                .map_err(|error| format!("inspect runtime path {}: {error}", cursor.display()))?;
            if metadata.file_type().is_symlink() {
                return Err(format!(
                    "runtime root contains symlink component {}; choose an explicit physical path",
                    cursor.display()
                ));
            }
        }
    }
    let existing_parent = canonical_existing_parent(&raw)?;
    if existing_parent == source || existing_parent.starts_with(&source) {
        return Err(format!(
            "runtime root {} is inside source root {}; choose an external root",
            raw.display(),
            source.display()
        ));
    }
    fs::create_dir_all(&raw)
        .map_err(|error| format!("create runtime root {}: {error}", raw.display()))?;
    let runtime = fs::canonicalize(&raw)
        .map_err(|error| format!("canonicalize runtime root {}: {error}", raw.display()))?;
    if runtime == source || runtime.starts_with(&source) {
        return Err(format!(
            "runtime root {} is inside source root {}; choose an external root",
            runtime.display(),
            source.display()
        ));
    }
    Ok(runtime)
}

/// Validate a write target: it must be absolute, external to the source, and
/// contained by the runtime root after resolving all existing symlinks.
pub(crate) fn validate_external_target(
    source_root: &Path,
    runtime_root: &Path,
    target: &Path,
    label: &str,
) -> Result<PathBuf, String> {
    let source = fs::canonicalize(source_root).map_err(|error| {
        format!(
            "canonicalize source root {}: {error}",
            source_root.display()
        )
    })?;
    let runtime = fs::canonicalize(runtime_root).map_err(|error| {
        format!(
            "canonicalize runtime root {}: {error}",
            runtime_root.display()
        )
    })?;
    let target = absolute(target)?;
    let parent = target
        .parent()
        .ok_or_else(|| format!("{label} has no parent: {}", target.display()))?;
    let canonical_parent = canonical_existing_parent(parent)?;
    if canonical_parent == source || canonical_parent.starts_with(&source) {
        return Err(format!(
            "{label} {} is inside source root {}",
            target.display(),
            source.display()
        ));
    }
    if canonical_parent != runtime && !canonical_parent.starts_with(&runtime) {
        return Err(format!(
            "{label} {} escapes runtime root {}",
            target.display(),
            runtime.display()
        ));
    }
    if target.exists() {
        let canonical_target = fs::canonicalize(&target)
            .map_err(|error| format!("canonicalize {label} {}: {error}", target.display()))?;
        if canonical_target == source || canonical_target.starts_with(&source) {
            return Err(format!(
                "{label} {} resolves inside source root {}",
                target.display(),
                source.display()
            ));
        }
        if canonical_target != runtime && !canonical_target.starts_with(&runtime) {
            return Err(format!(
                "{label} {} resolves outside runtime root {}",
                target.display(),
                runtime.display()
            ));
        }
    }
    Ok(target)
}

pub(crate) fn stable_source_key(source_root: &Path) -> String {
    let digest = Sha256::digest(source_root.to_string_lossy().as_bytes());
    digest[..12]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn rejects_source_and_symlink_escape() {
        let root = env::temp_dir().join("agent-canon-runtime-boundary-source");
        let runtime = env::temp_dir().join("agent-canon-runtime-boundary-runtime");
        let outside = env::temp_dir().join("agent-canon-runtime-boundary-outside");
        let _ = fs::remove_dir_all(&root);
        let _ = fs::remove_dir_all(&runtime);
        let _ = fs::remove_dir_all(&outside);
        fs::create_dir_all(&root).unwrap();
        fs::create_dir_all(&runtime).unwrap();
        fs::create_dir_all(&outside).unwrap();
        assert!(validate_external_target(&root, &runtime, &root.join("cache"), "db").is_err());
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(&outside, runtime.join("escape")).unwrap();
            assert!(
                validate_external_target(&root, &runtime, &runtime.join("escape/db"), "db")
                    .is_err()
            );
        }
        let _ = fs::remove_dir_all(&root);
        let _ = fs::remove_dir_all(&runtime);
        let _ = fs::remove_dir_all(&outside);
    }
}
