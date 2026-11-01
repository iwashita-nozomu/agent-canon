// @dependency-start
// contract implementation
// responsibility Resolves paths using non-strict filesystem semantics, including symbolic links with missing targets.
// downstream implementation source_dependency_graph.rs delegates Python-compatible path-component matching
// downstream implementation semantic_responsibility.rs delegates its checked references to this shared resolver
// downstream implementation lean_proof_env.rs resolves selected package and Lean source paths
// downstream implementation token_footprints.rs expands Python-compatible session glob patterns
// downstream implementation codex_runtime_summary.rs expands legacy session glob patterns
// @dependency-end

use std::collections::{BTreeMap, HashSet};
use std::env;
use std::ffi::OsString;
use std::fs;
use std::path::{Component, Path, PathBuf};

/// Expand one path pattern with Python `glob.glob(..., recursive=True)` traversal semantics.
///
/// Results retain traversal order. Callers that expose a stable result order apply their own
/// path normalization and sorting after expansion.
pub fn python_glob_paths(pattern: &str) -> Result<Vec<PathBuf>, String> {
    let (base, components, directory_only) = split_glob_pattern(pattern)?;
    Ok(glob_paths(&base, &components, directory_only))
}

/// Match one filename or component using Python's case-sensitive fnmatch rules.
pub fn python_fnmatch_case(value: &str, pattern: &str) -> bool {
    fnmatch_chars(
        &value.chars().collect::<Vec<_>>(),
        &pattern.chars().collect::<Vec<_>>(),
        0,
        0,
        &mut BTreeMap::new(),
    )
}

fn class_match(pattern: &[char], start: usize, value: Option<char>) -> Option<(usize, bool)> {
    let mut content_start = start + 1;
    let negated = pattern.get(content_start) == Some(&'!');
    if negated {
        content_start += 1;
    }
    let leading_close = pattern.get(content_start) == Some(&']');
    if leading_close {
        content_start += 1;
    }
    let closing = (content_start..pattern.len()).find(|index| pattern[*index] == ']')?;
    let Some(value) = value else {
        return Some((closing, false));
    };
    let mut index = content_start;
    let mut matched = leading_close && value == ']';
    while index < closing {
        let low = pattern[index];
        if index + 2 < closing && pattern[index + 1] == '-' {
            let high = pattern[index + 2];
            matched |= low <= value && value <= high;
            index += 3;
        } else {
            matched |= value == low;
            index += 1;
        }
    }
    Some((closing, if negated { !matched } else { matched }))
}

fn fnmatch_chars(
    value: &[char],
    pattern: &[char],
    value_index: usize,
    pattern_index: usize,
    memo: &mut BTreeMap<(usize, usize), bool>,
) -> bool {
    if let Some(result) = memo.get(&(value_index, pattern_index)) {
        return *result;
    }
    let result = if pattern_index == pattern.len() {
        value_index == value.len()
    } else {
        match pattern[pattern_index] {
            '*' => {
                let mut next = pattern_index + 1;
                while next < pattern.len() && pattern[next] == '*' {
                    next += 1;
                }
                fnmatch_chars(value, pattern, value_index, next, memo)
                    || (value_index < value.len()
                        && fnmatch_chars(value, pattern, value_index + 1, pattern_index, memo))
            }
            '?' => {
                value_index < value.len()
                    && fnmatch_chars(value, pattern, value_index + 1, pattern_index + 1, memo)
            }
            '[' => match class_match(pattern, pattern_index, value.get(value_index).copied()) {
                Some((end, matched)) => {
                    matched && fnmatch_chars(value, pattern, value_index + 1, end + 1, memo)
                }
                None => {
                    value.get(value_index) == Some(&'[')
                        && fnmatch_chars(value, pattern, value_index + 1, pattern_index + 1, memo)
                }
            },
            character => {
                value_index < value.len()
                    && character == value[value_index]
                    && fnmatch_chars(value, pattern, value_index + 1, pattern_index + 1, memo)
            }
        }
    };
    memo.insert((value_index, pattern_index), result);
    result
}

fn split_glob_pattern(pattern: &str) -> Result<(PathBuf, Vec<String>, bool), String> {
    let path = Path::new(pattern);
    let components = path.components().collect::<Vec<_>>();
    let prefix = components.iter().find_map(|component| match component {
        Component::Prefix(prefix) => Some(prefix.as_os_str()),
        _ => None,
    });
    let mut base = if path.is_absolute() {
        PathBuf::new()
    } else if let Some(prefix) = prefix {
        PathBuf::from(prefix)
    } else {
        env::current_dir().map_err(|error| format!("current directory: {error}"))?
    };
    let mut patterns = Vec::new();
    for component in components {
        match component {
            Component::Prefix(prefix) => {
                if path.is_absolute() {
                    base.push(prefix.as_os_str());
                }
            }
            Component::RootDir => base.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => patterns.push("..".to_owned()),
            Component::Normal(value) => patterns.push(
                value
                    .to_str()
                    .ok_or_else(|| "glob pattern contains a non-UTF-8 path component".to_owned())?
                    .to_owned(),
            ),
        }
    }
    let directory_only =
        pattern.ends_with(std::path::MAIN_SEPARATOR) || cfg!(windows) && pattern.ends_with('/');
    Ok((base, patterns, directory_only))
}

fn glob_paths(base: &Path, components: &[String], directory_only: bool) -> Vec<PathBuf> {
    let mut matches = Vec::new();
    let mut pending = vec![(base.to_path_buf(), 0_usize)];
    let mut visited = HashSet::new();

    while let Some((current, index)) = pending.pop() {
        if index == components.len() {
            if !directory_only || fs::metadata(&current).is_ok_and(|metadata| metadata.is_dir()) {
                matches.push(current);
            }
            continue;
        }

        let pattern = &components[index];
        if pattern == "**" {
            // Canonical traversal states stop directory-symlink cycles without a depth cap.
            let key = resolve_non_strict(&current).unwrap_or_else(|_| current.clone());
            if !visited.insert((key, index)) {
                continue;
            }
            pending.push((current.clone(), index + 1));
            let Ok(entries) = fs::read_dir(&current) else {
                continue;
            };
            for entry in entries.flatten() {
                let path = entry.path();
                let name = entry.file_name();
                let Some(name) = name.to_str() else {
                    continue;
                };
                if name.starts_with('.') {
                    continue;
                }
                if index + 1 == components.len() {
                    pending.push((path.clone(), index + 1));
                }
                if fs::metadata(&path).is_ok_and(|metadata| metadata.is_dir()) {
                    pending.push((path, index));
                }
            }
            continue;
        }

        let has_glob_magic = |value: &str| {
            value
                .chars()
                .any(|character| matches!(character, '*' | '?' | '['))
        };
        if !has_glob_magic(pattern) {
            let mut path = current;
            let mut next_index = index;
            while let Some(component) = components.get(next_index) {
                if component == "**" || has_glob_magic(component) {
                    break;
                }
                path.push(component);
                next_index += 1;
            }
            pending.push((path, next_index));
            continue;
        }

        let Ok(entries) = fs::read_dir(&current) else {
            continue;
        };
        for entry in entries.flatten() {
            let name = entry.file_name();
            let Some(name_text) = name.to_str() else {
                continue;
            };
            if name_text.starts_with('.') && !pattern.starts_with('.') {
                continue;
            }
            if python_fnmatch_case(name_text, pattern) {
                pending.push((entry.path(), index + 1));
            }
        }
    }

    matches
}

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
