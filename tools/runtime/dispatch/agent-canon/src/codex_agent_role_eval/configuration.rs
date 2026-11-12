use super::model_profiles::ModelProfileRegistry;
use super::{read_toml, Configs, Finding};
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

pub(super) fn evaluate(root: &Path, configs: &Configs) -> Result<Vec<Finding>, String> {
    let mut findings = parent_settings(root)?;
    findings.extend(generated_views(root, configs));
    let registry = match ModelProfileRegistry::load(root) {
        Ok(registry) => registry,
        Err(_) => {
            findings.push(Finding::new(
                "model-settings",
                "agents/model_profiles.toml",
                "registry-unreadable",
            ));
            return Ok(findings);
        }
    };
    for (id, config) in configs {
        for key in ["flex", "service_tier", "tier"] {
            if config.get(key).is_some() {
                findings.push(Finding::new(
                    "schema",
                    id,
                    format!("unsupported-profile-key-{key}"),
                ));
            }
        }
        for field in ["name", "description", "developer_instructions"] {
            if config
                .get(field)
                .and_then(Value::as_str)
                .is_none_or(|value| value.trim().is_empty())
            {
                findings.push(Finding::new("schema", id, format!("missing-{field}")));
            }
        }
        if config.get("name") != config.get("__stem") {
            findings.push(Finding::new("schema", id, "name-file-stem-mismatch"));
        }
        let model = config.get("model").and_then(Value::as_str).unwrap_or("");
        let effort = config
            .get("model_reasoning_effort")
            .and_then(Value::as_str)
            .unwrap_or("");
        if model.is_empty() {
            findings.push(Finding::new("model-settings", id, "missing-model"));
        } else if ["gpt-5.2", "gpt-5.3-codex"].contains(&model) {
            findings.push(Finding::new(
                "model-settings",
                id,
                format!("deprecated-model-{model}"),
            ));
        }
        let profile = match registry.profile_for_role(id) {
            Ok(profile) => profile,
            Err(_) => {
                findings.push(Finding::new(
                    "profile-attribution",
                    id,
                    "unknown-role-binding",
                ));
                continue;
            }
        };
        if model != profile.model {
            findings.push(Finding::new(
                "model-settings",
                id,
                format!("expected-model-{}", profile.model),
            ));
        }
        if effort != profile.reasoning_effort {
            findings.push(Finding::new(
                "model-settings",
                id,
                format!("expected-{}-reasoning", profile.reasoning_effort),
            ));
        }
        if !["low", "medium", "high", "xhigh"].contains(&effort) {
            findings.push(Finding::new(
                "model-settings",
                id,
                "invalid-model-reasoning-effort",
            ));
        }
        let read_only = id.ends_with("_reviewer")
            || [
                "diff_triage_reviewer",
                "explorer",
                "literature_researcher",
                "reviewer",
                "ship_reviewer",
                "test_designer",
                "skill_evaluator",
            ]
            .contains(&id.as_str());
        if read_only && config.get("sandbox_mode").and_then(Value::as_str) != Some("read-only") {
            findings.push(Finding::new("behavior", id, "read-only-role-not-read-only"));
        }
        if id == "skill_evaluator" {
            if config.get("sandbox_mode").and_then(Value::as_str) != Some("read-only") {
                findings.push(Finding::new("behavior", id, "evaluator-not-read-only"));
            }
            if config.get("approval_policy").and_then(Value::as_str) != Some("never") {
                findings.push(Finding::new(
                    "behavior",
                    id,
                    "evaluator-approval-policy-not-never",
                ));
            }
        }
    }
    Ok(findings)
}

fn parent_settings(root: &Path) -> Result<Vec<Finding>, String> {
    let path = root.join(".codex/config.toml");
    if !path.is_file() {
        return Ok(vec![Finding::new(
            "model-settings",
            ".codex/config.toml",
            "missing-config",
        )]);
    }
    let config = read_toml(&path)?;
    let mut findings = Vec::new();
    if config.get("agent_model_policy").is_some() {
        findings.push(Finding::new(
            "model-settings",
            ".codex/config.toml",
            "legacy-agent-model-policy",
        ));
    }
    let registry = match ModelProfileRegistry::load(root) {
        Ok(registry) => registry,
        Err(_) => {
            return Ok(vec![Finding::new(
                "model-settings",
                "agents/model_profiles.toml",
                "registry-unreadable",
            )])
        }
    };
    let (parent, review) = match (
        registry.by_profile("sol_parent_high"),
        registry.by_profile("luna_reasoning_high"),
    ) {
        (Ok(parent), Ok(review)) => (parent, review),
        _ => {
            return Ok(vec![Finding::new(
                "model-settings",
                "agents/model_profiles.toml",
                "registry-unreadable",
            )])
        }
    };
    for (key, expected) in [
        ("model", parent.model.as_str()),
        ("model_reasoning_effort", parent.reasoning_effort.as_str()),
        ("review_model", review.model.as_str()),
    ] {
        if config.get(key).and_then(Value::as_str) != Some(expected) {
            findings.push(Finding::new(
                "model-settings",
                ".codex/config.toml",
                format!("expected-{key}-{expected}"),
            ));
        }
    }
    for key in ["service_tier", "flex", "tier"] {
        if config.get(key).is_some() {
            findings.push(Finding::new(
                "model-settings",
                ".codex/config.toml",
                format!("unsupported-profile-key-{key}"),
            ));
        }
    }
    Ok(findings)
}

fn generated_views(root: &Path, configs: &Configs) -> Vec<Finding> {
    let team = match fs::read(root.join("agents/agents_config.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
    {
        Some(team) => team,
        None => {
            return vec![Finding::new(
                "generated-view",
                "canonical",
                "materializer-error-ValueError",
            )]
        }
    };
    let generated = match ModelProfileRegistry::load(root)
        .and_then(|registry| registry.generate_consumer_static_role_views(root))
    {
        Ok(generated) => generated,
        Err(_) => {
            return vec![Finding::new(
                "generated-view",
                "canonical",
                "materializer-error-ModelProfileRegistryError",
            )]
        }
    };
    let sources = team.get("agent_views").and_then(Value::as_object);
    let bindings = team.get("roles").and_then(Value::as_array).map(|roles| {
        roles
            .iter()
            .filter_map(|role| role.get("id").and_then(Value::as_str).map(|id| (id, role)))
            .collect::<std::collections::BTreeMap<_, _>>()
    });
    let ids = configs.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let Some((sources, bindings)) = sources.zip(bindings).filter(|(sources, bindings)| {
        sources.keys().map(String::as_str).collect::<BTreeSet<_>>() == ids
            && bindings.keys().copied().collect::<BTreeSet<_>>() == ids
    }) else {
        return vec![Finding::new(
            "generated-view",
            "agents_config",
            "role-view-binding-set-mismatch",
        )];
    };
    let registry = match ModelProfileRegistry::load(root) {
        Ok(registry) => registry,
        Err(_) => {
            return vec![Finding::new(
                "generated-view",
                "canonical",
                "materializer-error-ModelProfileRegistryError",
            )]
        }
    };
    let mut findings = Vec::new();
    for (id, config) in configs {
        let source = &sources[id];
        let binding = bindings[id.as_str()];
        let Some(profile_id) = source.get("profile_id").and_then(Value::as_str) else {
            findings.push(Finding::new("profile-attribution", id, "unknown-profile"));
            continue;
        };
        let profile = match registry.by_profile(profile_id) {
            Ok(profile) => profile,
            Err(_) => {
                findings.push(Finding::new("profile-attribution", id, "unknown-profile"));
                continue;
            }
        };
        if binding.get("profile_id").and_then(Value::as_str) != Some(profile_id) {
            findings.push(Finding::new(
                "profile-attribution",
                id,
                "binding-divergence",
            ));
        }
        if config.get("model").and_then(Value::as_str) != Some(profile.model.as_str())
            || config.get("model_reasoning_effort").and_then(Value::as_str)
                != Some(profile.reasoning_effort.as_str())
        {
            findings.push(Finding::new(
                "profile-attribution",
                id,
                "runtime-view-divergence",
            ));
        }
        for field in [
            "name",
            "description",
            "nickname_candidates",
            "sandbox_mode",
            "approval_policy",
        ] {
            if config.get(field) != source.get(field) {
                findings.push(Finding::new(
                    "generated-view",
                    id,
                    format!("source-divergence-{field}"),
                ));
            }
        }
        if generated.get(id).is_none_or(|view| {
            source
                .get("developer_instructions")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                != view.rendered_instructions.trim()
        }) {
            findings.push(Finding::new(
                "generated-view",
                id,
                "developer-instructions-not-materialized",
            ));
        }
        if !fs::read_to_string(root.join(".codex/agents").join(format!("{id}.toml")))
            .unwrap_or_default()
            .contains("generated_role_view_v1")
        {
            findings.push(Finding::new(
                "generated-view",
                id,
                "missing-generated-header",
            ));
        }
    }
    findings
}
