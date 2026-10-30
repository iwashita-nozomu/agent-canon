use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fmt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::LazyLock;

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
    let raw = value.trim();
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
        if keys != required {
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
    let mut routes = OrderedMap::new();
    let mut rules_by_skill = OrderedMap::new();
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

/// Runs the optional authoring-only YAML and JSON schema checks.
pub fn validate_catalog_schemas(root: &Path) -> Result<Vec<JsonValue>, CapabilityRootError> {
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
    if !yaml.output().is_ok_and(|output| output.status.success()) {
        return Err(CapabilityRootError::new("catalog-yaml-invalid"));
    }
    let mut results = Vec::new();
    for ((document, schema), document_path) in CATALOG_SCHEMA_PATHS.iter().zip(documents) {
        let output = Command::new("check-jsonschema")
            .arg("--schemafile")
            .arg(root.join(schema))
            .arg(&document_path)
            .current_dir(&root)
            .output();
        if !output.is_ok_and(|output| output.status.success()) {
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
