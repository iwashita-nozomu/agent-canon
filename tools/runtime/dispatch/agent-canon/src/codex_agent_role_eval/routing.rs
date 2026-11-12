use super::{read_toml, Finding};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;
use yaml_rust2::Yaml;

fn yaml_json(value: &Yaml) -> Value {
    match value {
        Yaml::String(value) => Value::String(value.clone()),
        Yaml::Integer(value) => Value::from(*value),
        Yaml::Boolean(value) => Value::Bool(*value),
        Yaml::Array(values) => Value::Array(values.iter().map(yaml_json).collect()),
        Yaml::Hash(values) => Value::Object(
            values
                .iter()
                .filter_map(|(key, value)| {
                    key.as_str().map(|key| (key.to_owned(), yaml_json(value)))
                })
                .collect(),
        ),
        Yaml::Real(value) => value.parse::<f64>().map(Value::from).unwrap_or(Value::Null),
        _ => Value::Null,
    }
}

fn strings(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect()
}

fn array<'a>(value: &'a Value, key: &str) -> &'a [Value] {
    value
        .get(key)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

fn specialists(config: &Value, catalog: &Value, task_id: &str) -> Result<Vec<String>, String> {
    let Some(task) = array(catalog, "tasks")
        .iter()
        .find(|task| task.get("id").and_then(Value::as_str) == Some(task_id))
    else {
        return Err(format!("unknown task id: {task_id}"));
    };
    let family_id = task.get("family").and_then(Value::as_str).unwrap_or("");
    let family = array(catalog, "workflow_families")
        .iter()
        .find(|family| family.get("id").and_then(Value::as_str) == Some(family_id))
        .ok_or_else(|| format!("unknown workflow family: {family_id}"))?;
    let family_roles = family
        .get("roles")
        .filter(|roles| roles.is_object())
        .ok_or_else(|| format!("workflow family roles must be a mapping for {family_id}"))?;
    let family_specialists = strings(family_roles.get("specialists"));
    let mut result = strings(task.get("specialists"));
    for id in &result {
        if !family_specialists.contains(id) {
            return Err(format!(
                "task {task_id} specialist {id} is not declared in family {family_id}"
            ));
        }
    }
    for pack in array(catalog, "review_packs") {
        if strings(pack.get("default_for_tasks")).contains(&task_id.to_owned()) {
            result.extend(strings(pack.get("specialists")));
        }
    }
    let known = array(config, "always_on_roles")
        .iter()
        .chain(array(config, "specialist_roles"))
        .filter_map(|role| role.get("id").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    let mut seen = BTreeSet::new();
    for id in &result {
        if !known.contains(id.as_str()) {
            return Err(format!("unknown role: {id}"));
        }
    }
    result.retain(|id| seen.insert(id.clone()));
    Ok(result)
}

fn python_tuple(values: &[String]) -> String {
    let body = values
        .iter()
        .map(|value| format!("'{value}'"))
        .collect::<Vec<_>>()
        .join(", ");
    format!("({body}{})", if values.len() == 1 { "," } else { "" })
}

pub(super) fn evaluate(root: &Path) -> Result<Vec<Finding>, String> {
    let config: Value = serde_json::from_slice(
        &fs::read(root.join("agents/agents_config.json")).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;
    let yaml =
        crate::catalog::tool_catalog::load_yaml_document(&root.join("agents/task_catalog.yaml"))?;
    let catalog = yaml_json(&yaml);
    let mut roles = BTreeMap::new();
    let mut ordered_roles = Vec::new();
    for role in array(&config, "always_on_roles")
        .iter()
        .chain(array(&config, "specialist_roles"))
    {
        if let Some(id) = role.get("id").and_then(Value::as_str) {
            roles.insert(id, role);
            ordered_roles.push((id, role));
        }
    }
    let always_on = array(&config, "always_on_roles")
        .iter()
        .filter_map(|role| role.get("id").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    let mut findings = Vec::new();
    if let Some(role) = roles.get("skill_evaluator") {
        for (condition, detail) in [
            (
                role.get("activation").and_then(Value::as_str)
                    != Some("explicit_empirical_skill_evaluation"),
                "activation-must-be-explicit",
            ),
            (
                always_on.contains("skill_evaluator"),
                "must-not-be-always-on",
            ),
            (
                role.pointer("/write_policy/mode").and_then(Value::as_str)
                    != Some("artifacts_only"),
                "must-be-artifacts-only",
            ),
            (
                !strings(role.pointer("/write_policy/allowed_artifacts"))
                    .contains(&"skill_evaluation".to_owned()),
                "missing-skill-evaluation-artifact",
            ),
        ] {
            if condition {
                findings.push(Finding::new("registration", "skill_evaluator", detail));
            }
        }
    } else {
        findings.push(Finding::new(
            "registration",
            "skill_evaluator",
            "missing-permanent-role",
        ));
    }
    if !roles.contains_key("terra") {
        findings.push(Finding::new(
            "registration",
            "terra",
            "missing-permanent-role",
        ));
    } else if always_on.contains("terra") {
        findings.push(Finding::new(
            "registration",
            "terra",
            "must-not-be-always-on",
        ));
    }
    for (id, role) in &ordered_roles {
        if *id != "skill_evaluator"
            && strings(role.get("codex_agents")).contains(&"skill_evaluator".to_owned())
        {
            findings.push(Finding::new(
                "registration",
                *id,
                "skill-evaluator-candidate-reserved-for-skill-evaluator-role",
            ));
        }
    }
    let project = if root.join(".codex/config.toml").is_file() {
        read_toml(&root.join(".codex/config.toml"))?
    } else {
        json!({})
    };
    let mut registered = BTreeSet::new();
    let mut types = Vec::new();
    for (_, role) in &ordered_roles {
        for id in strings(role.get("codex_agents")) {
            if id != "default" && registered.insert(id.clone()) {
                types.push(id);
            }
        }
    }
    if registered.insert("skill_evaluator".into()) {
        types.push("skill_evaluator".into());
    }
    for id in types {
        let registration = project.get("agents").and_then(|agents| agents.get(&id));
        if registration.is_none_or(|value| !value.is_object()) {
            findings.push(Finding::new(
                "registration",
                &id,
                "missing-project-registration",
            ));
        } else if registration
            .and_then(|value| value.get("config_file"))
            .and_then(Value::as_str)
            != Some(format!("agents/{id}.toml").as_str())
        {
            findings.push(Finding::new("registration", &id, "mismatched-config-file"));
        }
        if !root
            .join(".codex/agents")
            .join(format!("{id}.toml"))
            .is_file()
        {
            findings.push(Finding::new("registration", &id, "missing-toml"));
        }
    }
    let evaluator_tasks = array(&catalog, "tasks")
        .iter()
        .filter(|task| strings(task.get("specialists")).contains(&"skill_evaluator".to_owned()))
        .filter_map(|task| task.get("id").and_then(Value::as_str))
        .collect::<Vec<_>>();
    if evaluator_tasks != ["T14"] {
        findings.push(Finding::new(
            "registration",
            "skill_evaluator",
            "must-be-only-in-explicit-evaluation-task",
        ));
    }
    // The configured family boundary is independent of T14 task registration.
    for family in array(&catalog, "workflow_families") {
        let id = family.get("id").and_then(Value::as_str).unwrap_or("");
        if id != "skill_evaluation"
            && ["always_on", "specialists"].iter().any(|key| {
                strings(family.get("roles").and_then(|roles| roles.get(key)))
                    .contains(&"skill_evaluator".to_owned())
            })
        {
            findings.push(Finding::new(
                "routing",
                id,
                "skill-evaluator-only-in-skill-evaluation",
            ));
        }
    }
    for (id, expected) in [
        (
            "change_reviewer",
            &[
                "diff_triage_reviewer",
                "python_reviewer",
                "cpp_reviewer",
                "reviewer",
            ][..],
        ),
        ("experimenter", &["experiment_runner", "worker"][..]),
        (
            "final_reviewer",
            &["ship_reviewer", "reviewer", "project_reviewer"][..],
        ),
        ("implementer", &["worker", "spark_worker"][..]),
    ] {
        let expected = expected
            .iter()
            .map(|value| (*value).to_owned())
            .collect::<Vec<_>>();
        let observed = roles
            .get(id)
            .map(|role| strings(role.get("codex_agents")))
            .unwrap_or_default();
        if observed.get(..expected.len()) != Some(expected.as_slice()) {
            findings.push(Finding::new(
                "routing",
                id,
                format!("role-candidate-order-expected-{}", python_tuple(&expected)),
            ));
        }
    }
    if let Some(topology) = catalog
        .get("role_topology_defaults")
        .filter(|value| value.is_object())
    {
        let families = topology.get("role_families");
        if strings(families.and_then(|value| value.get("implementation")))
            != ["worker", "spark_worker"]
        {
            findings.push(Finding::new(
                "routing",
                "role_topology_defaults.role_families.implementation",
                "implementation-role-family-order",
            ));
        }
        if strings(families.and_then(|value| value.get("test_design"))) != ["test_designer"] {
            findings.push(Finding::new(
                "routing",
                "role_topology_defaults.role_families.test_design",
                "test-design-role-family",
            ));
        }
        if strings(families.and_then(|value| value.get("design"))).contains(&"test_designer".into())
        {
            findings.push(Finding::new(
                "routing",
                "role_topology_defaults.role_families.design",
                "test-designer-must-be-post-implementation",
            ));
        }
    }
    for id in ["T1", "T2"] {
        if array(&catalog, "tasks")
            .iter()
            .find(|task| task.get("id").and_then(Value::as_str) == Some(id))
            .and_then(|task| task.get("family"))
            .and_then(Value::as_str)
            != Some("owner_bounded_change")
        {
            findings.push(Finding::new("routing", id, "must-use-owner-bounded-change"));
        }
        let active = specialists(&config, &catalog, id)?;
        let forbidden = ["document_flow_reviewer", "schedule_reviewer", "scheduler"]
            .iter()
            .filter(|name| active.iter().any(|id| id == **name))
            .map(|name| format!("'{name}'"))
            .collect::<Vec<_>>();
        if !forbidden.is_empty() {
            findings.push(Finding::new(
                "routing",
                id,
                format!("lite-route-heavy-specialists-[{}]", forbidden.join(", ")),
            ));
        }
    }
    let t12 = specialists(&config, &catalog, "T12")?;
    if t12
        != [
            "scheduler",
            "schedule_reviewer",
            "project_reviewer",
            "docs_workflow_steward",
            "prompt_config_reviewer",
        ]
    {
        findings.push(Finding::new(
            "routing",
            "T12",
            format!("t12-overdefault-specialist-{}", python_tuple(&t12)),
        ));
    }
    for pack in array(&catalog, "review_packs") {
        let id = pack.get("id").and_then(Value::as_str).unwrap_or("");
        let defaults = strings(pack.get("default_for_tasks"));
        if id == "research_perspective_review" && !defaults.is_empty() {
            findings.push(Finding::new("routing", id, "full-pack-must-not-default"));
        }
        if id == "repo_integration_review" && defaults.contains(&"T12".into()) {
            findings.push(Finding::new("routing", id, "t12-overdefault-specialist"));
        }
        if id == "research_perspective_triage"
            && strings(pack.get("specialists"))
                .into_iter()
                .collect::<BTreeSet<_>>()
                != [
                    "reproducibility_reviewer".to_owned(),
                    "artifact_reviewer".to_owned(),
                ]
                .into_iter()
                .collect()
        {
            findings.push(Finding::new("routing", id, "unexpected-triage-specialists"));
        }
    }
    if array(&catalog, "tasks")
        .iter()
        .find(|task| task.get("id").and_then(Value::as_str) == Some("T14"))
        .and_then(|task| task.get("family"))
        .and_then(Value::as_str)
        != Some("skill_evaluation")
    {
        findings.push(Finding::new(
            "routing",
            "T14",
            "must-use-skill-evaluation-family",
        ));
    } else {
        let roles = array(&catalog, "workflow_families")
            .iter()
            .find(|family| family.get("id").and_then(Value::as_str) == Some("skill_evaluation"))
            .and_then(|family| family.get("roles"));
        if roles
            .and_then(|roles| roles.get("always_on"))
            .and_then(Value::as_array)
            .is_none_or(|values| !values.is_empty())
        {
            findings.push(Finding::new(
                "routing",
                "T14",
                "evaluation-route-has-default-roles",
            ));
        }
        if strings(roles.and_then(|roles| roles.get("specialists"))) != ["skill_evaluator"] {
            findings.push(Finding::new(
                "routing",
                "T14",
                "evaluation-route-specialists-must-be-evaluator-only",
            ));
        }
    }
    Ok(findings)
}
