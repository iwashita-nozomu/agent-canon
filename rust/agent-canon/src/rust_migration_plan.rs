// @dependency-start
// contract implementation
// responsibility Prints sequential Rust migration candidates for AgentCanon tools.
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// upstream design ../../../documents/runtime-log-archive.md hook and skill usage log archive policy
// downstream implementation ../../../tools/bin/agent-canon invokes this command through the CLI wrapper
// @dependency-end

use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_LIMIT: usize = 12;

const PORT_NOW_TARGETS: &[ToolTarget] = &[
    ToolTarget {
        name: "vector_search.py",
        path: "tools/agent_tools/vector_search.py",
        reason: "heavy repo-wide text search and ranking logic",
    },
    ToolTarget {
        name: "file_surface_inventory.py",
        path: "tools/agent_tools/file_surface_inventory.py",
        reason: "repo-wide filesystem classification with stable output schema",
    },
    ToolTarget {
        name: "helper_function_inventory.py",
        path: "tools/agent_tools/helper_function_inventory.py",
        reason: "AST inventory with deterministic checker behavior",
    },
    ToolTarget {
        name: "log_surface_inventory.py",
        path: "tools/agent_tools/log_surface_inventory.py",
        reason: "static log schema inventory across hooks, skills, and tools",
    },
    ToolTarget {
        name: "readability.py",
        path: "tools/oop/python/readability.py",
        reason:
            "hot hook-facing OOP checker that should reject bad edits before agent tokens are spent",
    },
    ToolTarget {
        name: "check_dependency_graph.sh",
        path: "tools/agent_tools/check_dependency_graph.sh",
        reason: "dependency graph traversal should become a single typed checker",
    },
];

const KEEP_PYTHON_TARGETS: &[ToolTarget] = &[
    ToolTarget {
        name: "bootstrap_agent_run.py",
        path: "tools/agent_tools/bootstrap_agent_run.py",
        reason: "workflow orchestration changes frequently and writes run bundles",
    },
    ToolTarget {
        name: "task_start.py",
        path: "tools/agent_tools/task_start.py",
        reason: "task bootstrap policy changes with agent protocol",
    },
    ToolTarget {
        name: "task_close.py",
        path: "tools/agent_tools/task_close.py",
        reason: "closeout policy is agent-facing and changes with workflow gates",
    },
    ToolTarget {
        name: "evaluate_agent_run.py",
        path: "tools/agent_tools/evaluate_agent_run.py",
        reason: "evaluation rubric remains easier to tune in Python",
    },
    ToolTarget {
        name: "agent_canon_update_todos.py",
        path: "tools/agent_tools/agent_canon_update_todos.py",
        reason: "parent-repo TODO protocol is still actively evolving",
    },
];

const COMPLETED_RUST_TARGETS: &[ToolTarget] = &[ToolTarget {
    name: "structured-analysis document-inventory",
    path: "tools/bin/agent-canon",
    reason: "document-canon inventory is owned by the Rust structured-analysis command; the old Python entrypoint is retired",
}];

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    limit: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ToolTarget {
    name: &'static str,
    path: &'static str,
    reason: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Candidate {
    name: String,
    path: String,
    class: &'static str,
    score: usize,
    reason: String,
    source: String,
}

#[derive(Debug, PartialEq, Eq)]
struct Plan {
    foundation: FoundationStatus,
    candidates: Vec<Candidate>,
    keep_python: Vec<Candidate>,
    completed: Vec<Candidate>,
    hook_log_count: usize,
}

#[derive(Debug, PartialEq, Eq)]
struct FoundationStatus {
    present: bool,
    missing: Vec<String>,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args) {
        Ok(parsed) => render(build_plan(&parsed.root, parsed.limit), &parsed.root),
        Err(message) => {
            eprintln!("RUST_MIGRATION_PLAN=fail");
            eprintln!("RUST_MIGRATION_PLAN_FINDING=invalid-arguments:{message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut root = PathBuf::from(".");
        let mut limit = DEFAULT_LIMIT;
        let mut index = 0;

        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    let value = args
                        .get(index + 1)
                        .ok_or_else(|| "--root requires a value".to_string())?;
                    root = PathBuf::from(value);
                    index += 2;
                }
                "--limit" => {
                    let value = args
                        .get(index + 1)
                        .ok_or_else(|| "--limit requires a value".to_string())?;
                    limit = value
                        .parse::<usize>()
                        .map_err(|_| format!("--limit must be a positive integer, got {value}"))?;
                    if limit == 0 {
                        return Err("--limit must be greater than zero".to_string());
                    }
                    index += 2;
                }
                unknown => return Err(format!("unknown argument {unknown}")),
            }
        }

        Ok(Self { root, limit })
    }
}

fn build_plan(root: &Path, limit: usize) -> Plan {
    let foundation = inspect_foundation(root);
    let (log_counts, hook_log_count) = collect_hook_tool_counts(root);
    let keep_names = target_names(KEEP_PYTHON_TARGETS);
    let port_names = target_names(PORT_NOW_TARGETS);
    let completed_names = target_names(COMPLETED_RUST_TARGETS);

    let mut candidates = Vec::new();
    for (index, target) in PORT_NOW_TARGETS.iter().enumerate() {
        let log_count = *log_counts.get(target.name).unwrap_or(&0);
        candidates.push(Candidate {
            name: target.name.to_string(),
            path: target.path.to_string(),
            class: "port-now",
            score: 1_000 - (index * 20) + (log_count * 10),
            reason: target.reason.to_string(),
            source: if log_count > 0 {
                "policy+hook-log".to_string()
            } else {
                "policy".to_string()
            },
        });
    }

    for (name, count) in log_counts {
        if port_names.contains(name.as_str())
            || keep_names.contains(name.as_str())
            || completed_names.contains(name.as_str())
        {
            continue;
        }
        candidates.push(Candidate {
            path: infer_tool_path(root, &name),
            class: "observe-before-port",
            score: count * 10,
            reason: "observed in hook or skill feedback logs; gather more stability evidence before porting"
                .to_string(),
            source: "hook-log".to_string(),
            name,
        });
    }

    candidates.sort_by(|left, right| {
        right
            .score
            .cmp(&left.score)
            .then_with(|| left.name.cmp(&right.name))
    });
    candidates.truncate(limit);

    let keep_python = KEEP_PYTHON_TARGETS
        .iter()
        .map(|target| Candidate {
            name: target.name.to_string(),
            path: target.path.to_string(),
            class: "keep-python",
            score: 0,
            reason: target.reason.to_string(),
            source: "policy".to_string(),
        })
        .collect();
    let completed = COMPLETED_RUST_TARGETS
        .iter()
        .map(|target| Candidate {
            name: target.name.to_string(),
            path: target.path.to_string(),
            class: "completed",
            score: 0,
            reason: target.reason.to_string(),
            source: "policy".to_string(),
        })
        .collect();

    Plan {
        foundation,
        candidates,
        keep_python,
        completed,
        hook_log_count,
    }
}

fn inspect_foundation(root: &Path) -> FoundationStatus {
    let mut missing = Vec::new();
    for relative in [
        "documents/rust-agent-tool-migration.md",
        "rust/agent-canon/Cargo.toml",
        "tools/bin/agent-canon",
    ] {
        if !root.join(relative).exists() {
            missing.push(format!("missing-path:{relative}"));
        }
    }

    let post_create = root.join(".devcontainer/post-create.sh");
    match fs::read_to_string(&post_create) {
        Ok(text) => {
            for snippet in [
                "rustup toolchain install",
                "cargo build --release",
                "${tools_home}/agent-canon/bin/agent-canon",
                "/usr/local/bin/agent-canon",
            ] {
                if !text.contains(snippet) {
                    missing.push(format!("post-create-missing:{snippet}"));
                }
            }
        }
        Err(_) => missing.push("missing-path:.devcontainer/post-create.sh".to_string()),
    }

    FoundationStatus {
        present: missing.is_empty(),
        missing,
    }
}

fn collect_hook_tool_counts(root: &Path) -> (BTreeMap<String, usize>, usize) {
    let mut counts = BTreeMap::new();
    let mut log_count = 0;

    for path in collect_jsonl_files(&root.join("agents/evals/results/hook-runs")) {
        log_count += 1;
        let Ok(text) = fs::read_to_string(path) else {
            continue;
        };
        for line in text.lines() {
            for tool in extract_string_array_field(line, "candidate_tools") {
                increment_tool_count(&mut counts, &tool);
            }
            for target in extract_string_array_field(line, "feedback_targets") {
                if let Some(tool) = target.strip_prefix("tool:") {
                    increment_tool_count(&mut counts, tool);
                }
            }
            if let Some(tool_name) = extract_string_field(line, "tool_name") {
                increment_tool_count(&mut counts, &tool_name);
            }
            for command_part in extract_string_array_field(line, "command") {
                if command_part.contains("/tools/") || command_part.starts_with("tools/") {
                    increment_tool_count(&mut counts, &command_part);
                }
            }
        }
    }

    (counts, log_count)
}

fn collect_jsonl_files(root: &Path) -> Vec<PathBuf> {
    let mut files = Vec::new();
    collect_jsonl_files_into(root, &mut files);
    files
}

fn collect_jsonl_files_into(root: &Path, files: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_jsonl_files_into(&path, files);
        } else if path
            .extension()
            .is_some_and(|extension| extension == "jsonl")
        {
            files.push(path);
        }
    }
}

fn increment_tool_count(counts: &mut BTreeMap<String, usize>, value: &str) {
    let Some(name) = normalize_tool_name(value) else {
        return;
    };
    *counts.entry(name).or_default() += 1;
}

fn normalize_tool_name(value: &str) -> Option<String> {
    let mut name = value.trim();
    if name.is_empty() {
        return None;
    }
    if let Some(stripped) = name.strip_prefix("tool:") {
        name = stripped;
    }
    if let Some((_, suffix)) = name.rsplit_once("/tools/") {
        name = suffix;
    }
    if let Some(stripped) = name.strip_prefix("tools/") {
        name = stripped;
    }
    if !name.ends_with(".py") && !name.ends_with(".sh") && !name.ends_with("agent-canon") {
        return None;
    }
    Some(
        name.rsplit('/')
            .next()
            .expect("split always returns a final component")
            .to_string(),
    )
}

fn extract_string_field(line: &str, field: &str) -> Option<String> {
    let marker = format!("\"{field}\":");
    let start = line.find(&marker)? + marker.len();
    let tail = &line[start..];
    let quote_index = tail.find('"')?;
    parse_json_string_at(tail, quote_index).map(|(value, _)| value)
}

fn extract_string_array_field(line: &str, field: &str) -> Vec<String> {
    let marker = format!("\"{field}\":");
    let Some(start) = line.find(&marker) else {
        return Vec::new();
    };
    let tail = &line[start + marker.len()..];
    let Some(array_start) = tail.find('[') else {
        return Vec::new();
    };
    let array_tail = &tail[array_start + 1..];
    let Some(array_end) = array_tail.find(']') else {
        return Vec::new();
    };
    let array = &array_tail[..array_end];

    let mut values = Vec::new();
    let mut index = 0;
    while index < array.len() {
        let Some(next_quote) = array[index..].find('"') else {
            break;
        };
        let string_start = index + next_quote;
        if let Some((value, next_index)) = parse_json_string_at(array, string_start) {
            values.push(value);
            index = next_index;
        } else {
            break;
        }
    }

    values
}

fn parse_json_string_at(text: &str, start: usize) -> Option<(String, usize)> {
    let bytes = text.as_bytes();
    if *bytes.get(start)? != b'"' {
        return None;
    }

    let mut index = start + 1;
    let mut value = String::new();
    while index < bytes.len() {
        match bytes[index] {
            b'\\' => {
                let escaped = *bytes.get(index + 1)?;
                value.push(escaped as char);
                index += 2;
            }
            b'"' => return Some((value, index + 1)),
            byte => {
                value.push(byte as char);
                index += 1;
            }
        }
    }

    None
}

fn infer_tool_path(root: &Path, name: &str) -> String {
    for prefix in [
        "tools/agent_tools",
        "tools/ci",
        "tools/docs",
        "tools/oop/python",
    ] {
        let path = format!("{prefix}/{name}");
        if root.join(&path).exists() {
            return path;
        }
    }
    format!("tools/<unknown>/{name}")
}

fn target_names(targets: &[ToolTarget]) -> HashSet<&'static str> {
    targets.iter().map(|target| target.name).collect()
}

fn render(plan: Plan, root: &Path) -> i32 {
    println!("RUST_MIGRATION_PLAN=pass");
    println!("RUST_MIGRATION_SOURCE_ROOT={}", root.display());
    println!(
        "RUST_MIGRATION_FOUNDATION={}",
        if plan.foundation.present {
            "present"
        } else {
            "missing"
        }
    );
    for finding in plan.foundation.missing {
        println!("RUST_MIGRATION_FOUNDATION_FINDING={finding}");
    }
    println!("RUST_MIGRATION_HOOK_LOG_FILES={}", plan.hook_log_count);
    println!("RUST_MIGRATION_CANDIDATE_COUNT={}", plan.candidates.len());
    for (index, candidate) in plan.candidates.iter().enumerate() {
        println!(
            "RUST_MIGRATION_CANDIDATE=rank={} class={} score={} name={} path={} source={} reason={}",
            index + 1,
            candidate.class,
            candidate.score,
            candidate.name,
            candidate.path,
            candidate.source,
            candidate.reason
        );
    }
    for candidate in plan.keep_python {
        println!(
            "RUST_MIGRATION_KEEP_PYTHON=name={} path={} reason={}",
            candidate.name, candidate.path, candidate.reason
        );
    }
    for candidate in plan.completed {
        println!(
            "RUST_MIGRATION_COMPLETED=name={} path={} reason={}",
            candidate.name, candidate.path, candidate.reason
        );
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn parse_defaults() {
        let parsed = Args::parse(&[]).expect("defaults should parse");
        assert_eq!(parsed.root, PathBuf::from("."));
        assert_eq!(parsed.limit, DEFAULT_LIMIT);
    }

    #[test]
    fn plan_includes_policy_first_target() {
        let root = make_fixture_root();
        write_foundation(&root);

        let plan = build_plan(&root, 3);

        assert_eq!(plan.candidates[0].name, "vector_search.py");
        assert_eq!(plan.candidates[0].class, "port-now");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn plan_counts_hook_candidate_tools() {
        let root = make_fixture_root();
        write_foundation(&root);
        write(
            &root,
            "agents/evals/results/hook-runs/example/skill_usage.jsonl",
            r#"{"candidate_tools":["skill_usage_logger.py","vector_search.py"],"feedback_targets":["tool:skill_usage_logger.py"],"tool_name":"workflow_monitor.py"}"#,
        );

        let plan = build_plan(&root, 10);

        let skill_logger = plan
            .candidates
            .iter()
            .find(|candidate| candidate.name == "skill_usage_logger.py")
            .expect("hook candidate should be included");
        assert_eq!(skill_logger.class, "observe-before-port");
        assert_eq!(skill_logger.score, 20);
        assert_eq!(plan.hook_log_count, 1);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn plan_keeps_orchestration_python() {
        let root = make_fixture_root();
        write_foundation(&root);

        let plan = build_plan(&root, 10);

        assert!(plan
            .keep_python
            .iter()
            .any(|candidate| candidate.name == "task_close.py"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn plan_marks_document_inventory_completed() {
        let root = make_fixture_root();
        write_foundation(&root);

        let plan = build_plan(&root, 10);

        assert!(plan
            .completed
            .iter()
            .any(|candidate| candidate.name == "structured-analysis document-inventory"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn foundation_reports_missing_post_create() {
        let root = make_fixture_root();
        write(&root, "documents/rust-agent-tool-migration.md", "fixture\n");
        write(&root, "rust/agent-canon/Cargo.toml", "fixture\n");
        write(&root, "tools/bin/agent-canon", "fixture\n");

        let foundation = inspect_foundation(&root);

        assert!(!foundation.present);
        assert!(foundation
            .missing
            .contains(&"missing-path:.devcontainer/post-create.sh".to_string()));
        let _ = fs::remove_dir_all(root);
    }

    fn make_fixture_root() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("agent-canon-rust-plan-{suffix}"))
    }

    fn write_foundation(root: &Path) {
        write(root, "documents/rust-agent-tool-migration.md", "fixture\n");
        write(root, "rust/agent-canon/Cargo.toml", "fixture\n");
        write(root, "tools/bin/agent-canon", "fixture\n");
        write(
            root,
            ".devcontainer/post-create.sh",
            "tools_home=\"${AGENT_CANON_TOOLS_HOME:-${HOME}/.tools}\"\nrustup toolchain install\ncargo build --release\n${tools_home}/agent-canon/bin/agent-canon\n/usr/local/bin/agent-canon\n",
        );
    }

    fn write(root: &Path, relative: &str, text: &str) {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().expect("fixture path has parent")).expect("mkdir");
        fs::write(path, text).expect("write fixture");
    }
}
