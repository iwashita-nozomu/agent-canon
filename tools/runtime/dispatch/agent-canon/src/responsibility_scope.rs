// @dependency-start
// contract implementation
// responsibility Validates the total single-owner relation from tracked repository paths to responsibility scopes.
// upstream design ../../../../../responsibility-scope.toml machine-readable repo-local scope manifest
// upstream design ../../../../../templates/documents/responsibility-scope.template.toml starter manifest for template-derived repositories
// upstream design ../../../../../documents/design/responsibility-scope-management.md scope ownership policy
// upstream design ../../../../../documents/structure/repo-structure-contract.toml separate path existence and kind contract
// upstream design ../../../../catalog.yaml structured tool ownership
// upstream design ../../../../README.md tool entrypoint index
// upstream design ../../../../../documents/tools/README.md user-facing tool index
// downstream implementation main.rs exposes the responsibility-scope CLI selector
// downstream implementation ../../../../validation/semantic/tools/tool_rejection_preflight.py queries planned path owners
// downstream test ../../../../../tests/agent_tools/test_responsibility_scope.py tests scope validation and ownership queries
// @dependency-end

use crate::dependency_headers::fnmatch_case;
use agent_canon::tool_catalog::as_sequence as yaml_sequence;
use serde::Serialize;
use serde_json::json;
use std::collections::{BTreeSet, HashSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use toml_edit::{DocumentMut, Item, TableLike};
use yaml_rust2::{Yaml, YamlLoader};

pub const SELECTOR: &str = "responsibility-scope";
const MANIFEST_PATH: &str = "responsibility-scope.toml";
const CATALOG_PATH: &str = "tools/catalog.yaml";
const CATALOG_KIND: &str = "agent_canon_responsibility_scope";
const VERSION: i64 = 1;
const USAGE: &str = "usage: agent-canon responsibility-scope [--root ROOT] [--manifest MANIFEST] [--format {text,json}] [--path PATH]...";
const HELP: &str = "Validate AgentCanon responsibility scopes.\n\noptions:\n  --root ROOT          repository root; defaults to the current directory\n  --manifest MANIFEST  root-relative manifest path; defaults to responsibility-scope.toml\n  --format {text,json} output format; defaults to text\n  --path PATH          report owning scope IDs for a planned path; may be repeated\n  -h, --help           show this help message";

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Finding {
    pub check: String,
    pub path: String,
    pub detail: String,
}

impl Finding {
    fn new(check: impl Into<String>, path: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            check: check.into(),
            path: path.into(),
            detail: detail.into(),
        }
    }

    fn render(&self) -> String {
        format!(
            "RESPONSIBILITY_SCOPE_FINDING={}:{}:{}",
            self.check, self.path, self.detail
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Scope {
    pub scope_id: String,
    pub owner: String,
    pub scope_class: String,
    pub description: String,
    pub paths: Vec<String>,
    pub exclude_paths: Vec<String>,
    pub protecting_tools: Vec<String>,
    pub issues: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct PathOwnership {
    path: String,
    scope_ids: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScopeReport {
    pub scopes: Vec<Scope>,
    pub findings: Vec<Finding>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    manifest: String,
    format: OutputFormat,
    paths: Vec<String>,
    help: bool,
}

pub fn run(args: &[String]) -> i32 {
    let args = match parse_args(args) {
        Ok(args) => args,
        Err(message) => {
            eprintln!("responsibility-scope: {message}");
            eprintln!("{USAGE}");
            return 2;
        }
    };
    if args.help {
        println!("{USAGE}\n\n{HELP}");
        return 0;
    }

    let root = fs::canonicalize(&args.root).unwrap_or_else(|_| args.root.clone());
    let report = validate(&root, &args.manifest);
    let path_owners = if args.paths.is_empty() {
        Vec::new()
    } else {
        owners_for_paths(&report.scopes, &args.paths)
    };
    match args.format {
        OutputFormat::Json => print_json(&report, &path_owners, !args.paths.is_empty()),
        OutputFormat::Text => print_text(&report, &path_owners),
    }
    if report.findings.is_empty() {
        0
    } else {
        1
    }
}

fn parse_args(args: &[String]) -> Result<Args, String> {
    let mut root = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut manifest = MANIFEST_PATH.to_owned();
    let mut format = OutputFormat::Text;
    let mut paths = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "-h" | "--help") {
            return Ok(Args {
                root,
                manifest,
                format,
                paths,
                help: true,
            });
        }
        let (option, inline) = split_option(argument);
        let Some(option) = option else {
            return Err(format!("unrecognized arguments: {argument}"));
        };
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            let Some(value) = args.get(index) else {
                return Err(format!("argument {option}: expected one argument"));
            };
            if value.starts_with("--") || matches!(value.as_str(), "-h" | "--help") {
                return Err(format!("argument {option}: expected one argument"));
            }
            value.clone()
        };
        match option {
            "--root" => root = PathBuf::from(value),
            "--manifest" => manifest = value,
            "--format" => {
                format = match value.as_str() {
                    "text" => OutputFormat::Text,
                    "json" => OutputFormat::Json,
                    _ => {
                        return Err(format!(
                            "argument --format: invalid choice: '{value}' (choose from 'text', 'json')"
                        ));
                    }
                };
            }
            "--path" => paths.push(value),
            _ => unreachable!("split_option only returns supported options"),
        }
        index += 1;
    }
    Ok(Args {
        root,
        manifest,
        format,
        paths,
        help: false,
    })
}

fn split_option(argument: &str) -> (Option<&'static str>, Option<&str>) {
    let (name, value) = argument
        .split_once('=')
        .map_or((argument, None), |(name, value)| (name, Some(value)));
    match name {
        "--root" => (Some("--root"), value),
        "--manifest" => (Some("--manifest"), value),
        "--format" => (Some("--format"), value),
        "--path" => (Some("--path"), value),
        _ => (None, None),
    }
}

pub fn validate(root: &Path, manifest: &str) -> ScopeReport {
    let scope_root = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let (document, mut findings) = load_manifest(&scope_root.join(manifest));
    let (catalog_paths, catalog_findings) = load_catalog_paths(&scope_root);
    findings.extend(catalog_findings);
    let Some(document) = document else {
        return ScopeReport {
            scopes: Vec::new(),
            findings,
        };
    };

    let owners = string_set(document.get("owner_values"));
    let classes = string_set(document.get("class_values"));
    let scopes = scopes_from_item(document.get("scope"));
    if !version_is_supported(document.get("version")) {
        findings.push(Finding::new("manifest", manifest, "unsupported-version"));
    }
    if scopes.is_empty() {
        findings.push(Finding::new("manifest", manifest, "missing-scopes"));
    }

    let mut seen = HashSet::new();
    for scope in &scopes {
        if !seen.insert(scope.scope_id.clone()) {
            findings.push(Finding::new("scope", &scope.scope_id, "duplicate-id"));
        }
        findings.extend(validate_scope_shape(scope, &owners, &classes));
        findings.extend(validate_scope_references(&scope_root, scope));
        findings.extend(validate_protecting_tools(
            &scope_root,
            scope,
            &catalog_paths,
        ));
    }
    findings.extend(ownership_findings(&tracked_paths(&scope_root), &scopes));
    findings.sort_by(|left, right| {
        left.check
            .cmp(&right.check)
            .then_with(|| left.path.cmp(&right.path))
            .then_with(|| left.detail.cmp(&right.detail))
    });
    ScopeReport { scopes, findings }
}

fn load_manifest(path: &Path) -> (Option<DocumentMut>, Vec<Finding>) {
    if !path.is_file() {
        return (
            None,
            vec![Finding::new("manifest", path_text(path), "missing-file")],
        );
    }
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) => {
            return (
                None,
                vec![Finding::new(
                    "manifest",
                    path_text(path),
                    format!("read-failed:{error}"),
                )],
            );
        }
    };
    let document = match text.parse::<DocumentMut>() {
        Ok(document) => document,
        Err(error) => {
            return (
                None,
                vec![Finding::new(
                    "manifest",
                    path_text(path),
                    format!("invalid-toml:{error}"),
                )],
            );
        }
    };
    if document.get("catalog_kind").and_then(Item::as_str) != Some(CATALOG_KIND) {
        return (
            None,
            vec![Finding::new(
                "manifest",
                path_text(path),
                "invalid-catalog-kind",
            )],
        );
    }
    (Some(document), Vec::new())
}

fn load_catalog_paths(root: &Path) -> (BTreeSet<String>, Vec<Finding>) {
    let mut path = root.join(CATALOG_PATH);
    if !path.is_file() {
        path = root.join("vendor").join("agent-canon").join(CATALOG_PATH);
    }
    if !path.is_file() {
        return (
            BTreeSet::new(),
            vec![Finding::new("catalog", CATALOG_PATH, "missing-file")],
        );
    }
    let text = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(error) => {
            return (
                BTreeSet::new(),
                vec![Finding::new(
                    "catalog",
                    CATALOG_PATH,
                    format!("read-failed:{error}"),
                )],
            );
        }
    };
    let documents = match YamlLoader::load_from_str(&text) {
        Ok(documents) => documents,
        Err(error) => {
            return (
                BTreeSet::new(),
                vec![Finding::new(
                    "catalog",
                    CATALOG_PATH,
                    format!("invalid-yaml:{error}"),
                )],
            );
        }
    };
    if documents.len() != 1 {
        return (
            BTreeSet::new(),
            vec![Finding::new("catalog", CATALOG_PATH, "not-mapping")],
        );
    }
    let document = &documents[0];
    if document.as_hash().is_none() {
        return (
            BTreeSet::new(),
            vec![Finding::new("catalog", CATALOG_PATH, "not-mapping")],
        );
    }
    let Some(entries) = yaml_field(document, "entries") else {
        return (
            BTreeSet::new(),
            vec![Finding::new("catalog", CATALOG_PATH, "missing-entries")],
        );
    };
    let Some(entries) = yaml_sequence(entries) else {
        return (
            BTreeSet::new(),
            vec![Finding::new("catalog", CATALOG_PATH, "missing-entries")],
        );
    };
    let mut paths = BTreeSet::new();
    for entry in entries {
        if let Some(path) = yaml_field(entry, "path").and_then(Yaml::as_str) {
            paths.insert(logical_tool_path(path));
        }
    }
    (paths, Vec::new())
}

fn yaml_field<'a>(mapping: &'a Yaml, name: &str) -> Option<&'a Yaml> {
    mapping
        .as_hash()?
        .iter()
        .find_map(|(key, value)| (key.as_str() == Some(name)).then_some(value))
}

fn logical_tool_path(path: &str) -> String {
    path.strip_prefix("tools/agent-canon/")
        .map(|suffix| format!("tools/{suffix}"))
        .unwrap_or_else(|| path.to_owned())
}

fn string_set(item: Option<&Item>) -> BTreeSet<String> {
    string_tuple(item).into_iter().collect()
}

fn string_tuple(item: Option<&Item>) -> Vec<String> {
    item.and_then(Item::as_array)
        .into_iter()
        .flat_map(|array| array.iter())
        .filter_map(|value| value.as_str().map(str::to_owned))
        .collect()
}

fn scopes_from_item(item: Option<&Item>) -> Vec<Scope> {
    let Some(item) = item else {
        return Vec::new();
    };
    if let Some(tables) = item.as_array_of_tables() {
        return tables
            .iter()
            .map(|table| scope_from_table(table as &dyn TableLike))
            .collect();
    }
    item.as_array()
        .into_iter()
        .flat_map(|array| array.iter())
        .filter_map(|value| value.as_inline_table())
        .map(|table| scope_from_table(table as &dyn TableLike))
        .collect()
}

fn scope_from_table(table: &dyn TableLike) -> Scope {
    Scope {
        scope_id: python_string_or_empty(table.get("id")),
        owner: python_string_or_empty(table.get("owner")),
        scope_class: python_string_or_empty(table.get("class")),
        description: python_string_or_empty(table.get("description")),
        paths: string_tuple(table.get("paths")),
        exclude_paths: string_tuple(table.get("exclude_paths")),
        protecting_tools: string_tuple(table.get("protecting_tools")),
        issues: string_tuple(table.get("issues")),
    }
}

fn python_string_or_empty(item: Option<&Item>) -> String {
    let Some(item) = item.filter(|item| toml_item_truthy(*item)) else {
        return String::new();
    };
    if let Some(value) = item.as_str() {
        return value.to_owned();
    }
    if let Some(value) = item.as_bool() {
        return if value { "True" } else { "False" }.to_owned();
    }
    if let Some(value) = item.as_integer() {
        return value.to_string();
    }
    if let Some(value) = item.as_float() {
        let rendered = format!("{value:?}");
        return rendered;
    }
    item.to_string()
}

fn toml_item_truthy(item: &Item) -> bool {
    if let Some(value) = item.as_str() {
        return !value.is_empty();
    }
    if let Some(value) = item.as_bool() {
        return value;
    }
    if let Some(value) = item.as_integer() {
        return value != 0;
    }
    if let Some(value) = item.as_float() {
        return value != 0.0;
    }
    if let Some(array) = item.as_array() {
        return !array.is_empty();
    }
    if let Some(tables) = item.as_array_of_tables() {
        return !tables.is_empty();
    }
    if let Some(table) = item.as_table_like() {
        return table.iter().next().is_some();
    }
    true
}

fn version_is_supported(item: Option<&Item>) -> bool {
    item.is_some_and(|item| {
        item.as_integer() == Some(VERSION)
            || item.as_float() == Some(VERSION as f64)
            || item.as_bool() == Some(true)
    })
}

fn validate_scope_shape(
    scope: &Scope,
    owners: &BTreeSet<String>,
    classes: &BTreeSet<String>,
) -> Vec<Finding> {
    let mut findings = Vec::new();
    let label = if scope.scope_id.is_empty() {
        "<missing-id>"
    } else {
        &scope.scope_id
    };
    if !valid_scope_id(&scope.scope_id) {
        findings.push(Finding::new("scope", label, "invalid-id"));
    }
    if !owners.contains(&scope.owner) {
        findings.push(Finding::new("scope", label, "invalid-owner"));
    }
    if !classes.contains(&scope.scope_class) {
        findings.push(Finding::new("scope", label, "invalid-class"));
    }
    if scope.description.trim().is_empty() {
        findings.push(Finding::new("scope", label, "missing-description"));
    }
    if scope.paths.is_empty() {
        findings.push(Finding::new("scope", label, "missing-paths"));
    }
    if scope.protecting_tools.is_empty() {
        findings.push(Finding::new("scope", label, "missing-protecting-tools"));
    }
    findings
}

fn valid_scope_id(id: &str) -> bool {
    !id.is_empty()
        && id.split('-').all(|component| {
            !component.is_empty()
                && component
                    .chars()
                    .all(|character| character.is_ascii_lowercase() || character.is_ascii_digit())
        })
}

fn validate_scope_references(root: &Path, scope: &Scope) -> Vec<Finding> {
    scope
        .issues
        .iter()
        .filter(|issue| !root.join(issue.as_str()).is_file())
        .map(|issue| {
            Finding::new(
                "scope_issue",
                scope.scope_id.as_str(),
                format!("missing:{issue}"),
            )
        })
        .collect()
}

fn validate_protecting_tools(
    root: &Path,
    scope: &Scope,
    catalog_paths: &BTreeSet<String>,
) -> Vec<Finding> {
    let mut findings = Vec::new();
    for tool in &scope.protecting_tools {
        let logical_tool = logical_tool_path(tool);
        let mut candidates = vec![root.join(&logical_tool)];
        if let Some(suffix) = logical_tool.strip_prefix("tools/") {
            candidates.push(root.join("tools/agent-canon").join(suffix));
            candidates.push(root.join("vendor/agent-canon").join(&logical_tool));
        }
        if !candidates.iter().any(|candidate| candidate.exists()) {
            findings.push(Finding::new(
                "scope_tool",
                scope.scope_id.as_str(),
                format!("missing:{tool}"),
            ));
        }
        if !catalog_paths.contains(&logical_tool) {
            findings.push(Finding::new(
                "scope_tool",
                scope.scope_id.as_str(),
                format!("uncataloged:{tool}"),
            ));
        }
    }
    findings
}

fn tracked_paths(root: &Path) -> Vec<String> {
    if let Ok(output) = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["ls-files"])
        .output()
    {
        if output.status.success() {
            return String::from_utf8_lossy(&output.stdout)
                .lines()
                .filter(|path| !path.is_empty())
                .map(str::to_owned)
                .collect();
        }
    }
    let ignored: HashSet<&str> = [
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "reports",
        "target",
    ]
    .into_iter()
    .collect();
    let mut paths = Vec::new();
    walk_untracked_files(root, root, &ignored, &mut paths);
    paths.sort();
    paths
}

fn walk_untracked_files(
    root: &Path,
    current: &Path,
    ignored: &HashSet<&str>,
    paths: &mut Vec<String>,
) {
    let Ok(entries) = fs::read_dir(current) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let relative = path_text(path.strip_prefix(root).unwrap_or(&path));
        if Path::new(&relative).components().any(|component| {
            let component_name = component.as_os_str().to_string_lossy();
            ignored.contains(component_name.as_ref())
        }) {
            continue;
        }
        let Ok(file_type) = entry.file_type() else {
            continue;
        };
        if file_type.is_dir() {
            walk_untracked_files(root, &path, ignored, paths);
        } else if path.is_file() {
            paths.push(relative);
        }
    }
}

fn ownership_findings(paths: &[String], scopes: &[Scope]) -> Vec<Finding> {
    let mut findings = Vec::new();
    for path in paths {
        let scope_ids = scopes
            .iter()
            .filter(|scope| scope_covers(scope, path))
            .map(|scope| scope.scope_id.as_str())
            .collect::<Vec<_>>();
        if scope_ids.is_empty() {
            findings.push(Finding::new(
                "scope_unowned",
                path.as_str(),
                "no-owning-scope",
            ));
        } else if scope_ids.len() > 1 {
            findings.push(Finding::new(
                "scope_overlap",
                path.as_str(),
                format!("scopes:{}", scope_ids.join(",")),
            ));
        }
    }
    findings
}

fn pattern_covers(pattern: &str, required_path: &str) -> bool {
    if pattern == required_path {
        return true;
    }
    if let Some(prefix) = pattern.strip_suffix("/**") {
        let prefix = prefix.trim_end_matches('/');
        return required_path == prefix || required_path.starts_with(&format!("{prefix}/"));
    }
    fnmatch_case(required_path, pattern)
}

fn scope_covers(scope: &Scope, path: &str) -> bool {
    if scope
        .exclude_paths
        .iter()
        .any(|pattern| pattern_covers(pattern, path))
    {
        return false;
    }
    scope
        .paths
        .iter()
        .any(|pattern| pattern_covers(pattern, path))
}

fn owners_for_paths(scopes: &[Scope], paths: &[String]) -> Vec<PathOwnership> {
    paths
        .iter()
        .map(|path| PathOwnership {
            path: path.clone(),
            scope_ids: scopes
                .iter()
                .filter(|scope| scope_covers(scope, path))
                .map(|scope| scope.scope_id.clone())
                .collect(),
        })
        .collect()
}

fn path_text(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn print_json(report: &ScopeReport, path_owners: &[PathOwnership], include_owners: bool) {
    let mut output = json!({
        "status": if report.findings.is_empty() { "pass" } else { "fail" },
        "findings": report.findings,
        "scopes": report.scopes,
    });
    if include_owners {
        output["path_owners"] = json!(path_owners);
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&output).expect("responsibility scope report serializes")
    );
}

fn print_text(report: &ScopeReport, path_owners: &[PathOwnership]) {
    for finding in &report.findings {
        println!("{}", finding.render());
    }
    for ownership in path_owners {
        println!(
            "RESPONSIBILITY_SCOPE_PATH_OWNER={}:{}",
            ownership.path,
            ownership.scope_ids.join(",")
        );
    }
    println!("RESPONSIBILITY_SCOPE_SCOPES={}", report.scopes.len());
    println!("RESPONSIBILITY_SCOPE_FINDINGS={}", report.findings.len());
    println!(
        "RESPONSIBILITY_SCOPE={}",
        if report.findings.is_empty() {
            "pass"
        } else {
            "fail"
        }
    );
}
