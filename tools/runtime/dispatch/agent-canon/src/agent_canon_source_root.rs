// @dependency-start
// contract implementation
// responsibility Resolves the current repository root and existing AgentCanon source-root overrides for the hook.
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/agent_canon_source_root.rs owns the shared root-resolution contract.
// downstream implementation ./hook_dispatcher.rs uses the current repository root for hook state.
// @dependency-end
//! Read-only source-root selection used by the native hook dispatcher.

use crate::path_expansion::expand_user_path;
use crate::path_resolution::resolve_non_strict;
use crate::python_text::python_strip;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

pub const LAYOUT_STANDALONE: &str = "standalone";
pub const LAYOUT_EXTERNAL: &str = "external";
pub const SOURCE_ROOT_OVERRIDE_ENV: &str = "AGENT_CANON_SOURCE_ROOT";
pub const CANON_ROOT_OVERRIDE_ENV: &str = "AGENT_CANON_ROOT";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HookSourceRootResolution {
    pub current_repository_root: PathBuf,
    pub layout: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceRoots {
    pub current_repository_root: PathBuf,
    pub source_root: PathBuf,
    pub canon_root: PathBuf,
    pub layout: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceRootFailure {
    pub code: &'static str,
    pub detail: String,
}

pub fn resolve_source_roots(
    raw_root: &Path,
    environment: &BTreeMap<String, String>,
) -> Result<SourceRoots, SourceRootFailure> {
    let current_repository_root =
        find_current_repository_root(raw_root).map_err(|detail| SourceRootFailure {
            code: "agent_canon_source_root_missing",
            detail,
        })?;
    let source = env_value(environment, SOURCE_ROOT_OVERRIDE_ENV);
    let canon = env_value(environment, CANON_ROOT_OVERRIDE_ENV);
    if source.is_empty() && canon.is_empty() {
        if !has_catalog(&current_repository_root) {
            return Err(SourceRootFailure {
                code: "agent_canon_source_root_missing",
                detail: format!("No AgentCanon catalog found at current_repository_root={}; select an external checkout with AGENT_CANON_SOURCE_ROOT", current_repository_root.display()),
            });
        }
        return Ok(SourceRoots {
            source_root: current_repository_root.clone(),
            canon_root: current_repository_root.clone(),
            current_repository_root,
            layout: LAYOUT_STANDALONE.into(),
        });
    }
    let resolve = |value: &str, kind: &str| -> Result<PathBuf, SourceRootFailure> {
        let (invalid, missing) = if kind == "source" {
            (
                "agent_canon_source_root_override_invalid",
                "agent_canon_source_root_override_missing",
            )
        } else {
            (
                "agent_canon_canon_root_override_invalid",
                "agent_canon_canon_root_override_missing",
            )
        };
        let root = resolve_override(value).map_err(|detail| SourceRootFailure {
            code: invalid,
            detail,
        })?;
        if !has_catalog(&root) {
            return Err(SourceRootFailure {
                code: missing,
                detail: format!(
                    "Override {kind} root has no AgentCanon catalog: {}",
                    root.display()
                ),
            });
        }
        Ok(root)
    };
    Ok(SourceRoots {
        current_repository_root,
        source_root: resolve(if source.is_empty() { &canon } else { &source }, "source")?,
        canon_root: resolve(if canon.is_empty() { &source } else { &canon }, "canon")?,
        layout: LAYOUT_EXTERNAL.into(),
    })
}

/// Preserve the shared resolver's repository-root and standalone/external result.
/// The hook caller supplies its known environment and entry directory.
pub fn resolve_agent_canon_source_root(
    raw_root: &Path,
    environment: &BTreeMap<String, String>,
) -> Result<HookSourceRootResolution, String> {
    let current_repository_root = find_current_repository_root(raw_root)?;
    let source_override = env_value(environment, SOURCE_ROOT_OVERRIDE_ENV);
    let canon_override = env_value(environment, CANON_ROOT_OVERRIDE_ENV);
    if !source_override.is_empty() || !canon_override.is_empty() {
        let source = if source_override.is_empty() {
            &canon_override
        } else {
            &source_override
        };
        let canon = if canon_override.is_empty() {
            &source_override
        } else {
            &canon_override
        };
        let source = resolve_override(source)?;
        let canon = resolve_override(canon)?;
        if !has_catalog(&source) {
            return Err(format!(
                "source root override has no AgentCanon catalog: {}",
                source.display()
            ));
        }
        if !has_catalog(&canon) {
            return Err(format!(
                "canon root override has no AgentCanon catalog: {}",
                canon.display()
            ));
        }
        return Ok(HookSourceRootResolution {
            current_repository_root,
            layout: LAYOUT_EXTERNAL.to_owned(),
        });
    }
    if !has_catalog(&current_repository_root) {
        return Err(format!(
            "no AgentCanon catalog at current repository root {}",
            current_repository_root.display()
        ));
    }
    Ok(HookSourceRootResolution {
        current_repository_root,
        layout: LAYOUT_STANDALONE.to_owned(),
    })
}

fn find_current_repository_root(raw_root: &Path) -> Result<PathBuf, String> {
    let start = resolve_non_strict(raw_root)?;
    for candidate in start.ancestors() {
        if has_catalog(candidate) || candidate.join(".git").exists() {
            return resolve_non_strict(candidate);
        }
    }
    Ok(start)
}

fn resolve_override(value: &str) -> Result<PathBuf, String> {
    let expanded = expand_user_path(Path::new(value)).map_err(|error| error.to_string())?;
    // Source selection is read-only. Compare and return physical paths; mutation
    // authority remains with the separate no-follow filesystem capabilities.
    resolve_non_strict(&expanded)
}

pub(crate) fn has_catalog(root: &Path) -> bool {
    root.join("agents/skills/catalog.yaml").is_file()
}

fn env_value(environment: &BTreeMap<String, String>, key: &str) -> String {
    environment
        .get(key)
        .map(|value| python_strip(value).to_owned())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn catalog(root: &Path) {
        let directory = root.join("agents/skills");
        std::fs::create_dir_all(&directory).expect("create fixture catalog directory");
        std::fs::write(directory.join("catalog.yaml"), "skills: []\n")
            .expect("write fixture catalog");
    }

    #[test]
    fn standalone_root_discovery_uses_nearest_catalog_and_preserves_layout() {
        let temporary = tempfile::tempdir().expect("temporary root");
        let source = temporary.path().join("source");
        let nested = source.join("tools/runtime");
        std::fs::create_dir_all(&nested).expect("create nested source path");
        catalog(&source);

        let roots = resolve_source_roots(&nested, &BTreeMap::new()).expect("standalone roots");

        assert_eq!(
            roots.current_repository_root,
            source.canonicalize().unwrap()
        );
        assert_eq!(roots.source_root, roots.current_repository_root);
        assert_eq!(roots.canon_root, roots.current_repository_root);
        assert_eq!(roots.layout, LAYOUT_STANDALONE);
    }

    #[test]
    fn external_overrides_keep_current_source_and_canon_roots_distinct() {
        let temporary = tempfile::tempdir().expect("temporary root");
        let current = temporary.path().join("parent");
        let source = temporary.path().join("development/source");
        let canon = temporary.path().join("installed/canon");
        std::fs::create_dir_all(&current).expect("create current root");
        catalog(&current);
        catalog(&source);
        catalog(&canon);
        let environment = BTreeMap::from([
            (
                SOURCE_ROOT_OVERRIDE_ENV.to_owned(),
                source.display().to_string(),
            ),
            (
                CANON_ROOT_OVERRIDE_ENV.to_owned(),
                canon.display().to_string(),
            ),
        ]);

        let roots = resolve_source_roots(&current, &environment).expect("external roots");

        assert_eq!(
            roots.current_repository_root,
            current.canonicalize().unwrap()
        );
        assert_eq!(roots.source_root, source.canonicalize().unwrap());
        assert_eq!(roots.canon_root, canon.canonicalize().unwrap());
        assert_eq!(roots.layout, LAYOUT_EXTERNAL);
    }

    #[test]
    fn missing_override_catalog_returns_the_typed_owner_failure() {
        let temporary = tempfile::tempdir().expect("temporary root");
        let current = temporary.path().join("parent");
        let source = temporary.path().join("source-without-catalog");
        std::fs::create_dir_all(&current).expect("create current root");
        catalog(&current);
        std::fs::create_dir_all(&source).expect("create source root");
        let environment = BTreeMap::from([(
            SOURCE_ROOT_OVERRIDE_ENV.to_owned(),
            source.display().to_string(),
        )]);

        let failure = resolve_source_roots(&current, &environment).unwrap_err();

        assert_eq!(failure.code, "agent_canon_source_root_override_missing");
    }

    #[test]
    fn unregistered_current_root_fails_closed_without_override() {
        let temporary = tempfile::tempdir().expect("temporary root");

        let failure = resolve_source_roots(temporary.path(), &BTreeMap::new()).unwrap_err();

        assert_eq!(failure.code, "agent_canon_source_root_missing");
    }

    #[test]
    fn hook_resolution_returns_only_the_current_root_and_layout() {
        let temporary = tempfile::tempdir().expect("temporary root");
        let source = temporary.path().join("source");
        let nested = source.join("tools/hooks");
        std::fs::create_dir_all(&nested).expect("create nested source path");
        catalog(&source);

        let resolution =
            resolve_agent_canon_source_root(&nested, &BTreeMap::new()).expect("hook source root");

        assert_eq!(
            resolution.current_repository_root,
            source.canonicalize().unwrap()
        );
        assert_eq!(resolution.layout, LAYOUT_STANDALONE);
    }
}
