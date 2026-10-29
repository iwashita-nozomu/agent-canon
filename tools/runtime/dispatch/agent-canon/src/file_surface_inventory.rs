// @dependency-start
// contract implementation
// responsibility Builds machine-readable file-surface inventories for repo review.
// upstream implementation ../../../../analysis/code/file_surface_inventory.py frozen migration oracle
// downstream implementation ../../../../repository/github/review_backlog_scan.sh includes inventory reports
// downstream test ../../../../../../tests/agent_tools/test_file_surface_inventory.py exercises the inventory CLI
// @dependency-end

use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::env;
use std::ffi::OsStr;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

const CHECKABLE_SUFFIXES: &[&str] = &[
    ".bash", ".cfg", ".css", ".h", ".hpp", ".html", ".c", ".cc", ".cpp", ".json", ".md", ".py",
    ".rst", ".sh", ".toml", ".txt", ".yaml", ".yml", ".zsh",
];
const EXCLUDED_PARTS: &[&str] = &[
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "reports",
];

#[derive(Debug, Clone, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    mode: String,
    json_out: Option<PathBuf>,
    markdown_out: Option<PathBuf>,
    max_markdown_entries: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FileEntry {
    scope: String,
    path: String,
    kind: String,
    suffix: String,
    checkable: bool,
    git_mode: String,
    symlink_target: String,
    real_source_path: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ScopeInventory {
    name: String,
    root: String,
    files: usize,
    checkable_files: usize,
    by_kind: BTreeMap<String, usize>,
    entries: Vec<FileEntry>,
}

pub fn run(args: &[String]) -> i32 {
    let parsed = match Args::parse(args) {
        Ok(Some(args)) => args,
        Ok(None) => {
            println!("usage: agent-canon file-surface-inventory --root <path> [--root-only|--agentcanon-only] [--json-out <path>] [--markdown-out <path>] [--max-markdown-entries <integer>]");
            return 0;
        }
        Err(message) => {
            eprintln!("agent-canon file-surface-inventory: {message}");
            eprintln!("usage: agent-canon file-surface-inventory --root <path> [--root-only|--agentcanon-only] [--json-out <path>] [--markdown-out <path>] [--max-markdown-entries <integer>]");
            return 2;
        }
    };
    let root = resolve_non_strict(&parsed.root);
    let scope_name = if parsed.mode == "agentcanon-only" {
        "agentcanon"
    } else {
        "root"
    };
    let scopes = match inventory_scope(scope_name, &root) {
        Ok(scope) => vec![scope],
        Err(message) => {
            println!("FILE_SURFACE_INVENTORY_ERROR={message}");
            println!("FILE_SURFACE_INVENTORY=fail");
            return 1;
        }
    };
    let json_text = render_json(&parsed.mode, &root, &scopes);
    let markdown_text = render_markdown(&parsed.mode, &root, &scopes, parsed.max_markdown_entries);
    if let Some(path) = &parsed.json_out {
        if let Err(error) = write_optional(path, &json_text) {
            eprintln!(
                "agent-canon file-surface-inventory: write {}: {error}",
                path.display()
            );
            return 1;
        }
    }
    if let Some(path) = &parsed.markdown_out {
        if let Err(error) = write_optional(path, &markdown_text) {
            eprintln!(
                "agent-canon file-surface-inventory: write {}: {error}",
                path.display()
            );
            return 1;
        }
    }
    let files: usize = scopes.iter().map(|scope| scope.files).sum();
    let checkable: usize = scopes.iter().map(|scope| scope.checkable_files).sum();
    println!("FILE_SURFACE_INVENTORY=pass");
    println!("FILE_SURFACE_INVENTORY_MODE={}", parsed.mode);
    println!("FILE_SURFACE_INVENTORY_FILES={files}");
    println!("FILE_SURFACE_INVENTORY_CHECKABLE={checkable}");
    if let Some(path) = &parsed.json_out {
        println!("FILE_SURFACE_INVENTORY_JSON={}", path.to_string_lossy());
    }
    if let Some(path) = &parsed.markdown_out {
        println!("FILE_SURFACE_INVENTORY_MARKDOWN={}", path.to_string_lossy());
    }
    0
}

impl Args {
    fn parse(args: &[String]) -> Result<Option<Self>, String> {
        let mut root = PathBuf::from(".");
        let mut root_only = false;
        let mut agentcanon_only = false;
        let mut json_out = None;
        let mut markdown_out = None;
        let mut max_markdown_entries = 200;
        let mut unknown = None;
        let mut index = 0;
        while index < args.len() {
            let raw_option = args[index].as_str();
            let (option, inline_value) = raw_option
                .split_once('=')
                .map_or((raw_option, None), |(option, value)| (option, Some(value)));
            match option {
                "-h" | "--help" => {
                    if inline_value.is_some() {
                        return Err(format!("argument {option} does not take a value"));
                    }
                    return Ok(None);
                }
                "--root" | "--json-out" | "--markdown-out" | "--max-markdown-entries" => {
                    let (value, consumed) = match inline_value {
                        Some(value) => (value, 1),
                        None => (next_option_value(args, index, option)?, 2),
                    };
                    match option {
                        "--root" => root = PathBuf::from(value),
                        "--json-out" => json_out = Some(PathBuf::from(value)),
                        "--markdown-out" => markdown_out = Some(PathBuf::from(value)),
                        _ => {
                            max_markdown_entries = value
                                .parse()
                                .map_err(|_| format!("invalid integer value: '{value}'"))?
                        }
                    }
                    index += consumed;
                }
                "--root-only" => {
                    if inline_value.is_some() {
                        return Err("argument --root-only does not take a value".into());
                    }
                    if agentcanon_only {
                        return Err(
                            "--root-only and --agentcanon-only are mutually exclusive".into()
                        );
                    }
                    root_only = true;
                    index += 1;
                }
                "--agentcanon-only" => {
                    if inline_value.is_some() {
                        return Err("argument --agentcanon-only does not take a value".into());
                    }
                    if root_only {
                        return Err(
                            "--root-only and --agentcanon-only are mutually exclusive".into()
                        );
                    }
                    agentcanon_only = true;
                    index += 1;
                }
                _ => {
                    unknown.get_or_insert_with(|| raw_option.to_string());
                    index += 1;
                }
            }
        }
        if let Some(unknown) = unknown {
            return Err(format!("unrecognized argument: {unknown}"));
        }
        let mode = if agentcanon_only {
            "agentcanon-only"
        } else {
            "root-only"
        }
        .to_string();
        Ok(Some(Self {
            root,
            mode,
            json_out,
            markdown_out,
            max_markdown_entries,
        }))
    }
}

fn next_option_value<'a>(
    args: &'a [String],
    index: usize,
    option: &str,
) -> Result<&'a str, String> {
    let value = args
        .get(index + 1)
        .ok_or_else(|| format!("{option} requires a value"))?;
    if looks_like_option(value) {
        return Err(format!("{option} requires a value"));
    }
    Ok(value)
}

fn looks_like_option(value: &str) -> bool {
    value.starts_with('-') && value != "-" && !is_argparse_negative_number(value)
}

fn is_argparse_negative_number(value: &str) -> bool {
    let Some(number) = value.strip_prefix('-') else {
        return false;
    };
    if !number.is_empty() && number.chars().all(|character| character.is_ascii_digit()) {
        return true;
    }
    let Some((whole, fraction)) = number.split_once('.') else {
        return false;
    };
    !fraction.is_empty()
        && fraction.chars().all(|character| character.is_ascii_digit())
        && (whole.is_empty() || whole.chars().all(|character| character.is_ascii_digit()))
}

fn inventory_scope(name: &str, root: &Path) -> Result<ScopeInventory, String> {
    let rows = git_files(root)?;
    let mut entries = Vec::new();
    for (git_mode, path) in rows {
        let relative = PathBuf::from(&path);
        if relative
            .components()
            .any(|part| EXCLUDED_PARTS.contains(&part.as_os_str().to_string_lossy().as_ref()))
        {
            continue;
        }
        let full_path = root.join(&relative);
        if git_mode != "160000" && !surface_exists(&full_path) {
            continue;
        }
        entries.push(make_entry(name, root, &relative, &full_path, &git_mode));
    }
    let mut by_kind = BTreeMap::new();
    for entry in &entries {
        *by_kind.entry(entry.kind.clone()).or_insert(0) += 1;
    }
    let files = entries.len();
    let checkable_files = entries.iter().filter(|entry| entry.checkable).count();
    Ok(ScopeInventory {
        name: name.to_string(),
        root: posix_path(root),
        files,
        checkable_files,
        by_kind,
        entries,
    })
}

fn git_files(root: &Path) -> Result<Vec<(String, String)>, String> {
    let tracked = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["ls-files", "-z", "-s"])
        .output()
        .map_err(|error| {
            format!(
                "git ls-files failed for inventory scope: {} ({error})",
                root.display()
            )
        })?;
    if !tracked.status.success() {
        return Err(format!(
            "git ls-files failed for inventory scope: {}",
            root.display()
        ));
    }
    let mut rows = Vec::new();
    for record in tracked
        .stdout
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
    {
        let Some(tab) = record.iter().position(|byte| *byte == b'\t') else {
            continue;
        };
        let metadata = String::from_utf8_lossy(&record[..tab]);
        let mode = metadata
            .split_whitespace()
            .next()
            .unwrap_or_default()
            .to_string();
        rows.push((
            mode,
            String::from_utf8_lossy(&record[tab + 1..]).into_owned(),
        ));
    }
    let untracked = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["ls-files", "-z", "--others", "--exclude-standard"])
        .output();
    if let Ok(output) = untracked {
        if output.status.success() {
            for path in output
                .stdout
                .split(|byte| *byte == 0)
                .filter(|path| !path.is_empty())
            {
                let path_string = String::from_utf8_lossy(path).into_owned();
                let full = root.join(&path_string);
                if surface_exists(&full) {
                    rows.push((mode_for_untracked_path(&full), path_string));
                }
            }
        }
    }
    rows.sort_by(|left, right| left.1.cmp(&right.1));
    Ok(rows)
}

fn mode_for_untracked_path(path: &Path) -> String {
    if fs::symlink_metadata(path).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return "120000".into();
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if fs::metadata(path).is_ok_and(|metadata| metadata.permissions().mode() & 0o111 != 0) {
            return "100755".into();
        }
    }
    #[cfg(not(unix))]
    {
        if fs::metadata(path).is_ok_and(|metadata| is_executable(path, &metadata)) {
            return "100755".into();
        }
    }
    "100644".into()
}

#[cfg(not(unix))]
fn is_executable(_path: &Path, _metadata: &fs::Metadata) -> bool {
    // Python's Windows os.access(..., X_OK) treats an existing file as accessible.
    true
}

fn surface_exists(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok()
}

fn make_entry(scope: &str, root: &Path, relative: &Path, full: &Path, git_mode: &str) -> FileEntry {
    let symlink =
        fs::symlink_metadata(full).is_ok_and(|metadata| metadata.file_type().is_symlink());
    let symlink_target = if symlink {
        fs::read_link(full)
            .map(|target| target.to_string_lossy().into_owned())
            .unwrap_or_default()
    } else {
        String::new()
    };
    let kind = if git_mode == "160000" {
        "gitlink"
    } else if scope == "root" && relative == Path::new("tools") && symlink {
        "agentcanon_tool_view"
    } else if scope == "agentcanon"
        && relative
            .components()
            .next()
            .is_some_and(|part| part.as_os_str() == OsStr::new("tools"))
    {
        "agentcanon_tool_source"
    } else if symlink {
        "symlink_view"
    } else if scope == "agentcanon" {
        "canon_source"
    } else {
        "product_file"
    };
    let suffix = relative
        .extension()
        .map(|extension| format!(".{}", extension.to_string_lossy()))
        .unwrap_or_default();
    let real_source_path = if surface_exists(full) {
        relative_real_path(root, full)
    } else {
        String::new()
    };
    FileEntry {
        scope: scope.to_string(),
        path: posix_path(relative),
        kind: kind.to_string(),
        checkable: CHECKABLE_SUFFIXES.contains(&suffix.as_str()) && git_mode != "160000",
        suffix,
        git_mode: git_mode.to_string(),
        symlink_target,
        real_source_path,
    }
}

fn relative_real_path(root: &Path, path: &Path) -> String {
    let resolved_root = resolve_non_strict(root);
    let resolved_path = resolve_non_strict(path);
    match resolved_path.strip_prefix(&resolved_root) {
        Ok(relative) => posix_path(relative),
        Err(_) => posix_path(&resolved_path),
    }
}

fn posix_path(path: &Path) -> String {
    let value = path.to_string_lossy();
    #[cfg(windows)]
    {
        value.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        value.into_owned()
    }
}

fn resolve_non_strict(path: &Path) -> PathBuf {
    resolve_non_strict_depth(path, 0)
}

fn resolve_non_strict_depth(path: &Path, depth: usize) -> PathBuf {
    if depth < 40
        && fs::symlink_metadata(path).is_ok_and(|metadata| metadata.file_type().is_symlink())
    {
        if let Ok(target) = fs::read_link(path) {
            let target = if target.is_absolute() {
                target
            } else {
                path.parent().unwrap_or_else(|| Path::new(".")).join(target)
            };
            return resolve_non_strict_depth(&target, depth + 1);
        }
    }
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir().unwrap_or_default().join(path)
    };
    if let Ok(canonical) = fs::canonicalize(&absolute) {
        return canonical;
    }
    let mut cursor = absolute.clone();
    let mut tail = Vec::new();
    while !cursor.exists() {
        let Some(name) = cursor.file_name() else {
            break;
        };
        tail.push(name.to_os_string());
        if !cursor.pop() {
            break;
        }
    }
    let base = fs::canonicalize(&cursor).unwrap_or(cursor);
    let mut resolved = base;
    for component in tail.iter().rev() {
        resolved.push(component);
    }
    normalize_path(resolved)
}

fn normalize_path(path: PathBuf) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

fn render_json(mode: &str, root: &Path, scopes: &[ScopeInventory]) -> String {
    let files: usize = scopes.iter().map(|scope| scope.files).sum();
    let checkable: usize = scopes.iter().map(|scope| scope.checkable_files).sum();
    let scopes_json: Vec<Value> = scopes.iter().map(|scope| json!({
        "name": scope.name, "root": scope.root, "files": scope.files,
        "checkable_files": scope.checkable_files, "by_kind": scope.by_kind,
        "entries": scope.entries.iter().map(|entry| json!({
            "scope": entry.scope, "path": entry.path, "kind": entry.kind, "suffix": entry.suffix,
            "checkable": entry.checkable, "git_mode": entry.git_mode,
            "symlink_target": entry.symlink_target, "real_source_path": entry.real_source_path
        })).collect::<Vec<_>>()
    })).collect();
    serde_json::to_string_pretty(&json!({ "status": "pass", "mode": mode, "root": posix_path(root), "files": files, "checkable_files": checkable, "scopes": scopes_json })).unwrap_or_else(|_| "{}".into())
}

fn markdown_rows(scopes: &[ScopeInventory], limit: i64) -> Vec<String> {
    let mut rows = Vec::new();
    let mut remaining = limit.max(0) as usize;
    for scope in scopes {
        for entry in &scope.entries {
            if remaining == 0 {
                return rows;
            }
            rows.push(format!(
                "| {} | {} | {} | {} | {} |",
                entry.scope,
                entry.path,
                entry.kind,
                if entry.checkable { "yes" } else { "no" },
                entry.real_source_path
            ));
            remaining -= 1;
        }
    }
    rows
}

fn render_markdown(mode: &str, root: &Path, scopes: &[ScopeInventory], limit: i64) -> String {
    let files: usize = scopes.iter().map(|scope| scope.files).sum();
    let checkable: usize = scopes.iter().map(|scope| scope.checkable_files).sum();
    let mut lines = vec![
        "# File Surface Inventory".to_string(), "".into(), "<!--".into(), "@dependency-start".into(),
        "responsibility Records file surface inventory for review.".into(),
        "upstream implementation ../../../../tools/runtime/dispatch/agent-canon/src/file_surface_inventory.rs generates this report".into(),
        "@dependency-end".into(), "-->".into(), "".into(), format!("- mode: {mode}"),
        format!("- root: {}", posix_path(root)), format!("- files: {files}"), format!("- checkable_files: {checkable}"),
        "".into(), "## Scope Summary".into(), "".into(), "| Scope | Root | Files | Checkable | By Kind |".into(),
        "| ----- | ---- | ----- | --------- | ------- |".into(),
    ];
    for scope in scopes {
        let by_kind = scope
            .by_kind
            .iter()
            .map(|(key, value)| format!("{key}={value}"))
            .collect::<Vec<_>>()
            .join(", ");
        lines.push(format!(
            "| {} | {} | {} | {} | {} |",
            scope.name, scope.root, scope.files, scope.checkable_files, by_kind
        ));
    }
    lines.extend([
        "".into(),
        "## File Rows".into(),
        "".into(),
        "| Scope | Path | Kind | Checkable | Real Source Path |".into(),
        "| ----- | ---- | ---- | --------- | ---------------- |".into(),
    ]);
    lines.extend(markdown_rows(scopes, limit));
    format!("{}\n", lines.join("\n").trim_end())
}

fn write_optional(path: &Path, text: &str) -> std::io::Result<()> {
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, text)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn scratch() -> PathBuf {
        let id = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = env::temp_dir().join(format!("file-surface-inventory-{id}"));
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn git(root: &Path, args: &[&str]) {
        assert!(Command::new("git")
            .arg("-C")
            .arg(root)
            .args(args)
            .status()
            .unwrap()
            .success());
    }

    #[test]
    fn parses_modes_and_rejects_mutually_exclusive_scope() {
        let args = vec![
            "--agentcanon-only".into(),
            "--root".into(),
            "/tmp/source".into(),
            "--max-markdown-entries".into(),
            "-3".into(),
        ];
        let parsed = Args::parse(&args).unwrap().unwrap();
        assert_eq!(parsed.mode, "agentcanon-only");
        assert_eq!(parsed.max_markdown_entries, -3);
        assert!(Args::parse(&["--root-only".into(), "--agentcanon-only".into()]).is_err());
    }

    #[test]
    fn parses_equals_style_values_and_preserves_embedded_equals() {
        let args = vec![
            "--root=/tmp/repo=fixture".into(),
            "--json-out=reports/inventory=full.json".into(),
            "--markdown-out=reports/inventory.md".into(),
            "--max-markdown-entries=7".into(),
        ];
        let parsed = Args::parse(&args).unwrap().unwrap();
        assert_eq!(parsed.root, PathBuf::from("/tmp/repo=fixture"));
        assert_eq!(
            parsed.json_out,
            Some(PathBuf::from("reports/inventory=full.json"))
        );
        assert_eq!(
            parsed.markdown_out,
            Some(PathBuf::from("reports/inventory.md"))
        );
        assert_eq!(parsed.max_markdown_entries, 7);
        assert!(Args::parse(&["--root-only=yes".into()]).is_err());
        assert!(Args::parse(&["--unknown=value".into()])
            .unwrap_err()
            .contains("--unknown=value"));
    }

    #[test]
    fn rejects_option_tokens_as_missing_values_but_accepts_argparse_dash_values() {
        for option in [
            "--root",
            "--json-out",
            "--markdown-out",
            "--max-markdown-entries",
        ] {
            assert!(Args::parse(&[option.into(), "--root-only".into()]).is_err());
        }

        assert_eq!(
            Args::parse(&["--json-out".into(), "-".into()])
                .unwrap()
                .unwrap()
                .json_out,
            Some(PathBuf::from("-"))
        );
        assert_eq!(
            Args::parse(&["--root".into(), "-3".into()])
                .unwrap()
                .unwrap()
                .root,
            PathBuf::from("-3")
        );
        assert_eq!(
            Args::parse(&["--max-markdown-entries".into(), "-3".into()])
                .unwrap()
                .unwrap()
                .max_markdown_entries,
            -3
        );
        assert!(Args::parse(&["--json-out".into(), "-report.json".into()]).is_err());
    }

    #[test]
    fn help_is_ordered_after_preceding_parse_errors() {
        assert!(Args::parse(&["--json-out".into(), "--help".into()]).is_err());
        assert!(Args::parse(&[
            "--root-only".into(),
            "--agentcanon-only".into(),
            "--help".into()
        ])
        .is_err());
        assert!(Args::parse(&[
            "--max-markdown-entries".into(),
            "invalid".into(),
            "--help".into()
        ])
        .is_err());
        assert!(Args::parse(&["--unknown".into(), "--help".into()])
            .unwrap()
            .is_none());
        assert!(Args::parse(&["--help".into(), "--unknown".into()])
            .unwrap()
            .is_none());
        assert!(
            Args::parse(&["--root".into(), "/tmp/repo".into(), "--help".into()])
                .unwrap()
                .is_none()
        );
        assert_eq!(
            Args::parse(&["--json-out=--help".into()])
                .unwrap()
                .unwrap()
                .json_out,
            Some(PathBuf::from("--help"))
        );
    }

    #[cfg(unix)]
    #[test]
    fn preserves_literal_backslash_in_unix_path() {
        let root = scratch();
        let name = "literal\\name.md";
        fs::write(root.join(name), "backslash is a filename character\n").unwrap();
        git(&root, &["init", "-q"]);
        git(&root, &["add", "--", name]);
        let scope = inventory_scope("root", &root).unwrap();
        let entry = scope
            .entries
            .iter()
            .find(|entry| entry.path == name)
            .unwrap();
        assert_eq!(entry.path, name);
        assert_eq!(entry.real_source_path, name);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn includes_untracked_and_dangling_symlink_but_skips_deleted_and_excluded() {
        let root = scratch();
        fs::write(root.join("kept.md"), "ok").unwrap();
        fs::write(root.join("deleted.md"), "gone").unwrap();
        git(&root, &["init", "-q"]);
        git(&root, &["add", "kept.md", "deleted.md"]);
        fs::remove_file(root.join("deleted.md")).unwrap();
        fs::create_dir(root.join("reports")).unwrap();
        fs::write(root.join("reports/hidden.md"), "hidden").unwrap();
        fs::write(root.join("target"), "target").unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink("missing", root.join("dangling.md")).unwrap();
        let scope = inventory_scope("root", &root).unwrap();
        let paths: Vec<_> = scope
            .entries
            .iter()
            .map(|entry| entry.path.as_str())
            .collect();
        assert!(paths.contains(&"kept.md"));
        #[cfg(unix)]
        assert!(paths.contains(&"dangling.md"));
        assert!(!paths.contains(&"deleted.md"));
        assert!(!paths.iter().any(|path| path.starts_with("reports/")));
        #[cfg(unix)]
        {
            let dangling = scope
                .entries
                .iter()
                .find(|entry| entry.path == "dangling.md")
                .unwrap();
            assert_eq!(dangling.symlink_target, "missing");
            assert_eq!(dangling.real_source_path, "missing");
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn non_git_root_is_an_inventory_failure() {
        let root = scratch();
        let error = git_files(&root).unwrap_err();
        assert!(error.contains("git ls-files failed for inventory scope"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn preserves_gitlink_and_tracked_modes() {
        let root = scratch();
        fs::write(root.join("run.sh"), "echo ok\n").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(root.join("run.sh"), fs::Permissions::from_mode(0o755)).unwrap();
        }
        fs::write(root.join("link-target"), "ok").unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink("link-target", root.join("link.md")).unwrap();
        git(&root, &["init", "-q"]);
        git(&root, &["add", "run.sh"]);
        #[cfg(unix)]
        git(&root, &["add", "link.md"]);
        git(
            &root,
            &[
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-qm",
                "fixture",
            ],
        );
        let commit = Command::new("git")
            .arg("-C")
            .arg(&root)
            .args(["rev-parse", "HEAD"])
            .output()
            .unwrap();
        let commit = String::from_utf8(commit.stdout).unwrap().trim().to_string();
        git(
            &root,
            &[
                "update-index",
                "--add",
                "--cacheinfo",
                &format!("160000,{commit},submodule"),
            ],
        );
        let scope = inventory_scope("root", &root).unwrap();
        let executable = scope
            .entries
            .iter()
            .find(|entry| entry.path == "run.sh")
            .unwrap();
        assert_eq!(executable.git_mode, "100755");
        let gitlink = scope
            .entries
            .iter()
            .find(|entry| entry.path == "submodule")
            .unwrap();
        assert_eq!(gitlink.kind, "gitlink");
        assert!(!gitlink.checkable);
        #[cfg(unix)]
        assert_eq!(
            scope
                .entries
                .iter()
                .find(|entry| entry.path == "link.md")
                .unwrap()
                .git_mode,
            "120000"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn markdown_limit_does_not_truncate_json_inventory() {
        let entries = vec![FileEntry {
            scope: "root".into(),
            path: "a.md".into(),
            kind: "product_file".into(),
            suffix: ".md".into(),
            checkable: true,
            git_mode: "100644".into(),
            symlink_target: String::new(),
            real_source_path: "a.md".into(),
        }];
        let scopes = vec![ScopeInventory {
            name: "root".into(),
            root: "/repo".into(),
            files: 1,
            checkable_files: 1,
            by_kind: BTreeMap::from([("product_file".into(), 1)]),
            entries,
        }];
        assert_eq!(markdown_rows(&scopes, 0).len(), 0);
        assert_eq!(
            json_count(&render_json("root-only", Path::new("/repo"), &scopes)),
            1
        );
    }

    fn json_count(text: &str) -> usize {
        let value: Value = serde_json::from_str(text).unwrap();
        value["scopes"][0]["entries"].as_array().unwrap().len()
    }
}
