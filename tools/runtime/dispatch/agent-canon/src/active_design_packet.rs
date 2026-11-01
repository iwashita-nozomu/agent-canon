// @dependency-start
// contract implementation
// responsibility Owns native normalization and mapping for the persisted active-design-packet contract.
// upstream design ../../../../../agents/COMMUNICATION_PROTOCOL.md active design packet schema
// upstream implementation ../../../../../tools/agent/orchestration/packets.py owns the source packet schema and normalized contract
// downstream implementation waterfall_gate.rs validates the persisted packet and reference projection
// @dependency-end

use crate::artifacts::artifact_identity::canonical_json_bytes;
use regex::Regex;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::path::{Component, Path};
use std::sync::OnceLock;
use yaml_rust2::Yaml;

pub const ACTIVE_DESIGN_PACKET_SCHEMA: &str = "waterfall.design_packet.v1";
pub const ACTIVE_DESIGN_PACKET_MATERIALIZATION_SCHEMA: &str =
    "waterfall.active_design_packet_materialization.v1";

pub const ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS: [&str; 3] = [
    "design_artifact",
    "design_review_artifact",
    "document_flow_review_artifact",
];

pub const ACTIVE_DESIGN_PACKET_FIELDS: [&str; 10] = [
    "schema",
    "design_artifact",
    "design_review_artifact",
    "document_flow_review_artifact",
    "document_flow_required",
    "clause_registry",
    "abstract_design_frame",
    "implementation_source_packet",
    "design_side_effect_map",
    "design_to_implementation_trace",
];

const ACTIVE_DESIGN_SECTIONS: [&str; 4] = [
    "abstract_design_frame",
    "implementation_source_packet",
    "design_side_effect_map",
    "design_to_implementation_trace",
];

const ACTIVE_PACKET_ENTRY_FIELDS: [&str; 8] = [
    "entry_id",
    "responsibility_id",
    "clause_refs",
    "owner_refs",
    "source_refs",
    "dependency_refs",
    "output_refs",
    "reviewer_refs",
];

const REFERENCE_FIELDS: [&str; 6] = [
    "clause_refs",
    "owner_refs",
    "source_refs",
    "dependency_refs",
    "output_refs",
    "reviewer_refs",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActiveDesignPacketError {
    message: String,
}

impl ActiveDesignPacketError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }

    pub fn message(&self) -> &str {
        &self.message
    }
}

impl fmt::Display for ActiveDesignPacketError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for ActiveDesignPacketError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActiveDesignClause {
    pub clause_id: String,
    pub source_ref: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActiveDesignPacketEntry {
    pub entry_id: String,
    pub responsibility_id: String,
    pub clause_refs: Vec<String>,
    pub owner_refs: Vec<String>,
    pub source_refs: Vec<String>,
    pub dependency_refs: Vec<String>,
    pub output_refs: Vec<String>,
    pub reviewer_refs: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActiveDesignPacketConfig {
    pub schema: String,
    pub design_artifact: String,
    pub design_review_artifact: String,
    pub document_flow_review_artifact: String,
    pub document_flow_required: bool,
    pub clause_registry: Vec<ActiveDesignClause>,
    pub abstract_design_frame: ActiveDesignPacketEntry,
    pub implementation_source_packet: ActiveDesignPacketEntry,
    pub design_side_effect_map: ActiveDesignPacketEntry,
    pub design_to_implementation_trace: ActiveDesignPacketEntry,
}

fn string_mapping<'a>(
    value: &'a Yaml,
    field: &str,
) -> Result<BTreeMap<&'a str, &'a Yaml>, ActiveDesignPacketError> {
    let Some(mapping) = value.as_hash() else {
        return Err(ActiveDesignPacketError::new(format!(
            "{field} must be a mapping"
        )));
    };
    let mut fields = BTreeMap::new();
    for (key, item) in mapping {
        let Some(key) = key.as_str() else {
            return Err(ActiveDesignPacketError::new(format!(
                "{field} must be a mapping"
            )));
        };
        fields.insert(key, item);
    }
    Ok(fields)
}

fn unknown_fields(mapping: &BTreeMap<&str, &Yaml>, allowed: &[&str]) -> Vec<String> {
    let mut unknown = mapping
        .keys()
        .copied()
        .filter(|key| !allowed.iter().any(|allowed_field| allowed_field == key))
        .map(str::to_owned)
        .collect::<Vec<_>>();
    unknown.sort_unstable();
    unknown
}

fn missing_fields(mapping: &BTreeMap<&str, &Yaml>, expected: &[&str]) -> Vec<String> {
    expected
        .iter()
        .copied()
        .filter(|field| !mapping.contains_key(field))
        .map(str::to_owned)
        .collect()
}

fn required_string(
    mapping: &BTreeMap<&str, &Yaml>,
    key: &str,
    diagnostic_field: &str,
) -> Result<String, ActiveDesignPacketError> {
    mapping
        .get(key)
        .and_then(|value| value.as_str())
        .map(str::to_owned)
        .ok_or_else(|| ActiveDesignPacketError::new(format!("{diagnostic_field} must be a string")))
}

fn string_tuple(value: &Yaml, field: &str) -> Result<Vec<String>, ActiveDesignPacketError> {
    if matches!(value, Yaml::Null) {
        return Ok(Vec::new());
    }
    let Some(values) = value.as_vec() else {
        return Err(ActiveDesignPacketError::new(format!(
            "{field} must be a list"
        )));
    };
    values
        .iter()
        .map(|item| {
            item.as_str().map(str::to_owned).ok_or_else(|| {
                ActiveDesignPacketError::new(format!("{field} entries must be strings"))
            })
        })
        .collect()
}

fn locator_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(
            r"(workspace|agentcanon|artifact):[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*(?:#(?:section|symbol):[A-Za-z0-9_][A-Za-z0-9_.-]*)?",
        )
        .expect("fixed active packet locator regex")
    })
}

fn header_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(
            r"header:([A-Za-z0-9_][A-Za-z0-9_.-]*):([A-Za-z0-9_][A-Za-z0-9_.-]*):((?:workspace|agentcanon|artifact):[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*(?:#(?:section|symbol):[A-Za-z0-9_][A-Za-z0-9_.-]*)?)->((?:workspace|agentcanon|artifact):[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*(?:#(?:section|symbol):[A-Za-z0-9_][A-Za-z0-9_.-]*)?)",
        )
        .expect("fixed active packet dependency regex")
    })
}

fn full_match(regex: &Regex, value: &str) -> bool {
    regex
        .find(value)
        .is_some_and(|matched| matched.start() == 0 && matched.end() == value.len())
}

fn validate_locator(value: &str) -> Result<(), ActiveDesignPacketError> {
    if value.is_empty() || value.starts_with("repo:") {
        return Err(ActiveDesignPacketError::new(
            if value.starts_with("repo:") {
                format!("active_design_packet_reference_ambiguous_root:{value}")
            } else {
                format!("active_design_packet_reference_invalid:syntax:{value}")
            },
        ));
    }
    if value
        .chars()
        .any(|character| (character as u32) < 32 || character as u32 == 127)
        || value.contains('\\')
        || value.to_ascii_lowercase().contains("%2f")
        || value.to_ascii_lowercase().contains("%5c")
        || !full_match(locator_regex(), value)
    {
        return Err(ActiveDesignPacketError::new(format!(
            "active_design_packet_reference_invalid:syntax:{value}"
        )));
    }
    Ok(())
}

fn validate_dependency(value: &str) -> Result<(), ActiveDesignPacketError> {
    if !value.starts_with("header:") {
        return Err(ActiveDesignPacketError::new(format!(
            "active_design_packet_reference_invalid:dependency:{value}"
        )));
    }
    if value.contains("repo:") || value.contains("->repo:") {
        return Err(ActiveDesignPacketError::new(format!(
            "active_design_packet_reference_ambiguous_root:{value}"
        )));
    }
    let Some(captures) = header_regex()
        .captures(value)
        .filter(|_| full_match(header_regex(), value))
    else {
        return Err(ActiveDesignPacketError::new(format!(
            "active_design_packet_reference_invalid:dependency:{value}"
        )));
    };
    let source = captures.get(3).map_or("", |matched| matched.as_str());
    let target = captures.get(4).map_or("", |matched| matched.as_str());
    validate_locator(source)?;
    validate_locator(target)
}

fn validate_reference_list(
    value: &Yaml,
    field: &str,
) -> Result<Vec<String>, ActiveDesignPacketError> {
    let values = string_tuple(value, field)?;
    if values.is_empty() {
        return Err(ActiveDesignPacketError::new(format!("{field}:empty")));
    }
    let leaf = field.rsplit('.').next().unwrap_or(field);
    for candidate in &values {
        if candidate.starts_with("repo:") {
            return Err(ActiveDesignPacketError::new(format!(
                "active_design_packet_reference_ambiguous_root:{candidate}"
            )));
        }
        let allowed = match leaf {
            "owner_refs" | "reviewer_refs" => candidate.starts_with("role:"),
            "source_refs" => ["workspace:", "agentcanon:", "artifact:"]
                .iter()
                .any(|prefix| candidate.starts_with(prefix)),
            "dependency_refs" => {
                candidate.starts_with("entry:") || candidate.starts_with("header:")
            }
            "output_refs" => candidate.starts_with("artifact:"),
            "clause_refs" => true,
            _ => false,
        };
        if !allowed {
            return Err(ActiveDesignPacketError::new(format!(
                "{field}:invalid_reference"
            )));
        }
        if leaf == "source_refs" {
            validate_locator(candidate)?;
        } else if leaf == "dependency_refs" && candidate.starts_with("header:") {
            validate_dependency(candidate)?;
        } else if leaf == "clause_refs"
            && (candidate.is_empty()
                || !candidate.chars().enumerate().all(|(index, character)| {
                    if index == 0 {
                        character.is_ascii_alphanumeric()
                    } else {
                        character.is_ascii_alphanumeric() || matches!(character, '_' | '-')
                    }
                }))
        {
            return Err(ActiveDesignPacketError::new(format!(
                "{field}:invalid_reference"
            )));
        }
    }
    Ok(values)
}

fn normalize_entry(
    raw_entry: &Yaml,
    section: &str,
    field_prefix: &str,
) -> Result<ActiveDesignPacketEntry, ActiveDesignPacketError> {
    let field = format!("{field_prefix}.{section}");
    let entry = string_mapping(raw_entry, &field)?;
    let unknown = unknown_fields(&entry, &ACTIVE_PACKET_ENTRY_FIELDS);
    if !unknown.is_empty() {
        return Err(ActiveDesignPacketError::new(format!(
            "{field}:field_unknown:{}",
            unknown.join(",")
        )));
    }
    let missing = missing_fields(&entry, &ACTIVE_PACKET_ENTRY_FIELDS);
    if !missing.is_empty() {
        return Err(ActiveDesignPacketError::new(format!(
            "{field}:field_missing:{}",
            missing.join(",")
        )));
    }
    let entry_id = required_string(&entry, "entry_id", &format!("{field}.entry_id"))?;
    let expected_id = match section {
        "abstract_design_frame" => "abstract-design-frame",
        "implementation_source_packet" => "implementation-source-packet",
        "design_side_effect_map" => "design-side-effect-map",
        "design_to_implementation_trace" => "design-to-implementation-trace",
        _ => {
            return Err(ActiveDesignPacketError::new(
                "active_design_packet:section_invalid",
            ))
        }
    };
    if entry_id != expected_id {
        return Err(ActiveDesignPacketError::new(format!(
            "{field}.entry_id:invalid"
        )));
    }
    let responsibility_id = required_string(
        &entry,
        "responsibility_id",
        &format!("{field}.responsibility_id"),
    )?;
    let mut references = BTreeMap::new();
    for reference_field in REFERENCE_FIELDS {
        let value = entry.get(reference_field).ok_or_else(|| {
            ActiveDesignPacketError::new(format!("{field}.{reference_field} must be a list"))
        })?;
        references.insert(
            reference_field,
            validate_reference_list(value, &format!("{field}.{reference_field}"))?,
        );
    }
    Ok(ActiveDesignPacketEntry {
        entry_id,
        responsibility_id,
        clause_refs: references.remove("clause_refs").unwrap_or_default(),
        owner_refs: references.remove("owner_refs").unwrap_or_default(),
        source_refs: references.remove("source_refs").unwrap_or_default(),
        dependency_refs: references.remove("dependency_refs").unwrap_or_default(),
        output_refs: references.remove("output_refs").unwrap_or_default(),
        reviewer_refs: references.remove("reviewer_refs").unwrap_or_default(),
    })
}

pub fn normalize_active_design_packet_config(
    raw_packet: &Yaml,
    field_prefix: &str,
) -> Result<ActiveDesignPacketConfig, ActiveDesignPacketError> {
    let packet = string_mapping(raw_packet, field_prefix)?;
    let unknown = unknown_fields(&packet, &ACTIVE_DESIGN_PACKET_FIELDS);
    if !unknown.is_empty() {
        return Err(ActiveDesignPacketError::new(format!(
            "{field_prefix}:field_unknown:{}",
            unknown.join(",")
        )));
    }
    let missing = missing_fields(&packet, &ACTIVE_DESIGN_PACKET_FIELDS);
    if !missing.is_empty() {
        return Err(ActiveDesignPacketError::new(format!(
            "{field_prefix}:field_missing:{}",
            missing.join(",")
        )));
    }
    let schema = required_string(&packet, "schema", &format!("{field_prefix}.schema"))?;
    if schema != ACTIVE_DESIGN_PACKET_SCHEMA {
        return Err(ActiveDesignPacketError::new(format!(
            "{field_prefix}:schema_unknown:{schema}"
        )));
    }
    let mut paths = BTreeMap::new();
    for field in ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS {
        let value = required_string(&packet, field, &format!("{field_prefix}.{field}"))?;
        let path = Path::new(&value);
        if path.is_absolute()
            || path
                .components()
                .any(|component| matches!(component, Component::ParentDir))
        {
            return Err(ActiveDesignPacketError::new(format!(
                "{field_prefix}:field_invalid:{field}"
            )));
        }
        paths.insert(field, value);
    }
    let document_flow_required = packet
        .get("document_flow_required")
        .and_then(|value| value.as_bool())
        .ok_or_else(|| {
            ActiveDesignPacketError::new(format!(
                "{field_prefix}:field_invalid:document_flow_required"
            ))
        })?;
    let raw_clauses = packet
        .get("clause_registry")
        .and_then(|value| value.as_vec())
        .filter(|clauses| !clauses.is_empty())
        .ok_or_else(|| {
            ActiveDesignPacketError::new(format!("{field_prefix}.clause_registry:field_invalid"))
        })?;
    let mut clauses = Vec::with_capacity(raw_clauses.len());
    for (index, raw_clause) in raw_clauses.iter().enumerate() {
        let clause_field = format!("{field_prefix}.clause_registry[{index}]");
        let clause = string_mapping(raw_clause, &clause_field)?;
        let allowed = ["clause_id", "source_ref"];
        let unknown = unknown_fields(&clause, &allowed);
        if !unknown.is_empty() {
            return Err(ActiveDesignPacketError::new(format!(
                "{clause_field}:field_unknown:{}",
                unknown.join(",")
            )));
        }
        let missing = missing_fields(&clause, &allowed);
        if !missing.is_empty() {
            return Err(ActiveDesignPacketError::new(format!(
                "{clause_field}:field_missing:{}",
                missing.join(",")
            )));
        }
        let clause_id =
            required_string(&clause, "clause_id", &format!("{clause_field}.clause_id"))?;
        let source_ref =
            required_string(&clause, "source_ref", &format!("{clause_field}.source_ref"))?;
        if clause_id.is_empty()
            || !clause_id.chars().enumerate().all(|(index, character)| {
                if index == 0 {
                    character.is_ascii_alphanumeric()
                } else {
                    character.is_ascii_alphanumeric() || matches!(character, '_' | '-')
                }
            })
        {
            return Err(ActiveDesignPacketError::new(format!(
                "{clause_field}.clause_id:invalid"
            )));
        }
        if !["workspace:", "agentcanon:", "artifact:"]
            .iter()
            .any(|prefix| source_ref.starts_with(prefix))
        {
            return Err(ActiveDesignPacketError::new(format!(
                "{clause_field}.source_ref:invalid"
            )));
        }
        validate_locator(&source_ref)?;
        clauses.push(ActiveDesignClause {
            clause_id,
            source_ref,
        });
    }
    let clause_ids = clauses
        .iter()
        .map(|clause| clause.clause_id.clone())
        .collect::<BTreeSet<_>>();
    if clause_ids.len() != clauses.len() {
        return Err(ActiveDesignPacketError::new(format!(
            "{field_prefix}.clause_registry:duplicate_id"
        )));
    }
    let mut entries = BTreeMap::new();
    for section in ACTIVE_DESIGN_SECTIONS {
        let raw_entry = packet.get(section).ok_or_else(|| {
            ActiveDesignPacketError::new(format!("{field_prefix}:field_missing:{section}"))
        })?;
        entries.insert(section, normalize_entry(raw_entry, section, field_prefix)?);
    }
    let responsibility_ids = entries
        .values()
        .map(|entry| entry.responsibility_id.as_str())
        .collect::<BTreeSet<_>>();
    if responsibility_ids.len() != 1 {
        return Err(ActiveDesignPacketError::new(format!(
            "{field_prefix}:responsibility_id:inconsistent"
        )));
    }
    let known_entry_ids = entries
        .values()
        .map(|entry| entry.entry_id.as_str())
        .collect::<BTreeSet<_>>();
    let expected_dependencies: BTreeMap<&str, BTreeSet<&str>> = BTreeMap::from([
        ("abstract_design_frame", BTreeSet::new()),
        (
            "implementation_source_packet",
            BTreeSet::from(["abstract-design-frame"]),
        ),
        (
            "design_side_effect_map",
            BTreeSet::from(["abstract-design-frame"]),
        ),
        (
            "design_to_implementation_trace",
            BTreeSet::from([
                "abstract-design-frame",
                "implementation-source-packet",
                "design-side-effect-map",
            ]),
        ),
    ]);
    let mut referenced_clauses = BTreeSet::new();
    for section in ACTIVE_DESIGN_SECTIONS {
        let entry = entries
            .get(section)
            .expect("normalized packet contains every section");
        referenced_clauses.extend(entry.clause_refs.iter().cloned());
        if !referenced_clauses.is_subset(&clause_ids) {
            return Err(ActiveDesignPacketError::new(format!(
                "{field_prefix}.{section}.clause_refs:invalid"
            )));
        }
        let dependency_entries = entry
            .dependency_refs
            .iter()
            .filter_map(|reference| reference.strip_prefix("entry:"))
            .collect::<BTreeSet<_>>();
        if dependency_entries != expected_dependencies[section]
            || !dependency_entries.is_subset(&known_entry_ids)
        {
            return Err(ActiveDesignPacketError::new(format!(
                "{field_prefix}.{section}.dependency_refs:invalid"
            )));
        }
    }
    if referenced_clauses != clause_ids {
        return Err(ActiveDesignPacketError::new(format!(
            "{field_prefix}.clause_registry:unreferenced_clause"
        )));
    }
    Ok(ActiveDesignPacketConfig {
        schema,
        design_artifact: paths.remove("design_artifact").unwrap_or_default(),
        design_review_artifact: paths.remove("design_review_artifact").unwrap_or_default(),
        document_flow_review_artifact: paths
            .remove("document_flow_review_artifact")
            .unwrap_or_default(),
        document_flow_required,
        clause_registry: clauses,
        abstract_design_frame: entries
            .remove("abstract_design_frame")
            .expect("normalized packet contains abstract design entry"),
        implementation_source_packet: entries
            .remove("implementation_source_packet")
            .expect("normalized packet contains implementation source entry"),
        design_side_effect_map: entries
            .remove("design_side_effect_map")
            .expect("normalized packet contains side-effect map entry"),
        design_to_implementation_trace: entries
            .remove("design_to_implementation_trace")
            .expect("normalized packet contains trace entry"),
    })
}

fn entry_mapping(entry: &ActiveDesignPacketEntry) -> Value {
    json!({
        "entry_id": &entry.entry_id,
        "responsibility_id": &entry.responsibility_id,
        "clause_refs": &entry.clause_refs,
        "owner_refs": &entry.owner_refs,
        "source_refs": &entry.source_refs,
        "dependency_refs": &entry.dependency_refs,
        "output_refs": &entry.output_refs,
        "reviewer_refs": &entry.reviewer_refs,
    })
}

pub fn active_design_packet_mapping(packet: &ActiveDesignPacketConfig) -> Value {
    let clause_registry = packet
        .clause_registry
        .iter()
        .map(|clause| {
            json!({
                "clause_id": &clause.clause_id,
                "source_ref": &clause.source_ref,
            })
        })
        .collect::<Vec<_>>();
    let mut mapping = Map::new();
    mapping.insert("schema".to_owned(), json!(&packet.schema));
    mapping.insert("design_artifact".to_owned(), json!(&packet.design_artifact));
    mapping.insert(
        "design_review_artifact".to_owned(),
        json!(&packet.design_review_artifact),
    );
    mapping.insert(
        "document_flow_review_artifact".to_owned(),
        json!(&packet.document_flow_review_artifact),
    );
    mapping.insert(
        "document_flow_required".to_owned(),
        json!(packet.document_flow_required),
    );
    mapping.insert("clause_registry".to_owned(), json!(clause_registry));
    mapping.insert(
        "abstract_design_frame".to_owned(),
        entry_mapping(&packet.abstract_design_frame),
    );
    mapping.insert(
        "implementation_source_packet".to_owned(),
        entry_mapping(&packet.implementation_source_packet),
    );
    mapping.insert(
        "design_side_effect_map".to_owned(),
        entry_mapping(&packet.design_side_effect_map),
    );
    mapping.insert(
        "design_to_implementation_trace".to_owned(),
        entry_mapping(&packet.design_to_implementation_trace),
    );
    Value::Object(mapping)
}

pub fn validate_active_design_packet_reference_projection(
    packet_mapping: &Value,
    projection: &Yaml,
) -> bool {
    const PROJECTION_FIELDS: [&str; 9] = [
        "schema",
        "packet_sha256",
        "source_results",
        "dependency_results",
        "role_output_projections",
        "reviewer_artifact_projections",
        "clause_results",
        "output_results",
        "planned_output_paths",
    ];
    let Ok(projection) = string_mapping(projection, "active_design_packet_reference_projection")
    else {
        return false;
    };
    if projection.len() != PROJECTION_FIELDS.len()
        || PROJECTION_FIELDS
            .iter()
            .any(|field| !projection.contains_key(field))
        || projection.get("schema").and_then(|value| value.as_str())
            != Some(ACTIVE_DESIGN_PACKET_MATERIALIZATION_SCHEMA)
    {
        return false;
    }
    let expected_digest = match canonical_json_bytes(packet_mapping) {
        Ok(bytes) => Sha256::digest(bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>(),
        Err(_) => return false,
    };
    if projection
        .get("packet_sha256")
        .and_then(|value| value.as_str())
        != Some(expected_digest.as_str())
    {
        return false;
    }
    [
        "source_results",
        "dependency_results",
        "role_output_projections",
        "reviewer_artifact_projections",
        "clause_results",
        "output_results",
        "planned_output_paths",
    ]
    .iter()
    .all(|field| {
        projection
            .get(field)
            .is_some_and(|value| value.as_vec().is_some())
    })
}
