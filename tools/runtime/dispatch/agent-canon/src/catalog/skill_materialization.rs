// @dependency-start
// contract implementation
// responsibility Renders, materializes, and reads back the v3 public Skill shim projections.
// upstream implementation ./skill_routes.rs provides validated catalog, route, and dependency values
// upstream design ../../../../../../documents/design/skill-runtime-shim-materialization.md owns the v3 record and projection contract
// upstream implementation ../source_mutation.rs owns exact source paths and atomic materialization
// downstream implementation ../skill_frontmatter.rs reports generated shim drift
// downstream test ../../../../../../tests/agent_tools/test_skill_shim_materializer.py exercises the native CLI and independent migration/readback oracles
// @dependency-end

use super::skill_routes::{
    load_skill_catalog, load_skill_dependency_map, load_skill_route_rules, CapabilityRoute,
    SkillDependencyRule, SkillOrderConstraint, SkillRoutingRule,
};
use crate::path_resolution::resolve_non_strict;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::source_mutation::{open_root_nofollow, SourceMutationCapability};
use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt};
use icu_normalizer::ComposingNormalizer;
use serde::ser::SerializeMap;
use serde::{Serialize, Serializer};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use yaml_rust2::{Yaml, YamlLoader};

const SKILL_CATALOG_PATH: &str = "agents/skills/catalog.yaml";
const SKILL_DEPENDENCY_MAP_PATH: &str = "agents/skills/skill-dependencies.yaml";
const RUNTIME_ROOT: &str = ".codex/personal/skills";
const CATALOG_REF: &str = "agents/skills/catalog.yaml";
const DEPENDENCY_REF: &str = "agents/skills/skill-dependencies.yaml";
const GRAPH_REF: &str = "documents/runtime/skill-dependency-graph.json";
pub const MATERIALIZER_ID: &str = "skill_shim_materializer.v3";
const TEMPLATE_ID: &str = "skill-runtime-shim-md-v3";
const SCHEMA_ID: &str = "agent_canon.skill_runtime_shim";
const RECORD_SCHEMA_ID: &str = "agent_canon.skill_runtime_shim.materialization_record";
pub const SELECTOR: &str = "skill-shim-materializer";
const MATERIALIZER_USAGE: &str = "usage: agent-canon skill-shim-materializer {check,materialize,readback} [--root ROOT] --all [--output-root ROOT] [--format text|json] [--source-mutation-capability-json JSON]";

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
struct RenderedSkill {
    skill: String,
    path: String,
    canonical_doc: String,
    discovery_description: String,
    content: String,
    record_digest: String,
    projection_digest: String,
}

/// One immutable native projection consumed by the retained Skill Eval producer.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SkillShimProjection {
    pub skill_id: String,
    pub canonical_doc: String,
    pub discovery_description: String,
    pub content: String,
    pub record_digest: String,
    pub projection_digest: String,
}

/// Catalog-sized deterministic rendering and source identity for one Eval run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SkillShimCatalog {
    pub source_snapshot_digest: String,
    pub skills: Vec<SkillShimProjection>,
}

#[derive(Clone, Debug)]
struct MaterializationPlan {
    output_root: std::path::PathBuf,
    source_snapshot_digest: String,
    skills: Vec<RenderedSkill>,
}

/// A source writer rejection, unresolved legacy receipt, or partial publish stop.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SkillShimMaterializerFailure {
    Input(SkillMaterializationError),
    LegacyMigration(Vec<serde_json::Value>),
    PartialStop { path: String, replaced: usize },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum MaterializerCommand {
    Check,
    Materialize,
    Readback,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum MaterializerFormat {
    Text,
    Json,
}

struct MaterializerOptions {
    command: MaterializerCommand,
    root: PathBuf,
    output_root: Option<PathBuf>,
    all: bool,
    format: MaterializerFormat,
    capability_json: Option<String>,
}

#[derive(Clone, Debug)]
struct RenderedShim {
    content: String,
    record_digest: String,
    canonical_doc_digest: String,
}

#[derive(Serialize)]
struct ProjectionIdentity {
    skill_id: String,
    record_digest: String,
    content_sha256: String,
}

#[derive(Serialize)]
struct ReadbackIdentity {
    skill_id: String,
    content_sha256: String,
    record_digest: String,
    projection_digest: String,
}

#[derive(Serialize)]
struct SourceSnapshot<'a> {
    catalog: &'a str,
    dependencies: &'a str,
    canonical_docs: &'a str,
}

struct OrderedDigestMap<'a>(&'a [(String, String)]);

impl Serialize for OrderedDigestMap<'_> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut map = serializer.serialize_map(Some(self.0.len()))?;
        for (key, value) in self.0 {
            map.serialize_entry(key, value)?;
        }
        map.end()
    }
}

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
    let plan = build_plan(root, None)?;
    let drift = drift_paths(&plan)?;
    Ok(SkillMaterializationCheck {
        content_delta_paths: drift,
    })
}

/// Return the complete native materializer check payload without writing files.
pub fn check_payload(
    root: &Path,
    output_root: Option<&Path>,
) -> Result<serde_json::Value, SkillMaterializationError> {
    let plan = build_plan(root, output_root)?;
    staged_readback(&plan)?;
    let drift = drift_paths(&plan)?;
    let record_digests = plan
        .skills
        .iter()
        .map(|skill| (skill.skill.clone(), skill.record_digest.clone()))
        .collect::<BTreeMap<_, _>>();
    let projection_digests = plan
        .skills
        .iter()
        .map(|skill| (skill.skill.clone(), skill.projection_digest.clone()))
        .collect::<BTreeMap<_, _>>();
    Ok(json!({
        "schema": "agent_canon.skill_runtime_shim.check",
        "version": 3,
        "source_snapshot_digest": plan.source_snapshot_digest,
        "record_digests": record_digests,
        "projection_digests": projection_digests,
        "content_delta_count": drift.len(),
        "content_delta_paths": drift,
        "status": if drift.is_empty() { "pass" } else { "fail" },
    }))
}

/// Read every generated target and return the fixed-size readback manifest.
pub fn readback_payload(
    root: &Path,
    output_root: Option<&Path>,
) -> Result<serde_json::Value, SkillMaterializationError> {
    let plan = build_plan(root, output_root)?;
    staged_readback(&plan)?;
    let readback_digest = readback_digest(&plan)?;
    let record_digests = plan
        .skills
        .iter()
        .map(|skill| (skill.skill.clone(), skill.record_digest.clone()))
        .collect::<BTreeMap<_, _>>();
    let projection_digests = plan
        .skills
        .iter()
        .map(|skill| (skill.skill.clone(), skill.projection_digest.clone()))
        .collect::<BTreeMap<_, _>>();
    Ok(json!({
        "schema": "agent_canon.skill_runtime_shim.readback",
        "version": 3,
        "source_snapshot_digest": plan.source_snapshot_digest,
        "record_digests": record_digests,
        "projection_digests": projection_digests,
        "readback_digest": readback_digest,
        "readback_count": plan.skills.len(),
        "status": "pass",
    }))
}

/// Materialize all catalog Skills under an exact source mutation capability.
pub fn materialize_payload(
    root: &Path,
    output_root: Option<&Path>,
    capability_json: Option<&str>,
) -> Result<serde_json::Value, SkillShimMaterializerFailure> {
    let plan = build_plan(root, output_root).map_err(SkillShimMaterializerFailure::Input)?;
    staged_readback(&plan).map_err(SkillShimMaterializerFailure::Input)?;
    let legacy = plan
        .skills
        .iter()
        .map(|skill| classify_legacy(&plan, skill))
        .collect::<Result<Vec<_>, _>>()
        .map_err(SkillShimMaterializerFailure::Input)?;
    if legacy.iter().any(|row| {
        row.get("unmatched_blocks")
            .and_then(serde_json::Value::as_array)
            .is_some_and(|blocks| !blocks.is_empty())
    }) {
        return Err(SkillShimMaterializerFailure::LegacyMigration(legacy));
    }
    let raw_capability = capability_json.ok_or_else(|| {
        SkillShimMaterializerFailure::Input(SkillMaterializationError::new(
            "mutation_capability_required:pass --source-mutation-capability-json",
        ))
    })?;
    let capability = SourceMutationCapability::from_json(&plan.output_root, Some(raw_capability))
        .map_err(|error| {
        SkillShimMaterializerFailure::Input(SkillMaterializationError::new(error.to_string()))
    })?;

    let mut ordered = plan.skills.iter().collect::<Vec<_>>();
    ordered.sort_by(|left, right| left.skill.cmp(&right.skill));
    let mut delta_paths = Vec::new();
    let mut replaced = 0;
    for skill in ordered {
        let target = plan.output_root.join(&skill.path);
        let current = read_source_file(&capability, &plan.output_root, &target)
            .map_err(SkillShimMaterializerFailure::Input)?;
        let unchanged = current.as_ref().is_some_and(|current| {
            current.bytes.as_slice() == skill.content.as_bytes()
                && current.mode.is_none_or(|mode| mode == 0o644)
        });
        if unchanged {
            continue;
        }
        if let Err(_error) = capability.atomic_write_text_with_parents(
            Path::new(&skill.path),
            &skill.content,
            0o644,
            true,
        ) {
            return Err(SkillShimMaterializerFailure::PartialStop {
                path: relative_path(&plan.output_root, &target),
                replaced,
            });
        }
        replaced += 1;
        delta_paths.push(relative_path(&plan.output_root, &target));
    }
    delta_paths.sort();
    let readback_digest = readback_digest(&plan).map_err(SkillShimMaterializerFailure::Input)?;
    Ok(json!({
        "schema": "agent_canon.skill_runtime_shim.materialize",
        "version": 3,
        "source_snapshot_digest": plan.source_snapshot_digest,
        "record_digests": record_digest_map(&plan),
        "projection_digests": projection_digest_map(&plan),
        "readback_digest": readback_digest,
        "content_delta_count": delta_paths.len(),
        "content_delta_paths": delta_paths,
        "legacy_resolution_count": legacy.len(),
        "legacy_migration_receipt": legacy,
        "replaced_count": replaced,
        "status": "pass",
    }))
}

/// Run two writes and compare all record, projection, and readback identities.
pub fn fixed_point_payload(
    root: &Path,
    output_root: Option<&Path>,
    capability_json: &str,
) -> Result<serde_json::Value, SkillShimMaterializerFailure> {
    let first = materialize_payload(root, output_root, Some(capability_json))?;
    let second = materialize_payload(root, output_root, Some(capability_json))?;
    let equal_records = first["record_digests"] == second["record_digests"];
    let equal_projections = first["projection_digests"] == second["projection_digests"];
    let equal_readback = first["readback_digest"] == second["readback_digest"];
    let second_is_empty =
        second["content_delta_count"] == 0 && second["content_delta_paths"] == json!([]);
    let status = if equal_records && equal_projections && equal_readback && second_is_empty {
        "pass"
    } else {
        "fail"
    };
    Ok(json!({
        "schema": "agent_canon.skill_runtime_shim.fixed_point",
        "version": 3,
        "source_snapshot_digest": first["source_snapshot_digest"],
        "first_run": {
            "record_digests": first["record_digests"],
            "projection_digests": first["projection_digests"],
            "readback_digest": first["readback_digest"],
            "content_delta_count": first["content_delta_count"],
            "content_delta_paths": first["content_delta_paths"],
        },
        "second_run": {
            "record_digests": second["record_digests"],
            "projection_digests": second["projection_digests"],
            "readback_digest": second["readback_digest"],
            "content_delta_count": second["content_delta_count"],
            "content_delta_paths": second["content_delta_paths"],
        },
        "equal_record_digests": equal_records,
        "equal_projection_digests": equal_projections,
        "equal_readback_digest": equal_readback,
        "status": status,
    }))
}

/// Run the retained all-skill check, materialize, or readback command.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_materializer_args(args) {
        Ok(Some(options)) => options,
        Ok(None) => {
            println!("{MATERIALIZER_USAGE}\n\nRender, check, or materialize the v3 public Skill shim set.");
            return 0;
        }
        Err(error) => {
            eprintln!("{MATERIALIZER_USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    if !options.all {
        return print_materializer_failure("all_required", "");
    }
    let result = match options.command {
        MaterializerCommand::Check => check_payload(&options.root, options.output_root.as_deref()),
        MaterializerCommand::Readback => {
            readback_payload(&options.root, options.output_root.as_deref())
        }
        MaterializerCommand::Materialize => {
            return match materialize_payload(
                &options.root,
                options.output_root.as_deref(),
                options.capability_json.as_deref(),
            ) {
                Ok(payload) => print_payload(&payload, options.format),
                Err(error) => print_materializer_error(error),
            };
        }
    };
    match result {
        Ok(payload) => print_payload(&payload, options.format),
        Err(error) => print_materializer_failure_from_input(error),
    }
}

fn parse_materializer_args(args: &[String]) -> Result<Option<MaterializerOptions>, String> {
    let Some(command) = args.first() else {
        return Err("the following arguments are required: command".to_owned());
    };
    let command = match command.as_str() {
        "check" => MaterializerCommand::Check,
        "materialize" => MaterializerCommand::Materialize,
        "readback" => MaterializerCommand::Readback,
        "-h" | "--help" => return Ok(None),
        value => {
            return Err(format!(
                "invalid choice: '{value}' (choose from 'check', 'materialize', 'readback')"
            ))
        }
    };
    let mut root = None;
    let mut output_root = None;
    let mut all = false;
    let mut format = MaterializerFormat::Text;
    let mut capability_json = None;
    let options = [
        ("--help", 0_u8),
        ("--root", 1),
        ("--all", 2),
        ("--output-root", 3),
        ("--format", 4),
        ("--source-mutation-capability-json", 5),
        ("--mutation-capability-json", 5),
    ];
    let mut index = 1;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "-h" {
            return Ok(None);
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument, None), |(option, value)| (option, Some(value)));
        let selected =
            resolve_long_option_prefix(option, &options).map_err(|error| match error {
                LongOptionError::Unrecognized => format!("unrecognized arguments: {argument}"),
                LongOptionError::Ambiguous(matches) => format!(
                    "ambiguous option: {option} could match {}",
                    matches.join(", ")
                ),
            })?;
        if selected == 0 {
            return Ok(None);
        }
        if selected == 2 {
            if inline_value.is_some() {
                return Err(format!("argument {option}: ignored explicit argument"));
            }
            all = true;
            index += 1;
            continue;
        }
        let value = if let Some(value) = inline_value {
            value
        } else {
            index += 1;
            args.get(index)
                .ok_or_else(|| format!("argument {option}: expected one argument"))?
                .as_str()
        };
        match selected {
            0 => return Ok(None),
            1 => root = Some(PathBuf::from(value)),
            2 => unreachable!("flag was handled above"),
            3 => output_root = Some(PathBuf::from(value)),
            4 => {
                format = match value {
                    "text" => MaterializerFormat::Text,
                    "json" => MaterializerFormat::Json,
                    _ => {
                        return Err(format!(
                            "invalid choice: '{value}' (choose from 'text', 'json')"
                        ))
                    }
                }
            }
            5 => capability_json = Some(value.to_owned()),
            _ => unreachable!("all materializer options are registered"),
        }
        index += 1;
    }
    let root = match root {
        Some(root) => root,
        None => std::env::current_dir()
            .map_err(|error| format!("resolve current directory: {error}"))?,
    };
    Ok(Some(MaterializerOptions {
        command,
        root,
        output_root,
        all,
        format,
        capability_json,
    }))
}

fn print_payload(payload: &serde_json::Value, format: MaterializerFormat) -> i32 {
    if format == MaterializerFormat::Json {
        match serde_json::to_string_pretty(payload) {
            Ok(text) => println!("{text}"),
            Err(error) => {
                return print_materializer_failure("render_json_invalid", &error.to_string())
            }
        }
    } else {
        println!(
            "SKILL_SHIM_MATERIALIZER_SCHEMA={}",
            payload["schema"].as_str().unwrap_or("")
        );
        println!(
            "SKILL_SHIM_MATERIALIZER_STATUS={}",
            payload["status"].as_str().unwrap_or("")
        );
        for key in [
            "source_snapshot_digest",
            "content_delta_count",
            "readback_digest",
        ] {
            if let Some(value) = payload.get(key) {
                println!("SKILL_SHIM_MATERIALIZER_{}={value}", key.to_uppercase());
            }
        }
        if let Some(paths) = payload
            .get("content_delta_paths")
            .and_then(serde_json::Value::as_array)
        {
            for path in paths {
                if let Some(path) = path.as_str() {
                    println!("SKILL_SHIM_MATERIALIZER_DELTA={path}");
                }
            }
        }
    }
    if payload["status"] == "pass" {
        0
    } else {
        1
    }
}

fn print_materializer_error(error: SkillShimMaterializerFailure) -> i32 {
    match error {
        SkillShimMaterializerFailure::Input(error) => print_materializer_failure_from_input(error),
        SkillShimMaterializerFailure::LegacyMigration(receipt) => {
            let text = serde_json::to_string(&receipt).unwrap_or_else(|_| "[]".to_owned());
            println!("SKILL_SHIM_MATERIALIZER_LEGACY_RECEIPT={text}");
            print_materializer_failure("unresolved_legacy_blocks", "")
        }
        SkillShimMaterializerFailure::PartialStop { path, replaced } => {
            print_materializer_failure("partial_stop", &format!("path={path}:replaced={replaced}"))
        }
    }
}

fn print_materializer_failure_from_input(error: SkillMaterializationError) -> i32 {
    let (code, detail) = error.detail.split_once(':').unwrap_or((&error.detail, ""));
    print_materializer_failure(code, detail)
}

fn print_materializer_failure(code: &str, detail: &str) -> i32 {
    println!("SKILL_SHIM_MATERIALIZER_FAILURE={code}:{detail}");
    2
}

fn record_digest_map(plan: &MaterializationPlan) -> BTreeMap<String, String> {
    plan.skills
        .iter()
        .map(|skill| (skill.skill.clone(), skill.record_digest.clone()))
        .collect()
}

fn projection_digest_map(plan: &MaterializationPlan) -> BTreeMap<String, String> {
    plan.skills
        .iter()
        .map(|skill| (skill.skill.clone(), skill.projection_digest.clone()))
        .collect()
}

fn staged_readback(plan: &MaterializationPlan) -> Result<(), SkillMaterializationError> {
    for skill in &plan.skills {
        let data = skill.content.as_bytes();
        let text = std::str::from_utf8(data).map_err(|_| {
            SkillMaterializationError::new(format!("staged_readback_decode:{}", skill.skill))
        })?;
        if contains_absolute_locator(text) {
            return Err(SkillMaterializationError::new(format!(
                "absolute_locator:{}",
                skill.skill
            )));
        }
        let mut separators = text.splitn(3, "---");
        let _before = separators.next();
        let frontmatter = separators.next().ok_or_else(|| {
            SkillMaterializationError::new(format!("staged_frontmatter_mismatch:{}", skill.skill))
        })?;
        let documents = YamlLoader::load_from_str(frontmatter).map_err(|_| {
            SkillMaterializationError::new(format!("staged_frontmatter_mismatch:{}", skill.skill))
        })?;
        let name = documents
            .first()
            .and_then(|document| get(document, "name"))
            .and_then(Yaml::as_str);
        if name != Some(skill.skill.as_str()) {
            return Err(SkillMaterializationError::new(format!(
                "staged_frontmatter_mismatch:{}",
                skill.skill
            )));
        }
        if text.matches("<!-- materialization-record:").count() != 1 {
            return Err(SkillMaterializationError::new(format!(
                "materialization_record_count:{}",
                skill.skill
            )));
        }
    }
    Ok(())
}

fn readback_digest(plan: &MaterializationPlan) -> Result<String, SkillMaterializationError> {
    let mut skills = plan.skills.iter().collect::<Vec<_>>();
    skills.sort_by(|left, right| left.skill.cmp(&right.skill));
    let mut rows = Vec::with_capacity(skills.len());
    for skill in skills {
        let path = plan.output_root.join(&skill.path);
        if !path.is_file() {
            return Err(SkillMaterializationError::new(format!(
                "readback_missing:{}",
                skill.skill
            )));
        }
        let content = fs::read(&path).map_err(io_error)?;
        let text = std::str::from_utf8(&content).map_err(|_| {
            SkillMaterializationError::new(format!("readback_invalid_utf8:{}", skill.skill))
        })?;
        let expected_record = json_compact(&MaterializationRecordComment {
            schema: RECORD_SCHEMA_ID.to_owned(),
            version: 3,
            record_digest: skill.record_digest.clone(),
        })?;
        let expected_comment = format!("<!-- materialization-record: {expected_record} -->");
        if text.matches("<!-- materialization-record:").count() != 1
            || text.matches(&expected_comment).count() != 1
        {
            return Err(SkillMaterializationError::new(format!(
                "materialization_record_mismatch:{}",
                skill.skill
            )));
        }
        if content != skill.content.as_bytes() {
            return Err(SkillMaterializationError::new(format!(
                "readback_mismatch:{}",
                skill.skill
            )));
        }
        rows.push(ReadbackIdentity {
            skill_id: skill.skill.clone(),
            content_sha256: sha256_hex(&content),
            record_digest: skill.record_digest.clone(),
            projection_digest: skill.projection_digest.clone(),
        });
    }
    if rows.len() != plan.skills.len() {
        return Err(SkillMaterializationError::new(format!(
            "readback_count_mismatch:{}",
            rows.len()
        )));
    }
    domain_digest("agent-canon.skill-runtime-shim.readback.v1", &rows)
}

fn build_plan(
    root: &Path,
    output_root: Option<&Path>,
) -> Result<MaterializationPlan, SkillMaterializationError> {
    let root = resolve_non_strict(root).map_err(SkillMaterializationError::new)?;
    let output_root = output_root
        .map(resolve_non_strict)
        .transpose()
        .map_err(SkillMaterializationError::new)?
        .unwrap_or_else(|| root.clone());
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
    let mut skills = Vec::with_capacity(catalog.len());
    let mut canonical_docs = Vec::with_capacity(catalog.len());
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
        let projection_digest = domain_digest(
            "agent-canon.skill-runtime-shim.projection.v1",
            &ProjectionIdentity {
                skill_id: entry.skill.clone(),
                record_digest: rendered.record_digest.clone(),
                content_sha256: sha256_hex(rendered.content.as_bytes()),
            },
        )?;
        canonical_docs.push((entry.skill.clone(), rendered.canonical_doc_digest));
        skills.push(RenderedSkill {
            skill: entry.skill.clone(),
            path: entry.shim_path.clone(),
            canonical_doc: entry.canonical_doc.clone(),
            discovery_description: entry.discovery_description.clone(),
            content: rendered.content,
            record_digest: rendered.record_digest,
            projection_digest,
        });
    }
    let canonical_docs_digest = domain_digest(
        "agent-canon.skill-runtime-shim.canonical-docs.v1",
        &OrderedDigestMap(&canonical_docs),
    )?;
    let source_snapshot_digest = domain_digest(
        "agent-canon.skill-runtime-shim.source-snapshot.v1",
        &SourceSnapshot {
            catalog: &catalog_source_digest,
            dependencies: &dependency_source_digest,
            canonical_docs: &canonical_docs_digest,
        },
    )?;
    Ok(MaterializationPlan {
        output_root,
        source_snapshot_digest,
        skills,
    })
}

/// Render the catalog-sized native view without writing targets.
pub fn render_catalog(root: &Path) -> Result<SkillShimCatalog, SkillMaterializationError> {
    let plan = build_plan(root, None)?;
    Ok(SkillShimCatalog {
        source_snapshot_digest: plan.source_snapshot_digest,
        skills: plan
            .skills
            .into_iter()
            .map(|skill| SkillShimProjection {
                skill_id: skill.skill,
                canonical_doc: skill.canonical_doc,
                discovery_description: skill.discovery_description,
                content: skill.content,
                record_digest: skill.record_digest,
                projection_digest: skill.projection_digest,
            })
            .collect(),
    })
}

fn drift_paths(plan: &MaterializationPlan) -> Result<Vec<String>, SkillMaterializationError> {
    let mut drift = Vec::new();
    for skill in &plan.skills {
        let target = plan.output_root.join(&skill.path);
        let differs = if !target.is_file() {
            true
        } else {
            fs::read(&target).map_err(io_error)?.as_slice() != skill.content.as_bytes()
        };
        if differs {
            drift.push(relative_path(&plan.output_root, &target));
        }
    }
    drift.sort();
    Ok(drift)
}

struct ExistingTarget {
    bytes: Vec<u8>,
    mode: Option<u32>,
}

fn read_source_file(
    capability: &SourceMutationCapability,
    root: &Path,
    target: &Path,
) -> Result<Option<ExistingTarget>, SkillMaterializationError> {
    let resolved = capability
        .assert_allowed(target)
        .map_err(|error| SkillMaterializationError::new(error.to_string()))?;
    let relative = resolved.strip_prefix(root).map_err(|_| {
        SkillMaterializationError::new(format!(
            "mutation target is outside source: {}",
            target.display()
        ))
    })?;
    read_target_nofollow(root, relative)
}

fn read_target_nofollow(
    root: &Path,
    relative: &Path,
) -> Result<Option<ExistingTarget>, SkillMaterializationError> {
    let components = relative.components().collect::<Vec<_>>();
    let Some(Component::Normal(name)) = components.last() else {
        return Err(SkillMaterializationError::new(format!(
            "mutation target must name a source file: {}",
            relative.display()
        )));
    };
    let mut directory = match open_root_nofollow(root) {
        Ok(directory) => directory,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => {
            return Err(SkillMaterializationError::new(format!(
                "cannot open mutation source root {}: {error}",
                root.display()
            )))
        }
    };
    for component in &components[..components.len() - 1] {
        let Component::Normal(component) = component else {
            return Err(SkillMaterializationError::new(format!(
                "unsafe mutation target: {}",
                relative.display()
            )));
        };
        directory = match directory.open_dir_nofollow(component) {
            Ok(directory) => directory,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => {
                return Err(SkillMaterializationError::new(format!(
                    "cannot open mutation parent for {}: {error}",
                    relative.display()
                )))
            }
        };
    }
    let metadata = match directory.symlink_metadata(name) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => {
            return Err(SkillMaterializationError::new(format!(
                "cannot inspect mutation target {}: {error}",
                relative.display()
            )))
        }
    };
    if metadata.file_type().is_symlink() {
        return Err(SkillMaterializationError::new(format!(
            "mutation target contains symlink component: {}",
            relative.display()
        )));
    }
    if !metadata.is_file() {
        return Err(SkillMaterializationError::new(format!(
            "mutation target is not a regular file: {}",
            relative.display()
        )));
    }
    let mut options = cap_std::fs::OpenOptions::new();
    options.read(true);
    options.follow(FollowSymlinks::No);
    let mut file = directory.open_with(name, &options).map_err(|error| {
        SkillMaterializationError::new(format!(
            "cannot read mutation target {}: {error}",
            relative.display()
        ))
    })?;
    let file_metadata = file.metadata().map_err(|error| {
        SkillMaterializationError::new(format!(
            "cannot inspect mutation target {}: {error}",
            relative.display()
        ))
    })?;
    if !file_metadata.is_file() {
        return Err(SkillMaterializationError::new(format!(
            "target is not a regular file: {}",
            path.display()
        )));
    }
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes).map_err(|error| {
        SkillMaterializationError::new(format!(
            "cannot read mutation target {}: {error}",
            relative.display()
        ))
    })?;
    #[cfg(unix)]
    let mode = {
        use cap_std::fs::PermissionsExt;
        Some(file_metadata.permissions().mode() & 0o777)
    };
    #[cfg(not(unix))]
    let mode = None;
    Ok(Some(ExistingTarget { bytes, mode }))
}

fn legacy_generated_schema_matches(candidate: &str, expected: &str) -> bool {
    let digest_pattern =
        regex::Regex::new(r"[0-9a-f]{64}").expect("static digest matcher compiles");
    let mut pattern = String::new();
    let mut cursor = 0;
    for digest in digest_pattern.find_iter(expected) {
        pattern.push_str(&regex::escape(&expected[cursor..digest.start()]));
        pattern.push_str(r"[0-9a-f]{64}");
        cursor = digest.end();
    }
    pattern.push_str(&regex::escape(&expected[cursor..]));
    if regex::Regex::new(&format!("\\A(?:{pattern})\\z"))
        .expect("generated legacy matcher compiles")
        .is_match(candidate)
    {
        return true;
    }
    let Some((candidate_metadata, candidate_body)) = frontmatter_and_body(candidate) else {
        return false;
    };
    let Some((expected_metadata, expected_body)) = frontmatter_and_body(expected) else {
        return false;
    };
    let Ok(candidate_yaml) = YamlLoader::load_from_str(candidate_metadata) else {
        return false;
    };
    let Ok(expected_yaml) = YamlLoader::load_from_str(expected_metadata) else {
        return false;
    };
    let same_name = candidate_yaml
        .first()
        .and_then(|value| get(value, "name"))
        .and_then(Yaml::as_str)
        == expected_yaml
            .first()
            .and_then(|value| get(value, "name"))
            .and_then(Yaml::as_str);
    if !same_name {
        return false;
    }
    let record_digest = regex::Regex::new(r#"("record_digest":")[0-9a-f]{64}"#)
        .expect("static record digest matcher compiles");
    let version = regex::Regex::new(r#"("version":)\d+"#).expect("static version matcher compiles");
    let stable_body = |body: &str| {
        let body = record_digest.replace_all(body, "$1<record-digest>");
        version.replace_all(&body, "$1<version>").into_owned()
    };
    stable_body(candidate_body) == stable_body(expected_body)
}

fn frontmatter_and_body(text: &str) -> Option<(&str, &str)> {
    let after_open = text.strip_prefix("---\n")?;
    let end = after_open.find("\n---\n")?;
    let body_start = end + "\n---\n".len();
    Some((&after_open[..end], &after_open[body_start..]))
}

fn markdown_sections(text: &str) -> Vec<(String, String)> {
    let normalized = text.replace("\r\n", "\n");
    let lines = normalized.split_inclusive('\n').collect::<Vec<_>>();
    let starts = lines
        .iter()
        .enumerate()
        .filter_map(|(index, line)| line.starts_with("## ").then_some(index))
        .collect::<Vec<_>>();
    let mut sections = Vec::new();
    for (offset, start) in starts.iter().copied().enumerate() {
        let end = starts.get(offset + 1).copied().unwrap_or(lines.len());
        sections.push((format!("L{}-L{end}", start + 1), lines[start..end].concat()));
    }
    let preamble_end = starts.first().copied().unwrap_or(lines.len());
    let preamble = lines[..preamble_end].concat();
    let preamble = preamble.trim();
    if !preamble.is_empty() {
        sections.push(("preamble".to_owned(), format!("{preamble}\n")));
    }
    sections
}

fn classify_legacy(
    plan: &MaterializationPlan,
    skill: &RenderedSkill,
) -> Result<serde_json::Value, SkillMaterializationError> {
    let path = plan.output_root.join(&skill.path);
    let relative = relative_path(&plan.output_root, &path);
    let current = read_target_nofollow(&plan.output_root, Path::new(&skill.path))?;
    let Some(current) = current else {
        return Ok(json!({
            "skill_id": skill.skill,
            "classification": "missing",
            "resolution": "migrated",
            "unmatched_blocks": [],
        }));
    };
    let body = match std::str::from_utf8(&current.bytes) {
        Ok(body) => body,
        Err(_) => {
            return Ok(json!({
                "skill_id": skill.skill,
                "classification": "invalid_utf8",
                "resolution": "blocked",
                "unmatched_blocks": [{
                    "locator": relative,
                    "digest": sha256_hex(&current.bytes),
                }],
            }))
        }
    };
    if body == skill.content {
        return Ok(json!({
            "skill_id": skill.skill,
            "classification": "generated",
            "resolution": "migrated",
            "unmatched_blocks": [],
        }));
    }
    if legacy_generated_schema_matches(body, &skill.content) {
        return Ok(json!({
            "skill_id": skill.skill,
            "classification": "generated_prior_schema",
            "resolution": "migrated",
            "unmatched_blocks": [],
        }));
    }
    let markdown_body = frontmatter_and_body(body)
        .map(|(_, body)| body)
        .unwrap_or(body);
    let mut unmatched_blocks = markdown_sections(markdown_body)
        .into_iter()
        .map(|(locator, section)| {
            json!({
                "locator": format!("{relative}#{locator}"),
                "digest": sha256_hex(section.as_bytes()),
            })
        })
        .collect::<Vec<_>>();
    if unmatched_blocks.is_empty() {
        unmatched_blocks.push(json!({
            "locator": relative,
            "digest": sha256_hex(body.as_bytes()),
        }));
    }
    Ok(json!({
        "skill_id": skill.skill,
        "classification": "legacy_schema_mismatch",
        "resolution": "blocked",
        "accepted_sections": [],
        "unmatched_blocks": unmatched_blocks,
        "reviewer_ref": "design:skill-runtime-shim-materialization.md#Adapter-Only--Canonical-Prose-Handling",
    }))
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
) -> Result<RenderedShim, SkillMaterializationError> {
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
            canonical_doc_digest: canonical_doc_digest.clone(),
            materializer_id: MATERIALIZER_ID.to_owned(),
        },
    };
    let record_digest = domain_digest("agent-canon.skill-runtime-shim.record.v3", &record)?;
    let record_comment = json_compact(&MaterializationRecordComment {
        schema: RECORD_SCHEMA_ID.to_owned(),
        version: 3,
        record_digest: record_digest.clone(),
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
    Ok(RenderedShim {
        content: rendered,
        record_digest,
        canonical_doc_digest,
    })
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

fn sha256_hex(bytes: &[u8]) -> String {
    hex_digest(&Sha256::digest(bytes))
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

fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
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
