// @dependency-start
// contract implementation
// responsibility Owns native run-bundle evaluation, fixed scoring, feedback rendering, and its public CLI.
// upstream design ../../../../../eval/definitions/agent_behavior_eval.toml declares behavior checks
// upstream design ../../../../../templates/agents/agent_evaluation.md defines evaluation artifact shape
// upstream design ../../../../../templates/agents/workflow_monitoring.md defines monitoring evidence
// upstream implementation eval_manifest_paths.rs resolves canonical and legacy Eval manifests
// upstream implementation report_artifact_checks.rs owns pure report artifact checks
// upstream implementation runtime_boundary.rs owns the external output capability
// downstream implementation ../../../../../tools/catalog.yaml registers the native CLI route
// downstream test ../tests/run_evaluation_native.rs verifies native scoring and CLI behavior
// @dependency-end

use crate::eval_manifest_paths::{eval_manifest_path, resolve_eval_manifest};
use crate::report_artifact_checks::{
    check_final_review_artifact, check_schedule_artifact, check_work_log_artifact,
    has_approve_decision, markdown_without_adjudicated_rejected_hypotheses, section_has_content,
};
use crate::runtime_boundary::{RuntimeArtifactBoundary, RuntimeDirectory, RUNTIME_ROOT_ENV};
use regex::Regex;
use serde_json::Value as JsonValue;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fmt;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::OnceLock;
use toml_edit::{DocumentMut, Item, TableLike};
use yaml_rust2::{Yaml, YamlLoader};

pub const DEFAULT_MIN_SCORE: i64 = 85;
pub const DEFAULT_BEHAVIOR_CRITERION_MAX_SCORE: i64 = 5;
pub const ARTIFACT_COMPLETENESS_SCORE: i64 = 8;
pub const REQUEST_TRACEABILITY_SCORE: i64 = 10;
pub const PLANNED_WORK_AND_CHRONOLOGY_SCORE: i64 = 10;
pub const WORKFLOW_MONITORING_SCORE: i64 = 12;
pub const TOOL_WARNING_OBLIGATION_SCORE: i64 = 8;
pub const ORCHESTRATION_INTAKE_SCORE: i64 = 12;
pub const REVIEW_FEEDBACK_LOOP_SCORE: i64 = 10;
pub const VALIDATION_AND_CLOSEOUT_SCORE: i64 = 12;
pub const DEPENDENCY_AND_CANONICAL_SCORE: i64 = 10;
pub const SELF_IMPROVEMENT_FEEDBACK_SCORE: i64 = 16;
pub const SELF_IMPROVEMENT_FEEDBACK_PARTIAL_SCORE: i64 = 8;
pub const CHILD_EXECUTION_RECEIPT_SCHEMA: &str = "agent-canon.child-execution-receipts.v1";
pub const VALIDATION_FAILURE_FORBIDDEN_TOKENS: &[&str] = &[
    "oracle_weakening=",
    "oracle_deleted=",
    "test_deleted=",
    "behavior_simplified=",
    "validation_downscope=",
];
const DEFAULT_BEHAVIOR_MANIFEST: &str = "eval/definitions/agent_behavior_eval.toml";
const BEHAVIOR_INVENTORY_RELATIVE_PATH: &str =
    "documents/runtime/runtime-profiles-and-check-matrix.json";
const MANIFEST_NAME: &str = "team_manifest.yaml";
const SCHEDULE_NAME: &str = "schedule.md";
const WORK_LOG_NAME: &str = "work_log.md";
const CLOSEOUT_GATE_NAME: &str = "closeout_gate.md";
const REQUEST_CONTRACT_NAME: &str = "user_request_contract.md";
const MONITORING_NAME: &str = "workflow_monitoring.md";
const RETROSPECTIVE_NAME: &str = "retrospective.md";
const FINAL_REVIEW_NAME: &str = "final_review.md";
const CHANGE_REVIEW_NAME: &str = "change_review.md";
const VERIFICATION_NAME: &str = "verification.txt";
const SELF_IMPROVEMENT_PARTIAL_SCORE: i64 = SELF_IMPROVEMENT_FEEDBACK_PARTIAL_SCORE;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunEvaluationError {
    pub message: String,
}

impl RunEvaluationError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for RunEvaluationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}
impl std::error::Error for RunEvaluationError {}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ArtifactName(String);

impl ArtifactName {
    pub fn parse(value: &str) -> Result<Self, SelectionProblem> {
        if value.is_empty()
            || value.trim() != value
            || value.contains('\0')
            || value.contains('\\')
            || value.ends_with('/')
            || value
                .split('/')
                .any(|part| part.is_empty() || part == "." || part == "..")
            || Path::new(value).is_absolute()
            || Path::new(value)
                .components()
                .any(|component| !matches!(component, Component::Normal(_)))
        {
            return Err(SelectionProblem::new(format!(
                "unsafe_artifact_path:{value}"
            )));
        }
        Ok(Self(value.to_string()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SelectionProblem {
    pub detail: String,
}

impl SelectionProblem {
    fn new(detail: impl Into<String>) -> Self {
        Self {
            detail: detail.into(),
        }
    }
}

impl fmt::Display for SelectionProblem {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.detail)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ArtifactSelection {
    Known(BTreeSet<ArtifactName>),
    Unknown(SelectionProblem),
}

impl ArtifactSelection {
    fn contains(&self, name: &ArtifactName) -> bool {
        match self {
            Self::Known(values) => values.contains(name),
            Self::Unknown(_) => false,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ArtifactState {
    Unselected,
    SelectedPresent(String),
    SelectedMissing,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlannedWorkEvidence {
    pub schedule: ArtifactState,
    pub work_log: ArtifactState,
    pub schedule_findings: Vec<String>,
    pub work_log_findings: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CriterionResult {
    pub name: String,
    pub score: i64,
    pub max_score: i64,
    pub status: String,
    pub feedback: String,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum BehaviorSource {
    BehaviorEvents,
    Bundle,
    RuntimeProfileProjectionGate,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BehaviorCriterion {
    pub name: String,
    pub max_score: i64,
    pub feedback: String,
    pub source: BehaviorSource,
    pub required_all: Vec<String>,
    pub required_any: Vec<String>,
    pub forbidden_any: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunIdentity {
    pub task: Option<String>,
    pub workflow_family: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunEvidence {
    pub report_dir: PathBuf,
    pub selection: ArtifactSelection,
    pub materialized_artifacts: BTreeSet<ArtifactName>,
    pub run_identity: RunIdentity,
    pub missing_artifacts: Vec<String>,
    pub planned_work: PlannedWorkEvidence,
    pub request_contract: BTreeMap<String, String>,
    pub verification: BTreeMap<String, String>,
    pub closeout: BTreeMap<String, String>,
    pub monitoring_text: String,
    pub monitoring_status: BTreeMap<String, String>,
    pub retrospective_text: String,
    pub final_decision: String,
    pub change_review_text: String,
    pub final_review_text: String,
    pub normalized_bundle: String,
    pub signals_text: String,
    pub behavior_events_text: String,
    pub behavior_events_raw_text: String,
    pub tool_warnings_text: String,
    pub child_execution_receipts_valid: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvaluationReport {
    pub criteria: Vec<CriterionResult>,
    pub blockers: Vec<String>,
    pub score: i64,
    pub max_score: i64,
    pub status: String,
    pub threshold: i64,
    pub markdown: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ValidationFailureTaxonomy {
    cause_classes: BTreeSet<String>,
    intent_preservation: BTreeSet<String>,
    implementation_bug: String,
    repair_same_intent: String,
    design_conflict: String,
    escalate_design_conflict: String,
    residual_checker_causes: BTreeSet<String>,
}

impl ValidationFailureTaxonomy {
    fn load(source_root: &Path) -> Result<Self, RunEvaluationError> {
        let path = source_root.join(BEHAVIOR_INVENTORY_RELATIVE_PATH);
        let bytes = fs::read(&path).map_err(|error| {
            RunEvaluationError::new(format!(
                "runtime_profile_inventory_unreadable:{}:{error}",
                path.display()
            ))
        })?;
        let raw: JsonValue = serde_json::from_slice(&bytes).map_err(|error| {
            RunEvaluationError::new(format!("runtime_profile_inventory_invalid:{error}"))
        })?;
        let root = raw.as_object().ok_or_else(|| {
            RunEvaluationError::new("runtime profile inventory must be a JSON object")
        })?;
        let response = root
            .get("validation_failure_response")
            .and_then(JsonValue::as_object)
            .ok_or_else(|| {
                RunEvaluationError::new(
                    "runtime profile inventory missing validation_failure_response",
                )
            })?;
        let cause_classes = inventory_slug_set(response, "cause_classes")?;
        let intent_preservation = inventory_slug_set(response, "intent_preservation")?;
        let implementation_bug =
            taxonomy_slug(&cause_classes, "implementation_bug", "cause_classes")?;
        let repair_same_intent = taxonomy_slug(
            &intent_preservation,
            "repair_same_intent",
            "intent_preservation",
        )?;
        let design_conflict = taxonomy_slug(
            &cause_classes,
            "approved_design_user_request_conflict",
            "cause_classes",
        )?;
        let escalate_design_conflict = taxonomy_slug(
            &intent_preservation,
            "escalate_design_conflict",
            "intent_preservation",
        )?;
        let residual_checker_causes = [
            "fixture_environment_issue",
            "pre_existing_unrelated_failure",
        ]
        .into_iter()
        .map(|slug| taxonomy_slug(&cause_classes, slug, "cause_classes"))
        .collect::<Result<BTreeSet<_>, _>>()?;
        Ok(Self {
            cause_classes,
            intent_preservation,
            implementation_bug,
            repair_same_intent,
            design_conflict,
            escalate_design_conflict,
            residual_checker_causes,
        })
    }
}

fn inventory_slug_set(
    response: &serde_json::Map<String, JsonValue>,
    field: &str,
) -> Result<BTreeSet<String>, RunEvaluationError> {
    let values = response
        .get(field)
        .and_then(JsonValue::as_array)
        .filter(|values| !values.is_empty())
        .ok_or_else(|| {
            RunEvaluationError::new(format!(
                "runtime profile inventory missing validation_failure_response.{field}"
            ))
        })?;
    let mut result = BTreeSet::new();
    for value in values {
        let text = value
            .as_str()
            .filter(|text| !text.is_empty())
            .ok_or_else(|| {
                RunEvaluationError::new(format!(
                    "validation_failure_response.{field} must contain strings"
                ))
            })?;
        result.insert(text.to_string());
    }
    Ok(result)
}

fn taxonomy_slug(
    values: &BTreeSet<String>,
    slug: &str,
    field: &str,
) -> Result<String, RunEvaluationError> {
    if !values.contains(slug) {
        return Err(RunEvaluationError::new(format!(
            "runtime profile inventory missing validation_failure_response.{field} slug: {slug}"
        )));
    }
    Ok(slug.to_string())
}

fn yaml_string<'a>(value: &'a Yaml, field: &str) -> Result<&'a str, SelectionProblem> {
    value
        .as_str()
        .filter(|text| !text.is_empty())
        .ok_or_else(|| {
            SelectionProblem::new(format!(
                "team_manifest.yaml:{field}:must_be_nonempty_string"
            ))
        })
}

fn manifest_map_value<'a>(value: &'a Yaml, key: &str) -> Option<&'a Yaml> {
    value.as_hash()?.get(&Yaml::String(key.to_string()))
}

fn manifest_path_list(
    value: Option<&Yaml>,
    field: &str,
    null_means_empty: bool,
) -> Result<Vec<ArtifactName>, SelectionProblem> {
    let Some(value) = value else {
        return Err(SelectionProblem::new(format!(
            "team_manifest.yaml:{field}:must_be_list"
        )));
    };
    if null_means_empty && matches!(value, Yaml::Null) {
        // manifest_one_role_lines emits an empty required_outputs key with no
        // following items; that existing representation parses as YAML null.
        return Ok(Vec::new());
    }
    let values = value
        .as_vec()
        .ok_or_else(|| SelectionProblem::new(format!("team_manifest.yaml:{field}:must_be_list")))?;
    values
        .iter()
        .map(|item| {
            let raw = yaml_string(item, field)?;
            ArtifactName::parse(raw)
        })
        .collect()
}

struct RunBundleReader {
    root: PathBuf,
    directory: Option<RuntimeDirectory>,
    all_files: BTreeSet<String>,
    top_level_files: Vec<PathBuf>,
}

impl RunBundleReader {
    fn open(path: &Path) -> Result<Self, RunEvaluationError> {
        let root = lexical_absolute(path).map_err(RunEvaluationError::new)?;
        if !root.is_dir() {
            return Ok(Self {
                root,
                directory: None,
                all_files: BTreeSet::new(),
                top_level_files: Vec::new(),
            });
        }
        let directory = RuntimeDirectory::open_nofollow(&root, false).map_err(|error| {
            RunEvaluationError::new(format!(
                "report_directory_unavailable:{}:{error}",
                root.display()
            ))
        })?;
        let files = directory.files(Path::new("")).map_err(|error| {
            RunEvaluationError::new(format!(
                "report_directory_unreadable:{}:{error}",
                root.display()
            ))
        })?;
        let mut all_files = BTreeSet::new();
        let mut top_level_files = Vec::new();
        for path in files {
            if let Some(path_text) = path.to_str() {
                all_files.insert(path_text.to_string());
            }
            if path.components().count() == 1 {
                top_level_files.push(path);
            }
        }
        top_level_files.sort();
        Ok(Self {
            root,
            directory: Some(directory),
            all_files,
            top_level_files,
        })
    }

    fn read_bytes(&self, relative: &str) -> Result<Option<Vec<u8>>, RunEvaluationError> {
        let Some(directory) = &self.directory else {
            return Ok(None);
        };
        directory.read(Path::new(relative)).map_err(|error| {
            RunEvaluationError::new(format!(
                "artifact_unreadable:{}:{error}",
                self.root.join(relative).display()
            ))
        })
    }

    fn read_optional_artifact_bytes(
        &self,
        relative: &str,
    ) -> Result<Option<Vec<u8>>, RunEvaluationError> {
        let Some(directory) = &self.directory else {
            return Ok(None);
        };
        match directory.read(Path::new(relative)) {
            Ok(bytes) => Ok(bytes),
            Err(error) if error.kind() == std::io::ErrorKind::InvalidData => Ok(None),
            Err(error) => Err(RunEvaluationError::new(format!(
                "artifact_unreadable:{}:{error}",
                self.root.join(relative).display()
            ))),
        }
    }

    fn read_text(&self, relative: &str) -> Result<Option<String>, RunEvaluationError> {
        let Some(bytes) = self.read_bytes(relative)? else {
            return Ok(None);
        };
        String::from_utf8(bytes).map(Some).map_err(|error| {
            RunEvaluationError::new(format!(
                "artifact_unreadable:{}:{error}",
                self.root.join(relative).display()
            ))
        })
    }

    fn contains_regular_file(&self, relative: &str) -> bool {
        self.all_files.contains(relative)
    }

    fn top_level_files(&self) -> &[PathBuf] {
        &self.top_level_files
    }
}

fn read_artifact_selection(
    reader: &RunBundleReader,
) -> (ArtifactSelection, BTreeSet<ArtifactName>, RunIdentity) {
    let text = match reader.read_text(MANIFEST_NAME) {
        Ok(Some(text)) => text,
        Ok(None) => {
            return (
                ArtifactSelection::Unknown(SelectionProblem::new("team_manifest.yaml:missing")),
                BTreeSet::new(),
                RunIdentity {
                    task: None,
                    workflow_family: None,
                },
            );
        }
        Err(error) => {
            return (
                ArtifactSelection::Unknown(SelectionProblem::new(format!(
                    "team_manifest.yaml:unreadable:{error}"
                ))),
                BTreeSet::new(),
                RunIdentity {
                    task: None,
                    workflow_family: None,
                },
            );
        }
    };
    let documents = match YamlLoader::load_from_str(&text) {
        Ok(documents) if documents.len() == 1 => documents,
        Ok(_) => {
            return (
                ArtifactSelection::Unknown(SelectionProblem::new(
                    "team_manifest.yaml:expected_single_document",
                )),
                BTreeSet::new(),
                RunIdentity {
                    task: None,
                    workflow_family: None,
                },
            );
        }
        Err(error) => {
            return (
                ArtifactSelection::Unknown(SelectionProblem::new(format!(
                    "team_manifest.yaml:invalid_yaml:{error}"
                ))),
                BTreeSet::new(),
                RunIdentity {
                    task: None,
                    workflow_family: None,
                },
            );
        }
    };
    let document = &documents[0];
    if document.as_hash().is_none() {
        return (
            ArtifactSelection::Unknown(SelectionProblem::new("team_manifest.yaml:must_be_mapping")),
            BTreeSet::new(),
            RunIdentity {
                task: None,
                workflow_family: None,
            },
        );
    }
    let run = manifest_map_value(document, "run");
    let run_identity = RunIdentity {
        task: run
            .and_then(|run| manifest_map_value(run, "task"))
            .and_then(Yaml::as_str)
            .map(str::to_string),
        workflow_family: run
            .and_then(|run| manifest_map_value(run, "workflow_family"))
            .and_then(Yaml::as_str)
            .map(str::to_string),
    };
    let Some(roles_value) = manifest_map_value(document, "roles") else {
        return (
            ArtifactSelection::Unknown(SelectionProblem::new(
                "team_manifest.yaml:roles:must_be_list",
            )),
            BTreeSet::new(),
            run_identity,
        );
    };
    let roles = if matches!(roles_value, Yaml::Null) {
        Vec::new()
    } else if let Some(roles) = roles_value.as_vec() {
        roles.clone()
    } else {
        return (
            ArtifactSelection::Unknown(SelectionProblem::new(
                "team_manifest.yaml:roles:must_be_list",
            )),
            BTreeSet::new(),
            run_identity,
        );
    };
    let mut required = BTreeSet::new();
    for (index, role) in roles.iter().enumerate() {
        if role.as_hash().is_none() {
            return (
                ArtifactSelection::Unknown(SelectionProblem::new(format!(
                    "team_manifest.yaml:roles[{index}]:must_be_mapping"
                ))),
                BTreeSet::new(),
                run_identity,
            );
        }
        let outputs = match manifest_path_list(
            manifest_map_value(role, "required_outputs"),
            &format!("roles[{index}].required_outputs"),
            true,
        ) {
            Ok(outputs) => outputs,
            Err(problem) => {
                return (
                    ArtifactSelection::Unknown(problem),
                    BTreeSet::new(),
                    run_identity,
                )
            }
        };
        required.extend(outputs);
    }
    let materialized = match manifest_path_list(
        manifest_map_value(document, "artifacts"),
        "artifacts",
        false,
    ) {
        Ok(values) => values.into_iter().collect(),
        Err(problem) => {
            return (
                ArtifactSelection::Unknown(problem),
                BTreeSet::new(),
                run_identity,
            )
        }
    };
    (
        ArtifactSelection::Known(required),
        materialized,
        run_identity,
    )
}

fn read_artifact_text(reader: &RunBundleReader, name: &str) -> Result<String, RunEvaluationError> {
    Ok(reader.read_text(name)?.unwrap_or_default())
}

fn read_selected_planning_state(
    reader: &RunBundleReader,
    name: &str,
    selection: &ArtifactSelection,
    materialized: &BTreeSet<ArtifactName>,
) -> Result<ArtifactState, RunEvaluationError> {
    let path = ArtifactName::parse(name)
        .map_err(|problem| RunEvaluationError::new(problem.to_string()))?;
    if !selection.contains(&path) {
        return Ok(ArtifactState::Unselected);
    }
    if !materialized.contains(&path) {
        return Ok(ArtifactState::SelectedMissing);
    }
    let Some(bytes) = reader.read_optional_artifact_bytes(path.as_str())? else {
        return Ok(ArtifactState::SelectedMissing);
    };
    let text = String::from_utf8(bytes).map_err(|error| {
        RunEvaluationError::new(format!(
            "artifact_unreadable:{}:{error}",
            reader.root.join(path.as_str()).display()
        ))
    })?;
    Ok(ArtifactState::SelectedPresent(text))
}

fn missing_selected_artifacts(
    reader: &RunBundleReader,
    selection: &ArtifactSelection,
    materialized: &BTreeSet<ArtifactName>,
) -> Result<Vec<String>, RunEvaluationError> {
    let ArtifactSelection::Known(required) = selection else {
        return Ok(Vec::new());
    };
    let mut missing = Vec::new();
    for name in required {
        if !materialized.contains(name) || !reader.contains_regular_file(name.as_str()) {
            missing.push(name.as_str().to_string());
        }
    }
    Ok(missing)
}

fn parse_kv_lines(
    reader: &RunBundleReader,
    name: &str,
) -> Result<BTreeMap<String, String>, RunEvaluationError> {
    let mut data = BTreeMap::new();
    let Some(text) = reader.read_text(name)? else {
        return Ok(data);
    };
    for line in text.lines() {
        let stripped = line.trim();
        if stripped.is_empty() {
            continue;
        }
        if let Some((key, value)) = stripped.split_once('=') {
            data.insert(key.trim().to_string(), value.trim().to_string());
        }
    }
    Ok(data)
}

fn parse_markdown_status(
    reader: &RunBundleReader,
    name: &str,
) -> Result<BTreeMap<String, String>, RunEvaluationError> {
    static STATUS_LINE: OnceLock<Regex> = OnceLock::new();
    let pattern = STATUS_LINE
        .get_or_init(|| Regex::new(r"^- ([a-zA-Z0-9_]+): (.+)$").expect("fixed status regex"));
    let mut data = BTreeMap::new();
    let Some(text) = reader.read_text(name)? else {
        return Ok(data);
    };
    for line in text.lines() {
        if let Some(captures) = pattern.captures(line.trim()) {
            data.insert(captures[1].to_string(), captures[2].trim().to_string());
        }
    }
    Ok(data)
}

fn markdown_decision(reader: &RunBundleReader, name: &str) -> Result<String, RunEvaluationError> {
    let Some(text) = reader.read_text(name)? else {
        return Ok(String::new());
    };
    let mut in_decision = false;
    for line in text.lines() {
        let stripped = line.trim();
        if stripped.starts_with("## ") {
            in_decision = stripped == "## Decision";
            continue;
        }
        if in_decision && !stripped.is_empty() && !stripped.starts_with("<!--") {
            return Ok(stripped.to_lowercase());
        }
    }
    Ok(String::new())
}

fn toml_text(table: &dyn TableLike, field: &str) -> Result<String, RunEvaluationError> {
    table
        .get(field)
        .and_then(Item::as_str)
        .map(str::to_string)
        .ok_or_else(|| RunEvaluationError::new(format!("behavior manifest missing string {field}")))
}

fn toml_string_tuple(
    table: &dyn TableLike,
    field: &str,
) -> Result<Vec<String>, RunEvaluationError> {
    let Some(value) = table.get(field) else {
        return Ok(Vec::new());
    };
    let array = value
        .as_array()
        .ok_or_else(|| RunEvaluationError::new(format!("{field} must be a list of strings")))?;
    let mut result = Vec::new();
    for item in array.iter() {
        result.push(
            item.as_str()
                .ok_or_else(|| {
                    RunEvaluationError::new(format!("{field} must be a list of strings"))
                })?
                .to_string(),
        );
    }
    Ok(result)
}

fn toml_max_score(table: &dyn TableLike) -> Result<i64, RunEvaluationError> {
    let Some(item) = table.get("max_score") else {
        return Ok(DEFAULT_BEHAVIOR_CRITERION_MAX_SCORE);
    };
    if let Some(value) = item.as_integer() {
        return Ok(value);
    }
    if let Some(value) = item.as_str() {
        return value.parse::<i64>().map_err(|_| {
            RunEvaluationError::new("behavior criterion max_score must be an integer")
        });
    }
    Err(RunEvaluationError::new(
        "behavior criterion max_score must be an integer",
    ))
}

pub fn load_behavior_manifest(path: &Path) -> Result<Vec<BehaviorCriterion>, RunEvaluationError> {
    let text = fs::read_to_string(path).map_err(|error| {
        RunEvaluationError::new(format!(
            "behavior_manifest_unreadable:{}:{error}",
            path.display()
        ))
    })?;
    let document = text
        .parse::<DocumentMut>()
        .map_err(|error| RunEvaluationError::new(format!("behavior_manifest_invalid:{error}")))?;
    let criteria_item = document.get("criteria").ok_or_else(|| {
        RunEvaluationError::new("behavior manifest must define at least one [[criteria]] entry")
    })?;
    let entries: Vec<&dyn TableLike> = if let Some(tables) = criteria_item.as_array_of_tables() {
        tables.iter().map(|table| table as &dyn TableLike).collect()
    } else if let Some(array) = criteria_item.as_array() {
        array
            .iter()
            .enumerate()
            .map(|(index, value)| {
                value
                    .as_inline_table()
                    .map(|table| table as &dyn TableLike)
                    .ok_or_else(|| {
                        RunEvaluationError::new(format!(
                            "behavior criterion {} must be a table",
                            index + 1
                        ))
                    })
            })
            .collect::<Result<Vec<_>, _>>()?
    } else {
        return Err(RunEvaluationError::new(
            "behavior manifest must define at least one [[criteria]] entry",
        ));
    };
    if entries.is_empty() {
        return Err(RunEvaluationError::new(
            "behavior manifest must define at least one [[criteria]] entry",
        ));
    }
    entries
        .into_iter()
        .map(|table| {
            let name = toml_text(table, "name")?;
            let source_value = match table.get("source") {
                None => "behavior_events",
                Some(item) => item.as_str().ok_or_else(|| {
                    RunEvaluationError::new(format!("behavior criterion {name} has invalid source"))
                })?,
            };
            let source = match source_value {
                "behavior_events" => BehaviorSource::BehaviorEvents,
                "bundle" => BehaviorSource::Bundle,
                "runtime_profile_projection_gate" => BehaviorSource::RuntimeProfileProjectionGate,
                other => {
                    return Err(RunEvaluationError::new(format!(
                        "behavior criterion {name} has invalid source={other}"
                    )))
                }
            };
            let feedback = match table.get("feedback") {
                None => format!("Record behavior evidence for {name}."),
                Some(item) => item.as_str().map(str::to_string).ok_or_else(|| {
                    RunEvaluationError::new(format!(
                        "behavior criterion {name} has invalid feedback"
                    ))
                })?,
            };
            Ok(BehaviorCriterion {
                name,
                max_score: toml_max_score(table)?,
                feedback,
                source,
                required_all: toml_string_tuple(table, "required_all")?,
                required_any: toml_string_tuple(table, "required_any")?,
                forbidden_any: toml_string_tuple(table, "forbidden_any")?,
            })
        })
        .collect()
}

fn markdown_section_lines<'a>(text: &'a str, heading: &str) -> Vec<&'a str> {
    let mut lines = Vec::new();
    let mut in_section = false;
    for line in text.lines() {
        let stripped = line.trim();
        if stripped.starts_with("## ") {
            if in_section {
                break;
            }
            in_section = stripped == heading;
        }
        if in_section {
            lines.push(line);
        }
    }
    lines
}

fn markdown_section_text_raw(text: &str, heading: &str) -> String {
    markdown_without_comments(&markdown_section_lines(text, heading).join("\n"))
}

fn markdown_section_text(text: &str, heading: &str) -> String {
    markdown_section_text_raw(text, heading).to_lowercase()
}

fn normalized_bundle(
    reader: &RunBundleReader,
    selection: &ArtifactSelection,
) -> Result<String, RunEvaluationError> {
    let mut text = Vec::new();
    for relative in reader.top_level_files() {
        if let (ArtifactSelection::Known(required), Some(name)) = (
            selection,
            relative.file_name().and_then(|name| name.to_str()),
        ) {
            if [SCHEDULE_NAME, WORK_LOG_NAME].contains(&name)
                && !required.contains(&ArtifactName(name.to_string()))
            {
                continue;
            }
        }
        let extension = relative
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default();
        if !matches!(extension, "md" | "txt" | "yaml" | "yml") {
            continue;
        }
        let name = relative.to_string_lossy();
        if let Some(contents) = reader.read_text(&name)? {
            text.push(markdown_without_comments(&contents));
        }
    }
    Ok(text.join("\n").to_lowercase())
}

fn has_any(text: &str, needles: &[String]) -> bool {
    needles
        .iter()
        .any(|needle| text.contains(&needle.to_lowercase()))
}

fn status_in(status: &BTreeMap<String, String>, key: &str, allowed: &[&str]) -> bool {
    let value = status
        .get(key)
        .map(|value| value.trim().to_lowercase())
        .unwrap_or_default();
    allowed.iter().any(|candidate| value == *candidate)
}

fn token_fields(line: &str) -> BTreeMap<String, String> {
    let mut data = BTreeMap::new();
    for token in line.split_whitespace() {
        if let Some((key, value)) = token.split_once('=') {
            data.insert(
                key.trim().to_string(),
                value
                    .trim_matches(|character| matches!(character, '`' | '\'' | '"'))
                    .to_string(),
            );
        }
    }
    data
}

fn child_execution_receipts_valid(reader: &RunBundleReader) -> bool {
    let Ok(Some(bytes)) = reader.read_bytes("runtime/child_execution_receipts.json") else {
        return false;
    };
    let Ok(value) = serde_json::from_slice::<JsonValue>(&bytes) else {
        return false;
    };
    let Some(mapping) = value.as_object() else {
        return false;
    };
    if mapping.get("schema").and_then(JsonValue::as_str) != Some(CHILD_EXECUTION_RECEIPT_SCHEMA) {
        return false;
    }
    let Some(receipt_sha) = mapping.get("receipt_sha256").and_then(JsonValue::as_str) else {
        return false;
    };
    let mut unsigned = mapping.clone();
    unsigned.remove("receipt_sha256");
    let expected = hex_sha256(&canonical_json_ascii_bytes(&JsonValue::Object(unsigned)));
    if receipt_sha != expected {
        return false;
    }
    let (Some(spawn), Some(close), Some(mutations)) = (
        mapping.get("spawn").and_then(JsonValue::as_object),
        mapping.get("close").and_then(JsonValue::as_object),
        mapping.get("mutations").and_then(JsonValue::as_array),
    ) else {
        return false;
    };
    if mutations.is_empty() {
        return false;
    }
    let actor_id = spawn
        .get("agent_id")
        .and_then(JsonValue::as_str)
        .unwrap_or_default();
    let role_id = spawn
        .get("role_id")
        .and_then(JsonValue::as_str)
        .unwrap_or_default();
    let scope_digest = spawn
        .get("scope_digest")
        .and_then(JsonValue::as_str)
        .unwrap_or_default();
    if actor_id.is_empty() || role_id.is_empty() || scope_digest.is_empty() {
        return false;
    }
    if close.get("agent_id").and_then(JsonValue::as_str) != Some(actor_id)
        || close.get("status").and_then(JsonValue::as_str) != Some("closed")
    {
        return false;
    }
    mutations.iter().all(|mutation| {
        let Some(mutation) = mutation.as_object() else {
            return false;
        };
        mutation.get("actor_id").and_then(JsonValue::as_str) == Some(actor_id)
            && mutation.get("role_id").and_then(JsonValue::as_str) == Some(role_id)
            && mutation.get("scope_digest").and_then(JsonValue::as_str) == Some(scope_digest)
            && matches!(
                mutation.get("status").and_then(JsonValue::as_str),
                Some("allowed" | "blocked")
            )
    })
}

fn canonical_json_ascii_bytes(value: &JsonValue) -> Vec<u8> {
    let compact = serde_json::to_string(value).expect("JSON values serialize");
    let mut output = String::with_capacity(compact.len());
    for character in compact.chars() {
        let code = character as u32;
        if code <= 0x7f {
            output.push(character);
        } else if code <= 0xffff {
            output.push_str(&format!("\\u{code:04x}"));
        } else {
            let adjusted = code - 0x1_0000;
            let high = 0xd800 + (adjusted >> 10);
            let low = 0xdc00 + (adjusted & 0x3ff);
            output.push_str(&format!("\\u{high:04x}\\u{low:04x}"));
        }
    }
    output.into_bytes()
}

fn hex_sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn has_open_review_findings(texts: &[&str]) -> bool {
    static NO_OPEN: OnceLock<Regex> = OnceLock::new();
    let no_open = NO_OPEN.get_or_init(|| {
        Regex::new(r"\b(no|none)\b.*\b(fix-now|required_change|open)\b")
            .expect("fixed review regex")
    });
    for text in texts {
        let cleaned =
            markdown_without_adjudicated_rejected_hypotheses(&markdown_without_comments(text))
                .to_lowercase();
        for line in cleaned.lines() {
            if no_open.is_match(line) {
                continue;
            }
            if line.contains("fix-now") && (line.contains("open") || line.contains("pending")) {
                return true;
            }
            if line.contains("required_change")
                && !["resolved", "applied", "fixed", "closed"]
                    .iter()
                    .any(|token| line.contains(token))
            {
                return true;
            }
        }
    }
    false
}

fn criterion(
    name: &str,
    max_score: i64,
    passed: bool,
    feedback: impl Into<String>,
    partial_score: i64,
) -> CriterionResult {
    if passed {
        CriterionResult {
            name: name.to_string(),
            score: max_score,
            max_score,
            status: "pass".to_string(),
            feedback: "No action required.".to_string(),
        }
    } else {
        CriterionResult {
            name: name.to_string(),
            score: partial_score,
            max_score,
            status: "revise".to_string(),
            feedback: feedback.into(),
        }
    }
}

pub fn read_run_evidence(report_dir: &Path) -> Result<RunEvidence, RunEvaluationError> {
    let reader = RunBundleReader::open(report_dir)?;
    let (selection, materialized_artifacts, run_identity) = read_artifact_selection(&reader);
    let missing_artifacts =
        missing_selected_artifacts(&reader, &selection, &materialized_artifacts)?;
    let schedule =
        read_selected_planning_state(&reader, SCHEDULE_NAME, &selection, &materialized_artifacts)?;
    let work_log =
        read_selected_planning_state(&reader, WORK_LOG_NAME, &selection, &materialized_artifacts)?;
    let schedule_findings = match &schedule {
        ArtifactState::SelectedPresent(text) => check_schedule_artifact(text),
        ArtifactState::SelectedMissing => vec!["schedule.md:missing".to_string()],
        ArtifactState::Unselected => Vec::new(),
    };
    let work_log_findings = match &work_log {
        ArtifactState::SelectedPresent(text) => check_work_log_artifact(text),
        ArtifactState::SelectedMissing => vec!["work_log.md:missing".to_string()],
        ArtifactState::Unselected => Vec::new(),
    };
    let monitoring_text = read_artifact_text(&reader, MONITORING_NAME)?;
    let behavior_events_raw_text =
        markdown_section_text_raw(&monitoring_text, "## Behavior Events");
    let tool_warnings_text = markdown_section_text_raw(&monitoring_text, "## Tool Warnings");
    let child_execution_receipts_valid = child_execution_receipts_valid(&reader);
    Ok(RunEvidence {
        report_dir: reader.root.clone(),
        selection,
        materialized_artifacts,
        run_identity,
        missing_artifacts,
        planned_work: PlannedWorkEvidence {
            schedule,
            work_log,
            schedule_findings,
            work_log_findings,
        },
        request_contract: parse_markdown_status(&reader, REQUEST_CONTRACT_NAME)?,
        verification: parse_kv_lines(&reader, VERIFICATION_NAME)?,
        closeout: parse_markdown_status(&reader, CLOSEOUT_GATE_NAME)?,
        monitoring_text: monitoring_text.clone(),
        monitoring_status: parse_markdown_status(&reader, MONITORING_NAME)?,
        retrospective_text: read_artifact_text(&reader, RETROSPECTIVE_NAME)?,
        final_decision: markdown_decision(&reader, FINAL_REVIEW_NAME)?,
        change_review_text: read_artifact_text(&reader, CHANGE_REVIEW_NAME)?,
        final_review_text: read_artifact_text(&reader, FINAL_REVIEW_NAME)?,
        normalized_bundle: normalized_bundle(&reader, &selection)?,
        signals_text: markdown_section_text(&monitoring_text, "## Signals"),
        behavior_events_text: markdown_section_text(&monitoring_text, "## Behavior Events"),
        behavior_events_raw_text,
        tool_warnings_text,
        child_execution_receipts_valid,
    })
}

fn monitoring_sections_complete(evidence: &RunEvidence) -> bool {
    [
        "## Signals",
        "## Behavior Events",
        "## Tool Warnings",
        "## Interventions",
        "## Improvement Decisions",
    ]
    .iter()
    .all(|heading| section_has_content(&evidence.monitoring_text, heading))
}

fn improvement_decisions_complete(evidence: &RunEvidence) -> bool {
    [
        "skill_improvement_decision",
        "config_improvement_decision",
        "workflow_improvement_decision",
        "knowledge_learning_decision",
    ]
    .iter()
    .all(|key| {
        status_in(
            &evidence.monitoring_status,
            key,
            &["applied", "recorded", "not_applicable"],
        )
    })
}

fn improvement_decision_applied_or_recorded(evidence: &RunEvidence) -> bool {
    [
        "skill_improvement_decision",
        "config_improvement_decision",
        "workflow_improvement_decision",
        "knowledge_learning_decision",
    ]
    .iter()
    .any(|key| status_in(&evidence.monitoring_status, key, &["applied", "recorded"]))
}

fn runtime_feedback_requires_improvement(evidence: &RunEvidence) -> bool {
    evidence
        .behavior_events_text
        .contains("runtime_feedback=observed")
        && !evidence.behavior_events_text.contains("action=no_op")
}

fn runtime_feedback_closure_complete(evidence: &RunEvidence) -> bool {
    !runtime_feedback_requires_improvement(evidence)
        || (improvement_decisions_complete(evidence)
            && improvement_decision_applied_or_recorded(evidence))
}

fn tool_warning_problems(evidence: &RunEvidence) -> Vec<String> {
    let mut problems = Vec::new();
    let status = evidence
        .monitoring_status
        .get("tool_warnings_status")
        .map(|status| status.trim().to_lowercase())
        .unwrap_or_default();
    if status != "none" && status != "resolved" {
        problems.push(
            "tool_warnings_status must be none or resolved in workflow_monitoring.md".to_string(),
        );
    }
    let mut latest_by_id: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    for line in evidence.tool_warnings_text.lines() {
        if !line.contains("tool_warning=recorded") {
            continue;
        }
        let fields = token_fields(line);
        let warning_id = fields.get("warning_id").cloned().unwrap_or_default();
        if warning_id.is_empty() {
            problems.push("tool_warning entry missing warning_id".to_string());
            continue;
        }
        latest_by_id.insert(warning_id, fields);
    }
    for (warning_id, fields) in latest_by_id {
        let warning_status = fields
            .get("status")
            .map(String::as_str)
            .unwrap_or_default()
            .to_lowercase();
        let severity = fields
            .get("severity")
            .map(String::as_str)
            .unwrap_or_default()
            .to_lowercase();
        if ["", "open", "pending", "observed", "unresolved"].contains(&warning_status.as_str()) {
            problems.push(format!("tool warning remains open: {warning_id}"));
        }
        if ["fix-now", "s0", "s1", "blocker"].contains(&severity.as_str())
            && warning_status != "resolved"
        {
            problems.push(format!(
                "fix-now tool warning must be resolved: {warning_id}"
            ));
        }
        if ["resolved", "accepted_with_reason", "deferred_with_issue"]
            .contains(&warning_status.as_str())
            && !fields.contains_key("evidence")
            && !fields.contains_key("issue")
        {
            problems.push(format!(
                "closed tool warning lacks evidence or issue: {warning_id}"
            ));
        }
    }
    problems
}

fn tool_warnings_closed(evidence: &RunEvidence) -> bool {
    tool_warning_problems(evidence).is_empty()
}

fn orchestration_evidence_present(evidence: &RunEvidence) -> bool {
    let signals = &evidence.signals_text;
    let behavior = &evidence.behavior_events_text;
    evidence.child_execution_receipts_valid
        && has_any(
            signals,
            &["skills=".to_string(), "$agent-orchestration".to_string()],
        )
        && has_any(
            behavior,
            &[
                "skill_invocation=".to_string(),
                "skill_invocation_not_required".to_string(),
            ],
        )
        && has_any(
            signals,
            &[
                "write_capable_child".to_string(),
                "write-capable child".to_string(),
                "write_capable_handoff".to_string(),
                "WRITE_SUBAGENT_AUTHORIZATION=required".to_string(),
            ],
        )
        && has_any(
            signals,
            &[
                "repo_dependency_review=pass".to_string(),
                "run_repo_dependency_review.sh".to_string(),
                "repo_dependency_intake_not_required".to_string(),
                "dependency review".to_string(),
            ],
        )
        && has_any(
            signals,
            &[
                "web_research".to_string(),
                "external_research".to_string(),
                "internet research".to_string(),
                "web_research_not_required".to_string(),
                "internet_research_not_required".to_string(),
            ],
        )
        && has_any(
            signals,
            &[
                "review_status=".to_string(),
                "review_decision=".to_string(),
                "review_not_required".to_string(),
            ],
        )
        && has_any(
            signals,
            &[
                "validation_status=".to_string(),
                "validation_complete: yes".to_string(),
                "validation_not_required".to_string(),
            ],
        )
        && has_any(
            signals,
            &[
                "drift_risk=".to_string(),
                "drift_risk_not_required".to_string(),
                "forbidden_drift_detected".to_string(),
            ],
        )
}

fn build_artifact_and_traceability_criteria(evidence: &RunEvidence) -> Vec<CriterionResult> {
    let completeness = match &evidence.selection {
        ArtifactSelection::Known(_) => criterion(
            "artifact_completeness",
            ARTIFACT_COMPLETENESS_SCORE,
            evidence.missing_artifacts.is_empty(),
            format!("Create missing run artifacts: {}.", evidence.missing_artifacts.join(", ")),
            0,
        ),
        ArtifactSelection::Unknown(problem) => criterion(
            "artifact_completeness",
            ARTIFACT_COMPLETENESS_SCORE,
            false,
            format!("Cannot establish required run artifacts because selection metadata is invalid: {}.", problem.detail),
            0,
        ),
    };
    let contract = &evidence.request_contract;
    vec![
        completeness,
        criterion(
            "request_traceability",
            REQUEST_TRACEABILITY_SCORE,
            contract.get("all_clauses_resolved").map(String::as_str) == Some("yes")
                && contract.get("forbidden_drift_detected").map(String::as_str) == Some("no")
                && contract.get("unresolved_clause_ids").map(|value| value.trim().is_empty()).unwrap_or(true),
            "Resolve all request clauses, clear unresolved ids, and confirm forbidden drift is absent.",
            0,
        ),
    ]
}

fn planned_work_criterion(evidence: &RunEvidence) -> CriterionResult {
    match &evidence.selection {
        ArtifactSelection::Unknown(problem) => criterion(
            "planned_work_and_chronology",
            PLANNED_WORK_AND_CHRONOLOGY_SCORE,
            false,
            format!("Cannot establish selected schedule/work-log artifacts from team_manifest.yaml: {}.", problem.detail),
            0,
        ),
        ArtifactSelection::Known(_) => {
            let selected_any = !matches!(evidence.planned_work.schedule, ArtifactState::Unselected)
                || !matches!(evidence.planned_work.work_log, ArtifactState::Unselected);
            if !selected_any {
                return criterion(
                    "planned_work_and_chronology",
                    PLANNED_WORK_AND_CHRONOLOGY_SCORE,
                    true,
                    "No planning artifacts were selected for this run.",
                    0,
                );
            }
            let findings = evidence
                .planned_work
                .schedule_findings
                .iter()
                .chain(evidence.planned_work.work_log_findings.iter())
                .cloned()
                .collect::<Vec<_>>();
            criterion(
                "planned_work_and_chronology",
                PLANNED_WORK_AND_CHRONOLOGY_SCORE,
                findings.is_empty(),
                if findings.is_empty() {
                    "Fill schedule stage/coverage/work-unit tables and add meaningful work-log entries."
                        .to_string()
                } else {
                    format!("Repair selected planning artifacts: {}.", findings.join(", "))
                },
                0,
            )
        }
    }
}

fn build_workflow_execution_criteria(evidence: &RunEvidence) -> Vec<CriterionResult> {
    let warning_problems = tool_warning_problems(evidence);
    vec![
        planned_work_criterion(evidence),
        criterion(
            "workflow_monitoring",
            WORKFLOW_MONITORING_SCORE,
            monitoring_sections_complete(evidence),
            "Fill workflow_monitoring.md with signals, Behavior Events, Tool Warnings, interventions, and improvement decisions from the active workflow.",
            0,
        ),
        criterion(
            "tool_warning_obligation_closure",
            TOOL_WARNING_OBLIGATION_SCORE,
            warning_problems.is_empty(),
            format!(
                "Record every non-blocking tool, hook, checker, and wrapper warning in ## Tool Warnings and close each item with resolved, accepted_with_reason, deferred_with_issue, not_applicable, or tool_warnings_status=none. Problems: {}",
                warning_problems.join("; ")
            ),
            0,
        ),
        criterion(
            "orchestration_and_pre_design_intake",
            ORCHESTRATION_INTAKE_SCORE,
            orchestration_evidence_present(evidence),
            "Record skills, write-capable child routing, MCP preflight or explicit opt-out, repo dependency intake, web research decision, review status, validation status, and drift risk before implementation.",
            0,
        ),
    ]
}

fn build_closeout_criteria(evidence: &RunEvidence) -> Vec<CriterionResult> {
    let closeout = &evidence.closeout;
    vec![
        criterion(
            "validation_and_closeout_evidence",
            VALIDATION_AND_CLOSEOUT_SCORE,
            evidence.verification.get("status").map(String::as_str) == Some("pass")
                && closeout.get("validation_complete").map(String::as_str) == Some("yes")
                && closeout.get("commit_created").map(String::as_str) == Some("yes")
                && closeout.get("push_completed").map(String::as_str) == Some("yes"),
            "Record passing verification, validation_complete=yes, commit evidence, and push evidence.",
            0,
        ),
        criterion(
            "dependency_and_canonical_evidence",
            DEPENDENCY_AND_CANONICAL_SCORE,
            closeout.get("dependency_headers_complete").map(String::as_str) == Some("yes")
                && closeout.get("repo_wide_dependency_tools_complete").map(String::as_str) == Some("yes")
                && closeout.get("repo_wide_static_analysis_complete").map(String::as_str) == Some("yes")
                && closeout.get("canonical_tree_head_complete").map(String::as_str) == Some("yes"),
            "Record changed-file dependency evidence, repo-wide dependency review evidence, repo-wide static analysis evidence, and canonical tree-head evidence in closeout_gate.md.",
            0,
        ),
    ]
}

fn build_review_and_closeout_criteria(evidence: &RunEvidence) -> Vec<CriterionResult> {
    let final_review_blockers = check_final_review_artifact(&evidence.final_review_text);
    let mut results = vec![criterion(
        "review_feedback_loop",
        REVIEW_FEEDBACK_LOOP_SCORE,
        has_approve_decision(&evidence.final_review_text)
            && final_review_blockers.is_empty()
            && !has_open_review_findings(&[&evidence.change_review_text, &evidence.final_review_text]),
        "Resolve or escalate review feedback and record a concrete approving final review decision.",
        0,
    )];
    results.extend(build_closeout_criteria(evidence));
    results
}

fn build_self_improvement_feedback_criterion(evidence: &RunEvidence) -> CriterionResult {
    let decisions_complete = improvement_decisions_complete(evidence);
    let feedback_closed = runtime_feedback_closure_complete(evidence);
    criterion(
        "self_improvement_feedback_capture",
        SELF_IMPROVEMENT_FEEDBACK_SCORE,
        section_has_content(&evidence.retrospective_text, "## What Worked")
            && section_has_content(&evidence.retrospective_text, "## What Hurt")
            && section_has_content(&evidence.retrospective_text, "## Follow-ups")
            && decisions_complete
            && feedback_closed,
        "Fill retrospective sections and mark skill/config/workflow/knowledge improvement decisions as applied, recorded, or not_applicable. When runtime_feedback=observed is not action=no_op, at least one improvement decision must be applied or recorded.",
        if decisions_complete && feedback_closed { SELF_IMPROVEMENT_PARTIAL_SCORE } else { 0 },
    )
}

fn build_base_criteria(evidence: &RunEvidence) -> Vec<CriterionResult> {
    let mut criteria = build_artifact_and_traceability_criteria(evidence);
    criteria.extend(build_workflow_execution_criteria(evidence));
    criteria.extend(build_review_and_closeout_criteria(evidence));
    criteria.push(build_self_improvement_feedback_criterion(evidence));
    criteria
}

fn evaluate_behavior_criteria(
    source_texts: &BTreeMap<BehaviorSource, String>,
    behavior_criteria: &[BehaviorCriterion],
    taxonomy: &ValidationFailureTaxonomy,
) -> Vec<CriterionResult> {
    behavior_criteria
        .iter()
        .map(|item| {
            let text = source_texts
                .get(&item.source)
                .map(String::as_str)
                .unwrap_or_default();
            evaluate_behavior_criterion(text, item, taxonomy)
        })
        .collect()
}

fn evaluate_behavior_criterion(
    text: &str,
    item: &BehaviorCriterion,
    taxonomy: &ValidationFailureTaxonomy,
) -> CriterionResult {
    if item.name == "token_efficiency_recorded" {
        return evaluate_token_efficiency_criterion(text, item);
    }
    if item.name == "validation_failure_response_recorded" {
        return evaluate_validation_failure_response_criterion(text, item, taxonomy);
    }
    let missing_all = item
        .required_all
        .iter()
        .filter(|token| !text.contains(&token.to_lowercase()))
        .cloned()
        .collect::<Vec<_>>();
    let any_passed = item.required_any.is_empty() || has_any(text, &item.required_any);
    let forbidden_hits = item
        .forbidden_any
        .iter()
        .filter(|token| text.contains(&token.to_lowercase()))
        .cloned()
        .collect::<Vec<_>>();
    let passed = missing_all.is_empty() && any_passed && forbidden_hits.is_empty();
    criterion(
        &format!("behavior::{}", item.name),
        item.max_score,
        passed,
        behavior_feedback(item, &missing_all, any_passed, &forbidden_hits),
        0,
    )
}

fn evaluate_token_efficiency_criterion(text: &str, item: &BehaviorCriterion) -> CriterionResult {
    let active_tokens = [
        "token_efficiency_protocol=active",
        "token_footprint_comparison=",
        "TOKEN_FOOTPRINT_COMPARISON=",
        "token_ratio=",
        "TOKEN_FOOTPRINT_RATIO=",
    ];
    if active_tokens
        .iter()
        .any(|token| text.contains(&token.to_lowercase()))
    {
        let missing_all = item
            .required_all
            .iter()
            .filter(|token| !text.contains(&token.to_lowercase()))
            .cloned()
            .collect::<Vec<_>>();
        let any_passed = item.required_any.is_empty() || has_any(text, &item.required_any);
        let forbidden_hits = item
            .forbidden_any
            .iter()
            .filter(|token| text.contains(&token.to_lowercase()))
            .cloned()
            .collect::<Vec<_>>();
        let passed = missing_all.is_empty() && any_passed && forbidden_hits.is_empty();
        return criterion(
            &format!("behavior::{}", item.name),
            item.max_score,
            passed,
            behavior_feedback(item, &missing_all, any_passed, &forbidden_hits),
            0,
        );
    }
    let opt_out = has_any(text, &["token_efficiency_not_required".to_string()]);
    criterion(
        &format!("behavior::{}", item.name),
        item.max_score,
        opt_out,
        if opt_out {
            item.feedback.clone()
        } else {
            format!(
                "{} (missing opt-out token: token_efficiency_not_required)",
                item.feedback
            )
        },
        0,
    )
}

fn evaluate_validation_failure_response_criterion(
    text: &str,
    item: &BehaviorCriterion,
    taxonomy: &ValidationFailureTaxonomy,
) -> CriterionResult {
    let failure_tokens = item
        .required_any
        .iter()
        .filter(|token| token.as_str() != "validation_failure_not_observed")
        .cloned()
        .collect::<Vec<_>>();
    let not_observed = text.contains("validation_failure_not_observed");
    let failure_observed = has_any(text, &failure_tokens);
    let observation_recorded = not_observed || failure_observed;
    let contradictory = not_observed && failure_observed;
    let forbidden_violations = validation_failure_forbidden_violations(
        text,
        &item
            .forbidden_any
            .iter()
            .cloned()
            .chain(
                VALIDATION_FAILURE_FORBIDDEN_TOKENS
                    .iter()
                    .map(|value| value.to_string()),
            )
            .collect::<Vec<_>>(),
        taxonomy,
    );
    let evidence_complete = validation_failure_evidence_complete(text, &failure_tokens, taxonomy);
    let passed = observation_recorded
        && !contradictory
        && (!failure_observed || evidence_complete)
        && forbidden_violations.is_empty();
    let missing = validation_failure_missing_tokens(
        observation_recorded,
        failure_observed,
        evidence_complete,
        &forbidden_violations,
        contradictory,
        taxonomy,
    );
    criterion(
        &format!("behavior::{}", item.name),
        item.max_score,
        passed,
        behavior_feedback(item, &missing, true, &forbidden_violations),
        0,
    )
}

fn validation_failure_event_fields(
    text: &str,
    failure_tokens: &[String],
) -> Vec<BTreeMap<String, String>> {
    text.lines()
        .filter(|line| {
            let line = line.to_lowercase();
            failure_tokens
                .iter()
                .any(|token| line.contains(&token.to_lowercase()))
        })
        .map(token_fields)
        .collect()
}

fn validation_failure_fields_complete(
    fields: &BTreeMap<String, String>,
    taxonomy: &ValidationFailureTaxonomy,
) -> bool {
    let cause = fields
        .get("cause_classification")
        .map(String::as_str)
        .unwrap_or_default();
    let intent = fields
        .get("intent_preservation")
        .map(String::as_str)
        .unwrap_or_default();
    fields
        .get("failing_contract")
        .is_some_and(|value| !value.is_empty())
        && fields
            .get("observation_level")
            .is_some_and(|value| !value.is_empty())
        && taxonomy.cause_classes.contains(cause)
        && taxonomy.intent_preservation.contains(intent)
        && fields
            .get("evidence")
            .is_some_and(|value| !value.is_empty())
}

fn validation_failure_evidence_complete(
    text: &str,
    failure_tokens: &[String],
    taxonomy: &ValidationFailureTaxonomy,
) -> bool {
    let events = validation_failure_event_fields(text, failure_tokens);
    !events.is_empty()
        && events
            .iter()
            .all(|fields| validation_failure_fields_complete(fields, taxonomy))
}

fn validation_failure_fields_escalated(
    fields: &BTreeMap<String, String>,
    taxonomy: &ValidationFailureTaxonomy,
) -> bool {
    fields.get("cause_classification").map(String::as_str)
        == Some(taxonomy.design_conflict.as_str())
        && fields.get("intent_preservation").map(String::as_str)
            == Some(taxonomy.escalate_design_conflict.as_str())
        && fields
            .get("evidence")
            .is_some_and(|value| !value.is_empty())
}

fn validation_failure_forbidden_violations(
    text: &str,
    forbidden_tokens: &[String],
    taxonomy: &ValidationFailureTaxonomy,
) -> Vec<String> {
    let mut normalized = Vec::new();
    for token in forbidden_tokens {
        let token = token.to_lowercase();
        if !normalized.contains(&token) {
            normalized.push(token);
        }
    }
    let mut violations = Vec::new();
    for line in text.lines() {
        let lower = line.to_lowercase();
        let hits = normalized
            .iter()
            .filter(|token| lower.contains(token.as_str()))
            .cloned()
            .collect::<Vec<_>>();
        if hits.is_empty() {
            continue;
        }
        let fields = token_fields(line);
        if validation_failure_fields_escalated(&fields, taxonomy) {
            continue;
        }
        for hit in hits {
            if !violations.contains(&hit) {
                violations.push(hit);
            }
        }
    }
    violations
}

fn validation_failure_missing_tokens(
    observation_recorded: bool,
    failure_observed: bool,
    evidence_complete: bool,
    forbidden_violations: &[String],
    contradictory: bool,
    taxonomy: &ValidationFailureTaxonomy,
) -> Vec<String> {
    let mut missing = Vec::new();
    if !observation_recorded {
        missing.push(
            "validation_failure_not_observed or observed validation failure token".to_string(),
        );
    }
    if contradictory {
        missing.push(
            "remove validation_failure_not_observed when later failure evidence exists".to_string(),
        );
    }
    if failure_observed && !evidence_complete {
        missing.extend([
            "failing_contract=".to_string(),
            "observation_level=".to_string(),
            "cause_classification=<canonical_slug>".to_string(),
            format!(
                "intent_preservation={}",
                validation_failure_slug_hint(&taxonomy.intent_preservation)
            ),
            "evidence=".to_string(),
        ]);
    }
    if !forbidden_violations.is_empty() {
        missing.push(format!(
            "intent_preservation={} with cause_classification={} on the same event",
            taxonomy.escalate_design_conflict, taxonomy.design_conflict
        ));
    }
    missing
}

fn validation_failure_slug_hint(values: &BTreeSet<String>) -> String {
    format!("<{}>", values.iter().cloned().collect::<Vec<_>>().join("|"))
}

fn behavior_feedback(
    item: &BehaviorCriterion,
    missing_all: &[String],
    any_passed: bool,
    forbidden_hits: &[String],
) -> String {
    let mut details = Vec::new();
    if !missing_all.is_empty() {
        details.push(format!(
            "missing all-required tokens: {}",
            missing_all.join(", ")
        ));
    }
    if !any_passed {
        details.push(format!(
            "missing any-required token: {}",
            item.required_any.join(" OR ")
        ));
    }
    if !forbidden_hits.is_empty() {
        details.push(format!(
            "forbidden token present: {}",
            forbidden_hits.join(", ")
        ));
    }
    if details.is_empty() {
        item.feedback.clone()
    } else {
        format!("{} ({})", item.feedback, details.join("; "))
    }
}

fn checker_identity(fields: &BTreeMap<String, String>) -> String {
    fields
        .get("checker")
        .or_else(|| fields.get("tool_call"))
        .cloned()
        .unwrap_or_else(|| "unknown-checker".to_string())
}

fn unresolved_checker_failure_blockers(
    text: &str,
    taxonomy: &ValidationFailureTaxonomy,
) -> Vec<String> {
    let mut latest_by_checker: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    let mut blockers = Vec::new();
    for line in text.lines() {
        let fields = token_fields(line);
        let status = fields
            .get("code_checker")
            .map(String::as_str)
            .unwrap_or_default();
        if status != "pass" && status != "fail" {
            continue;
        }
        let checker = checker_identity(&fields);
        latest_by_checker.insert(checker.clone(), fields.clone());
        if status == "fail" && !validation_failure_fields_complete(&fields, taxonomy) {
            blockers.push(format!(
                "{checker} code_checker=fail missing validation-failure field packet: failing_contract=, observation_level=, cause_classification=<canonical_slug>, intent_preservation=<canonical_slug>, evidence="
            ));
        }
    }
    for (checker, fields) in latest_by_checker {
        if fields.get("code_checker").map(String::as_str) != Some("fail")
            || !validation_failure_fields_complete(&fields, taxonomy)
        {
            continue;
        }
        let cause = fields
            .get("cause_classification")
            .cloned()
            .unwrap_or_default();
        let intent = fields
            .get("intent_preservation")
            .cloned()
            .unwrap_or_default();
        if cause == taxonomy.implementation_bug && intent == taxonomy.repair_same_intent {
            blockers.push(format!(
                "{checker} still reports code_checker=fail after cause_classification={} intent_preservation={}; rerun the same checker to a later code_checker=pass or keep repairing the owning surface",
                taxonomy.implementation_bug, taxonomy.repair_same_intent
            ));
            continue;
        }
        if taxonomy.residual_checker_causes.contains(&cause)
            && fields
                .get("evidence")
                .is_some_and(|value| !value.is_empty())
        {
            continue;
        }
        if !cause.is_empty() || !intent.is_empty() {
            blockers.push(format!(
                "{checker} code_checker=fail has unresolved validation-failure route cause_classification={} intent_preservation={}",
                if cause.is_empty() { "<missing>" } else { &cause },
                if intent.is_empty() { "<missing>" } else { &intent }
            ));
        }
    }
    blockers
}

fn build_behavior_sources(evidence: &RunEvidence) -> BTreeMap<BehaviorSource, String> {
    BTreeMap::from([
        (
            BehaviorSource::BehaviorEvents,
            evidence.behavior_events_text.clone(),
        ),
        (BehaviorSource::Bundle, evidence.normalized_bundle.clone()),
        (
            BehaviorSource::RuntimeProfileProjectionGate,
            evidence.behavior_events_text.clone(),
        ),
    ])
}

pub fn evaluate_run(
    report_dir: &Path,
    behavior_criteria: &[BehaviorCriterion],
    source_root: &Path,
    min_score: i64,
) -> Result<EvaluationReport, RunEvaluationError> {
    let evidence = read_run_evidence(report_dir)?;
    let taxonomy = ValidationFailureTaxonomy::load(source_root)?;
    let mut criteria = build_base_criteria(&evidence);
    criteria.extend(evaluate_behavior_criteria(
        &build_behavior_sources(&evidence),
        behavior_criteria,
        &taxonomy,
    ));
    let mut blockers = criteria
        .iter()
        .filter(|item| item.status != "pass")
        .map(|item| item.feedback.clone())
        .collect::<Vec<_>>();
    blockers.extend(unresolved_checker_failure_blockers(
        &evidence.behavior_events_raw_text,
        &taxonomy,
    ));
    let score = criteria.iter().map(|item| item.score).sum();
    let max_score = criteria.iter().map(|item| item.max_score).sum();
    let status = if score >= min_score && blockers.is_empty() {
        "pass"
    } else {
        "revise"
    }
    .to_string();
    let markdown = render_markdown(&evidence.report_dir, &criteria, &blockers, min_score);
    Ok(EvaluationReport {
        criteria,
        blockers,
        score,
        max_score,
        status,
        threshold: min_score,
        markdown,
    })
}

pub fn render_markdown(
    report_dir: &Path,
    criteria: &[CriterionResult],
    blockers: &[String],
    min_score: i64,
) -> String {
    let mut lines = render_markdown_header(report_dir, criteria, blockers, min_score);
    lines.extend(render_rubric_lines(criteria));
    lines.extend(render_feedback_action_lines(blockers));
    lines.extend(render_learning_capture_lines());
    lines.join("\n")
}

fn markdown_summary(
    criteria: &[CriterionResult],
    blockers: &[String],
    min_score: i64,
) -> BTreeMap<String, String> {
    let score = criteria.iter().map(|item| item.score).sum::<i64>();
    let max_score = criteria.iter().map(|item| item.max_score).sum::<i64>();
    let status = if score >= min_score && blockers.is_empty() {
        "pass"
    } else {
        "revise"
    };
    BTreeMap::from([
        ("evaluation_status".to_string(), status.to_string()),
        ("score".to_string(), score.to_string()),
        ("max_score".to_string(), max_score.to_string()),
        ("threshold".to_string(), min_score.to_string()),
        (
            "feedback_actions_resolved".to_string(),
            if status == "pass" { "yes" } else { "no" }.to_string(),
        ),
        (
            "learning_capture_complete".to_string(),
            learning_capture_complete(criteria),
        ),
    ])
}

fn render_markdown_header(
    report_dir: &Path,
    criteria: &[CriterionResult],
    blockers: &[String],
    min_score: i64,
) -> Vec<String> {
    let summary = markdown_summary(criteria, blockers, min_score);
    vec![
        "# Agent Evaluation".to_string(),
        String::new(),
        "<!--".to_string(),
        "@dependency-start".to_string(),
        "upstream design ../../agents/skills/agent-learning.md agent feedback skill".to_string(),
        "upstream implementation ../../tools/runtime/dispatch/agent-canon/src/run_evaluation.rs generates this artifact".to_string(),
        "@dependency-end".to_string(),
        "-->".to_string(),
        String::new(),
        format!("- evaluation_status: {}", summary["evaluation_status"]),
        format!("- score: {}", summary["score"]),
        format!("- max_score: {}", summary["max_score"]),
        format!("- threshold: {}", summary["threshold"]),
        format!("- feedback_actions_resolved: {}", summary["feedback_actions_resolved"]),
        format!("- learning_capture_complete: {}", summary["learning_capture_complete"]),
        String::new(),
        "## Scope".to_string(),
        String::new(),
        format!("- report_dir: {}", report_dir.display()),
        String::new(),
        "## Rubric".to_string(),
        String::new(),
        "| Criterion | Score | Max | Status | Feedback |".to_string(),
        "| --------- | ----- | --- | ------ | -------- |".to_string(),
    ]
}

fn learning_capture_complete(criteria: &[CriterionResult]) -> String {
    let learning_names = [
        "learning_and_feedback_capture",
        "self_improvement_feedback_capture",
    ];
    if criteria
        .iter()
        .any(|item| learning_names.contains(&item.name.as_str()) && item.status == "pass")
    {
        "yes".to_string()
    } else {
        "no".to_string()
    }
}

fn render_rubric_lines(criteria: &[CriterionResult]) -> Vec<String> {
    criteria
        .iter()
        .map(|item| {
            format!(
                "| {} | {} | {} | {} | {} |",
                item.name, item.score, item.max_score, item.status, item.feedback
            )
        })
        .collect()
}

fn render_feedback_action_lines(blockers: &[String]) -> Vec<String> {
    let action_lines = if blockers.is_empty() {
        vec!["| F0 | none | No open feedback actions. | resolved |".to_string()]
    } else {
        blockers
            .iter()
            .enumerate()
            .map(|(index, blocker)| format!("| F{} | fix-now | {} | open |", index + 1, blocker))
            .collect()
    };
    let mut lines = vec![
        String::new(),
        "## Feedback Actions".to_string(),
        String::new(),
        "| Action ID | Severity | Action | Status |".to_string(),
        "| --------- | -------- | ------ | ------ |".to_string(),
    ];
    lines.extend(action_lines);
    lines
}

fn render_learning_capture_lines() -> Vec<String> {
    vec![
        String::new(),
        "## Learning Capture".to_string(),
        String::new(),
        "If this evaluation exposed a durable agent-side lesson, record it with `agent-canon k add <topic> --stdin` or `agent-canon f add <topic> --stdin` and cite the evidence. If the lesson requires a durable process change, update the relevant skill, config, or workflow before marking the monitoring decision as applied. Do not copy raw chat.".to_string(),
        String::new(),
    ]
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum ReportInput {
    RunId(String),
    ReportDir(PathBuf),
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CliArgs {
    input: ReportInput,
    report_root: Option<PathBuf>,
    workspace_root: PathBuf,
    output: PathBuf,
    runtime_root: Option<PathBuf>,
    behavior_manifest: PathBuf,
    write: bool,
    min_score: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum CliParseError {
    Help,
    Invalid(String),
}

fn usage() -> &'static str {
    "usage: agent-canon run-evaluation (--run-id <run-id>|--report-dir <path>) [--report-root <path>] [--workspace-root <path>] [--output <path>] [--runtime-root <path>] [--behavior-manifest <path>] [--min-score <score>] [--write]"
}

fn parse_cli_args(args: &[String]) -> Result<CliArgs, CliParseError> {
    let mut run_id: Option<String> = None;
    let mut report_dir: Option<PathBuf> = None;
    let mut report_root = None;
    let mut workspace_root = PathBuf::from(".");
    let mut output = PathBuf::from("agent_evaluation.md");
    let mut runtime_root = None;
    let mut behavior_manifest = eval_manifest_path("agent_behavior_eval.toml");
    let mut write = false;
    let mut min_score = DEFAULT_MIN_SCORE;
    let mut index = 0;
    while index < args.len() {
        let option = args[index].as_str();
        if option == "--help" || option == "-h" {
            return Err(CliParseError::Help);
        }
        let value = |name: &str, index: usize| -> Result<&str, CliParseError> {
            args.get(index + 1)
                .map(String::as_str)
                .ok_or_else(|| CliParseError::Invalid(format!("{name} requires a value")))
        };
        match option {
            "--run-id" => {
                if run_id.is_some() || report_dir.is_some() {
                    return Err(CliParseError::Invalid(
                        "--run-id and --report-dir are mutually exclusive".to_string(),
                    ));
                }
                run_id = Some(value(option, index)?.to_string());
                index += 2;
            }
            "--report-dir" => {
                if report_dir.is_some() || run_id.is_some() {
                    return Err(CliParseError::Invalid(
                        "--run-id and --report-dir are mutually exclusive".to_string(),
                    ));
                }
                report_dir = Some(PathBuf::from(value(option, index)?));
                index += 2;
            }
            "--report-root" => {
                report_root = Some(PathBuf::from(value(option, index)?));
                index += 2;
            }
            "--workspace-root" => {
                workspace_root = PathBuf::from(value(option, index)?);
                index += 2;
            }
            "--output" => {
                output = PathBuf::from(value(option, index)?);
                index += 2;
            }
            "--runtime-root" => {
                runtime_root = Some(PathBuf::from(value(option, index)?));
                index += 2;
            }
            "--behavior-manifest" => {
                behavior_manifest = PathBuf::from(value(option, index)?);
                index += 2;
            }
            "--min-score" => {
                let raw = value(option, index)?;
                min_score = raw.parse::<i64>().map_err(|_| {
                    CliParseError::Invalid("--min-score must be an integer".to_string())
                })?;
                index += 2;
            }
            "--write" => {
                if write {
                    return Err(CliParseError::Invalid(
                        "--write may only be specified once".to_string(),
                    ));
                }
                write = true;
                index += 1;
            }
            other => return Err(CliParseError::Invalid(format!("unknown argument {other}"))),
        }
    }
    let input = match (run_id, report_dir) {
        (Some(run_id), None) if !run_id.is_empty() => ReportInput::RunId(run_id),
        (None, Some(report_dir)) => ReportInput::ReportDir(report_dir),
        (None, None) => {
            return Err(CliParseError::Invalid(
                "one of --run-id or --report-dir is required".to_string(),
            ))
        }
        _ => {
            return Err(CliParseError::Invalid(
                "--run-id must be non-empty".to_string(),
            ))
        }
    };
    Ok(CliArgs {
        input,
        report_root,
        workspace_root,
        output,
        runtime_root,
        behavior_manifest,
        write,
        min_score,
    })
}

fn lexical_absolute(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|error| format!("cannot read current directory: {error}"))?
            .join(path)
    };
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::RootDir | Component::Prefix(_) => normalized.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            Component::Normal(part) => normalized.push(part),
        }
    }
    Ok(normalized)
}

fn resolve_existing_or_lexical(path: &Path) -> Result<PathBuf, String> {
    let absolute = lexical_absolute(path)?;
    Ok(fs::canonicalize(&absolute).unwrap_or(absolute))
}

fn source_root() -> Result<PathBuf, String> {
    let crate_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    fs::canonicalize(crate_root.join("../../../../"))
        .map_err(|error| format!("AgentCanon source root unavailable: {error}"))
}

fn nearest_existing_directory(path: &Path) -> Result<PathBuf, String> {
    let mut current = path.to_path_buf();
    while !current.is_dir() {
        if !current.pop() {
            return Err(format!(
                "no existing parent directory for {}",
                path.display()
            ));
        }
    }
    fs::canonicalize(current).map_err(|error| format!("cannot resolve report root: {error}"))
}

fn runtime_boundary_for_report_root(
    source: &Path,
    report_root: Option<&Path>,
    create: bool,
) -> Result<(RuntimeArtifactBoundary, PathBuf), String> {
    let declared = report_root.unwrap_or(Path::new("reports/agents"));
    let env_runtime = env::var_os(RUNTIME_ROOT_ENV).filter(|value| !value.is_empty());
    if env_runtime.is_some() || !declared.is_absolute() {
        let boundary = RuntimeArtifactBoundary::for_source(source, None, create)?;
        let resolved = boundary.resolve(declared)?;
        return Ok((boundary, resolved));
    }
    let parent = nearest_existing_directory(declared)?;
    let boundary = RuntimeArtifactBoundary::for_source(source, Some(&parent), false)?;
    let resolved = boundary.resolve(declared)?;
    Ok((boundary, resolved))
}

pub fn run_cli(args: &[String]) -> i32 {
    let parsed = match parse_cli_args(args) {
        Ok(args) => args,
        Err(CliParseError::Help) => {
            println!(
                "{}\n\nEvaluate one run bundle and produce agent feedback actions.",
                usage()
            );
            return 0;
        }
        Err(CliParseError::Invalid(message)) => {
            eprintln!("AGENT_EVALUATION_ERROR={message}");
            eprintln!("{}", usage());
            return 2;
        }
    };
    let source = match source_root() {
        Ok(source) => source,
        Err(error) => {
            eprintln!("AGENT_EVALUATION_ERROR={error}");
            return 2;
        }
    };
    let workspace_root = match resolve_existing_or_lexical(&parsed.workspace_root) {
        Ok(root) => root,
        Err(error) => {
            eprintln!("AGENT_EVALUATION_ERROR={error}");
            return 2;
        }
    };
    let mut output_boundary = None;
    let mut output_path = parsed.output.clone();
    if parsed.write {
        let boundary = match RuntimeArtifactBoundary::for_source(
            &workspace_root,
            parsed.runtime_root.as_deref(),
            true,
        ) {
            Ok(boundary) => boundary,
            Err(error) => {
                eprintln!("agent-canon run-evaluation: runtime_root_required: {error}");
                return 2;
            }
        };
        output_path = match boundary.resolve(&parsed.output) {
            Ok(path) => path,
            Err(error) => {
                eprintln!("AGENT_EVALUATION_ERROR={error}");
                return 2;
            }
        };
        output_boundary = Some(boundary);
    }
    let report_dir = match &parsed.input {
        ReportInput::ReportDir(path) => match resolve_existing_or_lexical(path) {
            Ok(path) => path,
            Err(error) => {
                eprintln!("AGENT_EVALUATION_ERROR={error}");
                return 2;
            }
        },
        ReportInput::RunId(run_id) => {
            if let Err(problem) = ArtifactName::parse(run_id) {
                eprintln!("AGENT_EVALUATION_ERROR=invalid_run_id:{}", problem.detail);
                return 2;
            }
            let (boundary, report_root) = match runtime_boundary_for_report_root(
                &source,
                parsed.report_root.as_deref(),
                parsed.write,
            ) {
                Ok(value) => value,
                Err(error) => {
                    eprintln!("agent-canon run-evaluation: runtime_root_required: {error}");
                    return 2;
                }
            };
            match boundary.resolve(&report_root.join(run_id)) {
                Ok(path) => path,
                Err(error) => {
                    eprintln!("AGENT_EVALUATION_ERROR={error}");
                    return 2;
                }
            }
        }
    };
    let behavior_manifest = resolve_eval_manifest(&workspace_root, &parsed.behavior_manifest);
    let behavior_criteria = match load_behavior_manifest(&behavior_manifest) {
        Ok(criteria) => criteria,
        Err(error) => {
            eprintln!("AGENT_EVALUATION_ERROR={error}");
            return 2;
        }
    };
    let report = match evaluate_run(&report_dir, &behavior_criteria, &source, parsed.min_score) {
        Ok(report) => report,
        Err(error) => {
            eprintln!("AGENT_EVALUATION_ERROR={error}");
            return 2;
        }
    };
    if let Some(boundary) = output_boundary {
        if let Err(error) = boundary.atomic_write_text(&output_path, &report.markdown, 0o600) {
            eprintln!("AGENT_EVALUATION_ERROR={error}");
            return 2;
        }
    }
    println!("AGENT_EVALUATION_REPORT={}", output_path.display());
    println!("AGENT_EVALUATION_STATUS={}", report.status);
    println!("AGENT_EVALUATION_SCORE={}", report.score);
    println!("AGENT_EVALUATION_MAX_SCORE={}", report.max_score);
    println!("AGENT_EVALUATION_THRESHOLD={}", parsed.min_score);
    println!(
        "AGENT_EVALUATION_FEEDBACK_ACTIONS_OPEN={}",
        report.blockers.len()
    );
    if !report.blockers.is_empty() {
        println!("AGENT_EVALUATION_BLOCKERS={}", report.blockers.join("|"));
        return 1;
    }
    0
}
