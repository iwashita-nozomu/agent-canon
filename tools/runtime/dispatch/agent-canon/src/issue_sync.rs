// @dependency-start
// contract implementation
// responsibility Reads repository-qualified GitHub Issues and projects existing Issue clauses.
// upstream design ../../../../../documents/runtime/private-feedback-knowledge.md owns private offline packet storage
// upstream design ../../../../../agents/skills/issue-finding-report.md owns Issue publication decisions
// downstream test ../tests/issue_sync_native.rs verifies readback and offline identities
// @dependency-end

use crate::python_text::{python_splitlines, python_strip};
use icu_casemap::CaseMapper;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

const PACKET: &str = "agent-canon.feedback.issue-packet.v1";
#[derive(Debug)]
pub(crate) struct Failure {
    pub(crate) code: &'static str,
    pub(crate) detail: String,
}
type Result<T> = std::result::Result<T, Failure>;
fn fail(code: &'static str, detail: impl Into<String>) -> Failure {
    Failure {
        code,
        detail: detail.into(),
    }
}
fn io(error: impl std::fmt::Display) -> Failure {
    fail("storage_failed", error.to_string())
}
pub(crate) fn normalized_repository(value: &str) -> String {
    let mut value = python_strip(value);
    if let Some((_, rest)) = value.split_once("://") {
        value = rest.split_once('/').map_or("", |(_, path)| path);
    } else if value.starts_with("git@") {
        value = value.split_once(':').map_or(value, |(_, path)| path);
    }
    value = value
        .split(['?', '#'])
        .next()
        .unwrap_or(value)
        .trim_matches('/');
    let value = if CaseMapper::new().fold_string(value).ends_with(".git") {
        &value[..value.len() - 4]
    } else {
        value
    };
    let parts: Vec<_> = value.split('/').filter(|value| !value.is_empty()).collect();
    CaseMapper::new().fold_string(&parts[parts.len().saturating_sub(2)..].join("/"))
}
fn repo_path(repository: &str) -> Result<String> {
    let raw = repository.trim().replace('\\', "/");
    if raw.split('/').any(|value| ["", ".", ".."].contains(&value)) {
        return Err(fail(
            "issue_receipt_repository_invalid",
            "publication receipt repository contains an empty or dot path component",
        ));
    }
    let value = normalized_repository(repository);
    let parts: Vec<_> = value.split('/').collect();
    if parts.len() != 2
        || parts.iter().any(|part| {
            !part.bytes().all(|value| {
                value.is_ascii_lowercase() || value.is_ascii_digit() || b"_.-".contains(&value)
            })
        })
    {
        return Err(fail(
            "issue_receipt_repository_invalid",
            "publication receipt repository must be owner/repository",
        ));
    }
    Ok(value)
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Reference {
    pub(crate) repo: String,
    pub(crate) number: String,
    pub(crate) url: String,
}
pub(crate) fn reference(value: &str, default: &str) -> Result<Reference> {
    let value = value.trim();
    let (repo, number) = if let Some(value) = value.strip_prefix("https://github.com/") {
        let (repo, number) = value.split_once("/issues/").ok_or_else(|| {
            fail(
                "github_issue_invalid",
                "Issue identity must be a GitHub URL or owner/repo#number",
            )
        })?;
        (normalized_repository(repo), number)
    } else if let Some((repo, number)) = value.split_once('#') {
        (normalized_repository(repo), number)
    } else {
        (normalized_repository(default), value)
    };
    if repo.split('/').count() != 2
        || number.is_empty()
        || number.starts_with('0')
        || !number.bytes().all(|value| value.is_ascii_digit())
    {
        return Err(fail(
            "github_issue_invalid",
            "Issue identity must be a GitHub URL or owner/repo#number",
        ));
    }
    Ok(Reference {
        url: format!("https://github.com/{repo}/issues/{number}"),
        repo,
        number: number.into(),
    })
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Issue {
    repository: String,
    number: String,
    title: String,
    body: String,
    state: String,
    url: String,
}
pub(crate) fn state(value: &str) -> Result<String> {
    let state = CaseMapper::new().fold_string(python_strip(value));
    if !["open", "closed"].contains(&state.as_str()) {
        return Err(fail(
            "issue_state_invalid",
            "GitHub Issue state must be open or closed",
        ));
    }
    Ok(state)
}
fn gh(args: &[String]) -> Result<String> {
    let result = Command::new("gh")
        .args(args)
        .output()
        .map_err(|error| fail("github_adapter_failed", error.to_string()))?;
    if !result.status.success() {
        return Err(fail(
            "github_adapter_failed",
            String::from_utf8_lossy(&result.stderr)
                .lines()
                .last()
                .unwrap_or("GitHub adapter failed")
                .chars()
                .take(240)
                .collect::<String>(),
        ));
    }
    String::from_utf8(result.stdout)
        .map_err(|error| fail("github_readback_invalid", error.to_string()))
}
fn read(reference: &Reference) -> Result<Issue> {
    let raw = gh(&[
        "issue".into(),
        "view".into(),
        reference.number.clone(),
        "--repo".into(),
        reference.repo.clone(),
        "--json".into(),
        "number,title,body,state,url".into(),
    ])?;
    let raw: Value = serde_json::from_str(&raw)
        .map_err(|_| fail("github_readback_invalid", "gh returned invalid Issue JSON"))?;
    let field = |name| {
        raw.get(name)
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_owned()
    };
    Ok(Issue {
        repository: reference.repo.clone(),
        number: raw["number"]
            .as_u64()
            .map_or_else(|| reference.number.clone(), |value| value.to_string()),
        title: field("title"),
        body: field("body"),
        state: state(&field("state")).map_err(|_| {
            fail(
                "github_readback_invalid",
                "GitHub returned an unsupported Issue state",
            )
        })?,
        url: if field("url").is_empty() {
            reference.url.clone()
        } else {
            field("url")
        },
    })
}
fn sections(body: &str) -> BTreeMap<String, String> {
    let mut values = BTreeMap::<String, Vec<String>>::new();
    let mut current = String::new();
    for line in python_splitlines(body) {
        if let Some(heading) = line
            .strip_prefix("##")
            .filter(|value| value.chars().next().is_some_and(char::is_whitespace))
        {
            current = heading.trim().to_lowercase().replace(' ', "_");
            values.entry(current.clone()).or_default();
        } else if !current.is_empty() {
            values.entry(current.clone()).or_default().push(line.into());
        }
    }
    values
        .into_iter()
        .map(|(key, value)| (key, value.join("\n").trim().into()))
        .collect()
}
fn report(issues: &[Issue], checked: usize) -> Value {
    let mut findings = Vec::new();
    let rows:Vec<_>=issues.iter().map(|issue|{match reference(&issue.url,""){Err(_)=>findings.push(json!({"check":"identity","path":issue.url,"detail":"invalid-github-url"})),Ok(reference)if reference.repo!=issue.repository||reference.number!=issue.number=>findings.push(json!({"check":"identity","path":issue.url,"detail":"repository-number-mismatch"})),_=>{}}for(field,value)in[("title",&issue.title),("body",&issue.body)]{if value.trim().is_empty(){findings.push(json!({"check":"field","path":issue.url,"detail":format!("missing-{field}")}));}}let sections=sections(&issue.body);let clauses:Vec<_>=["problem","required_action","done","close_condition"].into_iter().map(|kind|{let value=sections.get(kind).cloned().unwrap_or_default();let grounded=!value.is_empty()&&(value.to_lowercase().contains("evidence")||value.to_lowercase().contains("user"));json!({"repository":issue.repository,"issue_number":issue.number,"issue_url":issue.url,"clause_kind":kind,"clause":value,"state":if grounded{"grounded"}else if kind=="problem"{"unproven"}else{"advisory"},"authority":"github-issue-body"})}).collect();json!({"repository":issue.repository,"number":issue.number,"title":issue.title,"state":issue.state,"url":issue.url,"clauses":clauses})}).collect();
    findings
        .sort_by_key(|value| format!("{}:{}:{}", value["check"], value["path"], value["detail"]));
    json!({"status":if findings.is_empty(){"pass"}else{"fail"},"issues":rows,"findings":findings,"github_checked":checked,"github_unavailable":0})
}
fn receipt_path(repository: &str, number: &str) -> Result<PathBuf> {
    let repository = repo_path(repository)?;
    if number.is_empty()
        || number.starts_with('0')
        || !number.bytes().all(|value| value.is_ascii_digit())
    {
        return Err(fail(
            "issue_receipt_number_invalid",
            "Issue number is invalid",
        ));
    }
    Ok(PathBuf::from("feedback/issue-packets/published")
        .join(repository)
        .join(format!("{number}.json")))
}
fn stage_receipt(
    runtime: &Path,
    source: &Path,
    payload: Option<&Value>,
    checkout_head: &str,
) -> Result<PathBuf> {
    let boundary =
        crate::runtime_boundary::RuntimeArtifactBoundary::for_source(source, Some(runtime), true)
            .map_err(io)?;
    let spool = boundary
        .ensure_directory(Path::new("spool/private-feedback"))
        .map_err(io)?;
    let directory =
        crate::runtime_boundary::RuntimeDirectory::open_nofollow(&spool, false).map_err(io)?;
    let source_commit = Some(checkout_head.to_owned())
        .filter(|value| valid_commit(value))
        .or_else(|| {
            std::env::var("AGENT_CANON_SOURCE_COMMIT")
                .ok()
                .filter(|value| valid_commit(value))
        })
        .or_else(|| {
            Command::new("git")
                .arg("-C")
                .arg(source)
                .args(["rev-parse", "--verify", "HEAD"])
                .output()
                .ok()
                .filter(|output| output.status.success())
                .map(|output| String::from_utf8_lossy(&output.stdout).trim().into())
        })
        .filter(|value| valid_commit(value))
        .ok_or_else(|| {
            fail(
                "private-feedback-sync-request-invalid",
                "checkout source commit is unavailable",
            )
        })?;
    let request_path = Path::new("sync-request.json");
    let old = directory.read(request_path).map_err(io)?;
    if let Some(old) = old {
        let old: Value = serde_json::from_slice(&old).map_err(|_| {
            fail(
                "private-feedback-sync-request-invalid",
                "sync request is invalid",
            )
        })?;
        let required = BTreeSet::from([
            "schema",
            "operation",
            "execution_plane",
            "requested_at",
            "source_commit",
        ]);
        if old.as_object().is_none_or(|value| {
            value.keys().map(String::as_str).collect::<BTreeSet<_>>() != required
        }) || old["schema"] != "agent-canon.private-feedback-sync-request.v1"
            || old["operation"] != "sync"
            || old["execution_plane"] != "agentcanon_tool_container"
            || !old["requested_at"].is_string()
            || !old["source_commit"].as_str().is_some_and(valid_commit)
        {
            return Err(fail(
                "private-feedback-sync-request-invalid",
                "sync request values are invalid",
            ));
        }
    } else {
        directory.write_once(request_path,format!("{}\n",json!({"schema":"agent-canon.private-feedback-sync-request.v1","operation":"sync","execution_plane":"agentcanon_tool_container","requested_at":now()?,"source_commit":source_commit})).as_bytes()).map_err(io)?;
    }
    let Some(payload) = payload else {
        return Ok(spool.join(request_path));
    };
    let path = receipt_path(
        payload["repository"].as_str().unwrap_or(""),
        payload["number"].as_str().unwrap_or(""),
    )?;
    validate_receipt(payload)?;
    let mut payload = payload.clone();
    let prior = directory.read_stable(&path).map_err(io)?;
    if payload["action"] == "noop" {
        if let Some((bytes, _)) = &prior {
            let old: Value = serde_json::from_slice(bytes).map_err(io)?;
            validate_receipt(&old)?;
            if payload
                .as_object()
                .unwrap()
                .iter()
                .filter(|(key, _)| key.as_str() != "timestamp")
                .all(|(key, value)| old[key] == *value)
            {
                payload = old;
            }
        }
    }
    let bytes = format!("{}\n", serde_json::to_string_pretty(&payload).map_err(io)?);
    let result = (|| {
        directory
            .atomic_write_bytes(&path, bytes.as_bytes(), 0o600)
            .map_err(io)?;
        let read = directory.read(&path).map_err(io)?;
        if read.as_deref() != Some(bytes.as_bytes()) {
            return Err(fail(
                "issue_receipt_readback_failed",
                "publication receipt readback differs",
            ));
        }
        Ok(())
    })();
    if let Err(error) = result {
        // Restore only our replacement: a concurrent writer retains its bytes.
        if directory.read(&path).map_err(io)?.as_deref() == Some(bytes.as_bytes()) {
            if let Some((prior, snapshot)) = prior {
                directory
                    .atomic_write_bytes(&path, &prior, snapshot.mode & 0o777)
                    .map_err(io)?;
            } else {
                directory.remove_file(&path).map_err(io)?;
            }
        }
        return Err(error);
    }
    Ok(spool.join(path))
}
fn valid_commit(value: &str) -> bool {
    (40..=64).contains(&value.len())
        && value
            .bytes()
            .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
}
fn now() -> Result<String> {
    OffsetDateTime::now_utc().format(&Rfc3339).map_err(io)
}
fn configured_path(explicit: &str, variable: &str, code: &'static str) -> Result<PathBuf> {
    let configured = if explicit.is_empty() {
        std::env::var(variable).unwrap_or_default()
    } else {
        explicit.to_owned()
    };
    if python_strip(&configured).is_empty() {
        return Err(fail(
            code,
            format!("{variable} or an explicit path is required"),
        ));
    }
    let expanded = crate::path_expansion::expand_user_path(Path::new(&configured)).map_err(io)?;
    crate::path_resolution::resolve_non_strict(&expanded).map_err(io)
}
fn log_root(explicit: &str) -> Result<PathBuf> {
    if explicit.is_empty()
        && std::env::var("AGENT_CANON_LOG_ROOT")
            .unwrap_or_default()
            .trim()
            .is_empty()
    {
        if let Ok(parent) = std::env::var("AGENT_CANON_CONTROL_PARENT_ROOT") {
            if !parent.trim().is_empty() {
                return configured_path(
                    &Path::new(&parent).join("agent-canon-log").to_string_lossy(),
                    "AGENT_CANON_LOG_ROOT",
                    "private_log_root_required",
                );
            }
        }
    }
    configured_path(
        explicit,
        "AGENT_CANON_LOG_ROOT",
        "private_log_root_required",
    )
}
fn find_receipt(root: &Path, repository: &str, payload: &Value) -> Result<Option<Value>> {
    if !root.is_dir() {
        return Ok(None);
    }
    let directory =
        crate::runtime_boundary::RuntimeDirectory::open_nofollow(root, false).map_err(io)?;
    let number = payload.get("number").and_then(Value::as_str).unwrap_or("");
    let candidates = if number.is_empty() {
        if payload.get("handoff").is_none() {
            return Ok(None);
        }
        directory
            .files(Path::new("feedback/issue-packets/published"))
            .map_err(io)?
    } else {
        vec![receipt_path(repository, number)?]
    };
    let handoff = payload.get("handoff");
    let mut responsibility = handoff
        .and_then(|value| value["responsibility"].as_array())
        .cloned()
        .unwrap_or_default();
    if let Some(fix) = handoff
        .and_then(|value| value["fix"].as_str())
        .filter(|value| !value.is_empty())
    {
        if !responsibility.contains(&json!(fix)) {
            responsibility.push(json!(fix));
        }
    }
    let locations = handoff
        .and_then(|value| value.get("occurrence_locations"))
        .cloned()
        .unwrap_or_else(|| json!([]));
    let kind = handoff
        .and_then(|value| value["source_finding_kind"].as_str())
        .unwrap_or("");
    let mut matches = Vec::new();
    for candidate in candidates {
        let Some(bytes) = directory.read(&candidate).map_err(io)? else {
            continue;
        };
        let Ok(value) = serde_json::from_slice::<Value>(&bytes) else {
            continue;
        };
        if validate_receipt(&value).is_err() || value["repository"] != repository {
            continue;
        }
        if receipt_path(repository, value["number"].as_str().unwrap_or(""))? != candidate {
            continue;
        }
        if handoff.is_some()
            && (value["responsibility"] != json!(responsibility)
                || value["occurrence_locations"] != locations
                || value["source_finding_kind"] != kind)
        {
            continue;
        }
        matches.push(value);
    }
    Ok(if matches.len() == 1 {
        matches.pop()
    } else {
        None
    })
}

pub fn qualify_finding(record: &Value, authenticated_repository: &str) -> Value {
    let first = |keys: &[&str]| {
        keys.iter()
            .find_map(|key| {
                record
                    .get(key)
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
            })
            .unwrap_or("")
            .to_owned()
    };
    let boolean = |keys: &[&str]| {
        keys.iter()
            .find_map(|key| record.get(key).and_then(Value::as_bool))
    };
    let repository = normalized_repository(&first(&["repository", "repo"]));
    let owner = first(&["owner", "owner_id"]);
    let fix = first(&["fix", "required_action", "action"]);
    let status = CaseMapper::new()
        .fold_string(&first(&["status", "resolution"]))
        .replace('_', "-");
    let kind = CaseMapper::new()
        .fold_string(&first(&[
            "finding_kind",
            "source_finding_kind",
            "kind",
            "category",
        ]))
        .replace('_', "-");
    let mut occurrence = Vec::new();
    let locations = record
        .get("occurrence_locations")
        .or_else(|| record.get("occurrence_location"));
    let values = match locations {
        Some(Value::Array(values)) => values.clone(),
        Some(Value::String(value)) => vec![json!(value)],
        _ => Vec::new(),
    };
    for value in values {
        let location = if let Some(value) = value.as_str() {
            value.trim().into()
        } else {
            let path = value["path"].as_str().unwrap_or("").trim();
            let locator = ["locator", "symbol", "heading"]
                .iter()
                .find_map(|key| {
                    value
                        .get(key)
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|value| !value.is_empty())
                })
                .unwrap_or("");
            if path.is_empty() || locator.is_empty() {
                String::new()
            } else {
                format!("{path}::{locator}")
            }
        };
        if !location.is_empty() && !occurrence.contains(&location) {
            occurrence.push(location);
        }
    }
    let related = record
        .get("related_issue_refs")
        .or_else(|| record.get("issue_refs"))
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| {
                    value
                        .as_str()
                        .map(str::trim)
                        .filter(|value| !value.is_empty())
                        .map(str::to_owned)
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let source = record
        .get("responsibility")
        .filter(|value| value.is_object())
        .unwrap_or(record);
    let mut responsibility = Vec::new();
    for key in ["owner", "decision", "mechanism", "validation", "completion"] {
        if let Some(value) = source
            .get(key)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            if !responsibility.contains(&value.to_owned()) {
                responsibility.push(value.to_owned());
            }
        }
    }
    let (classification, reason) = if boolean(&["actionable"]) == Some(false) {
        ("no-action", "not-actionable")
    } else if [
        "count",
        "raw-count",
        "status",
        "one-off",
        "selection",
        "selection-miss",
    ]
    .contains(&kind.as_str())
    {
        ("no-action", "non-durable-finding-kind")
    } else if [
        "resolved",
        "closed",
        "current-scope-resolved",
        "current-scope-closed",
    ]
    .contains(&status.as_str())
        || boolean(&["current_scope_resolved", "closed_by_active_repair"]) == Some(true)
    {
        ("no-action", "current-scope-resolved")
    } else if repository.is_empty() {
        ("handoff", "repository-unresolved")
    } else if authenticated_repository.is_empty() {
        ("handoff", "checkout-identity-unresolved")
    } else if repository != normalized_repository(authenticated_repository) {
        ("handoff", "other-repository")
    } else if owner.is_empty() {
        ("handoff", "owner-unresolved")
    } else if fix.is_empty() {
        ("handoff", "fix-unresolved")
    } else if boolean(&[
        "durable_follow_up",
        "needs_durable_follow_up",
        "recurrent",
        "repeatable",
    ]) == Some(false)
    {
        ("no-action", "durable-follow-up-not-established")
    } else {
        ("qualified", "user-owned-candidate")
    };
    json!({"schema":"agent-canon.issue-worker-handoff.v1","status":classification,"reason":reason,"repository":repository,"owner":owner,"fix":fix,"occurrence_locations":occurrence,"related_issue_refs":related,"responsibility":responsibility,"source_finding_kind":kind})
}

fn read_private_body(path: &Path, digest: &str) -> Result<String> {
    let path = if path.is_absolute() {
        path.to_owned()
    } else {
        std::env::current_dir().map_err(io)?.join(path)
    };
    let parent = path.parent().ok_or_else(|| {
        fail(
            "body_locator_missing",
            "private body locator is unavailable",
        )
    })?;
    let directory =
        crate::runtime_boundary::RuntimeDirectory::open_nofollow(parent, false).map_err(io)?;
    let bytes = directory
        .read(Path::new(path.file_name().unwrap_or_default()))
        .map_err(io)?
        .ok_or_else(|| {
            fail(
                "body_locator_missing",
                "private body locator is unavailable",
            )
        })?;
    if format!("sha256:{:x}", Sha256::digest(&bytes)) != digest {
        return Err(fail(
            "body_digest_mismatch",
            "private body digest does not match packet",
        ));
    }
    String::from_utf8(bytes).map_err(io)
}

fn packet_responsibility(payload: &Value) -> Vec<Value> {
    let handoff = &payload["handoff"];
    let mut values = handoff["responsibility"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    if let Some(fix) = handoff["fix"].as_str().filter(|fix| !fix.is_empty()) {
        if !values.contains(&json!(fix)) {
            values.push(json!(fix));
        }
    }
    values
}

fn cohesive_issue(record: &Issue, handoff: &Value) -> bool {
    let clauses = sections(&record.body);
    if ![
        "problem",
        "required_action",
        "done",
        "close_condition",
        "finding",
    ]
    .iter()
    .any(|key| clauses.get(*key).is_some_and(|value| !value.is_empty()))
    {
        return false;
    }
    let fold = |value: &str| CaseMapper::new().fold_string(value);
    let boundary = fold(
        clauses
            .get("responsibility_boundary")
            .map(String::as_str)
            .unwrap_or(""),
    );
    let terms = handoff["responsibility"]
        .as_array()
        .filter(|terms| !terms.is_empty())
        .cloned()
        .unwrap_or_else(|| vec![handoff["owner"].clone()]);
    if terms
        .iter()
        .filter_map(Value::as_str)
        .any(|term| !term.is_empty() && !boundary.contains(&fold(term)))
    {
        return false;
    }
    let fix = fold(handoff["fix"].as_str().unwrap_or(""));
    [
        "required_fix",
        "required_action",
        "required_investigation_or_fix",
    ]
    .iter()
    .any(|key| {
        clauses
            .get(*key)
            .is_some_and(|value| fold(value).contains(&fix))
    })
}

/// Host GitHub operations stage receipts through the existing resident route.
struct ContainerReceiptStager {
    prefix: Vec<String>,
    checkout_head: String,
    checkout_repository: String,
}

impl ContainerReceiptStager {
    fn new(runtime: &Path, checkout: &Path, repository: &str) -> Result<Self> {
        let environment = std::env::vars().collect::<BTreeMap<_, _>>();
        let source = crate::agent_canon_source_root::resolve_source_roots(checkout, &environment)
            .map_err(|error| fail(error.code, error.detail))?
            .source_root;
        let bootstrap = std::env::var_os("AGENT_CANON_BOOTSTRAP")
            .map(PathBuf::from)
            .unwrap_or_else(|| source.join("bootstrap.sh"));
        let bootstrap = if bootstrap.is_absolute() {
            bootstrap
        } else {
            source.join(bootstrap)
        };
        if !bootstrap.is_file() {
            return Err(fail(
                "issue_receipt_route_unavailable",
                "AgentCanon bootstrap entrypoint is unavailable",
            ));
        }
        let checkout = checkout.canonicalize().map_err(io)?;
        let head = Command::new("git")
            .arg("-C")
            .arg(&checkout)
            .args(["rev-parse", "--verify", "HEAD"])
            .output()
            .map_err(io)?;
        let head = String::from_utf8_lossy(&head.stdout).trim().to_owned();
        if !valid_commit(&head) {
            return Err(fail(
                "checkout-identity-unresolved",
                "receipt staging checkout commit is unavailable",
            ));
        }
        Ok(Self {
            prefix: vec![
                bootstrap.to_string_lossy().into_owned(),
                "--control-parent-root".into(),
                std::env::var("AGENT_CANON_CONTROL_PARENT_ROOT")
                    .unwrap_or_else(|_| "<control-parent-root>".into()),
                "--runtime-root".into(),
                runtime.to_string_lossy().into_owned(),
                "tool".into(),
                "run".into(),
                "--root".into(),
                checkout.to_string_lossy().into_owned(),
                "issue-sync".into(),
                "--".into(),
            ],
            checkout_head: head,
            checkout_repository: repository.to_owned(),
        })
    }

    fn execute(&self, payload: Option<&Value>) -> Result<()> {
        let mut args = self.prefix.clone();
        args.push(
            if payload.is_some() {
                "--stage-publication-receipt"
            } else {
                "--receipt-preflight"
            }
            .into(),
        );
        args.extend([
            "--checkout-head".into(),
            self.checkout_head.clone(),
            "--checkout-repository".into(),
            self.checkout_repository.clone(),
        ]);
        if let Some(payload) = payload {
            for (flag, field) in [
                ("--repo", "repository"),
                ("--receipt-number", "number"),
                ("--receipt-url", "url"),
                ("--receipt-state", "state"),
                ("--receipt-action", "action"),
                ("--receipt-source-finding-kind", "source_finding_kind"),
            ] {
                args.extend([flag.into(), payload[field].as_str().unwrap_or("").into()]);
            }
            for (flag, field) in [
                ("--receipt-responsibility", "responsibility"),
                ("--receipt-occurrence-location", "occurrence_locations"),
            ] {
                for value in payload[field].as_array().into_iter().flatten() {
                    args.extend([flag.into(), value.as_str().unwrap_or("").into()]);
                }
            }
        }
        let result = Command::new(&args[0]).args(&args[1..]).output();
        if result.is_ok_and(|result| result.status.success()) {
            return Ok(());
        }
        Err(fail(
            if payload.is_some() {
                "issue_receipt_write_failed"
            } else {
                "issue_receipt_route_unavailable"
            },
            "container receipt command failed",
        ))
    }
}

fn sync_packets(log: &Path, runtime: &Path, source: &Path) -> Result<Value> {
    let remote = Command::new("git")
        .arg("-C")
        .arg(source)
        .args(["remote", "get-url", "origin"])
        .output()
        .map_err(io)?;
    let repository = normalized_repository(String::from_utf8_lossy(&remote.stdout).trim());
    if !remote.status.success() || repository.is_empty() {
        return Err(fail(
            "checkout-identity-unresolved",
            "pending Issue publication requires the current checkout identity",
        ));
    }
    let log_directory =
        crate::runtime_boundary::RuntimeDirectory::open_nofollow(log, false).map_err(io)?;
    let pending = Path::new("feedback/issue-packets/pending");
    let mut paths = log_directory.files(pending).map_err(io)?;
    paths.retain(|path| path.extension().is_some_and(|value| value == "json"));
    paths.sort();
    let mut urls = Vec::new();
    let stager = if paths.is_empty() {
        None
    } else {
        Some(ContainerReceiptStager::new(runtime, source, &repository)?)
    };
    for path in paths {
        let bytes = log_directory
            .read(&path)
            .map_err(io)?
            .ok_or_else(|| fail("packet_invalid", "pending packet is missing"))?;
        let payload: Value = serde_json::from_slice(&bytes)
            .map_err(|_| fail("packet_invalid", "pending packet is not valid JSON"))?;
        if payload["schema"] != PACKET || payload["status"] != "pending" {
            return Err(fail(
                "packet_invalid",
                "pending packet schema/status is invalid",
            ));
        }
        if normalized_repository(payload["repository"].as_str().unwrap_or("")) != repository {
            return Err(fail(
                "checkout-repository-mismatch",
                "pending Issue repository does not match the current checkout identity",
            ));
        }
        if payload["route"] == "issue-worker" {
            if let Some(handoff) = payload.get("handoff").filter(|value| value.is_object()) {
                let qualified = qualify_finding(handoff, &repository);
                if qualified["status"] != "qualified" {
                    return Err(fail(
                        "issue_worker_not_qualified",
                        format!(
                            "IssueWorker handoff is {}:{}",
                            qualified["status"], qualified["reason"]
                        ),
                    ));
                }
            }
        }
        let body_path = Path::new(payload["body_locator"].as_str().ok_or_else(|| {
            fail(
                "body_locator_missing",
                "private body locator is unavailable",
            )
        })?);
        let body = read_private_body(body_path, payload["body_digest"].as_str().unwrap_or(""))?;
        stager
            .as_ref()
            .expect("nonempty packet queue has a stager")
            .execute(None)?;
        let existing = find_receipt(
            &runtime.join("spool/private-feedback"),
            &repository,
            &payload,
        )?
        .or(find_receipt(log, &repository, &payload)?);
        if let Some(existing) = existing {
            let record = read(&reference(
                existing["url"].as_str().unwrap_or(""),
                &repository,
            )?)?;
            log_directory.remove_file(&path).map_err(io)?;
            urls.push(record.url);
            continue;
        }
        let title = payload["title"].as_str().unwrap_or("");
        let number = payload.get("number").and_then(Value::as_str).unwrap_or("");
        let mut action = "noop";
        let mut record = if !number.is_empty() {
            read(&reference(number, &repository)?)?
        } else {
            let terms = payload
                .get("handoff")
                .map(|handoff| {
                    let mut values = vec![
                        handoff["owner"].as_str().unwrap_or(""),
                        handoff["fix"].as_str().unwrap_or(""),
                    ];
                    if let Some(responsibility) = handoff["responsibility"].as_array() {
                        values.extend(responsibility.iter().filter_map(Value::as_str));
                    }
                    values
                        .into_iter()
                        .filter(|value| !value.trim().is_empty())
                        .map(|value| format!("\"{value}\""))
                        .collect::<Vec<_>>()
                        .join(" ")
                })
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| format!("\"{title}\""));
            let raw = gh(&[
                "issue".into(),
                "list".into(),
                "--repo".into(),
                repository.clone(),
                "--state".into(),
                "all".into(),
                "--search".into(),
                terms,
                "--limit".into(),
                "100".into(),
                "--json".into(),
                "number,title,body,state,url".into(),
            ])?;
            let raw: Value = serde_json::from_str(&raw).map_err(|_| {
                fail(
                    "github_readback_invalid",
                    "gh returned invalid Issue search JSON",
                )
            })?;
            let candidates = raw.as_array().ok_or_else(|| {
                fail(
                    "github_readback_invalid",
                    "gh Issue search did not return a list",
                )
            })?;
            let mut exact = Vec::new();
            for candidate in candidates {
                if let Some(number) = candidate["number"].as_u64() {
                    let record = read(&reference(&number.to_string(), &repository)?)?;
                    if record.title.trim().replace("\r\n", "\n")
                        == title.trim().replace("\r\n", "\n")
                        && record.body.trim().replace("\r\n", "\n")
                            == body.trim().replace("\r\n", "\n")
                    {
                        exact.push(record);
                    }
                }
            }
            if exact.len() > 1 || (!candidates.is_empty() && exact.is_empty()) {
                return Err(fail(
                    "issue_worker_retry_unresolved",
                    "Issue search candidates do not exactly match one packet content",
                ));
            }
            if let Some(record) = exact.pop() {
                record
            } else {
                if payload["input_mode"] != "issue-publication-initial" {
                    return Err(fail(
                        "issue_worker_retry_unresolved",
                        "non-initial retry cannot create after a zero Issue search",
                    ));
                }
                action = "create";
                let body_temp = tempfile::NamedTempFile::new().map_err(io)?;
                fs::write(body_temp.path(), &body).map_err(io)?;
                let url = gh(&[
                    "issue".into(),
                    "create".into(),
                    "--repo".into(),
                    repository.clone(),
                    "--title".into(),
                    title.into(),
                    "--body-file".into(),
                    body_temp.path().to_string_lossy().into(),
                ])?;
                let record = read(&reference(url.lines().last().unwrap_or(""), &repository)?)?;
                if record.title != title || record.body != body {
                    return Err(fail(
                        "github_readback_mismatch",
                        "created Issue title/body readback differs",
                    ));
                }
                record
            }
        };
        if action == "noop"
            && record.state == "closed"
            && payload["route"] == "issue-worker"
            && cohesive_issue(&record, &payload["handoff"])
        {
            gh(&[
                "issue".into(),
                "reopen".into(),
                record.number.clone(),
                "--repo".into(),
                repository.clone(),
            ])?;
            record = read(&reference(&record.number, &repository)?)?;
            if record.state != "open" {
                return Err(fail(
                    "github_readback_mismatch",
                    "reopened Issue state readback differs",
                ));
            }
            action = "reopen";
        }
        let receipt = json!({"repository":record.repository,"number":record.number,"url":record.url,"state":record.state,"action":action,"responsibility":packet_responsibility(&payload),"occurrence_locations":payload.get("handoff").and_then(|value|value.get("occurrence_locations")).cloned().unwrap_or_else(||json!([])),"source_finding_kind":payload.get("handoff").and_then(|value|value["source_finding_kind"].as_str()).or_else(||payload["source_finding_kind"].as_str()).unwrap_or(""),"timestamp":now()?});
        stager
            .as_ref()
            .expect("nonempty packet queue has a stager")
            .execute(Some(&receipt))?;
        urls.push(record.url);
        log_directory.remove_file(&path).map_err(io)?;
    }
    Ok(json!({"schema":PACKET,"status":"synced","issues":urls}))
}
fn validate_receipt(value: &Value) -> Result<()> {
    let fields = BTreeSet::from([
        "repository",
        "number",
        "url",
        "state",
        "action",
        "responsibility",
        "occurrence_locations",
        "source_finding_kind",
        "timestamp",
    ]);
    let object = value.as_object().ok_or_else(|| {
        fail(
            "issue_receipt_invalid",
            "publication receipt fields are invalid",
        )
    })?;
    if object.keys().map(String::as_str).collect::<BTreeSet<_>>() != fields {
        return Err(fail(
            "issue_receipt_invalid",
            "publication receipt fields are invalid",
        ));
    }
    for key in [
        "repository",
        "number",
        "url",
        "state",
        "action",
        "source_finding_kind",
        "timestamp",
    ] {
        if !value[key].is_string() {
            return Err(fail(
                "issue_receipt_invalid",
                "publication receipt values are invalid",
            ));
        }
    }
    for key in ["responsibility", "occurrence_locations"] {
        if value[key]
            .as_array()
            .is_none_or(|values| values.iter().any(|value| !value.is_string()))
        {
            return Err(fail(
                "issue_receipt_invalid",
                "publication receipt values are invalid",
            ));
        }
    }
    if !["create", "update", "reopen", "reorganize", "noop"]
        .contains(&value["action"].as_str().unwrap())
        || state(value["state"].as_str().unwrap())? != value["state"]
    {
        return Err(fail(
            "issue_receipt_invalid",
            "publication receipt action or state is invalid",
        ));
    }
    let reference = reference(value["url"].as_str().unwrap(), "")?;
    if reference.repo != value["repository"] || reference.number != value["number"] {
        return Err(fail(
            "issue_receipt_identity_mismatch",
            "publication receipt identity differs",
        ));
    }
    Ok(())
}

pub fn run(args: &[String]) -> i32 {
    const USAGE:&str="usage: agent-canon issue-sync [--repo OWNER/REPO] [--issue-url URL] [--github-check] [--receipt-preflight|--stage-publication-receipt] [options]";
    let names = [
        "--repo",
        "--issue-url",
        "--offline-title",
        "--body-locator",
        "--body-digest",
        "--log-root",
        "--run",
        "--task",
        "--summary-file",
        "--runtime-root",
        "--receipt-number",
        "--receipt-url",
        "--receipt-state",
        "--receipt-action",
        "--receipt-responsibility",
        "--receipt-occurrence-location",
        "--receipt-source-finding-kind",
        "--receipt-timestamp",
        "--checkout-head",
        "--checkout-root",
        "--checkout-repository",
    ];
    let mut values = BTreeMap::<String, Vec<String>>::new();
    let mut flags = BTreeSet::new();
    let flag_names = [
        "--github-check",
        "--sync-pending",
        "--receipt-preflight",
        "--stage-publication-receipt",
        "--record-publication-receipt",
        "--help",
    ];
    let options = names
        .iter()
        .chain(flag_names.iter())
        .map(|name| (*name, *name))
        .collect::<Vec<_>>();
    let mut index = 0;
    while index < args.len() {
        let (raw, inline) = args[index]
            .split_once('=')
            .map_or((args[index].as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        let name = if raw == "-h" {
            "--help"
        } else if options.iter().any(|(name, _)| *name == raw) {
            raw
        } else {
            match crate::python_cli_options::resolve_long_option_prefix(raw, &options) {
                Ok(name) => name,
                Err(_) => {
                    eprintln!("{USAGE}");
                    return 2;
                }
            }
        };
        if name == "--help" && inline.is_none() {
            println!("{USAGE}");
            return 0;
        }
        if [
            "--github-check",
            "--sync-pending",
            "--receipt-preflight",
            "--stage-publication-receipt",
            "--record-publication-receipt",
        ]
        .contains(&name)
        {
            if inline.is_some() {
                eprintln!("{USAGE}");
                return 2;
            }
            flags.insert(name);
            index += 1;
            continue;
        }
        if !names.contains(&name) || (inline.is_none() && index + 1 == args.len()) {
            eprintln!("{USAGE}");
            return 2;
        }
        let value = inline.unwrap_or_else(|| args[index + 1].as_str());
        if inline.is_none()
            && value.starts_with('-')
            && !crate::python_cli_integer::is_argparse_negative_number(value)
        {
            eprintln!("{USAGE}");
            return 2;
        }
        values
            .entry(name.into())
            .or_default()
            .push(value.to_owned());
        index += if inline.is_some() { 1 } else { 2 };
    }
    let get = |name: &str| {
        values
            .get(name)
            .and_then(|values| values.last())
            .map(String::as_str)
            .unwrap_or("")
    };
    let result = (|| -> Result<Value> {
        if flags.contains("--receipt-preflight")
            || flags.contains("--stage-publication-receipt")
            || flags.contains("--record-publication-receipt")
        {
            let runtime = configured_path(
                get("--runtime-root"),
                "AGENT_CANON_RUNTIME_ROOT",
                "runtime-root-required",
            )?;
            let source = if get("--checkout-root").is_empty() {
                std::env::current_dir().map_err(io)?
            } else {
                PathBuf::from(get("--checkout-root"))
            };
            let payload = if flags.contains("--receipt-preflight") {
                None
            } else {
                let repo = normalized_repository(get("--repo"));
                let checkout = normalized_repository(get("--checkout-repository"));
                if !checkout.is_empty() && repo != checkout {
                    return Err(fail(
                        "checkout-repository-mismatch",
                        "receipt staging checkout repository differs from Issue repository",
                    ));
                }
                Some(
                    json!({"repository":repo,"number":get("--receipt-number"),"url":get("--receipt-url"),"state":state(get("--receipt-state"))?,"action":get("--receipt-action"),"responsibility":values.get("--receipt-responsibility").cloned().unwrap_or_default(),"occurrence_locations":values.get("--receipt-occurrence-location").cloned().unwrap_or_default(),"source_finding_kind":get("--receipt-source-finding-kind"),"timestamp":if get("--receipt-timestamp").is_empty(){now()?}else{get("--receipt-timestamp").into()}}),
                )
            };
            let path = stage_receipt(&runtime, &source, payload.as_ref(), get("--checkout-head"))?;
            return Ok(if payload.is_none() {
                json!({"status":"preflight","runtime_root":runtime})
            } else {
                json!({"status":"staged","receipt":path})
            });
        }
        if !get("--offline-title").is_empty() {
            if get("--repo").is_empty()
                || get("--body-locator").is_empty()
                || get("--body-digest").is_empty()
            {
                return Err(fail(
                    "offline_packet_incomplete",
                    "--repo, --offline-title, --body-locator, and --body-digest are required",
                ));
            }
            let digest = get("--body-digest");
            if !digest.strip_prefix("sha256:").is_some_and(|value| {
                value.len() == 64
                    && value
                        .bytes()
                        .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
            }) {
                return Err(fail(
                    "body_digest_invalid",
                    "body digest must be sha256:<64 hex>",
                ));
            }
            if get("--body-locator").is_empty() {
                return Err(fail(
                    "body_locator_invalid",
                    "private body locator is required",
                ));
            }
            let root = log_root(get("--log-root"))?;
            let directory = crate::runtime_boundary::RuntimeDirectory::open_nofollow(&root, true)
                .map_err(io)?;
            let title = get("--offline-title");
            let slug = regex::Regex::new("[^a-z0-9]+")
                .unwrap()
                .replace_all(&title.to_lowercase(), "-")
                .trim_matches('-')
                .chars()
                .take(80)
                .collect::<String>();
            let slug = if slug.is_empty() {
                "issue".to_owned()
            } else {
                slug
            };
            let path = PathBuf::from("feedback/issue-packets/pending").join(format!(
                "{}-{}.json",
                slug,
                &digest[7..23]
            ));
            let payload = json!({"schema":PACKET,"repository":get("--repo"),"title":title,"body_locator":get("--body-locator"),"body_digest":digest,"run":get("--run"),"task":get("--task"),"input_mode":"structured-log","reason":"","route":"issue-publication","status":"pending"});
            let encoded = format!("{}\n", serde_json::to_string_pretty(&payload).map_err(io)?);
            if let Some(old) = directory.read(&path).map_err(io)? {
                if old != encoded.as_bytes() {
                    return Err(fail(
                        "packet_conflict",
                        "pending packet already contains different metadata",
                    ));
                }
            } else {
                directory
                    .write_once(&path, encoded.as_bytes())
                    .map_err(io)?;
            }
            return Ok(
                json!({"schema":PACKET,"status":"pending","packet":root.join(path),"repository":get("--repo"),"title":title}),
            );
        }
        if flags.contains("--sync-pending") {
            let log = log_root(get("--log-root"))?;
            let runtime = configured_path(
                get("--runtime-root"),
                "AGENT_CANON_RUNTIME_ROOT",
                "runtime-root-required",
            )?;
            return sync_packets(&log, &runtime, &std::env::current_dir().map_err(io)?);
        }
        let Some(references) = values.get("--issue-url") else {
            return Err(fail("lookup_required", "GITHUB_ISSUE_LOOKUP_REQUIRED=1"));
        };
        let mut issues = Vec::new();
        for value in references {
            issues.push(read(&reference(value, get("--repo"))?)?);
        }
        Ok(report(
            &issues,
            if flags.contains("--github-check") {
                issues.len()
            } else {
                0
            },
        ))
    })();
    match result {
        Ok(report) => {
            let rendered = serde_json::to_string_pretty(&report).unwrap();
            if !get("--summary-file").is_empty() {
                let output = Path::new(get("--summary-file"));
                let result = (|| -> std::result::Result<(), String> {
                    let output = crate::path_resolution::resolve_non_strict(output)?;
                    let parent = output.parent().ok_or("summary parent missing")?;
                    let directory =
                        crate::runtime_boundary::RuntimeDirectory::open_nofollow(parent, true)
                            .map_err(|error| error.to_string())?;
                    directory
                        .atomic_write_bytes(
                            Path::new(output.file_name().ok_or("summary filename missing")?),
                            format!("{rendered}\n").as_bytes(),
                            0o644,
                        )
                        .map_err(|error| error.to_string())
                })();
                if let Err(error) = result {
                    eprintln!("{error}");
                    return 2;
                }
            }
            println!("{rendered}");
            i32::from(report["status"] == "fail")
        }
        Err(error) => {
            if error.code == "lookup_required" {
                println!("GITHUB_ISSUE_LOOKUP_REQUIRED=1");
                return 2;
            }
            eprintln!(
                "{}",
                json!({"status":"error","code":error.code,"detail":error.detail})
            );
            2
        }
    }
}
