//! Read one canonical code-template source file without writing its source tree.

use std::fmt;
use std::fs;
use std::io;
use std::path::{Component, Path, PathBuf};

#[derive(Debug)]
pub(crate) enum CodeTemplateError {
    Escape(String),
    NotFound(String),
    Read { path: PathBuf, source: io::Error },
}

impl fmt::Display for CodeTemplateError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Escape(name) => write!(formatter, "code template escapes owner: {name}"),
            Self::NotFound(name) => write!(formatter, "code template not found: {name}"),
            Self::Read { path, source } => {
                write!(formatter, "read code template {}: {source}", path.display())
            }
        }
    }
}

impl std::error::Error for CodeTemplateError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Read { source, .. } => Some(source),
            _ => None,
        }
    }
}

fn normalize(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() {
                    normalized.push(component.as_os_str());
                }
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

fn canonicalize_allow_missing(path: &Path) -> io::Result<PathBuf> {
    let mut missing = Vec::new();
    let mut cursor = path;
    loop {
        match fs::canonicalize(cursor) {
            Ok(mut resolved) => {
                for component in missing.iter().rev() {
                    resolved.push(component);
                }
                return Ok(resolved);
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                if let Ok(metadata) = fs::symlink_metadata(cursor) {
                    if metadata.file_type().is_symlink() {
                        let link = fs::read_link(cursor)?;
                        let mut target = if link.is_absolute() {
                            link
                        } else {
                            cursor.parent().unwrap_or(Path::new(".")).join(link)
                        };
                        for component in missing.iter().rev() {
                            target.push(component);
                        }
                        return canonicalize_allow_missing(&target);
                    }
                }
                let Some(name) = cursor.file_name() else {
                    return Err(error);
                };
                missing.push(name.to_os_string());
                cursor = cursor.parent().ok_or(error)?;
            }
            Err(error) => return Err(error),
        }
    }
}

/// Render a package-owned code template from an already-resolved source root.
///
/// The caller supplies the canonical source root capability once. This helper
/// has no working-directory lookup, command entrypoint, or compatibility layer.
pub(crate) fn render_code_template(
    canonical_source_root: &Path,
    template_name: &str,
) -> Result<String, CodeTemplateError> {
    let source_metadata =
        fs::symlink_metadata(canonical_source_root).map_err(|source| CodeTemplateError::Read {
            path: canonical_source_root.to_path_buf(),
            source,
        })?;
    if source_metadata.file_type().is_symlink() || !source_metadata.is_dir() {
        return Err(CodeTemplateError::Read {
            path: canonical_source_root.to_path_buf(),
            source: io::Error::new(
                io::ErrorKind::InvalidInput,
                "canonical source root required",
            ),
        });
    }
    let source_root = canonical_source_root.to_path_buf();
    let template_root = fs::canonicalize(source_root.join("templates/code")).map_err(|source| {
        if source.kind() == io::ErrorKind::NotFound {
            CodeTemplateError::NotFound(template_name.to_owned())
        } else {
            CodeTemplateError::Read {
                path: source_root.join("templates/code"),
                source,
            }
        }
    })?;
    let supplied = Path::new(template_name);
    let joined = if supplied.is_absolute() {
        supplied.to_path_buf()
    } else {
        template_root.join(supplied)
    };
    let lexical = normalize(&joined);
    if !lexical.starts_with(&template_root) {
        return Err(CodeTemplateError::Escape(template_name.to_owned()));
    }
    let resolved =
        canonicalize_allow_missing(&lexical).map_err(|source| CodeTemplateError::Read {
            path: lexical.clone(),
            source,
        })?;
    if !resolved.starts_with(&template_root) {
        return Err(CodeTemplateError::Escape(template_name.to_owned()));
    }
    let metadata = fs::metadata(&resolved).map_err(|source| {
        if source.kind() == io::ErrorKind::NotFound {
            CodeTemplateError::NotFound(template_name.to_owned())
        } else {
            CodeTemplateError::Read {
                path: resolved.clone(),
                source,
            }
        }
    })?;
    if !metadata.is_file() {
        return Err(CodeTemplateError::NotFound(template_name.to_owned()));
    }
    fs::read_to_string(&resolved).map_err(|source| CodeTemplateError::Read {
        path: resolved,
        source,
    })
}
