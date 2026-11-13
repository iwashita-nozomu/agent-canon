// @dependency-start
// contract implementation
// responsibility Produces the retained route-golden, fresh-packet, and Skill shim measurement Eval artifacts.
// upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md owns producer schemas and metric semantics
// upstream implementation ./catalog/skill_materialization.rs owns rendered Skill projections and record identity
// upstream implementation ./workflow_selection_eval.rs owns the frozen 525-case manifest loader
// upstream implementation ./catalog/skill_routes.rs owns native public-skill routing decisions
// upstream implementation ./runtime_boundary.rs owns external report output
// downstream test ../../../../../tests/agent_tools/test_skill_shim_evaluation.py exercises the native producer CLI and frozen host fixtures
// @dependency-end

use crate::catalog::skill_materialization::{self, SkillShimProjection, MATERIALIZER_ID};
use crate::catalog::skill_routes::{decide_task_route_skills, load_skill_route_rules};
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::runtime_boundary::RuntimeArtifactBoundary;
use crate::workflow_selection_eval;
use icu_normalizer::ComposingNormalizer;
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use toml_edit::{DocumentMut, Item, TableLike};

pub const SELECTOR: &str = "skill-shim-evaluation";
const ROUTE_SCHEMA: &str = "agent_canon.route.skill_route.v1";
const ROUTE_GOLDEN_SCHEMA: &str = "agent_canon.route_golden";
const PACKET_SCHEMA: &str = "agent_canon.skill_runtime_shim.fresh_packets";
const MEASUREMENT_SCHEMA: &str = "agent_canon.skill_runtime_shim.measurement";
const HOST_OBSERVATION_SCHEMA: &str = "agent_canon.skill_runtime_shim.host_observation";
const MODEL_ID: &str = "gpt-5.4-mini";
const HOST_PROFILE: &str = "medium";
const NORMALIZATION: &str = "utf8-nfc-lf-final-newline";
const PACKET_CLASSES: [&str; 2] = ["full", "changed"];
const VARIANTS: [&str; 2] = ["current", "generated"];
const SCENARIO_CATEGORIES: [&str; 6] = [
    "discovery-selection",
    "boundary-and-negative",
    "toolcall-route",
    "dependent-skill-ordering",
    "parent-subagent-instruction",
    "failure-argparse-normalization",
];

#[derive(Clone, Debug)]
struct Packet {
    id: String,
    packet_class: String,
    prompt_path: String,
    scenario_id: String,
    category: String,
    target_skill_id: String,
    iteration_ids: BTreeMap<String, String>,
    prompt_digest: String,
    packet_digest: String,
}

#[derive(Clone, Debug)]
struct HostObservation {
    scenario_id: String,
    category: String,
    packet_id: String,
    iteration_id: String,
    packet_class: String,
    skill_id: String,
    variant: String,
    prompt: String,
    prompt_digest: String,
    input_tokens: u64,
    canonical_followup_input_tokens: u64,
    cache_fields_observed: Value,
}

struct HostEnvelope {
    bytes: Vec<u8>,
    utf8_bytes: usize,
    unicode_scalars: usize,
    normalized_bytes: Vec<u8>,
}

#[derive(Clone, Debug)]
struct Options {
    command: EvalCommand,
    root: PathBuf,
    manifest: Option<PathBuf>,
    host_evaluation_dir: Option<PathBuf>,
    output: Option<PathBuf>,
    output_dir: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
    model: String,
    profile: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum EvalCommand {
    RouteGolden,
    Packets,
    Tokens,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum EvalOption {
    Help,
    Root,
    Manifest,
    Output,
    OutputDir,
    RuntimeRoot,
    Model,
    Profile,
    HostEvaluationDir,
}

const EVAL_OPTIONS: &[(&str, EvalOption)] = &[
    ("--help", EvalOption::Help),
    ("--root", EvalOption::Root),
    ("--manifest", EvalOption::Manifest),
    ("--output", EvalOption::Output),
    ("--output-dir", EvalOption::OutputDir),
    ("--runtime-root", EvalOption::RuntimeRoot),
    ("--model", EvalOption::Model),
    ("--profile", EvalOption::Profile),
    ("--host-evaluation-dir", EvalOption::HostEvaluationDir),
];

const EVAL_USAGE: &str =
    "usage: agent-canon skill-shim-evaluation {route-golden,packets,tokens} [options]";

#[derive(Clone, Debug, Serialize)]
struct RouteFailure {
    code: String,
    class: String,
    exit_code: i32,
    stderr_sha256: String,
}

#[derive(Clone, Debug, Serialize)]
struct RouteInvocation {
    cli: String,
    mode: String,
    format: String,
}

#[derive(Clone, Debug, Serialize)]
struct RouteGoldenRow {
    schema: String,
    case_id: String,
    prompt_sha256: String,
    invocation: RouteInvocation,
    status: String,
    normalized_route_json_digest: String,
    route: Value,
    failure: RouteFailure,
}

fn sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn canonical_json(value: &Value) -> Result<Vec<u8>, String> {
    serde_json::to_vec(value).map_err(|error| format!("canonical_json_invalid:{error}"))
}

fn normalize_text(value: &str) -> String {
    let normalized =
        ComposingNormalizer::new_nfc().normalize(&value.replace("\r\n", "\n").replace('\r', "\n"));
    format!("{}\n", normalized.trim_end_matches('\n'))
}

fn deterministic_measure(value: &str) -> (usize, usize, Vec<u8>) {
    let normalized = normalize_text(value);
    let bytes = normalized.as_bytes().to_vec();
    (bytes.len(), normalized.chars().count(), bytes)
}

fn runtime_boundary(
    root: &Path,
    runtime_root: Option<&Path>,
) -> Result<RuntimeArtifactBoundary, String> {
    RuntimeArtifactBoundary::for_source(root, runtime_root, true)
        .map_err(|error| format!("runtime_artifact_boundary:{error}"))
}

fn write_runtime(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    bytes: &[u8],
    purpose: &str,
) -> Result<(), String> {
    boundary
        .atomic_write_bytes(path, bytes, 0o600)
        .map(|_| ())
        .map_err(|error| format!("{purpose}:{error}"))
}

fn required_string(table: &dyn TableLike, key: &str, field: &str) -> Result<String, String> {
    table
        .get(key)
        .and_then(Item::as_str)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| format!("{field}:must_be_text"))
}

fn string_array(table: &dyn TableLike, key: &str, field: &str) -> Result<Vec<String>, String> {
    let values = table
        .get(key)
        .and_then(Item::as_array)
        .ok_or_else(|| format!("{field}:must_be_list"))?;
    values
        .iter()
        .map(|value| {
            value
                .as_str()
                .map(str::to_owned)
                .ok_or_else(|| format!("{field}:must_be_string_list"))
        })
        .collect()
}

fn prompt_under_test(content: &str, packet_id: &str) -> Result<String, String> {
    let lines = content.lines().collect::<Vec<_>>();
    let Some(start) = lines
        .iter()
        .position(|line| line.trim() == "## Prompt Under Test")
        .map(|index| index + 1)
    else {
        return Err(format!("packet_prompt_section_missing:{packet_id}"));
    };
    let body = lines[start..]
        .iter()
        .take_while(|line| !line.starts_with("## "))
        .copied()
        .collect::<Vec<_>>()
        .join("\n");
    let body = body.trim();
    if body.is_empty() {
        return Err(format!("packet_prompt_empty:{packet_id}"));
    }
    Ok(normalize_text(body))
}

fn expected_skill_id_from_targets(targets: &[String], packet_id: &str) -> Result<String, String> {
    let values = targets
        .iter()
        .filter_map(|target| {
            if target.starts_with("agents/skills/") && target.ends_with(".md") {
                Path::new(target)
                    .file_stem()
                    .map(|value| value.to_string_lossy().into_owned())
            } else if target.starts_with(".codex/personal/skills/") && target.ends_with("/SKILL.md")
            {
                Path::new(target)
                    .parent()
                    .and_then(Path::file_name)
                    .map(|value| value.to_string_lossy().into_owned())
            } else {
                None
            }
        })
        .collect::<BTreeSet<_>>();
    match values.len() {
        0 => Err(format!("packet_target_skill_id:{packet_id}")),
        1 => Ok(values.into_iter().next().expect("one target skill exists")),
        _ => Err(format!("packet_target_skill_id_ambiguous:{packet_id}")),
    }
}

fn read_packet_manifest(path: &Path) -> Result<Vec<Packet>, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("packet_manifest_read:{error}"))?;
    let document = text
        .parse::<DocumentMut>()
        .map_err(|error| format!("packet_manifest_parse:{error}"))?;
    let root = document.as_table();
    let expected_fields = ["catalog_kind", "version", "packet_class_order", "packet"]
        .into_iter()
        .collect::<BTreeSet<_>>();
    if root.iter().map(|(key, _)| key).collect::<BTreeSet<_>>() != expected_fields {
        return Err("packet_manifest_unknown_field".to_owned());
    }
    if required_string(root, "catalog_kind", "catalog_kind")?
        != "agent_canon_skill_runtime_shim_eval"
        || root.get("version").and_then(Item::as_integer) != Some(1)
    {
        return Err("packet_manifest_identity".to_owned());
    }
    if string_array(root, "packet_class_order", "packet_class_order")?
        != PACKET_CLASSES.map(str::to_owned)
    {
        return Err("packet_class_order".to_owned());
    }
    let tables = root
        .get("packet")
        .and_then(Item::as_array_of_tables)
        .ok_or_else(|| "packet_count".to_owned())?;
    if tables.len() != SCENARIO_CATEGORIES.len() {
        return Err("packet_count".to_owned());
    }
    let required_fields = [
        "id",
        "packet_class",
        "prompt_path",
        "canonical_target_files",
        "prompt_dependency_files",
        "scenario_id",
        "category",
        "target_skill_id",
        "iteration_ids",
        "prompt_digest",
        "method",
        "requirements",
        "report_grammar",
        "packet_digest",
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    let mut packets = Vec::with_capacity(tables.len());
    for table in tables.iter() {
        if table.iter().map(|(key, _)| key).collect::<BTreeSet<_>>() != required_fields {
            return Err("packet_manifest_packet_fields".to_owned());
        }
        let id = required_string(table, "id", "packet_manifest_packet_fields")?;
        let packet_class = required_string(table, "packet_class", "packet_manifest_packet_fields")?;
        let prompt_path = required_string(table, "prompt_path", "packet_manifest_packet_fields")?;
        let canonical_target_files =
            string_array(table, "canonical_target_files", "packet_target_files")?;
        let _prompt_dependency_files = string_array(
            table,
            "prompt_dependency_files",
            "packet_prompt_dependency_files",
        )?;
        let scenario_id = required_string(table, "scenario_id", "packet_manifest_packet_fields")?;
        let category = required_string(table, "category", "packet_manifest_packet_fields")?;
        let target_skill_id =
            required_string(table, "target_skill_id", "packet_manifest_packet_fields")?;
        let prompt_digest =
            required_string(table, "prompt_digest", "packet_manifest_packet_fields")?;
        let _method = required_string(table, "method", "packet_manifest_packet_fields")?;
        let _requirements = string_array(table, "requirements", "packet_requirements")?;
        let _report_grammar =
            required_string(table, "report_grammar", "packet_manifest_packet_fields")?;
        let packet_digest =
            required_string(table, "packet_digest", "packet_manifest_packet_fields")?;
        let iteration_table = table
            .get("iteration_ids")
            .and_then(Item::as_table_like)
            .ok_or_else(|| format!("packet_iteration_ids:{id}"))?;
        let iteration_ids = iteration_table
            .iter()
            .map(|(key, value)| {
                let value = value
                    .as_str()
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| format!("packet_iteration_ids:{id}"))?;
                Ok((key.to_owned(), value.to_owned()))
            })
            .collect::<Result<BTreeMap<_, _>, String>>()?;
        if iteration_ids.len() != VARIANTS.len()
            || VARIANTS
                .iter()
                .any(|variant| !iteration_ids.contains_key(*variant))
            || iteration_ids.values().collect::<BTreeSet<_>>().len() != VARIANTS.len()
        {
            return Err(format!("packet_iteration_ids:{id}"));
        }
        if !PACKET_CLASSES.contains(&packet_class.as_str())
            || scenario_id != category
            || !SCENARIO_CATEGORIES.contains(&category.as_str())
        {
            return Err(format!("packet_category:{id}"));
        }
        if expected_skill_id_from_targets(&canonical_target_files, &id)? != target_skill_id {
            return Err(format!("packet_target_skill_id_mismatch:{id}"));
        }
        let manifest_root = path
            .parent()
            .and_then(Path::parent)
            .and_then(Path::parent)
            .ok_or_else(|| "packet_manifest_path_invalid".to_owned())?;
        let packet_file = manifest_root.join(&prompt_path);
        let packet_content =
            fs::read_to_string(&packet_file).map_err(|_| format!("missing_packet:{id}"))?;
        let lowered = packet_content.to_lowercase();
        if [
            "expected_answer",
            "expected command",
            "oracle_",
            "prior reasoning",
        ]
        .iter()
        .any(|token| lowered.contains(token))
        {
            return Err(format!("answer_in_packet:{id}"));
        }
        if sha256(packet_content.as_bytes()) != packet_digest {
            return Err(format!("packet_digest_mismatch:{id}"));
        }
        let packet_prompt = prompt_under_test(&packet_content, &id)?;
        let packet_prompt_sha256 = sha256(packet_prompt.as_bytes());
        if packet_prompt_sha256 != prompt_digest {
            return Err(format!("packet_prompt_digest_mismatch:{id}"));
        }
        packets.push(Packet {
            id,
            packet_class,
            prompt_path,
            scenario_id,
            category,
            target_skill_id,
            iteration_ids,
            prompt_digest,
            packet_digest,
        });
    }
    if packets
        .iter()
        .map(|packet| packet.packet_class.as_str())
        .collect::<BTreeSet<_>>()
        != PACKET_CLASSES.into_iter().collect::<BTreeSet<_>>()
    {
        return Err("packet_class_coverage".to_owned());
    }
    if packets
        .iter()
        .map(|packet| packet.scenario_id.as_str())
        .collect::<BTreeSet<_>>()
        != SCENARIO_CATEGORIES.into_iter().collect::<BTreeSet<_>>()
    {
        return Err("packet_scenario_coverage".to_owned());
    }
    if packets
        .iter()
        .map(|packet| packet.id.as_str())
        .collect::<BTreeSet<_>>()
        .len()
        != packets.len()
    {
        return Err("packet_id_duplicate".to_owned());
    }
    if packets
        .iter()
        .map(|packet| packet.scenario_id.as_str())
        .collect::<BTreeSet<_>>()
        .len()
        != packets.len()
    {
        return Err("packet_scenario_duplicate".to_owned());
    }
    Ok(packets)
}

fn empty_route(mode: &str) -> Value {
    json!({
        "schema": ROUTE_SCHEMA,
        "route": "",
        "mode": mode,
        "skills": [],
        "active_skills": [],
        "deferred_skills": [],
        "matched_skills": [],
        "related_skill_candidates": [],
        "related_skills": {},
        "reasons": [],
        "evidence": "",
    })
}

fn normalize_route_result(
    return_code: i32,
    stdout: &[u8],
    stderr: &[u8],
    mode: &str,
) -> Result<(String, Value, RouteFailure), String> {
    let stderr_text = String::from_utf8_lossy(stderr);
    if return_code == 0 {
        let route: Value = serde_json::from_slice(stdout)
            .map_err(|_| "UNMAPPED_ROUTE_FAILURE:invalid_success_json".to_owned())?;
        if !route.is_object() || route.get("schema").and_then(Value::as_str) != Some(ROUTE_SCHEMA) {
            return Err("UNMAPPED_ROUTE_FAILURE:invalid_success_schema".to_owned());
        }
        if !stderr.is_empty() {
            return Err("UNMAPPED_ROUTE_FAILURE:success_stderr".to_owned());
        }
        return Ok((
            "pass".to_owned(),
            route,
            RouteFailure {
                code: "none".to_owned(),
                class: "none".to_owned(),
                exit_code: 0,
                stderr_sha256: sha256(&[]),
            },
        ));
    }
    let non_empty = stderr_text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>();
    let (code, failure_class) = if return_code == 2
        && non_empty
            .first()
            .is_some_and(|line| line.starts_with("usage:"))
        && non_empty
            .iter()
            .any(|line| line.starts_with("error:") || line.contains(" error:"))
    {
        ("ARGUMENT_ERROR".to_owned(), "argument".to_owned())
    } else if return_code == 2 {
        if non_empty
            .iter()
            .any(|line| line.starts_with("ROUTE_SOURCE_ROOT_FAILURE="))
        {
            (
                "ROUTE_SOURCE_ROOT_FAILURE".to_owned(),
                "source_root".to_owned(),
            )
        } else if non_empty
            .iter()
            .any(|line| line.starts_with("SKILL_ROUTER_ERROR="))
        {
            ("SKILL_ROUTER_ERROR".to_owned(), "runtime".to_owned())
        } else {
            return Err("UNMAPPED_ROUTE_FAILURE:unknown_exit_2".to_owned());
        }
    } else {
        return Err(format!("UNMAPPED_ROUTE_FAILURE:exit_{return_code}"));
    };
    Ok((
        "fail".to_owned(),
        empty_route(mode),
        RouteFailure {
            code,
            class: failure_class,
            exit_code: return_code,
            stderr_sha256: sha256(stderr),
        },
    ))
}

fn failure_stderr(prefix: &str, detail: &str) -> Vec<u8> {
    format!("{prefix}={detail}\n").into_bytes()
}

fn route_golden(
    root: &Path,
    manifest: &Path,
    output: &Path,
    runtime_root: Option<&Path>,
) -> Result<Value, String> {
    let manifest_data =
        workflow_selection_eval::manifest_json(manifest).map_err(|error| error.to_string())?;
    if manifest_data
        .get("expected_case_count")
        .and_then(Value::as_u64)
        != Some(525)
        || manifest_data
            .get("expected_generated_case_count")
            .and_then(Value::as_u64)
            != Some(525)
    {
        return Err("route_manifest_count_mismatch".to_owned());
    }
    let cases = manifest_data
        .get("cases")
        .and_then(Value::as_array)
        .ok_or_else(|| "route_case_count_mismatch".to_owned())?;
    if cases.len() != 525 {
        return Err("route_case_count_mismatch".to_owned());
    }
    let boundary = runtime_boundary(root, runtime_root)?;
    let environment = std::env::vars_os()
        .filter_map(|(key, value)| Some((key.into_string().ok()?, value.into_string().ok()?)))
        .collect::<BTreeMap<_, _>>();
    let source_roots = crate::agent_canon_source_root::resolve_source_roots(root, &environment);
    let route_rules = source_roots
        .as_ref()
        .map_err(|error| format!("ROUTE_SOURCE_ROOT_FAILURE={}:{}", error.code, error.detail))
        .and_then(|roots| {
            load_skill_route_rules(&roots.source_root)
                .map_err(|error| format!("SKILL_ROUTER_ERROR={error}"))
        });
    let mut rows = Vec::with_capacity(cases.len());
    for case in cases {
        let case_id = case
            .get("case_id")
            .and_then(Value::as_str)
            .ok_or_else(|| "route_case_id_invalid".to_owned())?;
        let prompt = case
            .get("prompt")
            .and_then(Value::as_str)
            .ok_or_else(|| "route_prompt_invalid".to_owned())?;
        let prompt_sha256 = sha256(prompt.as_bytes());
        let route_result = match &route_rules {
            Ok(rules) => match decide_task_route_skills(prompt, "repo-changing", rules) {
                Ok(route) => normalize_route_result(
                    0,
                    &serde_json::to_vec(&route).map_err(|error| error.to_string())?,
                    &[],
                    "repo-changing",
                ),
                Err(error) => normalize_route_result(
                    2,
                    &[],
                    &failure_stderr("SKILL_ROUTER_ERROR", &error),
                    "repo-changing",
                ),
            },
            Err(error) if error.starts_with("ROUTE_SOURCE_ROOT_FAILURE=") => {
                normalize_route_result(2, &[], format!("{error}\n").as_bytes(), "repo-changing")
            }
            Err(error) => normalize_route_result(
                2,
                &[],
                &failure_stderr("SKILL_ROUTER_ERROR", error),
                "repo-changing",
            ),
        }?;
        let (status, route, failure) = route_result;
        let normalized_route_json_digest = sha256(&canonical_json(&route)?);
        rows.push(RouteGoldenRow {
            schema: ROUTE_SCHEMA.to_owned(),
            case_id: case_id.to_owned(),
            prompt_sha256,
            invocation: RouteInvocation {
                cli: "tools/bin/agent-canon route".to_owned(),
                mode: "repo-changing".to_owned(),
                format: "json".to_owned(),
            },
            status,
            normalized_route_json_digest,
            route,
            failure,
        });
    }
    let payload = json!({
        "schema": ROUTE_GOLDEN_SCHEMA,
        "version": 1,
        "case_count": rows.len(),
        "cases": rows,
    });
    let mut encoded = serde_json::to_vec_pretty(&payload).map_err(|error| error.to_string())?;
    encoded.push(b'\n');
    write_runtime(&boundary, output, &encoded, "skill-shim-route-golden")?;
    Ok(payload)
}

fn packet_receipt(
    root: &Path,
    manifest: &Path,
    model: &str,
    profile: &str,
    output_dir: &Path,
    runtime_root: Option<&Path>,
) -> Result<Value, String> {
    if model != MODEL_ID || profile != HOST_PROFILE {
        return Err("fresh_model_profile_mismatch".to_owned());
    }
    let packets = read_packet_manifest(manifest)?;
    let receipt_rows = packets
        .iter()
        .map(|packet| {
            json!({
                "id": packet.id,
                "packet_class": packet.packet_class,
                "prompt_path": packet.prompt_path,
                "packet_digest": packet.packet_digest,
            })
        })
        .collect::<Vec<_>>();
    let payload = json!({
        "schema": PACKET_SCHEMA,
        "version": 1,
        "model_id": model,
        "host_profile": profile,
        "packet_count": receipt_rows.len(),
        "packets": receipt_rows,
    });
    let boundary = runtime_boundary(root, runtime_root)?;
    let output = output_dir.join("packet-receipt.json");
    let mut encoded = serde_json::to_vec_pretty(&payload).map_err(|error| error.to_string())?;
    encoded.push(b'\n');
    write_runtime(&boundary, &output, &encoded, "skill-shim-packet-receipt")?;
    Ok(payload)
}

fn read_host_observation(path: &Path) -> Result<HostObservation, String> {
    let bytes = fs::read(path).map_err(|error| format!("host_evaluation_read:{error}"))?;
    let raw: Value = serde_json::from_slice(&bytes)
        .map_err(|_| format!("host_evaluation_not_object:{}", path.display()))?;
    let object = raw
        .as_object()
        .ok_or_else(|| format!("host_evaluation_not_object:{}", path.display()))?;
    let required = [
        "schema",
        "version",
        "scenario_id",
        "category",
        "packet_id",
        "iteration_id",
        "packet_class",
        "skill_id",
        "variant",
        "prompt",
        "prompt_digest",
        "input_tokens",
        "model_id",
        "host_profile",
        "method",
        "observation_status",
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    let allowed = required
        .iter()
        .copied()
        .chain(["canonical_followup_input_tokens", "cache_fields_observed"])
        .collect::<BTreeSet<_>>();
    let keys = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let file_name = path.file_name().unwrap_or_default().to_string_lossy();
    if !required.is_subset(&keys) || !keys.is_subset(&allowed) {
        return Err(format!("host_observation_incomplete:{file_name}"));
    }
    let get_string = |key: &str, error: &str| -> Result<String, String> {
        object
            .get(key)
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or_else(|| format!("{error}:{file_name}"))
    };
    if object.get("schema").and_then(Value::as_str) != Some(HOST_OBSERVATION_SCHEMA)
        || object.get("version").and_then(Value::as_u64) != Some(1)
    {
        return Err(format!("host_schema:{file_name}"));
    }
    let scenario_id = get_string("scenario_id", "host_category")?;
    let category = get_string("category", "host_category")?;
    let prompt = get_string("prompt", "host_prompt")?;
    if prompt.is_empty() {
        return Err(format!("host_prompt:{file_name}"));
    }
    let prompt_digest = get_string("prompt_digest", "host_prompt_digest")?;
    if sha256(normalize_text(&prompt).as_bytes()) != prompt_digest {
        return Err(format!("host_prompt_digest:{file_name}"));
    }
    if object.get("model_id").and_then(Value::as_str) != Some(MODEL_ID)
        || object.get("host_profile").and_then(Value::as_str) != Some(HOST_PROFILE)
        || object.get("method").and_then(Value::as_str) != Some("fresh_read_only")
        || object.get("observation_status").and_then(Value::as_str) != Some("pass")
    {
        return Err(format!("host_metadata:{file_name}"));
    }
    let variant = get_string("variant", "host_variant")?;
    if !VARIANTS.contains(&variant.as_str()) {
        return Err(format!("host_variant:{file_name}"));
    }
    let skill_id = get_string("skill_id", "host_skill_id")?;
    let packet_id = get_string("packet_id", "host_observation_incomplete")?;
    let iteration_id = get_string("iteration_id", "host_observation_incomplete")?;
    let packet_class = get_string("packet_class", "host_observation_incomplete")?;
    let input_tokens = object
        .get("input_tokens")
        .and_then(Value::as_u64)
        .ok_or_else(|| format!("host_input_tokens_invalid:{file_name}"))?;
    let canonical_followup_input_tokens = object
        .get("canonical_followup_input_tokens")
        .map(|value| {
            value
                .as_u64()
                .ok_or_else(|| format!("canonical_followup_input_tokens_invalid:{file_name}"))
        })
        .transpose()?
        .unwrap_or(0);
    let cache_fields_observed = object
        .get("cache_fields_observed")
        .cloned()
        .unwrap_or_else(|| json!({}));
    if !cache_fields_observed.is_object() {
        return Err(format!("cache_fields_observed_invalid:{file_name}"));
    }
    Ok(HostObservation {
        scenario_id,
        category,
        packet_id,
        iteration_id,
        packet_class,
        skill_id,
        variant,
        prompt,
        prompt_digest,
        input_tokens,
        canonical_followup_input_tokens,
        cache_fields_observed,
    })
}

fn validate_host_observations(
    observations: &[HostObservation],
    packets: &[Packet],
) -> Result<(), String> {
    let expected = packets
        .iter()
        .map(|packet| (packet.scenario_id.as_str(), packet))
        .collect::<BTreeMap<_, _>>();
    let mut seen = BTreeSet::new();
    for observation in observations {
        let Some(packet) = expected.get(observation.scenario_id.as_str()) else {
            return Err(format!(
                "host_observation_mismatch:unknown_scenario:{}",
                observation.scenario_id
            ));
        };
        let pair = (
            observation.scenario_id.as_str(),
            observation.variant.as_str(),
        );
        if !seen.insert(pair) {
            return Err(format!(
                "host_observation_duplicate:{}:{}",
                observation.scenario_id, observation.variant
            ));
        }
        if observation.packet_id != packet.id
            || observation.category != packet.category
            || observation.packet_class != packet.packet_class
        {
            return Err(format!(
                "host_observation_mismatch:{}:{}",
                observation.scenario_id, observation.variant
            ));
        }
        if observation.skill_id != packet.target_skill_id {
            return Err(format!(
                "host_observation_wrong_skill_id:{}:{}",
                observation.scenario_id, observation.variant
            ));
        }
        if observation.prompt_digest != packet.prompt_digest
            || sha256(normalize_text(&observation.prompt).as_bytes()) != packet.prompt_digest
        {
            return Err(format!(
                "host_observation_unrelated_prompt:{}:{}",
                observation.scenario_id, observation.variant
            ));
        }
        if packet.iteration_ids.get(&observation.variant) != Some(&observation.iteration_id) {
            return Err(format!(
                "host_iteration_mismatch:{}:{}",
                observation.scenario_id, observation.variant
            ));
        }
    }
    let required = packets
        .iter()
        .flat_map(|packet| VARIANTS.map(|variant| (packet.scenario_id.as_str(), variant)))
        .collect::<BTreeSet<_>>();
    if let Some((scenario, variant)) = required.difference(&seen).next() {
        return Err(format!("host_observation_missing:{scenario}:{variant}"));
    }
    if observations.len() != required.len() {
        return Err("host_observation_incomplete".to_owned());
    }
    Ok(())
}

fn host_envelope(
    skill: &SkillShimProjection,
    model: &str,
    profile: &str,
    prompt_sha256: &str,
) -> Result<HostEnvelope, String> {
    let value = json!({
        "model_id": model,
        "host_profile": profile,
        "skill_id": skill.skill_id,
        "skill_projection_digest": skill.record_digest,
        "materializer_id": MATERIALIZER_ID,
        "prompt_sha256": prompt_sha256,
    });
    let bytes = canonical_json(&value)?;
    let text = std::str::from_utf8(&bytes).map_err(|_| "host_envelope_invalid_utf8".to_owned())?;
    let (byte_count, scalar_count, normalized) = deterministic_measure(text);
    Ok(HostEnvelope {
        bytes,
        utf8_bytes: byte_count,
        unicode_scalars: scalar_count,
        normalized_bytes: normalized,
    })
}

fn paired_reduction_summary(
    candidate_rows: &[Value],
    scenario_rows: &[Value],
) -> Result<(&'static str, usize, usize), String> {
    let mut candidates = BTreeMap::new();
    for row in candidate_rows {
        if row.get("row_type").and_then(Value::as_str) != Some("candidate") {
            return Err("candidate_row_type".to_owned());
        }
        let candidate_id = row
            .get("candidate_row_id")
            .and_then(Value::as_str)
            .ok_or_else(|| "candidate_row_id".to_owned())?;
        if candidates.insert(candidate_id, row).is_some() {
            return Err(format!("candidate_row_duplicate:{candidate_id}"));
        }
    }
    let mut pairs: BTreeMap<String, BTreeMap<String, &Value>> = BTreeMap::new();
    let mut paired_candidate_ids = BTreeSet::new();
    for scenario in scenario_rows {
        let scenario_id = scenario
            .get("scenario_id")
            .and_then(Value::as_str)
            .ok_or_else(|| "scenario_candidate_identity".to_owned())?;
        let candidate_id = scenario
            .get("candidate_row_id")
            .and_then(Value::as_str)
            .ok_or_else(|| "scenario_candidate_identity".to_owned())?;
        let variant = scenario
            .get("variant")
            .and_then(Value::as_str)
            .filter(|variant| VARIANTS.contains(variant))
            .ok_or_else(|| "scenario_candidate_identity".to_owned())?;
        let candidate = candidates
            .get(candidate_id)
            .copied()
            .ok_or_else(|| format!("scenario_candidate_mismatch:{scenario_id}:{variant}"))?;
        if candidate.get("variant").and_then(Value::as_str) != Some(variant) {
            return Err(format!(
                "scenario_candidate_mismatch:{scenario_id}:{variant}"
            ));
        }
        let pair_id = format!("scenario:{scenario_id}");
        let pair_values = pairs.entry(pair_id.clone()).or_default();
        if pair_values.insert(variant.to_owned(), candidate).is_some() {
            return Err(format!("candidate_pair_duplicate:{pair_id}:{variant}"));
        }
        paired_candidate_ids.insert(candidate_id.to_owned());
    }
    for (candidate_id, row) in &candidates {
        if paired_candidate_ids.contains(*candidate_id) {
            continue;
        }
        let host_envelope_id = row
            .get("host_envelope_id")
            .and_then(Value::as_str)
            .filter(|value| value.starts_with("deterministic-"))
            .ok_or_else(|| format!("candidate_pair_unmapped:{candidate_id}"))?;
        let skill_id = row
            .get("skill_id")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("deterministic_candidate_identity:{candidate_id}"))?;
        let variant = row
            .get("variant")
            .and_then(Value::as_str)
            .filter(|variant| VARIANTS.contains(variant))
            .ok_or_else(|| format!("deterministic_candidate_identity:{candidate_id}"))?;
        if host_envelope_id != format!("deterministic-{skill_id}-{variant}") {
            return Err(format!("deterministic_candidate_envelope:{candidate_id}"));
        }
        let pair_id = format!("deterministic:{skill_id}");
        let pair_values = pairs.entry(pair_id.clone()).or_default();
        if pair_values.insert(variant.to_owned(), row).is_some() {
            return Err(format!("candidate_pair_duplicate:{pair_id}:{variant}"));
        }
        paired_candidate_ids.insert((*candidate_id).to_owned());
    }
    let mut positive_count = 0;
    let mut non_positive_count = 0;
    for (pair_id, pair_values) in &pairs {
        let missing = VARIANTS
            .iter()
            .filter(|variant| !pair_values.contains_key(**variant))
            .copied()
            .collect::<Vec<_>>();
        if !missing.is_empty() {
            return Err(format!(
                "candidate_pair_missing:{pair_id}:{}",
                missing.join(",")
            ));
        }
        let current = pair_values["current"];
        let generated = pair_values["generated"];
        if current.get("skill_id") != generated.get("skill_id") {
            return Err(format!("candidate_pair_skill_mismatch:{pair_id}"));
        }
        let current_bytes = current.get("utf8_bytes").and_then(Value::as_u64);
        let generated_bytes = generated.get("utf8_bytes").and_then(Value::as_u64);
        let current_scalars = current.get("unicode_scalars").and_then(Value::as_u64);
        let generated_scalars = generated.get("unicode_scalars").and_then(Value::as_u64);
        let (
            Some(current_bytes),
            Some(generated_bytes),
            Some(current_scalars),
            Some(generated_scalars),
        ) = (
            current_bytes,
            generated_bytes,
            current_scalars,
            generated_scalars,
        )
        else {
            return Err(format!("candidate_pair_measure_invalid:{pair_id}"));
        };
        if current.get("denominator_status").and_then(Value::as_str) == Some("valid")
            && generated.get("denominator_status").and_then(Value::as_str) == Some("valid")
            && current_bytes > generated_bytes
            && current_scalars > generated_scalars
        {
            positive_count += 1;
        } else {
            non_positive_count += 1;
        }
    }
    if paired_candidate_ids.len() != candidates.len() || pairs.is_empty() {
        return Err("candidate_pair_incomplete".to_owned());
    }
    Ok((
        if non_positive_count == 0 {
            "pass"
        } else {
            "fail"
        },
        positive_count,
        non_positive_count,
    ))
}

/// Run the native Skill shim Eval producer family.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_args(args) {
        Ok(None) => {
            println!("{EVAL_USAGE}");
            return 0;
        }
        Ok(Some(options)) => options,
        Err(error) => {
            eprintln!("{EVAL_USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let result = match options.command {
        EvalCommand::RouteGolden => route_golden(
            &options.root,
            options
                .manifest
                .as_deref()
                .expect("route-golden requires a manifest"),
            options
                .output
                .as_deref()
                .expect("route-golden requires an output path"),
            options.runtime_root.as_deref(),
        ),
        EvalCommand::Packets => packet_receipt(
            &options.root,
            options
                .manifest
                .as_deref()
                .expect("packets requires a manifest"),
            &options.model,
            &options.profile,
            options
                .output_dir
                .as_deref()
                .expect("packets requires an output directory"),
            options.runtime_root.as_deref(),
        ),
        EvalCommand::Tokens => measurement(
            &options.root,
            &options.model,
            &options.profile,
            options
                .manifest
                .as_deref()
                .expect("tokens requires a manifest"),
            options
                .host_evaluation_dir
                .as_deref()
                .expect("tokens requires host observations"),
            options
                .output
                .as_deref()
                .expect("tokens requires an output path"),
            options.runtime_root.as_deref(),
        ),
    };
    match result {
        Ok(payload) => {
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "status": "pass",
                    "schema": payload.get("schema").cloned().unwrap_or(Value::Null),
                }))
                .unwrap_or_else(|_| "{}".to_owned())
            );
            0
        }
        Err(error) => {
            println!("SKILL_SHIM_EVALUATION_FAILURE={error}");
            2
        }
    }
}

fn parse_args(args: &[String]) -> Result<Option<Options>, String> {
    let Some(command) = args.first() else {
        return Err("the following arguments are required: command".to_owned());
    };
    let command = match command.as_str() {
        "route-golden" => EvalCommand::RouteGolden,
        "packets" => EvalCommand::Packets,
        "tokens" => EvalCommand::Tokens,
        "-h" | "--help" => return Ok(None),
        value => {
            return Err(format!(
                "invalid choice: '{value}' (choose from 'route-golden', 'packets', 'tokens')"
            ))
        }
    };
    let mut root = None;
    let mut manifest = None;
    let mut output = None;
    let mut output_dir = None;
    let mut runtime_root = None;
    let mut model = MODEL_ID.to_owned();
    let mut profile = HOST_PROFILE.to_owned();
    let mut host_evaluation_dir = None;
    let mut index = 1;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "-h" {
            return Ok(None);
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument, None), |(option, value)| (option, Some(value)));
        let selected = if let Some((_, selected)) = EVAL_OPTIONS
            .iter()
            .find(|(candidate, _)| *candidate == option)
        {
            *selected
        } else {
            resolve_long_option_prefix(option, EVAL_OPTIONS).map_err(|error| match error {
                LongOptionError::Unrecognized => format!("unrecognized arguments: {argument}"),
                LongOptionError::Ambiguous(matches) => format!(
                    "ambiguous option: {option} could match {}",
                    matches.join(", ")
                ),
            })?
        };
        if selected == EvalOption::Help {
            return Ok(None);
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
            EvalOption::Help => return Ok(None),
            EvalOption::Root => root = Some(PathBuf::from(value)),
            EvalOption::Manifest => manifest = Some(PathBuf::from(value)),
            EvalOption::Output => output = Some(PathBuf::from(value)),
            EvalOption::OutputDir => output_dir = Some(PathBuf::from(value)),
            EvalOption::RuntimeRoot => runtime_root = Some(PathBuf::from(value)),
            EvalOption::Model => model = value.to_owned(),
            EvalOption::Profile => profile = value.to_owned(),
            EvalOption::HostEvaluationDir => host_evaluation_dir = Some(PathBuf::from(value)),
        }
        index += 1;
    }
    let root = match root {
        Some(root) => root,
        None => std::env::current_dir()
            .map_err(|error| format!("resolve current directory: {error}"))?,
    };
    let root = crate::path_resolution::resolve_non_strict(&root)?;
    let resolve_arg = |path: Option<PathBuf>| {
        path.map(|path| crate::path_resolution::resolve_non_strict(&path))
            .transpose()
    };
    let manifest = resolve_arg(manifest)?;
    let output = resolve_arg(output)?;
    let output_dir = resolve_arg(output_dir)?;
    let host_evaluation_dir = resolve_arg(host_evaluation_dir)?;
    match command {
        EvalCommand::RouteGolden if manifest.is_none() || output.is_none() => {
            return Err("the following arguments are required: --manifest, --output".to_owned())
        }
        EvalCommand::Packets if manifest.is_none() || output_dir.is_none() => {
            return Err("the following arguments are required: --manifest, --output-dir".to_owned())
        }
        EvalCommand::Tokens
            if manifest.is_none() || host_evaluation_dir.is_none() || output.is_none() =>
        {
            return Err(
                "the following arguments are required: --manifest, --host-evaluation-dir, --output"
                    .to_owned(),
            )
        }
        _ => {}
    }
    Ok(Some(Options {
        command,
        root,
        manifest,
        host_evaluation_dir,
        output,
        output_dir,
        runtime_root,
        model,
        profile,
    }))
}

fn measurement(
    root: &Path,
    model: &str,
    profile: &str,
    manifest: &Path,
    host_dir: &Path,
    output: &Path,
    runtime_root: Option<&Path>,
) -> Result<Value, String> {
    if model != MODEL_ID || profile != HOST_PROFILE {
        return Err("measurement_model_profile_mismatch".to_owned());
    }
    let packets = read_packet_manifest(manifest)?;
    let catalog = skill_materialization::render_catalog(root)
        .map_err(|error| format!("skill_shim_materializer:{error}"))?;
    let mut skill_by_id = BTreeMap::new();
    for skill in &catalog.skills {
        skill_by_id.insert(skill.skill_id.as_str(), skill);
    }
    let mut host_paths = fs::read_dir(host_dir)
        .map_err(|_| "host_evaluations_empty".to_owned())?
        .filter_map(|entry| entry.ok().map(|entry| entry.path()))
        .filter(|path| path.extension().and_then(|extension| extension.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    host_paths.sort();
    let observations = host_paths
        .iter()
        .map(|path| read_host_observation(path))
        .collect::<Result<Vec<_>, _>>()?;
    if observations.is_empty() {
        return Err("host_evaluations_empty".to_owned());
    }
    validate_host_observations(&observations, &packets)?;
    let mut host_envelopes = Vec::new();
    let mut candidate_rows = Vec::new();
    let mut scenario_rows = Vec::new();
    for (index, observation) in observations.iter().enumerate() {
        let skill = skill_by_id
            .get(observation.skill_id.as_str())
            .copied()
            .ok_or_else(|| format!("unknown_skill:{}", observation.skill_id))?;
        let prompt_sha256 = sha256(observation.prompt.as_bytes());
        let envelope = host_envelope(skill, model, profile, &prompt_sha256)?;
        let host_envelope_id = format!(
            "host-{index:04}-{}-{}",
            observation.scenario_id, observation.variant
        );
        host_envelopes.push(json!({
            "row_type": "host_envelope",
            "host_envelope_id": host_envelope_id,
            "model_id": model,
            "host_profile": profile,
            "skill_id": skill.skill_id,
            "skill_projection_digest": skill.record_digest,
            "materializer_id": MATERIALIZER_ID,
            "prompt_sha256": prompt_sha256,
            "host_envelope_sha256": sha256(&envelope.normalized_bytes),
            "host_utf8_bytes": envelope.utf8_bytes,
            "host_unicode_scalars": envelope.unicode_scalars,
        }));
        let candidate_text = if observation.variant == "generated" {
            skill.content.clone()
        } else {
            fs::read_to_string(root.join(&skill.canonical_doc))
                .map_err(|_| format!("canonical_doc_unreadable:{}", skill.skill_id))?
        };
        let (_, _, normalized_candidate) = deterministic_measure(&candidate_text);
        let envelope_text = std::str::from_utf8(&envelope.bytes)
            .map_err(|_| "host_envelope_invalid_utf8".to_owned())?;
        let combined = normalize_text(&format!("{envelope_text}\n{candidate_text}"));
        let candidate_row_id = format!("candidate-{index:04}");
        candidate_rows.push(json!({
            "row_type": "candidate",
            "candidate_row_id": candidate_row_id,
            "host_envelope_id": host_envelope_id,
            "skill_id": skill.skill_id,
            "variant": observation.variant,
            "content_sha256": sha256(&normalized_candidate),
            "measured_input": "host_envelope_plus_candidate",
            "utf8_bytes": combined.len(),
            "unicode_scalars": combined.chars().count(),
            "denominator_status": "valid",
        }));
        scenario_rows.push(json!({
            "row_type": "scenario",
            "scenario_row_id": format!("scenario-{index:04}"),
            "scenario_id": observation.scenario_id,
            "packet_id": observation.packet_id,
            "iteration_id": observation.iteration_id,
            "provenance": "fresh",
            "candidate_row_id": candidate_row_id,
            "host_envelope_id": host_envelope_id,
            "variant": observation.variant,
            "host_input_tokens": observation.input_tokens,
            "host_usage_source": "fresh_host_evaluation",
            "canonical_followup_input_tokens": observation.canonical_followup_input_tokens,
            "cache_fields_observed": observation.cache_fields_observed,
            "observation_status": "pass",
        }));
    }
    let baseline_prompt_sha = sha256(b"agent-canon.skill-runtime-shim.deterministic-measurement");
    for skill in &catalog.skills {
        let envelope = host_envelope(skill, model, profile, &baseline_prompt_sha)?;
        let envelope_text = std::str::from_utf8(&envelope.bytes)
            .map_err(|_| "host_envelope_invalid_utf8".to_owned())?;
        for variant in VARIANTS {
            let host_envelope_id = format!("deterministic-{}-{variant}", skill.skill_id);
            host_envelopes.push(json!({
                "row_type": "host_envelope",
                "host_envelope_id": host_envelope_id,
                "model_id": model,
                "host_profile": profile,
                "skill_id": skill.skill_id,
                "skill_projection_digest": skill.record_digest,
                "materializer_id": MATERIALIZER_ID,
                "prompt_sha256": baseline_prompt_sha,
                "host_envelope_sha256": sha256(&envelope.normalized_bytes),
                "host_utf8_bytes": envelope.utf8_bytes,
                "host_unicode_scalars": envelope.unicode_scalars,
            }));
            let candidate_text = if variant == "generated" {
                skill.content.clone()
            } else {
                fs::read_to_string(root.join(&skill.canonical_doc))
                    .map_err(|_| format!("canonical_doc_unreadable:{}", skill.skill_id))?
            };
            let (_, _, normalized_candidate) = deterministic_measure(&candidate_text);
            let combined = normalize_text(&format!("{envelope_text}\n{candidate_text}"));
            candidate_rows.push(json!({
                "row_type": "candidate",
                "candidate_row_id": format!("candidate-deterministic-{}-{variant}", skill.skill_id),
                "host_envelope_id": host_envelope_id,
                "skill_id": skill.skill_id,
                "variant": variant,
                "content_sha256": sha256(&normalized_candidate),
                "measured_input": "host_envelope_plus_candidate",
                "utf8_bytes": combined.len(),
                "unicode_scalars": combined.chars().count(),
                "denominator_status": "valid",
            }));
        }
    }
    let (pair_status, positive_pair_count, non_positive_pair_count) =
        paired_reduction_summary(&candidate_rows, &scenario_rows)?;
    let sum_variant = |variant: &str, field: &str| -> u64 {
        candidate_rows
            .iter()
            .filter(|row| row.get("variant").and_then(Value::as_str) == Some(variant))
            .filter_map(|row| row.get(field).and_then(Value::as_u64))
            .sum()
    };
    let current_bytes = sum_variant("current", "utf8_bytes");
    let generated_bytes = sum_variant("generated", "utf8_bytes");
    let current_scalars = sum_variant("current", "unicode_scalars");
    let generated_scalars = sum_variant("generated", "unicode_scalars");
    let valid_rows = candidate_rows
        .iter()
        .filter(|row| row.get("denominator_status").and_then(Value::as_str) == Some("valid"))
        .count();
    let observed_tokens = scenario_rows
        .iter()
        .filter_map(|row| row.get("host_input_tokens").and_then(Value::as_u64))
        .sum::<u64>();
    let reduction = current_bytes > 0
        && generated_bytes < current_bytes
        && u128::from(current_bytes - generated_bytes) * 100 >= u128::from(current_bytes) * 70
        && pair_status == "pass";
    let run_id = output
        .file_stem()
        .and_then(|stem| stem.to_str())
        .filter(|stem| !stem.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| format!("skill-shim-{}", &catalog.source_snapshot_digest[..10]));
    let host_envelope_count = host_envelopes.len();
    let candidate_row_count = candidate_rows.len();
    let scenario_row_count = scenario_rows.len();
    let payload = json!({
        "schema": MEASUREMENT_SCHEMA,
        "version": 1,
        "run_id": run_id,
        "source_snapshot_digest": catalog.source_snapshot_digest,
        "model_id": model,
        "host_profile": profile,
        "normalization": NORMALIZATION,
        "host_envelopes": host_envelopes,
        "candidate_rows": candidate_rows,
        "scenario_rows": scenario_rows,
        "summary": {
            "host_envelope_count": host_envelope_count,
            "candidate_row_count": candidate_row_count,
            "scenario_row_count": scenario_row_count,
            "valid_denominator_row_count": valid_rows,
            "not_applicable_row_count": candidate_row_count - valid_rows,
            "current_utf8_bytes_total": current_bytes,
            "generated_utf8_bytes_total": generated_bytes,
            "current_unicode_scalars_total": current_scalars,
            "generated_unicode_scalars_total": generated_scalars,
            "observed_host_input_tokens_total": observed_tokens,
            "paired_reduction_row_count": positive_pair_count + non_positive_pair_count,
            "non_positive_reduction_row_count": non_positive_pair_count,
            "deterministic_reduction_status": if reduction { "pass" } else { "fail" },
        },
    });
    let boundary = runtime_boundary(root, runtime_root)?;
    let mut encoded = serde_json::to_vec_pretty(&payload).map_err(|error| error.to_string())?;
    encoded.push(b'\n');
    write_runtime(&boundary, output, &encoded, "skill-shim-measurement")?;
    Ok(payload)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candidate(
        id: &str,
        envelope: &str,
        skill: &str,
        variant: &str,
        bytes: u64,
        scalars: u64,
    ) -> Value {
        json!({
            "row_type": "candidate",
            "candidate_row_id": id,
            "host_envelope_id": envelope,
            "skill_id": skill,
            "variant": variant,
            "utf8_bytes": bytes,
            "unicode_scalars": scalars,
            "denominator_status": "valid",
        })
    }

    #[test]
    fn route_error_normalization_preserves_argparse_failure_class_and_digest() {
        let stderr = b"usage: route.py [-h]\nroute.py: error: argument --mode: invalid choice\n";
        let (status, route, failure) =
            normalize_route_result(2, b"", stderr, "repo-changing").expect("error maps");
        assert_eq!(status, "fail");
        assert_eq!(route["schema"], ROUTE_SCHEMA);
        assert_eq!(failure.code, "ARGUMENT_ERROR");
        assert_eq!(failure.class, "argument");
        assert_eq!(failure.exit_code, 2);
        assert_eq!(
            failure.stderr_sha256,
            "8b45c9c12c52a327356b3fe26ee46f954b791b14bfd2fc3ba1883bba1a39a80f"
        );
    }

    #[test]
    fn paired_reduction_requires_positive_byte_and_scalar_reduction_per_pair() {
        let rows = vec![
            candidate(
                "scenario-current",
                "host-current",
                "skill-a",
                "current",
                500,
                500,
            ),
            candidate(
                "scenario-generated",
                "host-generated",
                "skill-a",
                "generated",
                500,
                500,
            ),
            candidate(
                "det-current",
                "deterministic-skill-b-current",
                "skill-b",
                "current",
                300,
                300,
            ),
            candidate(
                "det-generated",
                "deterministic-skill-b-generated",
                "skill-b",
                "generated",
                250,
                250,
            ),
        ];
        let scenarios = vec![
            json!({"scenario_id":"scenario-a","candidate_row_id":"scenario-current","variant":"current"}),
            json!({"scenario_id":"scenario-a","candidate_row_id":"scenario-generated","variant":"generated"}),
        ];
        assert_eq!(
            paired_reduction_summary(&rows, &scenarios).unwrap(),
            ("fail", 1, 1)
        );
    }

    #[test]
    fn paired_reduction_rejects_duplicate_and_missing_pairs() {
        let current = candidate(
            "current",
            "deterministic-skill-a-current",
            "skill-a",
            "current",
            10,
            10,
        );
        let duplicate = candidate(
            "duplicate",
            "deterministic-skill-a-current",
            "skill-a",
            "current",
            10,
            10,
        );
        assert!(paired_reduction_summary(&[current.clone(), duplicate], &[])
            .unwrap_err()
            .contains("candidate_pair_duplicate"));
        assert!(paired_reduction_summary(&[current], &[])
            .unwrap_err()
            .contains("candidate_pair_missing"));
    }

    #[test]
    fn host_observations_require_each_fresh_packet_variant() {
        let prompt = normalize_text("fresh prompt");
        let prompt_digest = sha256(prompt.as_bytes());
        let packet = Packet {
            id: "packet-a".to_owned(),
            packet_class: "full".to_owned(),
            prompt_path: "eval/fixtures/packet.md".to_owned(),
            scenario_id: "scenario-a".to_owned(),
            category: "discovery-selection".to_owned(),
            target_skill_id: "task-routing".to_owned(),
            iteration_ids: BTreeMap::from([
                ("current".to_owned(), "iteration-current".to_owned()),
                ("generated".to_owned(), "iteration-generated".to_owned()),
            ]),
            prompt_digest: prompt_digest.clone(),
            packet_digest: "0".repeat(64),
        };
        let observation = HostObservation {
            scenario_id: "scenario-a".to_owned(),
            category: "discovery-selection".to_owned(),
            packet_id: "packet-a".to_owned(),
            iteration_id: "iteration-current".to_owned(),
            packet_class: "full".to_owned(),
            skill_id: "task-routing".to_owned(),
            variant: "current".to_owned(),
            prompt: prompt.clone(),
            prompt_digest,
            input_tokens: 10,
            canonical_followup_input_tokens: 0,
            cache_fields_observed: json!({}),
        };
        assert_eq!(
            validate_host_observations(&[observation], &[packet]).unwrap_err(),
            "host_observation_missing:scenario-a:generated"
        );
    }
}
