// @dependency-start
// contract implementation
// responsibility Renders the v3 public Skill shim readback expected from canonical catalog owners.
// upstream implementation ./skill_routes.rs provides validated catalog, route, and dependency values
// upstream design ../../../../../../documents/design/skill-runtime-shim-materialization.md owns the v3 record and projection contract
// downstream implementation ../skill_frontmatter.rs reports generated shim drift
// downstream test ../../tests/skill_frontmatter_native.rs qualifies fixed-point and drift readback
// @dependency-end

use super::skill_routes::{
    load_skill_catalog, load_skill_dependency_map, load_skill_route_rules, CapabilityRoute,
    SkillDependencyRule, SkillOrderConstraint, SkillRoutingRule,
};
use icu_normalizer::ComposingNormalizer;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::path::Path;
use yaml_rust2::Yaml;

const SKILL_CATALOG_PATH: &str = "agents/skills/catalog.yaml";
const SKILL_DEPENDENCY_MAP_PATH: &str = "agents/skills/skill-dependencies.yaml";
const RUNTIME_ROOT: &str = ".codex/personal/skills";
const CATALOG_REF: &str = "agents/skills/catalog.yaml";
const DEPENDENCY_REF: &str = "agents/skills/skill-dependencies.yaml";
const GRAPH_REF: &str = "documents/runtime/skill-dependency-graph.json";
const MATERIALIZER_ID: &str = "skill_shim_materializer.v3";
const TEMPLATE_ID: &str = "skill-runtime-shim-md-v3";
const SCHEMA_ID: &str = "agent_canon.skill_runtime_shim";
const RECORD_SCHEMA_ID: &str = "agent_canon.skill_runtime_shim.materialization_record";

/// The generated catalog-sized projection paths that differ from canonical rendering.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SkillMaterializationCheck {
    pub content_delta_paths: Vec<String>,
}

/// One fail-closed input, rendering, or readback error.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SkillMaterializationError {
    pub detail: String,
}

impl SkillMaterializationError {
    fn new(detail: impl Into<String>) -> Self {
        Self {
            detail: detail.into(),
        }
    }
}

impl fmt::Display for SkillMaterializationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.detail)
    }
}

impl std::error::Error for SkillMaterializationError {}

#[derive(Clone, Debug)]
struct CatalogEntry {
    skill: String,
    purpose: String,
    canonical_doc: String,
    shim_path: String,
    discovery_name: String,
    discovery_description: String,
}

#[derive(Serialize)]
struct RouteIdentity {
    skill: String,
    reason: String,
    stage_policy: String,
    triggers: Vec<Vec<String>>,
    capabilities: Vec<CapabilityIdentity>,
    related_skills: Vec<String>,
    responsibility_group: String,
}

#[derive(Serialize)]
struct CapabilityIdentity {
    skill: String,
    capability_id: String,
    owner: String,
    phase: String,
    activation: String,
    exclusive: bool,
}

#[derive(Serialize)]
struct DependencyIdentity {
    skill: String,
    responsibility_group: String,
    required_prerequisites: Vec<String>,
    routing_candidates: Vec<String>,
    successors: Vec<String>,
    order_constraints: Vec<OrderConstraintIdentity>,
    parallel_independent: Vec<String>,
}

#[derive(Serialize)]
struct OrderConstraintIdentity {
    before: String,
    after: String,
    reason: String,
}

#[derive(Serialize)]
struct CatalogIdentity {
    id: String,
    purpose: String,
    canonical_doc: String,
    shim: String,
    discovery: DiscoveryIdentity,
}

#[derive(Serialize)]
struct DiscoveryIdentity {
    name: String,
    description: String,
}

#[derive(Serialize)]
struct RecordBody {
    schema: RecordSchema,
    skill_id: String,
    discovery: RecordDiscovery,
    owner: RecordOwner,
    identity: RecordIdentity,
    render: RecordRender,
    provenance: RecordProvenance,
}

#[derive(Serialize)]
struct RecordSchema {
    id: String,
    version: u8,
}

#[derive(Serialize)]
struct RecordDiscovery {
    name: String,
    description: String,
    shim_path: String,
    method: String,
}

#[derive(Serialize)]
struct RecordOwner {
    canonical_doc: String,
    canonical_ref: String,
    catalog_ref: String,
    dependency_ref: String,
    route_ref: String,
    graph_ref: String,
}

#[derive(Serialize)]
struct RecordIdentity {
    catalog_identity_digest: String,
    dependency_identity_digest: String,
    route_identity_digest: String,
}

#[derive(Serialize)]
struct RecordRender {
    mode: String,
    template_id: String,
}

#[derive(Serialize)]
struct RecordProvenance {
    catalog_source_digest: String,
    dependency_source_digest: String,
    canonical_doc_digest: String,
    materializer_id: String,
}

#[derive(Serialize)]
struct MaterializationRecordComment {
    schema: String,
    version: u8,
    record_digest: String,
}

/// Render and compare every catalog-defined runtime Skill projection without writing files.
pub fn check(root: &Path) -> Result<SkillMaterializationCheck, SkillMaterializationError> {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let catalog = read_catalog_entries(&root)?;
    let skill_ids = catalog
        .iter()
        .map(|entry| entry.skill.clone())
        .collect::<Vec<_>>();
    let routes = load_skill_route_rules(&root)
        .map_err(|error| SkillMaterializationError::new(format!("owner_source_invalid:{error}")))?;
    let dependencies = load_skill_dependency_map(&root, Some(&skill_ids))
        .map_err(|error| SkillMaterializationError::new(format!("owner_source_invalid:{error}")))?;
    let routes = routes
        .into_iter()
        .map(|rule| (rule.skill.clone(), rule))
        .collect::<BTreeMap<_, _>>();
    let catalog_ids = skill_ids.iter().cloned().collect::<BTreeSet<_>>();
    let route_ids = routes.keys().cloned().collect::<BTreeSet<_>>();
    let dependency_ids = dependencies.keys().cloned().collect::<BTreeSet<_>>();
    if catalog_ids != route_ids || catalog_ids != dependency_ids {
        return Err(SkillMaterializationError::new("owner_skill_set_mismatch"));
    }

    let catalog_source_digest = file_digest(&root.join(SKILL_CATALOG_PATH))?;
    let dependency_source_digest = file_digest(&root.join(SKILL_DEPENDENCY_MAP_PATH))?;
    let mut drift = Vec::new();
    for entry in &catalog {
        let route = routes
            .get(&entry.skill)
            .ok_or_else(|| SkillMaterializationError::new("owner_skill_set_mismatch"))?;
        let dependency = dependencies
            .get(&entry.skill)
            .ok_or_else(|| SkillMaterializationError::new("owner_skill_set_mismatch"))?;
        let rendered = render_shim(
            &root,
            entry,
            route,
            dependency,
            &catalog_source_digest,
            &dependency_source_digest,
        )?;
        let target = root.join(&entry.shim_path);
        let differs = if !target.is_file() {
            true
        } else {
            fs::read(&target).map_err(io_error)?.as_slice() != rendered.as_bytes()
        };
        if differs {
            drift.push(entry.shim_path.clone());
        }
    }
    drift.sort();
    Ok(SkillMaterializationCheck {
        content_delta_paths: drift,
    })
}

fn read_catalog_entries(root: &Path) -> Result<Vec<CatalogEntry>, SkillMaterializationError> {
    let data = load_skill_catalog(root).map_err(SkillMaterializationError::new)?;
    let families = get(&data, "skill_families")
        .and_then(Yaml::as_vec)
        .ok_or_else(|| SkillMaterializationError::new("catalog_skill_families_invalid"))?;
    let mut entries = Vec::with_capacity(families.len());
    let mut seen = BTreeSet::new();
    for (index, family) in families.iter().enumerate() {
        let field = format!("skill_families[{index}]");
        let skill = required_string(family, "id", &field)?;
        if !seen.insert(skill.clone()) {
            return Err(SkillMaterializationError::new(format!(
                "catalog_duplicate:{skill}"
            )));
        }
        let purpose = required_string(family, "purpose", &field)?;
        let canonical_doc = required_string(family, "canonical_doc", &field)?;
        let shim_path = required_string(family, "shim", &field)?;
        let discovery = get(family, "discovery").ok_or_else(|| {
            SkillMaterializationError::new(format!("{field}.discovery is required"))
        })?;
        let discovery_name = required_string(discovery, "name", &format!("{field}.discovery"))?;
        let discovery_description =
            required_string(discovery, "description", &format!("{field}.discovery"))?;
        if discovery_name != skill {
            return Err(SkillMaterializationError::new(format!(
                "discovery_name_mismatch:{skill}"
            )));
        }
        entries.push(CatalogEntry {
            skill,
            purpose,
            canonical_doc,
            shim_path,
            discovery_name,
            discovery_description,
        });
    }
    Ok(entries)
}

fn get<'a>(value: &'a Yaml, key: &str) -> Option<&'a Yaml> {
    value
        .as_hash()?
        .iter()
        .find_map(|(candidate, item)| (candidate.as_str() == Some(key)).then_some(item))
}

fn required_string(
    value: &Yaml,
    key: &str,
    owner: &str,
) -> Result<String, SkillMaterializationError> {
    get(value, key)
        .and_then(Yaml::as_str)
        .map(str::to_owned)
        .ok_or_else(|| SkillMaterializationError::new(format!("{owner}.{key} is required")))
}

fn render_shim(
    root: &Path,
    entry: &CatalogEntry,
    route: &SkillRoutingRule,
    dependency: &SkillDependencyRule,
    catalog_source_digest: &str,
    dependency_source_digest: &str,
) -> Result<String, SkillMaterializationError> {
    let expected_doc = format!("agents/skills/{}.md", entry.skill);
    let expected_shim = format!("{RUNTIME_ROOT}/{}/SKILL.md", entry.skill);
    if entry.shim_path != expected_shim {
        return Err(SkillMaterializationError::new(format!(
            "shim_path_mismatch:{}",
            entry.skill
        )));
    }
    if entry.canonical_doc != expected_doc {
        return Err(SkillMaterializationError::new(format!(
            "canonical_doc_mismatch:{}",
            entry.skill
        )));
    }
    let canonical_path = root.join(&entry.canonical_doc);
    if !canonical_path.is_file() {
        return Err(SkillMaterializationError::new(format!(
            "missing_canonical_doc:{}",
            entry.skill
        )));
    }

    let route_identity = domain_digest(
        "agent-canon.skill-runtime-shim.owner.route.v1",
        &route_identity_payload(route),
    )?;
    let dependency_identity = domain_digest(
        "agent-canon.skill-runtime-shim.owner.dependency.v1",
        &dependency_identity_payload(dependency),
    )?;
    let catalog_identity = domain_digest(
        "agent-canon.skill-runtime-shim.owner.catalog.v1",
        &CatalogIdentity {
            id: normalize(&entry.skill),
            purpose: normalize(&entry.purpose),
            canonical_doc: normalize(&entry.canonical_doc),
            shim: normalize(&entry.shim_path),
            discovery: DiscoveryIdentity {
                name: normalize(&entry.discovery_name),
                description: normalize(&entry.discovery_description),
            },
        },
    )?;
    let canonical_doc_digest = file_digest(&canonical_path)?;
    let record = RecordBody {
        schema: RecordSchema {
            id: SCHEMA_ID.to_owned(),
            version: 3,
        },
        skill_id: normalize(&entry.skill),
        discovery: RecordDiscovery {
            name: normalize(&entry.discovery_name),
            description: normalize(&entry.discovery_description),
            shim_path: normalize(&entry.shim_path),
            method: "managed-global-agents-skills-discovery".to_owned(),
        },
        owner: RecordOwner {
            canonical_doc: normalize(&entry.canonical_doc),
            canonical_ref: normalize(&format!(
                "{CATALOG_REF}#skill:{}.canonical_doc",
                entry.skill
            )),
            catalog_ref: normalize(&format!("{CATALOG_REF}#skill:{}", entry.skill)),
            dependency_ref: normalize(&format!("{DEPENDENCY_REF}#invocation:{}", entry.skill)),
            route_ref: normalize(&format!("{CATALOG_REF}#skill:{}.routing", entry.skill)),
            graph_ref: normalize(&format!("{GRAPH_REF}#skill:{}", entry.skill)),
        },
        identity: RecordIdentity {
            catalog_identity_digest: catalog_identity,
            dependency_identity_digest: dependency_identity,
            route_identity_digest: route_identity,
        },
        render: RecordRender {
            mode: "adapter_only".to_owned(),
            template_id: TEMPLATE_ID.to_owned(),
        },
        provenance: RecordProvenance {
            catalog_source_digest: catalog_source_digest.to_owned(),
            dependency_source_digest: dependency_source_digest.to_owned(),
            canonical_doc_digest,
            materializer_id: MATERIALIZER_ID.to_owned(),
        },
    };
    let record_digest = domain_digest("agent-canon.skill-runtime-shim.record.v3", &record)?;
    let record_comment = json_compact(&MaterializationRecordComment {
        schema: RECORD_SCHEMA_ID.to_owned(),
        version: 3,
        record_digest,
    })?;
    let metadata_comment = format!("<!-- materialization-record: {record_comment} -->");
    let canonical_link = format!("../../../../{}", entry.canonical_doc);
    let description = json_compact(&normalize(&entry.discovery_description))?;
    let lines = [
        "---".to_owned(),
        format!("name: {}", normalize(&entry.discovery_name)),
        format!("description: {description}"),
        "---".to_owned(),
        metadata_comment,
        String::new(),
        "<!--".to_owned(),
        "@dependency-start".to_owned(),
        "contract skill".to_owned(),
        format!(
            "responsibility Exposes {} for runtime discovery.",
            entry.skill
        ),
        format!("upstream design {canonical_link} owner"),
        "@dependency-end".to_owned(),
        "-->".to_owned(),
        String::new(),
        format!("# {}", entry.skill),
        String::new(),
        "## Canonical Skill".to_owned(),
        String::new(),
        format!(
            "Canonical workflow and policy: [{}]({canonical_link}).",
            entry.skill
        ),
        String::new(),
        "1. Read the canonical owner before applying this skill.".to_owned(),
        String::new(),
    ];
    let rendered = lines.join("\n");
    if contains_absolute_locator(&rendered) {
        return Err(SkillMaterializationError::new(format!(
            "absolute_locator:{}",
            entry.skill
        )));
    }
    Ok(rendered)
}

fn route_identity_payload(rule: &SkillRoutingRule) -> RouteIdentity {
    RouteIdentity {
        skill: normalize(&rule.skill),
        reason: normalize(&rule.reason),
        stage_policy: normalize(&rule.stage_policy),
        triggers: rule
            .triggers
            .iter()
            .map(|group| group.iter().map(|value| normalize(value)).collect())
            .collect(),
        capabilities: rule.capabilities.iter().map(capability_identity).collect(),
        related_skills: rule
            .related_skills
            .iter()
            .map(|value| normalize(value))
            .collect(),
        responsibility_group: normalize(&rule.responsibility_group),
    }
}

fn capability_identity(route: &CapabilityRoute) -> CapabilityIdentity {
    CapabilityIdentity {
        skill: normalize(&route.skill),
        capability_id: normalize(&route.capability_id),
        owner: normalize(&route.owner),
        phase: normalize(&route.phase),
        activation: normalize(&route.activation),
        exclusive: route.exclusive,
    }
}

fn dependency_identity_payload(rule: &SkillDependencyRule) -> DependencyIdentity {
    DependencyIdentity {
        skill: normalize(&rule.skill),
        responsibility_group: normalize(&rule.responsibility_group),
        required_prerequisites: rule
            .required_prerequisites
            .iter()
            .map(|value| normalize(value))
            .collect(),
        routing_candidates: rule
            .routing_candidates
            .iter()
            .map(|value| normalize(value))
            .collect(),
        successors: rule
            .successors
            .iter()
            .map(|value| normalize(value))
            .collect(),
        order_constraints: rule
            .order_constraints
            .iter()
            .map(order_constraint_identity)
            .collect(),
        parallel_independent: rule
            .parallel_independent
            .iter()
            .map(|value| normalize(value))
            .collect(),
    }
}

fn order_constraint_identity(item: &SkillOrderConstraint) -> OrderConstraintIdentity {
    OrderConstraintIdentity {
        before: normalize(&item.before),
        after: normalize(&item.after),
        reason: normalize(&item.reason),
    }
}

fn normalize(value: &str) -> String {
    ComposingNormalizer::new_nfc()
        .normalize(value)
        .replace("\r\n", "\n")
        .replace('\r', "\n")
}

fn domain_digest<T: Serialize>(
    domain: &str,
    value: &T,
) -> Result<String, SkillMaterializationError> {
    let bytes = serde_json::to_vec(value).map_err(|error| {
        SkillMaterializationError::new(format!("canonical_json_invalid:{error}"))
    })?;
    let mut hasher = Sha256::new();
    hasher.update(domain.as_bytes());
    hasher.update([0]);
    hasher.update(bytes);
    let digest = hasher.finalize();
    Ok(hex_digest(&digest))
}

fn file_digest(path: &Path) -> Result<String, SkillMaterializationError> {
    let content = fs::read(path).map_err(io_error)?;
    let digest = Sha256::digest(content);
    Ok(hex_digest(&digest))
}

fn hex_digest(bytes: &[u8]) -> String {
    let mut text = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        use std::fmt::Write as _;
        let _ = write!(text, "{byte:02x}");
    }
    text
}

fn json_compact<T: Serialize>(value: &T) -> Result<String, SkillMaterializationError> {
    serde_json::to_string(value)
        .map_err(|error| SkillMaterializationError::new(format!("render_json_invalid:{error}")))
}

fn io_error(error: std::io::Error) -> SkillMaterializationError {
    SkillMaterializationError::new(error.to_string())
}

fn contains_absolute_locator(text: &str) -> bool {
    let bytes = text.as_bytes();
    for (index, character) in text.char_indices() {
        if character != '/' {
            continue;
        }
        if index > 0 {
            let previous = text[..index].chars().next_back().unwrap_or_default();
            if previous.is_ascii_alphanumeric()
                || matches!(previous, '.' | '_' | '~' | '/' | '<' | '>' | '-')
            {
                continue;
            }
        }
        let mut cursor = index + 1;
        while cursor < bytes.len()
            && (bytes[cursor].is_ascii_alphanumeric()
                || matches!(bytes[cursor], b'.' | b'_' | b'-'))
        {
            cursor += 1;
        }
        if cursor > index + 1 {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn absolute_locator_matches_the_materializer_boundary_rules() {
        assert!(contains_absolute_locator("use /tmp/private/file"));
        assert!(!contains_absolute_locator("relative/path/to/file"));
        assert!(!contains_absolute_locator("https://example.invalid/a"));
    }

    #[test]
    fn digest_uses_utf8_nfc_canonical_json_bytes() {
        #[derive(Serialize)]
        struct Payload {
            value: String,
        }
        let normalized = normalize("e\u{301}\r\nline");
        assert_eq!(normalized, "é\nline");
        let actual = domain_digest("fixture", &Payload { value: normalized }).unwrap();
        assert_eq!(
            actual,
            "350e25829cf8f6c0111e16d1a775509b62ee7a58d81137aa59597f99d3958dc3"
        );
    }
}
