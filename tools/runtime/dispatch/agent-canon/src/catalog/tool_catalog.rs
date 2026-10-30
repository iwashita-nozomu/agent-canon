use std::collections::{BTreeSet, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use regex::Regex;
use serde::Serialize;
use serde_json::{json, Map as JsonMap, Value as JsonValue};
use toml_edit::{DocumentMut, Item, TableLike};
use yaml_rust2::{
    parser::{Event, MarkedEventReceiver, Parser},
    scanner::{Marker, TScalarStyle},
    Yaml, YamlLoader,
};

use super::path_policy::is_retired_legacy_tool_path;

pub const CATALOG_PATH: &str = "tools/catalog.yaml";
pub const TOOL_DOCS_PATH: &str = "documents/tools/tool-docs.toml";
pub const PUBLIC_SURFACE_PRODUCER_VERSION: &str = "public-surface.v1";
pub const TOOL_CLASSIFICATIONS: [&str; 5] = ["public", "internal", "compat", "retired", "example"];

const DEFAULT_COMMAND_SOURCES: [&str; 2] = [
    "tools/validation/ci/runners/run_all_checks.sh",
    "tools/validation/ci/checks/check_agent_canon_pr.sh",
];
const ENTRY_WIRING_SOURCES: [&str; 6] = [
    "tools/validation/ci/runners/run_all_checks.sh",
    "tools/validation/ci/checks/check_agent_canon_pr.sh",
    "eval/producers/run_accumulated_agent_evals.py",
    "agents/skills/agent-canon-update.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
];
const CATALOG_DOCS: [&str; 4] = [
    "tools/README.md",
    "documents/tools/README.md",
    TOOL_DOCS_PATH,
    "documents/tools/repo-local-tool-imports.md",
];
const PUBLIC_TOOL_REFERENCE_PATTERN: &str =
    r"(?:^|[^A-Za-z0-9_./-])(tools/[A-Za-z0-9_./-]+\.(?:py|sh)\b)";

/// Regex matching default-wiring tool paths, with the path in capture group 1.
pub static TOOL_REFERENCE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(PUBLIC_TOOL_REFERENCE_PATTERN).expect("static tool reference regex")
});

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Finding {
    pub check: String,
    pub path: String,
    pub detail: String,
}

impl Finding {
    pub fn new(
        check: impl Into<String>,
        path: impl Into<String>,
        detail: impl Into<String>,
    ) -> Self {
        Self {
            check: check.into(),
            path: path.into(),
            detail: detail.into(),
        }
    }

    pub fn render(&self) -> String {
        format!(
            "TOOL_CATALOG_FINDING={}:{}:{}",
            self.check, self.path, self.detail
        )
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CatalogRow {
    pub tool_id: String,
    pub path: String,
    pub summary: String,
    pub family: String,
    pub role: String,
    pub status: String,
    pub audience: String,
    pub placement: String,
    pub command: Option<String>,
    pub writes: bool,
    pub ci: bool,
    pub pr_check: bool,
    pub docs: Vec<String>,
    pub tests: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CatalogReport {
    pub findings: Vec<Finding>,
    pub entries: Vec<CatalogRow>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct PublicSourceSpan {
    pub path: String,
    pub start_line: usize,
    pub start_column: usize,
    pub end_line: usize,
    pub end_column: usize,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct PublicSurfaceRow {
    pub surface_id: String,
    pub kind: String,
    pub path: String,
    pub selector: String,
    pub source_span: PublicSourceSpan,
    pub secondary_spans: Vec<PublicSourceSpan>,
    pub authority: String,
}

impl PublicSurfaceRow {
    fn new(
        surface_id: impl Into<String>,
        kind: impl Into<String>,
        path: impl Into<String>,
        selector: impl Into<String>,
        source_span: PublicSourceSpan,
        secondary_spans: Vec<PublicSourceSpan>,
    ) -> Self {
        Self {
            surface_id: surface_id.into(),
            kind: kind.into(),
            path: path.into(),
            selector: selector.into(),
            source_span,
            secondary_spans,
            authority: "public-surface".to_owned(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct PublicSurfaceReport {
    pub producer_version: String,
    pub rows: Vec<PublicSurfaceRow>,
    pub findings: Vec<Finding>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RustToken {
    pub value: String,
    pub start_line: usize,
    pub start_column: usize,
    pub end_line: usize,
    pub end_column: usize,
}

fn map_entries(value: &Yaml) -> Option<Vec<(&str, &Yaml)>> {
    let hash = value.as_hash()?;
    let mut entries = Vec::with_capacity(hash.len());
    for (key, item) in hash {
        entries.push((key.as_str()?, item));
    }
    Some(entries)
}

/// Returns a YAML mapping only when all keys are strings.
pub fn as_mapping(value: &Yaml) -> Option<Vec<(&str, &Yaml)>> {
    map_entries(value)
}

/// Returns a YAML sequence, excluding scalar strings and mappings.
pub fn as_sequence(value: &Yaml) -> Option<&[Yaml]> {
    value.as_vec().map(Vec::as_slice)
}

fn mapping_value<'a>(value: &'a Yaml, key: &str) -> Option<&'a Yaml> {
    value
        .as_hash()?
        .iter()
        .find_map(|(candidate, item)| (candidate.as_str() == Some(key)).then_some(item))
}

fn string_value(value: &Yaml) -> Option<&str> {
    value.as_str()
}

fn string_list(value: Option<&Yaml>) -> Vec<String> {
    value
        .and_then(Yaml::as_vec)
        .into_iter()
        .flatten()
        .filter_map(|item| item.as_str().map(str::to_owned))
        .collect()
}

fn bool_from_mapping(value: &Yaml, key: &str) -> bool {
    mapping_value(value, key).and_then(Yaml::as_bool) == Some(true)
}

fn inherited_string(entry: &Yaml, family_defaults: &Yaml, key: &str) -> Option<String> {
    let value = match mapping_value(entry, key) {
        Some(value) => Some(value),
        None => mapping_value(family_defaults, key),
    }?;
    string_value(value).map(str::to_owned)
}

fn has_non_string_key(mapping: &Yaml, key: &str) -> bool {
    mapping_value(mapping, key).is_some_and(|value| value.as_str().is_none())
}

pub fn resolve_repo_path(root: &Path, relative_path: &str, source_root: Option<&Path>) -> PathBuf {
    if let Some(source_root) = source_root {
        let source_root = source_root
            .canonicalize()
            .unwrap_or_else(|_| source_root.to_path_buf());
        return source_root.join(relative_path);
    }
    let root_path = root.join(relative_path);
    if root_path.exists() {
        return root_path;
    }
    let vendor_path = root.join("vendor/agent-canon").join(relative_path);
    if vendor_path.exists() {
        vendor_path
    } else {
        root_path
    }
}

fn load_catalog(path: &Path) -> (Option<Yaml>, Vec<Finding>) {
    if !path.is_file() {
        return (
            None,
            vec![Finding::new("catalog", CATALOG_PATH, "missing-file")],
        );
    }
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(_) => {
            return (
                None,
                vec![Finding::new("catalog", CATALOG_PATH, "read-failed")],
            )
        }
    };
    match YamlLoader::load_from_str(&text) {
        Ok(mut documents) => {
            let data = documents.pop().unwrap_or(Yaml::Null);
            if map_entries(&data).is_none() {
                (
                    None,
                    vec![Finding::new(
                        "catalog",
                        CATALOG_PATH,
                        "must-parse-as-mapping",
                    )],
                )
            } else {
                (Some(data), Vec::new())
            }
        }
        Err(_) => (
            None,
            vec![Finding::new("catalog", CATALOG_PATH, "yaml-parse-failed")],
        ),
    }
}

fn allowed_values(data: &Yaml, key: &str) -> BTreeSet<String> {
    string_list(mapping_value(data, key)).into_iter().collect()
}

fn entry_path(entry: &Yaml) -> String {
    mapping_value(entry, "path")
        .and_then(Yaml::as_str)
        .unwrap_or("<missing-path>")
        .to_owned()
}

fn entry_summary(entry: &Yaml) -> String {
    mapping_value(entry, "summary")
        .and_then(Yaml::as_str)
        .map(str::trim)
        .unwrap_or("")
        .to_owned()
}

fn family_default<'a>(family_defaults: &'a Yaml, family: &str) -> Option<&'a Yaml> {
    mapping_value(family_defaults, family)
}

fn catalog_row(entry: &Yaml, family_defaults: &Yaml) -> CatalogRow {
    let wiring = mapping_value(entry, "default_wiring").unwrap_or(&Yaml::Null);
    let family = mapping_value(entry, "family")
        .and_then(Yaml::as_str)
        .unwrap_or("<missing>");
    CatalogRow {
        tool_id: mapping_value(entry, "id")
            .and_then(Yaml::as_str)
            .unwrap_or("<missing-id>")
            .to_owned(),
        path: entry_path(entry),
        summary: entry_summary(entry),
        family: family.to_owned(),
        role: mapping_value(entry, "role")
            .and_then(Yaml::as_str)
            .unwrap_or("<missing>")
            .to_owned(),
        status: mapping_value(entry, "status")
            .and_then(Yaml::as_str)
            .unwrap_or("<missing>")
            .to_owned(),
        audience: inherited_string(entry, family_defaults, "audience")
            .unwrap_or_else(|| "<missing>".to_owned()),
        placement: inherited_string(entry, family_defaults, "placement")
            .unwrap_or_else(|| "<missing>".to_owned()),
        command: mapping_value(entry, "command")
            .and_then(Yaml::as_str)
            .map(str::to_owned),
        writes: mapping_value(entry, "writes").and_then(Yaml::as_bool) == Some(true),
        ci: bool_from_mapping(wiring, "ci"),
        pr_check: bool_from_mapping(wiring, "pr_check"),
        docs: string_list(mapping_value(entry, "docs")),
        tests: string_list(mapping_value(entry, "tests")),
    }
}

fn check_entry(
    root: &Path,
    entry: &Yaml,
    families: &BTreeSet<String>,
    statuses: &BTreeSet<String>,
    roles: &BTreeSet<String>,
    audiences: &BTreeSet<String>,
    placements: &BTreeSet<String>,
    family_defaults: &Yaml,
) -> Vec<Finding> {
    let mut findings = Vec::new();
    let path = entry_path(entry);
    let id = mapping_value(entry, "id").and_then(Yaml::as_str);
    let family = mapping_value(entry, "family").and_then(Yaml::as_str);
    let status = mapping_value(entry, "status").and_then(Yaml::as_str);
    let role = mapping_value(entry, "role").and_then(Yaml::as_str);
    let defaults = family
        .and_then(|name| family_default(family_defaults, name))
        .unwrap_or(&Yaml::Null);
    let audience = inherited_string(entry, defaults, "audience");
    let placement = inherited_string(entry, defaults, "placement");
    let target = resolve_repo_path(root, &path, None);

    if id.is_none_or(|value| !valid_id(value)) {
        findings.push(Finding::new("entry", &path, "invalid-id"));
    }
    if mapping_value(entry, "public").is_some_and(|value| value.as_bool().is_none()) {
        findings.push(Finding::new("entry", &path, "invalid-public"));
    }
    if family.is_none_or(|value| !families.contains(value)) {
        findings.push(Finding::new("entry", &path, "invalid-family"));
    }
    if status.is_none_or(|value| !statuses.contains(value)) {
        findings.push(Finding::new("entry", &path, "invalid-status"));
    }
    if role.is_none_or(|value| !roles.contains(value)) {
        findings.push(Finding::new("entry", &path, "invalid-role"));
    }
    if has_non_string_key(entry, "audience") {
        findings.push(Finding::new("entry", &path, "invalid-audience"));
    } else if audience.is_none() {
        findings.push(Finding::new("entry", &path, "missing-audience"));
    } else if !audiences.contains(audience.as_deref().unwrap_or_default()) {
        findings.push(Finding::new("entry", &path, "invalid-audience"));
    }
    if has_non_string_key(entry, "placement") {
        findings.push(Finding::new("entry", &path, "invalid-placement"));
    } else if placement.is_none() {
        findings.push(Finding::new("entry", &path, "missing-placement"));
    } else if !placements.contains(placement.as_deref().unwrap_or_default()) {
        findings.push(Finding::new("entry", &path, "invalid-placement"));
    }
    if status == Some("compatibility_wrapper")
        && placement.as_deref() != Some("compatibility_wrapper")
    {
        findings.push(Finding::new(
            "entry",
            &path,
            "compatibility-wrapper-placement-required",
        ));
    }
    if entry_summary(entry).is_empty() {
        findings.push(Finding::new("entry", &path, "missing-summary"));
    }
    if !target.exists() {
        findings.push(Finding::new("entry", &path, "missing-path"));
    }
    if is_retired_legacy_tool_path(&path) || status == Some("legacy_provenance") {
        findings.push(Finding::new("legacy", &path, "legacy-tools-are-retired"));
    }
    let docs = string_list(mapping_value(entry, "docs"));
    if docs.is_empty() {
        findings.push(Finding::new("entry", &path, "missing-docs"));
    }
    for doc in docs {
        if !resolve_repo_path(root, &doc, None).is_file() {
            findings.push(Finding::new("entry", &path, format!("missing-doc:{doc}")));
        }
    }
    let tests = string_list(mapping_value(entry, "tests"));
    let exempt_reason = mapping_value(entry, "test_exempt_reason").and_then(Yaml::as_str);
    if matches!(status, Some("canonical" | "compatibility_wrapper"))
        && tests.is_empty()
        && exempt_reason.is_none_or(|reason| reason.trim().is_empty())
    {
        findings.push(Finding::new("entry", &path, "missing-tests-or-exemption"));
    }
    for test in tests {
        if !resolve_repo_path(root, &test, None).is_file() {
            findings.push(Finding::new("entry", &path, format!("missing-test:{test}")));
        }
    }
    findings
}

fn valid_id(value: &str) -> bool {
    if value.is_empty() || value.starts_with('-') || value.ends_with('-') {
        return false;
    }
    value.split('-').all(|part| {
        !part.is_empty()
            && part
                .bytes()
                .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
    })
}

fn read_existing_text(root: &Path, paths: &[&str]) -> String {
    let mut chunks = Vec::new();
    for path in paths {
        let target = resolve_repo_path(root, path, None);
        if target.is_file() {
            if let Ok(text) = fs::read_to_string(target) {
                chunks.push(text);
            }
        }
    }
    chunks.join("\n")
}

pub fn referenced_tool_paths_from_text(text: &str) -> BTreeSet<String> {
    TOOL_REFERENCE_RE
        .captures_iter(text)
        .filter_map(|capture| capture.get(1).map(|value| value.as_str().to_owned()))
        .collect()
}

pub fn referenced_tool_paths(root: &Path) -> BTreeSet<String> {
    referenced_tool_paths_from_text(&read_existing_text(root, &DEFAULT_COMMAND_SOURCES))
}

fn check_default_wiring(root: &Path, entries: &[&Yaml]) -> Vec<Finding> {
    let catalog_paths: BTreeSet<String> = entries.iter().map(|entry| entry_path(entry)).collect();
    let default_text = read_existing_text(root, &ENTRY_WIRING_SOURCES);
    let mut findings = Vec::new();
    for path in referenced_tool_paths(root) {
        if !catalog_paths.contains(&path) {
            findings.push(Finding::new(
                "default_wiring",
                &path,
                "uncataloged-tool-reference",
            ));
        }
    }
    for entry in entries {
        let path = entry_path(entry);
        let wiring = mapping_value(entry, "default_wiring").unwrap_or(&Yaml::Null);
        if !(bool_from_mapping(wiring, "ci") || bool_from_mapping(wiring, "pr_check")) {
            continue;
        }
        let basename = Path::new(&path)
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or(&path);
        if !default_text.contains(&path) && !default_text.contains(basename) {
            findings.push(Finding::new(
                "default_wiring",
                &path,
                "wired-entry-not-referenced",
            ));
        }
    }
    findings
}

fn check_catalog_docs(root: &Path) -> Vec<Finding> {
    let mut findings = Vec::new();
    for path in CATALOG_DOCS {
        let target = resolve_repo_path(root, path, None);
        if !target.is_file() {
            findings.push(Finding::new("catalog_docs", path, "missing-file"));
            continue;
        }
        if let Ok(text) = fs::read_to_string(target) {
            for snippet in ["tools/catalog.yaml", "tool_catalog.py"] {
                if !text.contains(snippet) {
                    findings.push(Finding::new(
                        "catalog_docs",
                        path,
                        format!("missing:{snippet}"),
                    ));
                }
            }
        }
    }
    findings
}

#[derive(Clone, Debug)]
struct ToolDocEntry {
    is_mapping: bool,
    id: Option<String>,
    tool: Option<String>,
    doc: Option<String>,
    classification: Option<String>,
}

fn item_string(item: Option<&Item>) -> Option<&str> {
    item.and_then(Item::as_str)
}

fn tool_doc_entries(document: &DocumentMut) -> Option<Vec<ToolDocEntry>> {
    let item = document.get("tool")?;
    if let Some(tables) = item.as_array_of_tables() {
        return Some(
            tables
                .iter()
                .map(|table| tool_doc_from_table(table))
                .collect(),
        );
    }
    let array = item.as_array()?;
    let mut result = Vec::new();
    for value in array.iter() {
        let Some(inline) = value.as_inline_table() else {
            result.push(ToolDocEntry {
                is_mapping: false,
                id: None,
                tool: None,
                doc: None,
                classification: None,
            });
            continue;
        };
        let get = |key: &str| {
            inline
                .get(key)
                .and_then(|value| value.as_str())
                .map(str::to_owned)
        };
        result.push(ToolDocEntry {
            is_mapping: true,
            id: get("id"),
            tool: get("tool"),
            doc: get("doc"),
            classification: get("classification"),
        });
    }
    Some(result)
}

fn tool_doc_from_table(table: &dyn TableLike) -> ToolDocEntry {
    let get = |key: &str| table.get(key).and_then(Item::as_str).map(str::to_owned);
    ToolDocEntry {
        is_mapping: true,
        id: get("id"),
        tool: get("tool"),
        doc: get("doc"),
        classification: get("classification"),
    }
}

fn load_tool_docs(root: &Path) -> (Vec<ToolDocEntry>, Vec<Finding>) {
    let path = resolve_repo_path(root, TOOL_DOCS_PATH, None);
    if !path.is_file() {
        return (
            Vec::new(),
            vec![Finding::new("tool_docs", TOOL_DOCS_PATH, "missing-file")],
        );
    }
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(_) => {
            return (
                Vec::new(),
                vec![Finding::new("tool_docs", TOOL_DOCS_PATH, "read-failed")],
            )
        }
    };
    let document = match text.parse::<DocumentMut>() {
        Ok(document) => document,
        Err(_) => {
            return (
                Vec::new(),
                vec![Finding::new("tool_docs", TOOL_DOCS_PATH, "invalid-toml")],
            )
        }
    };
    if item_string(document.get("catalog_kind")) != Some("agent_canon_tool_docs") {
        return (
            Vec::new(),
            vec![Finding::new(
                "tool_docs",
                TOOL_DOCS_PATH,
                "invalid-catalog-kind",
            )],
        );
    }
    let classifications = document
        .get("classification_values")
        .and_then(Item::as_array)
        .map(|array| {
            array
                .iter()
                .filter_map(|value| value.as_str())
                .collect::<BTreeSet<_>>()
        })
        .unwrap_or_default();
    let expected: BTreeSet<&str> = TOOL_CLASSIFICATIONS.into_iter().collect();
    let mut findings = Vec::new();
    if classifications != expected {
        findings.push(Finding::new(
            "tool_docs",
            TOOL_DOCS_PATH,
            "invalid-classification-values",
        ));
    }
    let Some(entries) = tool_doc_entries(&document) else {
        findings.push(Finding::new(
            "tool_docs",
            TOOL_DOCS_PATH,
            "missing-tool-list",
        ));
        return (Vec::new(), findings);
    };
    let entries = entries
        .into_iter()
        .filter_map(|entry| {
            if entry.is_mapping {
                Some(entry)
            } else {
                findings.push(Finding::new(
                    "tool_docs",
                    TOOL_DOCS_PATH,
                    "tool-entry-not-mapping",
                ));
                None
            }
        })
        .collect();
    (entries, findings)
}

pub fn check_tool_docs_manifest(root: &Path, catalog_entries: &[&Yaml]) -> Vec<Finding> {
    let (doc_entries, mut findings) = load_tool_docs(root);
    let mut catalog_by_id: Vec<(String, &Yaml)> = Vec::new();
    for entry in catalog_entries {
        if let Some(id) = mapping_value(entry, "id").and_then(Yaml::as_str) {
            if let Some(existing) = catalog_by_id.iter_mut().find(|(key, _)| key == id) {
                existing.1 = entry;
            } else {
                catalog_by_id.push((id.to_owned(), entry));
            }
        }
    }
    let mut seen_tools = BTreeSet::new();
    let mut seen_docs = BTreeSet::new();
    let mut documented_public_ids = BTreeSet::new();
    let mut documented_public_tools: Vec<(String, String)> = Vec::new();
    let mut documented_ids = BTreeSet::new();
    for entry in &doc_entries {
        let (Some(id), Some(tool), Some(doc)) = (&entry.id, &entry.tool, &entry.doc) else {
            findings.push(Finding::new(
                "tool_docs",
                TOOL_DOCS_PATH,
                "missing-id-tool-or-doc",
            ));
            continue;
        };
        if !entry
            .classification
            .as_deref()
            .is_some_and(|value| TOOL_CLASSIFICATIONS.contains(&value))
        {
            findings.push(Finding::new("tool_docs", tool, "invalid-classification"));
        } else if entry.classification.as_deref() == Some("public") {
            documented_public_ids.insert(id.clone());
            if let Some(existing) = documented_public_tools
                .iter_mut()
                .find(|(key, _)| key == id)
            {
                existing.1 = tool.clone();
            } else {
                documented_public_tools.push((id.clone(), tool.clone()));
            }
        }
        if !seen_tools.insert(tool.clone()) {
            findings.push(Finding::new("tool_docs", tool, "duplicate-tool"));
        }
        if !seen_docs.insert(doc.clone()) {
            findings.push(Finding::new("tool_docs", doc, "duplicate-doc"));
        }
        documented_ids.insert(id.clone());
        let catalog_entry = catalog_by_id
            .iter()
            .find(|(key, _)| key == id)
            .map(|(_, entry)| *entry);
        let Some(catalog_entry) = catalog_entry else {
            findings.push(Finding::new(
                "tool_docs",
                tool,
                format!("missing-catalog-id:{id}"),
            ));
            continue;
        };
        if mapping_value(catalog_entry, "path").and_then(Yaml::as_str) != Some(tool.as_str()) {
            findings.push(Finding::new("tool_docs", tool, "catalog-path-mismatch"));
        }
        if !resolve_repo_path(root, tool, None).is_file() {
            findings.push(Finding::new("tool_docs", tool, "missing-tool"));
        }
        if !resolve_repo_path(root, doc, None).is_file() {
            findings.push(Finding::new("tool_docs", doc, "missing-doc"));
        }
        if !tool_doc_name_matches(tool, doc) {
            findings.push(Finding::new("tool_docs", doc, "tool-doc-name-mismatch"));
        }
        if !string_list(mapping_value(catalog_entry, "docs")).contains(doc) {
            findings.push(Finding::new(
                "tool_docs",
                tool,
                format!("catalog-doc-missing:{doc}"),
            ));
        }
    }
    let mut catalog_public_ids = BTreeSet::new();
    let mut all_catalog_ids = BTreeSet::new();
    for (id, entry) in &catalog_by_id {
        all_catalog_ids.insert(id.clone());
        if mapping_value(entry, "public").and_then(Yaml::as_bool) == Some(true) {
            catalog_public_ids.insert(id.clone());
        }
    }
    for id in documented_public_ids.difference(&catalog_public_ids) {
        let tool = documented_public_tools
            .iter()
            .find(|(key, _)| key == id)
            .map(|(_, tool)| tool.as_str())
            .unwrap_or("");
        let detail = if !all_catalog_ids.contains(id) {
            format!("missing-catalog-entry:{id}:{tool}")
        } else {
            format!("missing-public-mark:{id}:{tool}")
        };
        findings.push(Finding::new("public_tools", TOOL_DOCS_PATH, detail));
    }
    for id in catalog_public_ids.difference(&documented_public_ids) {
        let entry = catalog_by_id
            .iter()
            .find(|(key, _)| key == id)
            .map(|(_, entry)| *entry)
            .unwrap_or(&Yaml::Null);
        let detail = if !documented_ids.contains(id) {
            format!("missing-public-documentation:{id}:{}", entry_path(entry))
        } else {
            format!("non-public-documentation:{id}:{}", entry_path(entry))
        };
        findings.push(Finding::new("public_tools", CATALOG_PATH, detail));
    }
    findings
}

pub fn tool_doc_name_matches(tool: &str, doc: &str) -> bool {
    let tool_path = Path::new(tool);
    let doc_stem = Path::new(doc)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("");
    let tool_name = tool_path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("");
    if tool_name == "mod.rs" {
        let owner = tool_path
            .parent()
            .and_then(Path::file_name)
            .and_then(|value| value.to_str())
            .unwrap_or("");
        doc_stem == owner || doc_stem == owner.replace('_', "-")
    } else {
        tool_path.file_stem().and_then(|value| value.to_str()) == Some(doc_stem)
    }
}

pub fn validate_catalog(root: &Path) -> CatalogReport {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let (Some(data), mut findings) = load_catalog(&resolve_repo_path(&root, CATALOG_PATH, None))
    else {
        return CatalogReport {
            findings,
            entries: Vec::new(),
        };
    };
    let family_defaults = mapping_value(&data, "families")
        .cloned()
        .unwrap_or(Yaml::Null);
    let families: BTreeSet<String> = map_entries(&family_defaults)
        .unwrap_or_default()
        .into_iter()
        .map(|(name, _)| name.to_owned())
        .collect();
    let statuses = allowed_values(&data, "status_values");
    let roles = allowed_values(&data, "role_values");
    let audiences = allowed_values(&data, "audience_values");
    let placements = allowed_values(&data, "placement_values");
    if mapping_value(&data, "version").and_then(Yaml::as_i64) != Some(1) {
        findings.push(Finding::new("catalog", CATALOG_PATH, "unsupported-version"));
    }
    if families.is_empty() {
        findings.push(Finding::new("catalog", CATALOG_PATH, "missing-families"));
    }
    if statuses.is_empty() {
        findings.push(Finding::new(
            "catalog",
            CATALOG_PATH,
            "missing-status-values",
        ));
    }
    if roles.is_empty() {
        findings.push(Finding::new("catalog", CATALOG_PATH, "missing-role-values"));
    }
    if audiences.is_empty() {
        findings.push(Finding::new(
            "catalog",
            CATALOG_PATH,
            "missing-audience-values",
        ));
    }
    if placements.is_empty() {
        findings.push(Finding::new(
            "catalog",
            CATALOG_PATH,
            "missing-placement-values",
        ));
    }
    for (family_name, family_info) in map_entries(&family_defaults).unwrap_or_default() {
        let audience = inherited_string(family_info, &Yaml::Null, "audience");
        let placement = inherited_string(family_info, &Yaml::Null, "placement");
        if has_non_string_key(family_info, "audience") {
            findings.push(Finding::new("family", family_name, "invalid-audience"));
        } else if audience.is_none() {
            findings.push(Finding::new("family", family_name, "missing-audience"));
        } else if !audiences.contains(audience.as_deref().unwrap_or_default()) {
            findings.push(Finding::new("family", family_name, "invalid-audience"));
        }
        if has_non_string_key(family_info, "placement") {
            findings.push(Finding::new("family", family_name, "invalid-placement"));
        } else if placement.is_none() {
            findings.push(Finding::new("family", family_name, "missing-placement"));
        } else if !placements.contains(placement.as_deref().unwrap_or_default()) {
            findings.push(Finding::new("family", family_name, "invalid-placement"));
        }
    }
    let Some(raw_entries) = mapping_value(&data, "entries").and_then(Yaml::as_vec) else {
        findings.push(Finding::new(
            "catalog",
            CATALOG_PATH,
            "entries-must-be-list",
        ));
        return CatalogReport {
            findings,
            entries: Vec::new(),
        };
    };
    let mut entries = Vec::new();
    let mut rows = Vec::new();
    let mut ids = BTreeSet::new();
    for (index, raw_entry) in raw_entries.iter().enumerate() {
        if map_entries(raw_entry).is_none() {
            findings.push(Finding::new(
                "entry",
                CATALOG_PATH,
                format!("entry-{}-not-mapping", index + 1),
            ));
            continue;
        }
        entries.push(raw_entry);
        let family = mapping_value(raw_entry, "family")
            .and_then(Yaml::as_str)
            .unwrap_or("");
        let defaults = family_default(&family_defaults, family).unwrap_or(&Yaml::Null);
        rows.push(catalog_row(raw_entry, defaults));
        if let Some(id) = mapping_value(raw_entry, "id").and_then(Yaml::as_str) {
            if !ids.insert(id.to_owned()) {
                findings.push(Finding::new(
                    "entry",
                    entry_path(raw_entry),
                    format!("duplicate-id:{id}"),
                ));
            }
        }
        findings.extend(check_entry(
            &root,
            raw_entry,
            &families,
            &statuses,
            &roles,
            &audiences,
            &placements,
            &family_defaults,
        ));
    }
    findings.extend(check_default_wiring(&root, &entries));
    findings.extend(check_catalog_docs(&root));
    findings.extend(check_tool_docs_manifest(&root, &entries));
    findings.sort_by(|left, right| {
        (&left.check, &left.path, &left.detail).cmp(&(&right.check, &right.path, &right.detail))
    });
    CatalogReport {
        findings,
        entries: rows,
    }
}

pub fn check_catalog(root: &Path) -> Vec<Finding> {
    validate_catalog(root).findings
}

/// Lexes the bounded Rust token subset used by the public dispatch extractor.
pub fn rust_tokens(text: &str) -> Result<Vec<RustToken>, String> {
    let characters: Vec<char> = text.chars().collect();
    let mut tokens = Vec::new();
    let mut index = 0;
    let mut line = 1;
    let mut column = 1;
    while index < characters.len() {
        let character = characters[index];
        if character.is_whitespace() {
            advance_position(character, &mut line, &mut column);
            index += 1;
            continue;
        }
        if starts_with(&characters, index, "//") {
            let mut end = index;
            while end < characters.len() && characters[end] != '\n' {
                end += 1;
            }
            for current in &characters[index..end] {
                advance_position(*current, &mut line, &mut column);
            }
            index = end;
            continue;
        }
        if starts_with(&characters, index, "/*") {
            let mut depth = 1usize;
            let mut end = index + 2;
            while end < characters.len() && depth > 0 {
                if starts_with(&characters, end, "/*") {
                    depth += 1;
                    end += 2;
                } else if starts_with(&characters, end, "*/") {
                    depth -= 1;
                    end += 2;
                } else {
                    end += 1;
                }
            }
            if depth > 0 {
                return Err("unterminated block comment".to_owned());
            }
            for current in &characters[index..end] {
                advance_position(*current, &mut line, &mut column);
            }
            index = end;
            continue;
        }

        let start_line = line;
        let start_column = column;
        let end;
        let mut value;
        if character == '"' {
            let mut cursor = index + 1;
            let mut escaped = false;
            let mut closed = false;
            while cursor < characters.len() {
                let current = characters[cursor];
                if current == '"' && !escaped {
                    cursor += 1;
                    closed = true;
                    break;
                }
                escaped = current == '\\' && !escaped;
                if current != '\\' {
                    escaped = false;
                }
                cursor += 1;
            }
            if !closed {
                return Err("unterminated string literal".to_owned());
            }
            end = cursor;
            value = characters[index..end].iter().collect::<String>();
        } else if character.is_alphabetic() || character == '_' {
            let mut cursor = index + 1;
            while cursor < characters.len()
                && (characters[cursor].is_alphanumeric() || characters[cursor] == '_')
            {
                cursor += 1;
            }
            end = cursor;
            value = characters[index..end].iter().collect::<String>();
        } else if character.is_numeric() {
            let mut cursor = index + 1;
            while cursor < characters.len() && characters[cursor].is_numeric() {
                cursor += 1;
            }
            end = cursor;
            value = characters[index..end].iter().collect::<String>();
        } else {
            let compound = ["::", "..", ">=", "&&", "||", "==", "=>"]
                .into_iter()
                .find(|operator| starts_with(&characters, index, operator));
            value = compound
                .unwrap_or_else(|| {
                    // A one-character fallback is kept as a static slice only for
                    // the branch selection; the actual token is built below.
                    ""
                })
                .to_owned();
            if value.is_empty() {
                end = index + 1;
                value.push(character);
            } else {
                end = index + value.chars().count();
            }
        }
        for current in &characters[index..end] {
            advance_position(*current, &mut line, &mut column);
        }
        tokens.push(RustToken {
            value,
            start_line,
            start_column,
            end_line: line,
            end_column: column,
        });
        index = end;
    }
    Ok(tokens)
}

fn starts_with(characters: &[char], start: usize, needle: &str) -> bool {
    let needle: Vec<char> = needle.chars().collect();
    characters.get(start..start + needle.len()) == Some(needle.as_slice())
}

fn advance_position(character: char, line: &mut usize, column: &mut usize) {
    if character == '\n' {
        *line += 1;
        *column = 1;
    } else {
        *column += 1;
    }
}

/// Returns all starts of one exact token sequence.
pub fn token_sequence_matches(tokens: &[RustToken], values: &[&str]) -> Vec<usize> {
    if values.is_empty() {
        return (0..=tokens.len()).collect();
    }
    if values.len() > tokens.len() {
        return Vec::new();
    }
    (0..=tokens.len() - values.len())
        .filter(|start| {
            tokens[*start..*start + values.len()]
                .iter()
                .map(|token| token.value.as_str())
                .eq(values.iter().copied())
        })
        .collect()
}

/// Returns the one-based source span covering one token sequence.
pub fn token_span(
    path: &str,
    tokens: &[RustToken],
    start: usize,
    length: usize,
) -> PublicSourceSpan {
    let first = &tokens[start];
    let last = &tokens[start + length - 1];
    PublicSourceSpan {
        path: path.to_owned(),
        start_line: first.start_line,
        start_column: first.start_column,
        end_line: last.end_line,
        end_column: last.end_column,
    }
}

/// Returns a phrase span only when it occurs on exactly one source line.
pub fn text_phrase_span(path: &str, text: &str, phrase: &str) -> Option<PublicSourceSpan> {
    let mut matches = Vec::new();
    for (line_index, source_line) in text.lines().enumerate() {
        if let Some(start) = source_line.find(phrase) {
            let start_column = source_line[..start].chars().count() + 1;
            let end_column = start_column + phrase.chars().count();
            matches.push(PublicSourceSpan {
                path: path.to_owned(),
                start_line: line_index + 1,
                start_column,
                end_line: line_index + 1,
                end_column,
            });
        }
    }
    (matches.len() == 1).then(|| matches.remove(0))
}

#[derive(Default)]
struct MappingFrame {
    pending_key: Option<String>,
}

#[derive(Default)]
struct IdMarkReceiver {
    mappings: Vec<MappingFrame>,
    spans: Vec<(String, Marker, TScalarStyle)>,
}

impl IdMarkReceiver {
    fn begin_child(&mut self) {
        if let Some(mapping) = self.mappings.last_mut() {
            if mapping.pending_key.is_some() {
                mapping.pending_key = None;
            }
        }
    }

    fn scalar(&mut self, value: &str, marker: Marker, style: TScalarStyle) {
        if let Some(mapping) = self.mappings.last_mut() {
            if let Some(key) = mapping.pending_key.take() {
                if key == "id" {
                    self.spans.push((value.to_owned(), marker, style));
                }
            } else {
                mapping.pending_key = Some(value.to_owned());
            }
        }
    }
}

impl MarkedEventReceiver for IdMarkReceiver {
    fn on_event(&mut self, event: Event, marker: Marker) {
        match event {
            Event::MappingStart(..) => {
                self.begin_child();
                self.mappings.push(MappingFrame::default());
            }
            Event::MappingEnd => {
                self.mappings.pop();
            }
            Event::SequenceStart(..) => self.begin_child(),
            Event::Scalar(value, style, _, _) => self.scalar(&value, marker, style),
            Event::Alias(_) => self.scalar("", marker, TScalarStyle::Plain),
            _ => {}
        }
    }
}

/// Indexes YAML scalar values paired with an `id` key using parser source marks.
pub fn yaml_id_spans(path: &str, text: &str) -> Result<Vec<(String, PublicSourceSpan)>, String> {
    let mut parser = Parser::new_from_str(text);
    let mut receiver = IdMarkReceiver::default();
    parser
        .load(&mut receiver, true)
        .map_err(|error| error.to_string())?;
    let mut spans = Vec::new();
    let mut seen = HashSet::new();
    for (value, marker, style) in receiver.spans {
        if !seen.insert(value.clone()) {
            continue;
        }
        let (end_line, end_column) = yaml_scalar_end(text, marker, style);
        spans.push((
            value,
            PublicSourceSpan {
                path: path.to_owned(),
                start_line: marker.line(),
                start_column: marker.col(),
                end_line,
                end_column,
            },
        ));
    }
    Ok(spans)
}

fn yaml_scalar_end(text: &str, marker: Marker, style: TScalarStyle) -> (usize, usize) {
    let characters: Vec<char> = text.chars().collect();
    let start = char_offset(&characters, marker.line(), marker.col());
    let end = match style {
        TScalarStyle::SingleQuoted => scan_quoted_end(&characters, start, '\'', false),
        TScalarStyle::DoubleQuoted => scan_quoted_end(&characters, start, '"', true),
        TScalarStyle::Literal | TScalarStyle::Folded => {
            scan_block_end(&characters, start, marker.line())
        }
        TScalarStyle::Plain => scan_plain_end(&characters, start),
    };
    position_after(&characters, start, end)
}

fn char_offset(characters: &[char], wanted_line: usize, wanted_column: usize) -> usize {
    let mut line = 1;
    let mut column = 1;
    for (index, character) in characters.iter().enumerate() {
        if line == wanted_line && column == wanted_column {
            return index;
        }
        advance_position(*character, &mut line, &mut column);
    }
    characters.len()
}

fn scan_quoted_end(characters: &[char], start: usize, quote: char, escapes: bool) -> usize {
    let mut index = start + 1;
    let mut escaped = false;
    while index < characters.len() {
        let character = characters[index];
        if character == quote && !escaped {
            if !escapes && characters.get(index + 1) == Some(&quote) {
                index += 2;
                continue;
            }
            return index + 1;
        }
        if escapes {
            escaped = character == '\\' && !escaped;
            if character != '\\' {
                escaped = false;
            }
        }
        index += 1;
    }
    characters.len()
}

fn scan_plain_end(characters: &[char], start: usize) -> usize {
    let mut index = start;
    let mut last_non_space = start;
    while index < characters.len() {
        let character = characters[index];
        if character == '\n' || character == '\r' || matches!(character, ',' | ']' | '}') {
            break;
        }
        if character == '#' && (index == start || characters[index - 1].is_whitespace()) {
            break;
        }
        index += 1;
        if !character.is_whitespace() {
            last_non_space = index;
        }
    }
    last_non_space
}

fn scan_block_end(characters: &[char], start: usize, start_line: usize) -> usize {
    let lines: Vec<&[char]> = characters.split(|character| *character == '\n').collect();
    if start_line == 0 || start_line > lines.len() {
        return start;
    }
    let header_indent = lines[start_line - 1]
        .iter()
        .take_while(|character| **character == ' ')
        .count();
    let mut current_line = start_line;
    let mut last_end = start;
    while current_line < lines.len() {
        let line = lines[current_line];
        let indent = line
            .iter()
            .take_while(|character| **character == ' ')
            .count();
        let content = &line[indent..];
        if !content.is_empty() && indent <= header_indent {
            break;
        }
        if let Some(last) = content
            .iter()
            .rposition(|character| !character.is_whitespace())
        {
            last_end = line_start_offset(&lines, current_line) + indent + last + 1;
        }
        current_line += 1;
    }
    last_end
}

fn line_start_offset(lines: &[&[char]], line_index: usize) -> usize {
    lines
        .iter()
        .take(line_index)
        .map(|line| line.len() + 1)
        .sum()
}

fn position_after(characters: &[char], start: usize, end: usize) -> (usize, usize) {
    let mut line = 1;
    let mut column = 1;
    for character in &characters[..start.min(characters.len())] {
        advance_position(*character, &mut line, &mut column);
    }
    for character in &characters[start.min(characters.len())..end.min(characters.len())] {
        advance_position(*character, &mut line, &mut column);
    }
    (line, column)
}

fn indexed_spans(path: &str, text: &str) -> Result<Vec<(String, PublicSourceSpan)>, String> {
    yaml_id_spans(path, text)
}

fn yaml_document(text: &str) -> Result<Yaml, String> {
    YamlLoader::load_from_str(text)
        .map_err(|error| error.to_string())
        .map(|mut documents| documents.pop().unwrap_or(Yaml::Null))
}

fn yaml_sequence(value: Option<&Yaml>) -> &[Yaml] {
    value
        .and_then(Yaml::as_vec)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

fn sort_findings(findings: &mut [Finding]) {
    findings.sort_by(|left, right| {
        (&left.check, &left.path, &left.detail).cmp(&(&right.check, &right.path, &right.detail))
    });
}

/// Extracts canonical public CLI, tool, and skill surfaces with source spans.
pub fn extract_public_surface(root: &Path) -> PublicSurfaceReport {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let main_path = "tools/runtime/dispatch/agent-canon/src/main.rs";
    let graph_path = "tools/runtime/dispatch/agent-canon/src/graph.rs";
    let cli_path = "agents/canonical/CLI_ENTRYPOINTS.md";
    let tool_path = CATALOG_PATH;
    let skill_path = "agents/skills/catalog.yaml";
    let required_paths = [main_path, graph_path, cli_path, tool_path, skill_path];
    let mut findings = Vec::new();
    let mut texts = Vec::new();
    for relative_path in required_paths {
        let resolved = resolve_repo_path(&root, relative_path, None);
        if !resolved.is_file() {
            findings.push(Finding::new(
                "public_surface",
                relative_path,
                "missing-input",
            ));
            continue;
        }
        match fs::read_to_string(resolved) {
            Ok(text) => texts.push((relative_path, text)),
            Err(_) => findings.push(Finding::new("public_surface", relative_path, "read-failed")),
        }
    }
    let text_for = |path: &str| {
        texts
            .iter()
            .find(|(candidate, _)| *candidate == path)
            .map(|(_, text)| text.as_str())
    };
    let (Some(main_text), Some(graph_text), Some(cli_text)) = (
        text_for(main_path),
        text_for(graph_path),
        text_for(cli_path),
    ) else {
        return PublicSurfaceReport {
            producer_version: PUBLIC_SURFACE_PRODUCER_VERSION.to_owned(),
            rows: Vec::new(),
            findings,
        };
    };
    let main_tokens = match rust_tokens(main_text) {
        Ok(tokens) => tokens,
        Err(error) => {
            findings.push(Finding::new(
                "public_surface",
                "rust-dispatch",
                format!("rust_dispatch_invalid:{error}"),
            ));
            return PublicSurfaceReport {
                producer_version: PUBLIC_SURFACE_PRODUCER_VERSION.to_owned(),
                rows: Vec::new(),
                findings,
            };
        }
    };
    let graph_tokens = match rust_tokens(graph_text) {
        Ok(tokens) => tokens,
        Err(error) => {
            findings.push(Finding::new(
                "public_surface",
                "rust-dispatch",
                format!("rust_dispatch_invalid:{error}"),
            ));
            return PublicSurfaceReport {
                producer_version: PUBLIC_SURFACE_PRODUCER_VERSION.to_owned(),
                rows: Vec::new(),
                findings,
            };
        }
    };
    let mod_matches = token_sequence_matches(&main_tokens, &["mod", "graph", ";"]);
    let main_sequence = [
        "if",
        "args",
        ".",
        "len",
        "(",
        ")",
        ">=",
        "2",
        "&&",
        "args",
        "[",
        "1",
        "]",
        "==",
        "\"graph\"",
        "{",
        "std",
        "::",
        "process",
        "::",
        "exit",
        "(",
        "graph",
        "::",
        "run",
        "(",
        "&",
        "args",
        "[",
        "2",
        "..",
        "]",
        ")",
        ")",
        ";",
        "}",
    ];
    let main_matches = token_sequence_matches(&main_tokens, &main_sequence);
    if mod_matches.len() != 1 || main_matches.len() != 1 {
        let detail = if mod_matches.len() > 1 || main_matches.len() > 1 {
            "rust_dispatch_ambiguous"
        } else {
            "rust_dispatch_invalid"
        };
        findings.push(Finding::new("public_surface", main_path, detail));
        return PublicSurfaceReport {
            producer_version: PUBLIC_SURFACE_PRODUCER_VERSION.to_owned(),
            rows: Vec::new(),
            findings,
        };
    }
    let main_span = token_span(
        main_path,
        &main_tokens,
        main_matches[0],
        main_sequence.len(),
    );
    let mut rows = Vec::new();
    for (operation, handler) in [
        ("build", "build_graph_with_failure"),
        ("status", "read_graph_status"),
        ("query", "query_graph"),
        ("context", "context_graph"),
    ] {
        let sequence = [
            format!("\"{operation}\""),
            "=>".to_owned(),
            handler.to_owned(),
            "(".to_owned(),
            "&".to_owned(),
            "parsed".to_owned(),
            ")".to_owned(),
        ];
        let sequence_refs: Vec<&str> = sequence.iter().map(String::as_str).collect();
        let matches = token_sequence_matches(&graph_tokens, &sequence_refs);
        let doc_span = text_phrase_span(cli_path, cli_text, &format!("graph {operation}"));
        if matches.len() != 1 || doc_span.is_none() {
            let detail = if matches.len() > 1 {
                "rust_dispatch_ambiguous"
            } else {
                "rust_dispatch_invalid"
            };
            findings.push(Finding::new(
                "public_surface",
                graph_path,
                format!("{detail}:{operation}"),
            ));
            continue;
        }
        let mut secondary = vec![main_span.clone(), doc_span.expect("checked above")];
        secondary.sort_by(|left, right| {
            (&left.path, left.start_line, left.start_column).cmp(&(
                &right.path,
                right.start_line,
                right.start_column,
            ))
        });
        rows.push(PublicSurfaceRow::new(
            format!("cli:graph {operation}"),
            "cli",
            graph_path,
            format!("graph {operation}"),
            token_span(graph_path, &graph_tokens, matches[0], sequence.len()),
            secondary,
        ));
    }

    if let Some(text) = text_for(tool_path) {
        match yaml_document(text) {
            Ok(document) => {
                let tool_spans = indexed_spans(tool_path, text);
                match tool_spans {
                    Ok(spans) => {
                        for raw_entry in yaml_sequence(mapping_value(&document, "entries")) {
                            if map_entries(raw_entry).is_none()
                                || mapping_value(raw_entry, "public").and_then(Yaml::as_bool)
                                    != Some(true)
                            {
                                continue;
                            }
                            let Some(identifier) =
                                mapping_value(raw_entry, "id").and_then(Yaml::as_str)
                            else {
                                continue;
                            };
                            let Some((_, span)) =
                                spans.iter().find(|(candidate, _)| candidate == identifier)
                            else {
                                findings.push(Finding::new(
                                    "public_surface",
                                    tool_path,
                                    format!("span-missing:{identifier}"),
                                ));
                                continue;
                            };
                            let selector = mapping_value(raw_entry, "command")
                                .and_then(Yaml::as_str)
                                .unwrap_or(identifier);
                            rows.push(PublicSurfaceRow::new(
                                format!("tool:{identifier}"),
                                "tool",
                                span.path.clone(),
                                selector,
                                span.clone(),
                                Vec::new(),
                            ));
                        }
                    }
                    Err(error) => findings.push(Finding::new(
                        "public_surface",
                        tool_path,
                        format!("yaml-source-invalid:{error}"),
                    )),
                }
            }
            Err(error) => findings.push(Finding::new(
                "public_surface",
                tool_path,
                format!("yaml-parse-failed:{error}"),
            )),
        }
    }
    if let Some(text) = text_for(skill_path) {
        match yaml_document(text) {
            Ok(document) => {
                let skill_spans = indexed_spans(skill_path, text);
                match skill_spans {
                    Ok(spans) => {
                        for raw_entry in yaml_sequence(mapping_value(&document, "skill_families")) {
                            if map_entries(raw_entry).is_none() {
                                continue;
                            }
                            let Some(identifier) =
                                mapping_value(raw_entry, "id").and_then(Yaml::as_str)
                            else {
                                continue;
                            };
                            let Some((_, span)) =
                                spans.iter().find(|(candidate, _)| candidate == identifier)
                            else {
                                findings.push(Finding::new(
                                    "public_surface",
                                    skill_path,
                                    format!("span-missing:{identifier}"),
                                ));
                                continue;
                            };
                            rows.push(PublicSurfaceRow::new(
                                format!("skill:{identifier}"),
                                "skill",
                                span.path.clone(),
                                identifier,
                                span.clone(),
                                Vec::new(),
                            ));
                        }
                    }
                    Err(error) => findings.push(Finding::new(
                        "public_surface",
                        skill_path,
                        format!("yaml-source-invalid:{error}"),
                    )),
                }
            }
            Err(error) => findings.push(Finding::new(
                "public_surface",
                skill_path,
                format!("yaml-parse-failed:{error}"),
            )),
        }
    }
    rows.sort_by(|left, right| {
        (
            &left.kind,
            &left.surface_id,
            &left.source_span.path,
            left.source_span.start_line,
        )
            .cmp(&(
                &right.kind,
                &right.surface_id,
                &right.source_span.path,
                right.source_span.start_line,
            ))
    });
    let mut seen = BTreeSet::new();
    for row in &rows {
        if !seen.insert(row.surface_id.clone()) {
            findings.push(Finding::new(
                "public_surface",
                &row.source_span.path,
                format!("surface-id-duplicate:{}", row.surface_id),
            ));
        }
    }
    sort_findings(&mut findings);
    if !findings.is_empty() {
        rows.clear();
    }
    PublicSurfaceReport {
        producer_version: PUBLIC_SURFACE_PRODUCER_VERSION.to_owned(),
        rows,
        findings,
    }
}

/// Renders the stable JSON bundle used by catalog callers.
pub fn render_json(report: &CatalogReport, public: Option<&PublicSurfaceReport>) -> String {
    let catalog = json!({
        "status": if report.findings.is_empty() { "pass" } else { "fail" },
        "findings": &report.findings,
        "entries": &report.entries,
    });
    let mut payload = JsonMap::new();
    payload.insert("schema".to_owned(), json!("agent_canon.catalog_bundle.v1"));
    payload.insert("catalog".to_owned(), catalog);
    if let Some(public) = public {
        payload.insert(
            "public".to_owned(),
            json!({
                "producer_version": &public.producer_version,
                "status": if public.findings.is_empty() { "pass" } else { "fail" },
                "findings": &public.findings,
                "rows": &public.rows,
            }),
        );
    }
    serde_json::to_string_pretty(&JsonValue::Object(payload)).expect("catalog JSON serialization")
}

/// Escapes the only Markdown table delimiter used by the report projection.
pub fn markdown_cell(value: &str) -> String {
    value.replace('|', "\\|")
}

/// Renders the catalog validation report and tool crosswalk.
pub fn render_markdown(report: &CatalogReport) -> String {
    let status = if report.findings.is_empty() {
        "pass"
    } else {
        "fail"
    };
    let mut lines = vec![
        "# AgentCanon Tool Catalog".to_owned(),
        String::new(),
        format!("- Status: `{status}`"),
        format!("- Findings: `{}`", report.findings.len()),
        format!("- Entries: `{}`", report.entries.len()),
        String::new(),
    ];
    if !report.findings.is_empty() {
        lines.extend([
            "## Findings".to_owned(),
            String::new(),
            "| Check | Path | Detail |".to_owned(),
            "| ----- | ---- | ------ |".to_owned(),
        ]);
        for finding in &report.findings {
            lines.push(format!(
                "| {} | `{}` | {} |",
                markdown_cell(&finding.check),
                markdown_cell(&finding.path),
                markdown_cell(&finding.detail)
            ));
        }
        lines.push(String::new());
    }
    lines.extend([
        "## Tool Crosswalk".to_owned(),
        String::new(),
        "| ID | Family | Audience | Placement | Status | Default | Path | Summary |".to_owned(),
        "| -- | ------ | -------- | --------- | ------ | ------- | ---- | ------- |".to_owned(),
    ]);
    for entry in &report.entries {
        let default = [entry.ci.then_some("ci"), entry.pr_check.then_some("pr")]
            .into_iter()
            .flatten()
            .collect::<Vec<_>>()
            .join(",");
        let default = if default.is_empty() { "-" } else { &default };
        lines.push(format!(
            "| `{}` | {} | {} | {} | {} | {} | `{}` | {} |",
            markdown_cell(&entry.tool_id),
            markdown_cell(&entry.family),
            markdown_cell(&entry.audience),
            markdown_cell(&entry.placement),
            markdown_cell(&entry.status),
            markdown_cell(default),
            markdown_cell(&entry.path),
            markdown_cell(&entry.summary)
        ));
    }
    lines.join("\n")
}

enum CatalogCliArgs {
    Help,
    Run {
        root: PathBuf,
        format: CatalogOutputFormat,
    },
    Error(String),
}

#[derive(Clone, Copy)]
enum CatalogOutputFormat {
    Text,
    Json,
    Markdown,
}

const CLI_USAGE: &str = "usage: tool_catalog.py [-h] [--root ROOT] [--format {text,json,markdown}]";

fn parse_cli_args(args: &[String]) -> CatalogCliArgs {
    let mut root = PathBuf::from(".");
    let mut format = CatalogOutputFormat::Text;
    let mut unexpected = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "-h" || argument == "--help" {
            return CatalogCliArgs::Help;
        }
        if argument == "--root" {
            let Some(value) = args.get(index + 1) else {
                return CatalogCliArgs::Error("argument --root: expected one argument".to_owned());
            };
            if value.starts_with('-') {
                return CatalogCliArgs::Error("argument --root: expected one argument".to_owned());
            }
            root = if value.is_empty() {
                PathBuf::from(".")
            } else {
                PathBuf::from(value)
            };
            index += 2;
            continue;
        }
        if let Some(value) = argument.strip_prefix("--root=") {
            root = if value.is_empty() {
                PathBuf::from(".")
            } else {
                PathBuf::from(value)
            };
            index += 1;
            continue;
        }
        if argument == "--format" {
            let Some(value) = args.get(index + 1) else {
                return CatalogCliArgs::Error(
                    "argument --format: expected one argument".to_owned(),
                );
            };
            if value.starts_with('-') {
                return CatalogCliArgs::Error(
                    "argument --format: expected one argument".to_owned(),
                );
            }
            match parse_output_format(value) {
                Some(parsed) => format = parsed,
                None => return CatalogCliArgs::Error(invalid_format_error(value)),
            }
            index += 2;
            continue;
        }
        if let Some(value) = argument.strip_prefix("--format=") {
            match parse_output_format(value) {
                Some(parsed) => format = parsed,
                None => return CatalogCliArgs::Error(invalid_format_error(value)),
            }
            index += 1;
            continue;
        }
        unexpected.push(args[index].clone());
        index += 1;
    }
    if !unexpected.is_empty() {
        return CatalogCliArgs::Error(format!("unrecognized arguments: {}", unexpected.join(" ")));
    }
    CatalogCliArgs::Run { root, format }
}

fn parse_output_format(value: &str) -> Option<CatalogOutputFormat> {
    match value {
        "text" => Some(CatalogOutputFormat::Text),
        "json" => Some(CatalogOutputFormat::Json),
        "markdown" => Some(CatalogOutputFormat::Markdown),
        _ => None,
    }
}

fn invalid_format_error(value: &str) -> String {
    format!("argument --format: invalid choice: '{value}' (choose from 'text', 'json', 'markdown')")
}

fn write_cli_help<W: std::io::Write>(output: &mut W) -> std::io::Result<()> {
    writeln!(output, "{CLI_USAGE}")?;
    writeln!(output)?;
    writeln!(output, "Validate the structured AgentCanon tool catalog.")?;
    writeln!(output)?;
    writeln!(output, "options:")?;
    writeln!(
        output,
        "  -h, --help            show this help message and exit"
    )?;
    writeln!(
        output,
        "  --root ROOT           Repository root. Defaults to cwd."
    )?;
    writeln!(output, "  --format {{text,json,markdown}}")
}

pub(crate) fn run_with_io<W: std::io::Write, E: std::io::Write>(
    args: &[String],
    stdout: &mut W,
    stderr: &mut E,
) -> i32 {
    let (root, format) = match parse_cli_args(args) {
        CatalogCliArgs::Help => return if write_cli_help(stdout).is_ok() { 0 } else { 1 },
        CatalogCliArgs::Error(error) => {
            let _ = writeln!(stderr, "{CLI_USAGE}");
            let _ = writeln!(stderr, "tool_catalog.py: error: {error}");
            return 2;
        }
        CatalogCliArgs::Run { root, format } => (root, format),
    };

    let report = validate_catalog(&root);
    let public = extract_public_surface(&root);
    match format {
        CatalogOutputFormat::Json => {
            if writeln!(stdout, "{}", render_json(&report, Some(&public))).is_err() {
                return 1;
            }
        }
        CatalogOutputFormat::Markdown => {
            if writeln!(stdout, "{}", render_markdown(&report)).is_err() {
                return 1;
            }
            return if report.findings.is_empty() { 0 } else { 1 };
        }
        CatalogOutputFormat::Text => {
            for finding in report.findings.iter().chain(&public.findings) {
                if writeln!(stdout, "{}", finding.render()).is_err() {
                    return 1;
                }
            }
            let total_findings = report.findings.len() + public.findings.len();
            let status = if total_findings == 0 { "pass" } else { "fail" };
            if writeln!(stdout, "TOOL_CATALOG_FINDINGS={total_findings}").is_err()
                || writeln!(stdout, "TOOL_CATALOG={status}").is_err()
            {
                return 1;
            }
        }
    }
    if report.findings.is_empty() && public.findings.is_empty() {
        0
    } else {
        1
    }
}

/// Runs the existing tool-catalog CLI contract on native catalog owners.
pub fn run(args: &[String]) -> i32 {
    let stdout = std::io::stdout();
    let stderr = std::io::stderr();
    let mut output = stdout.lock();
    let mut error = stderr.lock();
    run_with_io(args, &mut output, &mut error)
}
