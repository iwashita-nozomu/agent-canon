// @dependency-start
// contract implementation
// responsibility Resolves the current repository root and existing AgentCanon source-root overrides for the hook.
// upstream implementation ../../../../../tools/runtime/source/agent_canon_source_root.py owns the shared root-resolution contract.
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
    let resolved = resolve_non_strict(&expanded)?;
    if !is_within(&resolved, &expanded) {
        return Err(format!(
            "source-root override resolves outside its declared root: {}",
            resolved.display()
        ));
    }
    Ok(resolved)
}

pub(crate) fn has_catalog(root: &Path) -> bool {
    root.join("agents/skills/catalog.yaml").is_file()
}

fn is_within(path: &Path, root: &Path) -> bool {
    path == root || root.is_absolute() && path.starts_with(root)
}

fn env_value(environment: &BTreeMap<String, String>, key: &str) -> String {
    environment
        .get(key)
        .map(|value| python_strip(value).to_owned())
        .unwrap_or_default()
}
