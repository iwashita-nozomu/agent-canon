//! Exact, caller-supplied capabilities for bounded source-file rewrites.
// @dependency-start
// contract implementation
// responsibility Validates source mutation capabilities and writes only beneath their exact source-bound paths.
// upstream implementation runtime_boundary.rs owns external runtime artifacts and intentionally rejects source writes
// upstream design ../../../../../tools/analysis/documents/formatting/_runtime_output.py defines the existing capability JSON contract
// downstream implementation docs.rs uses this capability for explicit link rewrites
// downstream test ../tests/source_mutation_native.rs validates exact scope and no-follow writes
// @dependency-end

use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt};
use serde_json::{Map, Value};
use std::collections::BTreeSet;
use std::fmt;
use std::fs;
use std::io::{self, Write};
use std::path::{Component, Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceMutationError {
    detail: String,
}

impl SourceMutationError {
    fn new(detail: impl Into<String>) -> Self {
        Self {
            detail: detail.into(),
        }
    }
}

impl fmt::Display for SourceMutationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.detail)
    }
}

impl std::error::Error for SourceMutationError {}

pub type Result<T> = std::result::Result<T, SourceMutationError>;

/// An opaque mutation grant bound to one canonical source root and allowed subtrees.
#[derive(Debug, Clone)]
pub struct SourceMutationCapability {
    source_root: PathBuf,
    allowed_paths: Vec<PathBuf>,
    _purpose: String,
    _authority: String,
}

impl SourceMutationCapability {
    /// Parse the existing exact three-field mutation-capability JSON shape.
    pub fn from_json(source_root: &Path, raw: Option<&str>) -> Result<Self> {
        let raw = raw.filter(|value| !value.is_empty()).ok_or_else(|| {
            SourceMutationError::new(
                "explicit mutation capability required; pass --mutation-capability-json",
            )
        })?;
        let value: Value = serde_json::from_str(raw)
            .map_err(|_| SourceMutationError::new("mutation capability is not valid JSON"))?;
        let object = value
            .as_object()
            .ok_or_else(|| SourceMutationError::new("mutation capability must be a JSON object"))?;
        reject_unknown_fields(object)?;
        let source_root = fs::canonicalize(source_root).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot resolve mutation source root {}: {error}",
                source_root.display()
            ))
        })?;
        let allowed_paths = parse_allowed_paths(object, &source_root)?;
        let purpose = required_label(object, "purpose")?;
        let authority = required_label(object, "authority")?;
        Ok(Self {
            source_root,
            allowed_paths,
            _purpose: purpose,
            _authority: authority,
        })
    }

    /// Resolve and recheck one target against this exact capability.
    pub fn assert_allowed(&self, path: &Path) -> Result<PathBuf> {
        let candidate = if path.is_absolute() {
            path.to_path_buf()
        } else {
            self.source_root.join(path)
        };
        if !candidate.starts_with(&self.source_root) {
            return Err(SourceMutationError::new(format!(
                "mutation target is outside source: {}",
                path.display()
            )));
        }
        reject_symlink_components(&self.source_root, &candidate)?;
        let resolved = resolve_with_missing(&candidate)?;
        let relative = resolved.strip_prefix(&self.source_root).map_err(|_| {
            SourceMutationError::new(format!(
                "mutation target is outside source: {}",
                path.display()
            ))
        })?;
        if !relative_path_is_allowed(relative, &self.allowed_paths) {
            return Err(SourceMutationError::new(format!(
                "mutation target is outside allowed_paths: {}",
                relative.display()
            )));
        }
        Ok(resolved)
    }

    /// Revalidate and write one UTF-8 source file without following a path symlink.
    pub fn write_text(&self, path: &Path, text: &str) -> Result<()> {
        let resolved = self.assert_allowed(path)?;
        let relative = resolved.strip_prefix(&self.source_root).map_err(|_| {
            SourceMutationError::new(format!(
                "mutation target is outside source: {}",
                path.display()
            ))
        })?;
        let components = relative.components().collect::<Vec<_>>();
        let Some(Component::Normal(name)) = components.last() else {
            return Err(SourceMutationError::new(format!(
                "mutation target must name a source file: {}",
                path.display()
            )));
        };
        let mut directory = open_root_nofollow(&self.source_root).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot open mutation source root {}: {error}",
                self.source_root.display()
            ))
        })?;
        for component in &components[..components.len() - 1] {
            let Component::Normal(component) = component else {
                return Err(SourceMutationError::new(format!(
                    "unsafe mutation target: {}",
                    path.display()
                )));
            };
            directory = directory.open_dir_nofollow(component).map_err(|error| {
                SourceMutationError::new(format!(
                    "cannot open mutation parent for {}: {error}",
                    path.display()
                ))
            })?;
        }
        let mut options = cap_std::fs::OpenOptions::new();
        options.write(true).truncate(true);
        options.follow(FollowSymlinks::No);
        let mut file = directory.open_with(name, &options).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot open mutation target {}: {error}",
                path.display()
            ))
        })?;
        file.write_all(text.as_bytes()).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot write mutation target {}: {error}",
                path.display()
            ))
        })
    }
}

fn relative_path_is_allowed(relative: &Path, allowed_paths: &[PathBuf]) -> bool {
    allowed_paths.iter().any(|allowed| {
        allowed.as_os_str().is_empty() || relative == allowed || relative.starts_with(allowed)
    })
}

fn reject_unknown_fields(object: &Map<String, Value>) -> Result<()> {
    const FIELDS: [&str; 3] = ["allowed_paths", "purpose", "authority"];
    let unknown = object
        .keys()
        .filter(|key| !FIELDS.contains(&key.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    if unknown.is_empty() {
        Ok(())
    } else {
        Err(SourceMutationError::new(
            "mutation capability fields must be allowed_paths, purpose, authority",
        ))
    }
}

fn parse_allowed_paths(object: &Map<String, Value>, source_root: &Path) -> Result<Vec<PathBuf>> {
    let allowed = object
        .get("allowed_paths")
        .and_then(Value::as_array)
        .filter(|items| !items.is_empty())
        .ok_or_else(|| SourceMutationError::new("mutation capability allowed_paths is required"))?;
    let mut normalized = BTreeSet::new();
    for item in allowed {
        let item = item
            .as_str()
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| SourceMutationError::new("mutation capability path must be text"))?;
        if item.starts_with('/')
            || Path::new(item).is_absolute()
            || Path::new(item)
                .components()
                .any(|component| matches!(component, Component::Prefix(_) | Component::RootDir))
            || cfg!(windows) && item.contains('\\')
        {
            return Err(SourceMutationError::new(format!(
                "unsafe mutation capability path: {item}"
            )));
        }
        let mut parts = Vec::new();
        for part in item.split('/') {
            match part {
                "" | "." => {}
                ".." => {
                    return Err(SourceMutationError::new(format!(
                        "unsafe mutation capability path: {item}"
                    )))
                }
                part => parts.push(part),
            }
        }
        let relative = PathBuf::from(parts.join("/"));
        let lexical = source_root.join(&relative);
        if !candidate_resolves_under(source_root, &lexical)? {
            return Err(SourceMutationError::new(format!(
                "mutation capability escapes source: {item}"
            )));
        }
        normalized.insert(relative);
    }
    Ok(normalized.into_iter().collect())
}

fn required_label(object: &Map<String, Value>, field: &str) -> Result<String> {
    object
        .get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(str::to_string)
        .ok_or_else(|| SourceMutationError::new(format!("mutation capability {field} is required")))
}

fn candidate_resolves_under(root: &Path, path: &Path) -> Result<bool> {
    let resolved = resolve_with_missing(path)?;
    Ok(resolved == root || resolved.starts_with(root))
}

fn reject_symlink_components(root: &Path, path: &Path) -> Result<()> {
    let relative = path.strip_prefix(root).map_err(|_| {
        SourceMutationError::new(format!(
            "mutation target is outside source: {}",
            path.display()
        ))
    })?;
    let mut cursor = root.to_path_buf();
    for component in relative.components() {
        let Component::Normal(part) = component else {
            return Err(SourceMutationError::new(format!(
                "unsafe mutation target: {}",
                path.display()
            )));
        };
        cursor.push(part);
        match fs::symlink_metadata(&cursor) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(SourceMutationError::new(format!(
                    "mutation target contains symlink component: {}",
                    cursor.display()
                )))
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(SourceMutationError::new(format!(
                    "cannot inspect mutation target {}: {error}",
                    cursor.display()
                )))
            }
        }
    }
    Ok(())
}

fn resolve_with_missing(path: &Path) -> Result<PathBuf> {
    let mut cursor = path.to_path_buf();
    let mut missing = Vec::new();
    loop {
        match fs::canonicalize(&cursor) {
            Ok(mut resolved) => {
                for component in missing.iter().rev() {
                    resolved.push(component);
                }
                return Ok(resolved);
            }
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                ) =>
            {
                let name = cursor.file_name().ok_or_else(|| {
                    SourceMutationError::new(format!(
                        "cannot resolve mutation path: {}",
                        path.display()
                    ))
                })?;
                missing.push(name.to_os_string());
                cursor = cursor
                    .parent()
                    .ok_or_else(|| {
                        SourceMutationError::new(format!(
                            "cannot resolve mutation path: {}",
                            path.display()
                        ))
                    })?
                    .to_path_buf();
            }
            Err(error) => {
                return Err(SourceMutationError::new(format!(
                    "cannot resolve mutation path {}: {error}",
                    path.display()
                )))
            }
        }
    }
}

fn open_root_nofollow(root: &Path) -> io::Result<cap_std::fs::Dir> {
    let mut components = root.components();
    #[cfg(windows)]
    let mut directory = {
        let prefix = match components.next() {
            Some(Component::Prefix(prefix)) => prefix,
            _ => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "absolute source root requires a volume prefix",
                ))
            }
        };
        if !matches!(components.next(), Some(Component::RootDir)) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "absolute source root requires a volume root",
            ));
        }
        let mut volume_root = PathBuf::from(prefix.as_os_str());
        volume_root.push(std::path::MAIN_SEPARATOR.to_string());
        cap_std::fs::Dir::open_ambient_dir(&volume_root, cap_std::ambient_authority())?
    };
    #[cfg(not(windows))]
    let mut directory = {
        if !matches!(components.next(), Some(Component::RootDir)) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "absolute source root requires a root component",
            ));
        }
        cap_std::fs::Dir::open_ambient_dir(Path::new("/"), cap_std::ambient_authority())?
    };
    for component in components {
        match component {
            Component::Normal(name) => {
                directory = directory.open_dir_nofollow(name)?;
            }
            Component::RootDir => {}
            Component::CurDir | Component::ParentDir | Component::Prefix(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "source root path is not canonical",
                ))
            }
        }
    }
    Ok(directory)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    #[test]
    fn allowed_path_comparison_keeps_invalid_utf8_component_identity() {
        use std::os::unix::ffi::OsStringExt;

        let allowed = PathBuf::from("docs").join("�");
        let valid_target = allowed.join("guide.md");
        let invalid_target = PathBuf::from("docs")
            .join(std::ffi::OsString::from_vec(vec![0xff]))
            .join("guide.md");

        assert!(relative_path_is_allowed(
            &valid_target,
            std::slice::from_ref(&allowed)
        ));
        assert!(!relative_path_is_allowed(
            &invalid_target,
            std::slice::from_ref(&allowed)
        ));
    }
}
