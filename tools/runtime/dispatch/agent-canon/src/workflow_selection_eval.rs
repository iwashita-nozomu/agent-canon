// @dependency-start
// contract implementation
// responsibility Evaluates deterministic workflow-selection cases and publishes prompt-free reports.
// upstream design ../../../../../eval/definitions/workflow_selection_eval.toml owns the frozen case inputs
// upstream implementation prompt_classifier.rs owns prompt-to-workflow and skill classification
// upstream implementation skill_lane_detector.rs owns structural lane evidence
// upstream implementation eval_manifest_paths.rs resolves canonical Eval manifests
// upstream implementation eval_archive_paths.rs owns accumulated Eval destinations
// upstream implementation runtime_boundary.rs owns external report publication
// downstream implementation main.rs exposes the evaluate-workflow-selection selector
// downstream test ../../tests/agent_tools/test_evaluate_workflow_selection.py preserves CLI oracles
// @dependency-end

use crate::eval_archive_paths::eval_results_dir;
use crate::eval_manifest_paths::{eval_manifest_path, resolve_eval_manifest};
use crate::prompt_classifier::{
    prompt_intake_signals, PromptClassifierInputs, SkillLaneEvidence,
};
use crate::python_cli_integer::is_argparse_negative_number;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::python_json::{JsonObject, JsonString, JsonValue};
use crate::python_text::python_strip;
use crate::runtime_boundary::RuntimeArtifactBoundary;
use crate::skill_lane_detector::{
    structural_skill_lane_concept_matches, validation_failure_repair_concept_matches,
};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use time::OffsetDateTime;
use toml_edit::{DocumentMut, Item, TableLike, Value as TomlValue};

const DEFAULT_RESULTS_FAMILY: &str = "workflow-selection";
const RUN_ID_DIGEST_LENGTH: usize = 10;
const MARKDOWN_TICK: char = '\x60';
const USAGE: &str = "usage: agent-canon evaluate-workflow-selection [--root ROOT] [--runtime-root RUNTIME_ROOT] [--manifest MANIFEST] [--report-out REPORT_OUT] [--accumulate] [--run-id RUN_ID] [--results-dir RESULTS_DIR]";

#[derive(Clone, Debug)]
struct WorkflowSelectionCase {
    case_id: String,
    group_id: String,
    description: String,
    prompt: String,
    expected_workflows: Vec<String>,
    forbidden_workflows: Vec<String>,
    expected_skills: Vec<String>,
    expected_tools: Vec<String>,
}

#[derive(Clone, Debug)]
struct WorkflowSelectionResult {
    case: WorkflowSelectionCase,
    observed_workflows: Vec<String>,
    selected_skills: Vec<String>,
    candidate_skills: Vec<String>,
    observed_tools: Vec<String>,
    missing_workflows: Vec<String>,
    forbidden_workflows_seen: Vec<String>,
    missing_skills: Vec<String>,
    missing_tools: Vec<String>,
}

impl WorkflowSelectionResult {
    fn passed(&self) -> bool {
        self.missing_workflows.is_empty()
            && self.forbidden_workflows_seen.is_empty()
            && self.missing_skills.is_empty()
            && self.missing_tools.is_empty()
    }
}

#[derive(Clone, Debug)]
struct WorkflowSelectionManifest {
    cases: Vec<WorkflowSelectionCase>,
    expected_case_count: Option<i64>,
    expected_generated_case_count: Option<i64>,
    generated_case_count: usize,
    count_failures: Vec<String>,
}

#[derive(Clone, Debug)]
struct WorkflowSelectionBundle {
    run_id: String,
    requested_run_id: String,
    status: &'static str,
    root: PathBuf,
    manifest: PathBuf,
    results: Vec<WorkflowSelectionResult>,
    expected_case_count: Option<i64>,
    expected_generated_case_count: Option<i64>,
    generated_case_count: usize,
    count_failures: Vec<String>,
}

impl WorkflowSelectionBundle {
    fn failed_count(&self) -> usize {
        self.results.iter().filter(|result| !result.passed()).count()
    }
}

#[derive(Clone, Copy)]
enum CliOption {
    Help,
    Root,
    RuntimeRoot,
    Manifest,
    ReportOut,
    Accumulate,
    RunId,
    ResultsDir,
}

const CLI_OPTIONS: &[(&str, CliOption)] = &[
    ("--help", CliOption::Help),
    ("--root", CliOption::Root),
    ("--runtime-root", CliOption::RuntimeRoot),
    ("--manifest", CliOption::Manifest),
    ("--report-out", CliOption::ReportOut),
    ("--accumulate", CliOption::Accumulate),
    ("--run-id", CliOption::RunId),
    ("--results-dir", CliOption::ResultsDir),
];

struct CliOptions {
    root: PathBuf,
    runtime_root: Option<PathBuf>,
    manifest: PathBuf,
    report_out: Option<PathBuf>,
    accumulate: bool,
    run_id: String,
    results_dir: String,
}

enum RunFailure {
    Evaluation(String),
    Runtime(String),
}

fn table_entries<'a>(
    item: Option<&'a Item>,
    field: &str,
) -> Result<Vec<&'a dyn TableLike>, String> {
    let Some(item) = item else {
        return Ok(Vec::new());
    };
    if let Some(tables) = item.as_array_of_tables() {
        return Ok(tables
            .iter()
            .map(|table| table as &dyn TableLike)
            .collect());
    }
    let Some(array) = item.as_array() else {
        return Err(format!("{field} must be a list of tables"));
    };
    let singular = if field == "cases" {
        "case"
    } else {
        "case group"
    };
    array
        .iter()
        .enumerate()
        .map(|(index, value)| {
            value
                .as_inline_table()
                .map(|table| table as &dyn TableLike)
                .ok_or_else(|| format!("{singular} {} must be a table", index + 1))
        })
        .collect()
}

fn toml_value_string(value: &TomlValue) -> String {
    if let Some(text) = value.as_str() {
        return text.to_owned();
    }
    if let Some(integer) = value.as_integer() {
        return integer.to_string();
    }
    if let Some(boolean) = value.as_bool() {
        return if boolean { "True" } else { "False" }.to_owned();
    }
    if let Some(float) = value.as_float() {
        return float.to_string();
    }
    if let Some(datetime) = value.as_datetime() {
        return datetime.to_string();
    }
    value.to_string()
}

fn item_is_truthy(item: Option<&Item>) -> bool {
    let Some(item) = item else {
        return false;
    };
    if let Some(value) = item.as_value() {
        if let Some(text) = value.as_str() {
            return !text.is_empty();
        }
        if let Some(boolean) = value.as_bool() {
            return boolean;
        }
        if let Some(integer) = value.as_integer() {
            return integer != 0;
        }
        if let Some(float) = value.as_float() {
            return float != 0.0;
        }
        if let Some(array) = value.as_array() {
            return !array.is_empty();
        }
    }
    if let Some(array) = item.as_array_of_tables() {
        return !array.is_empty();
    }
    if let Some(table) = item.as_table_like() {
        return table.iter().next().is_some();
    }
    true
}

fn python_string_or(item: Option<&Item>, default: &str) -> String {
    if !item_is_truthy(item) {
        return default.to_owned();
    }
    let Some(item) = item else {
        return default.to_owned();
    };
    if let Some(value) = item.as_value() {
        return toml_value_string(value);
    }
    item.to_string()
}

fn string_list(table: &dyn TableLike, field: &str) -> Result<Vec<String>, String> {
    let Some(item) = table.get(field) else {
        return Ok(Vec::new());
    };
    let Some(array) = item.as_array() else {
        return Err(format!("{field} must be a list of strings"));
    };
    array
        .iter()
        .map(|value| {
            value
                .as_str()
                .map(str::to_owned)
                .ok_or_else(|| format!("{field} must be a list of strings"))
        })
        .collect()
}

fn optional_count(table: &dyn TableLike, field: &str) -> Result<Option<i64>, String> {
    let Some(item) = table.get(field) else {
        return Ok(None);
    };
    let Some(value) = item.as_value().and_then(TomlValue::as_integer) else {
        return Err(format!("{field} must be a non-negative integer"));
    };
    if value < 0 {
        return Err(format!("{field} must be a non-negative integer"));
    }
    Ok(Some(value))
}

fn positive_count(table: &dyn TableLike, field: &str) -> Result<usize, String> {
    let Some(value) = table
        .get(field)
        .and_then(Item::as_value)
        .and_then(TomlValue::as_integer)
    else {
        return Err(format!("{field} must be a positive integer"));
    };
    if value <= 0 {
        return Err(format!("{field} must be a positive integer"));
    }
    usize::try_from(value).map_err(|_| format!("{field} must be a positive integer"))
}

fn format_string_spec(value: &str, spec: &str, group_id: &str) -> Result<String, String> {
    if spec.is_empty() {
        return Ok(value.to_owned());
    }
    let invalid = || format!("case group {group_id} has invalid prompt template");
    let characters = spec.chars().collect::<Vec<_>>();
    let mut index = 0;
    let mut fill = ' ';
    let mut alignment = '<';
    if characters.len() >= 2 && matches!(characters[1], '<' | '>' | '^') {
        fill = characters[0];
        alignment = characters[1];
        index = 2;
    } else if characters
        .first()
        .is_some_and(|character| matches!(character, '<' | '>' | '^'))
    {
        alignment = characters[0];
        index = 1;
    }
    if matches!(fill, '{' | '}') {
        return Err(invalid());
    }
    let width_start = index;
    while characters.get(index).is_some_and(|character| character.is_ascii_digit()) {
        index += 1;
    }
    let width = if width_start == index {
        0
    } else {
        characters[width_start..index]
            .iter()
            .collect::<String>()
            .parse::<usize>()
            .map_err(|_| invalid())?
    };
    let mut value = value.to_owned();
    if characters.get(index) == Some(&'.') {
        index += 1;
        let precision_start = index;
        while characters.get(index).is_some_and(|character| character.is_ascii_digit()) {
            index += 1;
        }
        if precision_start == index {
            return Err(invalid());
        }
        let precision = characters[precision_start..index]
            .iter()
            .collect::<String>()
            .parse::<usize>()
            .map_err(|_| invalid())?;
        value = value.chars().take(precision).collect();
    }
    if characters.get(index) == Some(&'s') {
        index += 1;
    }
    if index != characters.len() {
        return Err(invalid());
    }
    let padding = width.saturating_sub(value.chars().count());
    if padding == 0 {
        return Ok(value);
    }
    let fill = fill.to_string();
    let pad = |count: usize| fill.repeat(count);
    Ok(match alignment {
        '<' => format!("{value}{}", pad(padding)),
        '>' => format!("{}{value}", pad(padding)),
        '^' => {
            let before = padding / 2;
            let after = padding - before;
            format!("{}{value}{}", pad(before), pad(after))
        }
        _ => return Err(invalid()),
    })
}

fn format_group_prompt(template: &str, subject: &str, group_id: &str) -> Result<String, String> {
    let characters = template.chars().collect::<Vec<_>>();
    let mut prompt = String::new();
    let mut index = 0;
    while index < characters.len() {
        match characters[index] {
            '{' if characters.get(index + 1) == Some(&'{') => {
                prompt.push('{');
                index += 2;
            }
            '{' => {
                index += 1;
                let start = index;
                while index < characters.len() && characters[index] != '}' {
                    if characters[index] == '{' {
                        return Err(format!("case group {group_id} has invalid prompt template"));
                    }
                    index += 1;
                }
                if index == characters.len() {
                    return Err(format!("case group {group_id} has invalid prompt template"));
                }
                let field = characters[start..index].iter().collect::<String>();
                let field_name = field.split(['!', ':']).next().unwrap_or_default();
                if field_name != "subject" {
                    if field_name.is_empty()
                        || field_name.chars().all(|character| character.is_ascii_digit())
                    {
                        return Err(format!(
                            "case group {group_id} has invalid prompt template"
                        ));
                    }
                    return Err(format!(
                        "case group {group_id} template uses unsupported field {field_name:?}"
                    ));
                }
                let suffix = &field["subject".len()..];
                let (conversion, spec) = if let Some(after_marker) = suffix.strip_prefix('!') {
                    let conversion = after_marker.chars().next().ok_or_else(|| {
                        format!("case group {group_id} has invalid prompt template")
                    })?;
                    let rest = &after_marker[conversion.len_utf8()..];
                    if let Some(spec) = rest.strip_prefix(':') {
                        (conversion, spec)
                    } else if rest.is_empty() {
                        (conversion, "")
                    } else {
                        return Err(format!(
                            "case group {group_id} has invalid prompt template"
                        ));
                    }
                } else if let Some(spec) = suffix.strip_prefix(':') {
                    ('s', spec)
                } else if suffix.is_empty() {
                    ('s', "")
                } else {
                    return Err(format!(
                        "case group {group_id} has invalid prompt template"
                    ));
                };
                let converted = match conversion {
                    's' => subject.to_owned(),
                    'r' => python_repr_string(subject),
                    'a' => python_ascii_repr_string(subject),
                    _ => {
                        return Err(format!(
                            "case group {group_id} has invalid prompt template"
                        ));
                    }
                };
                prompt.push_str(&format_string_spec(&converted, spec, group_id)?);
                index += 1;
            }
            '}' if characters.get(index + 1) == Some(&'}') => {
                prompt.push('}');
                index += 2;
            }
            '}' => {
                return Err(format!("case group {group_id} has invalid prompt template"));
            }
            character => {
                prompt.push(character);
                index += 1;
            }
        }
    }
    let prompt = python_strip(&prompt);
    if prompt.is_empty() {
        return Err(format!("case group {group_id} generated an empty prompt"));
    }
    Ok(prompt)
}

fn load_explicit_cases(
    raw_cases: Option<&Item>,
    seen_ids: &mut HashSet<String>,
) -> Result<Vec<WorkflowSelectionCase>, String> {
    let mut cases = Vec::new();
    for (index, entry) in table_entries(raw_cases, "cases")?.into_iter().enumerate() {
        let case_id = python_strip(&python_string_or(entry.get("id"), ""));
        if case_id.is_empty() {
            return Err(format!("case {} must define id", index + 1));
        }
        if !seen_ids.insert(case_id.clone()) {
            return Err(format!("duplicate case id: {case_id}"));
        }
        let prompt = python_strip(&python_string_or(entry.get("prompt"), ""));
        if prompt.is_empty() {
            return Err(format!("case {case_id} must define prompt"));
        }
        let expected_workflows = string_list(entry, "expected_workflows")
            .map_err(|_| format!("{case_id}.expected_workflows must be a list of strings"))?;
        if expected_workflows.is_empty() {
            return Err(format!("case {case_id} must define expected_workflows"));
        }
        cases.push(WorkflowSelectionCase {
            case_id,
            group_id: python_string_or(entry.get("group_id"), "explicit"),
            description: python_string_or(entry.get("description"), ""),
            prompt,
            expected_workflows,
            forbidden_workflows: string_list(entry, "forbidden_workflows")
                .map_err(|_| format!("{case_id}.forbidden_workflows must be a list of strings"))?,
            expected_skills: string_list(entry, "expected_skills")
                .map_err(|_| format!("{case_id}.expected_skills must be a list of strings"))?,
            expected_tools: string_list(entry, "expected_tools")
                .map_err(|_| format!("{case_id}.expected_tools must be a list of strings"))?,
        });
    }
    Ok(cases)
}

fn load_case_groups(
    raw_groups: Option<&Item>,
    seen_ids: &mut HashSet<String>,
) -> Result<(Vec<WorkflowSelectionCase>, usize), String> {
    let mut cases = Vec::new();
    let mut generated_count = 0;
    for (index, entry) in table_entries(raw_groups, "case_groups")?.into_iter().enumerate() {
        let group_id = python_strip(&python_string_or(entry.get("id"), ""));
        if group_id.is_empty() {
            return Err(format!("case group {} must define id", index + 1));
        }
        let templates = string_list(entry, "prompt_templates")
            .map_err(|_| format!("{group_id}.prompt_templates must be a list of strings"))?;
        let subjects = string_list(entry, "subjects")
            .map_err(|_| format!("{group_id}.subjects must be a list of strings"))?;
        if templates.is_empty() {
            return Err(format!("case group {group_id} must define prompt_templates"));
        }
        if subjects.is_empty() {
            return Err(format!("case group {group_id} must define subjects"));
        }
        let expected_workflows = string_list(entry, "expected_workflows")
            .map_err(|_| format!("{group_id}.expected_workflows must be a list of strings"))?;
        if expected_workflows.is_empty() {
            return Err(format!(
                "case group {group_id} must define expected_workflows"
            ));
        }
        let available = templates
            .len()
            .checked_mul(subjects.len())
            .ok_or_else(|| format!("case group {group_id} has too many prompt combinations"))?;
        let limit = match entry.get("limit") {
            Some(_) => positive_count(entry, "limit")?,
            None => available,
        };
        if available < limit {
            return Err(format!(
                "case group {group_id} has {available} prompt combinations but limit={limit}"
            ));
        }
        let description = python_string_or(entry.get("description"), "");
        let forbidden_workflows = string_list(entry, "forbidden_workflows")
            .map_err(|_| format!("{group_id}.forbidden_workflows must be a list of strings"))?;
        let expected_skills = string_list(entry, "expected_skills")
            .map_err(|_| format!("{group_id}.expected_skills must be a list of strings"))?;
        let expected_tools = string_list(entry, "expected_tools")
            .map_err(|_| format!("{group_id}.expected_tools must be a list of strings"))?;
        let mut group_count = 0;
        for subject in &subjects {
            for template in &templates {
                if group_count >= limit {
                    break;
                }
                group_count += 1;
                let case_id = format!("{group_id}-{group_count:03}");
                if !seen_ids.insert(case_id.clone()) {
                    return Err(format!("duplicate case id: {case_id}"));
                }
                cases.push(WorkflowSelectionCase {
                    case_id,
                    group_id: group_id.clone(),
                    description: description.clone(),
                    prompt: format_group_prompt(template, subject, &group_id)?,
                    expected_workflows: expected_workflows.clone(),
                    forbidden_workflows: forbidden_workflows.clone(),
                    expected_skills: expected_skills.clone(),
                    expected_tools: expected_tools.clone(),
                });
            }
            if group_count >= limit {
                break;
            }
        }
        generated_count += group_count;
    }
    Ok((cases, generated_count))
}

fn load_manifest(path: &Path) -> Result<WorkflowSelectionManifest, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("cannot read manifest {}: {error}", path.display()))?;
    let document = text
        .parse::<DocumentMut>()
        .map_err(|error| format!("cannot parse manifest {}: {error}", path.display()))?;
    let root = document.as_table();
    let mut seen_ids = HashSet::new();
    let mut cases = load_explicit_cases(root.get("cases"), &mut seen_ids)?;
    let (generated_cases, generated_case_count) =
        load_case_groups(root.get("case_groups"), &mut seen_ids)?;
    cases.extend(generated_cases);
    if cases.is_empty() {
        return Err("manifest must define at least one [[cases]] or [[case_groups]] entry".to_owned());
    }
    let expected_case_count = optional_count(root, "expected_case_count")?;
    let expected_generated_case_count =
        optional_count(root, "expected_generated_case_count")?;
    let mut count_failures = Vec::new();
    if let Some(expected) = expected_case_count {
        if expected != cases.len() as i64 {
            count_failures.push(format!(
                "expected_case_count={expected} observed={}",
                cases.len()
            ));
        }
    }
    if let Some(expected) = expected_generated_case_count {
        if expected != generated_case_count as i64 {
            count_failures.push(format!(
                "expected_generated_case_count={expected} observed={generated_case_count}"
            ));
        }
    }
    Ok(WorkflowSelectionManifest {
        cases,
        expected_case_count,
        expected_generated_case_count,
        generated_case_count,
        count_failures,
    })
}

/// Serialize the existing manifest loader result for the internal skill-shim bridge.
pub fn manifest_json(path: &Path) -> Result<serde_json::Value, String> {
    let manifest = load_manifest(path)?;
    let cases = manifest
        .cases
        .iter()
        .map(|case| {
            serde_json::json!({
                "case_id": &case.case_id,
                "group_id": &case.group_id,
                "description": &case.description,
                "prompt": &case.prompt,
                "expected_workflows": &case.expected_workflows,
                "forbidden_workflows": &case.forbidden_workflows,
                "expected_skills": &case.expected_skills,
                "expected_tools": &case.expected_tools,
            })
        })
        .collect::<Vec<_>>();
    Ok(serde_json::json!({
        "cases": cases,
        "expected_case_count": manifest.expected_case_count,
        "expected_generated_case_count": manifest.expected_generated_case_count,
        "generated_case_count": manifest.generated_case_count,
        "count_failures": &manifest.count_failures,
    }))
}

fn deduplicate(values: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut seen = HashSet::new();
    values
        .into_iter()
        .filter(|value| seen.insert(value.clone()))
        .collect()
}

fn json_strings(values: Vec<JsonString>) -> Vec<String> {
    values
        .into_iter()
        .map(|value| value.to_text().unwrap_or_default())
        .collect()
}

fn evaluate_case(root: &Path, case: &WorkflowSelectionCase) -> WorkflowSelectionResult {
    let prompt = JsonString::from_text(&case.prompt);
    let lane_evidence = structural_skill_lane_concept_matches(&prompt)
        .into_iter()
        .map(|matched| SkillLaneEvidence {
            schema: JsonString::from_text("agent-canon.skill-lane.v1"),
            lane: matched.concept.name,
            route_skills: matched.concept.route_skills,
            evidence_categories: matched.observed_evidence_categories,
            status: JsonString::from_text("observed"),
            source: JsonString::from_text("prompt_classifier"),
        })
        .collect::<Vec<_>>();
    let validation_evidence = validation_failure_repair_concept_matches(&prompt)
        .into_iter()
        .map(|matched| JsonString::from_text(&matched.reason()))
        .collect::<Vec<_>>();
    let empty_object = JsonValue::Object(JsonObject(Vec::new()));
    let signals = prompt_intake_signals(&PromptClassifierInputs {
        prompt: &prompt,
        repo_root: root,
        catalog: &empty_object,
        routing_rules: &empty_object,
        structural_lane_evidence: &lane_evidence,
        validation_repair_evidence: &validation_evidence,
    });
    let selected_workflows = json_strings(signals.selected_workflows);
    let candidate_workflows = json_strings(signals.candidate_workflows);
    let observed_workflows = deduplicate(
        selected_workflows
            .iter()
            .chain(&candidate_workflows)
            .cloned(),
    );
    let selected_skills = json_strings(signals.skills);
    let candidate_skills = json_strings(signals.candidate_skills);
    let observed_skills = deduplicate(
        selected_skills.iter().chain(&candidate_skills).cloned(),
    );
    let observed_tools = json_strings(signals.candidate_tools);
    WorkflowSelectionResult {
        case: case.clone(),
        missing_workflows: case
            .expected_workflows
            .iter()
            .filter(|workflow| !observed_workflows.contains(workflow))
            .cloned()
            .collect(),
        forbidden_workflows_seen: case
            .forbidden_workflows
            .iter()
            .filter(|workflow| observed_workflows.contains(workflow))
            .cloned()
            .collect(),
        missing_skills: case
            .expected_skills
            .iter()
            .filter(|skill| !observed_skills.contains(skill))
            .cloned()
            .collect(),
        missing_tools: case
            .expected_tools
            .iter()
            .filter(|tool| !observed_tools.contains(tool))
            .cloned()
            .collect(),
        observed_workflows,
        selected_skills,
        candidate_skills,
        observed_tools,
    }
}

fn python_repr_string(value: &str) -> String {
    python_repr_string_with_ascii(value, false)
}

fn python_ascii_repr_string(value: &str) -> String {
    python_repr_string_with_ascii(value, true)
}

fn python_repr_string_with_ascii(value: &str, ascii_only: bool) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut output = String::with_capacity(value.len() + 2);
    output.push(quote);
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
            character if character.is_control() => {
                let code = character as u32;
                if code <= 0xff {
                    output.push_str(&format!("\\x{code:02x}"));
                } else if code <= 0xffff {
                    output.push_str(&format!("\\u{code:04x}"));
                } else {
                    output.push_str(&format!("\\U{code:08x}"));
                }
            }
            character if ascii_only && !character.is_ascii() => {
                let code = character as u32;
                if code <= 0xff {
                    output.push_str(&format!("\\x{code:02x}"));
                } else if code <= 0xffff {
                    output.push_str(&format!("\\u{code:04x}"));
                } else {
                    output.push_str(&format!("\\U{code:08x}"));
                }
            }
            character => output.push(character),
        }
    }
    output.push(quote);
    output
}

fn python_tuple_repr(values: &[String]) -> String {
    let values = values
        .iter()
        .map(|value| python_repr_string(value))
        .collect::<Vec<_>>();
    match values.as_slice() {
        [] => "()".to_owned(),
        [value] => format!("({value},)"),
        _ => format!("({})", values.join(", ")),
    }
}

fn timestamp_id() -> String {
    let now = OffsetDateTime::now_utc();
    format!(
        "{:04}{:02}{:02}T{:02}{:02}{:02}{:06}Z",
        now.year(),
        u8::from(now.month()),
        now.day(),
        now.hour(),
        now.minute(),
        now.second(),
        now.microsecond()
    )
}

fn run_id_for(
    manifest: &Path,
    results: &[WorkflowSelectionResult],
    requested_run_id: &str,
) -> String {
    let timestamp = timestamp_id();
    let mut digest_lines = vec![path_as_posix(manifest), requested_run_id.to_owned()];
    digest_lines.extend(results.iter().map(|result| {
        format!(
            "{}:{}:{}",
            result.case.case_id,
            if result.passed() { "True" } else { "False" },
            python_tuple_repr(&result.observed_workflows)
        )
    }));
    digest_lines.extend(results.iter().map(|result| {
        format!(
            "{}:selected:{}",
            result.case.case_id,
            python_tuple_repr(&result.selected_skills)
        )
    }));
    digest_lines.extend(results.iter().map(|result| {
        format!(
            "{}:candidate:{}",
            result.case.case_id,
            python_tuple_repr(&result.candidate_skills)
        )
    }));
    digest_lines.extend(results.iter().map(|result| {
        format!(
            "{}:tools:{}",
            result.case.case_id,
            python_tuple_repr(&result.observed_tools)
        )
    }));
    digest_lines.push(timestamp.clone());
    let digest_source = digest_lines.join("\n");
    let digest = format!("{:x}", Sha256::digest(digest_source.as_bytes()));
    format!(
        "workflow-selection-eval-{timestamp}-{}",
        &digest[..RUN_ID_DIGEST_LENGTH]
    )
}

fn evaluate(
    root: &Path,
    manifest_path: &Path,
    requested_run_id: &str,
) -> Result<WorkflowSelectionBundle, String> {
    let root = crate::path_resolution::resolve_non_strict(root)?;
    let manifest = resolve_eval_manifest(&root, manifest_path);
    let manifest = crate::path_resolution::resolve_non_strict(&manifest)?;
    let loaded = load_manifest(&manifest)?;
    let results = loaded
        .cases
        .iter()
        .map(|case| evaluate_case(&root, case))
        .collect::<Vec<_>>();
    let status = if results.iter().all(WorkflowSelectionResult::passed)
        && loaded.count_failures.is_empty()
    {
        "pass"
    } else {
        "fail"
    };
    let run_id = run_id_for(&manifest, &results, requested_run_id);
    Ok(WorkflowSelectionBundle {
        run_id,
        requested_run_id: requested_run_id.to_owned(),
        status,
        root,
        manifest,
        results,
        expected_case_count: loaded.expected_case_count,
        expected_generated_case_count: loaded.expected_generated_case_count,
        generated_case_count: loaded.generated_case_count,
        count_failures: loaded.count_failures,
    })
}

fn comma(values: &[String]) -> String {
    if values.is_empty() {
        format!("{MARKDOWN_TICK}none{MARKDOWN_TICK}")
    } else {
        values
            .iter()
            .map(|value| format!("{MARKDOWN_TICK}{value}{MARKDOWN_TICK}"))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

fn display_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .map(path_as_posix)
        .unwrap_or_else(|_| path_as_posix(path))
}

fn path_as_posix(path: &Path) -> String {
    let value = path.to_string_lossy();
    #[cfg(windows)]
    {
        value.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        value.into_owned()
    }
}

fn render_report(bundle: &WorkflowSelectionBundle) -> String {
    let count_failures = if bundle.count_failures.is_empty() {
        "none".to_owned()
    } else {
        bundle.count_failures.join("; ")
    };
    let mut lines = vec![
        "# Workflow Selection Eval".to_owned(),
        String::new(),
        "<!--".to_owned(),
        "@dependency-start".to_owned(),
        "responsibility Records one workflow selection eval run.".to_owned(),
        "upstream implementation ../../../../tools/runtime/dispatch/agent-canon/src/workflow_selection_eval.rs generates this report".to_owned(),
        "@dependency-end".to_owned(),
        "-->".to_owned(),
        String::new(),
        format!("WORKFLOW_SELECTION_EVAL_RUN_ID={}", bundle.run_id),
        format!(
            "WORKFLOW_SELECTION_EVAL_SOURCE_RUN_ID={}",
            if bundle.requested_run_id.is_empty() {
                "none"
            } else {
                &bundle.requested_run_id
            }
        ),
        format!("WORKFLOW_SELECTION_EVAL_STATUS={}", bundle.status),
        format!("WORKFLOW_SELECTION_EVAL_CASES={}", bundle.results.len()),
        format!(
            "WORKFLOW_SELECTION_EVAL_EXPECTED_CASES={}",
            bundle
                .expected_case_count
                .map(|value| value.to_string())
                .unwrap_or_else(|| "none".to_owned())
        ),
        format!(
            "WORKFLOW_SELECTION_EVAL_GENERATED_CASES={}",
            bundle.generated_case_count
        ),
        format!(
            "WORKFLOW_SELECTION_EVAL_EXPECTED_GENERATED_CASES={}",
            bundle
                .expected_generated_case_count
                .map(|value| value.to_string())
                .unwrap_or_else(|| "none".to_owned())
        ),
        format!("WORKFLOW_SELECTION_EVAL_COUNT_FAILURES={count_failures}"),
        format!("WORKFLOW_SELECTION_EVAL_FAILED={}", bundle.failed_count()),
        format!(
            "manifest: {}{}{}",
            MARKDOWN_TICK,
            display_path(&bundle.root, &bundle.manifest),
            MARKDOWN_TICK
        ),
        String::new(),
        "| group | case | status | expected workflows | observed workflows | selected skills | candidate skills | expected tools | observed tools | missing workflows | forbidden workflows | missing skills | missing tools |".to_owned(),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |".to_owned(),
    ];
    for result in &bundle.results {
        let fields = [
            format!("{}{}{}", MARKDOWN_TICK, result.case.group_id, MARKDOWN_TICK),
            format!("{}{}{}", MARKDOWN_TICK, result.case.case_id, MARKDOWN_TICK),
            if result.passed() {
                format!("{MARKDOWN_TICK}pass{MARKDOWN_TICK}")
            } else {
                format!("{MARKDOWN_TICK}fail{MARKDOWN_TICK}")
            },
            comma(&result.case.expected_workflows),
            comma(&result.observed_workflows),
            comma(&result.selected_skills),
            comma(&result.candidate_skills),
            comma(&result.case.expected_tools),
            comma(&result.observed_tools),
            comma(&result.missing_workflows),
            comma(&result.forbidden_workflows_seen),
            comma(&result.missing_skills),
            comma(&result.missing_tools),
        ];
        lines.push(format!("| {} |", fields.join(" | ")));
    }
    lines.join("\n") + "\n"
}

fn report_path_with_run_id(path: &Path, run_id: &str) -> Result<PathBuf, String> {
    let file_name = path
        .file_name()
        .ok_or_else(|| format!("report output path has no file name: {}", path.display()))?;
    let stem = path.file_stem().unwrap_or(file_name).to_string_lossy();
    let suffix = path
        .extension()
        .map(|extension| format!(".{}", extension.to_string_lossy()))
        .unwrap_or_default();
    Ok(path.with_file_name(format!("{stem}-{run_id}{suffix}")))
}

fn write_report(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    bundle: &WorkflowSelectionBundle,
) -> Result<PathBuf, RunFailure> {
    let output_path = if path.exists() {
        report_path_with_run_id(path, &bundle.run_id).map_err(RunFailure::Evaluation)?
    } else {
        path.to_path_buf()
    };
    boundary
        .atomic_write_text(&output_path, &render_report(bundle), 0o600)
        .map_err(RunFailure::Runtime)
}

fn resolve_results_dir(
    bundle: &WorkflowSelectionBundle,
    value: &str,
    boundary: &RuntimeArtifactBoundary,
) -> Result<PathBuf, String> {
    let value = python_strip(value);
    if !value.is_empty() {
        let path = PathBuf::from(value);
        if path.is_absolute() {
            return Ok(path);
        }
        return boundary.resolve(&path);
    }
    eval_results_dir(
        &bundle.root,
        DEFAULT_RESULTS_FAMILY,
        Some(boundary.root()),
    )
}

fn build_report_paths(
    bundle: &WorkflowSelectionBundle,
    options: &CliOptions,
) -> Result<Vec<PathBuf>, RunFailure> {
    if options.report_out.is_none() && !options.accumulate {
        return Ok(Vec::new());
    }
    let boundary = RuntimeArtifactBoundary::for_source(
        &bundle.root,
        options.runtime_root.as_deref(),
        false,
    )
    .map_err(RunFailure::Runtime)?;
    let mut paths = Vec::new();
    if let Some(path) = options.report_out.as_deref() {
        paths.push(write_report(&boundary, path, bundle)?);
    }
    if options.accumulate {
        let results_dir = resolve_results_dir(bundle, &options.results_dir, &boundary)
            .map_err(RunFailure::Runtime)?;
        let report_path = results_dir.join(format!("{}-{}.md", bundle.run_id, bundle.status));
        paths.push(write_report(&boundary, &report_path, bundle)?);
    }
    Ok(paths)
}

fn execute(options: &CliOptions) -> Result<(WorkflowSelectionBundle, Vec<PathBuf>), RunFailure> {
    let root = crate::path_resolution::resolve_non_strict(&options.root)
        .map_err(RunFailure::Evaluation)?;
    let bundle =
        evaluate(&root, &options.manifest, &options.run_id).map_err(RunFailure::Evaluation)?;
    let paths = build_report_paths(&bundle, options)?;
    Ok((bundle, paths))
}

fn print_usage_error(error: &str) {
    eprintln!("{USAGE}");
    eprintln!("agent-canon evaluate-workflow-selection: error: {error}");
}

fn print_help() {
    println!(
        "Evaluate workflow selection routing against frozen prompt cases.\n\n{USAGE}\n\nOptions:\n  -h, --help\n  --root ROOT\n  --runtime-root RUNTIME_ROOT\n  --manifest MANIFEST\n  --report-out REPORT_OUT\n  --accumulate\n  --run-id RUN_ID\n  --results-dir RESULTS_DIR"
    );
}

fn parse_arguments(args: &[String]) -> Result<Option<CliOptions>, String> {
    let mut root = env::current_dir().map_err(|error| format!("current directory: {error}"))?;
    let mut runtime_root = None;
    let mut manifest = eval_manifest_path("workflow_selection_eval.toml");
    let mut report_out = None;
    let mut accumulate = false;
    let mut run_id = String::new();
    let mut results_dir = String::new();
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if token == "-h" || token == "--help" {
            return Ok(None);
        }
        if !token.starts_with("--") {
            return Err(format!("unrecognized argument: {token}"));
        }
        let (option_text, inline_value) = match token.split_once('=') {
            Some((option, value)) => (option, Some(value.to_owned())),
            None => (token.as_str(), None),
        };
        let option = resolve_long_option_prefix(option_text, CLI_OPTIONS).map_err(|error| {
            match error {
                LongOptionError::Unrecognized => format!("unrecognized argument: {token}"),
                LongOptionError::Ambiguous(_) => format!("ambiguous option: {option_text}"),
            }
        })?;
        if matches!(option, CliOption::Help) {
            if inline_value.is_some() {
                return Err(format!("ignored explicit argument for --help: {token}"));
            }
            return Ok(None);
        }
        if matches!(option, CliOption::Accumulate) {
            if inline_value.is_some() {
                return Err(format!("ignored explicit argument for --accumulate: {token}"));
            }
            accumulate = true;
            index += 1;
            continue;
        }
        let value = if let Some(value) = inline_value {
            value
        } else {
            index += 1;
            let Some(value) = args.get(index) else {
                return Err(format!("argument {option_text}: expected one argument"));
            };
            if value.starts_with('-') && !is_argparse_negative_number(value) {
                return Err(format!("argument {option_text}: expected one argument"));
            }
            value.clone()
        };
        match option {
            CliOption::Root => root = PathBuf::from(value),
            CliOption::RuntimeRoot => runtime_root = Some(PathBuf::from(value)),
            CliOption::Manifest => manifest = PathBuf::from(value),
            CliOption::ReportOut => {
                report_out = (!value.is_empty()).then(|| PathBuf::from(value));
            }
            CliOption::RunId => run_id = value,
            CliOption::ResultsDir => results_dir = value,
            CliOption::Help | CliOption::Accumulate => unreachable!(),
        }
        index += 1;
    }
    Ok(Some(CliOptions {
        root,
        runtime_root,
        manifest,
        report_out,
        accumulate,
        run_id,
        results_dir,
    }))
}

fn emit_bundle(bundle: &WorkflowSelectionBundle, report_paths: &[PathBuf]) {
    println!("WORKFLOW_SELECTION_EVAL_RUN_ID={}", bundle.run_id);
    println!(
        "WORKFLOW_SELECTION_EVAL_SOURCE_RUN_ID={}",
        if bundle.requested_run_id.is_empty() {
            "none"
        } else {
            &bundle.requested_run_id
        }
    );
    println!("WORKFLOW_SELECTION_EVAL_CASES={}", bundle.results.len());
    println!(
        "WORKFLOW_SELECTION_EVAL_EXPECTED_CASES={}",
        bundle
            .expected_case_count
            .map(|value| value.to_string())
            .unwrap_or_else(|| "none".to_owned())
    );
    println!(
        "WORKFLOW_SELECTION_EVAL_GENERATED_CASES={}",
        bundle.generated_case_count
    );
    println!(
        "WORKFLOW_SELECTION_EVAL_EXPECTED_GENERATED_CASES={}",
        bundle
            .expected_generated_case_count
            .map(|value| value.to_string())
            .unwrap_or_else(|| "none".to_owned())
    );
    println!(
        "WORKFLOW_SELECTION_EVAL_COUNT_FAILURES={}",
        if bundle.count_failures.is_empty() {
            "none".to_owned()
        } else {
            bundle.count_failures.join("; ")
        }
    );
    println!("WORKFLOW_SELECTION_EVAL_FAILED={}", bundle.failed_count());
    for path in report_paths {
        println!("WORKFLOW_SELECTION_EVAL_REPORT={}", path.display());
    }
    println!("WORKFLOW_SELECTION_EVAL_STATUS={}", bundle.status);
}

/// Evaluate workflow-selection cases with the canonical native classifier.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_arguments(args) {
        Ok(Some(options)) => options,
        Ok(None) => {
            print_help();
            return 0;
        }
        Err(error) => {
            print_usage_error(&error);
            return 2;
        }
    };
    match execute(&options) {
        Ok((bundle, report_paths)) => {
            emit_bundle(&bundle, &report_paths);
            if bundle.status == "pass" { 0 } else { 1 }
        }
        Err(RunFailure::Evaluation(error)) => {
            eprintln!("{error}");
            1
        }
        Err(RunFailure::Runtime(error)) => {
            eprintln!("agent-canon evaluate-workflow-selection: runtime_root_required: {error}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{load_manifest, WorkflowSelectionManifest};
    use std::collections::HashSet;
    use std::path::PathBuf;

    fn canonical_manifest() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(4)
            .expect("native crate is nested below the repository root")
            .join("eval/definitions/workflow_selection_eval.toml")
    }

    fn load_canonical() -> WorkflowSelectionManifest {
        load_manifest(&canonical_manifest()).expect("canonical workflow manifest reads")
    }

    #[test]
    fn current_manifest_expands_all_expected_workflow_groups() {
        let manifest = load_canonical();
        let expected_groups = [
            "routing-advisory",
            "scoped-lite-code",
            "scoped-change-behavior",
            "validation-failure-cause-analysis",
            "docs-structure",
            "markdown-style",
            "large-refactor",
            "platform-environment",
            "research-benchmark",
            "adaptive-loop",
            "computational-optimization",
            "experiment-html-report",
            "tool-finding-report",
            "agent-log-analysis",
            "agent-canon-update",
            "pr-processing",
            "repo-structure-drift",
            "academic-paper",
            "oop-readability",
            "user-guided-debugging",
            "run-report-archive",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect::<HashSet<_>>();
        assert_eq!(manifest.cases.len(), 525);
        assert_eq!(manifest.generated_case_count, 525);
        assert_eq!(manifest.expected_case_count, Some(525));
        assert_eq!(manifest.expected_generated_case_count, Some(525));
        assert!(manifest.count_failures.is_empty());
        assert_eq!(
            manifest
                .cases
                .iter()
                .map(|case| case.group_id.clone())
                .collect::<HashSet<_>>(),
            expected_groups
        );
        for group_id in &expected_groups {
            assert_eq!(
                manifest
                    .cases
                    .iter()
                    .filter(|case| case.group_id.as_str() == group_id.as_str())
                    .count(),
                25,
                "{group_id}"
            );
        }
        let docs_cases = manifest
            .cases
            .iter()
            .filter(|case| case.group_id == "docs-structure")
            .collect::<Vec<_>>();
        let large_cases = manifest
            .cases
            .iter()
            .filter(|case| case.group_id == "large-refactor")
            .collect::<Vec<_>>();
        let validation_cases = manifest
            .cases
            .iter()
            .filter(|case| case.group_id == "validation-failure-cause-analysis")
            .collect::<Vec<_>>();
        assert!(docs_cases.iter().all(|case| {
            ["structure-planning", "prose-reasoning-graph"]
                .iter()
                .all(|required| {
                    case.expected_skills
                        .iter()
                        .any(|skill| skill.as_str() == *required)
                })
        }));
        assert!(large_cases
            .iter()
            .all(|case| {
                case.expected_skills.len() == 1
                    && case.expected_skills[0] == "refactor-loop"
            }));
        assert!(validation_cases
            .iter()
            .all(|case| {
                case.expected_skills
                    .iter()
                    .any(|skill| skill == "codex-task-workflow")
            }));
        assert!(validation_cases.iter().all(|case| {
            !case
                .expected_skills
                .iter()
                .any(|skill| skill == "test-design")
        }));
    }
}
