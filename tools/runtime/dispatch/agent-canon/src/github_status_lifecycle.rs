// @dependency-start
// contract implementation
// responsibility Reconciles Issue lifecycle labels using native comment identities and single GitHub operations.
// upstream design ../../../../../agents/internal-routines/github-status-lifecycle.md owns lifecycle facts and publication authority
// upstream design ../../../../../documents/operations/issue-label-taxonomy.toml owns canonical labels and aliases
// downstream test ../../../../../tests/agent_tools/test_github_status_lifecycle.py verifies the native CLI
// @dependency-end

use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::process::Command;
use toml_edit::{DocumentMut, Item};

const OWNER: &str = "github_status_lifecycle.rs";
const SCOPE: &str = "status-label-lifecycle";
const TRANSPORT: &str = "github-api-transport";
type Result<T> = std::result::Result<T, Failure>;
#[derive(Debug)]
pub struct Failure {
    code: &'static str,
    message: String,
    scope: &'static str,
    details: Value,
}
impl Failure {
    fn value(&self) -> Value {
        json!({"kind":"failure","code":self.code,"message":self.message,"code_owner":OWNER,"responsibility_scope":self.scope,"details":self.details,"next_action":"fresh-reconcile-after-owner-review"})
    }
}
fn fail(code: &'static str, message: impl Into<String>) -> Failure {
    Failure {
        code,
        message: message.into(),
        scope: SCOPE,
        details: json!({}),
    }
}
fn detail(mut error: Failure, details: Value) -> Failure {
    error.details = details;
    error
}
fn transport(code: &'static str, message: impl Into<String>) -> Failure {
    let mut error = fail(code, message);
    error.scope = TRANSPORT;
    error
}

pub trait Runner {
    fn execute(&mut self, args: &[String]) -> std::io::Result<(i32, String)>;
}
pub struct SystemRunner;
impl Runner for SystemRunner {
    fn execute(&mut self, args: &[String]) -> std::io::Result<(i32, String)> {
        let result = Command::new("gh").arg("api").args(args).output()?;
        Ok((
            result.status.code().unwrap_or(1),
            String::from_utf8_lossy(&result.stdout).into(),
        ))
    }
}

#[derive(Clone)]
pub struct Mapping {
    canonical: Vec<(&'static str, String)>,
    aliases: BTreeMap<&'static str, Vec<String>>,
}
impl Mapping {
    fn from_value(raw: &Value) -> Result<Self> {
        let keys = ["active", "ready_for_review", "needs_verification"];
        let table = raw
            .get("status_lifecycle")
            .and_then(Value::as_object)
            .ok_or_else(|| fail("taxonomy_invalid", "invalid status_lifecycle table"))?;
        if table
            .keys()
            .any(|key| !keys.contains(&key.as_str()) && key != "legacy_aliases")
        {
            return Err(fail("taxonomy_invalid", "invalid status_lifecycle table"));
        }
        let mut canonical = Vec::new();
        let mut aliases = BTreeMap::new();
        let mut names = BTreeSet::new();
        let legacy = table.get("legacy_aliases").and_then(Value::as_object);
        if table.get("legacy_aliases").is_some() && legacy.is_none()
            || legacy.is_some_and(|value| value.keys().any(|key| !keys.contains(&key.as_str())))
        {
            return Err(fail("taxonomy_invalid", "invalid legacy_aliases table"));
        }
        for key in keys {
            let name = table
                .get(key)
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .ok_or_else(|| {
                    detail(
                        fail("taxonomy_invalid", "canonical label is missing"),
                        json!({"field":key}),
                    )
                })?;
            if !names.insert(name.to_owned()) {
                return Err(fail("taxonomy_invalid", "status labels overlap"));
            }
            canonical.push((key, name.into()));
            let values = match legacy.and_then(|value| value.get(key)) {
                None => Vec::new(),
                Some(Value::Array(values)) => values
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .filter(|value| !value.trim().is_empty())
                            .map(str::to_owned)
                            .ok_or_else(|| {
                                detail(
                                    fail("taxonomy_invalid", "invalid legacy label list"),
                                    json!({"field":key}),
                                )
                            })
                    })
                    .collect::<Result<Vec<_>>>()?,
                _ => return Err(fail("taxonomy_invalid", "invalid legacy label list")),
            };
            aliases.insert(key, values);
        }
        for value in aliases.values().flatten() {
            if !names.insert(value.clone()) {
                return Err(fail("taxonomy_invalid", "status labels overlap"));
            }
        }
        Ok(Self { canonical, aliases })
    }
    fn load(root: &Path) -> Result<Self> {
        let text =
            std::fs::read_to_string(root.join("documents/operations/issue-label-taxonomy.toml"))
                .map_err(|_| fail("taxonomy_invalid", "label taxonomy could not be read"))?;
        let document = text
            .parse::<DocumentMut>()
            .map_err(|_| fail("taxonomy_invalid", "label taxonomy could not be read"))?;
        let table = document
            .get("status_lifecycle")
            .and_then(Item::as_table_like)
            .ok_or_else(|| fail("taxonomy_invalid", "invalid status_lifecycle table"))?;
        let mut value = serde_json::Map::new();
        for (key, item) in table.iter() {
            if key == "legacy_aliases" {
                let Some(aliases) = item.as_table_like() else {
                    return Err(fail("taxonomy_invalid", "invalid legacy_aliases table"));
                };
                let mut raw = serde_json::Map::new();
                for (name, values) in aliases.iter() {
                    raw.insert(
                        name.into(),
                        values
                            .as_array()
                            .map(|values| {
                                Value::Array(
                                    values
                                        .iter()
                                        .map(|value| {
                                            value.as_str().map_or(Value::Null, |text| json!(text))
                                        })
                                        .collect(),
                                )
                            })
                            .unwrap_or(Value::Null),
                    );
                }
                value.insert(key.into(), Value::Object(raw));
            } else {
                value.insert(
                    key.into(),
                    item.as_str().map_or(Value::Null, |text| json!(text)),
                );
            }
        }
        Self::from_value(&json!({"status_lifecycle":value}))
    }
    fn managed(&self) -> BTreeSet<String> {
        self.canonical
            .iter()
            .map(|(_, value)| value.clone())
            .chain(self.aliases.values().flatten().cloned())
            .collect()
    }
    fn desired(&self, lifecycle: &str) -> BTreeSet<String> {
        self.canonical
            .iter()
            .filter(|(key, _)| match lifecycle {
                "active" => *key == "active",
                "review-ready" => *key == "ready_for_review",
                _ => *key != "active",
            })
            .map(|(_, value)| value.clone())
            .collect()
    }
}
fn classify(facts: &Value) -> Result<&'static str> {
    if facts.get("work_started") != Some(&Value::Bool(true)) {
        return Err(fail("lifecycle_facts_incomplete", "work has not started"));
    }
    for key in ["implementation_failure", "validation_failed"] {
        match facts.get(key) {
            Some(Value::Bool(true)) => return Ok("active"),
            None | Some(Value::Bool(false)) => {}
            _ => {
                return Err(detail(
                    fail("lifecycle_facts_incomplete", "invalid lifecycle fact"),
                    json!({"field":key}),
                ))
            }
        }
    }
    for key in [
        "handoff_ready",
        "validation_complete",
        "verification_unavailable",
    ] {
        if facts.get(key).is_some_and(|value| !value.is_boolean()) {
            return Err(detail(
                fail("lifecycle_facts_incomplete", "invalid lifecycle fact"),
                json!({"field":key}),
            ));
        }
    }
    if facts.get("handoff_ready") != Some(&Value::Bool(true))
        || facts.get("validation_complete") != Some(&Value::Bool(true))
    {
        return Ok("active");
    }
    Ok(
        if facts.get("verification_unavailable") == Some(&Value::Bool(true)) {
            "review-ready-unverified"
        } else {
            "review-ready"
        },
    )
}
#[derive(Clone, Debug, PartialEq, Eq)]
struct Comment {
    id: u64,
    body: String,
    url: String,
}
impl Comment {
    fn value(&self) -> Value {
        json!({"id":self.id,"body":self.body,"url":self.url})
    }
}
struct Issue {
    number: u64,
    url: String,
    state: String,
    labels: BTreeSet<String>,
}
impl Issue {
    fn value(&self) -> Value {
        json!({"number":self.number,"url":self.url,"state":self.state,"labels":self.labels})
    }
}
pub struct Adapter<R> {
    repository: String,
    issue: u64,
    runner: R,
}
impl<R: Runner> Adapter<R> {
    pub fn new(repository: &str, issue: u64, runner: R) -> Result<Self> {
        let parts: Vec<_> = repository.split('/').collect();
        if issue == 0
            || parts.len() != 2
            || parts.iter().any(|value| value.is_empty())
            || repository
                .chars()
                .any(|value| value.is_whitespace() || matches!(value, '?' | '#'))
        {
            return Err(fail(
                "identity_invalid",
                "repository must be owner/name and issue a positive integer",
            ));
        }
        Ok(Self {
            repository: repository.into(),
            issue,
            runner,
        })
    }
    fn path(&self) -> String {
        format!("repos/{}/issues/{}", self.repository, self.issue)
    }
    fn api(&mut self, args: &[String], mutation: bool) -> Result<Value> {
        let (code, text) = self.runner.execute(args).map_err(|_| {
            transport(
                if mutation {
                    "mutation_partial"
                } else {
                    "readback_unavailable"
                },
                "GitHub response is unavailable; do not blindly retry a write",
            )
        })?;
        if code != 0 {
            return Err(transport(
                if mutation {
                    "mutation_partial"
                } else {
                    "readback_unavailable"
                },
                "GitHub response is unavailable; do not blindly retry a write",
            ));
        }
        serde_json::from_str(&text).map_err(|_| {
            transport(
                if mutation {
                    "mutation_partial"
                } else {
                    "readback_unavailable"
                },
                "GitHub response is unavailable; do not blindly retry a write",
            )
        })
    }
    fn issue(&mut self) -> Result<Issue> {
        let raw = self.api(&[self.path()], false)?;
        let invalid = || transport("readback_invalid", "invalid Issue snapshot");
        if raw.get("number").and_then(Value::as_u64) != Some(self.issue) {
            return Err(invalid());
        }
        let rows = raw
            .get("labels")
            .and_then(Value::as_array)
            .ok_or_else(invalid)?;
        let names: Vec<_> = rows
            .iter()
            .map(|row| {
                row.get("name")
                    .and_then(Value::as_str)
                    .filter(|value| !value.is_empty())
                    .map(str::to_owned)
                    .ok_or_else(invalid)
            })
            .collect::<Result<_>>()?;
        let labels: BTreeSet<_> = names.iter().cloned().collect();
        if labels.len() != names.len() {
            return Err(invalid());
        }
        let url = raw
            .get("html_url")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(invalid)?;
        let state = raw
            .get("state")
            .and_then(Value::as_str)
            .filter(|value| ["open", "closed"].contains(value))
            .ok_or_else(invalid)?;
        Ok(Issue {
            number: self.issue,
            url: url.into(),
            state: state.into(),
            labels,
        })
    }
    fn catalog(&mut self) -> Result<BTreeSet<String>> {
        let raw = self.api(
            &[
                "--paginate".into(),
                "--slurp".into(),
                format!("repos/{}/labels?per_page=100", self.repository),
            ],
            false,
        )?;
        let invalid = || transport("readback_invalid", "invalid label catalog pages");
        let mut names = BTreeSet::new();
        for page in raw.as_array().ok_or_else(invalid)? {
            for row in page.as_array().ok_or_else(invalid)? {
                names.insert(
                    row.get("name")
                        .and_then(Value::as_str)
                        .filter(|value| !value.is_empty())
                        .ok_or_else(invalid)?
                        .into(),
                );
            }
        }
        Ok(names)
    }
    fn parse_comment(&self, raw: &Value, expected: Option<u64>) -> Result<Comment> {
        let id = raw
            .get("id")
            .and_then(Value::as_u64)
            .filter(|value| *value != 0)
            .ok_or_else(|| fail("identity_invalid", "comment id must be a positive integer"))?;
        if expected.is_some_and(|expected| expected != id) {
            return Err(fail("evidence_readback_mismatch", "comment id changed"));
        }
        let field = |name| {
            raw.get(name)
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .ok_or_else(|| {
                    transport(
                        "evidence_readback_unavailable",
                        "comment fields are missing",
                    )
                })
        };
        let body = field("body")?;
        let url = field("html_url")?;
        let issue_url = field("issue_url")?;
        let path = issue_url
            .split_once("://")
            .and_then(|(_, rest)| rest.find('/').map(|index| &rest[index..]))
            .unwrap_or(issue_url)
            .split(['?', '#'])
            .next()
            .unwrap_or("");
        if !path.eq_ignore_ascii_case(&format!("/{}", self.path())) {
            return Err(fail(
                "evidence_readback_mismatch",
                "comment belongs to a different Issue",
            ));
        }
        Ok(Comment {
            id,
            body: body.into(),
            url: url.into(),
        })
    }
    fn comment(&mut self, id: u64) -> Result<Comment> {
        let raw = self.api(
            &[format!("repos/{}/issues/comments/{id}", self.repository)],
            false,
        )?;
        self.parse_comment(&raw, Some(id))
    }
    fn create_comment(&mut self, body: &str) -> Result<Comment> {
        let raw = self.api(
            &[
                "--method".into(),
                "POST".into(),
                format!("{}/comments", self.path()),
                "-f".into(),
                format!("body={body}"),
            ],
            true,
        )?;
        let created = self.parse_comment(&raw, None)?;
        let observed = self.comment(created.id)?;
        if observed != created || observed.body != body {
            return Err(detail(
                fail(
                    "evidence_readback_mismatch",
                    "created comment could not be read back unchanged",
                ),
                json!({"comment_id":created.id}),
            ));
        }
        Ok(observed)
    }
    fn mutate(&mut self, action: &str, label: &str) -> Result<()> {
        if action == "add" {
            self.api(
                &[
                    "--method".into(),
                    "POST".into(),
                    format!("{}/labels", self.path()),
                    "-f".into(),
                    format!("labels[]={label}"),
                ],
                true,
            )?;
        } else {
            let encoded: String = label
                .as_bytes()
                .iter()
                .map(|value| {
                    if value.is_ascii_alphanumeric() || b"-._~".contains(value) {
                        (*value as char).to_string()
                    } else {
                        format!("%{value:02X}")
                    }
                })
                .collect();
            let args = [
                "--method".into(),
                "DELETE".into(),
                format!("{}/labels/{encoded}", self.path()),
            ];
            let (code, _) = self
                .runner
                .execute(&args)
                .map_err(|_| transport("mutation_partial", "label removal response unavailable"))?;
            if code != 0 {
                return Err(transport(
                    "mutation_partial",
                    "label removal response unavailable",
                ));
            }
        }
        Ok(())
    }
}
pub fn reconcile<R: Runner>(
    adapter: &mut Adapter<R>,
    mapping: &Mapping,
    facts: &Value,
    body: Option<&str>,
    id: Option<u64>,
) -> Result<Value> {
    if body.is_some() == id.is_some() || body.is_some_and(|value| value.trim().is_empty()) {
        return Err(fail(
            "evidence_missing",
            "supply either a non-empty comment_body or an existing comment_id",
        ));
    }
    if id == Some(0) {
        return Err(fail(
            "identity_invalid",
            "comment id must be a positive integer",
        ));
    }
    let lifecycle = classify(facts)?;
    let desired = mapping.desired(lifecycle);
    let managed = mapping.managed();
    let catalog = adapter.catalog()?;
    let missing: Vec<_> = mapping
        .canonical
        .iter()
        .map(|(_, name)| name)
        .filter(|name| !catalog.contains(*name))
        .collect();
    if !missing.is_empty() {
        return Err(detail(
            fail("label_mapping_missing", "canonical labels are absent"),
            json!({"missing":missing}),
        ));
    }
    let before = adapter.issue()?;
    let evidence = if let Some(id) = id {
        adapter.comment(id)?
    } else {
        adapter.create_comment(body.unwrap_or_default())?
    };
    let mut expected = before.labels.clone();
    let mut operations = Vec::new();
    for label in before
        .labels
        .intersection(&managed)
        .filter(|label| !desired.contains(*label))
    {
        operations.push(("remove", label.clone()));
    }
    for (_, label) in &mapping.canonical {
        if desired.contains(label) && !before.labels.contains(label) {
            operations.push(("add", label.clone()));
        }
    }
    let mut completed = Vec::<Value>::new();
    for (action, label) in operations {
        let observed = adapter.issue()?;
        if observed.labels != expected {
            return Err(detail(
                fail("fresh_state_changed", "labels changed before mutation"),
                json!({"completed_prefix":completed,"observed_labels":observed.labels,"comment_id":evidence.id}),
            ));
        }
        if let Err(error) = adapter.mutate(action, &label) {
            let observed = adapter.issue().ok().map(|value| value.labels);
            return Err(detail(
                fail(
                    "mutation_partial",
                    "mutation result requires fresh owner review",
                ),
                json!({"completed_prefix":completed,"failed_operation":{"action":action,"label":label},"observed_labels":observed,"desired_labels":desired,"comment_id":evidence.id,"cause":error.value(),"rollback":"not-attempted"}),
            ));
        }
        if action == "remove" {
            expected.remove(&label);
        } else {
            expected.insert(label.clone());
        }
        let observed = adapter.issue()?;
        if observed.labels != expected {
            return Err(detail(
                fail("readback_mismatch", "labels differ after mutation"),
                json!({"completed_prefix":completed,"last_operation":{"action":action,"label":label},"observed_labels":observed.labels,"comment_id":evidence.id}),
            ));
        }
        completed.push(json!({"action":action,"label":label}));
    }
    let final_state = adapter.issue()?;
    if adapter.comment(evidence.id)? != evidence {
        return Err(detail(
            fail("evidence_readback_mismatch", "selected evidence changed"),
            json!({"comment_id":evidence.id,"completed_prefix":completed}),
        ));
    }
    if final_state
        .labels
        .intersection(&managed)
        .cloned()
        .collect::<BTreeSet<_>>()
        != desired
        || final_state
            .labels
            .difference(&managed)
            .ne(before.labels.difference(&managed))
    {
        return Err(detail(
            fail(
                "readback_mismatch",
                "final labels differ from intended state",
            ),
            json!({"observed_labels":final_state.labels,"completed_prefix":completed}),
        ));
    }
    Ok(
        json!({"kind":"success","lifecycle":lifecycle,"before_managed":before.labels.intersection(&managed).collect::<Vec<_>>(),"after_managed":desired,"labels_added":completed.iter().filter(|value| value["action"] == "add").map(|value| &value["label"]).collect::<Vec<_>>(),"labels_removed":completed.iter().filter(|value| value["action"] == "remove").map(|value| &value["label"]).collect::<Vec<_>>(),"completed_operations":completed,"evidence":evidence.value(),"readback":final_state.value(),"code_owner":OWNER,"responsibility_scope":SCOPE}),
    )
}

pub fn run(args: &[String]) -> i32 {
    const USAGE: &str = "usage: agent-canon github-status-lifecycle --repo OWNER/REPO --issue NUMBER --facts-json PATH (--comment-body-file PATH|--comment-id NUMBER) [--root ROOT]";
    let mut values = BTreeMap::new();
    let mut index = 0;
    while index < args.len() {
        let name = args[index].as_str();
        if ["--help", "-h"].contains(&name) {
            println!("{USAGE}");
            return 0;
        }
        if ![
            "--repo",
            "--issue",
            "--facts-json",
            "--comment-body-file",
            "--comment-id",
            "--root",
        ]
        .contains(&name)
            || index + 1 == args.len()
        {
            eprintln!("{USAGE}");
            return 2;
        }
        values.insert(name, args[index + 1].as_str());
        index += 2;
    }
    let result = (|| {
        let required = |key| {
            values
                .get(key)
                .copied()
                .ok_or_else(|| fail("identity_invalid", format!("missing {key}")))
        };
        let issue = required("--issue")?
            .parse::<u64>()
            .map_err(|_| fail("identity_invalid", "issue must be a positive integer"))?;
        let facts = std::fs::read(required("--facts-json")?)
            .map_err(|error| fail("lifecycle_facts_incomplete", error.to_string()))?;
        let facts = serde_json::from_slice(&facts)
            .map_err(|error| fail("lifecycle_facts_incomplete", error.to_string()))?;
        let body = values
            .get("--comment-body-file")
            .map(std::fs::read_to_string)
            .transpose()
            .map_err(|error| fail("evidence_missing", error.to_string()))?;
        let id = values
            .get("--comment-id")
            .map(|value| {
                value
                    .parse::<u64>()
                    .map_err(|_| fail("identity_invalid", "comment id must be a positive integer"))
            })
            .transpose()?;
        let root = values
            .get("--root")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."));
        let mapping = Mapping::load(&root)?;
        let mut adapter = Adapter::new(required("--repo")?, issue, SystemRunner)?;
        reconcile(&mut adapter, &mapping, &facts, body.as_deref(), id)
    })();
    match result {
        Ok(value) => {
            println!("{value}");
            0
        }
        Err(error) => {
            println!("{}", error.value());
            1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fake {
        labels: BTreeSet<String>,
        comments: BTreeMap<u64, Value>,
        catalog: Vec<String>,
        calls: Vec<Vec<String>>,
        issue_reads: usize,
        comment_reads: usize,
        drift: usize,
        edit: bool,
        hide: bool,
        lost_post: bool,
        fail_label: bool,
        aba: bool,
    }
    impl Default for Fake {
        fn default() -> Self {
            Self {
                labels: BTreeSet::from(["bug".into(), "in progress".into()]),
                comments: BTreeMap::new(),
                catalog: vec![
                    "in progress".into(),
                    "ready for review".into(),
                    "need verification".into(),
                ],
                calls: Vec::new(),
                issue_reads: 0,
                comment_reads: 0,
                drift: 0,
                edit: false,
                hide: false,
                lost_post: false,
                fail_label: false,
                aba: false,
            }
        }
    }
    impl Fake {
        fn comment(&mut self, body: &str, issue: u64) -> u64 {
            let id = self.comments.len() as u64 + 10;
            self.comments.insert(id, json!({"id":id,"body":body,"html_url":format!("https://github.com/owner/repo/issues/{issue}#issuecomment-{id}"),"issue_url":format!("https://api.github.com/repos/owner/repo/issues/{issue}")}));
            id
        }
        fn writes(&self) -> usize {
            self.calls
                .iter()
                .filter(|args| args.contains(&"--method".into()))
                .count()
        }
    }
    impl Runner for Fake {
        fn execute(&mut self, args: &[String]) -> std::io::Result<(i32, String)> {
            self.calls.push(args.into());
            let method = args
                .iter()
                .position(|value| value == "--method")
                .map_or("GET", |index| args[index + 1].as_str());
            let endpoint = args
                .iter()
                .find(|value| value.starts_with("repos/"))
                .expect("API endpoint");
            let mut code = 0;
            let raw = if endpoint.ends_with("/labels?per_page=100") {
                json!([self
                    .catalog
                    .iter()
                    .map(|name| json!({"name":name}))
                    .collect::<Vec<_>>()])
            } else if endpoint.contains("/issues/comments/") {
                self.comment_reads += 1;
                if self.edit && self.comment_reads == 2 {
                    self.comments.get_mut(&10).unwrap()["body"] = json!("changed");
                }
                let id = endpoint.rsplit('/').next().unwrap().parse().unwrap();
                if self.hide {
                    code = 1;
                    Value::Null
                } else {
                    self.comments.get(&id).cloned().unwrap_or_else(|| {
                        code = 1;
                        Value::Null
                    })
                }
            } else if method == "GET" && endpoint == "repos/owner/repo/issues/719" {
                self.issue_reads += 1;
                if self.aba && self.issue_reads == 2 {
                    self.labels.insert("temporary".into());
                    self.labels.remove("temporary");
                }
                if self.drift == self.issue_reads {
                    self.labels.insert("other-owner".into());
                }
                json!({"number":719,"html_url":"https://github.com/owner/repo/issues/719","state":"open","labels":self.labels.iter().map(|name| json!({"name":name})).collect::<Vec<_>>()})
            } else if method == "POST" && endpoint.ends_with("/comments") {
                let body = args[args.iter().position(|value| value == "-f").unwrap() + 1]
                    .strip_prefix("body=")
                    .unwrap();
                let id = self.comment(body, 719);
                if self.lost_post {
                    code = 1;
                    Value::Null
                } else {
                    self.comments[&id].clone()
                }
            } else if endpoint.contains("/labels") {
                if self.fail_label {
                    code = 1;
                } else if method == "POST" {
                    let name = args[args.iter().position(|value| value == "-f").unwrap() + 1]
                        .strip_prefix("labels[]=")
                        .unwrap();
                    self.labels.insert(name.into());
                } else {
                    let name = endpoint.rsplit('/').next().unwrap();
                    self.labels
                        .remove(&name.replace("%2F", "/").replace("%20", " "));
                    return Ok((0, String::new()));
                }
                json!([])
            } else {
                panic!("unexpected argv {args:?}")
            };
            Ok((code, raw.to_string()))
        }
    }
    fn mapping() -> Mapping {
        Mapping::from_value(&json!({"status_lifecycle":{"active":"in progress","ready_for_review":"ready for review","needs_verification":"need verification","legacy_aliases":{"active":["working"]}}})).unwrap()
    }
    fn facts() -> Value {
        json!({"work_started":true,"handoff_ready":true,"validation_complete":true})
    }
    fn adapter() -> Adapter<Fake> {
        Adapter::new("owner/repo", 719, Fake::default()).unwrap()
    }
    fn invoke(adapter: &mut Adapter<Fake>) -> Result<Value> {
        reconcile(adapter, &mapping(), &facts(), Some("修正と根拠。"), None)
    }
    #[test]
    fn taxonomy_and_native_ids_are_validated_before_transport() {
        for raw in [
            json!({}),
            json!({"status_lifecycle":{}}),
            json!({"status_lifecycle":{"active":"x","ready_for_review":"x","needs_verification":"y"}}),
        ] {
            assert_eq!(
                Mapping::from_value(&raw).err().unwrap().code,
                "taxonomy_invalid"
            );
        }
        assert!(Adapter::new("owner/repo", 0, Fake::default()).is_err());
        for repo in ["../owner/repo", "owner/repo?x", "owner /repo", "owner/"] {
            assert!(Adapter::new(repo, 1, Fake::default()).is_err());
        }
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../..");
        assert_eq!(Mapping::load(&root).unwrap().canonical[0].1, "in progress");
    }
    #[test]
    fn ordinary_comment_is_posted_once_and_unrelated_labels_survive() {
        let mut adapter = adapter();
        let result = invoke(&mut adapter).unwrap();
        assert_eq!(result["kind"], "success");
        assert_eq!(result["evidence"]["id"], 10);
        assert_eq!(
            adapter.runner.labels,
            BTreeSet::from(["bug".into(), "ready for review".into()])
        );
        assert_eq!(
            adapter
                .runner
                .calls
                .iter()
                .filter(|args| args
                    .iter()
                    .any(|value| value == "repos/owner/repo/issues/719/comments"))
                .count(),
            1
        );
        assert!(!adapter
            .runner
            .calls
            .iter()
            .flatten()
            .any(|value| value.contains("comments?")));
    }
    #[test]
    fn explicit_existing_id_and_identical_other_comments_do_not_post() {
        let mut adapter = adapter();
        let id = adapter.runner.comment("same", 719);
        adapter.runner.comment("same", 719);
        adapter.runner.comment("other", 719);
        let result = reconcile(&mut adapter, &mapping(), &facts(), None, Some(id)).unwrap();
        assert_eq!(result["evidence"]["id"], id);
        assert!(!adapter
            .runner
            .calls
            .iter()
            .any(|args| args.contains(&"repos/owner/repo/issues/719/comments".into())));
    }
    #[test]
    fn foreign_comment_and_ambiguous_evidence_never_mutate() {
        let mut adapter = adapter();
        let id = adapter.runner.comment("foreign", 720);
        assert_eq!(
            reconcile(&mut adapter, &mapping(), &facts(), None, Some(id))
                .unwrap_err()
                .code,
            "evidence_readback_mismatch"
        );
        assert_eq!(adapter.runner.writes(), 0);
        for (body, id) in [(None, None), (Some(" "), None), (Some("body"), Some(10))] {
            assert_eq!(
                reconcile(&mut adapter, &mapping(), &facts(), body, id)
                    .unwrap_err()
                    .code,
                "evidence_missing"
            );
        }
    }
    #[test]
    fn uncertain_post_is_not_retried_and_created_comment_is_read_back() {
        let mut adapter = adapter();
        adapter.runner.lost_post = true;
        assert_eq!(invoke(&mut adapter).unwrap_err().code, "mutation_partial");
        assert_eq!(adapter.runner.writes(), 1);
        assert_eq!(adapter.runner.comments.len(), 1);
        let mut adapter = self::adapter();
        adapter.runner.hide = true;
        assert_eq!(
            invoke(&mut adapter).unwrap_err().code,
            "readback_unavailable"
        );
        assert_eq!(adapter.runner.writes(), 1);
        assert!(adapter.runner.labels.contains("in progress"));
    }
    #[test]
    fn selected_comment_edit_prevents_success() {
        let mut adapter = adapter();
        adapter.runner.edit = true;
        assert_eq!(
            invoke(&mut adapter).unwrap_err().code,
            "evidence_readback_mismatch"
        );
    }
    #[test]
    fn three_states_and_failure_precedence_preserve_unmanaged_labels() {
        for (change, expected) in [
            (json!({"handoff_ready":false}), vec!["bug", "in progress"]),
            (json!({}), vec!["bug", "ready for review"]),
            (
                json!({"verification_unavailable":true}),
                vec!["bug", "ready for review", "need verification"],
            ),
        ] {
            let mut facts = facts();
            for (key, value) in change.as_object().unwrap() {
                facts[key] = value.clone();
            }
            let mut adapter = adapter();
            reconcile(&mut adapter, &mapping(), &facts, Some("evidence"), None).unwrap();
            assert_eq!(
                adapter.runner.labels,
                expected.into_iter().map(str::to_owned).collect()
            );
        }
        for key in ["implementation_failure", "validation_failed"] {
            let mut facts = facts();
            facts[key] = json!(true);
            facts["verification_unavailable"] = json!(true);
            assert_eq!(classify(&facts).unwrap(), "active");
        }
        let mut facts = facts();
        facts["handoff_ready"] = json!("yes");
        assert_eq!(
            classify(&facts).unwrap_err().code,
            "lifecycle_facts_incomplete"
        );
    }
    #[test]
    fn drift_stops_at_the_observed_prefix_and_unknown_writes_are_not_retried() {
        for read in [2, 4] {
            let mut adapter = adapter();
            adapter.runner.drift = read;
            let error = invoke(&mut adapter).unwrap_err();
            assert_eq!(error.code, "fresh_state_changed");
            assert_eq!(
                error.details["completed_prefix"].as_array().unwrap().len(),
                usize::from(read == 4)
            );
        }
        let mut adapter = adapter();
        adapter.runner.fail_label = true;
        let error = invoke(&mut adapter).unwrap_err();
        assert_eq!(error.code, "mutation_partial");
        assert_eq!(error.details["rollback"], "not-attempted");
        assert_eq!(adapter.runner.writes(), 2);
    }
    #[test]
    fn missing_catalog_names_prevent_comments_and_delete_uses_encoded_native_path() {
        let mut adapter = adapter();
        adapter.runner.catalog.truncate(1);
        assert_eq!(
            invoke(&mut adapter).unwrap_err().code,
            "label_mapping_missing"
        );
        assert_eq!(adapter.runner.writes(), 0);
        adapter.runner.labels.insert("status/old state".into());
        adapter.mutate("remove", "status/old state").unwrap();
        assert_eq!(
            adapter.runner.calls.last().unwrap(),
            &vec![
                "--method",
                "DELETE",
                "repos/owner/repo/issues/719/labels/status%2Fold%20state"
            ]
        );
    }
    #[test]
    fn declared_aliases_are_removed_in_order_without_claiming_unobserved_aba_detection() {
        let mut adapter = adapter();
        adapter.runner.labels.insert("working".into());
        adapter.runner.aba = true;
        let result = reconcile(&mut adapter, &mapping(), &json!({"work_started":true,"handoff_ready":true,"validation_complete":true,"verification_unavailable":true}), Some("evidence"), None).unwrap();
        assert_eq!(
            result["completed_operations"],
            json!([
                {"action":"remove","label":"in progress"}, {"action":"remove","label":"working"},
                {"action":"add","label":"ready for review"}, {"action":"add","label":"need verification"}
            ])
        );
        assert!(adapter.runner.labels.contains("bug"));
    }
}
