// @dependency-start
// contract implementation
// responsibility Confirms that structural changes from a source branch survive local integration.
// upstream design ../../../../../documents/operations/BRANCH_SCOPE.md local structural integration contract
// upstream design ../../../../../agents/skills/integration.md targeted merge readback route
// downstream implementation main.rs exposes the check-merge-structure command
// downstream implementation ../../../../../tests/tools/test_check_merge_structure.py preserves Git fixture oracles
// @dependency-end

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::process::Command;

const STRUCTURAL_PREFIXES: &[char] = &['A', 'D', 'R', 'T'];
const USAGE: &str = "Usage: agent-canon check-merge-structure --source SOURCE [--target TARGET] [--compare-commit COMMIT] [--repo-root PATH]

Confirm that structural changes from a source branch (add/delete/rename/type change)
are preserved in a local integration commit. Defaults: --target main,
--compare-commit HEAD, --repo-root .";

#[derive(Debug, PartialEq, Eq)]
struct Args {
    source: String,
    target: String,
    compare_commit: String,
    repo_root: PathBuf,
}

#[derive(Debug, PartialEq, Eq)]
struct PathState {
    mode: String,
    kind: String,
    oid: String,
}

pub fn run(raw_args: &[String]) -> i32 {
    match Args::parse(raw_args) {
        Ok(None) => {
            println!("{USAGE}");
            0
        }
        Ok(Some(args)) => check(&args),
        Err(message) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon check-merge-structure: error: {message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Option<Self>, String> {
        let mut source = None;
        let mut target = "main".to_string();
        let mut compare_commit = "HEAD".to_string();
        let mut repo_root = PathBuf::from(".");
        let mut index = 0;

        while index < args.len() {
            let raw = &args[index];
            if matches!(raw.as_str(), "-h" | "--help") {
                return Ok(None);
            }
            let (flag, inline_value) = match raw.split_once('=') {
                Some((flag, value)) => (flag, Some(value.to_string())),
                None => (raw.as_str(), None),
            };
            match flag {
                "--source" => {
                    let (value, consumed) = value_after(args, index, flag, inline_value)?;
                    source = Some(value);
                    index += consumed;
                }
                "--target" => {
                    let (value, consumed) = value_after(args, index, flag, inline_value)?;
                    target = value;
                    index += consumed;
                }
                "--compare-commit" => {
                    let (value, consumed) = value_after(args, index, flag, inline_value)?;
                    compare_commit = value;
                    index += consumed;
                }
                "--repo-root" => {
                    let (value, consumed) = value_after(args, index, flag, inline_value)?;
                    repo_root = PathBuf::from(value);
                    index += consumed;
                }
                _ => return Err(format!("unrecognized arguments: {raw}")),
            }
        }

        let source =
            source.ok_or_else(|| "the following argument is required: --source".to_string())?;
        Ok(Some(Self {
            source,
            target,
            compare_commit,
            repo_root,
        }))
    }
}

fn value_after(
    args: &[String],
    index: usize,
    flag: &str,
    inline_value: Option<String>,
) -> Result<(String, usize), String> {
    if let Some(value) = inline_value {
        return Ok((value, 1));
    }
    let Some(value) = args.get(index + 1) else {
        return Err(format!("{flag} requires a value"));
    };
    if value.starts_with('-') {
        return Err(format!("{flag} requires a value"));
    }
    Ok((value.clone(), 2))
}

fn check(args: &Args) -> i32 {
    let root = match args.repo_root.canonicalize() {
        Ok(root) => root,
        Err(error) => return git_failure(format!("cannot resolve repository root: {error}")),
    };
    let merge_base = match run_git(
        &root,
        &["merge-base", args.target.as_str(), args.source.as_str()],
    ) {
        Ok(value) => value,
        Err(error) => return git_failure(error),
    };
    let paths = match structural_paths(&root, &merge_base, &args.source) {
        Ok(paths) => paths,
        Err(error) => return git_failure(error),
    };

    println!("REPO_ROOT={}", root.display());
    println!("TARGET={}", args.target);
    println!("SOURCE={}", args.source);
    println!("COMPARE_COMMIT={}", args.compare_commit);
    println!("MERGE_BASE={merge_base}");

    if paths.is_empty() {
        println!("STRUCTURAL_PATH_COUNT=0");
        println!("MERGE_STRUCTURE_CHECK=pass (no structural changes on source branch)");
        return 0;
    }

    println!("STRUCTURAL_PATH_COUNT={}", paths.len());
    let mut mismatches = Vec::new();
    for path in paths {
        let source_state = match path_state(&root, &args.source, &path) {
            Ok(state) => state,
            Err(error) => return git_failure(error),
        };
        let compare_state = match path_state(&root, &args.compare_commit, &path) {
            Ok(state) => state,
            Err(error) => return git_failure(error),
        };
        if source_state != compare_state {
            mismatches.push(format!(
                "{path}: source={} compare={}",
                source_state.display(),
                compare_state.display()
            ));
        }
    }

    if mismatches.is_empty() {
        println!("MERGE_STRUCTURE_CHECK=pass");
        return 0;
    }

    println!("MERGE_STRUCTURE_CHECK=fail");
    println!("MISMATCHES:");
    for mismatch in mismatches {
        println!("- {mismatch}");
    }
    1
}

fn structural_paths(
    repo_root: &Path,
    merge_base: &str,
    source: &str,
) -> Result<Vec<String>, String> {
    let output = run_git(
        repo_root,
        &[
            "diff",
            "--name-status",
            "--find-renames",
            merge_base,
            source,
        ],
    )?;
    let mut paths = BTreeSet::new();
    for line in output.lines().filter(|line| !line.trim().is_empty()) {
        let parts: Vec<&str> = line.split('\t').collect();
        let status = parts.first().copied().unwrap_or_default();
        let Some(prefix) = status.chars().next() else {
            continue;
        };
        if !STRUCTURAL_PREFIXES.contains(&prefix) {
            continue;
        }
        if prefix == 'R' {
            if parts.len() >= 3 {
                paths.insert(parts[1].to_string());
                paths.insert(parts[2].to_string());
            }
        } else if parts.len() >= 2 {
            paths.insert(parts[1].to_string());
        }
    }
    Ok(paths.into_iter().collect())
}

fn path_state(repo_root: &Path, revision: &str, path: &str) -> Result<PathState, String> {
    let output = run_git(repo_root, &["ls-tree", revision, "--", path])?;
    let line = output.trim();
    if line.is_empty() {
        return Ok(PathState {
            mode: String::new(),
            kind: "absent".to_string(),
            oid: String::new(),
        });
    }

    let Some((entry, _path)) = line.split_once('\t') else {
        return Err(format!("unexpected git ls-tree output for {path}"));
    };
    let fields: Vec<&str> = entry.split_whitespace().collect();
    if fields.len() != 3 {
        return Err(format!("unexpected git ls-tree entry for {path}"));
    }
    let mode = fields[0].to_string();
    let kind = if mode == "120000" {
        "symlink".to_string()
    } else {
        fields[1].to_string()
    };
    Ok(PathState {
        mode,
        kind,
        oid: fields[2].to_string(),
    })
}

impl PathState {
    fn display(&self) -> String {
        if self.kind == "absent" {
            "absent".to_string()
        } else {
            format!("{}:{}:{}", self.mode, self.kind, self.oid)
        }
    }
}

fn run_git(repo_root: &Path, args: &[&str]) -> Result<String, String> {
    let result = Command::new("git")
        .arg("-C")
        .arg(repo_root)
        .args(args)
        .output()
        .map_err(|error| format!("could not execute git: {error}"))?;
    if !result.status.success() {
        let stderr = String::from_utf8_lossy(&result.stderr).trim().to_string();
        return Err(format!(
            "git {} failed with status {:?}: {stderr}",
            args.join(" "),
            result.status
        ));
    }
    String::from_utf8(result.stdout)
        .map_err(|error| format!("git {} returned non-UTF-8 output: {error}", args.join(" ")))
        .map(|output| output.trim().to_string())
}

fn git_failure(message: String) -> i32 {
    eprintln!("agent-canon check-merge-structure: {message}");
    1
}
