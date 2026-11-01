// @dependency-start
// contract implementation
// responsibility Detects structural project-skill lanes and same-intent validation repair evidence.
// upstream implementation ../../../../../tools/agent/skills/skill_lane_detector.py owns the current Python matching contract.
// upstream implementation ../../../../../tools/agent/orchestration/prompt_classifier.py consumes injected SkillLaneEvidence.
// upstream implementation python_text.rs owns Python-compatible whitespace.
// downstream implementation ../tests/skill_lane_detector_native.rs checks frozen CPython 3.12.3 lane outputs.
// downstream reference ../../../../../tests/fixtures/skill_lane_detector/python_golden.json freezes old detector inputs and outputs.
// @dependency-end
//! Pure structural skill-lane and validation-repair evidence detection.

use crate::python_json::JsonString;
use icu_casemap::CaseMapper;

#[derive(Clone, Copy)]
struct EvidenceCategoryDefinition {
    name: &'static str,
    groups: &'static [&'static [&'static str]],
}

#[derive(Clone, Copy)]
struct StructuralSkillLaneConceptDefinition {
    name: &'static str,
    required_evidence_categories: &'static [&'static str],
    route_skills: &'static [&'static str],
    evidence_groups: &'static [EvidenceCategoryDefinition],
}

#[derive(Clone, Copy)]
struct ValidationFailureRepairConceptDefinition {
    name: &'static str,
    required_evidence_categories: &'static [&'static str],
    owner_skill: &'static str,
    secondary_skills: &'static [&'static str],
    evidence_groups: &'static [EvidenceCategoryDefinition],
}

const PROJECT_SKILL_LANE_CONCEPTS: &[StructuralSkillLaneConceptDefinition] =
    &[StructuralSkillLaneConceptDefinition {
        name: "repository_skill_discovery_surface",
        required_evidence_categories: &["project_owner", "skill_lane_surface"],
        route_skills: &["task-routing", "structure-refactor"],
        evidence_groups: &[
            EvidenceCategoryDefinition {
                name: "project_owner",
                groups: &[
                    &[".codex/personal/skills"],
                    &["parent", "repo"],
                    &["parent-repo"],
                    &["project-owned"],
                    &["repo-specific"],
                    &["親レポ"],
                ],
            },
            EvidenceCategoryDefinition {
                name: "skill_lane_surface",
                groups: &[
                    &["skill", "lane"],
                    &["skill", "surface"],
                    &["skill", "discovery"],
                    &["automatic", "discovery"],
                    &["skill.md"],
                    &["固有スキル"],
                    &["スキル", "置"],
                ],
            },
            EvidenceCategoryDefinition {
                name: "runtime_boundary_surface",
                groups: &[
                    &[".codex", ".agents"],
                    &[".codex/config.toml"],
                    &[".codex/personal/skills"],
                    &["shared", "public", "catalog"],
                ],
            },
        ],
    }];

const VALIDATION_FAILURE_REPAIR_CONCEPTS: &[ValidationFailureRepairConceptDefinition] =
    &[ValidationFailureRepairConceptDefinition {
        name: "validation_failure_same_intent_repair",
        required_evidence_categories: &["validation_failure"],
        owner_skill: "codex-task-workflow",
        secondary_skills: &["test-design"],
        evidence_groups: &[EvidenceCategoryDefinition {
            name: "validation_failure",
            groups: &[
                &["failed", "validation"],
                &["validation", "failure"],
                &["validation", "failing"],
                &["failing", "test"],
                &["failing", "tests"],
                &["tests", "failing"],
                &["failed", "test"],
                &["failed", "tests"],
                &["test", "failure"],
                &["tests", "failure"],
                &["failing", "contract"],
                &["cause_classification"],
                &["same-intent", "repair"],
                &["preserved-intent", "repair"],
            ],
        }],
    }];

/// One evidence category and the alternative term groups that establish it.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EvidenceGroupsByCategory {
    pub category: JsonString,
    pub groups: Vec<Vec<JsonString>>,
}

/// Shared concept shape used by the evidence-category matcher.
pub trait EvidenceConcept {
    fn required_evidence_categories(&self) -> &[JsonString];
    fn evidence_groups(&self) -> &[EvidenceGroupsByCategory];
}

/// One structural routing concept with its evidence contract.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct StructuralSkillLaneConcept {
    pub name: JsonString,
    pub required_evidence_categories: Vec<JsonString>,
    pub route_skills: Vec<JsonString>,
    pub evidence_groups: Vec<EvidenceGroupsByCategory>,
}

impl EvidenceConcept for StructuralSkillLaneConcept {
    fn required_evidence_categories(&self) -> &[JsonString] {
        &self.required_evidence_categories
    }

    fn evidence_groups(&self) -> &[EvidenceGroupsByCategory] {
        &self.evidence_groups
    }
}

/// One matched structural skill-lane concept.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct StructuralSkillLaneMatch {
    pub concept: StructuralSkillLaneConcept,
    pub observed_evidence_categories: Vec<JsonString>,
}

/// One validation-failure repair concept with its owner and secondary skills.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ValidationFailureRepairConcept {
    pub name: JsonString,
    pub required_evidence_categories: Vec<JsonString>,
    pub owner_skill: JsonString,
    pub secondary_skills: Vec<JsonString>,
    pub evidence_groups: Vec<EvidenceGroupsByCategory>,
}

impl EvidenceConcept for ValidationFailureRepairConcept {
    fn required_evidence_categories(&self) -> &[JsonString] {
        &self.required_evidence_categories
    }

    fn evidence_groups(&self) -> &[EvidenceGroupsByCategory] {
        &self.evidence_groups
    }
}

/// One matched validation-failure repair concept.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ValidationFailureRepairMatch {
    pub concept: ValidationFailureRepairConcept,
    pub observed_evidence_categories: Vec<JsonString>,
}

/// One observed lane record passed into prompt classification.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SkillLaneEvidence {
    pub schema: JsonString,
    pub lane: JsonString,
    pub route_skills: Vec<JsonString>,
    pub evidence_categories: Vec<JsonString>,
    pub status: JsonString,
    pub source: JsonString,
}

impl StructuralSkillLaneMatch {
    /// Return the stable route reason used by tests and hook evidence.
    pub fn reason(&self) -> String {
        format!(
            "structural_concept={};required_evidence={};observed_evidence={}",
            string_text(&self.concept.name),
            joined_strings(&self.concept.required_evidence_categories),
            joined_strings(&self.observed_evidence_categories),
        )
    }
}

impl ValidationFailureRepairMatch {
    /// Return the stable same-intent repair reason used by the evaluator.
    pub fn reason(&self) -> String {
        format!(
            "structural_concept={};required_evidence={};observed_evidence={};repair_contract=classify cause then proceed to owning repair surface;tests_are=validation_control_surface_not_default_work_owner",
            string_text(&self.concept.name),
            joined_strings(&self.concept.required_evidence_categories),
            joined_strings(&self.observed_evidence_categories),
        )
    }
}

fn materialize_evidence_groups(
    definitions: &[EvidenceCategoryDefinition],
) -> Vec<EvidenceGroupsByCategory> {
    definitions
        .iter()
        .map(|definition| EvidenceGroupsByCategory {
            category: JsonString::from_text(definition.name),
            groups: definition
                .groups
                .iter()
                .map(|group| {
                    group
                        .iter()
                        .map(|term| JsonString::from_text(term))
                        .collect()
                })
                .collect(),
        })
        .collect()
}

fn materialize_structural_concept(
    definition: &StructuralSkillLaneConceptDefinition,
) -> StructuralSkillLaneConcept {
    StructuralSkillLaneConcept {
        name: JsonString::from_text(definition.name),
        required_evidence_categories: definition
            .required_evidence_categories
            .iter()
            .map(|category| JsonString::from_text(category))
            .collect(),
        route_skills: definition
            .route_skills
            .iter()
            .map(|skill| JsonString::from_text(skill))
            .collect(),
        evidence_groups: materialize_evidence_groups(definition.evidence_groups),
    }
}

fn materialize_repair_concept(
    definition: &ValidationFailureRepairConceptDefinition,
) -> ValidationFailureRepairConcept {
    ValidationFailureRepairConcept {
        name: JsonString::from_text(definition.name),
        required_evidence_categories: definition
            .required_evidence_categories
            .iter()
            .map(|category| JsonString::from_text(category))
            .collect(),
        owner_skill: JsonString::from_text(definition.owner_skill),
        secondary_skills: definition
            .secondary_skills
            .iter()
            .map(|skill| JsonString::from_text(skill))
            .collect(),
        evidence_groups: materialize_evidence_groups(definition.evidence_groups),
    }
}

fn fold_json_string(value: &JsonString) -> JsonString {
    let case_mapper = CaseMapper::new();
    let mut output = Vec::new();
    let mut valid_run = String::new();
    for &codepoint in &value.0 {
        if let Some(character) = char::from_u32(codepoint) {
            valid_run.push(character);
        } else {
            output.extend(case_mapper.fold_string(&valid_run).chars().map(u32::from));
            valid_run.clear();
            output.push(codepoint);
        }
    }
    output.extend(case_mapper.fold_string(&valid_run).chars().map(u32::from));
    JsonString(output)
}

fn contains_substring(text: &JsonString, needle: &JsonString) -> bool {
    needle.is_empty()
        || (needle.0.len() <= text.0.len()
            && text
                .0
                .windows(needle.0.len())
                .any(|window| window == needle.0))
}

fn string_text(value: &JsonString) -> String {
    value.to_text().unwrap_or_default()
}

fn joined_strings(values: &[JsonString]) -> String {
    values.iter().map(string_text).collect::<Vec<_>>().join(",")
}

pub fn text_matches_evidence_group(text: &JsonString, group: &[JsonString]) -> bool {
    group
        .iter()
        .all(|term| contains_substring(text, &fold_json_string(term)))
}

pub fn observed_evidence_categories(
    text: &JsonString,
    concept: &dyn EvidenceConcept,
) -> Vec<JsonString> {
    concept
        .evidence_groups()
        .iter()
        .filter(|category| {
            category
                .groups
                .iter()
                .any(|group| text_matches_evidence_group(text, group))
        })
        .map(|category| category.category.clone())
        .collect()
}

pub fn structural_skill_lane_concept_matches(text: &JsonString) -> Vec<StructuralSkillLaneMatch> {
    let folded = fold_json_string(text);
    PROJECT_SKILL_LANE_CONCEPTS
        .iter()
        .filter_map(|definition| {
            let concept = materialize_structural_concept(definition);
            let observed = observed_evidence_categories(&folded, &concept);
            concept
                .required_evidence_categories
                .iter()
                .all(|required| observed.contains(required))
                .then_some(StructuralSkillLaneMatch {
                    concept,
                    observed_evidence_categories: observed,
                })
        })
        .collect()
}

pub fn validation_failure_repair_concept_matches(
    text: &JsonString,
) -> Vec<ValidationFailureRepairMatch> {
    let folded = fold_json_string(text);
    VALIDATION_FAILURE_REPAIR_CONCEPTS
        .iter()
        .filter_map(|definition| {
            let concept = materialize_repair_concept(definition);
            let observed = observed_evidence_categories(&folded, &concept);
            concept
                .required_evidence_categories
                .iter()
                .all(|required| observed.contains(required))
                .then_some(ValidationFailureRepairMatch {
                    concept,
                    observed_evidence_categories: observed,
                })
        })
        .collect()
}

pub fn detect_skill_lane_evidence(text: &JsonString) -> Vec<SkillLaneEvidence> {
    structural_skill_lane_concept_matches(text)
        .into_iter()
        .map(|matched| SkillLaneEvidence {
            schema: JsonString::from_text("agent-canon.skill-lane.v1"),
            lane: matched.concept.name,
            route_skills: matched.concept.route_skills,
            evidence_categories: matched.observed_evidence_categories,
            status: JsonString::from_text("observed"),
            source: JsonString::from_text("prompt_classifier"),
        })
        .collect()
}
