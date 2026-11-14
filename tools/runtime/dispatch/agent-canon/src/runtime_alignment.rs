// @dependency-start
// contract implementation
// responsibility Composes the native model/role, skill-catalog, and documentation runtime-alignment owners.
// upstream implementation codex_agent_role_eval/mod.rs validates model/profile, generated role, and task-routing contracts
// upstream implementation catalog/skill_routes.rs owns the skill catalog and dependency route loader
// downstream implementation main.rs registers the native runtime-alignment command
// downstream test ../../../../../tests/agent_tools/test_check_agent_runtime_alignment.py exercises native source and documentation closure
// @dependency-end

use crate::codex_agent_role_eval;
use crate::hook_dispatcher::HOOK_EVENT_CONTRACTS;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::{catalog::skill_routes, catalog::tool_catalog};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use toml_edit::{DocumentMut, Item};
use yaml_rust2::Yaml;

const OFFICIAL_SYSTEM_SKILLS: &[&str] = &[
    "imagegen",
    "openai-docs",
    "plugin-creator",
    "skill-creator",
    "skill-installer",
];
const TOOL_RESULT_ROUTE_MARKERS: &[&str] = &[
    "raw checker/stat artifacts -> artifact_reviewer",
    "reader-facing narrative interpretation -> report_reviewer",
    "OOP mechanical reports -> oop_readability_reviewer",
    "repo-wide drift and integration risk -> project_reviewer",
];

#[derive(Clone, Debug, Serialize)]
struct AlignmentFinding {
    check: String,
    target: String,
    detail: String,
}

impl AlignmentFinding {
    fn new(check: &str, target: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            check: check.to_owned(),
            target: target.into(),
            detail: detail.into(),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Format {
    Text,
    Json,
}

const OPTIONS: &[(&str, usize)] = &[("--help", 0), ("--root", 1), ("--format", 2)];

fn read_json(root: &Path, relative: &str) -> Result<Value, String> {
    let path = root.join(relative);
    let bytes = fs::read(&path).map_err(|error| format!("{}:{error}", path.display()))?;
    serde_json::from_slice(&bytes).map_err(|error| format!("{}:{error}", path.display()))
}

fn read_text(root: &Path, relative: &str) -> Result<String, String> {
    let path = root.join(relative);
    fs::read_to_string(&path).map_err(|error| format!("{}:{error}", path.display()))
}

fn parse_toml(root: &Path, relative: &str) -> Result<DocumentMut, String> {
    let path = root.join(relative);
    fs::read_to_string(&path)
        .map_err(|error| format!("{}:{error}", path.display()))?
        .parse::<DocumentMut>()
        .map_err(|error| format!("{}:{error}", path.display()))
}

fn yaml_get<'a>(value: &'a Yaml, key: &str) -> Option<&'a Yaml> {
    value
        .as_hash()?
        .iter()
        .find_map(|(candidate, value)| (candidate.as_str() == Some(key)).then_some(value))
}

fn yaml_string(value: Option<&Yaml>) -> Option<&str> {
    value.and_then(Yaml::as_str)
}

fn yaml_strings(value: Option<&Yaml>) -> Vec<String> {
    value
        .and_then(Yaml::as_vec)
        .into_iter()
        .flatten()
        .filter_map(Yaml::as_str)
        .map(str::to_owned)
        .collect()
}

fn yaml_values(value: Option<&Yaml>) -> &[Yaml] {
    value
        .and_then(Yaml::as_vec)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

fn valid_prompt_entries(value: Option<&Yaml>) -> bool {
    value.and_then(Yaml::as_vec).is_some_and(|values| {
        !values.is_empty()
            && values.iter().all(|item| {
                item.as_str().is_some_and(|text| !text.trim().is_empty())
                    || item.as_hash().is_some_and(|mapping| {
                        !mapping.is_empty()
                            && mapping.iter().all(|(key, value)| {
                                key.as_str().is_some() && value.as_str().is_some()
                            })
                    })
            })
    })
}

fn check_profile_policy(root: &Path, findings: &mut Vec<AlignmentFinding>) {
    let document = match parse_toml(root, "agents/model_profiles.toml") {
        Ok(document) => document,
        Err(error) => {
            findings.push(AlignmentFinding::new(
                "model-profile",
                "agents/model_profiles.toml",
                error,
            ));
            return;
        }
    };
    let profiles = document
        .get("model_profiles")
        .and_then(Item::as_array_of_tables)
        .map(|profiles| profiles.iter().collect::<Vec<_>>())
        .unwrap_or_default();
    let return_schemas = profiles
        .iter()
        .filter_map(|profile| profile.get("return_schema_id").and_then(Item::as_str))
        .collect::<BTreeSet<_>>();
    if return_schemas != ["claim_evidence_v1"].into_iter().collect() {
        findings.push(AlignmentFinding::new(
            "model-profile",
            "agents/model_profiles.toml",
            "common-return-schema-divergence",
        ));
    }
    let writer = document
        .get("writer_isolation_policy")
        .and_then(Item::as_table_like);
    let expected_requirements = [
        "disjoint_paths",
        "no_shared_git_index_or_head",
        "no_generated_or_formatter_effects",
    ];
    let valid_writer = writer.is_some_and(|writer| {
        writer.get("current_checkout_mode").and_then(Item::as_str)
            == Some("parallel_only_for_disjoint_paths_without_shared_state")
            && writer
                .get("parallel_requirements")
                .and_then(Item::as_array)
                .is_some_and(|values| {
                    values
                        .iter()
                        .filter_map(|value| value.as_str())
                        .collect::<Vec<_>>()
                        == expected_requirements
                })
            && writer.get("collision_action").and_then(Item::as_str)
                == Some("reject_same_checkout_root_before_spawn")
            && writer.get("isolated_worktree_mode").and_then(Item::as_str)
                == Some("explicit_alternative_implementation_experiment_only")
    });
    if !valid_writer {
        findings.push(AlignmentFinding::new(
            "model-profile",
            "agents/model_profiles.toml",
            "writer-isolation-policy-divergence",
        ));
    }
    let expected_write = [
        "worker",
        "spark_worker",
        "integration_executor",
        "publisher",
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    if let Some(bindings) = document
        .get("role_sandbox_bindings")
        .and_then(Item::as_table_like)
    {
        for (role, sandbox) in bindings.iter() {
            let expected = if expected_write.contains(role) {
                "workspace-write"
            } else {
                "read-only"
            };
            if sandbox.as_str() != Some(expected) {
                findings.push(AlignmentFinding::new(
                    "model-profile",
                    role,
                    format!("sandbox-policy-expected-{expected}"),
                ));
            }
        }
    } else {
        findings.push(AlignmentFinding::new(
            "model-profile",
            "agents/model_profiles.toml",
            "role-sandbox-bindings-unreadable",
        ));
    }
    let project = match parse_toml(root, ".codex/config.toml") {
        Ok(project) => project,
        Err(error) => {
            findings.push(AlignmentFinding::new(
                "project-config",
                ".codex/config.toml",
                error,
            ));
            return;
        }
    };
    let profile_map = profiles
        .iter()
        .filter_map(|profile| Some((profile.get("id")?.as_str()?, *profile)))
        .collect::<BTreeMap<_, _>>();
    for (key, profile_id) in [
        ("model", "sol_parent_high"),
        ("model_reasoning_effort", "sol_parent_high"),
        ("review_model", "luna_reasoning_high"),
    ] {
        let Some(profile) = profile_map.get(profile_id) else {
            findings.push(AlignmentFinding::new(
                "model-profile",
                profile_id,
                "required-profile-missing",
            ));
            continue;
        };
        let expected = if key == "model" || key == "review_model" {
            profile.get("model").and_then(Item::as_str)
        } else {
            profile.get("reasoning_effort").and_then(Item::as_str)
        };
        if project.get(key).and_then(Item::as_str) != expected {
            findings.push(AlignmentFinding::new(
                "project-config",
                ".codex/config.toml",
                format!("expected-{key}-{profile_id}"),
            ));
        }
    }
    for key in [
        "service_tier",
        "flex",
        "tier",
        "features",
        "skills",
        "profiles",
    ] {
        if project.get(key).is_some() {
            findings.push(AlignmentFinding::new(
                "project-config",
                ".codex/config.toml",
                format!("unsupported-key-{key}"),
            ));
        }
    }
    if project
        .get("tool_output_token_limit")
        .and_then(Item::as_integer)
        != Some(4096)
        || project.get("approval_policy").and_then(Item::as_str) != Some("on-request")
        || project.get("sandbox_mode").and_then(Item::as_str) != Some("workspace-write")
        || project
            .get("agents")
            .and_then(Item::as_table_like)
            .and_then(|agents| agents.get("max_threads"))
            .and_then(Item::as_integer)
            != Some(27)
        || project
            .get("agents")
            .and_then(Item::as_table_like)
            .and_then(|agents| agents.get("max_depth"))
            .and_then(Item::as_integer)
            != Some(2)
        || project
            .get("agents")
            .and_then(Item::as_table_like)
            .and_then(|agents| agents.get("job_max_runtime_seconds"))
            .and_then(Item::as_integer)
            != Some(3600)
    {
        findings.push(AlignmentFinding::new(
            "project-config",
            ".codex/config.toml",
            "project-default-policy-divergence",
        ));
    }
}

fn check_team_task_catalog(root: &Path, findings: &mut Vec<AlignmentFinding>) {
    let team = match read_json(root, "agents/agents_config.json") {
        Ok(team) => team,
        Err(error) => {
            findings.push(AlignmentFinding::new(
                "team-config",
                "agents/agents_config.json",
                error,
            ));
            return;
        }
    };
    let task_yaml = match tool_catalog::load_yaml_document(&root.join("agents/task_catalog.yaml")) {
        Ok(task_yaml) => task_yaml,
        Err(error) => {
            findings.push(AlignmentFinding::new(
                "task-catalog",
                "agents/task_catalog.yaml",
                error,
            ));
            return;
        }
    };
    let role_ids = ["always_on_roles", "specialist_roles"]
        .into_iter()
        .flat_map(|section| {
            team.get(section)
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
        })
        .filter_map(|role| role.get("id").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    for key in [
        "model",
        "model_reasoning_effort",
        "review_model",
        "service_tier",
        "flex",
        "tier",
    ] {
        if team.get(key).is_some() {
            findings.push(AlignmentFinding::new(
                "team-config",
                "agents/agents_config.json",
                format!("forbidden-model-policy:{key}"),
            ));
        }
    }
    let codex_config = parse_toml(root, ".codex/config.toml").ok();
    let codex_role_ids = codex_config
        .as_ref()
        .and_then(|config| config.get("agents"))
        .and_then(Item::as_table_like)
        .into_iter()
        .flat_map(|agents| agents.iter())
        .filter_map(|(id, value)| value.as_table_like().map(|_| id.to_owned()))
        .collect::<BTreeSet<_>>();
    for section in ["always_on_roles", "specialist_roles"] {
        for (index, role) in team
            .get(section)
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .enumerate()
        {
            let Some(id) = role.get("id").and_then(Value::as_str) else {
                findings.push(AlignmentFinding::new(
                    "team-config",
                    format!("{section}[{index}]"),
                    "role-id-must-be-text",
                ));
                continue;
            };
            for agent in role
                .get("codex_agents")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
            {
                let Some(agent) = agent.as_str() else {
                    findings.push(AlignmentFinding::new(
                        "team-config",
                        id,
                        "codex-agent-id-must-be-text",
                    ));
                    continue;
                };
                let config = root.join(".codex/agents").join(format!("{agent}.toml"));
                if !config.is_file() {
                    findings.push(AlignmentFinding::new(
                        "team-config",
                        id,
                        format!("missing-codex-agent:{agent}"),
                    ));
                }
                if !codex_role_ids.contains(agent) {
                    findings.push(AlignmentFinding::new(
                        "team-config",
                        id,
                        format!("missing-project-registration:{agent}"),
                    ));
                }
            }
        }
    }
    let family_ids = yaml_values(yaml_get(&task_yaml, "workflow_families"))
        .iter()
        .filter_map(|family| yaml_string(yaml_get(family, "id")))
        .collect::<BTreeSet<_>>();
    let task_ids = yaml_values(yaml_get(&task_yaml, "tasks"))
        .iter()
        .filter_map(|task| yaml_string(yaml_get(task, "id")))
        .collect::<BTreeSet<_>>();
    check_math_intent_route(&task_yaml, findings);
    for field in [
        "model",
        "model_reasoning_effort",
        "review_model",
        "service_tier",
        "flex",
        "tier",
    ] {
        if yaml_get(&task_yaml, field).is_some() {
            findings.push(AlignmentFinding::new(
                "task-catalog",
                "agents/task_catalog.yaml",
                format!("forbidden-model-policy:{field}"),
            ));
        }
    }
    let review_policy = yaml_get(&task_yaml, "review_activation_policy");
    for (key, expected) in [
        ("mode", "candidate_only"),
        (
            "owner_gate_cardinality",
            "one_gate_per_replaceable_responsibility",
        ),
        (
            "specialist_activation",
            "distinct_unresolved_claim_or_risk_only",
        ),
    ] {
        if yaml_string(review_policy.and_then(|policy| yaml_get(policy, key))) != Some(expected) {
            findings.push(AlignmentFinding::new(
                "task-catalog",
                "review_activation_policy",
                format!("{key}-divergence"),
            ));
        }
    }
    if let Some(topology) = yaml_get(&task_yaml, "role_topology_defaults") {
        let families = yaml_get(topology, "role_families");
        if yaml_strings(families.and_then(|families| yaml_get(families, "implementation")))
            != ["worker", "spark_worker"]
        {
            findings.push(AlignmentFinding::new(
                "task-catalog",
                "role_topology_defaults.role_families.implementation",
                "implementation-role-family-order",
            ));
        }
        if yaml_strings(families.and_then(|families| yaml_get(families, "test_design")))
            != ["test_designer"]
        {
            findings.push(AlignmentFinding::new(
                "task-catalog",
                "role_topology_defaults.role_families.test_design",
                "test-design-role-family",
            ));
        }
        if yaml_strings(families.and_then(|families| yaml_get(families, "design")))
            .contains(&"test_designer".to_owned())
        {
            findings.push(AlignmentFinding::new(
                "task-catalog",
                "role_topology_defaults.role_families.design",
                "test-designer-must-be-post-implementation",
            ));
        }
        if yaml_string(
            yaml_get(topology, "same_role_parallel_instances")
                .and_then(|instance| yaml_get(instance, "identity_key")),
        ) != Some("role_id+instance_id+agent_type")
        {
            findings.push(AlignmentFinding::new(
                "task-catalog",
                "role_topology_defaults.same_role_parallel_instances.identity_key",
                "same-role-identity-key-divergence",
            ));
        }
    }
    for task in yaml_values(yaml_get(&task_yaml, "tasks")) {
        let task_id = yaml_string(yaml_get(task, "id")).unwrap_or("unknown");
        let family = yaml_string(yaml_get(task, "family")).unwrap_or("");
        if !family_ids.contains(family) {
            findings.push(AlignmentFinding::new(
                "task-catalog",
                task_id,
                "unknown-workflow-family",
            ));
        }
        let specialists = yaml_strings(yaml_get(task, "specialists"));
        for role in &specialists {
            if !role_ids.contains(role.as_str()) {
                findings.push(AlignmentFinding::new(
                    "task-catalog",
                    task_id,
                    format!("unknown-role:{role}"),
                ));
            }
            if role == "test_designer" {
                findings.push(AlignmentFinding::new(
                    "task-catalog",
                    task_id,
                    "test-designer-must-not-be-default-specialist",
                ));
            }
        }
    }
    for family in yaml_values(yaml_get(&task_yaml, "workflow_families")) {
        let family_id = yaml_string(yaml_get(family, "id")).unwrap_or("unknown");
        for group in ["always_on", "specialists"] {
            let values = yaml_get(family, "roles").and_then(|roles| yaml_get(roles, group));
            for role in yaml_strings(values) {
                if !role_ids.contains(role.as_str()) {
                    findings.push(AlignmentFinding::new(
                        "task-catalog",
                        family_id,
                        format!("unknown-role:{role}"),
                    ));
                }
            }
        }
        let prompt = yaml_get(family, "subagent_prompt");
        for field in [
            "purpose",
            "prompt_preamble",
            "workflow_focus",
            "reviewer_prompt",
        ] {
            let value = prompt.and_then(|prompt| yaml_get(prompt, field));
            let valid = if field == "purpose" {
                yaml_string(value).is_some_and(|value| !value.trim().is_empty())
            } else {
                valid_prompt_entries(value)
            };
            if !valid {
                findings.push(AlignmentFinding::new(
                    "task-catalog",
                    family_id,
                    format!("subagent-prompt-{field}-invalid"),
                ));
            }
        }
    }
    for pack in yaml_values(yaml_get(&task_yaml, "review_packs")) {
        let pack_id = yaml_string(yaml_get(pack, "id")).unwrap_or("unknown");
        for role in yaml_strings(yaml_get(pack, "specialists")) {
            if !role_ids.contains(role.as_str()) {
                findings.push(AlignmentFinding::new(
                    "task-catalog",
                    pack_id,
                    format!("unknown-role:{role}"),
                ));
            }
        }
        for task in yaml_strings(yaml_get(pack, "default_for_tasks"))
            .into_iter()
            .chain(yaml_strings(yaml_get(pack, "optional_for_tasks")))
        {
            if !task_ids.contains(task.as_str()) {
                findings.push(AlignmentFinding::new(
                    "task-catalog",
                    pack_id,
                    format!("unknown-task:{task}"),
                ));
            }
        }
    }
    for handoff in team
        .get("handoffs")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        for field in ["from", "to"] {
            let role = handoff.get(field).and_then(Value::as_str).unwrap_or("");
            if !role_ids.contains(role) {
                findings.push(AlignmentFinding::new(
                    "team-config",
                    "agents/agents_config.json#handoffs",
                    format!("unknown-{field}-role:{role}"),
                ));
            }
        }
    }
    let test_design_handoffs = team
        .get("handoffs")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|handoff| {
            handoff.get("to").and_then(Value::as_str) == Some("test_designer")
                || handoff.get("from").and_then(Value::as_str) == Some("test_designer")
        })
        .collect::<Vec<_>>();
    if test_design_handoffs.len() != 1
        || test_design_handoffs[0].get("from").and_then(Value::as_str) != Some("implementer")
        || test_design_handoffs[0].get("to").and_then(Value::as_str) != Some("test_designer")
        || !test_design_handoffs[0]
            .get("gate")
            .and_then(Value::as_str)
            .is_some_and(|gate| {
                gate.contains("implementation mechanism") && gate.contains("unresolved")
            })
    {
        findings.push(AlignmentFinding::new(
            "team-config",
            "agents/agents_config.json#handoffs",
            "test-designer-must-have-only-conditional-post-implementation-risk-handoff",
        ));
    }
    for policy in team
        .get("context_policies")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        for role in policy
            .get("roles")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
        {
            if !role_ids.contains(role) {
                findings.push(AlignmentFinding::new(
                    "team-config",
                    "agents/agents_config.json#context_policies",
                    format!("unknown-role:{role}"),
                ));
            }
        }
    }
    for rule in team
        .get("activation_rules")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let role = rule.get("role").and_then(Value::as_str).unwrap_or("");
        if !role_ids.contains(role) {
            findings.push(AlignmentFinding::new(
                "team-config",
                "agents/agents_config.json#activation_rules",
                format!("unknown-role:{role}"),
            ));
        }
    }
}

fn check_math_intent_route(task_catalog: &Yaml, findings: &mut Vec<AlignmentFinding>) {
    let route_id = "mathematical_correction";
    let route =
        yaml_get(task_catalog, "math_intent_routes").and_then(|routes| yaml_get(routes, route_id));
    let expected = [
        ("id", "mathematical_correction"),
        (
            "activation",
            "mathematical_or_numerical_correction_evidence",
        ),
        ("owner_skill", "computational-optimization"),
        ("reviewer", "mathematical_correctness_reviewer"),
        ("required_packet", "mathematical_intent_packet"),
    ];
    if route.is_none()
        || expected.iter().any(|(field, value)| {
            yaml_string(route.and_then(|route| yaml_get(route, field))) != Some(*value)
        })
        || route
            .and_then(|route| yaml_get(route, "requires_math_intent"))
            .and_then(Yaml::as_bool)
            != Some(true)
    {
        findings.push(AlignmentFinding::new(
            "math-intent-route",
            "agents/task_catalog.yaml#math_intent_routes.mathematical_correction",
            "canonical-route-record-divergence",
        ));
    }
    let family = yaml_values(yaml_get(task_catalog, "workflow_families"))
        .iter()
        .find(|family| yaml_string(yaml_get(family, "id")) == Some("research_driven_change"));
    let family_specialists = family
        .and_then(|family| yaml_get(family, "roles"))
        .and_then(|roles| yaml_get(roles, "specialists"));
    if !yaml_strings(family_specialists)
        .iter()
        .any(|role| role == "mathematical_correctness_reviewer")
    {
        findings.push(AlignmentFinding::new(
            "math-intent-route",
            "research_driven_change",
            "math-reviewer-must-remain-a-route-candidate",
        ));
    }
    for task_id in ["T4", "T5"] {
        let task = yaml_values(yaml_get(task_catalog, "tasks"))
            .iter()
            .find(|task| yaml_string(yaml_get(task, "id")) == Some(task_id));
        if yaml_string(task.and_then(|task| yaml_get(task, "math_intent_route"))) != Some(route_id)
        {
            findings.push(AlignmentFinding::new(
                "math-intent-route",
                task_id,
                "canonical-route-not-selected",
            ));
            continue;
        }
        let task_specialists = yaml_strings(task.and_then(|task| yaml_get(task, "specialists")));
        let default_pack_specialists = yaml_values(yaml_get(task_catalog, "review_packs"))
            .iter()
            .filter(|pack| {
                yaml_strings(yaml_get(pack, "default_for_tasks"))
                    .iter()
                    .any(|id| id == task_id)
            })
            .flat_map(|pack| yaml_strings(yaml_get(pack, "specialists")))
            .collect::<Vec<_>>();
        if task_specialists
            .iter()
            .any(|role| role == "mathematical_correctness_reviewer")
            || default_pack_specialists
                .iter()
                .any(|role| role == "mathematical_correctness_reviewer")
        {
            findings.push(AlignmentFinding::new(
                "math-intent-route",
                task_id,
                "math-reviewer-must-remain-conditional",
            ));
        }
    }
}

fn check_hooks(root: &Path, findings: &mut Vec<AlignmentFinding>) {
    let value = match read_json(root, ".codex/hooks.json") {
        Ok(value) => value,
        Err(error) => {
            findings.push(AlignmentFinding::new("hook", ".codex/hooks.json", error));
            return;
        }
    };
    let Some(object) = value.as_object() else {
        findings.push(AlignmentFinding::new(
            "hook",
            ".codex/hooks.json",
            "top-level-must-be-mapping",
        ));
        return;
    };
    if object.keys().map(String::as_str).collect::<BTreeSet<_>>() != ["hooks"].into_iter().collect()
    {
        findings.push(AlignmentFinding::new(
            "hook",
            ".codex/hooks.json",
            "top-level-keys-must-match-hook-schema",
        ));
    }
    let Some(hooks) = object.get("hooks").and_then(Value::as_object) else {
        findings.push(AlignmentFinding::new(
            "hook",
            ".codex/hooks.json",
            "hooks-must-be-mapping",
        ));
        return;
    };
    for event in ["UserPromptSubmit", "PreToolUse", "PostToolUse"] {
        if hooks
            .get(event)
            .and_then(Value::as_array)
            .is_none_or(Vec::is_empty)
        {
            findings.push(AlignmentFinding::new(
                "hook",
                event,
                "hook-must-be-configured",
            ));
        }
    }
    if hooks.contains_key("Stop") {
        findings.push(AlignmentFinding::new(
            "hook",
            "Stop",
            "inactive-event-must-not-be-registered",
        ));
    }
    if read_text(root, ".codex/hooks.json")
        .is_ok_and(|text| text.contains("mcp_session_context.sh"))
    {
        findings.push(AlignmentFinding::new(
            "hook",
            ".codex/hooks.json",
            "retired-startup-hook-present",
        ));
    }
    for (event, contract) in HOOK_EVENT_CONTRACTS {
        if hooks.contains_key(event) != contract.active {
            findings.push(AlignmentFinding::new(
                "hook",
                event,
                "hook-registration-contract-divergence",
            ));
        }
    }
    for (event, groups) in hooks {
        let Some(groups) = groups.as_array() else {
            findings.push(AlignmentFinding::new(
                "hook",
                event,
                "hook-groups-must-be-list",
            ));
            continue;
        };
        for group in groups {
            let Some(hooks) = group.get("hooks").and_then(Value::as_array) else {
                findings.push(AlignmentFinding::new(
                    "hook",
                    event,
                    "hook-list-must-be-list",
                ));
                continue;
            };
            for hook in hooks {
                if hook.get("command").and_then(Value::as_str).is_none() {
                    findings.push(AlignmentFinding::new(
                        "hook",
                        event,
                        "hook-command-must-be-text",
                    ));
                }
            }
        }
    }
}

fn walk_markdown(root: &Path, current: &Path, results: &mut Vec<PathBuf>) -> Result<(), String> {
    for entry in fs::read_dir(current).map_err(|error| format!("{}:{error}", current.display()))? {
        let path = entry.map_err(|error| error.to_string())?.path();
        let metadata = fs::symlink_metadata(&path).map_err(|error| error.to_string())?;
        if metadata.file_type().is_symlink() {
            continue;
        }
        if metadata.is_dir() {
            walk_markdown(root, &path, results)?;
        } else if metadata.is_file() && path.extension().is_some_and(|extension| extension == "md")
        {
            results.push(
                path.strip_prefix(root)
                    .map_err(|error| error.to_string())?
                    .to_path_buf(),
            );
        }
    }
    Ok(())
}

fn check_skill_surface(root: &Path, findings: &mut Vec<AlignmentFinding>) {
    let catalog = match skill_routes::load_skill_catalog(root) {
        Ok(catalog) => catalog,
        Err(error) => {
            findings.push(AlignmentFinding::new(
                "skill-catalog",
                "agents/skills/catalog.yaml",
                error,
            ));
            return;
        }
    };
    let rules = match skill_routes::load_skill_route_rules(root) {
        Ok(rules) => rules,
        Err(error) => {
            findings.push(AlignmentFinding::new(
                "skill-catalog",
                "agents/skills/catalog.yaml",
                format!("blocked-by=catalog-gate:{error}"),
            ));
            return;
        }
    };
    let families = yaml_get(&catalog, "skill_families")
        .and_then(Yaml::as_vec)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if families.len() != rules.len() {
        findings.push(AlignmentFinding::new(
            "skill-catalog",
            "agents/skills/catalog.yaml",
            "catalog-rule-source-order-mismatch",
        ));
        return;
    }
    let mut skill_ids = BTreeSet::new();
    let mut canonical_docs = BTreeSet::new();
    let shim_root = root.join(".codex/personal/skills");
    for (index, (entry, rule)) in families.iter().zip(&rules).enumerate() {
        let Some(id) = yaml_string(yaml_get(entry, "id")) else {
            findings.push(AlignmentFinding::new(
                "skill-catalog",
                format!("skill_families[{index}]"),
                "id-must-be-text",
            ));
            continue;
        };
        if id.starts_with('_') {
            findings.push(AlignmentFinding::new(
                "skill-catalog",
                id,
                "public-skill-id-must-not-be-private",
            ));
        }
        skill_ids.insert(id.to_owned());
        if id != rule.skill {
            findings.push(AlignmentFinding::new(
                "skill-catalog",
                id,
                "catalog-rule-source-order-mismatch",
            ));
        }
        let Some(canonical) = yaml_string(yaml_get(entry, "canonical_doc")) else {
            findings.push(AlignmentFinding::new(
                "skill-catalog",
                id,
                "canonical_doc-must-be-text",
            ));
            continue;
        };
        let canonical_path = root.join(canonical);
        if canonical != rule.canonical_doc {
            findings.push(AlignmentFinding::new(
                "skill-catalog",
                id,
                "canonical-doc-route-divergence",
            ));
        }
        if !canonical_path.is_file() {
            findings.push(AlignmentFinding::new(
                "skill-doc",
                canonical,
                "canonical-doc-missing",
            ));
        }
        if fs::canonicalize(&canonical_path)
            .ok()
            .is_none_or(|path| !path.starts_with(root.join("agents/skills")))
        {
            findings.push(AlignmentFinding::new(
                "skill-doc",
                canonical,
                "canonical-doc-outside-public-root",
            ));
        }
        canonical_docs.insert(canonical.to_owned());
        let Some(shim) = yaml_string(yaml_get(entry, "shim")) else {
            findings.push(AlignmentFinding::new(
                "skill-catalog",
                id,
                "shim-must-be-text",
            ));
            continue;
        };
        let shim_path = root.join(shim);
        if !shim_path.is_file() {
            findings.push(AlignmentFinding::new("skill-shim", shim, "shim-missing"));
        }
        if fs::canonicalize(&shim_path)
            .ok()
            .is_none_or(|path| !path.starts_with(&shim_root))
        {
            findings.push(AlignmentFinding::new(
                "skill-shim",
                shim,
                "shim-outside-codex-skill-root",
            ));
        }
    }
    let public_docs_root = root.join("agents/skills");
    let internal_root = root.join("agents/internal-routines");
    if !public_docs_root.is_dir() {
        findings.push(AlignmentFinding::new(
            "skill-doc",
            "agents/skills",
            "public-doc-root-missing",
        ));
    }
    if !internal_root.is_dir() || !internal_root.join("README.md").is_file() {
        findings.push(AlignmentFinding::new(
            "skill-doc",
            "agents/internal-routines/README.md",
            "internal-routine-readme-missing",
        ));
    }
    let mut public_docs = Vec::new();
    if public_docs_root.is_dir() {
        if let Err(error) = walk_markdown(root, &public_docs_root, &mut public_docs) {
            findings.push(AlignmentFinding::new("skill-doc", "agents/skills", error));
        }
    }
    let public_docs = public_docs
        .into_iter()
        .filter(|path| path.file_name().and_then(|name| name.to_str()) != Some("README.md"))
        .map(|path| path.to_string_lossy().replace('\\', "/"))
        .collect::<BTreeSet<_>>();
    for extra in public_docs.difference(&canonical_docs) {
        findings.push(AlignmentFinding::new(
            "skill-doc",
            extra,
            "non-catalog-public-doc",
        ));
    }
    for missing in canonical_docs.difference(&public_docs) {
        findings.push(AlignmentFinding::new(
            "skill-doc",
            missing,
            "catalog-canonical-doc-missing",
        ));
    }
    let mut observed_shims = BTreeSet::new();
    if shim_root.is_dir() {
        if let Ok(entries) = fs::read_dir(&shim_root) {
            for entry in entries.flatten() {
                let path = entry.path().join("SKILL.md");
                if path.is_file() {
                    if let Some(id) = path
                        .parent()
                        .and_then(Path::file_name)
                        .and_then(|name| name.to_str())
                    {
                        if !id.starts_with('_') {
                            observed_shims.insert(id.to_owned());
                        }
                    }
                }
            }
        }
    }
    for extra in observed_shims.difference(&skill_ids) {
        findings.push(AlignmentFinding::new(
            "skill-shim",
            extra,
            "public-shim-missing-catalog-entry",
        ));
    }
    for missing in skill_ids.difference(&observed_shims) {
        findings.push(AlignmentFinding::new(
            "skill-shim",
            missing,
            "catalog-entry-missing-public-shim",
        ));
    }
    for id in OFFICIAL_SYSTEM_SKILLS {
        if skill_ids.contains(*id)
            || root.join("agents/skills").join(format!("{id}.md")).exists()
            || root
                .join(".codex/personal/skills")
                .join(*id)
                .join("SKILL.md")
                .exists()
        {
            findings.push(AlignmentFinding::new(
                "official-skill",
                *id,
                "host-provided-skill-must-not-be-local",
            ));
        }
    }
    match read_text(root, "agents/skills/README.md") {
        Ok(readme) => {
            let duplicate_rows = readme
                .lines()
                .filter(|line| {
                    line.trim_start().starts_with('|')
                        && line.contains("`agents/skills/")
                        && line.contains("`.codex/personal/skills/")
                })
                .count();
            if duplicate_rows > 0 {
                findings.push(AlignmentFinding::new(
                    "skill-doc",
                    "agents/skills/README.md",
                    "duplicate-public-catalog-rows",
                ));
            }
            if !readme.contains("## Official System Skill Delegation") {
                findings.push(AlignmentFinding::new(
                    "official-skill",
                    "agents/skills/README.md",
                    "delegation-section-missing",
                ));
            }
            for id in OFFICIAL_SYSTEM_SKILLS {
                if !readme.contains(&format!("${id}")) {
                    findings.push(AlignmentFinding::new(
                        "official-skill",
                        "agents/skills/README.md",
                        format!("delegation-route-missing:{id}"),
                    ));
                }
            }
        }
        Err(error) => findings.push(AlignmentFinding::new(
            "skill-doc",
            "agents/skills/README.md",
            error,
        )),
    }
    match read_text(root, "agents/canonical/skills.md") {
        Ok(index) if index.contains("[Official System Skill Delegation](../skills/README.md#official-system-skill-delegation)") => {}
        _ => findings.push(AlignmentFinding::new("official-skill", "agents/canonical/skills.md", "delegation-owner-link-missing")),
    }
}

fn check_protocol_docs(root: &Path, findings: &mut Vec<AlignmentFinding>) {
    for (path, markers) in [(
        "agents/TASK_WORKFLOWS.md",
        &[
            "Workflow Contract Owners",
            "agents/task_catalog.yaml",
            "agents/agents_config.json",
            ".codex/agents/*.toml",
            "tools/bin/agent-canon route --prompt",
        ][..],
    )] {
        match read_text(root, path) {
            Ok(text) => {
                for marker in markers {
                    if !text.contains(marker) {
                        findings.push(AlignmentFinding::new(
                            "protocol-doc",
                            path,
                            format!("missing-owner-marker:{marker}"),
                        ));
                    }
                }
            }
            Err(error) => findings.push(AlignmentFinding::new("protocol-doc", path, error)),
        }
    }
    match read_text(root, "agents/canonical/CODEX_SUBAGENTS.md") {
        Ok(text) => {
            if !text.contains("起動結果") || !text.contains("完了結果") {
                findings.push(AlignmentFinding::new(
                    "protocol-doc",
                    "agents/canonical/CODEX_SUBAGENTS.md",
                    "launch-completion-results-not-distinguished",
                ));
            }
            let required_registry_markers = [
                "agents/model_profiles.toml",
                "tools/bin/agent-canon evaluate-codex-agent-roles",
                "generated",
                "readback",
                "restart",
            ];
            for marker in required_registry_markers {
                if !text.contains(marker) {
                    findings.push(AlignmentFinding::new(
                        "protocol-doc",
                        "agents/canonical/CODEX_SUBAGENTS.md",
                        format!("missing-role-profile-marker:{marker}"),
                    ));
                }
            }
            for marker in TOOL_RESULT_ROUTE_MARKERS {
                if !text.contains(marker) {
                    findings.push(AlignmentFinding::new(
                        "protocol-doc",
                        "agents/canonical/CODEX_SUBAGENTS.md",
                        format!("missing-tool-result-route:{marker}"),
                    ));
                }
            }
            if stale_generated_role_authority(&text) {
                findings.push(AlignmentFinding::new(
                    "protocol-doc",
                    "agents/canonical/CODEX_SUBAGENTS.md",
                    "stale-generated-role-authority",
                ));
            }
            let team = read_json(root, "agents/agents_config.json").ok();
            let expected_roles = team
                .as_ref()
                .map(|team| {
                    ["always_on_roles", "specialist_roles"]
                        .into_iter()
                        .flat_map(|section| {
                            team.get(section)
                                .and_then(Value::as_array)
                                .into_iter()
                                .flatten()
                        })
                        .filter_map(|role| {
                            role.get("id").and_then(Value::as_str).map(str::to_owned)
                        })
                        .collect::<BTreeSet<_>>()
                })
                .unwrap_or_default();
            let observed_roles = permanent_team_mapping_roles(&text);
            for missing in expected_roles.difference(&observed_roles) {
                findings.push(AlignmentFinding::new(
                    "protocol-doc",
                    "agents/canonical/CODEX_SUBAGENTS.md",
                    format!("permanent-team-mapping-missing:{missing}"),
                ));
            }
            for stale in observed_roles.difference(&expected_roles) {
                findings.push(AlignmentFinding::new(
                    "protocol-doc",
                    "agents/canonical/CODEX_SUBAGENTS.md",
                    format!("permanent-team-mapping-stale:{stale}"),
                ));
            }
        }
        Err(error) => findings.push(AlignmentFinding::new(
            "protocol-doc",
            "agents/canonical/CODEX_SUBAGENTS.md",
            error,
        )),
    }
    match read_text(root, ".codex/README.md") {
        Ok(text) => {
            let required = [
                "agents/model_profiles.toml",
                "tools/bin/agent-canon evaluate-codex-agent-roles",
                "generated",
                "readback",
                "restart",
            ];
            for marker in required {
                if !text.contains(marker) {
                    findings.push(AlignmentFinding::new(
                        "protocol-doc",
                        ".codex/README.md",
                        format!("missing-role-profile-marker:{marker}"),
                    ));
                }
            }
            if stale_generated_role_authority(&text) {
                findings.push(AlignmentFinding::new(
                    "protocol-doc",
                    ".codex/README.md",
                    "stale-generated-role-authority",
                ));
            }
        }
        Err(error) => findings.push(AlignmentFinding::new(
            "protocol-doc",
            ".codex/README.md",
            error,
        )),
    }
}

fn stale_generated_role_authority(text: &str) -> bool {
    let normalized = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let lowered = normalized.to_lowercase();
    lowered.contains(".codex/agents/*.toml is the source of truth for")
        || lowered.contains("child model settings remain in role tomls")
        || lowered.contains("role tomls are authoritative for model")
        || normalized.contains("各 agent TOML が正本")
        || normalized.contains(".codex/agents/*.toml を更新し、検証します")
}

fn permanent_team_mapping_roles(text: &str) -> BTreeSet<String> {
    let mut in_mapping = false;
    let mut roles = BTreeSet::new();
    for line in text.lines() {
        let line = line.trim();
        if line == "## Permanent Team To Codex Mapping" {
            in_mapping = true;
            continue;
        }
        if in_mapping && line.starts_with("## ") {
            break;
        }
        if !in_mapping || !line.starts_with('|') {
            continue;
        }
        let Some(cell) = line.trim_matches('|').split('|').next() else {
            continue;
        };
        let cell = cell.trim();
        if cell == "Permanent Team Role"
            || cell
                .chars()
                .all(|character| character == '-' || character == ' ')
        {
            continue;
        }
        if let Some(role) = cell
            .strip_prefix('`')
            .and_then(|cell| cell.strip_suffix('`'))
        {
            roles.insert(role.to_owned());
        }
    }
    roles
}

fn check(root: &Path) -> Vec<AlignmentFinding> {
    let mut findings = Vec::new();
    match codex_agent_role_eval::check_alignment(root) {
        Ok(role_findings) => {
            findings.extend(role_findings.into_iter().map(|finding| {
                AlignmentFinding::new(&finding.check, finding.target, finding.detail)
            }))
        }
        Err(error) => findings.push(AlignmentFinding::new("role-eval", "root", error)),
    }
    check_profile_policy(root, &mut findings);
    check_hooks(root, &mut findings);
    check_team_task_catalog(root, &mut findings);
    check_skill_surface(root, &mut findings);
    check_protocol_docs(root, &mut findings);
    findings.sort_by(|left, right| {
        (&left.check, &left.target, &left.detail).cmp(&(&right.check, &right.target, &right.detail))
    });
    findings
}

pub fn run(args: &[String]) -> i32 {
    let mut root = PathBuf::from(".");
    let mut format = Format::Text;
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "-h" | "--help") {
            println!("usage: agent-canon check-agent-runtime-alignment [--root ROOT] [--format text|json]");
            return 0;
        }
        let (name, inline) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        let selected = match resolve_long_option_prefix(name, OPTIONS) {
            Ok(selected) => selected,
            Err(LongOptionError::Unrecognized) => {
                eprintln!("check-agent-runtime-alignment: unrecognized argument {argument}");
                return 2;
            }
            Err(LongOptionError::Ambiguous(matches)) => {
                eprintln!(
                    "check-agent-runtime-alignment: ambiguous option {name}: {}",
                    matches.join(", ")
                );
                return 2;
            }
        };
        if selected == 0 {
            println!("usage: agent-canon check-agent-runtime-alignment [--root ROOT] [--format text|json]");
            return 0;
        }
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            match args.get(index) {
                Some(value) => value.clone(),
                None => {
                    eprintln!("check-agent-runtime-alignment: {name} requires a value");
                    return 2;
                }
            }
        };
        match selected {
            1 => root = PathBuf::from(value),
            2 => match value.as_str() {
                "text" => format = Format::Text,
                "json" => format = Format::Json,
                _ => {
                    eprintln!("check-agent-runtime-alignment: invalid format {value}");
                    return 2;
                }
            },
            _ => unreachable!(),
        }
        index += 1;
    }
    let root = crate::path_resolution::resolve_non_strict(&root).unwrap_or(root);
    let findings = check(&root);
    match format {
        Format::Text => {
            for finding in &findings { println!("AGENT_RUNTIME_ALIGNMENT_FINDING={}:{}:{}", finding.check, finding.target, finding.detail); }
            println!("AGENT_RUNTIME_ALIGNMENT={}", if findings.is_empty() { "pass" } else { "fail" });
        }
        Format::Json => println!("{}", serde_json::to_string_pretty(&json!({"schema":"agent_canon.runtime_alignment.v1","status":if findings.is_empty(){"pass"}else{"fail"},"findings":findings})).unwrap_or_else(|_| "{}".to_owned())),
    }
    i32::from(!findings.is_empty())
}
