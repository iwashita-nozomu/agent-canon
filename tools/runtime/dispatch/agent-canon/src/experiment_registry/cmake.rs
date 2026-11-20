// @dependency-start
// contract implementation
// responsibility Checks the project-owned CMake entry and experiment topic registrations without building.
// upstream design ../../../../../../documents/experiments/experiment-registry.md CMake profile contract
// downstream implementation ../experiment_registry.rs native experiment-registry dispatch
// @dependency-end

use super::{validate_segment, Finding};
use serde::Deserialize;
use std::collections::BTreeSet;
use std::path::{Component, Path, PathBuf};

#[derive(Deserialize)]
struct Registry {
    schema_version: u32,
    defaults: Defaults,
    topic: Vec<Topic>,
}

#[derive(Deserialize)]
struct Defaults {
    integration_branch: String,
}

#[derive(Deserialize)]
struct Topic {
    topic: String,
    topic_dir: PathBuf,
}

pub(super) fn collect_findings(
    root: &Path,
    registry_path: &Path,
    cmake_entry: &Path,
) -> Result<Vec<Finding>, String> {
    let root = root
        .canonicalize()
        .map_err(|error| format!("repository {}: {error}", root.display()))?;
    let Some(registry_file) = registry_path
        .canonicalize()
        .ok()
        .filter(|path| path.starts_with(&root) && path.is_file())
    else {
        return Ok(vec![error(format!(
            "registry must be a file within the repository: {}",
            registry_path.display()
        ))]);
    };
    let text = std::fs::read_to_string(&registry_file)
        .map_err(|failure| format!("{}: {failure}", registry_file.display()))?;
    let registry: Registry = toml_edit::de::from_str(&text).map_err(|failure| {
        format!(
            "invalid CMake registry {}: {failure}",
            registry_file.display()
        )
    })?;
    let mut findings = Vec::new();
    if registry.schema_version != 1 {
        findings.push(error(format!(
            "schema_version must be 1, got {}",
            registry.schema_version
        )));
    }
    if registry.defaults.integration_branch.trim().is_empty() {
        findings.push(error("defaults.integration_branch must name a branch"));
    }
    if !existing_path(&root, cmake_entry).is_some_and(|path| path.is_file()) {
        findings.push(error(format!(
            "CMake entry must be a file within the repository: {}",
            cmake_entry.display()
        )));
    }
    let mut names = BTreeSet::new();
    for topic in registry.topic {
        if let Err(failure) = validate_segment(&topic.topic, "topic") {
            findings.push(error(failure));
        }
        if !names.insert(topic.topic.clone()) {
            findings.push(error(format!("duplicate topic name: {}", topic.topic)));
        }
        if !existing_path(&root, &topic.topic_dir).is_some_and(|path| path.is_dir()) {
            findings.push(error(format!(
                "{}.topic_dir must be a directory within the repository: {}",
                topic.topic,
                topic.topic_dir.display()
            )));
        }
    }
    Ok(findings)
}

fn existing_path(root: &Path, relative: &Path) -> Option<PathBuf> {
    if relative.as_os_str().is_empty()
        || !relative
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
    {
        return None;
    }
    root.join(relative)
        .canonicalize()
        .ok()
        .filter(|path| path.starts_with(root))
}

fn error(message: impl Into<String>) -> Finding {
    Finding {
        level: "error",
        message: message.into(),
    }
}
