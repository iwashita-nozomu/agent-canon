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
