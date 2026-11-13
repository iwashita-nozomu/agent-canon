//! Native host owner for the AgentCanon runtime-log archive.
mod context_discovery;
mod github_eval_delivery;
mod hook_spool;
mod runtime_event;
// @dependency-start
// contract implementation
// responsibility Owns archive path/identity resolution, bounded Git branch lifecycle, immutable runtime-event publication, and source-bound archive readback.
// upstream design ../../../../../documents/runtime/runtime-log-archive.md archive branch, spool, publication, and privacy contract
// upstream design ../../../../../documents/runtime/runtime-log-archive-migration.md explicit legacy source migration contract
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/runtime_boundary.rs owns external runtime and spool capabilities
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/source_mutation.rs owns exact source deletion capabilities
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/log_repository_identity.rs owns stable source identity
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/eval_archive_paths.rs owns mounted archive and spool path projection
// upstream implementation ../../../../../tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs owns generated report and review checks
// downstream implementation main.rs exposes the native runtime-log-archive-git CLI
// downstream implementation ../../../../../bootstrap/host/lifecycle/entrypoint.sh invokes archive-eval on the host adapter
// downstream test ../tests/runtime_log_archive_native.rs validates archive command/output behavior
// @dependency-end

use agent_canon::authority::{
    AttestationRequest, AttestedParent, NonEmptyTrimmedString, Nonce128, ParentRootAttestor,
};
use agent_canon::eval_archive_paths;
use agent_canon::log_repository_identity::{
    UNIDENTIFIED_SOURCE, normalize_remote, source_remote, stable_source_id_from_runtime_env,
};
use agent_canon::runtime_boundary::{
    RUNTIME_ROOT_ENV, RuntimeArtifactBoundary, RuntimeFileLock, RuntimeSpoolBoundary,
    resolve_external_artifact_path,
};
use agent_canon::source_mutation::SourceMutationCapability;
use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt};
use cap_std::ambient_authority;
use cap_std::fs::{Dir, OpenOptions};
use regex::bytes::Regex as BytesRegex;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::ffi::OsStr;
use std::fmt;
use std::fs;
use std::io;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output};
use std::sync::OnceLock;
use std::thread;
use std::time::Duration;

const TOOL_NAME: &str = "runtime_log_archive_git.py";
const LOG_ARCHIVE_REMOTE: &str = "git@github.com:iwashita-nozomu/agent-canon-log.git";
const DEFAULT_COMMIT_NAME: &str = "AgentCanon Log Archive";
const DEFAULT_COMMIT_EMAIL: &str = "agent-canon-log@example.invalid";
const BRANCH_SWITCH_COMMIT_MESSAGE: &str = "Preserve managed runtime logs before branch switch";
const GIT_INDEX_LOCK_RETRIES: usize = 5;
const GIT_INDEX_LOCK_RETRY_MILLIS: u64 = 1_000;
const REPO_KEYED_ARCHIVE_FAMILIES: &[&str] = &["agent-reports", "codex-runtime", "hook-runs"];
const MANAGED_GLOBAL_ARCHIVE_FAMILIES: &[&str] = &["eval-results", "legacy-import", "feedback"];
const DEFAULT_AGENT_REPORT_DESTINATION: &str = "agent-reports";
const DEFAULT_AGENT_REPORT_MAX_FILE_BYTES: i64 = 10 * 1024 * 1024;
const AGENT_REPORT_ARCHIVE_SCHEMA: &str = "agent-report-snapshot.v1";
const AGENT_REPORT_PROVENANCE_ARCHIVE_SCHEMA: &str = AGENT_REPORT_ARCHIVE_SCHEMA;
const AGENT_REPORT_PROVENANCE_SCHEMA: &str = "agent-canon-log-report-provenance.v1";
const REPORT_SNAPSHOT_DIGEST_CHARS: usize = 64;
const ARCHIVE_TRANSACTION_LOCK_RELATIVE: &str = "locks/archive-transaction.lock";

const COMMANDS: &[&str] = &[
    "append-context-discovery",
    "materialize-runtime-event",
    "repo-key",
    "ensure",
    "status",
    "check-clean",
    "archive-agent-reports",
    "import-legacy",
    "import-eval-results",
    "archive-eval",
    "archive-agent-report",
    "push",
    "sync",
];

const USAGE: &str = "usage: runtime_log_archive_git.py [-h] [--source-root SOURCE_ROOT] [--canon-root CANON_ROOT] [--remote REMOTE] [--archive-root ARCHIVE_ROOT] [--runtime-root RUNTIME_ROOT] {append-context-discovery,materialize-runtime-event,repo-key,ensure,status,check-clean,archive-agent-reports,import-legacy,import-eval-results,archive-eval,archive-agent-report,push,sync} ...";

#[derive(Debug)]
struct ArchiveError {
    code: String,
    detail: String,
}

impl ArchiveError {
    fn new(code: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            detail: detail.into(),
        }
    }

    fn usage(detail: impl Into<String>) -> Self {
        Self::new("usage", detail)
    }
}

impl fmt::Display for ArchiveError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

#[derive(Debug, Clone)]
struct ArchiveContext {
    source_root: PathBuf,
    canon_root: PathBuf,
    archive_root: PathBuf,
    repo_key: String,
    env_key: String,
    branch_key: String,
    branch: String,
    remote: String,
    runtime_root: Option<PathBuf>,
    parent_root: Option<PathBuf>,
}

#[derive(Debug, Clone, Default)]
struct ArchiveStatusSummary {
    current_branch: String,
    dirty: bool,
    branch_matches: bool,
    dirty_keys: Vec<String>,
    current_key_dirty: bool,
    foreign_dirty_keys: Vec<String>,
    tree_keys: Vec<String>,
    foreign_tree_keys: Vec<String>,
    global_dirty: bool,
}

struct PreparedArchiveTransaction {
    context: ArchiveContext,
    _lock: RuntimeFileLock,
    archive_head_before: String,
    ensured_branch: String,
}

#[derive(Debug, Clone)]
struct ArchivePublicationReceipt {
    status: String,
    commit_created: bool,
    pushed: bool,
    archive_commit_oid: String,
    archive_tree_oid: String,
    dedup_index_sha256: String,
    cursor_sha256: String,
    push_status: String,
}

#[derive(Clone)]
struct LegacyImportRecord {
    source: PathBuf,
    source_relative: String,
    destination: Option<String>,
    byte_count: usize,
    sha256: String,
}

struct LegacyImportPlan {
    family: String,
    index_path: PathBuf,
    inventory_sha256: String,
    records: Vec<LegacyImportRecord>,
    delete_source: bool,
}

struct AgentReportArchiveSummary {
    report_root: PathBuf,
    destination: PathBuf,
    files: usize,
    copied: usize,
    updated: usize,
    existing: usize,
    skipped: usize,
}

#[derive(Default)]
struct GlobalOptions {
    source_root: Option<PathBuf>,
    canon_root: Option<PathBuf>,
    remote: Option<String>,
    archive_root: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
}

struct ParsedArchiveCommand {
    global: GlobalOptions,
    command: String,
    args: Vec<String>,
}

#[derive(Default)]
struct CommandOptions {
    values: BTreeMap<String, String>,
    flags: BTreeSet<String>,
}

impl CommandOptions {
    fn value(&self, name: &str) -> Option<&str> {
        self.values.get(name).map(String::as_str)
    }

    fn required(&self, name: &str) -> Result<&str, ArchiveError> {
        self.value(name).ok_or_else(|| {
            ArchiveError::usage(format!("the following arguments are required: {name}"))
        })
    }

    fn flag(&self, name: &str) -> bool {
        self.flags.contains(name)
    }
}

fn source_root_fallback() -> PathBuf {
    env::var_os("AGENT_CANON_SOURCE_ROOT")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../../"))
}

fn source_identity_environment() -> BTreeMap<String, String> {
    [
        agent_canon::log_repository_identity::SOURCE_REMOTE_ENV,
        agent_canon::log_repository_identity::SOURCE_REMOTE_NAME_ENV,
        agent_canon::log_repository_identity::STABLE_ID_ENV,
    ]
    .into_iter()
    .filter_map(|name| env::var(name).ok().map(|value| (name.to_owned(), value)))
    .collect()
}

fn parse_option_value(value: &str) -> (&str, Option<&str>) {
    value
        .split_once('=')
        .map_or((value, None), |(name, value)| (name, Some(value)))
}

fn resolve_option<'a>(
    value: &'a str,
    options: &'a [(&'a str, usize)],
) -> Result<usize, ArchiveError> {
    crate::python_cli_options::resolve_long_option_prefix(value, options).map_err(|error| {
        let detail = match error {
            crate::python_cli_options::LongOptionError::Unrecognized => {
                format!("unrecognized arguments: {value}")
            }
            crate::python_cli_options::LongOptionError::Ambiguous(matches) => format!(
                "ambiguous option: {value} could match {}",
                matches.join(", ")
            ),
        };
        ArchiveError::usage(detail)
    })
}

fn parse_command(args: &[String]) -> Result<ParsedArchiveCommand, ArchiveError> {
    const GLOBAL_OPTIONS: &[(&str, usize)] = &[
        ("--source-root", 0),
        ("--canon-root", 1),
        ("--remote", 2),
        ("--archive-root", 3),
        ("--runtime-root", 4),
    ];
    let mut global = GlobalOptions::default();
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if token == "-h" || token == "--help" {
            return Err(ArchiveError::new("help", "global"));
        }
        if !token.starts_with("--") {
            break;
        }
        let (name, inline) = parse_option_value(token);
        let option = resolve_option(name, GLOBAL_OPTIONS)?;
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            args.get(index).cloned().ok_or_else(|| {
                ArchiveError::usage(format!("argument {name}: expected one argument"))
            })?
        };
        match option {
            0 => global.source_root = Some(PathBuf::from(value)),
            1 => global.canon_root = Some(PathBuf::from(value)),
            2 => global.remote = Some(value),
            3 => global.archive_root = Some(PathBuf::from(value)),
            4 => global.runtime_root = Some(PathBuf::from(value)),
            _ => unreachable!(),
        }
        index += 1;
    }
    let command = args
        .get(index)
        .ok_or_else(|| ArchiveError::usage("the following arguments are required: command"))?
        .clone();
    if command == "-h" || command == "--help" {
        return Err(ArchiveError::new("help", "global"));
    }
    if !COMMANDS.contains(&command.as_str()) {
        return Err(ArchiveError::usage(format!("invalid choice: '{command}'")));
    }
    Ok(ParsedArchiveCommand {
        global,
        command,
        args: args[index + 1..].to_vec(),
    })
}

fn command_option_specs(
    command: &str,
) -> (
    &'static [(&'static str, &'static str)],
    &'static [&'static str],
) {
    match command {
        "append-context-discovery" => (
            &[
                ("--run-id", "run-id"),
                ("--agent-context-id", "agent-context-id"),
                ("--turn-id", "turn-id"),
            ],
            &[],
        ),
        "materialize-runtime-event" => (
            &[
                ("--result-family", "result-family"),
                ("--run-id", "run-id"),
                ("--gate-id", "gate-id"),
                ("--base-ref", "base-ref"),
                ("--unit-id", "unit-id"),
            ],
            &[],
        ),
        "ensure" => (&[], &["--no-fetch"]),
        "status" | "check-clean" => (&[], &["--porcelain"]),
        "archive-agent-reports" => (
            &[
                ("--report-root", "report-root"),
                ("--destination-prefix", "destination-prefix"),
                ("--max-file-bytes", "max-file-bytes"),
            ],
            &[],
        ),
        "import-legacy" | "import-eval-results" => (
            &[
                ("--legacy-root", "legacy-root"),
                ("--destination-prefix", "destination-prefix"),
            ],
            &["--delete-source"],
        ),
        "archive-eval" => (
            &[("--spool-root", "spool-root"), ("--run-id", "run-id")],
            &[],
        ),
        "archive-agent-report" => (
            &[
                ("--report-dir", "report-dir"),
                ("--provenance", "provenance"),
                ("--message", "message"),
            ],
            &["--publish", "--no-pull"],
        ),
        "push" => (&[("--message", "message")], &["--no-pull"]),
        "sync" => (
            &[
                ("--message", "message"),
                ("--report-root", "report-root"),
                ("--max-file-bytes", "max-file-bytes"),
            ],
            &[
                "--no-pull",
                "--no-push",
                "--no-agent-reports",
                "--include-main-evals",
            ],
        ),
        _ => (&[], &[]),
    }
}

fn parse_subcommand_options(
    command: &str,
    args: &[String],
) -> Result<CommandOptions, ArchiveError> {
    let (value_options, flags) = command_option_specs(command);
    let mut options = value_options
        .iter()
        .enumerate()
        .map(|(index, (name, _))| (*name, index))
        .collect::<Vec<_>>();
    options.extend(
        flags
            .iter()
            .enumerate()
            .map(|(index, name)| (*name, value_options.len() + index)),
    );
    let mut parsed = CommandOptions::default();
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if token == "-h" || token == "--help" {
            return Err(ArchiveError::new("help", command.to_owned()));
        }
        if !token.starts_with("--") {
            return Err(ArchiveError::usage(format!(
                "unrecognized arguments: {token}"
            )));
        }
        let (name, inline) = parse_option_value(token);
        let option = resolve_option(name, &options)?;
        if option >= value_options.len() {
            let flag = flags[option - value_options.len()];
            if inline.is_some() {
                return Err(ArchiveError::usage(format!(
                    "argument {flag}: ignored explicit argument"
                )));
            }
            parsed.flags.insert(flag.to_owned());
            index += 1;
            continue;
        }
        let (canonical, key) = value_options[option];
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            args.get(index)
                .cloned()
                .filter(|value| !value.starts_with("--"))
                .ok_or_else(|| {
                    ArchiveError::usage(format!("argument {canonical}: expected one argument"))
                })?
        };
        parsed.values.insert(key.to_owned(), value);
        index += 1;
    }
    for name in required_subcommand_options(command) {
        if parsed.value(name).is_none() {
            return Err(ArchiveError::usage(format!(
                "the following arguments are required: --{name}"
            )));
        }
    }
    Ok(parsed)
}

fn required_subcommand_options(command: &str) -> &'static [&'static str] {
    match command {
        "append-context-discovery" => &["run-id", "agent-context-id", "turn-id"],
        "materialize-runtime-event" => &["result-family", "run-id", "gate-id", "base-ref"],
        "archive-eval" => &["spool-root", "run-id"],
        "archive-agent-report" => &["report-dir"],
        _ => &[],
    }
}

fn print_global_help() {
    println!(
        "{USAGE}\n\nManage the external AgentCanon runtime log archive Git repository.\n\ncommands:\n  {}",
        COMMANDS.join("\n  ")
    );
}

fn print_subcommand_help(command: &str) {
    println!("usage: {TOOL_NAME} {command} [options]");
}

pub(crate) fn run(args: &[String]) -> i32 {
    let parsed = match parse_command(args) {
        Ok(parsed) => parsed,
        Err(error) if error.code == "help" => {
            print_global_help();
            return 0;
        }
        Err(error) => return print_archive_error(error),
    };
    let command_options = match parse_subcommand_options(&parsed.command, &parsed.args) {
        Ok(options) => options,
        Err(error) if error.code == "help" => {
            print_subcommand_help(&parsed.command);
            return 0;
        }
        Err(error) => return print_archive_error(error),
    };
    let context = match build_context(&parsed.global) {
        Ok(context) => context,
        Err(error) => return print_archive_error(error),
    };
    match parsed.command.as_str() {
        "append-context-discovery" => match context_discovery::append(&context, &command_options) {
            Ok(code) => code,
            Err(error) => {
                println!("CONTEXT_DISCOVERY_ERROR_CODE={}", error.code);
                println!("CONTEXT_DISCOVERY_APPEND=fail");
                1
            }
        },
        "materialize-runtime-event" => match runtime_event::materialize(&context, &command_options)
        {
            Ok(code) => code,
            Err(error) => {
                println!("RUNTIME_EVENT_ERROR_CODE={}", error.code);
                println!("RUNTIME_EVENT_MATERIALIZE=fail");
                1
            }
        },
        "repo-key" => command_repo_key(&context),
        "ensure" => command_ensure(&context, command_options.flag("--no-fetch"))
            .unwrap_or_else(print_archive_error),
        "status" => command_status(&context, command_options.flag("--porcelain"))
            .unwrap_or_else(print_archive_error),
        "check-clean" => command_check_clean(&context, command_options.flag("--porcelain"))
            .unwrap_or_else(print_archive_error),
        "archive-eval" => command_archive_eval(&context, &command_options, false)
            .unwrap_or_else(print_archive_error),
        "import-legacy" => {
            command_import_legacy(&context, &command_options).unwrap_or_else(print_archive_error)
        }
        "import-eval-results" => command_import_eval_results(&context, &command_options)
            .unwrap_or_else(print_archive_error),
        "archive-agent-report" => command_archive_agent_report(&context, &command_options)
            .unwrap_or_else(print_archive_error),
        "archive-agent-reports" => command_archive_agent_reports(&context, &command_options)
            .unwrap_or_else(print_archive_error),
        "push" => command_push(
            &context,
            command_options.value("message"),
            command_options.flag("--no-pull"),
        )
        .unwrap_or_else(print_archive_error),
        "sync" => command_sync(&context, &command_options).unwrap_or_else(print_archive_error),
        command => {
            let _ = command_options;
            print_archive_error(ArchiveError::new(
                "archive_operation_unavailable",
                format!("native archive operation has not been registered: {command}"),
            ))
        }
    }
}

fn print_archive_error(error: ArchiveError) -> i32 {
    if error.code == "usage" {
        eprintln!("{USAGE}");
        eprintln!("{TOOL_NAME}: error: {}", error.detail);
        return 2;
    }
    let code = if error.code == "source_identity_preflight_failed" {
        format!("source_identity_preflight_failed:{}", error.detail)
    } else {
        error.code.clone()
    };
    if code.starts_with("source_identity_preflight_failed:")
        || code.chars().all(|character| {
            character.is_ascii_lowercase() || character.is_ascii_digit() || character == '_'
        })
    {
        println!("RUNTIME_LOG_ARCHIVE_ERROR_CODE={code}");
    }
    println!("RUNTIME_LOG_ARCHIVE_ERROR={}: {}", error.code, error.detail);
    println!("RUNTIME_LOG_ARCHIVE=fail");
    1
}

fn build_context(options: &GlobalOptions) -> Result<ArchiveContext, ArchiveError> {
    let canon_input = options
        .canon_root
        .clone()
        .unwrap_or_else(source_root_fallback);
    let canon_root = agent_canon::path_resolution::resolve_non_strict(&canon_input)
        .map_err(|error| ArchiveError::new("canon_root_invalid", error))?;
    let source_input = options
        .source_root
        .clone()
        .unwrap_or_else(|| canon_root.clone());
    let source_root = agent_canon::path_resolution::resolve_non_strict(&source_input)
        .map_err(|error| ArchiveError::new("source_root_invalid", error))?;
    let runtime_root = options
        .runtime_root
        .clone()
        .map(|path| agent_canon::path_resolution::resolve_non_strict(&path))
        .transpose()
        .map_err(|error| ArchiveError::new("runtime_root_invalid", error))?;
    let remote = options
        .remote
        .clone()
        .unwrap_or_else(|| LOG_ARCHIVE_REMOTE.to_owned());
    let archive_root = if let Some(path) = &options.archive_root {
        let path = agent_canon::path_resolution::resolve_non_strict(path)
            .map_err(|error| ArchiveError::new("archive_root_invalid", error))?;
        resolve_external_artifact_path(&canon_root, &path)
            .map_err(|error| ArchiveError::new("archive_root_invalid", error))?
    } else {
        eval_archive_paths::mounted_log_archive_root(&canon_root, runtime_root.as_deref())
            .map_err(|error| ArchiveError::new("archive_root_invalid", error))?
    };
    if archive_root == source_root || archive_root.starts_with(&source_root) {
        return Err(ArchiveError::new(
            "archive_root_invalid",
            format!(
                "runtime-log-archive must be external to source root: source={} archive={}",
                source_root.display(),
                archive_root.display()
            ),
        ));
    }
    let source_remote = source_remote(&source_root).map_err(|error| {
        ArchiveError::new("source_identity_preflight_failed", error.to_string())
    })?;
    let identity_environment = source_identity_environment();
    let repo_key = stable_source_id_from_runtime_env(Some(&source_root), &identity_environment)
        .map_err(|error| {
            ArchiveError::new("source_identity_preflight_failed", error.to_string())
        })?;
    if repo_key == UNIDENTIFIED_SOURCE {
        return Err(ArchiveError::new(
            "source_identity_preflight_failed",
            "source remote identity is unavailable",
        ));
    }
    normalize_remote(&source_remote).map_err(|error| {
        ArchiveError::new("source_identity_preflight_failed", error.to_string())
    })?;
    let branch_key = repo_key.clone();
    let branch = format!("logs/{branch_key}");
    let env_key = eval_archive_paths::log_environment_key(&canon_root);
    let parent_root = env::var_os("AGENT_CANON_PARENT_ROOT")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .map(|path| agent_canon::path_resolution::resolve_non_strict(&path))
        .transpose()
        .map_err(|error| ArchiveError::new("parent_root_invalid", error))?;
    if let Some(parent_root) = &parent_root {
        if archive_root != *parent_root && !archive_root.starts_with(parent_root) {
            return Err(ArchiveError::new(
                "parent_root_path_rejected",
                format!(
                    "archive root is outside the attested parent: {}",
                    archive_root.display()
                ),
            ));
        }
    }
    let mut context = ArchiveContext {
        source_root,
        canon_root,
        archive_root,
        repo_key,
        env_key,
        branch_key,
        branch,
        remote,
        runtime_root,
        parent_root,
    };
    context.archive_root =
        parent_owned_path(&context, &context.archive_root, "runtime-log-archive")?;
    Ok(context)
}

fn run_process(cwd: &Path, program: &str, args: &[String]) -> Result<Output, ArchiveError> {
    Command::new(program)
        .args(args)
        .current_dir(cwd)
        .output()
        .map_err(|error| ArchiveError::new("process_unavailable", format!("{program}: {error}")))
}

fn git(archive_root: &Path, args: &[String], check: bool) -> Result<Output, ArchiveError> {
    let mut command = vec!["-C".to_owned(), archive_root.display().to_string()];
    command.extend_from_slice(args);
    let cwd = archive_root.parent().unwrap_or_else(|| Path::new("/"));
    for attempt in 0..=GIT_INDEX_LOCK_RETRIES {
        let result = run_process(cwd, "git", &command)?;
        if result.status.success()
            || !git_index_locked(&result)
            || attempt == GIT_INDEX_LOCK_RETRIES
        {
            if check && !result.status.success() {
                let detail = output_bytes_text(&result.stderr);
                let detail = if detail.trim().is_empty() {
                    output_bytes_text(&result.stdout)
                } else {
                    detail
                };
                return Err(ArchiveError::new(
                    "git_command_failed",
                    format!("git {} failed: {}", args.join(" "), detail.trim()),
                ));
            }
            return Ok(result);
        }
        thread::sleep(Duration::from_millis(GIT_INDEX_LOCK_RETRY_MILLIS));
    }
    Err(ArchiveError::new("git_command_failed", args.join(" ")))
}

fn git_index_locked(result: &Output) -> bool {
    let detail = [result.stderr.as_slice(), result.stdout.as_slice()].concat();
    detail
        .windows(b"index.lock".len())
        .any(|window| window == b"index.lock")
}

fn output_text(output: &Output) -> String {
    output_bytes_text(&output.stdout)
}

fn output_bytes_text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

fn attest_parent(context: &ArchiveContext) -> Result<Option<AttestedParent>, ArchiveError> {
    let Some(parent_root) = &context.parent_root else {
        return Ok(None);
    };
    let purpose = NonEmptyTrimmedString::new("runtime-log-archive")
        .map_err(|error| ArchiveError::new("parent_root_invalid", error.to_string()))?;
    let nonce = Nonce128::generate()
        .map_err(|error| ArchiveError::new("parent_root_invalid", error.to_string()))?;
    let request = AttestationRequest {
        cwd: parent_root.clone(),
        explicit_root: Some(parent_root.clone()),
        source_root: Some(context.canon_root.clone()),
        clone_root: None,
        topic_marker: None,
        gitmodules: None,
        owner_evidence: None,
        expected_remote: None,
        expected_module_digest: None,
        child_handoff_token: None,
        purpose,
        nonce,
    };
    ParentRootAttestor::new()
        .attest(&request)
        .map(Some)
        .map_err(|error| {
            ArchiveError::new(
                "parent_root_invalid",
                format!("{}:{}", error.reject, error.detail()),
            )
        })
}

fn parent_owned_path(
    context: &ArchiveContext,
    path: &Path,
    purpose: &str,
) -> Result<PathBuf, ArchiveError> {
    let Some(attested) = attest_parent(context)? else {
        return Ok(path.to_path_buf());
    };
    let purpose = NonEmptyTrimmedString::new(purpose)
        .map_err(|error| ArchiveError::new("parent_root_path_rejected", error.to_string()))?;
    attested
        .resolve_parent_owned_path(path, purpose)
        .map(|receipt| receipt.physical_path().to_path_buf())
        .map_err(|error| {
            ArchiveError::new(
                "parent_root_path_rejected",
                format!("{}:{}", error.reject, error.detail()),
            )
        })
}

fn ensure_external_directory(
    context: &ArchiveContext,
    directory: &Path,
    purpose: &str,
) -> Result<PathBuf, ArchiveError> {
    let directory = parent_owned_path(context, directory, purpose)?;
    let (boundary_root, relative) = if let Some(parent_root) = &context.parent_root {
        let parent_root = agent_canon::path_resolution::resolve_non_strict(parent_root)
            .map_err(|error| ArchiveError::new("parent_root_invalid", error))?;
        let relative = directory.strip_prefix(&parent_root).map_err(|_| {
            ArchiveError::new(
                "parent_root_path_rejected",
                format!("path escapes attested parent: {}", directory.display()),
            )
        })?;
        (parent_root, relative.to_path_buf())
    } else {
        let parent = directory
            .parent()
            .ok_or_else(|| ArchiveError::new("archive_root_invalid", "directory has no parent"))?;
        (parent.to_path_buf(), PathBuf::from("."))
    };
    let boundary =
        RuntimeArtifactBoundary::for_source(&context.canon_root, Some(&boundary_root), true)
            .map_err(|error| ArchiveError::new("archive_root_invalid", error))?;
    boundary
        .ensure_directory(&relative)
        .map_err(|error| ArchiveError::new("archive_root_invalid", error))
}

fn is_archive_clone(path: &Path) -> bool {
    fs::symlink_metadata(path.join(".git")).is_ok_and(|metadata| {
        !metadata.file_type().is_symlink() && (metadata.is_dir() || metadata.is_file())
    })
}

fn remote_branch_exists(context: &ArchiveContext, branch: &str) -> Result<bool, ArchiveError> {
    let result = git(
        &context.archive_root,
        &[
            "rev-parse".to_owned(),
            "--verify".to_owned(),
            format!("origin/{branch}"),
        ],
        false,
    )?;
    Ok(result.status.success())
}

fn local_branch_exists(context: &ArchiveContext, branch: &str) -> Result<bool, ArchiveError> {
    let result = git(
        &context.archive_root,
        &[
            "rev-parse".to_owned(),
            "--verify".to_owned(),
            branch.to_owned(),
        ],
        false,
    )?;
    Ok(result.status.success())
}

fn ensure_origin(context: &ArchiveContext) -> Result<(), ArchiveError> {
    let remote = git(
        &context.archive_root,
        &[
            "remote".to_owned(),
            "get-url".to_owned(),
            "origin".to_owned(),
        ],
        false,
    )?;
    if !remote.status.success() {
        git(
            &context.archive_root,
            &[
                "remote".to_owned(),
                "add".to_owned(),
                "origin".to_owned(),
                context.remote.clone(),
            ],
            true,
        )?;
    } else if output_text(&remote).trim() != context.remote {
        git(
            &context.archive_root,
            &[
                "remote".to_owned(),
                "set-url".to_owned(),
                "origin".to_owned(),
                context.remote.clone(),
            ],
            true,
        )?;
    }
    Ok(())
}

fn switch_to_archive_branch(context: &ArchiveContext, branch: &str) -> Result<(), ArchiveError> {
    if local_branch_exists(context, branch)? {
        git(
            &context.archive_root,
            &["switch".to_owned(), branch.to_owned()],
            true,
        )?;
    } else if remote_branch_exists(context, branch)? {
        git(
            &context.archive_root,
            &[
                "switch".to_owned(),
                "--track".to_owned(),
                "-c".to_owned(),
                branch.to_owned(),
                format!("origin/{branch}"),
            ],
            true,
        )?;
    } else if remote_branch_exists(context, "main")? {
        git(
            &context.archive_root,
            &[
                "switch".to_owned(),
                "-c".to_owned(),
                branch.to_owned(),
                "origin/main".to_owned(),
            ],
            true,
        )?;
    } else {
        git(
            &context.archive_root,
            &["switch".to_owned(), "-c".to_owned(), branch.to_owned()],
            true,
        )?;
    }
    Ok(())
}

fn ensure_commit_identity(context: &ArchiveContext) -> Result<(), ArchiveError> {
    let name = git(
        &context.archive_root,
        &[
            "config".to_owned(),
            "--get".to_owned(),
            "user.name".to_owned(),
        ],
        false,
    )?;
    if !name.status.success() || output_text(&name).trim().is_empty() {
        git(
            &context.archive_root,
            &[
                "config".to_owned(),
                "user.name".to_owned(),
                DEFAULT_COMMIT_NAME.to_owned(),
            ],
            true,
        )?;
    }
    let email = git(
        &context.archive_root,
        &[
            "config".to_owned(),
            "--get".to_owned(),
            "user.email".to_owned(),
        ],
        false,
    )?;
    if !email.status.success() || output_text(&email).trim().is_empty() {
        git(
            &context.archive_root,
            &[
                "config".to_owned(),
                "user.email".to_owned(),
                DEFAULT_COMMIT_EMAIL.to_owned(),
            ],
            true,
        )?;
    }
    Ok(())
}

fn preserve_managed_dirty_paths(
    context: &ArchiveContext,
    current: &str,
) -> Result<(), ArchiveError> {
    let paths = porcelain_status(context)?
        .lines()
        .map(porcelain_path)
        .filter(|path| !path.is_empty())
        .collect::<Vec<_>>();
    let unmanaged = paths
        .iter()
        .filter(|path| !managed_runtime_archive_path(path))
        .cloned()
        .collect::<Vec<_>>();
    if !unmanaged.is_empty() {
        return Err(ArchiveError::new(
            "archive_dirty_unmanaged",
            format!(
                "archive has non-runtime local changes on {current}: {}",
                unmanaged.join(", ")
            ),
        ));
    }
    if paths.is_empty() {
        return Ok(());
    }
    ensure_commit_identity(context)?;
    let mut add = vec!["add".to_owned(), "--".to_owned()];
    add.extend(paths);
    git(&context.archive_root, &add, true)?;
    let staged = git(
        &context.archive_root,
        &[
            "diff".to_owned(),
            "--cached".to_owned(),
            "--quiet".to_owned(),
        ],
        false,
    )?;
    if staged.status.code() != Some(0) {
        git(
            &context.archive_root,
            &[
                "commit".to_owned(),
                "-m".to_owned(),
                format!("{BRANCH_SWITCH_COMMIT_MESSAGE}: {current}"),
            ],
            true,
        )?;
    }
    Ok(())
}

fn ensure_archive(
    context: &ArchiveContext,
    fetch: bool,
    allow_branch_switch: bool,
) -> Result<String, ArchiveError> {
    let mut created = false;
    match fs::symlink_metadata(&context.archive_root) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            return Err(ArchiveError::new(
                "archive_root_invalid",
                format!(
                    "archive path is a symlink: {}",
                    context.archive_root.display()
                ),
            ));
        }
        Ok(metadata) if metadata.is_dir() && !is_archive_clone(&context.archive_root) => {
            let mut entries = fs::read_dir(&context.archive_root)
                .map_err(|error| ArchiveError::new("archive_root_invalid", error.to_string()))?;
            if entries.next().is_some() {
                return Err(ArchiveError::new(
                    "archive_root_invalid",
                    format!(
                        "archive path is not a Git clone: {}",
                        context.archive_root.display()
                    ),
                ));
            }
            fs::remove_dir(&context.archive_root)
                .map_err(|error| ArchiveError::new("archive_root_invalid", error.to_string()))?;
        }
        Ok(_) if !is_archive_clone(&context.archive_root) => {
            return Err(ArchiveError::new(
                "archive_root_invalid",
                format!(
                    "archive path is not a Git clone: {}",
                    context.archive_root.display()
                ),
            ));
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(ArchiveError::new("archive_root_invalid", error.to_string())),
        _ => {}
    }
    if !context.archive_root.exists() {
        let parent = context.archive_root.parent().ok_or_else(|| {
            ArchiveError::new("archive_root_invalid", "archive path has no parent")
        })?;
        ensure_external_directory(context, parent, "runtime-archive-clone")?;
        let clone = Command::new("git")
            .args(["clone", context.remote.as_str()])
            .arg(&context.archive_root)
            .current_dir(parent)
            .output()
            .map_err(|error| ArchiveError::new("process_unavailable", error.to_string()))?;
        if !clone.status.success() {
            return Err(ArchiveError::new(
                "archive_clone_failed",
                output_bytes_text(&clone.stderr),
            ));
        }
        created = true;
    }
    if !is_archive_clone(&context.archive_root) {
        return Err(ArchiveError::new(
            "archive_root_invalid",
            format!(
                "archive path is not a Git clone: {}",
                context.archive_root.display()
            ),
        ));
    }
    ensure_origin(context)?;
    if fetch {
        let _ = git(
            &context.archive_root,
            &["fetch".to_owned(), "origin".to_owned()],
            false,
        )?;
    }
    let current = current_branch(context)?;
    if current == context.branch {
        return Ok(current);
    }
    if created && !allow_branch_switch {
        switch_to_archive_branch(context, &context.branch)?;
        return current_branch(context);
    }
    if !allow_branch_switch {
        return Err(ArchiveError::new(
            "archive_branch_mismatch",
            format!("current={current}:expected={}", context.branch),
        ));
    }
    let summary = archive_status_summary(context)?;
    if summary.dirty {
        preserve_managed_dirty_paths(context, &current)?;
        let summary = archive_status_summary(context)?;
        if summary.dirty {
            return Err(ArchiveError::new(
                "archive_dirty_branch_switch_rejected",
                format!(
                    "archive has local changes on {current}; run sync or push before switching to {}",
                    context.branch
                ),
            ));
        }
    }
    switch_to_archive_branch(context, &context.branch)?;
    current_branch(context)
}

fn archive_oid(context: &ArchiveContext, revision: &str) -> String {
    git(
        &context.archive_root,
        &[
            "rev-parse".to_owned(),
            "--verify".to_owned(),
            revision.to_owned(),
        ],
        false,
    )
    .ok()
    .filter(|result| result.status.success())
    .map(|result| output_text(&result).trim().to_owned())
    .unwrap_or_default()
}

fn prepare_archive_transaction(
    context: &ArchiveContext,
    fetch: bool,
    allow_branch_switch: bool,
) -> Result<PreparedArchiveTransaction, ArchiveError> {
    let runtime_root = context
        .runtime_root
        .clone()
        .or_else(|| {
            env::var_os(RUNTIME_ROOT_ENV)
                .filter(|value| !value.is_empty())
                .map(PathBuf::from)
        })
        .ok_or_else(|| ArchiveError::new("runtime_root_required", RUNTIME_ROOT_ENV))?;
    let spool = RuntimeSpoolBoundary::for_source(&context.source_root, Some(&runtime_root), true)
        .map_err(|error| ArchiveError::new("runtime_root_invalid", error))?;
    spool
        .ensure_directory(Path::new("locks"))
        .map_err(|error| ArchiveError::new("runtime_lock_failed", error))?;
    let lock = spool
        .try_lock_with_empty_marker(Path::new(ARCHIVE_TRANSACTION_LOCK_RELATIVE))
        .map_err(|error| {
            let detail = error.to_ascii_lowercase();
            if detail.contains("would block") || detail.contains("resource temporarily unavailable")
            {
                ArchiveError::new("archive_transaction_busy", "archive transaction is busy")
            } else {
                ArchiveError::new("archive_transaction_lock_failed", error)
            }
        })?;
    let ensured_branch = match ensure_archive(context, fetch, allow_branch_switch) {
        Ok(branch) => branch,
        Err(error) => {
            let _ = lock.finish();
            return Err(error);
        }
    };
    if ensured_branch != context.branch {
        let _ = lock.finish();
        return Err(ArchiveError::new(
            "archive_transaction_branch_mismatch",
            format!("{ensured_branch}:{}", context.branch),
        ));
    }
    Ok(PreparedArchiveTransaction {
        context: context.clone(),
        _lock: lock,
        archive_head_before: archive_oid(context, "HEAD"),
        ensured_branch,
    })
}

fn safe_archive_relative_path(value: &str) -> Result<PathBuf, ArchiveError> {
    let path = Path::new(value);
    if path.is_absolute()
        || path
            .components()
            .any(|component| component == Component::ParentDir)
    {
        return Err(ArchiveError::new(
            "archive_path_invalid",
            format!("archive path must be relative and cannot contain '..': {value}"),
        ));
    }
    if path.components().any(|component| {
        matches!(
            component,
            Component::ParentDir | Component::RootDir | Component::Prefix(_)
        )
    }) {
        return Err(ArchiveError::new(
            "archive_path_invalid",
            format!("archive path contains an unsafe component: {value}"),
        ));
    }
    Ok(path.to_path_buf())
}

fn safe_run_id(value: &str) -> Result<(), ArchiveError> {
    if value.is_empty()
        || matches!(value, "." | "..")
        || value.contains('/')
        || value.contains('\\')
    {
        return Err(ArchiveError::new("run_id_invalid", value.to_owned()));
    }
    Ok(())
}

fn archive_blob_at(
    context: &ArchiveContext,
    commit: &str,
    path: &Path,
) -> Result<Vec<u8>, ArchiveError> {
    let relative = safe_archive_relative_path(&path.to_string_lossy())?;
    let spec = format!("{}:{}", commit, relative.to_string_lossy());
    let output = Command::new("git")
        .arg("-C")
        .arg(&context.archive_root)
        .arg("show")
        .arg(spec)
        .current_dir(
            context
                .archive_root
                .parent()
                .unwrap_or_else(|| Path::new("/")),
        )
        .output()
        .map_err(|error| ArchiveError::new("process_unavailable", format!("git show: {error}")))?;
    if !output.status.success() {
        return Err(ArchiveError::new(
            "archive_readback_mismatch",
            "missing remote blob",
        ));
    }
    Ok(output.stdout)
}

fn remote_ref_oid(context: &ArchiveContext) -> String {
    let output = git(
        &context.archive_root,
        &[
            "ls-remote".to_owned(),
            "origin".to_owned(),
            format!("refs/heads/{}", context.branch),
        ],
        false,
    );
    let Ok(output) = output else {
        return String::new();
    };
    if !output.status.success() {
        return String::new();
    }
    output_text(&output)
        .lines()
        .next()
        .and_then(|line| line.split_once('\t'))
        .map(|(oid, _)| oid.to_owned())
        .unwrap_or_default()
}

fn verify_remote_archive_readback(
    context: &ArchiveContext,
    receipt: &ArchivePublicationReceipt,
    required_paths: &[PathBuf],
) -> Result<BTreeMap<String, String>, ArchiveError> {
    if receipt.status != "committed" || !receipt.pushed {
        return Err(ArchiveError::new(
            "archive_readback_mismatch",
            "publication_not_committed",
        ));
    }
    let remote_commit = remote_ref_oid(context);
    if remote_commit.is_empty() || remote_commit != receipt.archive_commit_oid {
        return Err(ArchiveError::new("archive_readback_mismatch", "remote_ref"));
    }
    let remote_tree = archive_oid(context, &format!("{remote_commit}^{{tree}}"));
    if remote_tree.is_empty() || remote_tree != receipt.archive_tree_oid {
        return Err(ArchiveError::new("archive_readback_mismatch", "tree"));
    }
    let archive_root = agent_canon::path_resolution::resolve_non_strict(&context.archive_root)
        .map_err(|error| ArchiveError::new("archive_readback_mismatch", error))?;
    let mut blobs = BTreeMap::new();
    for path in required_paths {
        let path = agent_canon::path_resolution::resolve_non_strict(path)
            .map_err(|_| ArchiveError::new("archive_readback_mismatch", "path"))?;
        let relative = path
            .strip_prefix(&archive_root)
            .map_err(|_| ArchiveError::new("archive_readback_mismatch", "path"))?;
        let metadata = fs::symlink_metadata(&path)
            .map_err(|_| ArchiveError::new("archive_readback_mismatch", "missing_local_blob"))?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(ArchiveError::new(
                "archive_readback_mismatch",
                "missing_local_blob",
            ));
        }
        let local = fs::read(&path)
            .map_err(|_| ArchiveError::new("archive_readback_mismatch", "missing_local_blob"))?;
        let remote = archive_blob_at(context, &remote_commit, relative)?;
        if local != remote {
            return Err(ArchiveError::new(
                "archive_readback_mismatch",
                format!("blob:{}", relative.to_string_lossy()),
            ));
        }
        blobs.insert(relative.to_string_lossy().into_owned(), sha256_hex(&remote));
    }
    Ok(blobs)
}

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn python_json_bytes(value: &Value) -> Result<Vec<u8>, ArchiveError> {
    let text = serde_json::to_string(value)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error.to_string()))?;
    let parsed = agent_canon::python_json::parse_json(&text)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error))?;
    agent_canon::python_json::python_json_ascii_bytes(&parsed)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error))
}

fn python_json_pretty_bytes(value: &Value) -> Result<Vec<u8>, ArchiveError> {
    let text = serde_json::to_string(value)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error.to_string()))?;
    let parsed = agent_canon::python_json::parse_json(&text)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error))?;
    agent_canon::python_json::python_json_pretty_ascii_bytes(&parsed)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error))
}

fn canonical_compact_json(value: &Value) -> Result<Vec<u8>, ArchiveError> {
    let text = serde_json::to_string(value)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error.to_string()))?;
    let parsed = agent_canon::python_json::parse_json(&text)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error))?;
    agent_canon::python_json::canonical_json_ascii_bytes_reject_nonfinite(&parsed)
        .map_err(|error| ArchiveError::new("json_serialization_failed", error))
}

fn open_file_nofollow(path: &Path) -> Result<cap_std::fs::File, ArchiveError> {
    let path = agent_canon::path_resolution::resolve_non_strict(path)
        .map_err(|error| ArchiveError::new("archive_file_invalid", error))?;
    let root = path
        .ancestors()
        .last()
        .ok_or_else(|| ArchiveError::new("archive_file_invalid", "file has no root"))?;
    let relative = path
        .strip_prefix(root)
        .map_err(|_| ArchiveError::new("archive_file_invalid", "file path is not rooted"))?;
    let components = relative.components().collect::<Vec<_>>();
    let Some(Component::Normal(name)) = components.last() else {
        return Err(ArchiveError::new(
            "archive_file_invalid",
            "file path has no filename",
        ));
    };
    let mut directory = Dir::open_ambient_dir(root, ambient_authority())
        .map_err(|error| ArchiveError::new("archive_file_invalid", error.to_string()))?;
    for component in &components[..components.len() - 1] {
        let Component::Normal(part) = component else {
            return Err(ArchiveError::new(
                "archive_file_invalid",
                "unsafe file path",
            ));
        };
        directory = directory
            .open_dir_nofollow(part)
            .map_err(|error| ArchiveError::new("archive_file_invalid", error.to_string()))?;
    }
    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No);
    let file = directory
        .open_with(name, &options)
        .map_err(|error| ArchiveError::new("archive_file_invalid", error.to_string()))?;
    if !file
        .metadata()
        .map_err(|error| ArchiveError::new("archive_file_invalid", error.to_string()))?
        .is_file()
    {
        return Err(ArchiveError::new(
            "archive_file_invalid",
            "path is not a regular file",
        ));
    }
    Ok(file)
}

fn read_file_nofollow(path: &Path) -> Result<Vec<u8>, ArchiveError> {
    let mut file = open_file_nofollow(path)?;
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|error| ArchiveError::new("archive_file_read_failed", error.to_string()))?;
    Ok(bytes)
}

fn stage_archive_paths(context: &ArchiveContext) -> Result<(), ArchiveError> {
    let paths = [
        format!("hook-runs/{}", context.repo_key),
        format!("codex-runtime/{}", context.repo_key),
        format!("{DEFAULT_AGENT_REPORT_DESTINATION}/{}", context.repo_key),
        "eval-results".to_owned(),
        "legacy-import".to_owned(),
        "feedback/issue-packets/published".to_owned(),
    ];
    let existing = paths
        .into_iter()
        .filter(|path| context.archive_root.join(path).exists())
        .collect::<Vec<_>>();
    if !existing.is_empty() {
        let mut args = vec!["add".to_owned(), "--".to_owned()];
        args.extend(existing);
        git(&context.archive_root, &args, true)?;
    }
    Ok(())
}

fn compare_and_push(
    transaction: &PreparedArchiveTransaction,
    no_pull: bool,
) -> (bool, bool, String) {
    let context = &transaction.context;
    let mut expected = transaction.archive_head_before.clone();
    for attempt in 0..3 {
        if attempt > 0 {
            let (rebased, detail) = rebase_to_remote(context);
            if !rebased {
                return (false, false, format!("conflict:{detail}"));
            }
            expected = remote_ref_oid(context);
        } else {
            let _ = git(
                &context.archive_root,
                &[
                    "fetch".to_owned(),
                    "origin".to_owned(),
                    context.branch.clone(),
                ],
                false,
            );
            let observed = remote_ref_oid(context);
            if observed != expected {
                if no_pull {
                    return (false, false, "expected_remote_head_changed".to_owned());
                }
                let (rebased, detail) = rebase_to_remote(context);
                if !rebased {
                    return (false, false, format!("conflict:{detail}"));
                }
                expected = remote_ref_oid(context);
            }
        }
        let local = archive_oid(context, "HEAD");
        if local.is_empty() {
            return (false, false, "local_head_missing".to_owned());
        }
        let pushed = git(
            &context.archive_root,
            &[
                "push".to_owned(),
                "-u".to_owned(),
                "origin".to_owned(),
                format!("HEAD:refs/heads/{}", context.branch),
            ],
            false,
        );
        if pushed.is_ok_and(|output| output.status.success()) {
            if remote_ref_oid(context) == local {
                return (true, true, "committed".to_owned());
            }
            return (false, false, "remote_readback_mismatch".to_owned());
        }
        if attempt + 1 < 3 && !no_pull {
            continue;
        }
        return (false, false, "compare_and_push_conflict".to_owned());
    }
    (false, false, "retry_limit".to_owned())
}

fn rebase_to_remote(context: &ArchiveContext) -> (bool, String) {
    let fetched = git(
        &context.archive_root,
        &[
            "fetch".to_owned(),
            "origin".to_owned(),
            context.branch.clone(),
        ],
        false,
    );
    if fetched.is_err() && !remote_ref_oid(context).is_empty() {
        return (false, "fetch_failed".to_owned());
    }
    let remote = archive_oid(context, &format!("origin/{}", context.branch));
    let local = archive_oid(context, "HEAD");
    if remote.is_empty() || remote == local {
        return (true, "no_rebase_needed".to_owned());
    }
    let rebased = git(
        &context.archive_root,
        &["rebase".to_owned(), format!("origin/{}", context.branch)],
        false,
    );
    if rebased.as_ref().is_ok_and(|output| output.status.success()) {
        return (true, "rebased".to_owned());
    }
    let conflicted = git(
        &context.archive_root,
        &[
            "diff".to_owned(),
            "--name-only".to_owned(),
            "--diff-filter=U".to_owned(),
        ],
        false,
    )
    .map(|output| {
        output_text(&output)
            .lines()
            .map(str::to_owned)
            .collect::<Vec<_>>()
    })
    .unwrap_or_default();
    if !conflicted.is_empty() && conflicted.iter().all(|path| path.ends_with(".jsonl")) {
        for path in conflicted {
            let ours = git(
                &context.archive_root,
                &["show".to_owned(), format!(":2:{path}")],
                true,
            );
            let theirs = git(
                &context.archive_root,
                &["show".to_owned(), format!(":3:{path}")],
                true,
            );
            let (Ok(ours), Ok(theirs)) = (ours, theirs) else {
                let _ = git(
                    &context.archive_root,
                    &["rebase".to_owned(), "--abort".to_owned()],
                    false,
                );
                return (false, "rebase_jsonl_read_failed".to_owned());
            };
            let mut merged = ours.stdout;
            for line in theirs.stdout.split_inclusive(|byte| *byte == b'\n') {
                if !merged
                    .split_inclusive(|byte| *byte == b'\n')
                    .any(|existing| existing == line)
                {
                    merged.extend_from_slice(line);
                }
            }
            let boundary = RuntimeArtifactBoundary::for_source(
                &context.canon_root,
                Some(&context.archive_root),
                false,
            );
            if boundary
                .and_then(|boundary| boundary.atomic_write_bytes(Path::new(&path), &merged, 0o600))
                .is_err()
                || git(
                    &context.archive_root,
                    &["add".to_owned(), "--".to_owned(), path.clone()],
                    false,
                )
                .is_err()
            {
                let _ = git(
                    &context.archive_root,
                    &["rebase".to_owned(), "--abort".to_owned()],
                    false,
                );
                return (false, "rebase_jsonl_union_failed".to_owned());
            }
        }
        let continued = Command::new("git")
            .arg("-C")
            .arg(&context.archive_root)
            .args(["rebase", "--continue"])
            .env("GIT_EDITOR", "true")
            .current_dir(
                context
                    .archive_root
                    .parent()
                    .unwrap_or_else(|| Path::new("/")),
            )
            .output();
        if continued.is_ok_and(|output| output.status.success()) {
            return (true, "rebased_jsonl_union".to_owned());
        }
    }
    let _ = git(
        &context.archive_root,
        &["rebase".to_owned(), "--abort".to_owned()],
        false,
    );
    let detail = rebased
        .map(|output| {
            let detail = output_bytes_text(&output.stderr);
            if detail.trim().is_empty() {
                output_bytes_text(&output.stdout)
            } else {
                detail
            }
        })
        .unwrap_or_else(|error| error.to_string());
    (false, detail.replace('\n', " ").chars().take(240).collect())
}

fn publish_prepared_archive(
    transaction: &PreparedArchiveTransaction,
    message: Option<&str>,
    no_pull: bool,
    no_push: bool,
) -> ArchivePublicationReceipt {
    let context = &transaction.context;
    if stage_archive_paths(context).is_err() {
        let commit = archive_oid(context, "HEAD");
        return ArchivePublicationReceipt {
            status: "failed".to_owned(),
            commit_created: false,
            pushed: false,
            archive_tree_oid: if commit.is_empty() {
                String::new()
            } else {
                archive_oid(context, &format!("{commit}^{{tree}}"))
            },
            archive_commit_oid: commit,
            dedup_index_sha256: String::new(),
            cursor_sha256: String::new(),
            push_status: "stage_failed".to_owned(),
        };
    }
    let staged = git(
        &context.archive_root,
        &[
            "diff".to_owned(),
            "--cached".to_owned(),
            "--quiet".to_owned(),
        ],
        false,
    );
    let commit_created = match staged {
        Ok(output) => output.status.code() != Some(0),
        Err(_) => true,
    };
    if no_push {
        let commit = archive_oid(context, "HEAD");
        let tree = if commit.is_empty() {
            String::new()
        } else {
            archive_oid(context, &format!("{commit}^{{tree}}"))
        };
        return ArchivePublicationReceipt {
            status: "partial_retained".to_owned(),
            commit_created: false,
            pushed: false,
            archive_commit_oid: commit,
            archive_tree_oid: tree,
            dedup_index_sha256: String::new(),
            cursor_sha256: String::new(),
            push_status: "not_pushed".to_owned(),
        };
    }
    if commit_created {
        let commit_message = message
            .map(str::to_owned)
            .unwrap_or_else(|| format!("Append {} runtime logs", context.repo_key));
        let commit_result = ensure_commit_identity(context).and_then(|()| {
            git(
                &context.archive_root,
                &["commit".to_owned(), "-m".to_owned(), commit_message],
                false,
            )
        });
        if commit_result.is_err() || commit_result.is_ok_and(|output| !output.status.success()) {
            let commit = archive_oid(context, "HEAD");
            let tree = if commit.is_empty() {
                String::new()
            } else {
                archive_oid(context, &format!("{commit}^{{tree}}"))
            };
            return ArchivePublicationReceipt {
                status: "failed".to_owned(),
                commit_created,
                pushed: false,
                archive_commit_oid: commit,
                archive_tree_oid: tree,
                dedup_index_sha256: String::new(),
                cursor_sha256: String::new(),
                push_status: "commit_failed".to_owned(),
            };
        }
    }
    let (pushed, push_succeeded, push_status) = compare_and_push(transaction, no_pull);
    let mut status = if pushed && push_succeeded {
        "committed".to_owned()
    } else {
        "uncertain".to_owned()
    };
    let commit = archive_oid(context, "HEAD");
    let tree = if commit.is_empty() {
        String::new()
    } else {
        archive_oid(context, &format!("{commit}^{{tree}}"))
    };
    if status == "committed" && (commit.is_empty() || tree.is_empty()) {
        status = "uncertain".to_owned();
    }
    ArchivePublicationReceipt {
        status,
        commit_created,
        pushed: push_succeeded,
        archive_commit_oid: commit,
        archive_tree_oid: tree,
        dedup_index_sha256: String::new(),
        cursor_sha256: String::new(),
        push_status,
    }
}

fn archive_runtime_root(context: &ArchiveContext) -> Result<PathBuf, ArchiveError> {
    context
        .runtime_root
        .clone()
        .or_else(|| {
            env::var_os(RUNTIME_ROOT_ENV)
                .filter(|value| !value.is_empty())
                .map(PathBuf::from)
        })
        .map(|path| agent_canon::path_resolution::resolve_non_strict(&path))
        .transpose()
        .map_err(|error| ArchiveError::new("runtime_root_invalid", error))?
        .ok_or_else(|| ArchiveError::new("runtime_root_required", RUNTIME_ROOT_ENV))
}

fn read_boundary_file(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    missing_code: &str,
) -> Result<Vec<u8>, ArchiveError> {
    boundary
        .read_bytes(path)
        .map_err(|error| ArchiveError::new("runtime_artifact_invalid", error))?
        .ok_or_else(|| ArchiveError::new(missing_code, path.display().to_string()))
}

fn collect_eval_files(
    boundary: &RuntimeArtifactBoundary,
    source_dir: &Path,
    destination_prefix: &Path,
) -> Result<Vec<(PathBuf, PathBuf, Vec<u8>)>, ArchiveError> {
    let root = boundary
        .resolve(source_dir)
        .map_err(|error| ArchiveError::new("eval_bundle_invalid", error))?;
    let metadata = fs::symlink_metadata(&root)
        .map_err(|_| ArchiveError::new("eval_bundle_missing", root.display().to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(ArchiveError::new(
            "eval_bundle_invalid",
            root.display().to_string(),
        ));
    }
    let mut stack = vec![root.clone()];
    let mut files = Vec::new();
    while let Some(directory) = stack.pop() {
        let mut entries = fs::read_dir(&directory)
            .map_err(|error| ArchiveError::new("eval_bundle_invalid", error.to_string()))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| ArchiveError::new("eval_bundle_invalid", error.to_string()))?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries.into_iter().rev() {
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path)
                .map_err(|error| ArchiveError::new("eval_bundle_invalid", error.to_string()))?;
            if metadata.file_type().is_symlink() {
                return Err(ArchiveError::new(
                    "eval_bundle_symlink",
                    path.display().to_string(),
                ));
            }
            if metadata.is_dir() {
                stack.push(path);
                continue;
            }
            if !metadata.is_file() {
                continue;
            }
            let relative = path.strip_prefix(&root).map_err(|_| {
                ArchiveError::new("eval_bundle_invalid", path.display().to_string())
            })?;
            let source_bytes = read_boundary_file(boundary, &path, "eval_bundle_missing")?;
            let destination = destination_prefix.join(relative);
            let destination = safe_archive_relative_path(&destination.to_string_lossy())?;
            files.push((path, destination, source_bytes));
        }
    }
    files.sort_by(|left, right| left.1.cmp(&right.1));
    Ok(files)
}

fn eval_bundle_files(
    spool_root: &Path,
    run_id: &str,
    runtime_boundary: &RuntimeArtifactBoundary,
) -> Result<Vec<(PathBuf, PathBuf, Vec<u8>)>, ArchiveError> {
    let spool = runtime_boundary
        .resolve(spool_root)
        .map_err(|error| ArchiveError::new("eval_spool_invalid", error))?;
    let metadata = fs::symlink_metadata(&spool)
        .map_err(|_| ArchiveError::new("eval_spool_missing", spool.display().to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(ArchiveError::new(
            "eval_spool_missing",
            spool.display().to_string(),
        ));
    }
    let collection_path = spool.join("collection.json");
    let collection = read_boundary_file(
        runtime_boundary,
        &collection_path,
        "eval_collection_missing",
    )?;
    let collection_value: Value = serde_json::from_slice(&collection)
        .map_err(|_| ArchiveError::new("eval_collection_invalid", "invalid collection JSON"))?;
    if collection_value.get("schema").and_then(Value::as_str)
        != Some("agent_canon.eval_collection.v1")
    {
        return Err(ArchiveError::new("eval_collection_invalid", "schema"));
    }
    if collection_value.get("run_id").and_then(Value::as_str) != Some(run_id) {
        return Err(ArchiveError::new("eval_collection_invalid", "run_id"));
    }
    let results_root = spool.join("eval-results");
    let producer_root = spool.join("producer-logs");
    let mut files = collect_eval_files(runtime_boundary, &results_root, Path::new("eval-results"))?;
    let mut logs = collect_eval_files(
        runtime_boundary,
        &producer_root,
        &Path::new("eval-results")
            .join("runs")
            .join(run_id)
            .join("producer-logs"),
    )?;
    files.append(&mut logs);
    files.push((
        collection_path,
        PathBuf::from("eval-results")
            .join("collections")
            .join(format!("{run_id}.json")),
        collection,
    ));
    files.sort_by(|left, right| left.1.cmp(&right.1));
    Ok(files)
}

fn prepare_eval_bundle(
    transaction: &PreparedArchiveTransaction,
    spool_root: &Path,
    run_id: &str,
) -> Result<(Vec<PathBuf>, usize), ArchiveError> {
    let context = &transaction.context;
    safe_run_id(run_id)?;
    let runtime_root = archive_runtime_root(context)?;
    let spool_boundary =
        RuntimeArtifactBoundary::for_source(&context.source_root, Some(&runtime_root), false)
            .map_err(|error| ArchiveError::new("eval_spool_invalid", error))?;
    let pairs = eval_bundle_files(spool_root, run_id, &spool_boundary)?;
    let archive_boundary =
        RuntimeArtifactBoundary::for_source(&context.canon_root, Some(&context.archive_root), true)
            .map_err(|error| ArchiveError::new("archive_root_invalid", error))?;
    let mut conflicts = Vec::new();
    let mut new_pairs = Vec::new();
    for (source, relative, bytes) in &pairs {
        let target = archive_boundary
            .resolve(relative)
            .map_err(|error| ArchiveError::new("eval_archive_conflict", error))?;
        if let Some(existing) = archive_boundary
            .read_bytes(relative)
            .map_err(|error| ArchiveError::new("eval_archive_conflict", error))?
        {
            if existing != *bytes {
                conflicts.push(relative.clone());
            }
        } else {
            let _ = source;
            let _ = target;
            new_pairs.push((relative.clone(), bytes.clone()));
        }
    }
    if !conflicts.is_empty() {
        return Err(ArchiveError::new(
            "eval_archive_conflict",
            conflicts
                .iter()
                .map(|path| path.to_string_lossy().into_owned())
                .collect::<Vec<_>>()
                .join(","),
        ));
    }
    for (relative, bytes) in &new_pairs {
        archive_boundary
            .write_once_bytes(relative, bytes)
            .map_err(|error| ArchiveError::new("eval_archive_write_failed", error))?;
    }
    let required = pairs
        .into_iter()
        .map(|(_, path, _)| context.archive_root.join(path))
        .collect::<Vec<_>>();
    Ok((required, new_pairs.len()))
}

fn command_archive_eval(
    context: &ArchiveContext,
    options: &CommandOptions,
    no_pull: bool,
) -> Result<i32, ArchiveError> {
    let spool_root = PathBuf::from(options.required("spool-root")?);
    let run_id = options.required("run-id")?;
    safe_run_id(run_id)?;
    let transaction = prepare_archive_transaction(context, true, true)?;
    let (required, new_count) = prepare_eval_bundle(&transaction, &spool_root, run_id)?;
    if new_count == 0 {
        let commit = archive_oid(context, "HEAD");
        let duplicate = ArchivePublicationReceipt {
            status: "committed".to_owned(),
            commit_created: false,
            pushed: true,
            archive_commit_oid: commit.clone(),
            archive_tree_oid: if commit.is_empty() {
                String::new()
            } else {
                archive_oid(context, &format!("{commit}^{{tree}}"))
            },
            dedup_index_sha256: String::new(),
            cursor_sha256: String::new(),
            push_status: "duplicate_noop".to_owned(),
        };
        let blobs = verify_remote_archive_readback(context, &duplicate, &required)?;
        print_context(context);
        println!("RUNTIME_LOG_ARCHIVE_EVAL_RUN_ID={run_id}");
        println!("RUNTIME_LOG_ARCHIVE_EVAL_STATUS=duplicate_noop");
        println!("RUNTIME_LOG_ARCHIVE_EVAL_NEW_FILES=0");
        println!(
            "RUNTIME_LOG_ARCHIVE_EVAL_COMMIT={}",
            duplicate.archive_commit_oid
        );
        println!(
            "RUNTIME_LOG_ARCHIVE_EVAL_TREE={}",
            duplicate.archive_tree_oid
        );
        println!(
            "RUNTIME_LOG_ARCHIVE_EVAL_REMOTE_REF=refs/heads/{}",
            context.branch
        );
        println!(
            "RUNTIME_LOG_ARCHIVE_EVAL_BLOBS={}",
            serde_json::to_string(&blobs).unwrap_or_else(|_| "{}".to_owned())
        );
        return Ok(0);
    }
    let receipt = publish_prepared_archive(&transaction, None, no_pull, false);
    let blobs = if receipt.status == "committed" {
        verify_remote_archive_readback(context, &receipt, &required)?
    } else {
        BTreeMap::new()
    };
    print_context(context);
    println!("RUNTIME_LOG_ARCHIVE_EVAL_RUN_ID={run_id}");
    println!("RUNTIME_LOG_ARCHIVE_EVAL_STATUS={}", receipt.status);
    println!("RUNTIME_LOG_ARCHIVE_EVAL_NEW_FILES={new_count}");
    println!(
        "RUNTIME_LOG_ARCHIVE_EVAL_COMMIT={}",
        receipt.archive_commit_oid
    );
    println!("RUNTIME_LOG_ARCHIVE_EVAL_TREE={}", receipt.archive_tree_oid);
    println!(
        "RUNTIME_LOG_ARCHIVE_EVAL_REMOTE_REF=refs/heads/{}",
        context.branch
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_EVAL_BLOBS={}",
        serde_json::to_string(&blobs).unwrap_or_else(|_| "{}".to_owned())
    );
    Ok(if receipt.status == "committed" { 0 } else { 1 })
}

fn legacy_source_files(
    root: &Path,
    eval_results: bool,
) -> Result<Vec<(PathBuf, String, bool)>, ArchiveError> {
    let metadata = match fs::symlink_metadata(root) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(ArchiveError::new("legacy_root_invalid", error.to_string())),
    };
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(ArchiveError::new(
            "legacy_root_invalid",
            format!("legacy root is not a regular directory: {}", root.display()),
        ));
    }
    let mut directories = vec![root.to_path_buf()];
    let mut files = Vec::new();
    while let Some(directory) = directories.pop() {
        let mut entries = fs::read_dir(&directory)
            .map_err(|error| ArchiveError::new("legacy_root_invalid", error.to_string()))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| ArchiveError::new("legacy_root_invalid", error.to_string()))?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries.into_iter().rev() {
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path)
                .map_err(|error| ArchiveError::new("legacy_source_invalid", error.to_string()))?;
            if metadata.file_type().is_symlink() {
                return Err(ArchiveError::new(
                    "legacy_source_symlink",
                    path.display().to_string(),
                ));
            }
            if metadata.is_dir() {
                directories.push(path);
                continue;
            }
            if !metadata.is_file() {
                continue;
            }
            let relative = path.strip_prefix(root).map_err(|_| {
                ArchiveError::new("legacy_source_invalid", path.display().to_string())
            })?;
            if eval_results {
                if relative
                    .components()
                    .next()
                    .is_some_and(|component| component.as_os_str() == OsStr::new("hook-runs"))
                {
                    continue;
                }
            } else if path.extension() != Some(OsStr::new("jsonl")) {
                continue;
            }
            let relative = relative
                .to_str()
                .ok_or_else(|| ArchiveError::new("legacy_source_invalid", "path is not UTF-8"))?
                .replace('\\', "/");
            files.push((path, relative, true));
        }
    }
    files.sort_by(|left, right| left.1.as_bytes().cmp(right.1.as_bytes()));
    if eval_results {
        let hook_notice = root.join("hook-runs/README.md");
        match fs::symlink_metadata(&hook_notice) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(ArchiveError::new(
                    "legacy_source_symlink",
                    hook_notice.display().to_string(),
                ));
            }
            Ok(metadata) if metadata.is_file() => {
                files.push((hook_notice, "hook-runs/README.md".to_owned(), false));
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(ArchiveError::new(
                    "legacy_source_invalid",
                    error.to_string(),
                ));
            }
        }
    }
    Ok(files)
}

fn legacy_import_index_path(context: &ArchiveContext) -> PathBuf {
    context
        .archive_root
        .join("legacy-import/import-index.jsonl")
}

fn legacy_index_contains_inventory(
    boundary: &RuntimeArtifactBoundary,
    relative: &Path,
    inventory_sha256: &str,
) -> Result<bool, ArchiveError> {
    let Some(bytes) = boundary
        .read_bytes(relative)
        .map_err(|error| ArchiveError::new("legacy_import_index_invalid", error))?
    else {
        return Ok(false);
    };
    std::str::from_utf8(&bytes)
        .map_err(|_| ArchiveError::new("legacy_import_index_invalid", "index is not UTF-8"))?;
    for line in bytes.split(|byte| *byte == b'\n') {
        if line.iter().all(u8::is_ascii_whitespace) {
            continue;
        }
        let Ok(value) = serde_json::from_slice::<Value>(line) else {
            continue;
        };
        if value.get("inventory_sha256").and_then(Value::as_str) == Some(inventory_sha256) {
            return Ok(true);
        }
    }
    Ok(false)
}

fn legacy_record_json(record: &LegacyImportRecord) -> Value {
    json!({
        "bytes": record.byte_count,
        "destination": record.destination,
        "sha256": record.sha256,
        "source": record.source_relative,
    })
}

fn legacy_import_plan(
    transaction: &PreparedArchiveTransaction,
    family: &str,
    legacy_root: &Path,
    destination_prefix: &Path,
    sources: Vec<(PathBuf, String, bool)>,
    delete_source: bool,
) -> Result<LegacyImportPlan, ArchiveError> {
    let context = &transaction.context;
    let archive_boundary =
        RuntimeArtifactBoundary::for_source(&context.canon_root, Some(&context.archive_root), true)
            .map_err(|error| ArchiveError::new("archive_root_invalid", error))?;
    let mut records = Vec::new();
    let mut imported = 0;
    let mut existing = 0;
    for (source, relative, should_copy) in sources {
        let payload = read_file_nofollow(&source)?;
        let destination = should_copy.then(|| {
            destination_prefix
                .join(&relative)
                .to_string_lossy()
                .replace('\\', "/")
        });
        let mut record = LegacyImportRecord {
            source,
            source_relative: relative,
            destination,
            byte_count: payload.len(),
            sha256: sha256_hex(&payload),
        };
        if let Some(destination) = record.destination.as_deref() {
            let destination = safe_archive_relative_path(destination)?;
            let parent = destination.parent().unwrap_or_else(|| Path::new("."));
            archive_boundary
                .ensure_directory(parent)
                .map_err(|error| ArchiveError::new("legacy_archive_write_failed", error))?;
            if let Some(prior) = archive_boundary
                .read_bytes(&destination)
                .map_err(|error| ArchiveError::new("legacy_archive_conflict", error))?
            {
                if prior != payload {
                    return Err(ArchiveError::new(
                        "legacy_archive_conflict",
                        format!(
                            "archive destination already exists with different content: {}",
                            destination.display()
                        ),
                    ));
                }
                existing += 1;
            } else {
                archive_boundary
                    .write_once_bytes(&destination, &payload)
                    .map_err(|error| ArchiveError::new("legacy_archive_write_failed", error))?;
                imported += 1;
            }
            record.destination = Some(destination.to_string_lossy().replace('\\', "/"));
        }
        records.push(record);
    }

    for record in &records {
        let observed = read_file_nofollow(&record.source)
            .map_err(|_| ArchiveError::new("legacy_source_changed_before_inventory", ""))?;
        if observed.len() != record.byte_count || sha256_hex(&observed) != record.sha256 {
            return Err(ArchiveError::new(
                "legacy_source_changed_before_inventory",
                "",
            ));
        }
    }
    let inventory_records = records.iter().map(legacy_record_json).collect::<Vec<_>>();
    let inventory = json!({
        "family": family,
        "files": inventory_records,
        "schema": "agent_canon.legacy_import.v1",
    });
    let inventory_sha256 = sha256_hex(&canonical_compact_json(&inventory)?);
    let index_entry = json!({
        "family": family,
        "file_count": records.len(),
        "files": inventory_records,
        "inventory_sha256": inventory_sha256,
        "schema": "agent_canon.legacy_import.v1",
    });
    let index_path = legacy_import_index_path(context);
    let index_relative = index_path
        .strip_prefix(&context.archive_root)
        .map_err(|_| ArchiveError::new("legacy_import_index_invalid", ""))?;
    let index_appended = if !records.is_empty()
        && !legacy_index_contains_inventory(&archive_boundary, index_relative, &inventory_sha256)?
    {
        archive_boundary
            .ensure_directory(index_relative.parent().unwrap_or_else(|| Path::new(".")))
            .map_err(|error| ArchiveError::new("legacy_import_index_invalid", error))?;
        let mut line = python_json_bytes(&index_entry)?;
        line.push(b'\n');
        let mut updated = archive_boundary
            .read_bytes(index_relative)
            .map_err(|error| ArchiveError::new("legacy_import_index_invalid", error))?
            .unwrap_or_default();
        updated.extend_from_slice(&line);
        archive_boundary
            .atomic_write_bytes(index_relative, &updated, 0o600)
            .map_err(|error| ArchiveError::new("legacy_import_index_invalid", error))?;
        true
    } else {
        false
    };
    if index_appended {
        git(
            &context.archive_root,
            &[
                "add".to_owned(),
                "--".to_owned(),
                "legacy-import".to_owned(),
            ],
            true,
        )?;
    }
    print_context(context);
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_FAMILY={family}");
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_ROOT={}", legacy_root.display());
    let copied = records
        .iter()
        .filter(|record| record.destination.is_some())
        .count();
    let preserved = records.len() - copied;
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_FILES={copied}");
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_NEW_FILES={imported}");
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_EXISTING_FILES={existing}");
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_DELETIONS={copied}");
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_PRESERVED={preserved}");
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_NOT_IMPORTED={preserved}");
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_INVENTORY_SHA256={inventory_sha256}");
    if family == "hook-runs" {
        println!(
            "RUNTIME_LOG_ARCHIVE_IMPORT_LEGACY_ROOT={}",
            legacy_root.display()
        );
        println!(
            "RUNTIME_LOG_ARCHIVE_IMPORT_DESTINATION={}",
            destination_prefix.display()
        );
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_FILES={copied}");
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_NEW_FILES={imported}");
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EXISTING_FILES={existing}");
    } else {
        println!(
            "RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_ROOT={}",
            legacy_root.display()
        );
        println!(
            "RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DESTINATION={}",
            destination_prefix.display()
        );
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_FILES={copied}");
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_NEW_FILES={imported}");
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_EXISTING_FILES={existing}");
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_DELETIONS={copied}");
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_PRESERVED={preserved}");
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_NOT_IMPORTED={preserved}");
    }
    let _ = index_appended;
    Ok(LegacyImportPlan {
        family: family.to_owned(),
        index_path,
        inventory_sha256,
        records,
        delete_source,
    })
}

fn command_import_legacy(
    context: &ArchiveContext,
    options: &CommandOptions,
) -> Result<i32, ArchiveError> {
    let legacy_root = options
        .value("legacy-root")
        .map(PathBuf::from)
        .unwrap_or_else(|| context.canon_root.join("agents/evals/results/hook-runs"));
    let legacy_root = agent_canon::path_resolution::resolve_non_strict(&legacy_root)
        .map_err(|error| ArchiveError::new("legacy_root_invalid", error))?;
    let destination_prefix = safe_archive_relative_path(
        options
            .value("destination-prefix")
            .unwrap_or("legacy-import/hook-runs"),
    )?;
    if context.archive_root == legacy_root || context.archive_root.starts_with(&legacy_root) {
        return Err(ArchiveError::new(
            "legacy_root_invalid",
            "legacy root cannot be inside the archive clone",
        ));
    }
    let sources = legacy_source_files(&legacy_root, false)?;
    let transaction = prepare_archive_transaction(context, true, false)?;
    let plan = legacy_import_plan(
        &transaction,
        "hook-runs",
        &legacy_root,
        &destination_prefix,
        sources,
        options.flag("--delete-source"),
    )?;
    finalize_legacy_import(&transaction, &plan, None, false)
}

fn command_import_eval_results(
    context: &ArchiveContext,
    options: &CommandOptions,
) -> Result<i32, ArchiveError> {
    let legacy_root = options
        .value("legacy-root")
        .map(PathBuf::from)
        .unwrap_or_else(|| context.canon_root.join("agents/evals/results"));
    let legacy_root = agent_canon::path_resolution::resolve_non_strict(&legacy_root)
        .map_err(|error| ArchiveError::new("legacy_root_invalid", error))?;
    let destination_prefix = safe_archive_relative_path(
        options
            .value("destination-prefix")
            .unwrap_or("legacy-import/eval-results"),
    )?;
    if context.archive_root == legacy_root || context.archive_root.starts_with(&legacy_root) {
        return Err(ArchiveError::new(
            "legacy_root_invalid",
            "legacy root cannot be inside the archive clone",
        ));
    }
    let sources = legacy_source_files(&legacy_root, true)?;
    let transaction = prepare_archive_transaction(context, true, false)?;
    let plan = legacy_import_plan(
        &transaction,
        "eval-results",
        &legacy_root,
        &destination_prefix,
        sources,
        options.flag("--delete-source"),
    )?;
    finalize_legacy_import(&transaction, &plan, None, false)
}

fn verify_legacy_import_readback(
    context: &ArchiveContext,
    commit_oid: &str,
    plan: &LegacyImportPlan,
    concrete_records: &[LegacyImportRecord],
) -> Result<(), ArchiveError> {
    let index_relative = plan
        .index_path
        .strip_prefix(&context.archive_root)
        .map_err(|_| ArchiveError::new("legacy_readback_mismatch", "index_path"))?;
    let index_bytes = archive_blob_at(context, commit_oid, index_relative)?;
    let text = std::str::from_utf8(&index_bytes)
        .map_err(|_| ArchiveError::new("legacy_readback_mismatch", "index_json"))?;
    let mut matches = Vec::new();
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let entry: Value = serde_json::from_str(line)
            .map_err(|_| ArchiveError::new("legacy_readback_mismatch", "index_json"))?;
        if entry.get("inventory_sha256").and_then(Value::as_str)
            == Some(plan.inventory_sha256.as_str())
        {
            matches.push(entry);
        }
    }
    if matches.len() != 1 {
        return Err(ArchiveError::new("legacy_readback_mismatch", "index_entry"));
    }
    let expected_records = plan
        .records
        .iter()
        .map(legacy_record_json)
        .collect::<Vec<_>>();
    let entry = &matches[0];
    if entry.get("family").and_then(Value::as_str) != Some(plan.family.as_str())
        || entry.get("schema").and_then(Value::as_str) != Some("agent_canon.legacy_import.v1")
        || entry.get("file_count").and_then(Value::as_u64) != Some(expected_records.len() as u64)
        || entry.get("files").and_then(Value::as_array) != Some(&expected_records)
    {
        return Err(ArchiveError::new(
            "legacy_readback_mismatch",
            "index_records",
        ));
    }
    let inventory = json!({
        "family": plan.family,
        "files": expected_records,
        "schema": "agent_canon.legacy_import.v1",
    });
    if sha256_hex(&canonical_compact_json(&inventory)?) != plan.inventory_sha256 {
        return Err(ArchiveError::new(
            "legacy_readback_mismatch",
            "inventory_digest",
        ));
    }
    for record in concrete_records {
        let destination = PathBuf::from(record.destination.as_deref().unwrap_or_default());
        let spec = format!("{commit_oid}:{}", destination.to_string_lossy());
        let kind = git(
            &context.archive_root,
            &["cat-file".to_owned(), "-t".to_owned(), spec],
            false,
        )?;
        if !kind.status.success() || output_text(&kind).trim() != "blob" {
            return Err(ArchiveError::new(
                "legacy_readback_mismatch",
                format!("tree_membership:{}", destination.display()),
            ));
        }
        let remote = archive_blob_at(context, commit_oid, &destination)?;
        if remote.len() != record.byte_count || sha256_hex(&remote) != record.sha256 {
            return Err(ArchiveError::new(
                "legacy_readback_mismatch",
                format!("blob_digest:{}", destination.display()),
            ));
        }
    }
    Ok(())
}

fn source_is_tracked(
    context: &ArchiveContext,
    source: &Path,
) -> Result<Option<PathBuf>, ArchiveError> {
    let source_root = agent_canon::path_resolution::resolve_non_strict(&context.canon_root)
        .map_err(|error| ArchiveError::new("source_root_invalid", error))?;
    let source = agent_canon::path_resolution::resolve_non_strict(source)
        .map_err(|error| ArchiveError::new("legacy_source_invalid", error))?;
    let Ok(relative) = source.strip_prefix(&source_root) else {
        return Ok(None);
    };
    let relative = relative.to_path_buf();
    let output = Command::new("git")
        .arg("-C")
        .arg(&source_root)
        .args(["ls-files", "--error-unmatch", "--"])
        .arg(&relative)
        .current_dir(source_root.parent().unwrap_or_else(|| Path::new("/")))
        .output()
        .map_err(|error| ArchiveError::new("source_git_unavailable", error.to_string()))?;
    Ok(output.status.success().then_some(relative))
}

fn source_delete_capability(source: &Path) -> Result<SourceMutationCapability, ArchiveError> {
    let parent = source
        .parent()
        .ok_or_else(|| ArchiveError::new("legacy_source_delete_failed", "source has no parent"))?;
    let name = source.file_name().and_then(OsStr::to_str).ok_or_else(|| {
        ArchiveError::new("legacy_source_delete_failed", "source name is not UTF-8")
    })?;
    let capability = json!({
        "allowed_paths": [name],
        "purpose": "runtime-legacy-import-source-delete",
        "authority": "explicit-delete-source",
    });
    let capability = serde_json::to_string(&capability)
        .map_err(|error| ArchiveError::new("legacy_source_delete_failed", error.to_string()))?;
    SourceMutationCapability::from_json(parent, Some(&capability))
        .map_err(|error| ArchiveError::new("legacy_source_delete_failed", error.to_string()))
}

fn delete_source_file(context: &ArchiveContext, source: &Path) -> Result<(), ArchiveError> {
    let capability = source_delete_capability(source)?;
    let source = capability
        .assert_allowed(source)
        .map_err(|error| ArchiveError::new("legacy_source_delete_failed", error.to_string()))?;
    if let Some(relative) = source_is_tracked(context, &source)? {
        let source_root = agent_canon::path_resolution::resolve_non_strict(&context.canon_root)
            .map_err(|error| ArchiveError::new("source_root_invalid", error))?;
        let result = Command::new("git")
            .arg("-C")
            .arg(&source_root)
            .args(["rm", "--"])
            .arg(relative)
            .current_dir(source_root.parent().unwrap_or_else(|| Path::new("/")))
            .output()
            .map_err(|error| ArchiveError::new("legacy_source_delete_failed", error.to_string()))?;
        if !result.status.success() {
            return Err(ArchiveError::new(
                "legacy_source_delete_failed",
                output_bytes_text(&result.stderr),
            ));
        }
        Ok(())
    } else {
        capability
            .remove_file(&source)
            .map_err(|error| ArchiveError::new("legacy_source_delete_failed", error.to_string()))
    }
}

fn finalize_legacy_import(
    transaction: &PreparedArchiveTransaction,
    plan: &LegacyImportPlan,
    message: Option<&str>,
    no_pull: bool,
) -> Result<i32, ArchiveError> {
    let context = &transaction.context;
    let concrete = plan
        .records
        .iter()
        .filter(|record| record.destination.is_some())
        .cloned()
        .collect::<Vec<_>>();
    let preserved = plan.records.len() - concrete.len();
    if !plan.delete_source || plan.records.is_empty() {
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no");
        if plan.family == "eval-results" {
            println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE=no");
        }
        println!("RUNTIME_LOG_ARCHIVE_IMPORT=pass");
        return Ok(0);
    }
    let receipt = publish_prepared_archive(transaction, message, no_pull, false);
    if receipt.status != "committed" || !receipt.pushed {
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no");
        if plan.family == "eval-results" {
            println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE=no");
        }
        println!("RUNTIME_LOG_ARCHIVE_IMPORT=publication_{}", receipt.status);
        return Ok(1);
    }
    let mut required_paths = vec![plan.index_path.clone()];
    required_paths.extend(concrete.iter().filter_map(|record| {
        record
            .destination
            .as_ref()
            .map(|path| context.archive_root.join(path))
    }));
    verify_remote_archive_readback(context, &receipt, &required_paths)?;
    verify_legacy_import_readback(context, &receipt.archive_commit_oid, plan, &concrete)?;
    for record in &concrete {
        let payload = read_file_nofollow(&record.source)
            .map_err(|_| ArchiveError::new("legacy_source_changed_before_finalize", ""))?;
        if payload.len() != record.byte_count || sha256_hex(&payload) != record.sha256 {
            return Err(ArchiveError::new(
                "legacy_source_changed_before_finalize",
                "",
            ));
        }
    }
    for record in &concrete {
        delete_source_file(context, &record.source)?;
    }
    println!(
        "RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_DELETIONS={}",
        concrete.len()
    );
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_PRESERVED={preserved}");
    println!("RUNTIME_LOG_ARCHIVE_IMPORT_SOURCE_NOT_IMPORTED={preserved}");
    println!(
        "RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE={}",
        if concrete.is_empty() { "no" } else { "yes" }
    );
    if plan.family == "eval-results" {
        println!(
            "RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_DELETIONS={}",
            concrete.len()
        );
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_PRESERVED={preserved}");
        println!("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_NOT_IMPORTED={preserved}");
        println!(
            "RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE={}",
            if concrete.is_empty() { "no" } else { "yes" }
        );
    }
    println!("RUNTIME_LOG_ARCHIVE_IMPORT=pass");
    Ok(0)
}

fn command_push(
    context: &ArchiveContext,
    message: Option<&str>,
    no_pull: bool,
) -> Result<i32, ArchiveError> {
    let transaction = prepare_archive_transaction(context, true, false)?;
    let receipt = publish_prepared_archive(&transaction, message, no_pull, false);
    print_context(context);
    println!(
        "RUNTIME_LOG_ARCHIVE_COMMITTED={}",
        if receipt.commit_created { "yes" } else { "no" }
    );
    println!("RUNTIME_LOG_ARCHIVE_PUBLICATION_STATUS={}", receipt.status);
    println!("RUNTIME_LOG_ARCHIVE_PUSH_STATUS={}", receipt.push_status);
    println!(
        "RUNTIME_LOG_ARCHIVE_PUSH={}",
        if receipt.status == "committed" {
            "pass"
        } else {
            &receipt.status
        }
    );
    Ok(if receipt.status == "committed" { 0 } else { 1 })
}

fn command_sync(context: &ArchiveContext, options: &CommandOptions) -> Result<i32, ArchiveError> {
    let no_push = options.flag("--no-push");
    let no_pull = options.flag("--no-pull");
    let include_main_evals = options.flag("--include-main-evals");
    if include_main_evals && no_push {
        return Err(ArchiveError::new("main_evals_require_publication", ""));
    }
    let max_file_bytes = match options.value("max-file-bytes") {
        Some(value) => value
            .parse::<i64>()
            .map_err(|_| ArchiveError::usage("argument --max-file-bytes: invalid int value"))?,
        None => DEFAULT_AGENT_REPORT_MAX_FILE_BYTES,
    };
    let destination_prefix = safe_archive_relative_path(
        options
            .value("destination-prefix")
            .unwrap_or(DEFAULT_AGENT_REPORT_DESTINATION),
    )?;
    let transaction = prepare_archive_transaction(context, true, false)?;
    let snapshot = hook_spool::snapshot(context)?;
    let ingest = hook_spool::ingest(&transaction, snapshot)?;
    print_context(context);
    println!(
        "RUNTIME_LOG_ARCHIVE_SPOOL_SOURCE_EVENTS={}",
        ingest.snapshot.len()
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_SPOOL_ACCEPTED={}",
        ingest.accepted.len()
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_SPOOL_DUPLICATES={}",
        ingest.duplicates.len()
    );
    if !options.flag("--no-agent-reports") {
        let report_root = options.value("report-root").map(PathBuf::from);
        let summary = copy_agent_reports_prepared(
            &transaction,
            report_root.as_deref(),
            &destination_prefix,
            max_file_bytes,
        )?;
        println!(
            "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_ROOT={}",
            summary.report_root.display()
        );
        println!(
            "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_DESTINATION={}",
            summary.destination.display()
        );
        println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES={}", summary.files);
        println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_COPIED={}", summary.copied);
        println!(
            "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_UPDATED={}",
            summary.updated
        );
        println!(
            "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_EXISTING={}",
            summary.existing
        );
        println!(
            "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SKIPPED={}",
            summary.skipped
        );
    }
    let mut receipt =
        publish_prepared_archive(&transaction, options.value("message"), no_pull, no_push);
    receipt.dedup_index_sha256 = ingest.index_sha256.clone();
    receipt.cursor_sha256 = ingest.cursor_sha256.clone();
    let removed = hook_spool::finalize(&transaction, &receipt, &ingest)?;
    println!("RUNTIME_LOG_ARCHIVE_SPOOL_FINALIZED={removed}");
    println!(
        "RUNTIME_LOG_ARCHIVE_COMMITTED={}",
        if receipt.commit_created { "yes" } else { "no" }
    );
    println!("RUNTIME_LOG_ARCHIVE_PUBLICATION_STATUS={}", receipt.status);
    println!("RUNTIME_LOG_ARCHIVE_PUSH_STATUS={}", receipt.push_status);
    match receipt.status.as_str() {
        "partial_retained" => {
            println!("RUNTIME_LOG_ARCHIVE_SYNC_PUSH=skipped");
            println!("RUNTIME_LOG_ARCHIVE_SYNC=partial_retained");
            return Ok(0);
        }
        "uncertain" => {
            println!("RUNTIME_LOG_ARCHIVE_SYNC=uncertain");
            return Ok(1);
        }
        "failed" => {
            println!("RUNTIME_LOG_ARCHIVE_SYNC=failed");
            return Ok(1);
        }
        _ => {}
    }
    drop(transaction);
    if include_main_evals {
        let listed = git(
            &context.archive_root,
            &[
                "ls-tree".to_owned(),
                "-r".to_owned(),
                "--name-only".to_owned(),
                receipt.archive_commit_oid.clone(),
                "--".to_owned(),
                "eval-results/collections".to_owned(),
            ],
            true,
        )?;
        let paths = output_text(&listed)
            .lines()
            .filter(|path| !path.is_empty())
            .map(PathBuf::from)
            .collect::<Vec<_>>();
        if !paths.is_empty() {
            let required = paths
                .iter()
                .map(|path| context.archive_root.join(path))
                .collect::<Vec<_>>();
            verify_remote_archive_readback(context, &receipt, &required)?;
        }
        let mut published = paths
            .iter()
            .filter_map(|path| path.file_stem().and_then(OsStr::to_str).map(str::to_owned))
            .collect::<BTreeSet<_>>();
        let count = github_eval_delivery::deliver_main_evals(context, &mut published, no_pull)?;
        println!("RUNTIME_LOG_ARCHIVE_MAIN_EVAL_DELIVERED={count}");
    }
    println!("RUNTIME_LOG_ARCHIVE_SYNC=pass");
    Ok(0)
}

fn write_jsonl_once(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    payload: &Value,
    key: &str,
) -> Result<bool, ArchiveError> {
    let prior = boundary
        .read_bytes(path)
        .map_err(|error| ArchiveError::new("archive_index_invalid", error))?
        .unwrap_or_default();
    if !prior.is_empty() {
        std::str::from_utf8(&prior)
            .map_err(|_| ArchiveError::new("archive_index_invalid", "index is not UTF-8"))?;
        for line in prior
            .split(|byte| *byte == b'\n')
            .filter(|line| !line.iter().all(u8::is_ascii_whitespace))
        {
            let Ok(existing) = serde_json::from_slice::<Value>(line) else {
                return Err(ArchiveError::new(
                    "archive_index_invalid",
                    "index line is invalid JSON",
                ));
            };
            if existing.get("archive_id").and_then(Value::as_str) == Some(key) {
                return Ok(false);
            }
        }
    }
    let mut next = prior;
    next.extend_from_slice(&python_json_bytes(payload)?);
    next.push(b'\n');
    boundary
        .atomic_write_bytes(path, &next, 0o600)
        .map_err(|error| ArchiveError::new("archive_index_write_failed", error))?;
    Ok(true)
}

fn report_archive_root(context: &ArchiveContext) -> PathBuf {
    context
        .archive_root
        .join(DEFAULT_AGENT_REPORT_DESTINATION)
        .join(&context.repo_key)
}

fn iter_report_files(report_dir: &Path) -> Result<Vec<PathBuf>, ArchiveError> {
    let root = agent_canon::path_resolution::resolve_non_strict(report_dir)
        .map_err(|error| ArchiveError::new("report_directory_invalid", error))?;
    let metadata = fs::symlink_metadata(&root)
        .map_err(|error| ArchiveError::new("report_directory_invalid", error.to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(ArchiveError::new(
            "report_directory_invalid",
            format!(
                "report directory is not a regular directory: {}",
                root.display()
            ),
        ));
    }
    let mut pending = vec![root.clone()];
    let mut files = Vec::new();
    while let Some(directory) = pending.pop() {
        let mut entries = fs::read_dir(&directory)
            .map_err(|error| ArchiveError::new("report_directory_invalid", error.to_string()))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| ArchiveError::new("report_directory_invalid", error.to_string()))?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries.into_iter().rev() {
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path)
                .map_err(|error| ArchiveError::new("report_file_invalid", error.to_string()))?;
            if metadata.file_type().is_symlink() {
                return Err(ArchiveError::new(
                    "report_file_symlink",
                    path.display().to_string(),
                ));
            }
            if metadata.is_dir() {
                if path.file_name().is_some_and(|name| {
                    name == OsStr::new(".git") || name == OsStr::new("__pycache__")
                }) {
                    continue;
                }
                pending.push(path);
            } else if metadata.is_file() {
                files.push(path);
            }
        }
    }
    files.sort_by_key(|path| {
        path.strip_prefix(&root)
            .unwrap_or(path)
            .to_string_lossy()
            .replace('\\', "/")
    });
    Ok(files)
}

fn report_snapshot_digest(report_dir: &Path, files: &[PathBuf]) -> Result<String, ArchiveError> {
    use sha2::{Digest, Sha256};
    let root = agent_canon::path_resolution::resolve_non_strict(report_dir)
        .map_err(|error| ArchiveError::new("report_directory_invalid", error))?;
    let mut digest = Sha256::new();
    for path in files {
        let relative = path
            .strip_prefix(&root)
            .map_err(|_| ArchiveError::new("report_path_invalid", path.display().to_string()))?;
        let relative = relative
            .to_str()
            .ok_or_else(|| ArchiveError::new("report_path_invalid", "path is not UTF-8"))?
            .replace('\\', "/");
        let bytes = read_file_nofollow(path)?;
        digest.update(relative.as_bytes());
        digest.update([0]);
        digest.update(sha256_hex(&bytes).as_bytes());
        digest.update([0]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn should_skip_agent_report(relative: &Path, source: &Path, max_file_bytes: i64) -> bool {
    if relative.components().any(|component| {
        component.as_os_str() == OsStr::new(".cache")
            || component.as_os_str() == OsStr::new("__pycache__")
            || component.as_os_str() == OsStr::new(".pytest_cache")
            || component.as_os_str() == OsStr::new(".ruff_cache")
            || component.as_os_str() == OsStr::new(".mypy_cache")
    }) {
        return true;
    }
    if relative.file_name().is_some_and(|name| {
        name == OsStr::new(".active_run") || name == OsStr::new(".mcp_inventory_cache.json")
    }) {
        return true;
    }
    fs::metadata(source)
        .map(|metadata| metadata.len() > max_file_bytes.max(0) as u64)
        .unwrap_or(true)
}

fn current_timestamp() -> String {
    let now = time::OffsetDateTime::now_utc();
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:06}+00:00",
        now.year(),
        now.month() as u8,
        now.day(),
        now.hour(),
        now.minute(),
        now.second(),
        now.nanosecond() / 1_000,
    )
}

fn archive_agent_report_prepared(
    transaction: &PreparedArchiveTransaction,
    report_dir: &Path,
    max_file_bytes: Option<i64>,
) -> Result<(Value, usize, usize, PathBuf, Vec<PathBuf>), ArchiveError> {
    let context = &transaction.context;
    let report_dir = agent_canon::path_resolution::resolve_non_strict(report_dir)
        .map_err(|error| ArchiveError::new("report_directory_invalid", error))?;
    if !report_dir.starts_with(&context.source_root) {
        return Err(ArchiveError::new(
            "report_directory_outside_source",
            format!(
                "report directory must be under source root {}: {}",
                context.source_root.display(),
                report_dir.display()
            ),
        ));
    }
    let run_id = report_dir
        .file_name()
        .and_then(OsStr::to_str)
        .ok_or_else(|| ArchiveError::new("run_id_invalid", report_dir.display().to_string()))?;
    safe_run_id(run_id)?;
    let mut files = iter_report_files(&report_dir)?;
    if let Some(max_file_bytes) = max_file_bytes {
        files.retain(|path| {
            path.strip_prefix(&report_dir)
                .map(|relative| !should_skip_agent_report(relative, path, max_file_bytes))
                .unwrap_or(false)
        });
    }
    if files.is_empty() {
        return Err(ArchiveError::new(
            "report_files_missing",
            format!(
                "report directory has no files to archive: {}",
                report_dir.display()
            ),
        ));
    }
    let snapshot_id = report_snapshot_digest(&report_dir, &files)?;
    let archive_id = format!("{run_id}-{snapshot_id}");
    let destination = report_archive_root(context).join(run_id).join(&snapshot_id);
    let archive_boundary =
        RuntimeArtifactBoundary::for_source(&context.canon_root, Some(&context.archive_root), true)
            .map_err(|error| ArchiveError::new("archive_root_invalid", error))?;
    let destination_relative = destination
        .strip_prefix(&context.archive_root)
        .map_err(|_| ArchiveError::new("report_destination_invalid", ""))?;
    archive_boundary
        .ensure_directory(destination_relative)
        .map_err(|error| ArchiveError::new("report_destination_invalid", error))?;
    let mut entries = Vec::new();
    let mut copied = 0;
    let mut existing = 0;
    let mut required_paths = Vec::new();
    for source in &files {
        let relative = source
            .strip_prefix(&report_dir)
            .map_err(|_| ArchiveError::new("report_path_invalid", source.display().to_string()))?;
        let relative_text = relative
            .to_str()
            .ok_or_else(|| ArchiveError::new("report_path_invalid", "path is not UTF-8"))?
            .replace('\\', "/");
        let target_relative = destination_relative.join(relative);
        let source_bytes = read_file_nofollow(source)?;
        let target = archive_boundary
            .resolve(&target_relative)
            .map_err(|error| ArchiveError::new("report_destination_invalid", error))?;
        if let Some(prior) = archive_boundary
            .read_bytes(&target_relative)
            .map_err(|error| ArchiveError::new("report_destination_invalid", error))?
        {
            if prior != source_bytes {
                return Err(ArchiveError::new(
                    "report_destination_conflict",
                    format!(
                        "archive destination has conflicting content: {}",
                        target.display()
                    ),
                ));
            }
            existing += 1;
        } else {
            archive_boundary
                .write_once_bytes(&target_relative, &source_bytes)
                .map_err(|error| ArchiveError::new("report_copy_failed", error))?;
            copied += 1;
        }
        entries.push(json!({
            "path": relative_text,
            "bytes": source_bytes.len(),
            "sha256": sha256_hex(&source_bytes),
        }));
        required_paths.push(target);
    }
    let destination_text = destination_relative
        .to_str()
        .ok_or_else(|| ArchiveError::new("report_destination_invalid", "path is not UTF-8"))?
        .replace('\\', "/");
    let manifest = json!({
        "schema": "agent-report-snapshot.v1",
        "archive_id": archive_id,
        "archived_at": current_timestamp(),
        "codex_trace_key": eval_archive_paths::codex_trace_key(),
        "agent_canon_git_head": eval_archive_paths::source_git_head(&context.canon_root),
        "source_git_head": eval_archive_paths::source_git_head(&context.source_root),
        "source_root": context.source_root,
        "canon_root": context.canon_root,
        "repo_key": context.repo_key,
        "branch": context.branch,
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "report_dir": report_dir,
        "destination": destination_text,
        "file_count": entries.len(),
        "files": entries,
    });
    let manifest_path = destination_relative.join("archive_manifest.json");
    let mut manifest_bytes = python_json_pretty_bytes(&manifest)?;
    manifest_bytes.push(b'\n');
    let manifest_existing = archive_boundary
        .read_bytes(&manifest_path)
        .map_err(|error| ArchiveError::new("report_manifest_invalid", error))?;
    if let Some(bytes) = manifest_existing {
        let existing: Value = serde_json::from_slice(&bytes).map_err(|_| {
            ArchiveError::new("report_manifest_invalid", "manifest is invalid JSON")
        })?;
        if existing.get("archive_id") != manifest.get("archive_id") {
            return Err(ArchiveError::new(
                "report_manifest_conflict",
                "archive id differs",
            ));
        }
    } else {
        archive_boundary
            .write_once_bytes(&manifest_path, &manifest_bytes)
            .map_err(|error| ArchiveError::new("report_manifest_write_failed", error))?;
        required_paths.push(context.archive_root.join(&manifest_path));
    }
    let index_root = Path::new(DEFAULT_AGENT_REPORT_DESTINATION).join(&context.repo_key);
    let index_path = index_root.join("index.jsonl");
    let index_entry = json!({
        "schema": "agent-report-snapshot.v1",
        "archive_id": archive_id,
        "archived_at": manifest["archived_at"],
        "repo_key": context.repo_key,
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "destination": manifest["destination"],
        "file_count": entries.len(),
    });
    let index_appended =
        write_jsonl_once(&archive_boundary, &index_path, &index_entry, &archive_id)?;
    let index_absolute = context.archive_root.join(&index_path);
    required_paths.push(index_absolute.clone());
    git(
        &context.archive_root,
        &[
            "add".to_owned(),
            "--".to_owned(),
            "agent-reports".to_owned(),
        ],
        true,
    )?;
    let output = json!({
        "archive_id": archive_id,
        "manifest": manifest,
        "index_appended": index_appended,
        "files": entries,
    });
    Ok((output, copied, existing, index_absolute, required_paths))
}

fn command_archive_agent_report(
    context: &ArchiveContext,
    options: &CommandOptions,
) -> Result<i32, ArchiveError> {
    let report_dir = PathBuf::from(options.required("report-dir")?);
    let transaction = prepare_archive_transaction(context, true, false)?;
    if options.value("provenance").is_some() {
        return archive_agent_report_provenance(&transaction, &report_dir, options);
    }
    if options.flag("--publish") {
        return Err(ArchiveError::new(
            "agent_report_publish_requires_provenance",
            "agent_report:publish_requires_provenance",
        ));
    }
    let (manifest, copied, existing, _index_path, _required) =
        archive_agent_report_prepared(&transaction, &report_dir, None)?;
    let archive_id = manifest["archive_id"].as_str().unwrap_or_default();
    let run_id = manifest["run_id"].as_str().unwrap_or_default();
    let snapshot_id = manifest["snapshot_id"].as_str().unwrap_or_default();
    let destination = manifest["destination"].as_str().unwrap_or_default();
    let files = manifest["file_count"].as_u64().unwrap_or(0);
    let index_appended = manifest["index_appended"].as_bool().unwrap_or(false);
    let _ = archive_id;
    print_context(context);
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_RUN_ID={run_id}");
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SNAPSHOT={snapshot_id}");
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_DESTINATION={destination}");
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES={files}");
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_NEW_FILES={copied}");
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_EXISTING_FILES={existing}");
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_INDEX_APPENDED={}",
        if index_appended { "yes" } else { "no" }
    );
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass");
    Ok(0)
}

struct ValidatedReportProvenance {
    run_id: String,
    snapshot_id: String,
    source_commit: String,
    source_prefix: String,
    source_tree_digest: String,
    source_file_count: u64,
    source_remote: String,
    source_normalized_remote: String,
    source_branch: String,
    redaction_count: u64,
    redaction_rule_counts: Value,
    redaction_policy: Value,
    files: Vec<Value>,
    supersession: Value,
}

fn archive_forbidden_content() -> &'static BytesRegex {
    static PATTERN: OnceLock<BytesRegex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        BytesRegex::new(
            r"(?:/(?:home|mnt|Users|workspace|tmp)/|~[/\\]|(?:\$HOME|\$\{HOME\}|%USERPROFILE%|%HOMEDRIVE%%HOMEPATH%)[/\\]|(?:^|[^A-Za-z0-9])[A-Za-z]:[/\\]|-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|AKIA[0-9A-Z]{16}|Authorization:\s*Bearer\s+)",
        )
        .expect("static archive privacy pattern")
    })
}

fn provenance_error(field: &str) -> ArchiveError {
    ArchiveError::new(
        format!("agent_report_provenance:{field}"),
        "provenance validation failed",
    )
}

fn hex_field(value: Option<&Value>, length: usize, field: &str) -> Result<String, ArchiveError> {
    let Some(value) = value.and_then(Value::as_str) else {
        return Err(provenance_error(&format!("{field}_invalid")));
    };
    if value.len() != length
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(provenance_error(&format!("{field}_invalid")));
    }
    Ok(value.to_owned())
}

fn safe_provenance_path(value: Option<&Value>, field: &str) -> Result<String, ArchiveError> {
    let Some(value) = value.and_then(Value::as_str) else {
        return Err(provenance_error(&format!("{field}_invalid")));
    };
    if value.is_empty() || value.contains('\\') || Path::new(value).is_absolute() {
        return Err(provenance_error(&format!("{field}_invalid")));
    }
    let mut parts = Vec::new();
    for part in value.split('/') {
        match part {
            "" => {}
            "." | ".." => return Err(provenance_error(&format!("{field}_invalid"))),
            part => parts.push(part),
        }
    }
    if parts.is_empty() {
        return Err(provenance_error(&format!("{field}_invalid")));
    }
    Ok(parts.join("/"))
}

fn source_git_bytes(
    source_root: &Path,
    args: &[String],
    code: &str,
) -> Result<Vec<u8>, ArchiveError> {
    let mut command = vec!["-C".to_owned(), source_root.display().to_string()];
    command.extend_from_slice(args);
    let result = Command::new("git")
        .args(&command)
        .current_dir(source_root.parent().unwrap_or_else(|| Path::new("/")))
        .output()
        .map_err(|error| ArchiveError::new(code, error.to_string()))?;
    if !result.status.success() {
        return Err(ArchiveError::new(code, output_bytes_text(&result.stderr)));
    }
    Ok(result.stdout)
}

fn validate_redaction_metadata(
    item: &Value,
    prefix: &str,
) -> Result<(Vec<Value>, BTreeMap<String, u64>), ArchiveError> {
    let redactions = item
        .get("redactions")
        .and_then(Value::as_array)
        .ok_or_else(|| provenance_error(&format!("{prefix}_redactions_invalid")))?;
    let rule_ids = item
        .get("redaction_rule_ids")
        .and_then(Value::as_array)
        .ok_or_else(|| provenance_error(&format!("{prefix}_rule_ids_invalid")))?;
    let raw_counts = item
        .get("redaction_rule_counts")
        .and_then(Value::as_object)
        .ok_or_else(|| provenance_error(&format!("{prefix}_redaction_counts_invalid")))?;
    let mut ids = BTreeSet::new();
    for id in rule_ids {
        let Some(id) = id.as_str().filter(|id| !id.is_empty()) else {
            return Err(provenance_error(&format!("{prefix}_rule_ids_invalid")));
        };
        if !ids.insert(id.to_owned()) {
            return Err(provenance_error(&format!("{prefix}_rule_ids_invalid")));
        }
    }
    let mut counts = BTreeMap::new();
    for (key, value) in raw_counts {
        let Some(value) = value.as_u64() else {
            return Err(provenance_error(&format!("{prefix}_rule_counts_invalid")));
        };
        counts.insert(key.clone(), value);
    }
    if counts.keys().cloned().collect::<BTreeSet<_>>() != ids {
        return Err(provenance_error(&format!("{prefix}_rule_counts_invalid")));
    }
    let mut normalized = Vec::new();
    for (index, raw) in redactions.iter().enumerate() {
        let Some(object) = raw.as_object() else {
            return Err(provenance_error(&format!(
                "{prefix}.redactions[{index}]_invalid"
            )));
        };
        let rule_id = object
            .get("rule_id")
            .and_then(Value::as_str)
            .filter(|id| counts.contains_key(*id))
            .ok_or_else(|| {
                provenance_error(&format!("{prefix}.redactions[{index}]_rule_invalid"))
            })?;
        let kind = object
            .get("kind")
            .and_then(Value::as_str)
            .filter(|kind| !kind.is_empty())
            .ok_or_else(|| {
                provenance_error(&format!("{prefix}.redactions[{index}]_kind_invalid"))
            })?;
        let replacement = object
            .get("replacement")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                provenance_error(&format!("{prefix}.redactions[{index}]_replacement_invalid"))
            })?;
        normalized.push(json!({
            "kind": kind,
            "original_sha256": hex_field(object.get("original_sha256"),64,&format!("{prefix}.redactions[{index}].original_sha256"))?,
            "replacement": replacement,
            "rule_id": rule_id,
        }));
    }
    let total = counts.values().sum::<u64>();
    if total != redactions.len() as u64
        || item.get("redaction_count").and_then(Value::as_u64) != Some(redactions.len() as u64)
    {
        return Err(provenance_error(&format!(
            "{prefix}_redaction_count_invalid"
        )));
    }
    Ok((normalized, counts))
}

fn validate_supersession_identity(
    context: &ArchiveContext,
    value: &Value,
) -> Result<Value, ArchiveError> {
    let status = value.get("status").and_then(Value::as_str);
    let quarantine = value.get("quarantine_status").and_then(Value::as_str);
    if status != Some("superseded") || quarantine != Some("quarantined") {
        return Err(provenance_error("supersession_status_invalid"));
    }
    let snapshot_id = value
        .get("superseded_snapshot_id")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| provenance_error("superseded_snapshot_invalid"))?;
    let archive_ref = value
        .get("superseded_archive_ref")
        .and_then(Value::as_str)
        .ok_or_else(|| provenance_error("superseded_ref_invalid"))?;
    if archive_ref != format!("refs/heads/{}", context.branch) {
        return Err(provenance_error("superseded_ref_invalid"));
    }
    let old_commit = hex_field(
        value.get("superseded_archive_commit"),
        40,
        "superseded_archive_commit",
    )?;
    let old_tree = hex_field(
        value.get("superseded_archive_tree"),
        40,
        "superseded_archive_tree",
    )?;
    let old_index = hex_field(
        value.get("superseded_index_blob"),
        40,
        "superseded_index_blob",
    )?;
    let destination = safe_provenance_path(
        value.get("superseded_destination_prefix"),
        "superseded_destination_prefix",
    )?;
    if !destination.starts_with(&format!("agent-reports/{}/", context.repo_key)) {
        return Err(provenance_error("superseded_destination_invalid"));
    }
    let reason = value
        .get("reason")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| provenance_error("supersession_reason_invalid"))?;
    let current = remote_ref_oid(context);
    if current.is_empty() {
        return Err(provenance_error("superseded_remote_missing"));
    }
    let ancestor = git(
        &context.archive_root,
        &[
            "merge-base".to_owned(),
            "--is-ancestor".to_owned(),
            old_commit.clone(),
            current,
        ],
        false,
    )?;
    if !ancestor.status.success() {
        return Err(provenance_error("superseded_remote_not_ancestor"));
    }
    if archive_oid(context, &format!("{old_commit}^{{tree}}")) != old_tree {
        return Err(provenance_error("superseded_tree_mismatch"));
    }
    let index_path = format!("agent-reports/{}/index.jsonl", context.repo_key);
    let index_oid = git(
        &context.archive_root,
        &["rev-parse".to_owned(), format!("{old_commit}:{index_path}")],
        false,
    )?;
    if !index_oid.status.success() || output_text(&index_oid).trim() != old_index {
        return Err(provenance_error("superseded_index_mismatch"));
    }
    let index_bytes = archive_blob_at(context, &old_commit, Path::new(&index_path))?;
    let text = std::str::from_utf8(&index_bytes)
        .map_err(|_| provenance_error("superseded_index_invalid"))?;
    let mut found = false;
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let entry: Value =
            serde_json::from_str(line).map_err(|_| provenance_error("superseded_index_invalid"))?;
        found |= entry.get("snapshot_id").and_then(Value::as_str) == Some(snapshot_id);
    }
    if !found {
        return Err(provenance_error("superseded_snapshot_not_found"));
    }
    Ok(json!({
        "status": status,
        "quarantine_status": quarantine,
        "superseded_snapshot_id": snapshot_id,
        "superseded_archive_ref": archive_ref,
        "superseded_archive_commit": old_commit,
        "superseded_archive_tree": old_tree,
        "superseded_index_blob": old_index,
        "superseded_destination_prefix": destination,
        "reason": reason,
    }))
}

fn validate_prepared_report_provenance(
    context: &ArchiveContext,
    report_dir: &Path,
    provenance_path: &Path,
) -> Result<ValidatedReportProvenance, ArchiveError> {
    let payload_bytes =
        read_file_nofollow(provenance_path).map_err(|_| provenance_error("input_missing"))?;
    let payload: Value =
        serde_json::from_slice(&payload_bytes).map_err(|_| provenance_error("input_invalid"))?;
    if payload.get("schema").and_then(Value::as_str) != Some(AGENT_REPORT_PROVENANCE_SCHEMA) {
        return Err(provenance_error("schema_invalid"));
    }
    if payload.get("archive_schema").and_then(Value::as_str) != Some(AGENT_REPORT_ARCHIVE_SCHEMA) {
        return Err(provenance_error("archive_schema_invalid"));
    }
    let run_id = payload
        .get("run_id")
        .and_then(Value::as_str)
        .ok_or_else(|| provenance_error("run_id_invalid"))?;
    safe_run_id(run_id)?;
    let source_commit = hex_field(payload.get("source_commit"), 40, "source_commit")?;
    let source_prefix = safe_provenance_path(payload.get("source_prefix"), "source_prefix")?;
    let source_tree_digest = hex_field(
        payload.get("source_tree_digest_sha256"),
        REPORT_SNAPSHOT_DIGEST_CHARS,
        "source_tree_digest_sha256",
    )?;
    let source_file_count = payload
        .get("source_file_count")
        .and_then(Value::as_u64)
        .filter(|count| *count > 0)
        .ok_or_else(|| provenance_error("source_file_count_invalid"))?;
    let redaction_policy = payload
        .get("redaction_policy")
        .and_then(Value::as_object)
        .map(|object| Value::Object(object.clone()))
        .ok_or_else(|| provenance_error("redaction_policy_invalid"))?;
    let actual_source_remote = source_remote(&context.source_root)
        .map_err(|_| provenance_error("source_remote_invalid"))?;
    let normalized_remote = normalize_remote(&actual_source_remote)
        .map_err(|_| provenance_error("source_remote_invalid"))?;
    if payload.get("source_stable_id").and_then(Value::as_str) != Some(context.repo_key.as_str()) {
        return Err(provenance_error("source_stable_id_mismatch"));
    }
    if payload.get("source_remote").and_then(Value::as_str) != Some(actual_source_remote.as_str()) {
        return Err(provenance_error("source_remote_mismatch"));
    }
    if payload
        .get("source_normalized_remote")
        .and_then(Value::as_str)
        != Some(normalized_remote.as_str())
    {
        return Err(provenance_error("source_normalized_remote_mismatch"));
    }
    let source_branch = payload
        .get("source_branch")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| provenance_error("source_branch_invalid"))?;
    let tree_listing = source_git_bytes(
        &context.source_root,
        &[
            "ls-tree".to_owned(),
            "-r".to_owned(),
            "-z".to_owned(),
            source_commit.clone(),
            "--".to_owned(),
            source_prefix.clone(),
        ],
        "source_tree_read_failed",
    )?;
    if sha256_hex(&tree_listing) != source_tree_digest {
        return Err(provenance_error("source_tree_mismatch"));
    }
    let mut source_tree_paths = BTreeSet::new();
    for record in tree_listing
        .split(|byte| *byte == b'\0')
        .filter(|record| !record.is_empty())
    {
        let Some(separator) = record.iter().position(|byte| *byte == b'\t') else {
            return Err(provenance_error("source_tree_invalid"));
        };
        let path = &record[separator + 1..];
        let path =
            std::str::from_utf8(path).map_err(|_| provenance_error("source_tree_invalid"))?;
        source_tree_paths.insert(path.to_owned());
    }
    let files_value = payload
        .get("files")
        .and_then(Value::as_array)
        .filter(|files| !files.is_empty())
        .ok_or_else(|| provenance_error("files_invalid"))?;
    let files = files_value
        .iter()
        .map(|file| file.as_object().map(|object| Value::Object(object.clone())))
        .collect::<Option<Vec<_>>>()
        .ok_or_else(|| provenance_error("files_invalid"))?;
    if files.len() != source_file_count as usize {
        return Err(provenance_error("file_count_invalid"));
    }
    let prepared_paths = iter_report_files(report_dir)?
        .into_iter()
        .map(|path| {
            path.strip_prefix(report_dir)
                .ok()
                .and_then(Path::to_str)
                .map(|value| value.replace('\\', "/"))
                .ok_or_else(|| provenance_error("prepared_tree_mismatch"))
        })
        .collect::<Result<BTreeSet<_>, _>>()?;
    let mut declared_prepared = BTreeSet::new();
    let mut declared_sources = BTreeSet::new();
    for (index, item) in files.iter().enumerate() {
        declared_prepared.insert(safe_provenance_path(
            item.get("relative_path"),
            &format!("files[{index}].relative_path"),
        )?);
        declared_sources.insert(safe_provenance_path(
            item.get("source_path"),
            &format!("files[{index}].source_path"),
        )?);
    }
    if prepared_paths != declared_prepared {
        return Err(provenance_error("prepared_tree_mismatch"));
    }
    if declared_sources != source_tree_paths {
        return Err(provenance_error("source_tree_files_mismatch"));
    }
    let mut normalized_files = Vec::new();
    let mut aggregate_rule_counts = BTreeMap::<String, u64>::new();
    for (index, item) in files.iter().enumerate() {
        let relative = safe_provenance_path(
            item.get("relative_path"),
            &format!("files[{index}].relative_path"),
        )?;
        let source_path = safe_provenance_path(
            item.get("source_path"),
            &format!("files[{index}].source_path"),
        )?;
        if source_path != source_prefix && !source_path.starts_with(&format!("{source_prefix}/")) {
            return Err(provenance_error("source_path_outside_prefix"));
        }
        let prepared = report_dir.join(&relative);
        let archived_bytes = read_file_nofollow(&prepared)
            .map_err(|_| provenance_error("prepared_tree_mismatch"))?;
        let archive_sha = sha256_hex(&archived_bytes);
        if item.get("archive_sha256").and_then(Value::as_str) != Some(archive_sha.as_str()) {
            return Err(provenance_error("archive_sha256_mismatch"));
        }
        if item.get("size").and_then(Value::as_u64) != Some(archived_bytes.len() as u64) {
            return Err(provenance_error("file_size_mismatch"));
        }
        if archive_forbidden_content().is_match(&archived_bytes) {
            return Err(provenance_error("prepared_content_not_sanitized"));
        }
        let source_bytes = source_git_bytes(
            &context.source_root,
            &["show".to_owned(), format!("{source_commit}:{source_path}")],
            "source_blob_read_failed",
        )?;
        let source_sha = sha256_hex(&source_bytes);
        if item.get("source_sha256").and_then(Value::as_str) != Some(source_sha.as_str()) {
            return Err(provenance_error("source_sha256_mismatch"));
        }
        let (redactions, rule_counts) =
            validate_redaction_metadata(item, &format!("files[{index}]"))?;
        for (rule, count) in &rule_counts {
            *aggregate_rule_counts.entry(rule.clone()).or_insert(0) += count;
        }
        let rule_ids = item
            .get("redaction_rule_ids")
            .cloned()
            .unwrap_or(Value::Null);
        normalized_files.push(json!({
            "relative_path": relative,
            "source_path": source_path,
            "source_sha256": source_sha,
            "archive_sha256": archive_sha,
            "size": archived_bytes.len(),
            "redactions": redactions,
            "redaction_count": item.get("redaction_count").cloned().unwrap_or(Value::Null),
            "redaction_rule_ids": rule_ids,
            "redaction_rule_counts": rule_counts,
        }));
    }
    let sorted_paths = normalized_files
        .iter()
        .filter_map(|item| item.get("relative_path").and_then(Value::as_str))
        .collect::<Vec<_>>();
    if !sorted_paths
        .windows(2)
        .all(|pair| pair[0].as_bytes() <= pair[1].as_bytes())
    {
        return Err(provenance_error("files_not_sorted"));
    }
    let redaction_count = normalized_files
        .iter()
        .map(|item| {
            item.get("redaction_count")
                .and_then(Value::as_u64)
                .unwrap_or(0)
        })
        .sum::<u64>();
    if payload.get("redaction_count").and_then(Value::as_u64) != Some(redaction_count) {
        return Err(provenance_error("redaction_count_invalid"));
    }
    let top_counts = payload
        .get("redaction_rule_counts")
        .and_then(Value::as_object)
        .ok_or_else(|| provenance_error("redaction_rule_counts_invalid"))?;
    let top_counts = top_counts
        .iter()
        .map(|(key, value)| value.as_u64().map(|value| (key.clone(), value)))
        .collect::<Option<BTreeMap<_, _>>>()
        .ok_or_else(|| provenance_error("redaction_rule_counts_invalid"))?;
    if top_counts != aggregate_rule_counts {
        return Err(provenance_error("redaction_rule_counts_invalid"));
    }
    let snapshot_payload = json!({
        "source_commit": source_commit,
        "source_tree_digest_sha256": source_tree_digest,
        "files": normalized_files.iter().map(|item| json!({
            "archive_sha256": item["archive_sha256"],
            "relative_path": item["relative_path"],
            "size": item["size"],
        })).collect::<Vec<_>>(),
        "redaction_count": redaction_count,
    });
    let snapshot_id = sha256_hex(&canonical_compact_json(&snapshot_payload)?);
    if payload
        .get("snapshot_id")
        .and_then(Value::as_str)
        .is_some_and(|value| value != snapshot_id)
    {
        return Err(provenance_error("snapshot_id_mismatch"));
    }
    let supersession = payload
        .get("supersession")
        .and_then(Value::as_object)
        .map(|object| Value::Object(object.clone()))
        .ok_or_else(|| provenance_error("supersession_invalid"))?;
    let supersession = validate_supersession_identity(context, &supersession)?;
    Ok(ValidatedReportProvenance {
        run_id: run_id.to_owned(),
        snapshot_id,
        source_commit,
        source_prefix,
        source_tree_digest,
        source_file_count,
        source_remote: actual_source_remote,
        source_normalized_remote: normalized_remote,
        source_branch: source_branch.to_owned(),
        redaction_count,
        redaction_rule_counts: Value::Object(
            aggregate_rule_counts
                .into_iter()
                .map(|(key, value)| (key, Value::from(value)))
                .collect(),
        ),
        redaction_policy,
        files: normalized_files,
        supersession,
    })
}

fn write_provenance_once(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    payload: &mut Value,
    archive_id: &str,
) -> Result<bool, ArchiveError> {
    if let Some(prior) = boundary
        .read_bytes(path)
        .map_err(|error| provenance_error(&format!("index_invalid:{error}")))?
    {
        let text = std::str::from_utf8(&prior).map_err(|_| provenance_error("index_invalid"))?;
        for line in text.lines().filter(|line| !line.trim().is_empty()) {
            let existing: Value =
                serde_json::from_str(line).map_err(|_| provenance_error("index_invalid"))?;
            if existing.get("archive_id").and_then(Value::as_str) != Some(archive_id) {
                continue;
            }
            if canonical_compact_json(&existing)? != canonical_compact_json(payload)? {
                if existing.get("snapshot_id") != payload.get("snapshot_id") {
                    return Err(provenance_error("index_conflict"));
                }
                *payload = existing;
            }
            return Ok(false);
        }
    }
    write_jsonl_once(boundary, path, payload, archive_id)
}

fn verify_remote_agent_report_readback(
    context: &ArchiveContext,
    receipt: &ArchivePublicationReceipt,
    provenance: &Value,
    required_paths: &[PathBuf],
) -> Result<BTreeMap<String, String>, ArchiveError> {
    let blobs = verify_remote_archive_readback(context, receipt, required_paths)?;
    let index_path = Path::new(DEFAULT_AGENT_REPORT_DESTINATION)
        .join(&context.repo_key)
        .join("index.jsonl");
    let index_bytes = archive_blob_at(context, &receipt.archive_commit_oid, &index_path)?;
    let text =
        std::str::from_utf8(&index_bytes).map_err(|_| provenance_error("remote_index_invalid"))?;
    let mut matching = Vec::new();
    let snapshot_id = provenance.get("snapshot_id");
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let value: Value =
            serde_json::from_str(line).map_err(|_| provenance_error("remote_index_invalid"))?;
        if value.get("snapshot_id") == snapshot_id {
            matching.push(canonical_compact_json(&value)?);
        }
    }
    if matching != vec![canonical_compact_json(provenance)?] {
        return Err(provenance_error("remote_provenance_mismatch"));
    }
    let files = provenance
        .get("files")
        .and_then(Value::as_array)
        .ok_or_else(|| provenance_error("files_invalid"))?;
    for item in files {
        let destination = item
            .get("destination_path")
            .and_then(Value::as_str)
            .ok_or_else(|| provenance_error("destination_path_invalid"))?;
        let remote = archive_blob_at(context, &receipt.archive_commit_oid, Path::new(destination))?;
        if item.get("archive_sha256").and_then(Value::as_str) != Some(sha256_hex(&remote).as_str())
        {
            return Err(provenance_error(&format!(
                "remote_blob_mismatch:{destination}"
            )));
        }
    }
    Ok(blobs)
}

fn archive_agent_report_provenance(
    transaction: &PreparedArchiveTransaction,
    report_dir: &Path,
    options: &CommandOptions,
) -> Result<i32, ArchiveError> {
    let context = &transaction.context;
    let report_dir = agent_canon::path_resolution::resolve_non_strict(report_dir)
        .map_err(|error| provenance_error(&format!("prepared_tree_missing:{error}")))?;
    let metadata =
        fs::symlink_metadata(&report_dir).map_err(|_| provenance_error("prepared_tree_missing"))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(provenance_error("prepared_tree_missing"));
    }
    let provenance_path = PathBuf::from(
        options
            .value("provenance")
            .ok_or_else(|| ArchiveError::usage("missing --provenance"))?,
    );
    let provenance_path = agent_canon::path_resolution::resolve_non_strict(&provenance_path)
        .map_err(|_| provenance_error("input_missing"))?;
    let validated = validate_prepared_report_provenance(context, &report_dir, &provenance_path)?;
    let destination = report_archive_root(context)
        .join(&validated.run_id)
        .join(&validated.snapshot_id);
    let destination_relative = destination
        .strip_prefix(&context.archive_root)
        .map_err(|_| provenance_error("destination_invalid"))?
        .to_str()
        .ok_or_else(|| provenance_error("destination_invalid"))?
        .replace('\\', "/");
    let archive_boundary =
        RuntimeArtifactBoundary::for_source(&context.canon_root, Some(&context.archive_root), true)
            .map_err(|error| ArchiveError::new("archive_root_invalid", error))?;
    archive_boundary
        .ensure_directory(Path::new(&destination_relative))
        .map_err(|error| ArchiveError::new("agent_report_destination_invalid", error))?;
    let mut output_files = Vec::new();
    let mut copied = 0;
    let mut existing = 0;
    let mut required_paths = Vec::new();
    for item in &validated.files {
        let relative = item
            .get("relative_path")
            .and_then(Value::as_str)
            .ok_or_else(|| provenance_error("relative_path_invalid"))?;
        let source = report_dir.join(relative);
        let source_bytes =
            read_file_nofollow(&source).map_err(|_| provenance_error("prepared_tree_mismatch"))?;
        let destination_path = format!("{destination_relative}/{relative}");
        let destination_path =
            safe_provenance_path(Some(&Value::String(destination_path)), "destination_path")?;
        let target_relative = Path::new(&destination_path);
        if let Some(prior) = archive_boundary
            .read_bytes(target_relative)
            .map_err(|error| {
                provenance_error(&format!("destination_conflict:{relative}:{error}"))
            })?
        {
            if prior != source_bytes {
                return Err(provenance_error(&format!(
                    "destination_conflict:{relative}"
                )));
            }
            existing += 1;
        } else {
            archive_boundary
                .write_once_bytes(target_relative, &source_bytes)
                .map_err(|error| {
                    provenance_error(&format!("destination_write_failed:{relative}:{error}"))
                })?;
            copied += 1;
        }
        output_files.push(json!({
            "archive_sha256": item["archive_sha256"],
            "destination_path": destination_path,
            "redactions": item["redactions"],
            "redaction_count": item["redaction_count"],
            "redaction_rule_ids": item["redaction_rule_ids"],
            "redaction_rule_counts": item["redaction_rule_counts"],
            "relative_path": relative,
            "size": item["size"],
            "source_path": item["source_path"],
            "source_sha256": item["source_sha256"],
        }));
        required_paths.push(context.archive_root.join(target_relative));
    }
    let archive_id = format!("{}-{}", validated.run_id, validated.snapshot_id);
    let mut output = json!({
        "archive_id": archive_id,
        "archive_repository": context.remote,
        "archive_schema": AGENT_REPORT_PROVENANCE_ARCHIVE_SCHEMA,
        "archived_at": current_timestamp(),
        "destination_prefix": destination_relative,
        "files": output_files,
        "redaction_count": validated.redaction_count,
        "redaction_policy": validated.redaction_policy,
        "redaction_rule_counts": validated.redaction_rule_counts,
        "run_id": validated.run_id,
        "schema": AGENT_REPORT_PROVENANCE_SCHEMA,
        "snapshot_id": validated.snapshot_id,
        "source_branch": validated.source_branch,
        "source_commit": validated.source_commit,
        "source_file_count": validated.source_file_count,
        "source_normalized_remote": validated.source_normalized_remote,
        "source_prefix": validated.source_prefix,
        "source_remote": validated.source_remote,
        "source_stable_id": context.repo_key,
        "source_tree_digest_sha256": validated.source_tree_digest,
        "snapshot_schema": AGENT_REPORT_ARCHIVE_SCHEMA,
        "supersedes": validated.supersession,
        "quarantines": validated.supersession,
        "supersession": validated.supersession,
    });
    let index_path = Path::new(DEFAULT_AGENT_REPORT_DESTINATION)
        .join(&context.repo_key)
        .join("index.jsonl");
    let index_appended =
        write_provenance_once(&archive_boundary, &index_path, &mut output, &archive_id)?;
    git(
        &context.archive_root,
        &[
            "add".to_owned(),
            "--".to_owned(),
            DEFAULT_AGENT_REPORT_DESTINATION.to_owned(),
        ],
        true,
    )?;
    print_context(context);
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_RUN_ID={}",
        validated.run_id
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SNAPSHOT={}",
        validated.snapshot_id
    );
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_DESTINATION={destination_relative}");
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES={}",
        output_files.len()
    );
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_NEW_FILES={copied}");
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_EXISTING_FILES={existing}");
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_INDEX_APPENDED={}",
        if index_appended { "yes" } else { "no" }
    );
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_PROVENANCE=pass");
    if !options.flag("--publish") {
        println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass");
        return Ok(0);
    }
    let receipt = publish_prepared_archive(
        transaction,
        options.value("message"),
        options.flag("--no-pull"),
        false,
    );
    if receipt.status != "committed" || !receipt.pushed {
        println!(
            "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_PUBLICATION={}",
            receipt.status
        );
        println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=fail");
        return Ok(1);
    }
    let index_absolute = context.archive_root.join(&index_path);
    required_paths.insert(0, index_absolute);
    let blobs = verify_remote_agent_report_readback(context, &receipt, &output, &required_paths)?;
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_COMMIT={}",
        receipt.archive_commit_oid
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_TREE={}",
        receipt.archive_tree_oid
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_REMOTE_REF=refs/heads/{}",
        context.branch
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_BLOBS={}",
        serde_json::to_string(&blobs).unwrap_or_else(|_| "{}".to_owned())
    );
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass");
    Ok(0)
}

fn copy_agent_reports_prepared(
    transaction: &PreparedArchiveTransaction,
    report_root: Option<&Path>,
    destination_prefix: &Path,
    max_file_bytes: i64,
) -> Result<AgentReportArchiveSummary, ArchiveError> {
    let context = &transaction.context;
    if destination_prefix != Path::new(DEFAULT_AGENT_REPORT_DESTINATION) {
        return Err(ArchiveError::new(
            "agent_report_destination_policy_owned",
            format!("expected {DEFAULT_AGENT_REPORT_DESTINATION}"),
        ));
    }
    let root = report_root
        .map(|path| agent_canon::path_resolution::resolve_non_strict(path))
        .transpose()
        .map_err(|error| ArchiveError::new("report_root_invalid", error))?
        .unwrap_or_else(|| context.source_root.join("reports/agents"));
    let destination = report_archive_root(context);
    if context.archive_root == root
        || context.archive_root.starts_with(&root)
        || root.starts_with(&context.archive_root)
    {
        return Err(ArchiveError::new(
            "report_root_inside_archive",
            "agent report root cannot be inside the archive clone",
        ));
    }
    match fs::symlink_metadata(&root) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return Ok(AgentReportArchiveSummary {
                report_root: root,
                destination,
                files: 0,
                copied: 0,
                updated: 0,
                existing: 0,
                skipped: 0,
            });
        }
        Err(error) => return Err(ArchiveError::new("report_root_invalid", error.to_string())),
        Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
            return Err(ArchiveError::new(
                "report_root_invalid",
                root.display().to_string(),
            ));
        }
        _ => {}
    }
    let mut entries = fs::read_dir(&root)
        .map_err(|error| ArchiveError::new("report_root_invalid", error.to_string()))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| ArchiveError::new("report_root_invalid", error.to_string()))?;
    entries.sort_by_key(|entry| entry.file_name());
    let mut summary = AgentReportArchiveSummary {
        report_root: root,
        destination,
        files: 0,
        copied: 0,
        updated: 0,
        existing: 0,
        skipped: 0,
    };
    for entry in entries {
        let run_dir = entry.path();
        let metadata = fs::symlink_metadata(&run_dir)
            .map_err(|error| ArchiveError::new("report_directory_invalid", error.to_string()))?;
        if metadata.file_type().is_symlink() {
            return Err(ArchiveError::new(
                "report_directory_symlink",
                run_dir.display().to_string(),
            ));
        }
        if !metadata.is_dir() {
            continue;
        }
        let run_files = iter_report_files(&run_dir)?;
        let eligible = run_files
            .iter()
            .filter(|path| {
                path.strip_prefix(&run_dir)
                    .map(|relative| !should_skip_agent_report(relative, path, max_file_bytes))
                    .unwrap_or(false)
            })
            .cloned()
            .collect::<Vec<_>>();
        summary.skipped += run_files.len().saturating_sub(eligible.len());
        if eligible.is_empty() {
            continue;
        }
        let (manifest, copied, existing, _, _) =
            archive_agent_report_prepared(transaction, &run_dir, Some(max_file_bytes))?;
        summary.files += manifest
            .get("file_count")
            .and_then(Value::as_u64)
            .unwrap_or(0) as usize;
        summary.copied += copied;
        summary.existing += existing;
    }
    Ok(summary)
}

fn command_archive_agent_reports(
    context: &ArchiveContext,
    options: &CommandOptions,
) -> Result<i32, ArchiveError> {
    let report_root = options.value("report-root").map(PathBuf::from);
    let destination_prefix = safe_archive_relative_path(
        options
            .value("destination-prefix")
            .unwrap_or(DEFAULT_AGENT_REPORT_DESTINATION),
    )?;
    let max_file_bytes = match options.value("max-file-bytes") {
        Some(value) => value
            .parse::<i64>()
            .map_err(|_| ArchiveError::usage("argument --max-file-bytes: invalid int value"))?,
        None => DEFAULT_AGENT_REPORT_MAX_FILE_BYTES,
    };
    let transaction = prepare_archive_transaction(context, true, false)?;
    let summary = copy_agent_reports_prepared(
        &transaction,
        report_root.as_deref(),
        &destination_prefix,
        max_file_bytes,
    )?;
    stage_archive_paths(context)?;
    print_context(context);
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_ROOT={}",
        summary.report_root.display()
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_DESTINATION={}",
        summary.destination.display()
    );
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES={}", summary.files);
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_COPIED={}", summary.copied);
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_UPDATED={}",
        summary.updated
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_EXISTING={}",
        summary.existing
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SKIPPED={}",
        summary.skipped
    );
    println!("RUNTIME_LOG_ARCHIVE_AGENT_REPORTS=pass");
    Ok(0)
}

fn command_repo_key(context: &ArchiveContext) -> i32 {
    print_context(context);
    0
}

fn command_ensure(context: &ArchiveContext, no_fetch: bool) -> Result<i32, ArchiveError> {
    let transaction = prepare_archive_transaction(context, !no_fetch, true)?;
    print_context(&transaction.context);
    println!(
        "RUNTIME_LOG_ARCHIVE_CURRENT_BRANCH={}",
        transaction.ensured_branch
    );
    println!("RUNTIME_LOG_ARCHIVE_ENSURE=pass");
    drop(transaction);
    Ok(0)
}

fn command_status(context: &ArchiveContext, porcelain: bool) -> Result<i32, ArchiveError> {
    print_context(context);
    match fs::symlink_metadata(&context.archive_root) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            println!("RUNTIME_LOG_ARCHIVE_STATUS=missing");
            return Ok(0);
        }
        Err(error) => return Err(ArchiveError::new("archive_root_invalid", error.to_string())),
        Ok(metadata) if metadata.file_type().is_symlink() => {
            println!("RUNTIME_LOG_ARCHIVE_STATUS=invalid");
            return Ok(1);
        }
        Ok(_) if !is_archive_clone(&context.archive_root) => {
            println!("RUNTIME_LOG_ARCHIVE_STATUS=invalid");
            return Ok(1);
        }
        _ => {}
    }
    let status = porcelain_status(context)?;
    let summary = archive_status_summary(context)?;
    print_status_summary(context, &summary);
    println!(
        "RUNTIME_LOG_ARCHIVE_NEXT_ACTION={}",
        archive_next_action(context, &summary)
    );
    if porcelain {
        for line in status.lines() {
            println!("RUNTIME_LOG_ARCHIVE_PORCELAIN={line}");
        }
    }
    if !summary.branch_matches {
        println!("RUNTIME_LOG_ARCHIVE_ERROR_CODE=archive_branch_mismatch");
        println!("RUNTIME_LOG_ARCHIVE_STATUS=branch_mismatch");
        return Ok(1);
    }
    println!("RUNTIME_LOG_ARCHIVE_STATUS=pass");
    Ok(0)
}

fn command_check_clean(context: &ArchiveContext, porcelain: bool) -> Result<i32, ArchiveError> {
    print_context(context);
    match fs::symlink_metadata(&context.archive_root) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            println!("RUNTIME_LOG_ARCHIVE_CLEAN=no");
            println!("RUNTIME_LOG_ARCHIVE_STATUS=missing");
            return Ok(1);
        }
        Err(error) => return Err(ArchiveError::new("archive_root_invalid", error.to_string())),
        Ok(metadata) if metadata.file_type().is_symlink() => {
            println!("RUNTIME_LOG_ARCHIVE_CLEAN=no");
            println!("RUNTIME_LOG_ARCHIVE_STATUS=invalid");
            return Ok(1);
        }
        Ok(_) if !is_archive_clone(&context.archive_root) => {
            println!("RUNTIME_LOG_ARCHIVE_CLEAN=no");
            println!("RUNTIME_LOG_ARCHIVE_STATUS=invalid");
            return Ok(1);
        }
        _ => {}
    }
    let status = porcelain_status(context)?;
    let summary = archive_status_summary(context)?;
    print_status_summary(context, &summary);
    let clean = summary.branch_matches && !summary.dirty && summary.foreign_tree_keys.is_empty();
    println!(
        "RUNTIME_LOG_ARCHIVE_NEXT_ACTION={}",
        archive_next_action(context, &summary)
    );
    if porcelain {
        for line in status.lines() {
            println!("RUNTIME_LOG_ARCHIVE_PORCELAIN={line}");
        }
    }
    println!(
        "RUNTIME_LOG_ARCHIVE_CLEAN={}",
        if clean { "yes" } else { "no" }
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_CHECK_CLEAN={}",
        if clean { "pass" } else { "fail" }
    );
    Ok(if clean { 0 } else { 1 })
}

fn current_branch(context: &ArchiveContext) -> Result<String, ArchiveError> {
    Ok(output_text(&git(
        &context.archive_root,
        &["branch".to_owned(), "--show-current".to_owned()],
        true,
    )?)
    .trim()
    .to_owned())
}

fn porcelain_status(context: &ArchiveContext) -> Result<String, ArchiveError> {
    let output = git(
        &context.archive_root,
        &[
            "status".to_owned(),
            "--porcelain".to_owned(),
            "--untracked-files=all".to_owned(),
        ],
        false,
    )?;
    Ok(output_bytes_text(&output.stdout))
}

fn porcelain_path(line: &str) -> String {
    if line.len() < 3 {
        return String::new();
    }
    let mut path = line[3..].to_owned();
    if let Some((_, destination)) = path.rsplit_once(" -> ") {
        path = destination.to_owned();
    }
    path.trim().to_owned()
}

fn managed_runtime_archive_path(path: &str) -> bool {
    let mut parts = Path::new(path).components();
    let Some(Component::Normal(first)) = parts.next() else {
        return false;
    };
    let first = first.to_string_lossy();
    let keyed = REPO_KEYED_ARCHIVE_FAMILIES.contains(&first.as_ref());
    let global = MANAGED_GLOBAL_ARCHIVE_FAMILIES.contains(&first.as_ref());
    if keyed {
        return parts.next().is_some();
    }
    global
}

fn dirty_key_for_path(path: &str) -> (String, bool) {
    let parts = Path::new(path)
        .components()
        .filter_map(|component| match component {
            Component::Normal(value) => Some(value.to_string_lossy().into_owned()),
            _ => None,
        })
        .collect::<Vec<_>>();
    if parts.len() >= 2 && REPO_KEYED_ARCHIVE_FAMILIES.contains(&parts[0].as_str()) {
        if parts[1] != "legacy-import" {
            return (parts[1].clone(), false);
        }
    }
    if parts.first().is_some_and(|part| {
        matches!(
            part.as_str(),
            ".gitattributes" | "README.md" | "eval-results" | "legacy-import" | "reports" | "tools"
        )
    }) {
        return (String::new(), true);
    }
    (String::new(), false)
}

fn archive_tree_keys(context: &ArchiveContext) -> Vec<String> {
    let mut keys = BTreeSet::new();
    for family in REPO_KEYED_ARCHIVE_FAMILIES {
        let family_root = context.archive_root.join(family);
        if fs::symlink_metadata(&family_root)
            .is_ok_and(|metadata| metadata.file_type().is_symlink())
        {
            continue;
        }
        let Ok(children) = fs::read_dir(family_root) else {
            continue;
        };
        for child in children.flatten() {
            if child.file_name() == OsStr::new("legacy-import") {
                continue;
            }
            if child.file_type().is_ok_and(|kind| kind.is_dir()) {
                keys.insert(child.file_name().to_string_lossy().into_owned());
            }
        }
    }
    keys.into_iter().collect()
}

fn associated_repo_keys(context: &ArchiveContext) -> BTreeSet<String> {
    let canon_key = agent_canon::log_repository_identity::repo_log_key(
        &context.canon_root,
        &source_identity_environment(),
    )
    .unwrap_or_else(|_| "unidentified-source".to_owned());
    [context.repo_key.clone(), canon_key].into_iter().collect()
}

fn archive_status_summary(context: &ArchiveContext) -> Result<ArchiveStatusSummary, ArchiveError> {
    let current = current_branch(context)?;
    let status = porcelain_status(context)?;
    let tree_keys = archive_tree_keys(context);
    let associated = associated_repo_keys(context);
    let mut dirty_keys = BTreeSet::new();
    let mut global_dirty = false;
    for line in status.lines() {
        let (key, global) = dirty_key_for_path(&porcelain_path(line));
        if !key.is_empty() {
            dirty_keys.insert(key);
        }
        global_dirty |= global;
    }
    let foreign_dirty_keys = dirty_keys
        .iter()
        .filter(|key| !associated.contains(*key))
        .cloned()
        .collect::<Vec<_>>();
    let foreign_tree_keys = tree_keys
        .iter()
        .filter(|key| !associated.contains(*key))
        .cloned()
        .collect::<Vec<_>>();
    let dirty_keys = dirty_keys.into_iter().collect::<Vec<_>>();
    Ok(ArchiveStatusSummary {
        current_branch: current.clone(),
        dirty: !status.trim().is_empty(),
        branch_matches: current == context.branch,
        current_key_dirty: dirty_keys.iter().any(|key| key == &context.repo_key),
        dirty_keys,
        foreign_dirty_keys,
        tree_keys,
        foreign_tree_keys,
        global_dirty,
    })
}

fn print_context(context: &ArchiveContext) {
    println!(
        "RUNTIME_LOG_ARCHIVE_SOURCE_ROOT={}",
        context.source_root.display()
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_CANON_ROOT={}",
        context.canon_root.display()
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_ROOT={}",
        context.archive_root.display()
    );
    println!("RUNTIME_LOG_ARCHIVE_ENV_KEY={}", context.env_key);
    println!("RUNTIME_LOG_ARCHIVE_REMOTE={}", context.remote);
    println!("RUNTIME_LOG_ARCHIVE_REPO_KEY={}", context.repo_key);
    println!("RUNTIME_LOG_ARCHIVE_BRANCH_KEY={}", context.branch_key);
    println!("RUNTIME_LOG_ARCHIVE_BRANCH={}", context.branch);
    println!(
        "RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL={}",
        context.source_root.join("reports/agents").display()
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH={}",
        context.branch
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR={}",
        context
            .archive_root
            .join(DEFAULT_AGENT_REPORT_DESTINATION)
            .join(&context.repo_key)
            .display()
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_REL=agent-reports/{}",
        context.repo_key
    );
}

fn print_status_summary(context: &ArchiveContext, summary: &ArchiveStatusSummary) {
    println!(
        "RUNTIME_LOG_ARCHIVE_CURRENT_BRANCH={}",
        summary.current_branch
    );
    println!("RUNTIME_LOG_ARCHIVE_EXPECTED_BRANCH={}", context.branch);
    println!(
        "RUNTIME_LOG_ARCHIVE_BRANCH_MATCH={}",
        if summary.branch_matches { "yes" } else { "no" }
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_DIRTY={}",
        if summary.dirty { "yes" } else { "no" }
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={}",
        summary.dirty_keys.join(",")
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY={}",
        if summary.current_key_dirty {
            "yes"
        } else {
            "no"
        }
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY_KEYS={}",
        summary.foreign_dirty_keys.join(",")
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY={}",
        if summary.foreign_dirty_keys.is_empty() {
            "no"
        } else {
            "yes"
        }
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_TREE_KEYS={}",
        summary.tree_keys.join(",")
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_FOREIGN_TREE_KEYS={}",
        summary.foreign_tree_keys.join(",")
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_FOREIGN_TREE={}",
        if summary.foreign_tree_keys.is_empty() {
            "no"
        } else {
            "yes"
        }
    );
    println!(
        "RUNTIME_LOG_ARCHIVE_GLOBAL_DIRTY={}",
        if summary.global_dirty { "yes" } else { "no" }
    );
}

fn archive_next_action(context: &ArchiveContext, summary: &ArchiveStatusSummary) -> String {
    if !summary.branch_matches {
        return format!(
            "run agent-canon runtime-log-archive-git ensure for archive branch {}",
            context.branch
        );
    }
    if !summary.foreign_dirty_keys.is_empty() {
        return format!(
            "commit or migrate foreign repo-key log paths before closeout: {}",
            summary.foreign_dirty_keys.join(",")
        );
    }
    if summary.global_dirty {
        return "commit or revert archive-level dirty paths before closeout".to_owned();
    }
    if summary.dirty {
        return "run agent-canon runtime-log-archive-git sync, then check-clean".to_owned();
    }
    "none".to_owned()
}
