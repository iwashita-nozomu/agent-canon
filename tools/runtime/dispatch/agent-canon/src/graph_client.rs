// @dependency-start
// contract implementation
// responsibility Provides typed source-derived dependency query/context and explicit persisted graph runtime commands.
// upstream design ../../../../../documents/design/dependency-manifest-design.md tracked-source dependency semantics
// upstream implementation source_dependency_graph.rs derives dependency query and context without runtime state
// upstream implementation graph.rs owns opt-in persisted graph build/status and non-dependency relations
// downstream implementation main.rs exposes the native GraphClient API to in-process callers
// downstream implementation ../../../../analysis/documents/prose_reasoning_graph.py consumes the native typed source query route
// downstream implementation tool_drift.rs consumes source-derived dependency facts
// downstream implementation agent_search.rs consumes selected source-derived dependency facts
// downstream implementation source_dependency_tests.rs verifies source and persisted client behavior
// @dependency-end

use crate::source_dependency_graph::{
    build_context_projection_default, build_dependency_projection,
};
use serde::Serialize;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus};

const GRAPH_COMMANDS: &[&str] = &["build", "status", "query", "context"];
const GRAPH_CLIENT_COMMANDS: &[&str] = &["status", "query", "context"];
const GRAPH_RELATIONS: &[&str] = &[
    "all",
    "dependency",
    "owner",
    "scope",
    "import",
    "include",
    "symbol",
    "call",
    "containment",
    "document",
    "catalog",
    "pin",
    "view",
    "generated",
    "submodule",
    "public",
];
const GRAPH_DIRECTIONS: &[&str] = &["outgoing", "incoming", "both"];
const GRAPH_STATUSES: &[&str] = &["fresh", "incomplete", "stale", "unavailable"];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GraphClientError {
    pub message: String,
}

impl GraphClientError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for GraphClientError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for GraphClientError {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GraphSourceIdentity {
    pub snapshot_commit: String,
    pub source_path: String,
    pub content_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GraphDependencyFact {
    pub id: String,
    pub direction: String,
    pub kind: String,
    pub source: String,
    pub target: String,
    pub reason: String,
    pub producer: String,
    pub source_path: Option<String>,
    pub source_span: Option<Map<String, Value>>,
    pub evidence_ref: String,
    pub authority: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct GraphResponse {
    pub schema: String,
    pub command: String,
    pub status: String,
    pub payload: Value,
    pub exit_code: i32,
}

impl GraphResponse {
    fn from_source_projection(command: &str, payload: Value) -> Result<Self, GraphClientError> {
        if !matches!(command, "query" | "context") || !payload.is_object() {
            return Err(GraphClientError::new(
                "source projection response identity is invalid",
            ));
        }
        if payload.get("exit_code").and_then(Value::as_i64) != Some(0) {
            return Err(GraphClientError::new("graph response exit status mismatch"));
        }
        Ok(Self {
            schema: format!("agent-canon.graph.{command}.v1"),
            command: command.to_string(),
            status: "fresh".to_string(),
            payload,
            exit_code: 0,
        })
    }

    fn from_payload(
        command: &str,
        payload: Value,
        process_exit_code: Option<i32>,
    ) -> Result<Self, GraphClientError> {
        let object = payload
            .as_object()
            .ok_or_else(|| GraphClientError::new("graph response must be an object"))?;
        let schema = object
            .get("schema")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| GraphClientError::new("graph response identity is incomplete"))?;
        let response_command = object
            .get("command")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| GraphClientError::new("graph response identity is incomplete"))?;
        let status = object
            .get("status")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| GraphClientError::new("graph response identity is incomplete"))?;
        if response_command != command {
            return Err(GraphClientError::new("graph response command mismatch"));
        }
        let expected_schema = format!("agent-canon.graph.{command}.v1");
        if schema != expected_schema {
            return Err(GraphClientError::new("graph response schema mismatch"));
        }
        let exit_code = object
            .get("exit_code")
            .and_then(Value::as_i64)
            .and_then(|value| i32::try_from(value).ok())
            .ok_or_else(|| GraphClientError::new("graph response exit status mismatch"))?;
        if process_exit_code.is_some_and(|actual| actual != exit_code) {
            return Err(GraphClientError::new("graph response exit status mismatch"));
        }
        if !GRAPH_STATUSES.contains(&status) {
            return Err(GraphClientError::new("graph response status is invalid"));
        }
        Ok(Self {
            schema: schema.to_string(),
            command: command.to_string(),
            status: status.to_string(),
            payload,
            exit_code,
        })
    }

    /// Project the response and typed source-derived records for native CLI consumers.
    pub fn consumer_payload(&self) -> Result<Value, GraphClientError> {
        let successful_response = self.status == "fresh" && self.exit_code == 0;
        let dependency_facts = if self.command == "query" && successful_response {
            self.dependency_facts()?
        } else {
            Vec::new()
        };
        let source_identity = if self.command == "context" && successful_response {
            self.source_identity()?
        } else {
            None
        };
        Ok(json!({
            "schema": self.schema.clone(),
            "command": self.command.clone(),
            "status": self.status.clone(),
            "payload": self.payload.clone(),
            "exit_code": self.exit_code,
            "dependency_facts": dependency_facts,
            "source_identity": source_identity,
        }))
    }

    /// Return the source-bound identity carried by dependency context.
    pub fn source_identity(&self) -> Result<Option<GraphSourceIdentity>, GraphClientError> {
        if self.command != "context" {
            return Ok(None);
        }
        let Some(raw) = self.payload.get("source_identity") else {
            return Ok(None);
        };
        if raw.is_null() {
            return Ok(None);
        }
        let identity = raw.as_object().ok_or_else(|| {
            GraphClientError::new("graph context source_identity must be an object")
        })?;
        let required = ["snapshot_commit", "source_path", "content_sha256"];
        if identity.len() != required.len()
            || required.iter().any(|key| !identity.contains_key(*key))
        {
            return Err(GraphClientError::new(
                "graph context source_identity fields are not canonical",
            ));
        }
        let identity_string = |field: &str| {
            identity
                .get(field)
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .map(str::to_string)
                .ok_or_else(|| {
                    GraphClientError::new("graph context source_identity has empty fields")
                })
        };
        let snapshot_commit = identity_string("snapshot_commit")?;
        let source_path = identity_string("source_path")?;
        let content_sha256 = identity_string("content_sha256")?;
        if self.payload.get("resolved_path").is_some_and(|resolved| {
            !resolved.is_null() && resolved != &Value::String(source_path.clone())
        }) {
            return Err(GraphClientError::new(
                "graph context source identity path mismatch",
            ));
        }
        if content_sha256.len() != 64
            || !content_sha256
                .bytes()
                .all(|character| character.is_ascii_digit() || (b'a'..=b'f').contains(&character))
        {
            return Err(GraphClientError::new(
                "graph context source identity hash is invalid",
            ));
        }
        Ok(Some(GraphSourceIdentity {
            snapshot_commit,
            source_path,
            content_sha256,
        }))
    }

    /// Project explicit dependency facts using response node identities.
    pub fn dependency_facts(&self) -> Result<Vec<GraphDependencyFact>, GraphClientError> {
        if self.command != "query" {
            return Ok(Vec::new());
        }
        let payload = self
            .payload
            .as_object()
            .ok_or_else(|| GraphClientError::new("graph response payload must be an object"))?;
        let raw_nodes = payload
            .get("nodes")
            .and_then(Value::as_array)
            .ok_or_else(|| GraphClientError::new("graph query nodes/facts must be arrays"))?;
        let raw_facts = payload
            .get("facts")
            .and_then(Value::as_array)
            .ok_or_else(|| GraphClientError::new("graph query nodes/facts must be arrays"))?;
        let mut paths = BTreeMap::new();
        for raw_node in raw_nodes {
            let node = raw_node
                .as_object()
                .ok_or_else(|| GraphClientError::new("graph node must be an object"))?;
            let Some(node_id) = node
                .get("id")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
            else {
                return Err(GraphClientError::new("graph node identity is incomplete"));
            };
            let endpoint = node
                .get("path")
                .filter(|value| python_truthy(value))
                .or_else(|| node.get("selector"))
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| GraphClientError::new("graph node identity is incomplete"))?;
            if paths
                .insert(node_id.to_string(), endpoint.to_string())
                .is_some()
            {
                return Err(GraphClientError::new(format!(
                    "duplicate graph node id: {node_id}"
                )));
            }
        }
        let mut projected = Vec::new();
        for raw_fact in raw_facts {
            let fact = raw_fact
                .as_object()
                .ok_or_else(|| GraphClientError::new("graph fact must be an object"))?;
            if fact.get("kind").and_then(Value::as_str) != Some("dependency")
                || fact.get("inferred") == Some(&Value::Bool(true))
            {
                continue;
            }
            if fact.get("inferred") != Some(&Value::Bool(false)) {
                return Err(GraphClientError::new(
                    "explicit dependency fact inferred must be false",
                ));
            }
            let fact_id = required_string(fact, "id", "graph fact")?;
            let source_id = required_string(fact, "from", &fact_id)?;
            let target_id = required_string(fact, "to", &fact_id)?;
            let source = paths.get(&source_id).cloned().ok_or_else(|| {
                GraphClientError::new(format!(
                    "graph fact {fact_id} endpoint is absent from nodes"
                ))
            })?;
            let target = paths.get(&target_id).cloned().ok_or_else(|| {
                GraphClientError::new(format!(
                    "graph fact {fact_id} endpoint is absent from nodes"
                ))
            })?;
            let detail = required_mapping(
                fact.get("dependency_detail"),
                &format!("graph fact {fact_id}.dependency_detail"),
            )?;
            projected.push(GraphDependencyFact {
                id: fact_id.clone(),
                direction: required_string(detail, "direction", "dependency detail")?,
                kind: required_string(detail, "kind", "dependency detail")?,
                source,
                target,
                reason: required_string(detail, "reason", "dependency detail")?,
                producer: required_string(fact, "producer", &fact_id)?,
                source_path: optional_string(fact.get("source_path"))?,
                source_span: optional_mapping(fact.get("source_span"))?,
                evidence_ref: required_string(fact, "evidence_ref", &fact_id)?,
                authority: required_string(fact, "authority", &fact_id)?,
            });
        }
        projected.sort_by(|left, right| {
            (
                &left.source,
                &left.target,
                &left.direction,
                &left.kind,
                &left.id,
            )
                .cmp(&(
                    &right.source,
                    &right.target,
                    &right.direction,
                    &right.kind,
                    &right.id,
                ))
        });
        Ok(projected)
    }
}

/// A bound repository client that reads source dependencies directly and calls the graph owner only for explicit persisted operations.
#[derive(Debug, Clone)]
pub struct GraphClient {
    root: PathBuf,
    executable: Option<PathBuf>,
}

impl GraphClient {
    /// Bind one repository root for native in-process operations.
    pub fn new(root: &Path) -> Result<Self, GraphClientError> {
        Ok(Self {
            root: resolve_path(root)?,
            executable: None,
        })
    }

    /// Bind an explicit external graph executable provider.
    pub fn with_executable(root: &Path, executable: &Path) -> Result<Self, GraphClientError> {
        Ok(Self {
            root: resolve_path(root)?,
            executable: Some(resolve_path(executable)?),
        })
    }

    /// Invoke one explicit persisted graph command and validate its JSON response.
    pub fn invoke(
        &self,
        command: &str,
        options: &[String],
    ) -> Result<GraphResponse, GraphClientError> {
        if !GRAPH_COMMANDS.contains(&command) {
            return Err(GraphClientError::new(format!(
                "unsupported graph command: {command}"
            )));
        }
        if let Some(executable) = &self.executable {
            return self.invoke_external(executable, command, options);
        }
        let payload = crate::graph::invoke(&self.root, command, options).map_err(|error| {
            GraphClientError::new(format!("graph response is not JSON: {error}"))
        })?;
        GraphResponse::from_payload(command, payload, None)
    }

    /// Build one opt-in persisted graph transaction.
    pub fn build(&self) -> Result<GraphResponse, GraphClientError> {
        self.invoke("build", &[])
    }

    /// Read persisted graph status without rebuilding producers.
    pub fn status(&self) -> Result<GraphResponse, GraphClientError> {
        self.invoke("status", &[])
    }

    /// Read a source projection or query persisted graph records.
    pub fn query(
        &self,
        path: Option<&str>,
        relation: &str,
        direction: &str,
        depth: i64,
        all_nodes: bool,
    ) -> Result<GraphResponse, GraphClientError> {
        if !GRAPH_RELATIONS.contains(&relation) {
            return Err(GraphClientError::new(format!(
                "unsupported graph relation: {relation}"
            )));
        }
        if !GRAPH_DIRECTIONS.contains(&direction) {
            return Err(GraphClientError::new(format!(
                "unsupported graph direction: {direction}"
            )));
        }
        if depth < 0 {
            return Err(GraphClientError::new(
                "graph query depth must be non-negative",
            ));
        }
        if relation == "dependency"
            && direction == "both"
            && depth == 0
            && all_nodes
            && path.is_none()
        {
            let projection = build_dependency_projection(&self.root).map_err(|error| {
                GraphClientError::new(format!("source dependency projection failed: {error}"))
            })?;
            let mut payload = projection.payload();
            payload
                .as_object_mut()
                .ok_or_else(|| {
                    GraphClientError::new("source dependency payload must be an object")
                })?
                .insert("exit_code".to_string(), json!(0));
            return GraphResponse::from_source_projection("query", payload);
        }
        let mut options = vec![
            "--relation".to_string(),
            relation.to_string(),
            "--direction".to_string(),
            direction.to_string(),
            "--depth".to_string(),
            depth.to_string(),
        ];
        if let Some(path) = path {
            options.extend(["--path".to_string(), path.to_string()]);
        }
        if all_nodes {
            options.push("--all".to_string());
        }
        self.invoke("query", &options)
    }

    /// Read dependency context from source; token context remains an explicit persisted operation.
    pub fn context(
        &self,
        path: &str,
        token: Option<&str>,
    ) -> Result<GraphResponse, GraphClientError> {
        if let Some(token) = token {
            let options = [
                "--path".to_string(),
                path.to_string(),
                "--token".to_string(),
                token.to_string(),
            ];
            return self.invoke("context", &options);
        }
        let projection = build_context_projection_default(&self.root, path).map_err(|error| {
            GraphClientError::new(format!("source dependency context failed: {error}"))
        })?;
        let mut payload = projection.payload();
        payload
            .as_object_mut()
            .ok_or_else(|| GraphClientError::new("source context payload must be an object"))?
            .insert("exit_code".to_string(), json!(0));
        GraphResponse::from_source_projection("context", payload)
    }

    fn invoke_external(
        &self,
        executable: &Path,
        command: &str,
        options: &[String],
    ) -> Result<GraphResponse, GraphClientError> {
        let output = Command::new(executable)
            .arg("graph")
            .arg(command)
            .arg("--root")
            .arg(&self.root)
            .arg("--format")
            .arg("json")
            .args(options)
            .output()
            .map_err(|error| GraphClientError::new(format!("process launch failed: {error}")))?;
        let payload: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
            GraphClientError::new(format!("graph response is not JSON: {error}"))
        })?;
        let exit_code = process_exit_code(&output.status);
        GraphResponse::from_payload(command, payload, Some(exit_code))
    }
}

/// Run one typed GraphClient operation and return its validated response as JSON.
pub fn run(args: &[String]) -> i32 {
    if args
        .first()
        .is_some_and(|argument| matches!(argument.as_str(), "-h" | "--help"))
    {
        println!("{}", graph_client_usage());
        return 0;
    }
    let options = match GraphClientCli::parse(args) {
        Ok(options) => options,
        Err(error) => {
            eprintln!("GRAPH_CLIENT=fail reason={error}");
            return 2;
        }
    };
    let client = match options.executable.as_deref() {
        Some(executable) => GraphClient::with_executable(&options.root, executable),
        None => GraphClient::new(&options.root),
    };
    let result = client.and_then(|client| match options.command.as_str() {
        "status" => client.status(),
        "query" => client.query(
            options.path.as_deref(),
            &options.relation,
            &options.direction,
            options.depth,
            options.all_nodes,
        ),
        "context" => {
            let path = options
                .path
                .as_deref()
                .ok_or_else(|| GraphClientError::new("graph context requires --path"))?;
            client.context(path, options.token.as_deref())
        }
        _ => unreachable!("GraphClientCli validates the command"),
    });
    match result.and_then(|response| {
        let exit_code = response.exit_code;
        let payload = response.consumer_payload()?;
        Ok((payload, exit_code))
    }) {
        Ok((payload, exit_code)) => {
            match serde_json::to_string(&payload) {
                Ok(payload) => println!("{payload}"),
                Err(error) => {
                    eprintln!("GRAPH_CLIENT=fail reason=response serialization failed: {error}");
                    return 1;
                }
            }
            exit_code
        }
        Err(error) => {
            eprintln!("{error}");
            1
        }
    }
}

struct GraphClientCli {
    command: String,
    root: PathBuf,
    path: Option<String>,
    token: Option<String>,
    relation: String,
    direction: String,
    depth: i64,
    all_nodes: bool,
    executable: Option<PathBuf>,
}

impl GraphClientCli {
    fn parse(args: &[String]) -> Result<Self, String> {
        let Some(command) = args.first() else {
            return Err(graph_client_usage());
        };
        if !GRAPH_CLIENT_COMMANDS.contains(&command.as_str()) {
            return Err(format!("unsupported graph command: {command}"));
        }
        let mut root = None;
        let mut path = None;
        let mut token = None;
        let mut relation = "dependency".to_owned();
        let mut direction = "both".to_owned();
        let mut depth = 0_i64;
        let mut all_nodes = false;
        let mut executable = None;
        let mut format = "json".to_owned();
        let mut index = 1;
        while index < args.len() {
            let option = &args[index];
            let value = |index: &mut usize| -> Result<String, String> {
                let Some(value) = args.get(*index + 1) else {
                    return Err(format!("{option}: expected one argument"));
                };
                if value.starts_with('-') {
                    return Err(format!("{option}: expected one argument"));
                }
                *index += 1;
                Ok(value.clone())
            };
            match option.as_str() {
                "--root" => root = Some(PathBuf::from(value(&mut index)?)),
                "--path" => path = Some(value(&mut index)?),
                "--token" => token = Some(value(&mut index)?),
                "--relation" => relation = value(&mut index)?,
                "--direction" => direction = value(&mut index)?,
                "--depth" => {
                    depth = value(&mut index)?
                        .parse()
                        .map_err(|_| "graph query depth must be an integer".to_owned())?;
                }
                "--executable" => executable = Some(PathBuf::from(value(&mut index)?)),
                "--format" => format = value(&mut index)?,
                "--all" => all_nodes = true,
                "-h" | "--help" => return Err(graph_client_usage()),
                _ => return Err(format!("unrecognized argument: {option}")),
            }
            index += 1;
        }
        let root = root.ok_or_else(|| "--root is required".to_owned())?;
        if format != "json" {
            return Err("--format must be json".to_owned());
        }
        if *command == "context" && path.is_none() {
            return Err("graph context requires --path".to_owned());
        }
        Ok(Self {
            command: command.clone(),
            root,
            path,
            token,
            relation,
            direction,
            depth,
            all_nodes,
            executable,
        })
    }
}

fn graph_client_usage() -> String {
    "usage: agent-canon graph-client <status|query|context> --root ROOT [--path PATH] [--token TOKEN] [--relation RELATION] [--direction DIRECTION] [--depth N] [--all] [--executable PATH] [--format json]".to_owned()
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

fn resolve_path(path: &Path) -> Result<PathBuf, GraphClientError> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| GraphClientError::new(error.to_string()))?
            .join(path)
    };
    match fs::canonicalize(&absolute) {
        Ok(path) => Ok(path),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(absolute),
        Err(error) => Err(GraphClientError::new(error.to_string())),
    }
}

fn required_string(
    object: &Map<String, Value>,
    field: &str,
    owner: &str,
) -> Result<String, GraphClientError> {
    let candidate = object.get(field).and_then(Value::as_str);
    if let Some(candidate) = candidate.filter(|value| !value.is_empty()) {
        Ok(candidate.to_string())
    } else {
        Err(GraphClientError::new(format!(
            "{owner}.{field} must be nonempty text"
        )))
    }
}

fn required_mapping<'a>(
    value: Option<&'a Value>,
    owner: &str,
) -> Result<&'a Map<String, Value>, GraphClientError> {
    value
        .and_then(Value::as_object)
        .ok_or_else(|| GraphClientError::new(format!("{owner} must be an object")))
}

fn optional_mapping(value: Option<&Value>) -> Result<Option<Map<String, Value>>, GraphClientError> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::Object(object)) => Ok(Some(object.clone())),
        Some(_) => Err(GraphClientError::new(
            "graph optional mapping must be an object",
        )),
    }
}

fn optional_string(value: Option<&Value>) -> Result<Option<String>, GraphClientError> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(value)) => Ok(Some(value.clone())),
        Some(_) => Err(GraphClientError::new("graph optional string is invalid")),
    }
}

fn python_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => {
            value.as_i64() != Some(0) && value.as_u64() != Some(0) && value.as_f64() != Some(0.0)
        }
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}
