// @dependency-start
// contract implementation
// responsibility Exports bounded Codex history, SQLite, and session summaries to the external runtime archive.
// upstream design ../../../../../documents/runtime/runtime-log-archive.md owns the archive path and privacy contract
// upstream implementation hook_event_log.rs owns the UTC timestamp and shared archive path slug
// upstream implementation log_repository_identity.rs owns source-repository archive keys
// upstream implementation runtime_boundary.rs owns safe external-runtime path resolution and append locking
// upstream implementation python_json.rs owns Python-compatible JSON parsing and serialization
// upstream implementation python_text.rs owns Python-compatible whitespace and line splitting
// upstream implementation path_expansion.rs owns user-home expansion
// upstream implementation path_resolution.rs owns non-strict path resolution
// upstream implementation python_cli_integer.rs owns Python-compatible CLI integer parsing
// upstream implementation python_cli_options.rs owns Python argparse option prefixes
// downstream implementation main.rs exposes the native export command
// downstream implementation ../../../../../tests/agent_tools/test_export_codex_runtime_summary.py preserves independent raw-input scenarios
// @dependency-end

use crate::hook_event_log::{safe_slug, utc_now};
use crate::log_repository_identity::{repo_log_key, UNIDENTIFIED_SOURCE};
use crate::path_expansion::expand_user_path;
use crate::path_resolution::{python_glob_paths, resolve_non_strict};
use crate::python_cli_integer;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::python_json::{
    canonical_json_ascii_bytes, parse_json, to_serde_json_value, JsonArray, JsonNumber, JsonObject,
    JsonString, JsonValue,
};
use crate::python_text::{python_splitlines, python_strip};
use crate::runtime_boundary::{
    resolve_external_artifact_path, RuntimeArtifactBoundary, RUNTIME_ROOT_ENV,
};
use icu_casemap::CaseMapper;
use regex::Regex;
use rusqlite::types::ValueRef;
use rusqlite::{Connection, OpenFlags};
use rustpython_ast::bigint::BigInt;
use serde_json::{json, Map, Value as SerdeValue};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::env;
use std::fs;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use time::format_description::well_known::Rfc3339;
use time::OffsetDateTime;

const DEFAULT_RECENT_DAYS: i64 = 5;
const MAX_COUNTER_ITEMS: usize = 20;
const MAX_TURN_ITEMS: usize = 40;
const SECONDS_PER_DAY: i64 = 24 * 60 * 60;
const SUMMARY_ID_DIGEST_LENGTH: usize = 16;
const INDEX_SCHEMA: &str = "codex-runtime-summary-index.v1";
const SUMMARY_SCHEMA: &str = "codex-runtime-summary.v1";
const CODEX_HOME_ENV: &str = "CODEX_HOME";
const THREAD_ID_ENV: &str = "CODEX_THREAD_ID";
const HISTORY_FILE: &str = "history.jsonl";
const SQLITE_FILE: &str = "logs_2.sqlite";
const ARCHIVE_ROOT_ENV: &str = "AGENT_CANON_HOOK_ARCHIVE_DIR";
const PRIVATE_LOG_ROOT_ENV: &str = "AGENT_CANON_LOG_ROOT";
const ARCHIVE_RELATIVE_ROOT: &str = "archive/agent-canon-log";
const CODEX_RUNTIME_DIRECTORY: &str = "codex-runtime";
const CODEX_CHAT_DIRECTORY: &str = "chats";
const CODEX_INDEX_FILE: &str = "index.jsonl";
const GIT_COMMIT_KEY_LENGTH: usize = 12;
const GIT_HEAD_TIMEOUT: Duration = Duration::from_secs(5);
const HELP: &str = "usage: export_codex_runtime_summary.py [-h] [--source-root SOURCE_ROOT]\n                                       [--canon-root CANON_ROOT]\n                                       [--thread-id THREAD_ID] [--all-threads]\n                                       [--history-jsonl HISTORY_JSONL]\n                                       [--sqlite-log SQLITE_LOG]\n                                       [--session-glob SESSION_GLOB]\n                                       [--recent-days RECENT_DAYS]\n                                       [--all-time] [--output OUTPUT]\n                                       [--dry-run] [--print-json]\n\nExport bounded Codex runtime summaries into the AgentCanon log archive.\n\noptions:\n  -h, --help            show this help message and exit\n  --source-root SOURCE_ROOT\n  --canon-root CANON_ROOT\n  --thread-id THREAD_ID\n  --all-threads\n  --history-jsonl HISTORY_JSONL\n  --sqlite-log SQLITE_LOG\n  --session-glob SESSION_GLOB\n  --recent-days RECENT_DAYS\n  --all-time\n  --output OUTPUT\n  --dry-run\n  --print-json\n";

#[derive(Debug, Clone, PartialEq, Eq)]
struct HistorySummary {
    entry_count: usize,
    first_ts: Option<BigInt>,
    last_ts: Option<BigInt>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct TokenTurn {
    turn_id: String,
    timestamp: i64,
    total_usage_tokens: BigInt,
    estimated_token_count: Option<BigInt>,
    token_limit_reached: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SqliteSummary {
    row_count: usize,
    estimated_bytes: BigInt,
    first_ts: Option<i64>,
    last_ts: Option<i64>,
    post_sampling_rows: usize,
    token_turns: Vec<TokenTurn>,
    targets: OrderedCounter,
    levels: OrderedCounter,
    tools: OrderedCounter,
    models: OrderedCounter,
    reasoning_efforts: OrderedCounter,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SessionSummary {
    file_count: usize,
    token_event_count: usize,
    total_tokens: BigInt,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct OrderedCounter {
    entries: Vec<(String, usize)>,
    indexes: HashMap<String, usize>,
}

impl OrderedCounter {
    fn increment(&mut self, key: &str) {
        if let Some(index) = self.indexes.get(key).copied() {
            self.entries[index].1 += 1;
        } else {
            let index = self.entries.len();
            self.entries.push((key.to_owned(), 1));
            self.indexes.insert(key.to_owned(), index);
        }
    }

    fn compact_json(&self) -> SerdeValue {
        let mut entries = self.entries.clone();
        entries.sort_by_key(|entry| std::cmp::Reverse(entry.1));
        entries.truncate(MAX_COUNTER_ITEMS);
        let mut values = Map::new();
        for (key, count) in entries {
            values.insert(key, SerdeValue::from(count as u64));
        }
        SerdeValue::Object(values)
    }
}

struct SummaryOutput {
    payload: JsonValue,
    summary_id: String,
    recorded_at: String,
    source_repo_key: String,
    thread_id: String,
    history_entry_count: usize,
    sqlite_row_count: usize,
    live_total_usage_tokens: BigInt,
    live_turn_count: usize,
    latest_turn_id: String,
}

struct SummaryPaths<'a> {
    source_root: &'a Path,
    canon_root: &'a Path,
    history_path: &'a Path,
    sqlite_path: &'a Path,
}

struct ExportResult {
    status: String,
    index_status: String,
    output_path: PathBuf,
    index_path: Option<PathBuf>,
    summary: SummaryOutput,
    history: HistorySummary,
    sqlite: SqliteSummary,
}

#[derive(Clone, Copy)]
enum OptionName {
    Help,
    SourceRoot,
    CanonRoot,
    ThreadId,
    AllThreads,
    HistoryJsonl,
    SqliteLog,
    SessionGlob,
    RecentDays,
    AllTime,
    Output,
    DryRun,
    PrintJson,
}

struct CliOptions {
    source_root: PathBuf,
    canon_root: Option<PathBuf>,
    thread_id: String,
    all_threads: bool,
    history_jsonl: PathBuf,
    sqlite_log: PathBuf,
    session_globs: Vec<String>,
    recent_days: BigInt,
    all_time: bool,
    output: Option<PathBuf>,
    dry_run: bool,
    print_json: bool,
}

impl CliOptions {
    fn from_environment() -> Result<Self, String> {
        Ok(Self {
            source_root: env::current_dir().map_err(|error| error.to_string())?,
            canon_root: None,
            thread_id: env::var(THREAD_ID_ENV).unwrap_or_default(),
            all_threads: false,
            history_jsonl: default_codex_home()?.join(HISTORY_FILE),
            sqlite_log: default_codex_home()?.join(SQLITE_FILE),
            session_globs: Vec::new(),
            recent_days: BigInt::from(DEFAULT_RECENT_DAYS),
            all_time: false,
            output: None,
            dry_run: false,
            print_json: false,
        })
    }
}

fn default_codex_home() -> Result<PathBuf, String> {
    if let Some(value) = env::var_os(CODEX_HOME_ENV) {
        let value = value.to_string_lossy();
        let value = python_strip(&value);
        if !value.is_empty() {
            return expand_user_path(Path::new(value)).map_err(|error| error.to_string());
        }
    }
    if let Some(value) = env::var_os("HOME") {
        let value = value.to_string_lossy();
        let value = python_strip(&value);
        if !value.is_empty() {
            return expand_user_path(Path::new(value))
                .map(|home| home.join(".codex"))
                .map_err(|error| error.to_string());
        }
    }
    Ok(PathBuf::from(".codex"))
}

/// Run the native exporter and return its process exit code.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_arguments(args) {
        Ok(None) => {
            print!("{HELP}");
            return 0;
        }
        Ok(Some(options)) => options,
        Err(error) => return usage_error(&error),
    };
    match run_export(options) {
        Ok(code) => code,
        Err(error) => command_error(error),
    }
}

fn parse_arguments(args: &[String]) -> Result<Option<CliOptions>, String> {
    const OPTIONS: &[(&str, OptionName)] = &[
        ("--help", OptionName::Help),
        ("--source-root", OptionName::SourceRoot),
        ("--canon-root", OptionName::CanonRoot),
        ("--thread-id", OptionName::ThreadId),
        ("--all-threads", OptionName::AllThreads),
        ("--history-jsonl", OptionName::HistoryJsonl),
        ("--sqlite-log", OptionName::SqliteLog),
        ("--session-glob", OptionName::SessionGlob),
        ("--recent-days", OptionName::RecentDays),
        ("--all-time", OptionName::AllTime),
        ("--output", OptionName::Output),
        ("--dry-run", OptionName::DryRun),
        ("--print-json", OptionName::PrintJson),
    ];
    let mut options = CliOptions::from_environment()?;
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if argument == "-h" {
            return Ok(None);
        }
        if let Some(value) = argument.strip_prefix("-h=") {
            return Err(format!(
                "argument -h/--help: ignored explicit argument '{value}'"
            ));
        }
        if argument == "--" {
            if index + 1 == args.len() {
                break;
            }
            return Err(format!(
                "unrecognized arguments: {}",
                args[index + 1..].join(" ")
            ));
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(option, value)| {
                (option, Some(value.to_owned()))
            });
        if !option.starts_with("--") {
            return Err(format!("unrecognized arguments: {argument}"));
        }
        let name = resolve_long_option_prefix(option, OPTIONS).map_err(|error| match error {
            LongOptionError::Unrecognized => format!("unrecognized arguments: {argument}"),
            LongOptionError::Ambiguous(options) => format!(
                "ambiguous option: {option} could match {}",
                options.join(", ")
            ),
        })?;
        if matches!(name, OptionName::Help) {
            return match inline_value {
                Some(value) => Err(format!(
                    "argument -h/--help: ignored explicit argument '{value}'"
                )),
                None => Ok(None),
            };
        }
        let takes_value = matches!(
            name,
            OptionName::SourceRoot
                | OptionName::CanonRoot
                | OptionName::ThreadId
                | OptionName::HistoryJsonl
                | OptionName::SqliteLog
                | OptionName::SessionGlob
                | OptionName::RecentDays
                | OptionName::Output
        );
        if !takes_value {
            if let Some(value) = inline_value {
                return Err(format!(
                    "argument {option}: ignored explicit argument '{value}'"
                ));
            }
            match name {
                OptionName::AllThreads => options.all_threads = true,
                OptionName::AllTime => options.all_time = true,
                OptionName::DryRun => options.dry_run = true,
                OptionName::PrintJson => options.print_json = true,
                _ => unreachable!("value-taking options were handled above"),
            }
            index += 1;
            continue;
        }
        let value = match inline_value {
            Some(value) => value,
            None => {
                index += 1;
                let Some(value) = args.get(index) else {
                    return Err(format!("argument {option}: expected one argument"));
                };
                if value.starts_with("--") || value == "-h" {
                    return Err(format!("argument {option}: expected one argument"));
                }
                value.clone()
            }
        };
        match name {
            OptionName::Help => unreachable!("help option returns before assigning a value"),
            OptionName::SourceRoot => options.source_root = PathBuf::from(value),
            OptionName::CanonRoot => options.canon_root = Some(PathBuf::from(value)),
            OptionName::ThreadId => options.thread_id = value,
            OptionName::AllThreads => unreachable!("flag options were handled above"),
            OptionName::HistoryJsonl => options.history_jsonl = PathBuf::from(value),
            OptionName::SqliteLog => options.sqlite_log = PathBuf::from(value),
            OptionName::SessionGlob => options.session_globs.push(value),
            OptionName::RecentDays => {
                options.recent_days = python_cli_integer::parse(&value).ok_or_else(|| {
                    format!(
                        "argument {option}: invalid int value: {}",
                        rustpython_ast::Constant::Str(value.clone())
                    )
                })?;
            }
            OptionName::AllTime => unreachable!("flag options were handled above"),
            OptionName::Output => options.output = Some(PathBuf::from(value)),
            OptionName::DryRun | OptionName::PrintJson => {
                unreachable!("flag options were handled above")
            }
        }
        index += 1;
    }
    Ok(Some(options))
}

fn usage_error(message: &str) -> i32 {
    let usage = HELP.split_once("\n\n").map_or(HELP, |(usage, _)| usage);
    eprintln!("{usage}\nexport_codex_runtime_summary.py: error: {message}");
    2
}

fn command_error(message: String) -> i32 {
    eprintln!("export-codex-runtime-summary: {message}");
    1
}

fn run_export(options: CliOptions) -> Result<i32, String> {
    let source_root = resolve_non_strict(&options.source_root)?;
    let canon_root = match options.canon_root {
        Some(root) => resolve_non_strict(&root)?,
        None => agent_canon_root(&source_root)?,
    };
    let recent_days = if options.all_time {
        None
    } else {
        Some(options.recent_days)
    };
    let session_cutoff = recent_cutoff(recent_days.as_ref());
    let history_path =
        expand_user_path(&options.history_jsonl).map_err(|error| error.to_string())?;
    let sqlite_path = expand_user_path(&options.sqlite_log).map_err(|error| error.to_string())?;
    let session_paths = iter_session_paths(&options.session_globs, session_cutoff.as_ref())?;
    let grouped_session_paths = session_paths_by_thread(&session_paths);
    let thread_ids = if options.all_threads {
        discover_thread_ids(
            &history_path,
            &sqlite_path,
            &session_paths,
            session_cutoff.as_ref(),
        )?
    } else {
        let thread_id = python_strip(&options.thread_id);
        if thread_id.is_empty() {
            println!("CODEX_RUNTIME_SUMMARY=skip");
            println!("CODEX_RUNTIME_SUMMARY_REASON=missing_thread_id");
            return Ok(0);
        }
        vec![thread_id.to_owned()]
    };
    if thread_ids.is_empty() {
        println!("CODEX_RUNTIME_SUMMARY=skip");
        println!("CODEX_RUNTIME_SUMMARY_REASON=no_threads");
        return Ok(0);
    }
    if options.output.is_some() && thread_ids.len() > 1 {
        println!("CODEX_RUNTIME_SUMMARY=skip");
        println!("CODEX_RUNTIME_SUMMARY_REASON=output_requires_single_thread");
        return Ok(2);
    }

    let mut status_counts = BTreeMap::<String, usize>::new();
    let mut index_status_counts = BTreeMap::<String, usize>::new();
    let mut summaries = Vec::with_capacity(thread_ids.len());
    let mut last_output = None;
    let mut last_index = None;
    let mut total_history_entries = 0_usize;
    let mut total_sqlite_rows = 0_usize;
    let mut total_live_token_turns = 0_usize;
    let mut total_live_tokens = BigInt::from(0_u8);

    for thread_id in &thread_ids {
        let result = export_summary(
            &SummaryPaths {
                source_root: &source_root,
                canon_root: &canon_root,
                history_path: &history_path,
                sqlite_path: &sqlite_path,
            },
            thread_id,
            grouped_session_paths
                .get(thread_id)
                .map(Vec::as_slice)
                .unwrap_or(&[]),
            recent_days.as_ref(),
            options.output.as_deref(),
            options.dry_run,
        )?;
        *status_counts.entry(result.status.clone()).or_default() += 1;
        *index_status_counts
            .entry(result.index_status.clone())
            .or_default() += 1;
        total_history_entries += result.history.entry_count;
        total_sqlite_rows += result.sqlite.row_count;
        total_live_token_turns += result.sqlite.token_turns.len();
        total_live_tokens += &result.summary.live_total_usage_tokens;
        last_output = Some(result.output_path.clone());
        if let Some(path) = &result.index_path {
            last_index = Some(path.clone());
        }
        summaries.push(result.summary);
    }

    if options.print_json {
        let mut payloads = summaries
            .into_iter()
            .map(|summary| summary.payload)
            .collect::<Vec<_>>();
        let value = if payloads.len() == 1 {
            payloads.pop().expect("one summary payload exists")
        } else {
            JsonValue::Object(JsonObject(vec![(
                JsonString::from_text("summaries"),
                JsonValue::Array(JsonArray(payloads)),
            )]))
        };
        print_pretty_json(&value)?;
    }

    println!("CODEX_RUNTIME_SUMMARY=pass");
    println!(
        "CODEX_RUNTIME_SUMMARY_STATUS={}",
        status_counts_text(&status_counts, thread_ids.len())
    );
    println!(
        "CODEX_RUNTIME_SUMMARY_OUTPUT={}",
        last_output
            .as_deref()
            .map_or_else(String::new, path_display)
    );
    println!(
        "CODEX_RUNTIME_SUMMARY_INDEX_STATUS={}",
        status_counts_text(&index_status_counts, thread_ids.len())
    );
    println!(
        "CODEX_RUNTIME_SUMMARY_INDEX={}",
        last_index.as_deref().map_or_else(String::new, path_display)
    );
    println!("CODEX_RUNTIME_SUMMARY_THREADS={}", thread_ids.len());
    println!("CODEX_RUNTIME_SUMMARY_HISTORY_ENTRIES={total_history_entries}");
    println!("CODEX_RUNTIME_SUMMARY_SQLITE_ROWS={total_sqlite_rows}");
    println!("CODEX_RUNTIME_SUMMARY_LIVE_TOKEN_TURNS={total_live_token_turns}");
    println!("CODEX_RUNTIME_SUMMARY_LIVE_TOTAL_TOKENS={total_live_tokens}");
    if thread_ids.len() == 1 {
        println!("CODEX_RUNTIME_SUMMARY_THREAD_ID={}", thread_ids[0]);
    }
    Ok(0)
}

fn status_counts_text(counts: &BTreeMap<String, usize>, thread_count: usize) -> String {
    if thread_count == 1 && counts.len() == 1 {
        return counts
            .keys()
            .next()
            .expect("one summary status exists")
            .clone();
    }
    counts
        .iter()
        .map(|(status, count)| format!("{status}:{count}"))
        .collect::<Vec<_>>()
        .join(",")
}

fn print_pretty_json(value: &JsonValue) -> Result<(), String> {
    let serde_value = to_serde_json_value(value)?;
    let pretty = serde_json::to_string_pretty(&serde_value)
        .map_err(|error| format!("runtime JSON serialization failed: {error}"))?;
    let output = ensure_ascii_json(&pretty);
    let mut stdout = io::stdout().lock();
    stdout
        .write_all(output.as_bytes())
        .and_then(|()| stdout.write_all(b"\n"))
        .map_err(|error| format!("cannot write JSON summary to stdout: {error}"))
}

fn ensure_ascii_json(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut in_string = false;
    let mut escaped = false;
    for character in value.chars() {
        if in_string && character as u32 > 0x7e {
            let codepoint = character as u32;
            if codepoint <= 0xffff {
                output.push_str(&format!("\\u{codepoint:04x}"));
            } else {
                let scalar = codepoint - 0x1_0000;
                let high = 0xd800 + (scalar >> 10);
                let low = 0xdc00 + (scalar & 0x3ff);
                output.push_str(&format!("\\u{high:04x}\\u{low:04x}"));
            }
            continue;
        }
        output.push(character);
        if in_string {
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_string = false;
            }
        } else if character == '"' {
            in_string = true;
        }
    }
    output
}

fn path_display(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

fn path_posix(path: &Path) -> String {
    let value = path.to_string_lossy();
    if cfg!(windows) {
        value.replace('\\', "/")
    } else {
        value.into_owned()
    }
}

fn export_summary(
    paths: &SummaryPaths<'_>,
    thread_id: &str,
    session_paths: &[PathBuf],
    recent_days: Option<&BigInt>,
    output: Option<&Path>,
    dry_run: bool,
) -> Result<ExportResult, String> {
    let source_root = paths.source_root;
    let canon_root = paths.canon_root;
    let history_path = paths.history_path;
    let sqlite_path = paths.sqlite_path;
    let cutoff = recent_cutoff(recent_days);
    let history = read_history(history_path, thread_id, cutoff.as_ref())?;
    let sqlite = read_sqlite(sqlite_path, thread_id, cutoff.as_ref())?;
    let sessions = read_sessions(session_paths)?;
    let summary = summary_payload(paths, thread_id, &history, &sqlite, &sessions, recent_days)?;
    let output_path = match output {
        Some(path) => path.to_path_buf(),
        None => codex_runtime_summary_path(source_root, canon_root, thread_id)?,
    };
    let status = write_summary(&output_path, &summary, dry_run)?;
    let (index_status, index_path) = if output.is_none() {
        let index_path = codex_runtime_index_path(source_root, canon_root)?;
        let record = summary_index_payload(&summary, &output_path, &index_path)?;
        let status = write_summary_index(&index_path, &record, &summary.summary_id, dry_run)?;
        (status, Some(index_path))
    } else {
        ("skipped-output-override".to_owned(), None)
    };
    Ok(ExportResult {
        status,
        index_status,
        output_path,
        index_path,
        summary,
        history,
        sqlite,
    })
}

fn codex_runtime_summary_path(
    active_root: &Path,
    canon_root: &Path,
    thread_id: &str,
) -> Result<PathBuf, String> {
    Ok(codex_runtime_summary_dir(active_root, canon_root)?
        .join(CODEX_CHAT_DIRECTORY)
        .join(runtime_path_slug(thread_id))
        .join(format!(
            "summary-{}.jsonl",
            agent_canon_git_commit_key(canon_root)
        )))
}

fn codex_runtime_index_path(active_root: &Path, canon_root: &Path) -> Result<PathBuf, String> {
    Ok(codex_runtime_summary_dir(active_root, canon_root)?.join(CODEX_INDEX_FILE))
}

fn codex_runtime_summary_dir(active_root: &Path, canon_root: &Path) -> Result<PathBuf, String> {
    Ok(archive_root(canon_root)?
        .join(CODEX_RUNTIME_DIRECTORY)
        .join(repo_key(active_root)?))
}

fn archive_root(canon_root: &Path) -> Result<PathBuf, String> {
    let override_value = env::var_os(ARCHIVE_ROOT_ENV).unwrap_or_default();
    let override_value = override_value.to_string_lossy();
    let override_value = python_strip(&override_value);
    if !override_value.is_empty() {
        let expanded =
            expand_user_path(Path::new(override_value)).map_err(|error| error.to_string())?;
        if expanded.is_absolute() {
            let declared = env::var_os(PRIVATE_LOG_ROOT_ENV).unwrap_or_default();
            let declared = declared.to_string_lossy();
            let declared = python_strip(&declared);
            if declared.is_empty() {
                return Err(
                    "absolute archive override must equal the declared private-log mount root"
                        .to_owned(),
                );
            }
            let declared =
                expand_user_path(Path::new(declared)).map_err(|error| error.to_string())?;
            let declared = resolve_non_strict(&declared)?;
            let resolved = resolve_external_artifact_path(canon_root, &expanded)?;
            if resolved != declared {
                return Err(
                    "absolute archive override must equal the declared private-log mount root"
                        .to_owned(),
                );
            }
            return Ok(resolved);
        }
        return runtime_relative_path(canon_root, &expanded);
    }
    runtime_relative_path(canon_root, Path::new(ARCHIVE_RELATIVE_ROOT))
}

fn runtime_relative_path(canon_root: &Path, relative: &Path) -> Result<PathBuf, String> {
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(format!(
            "unsafe runtime-relative path: {}",
            relative.display()
        ));
    }
    let runtime_root = env::var_os(RUNTIME_ROOT_ENV).unwrap_or_default();
    let runtime_root = runtime_root.to_string_lossy();
    let runtime_root = python_strip(&runtime_root);
    if runtime_root.is_empty() {
        return Err(format!(
            "explicit runtime root required; pass --runtime-root or set {RUNTIME_ROOT_ENV}"
        ));
    }
    let runtime_root =
        expand_user_path(Path::new(runtime_root)).map_err(|error| error.to_string())?;
    if !runtime_root.is_absolute() {
        return Err(format!(
            "runtime root must be absolute: {}",
            runtime_root.display()
        ));
    }
    resolve_external_artifact_path(canon_root, &runtime_root.join(relative))
}

fn agent_canon_git_commit_key(canon_root: &Path) -> String {
    let head = source_git_head(canon_root).unwrap_or_default();
    if head.is_empty() {
        "no-git-head".to_owned()
    } else {
        runtime_path_slug(&head[..head.len().min(GIT_COMMIT_KEY_LENGTH)])
    }
}

fn runtime_path_slug(value: &str) -> String {
    if !value.bytes().any(|byte| byte.is_ascii_alphanumeric()) {
        return "unknown".to_owned();
    }
    safe_slug(value)
}

fn source_git_head(source_root: &Path) -> Result<String, String> {
    let mut child = match Command::new("git")
        .arg("-C")
        .arg(source_root)
        .args(["rev-parse", "--show-toplevel", "--verify", "HEAD"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(_) => return Ok(String::new()),
    };
    let mut stdout = child
        .stdout
        .take()
        .ok_or_else(|| "cannot capture Git source identity output".to_owned())?;
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if started.elapsed() < GIT_HEAD_TIMEOUT => {
                thread::sleep(Duration::from_millis(10));
            }
            Ok(None) | Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
        }
    };
    let mut output = Vec::new();
    stdout
        .read_to_end(&mut output)
        .map_err(|error| format!("cannot read Git source identity output: {error}"))?;
    if !status.is_some_and(|status| status.success()) {
        return Ok(String::new());
    }
    let output = String::from_utf8(output)
        .map_err(|error| format!("Git source identity output is not UTF-8: {error}"))?;
    let lines = python_splitlines(&output);
    if lines.len() != 2 {
        return Ok(String::new());
    }
    let discovered_root = match fs::canonicalize(lines[0]) {
        Ok(path) => path,
        Err(_) => return Ok(String::new()),
    };
    let requested_root = match fs::canonicalize(source_root) {
        Ok(path) => path,
        Err(_) => return Ok(String::new()),
    };
    if discovered_root == requested_root {
        Ok(python_strip(lines[1]).to_owned())
    } else {
        Ok(String::new())
    }
}

fn repo_key(source_root: &Path) -> Result<String, String> {
    let environment = env::vars_os()
        .filter_map(|(name, value)| Some((name.into_string().ok()?, value.into_string().ok()?)))
        .collect::<BTreeMap<_, _>>();
    Ok(repo_log_key(source_root, &environment).unwrap_or_else(|_| UNIDENTIFIED_SOURCE.to_owned()))
}

fn source_artifact_root() -> Result<PathBuf, String> {
    let source = match env::var_os("AGENT_CANON_SOURCE_ROOT") {
        Some(source) => PathBuf::from(source),
        None => PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../../"),
    };
    resolve_non_strict(&source)
}

fn append_parent_jsonl(path: &Path, record: &JsonValue) -> Result<(), String> {
    let mut line = canonical_json_ascii_bytes(record)?;
    line.push(b'\n');
    let source = source_artifact_root()?;
    let boundary = RuntimeArtifactBoundary::for_source(&source, None, true)?;
    boundary.append_bytes_with_empty_lock(path, &line, 0o600)?;
    Ok(())
}

fn write_summary(path: &Path, summary: &SummaryOutput, dry_run: bool) -> Result<String, String> {
    if read_existing_summary_ids(path)?.contains(&summary.summary_id) {
        return Ok("already-present".to_owned());
    }
    if dry_run {
        return Ok("dry-run".to_owned());
    }
    append_parent_jsonl(path, &summary.payload)?;
    Ok("appended".to_owned())
}

fn write_summary_index(
    path: &Path,
    record: &JsonValue,
    summary_id: &str,
    dry_run: bool,
) -> Result<String, String> {
    if read_existing_summary_ids(path)?.contains(summary_id) {
        return Ok("already-present".to_owned());
    }
    if dry_run {
        return Ok("dry-run".to_owned());
    }
    append_parent_jsonl(path, record)?;
    Ok("appended".to_owned())
}

fn recent_cutoff(recent_days: Option<&BigInt>) -> Option<BigInt> {
    recent_days.map(|days| {
        let days = if days < &BigInt::from(0_u8) {
            BigInt::from(0_u8)
        } else {
            days.clone()
        };
        BigInt::from(OffsetDateTime::now_utc().unix_timestamp())
            - days * BigInt::from(SECONDS_PER_DAY)
    })
}

fn agent_canon_root(root: &Path) -> Result<PathBuf, String> {
    const MARKERS: &[(&str, usize)] = &[
        ("tools/runtime/archive/runtime_log_paths.py", 3),
        ("eval/definitions/README.md", 2),
        ("documents/runtime/runtime-log-archive.md", 2),
    ];
    for (marker, depth) in MARKERS {
        let marker_path = root.join(marker);
        if marker_path.is_file() {
            let marker_path = resolve_non_strict(&marker_path)?;
            return marker_path
                .ancestors()
                .nth(depth + 1)
                .map(Path::to_path_buf)
                .ok_or_else(|| format!("cannot resolve AgentCanon root from marker {marker}"));
        }
    }
    Ok(root.to_path_buf())
}

fn object_member<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .find_map(|(candidate, value)| candidate.equals_text(key).then_some(value))
}

fn string_value(value: Option<&JsonValue>) -> Option<String> {
    let Some(JsonValue::String(value)) = value else {
        return None;
    };
    value.to_text()
}

fn python_integer(value: Option<&JsonValue>) -> Option<BigInt> {
    match value {
        Some(JsonValue::Bool(value)) => Some(BigInt::from(u8::from(*value))),
        Some(JsonValue::Number(JsonNumber::Integer(value))) => value.parse().ok(),
        _ => None,
    }
}

fn integer_in_cutoff(timestamp: &BigInt, cutoff: Option<&BigInt>) -> bool {
    cutoff.is_none_or(|cutoff| timestamp >= cutoff)
}

fn for_each_python_text_line<F>(path: &Path, mut consume: F) -> Result<(), String>
where
    F: FnMut(&str) -> Result<(), String>,
{
    let file =
        fs::File::open(path).map_err(|error| format!("cannot read {}: {error}", path.display()))?;
    let mut reader = BufReader::new(file);
    let mut pending = Vec::new();
    loop {
        let mut chunk = Vec::new();
        let read = reader
            .read_until(b'\n', &mut chunk)
            .map_err(|error| format!("cannot read {}: {error}", path.display()))?;
        if read == 0 {
            break;
        }
        let mut start = 0;
        let mut index = 0;
        while index < chunk.len() {
            if !matches!(chunk[index], b'\r' | b'\n') {
                index += 1;
                continue;
            }
            let mut line = Vec::with_capacity(pending.len() + index - start);
            line.append(&mut pending);
            line.extend_from_slice(&chunk[start..index]);
            consume(&String::from_utf8_lossy(&line))?;
            let delimiter = chunk[index];
            index += 1;
            if delimiter == b'\r' && chunk.get(index) == Some(&b'\n') {
                index += 1;
            }
            start = index;
        }
        pending.extend_from_slice(&chunk[start..]);
    }
    if !pending.is_empty() {
        consume(&String::from_utf8_lossy(&pending))?;
    }
    Ok(())
}

fn read_history(
    path: &Path,
    thread_id: &str,
    cutoff: Option<&BigInt>,
) -> Result<HistorySummary, String> {
    if !path.is_file() {
        return Ok(HistorySummary {
            entry_count: 0,
            first_ts: None,
            last_ts: None,
        });
    }
    let mut result = HistorySummary {
        entry_count: 0,
        first_ts: None,
        last_ts: None,
    };
    for_each_python_text_line(path, |raw_line| {
        let line = python_strip(raw_line);
        if line.is_empty() {
            return Ok(());
        }
        let Ok(value) = parse_json(line) else {
            return Ok(());
        };
        if string_value(object_member(&value, "session_id")).as_deref() != Some(thread_id) {
            return Ok(());
        }
        let Some(timestamp) = python_integer(object_member(&value, "ts")) else {
            return Ok(());
        };
        if !integer_in_cutoff(&timestamp, cutoff) {
            return Ok(());
        }
        result.entry_count += 1;
        result.first_ts = Some(
            result
                .first_ts
                .take()
                .map_or_else(|| timestamp.clone(), |value| value.min(timestamp.clone())),
        );
        result.last_ts = Some(match result.last_ts.take() {
            Some(value) => value.max(timestamp),
            None => timestamp,
        });
        Ok(())
    })?;
    Ok(result)
}

fn read_history_thread_ids(
    path: &Path,
    cutoff: Option<&BigInt>,
) -> Result<BTreeSet<String>, String> {
    if !path.is_file() {
        return Ok(BTreeSet::new());
    }
    let mut thread_ids = BTreeSet::new();
    for_each_python_text_line(path, |raw_line| {
        let line = python_strip(raw_line);
        if line.is_empty() {
            return Ok(());
        }
        let Ok(value) = parse_json(line) else {
            return Ok(());
        };
        let Some(thread_id) = string_value(object_member(&value, "session_id")) else {
            return Ok(());
        };
        if thread_id.is_empty() {
            return Ok(());
        }
        let Some(timestamp) = python_integer(object_member(&value, "ts")) else {
            return Ok(());
        };
        if integer_in_cutoff(&timestamp, cutoff) {
            thread_ids.insert(thread_id);
        }
        Ok(())
    })?;
    Ok(thread_ids)
}

fn open_readonly_sqlite(path: &Path) -> Result<Connection, String> {
    let uri = format!("file:{}?mode=ro", path_posix(path));
    let connection = Connection::open_with_flags(
        uri,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_URI,
    )
    .map_err(|error| format!("cannot open SQLite runtime log {}: {error}", path.display()))?;
    connection
        .busy_timeout(Duration::from_secs(1))
        .map_err(|error| {
            format!(
                "cannot configure SQLite runtime log {}: {error}",
                path.display()
            )
        })?;
    Ok(connection)
}

fn sqlite_integer(row: &rusqlite::Row<'_>, index: usize) -> Result<Option<i64>, String> {
    match row
        .get_ref(index)
        .map_err(|error| format!("cannot read SQLite runtime log column: {error}"))?
    {
        ValueRef::Integer(value) => Ok(Some(value)),
        _ => Ok(None),
    }
}

fn sqlite_text(row: &rusqlite::Row<'_>, index: usize) -> Result<Option<String>, String> {
    match row
        .get_ref(index)
        .map_err(|error| format!("cannot read SQLite runtime log column: {error}"))?
    {
        ValueRef::Text(value) => String::from_utf8(value.to_vec())
            .map(Some)
            .map_err(|error| format!("SQLite runtime log text is not UTF-8: {error}")),
        _ => Ok(None),
    }
}

fn read_sqlite(
    path: &Path,
    thread_id: &str,
    cutoff: Option<&BigInt>,
) -> Result<SqliteSummary, String> {
    let mut result = SqliteSummary {
        row_count: 0,
        estimated_bytes: BigInt::from(0_u8),
        first_ts: None,
        last_ts: None,
        post_sampling_rows: 0,
        token_turns: Vec::new(),
        targets: OrderedCounter::default(),
        levels: OrderedCounter::default(),
        tools: OrderedCounter::default(),
        models: OrderedCounter::default(),
        reasoning_efforts: OrderedCounter::default(),
    };
    if !path.is_file() {
        return Ok(result);
    }
    let connection = open_readonly_sqlite(path)?;
    let mut statement = connection
        .prepare(
            "SELECT ts, level, target, feedback_log_body, estimated_bytes FROM logs WHERE thread_id=?",
        )
        .map_err(|error| format!("cannot query SQLite runtime log {}: {error}", path.display()))?;
    let mut turns = BTreeMap::<String, TokenTurn>::new();
    let mut rows = statement.query([thread_id]).map_err(|error| {
        format!(
            "cannot query SQLite runtime log {}: {error}",
            path.display()
        )
    })?;
    while let Some(row) = rows
        .next()
        .map_err(|error| format!("cannot read SQLite runtime log {}: {error}", path.display()))?
    {
        let Some(timestamp) = sqlite_integer(row, 0)? else {
            continue;
        };
        if !integer_in_cutoff(&BigInt::from(timestamp), cutoff) {
            continue;
        }
        result.row_count += 1;
        result.first_ts = Some(
            result
                .first_ts
                .map_or(timestamp, |value| value.min(timestamp)),
        );
        result.last_ts = Some(
            result
                .last_ts
                .map_or(timestamp, |value| value.max(timestamp)),
        );
        if let Some(estimated_bytes) = sqlite_integer(row, 4)? {
            result.estimated_bytes += BigInt::from(estimated_bytes);
        }
        if let Some(level) = sqlite_text(row, 1)?.filter(|value| !value.is_empty()) {
            result.levels.increment(&level);
        }
        if let Some(target) = sqlite_text(row, 2)?.filter(|value| !value.is_empty()) {
            result.targets.increment(&target);
        }
        let Some(body) = sqlite_text(row, 3)? else {
            continue;
        };
        for captures in tool_call_regex().captures_iter(&body) {
            result.tools.increment(&captures["tool"]);
        }
        for captures in model_regex().captures_iter(&body) {
            result.models.increment(&captures["model"]);
        }
        for captures in reasoning_regex().captures_iter(&body) {
            result.reasoning_efforts.increment(&captures["effort"]);
        }
        if !body.contains("post sampling token usage") {
            continue;
        }
        result.post_sampling_rows += 1;
        if let Some(captures) = post_sampling_regex().captures(&body) {
            update_token_turn(&mut turns, &body, timestamp, &captures)?;
        } else if let Some(captures) = turn_id_regex().captures(&body) {
            result
                .tools
                .increment(&format!("post_sampling_unparsed:{}", &captures["turn_id"]));
        }
    }
    result.token_turns = turns.into_values().collect();
    result.token_turns.sort_by(|left, right| {
        (left.timestamp, &left.turn_id).cmp(&(right.timestamp, &right.turn_id))
    });
    if result.token_turns.len() > MAX_TURN_ITEMS {
        result
            .token_turns
            .drain(..result.token_turns.len() - MAX_TURN_ITEMS);
    }
    Ok(result)
}

fn update_token_turn(
    turns: &mut BTreeMap<String, TokenTurn>,
    body: &str,
    timestamp: i64,
    captures: &regex::Captures<'_>,
) -> Result<(), String> {
    let turn_id = captures["turn_id"].to_owned();
    let total_usage_tokens = python_cli_integer::parse(&captures["total"])
        .ok_or_else(|| "invalid integer token usage in SQLite runtime log".to_owned())?;
    let estimated_token_count = estimated_token_regex()
        .captures(body)
        .and_then(|captures| python_cli_integer::parse(&captures["estimated"]));
    let token_limit_reached = token_limit_regex()
        .captures(body)
        .map(|captures| CaseMapper::new().fold_string(&captures["limit"]) == "true");
    let candidate = TokenTurn {
        turn_id: turn_id.clone(),
        timestamp,
        total_usage_tokens,
        estimated_token_count,
        token_limit_reached,
    };
    let replace = turns
        .get(&turn_id)
        .is_none_or(|existing| candidate.total_usage_tokens >= existing.total_usage_tokens);
    if replace {
        turns.insert(turn_id, candidate);
    }
    Ok(())
}

fn post_sampling_regex() -> &'static Regex {
    static REGEX: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
        Regex::new(
            r"turn_id=(?P<turn_id>\S+).*?total_usage_tokens=(?P<total>[\p{Nd}&&\p{Age:15.0}]+)",
        )
        .expect("Codex post-sampling regex is valid")
    });
    &REGEX
}

fn estimated_token_regex() -> &'static Regex {
    static REGEX: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
        Regex::new(r"estimated_token_count=(?:Some\()?(?P<estimated>[\p{Nd}&&\p{Age:15.0}]+)\)?")
            .expect("Codex estimated-token regex is valid")
    });
    &REGEX
}

fn token_limit_regex() -> &'static Regex {
    static REGEX: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
        Regex::new(r"token_limit_reached=(?P<limit>\w+)").expect("Codex token-limit regex is valid")
    });
    &REGEX
}

fn turn_id_regex() -> &'static Regex {
    static REGEX: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
        Regex::new(r"turn\.id=(?P<turn_id>[0-9a-f-]+)").expect("Codex turn id regex is valid")
    });
    &REGEX
}

fn model_regex() -> &'static Regex {
    static REGEX: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
        Regex::new(r"\bmodel=(?P<model>[A-Za-z0-9._-]+)").expect("Codex model regex is valid")
    });
    &REGEX
}

fn reasoning_regex() -> &'static Regex {
    static REGEX: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
        Regex::new(r"codex\.turn\.reasoning_effort=(?P<effort>[A-Za-z0-9._-]+)")
            .expect("Codex reasoning regex is valid")
    });
    &REGEX
}

fn tool_call_regex() -> &'static Regex {
    static REGEX: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
        Regex::new(r"ToolCall:\s*(?P<tool>[A-Za-z0-9_.-]+)")
            .expect("Codex tool call regex is valid")
    });
    &REGEX
}

fn session_thread_id_regex() -> &'static Regex {
    static REGEX: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
        Regex::new(r"(?P<thread_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
            .expect("Codex session thread id regex is valid")
    });
    &REGEX
}

fn read_sqlite_thread_ids(
    path: &Path,
    cutoff: Option<&BigInt>,
) -> Result<BTreeSet<String>, String> {
    if !path.is_file() {
        return Ok(BTreeSet::new());
    }
    let connection = open_readonly_sqlite(path)?;
    let mut query = String::from(
        "SELECT DISTINCT thread_id FROM logs WHERE thread_id IS NOT NULL AND thread_id != ''",
    );
    let cutoff = cutoff
        .map(|value| {
            value
                .to_string()
                .parse::<i64>()
                .map_err(|_| "Python int too large to convert to SQLite INTEGER".to_owned())
        })
        .transpose()?;
    if cutoff.is_some() {
        query.push_str(" AND ts >= ?");
    }
    let mut statement = connection.prepare(&query).map_err(|error| {
        format!(
            "cannot query SQLite runtime log {}: {error}",
            path.display()
        )
    })?;
    let mut rows = if let Some(cutoff) = cutoff {
        statement.query([cutoff]).map_err(|error| {
            format!(
                "cannot query SQLite runtime log {}: {error}",
                path.display()
            )
        })?
    } else {
        statement.query([]).map_err(|error| {
            format!(
                "cannot query SQLite runtime log {}: {error}",
                path.display()
            )
        })?
    };
    let mut thread_ids = BTreeSet::new();
    while let Some(row) = rows
        .next()
        .map_err(|error| format!("cannot read SQLite runtime log {}: {error}", path.display()))?
    {
        if let Some(thread_id) = sqlite_text(row, 0)? {
            if !thread_id.is_empty() {
                thread_ids.insert(thread_id);
            }
        }
    }
    Ok(thread_ids)
}

fn iter_session_paths(
    patterns: &[String],
    cutoff: Option<&BigInt>,
) -> Result<Vec<PathBuf>, String> {
    let mut unique_paths = BTreeMap::<Vec<String>, PathBuf>::new();
    for pattern in patterns {
        for path in python_glob_paths(pattern)? {
            // `glob.glob` runs before `Path.expanduser` in the former Python owner. The shared
            // walker returns absolute matches, so recover the relative match spelling only for
            // a leading tilde pattern before applying the same post-glob expansion.
            let expansion_input = if pattern.starts_with('~') && !Path::new(pattern).is_absolute() {
                let current = env::current_dir().map_err(|error| error.to_string())?;
                path.strip_prefix(current).unwrap_or(&path)
            } else {
                &path
            };
            let expanded = expand_user_path(expansion_input).map_err(|error| error.to_string())?;
            let resolved = resolve_non_strict(&expanded)?;
            let key = python_path_components(&resolved);
            unique_paths.entry(key).or_insert(resolved);
        }
    }
    let mut paths = unique_paths.into_values().collect::<Vec<_>>();
    paths.sort_by_key(|path| python_path_components(path));
    let mut selected = Vec::with_capacity(paths.len());
    for path in paths {
        let Ok(metadata) = fs::metadata(&path) else {
            continue;
        };
        if !metadata.is_file() {
            continue;
        }
        if let Some(cutoff) = cutoff {
            let modified = metadata
                .modified()
                .map_err(|error| format!("cannot stat {}: {error}", path.display()))?;
            let modified = unix_seconds_truncated(modified);
            if BigInt::from(modified) < *cutoff {
                continue;
            }
        }
        selected.push(path);
    }
    Ok(selected)
}

fn python_path_components(path: &Path) -> Vec<String> {
    path.components()
        .map(|component| {
            let value = component.as_os_str().to_string_lossy();
            if cfg!(windows) {
                CaseMapper::new().fold_string(&value)
            } else {
                value.into_owned()
            }
        })
        .collect()
}

fn unix_seconds_truncated(value: SystemTime) -> i64 {
    match value.duration_since(UNIX_EPOCH) {
        Ok(duration) => duration.as_secs() as i64,
        Err(error) => -(error.duration().as_secs() as i64),
    }
}

fn session_thread_id(path: &Path) -> Option<String> {
    let name = path.file_name()?.to_str()?;
    session_thread_id_regex()
        .captures(name)
        .and_then(|captures| captures.name("thread_id"))
        .map(|value| value.as_str().to_owned())
}

fn session_paths_by_thread(paths: &[PathBuf]) -> BTreeMap<String, Vec<PathBuf>> {
    let mut grouped = BTreeMap::<String, Vec<PathBuf>>::new();
    for path in paths {
        if let Some(thread_id) = session_thread_id(path) {
            grouped.entry(thread_id).or_default().push(path.clone());
        }
    }
    for values in grouped.values_mut() {
        values.sort_by_key(|path| python_path_components(path));
    }
    grouped
}

fn discover_thread_ids(
    history_path: &Path,
    sqlite_path: &Path,
    session_paths: &[PathBuf],
    cutoff: Option<&BigInt>,
) -> Result<Vec<String>, String> {
    let mut thread_ids = read_history_thread_ids(history_path, cutoff)?;
    thread_ids.extend(read_sqlite_thread_ids(sqlite_path, cutoff)?);
    for path in session_paths {
        if let Some(thread_id) = session_thread_id(path) {
            thread_ids.insert(thread_id);
        }
    }
    Ok(thread_ids.into_iter().collect())
}

fn read_sessions(paths: &[PathBuf]) -> Result<SessionSummary, String> {
    let mut summary = SessionSummary {
        file_count: 0,
        token_event_count: 0,
        total_tokens: BigInt::from(0_u8),
    };
    for path in paths {
        let mut file_events = 0_usize;
        let mut last_total = BigInt::from(0_u8);
        for_each_python_text_line(path, |raw_line| {
            let line = python_strip(raw_line);
            if line.is_empty() {
                return Ok(());
            }
            let Ok(value) = parse_json(line) else {
                return Ok(());
            };
            if !string_value(object_member(&value, "type"))
                .is_some_and(|value| value == "event_msg")
            {
                return Ok(());
            }
            let payload = object_member(&value, "payload");
            if !string_value(payload.and_then(|value| object_member(value, "type")))
                .is_some_and(|value| value == "token_count")
            {
                return Ok(());
            }
            let info = payload.and_then(|value| object_member(value, "info"));
            if !matches!(info, Some(JsonValue::Object(object)) if !object.0.is_empty()) {
                return Ok(());
            }
            let usage = info.and_then(|value| object_member(value, "total_token_usage"));
            if !matches!(usage, Some(JsonValue::Object(object)) if !object.0.is_empty()) {
                return Ok(());
            }
            let Some(total) =
                python_integer(usage.and_then(|value| object_member(value, "total_tokens")))
            else {
                return Ok(());
            };
            file_events += 1;
            last_total = total;
            Ok(())
        })?;
        if file_events > 0 {
            summary.file_count += 1;
            summary.token_event_count += file_events;
            summary.total_tokens += last_total;
        }
    }
    Ok(summary)
}

fn read_existing_summary_ids(path: &Path) -> Result<HashSet<String>, String> {
    if !path.is_file() {
        return Ok(HashSet::new());
    }
    let mut ids = HashSet::new();
    for_each_python_text_line(path, |raw_line| {
        let line = python_strip(raw_line);
        if line.is_empty() {
            return Ok(());
        }
        let Ok(value) = parse_json(line) else {
            return Ok(());
        };
        if let Some(summary_id) = string_value(object_member(&value, "summary_id")) {
            ids.insert(summary_id);
        }
        Ok(())
    })?;
    Ok(ids)
}

fn json_big_integer(value: &BigInt) -> Result<SerdeValue, String> {
    serde_json::from_str(&value.to_string())
        .map(SerdeValue::Number)
        .map_err(|error| format!("cannot serialize Python integer: {error}"))
}

fn epoch_to_utc(value: Option<i64>) -> Result<SerdeValue, String> {
    let Some(value) = value else {
        return Ok(SerdeValue::Null);
    };
    let timestamp = OffsetDateTime::from_unix_timestamp(value)
        .map_err(|error| format!("timestamp is outside datetime range: {error}"))?;
    let text = timestamp
        .format(&Rfc3339)
        .map_err(|error| format!("cannot format UTC timestamp: {error}"))?;
    Ok(SerdeValue::String(text))
}

fn epoch_bigint_to_utc(value: Option<&BigInt>) -> Result<SerdeValue, String> {
    let Some(value) = value else {
        return Ok(SerdeValue::Null);
    };
    let timestamp = value
        .to_string()
        .parse::<i64>()
        .map_err(|_| "timestamp is outside datetime range".to_owned())?;
    epoch_to_utc(Some(timestamp))
}

fn json_value(value: &SerdeValue) -> Result<JsonValue, String> {
    let text = serde_json::to_string(value)
        .map_err(|error| format!("cannot serialize Python JSON value: {error}"))?;
    parse_json(&text)
}

fn summary_payload(
    paths: &SummaryPaths<'_>,
    thread_id: &str,
    history: &HistorySummary,
    sqlite_summary: &SqliteSummary,
    sessions: &SessionSummary,
    recent_days: Option<&BigInt>,
) -> Result<SummaryOutput, String> {
    let source_root = paths.source_root;
    let canon_root = paths.canon_root;
    let history_path = paths.history_path;
    let sqlite_path = paths.sqlite_path;
    let live_total_usage_tokens = sqlite_summary
        .token_turns
        .iter()
        .fold(BigInt::from(0_u8), |sum, turn| {
            sum + &turn.total_usage_tokens
        });
    let latest_turn = sqlite_summary.token_turns.last();
    let recorded_at = utc_now();
    let source_repo_key = repo_key(source_root)?;
    let source_root_text = path_posix(source_root);
    let canon_root_text = path_posix(canon_root);
    let agent_canon_git_head = source_git_head(canon_root)?;
    let live_turn_count = sqlite_summary.token_turns.len();
    let latest_turn_id = latest_turn.map_or_else(String::new, |turn| turn.turn_id.clone());
    let recent_days_value = match recent_days {
        Some(value) => json_big_integer(value)?,
        None => SerdeValue::String("all".to_owned()),
    };
    let token_turns = sqlite_summary
        .token_turns
        .iter()
        .map(|turn| {
            Ok(json!({
                "turn_id": turn.turn_id,
                "timestamp": epoch_to_utc(Some(turn.timestamp))?,
                "total_usage_tokens": json_big_integer(&turn.total_usage_tokens)?,
                "estimated_token_count": match &turn.estimated_token_count {
                    Some(value) => json_big_integer(value)?,
                    None => SerdeValue::Null,
                },
                "token_limit_reached": turn.token_limit_reached,
            }))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let stable_payload = json!({
        "schema": SUMMARY_SCHEMA,
        "source_repo_key": source_repo_key,
        "source_root": source_root_text,
        "canon_root": canon_root_text,
        "agent_canon_git_head": agent_canon_git_head,
        "conversation_id": thread_id,
        "session_id": thread_id,
        "thread_id": thread_id,
        "recent_days": recent_days_value,
        "history": {
            "entry_count": history.entry_count as u64,
            "first_timestamp": epoch_bigint_to_utc(history.first_ts.as_ref())?,
            "last_timestamp": epoch_bigint_to_utc(history.last_ts.as_ref())?,
        },
        "sqlite": {
            "row_count": sqlite_summary.row_count as u64,
            "estimated_bytes": json_big_integer(&sqlite_summary.estimated_bytes)?,
            "first_timestamp": epoch_to_utc(sqlite_summary.first_ts)?,
            "last_timestamp": epoch_to_utc(sqlite_summary.last_ts)?,
            "post_sampling_rows": sqlite_summary.post_sampling_rows as u64,
            "target_counts": sqlite_summary.targets.compact_json(),
            "level_counts": sqlite_summary.levels.compact_json(),
        },
        "tokens": {
            "live_turn_count": live_turn_count as u64,
            "live_total_usage_tokens": json_big_integer(&live_total_usage_tokens)?,
            "latest_turn_id": latest_turn_id,
            "latest_total_usage_tokens": match latest_turn {
                Some(turn) => json_big_integer(&turn.total_usage_tokens)?,
                None => SerdeValue::from(0),
            },
            "latest_estimated_token_count": match latest_turn.and_then(|turn| turn.estimated_token_count.as_ref()) {
                Some(value) => json_big_integer(value)?,
                None => SerdeValue::Null,
            },
            "legacy_session_count": sessions.file_count as u64,
            "legacy_session_token_events": sessions.token_event_count as u64,
            "legacy_session_total_tokens": json_big_integer(&sessions.total_tokens)?,
        },
        "runtime": {
            "model_counts": sqlite_summary.models.compact_json(),
            "reasoning_effort_counts": sqlite_summary.reasoning_efforts.compact_json(),
            "tool_call_counts": sqlite_summary.tools.compact_json(),
        },
        "token_turns": token_turns,
        "sources": {
            "history_jsonl": path_posix(history_path),
            "sqlite_log": path_posix(sqlite_path),
        },
    });
    let stable = json_value(&stable_payload)?;
    let stable_bytes = canonical_json_ascii_bytes(&stable)?;
    let digest = Sha256::digest(&stable_bytes);
    let summary_id = digest[..SUMMARY_ID_DIGEST_LENGTH / 2]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let mut payload = stable_payload;
    let payload_map = payload
        .as_object_mut()
        .expect("summary payload is an object");
    payload_map.insert(
        "recorded_at".to_owned(),
        SerdeValue::String(recorded_at.clone()),
    );
    payload_map.insert(
        "summary_id".to_owned(),
        SerdeValue::String(summary_id.clone()),
    );
    let payload = json_value(&payload)?;
    Ok(SummaryOutput {
        payload,
        summary_id,
        recorded_at,
        source_repo_key,
        thread_id: thread_id.to_owned(),
        history_entry_count: history.entry_count,
        sqlite_row_count: sqlite_summary.row_count,
        live_total_usage_tokens,
        live_turn_count,
        latest_turn_id,
    })
}

fn summary_index_payload(
    summary: &SummaryOutput,
    summary_path: &Path,
    index_path: &Path,
) -> Result<JsonValue, String> {
    let relative_summary_path = match index_path.parent() {
        Some(parent) => summary_path
            .strip_prefix(parent)
            .map(path_posix)
            .unwrap_or_else(|_| path_posix(summary_path)),
        None => path_posix(summary_path),
    };
    json_value(&json!({
        "schema": INDEX_SCHEMA,
        "summary_id": summary.summary_id,
        "recorded_at": summary.recorded_at,
        "source_repo_key": summary.source_repo_key,
        "conversation_id": summary.thread_id,
        "session_id": summary.thread_id,
        "thread_id": summary.thread_id,
        "summary_path": relative_summary_path,
        "history_entry_count": summary.history_entry_count as u64,
        "sqlite_row_count": summary.sqlite_row_count as u64,
        "live_total_usage_tokens": json_big_integer(&summary.live_total_usage_tokens)?,
        "live_turn_count": summary.live_turn_count as u64,
        "latest_turn_id": summary.latest_turn_id,
    }))
}
