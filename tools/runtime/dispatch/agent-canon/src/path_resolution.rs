// @dependency-start
// contract implementation
// responsibility Resolves paths using non-strict filesystem semantics, including symbolic links with missing targets.
// downstream implementation semantic_responsibility.rs delegates its checked references to this shared resolver
// downstream implementation lean_proof_env.rs resolves selected package and Lean source paths
// downstream implementation hook_retirement.rs resolves the read-only audit root
// @dependency-end

use std::collections::HashSet;
use std::env;
use std::ffi::OsString;
use std::fs;
use std::path::{Component, Path, PathBuf};

fn permits_lexical_suffix(error: &std::io::Error) -> bool {
    if error.kind() == std::io::ErrorKind::NotFound {
        return true;
    }
    // CPython's non-strict Windows resolver keeps invalid names lexical.
    // This read-only resolution does not authorize opening the resulting path.
    #[cfg(windows)]
    if error.raw_os_error() == Some(123) {
        return true;
    }
    false
}

#[derive(Clone)]
enum ResolutionComponent {
    RootDir(OsString),
    CurDir,
    ParentDir,
    Normal(OsString),
    Prefix(OsString),
}

struct ResolutionFrame {
    components: Vec<ResolutionComponent>,
    next: usize,
    resolving_symlink: Option<PathBuf>,
}

impl ResolutionFrame {
    fn new(path: &Path, resolving_symlink: Option<PathBuf>) -> Self {
        let components = path
            .components()
            .map(|component| match component {
                root @ Component::RootDir => {
                    ResolutionComponent::RootDir(root.as_os_str().to_os_string())
                }
                Component::CurDir => ResolutionComponent::CurDir,
                Component::ParentDir => ResolutionComponent::ParentDir,
                Component::Normal(name) => ResolutionComponent::Normal(name.to_os_string()),
                Component::Prefix(prefix) => {
                    ResolutionComponent::Prefix(prefix.as_os_str().to_os_string())
                }
            })
            .collect();
        Self {
            components,
            next: 0,
            resolving_symlink,
        }
    }
}

/// Resolve a path while permitting missing suffix components.
///
/// Existing components are canonicalized and symbolic-link targets are followed.
/// Missing components remain lexical path components, matching non-strict path resolution.
pub fn resolve_non_strict(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|error| format!("current directory: {error}"))?
            .join(path)
    };
    let mut resolved = PathBuf::new();
    let mut frames = vec![ResolutionFrame::new(&absolute, None)];
    let mut active_symlinks = HashSet::new();

    while !frames.is_empty() {
        let frame_finished = frames
            .last()
            .is_some_and(|frame| frame.next == frame.components.len());
        if frame_finished {
            let frame = frames.pop().expect("finished frame exists");
            if let Some(symlink) = frame.resolving_symlink {
                active_symlinks.remove(&symlink);
            }
            continue;
        }
        let component = {
            let frame = frames.last_mut().expect("active frame exists");
            let component = frame.components[frame.next].clone();
            frame.next += 1;
            component
        };
        match component {
            ResolutionComponent::RootDir(root) => resolved.push(root),
            ResolutionComponent::CurDir => {}
            ResolutionComponent::ParentDir => {
                if !resolved.pop() && !resolved.has_root() {
                    resolved.push("..");
                }
            }
            ResolutionComponent::Normal(name) => {
                let candidate = resolved.join(&name);
                match fs::symlink_metadata(&candidate) {
                    Ok(metadata) if metadata.file_type().is_symlink() => {
                        if !active_symlinks.insert(candidate.clone()) {
                            return Err(format!("symbolic link loop at {}", candidate.display()));
                        }
                        let target = fs::read_link(&candidate).map_err(|error| {
                            format!("read symbolic link {}: {error}", candidate.display())
                        })?;
                        let target = if target.is_absolute() {
                            target
                        } else {
                            resolved.join(target)
                        };
                        frames.push(ResolutionFrame::new(&target, Some(candidate)));
                    }
                    Ok(_) => {
                        resolved = fs::canonicalize(&candidate).map_err(|error| {
                            format!("canonicalize {}: {error}", candidate.display())
                        })?;
                    }
                    Err(error) if permits_lexical_suffix(&error) => {
                        resolved.push(name);
                    }
                    Err(error) => {
                        return Err(format!("inspect {}: {error}", candidate.display()));
                    }
                }
            }
            ResolutionComponent::Prefix(prefix) => resolved.push(prefix),
        }
    }
    Ok(resolved)
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;

    #[test]
    fn invalid_windows_names_remain_lexical_without_creating_files() {
        let root = fs::canonicalize(env::temp_dir()).expect("temporary root resolves");
        for name in ["\u{1c}", "invalid<name"] {
            let path = root.join(name);
            assert_eq!(
                fs::symlink_metadata(&path)
                    .expect_err("Windows cannot address this name")
                    .raw_os_error(),
                Some(123)
            );
            assert_eq!(resolve_non_strict(&path).expect("lexical suffix"), path);
        }
    }
}
