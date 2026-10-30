use std::fs;
use std::path::Path;

/// Returns true when any POSIX path component has `legacy` in its stem.
///
/// This deliberately preserves the source policy's lexical normalization:
/// backslashes become separators and one leading `./` is removed. It does not
/// resolve `..`, collapse repeated separators, or inspect filesystem authority.
pub fn has_retired_legacy_path_token(path: &str) -> bool {
    let normalized = normalize_lexically(path);
    normalized.split('/').any(|part| {
        if part.is_empty() || part == "." {
            return false;
        }
        let stem = Path::new(part)
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or(part);
        stem.to_lowercase().contains("legacy")
    })
}

/// Returns true when a path belongs lexically to the AgentCanon tools tree.
pub fn is_tool_surface_path(path: &str) -> bool {
    let normalized = normalize_lexically(path);
    normalized == "tools" || normalized.starts_with("tools/")
}

/// Returns true for a retired legacy path under `tools/`.
pub fn is_retired_legacy_tool_path(path: &str) -> bool {
    is_tool_surface_path(path) && has_retired_legacy_path_token(path)
}

/// Lists existing retired legacy paths under `root/tools`, sorted and unique.
pub fn iter_retired_legacy_tool_paths(root: &Path) -> Vec<String> {
    let tools_root = root.join("tools");
    if !tools_root.exists() {
        return Vec::new();
    }

    let mut retired = Vec::new();
    walk_tools(root, &tools_root, &mut retired);
    retired.sort();
    retired.dedup();
    retired
}

/// Returns the stable finding detail for one retired legacy tool path.
pub fn retired_legacy_tool_detail(path: &str) -> &'static str {
    if path == "tools/legacy" {
        "legacy-directory-present"
    } else {
        "legacy-tools-are-retired"
    }
}

fn normalize_lexically(path: &str) -> String {
    let replaced = path.replace('\\', "/");
    replaced
        .strip_prefix("./")
        .unwrap_or(&replaced)
        .to_owned()
}

fn walk_tools(root: &Path, current: &Path, retired: &mut Vec<String>) {
    let relative_dir = relative_posix(root, current);
    if relative_dir != "tools" && is_retired_legacy_tool_path(&relative_dir) {
        retired.push(relative_dir);
        return;
    }

    let Ok(entries) = fs::read_dir(current) else {
        return;
    };
    let mut entries: Vec<_> = entries.flatten().collect();
    entries.sort_by_key(|entry| entry.file_name());
    for entry in entries {
        let path = entry.path();
        let relative = relative_posix(root, &path);
        if entry.file_type().is_ok_and(|kind| kind.is_dir()) {
            walk_tools(root, &path, retired);
        } else if is_retired_legacy_tool_path(&relative) {
            retired.push(relative);
        }
    }
}

fn relative_posix(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}
