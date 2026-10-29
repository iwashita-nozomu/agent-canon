// @dependency-start
// contract implementation
// responsibility Owns native private feedback/knowledge storage and body-free receipts.
// upstream design ../../../../../documents/runtime/private-feedback-knowledge.md command and storage contract
// upstream implementation runtime_boundary.rs owns handle-relative runtime files and locks
// downstream implementation ../../../../../tests/agent_tools/test_private_feedback.py verifies public behavior
// @dependency-end

use crate::runtime_boundary::RuntimeDirectory;
use regex::Regex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

const SCHEMA: &str = "agent-canon.private-feedback.v1";
const REQUEST_SCHEMA: &str = "agent-canon.private-feedback-sync-request.v1";
const REQUEST: &str = "sync-request.json";
const LOCK: &str = "spool/.private-feedback.lock";
const CAPTURE_LIMIT: usize = 16 * 1024;
type Metadata = BTreeMap<String, String>;

#[derive(Debug)]
struct Failure {
    code: &'static str,
    detail: &'static str,
}
type Result<T> = std::result::Result<T, Failure>;

fn fail(code: &'static str, detail: &'static str) -> Failure {
    Failure { code, detail }
}

fn storage(_: io::Error) -> Failure {
    fail("storage_failed", "private storage operation failed")
}

fn write_error(error: io::Error) -> Failure {
    if error.kind() == io::ErrorKind::AlreadyExists {
        fail("content_conflict", "existing private record differs")
    } else {
        storage(error)
    }
}

#[derive(Default)]
struct Args {
    runtime: Option<String>,
    log: Option<String>,
    run: String,
    task: String,
    family: String,
    operation: String,
    topic: String,
    text: Vec<String>,
    stdin: bool,
    show: bool,
    structured: bool,
    query: String,
}

fn looks_like_option(value: &str) -> bool {
    static NEGATIVE_NUMBER: OnceLock<Regex> = OnceLock::new();
    value.starts_with('-') && value != "-" &&
        !NEGATIVE_NUMBER.get_or_init(|| Regex::new(r"^-\d+$|^-\d*\.\d+$")
            .expect("static argparse negative-number expression")).is_match(value)
}

fn option_value(raw: &[String], index: usize) -> Result<String> {
    let value = raw.get(index + 1).filter(|value| !looks_like_option(value))
        .ok_or_else(|| fail("usage", "option value required"))?;
    Ok(value.clone())
}

/// Like the inventory parser, help is an ordered parse result, not a raw scan.
fn parse(raw: &[String]) -> Result<Option<Args>> {
    let mut args = Args::default();
    let mut rest = Vec::new();
    let mut index = 0;
    while index < raw.len() {
        if raw[index] == "--" {
            rest.extend(raw[index..].iter().cloned());
            break;
        }
        let destination = match raw[index].as_str() {
            "--runtime-root" => Some(0),
            "--log-root" => Some(1),
            "--run" => Some(2),
            "--task" => Some(3),
            _ => None,
        };
        if let Some(destination) = destination {
            let value = option_value(raw, index)?;
            match destination {
                0 => args.runtime = Some(value),
                1 => args.log = Some(value),
                2 => args.run = value,
                _ => args.task = value,
            }
            index += 2;
        } else {
            rest.push(raw[index].clone());
            index += 1;
        }
    }
    args.family = rest.first().ok_or_else(|| fail("usage", "family required"))?.clone();
    if matches!(args.family.as_str(), "-h" | "--help") {
        return Ok(None);
    }
    let knowledge = matches!(args.family.as_str(), "knowledge" | "k");
    if !knowledge && !matches!(args.family.as_str(), "feedback" | "f") {
        return Err(fail("usage", "unknown private feedback family"));
    }
    // argparse defers unknown options, but an invalid command choice is immediate.
    let mut unknown = false;
    index = 1;
    while index < rest.len() {
        if matches!(rest[index].as_str(), "-h" | "--help") {
            return Ok(None);
        }
        if looks_like_option(&rest[index]) {
            if rest[index] == "--" {
                return Err(fail("usage", "operation required before literal arguments"));
            }
            unknown = true;
            index += 1;
        } else {
            args.operation = rest[index].clone();
            index += 1;
            break;
        }
    }
    if !matches!(args.operation.as_str(), "add" | "capture" | "status" | "sync")
        && !(knowledge && matches!(args.operation.as_str(), "read" | "search"))
    {
        return Err(fail("usage", "unknown private feedback operation"));
    }
    let mut literal = false;
    let mut topic_present = false;
    while index < rest.len() {
        let value = &rest[index];
        if !literal {
            match value.as_str() {
                "-h" | "--help" => return Ok(None),
                "--" => {
                    literal = true;
                    index += 1;
                    continue;
                }
                "--stdin" if matches!(args.operation.as_str(), "add" | "capture") => {
                    args.stdin = true;
                    index += 1;
                    continue;
                }
                "--show" if args.operation == "read" => {
                    args.show = true;
                    index += 1;
                    continue;
                }
                "--structured-log" if args.operation == "capture" => {
                    args.structured = true;
                    index += 1;
                    continue;
                }
                "--query" if args.operation == "search" => {
                    args.query = option_value(&rest, index)?;
                    index += 2;
                    continue;
                }
                _ if looks_like_option(value) => {
                    unknown = true;
                    index += 1;
                    continue;
                }
                _ => {}
            }
        }
        if !topic_present && matches!(args.operation.as_str(), "add" | "read") {
            args.topic = value.clone();
            topic_present = true;
        } else if matches!(args.operation.as_str(), "add" | "capture") {
            args.text.push(value.clone());
        } else {
            unknown = true;
        }
        index += 1;
    }
    if matches!(args.operation.as_str(), "add" | "read") && !topic_present {
        return Err(fail("usage", "topic required"));
    }
    if unknown {
        return Err(fail("usage", "unsupported private feedback argument"));
    }
    if args.structured && (!args.stdin || !args.text.is_empty()) {
        return Err(fail("input_required", "structured capture requires --stdin"));
    }
    Ok(Some(args))
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn topic_slug(value: &str) -> Result<String> {
    let mut slug = String::new();
    let mut separator = false;
    for character in value.trim().to_lowercase().chars() {
        if character.is_ascii_lowercase() || character.is_ascii_digit() {
            if separator && !slug.is_empty() {
                slug.push('-');
            }
            slug.push(character);
            separator = false;
        } else {
            separator = true;
        }
    }
    if slug.is_empty() || slug.len() > 96 {
        return Err(fail("topic_invalid", "topic must be lowercase ASCII and non-empty"));
    }
    Ok(slug)
}

fn sensitive(body: &str) -> bool {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(
        r"(?is)(?:\b(?:password|passwd|secret|token|api[_ -]?key|authorization|cookie)\b\s*[:=]\s*\S+|\bBearer\s+\S+|-----BEGIN (?:OPENSSH|RSA|EC|PRIVATE) KEY-----)"
    ).expect("static private feedback redaction expression")).is_match(&body.replace(['\u{0130}', '\u{0131}'], "i"))
}

fn body(args: &Args) -> Result<(String, &'static str)> {
    if args.stdin != args.text.is_empty() {
        return Err(fail("input_required", "provide direct prose or --stdin, exactly once"));
    }
    let mut value = if args.stdin {
        let mut value = String::new();
        io::stdin().read_to_string(&mut value).map_err(|_| fail("body_invalid", "body must be UTF-8 text"))?;
        value
    } else {
        args.text.join(" ").trim().to_string()
    };
    if args.structured {
        if value.len() > CAPTURE_LIMIT || sensitive(&value) {
            return Err(fail("private_data_rejected", "structured feedback is not a permitted private payload"));
        }
        return Ok((format!("{}\n", value.trim()), "structured-log"));
    }
    if value.trim().is_empty() || value.contains('\0') {
        return Err(fail("body_invalid", "body must be non-empty UTF-8 text"));
    }
    if sensitive(&value) {
        return Err(fail("private_data_rejected", "credential-shaped or private payload is not accepted"));
    }
    if args.operation == "capture" {
        value = value.trim().to_string();
    }
    value.truncate(value.trim_end().len());
    value.push('\n');
    if args.operation == "capture" && value.len() > CAPTURE_LIMIT {
        return Err(fail("capture_too_large", "structured capture exceeds 16 KiB"));
    }
    // Public capture historically normalizes through the text-add operation.
    let mode = if args.stdin && args.operation != "capture" { "stdin" } else { "text" };
    Ok((value, mode))
}

fn now() -> Result<String> {
    OffsetDateTime::now_utc().replace_nanosecond(0)
        .map_err(|_| fail("clock_failed", "UTC timestamp unavailable"))?
        .format(&Rfc3339).map_err(|_| fail("clock_failed", "UTC timestamp unavailable"))
}

fn source_commit() -> String {
    let configured = env::var("AGENT_CANON_SOURCE_COMMIT").unwrap_or_default();
    let configured = configured.trim();
    if (40..=64).contains(&configured.len()) && configured.bytes().all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value)) {
        return configured.to_string();
    }
    Command::new("git").args(["rev-parse", "--verify", "HEAD"]).output().ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_string())
        .unwrap_or_else(|| "unknown".to_string())
}

fn expanded_absolute(value: &str, code: &'static str) -> Result<PathBuf> {
    let value = if value == "~" || value.starts_with("~/") || (cfg!(windows) && value.starts_with("~\\")) {
        #[cfg(windows)]
        let home = env::var_os("USERPROFILE").or_else(|| {
            let mut drive = env::var_os("HOMEDRIVE").unwrap_or_default();
            drive.push(env::var_os("HOMEPATH")?);
            Some(drive)
        });
        #[cfg(not(windows))]
        let home = env::var_os("HOME");
        let home = home.ok_or_else(|| fail(code, "home directory unavailable"))?;
        PathBuf::from(home).join(value.get(2..).unwrap_or(""))
    } else {
        PathBuf::from(value)
    };
    if !value.is_absolute() {
        return Err(fail(code, "configured root must be absolute"));
    }
    Ok(value)
}

fn log_root(args: &Args) -> Result<PathBuf> {
    let configured = args.log.clone().filter(|value| !value.is_empty())
        .or_else(|| env::var("AGENT_CANON_LOG_ROOT").ok().filter(|value| !value.trim().is_empty()))
        .or_else(|| env::var("AGENT_CANON_CONTROL_PARENT_ROOT").ok().filter(|value| !value.trim().is_empty())
            .map(|parent| PathBuf::from(parent.trim()).join("agent-canon-log").to_string_lossy().into_owned()))
        .ok_or_else(|| fail("log_root_required", "pass --log-root or set AGENT_CANON_LOG_ROOT/AGENT_CANON_CONTROL_PARENT_ROOT"))?;
    let path = expanded_absolute(configured.trim(), "log_root_invalid")?;
    // Preserve the configured missing-log case without creating its checkout.
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {},
            Component::ParentDir => { normalized.pop(); },
            value => normalized.push(value.as_os_str()),
        }
    }
    let mut ancestor = normalized.clone();
    let mut suffix = Vec::new();
    while !ancestor.exists() {
        let name = ancestor.file_name().ok_or_else(|| fail("log_root_invalid", "private log root is unavailable"))?;
        suffix.push(name.to_os_string());
        ancestor.pop();
    }
    let mut resolved = std::fs::canonicalize(ancestor).map_err(storage)?;
    for name in suffix.into_iter().rev() {
        resolved.push(name);
    }
    Ok(resolved)
}

struct Store {
    runtime: RuntimeDirectory,
    spool: RuntimeDirectory,
}
impl Store {
    fn open(args: &Args) -> Result<Self> {
        let configured = args.runtime.clone().filter(|value| !value.is_empty())
            .or_else(|| env::var("AGENT_CANON_RUNTIME_ROOT").ok().filter(|value| !value.trim().is_empty()))
            .ok_or_else(|| fail("runtime_root_required", "pass --runtime-root or set AGENT_CANON_RUNTIME_ROOT"))?;
        let path = expanded_absolute(configured.trim(), "runtime_root_invalid")?;
        let runtime = RuntimeDirectory::open(&path, true).map_err(storage)?;
        let spool = runtime.child(Path::new("spool/private-feedback"), true).map_err(storage)?;
        spool.make_private().map_err(storage)?;
        Ok(Self { runtime, spool })
    }

    fn locked<T>(&self, operation: impl FnOnce() -> Result<T>) -> Result<T> {
        let lock = self.runtime.lock(Path::new(LOCK)).map_err(storage)?;
        let result = operation();
        let unlocked = lock.finish().map_err(storage);
        match result {
            Err(error) => Err(error),
            Ok(value) => { unlocked?; Ok(value) },
        }
    }

    fn sync_request(&self) -> Result<bool> {
        let existing = self.spool.read(Path::new(REQUEST))
            .map_err(|_| fail("sync_request_invalid", "private feedback sync request is invalid"))?;
        if let Some(bytes) = existing {
            let request: Value = serde_json::from_slice(&bytes)
                .map_err(|_| fail("sync_request_invalid", "private feedback sync request is invalid"))?;
            if request.get("schema").and_then(Value::as_str) != Some(REQUEST_SCHEMA)
                || request.get("operation").and_then(Value::as_str) != Some("sync")
                || request.get("execution_plane").and_then(Value::as_str) != Some("agentcanon_tool_container")
            {
                return Err(fail("sync_request_invalid", "private feedback sync request schema is invalid"));
            }
            return Ok(true);
        }
        let request = json!({
            "schema": REQUEST_SCHEMA, "operation": "sync",
            "execution_plane": "agentcanon_tool_container",
            "requested_at": now()?, "source_commit": source_commit()
        });
        let mut bytes = serde_json::to_vec(&request).map_err(|_| fail("serialization_failed", "private request serialization failed"))?;
        bytes.push(b'\n');
        self.spool.write_once(Path::new(REQUEST), &bytes).map_err(write_error)?;
        Ok(false)
    }
}

fn scope(args: &Args) -> (String, String) {
    if args.structured {
        return (args.run.clone(), args.task.clone());
    }
    let run = if args.run.is_empty() { env::var("AGENT_CANON_RUN_ID").unwrap_or_default() } else { args.run.clone() };
    let task = if args.task.is_empty() { env::var("AGENT_CANON_TASK_ID").unwrap_or_default() } else { args.task.clone() };
    (run.trim().to_string(), task.trim().to_string())
}

fn metadata(kind: &str, topic: &str, locator: &str, content_digest: &str, scope: (&str, &str), input_mode: &str, status: &str) -> Metadata {
    let (run, task) = scope;
    [
        ("schema", SCHEMA), ("kind", kind), ("topic", topic), ("locator", locator),
        ("content_digest", &format!("sha256:{content_digest}")),
        ("source_commit", &source_commit()), ("run", run), ("task", task),
        ("input_mode", input_mode), ("status", status),
    ].into_iter().map(|(key, value)| (key.to_string(), value.to_string())).collect()
}

fn frontmatter(meta: &Metadata, body: &str) -> String {
    format!(
        "---\nkind: {}\ntopic: {}\nsource_locator: {}\nsource_digest: {}\nrun: {}\ninput_mode: {}\nstatus: {}\n---\n\n{}\n",
        meta["kind"], meta["topic"], meta["locator"], meta["content_digest"], meta["run"],
        meta["input_mode"], meta["status"], body.trim_end()
    )
}

fn emit(value: &impl serde::Serialize) -> Result<()> {
    let mut out = io::stdout().lock();
    serde_json::to_writer(&mut out, value).map_err(|_| fail("output_failed", "metadata output failed"))?;
    out.write_all(b"\n").map_err(|_| fail("output_failed", "metadata output failed"))
}

fn add(args: &Args) -> Result<()> {
    let (body, mode) = body(args)?;
    let capture = args.operation == "capture";
    let kind = if !capture && matches!(args.family.as_str(), "knowledge" | "k") { "knowledge" } else { "feedback" };
    let topic = if capture { "runtime-feedback".to_string() } else { topic_slug(&args.topic)? };
    let store = Store::open(args)?;
    let (run, task) = scope(args);
    let hash = digest(body.as_bytes());
    let locator = if kind == "feedback" { format!("feedback/{topic}/{}.md", &hash[..16]) } else { format!("knowledge/topics/{topic}/candidate.md") };
    let mut meta = metadata(kind, &topic, &locator, &hash, (&run, &task), mode, if kind == "feedback" { "observed" } else { "candidate" });
    let reused = store.locked(|| {
        store.spool.write_once(Path::new(&locator), frontmatter(&meta, &body).as_bytes()).map_err(write_error)?;
        store.sync_request()
    })?;
    if !args.structured {
        meta.insert("status".to_string(), "spooled".to_string());
    }
    meta.insert("sync_request".to_string(), if reused { "reused" } else { "created" }.to_string());
    emit(&meta)
}

fn text(bytes: Vec<u8>) -> Result<String> {
    String::from_utf8(bytes).map_err(|_| fail("record_invalid", "private record is not UTF-8"))
}

fn distinct_scopes(contents: &str) -> BTreeSet<String> {
    let mut scopes = BTreeSet::new();
    let (mut run, mut task) = (String::new(), String::new());
    for line in contents.lines().chain(std::iter::once("## Read receipt")) {
        if let Some(value) = line.strip_prefix("run:") {
            run = value.trim().to_string();
        } else if let Some(value) = line.strip_prefix("task:") {
            task = value.trim().to_string();
        } else if line == "## Read receipt" {
            if !task.is_empty() { scopes.insert(format!("task:{task}")); }
            else if !run.is_empty() { scopes.insert(format!("run:{run}")); }
            run.clear();
            task.clear();
        }
    }
    scopes
}

fn skill_content(topic: &str, body: &str, hash: &str, scopes: &BTreeSet<String>) -> String {
    format!(
        "---\nkind: skill-candidate\ntopic: {topic}\nsource_locator: knowledge/topics/{topic}/candidate.md\nsource_digest: sha256:{hash}\nrun: private-feedback-promotion\ninput_mode: structured-log\nstatus: candidate\n---\n\n# {topic}\n\n{}\n\n## Evidence\n\nRepeated private reads in distinct task/run scopes:\n{}\n\n## Use and limits\n\nUse only for the private runtime context represented by the source feedback.\nThis candidate is not public AgentCanon policy and is not approval or proof.\n",
        body.trim_end(), scopes.iter().map(|scope| format!("- {scope}")).collect::<Vec<_>>().join("\n")
    )
}

fn read(args: &Args) -> Result<()> {
    let topic = topic_slug(&args.topic)?;
    let store = Store::open(args)?;
    let log = log_root(args)?;
    store.locked(|| {
        let relative = PathBuf::from(format!("knowledge/topics/{topic}/candidate.md"));
        let archived = match RuntimeDirectory::open(&log, false) {
            Ok(root) => root.read_candidate(&relative).map_err(storage)?,
            Err(error) if error.kind() == io::ErrorKind::NotFound => None,
            Err(error) => return Err(storage(error)),
        };
        let bytes = match archived {
            Some(bytes) => Some(bytes),
            None => store.spool.read_candidate(&relative).map_err(storage)?,
        }
            .ok_or_else(|| fail("knowledge_not_found", "private knowledge candidate is unavailable"))?;
        let contents = text(bytes)?;
        let body = if contents.starts_with("---") { contents.splitn(3, "---").last().unwrap_or("").trim() } else { contents.trim() };
        let hash = digest(body.as_bytes());
        let (run, task) = scope(args);
        let receipt_path = PathBuf::from(format!("knowledge/topics/{topic}/read-receipt.md"));
        let old = text(store.spool.read(&receipt_path).map_err(storage)?.unwrap_or_default())?;
        let duplicate = if !task.is_empty() { old.contains(&format!("task: {task}")) } else if !run.is_empty() { old.contains(&format!("run: {run}")) } else { false };
        let receipt = format!(
            "## Read receipt\nkind: knowledge-read-receipt\ntopic: {topic}\ncandidate_locator: knowledge/topics/{topic}/candidate.md\ncandidate_digest: sha256:{hash}\nreader: agent-canon\nread_at: {}\nrun: {run}\ntask: {task}\nsource_commit: {}\nresult: read\n",
            now()?, source_commit()
        );
        if !duplicate {
            let separator = if !old.is_empty() && !old.ends_with('\n') { "\n" } else { "" };
            store.spool.append(&receipt_path, format!("{separator}{receipt}").as_bytes()).map_err(storage)?;
        }
        let scopes = distinct_scopes(&format!("{old}{}", if duplicate { String::new() } else { format!("\n{receipt}") }));
        let promoted = scopes.len() >= 2;
        if promoted {
            let skill = skill_content(&topic, body, &hash, &scopes);
            store.spool.write_once(Path::new(&format!("runtime/skills/{topic}/SKILL.md")), skill.as_bytes()).map_err(write_error)?;
            store.runtime.write_once(Path::new(&format!("private-skills/{topic}/SKILL.md")), skill.as_bytes()).map_err(write_error)?;
        }
        let mut meta = metadata("knowledge-read-receipt", &topic, &relative.to_string_lossy().replace('\\', "/"), &hash, (&run, &task), "read", if duplicate { "duplicate" } else { "read" });
        meta.insert("promotion".to_string(), if promoted { "private-skill-candidate" } else { "none" }.to_string());
        emit(&meta)?;
        if args.show {
            let mut output = io::stdout().lock();
            writeln!(output, "{body}").map_err(|_| fail("output_failed", "private display failed"))?;
        }
        Ok(())
    })
}

fn git_output(root: &Path, args: &[&str]) -> String {
    Command::new("git").arg("-C").arg(root).args(args).output().ok()
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_string()).unwrap_or_default()
}

fn status(args: &Args) -> Result<()> {
    let store = Store::open(args)?;
    let log = log_root(args)?;
    let mut count = 0;
    for family in ["feedback", "knowledge", "runtime", "private-skills"] {
        count += store.spool.files(Path::new(family)).map_err(storage)?.len();
    }
    let mut meta: Metadata = [
        ("schema".to_string(), SCHEMA.to_string()),
        ("status".to_string(), if count == 0 { "clean" } else { "pending" }.to_string()),
        ("pending".to_string(), count.to_string()),
        ("log_root".to_string(), log.to_string_lossy().into_owned()),
    ].into_iter().collect();
    if log.exists() {
        meta.insert("branch".to_string(), git_output(&log, &["branch", "--show-current"]));
        meta.insert("remote".to_string(), git_output(&log, &["remote", "get-url", "origin"]));
    }
    emit(&meta)
}

fn search(args: &Args) -> Result<()> {
    let store = Store::open(args)?;
    let log = log_root(args)?;
    let query = args.query.trim().to_lowercase();
    let mut results = Vec::new();
    let mut collect = |root: &RuntimeDirectory| -> Result<()> {
        for family in ["knowledge", "feedback"] {
            for path in root.files(Path::new(family)).map_err(storage)? {
                let locator = path.to_string_lossy().replace('\\', "/");
                if path.extension().and_then(|value| value.to_str()) != Some("md")
                    || (!query.is_empty() && !locator.to_lowercase().contains(&query)) { continue; }
                if let Some(bytes) = root.read(&path).map_err(storage)? {
                    results.push(json!({"locator": locator, "content_digest": format!("sha256:{}", digest(&bytes)), "status": "spooled"}));
                }
            }
        }
        Ok(())
    };
    collect(&store.spool)?;
    match RuntimeDirectory::open(&log, false) {
        Ok(root) => collect(&root)?,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {},
        Err(error) => return Err(storage(error)),
    }
    emit(&json!({"schema": SCHEMA, "status": "ok", "results": results}))
}

fn execute(args: &Args) -> Result<()> {
    match args.operation.as_str() {
        "add" | "capture" => add(args),
        "read" => read(args),
        "status" => status(args),
        "search" => search(args),
        "sync" => {
            let store = Store::open(args)?;
            let reused = store.locked(|| store.sync_request())?;
            emit(&json!({"schema": SCHEMA, "status": "requested", "execution_plane": "agentcanon_tool_container", "request": "private-feedback-sync", "request_reused": if reused { "yes" } else { "no" }}))
        }
        _ => Err(fail("operation_invalid", "private feedback operation is invalid")),
    }
}

pub fn run(args: &[String]) -> i32 {
    let outcome = match parse(args) {
        Ok(None) => {
            println!("Private AgentCanon feedback and knowledge\nagent-canon <knowledge|k|feedback|f> <add|capture|read|search|status|sync>\nGlobal options: --runtime-root PATH --log-root PATH --run ID --task ID\nadd TOPIC [TEXT ... | --stdin]; capture [TEXT ... | --stdin] [--structured-log]\nknowledge read TOPIC [--show]; knowledge search [--query TEXT]");
            return 0;
        }
        Ok(Some(args)) => execute(&args),
        Err(error) => Err(error),
    };
    match outcome {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("{}", json!({"schema": SCHEMA, "status": "error", "code": error.code, "detail": error.detail}));
            2
        }
    }
}
