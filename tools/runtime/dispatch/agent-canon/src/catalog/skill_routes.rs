// @dependency-start
// contract implementation
// responsibility Owns typed skill-route catalog loading, dependency validation, and explicit capability decisions.
// upstream design ../../../../../../agents/skills/catalog.yaml canonical public skill-route inputs
// upstream design ../../../../../../agents/skills/skill-dependencies.yaml ordered dependency inputs
// upstream implementation ../path_expansion.rs shared user-home expansion
// upstream implementation ../path_resolution.rs shared non-strict filesystem resolution
// upstream implementation ../python_text.rs Python-compatible route text normalization
// downstream implementation ../main.rs native capability-route command
// downstream implementation ../../../../../../tools/agent/orchestration/route.py public route facade
// downstream implementation ../../../../../../tests/agent_tools/test_route.py capability route contract tests
// @dependency-end

use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::env;
use std::fmt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::LazyLock;

use crate::agent_canon_source_root::has_catalog;
use regex::Regex;
use serde::ser::SerializeMap;
use serde::{Serialize, Serializer};
use serde_json::{json, Value as JsonValue};
use yaml_rust2::{Yaml, YamlLoader};

pub type CapabilityId = String;

pub const SKILL_CATALOG_PATH: &str = "agents/skills/catalog.yaml";
pub const SKILL_DEPENDENCY_MAP_PATH: &str = "agents/skills/skill-dependencies.yaml";
pub const TOOL_CATALOG_PATH: &str = "tools/catalog.yaml";
pub const CATALOG_SCHEMA_ROOT: &str = "schemas/agent-canon";
pub const PRIVATE_SKILL_PREFIX: &str = "_";
pub const CAPABILITY_ROUTE_SCHEMA: &str = "agent_canon.route.capability_route.v1";
pub const CAPABILITY_FORMAT_VALUES: [&str; 3] = ["text", "json", "markdown"];
pub const CAPABILITY_MODE_VALUES: [&str; 2] = ["routing-only", "repo-changing"];
pub const CAPABILITY_RISK_VALUES: [&str; 5] = ["routine", "focused", "profile", "shared", "large"];

pub const CATALOG_SCHEMA_PATHS: [(&str, &str); 3] = [
    (
        SKILL_CATALOG_PATH,
        "schemas/agent-canon/skill-catalog.schema.json",
    ),
    (
        SKILL_DEPENDENCY_MAP_PATH,
        "schemas/agent-canon/skill-dependencies.schema.json",
    ),
    (
        TOOL_CATALOG_PATH,
        "schemas/agent-canon/tool-catalog.schema.json",
    ),
];

/// Capability identifiers contain lowercase ASCII letters, digits, and underscores.
pub static CAPABILITY_ID_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\A[a-z0-9_]+\z").expect("static capability id regex"));

/// An insertion-ordered map with no public mutation operations.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OrderedMap<K, V> {
    entries: Vec<(K, V)>,
}

impl<K: Serialize + Eq, V: Serialize> Serialize for OrderedMap<K, V> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut map = serializer.serialize_map(Some(self.entries.len()))?;
        for (key, value) in &self.entries {
            map.serialize_entry(key, value)?;
        }
        map.end()
    }
}

impl<K: Eq, V> OrderedMap<K, V> {
    fn new() -> Self {
        Self {
            entries: Vec::new(),
        }
    }

    fn insert(&mut self, key: K, value: V) {
        if let Some(index) = self
            .entries
            .iter()
            .position(|(candidate, _)| candidate == &key)
        {
            self.entries[index].1 = value;
        } else {
            self.entries.push((key, value));
        }
    }

    pub fn get(&self, key: &K) -> Option<&V> {
        self.entries
            .iter()
            .find(|(candidate, _)| candidate == key)
            .map(|(_, value)| value)
    }

    pub fn contains_key(&self, key: &K) -> bool {
        self.get(key).is_some()
    }
    pub fn iter(&self) -> impl Iterator<Item = (&K, &V)> {
        self.entries.iter().map(|(key, value)| (key, value))
    }
    pub fn keys(&self) -> impl Iterator<Item = &K> {
        self.entries.iter().map(|(key, _)| key)
    }
    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.entries.iter().map(|(_, value)| value)
    }
    pub fn len(&self) -> usize {
        self.entries.len()
    }
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CapabilityRoute {
    pub skill: String,
    pub capability_id: CapabilityId,
    pub owner: String,
    pub phase: String,
    pub activation: String,
    pub exclusive: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct SkillOrderConstraint {
    pub before: String,
    pub after: String,
    pub reason: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct SkillDependencyRule {
    pub skill: String,
    pub responsibility_group: String,
    pub required_prerequisites: Vec<String>,
    pub routing_candidates: Vec<String>,
    pub successors: Vec<String>,
    pub order_constraints: Vec<SkillOrderConstraint>,
    pub parallel_independent: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct SkillRoutingRule {
    pub skill: String,
    pub canonical_doc: String,
    pub reason: String,
    pub stage_policy: String,
    pub triggers: Vec<Vec<String>>,
    pub capabilities: Vec<CapabilityRoute>,
    pub related_skills: Vec<String>,
    pub required_prerequisites: Vec<String>,
    pub successors: Vec<String>,
    pub order_constraints: Vec<SkillOrderConstraint>,
    pub parallel_independent: Vec<String>,
    pub responsibility_group: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CapabilityIndex {
    pub routes: OrderedMap<CapabilityId, CapabilityRoute>,
    pub rules_by_skill: OrderedMap<String, SkillRoutingRule>,
    pub owner_ambiguities: Vec<CapabilityId>,
    pub duplicate_definitions: Vec<CapabilityId>,
}

/// Raw argument validation result for explicit capability routing.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CapabilityPreflight {
    pub capability_ids: Vec<CapabilityId>,
    pub mode: String,
    pub output_format: String,
    pub error_code: String,
    pub root: Option<PathBuf>,
}

/// Stable output envelope for explicit capability routing.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct CapabilityRouteDecision {
    pub schema: String,
    pub route: String,
    pub mode: String,
    pub status: String,
    pub error_code: String,
    pub capability_ids: Vec<CapabilityId>,
    pub matches: Vec<CapabilityRoute>,
    pub skills: Vec<String>,
    pub active_skills: Vec<String>,
    pub deferred_skills: Vec<String>,
    pub related_skill_candidates: Vec<String>,
    pub related_skills: OrderedMap<String, Vec<String>>,
    pub reasons: Vec<String>,
}

/// One fixed invalid direct capability-match precondition error.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CapabilityRouteError {
    pub code: String,
}

impl CapabilityRouteError {
    fn new(code: impl Into<String>) -> Self {
        Self { code: code.into() }
    }
}

impl fmt::Display for CapabilityRouteError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.code)
    }
}

impl std::error::Error for CapabilityRouteError {}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CapabilityCatalogError {
    pub code: String,
}

impl CapabilityCatalogError {
    fn new(code: impl Into<String>) -> Self {
        Self { code: code.into() }
    }
}

impl fmt::Display for CapabilityCatalogError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.code)
    }
}

impl std::error::Error for CapabilityCatalogError {}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CapabilityRootError {
    pub code: String,
}

impl CapabilityRootError {
    fn new(code: impl Into<String>) -> Self {
        Self { code: code.into() }
    }
}

impl fmt::Display for CapabilityRootError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.code)
    }
}

impl std::error::Error for CapabilityRootError {}

fn yaml_mapping<'a>(value: &'a Yaml, field: &str) -> Result<Vec<(String, &'a Yaml)>, String> {
    let Some(hash) = value.as_hash() else {
        return Err(format!("{field} must be a mapping"));
    };
    let mut entries = Vec::with_capacity(hash.len());
    for (key, value) in hash {
        let Some(key) = key.as_str() else {
            return Err(format!("{field} must have string keys"));
        };
        entries.push((key.to_owned(), value));
    }
    Ok(entries)
}

fn yaml_get<'a>(value: &'a Yaml, key: &str) -> Option<&'a Yaml> {
    value
        .as_hash()?
        .iter()
        .find_map(|(candidate, item)| (candidate.as_str() == Some(key)).then_some(item))
}

fn yaml_string(value: &Yaml, field: &str) -> Result<String, String> {
    value
        .as_str()
        .map(str::to_owned)
        .ok_or_else(|| format!("{field} must be a string"))
}

fn yaml_sequence<'a>(value: Option<&'a Yaml>, field: &str) -> Result<&'a [Yaml], String> {
    value
        .and_then(Yaml::as_vec)
        .map(Vec::as_slice)
        .ok_or_else(|| format!("{field} must be a list"))
}

fn yaml_string_sequence(value: Option<&Yaml>, field: &str) -> Result<Vec<String>, String> {
    yaml_sequence(value, field)?
        .iter()
        .enumerate()
        .map(|(index, item)| yaml_string(item, &format!("{field}[{index}]")))
        .collect()
}

pub fn load_skill_catalog(root: &Path) -> Result<Yaml, String> {
    let path = root.join(SKILL_CATALOG_PATH);
    let text = std::fs::read_to_string(&path).map_err(|error| error.to_string())?;
    let mut documents = YamlLoader::load_from_str(&text)
        .map_err(|error| format!("{SKILL_CATALOG_PATH} YAML parse failed: {error}"))?;
    if documents.len() > 1 {
        return Err(format!(
            "{SKILL_CATALOG_PATH} YAML parse failed: expected a single YAML document"
        ));
    }
    let document = documents.pop().unwrap_or(Yaml::Null);
    if document.as_hash().is_none() {
        return Err(format!("{SKILL_CATALOG_PATH} must parse as a mapping"));
    }
    Ok(document)
}

fn skill_ids_from_catalog(data: &Yaml) -> Result<Vec<String>, String> {
    let families = yaml_sequence(yaml_get(data, "skill_families"), "skill_families")?;
    let mut ids = Vec::new();
    for (index, entry) in families.iter().enumerate() {
        yaml_mapping(entry, &format!("skill_families[{index}]"))?;
        let skill_id = yaml_get(entry, "id")
            .ok_or_else(|| format!("skill_families[{index}].id is required"))?;
        let skill_id = yaml_string(skill_id, &format!("skill_families[{index}].id"))?;
        if skill_id.starts_with(PRIVATE_SKILL_PREFIX) {
            return Err(format!(
                "skill_families[{index}].id must be public: {skill_id}"
            ));
        }
        if ids.contains(&skill_id) {
            return Err(format!("duplicate skill catalog id: {skill_id}"));
        }
        ids.push(skill_id);
    }
    Ok(ids)
}

fn dependency_order_constraints(
    value: Option<&Yaml>,
    skill: &str,
) -> Result<Vec<SkillOrderConstraint>, String> {
    let field = format!("{skill}.order_constraints");
    yaml_sequence(value, &field)?
        .iter()
        .enumerate()
        .map(|(index, item)| {
            yaml_mapping(item, &format!("{field}[{index}]"))?;
            Ok(SkillOrderConstraint {
                before: yaml_string(
                    yaml_get(item, "before")
                        .ok_or_else(|| format!("{field}[{index}].before is required"))?,
                    &format!("{field}[{index}].before"),
                )?,
                after: yaml_string(
                    yaml_get(item, "after")
                        .ok_or_else(|| format!("{field}[{index}].after is required"))?,
                    &format!("{field}[{index}].after"),
                )?,
                reason: yaml_string(
                    yaml_get(item, "reason")
                        .ok_or_else(|| format!("{field}[{index}].reason is required"))?,
                    &format!("{field}[{index}].reason"),
                )?,
            })
        })
        .collect()
}

fn dependency_edges(
    rules: &OrderedMap<String, SkillDependencyRule>,
) -> OrderedMap<String, Vec<String>> {
    let mut edges = OrderedMap::new();
    for (skill, _) in rules.iter() {
        edges.insert(skill.clone(), Vec::new());
    }
    for rule in rules.values() {
        for prerequisite in &rule.required_prerequisites {
            push_unique(
                edges_value_mut(&mut edges, prerequisite),
                rule.skill.clone(),
            );
        }
        for successor in &rule.successors {
            push_unique(edges_value_mut(&mut edges, &rule.skill), successor.clone());
        }
        for constraint in &rule.order_constraints {
            push_unique(
                edges_value_mut(&mut edges, &constraint.before),
                constraint.after.clone(),
            );
        }
    }
    edges
}

fn edges_value_mut<'a>(
    edges: &'a mut OrderedMap<String, Vec<String>>,
    key: &str,
) -> &'a mut Vec<String> {
    if !edges.entries.iter().any(|(candidate, _)| candidate == key) {
        edges.insert(key.to_owned(), Vec::new());
    }
    edges
        .entries
        .iter_mut()
        .find(|(candidate, _)| candidate == key)
        .map(|(_, value)| value)
        .expect("edge key was inserted")
}

fn push_unique(values: &mut Vec<String>, value: String) {
    if !values.contains(&value) {
        values.push(value);
    }
}

fn reachable(edges: &OrderedMap<String, Vec<String>>, source: &str, target: &str) -> bool {
    let mut pending = edges.get(&source.to_owned()).cloned().unwrap_or_default();
    let mut seen = BTreeSet::new();
    while let Some(current) = pending.pop() {
        if current == target {
            return true;
        }
        if !seen.insert(current.clone()) {
            continue;
        }
        if let Some(next) = edges.get(&current) {
            pending.extend(next.iter().cloned());
        }
    }
    false
}

fn validate_dependency_graph(
    rules: &OrderedMap<String, SkillDependencyRule>,
) -> Result<(), String> {
    let edges = dependency_edges(rules);
    for rule in rules.values() {
        for constraint in &rule.order_constraints {
            if constraint.before == constraint.after
                || reachable(&edges, &constraint.after, &constraint.before)
            {
                return Err(format!(
                    "skill-dependency-map-order-contradiction:{}:{}",
                    constraint.before, constraint.after
                ));
            }
        }
    }
    let mut indegree: BTreeMap<String, usize> =
        rules.keys().map(|skill| (skill.clone(), 0)).collect();
    for targets in edges.values() {
        for target in targets {
            *indegree.entry(target.clone()).or_default() += 1;
        }
    }
    let mut ready: Vec<String> = indegree
        .iter()
        .filter_map(|(skill, degree)| (*degree == 0).then_some(skill.clone()))
        .collect();
    let mut visited = 0;
    while let Some(current) = ready.pop() {
        visited += 1;
        for target in edges.get(&current).into_iter().flatten() {
            if let Some(degree) = indegree.get_mut(target) {
                *degree -= 1;
                if *degree == 0 {
                    ready.push(target.clone());
                }
            }
        }
    }
    if visited != rules.len() {
        return Err("skill-dependency-map-cycle".to_owned());
    }
    for rule in rules.values() {
        for parallel in &rule.parallel_independent {
            if parallel == &rule.skill
                || reachable(&edges, &rule.skill, parallel)
                || reachable(&edges, parallel, &rule.skill)
            {
                return Err(format!(
                    "skill-dependency-map-parallel-contradiction:{}:{parallel}",
                    rule.skill
                ));
            }
            if !rules
                .get(parallel)
                .is_some_and(|other| other.parallel_independent.contains(&rule.skill))
            {
                return Err(format!(
                    "skill-dependency-map-parallel-not-symmetric:{}:{parallel}",
                    rule.skill
                ));
            }
        }
    }
    Ok(())
}

/// Loads and validates the complete public skill dependency dictionary.
pub fn load_skill_dependency_map(
    root: &Path,
    public_skill_ids: Option<&[String]>,
) -> Result<OrderedMap<String, SkillDependencyRule>, String> {
    let path = root.join(SKILL_DEPENDENCY_MAP_PATH);
    let text =
        std::fs::read_to_string(path).map_err(|_| "skill-dependency-map-unavailable".to_owned())?;
    let mut documents = YamlLoader::load_from_str(&text)
        .map_err(|_| "skill-dependency-map-unavailable".to_owned())?;
    if documents.len() > 1 {
        return Err("skill-dependency-map-unavailable".to_owned());
    }
    let raw = documents.pop().unwrap_or(Yaml::Null);
    if raw.as_hash().is_none() {
        return Err("skill-dependency-map-unavailable".to_owned());
    }
    let data = yaml_mapping(&raw, SKILL_DEPENDENCY_MAP_PATH)?;
    let dependency_data = yaml_get(&raw, "skill_dependencies")
        .ok_or_else(|| "skill_dependencies must be a mapping".to_owned())?;
    let dependency_entries = yaml_mapping(dependency_data, "skill_dependencies")?;
    let loaded_ids = if public_skill_ids.filter(|ids| !ids.is_empty()).is_none() {
        Some(skill_ids_from_catalog(&load_skill_catalog(root)?)?)
    } else {
        None
    };
    let expected_ids = public_skill_ids
        .filter(|ids| !ids.is_empty())
        .unwrap_or_else(|| {
            loaded_ids
                .as_deref()
                .expect("fallback skill ids were loaded")
        });
    let observed_ids: Vec<String> = dependency_entries
        .iter()
        .map(|(key, _)| key.clone())
        .collect();
    let missing: Vec<&str> = expected_ids
        .iter()
        .filter(|skill| !observed_ids.contains(skill))
        .map(String::as_str)
        .collect();
    let extra: Vec<&str> = observed_ids
        .iter()
        .filter(|skill| !expected_ids.contains(skill))
        .map(String::as_str)
        .collect();
    if !missing.is_empty() || !extra.is_empty() {
        return Err(format!(
            "skill-dependency-map-key-mismatch:missing={}:extra={}",
            if missing.is_empty() {
                "-".to_owned()
            } else {
                missing.join(",")
            },
            if extra.is_empty() {
                "-".to_owned()
            } else {
                extra.join(",")
            }
        ));
    }
    let mut rules = OrderedMap::new();
    for skill in expected_ids {
        let mapping = dependency_entries
            .iter()
            .find(|(key, _)| key == skill)
            .map(|(_, value)| *value)
            .ok_or_else(|| format!("skill-dependency-map-key-mismatch:missing={skill}:extra=-"))?;
        let responsibility_group = yaml_string(
            yaml_get(mapping, "responsibility_group")
                .ok_or_else(|| format!("{skill}.responsibility_group is required"))?,
            &format!("{skill}.responsibility_group"),
        )?;
        rules.insert(
            skill.clone(),
            SkillDependencyRule {
                skill: skill.clone(),
                responsibility_group,
                required_prerequisites: yaml_string_sequence(
                    yaml_get(mapping, "required_prerequisites"),
                    &format!("{skill}.required_prerequisites"),
                )?,
                routing_candidates: match yaml_get(mapping, "routing_candidates") {
                    Some(Yaml::Null) | None => Vec::new(),
                    Some(value) => {
                        yaml_string_sequence(Some(value), &format!("{skill}.routing_candidates"))?
                    }
                },
                successors: yaml_string_sequence(
                    yaml_get(mapping, "successors"),
                    &format!("{skill}.successors"),
                )?,
                order_constraints: dependency_order_constraints(
                    yaml_get(mapping, "order_constraints"),
                    skill,
                )?,
                parallel_independent: yaml_string_sequence(
                    yaml_get(mapping, "parallel_independent"),
                    &format!("{skill}.parallel_independent"),
                )?,
            },
        );
    }
    for rule in rules.values() {
        for (field, references) in [
            ("required_prerequisites", &rule.required_prerequisites),
            ("routing_candidates", &rule.routing_candidates),
            ("successors", &rule.successors),
            ("parallel_independent", &rule.parallel_independent),
        ] {
            for reference in references {
                if !rules.contains_key(reference) {
                    return Err(format!(
                        "skill-dependency-map-unknown-reference:{}:{field}:{reference}",
                        rule.skill
                    ));
                }
                if reference == &rule.skill {
                    return Err(format!(
                        "skill-dependency-map-self-reference:{}:{field}",
                        rule.skill
                    ));
                }
            }
        }
        for constraint in &rule.order_constraints {
            for reference in [&constraint.before, &constraint.after] {
                if !rules.contains_key(reference) {
                    return Err(format!(
                        "skill-dependency-map-unknown-reference:{}:order_constraints:{reference}",
                        rule.skill
                    ));
                }
            }
        }
    }
    validate_dependency_graph(&rules)?;
    let _ = data;
    Ok(rules)
}

/// Returns catalog-ordered directed prerequisite and ordering edges.
pub fn build_skill_dependency_edges(
    rules: &OrderedMap<String, SkillDependencyRule>,
) -> OrderedMap<String, Vec<String>> {
    let edges = dependency_edges(rules);
    let mut ordered = OrderedMap::new();
    for skill in rules.keys() {
        let targets = rules
            .keys()
            .filter(|target| {
                edges
                    .get(skill)
                    .is_some_and(|values| values.contains(target))
            })
            .cloned()
            .collect();
        ordered.insert(skill.clone(), targets);
    }
    ordered
}

/// Expands required prerequisites and topologically orders selected skills.
pub fn derive_skill_invocation_order(
    skills: &[String],
    rules: &[SkillRoutingRule],
) -> Result<Vec<String>, String> {
    let mut by_skill = BTreeMap::new();
    for rule in rules {
        by_skill.insert(rule.skill.clone(), rule);
    }
    let mut selected: Vec<String> = Vec::new();
    let mut pending = Vec::new();
    for skill in skills {
        if !selected.contains(skill) {
            selected.push(skill.clone());
            pending.push(skill.clone());
        }
    }
    while let Some(skill) = pending.pop() {
        let Some(rule) = by_skill.get(&skill) else {
            return Err(format!("unknown-skill:{skill}"));
        };
        for prerequisite in &rule.required_prerequisites {
            if !selected.contains(prerequisite) {
                selected.push(prerequisite.clone());
                pending.push(prerequisite.clone());
            }
        }
    }
    let mut edges: BTreeMap<String, BTreeSet<String>> = selected
        .iter()
        .map(|skill| (skill.clone(), BTreeSet::new()))
        .collect();
    for skill in &selected {
        let rule = by_skill.get(skill).expect("selected skill was checked");
        for prerequisite in &rule.required_prerequisites {
            if edges.contains_key(prerequisite) {
                edges
                    .get_mut(prerequisite)
                    .expect("checked edge")
                    .insert(skill.clone());
            }
        }
        for successor in &rule.successors {
            if edges.contains_key(successor) {
                edges
                    .get_mut(skill)
                    .expect("selected edge")
                    .insert(successor.clone());
            }
        }
        for constraint in &rule.order_constraints {
            if edges.contains_key(&constraint.before) && edges.contains_key(&constraint.after) {
                edges
                    .get_mut(&constraint.before)
                    .expect("checked edge")
                    .insert(constraint.after.clone());
            }
        }
    }
    let mut indegree: BTreeMap<String, usize> =
        selected.iter().map(|skill| (skill.clone(), 0)).collect();
    for targets in edges.values() {
        for target in targets {
            *indegree.get_mut(target).expect("selected target") += 1;
        }
    }
    let order_index: BTreeMap<String, usize> = rules
        .iter()
        .enumerate()
        .map(|(index, rule)| (rule.skill.clone(), index))
        .collect();
    let mut ready: Vec<String> = indegree
        .iter()
        .filter_map(|(skill, degree)| (*degree == 0).then_some(skill.clone()))
        .collect();
    ready.sort_by_key(|skill| order_index[skill]);
    let mut result = Vec::new();
    while !ready.is_empty() {
        let current = ready.remove(0);
        result.push(current.clone());
        let mut targets: Vec<String> = edges[&current].iter().cloned().collect();
        targets.sort_by_key(|skill| order_index[skill]);
        for target in targets {
            let degree = indegree.get_mut(&target).expect("selected target");
            *degree -= 1;
            if *degree == 0 {
                ready.push(target);
            }
        }
        ready.sort_by_key(|skill| order_index[skill]);
    }
    if result.len() != selected.len() {
        return Err("skill-dependency-map-cycle".to_owned());
    }
    Ok(result)
}

/// Normalizes and validates one explicit capability identifier.
pub fn capability_id_from_raw(value: &str) -> Result<CapabilityId, String> {
    let raw = crate::python_text::python_strip(value);
    if raw.is_empty() || !CAPABILITY_ID_RE.is_match(raw) {
        return Err(format!("invalid-capability-id:{value}"));
    }
    Ok(raw.to_owned())
}

fn capability_catalog_error(skill: &str, field: &str) -> CapabilityCatalogError {
    CapabilityCatalogError::new(format!("capability-catalog-invalid:{skill}:{field}"))
}

/// Parses one catalog capability sequence into immutable route records.
pub fn capability_routes(
    value: Option<&Yaml>,
    field: &str,
    skill: &str,
) -> Result<Vec<CapabilityRoute>, CapabilityCatalogError> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    if matches!(value, Yaml::Null) {
        return Ok(Vec::new());
    }
    let Some(records) = value.as_vec() else {
        return Err(capability_catalog_error(skill, field));
    };
    let required = BTreeSet::from(["id", "owner", "phase", "activation", "exclusive"]);
    let mut routes = Vec::new();
    for (index, record) in records.iter().enumerate() {
        let record_field = format!("{field}[{index}]");
        let Some(entries) = record.as_hash() else {
            return Err(capability_catalog_error(skill, &record_field));
        };
        let keys: BTreeSet<&str> = entries.keys().filter_map(Yaml::as_str).collect();
        if entries.len() != required.len()
            || entries.keys().any(|key| key.as_str().is_none())
            || keys != required
        {
            return Err(capability_catalog_error(skill, &record_field));
        }
        let mut values = BTreeMap::new();
        for key in ["id", "owner", "phase", "activation"] {
            let value = yaml_get(record, key).and_then(Yaml::as_str);
            if value.is_none_or(|item| {
                item.trim().is_empty()
                    || !item.bytes().all(|byte| {
                        byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_'
                    })
            }) {
                return Err(capability_catalog_error(
                    skill,
                    &format!("{record_field}.{key}"),
                ));
            }
            values.insert(key, value.expect("validated string").to_owned());
        }
        let Some(exclusive) = yaml_get(record, "exclusive").and_then(Yaml::as_bool) else {
            return Err(capability_catalog_error(
                skill,
                &format!("{record_field}.exclusive"),
            ));
        };
        let raw_id = values.get("id").expect("required capability id");
        let capability_id = capability_id_from_raw(raw_id)
            .map_err(|_| capability_catalog_error(skill, &format!("{record_field}.id")))?;
        routes.push(CapabilityRoute {
            skill: skill.to_owned(),
            capability_id,
            owner: values.remove("owner").expect("validated owner"),
            phase: values.remove("phase").expect("validated phase"),
            activation: values.remove("activation").expect("validated activation"),
            exclusive,
        });
    }
    Ok(routes)
}

/// Copies related-skill values into an immutable insertion-ordered mapping.
pub fn freeze_related_skill_mapping(
    entries: Vec<(String, Vec<String>)>,
    field: &str,
) -> Result<OrderedMap<String, Vec<String>>, String> {
    let mut mapping = OrderedMap::new();
    for (key, values) in entries {
        mapping.insert(key, values);
    }
    let _ = field;
    Ok(mapping)
}

/// Copies capability routes into an immutable insertion-ordered mapping.
pub fn freeze_capability_route_mapping(
    entries: Vec<(CapabilityId, CapabilityRoute)>,
    field: &str,
) -> Result<OrderedMap<CapabilityId, CapabilityRoute>, String> {
    let mut mapping = OrderedMap::new();
    for (key, route) in entries {
        mapping.insert(key, route);
    }
    let _ = field;
    Ok(mapping)
}

/// Copies skill rules into an immutable insertion-ordered mapping.
pub fn freeze_skill_rule_mapping(
    entries: Vec<(String, SkillRoutingRule)>,
    field: &str,
) -> Result<OrderedMap<String, SkillRoutingRule>, String> {
    let mut mapping = OrderedMap::new();
    for (key, rule) in entries {
        mapping.insert(key, rule);
    }
    let _ = field;
    Ok(mapping)
}

/// Loads prompt-routing rules and their cross-catalog relationships.
pub fn load_skill_route_rules(root: &Path) -> Result<Vec<SkillRoutingRule>, String> {
    let data = load_skill_catalog(root)?;
    let families = yaml_sequence(yaml_get(&data, "skill_families"), "skill_families")?;
    let public_skill_ids = skill_ids_from_catalog(&data)?;
    let dependency_rules = load_skill_dependency_map(root, Some(&public_skill_ids))?;
    let mut rules = Vec::new();
    let mut observed = BTreeSet::new();
    for (index, entry) in families.iter().enumerate() {
        yaml_mapping(entry, &format!("skill_families[{index}]"))?;
        let skill_id = yaml_string(
            yaml_get(entry, "id")
                .ok_or_else(|| format!("skill_families[{index}].id is required"))?,
            &format!("skill_families[{index}].id"),
        )?;
        if skill_id.starts_with(PRIVATE_SKILL_PREFIX) {
            return Err(format!(
                "skill_families[{index}].id must be public: {skill_id}"
            ));
        }
        if !observed.insert(skill_id.clone()) {
            return Err(format!("duplicate skill catalog id: {skill_id}"));
        }
        if yaml_get(entry, "related_skills").is_some() {
            return Err(format!(
                "{skill_id}.related_skills must be declared in {SKILL_DEPENDENCY_MAP_PATH}"
            ));
        }
        let routing = yaml_get(entry, "routing").filter(|value| !matches!(value, Yaml::Null));
        if let Some(routing) = routing {
            yaml_mapping(routing, &format!("{skill_id}.routing"))?;
        }
        let canonical_doc = yaml_string(
            yaml_get(entry, "canonical_doc")
                .ok_or_else(|| format!("{skill_id}.canonical_doc is required"))?,
            &format!("{skill_id}.canonical_doc"),
        )?;
        let reason = yaml_get(routing.unwrap_or(&Yaml::Null), "reason")
            .and_then(Yaml::as_str)
            .unwrap_or("prompt explicitly names public skill")
            .to_owned();
        let stage_policy = yaml_get(routing.unwrap_or(&Yaml::Null), "stage_policy")
            .and_then(Yaml::as_str)
            .unwrap_or("deferred")
            .to_owned();
        let triggers_value = yaml_get(routing.unwrap_or(&Yaml::Null), "triggers");
        let mut triggers = Vec::new();
        if let Some(value) = triggers_value.filter(|value| !matches!(value, Yaml::Null)) {
            for group in yaml_sequence(Some(value), &format!("{skill_id}.routing.triggers"))? {
                let values = group
                    .as_vec()
                    .ok_or_else(|| format!("{skill_id}.routing.triggers must contain lists"))?;
                triggers.push(
                    values
                        .iter()
                        .enumerate()
                        .map(|(index, term)| {
                            yaml_string(term, &format!("{skill_id}.routing.triggers[{index}]"))
                        })
                        .collect::<Result<Vec<_>, _>>()?,
                );
            }
        }
        let dependency = dependency_rules.get(&skill_id).ok_or_else(|| {
            format!("skill-dependency-map-key-mismatch:missing={skill_id}:extra=-")
        })?;
        rules.push(SkillRoutingRule {
            skill: skill_id.clone(),
            canonical_doc,
            reason,
            stage_policy,
            triggers,
            capabilities: capability_routes(
                yaml_get(routing.unwrap_or(&Yaml::Null), "capabilities"),
                "routing.capabilities",
                &skill_id,
            )
            .map_err(|error| error.code)?,
            related_skills: ordered_unique(&dependency.routing_candidates),
            required_prerequisites: dependency.required_prerequisites.clone(),
            successors: dependency.successors.clone(),
            order_constraints: dependency.order_constraints.clone(),
            parallel_independent: dependency.parallel_independent.clone(),
            responsibility_group: dependency.responsibility_group.clone(),
        });
    }
    Ok(rules)
}

/// Loads complete rules from one resolved custom repository root.
pub fn load_skill_route_rules_from_root(
    root: &Path,
) -> Result<Vec<SkillRoutingRule>, CapabilityRootError> {
    if !root.exists() {
        return Err(CapabilityRootError::new("capability-root-not-found"));
    }
    if !root.is_dir() {
        return Err(CapabilityRootError::new("capability-root-not-directory"));
    }
    if !root.join(SKILL_CATALOG_PATH).is_file() {
        return Err(CapabilityRootError::new("capability-root-catalog-missing"));
    }
    load_skill_route_rules(root)
        .map_err(|_| CapabilityRootError::new("capability-root-catalog-invalid"))
}

/// Returns catalog-backed related-skill candidates keyed by public skill id.
pub fn load_skill_related_map(root: &Path) -> Result<OrderedMap<String, Vec<String>>, String> {
    let rules = load_skill_route_rules(root)?;
    let entries = rules
        .into_iter()
        .map(|rule| (rule.skill, rule.related_skills))
        .collect();
    freeze_related_skill_mapping(entries, "related_skills")
}

/// Builds the catalog-ordered capability index and duplicate diagnostics.
pub fn build_capability_index(rules: &[SkillRoutingRule]) -> CapabilityIndex {
    let mut routes: OrderedMap<CapabilityId, CapabilityRoute> = OrderedMap::new();
    let mut rules_by_skill: OrderedMap<String, SkillRoutingRule> = OrderedMap::new();
    let mut owner_ambiguities = Vec::new();
    let mut duplicate_definitions = Vec::new();
    for rule in rules {
        rules_by_skill.insert(rule.skill.clone(), rule.clone());
        for route in &rule.capabilities {
            if let Some(existing) = routes.get(&route.capability_id) {
                if existing.skill == route.skill {
                    push_unique(&mut duplicate_definitions, route.capability_id.clone());
                } else {
                    push_unique(&mut owner_ambiguities, route.capability_id.clone());
                }
            } else {
                routes.insert(route.capability_id.clone(), route.clone());
            }
        }
    }
    CapabilityIndex {
        routes,
        rules_by_skill,
        owner_ambiguities,
        duplicate_definitions,
    }
}

/// Removes duplicates while preserving first-seen order.
pub fn ordered_unique(values: &[String]) -> Vec<String> {
    let mut seen = HashSet::new();
    values
        .iter()
        .filter(|value| seen.insert((*value).clone()))
        .cloned()
        .collect()
}

/// Returns related skills for matched skills without activating those candidates.
pub fn related_skill_candidates(
    matched_skills: &[String],
    rules_by_skill: &OrderedMap<String, SkillRoutingRule>,
    selected_skills: &[String],
) -> (OrderedMap<String, Vec<String>>, Vec<String>) {
    let selected: BTreeSet<&str> = selected_skills.iter().map(String::as_str).collect();
    let mut related_by_source = OrderedMap::new();
    let mut candidates = Vec::new();
    for skill in matched_skills {
        let Some(rule) = rules_by_skill.get(skill) else {
            continue;
        };
        if rule.related_skills.is_empty() {
            continue;
        }
        let pending: Vec<String> = rule
            .related_skills
            .iter()
            .filter(|related| !selected.contains(related.as_str()))
            .cloned()
            .collect();
        if pending.is_empty() {
            continue;
        }
        related_by_source.insert(skill.clone(), pending.clone());
        candidates.extend(pending);
    }
    (related_by_source, ordered_unique(&candidates))
}

fn capability_value_option(option: &str) -> Option<&str> {
    match option {
        "--capability" | "--format" | "--mode" | "--risk" | "--root" | "--name" | "--area" => {
            Some(option)
        }
        "--prompt" | "--request" | "--purpose" | "--task" => Some("--prompt"),
        "--prompt-file" | "--request-file" | "--query-file" => Some("--prompt-file"),
        _ => None,
    }
}

fn capability_boolean_option(option: &str) -> Option<&'static str> {
    match option {
        "--prompt-stdin" | "--request-stdin" | "--query-stdin" => Some("--prompt-stdin"),
        "--list" => Some("--list"),
        _ => None,
    }
}

/// Returns the first raw-argument conflict for explicit capability mode.
pub fn capability_flag_conflict(argv: &[String]) -> Option<String> {
    let capability_present = argv
        .iter()
        .any(|token| token == "--capability" || token.starts_with("--capability="));
    if !capability_present {
        return None;
    }
    let mut index = 0;
    while index < argv.len() {
        let token = &argv[index];
        if token == "--capability" || token.starts_with("--capability=") {
            index += 1;
            if token == "--capability" && index < argv.len() && !argv[index].starts_with("--") {
                index += 1;
            }
            continue;
        }
        if token.starts_with("--") && token.contains('=') {
            let option = token
                .split_once('=')
                .map_or(token.as_str(), |(option, _)| option);
            if let Some(canonical) = capability_value_option(option) {
                if !matches!(canonical, "--format" | "--mode" | "--risk" | "--root") {
                    return Some(format!("capability-input-conflict:{canonical}"));
                }
                index += 1;
                continue;
            }
            if let Some(canonical) = capability_boolean_option(option) {
                return Some(format!("capability-input-conflict:{canonical}"));
            }
            if option == "--changed" {
                return Some("capability-input-conflict:--changed".to_owned());
            }
            return Some(format!("capability-unsupported-option:{token}"));
        }
        if let Some(canonical) = capability_value_option(token) {
            if !matches!(
                canonical,
                "--capability" | "--format" | "--mode" | "--risk" | "--root"
            ) {
                return Some(format!("capability-input-conflict:{canonical}"));
            }
            index += 1;
            if index >= argv.len() || argv[index].starts_with("--") {
                if !matches!(canonical, "--format" | "--mode" | "--risk" | "--root") {
                    return Some(format!("capability-input-conflict:{canonical}"));
                }
            } else {
                index += 1;
            }
            continue;
        }
        if let Some(canonical) = capability_boolean_option(token) {
            return Some(format!("capability-input-conflict:{canonical}"));
        }
        if token == "--changed" || token.starts_with("--changed=") {
            return Some("capability-input-conflict:--changed".to_owned());
        }
        if token.starts_with("--") {
            return Some(format!("capability-unsupported-option:{token}"));
        }
        return Some("capability-input-conflict:--prompt".to_owned());
    }
    None
}

/// Validate raw capability arguments before catalog loading or route parsing.
pub fn preflight_capability_argv(argv: &[String]) -> CapabilityPreflight {
    let mut values = Vec::new();
    let mut output_format = "text".to_owned();
    let mut mode = "routing-only".to_owned();
    let mut root = None;
    let mut format_raw = None;
    let mut mode_raw = None;
    let mut risk_raw = None;
    let mut capability_present = false;
    let mut index = 0;
    while index < argv.len() {
        let token = &argv[index];
        if token == "--capability" || token.starts_with("--capability=") {
            capability_present = true;
            if token == "--capability" {
                if index + 1 >= argv.len() || argv[index + 1].starts_with("--") {
                    return CapabilityPreflight {
                        capability_ids: Vec::new(),
                        mode,
                        output_format,
                        error_code: "missing-capability-value".to_owned(),
                        root,
                    };
                }
                values.push(argv[index + 1].clone());
                index += 2;
                continue;
            }
            values.push(
                token
                    .split_once('=')
                    .map_or("", |(_, value)| value)
                    .to_owned(),
            );
            index += 1;
            continue;
        }
        let option = if token.starts_with("--") {
            token
                .split_once('=')
                .map_or(token.as_str(), |(option, _)| option)
        } else {
            ""
        };
        let has_equals = token.starts_with("--") && token.contains('=');
        if matches!(option, "--format" | "--mode" | "--risk" | "--root") {
            let value = if has_equals {
                token
                    .split_once('=')
                    .map_or("", |(_, value)| value)
                    .to_owned()
            } else if index + 1 >= argv.len() || argv[index + 1].starts_with("--") {
                let error_code = match option {
                    "--format" => "missing-format-value",
                    "--mode" => "missing-mode-value",
                    "--risk" => "missing-risk-value",
                    _ => "missing-root-value",
                };
                return CapabilityPreflight {
                    capability_ids: Vec::new(),
                    mode,
                    output_format,
                    error_code: error_code.to_owned(),
                    root,
                };
            } else {
                index += 1;
                argv[index].clone()
            };
            match option {
                "--format" => {
                    format_raw = Some(value.clone());
                    output_format = if CAPABILITY_FORMAT_VALUES.contains(&value.as_str()) {
                        value
                    } else {
                        "text".to_owned()
                    };
                }
                "--mode" => {
                    mode_raw = Some(value.clone());
                    mode = if CAPABILITY_MODE_VALUES.contains(&value.as_str()) {
                        value
                    } else {
                        "routing-only".to_owned()
                    };
                }
                "--risk" => risk_raw = Some(value),
                "--root" => root = Some(PathBuf::from(value)),
                _ => unreachable!("capability option was matched above"),
            }
            index += 1;
            continue;
        }
        index += 1;
    }

    if !capability_present {
        return CapabilityPreflight {
            capability_ids: Vec::new(),
            mode,
            output_format,
            error_code: String::new(),
            root,
        };
    }
    let normalized_ids = match values
        .iter()
        .map(|value| capability_id_from_raw(value))
        .collect::<Result<Vec<_>, _>>()
    {
        Ok(values) => values,
        Err(error) => {
            return CapabilityPreflight {
                capability_ids: Vec::new(),
                mode,
                output_format,
                error_code: error,
                root,
            };
        }
    };
    if let Some(duplicate) = normalized_ids
        .iter()
        .enumerate()
        .find_map(|(position, value)| normalized_ids[..position].contains(value).then_some(value))
    {
        let error_code = format!("duplicate-capability:{duplicate}");
        return CapabilityPreflight {
            capability_ids: normalized_ids,
            mode,
            output_format,
            error_code,
            root,
        };
    }
    if let Some(error_code) = capability_flag_conflict(argv) {
        return CapabilityPreflight {
            capability_ids: normalized_ids,
            mode,
            output_format,
            error_code,
            root,
        };
    }
    if let Some(format) = format_raw {
        if !CAPABILITY_FORMAT_VALUES.contains(&format.as_str()) {
            return CapabilityPreflight {
                capability_ids: normalized_ids,
                mode,
                output_format: "text".to_owned(),
                error_code: format!("invalid-capability-format:{format}"),
                root,
            };
        }
    }
    if let Some(mode_value) = mode_raw {
        if !CAPABILITY_MODE_VALUES.contains(&mode_value.as_str()) {
            return CapabilityPreflight {
                capability_ids: normalized_ids,
                mode: "routing-only".to_owned(),
                output_format,
                error_code: format!("invalid-capability-mode:{mode_value}"),
                root,
            };
        }
    }
    if let Some(risk) = risk_raw {
        if !CAPABILITY_RISK_VALUES.contains(&risk.as_str()) || risk != "focused" {
            return CapabilityPreflight {
                capability_ids: normalized_ids,
                mode,
                output_format,
                error_code: "capability-risk-conflict".to_owned(),
                root,
            };
        }
    }
    CapabilityPreflight {
        capability_ids: normalized_ids,
        mode,
        output_format,
        error_code: String::new(),
        root,
    }
}

/// Validates one capability selection against the catalog index.
pub fn capability_skill_routes(
    capability_ids: &[String],
    index: &CapabilityIndex,
) -> Result<Vec<CapabilityRoute>, CapabilityRouteError> {
    if capability_ids.is_empty() {
        return Err(CapabilityRouteError::new("unknown-capability:"));
    }
    let mut normalized = Vec::new();
    for raw in capability_ids {
        let capability_id = capability_id_from_raw(raw)
            .map_err(|_| CapabilityRouteError::new(format!("invalid-capability-id:{raw}")))?;
        if normalized.contains(&capability_id) {
            return Err(CapabilityRouteError::new(format!(
                "duplicate-capability:{capability_id}"
            )));
        }
        normalized.push(capability_id);
    }
    if normalized.len() > 1 {
        return Err(CapabilityRouteError::new(
            "multiple-capabilities-not-supported",
        ));
    }
    let route = index.routes.get(&normalized[0]).ok_or_else(|| {
        CapabilityRouteError::new(format!("unknown-capability:{}", normalized[0]))
    })?;
    Ok(vec![route.clone()])
}

/// Selects the sole deterministic capability diagnostic.
pub fn capability_error_code(
    capability_ids: &[String],
    preflight: &CapabilityPreflight,
    index: &CapabilityIndex,
) -> String {
    if !preflight.error_code.is_empty() {
        return preflight.error_code.clone();
    }
    for capability_id in &index.owner_ambiguities {
        if capability_ids.contains(capability_id) {
            return format!("capability-owner-ambiguity:{capability_id}");
        }
    }
    for capability_id in &index.duplicate_definitions {
        if capability_ids.contains(capability_id) {
            return format!("duplicate-capability-definition:{capability_id}");
        }
    }
    let mut normalized = Vec::new();
    for raw in capability_ids {
        let capability_id = match capability_id_from_raw(raw) {
            Ok(value) => value,
            Err(_) => return format!("invalid-capability-id:{raw}"),
        };
        if normalized.contains(&capability_id) {
            return format!("duplicate-capability:{capability_id}");
        }
        normalized.push(capability_id);
    }
    if normalized.len() > 1 {
        return "multiple-capabilities-not-supported".to_owned();
    }
    if let Some(capability_id) = normalized.first() {
        if !index.routes.contains_key(capability_id) {
            return format!("unknown-capability:{capability_id}");
        }
    }
    String::new()
}

/// Creates one deterministic failure envelope without rendering.
pub fn capability_failure_decision(
    error_code: &str,
    capability_ids: &[String],
    mode: &str,
) -> CapabilityRouteDecision {
    let capability_ids = if error_code.starts_with("invalid-capability-id:") {
        Vec::new()
    } else {
        capability_ids.to_vec()
    };
    CapabilityRouteDecision {
        schema: CAPABILITY_ROUTE_SCHEMA.to_owned(),
        route: "capability-selection".to_owned(),
        mode: if CAPABILITY_MODE_VALUES.contains(&mode) {
            mode.to_owned()
        } else {
            "routing-only".to_owned()
        },
        status: "fail".to_owned(),
        error_code: error_code.to_owned(),
        capability_ids,
        matches: Vec::new(),
        skills: Vec::new(),
        active_skills: Vec::new(),
        deferred_skills: Vec::new(),
        related_skill_candidates: Vec::new(),
        related_skills: OrderedMap::new(),
        reasons: Vec::new(),
    }
}

/// Builds the capability-owned route decision without prompt inference.
pub fn decide_capabilities(
    capability_ids: &[String],
    mode: &str,
    index: &CapabilityIndex,
    preflight: &CapabilityPreflight,
) -> CapabilityRouteDecision {
    let error_code = capability_error_code(capability_ids, preflight, index);
    if !error_code.is_empty() {
        return capability_failure_decision(&error_code, capability_ids, mode);
    }
    let matches = match capability_skill_routes(capability_ids, index) {
        Ok(matches) => matches,
        Err(error) => return capability_failure_decision(&error.code, capability_ids, mode),
    };
    let matched = &matches[0];
    let mut skills = vec!["agent-orchestration".to_owned()];
    if mode == "repo-changing" {
        skills.push("codex-task-workflow".to_owned());
    }
    skills.push(matched.skill.clone());
    let skills = ordered_unique(&skills);
    let active_skills = ordered_unique(&["agent-orchestration".to_owned(), matched.skill.clone()]);
    let deferred_skills = skills
        .iter()
        .filter(|skill| !active_skills.contains(skill))
        .cloned()
        .collect();
    let (related_skills, related_skill_candidates) = related_skill_candidates(
        std::slice::from_ref(&matched.skill),
        &index.rules_by_skill,
        std::slice::from_ref(&matched.skill),
    );
    let reason = format!(
        "capability={};owner={};phase={};activation={}",
        matched.capability_id, matched.owner, matched.phase, matched.activation
    );
    let reasons = vec![format!("{}:{reason}", matched.skill)];
    CapabilityRouteDecision {
        schema: CAPABILITY_ROUTE_SCHEMA.to_owned(),
        route: "capability-selection".to_owned(),
        mode: mode.to_owned(),
        status: "pass".to_owned(),
        error_code: String::new(),
        capability_ids: capability_ids.to_vec(),
        matches,
        skills,
        active_skills,
        deferred_skills,
        related_skill_candidates,
        related_skills,
        reasons,
    }
}

fn route_source_override(raw: &str, code: &str) -> Result<PathBuf, (String, String)> {
    let expanded = crate::path_expansion::expand_user_path(Path::new(raw))
        .map_err(|error| (code.to_owned(), format!("Unable to resolve {raw}: {error}")))?;
    let resolved = crate::path_resolution::resolve_non_strict(&expanded)
        .map_err(|error| (code.to_owned(), format!("Unable to resolve {raw}: {error}")))?;
    if resolved != expanded && !(expanded.is_absolute() && resolved.starts_with(&expanded)) {
        return Err((
            code.to_owned(),
            format!(
                "{raw} resolves outside its declared root: {}",
                resolved.display()
            ),
        ));
    }
    Ok(resolved)
}

fn current_route_repository_root(raw_root: &Path) -> Result<PathBuf, String> {
    let expanded =
        crate::path_expansion::expand_user_path(raw_root).map_err(|error| error.to_string())?;
    let start = if expanded.is_absolute() {
        expanded
    } else {
        crate::path_resolution::resolve_non_strict(&expanded)?
    };
    for candidate in start.ancestors() {
        if has_catalog(candidate) {
            return crate::path_resolution::resolve_non_strict(candidate);
        }
        if candidate.join(".git").exists() {
            return crate::path_resolution::resolve_non_strict(candidate);
        }
    }
    crate::path_resolution::resolve_non_strict(&start)
}

fn resolve_capability_catalog_root(raw_root: &Path) -> Result<PathBuf, (String, String)> {
    let current_repository_root = current_route_repository_root(raw_root)
        .map_err(|error| ("agent_canon_source_root_missing".to_owned(), error))?;
    let source_override = env::var("AGENT_CANON_SOURCE_ROOT")
        .map(|value| crate::python_text::python_strip(&value).to_owned())
        .unwrap_or_default();
    let canon_override = env::var("AGENT_CANON_ROOT")
        .map(|value| crate::python_text::python_strip(&value).to_owned())
        .unwrap_or_default();
    if !source_override.is_empty() || !canon_override.is_empty() {
        let source_value = if source_override.is_empty() {
            &canon_override
        } else {
            &source_override
        };
        let canon_value = if canon_override.is_empty() {
            &source_override
        } else {
            &canon_override
        };
        let source =
            route_source_override(source_value, "agent_canon_source_root_override_invalid")?;
        let canon = route_source_override(canon_value, "agent_canon_canon_root_override_invalid")?;
        if !has_catalog(&source) {
            return Err((
                "agent_canon_source_root_override_missing".to_owned(),
                format!(
                    "Override source root has no AgentCanon catalog: {}",
                    source.display()
                ),
            ));
        }
        if !has_catalog(&canon) {
            return Err((
                "agent_canon_canon_root_override_missing".to_owned(),
                format!(
                    "Override canon root has no AgentCanon catalog: {}",
                    canon.display()
                ),
            ));
        }
        return Ok(source);
    }
    if !has_catalog(&current_repository_root) {
        return Err((
            "agent_canon_source_root_missing".to_owned(),
            format!(
                "No AgentCanon catalog found at current_repository_root={}; select an external checkout with AGENT_CANON_SOURCE_ROOT",
                current_repository_root.display()
            ),
        ));
    }
    Ok(current_repository_root)
}

fn render_capability_decision(decision: &CapabilityRouteDecision, output_format: &str) -> String {
    let matches = serde_json::to_string(&decision.matches).expect("matches serialize");
    let related_skills =
        serde_json::to_string(&decision.related_skills).expect("related skills serialize");
    let reasons = serde_json::to_string(&decision.reasons).expect("reasons serialize");
    let capability_ids = if decision.capability_ids.is_empty() {
        "-".to_owned()
    } else {
        decision.capability_ids.join(",")
    };
    let join_or_dash = |values: &[String]| {
        if values.is_empty() {
            "-".to_owned()
        } else {
            values.join(",")
        }
    };
    if output_format == "json" {
        return serde_json::to_string_pretty(decision).expect("route decision serializes");
    }
    if output_format == "markdown" {
        return [
            format!("- Schema: `{}`", decision.schema),
            format!("- Route: `{}`", decision.route),
            format!("- Mode: `{}`", decision.mode),
            format!("- Status: `{}`", decision.status),
            format!("- Error code: `{}`", decision.error_code),
            format!("- Capability IDs: `{capability_ids}`"),
            format!("- Matches: `{matches}`"),
            format!("- Skills: `{}`", join_or_dash(&decision.skills)),
            format!(
                "- Active skills: `{}`",
                join_or_dash(&decision.active_skills)
            ),
            format!(
                "- Deferred skills: `{}`",
                join_or_dash(&decision.deferred_skills)
            ),
            format!(
                "- Related skill candidates: `{}`",
                join_or_dash(&decision.related_skill_candidates)
            ),
            format!("- Related skills: `{related_skills}`"),
            format!("- Reasons: `{reasons}`"),
        ]
        .join("\n");
    }
    [
        format!("CAPABILITY_ROUTE_SCHEMA={}", decision.schema),
        format!("CAPABILITY_ROUTE={}", decision.route),
        format!("CAPABILITY_MODE={}", decision.mode),
        format!("CAPABILITY_ROUTE_STATUS={}", decision.status),
        format!("CAPABILITY_ERROR_CODE={}", decision.error_code),
        format!("CAPABILITY_IDS={capability_ids}"),
        format!("CAPABILITY_MATCHES={matches}"),
        format!("SKILLS={}", join_or_dash(&decision.skills)),
        format!("ACTIVE_SKILLS={}", join_or_dash(&decision.active_skills)),
        format!(
            "DEFERRED_SKILLS={}",
            join_or_dash(&decision.deferred_skills)
        ),
        format!(
            "RELATED_SKILL_CANDIDATES={}",
            join_or_dash(&decision.related_skill_candidates)
        ),
        format!("RELATED_SKILLS={related_skills}"),
        format!("REASONS={reasons}"),
    ]
    .join("\n")
}

/// Execute the capability-selection branch of the canonical route CLI.
pub fn run_capability_route(args: &[String]) -> i32 {
    let preflight = preflight_capability_argv(args);
    if !args
        .iter()
        .any(|token| token == "--capability" || token.starts_with("--capability="))
    {
        eprintln!("usage: agent-canon capability-route --capability ID [options]");
        return 2;
    }
    if !preflight.error_code.is_empty() {
        let decision = capability_failure_decision(
            &preflight.error_code,
            &preflight.capability_ids,
            &preflight.mode,
        );
        println!(
            "{}",
            render_capability_decision(&decision, &preflight.output_format)
        );
        return 2;
    }
    let default_root = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let raw_root = preflight.root.as_deref().unwrap_or(&default_root);
    let root = match resolve_capability_catalog_root(raw_root) {
        Ok(root) => root,
        Err((code, detail)) => {
            eprintln!("ROUTE_SOURCE_ROOT_FAILURE={code}:{detail}");
            return 2;
        }
    };
    let rules = match load_skill_route_rules_from_root(&root) {
        Ok(rules) => rules,
        Err(_) => {
            let decision = capability_failure_decision(
                "capability-root-catalog-invalid",
                &preflight.capability_ids,
                &preflight.mode,
            );
            println!(
                "{}",
                render_capability_decision(&decision, &preflight.output_format)
            );
            return 2;
        }
    };
    let index = build_capability_index(&rules);
    let decision = decide_capabilities(
        &preflight.capability_ids,
        &preflight.mode,
        &index,
        &preflight,
    );
    println!(
        "{}",
        render_capability_decision(&decision, &preflight.output_format)
    );
    if decision.status == "pass" {
        0
    } else {
        2
    }
}

/// Runs the optional authoring-only YAML and JSON schema checks.
pub fn validate_catalog_schemas(root: &Path) -> Result<Vec<JsonValue>, CapabilityRootError> {
    validate_catalog_schemas_with(root, &mut Command::output)
}

fn validate_catalog_schemas_with(
    root: &Path,
    execute: &mut impl FnMut(&mut Command) -> std::io::Result<Output>,
) -> Result<Vec<JsonValue>, CapabilityRootError> {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let config = root.join(CATALOG_SCHEMA_ROOT).join("yamllint.yaml");
    let documents: Vec<PathBuf> = CATALOG_SCHEMA_PATHS
        .iter()
        .map(|(document, _)| root.join(document))
        .collect();
    let mut yaml = Command::new("yamllint");
    yaml.arg("--strict")
        .arg("--config-file")
        .arg(&config)
        .args(&documents)
        .current_dir(&root);
    let yaml_output = execute(&mut yaml).map_err(|error| {
        CapabilityRootError::new(format!("catalog-validator-execution:yamllint:{error}"))
    })?;
    if !yaml_output.status.success() {
        return Err(CapabilityRootError::new("catalog-yaml-invalid"));
    }
    let mut results = Vec::new();
    for ((document, schema), document_path) in CATALOG_SCHEMA_PATHS.iter().zip(documents) {
        let mut schema_command = Command::new("check-jsonschema");
        schema_command
            .arg("--schemafile")
            .arg(root.join(schema))
            .arg(&document_path)
            .current_dir(&root);
        let output = execute(&mut schema_command).map_err(|error| {
            CapabilityRootError::new(format!(
                "catalog-validator-execution:check-jsonschema:{error}"
            ))
        })?;
        if !output.status.success() {
            return Err(CapabilityRootError::new(format!(
                "catalog-schema-invalid:{document}"
            )));
        }
        results.push(json!({
            "tool": "check-jsonschema",
            "schema": schema,
            "document": document,
            "argv": ["--schemafile", schema, document],
            "exit_code": 0,
        }));
    }
    Ok(results)
}

#[cfg(test)]
mod capability_route_tests {
    use super::*;

    fn sample_index() -> CapabilityIndex {
        let route = CapabilityRoute {
            skill: "oop-type-design".to_owned(),
            capability_id: "oop_type_design".to_owned(),
            owner: "pre_implementation_oop_type_design".to_owned(),
            phase: "pre_implementation_design".to_owned(),
            activation: "explicit_capability".to_owned(),
            exclusive: true,
        };
        let rule = SkillRoutingRule {
            skill: "oop-type-design".to_owned(),
            canonical_doc: "agents/skills/oop-type-design.md".to_owned(),
            reason: "fixture".to_owned(),
            stage_policy: "active".to_owned(),
            triggers: Vec::new(),
            capabilities: vec![route],
            related_skills: vec![
                "python-review".to_owned(),
                "cpp-review".to_owned(),
                "oop-readability-check".to_owned(),
            ],
            required_prerequisites: Vec::new(),
            successors: Vec::new(),
            order_constraints: Vec::new(),
            parallel_independent: Vec::new(),
            responsibility_group: "design".to_owned(),
        };
        build_capability_index(&[rule])
    }

    #[test]
    fn raw_preflight_preserves_capability_errors_and_defaults() {
        let missing = preflight_capability_argv(&[
            "--capability".to_owned(),
            "--format".to_owned(),
            "json".to_owned(),
        ]);
        assert_eq!(missing.error_code, "missing-capability-value");
        assert_eq!(missing.output_format, "text");

        let conflict = preflight_capability_argv(&[
            "--capability".to_owned(),
            "oop_type_design".to_owned(),
            "--prompt".to_owned(),
            "design".to_owned(),
        ]);
        assert_eq!(conflict.error_code, "capability-input-conflict:--prompt");
        assert_eq!(conflict.mode, "routing-only");

        let invalid_mode = preflight_capability_argv(&[
            "--capability".to_owned(),
            "oop_type_design".to_owned(),
            "--mode".to_owned(),
            "other".to_owned(),
        ]);
        assert_eq!(invalid_mode.error_code, "invalid-capability-mode:other");
        assert_eq!(invalid_mode.mode, "routing-only");
    }

    #[test]
    fn capability_decision_reuses_catalog_order_and_keeps_repo_change_deferred() {
        let index = sample_index();
        let preflight = preflight_capability_argv(&[
            "--capability".to_owned(),
            "oop_type_design".to_owned(),
            "--mode".to_owned(),
            "repo-changing".to_owned(),
        ]);
        let decision = decide_capabilities(
            &preflight.capability_ids,
            &preflight.mode,
            &index,
            &preflight,
        );
        assert_eq!(decision.status, "pass");
        assert_eq!(decision.capability_ids, vec!["oop_type_design".to_owned()]);
        assert_eq!(
            decision.matches[0].owner,
            "pre_implementation_oop_type_design"
        );
        assert_eq!(
            decision.skills,
            vec![
                "agent-orchestration".to_owned(),
                "codex-task-workflow".to_owned(),
                "oop-type-design".to_owned(),
            ]
        );
        assert_eq!(
            decision.active_skills,
            vec![
                "agent-orchestration".to_owned(),
                "oop-type-design".to_owned()
            ]
        );
        assert_eq!(
            decision.deferred_skills,
            vec!["codex-task-workflow".to_owned()]
        );
        assert_eq!(
            decision.related_skill_candidates,
            vec![
                "python-review".to_owned(),
                "cpp-review".to_owned(),
                "oop-readability-check".to_owned(),
            ]
        );
    }

    #[test]
    fn direct_capability_match_rejects_unknown_and_multiple_ids() {
        let index = sample_index();
        assert_eq!(
            capability_skill_routes(&["unknown_capability".to_owned()], &index)
                .expect_err("unknown capability is rejected")
                .code,
            "unknown-capability:unknown_capability"
        );
        assert_eq!(
            capability_skill_routes(
                &["oop_type_design".to_owned(), "other_capability".to_owned()],
                &index,
            )
            .expect_err("multiple capabilities are not arbitrated")
            .code,
            "multiple-capabilities-not-supported"
        );
    }
}

#[cfg(test)]
mod validator_tests {
    use super::*;
    use std::io;
    use std::process::ExitStatus;

    fn result(code: u32) -> Output {
        #[cfg(unix)]
        let status = {
            use std::os::unix::process::ExitStatusExt;
            ExitStatus::from_raw((code as i32) << 8)
        };
        #[cfg(windows)]
        let status = {
            use std::os::windows::process::ExitStatusExt;
            ExitStatus::from_raw(code)
        };
        Output {
            status,
            stdout: Vec::new(),
            stderr: Vec::new(),
        }
    }

    #[test]
    fn explicit_validation_preserves_provider_order_arguments_and_fresh_execution() {
        let root = std::env::temp_dir().canonicalize().unwrap();
        let mut calls = Vec::new();
        let mut execute = |command: &mut Command| {
            calls.push((
                command.get_program().to_owned(),
                command
                    .get_args()
                    .map(ToOwned::to_owned)
                    .collect::<Vec<_>>(),
            ));
            assert_eq!(command.get_current_dir(), Some(root.as_path()));
            Ok(result(0))
        };
        let first = validate_catalog_schemas_with(&root, &mut execute).unwrap();
        assert_eq!(
            first,
            validate_catalog_schemas_with(&root, &mut execute).unwrap()
        );
        assert_eq!(calls.len(), 8);
        let expected_documents = [
            "agents/skills/catalog.yaml",
            "agents/skills/skill-dependencies.yaml",
            "tools/catalog.yaml",
        ];
        let expected_schemas = [
            "schemas/agent-canon/skill-catalog.schema.json",
            "schemas/agent-canon/skill-dependencies.schema.json",
            "schemas/agent-canon/tool-catalog.schema.json",
        ];
        let (rounds, remainder) = calls.as_chunks::<4>();
        assert!(remainder.is_empty());
        for round in rounds {
            assert_eq!(round[0].0, "yamllint");
            let mut yaml_args = vec![
                "--strict".into(),
                "--config-file".into(),
                root.join("schemas/agent-canon/yamllint.yaml")
                    .into_os_string(),
            ];
            yaml_args.extend(expected_documents.map(|path| root.join(path).into_os_string()));
            assert_eq!(round[0].1, yaml_args);
            for (index, (document, schema)) in
                expected_documents.iter().zip(expected_schemas).enumerate()
            {
                assert_eq!(round[index + 1].0, "check-jsonschema");
                assert_eq!(
                    round[index + 1].1,
                    vec![
                        std::ffi::OsString::from("--schemafile"),
                        root.join(schema).into_os_string(),
                        root.join(document).into_os_string()
                    ]
                );
            }
        }
        assert_eq!(first, expected_documents.iter().zip(expected_schemas).map(|(document, schema)| json!({"tool":"check-jsonschema","document":document,"schema":schema,"argv":["--schemafile",schema,document],"exit_code":0})).collect::<Vec<_>>());
    }

    #[test]
    fn spawn_failures_remain_distinct_from_validator_rejections() {
        let root = std::env::temp_dir();
        for failed_call in 0..2 {
            let mut count = 0;
            let error = validate_catalog_schemas_with(&root, &mut |_| {
                let index = count;
                count += 1;
                if index == failed_call {
                    Err(io::Error::new(
                        io::ErrorKind::NotFound,
                        "missing executable",
                    ))
                } else {
                    Ok(result(0))
                }
            })
            .unwrap_err();
            let provider = if failed_call == 0 {
                "yamllint"
            } else {
                "check-jsonschema"
            };
            assert_eq!(
                error.code,
                format!("catalog-validator-execution:{provider}:missing executable")
            );
            assert_eq!(count, failed_call + 1);
        }
    }

    #[test]
    fn validator_rejection_codes_and_short_circuit_remain_stable() {
        for failed_call in 0..2 {
            let mut count = 0;
            let error = validate_catalog_schemas_with(&std::env::temp_dir(), &mut |_| {
                let index = count;
                count += 1;
                Ok(result(if index == failed_call { 1 } else { 0 }))
            })
            .unwrap_err();
            assert_eq!(
                error.code,
                if failed_call == 0 {
                    "catalog-yaml-invalid"
                } else {
                    "catalog-schema-invalid:agents/skills/catalog.yaml"
                }
            );
            assert_eq!(count, failed_call + 1);
        }
    }
}
