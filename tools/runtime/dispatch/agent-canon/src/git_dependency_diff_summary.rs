// @dependency-start
// contract implementation
// responsibility Summarizes Git changes with optional native SCIP impact and the existing dependency-header review provider.
// upstream implementation scip_index.rs owns official SCIP index/query projection
// upstream implementation lsp_code_analysis.rs owns the native source-language suffix map
// upstream implementation runtime_boundary.rs owns external report paths and root capabilities
// downstream implementation main.rs exposes the existing git-dependency-diff-summary command
// downstream test ../tests/git_dependency_diff_summary_native.rs preserves Git parsing and CLI behavior
// @dependency-end

use crate::lsp_code_analysis::language_for_path;
use crate::python_text::python_strip;
use crate::runtime_boundary::{root_capability_environment, RuntimeArtifactBoundary};
use serde::Serialize;
use serde_json::{json, Map, Value};
use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use time::format_description::well_known::Rfc3339;
use time::OffsetDateTime;

pub const SCHEMA: &str = "agent_canon.git_dependency_diff_summary.v2";
const GIT_RENAME_OR_COPY_FIELD_COUNT: usize = 3;
const GIT_NUMSTAT_FIELD_COUNT: usize = 3;

static NEXT_REPORT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct CommandRecord {
    pub command: Vec<String>,
    pub returncode: i32,
    pub stdout_path: Option<String>,
    pub stderr_path: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChangedPath {
    pub status: String,
    pub path: OsString,
    pub old_path: Option<OsString>,
    pub additions: Option<i64>,
    pub deletions: Option<i64>,
    pub binary: bool,
    pub exists_in_worktree: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiffSpec {
    pub base: String,
    pub head: String,
    pub paths: Vec<String>,
}

impl DiffSpec {
    pub fn compares_worktree(&self) -> bool {
        self.head.is_empty()
    }

    fn git_args(&self) -> Vec<String> {
        let mut args = vec![self.base.clone()];
        if !self.head.is_empty() {
            args.push(self.head.clone());
        }
        args.push("--".to_string());
        args.extend(self.paths.iter().cloned());
        args
    }
}

#[derive(Debug, Clone)]
struct DiffArtifacts {
    rows: Vec<ChangedPath>,
    changed_files_path: PathBuf,
    git_stat_path: PathBuf,
}

#[derive(Debug, Clone)]
struct DependencyArtifacts {
    scip_impact_path: PathBuf,
    dependency_dir: PathBuf,
    commands: BTreeMap<String, Value>,
    status_code: i32,
}

pub fn parse_name_status(output: &str) -> Vec<ChangedPath> {
    let mut rows = Vec::new();
    for line in output.lines().filter(|line| !python_strip(line).is_empty()) {
        let fields = line
            .splitn(GIT_NUMSTAT_FIELD_COUNT, '\t')
            .collect::<Vec<_>>();
        if fields.is_empty() {
            continue;
        }
        let status = fields[0];
        if (status.starts_with('R') || status.starts_with('C'))
            && fields.len() >= GIT_RENAME_OR_COPY_FIELD_COUNT
        {
            rows.push(ChangedPath {
                status: status.to_string(),
                old_path: Some(OsString::from(fields[1])),
                path: OsString::from(fields[2]),
                additions: None,
                deletions: None,
                binary: false,
                exists_in_worktree: false,
            });
        } else if fields.len() >= 2 {
            rows.push(ChangedPath {
                status: status.to_string(),
                path: OsString::from(fields[1]),
                old_path: None,
                additions: None,
                deletions: None,
                binary: false,
                exists_in_worktree: false,
            });
        }
    }
    rows
}

fn decode_git_status(value: &[u8]) -> String {
    String::from_utf8_lossy(value).into_owned()
}

fn decode_git_path(value: &[u8]) -> OsString {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStringExt;
        OsString::from_vec(value.to_vec())
    }
    #[cfg(not(unix))]
    {
        String::from_utf8_lossy(value).into_owned().into()
    }
}

pub fn parse_name_status_z(output: &[u8]) -> Vec<ChangedPath> {
    let fields = output.split(|byte| *byte == 0).collect::<Vec<_>>();
    let mut rows = Vec::new();
    let mut index = 0;
    while index < fields.len() {
        let raw_status = fields[index];
        index += 1;
        if raw_status.is_empty() {
            continue;
        }
        let status = decode_git_status(raw_status);
        if index >= fields.len() {
            break;
        }
        let first_path = decode_git_path(fields[index]);
        index += 1;
        if status.starts_with('R') || status.starts_with('C') {
            if index >= fields.len() {
                break;
            }
            let path = decode_git_path(fields[index]);
            index += 1;
            rows.push(ChangedPath {
                status,
                path,
                old_path: Some(first_path),
                additions: None,
                deletions: None,
                binary: false,
                exists_in_worktree: false,
            });
        } else {
            rows.push(ChangedPath {
                status,
                path: first_path,
                old_path: None,
                additions: None,
                deletions: None,
                binary: false,
                exists_in_worktree: false,
            });
        }
    }
    rows
}

fn parse_numstat_fields(
    additions: &str,
    deletions: &str,
    path: OsString,
) -> Result<(OsString, Option<i64>, Option<i64>, bool), String> {
    let binary = additions == "-" || deletions == "-";
    if binary {
        return Ok((path, None, None, true));
    }
    let additions = additions
        .parse::<i64>()
        .map_err(|error| format!("invalid Git numstat additions: {error}"))?;
    let deletions = deletions
        .parse::<i64>()
        .map_err(|error| format!("invalid Git numstat deletions: {error}"))?;
    Ok((path, Some(additions), Some(deletions), false))
}

pub fn parse_numstat(
    output: &str,
) -> Result<BTreeMap<OsString, (Option<i64>, Option<i64>, bool)>, String> {
    let mut stats = BTreeMap::new();
    for line in output.lines().filter(|line| !python_strip(line).is_empty()) {
        let fields = line.split('\t').collect::<Vec<_>>();
        if fields.len() < GIT_NUMSTAT_FIELD_COUNT {
            continue;
        }
        let (path, additions, deletions, binary) = parse_numstat_fields(
            fields[0],
            fields[1],
            OsString::from(current_numstat_path(
                fields.last().copied().unwrap_or_default(),
            )),
        )?;
        stats.insert(path, (additions, deletions, binary));
    }
    Ok(stats)
}

pub fn current_numstat_path(path: &str) -> String {
    let marker = " => ";
    if !path.contains(marker) {
        return path.to_string();
    }
    if path.contains('{') && path.contains('}') {
        if let Some((prefix, rest)) = path.split_once('{') {
            if let Some((body, suffix)) = rest.split_once('}') {
                if let Some((_, current)) = body.split_once(marker) {
                    return format!("{prefix}{current}{suffix}");
                }
            }
        }
    }
    path.split_once(marker)
        .map(|(_, current)| current.to_string())
        .unwrap_or_else(|| path.to_string())
}

pub fn parse_numstat_z(
    output: &[u8],
) -> Result<BTreeMap<OsString, (Option<i64>, Option<i64>, bool)>, String> {
    let fields = output.split(|byte| *byte == 0).collect::<Vec<_>>();
    let mut stats = BTreeMap::new();
    let mut index = 0;
    while index < fields.len() {
        let header = fields[index];
        index += 1;
        if header.is_empty() {
            continue;
        }
        let parts = header
            .splitn(GIT_NUMSTAT_FIELD_COUNT, |byte| *byte == b'\t')
            .collect::<Vec<_>>();
        if parts.len() < GIT_NUMSTAT_FIELD_COUNT {
            continue;
        }
        let additions = std::str::from_utf8(parts[0])
            .map_err(|error| format!("invalid Git numstat additions: {error}"))?;
        let deletions = std::str::from_utf8(parts[1])
            .map_err(|error| format!("invalid Git numstat deletions: {error}"))?;
        let mut path = parts[2];
        if path.is_empty() {
            if index + 1 >= fields.len() {
                continue;
            }
            index += 1;
            path = fields[index];
            index += 1;
        }
        let (path, additions, deletions, binary) =
            parse_numstat_fields(additions, deletions, decode_git_path(path))?;
        stats.insert(path, (additions, deletions, binary));
    }
    Ok(stats)
}

pub fn git_stdout(root: &Path, args: &[String]) -> Result<String, String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .map_err(|error| format!("unable to execute git: {error}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stderr = python_strip(&stderr);
        return Err(if stderr.is_empty() {
            format!("git {} failed", args.join(" "))
        } else {
            stderr.to_string()
        });
    }
    String::from_utf8(output.stdout).map_err(|error| format!("Git stdout is not UTF-8: {error}"))
}

pub fn git_stdout_bytes(root: &Path, args: &[String]) -> Result<Vec<u8>, String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .map_err(|error| format!("unable to execute git: {error}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stderr = python_strip(&stderr);
        return Err(if stderr.is_empty() {
            format!("git {} failed", args.join(" "))
        } else {
            stderr.to_string()
        });
    }
    Ok(output.stdout)
}

fn git_diff_args(diff: &DiffSpec) -> Vec<String> {
    diff.git_args()
}

fn untracked_paths(root: &Path, paths: &[String]) -> Result<Vec<OsString>, String> {
    let mut args = vec![
        "ls-files".to_string(),
        "--others".to_string(),
        "--exclude-standard".to_string(),
        "--".to_string(),
    ];
    args.extend(paths.iter().cloned());
    Ok(git_stdout(root, &args)?
        .lines()
        .filter(|line| !python_strip(line).is_empty())
        .map(OsString::from)
        .collect())
}

fn is_file_in_worktree(root: &Path, path: &OsStr) -> bool {
    fs::metadata(root.join(path)).is_ok_and(|metadata| metadata.is_file())
}

fn path_order(left: &OsStr, right: &OsStr) -> Ordering {
    match (left.to_str(), right.to_str()) {
        (Some(left), Some(right)) => left.cmp(right),
        _ => left.cmp(right),
    }
}

pub fn collect_changed_paths(root: &Path, diff: &DiffSpec) -> Result<Vec<ChangedPath>, String> {
    let suffix = git_diff_args(diff);
    let mut names_args = vec![
        "diff".to_string(),
        "--name-status".to_string(),
        "-z".to_string(),
        "--find-renames".to_string(),
    ];
    names_args.extend(suffix.iter().cloned());
    let rows = parse_name_status_z(&git_stdout_bytes(root, &names_args)?);
    let mut numstat_args = vec![
        "diff".to_string(),
        "--numstat".to_string(),
        "-z".to_string(),
    ];
    numstat_args.extend(suffix);
    let numstat = parse_numstat_z(&git_stdout_bytes(root, &numstat_args)?)?;
    let mut merged = Vec::new();
    let mut seen = BTreeSet::<OsString>::new();
    for row in rows {
        let (additions, deletions, binary) = numstat
            .get(&row.path)
            .copied()
            .unwrap_or((None, None, false));
        seen.insert(row.path.clone());
        merged.push(ChangedPath {
            status: row.status,
            exists_in_worktree: is_file_in_worktree(root, &row.path),
            path: row.path,
            old_path: row.old_path,
            additions,
            deletions,
            binary,
        });
    }
    if diff.compares_worktree() {
        for path in untracked_paths(root, &diff.paths)? {
            if seen.contains(&path) {
                continue;
            }
            merged.push(ChangedPath {
                status: "??".to_string(),
                exists_in_worktree: is_file_in_worktree(root, &path),
                path,
                old_path: None,
                additions: None,
                deletions: None,
                binary: false,
            });
        }
    }
    merged.sort_by(|left, right| {
        path_order(&left.path, &right.path).then_with(|| left.status.cmp(&right.status))
    });
    Ok(merged)
}

pub fn changed_file_list(rows: &[ChangedPath]) -> Vec<OsString> {
    let mut paths = BTreeSet::new();
    for row in rows {
        paths.insert(row.path.clone());
        if let Some(old_path) = &row.old_path {
            paths.insert(old_path.clone());
        }
    }
    let mut paths = paths.into_iter().collect::<Vec<_>>();
    paths.sort_by(|left, right| path_order(left, right));
    paths
}

pub fn scip_target_paths(rows: &[ChangedPath]) -> Vec<OsString> {
    let mut candidates = BTreeSet::new();
    for row in rows {
        for path in std::iter::once(&row.path).chain(row.old_path.iter()) {
            if language_for_path(Path::new(path)).is_some() {
                candidates.insert((*path).clone());
            }
        }
    }
    let mut candidates = candidates.into_iter().collect::<Vec<_>>();
    candidates.sort_by(|left, right| path_order(left, right));
    candidates
}

fn source_repository_root() -> Result<PathBuf, String> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .map(Path::to_path_buf)
        .ok_or_else(|| "AgentCanon source root is unavailable".to_string())
}

fn path_as_posix(path: &Path) -> String {
    let value = path.to_string_lossy().into_owned();
    #[cfg(windows)]
    {
        value.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        value
    }
}

fn write_text(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    text: &str,
) -> Result<PathBuf, String> {
    boundary.atomic_write_text(path, text, 0o600)
}

fn run_capture(
    root: &Path,
    command: &[String],
    stdout_path: &Path,
    stderr_path: &Path,
    boundary: &RuntimeArtifactBoundary,
    environment: &BTreeMap<String, String>,
) -> Result<CommandRecord, String> {
    let Some(executable) = command.first() else {
        return Err("dependency command is empty".to_string());
    };
    let output = Command::new(executable)
        .args(command.iter().skip(1))
        .current_dir(root)
        .env_clear()
        .envs(environment)
        .output()
        .map_err(|error| format!("unable to execute {executable}: {error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let stdout_path = write_text(boundary, stdout_path, &stdout)?;
    let stderr_path = write_text(boundary, stderr_path, &stderr)?;
    Ok(CommandRecord {
        command: command.to_vec(),
        returncode: process_exit_code(&output.status),
        stdout_path: Some(path_as_posix(&stdout_path)),
        stderr_path: Some(path_as_posix(&stderr_path)),
    })
}

fn process_exit_code(status: &ExitStatus) -> i32 {
    match status.code() {
        Some(code) => code,
        None => {
            #[cfg(unix)]
            {
                use std::os::unix::process::ExitStatusExt;
                status.signal().map_or(1, |signal| -signal)
            }
            #[cfg(not(unix))]
            {
                1
            }
        }
    }
}

fn command_value(record: &CommandRecord) -> Value {
    serde_json::to_value(record).unwrap_or(Value::Null)
}

fn git_path_utf8<'a>(path: &'a OsStr, label: &str) -> Result<&'a str, String> {
    path.to_str()
        .ok_or_else(|| format!("{label} contains a path that is not valid UTF-8"))
}

fn changed_path_value(row: &ChangedPath) -> Result<Value, String> {
    let path = git_path_utf8(&row.path, "changed path")?;
    let old_path = match row.old_path.as_deref() {
        Some(path) => Some(git_path_utf8(path, "previous changed path")?),
        None => None,
    };
    Ok(json!({
        "status": row.status,
        "path": path,
        "old_path": old_path,
        "additions": row.additions,
        "deletions": row.deletions,
        "binary": row.binary,
        "exists_in_worktree": row.exists_in_worktree
    }))
}

fn write_diff_artifacts(
    root: &Path,
    report_dir: &Path,
    diff: &DiffSpec,
    boundary: &RuntimeArtifactBoundary,
) -> Result<DiffArtifacts, String> {
    let rows = collect_changed_paths(root, diff)?;
    let changed_paths = changed_file_list(&rows);
    let changed_paths = changed_paths
        .iter()
        .map(|path| git_path_utf8(path, "changed_files.txt"))
        .collect::<Result<Vec<_>, _>>()?;
    let changed_files_path = write_text(
        boundary,
        &report_dir.join("changed_files.txt"),
        &format!("{}\n", changed_paths.join("\n")),
    )?;
    let mut stat_args = vec!["diff".to_string(), "--stat".to_string()];
    stat_args.extend(diff.git_args());
    let git_stat = git_stdout(root, &stat_args)?;
    let git_stat_path = write_text(boundary, &report_dir.join("git_stat.txt"), &git_stat)?;
    Ok(DiffArtifacts {
        rows,
        changed_files_path,
        git_stat_path,
    })
}

fn scip_impact(
    root: &Path,
    report_dir: &Path,
    rows: &[ChangedPath],
    index_paths: &[PathBuf],
    skip: bool,
    boundary: &RuntimeArtifactBoundary,
    environment: &BTreeMap<String, String>,
) -> Result<(PathBuf, BTreeMap<String, Value>, i32), String> {
    let impact_path = report_dir.join("scip_impact.json");
    let mut commands = BTreeMap::new();
    if skip {
        write_text(
            boundary,
            &impact_path,
            &format!(
                "{}\n",
                json!({"status": "skipped", "capabilities": {"scip": "not-selected"}})
            ),
        )?;
        return Ok((impact_path, commands, 0));
    }
    let target_paths = scip_target_paths(rows);
    if target_paths.is_empty() {
        write_text(
            boundary,
            &impact_path,
            &format!(
                "{}\n",
                json!({"status": "no-selected-targets", "capabilities": {"scip": "not-needed"}})
            ),
        )?;
        return Ok((impact_path, commands, 0));
    }
    if index_paths.is_empty() {
        write_text(
            boundary,
            &impact_path,
            &format!(
                "{}\n",
                json!({"status": "not-selected", "capabilities": {"scip": "not-selected"}})
            ),
        )?;
        return Ok((impact_path, commands, 0));
    }
    let executable = std::env::current_exe()
        .map_err(|error| format!("native agent-canon executable is unavailable: {error}"))?;
    let mut command = vec![
        executable.to_string_lossy().into_owned(),
        "scip-index".to_string(),
        "query".to_string(),
        "--root".to_string(),
        root.to_string_lossy().into_owned(),
        "--runtime-root".to_string(),
        boundary.root().to_string_lossy().into_owned(),
    ];
    for index_path in index_paths {
        command.extend([
            "--index".to_string(),
            index_path.to_string_lossy().into_owned(),
        ]);
    }
    for path in target_paths {
        command.extend([
            "--path".to_string(),
            git_path_utf8(&path, "SCIP target path")?.to_string(),
        ]);
    }
    let record = run_capture(
        root,
        &command,
        &impact_path,
        &report_dir.join("scip_impact.stderr.txt"),
        boundary,
        environment,
    )?;
    let status = record.returncode;
    commands.insert("scip_impact".to_string(), command_value(&record));
    Ok((impact_path, commands, status))
}

fn run_dependency_review(
    root: &Path,
    report_dir: &Path,
    dependency_dir: &Path,
    changed_files_path: &Path,
    skip: bool,
    strict: bool,
    boundary: &RuntimeArtifactBoundary,
    environment: &BTreeMap<String, String>,
) -> Result<(BTreeMap<String, Value>, i32), String> {
    let mut commands = BTreeMap::new();
    if skip {
        let relative = dependency_dir.strip_prefix(boundary.root()).map_err(|_| {
            format!(
                "dependency review escapes runtime root: {}",
                dependency_dir.display()
            )
        })?;
        boundary.ensure_directory(relative)?;
        write_text(boundary, &dependency_dir.join("dependency_graph.tsv"), "")?;
        write_text(
            boundary,
            &dependency_dir.join("dependency_edit_scope.txt"),
            "",
        )?;
        return Ok((commands, 0));
    }
    let script =
        source_repository_root()?.join("tools/analysis/dependencies/run_repo_dependency_review.sh");
    let mut command = vec![
        "bash".to_string(),
        script.to_string_lossy().into_owned(),
        "--root".to_string(),
        root.to_string_lossy().into_owned(),
        "--report-dir".to_string(),
        dependency_dir.to_string_lossy().into_owned(),
        "--search-hits-file".to_string(),
        changed_files_path.to_string_lossy().into_owned(),
    ];
    if strict {
        command.push("--fail-missing".to_string());
    }
    let record = run_capture(
        root,
        &command,
        &report_dir.join("dependency_review.stdout.txt"),
        &report_dir.join("dependency_review.stderr.txt"),
        boundary,
        environment,
    )?;
    let status = record.returncode;
    commands.insert("dependency_review".to_string(), command_value(&record));
    Ok((commands, status))
}

fn nonempty_line_count(path: &Path) -> Result<usize, String> {
    if !path.exists() {
        return Ok(0);
    }
    let text = fs::read_to_string(path).map_err(|error| {
        format!(
            "unable to read dependency edit scope {}: {error}",
            path.display()
        )
    })?;
    Ok(text
        .lines()
        .filter(|line| !python_strip(line).is_empty())
        .count())
}

fn json_pretty(value: &Value) -> Result<String, String> {
    serde_json::to_string_pretty(value)
        .map_err(|error| format!("summary JSON serialization failed: {error}"))
}

fn render_markdown(summary: &Value) -> Result<String, String> {
    let rows = summary["changed_files"]
        .as_array()
        .ok_or_else(|| "summary changed_files must be an array".to_string())?;
    let totals = summary["totals"]
        .as_object()
        .ok_or_else(|| "summary totals must be an object".to_string())?;
    let total = |key: &str| totals.get(key).and_then(Value::as_u64).unwrap_or(0);
    let text = |key: &str| summary[key].as_str().unwrap_or_default();
    let mut lines = vec![
        "# Git Dependency Diff Summary".to_string(),
        String::new(),
        format!("- Schema: `{}`", text("schema")),
        format!("- Status: `{}`", text("status")),
        format!("- Root: `{}`", text("root")),
        format!("- Diff: `{}` -> `{}`", text("base"), {
            let head = text("head");
            if head.is_empty() {
                "worktree"
            } else {
                head
            }
        }),
        format!("- Changed files: {}", total("changed_files")),
        format!("- Added lines: {}", total("additions")),
        format!("- Deleted lines: {}", total("deletions")),
        format!(
            "- Dependency edit-scope lines: {}",
            total("dependency_edit_scope_lines")
        ),
        String::new(),
        "## Changed Files".to_string(),
        String::new(),
        "| Status | Path | Lines | Previous path |".to_string(),
        "| --- | --- | --- | --- |".to_string(),
    ];
    for row in rows {
        let status = row["status"].as_str().unwrap_or_default();
        let path = row["path"].as_str().unwrap_or_default();
        let old_path = row["old_path"].as_str().unwrap_or_default();
        let additions = row["additions"].as_i64().unwrap_or(0);
        let deletions = row["deletions"].as_i64().unwrap_or(0);
        let line_text = if row["binary"].as_bool().unwrap_or(false) {
            "binary".to_string()
        } else {
            format!("+{additions} / -{deletions}")
        };
        lines.push(format!(
            "| `{status}` | `{path}` | {line_text} | `{old_path}` |"
        ));
    }
    let artifacts = summary["artifacts"]
        .as_object()
        .ok_or_else(|| "summary artifacts must be an object".to_string())?;
    let artifact = |key: &str| {
        artifacts
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
    };
    lines.extend([
        String::new(),
        "## Dependency Artifacts".to_string(),
        String::new(),
        format!("- Changed file list: `{}`", artifact("changed_files")),
        format!("- Git stat: `{}`", artifact("git_stat")),
        format!("- SCIP impact projection: {}", artifact("scip_impact")),
        format!(
            "- Dependency review directory: `{}`",
            artifact("dependency_review_dir")
        ),
        format!("- Dependency graph TSV: `{}`", artifact("dependency_graph")),
        format!(
            "- Dependency edit scope: `{}`",
            artifact("dependency_edit_scope")
        ),
    ]);
    if let Some(returncode) = summary["commands"]["dependency_review"]["returncode"].as_i64() {
        lines.extend([
            String::new(),
            "## Command Status".to_string(),
            String::new(),
            format!("- Dependency review exit code: {returncode}"),
        ]);
    }
    Ok(lines.join("\n") + "\n")
}

fn timestamp_utc() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "1970-01-01T00:00:00Z".to_string())
}

fn build_summary(
    root: &Path,
    report_dir: &Path,
    diff: &DiffSpec,
    diff_artifacts: &DiffArtifacts,
    dependency_artifacts: &DependencyArtifacts,
    boundary: &RuntimeArtifactBoundary,
) -> Result<Value, String> {
    let rows = diff_artifacts.rows.iter().collect::<Vec<_>>();
    let dependency_dir = &dependency_artifacts.dependency_dir;
    let additions = rows
        .iter()
        .map(|row| row.additions.unwrap_or(0))
        .sum::<i64>();
    let deletions = rows
        .iter()
        .map(|row| row.deletions.unwrap_or(0))
        .sum::<i64>();
    let dependency_edit_scope_lines =
        nonempty_line_count(&dependency_dir.join("dependency_edit_scope.txt"))?;
    let serialized_rows = rows
        .iter()
        .map(|row| changed_path_value(row))
        .collect::<Result<Vec<_>, _>>()?;
    let mut summary = json!({
        "schema": SCHEMA,
        "status": if dependency_artifacts.status_code == 0 {"pass"} else {"fail"},
        "generated_at": timestamp_utc(),
        "root": path_as_posix(root),
        "base": diff.base,
        "head": if diff.head.is_empty() {Value::Null} else {Value::String(diff.head.clone())},
        "paths": diff.paths,
        "changed_files": serialized_rows,
        "totals": {
            "changed_files": rows.len(),
            "additions": additions,
            "deletions": deletions,
            "dependency_edit_scope_lines": dependency_edit_scope_lines
        },
        "artifacts": {
            "report_dir": path_as_posix(report_dir),
            "changed_files": path_as_posix(&diff_artifacts.changed_files_path),
            "git_stat": path_as_posix(&diff_artifacts.git_stat_path),
            "scip_impact": path_as_posix(&dependency_artifacts.scip_impact_path),
            "dependency_review_dir": path_as_posix(dependency_dir),
            "dependency_graph": path_as_posix(&dependency_dir.join("dependency_graph.tsv")),
            "dependency_edit_scope": path_as_posix(&dependency_dir.join("dependency_edit_scope.txt"))
        },
        "commands": dependency_artifacts.commands
    });
    let summary_json_path = report_dir.join("summary.json");
    let summary_markdown_path = report_dir.join("summary.md");
    write_text(
        boundary,
        &summary_json_path,
        &(json_pretty(&summary)? + "\n"),
    )?;
    write_text(
        boundary,
        &summary_markdown_path,
        &render_markdown(&summary)?,
    )?;
    let artifacts = summary["artifacts"]
        .as_object_mut()
        .ok_or_else(|| "summary artifacts must be an object".to_string())?;
    artifacts.insert(
        "summary_json".to_string(),
        Value::String(path_as_posix(&summary_json_path)),
    );
    artifacts.insert(
        "summary_markdown".to_string(),
        Value::String(path_as_posix(&summary_markdown_path)),
    );
    write_text(
        boundary,
        &summary_json_path,
        &(json_pretty(&summary)? + "\n"),
    )?;
    write_text(
        boundary,
        &summary_markdown_path,
        &render_markdown(&summary)?,
    )?;
    Ok(summary)
}

fn emit(summary: &Value, format: &str) -> Result<String, String> {
    match format {
        "json" => Ok(json_pretty(summary)? + "\n"),
        "markdown" => render_markdown(summary),
        _ => {
            let artifacts = summary["artifacts"]
                .as_object()
                .ok_or_else(|| "summary artifacts must be an object".to_string())?;
            let totals = summary["totals"]
                .as_object()
                .ok_or_else(|| "summary totals must be an object".to_string())?;
            let value = |map: &Map<String, Value>, key: &str| {
                map.get(key).and_then(Value::as_str).unwrap_or_default()
            };
            Ok(vec![
                format!(
                    "GIT_DEPENDENCY_DIFF_SUMMARY={}",
                    summary["status"].as_str().unwrap_or_default()
                ),
                format!(
                    "GIT_DEPENDENCY_DIFF_SUMMARY_SCHEMA={}",
                    summary["schema"].as_str().unwrap_or_default()
                ),
                format!(
                    "GIT_DEPENDENCY_DIFF_SUMMARY_CHANGED_FILES={}",
                    totals
                        .get("changed_files")
                        .and_then(Value::as_u64)
                        .unwrap_or(0)
                ),
                format!(
                    "GIT_DEPENDENCY_DIFF_SUMMARY_EDIT_SCOPE_LINES={}",
                    totals
                        .get("dependency_edit_scope_lines")
                        .and_then(Value::as_u64)
                        .unwrap_or(0)
                ),
                format!(
                    "GIT_DEPENDENCY_DIFF_SUMMARY_JSON={}",
                    value(artifacts, "summary_json")
                ),
                format!(
                    "GIT_DEPENDENCY_DIFF_SUMMARY_MARKDOWN={}",
                    value(artifacts, "summary_markdown")
                ),
                format!(
                    "GIT_DEPENDENCY_DIFF_SUMMARY_REPORT_DIR={}",
                    value(artifacts, "report_dir")
                ),
            ]
            .join("\n")
                + "\n")
        }
    }
}

struct CliOptions {
    root: PathBuf,
    base: String,
    head: String,
    report_dir: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
    format: String,
    output: Option<PathBuf>,
    scip_indexes: Vec<PathBuf>,
    skip_scip_impact: bool,
    skip_dependency_review: bool,
    strict_dependency_review: bool,
    paths: Vec<String>,
}

const USAGE: &str = "usage: agent-canon git-dependency-diff-summary [options] [pathspecs...]\n\n\
  --root ROOT\n\
  --base REF\n\
  --head REF\n\
  --report-dir PATH\n\
  --runtime-root PATH\n\
  --format text|json|markdown\n\
  --output PATH\n\
  --scip-index PATH ...\n\
  --skip-scip-impact\n\
  --skip-dependency-review\n\
  --strict-dependency-review\n\
  -h, --help";

fn option_value(
    args: &[String],
    index: &mut usize,
    name: &str,
    inline: Option<&str>,
) -> Result<String, String> {
    if let Some(value) = inline {
        return Ok(value.to_string());
    }
    let Some(value) = args.get(*index + 1) else {
        return Err(format!("argument {name}: expected one argument"));
    };
    if value.starts_with('-') && !crate::python_cli_integer::is_argparse_negative_number(value) {
        return Err(format!("argument {name}: expected one argument"));
    }
    *index += 1;
    Ok(value.clone())
}

fn parse_options(args: &[String]) -> Result<CliOptions, String> {
    let mut options = CliOptions {
        root: std::env::current_dir().map_err(|error| error.to_string())?,
        base: "HEAD".to_string(),
        head: String::new(),
        report_dir: None,
        runtime_root: None,
        format: "text".to_string(),
        output: None,
        scip_indexes: Vec::new(),
        skip_scip_impact: false,
        skip_dependency_review: false,
        strict_dependency_review: false,
        paths: Vec::new(),
    };
    let mut index = 0;
    let mut positional_only = false;
    while index < args.len() {
        let argument = &args[index];
        if positional_only {
            options.paths.push(argument.clone());
            index += 1;
            continue;
        }
        match argument.as_str() {
            "-h" | "--help" => return Err("__help__".to_string()),
            "--skip-scip-impact" => options.skip_scip_impact = true,
            "--skip-dependency-review" => options.skip_dependency_review = true,
            "--strict-dependency-review" => options.strict_dependency_review = true,
            "--" => {
                positional_only = true;
                index += 1;
                continue;
            }
            _ => {
                if argument.starts_with('-') {
                    let (name, inline) = argument
                        .split_once('=')
                        .map_or((argument.as_str(), None), |(name, value)| {
                            (name, Some(value))
                        });
                    let value = option_value(args, &mut index, name, inline)?;
                    match name {
                        "--root" => options.root = PathBuf::from(value),
                        "--base" => options.base = value,
                        "--head" => options.head = value,
                        "--report-dir" => {
                            options.report_dir = if value.is_empty() {
                                None
                            } else {
                                Some(PathBuf::from(value))
                            }
                        }
                        "--runtime-root" => options.runtime_root = Some(PathBuf::from(value)),
                        "--format" if matches!(value.as_str(), "text" | "json" | "markdown") => {
                            options.format = value
                        }
                        "--format" => {
                            return Err(format!(
                                "invalid choice: '{value}' (choose from 'text', 'json', 'markdown')"
                            ))
                        }
                        "--output" => options.output = Some(PathBuf::from(value)),
                        "--scip-index" => options.scip_indexes.push(PathBuf::from(value)),
                        _ => return Err(format!("unrecognized arguments: {argument}")),
                    }
                } else {
                    options.paths.push(argument.clone());
                }
            }
        }
        index += 1;
    }
    Ok(options)
}

fn fresh_report_directory(boundary: &RuntimeArtifactBoundary) -> Result<PathBuf, String> {
    let parent = Path::new("tasks/dependency-diff");
    boundary.ensure_directory(parent)?;
    let sequence = NEXT_REPORT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| format!("system clock is unavailable: {error}"))?
        .as_nanos();
    let relative = parent.join(format!("run-{}-{nanos}-{sequence}", std::process::id()));
    let path = boundary.resolve(&relative)?;
    if path.exists() {
        return Err(format!(
            "temporary report directory already exists: {}",
            path.display()
        ));
    }
    boundary.ensure_directory(&relative)
}

fn execute(
    options: CliOptions,
) -> Result<(Value, RuntimeArtifactBoundary, i32, String, Option<PathBuf>), String> {
    let output_format = options.format.clone();
    let output_path = options.output.clone();
    let root = fs::canonicalize(&options.root).map_err(|error| {
        format!(
            "repository root is unavailable: {}: {error}",
            options.root.display()
        )
    })?;
    let boundary =
        RuntimeArtifactBoundary::for_source(&root, options.runtime_root.as_deref(), true)?;
    let report_dir = if let Some(report_dir) = options.report_dir.as_deref() {
        let path = boundary.resolve(report_dir)?;
        let relative = path
            .strip_prefix(boundary.root())
            .map_err(|_| format!("report directory escapes runtime root: {}", path.display()))?;
        boundary.ensure_directory(relative)?
    } else {
        fresh_report_directory(&boundary)?
    };
    let mut environment = root_capability_environment(&root, boundary.root(), None, Some(&root))?;
    environment.insert(
        "AGENT_CANON_CONTROL_PARENT_ROOT".to_string(),
        root.display().to_string(),
    );
    let diff = DiffSpec {
        base: options.base,
        head: options.head,
        paths: options.paths,
    };
    let diff_artifacts = write_diff_artifacts(&root, &report_dir, &diff, &boundary)?;
    let dependency_dir = report_dir.join("dependency-review");
    let (scip_impact_path, mut commands, scip_status) = scip_impact(
        &root,
        &report_dir,
        &diff_artifacts.rows,
        &options.scip_indexes,
        options.skip_scip_impact,
        &boundary,
        &environment,
    )?;
    let (dependency_commands, dependency_status) = run_dependency_review(
        &root,
        &report_dir,
        &dependency_dir,
        &diff_artifacts.changed_files_path,
        options.skip_dependency_review,
        options.strict_dependency_review,
        &boundary,
        &environment,
    )?;
    commands.extend(dependency_commands);
    let dependency_artifacts = DependencyArtifacts {
        scip_impact_path,
        dependency_dir,
        commands,
        status_code: scip_status.max(dependency_status),
    };
    let summary = build_summary(
        &root,
        &report_dir,
        &diff,
        &diff_artifacts,
        &dependency_artifacts,
        &boundary,
    )?;
    Ok((
        summary,
        boundary,
        dependency_artifacts.status_code,
        output_format,
        output_path,
    ))
}

/// Run the canonical Git dependency-diff summary command.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_options(args) {
        Ok(options) => options,
        Err(error) if error == "__help__" => {
            println!("{USAGE}");
            return 0;
        }
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon git-dependency-diff-summary: {error}");
            return 2;
        }
    };
    let (summary, boundary, status, output_format, output_path) = match execute(options) {
        Ok(result) => result,
        Err(error) => {
            eprintln!("GIT_DEPENDENCY_DIFF_SUMMARY=fail");
            eprintln!("GIT_DEPENDENCY_DIFF_SUMMARY_ERROR={error}");
            return 1;
        }
    };
    let payload = match emit(&summary, &output_format) {
        Ok(payload) => payload,
        Err(error) => {
            eprintln!("GIT_DEPENDENCY_DIFF_SUMMARY=fail");
            eprintln!("GIT_DEPENDENCY_DIFF_SUMMARY_ERROR={error}");
            return 1;
        }
    };
    if let Some(output) = output_path {
        if let Err(error) = write_text(&boundary, &output, &payload) {
            eprintln!("GIT_DEPENDENCY_DIFF_SUMMARY=fail");
            eprintln!("GIT_DEPENDENCY_DIFF_SUMMARY_ERROR={error}");
            return 1;
        }
    }
    print!("{payload}");
    status
}
