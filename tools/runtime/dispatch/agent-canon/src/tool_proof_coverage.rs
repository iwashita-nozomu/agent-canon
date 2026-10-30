// @dependency-start
// contract implementation
// responsibility Reports Lean proof-obligation coverage for cataloged AgentCanon tools.
// upstream implementation catalog::tool_catalog reuses canonical catalog validation and path resolution
// upstream design ../../../../../../agents/skills/formal-proof-workflow.md formal proof status policy
// upstream design ../../../../../../documents/tools/lean_capability_matrix.md Lean capability routing policy
// downstream design ../../../../../../documents/tools/tool_proof_coverage.md proof coverage report contract
// downstream implementation ../../../../../../tests/agent_tools/test_tool_proof_coverage.py native CLI oracle
// @dependency-end

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use regex::Regex;
use serde::Serialize;
use serde_json::json;
use yaml_rust2::{Yaml, YamlLoader};

use crate::catalog::tool_catalog;

pub const LEAN_VERIFIED: &str = "lean_verified";
pub const INVALID_LEAN_VERIFIED: &str = "invalid_lean_verified";
pub const UNVERIFIED: &str = "unverified_with_next_witness";
pub const EXTERNAL_ASSUMPTION: &str = "external_assumption_required";
pub const TEST_EVIDENCE_ONLY: &str = "test_evidence_only";

pub static PROOF_ESCAPE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b(sorry|admit|axiom)\b").expect("static Lean proof escape regex")
});

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Finding {
    pub check: String,
    pub tool_id: String,
    pub detail: String,
}

impl Finding {
    fn new(
        check: impl Into<String>,
        tool_id: impl Into<String>,
        detail: impl Into<String>,
    ) -> Self {
        Self {
            check: check.into(),
            tool_id: tool_id.into(),
            detail: detail.into(),
        }
    }

    pub fn render(&self) -> String {
        format!(
            "TOOL_PROOF_COVERAGE_FINDING={}:{}:{}",
            self.check, self.tool_id, self.detail
        )
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ProofClaim {
    pub status: String,
    pub theorem: Option<String>,
    pub artifact: Option<String>,
    pub checker: Option<String>,
    pub next_witness: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ToolProofRow {
    pub tool_id: String,
    pub path: String,
    pub role: String,
    pub writes: bool,
    pub docs: Vec<String>,
    pub tests: Vec<String>,
    pub performance_model: String,
    pub behavior: ProofClaim,
    pub performance: ProofClaim,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ProofCoverageReport {
    pub findings: Vec<Finding>,
    pub rows: Vec<ToolProofRow>,
    pub require_lean_verified: bool,
    pub selected_tool_ids: Vec<String>,
}

fn mapping_value<'a>(value: &'a Yaml, key: &str) -> Option<&'a Yaml> {
    tool_catalog::as_mapping(value)?
        .into_iter()
        .find_map(|(candidate, item)| (candidate == key).then_some(item))
}

fn sequence_value(value: &Yaml) -> Option<&[Yaml]> {
    tool_catalog::as_sequence(value)
}

pub fn string_tuple(value: Option<&Yaml>) -> Vec<String> {
    let Some(values) = value.and_then(sequence_value) else {
        return Vec::new();
    };
    values
        .iter()
        .filter_map(|item| item.as_str().map(str::to_owned))
        .collect()
}

fn yaml_truthy(value: &Yaml) -> bool {
    match value {
        Yaml::Null | Yaml::BadValue => false,
        Yaml::Boolean(value) => *value,
        Yaml::Integer(value) => *value != 0,
        Yaml::Real(value) => {
            if matches!(
                value.to_ascii_lowercase().as_str(),
                ".nan" | ".inf" | "+.inf" | "-.inf"
            ) {
                true
            } else {
                value.parse::<f64>().is_ok_and(|number| number != 0.0)
            }
        }
        Yaml::String(value) => !value.is_empty(),
        Yaml::Array(value) => !value.is_empty(),
        Yaml::Hash(value) => !value.is_empty(),
        Yaml::Alias(_) => true,
    }
}

fn yaml_python_string(value: &Yaml) -> String {
    match value {
        Yaml::Null => "None".to_owned(),
        Yaml::BadValue => "None".to_owned(),
        Yaml::Boolean(true) => "True".to_owned(),
        Yaml::Boolean(false) => "False".to_owned(),
        Yaml::Integer(value) => value.to_string(),
        Yaml::Real(value) => match value.to_ascii_lowercase().as_str() {
            ".nan" => "nan".to_owned(),
            ".inf" | "+.inf" => "inf".to_owned(),
            "-.inf" => "-inf".to_owned(),
            _ => value.clone(),
        },
        Yaml::String(value) => value.clone(),
        Yaml::Array(values) => format!(
            "[{}]",
            values.iter().map(yaml_repr).collect::<Vec<_>>().join(", ")
        ),
        Yaml::Hash(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| format!("{}: {}", yaml_repr(key), yaml_repr(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Yaml::Alias(value) => format!("*{value}"),
    }
}

fn yaml_repr(value: &Yaml) -> String {
    match value {
        Yaml::String(value) => {
            let quote = if value.contains('\'') && !value.contains('"') {
                '"'
            } else {
                '\''
            };
            let mut output = String::from(quote);
            for character in value.chars() {
                match character {
                    '\\' => output.push_str("\\\\"),
                    '\n' => output.push_str("\\n"),
                    '\r' => output.push_str("\\r"),
                    '\t' => output.push_str("\\t"),
                    character if character == quote => {
                        output.push('\\');
                        output.push(character);
                    }
                    character => output.push(character),
                }
            }
            output.push(quote);
            output
        }
        _ => yaml_python_string(value),
    }
}

fn string_or(value: Option<&Yaml>, fallback: &str) -> String {
    value
        .filter(|value| yaml_truthy(value))
        .map(yaml_python_string)
        .unwrap_or_else(|| fallback.to_owned())
}

fn optional_string(value: Option<&Yaml>) -> Option<String> {
    value.and_then(Yaml::as_str).map(str::to_owned)
}

pub fn entry_bool(entry: &Yaml, key: &str) -> bool {
    mapping_value(entry, key).and_then(Yaml::as_bool) == Some(true)
}

/// Loads validated catalog rows by reusing the shared tool catalog validator.
pub fn load_catalog_entries(root: &Path) -> (Vec<Yaml>, Vec<Finding>) {
    let catalog_report = tool_catalog::validate_catalog(root);
    let findings: Vec<Finding> = catalog_report
        .findings
        .iter()
        .map(|finding| Finding::new("catalog", &finding.path, &finding.detail))
        .collect();
    let catalog_path = tool_catalog::resolve_repo_path(root, tool_catalog::CATALOG_PATH, None);
    if !findings.is_empty() || !catalog_path.is_file() {
        return (Vec::new(), findings);
    }
    let text = match fs::read_to_string(&catalog_path) {
        Ok(text) => text,
        Err(_) => {
            return (
                Vec::new(),
                vec![Finding::new(
                    "catalog",
                    tool_catalog::CATALOG_PATH,
                    "read-failed",
                )],
            )
        }
    };
    let document = match YamlLoader::load_from_str(&text) {
        Ok(mut documents) => documents.pop().unwrap_or(Yaml::Null),
        Err(_) => {
            return (
                Vec::new(),
                vec![Finding::new(
                    "catalog",
                    tool_catalog::CATALOG_PATH,
                    "yaml-parse-failed",
                )],
            )
        }
    };
    if tool_catalog::as_mapping(&document).is_none() {
        return (
            Vec::new(),
            vec![Finding::new(
                "catalog",
                tool_catalog::CATALOG_PATH,
                "must-parse-as-mapping",
            )],
        );
    }
    let Some(raw_entries) = mapping_value(&document, "entries").and_then(sequence_value) else {
        return (
            Vec::new(),
            vec![Finding::new(
                "catalog",
                tool_catalog::CATALOG_PATH,
                "entries-must-be-list",
            )],
        );
    };
    let entries = raw_entries
        .iter()
        .filter(|entry| tool_catalog::as_mapping(entry).is_some())
        .cloned()
        .collect();
    (entries, findings)
}

/// Classifies the cost-model shape needed before a Lean performance proof.
pub fn performance_model_for(role: &str, writes: bool) -> &'static str {
    if matches!(role, "catalog" | "checker" | "inventory" | "docs") {
        "bounded_catalog_or_file_scan"
    } else if matches!(role, "runner" | "sync" | "workflow" | "experiment") {
        "external_command_or_runtime"
    } else if writes {
        "bounded_artifact_write"
    } else {
        "command_contract"
    }
}

/// Builds the default unverified claim for one catalog row.
pub fn default_claim(kind: &str, tool_id: &str, role: &str, tests: &[String]) -> ProofClaim {
    let (status, witness) = if kind == "behavior" && !tests.is_empty() {
        (
            TEST_EVIDENCE_ONLY,
            format!("Lean theorem binding {tool_id} behavior spec to implementation model"),
        )
    } else if matches!(role, "runner" | "sync" | "workflow" | "experiment") && kind == "performance"
    {
        (
            EXTERNAL_ASSUMPTION,
            format!("explicit runtime/backend cost axiom plus Lean theorem for {tool_id}"),
        )
    } else {
        (
            UNVERIFIED,
            format!("Lean theorem and checked proof artifact for {tool_id} {kind}"),
        )
    };
    ProofClaim {
        status: status.to_owned(),
        theorem: None,
        artifact: None,
        checker: None,
        next_witness: witness,
    }
}

/// Parses an optional declared proof claim and validates its evidence.
pub fn proof_claim_from_entry(
    root: &Path,
    entry: &Yaml,
    kind: &str,
    default: &ProofClaim,
) -> (ProofClaim, Vec<Finding>) {
    let tool_id = string_or(mapping_value(entry, "id"), "<missing-id>");
    let Some(proofs) =
        mapping_value(entry, "proofs").filter(|proofs| tool_catalog::as_mapping(proofs).is_some())
    else {
        return (default.clone(), Vec::new());
    };
    let Some(raw_claim) =
        mapping_value(proofs, kind).filter(|claim| tool_catalog::as_mapping(claim).is_some())
    else {
        return (default.clone(), Vec::new());
    };
    if mapping_value(raw_claim, "status").and_then(Yaml::as_str) != Some(LEAN_VERIFIED) {
        return (non_verified_claim(raw_claim, default), Vec::new());
    }
    verified_claim_from_metadata(root, &tool_id, kind, raw_claim)
}

/// Copies a declared non-verified proof claim without treating it as evidence.
pub fn non_verified_claim(raw_claim: &Yaml, default: &ProofClaim) -> ProofClaim {
    let status = mapping_value(raw_claim, "status")
        .filter(|value| yaml_truthy(value))
        .map(yaml_python_string)
        .unwrap_or_else(|| default.status.clone());
    let next_witness = optional_string(mapping_value(raw_claim, "next_witness"))
        .unwrap_or_else(|| default.next_witness.clone());
    ProofClaim {
        status,
        theorem: optional_string(mapping_value(raw_claim, "theorem")),
        artifact: optional_string(mapping_value(raw_claim, "artifact")),
        checker: optional_string(mapping_value(raw_claim, "checker")),
        next_witness,
    }
}

/// Validates metadata and the referenced proof artifact for a Lean claim.
pub fn verified_claim_from_metadata(
    root: &Path,
    tool_id: &str,
    kind: &str,
    raw_claim: &Yaml,
) -> (ProofClaim, Vec<Finding>) {
    let theorem = optional_string(mapping_value(raw_claim, "theorem"));
    let artifact = optional_string(mapping_value(raw_claim, "artifact"));
    let checker = optional_string(mapping_value(raw_claim, "checker"));
    let mut findings = Vec::new();
    if mapping_value(raw_claim, "checked").and_then(Yaml::as_bool) != Some(true) {
        findings.push(Finding::new(
            "proof",
            tool_id,
            format!("{kind}-lean-verified-requires-checked-true"),
        ));
    }
    if theorem
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        findings.push(Finding::new(
            "proof",
            tool_id,
            format!("{kind}-lean-verified-missing-theorem"),
        ));
    }
    if checker
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        findings.push(Finding::new(
            "proof",
            tool_id,
            format!("{kind}-lean-verified-missing-checker"),
        ));
    }
    findings.extend(validate_proof_artifact(
        root,
        tool_id,
        kind,
        mapping_value(raw_claim, "artifact"),
    ));
    let status = if findings.is_empty() {
        LEAN_VERIFIED
    } else {
        INVALID_LEAN_VERIFIED
    };
    let next_witness = if findings.is_empty() {
        "none".to_owned()
    } else {
        format!("repair Lean proof metadata for {tool_id} {kind}")
    };
    (
        ProofClaim {
            status: status.to_owned(),
            theorem,
            artifact,
            checker,
            next_witness,
        },
        findings,
    )
}

/// Validates one declared Lean proof artifact path without claiming it proves a theorem.
pub fn validate_proof_artifact(
    root: &Path,
    tool_id: &str,
    kind: &str,
    artifact: Option<&Yaml>,
) -> Vec<Finding> {
    let Some(artifact) = artifact
        .and_then(Yaml::as_str)
        .filter(|value| !value.trim().is_empty())
    else {
        return vec![Finding::new(
            "proof",
            tool_id,
            format!("{kind}-lean-verified-missing-artifact"),
        )];
    };
    let artifact_path = tool_catalog::resolve_repo_path(root, artifact, None);
    if !artifact_path.is_file() {
        return vec![Finding::new(
            "proof",
            tool_id,
            format!("{kind}-proof-artifact-missing:{artifact}"),
        )];
    }
    let text = match fs::read_to_string(&artifact_path) {
        Ok(text) => text,
        Err(_) => {
            return vec![Finding::new(
                "proof",
                tool_id,
                format!("{kind}-proof-artifact-unreadable:{artifact}"),
            )]
        }
    };
    if PROOF_ESCAPE_RE.is_match(&text) {
        vec![Finding::new(
            "proof",
            tool_id,
            format!("{kind}-proof-artifact-has-escape"),
        )]
    } else {
        Vec::new()
    }
}

/// Builds one proof-coverage row from a validated catalog entry.
pub fn row_from_entry(root: &Path, entry: &Yaml) -> (ToolProofRow, Vec<Finding>) {
    let tool_id = string_or(mapping_value(entry, "id"), "<missing-id>");
    let path = string_or(mapping_value(entry, "path"), "<missing-path>");
    let role = string_or(mapping_value(entry, "role"), "<missing-role>");
    let writes = entry_bool(entry, "writes");
    let docs = string_tuple(mapping_value(entry, "docs"));
    let tests = string_tuple(mapping_value(entry, "tests"));
    let performance_model = performance_model_for(&role, writes).to_owned();
    let (behavior, mut findings) = proof_claim_from_entry(
        root,
        entry,
        "behavior",
        &default_claim("behavior", &tool_id, &role, &tests),
    );
    let (performance, performance_findings) = proof_claim_from_entry(
        root,
        entry,
        "performance",
        &default_claim("performance", &tool_id, &role, &tests),
    );
    findings.extend(performance_findings);
    let row = ToolProofRow {
        tool_id,
        path,
        role,
        writes,
        docs,
        tests,
        performance_model,
        behavior,
        performance,
    };
    (row, findings)
}

/// Builds proof coverage and enforces Lean only for explicitly selected tools.
pub fn build_report(
    root: &Path,
    require_lean_verified: bool,
    selected_tool_ids: &[String],
) -> ProofCoverageReport {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let (entries, mut findings) = load_catalog_entries(&root);
    let mut selected = Vec::new();
    for tool_id in selected_tool_ids
        .iter()
        .filter(|tool_id| !tool_id.is_empty())
    {
        if !selected.contains(tool_id) {
            selected.push(tool_id.clone());
        }
    }
    let available: BTreeSet<String> = entries
        .iter()
        .map(|entry| string_or(mapping_value(entry, "id"), "<missing-id>"))
        .collect();
    for tool_id in &selected {
        if !available.contains(tool_id) {
            findings.push(Finding::new("selection", tool_id, "unknown-tool-id"));
        }
    }
    if require_lean_verified && selected.is_empty() {
        findings.push(Finding::new(
            "selection",
            "<none>",
            "explicit-tool-selection-required; universal-proof-backlog-retired",
        ));
    }
    let mut rows = Vec::new();
    for entry in &entries {
        let tool_id = string_or(mapping_value(entry, "id"), "<missing-id>");
        if !selected.is_empty() && !selected.contains(&tool_id) {
            continue;
        }
        let (row, row_findings) = row_from_entry(&root, entry);
        if require_lean_verified && !selected.is_empty() && row.behavior.status != LEAN_VERIFIED {
            findings.push(Finding::new(
                "coverage",
                &row.tool_id,
                "behavior-not-lean-verified",
            ));
        }
        if require_lean_verified && !selected.is_empty() && row.performance.status != LEAN_VERIFIED
        {
            findings.push(Finding::new(
                "coverage",
                &row.tool_id,
                "performance-not-lean-verified",
            ));
        }
        rows.push(row);
        findings.extend(row_findings);
    }
    findings.sort_by(|left, right| {
        (&left.check, &left.tool_id, &left.detail).cmp(&(
            &right.check,
            &right.tool_id,
            &right.detail,
        ))
    });
    ProofCoverageReport {
        findings,
        rows,
        require_lean_verified,
        selected_tool_ids: selected,
    }
}

/// Renders proof coverage as sorted-key, two-space-indented JSON.
pub fn render_json(report: &ProofCoverageReport) -> String {
    let payload = json!({
        "status": if report.findings.is_empty() { "pass" } else { "fail" },
        "require_lean_verified": report.require_lean_verified,
        "selected_tool_ids": &report.selected_tool_ids,
        "findings": &report.findings,
        "rows": &report.rows,
    });
    let json = serde_json::to_string_pretty(&payload).expect("proof coverage JSON serialization");
    escape_non_ascii_json(&json)
}

fn escape_non_ascii_json(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        let codepoint = character as u32;
        if codepoint <= 0x7f {
            escaped.push(character);
        } else if codepoint <= 0xffff {
            escaped.push_str(&format!("\\u{codepoint:04x}"));
        } else {
            let supplementary = codepoint - 0x1_0000;
            let high = 0xd800 + (supplementary >> 10);
            let low = 0xdc00 + (supplementary & 0x3ff);
            escaped.push_str(&format!("\\u{high:04x}\\u{low:04x}"));
        }
    }
    escaped
}

/// Escapes a pipe in a Markdown table cell.
pub fn markdown_cell(value: &str) -> String {
    value.replace('|', "\\|")
}

/// Renders the proof coverage table.
pub fn render_markdown(report: &ProofCoverageReport) -> String {
    let selected = if report.selected_tool_ids.is_empty() {
        "all (observational)".to_owned()
    } else {
        report.selected_tool_ids.join(",")
    };
    let mut lines = vec![
        "# Tool Proof Coverage".to_owned(),
        String::new(),
        format!(
            "- Status: `{}`",
            if report.findings.is_empty() {
                "pass"
            } else {
                "fail"
            }
        ),
        format!("- Tools: `{}`", report.rows.len()),
        format!("- Findings: `{}`", report.findings.len()),
        format!(
            "- Require Lean verified: `{}`",
            if report.require_lean_verified {
                "yes"
            } else {
                "no"
            }
        ),
        format!("- Selected tools: `{selected}`"),
        String::new(),
        "| Tool | Behavior Status | Performance Status | Performance Model | Next Witness |"
            .to_owned(),
        "| ---- | --------------- | ------------------ | ----------------- | ------------ |"
            .to_owned(),
    ];
    for row in &report.rows {
        lines.push(format!(
            "| `{}` | {} | {} | {} | {}; {} |",
            markdown_cell(&row.tool_id),
            markdown_cell(&row.behavior.status),
            markdown_cell(&row.performance.status),
            markdown_cell(&row.performance_model),
            markdown_cell(&row.behavior.next_witness),
            markdown_cell(&row.performance.next_witness),
        ));
    }
    if !report.findings.is_empty() {
        lines.extend([
            String::new(),
            "## Findings".to_owned(),
            String::new(),
            "| Check | Tool | Detail |".to_owned(),
            "| ----- | ---- | ------ |".to_owned(),
        ]);
        for finding in &report.findings {
            lines.push(format!(
                "| {} | `{}` | {} |",
                markdown_cell(&finding.check),
                markdown_cell(&finding.tool_id),
                markdown_cell(&finding.detail),
            ));
        }
    }
    lines.join("\n")
}

pub fn count_status(rows: &[ToolProofRow], kind: &str) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    for row in rows {
        let status = if kind == "behavior" {
            &row.behavior.status
        } else {
            &row.performance.status
        };
        *counts.entry(status.clone()).or_insert(0) += 1;
    }
    counts
}

/// Renders compact machine-readable text output.
pub fn render_text(report: &ProofCoverageReport) -> String {
    let behavior_counts = count_status(&report.rows, "behavior");
    let performance_counts = count_status(&report.rows, "performance");
    let mut lines: Vec<String> = report.findings.iter().map(Finding::render).collect();
    lines.extend([
        format!("TOOL_PROOF_COVERAGE_TOOLS={}", report.rows.len()),
        format!(
            "TOOL_PROOF_COVERAGE_BEHAVIOR_LEAN_VERIFIED={}",
            behavior_counts.get(LEAN_VERIFIED).copied().unwrap_or(0)
        ),
        format!(
            "TOOL_PROOF_COVERAGE_PERFORMANCE_LEAN_VERIFIED={}",
            performance_counts.get(LEAN_VERIFIED).copied().unwrap_or(0)
        ),
        format!(
            "TOOL_PROOF_COVERAGE_BEHAVIOR_TEST_EVIDENCE_ONLY={}",
            behavior_counts
                .get(TEST_EVIDENCE_ONLY)
                .copied()
                .unwrap_or(0)
        ),
        format!(
            "TOOL_PROOF_COVERAGE_PERFORMANCE_EXTERNAL_ASSUMPTION={}",
            performance_counts
                .get(EXTERNAL_ASSUMPTION)
                .copied()
                .unwrap_or(0)
        ),
        format!(
            "TOOL_PROOF_COVERAGE_REQUIRE_LEAN_VERIFIED={}",
            if report.require_lean_verified {
                "yes"
            } else {
                "no"
            }
        ),
        format!(
            "TOOL_PROOF_COVERAGE_SELECTED_TOOLS={}",
            report.selected_tool_ids.join(",")
        ),
        format!("TOOL_PROOF_COVERAGE_FINDINGS={}", report.findings.len()),
        format!(
            "TOOL_PROOF_COVERAGE={}",
            if report.findings.is_empty() {
                "pass"
            } else {
                "fail"
            }
        ),
    ]);
    lines.join("\n")
}

enum ProofCliArgs {
    Help,
    Run {
        root: PathBuf,
        format: ProofOutputFormat,
        require_lean_verified: bool,
        tool_ids: Vec<String>,
    },
    Error(String),
}

#[derive(Clone, Copy)]
enum ProofOutputFormat {
    Text,
    Json,
    Markdown,
}

const CLI_USAGE: &str = "usage: tool_proof_coverage.py [-h] [--root ROOT] [--format {text,json,markdown}] [--require-lean-verified] [--tool-id TOOL_ID]";

fn parse_output_format(value: &str) -> Option<ProofOutputFormat> {
    match value {
        "text" => Some(ProofOutputFormat::Text),
        "json" => Some(ProofOutputFormat::Json),
        "markdown" => Some(ProofOutputFormat::Markdown),
        _ => None,
    }
}

fn format_error(value: &str) -> String {
    format!("argument --format: invalid choice: '{value}' (choose from 'text', 'json', 'markdown')")
}

fn parse_cli_args(args: &[String]) -> ProofCliArgs {
    let mut root = PathBuf::from(".");
    let mut format = ProofOutputFormat::Text;
    let mut require_lean_verified = false;
    let mut tool_ids = Vec::new();
    let mut unknown = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let arg = args[index].as_str();
        if matches!(arg, "-h" | "--help") {
            return ProofCliArgs::Help;
        }
        if arg == "--require-lean-verified" {
            require_lean_verified = true;
            index += 1;
            continue;
        }
        if matches!(arg, "--root" | "--format" | "--tool-id") {
            let option = arg;
            let Some(value) = args.get(index + 1) else {
                return ProofCliArgs::Error(format!("argument {option}: expected one argument"));
            };
            if value.starts_with('-') {
                return ProofCliArgs::Error(format!("argument {option}: expected one argument"));
            }
            match option {
                "--root" => {
                    root = if value.is_empty() {
                        PathBuf::from(".")
                    } else {
                        PathBuf::from(value)
                    }
                }
                "--format" => match parse_output_format(value) {
                    Some(parsed) => format = parsed,
                    None => return ProofCliArgs::Error(format_error(value)),
                },
                "--tool-id" => tool_ids.push(value.clone()),
                _ => unreachable!(),
            }
            index += 2;
            continue;
        }
        if let Some(value) = arg.strip_prefix("--root=") {
            root = if value.is_empty() {
                PathBuf::from(".")
            } else {
                PathBuf::from(value)
            };
            index += 1;
            continue;
        }
        if let Some(value) = arg.strip_prefix("--format=") {
            match parse_output_format(value) {
                Some(parsed) => format = parsed,
                None => return ProofCliArgs::Error(format_error(value)),
            }
            index += 1;
            continue;
        }
        if let Some(value) = arg.strip_prefix("--tool-id=") {
            tool_ids.push(value.to_owned());
            index += 1;
            continue;
        }
        unknown.push(args[index].clone());
        index += 1;
    }
    if !unknown.is_empty() {
        return ProofCliArgs::Error(format!("unrecognized arguments: {}", unknown.join(" ")));
    }
    ProofCliArgs::Run {
        root,
        format,
        require_lean_verified,
        tool_ids,
    }
}

fn write_help<W: std::io::Write>(output: &mut W) -> std::io::Result<()> {
    writeln!(output, "{CLI_USAGE}")?;
    writeln!(output)?;
    writeln!(
        output,
        "Report formal proof-obligation coverage for cataloged AgentCanon tools."
    )?;
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
    writeln!(output, "  --format {{text,json,markdown}}")?;
    writeln!(output, "  --require-lean-verified")?;
    writeln!(
        output,
        "                        Require Lean evidence for the explicitly selected tools."
    )?;
    writeln!(output, "  --tool-id TOOL_ID     Select a catalog tool for proof validation; repeat for multiple tools.")
}

fn run_with_io<W: std::io::Write, E: std::io::Write>(
    args: &[String],
    stdout: &mut W,
    stderr: &mut E,
) -> i32 {
    let (root, format, require_lean_verified, tool_ids) = match parse_cli_args(args) {
        ProofCliArgs::Help => return if write_help(stdout).is_ok() { 0 } else { 1 },
        ProofCliArgs::Error(error) => {
            let _ = writeln!(stderr, "{CLI_USAGE}");
            let _ = writeln!(stderr, "tool_proof_coverage.py: error: {error}");
            return 2;
        }
        ProofCliArgs::Run {
            root,
            format,
            require_lean_verified,
            tool_ids,
        } => (root, format, require_lean_verified, tool_ids),
    };
    let report = build_report(&root, require_lean_verified, &tool_ids);
    let rendered = match format {
        ProofOutputFormat::Text => render_text(&report),
        ProofOutputFormat::Json => render_json(&report),
        ProofOutputFormat::Markdown => render_markdown(&report),
    };
    if writeln!(stdout, "{rendered}").is_err() {
        return 1;
    }
    if report.findings.is_empty() {
        0
    } else {
        1
    }
}

/// Runs the proof coverage command through the existing native AgentCanon CLI.
pub fn run(args: &[String]) -> i32 {
    let stdout = std::io::stdout();
    let stderr = std::io::stderr();
    let mut output = stdout.lock();
    let mut error = stderr.lock();
    run_with_io(args, &mut output, &mut error)
}
