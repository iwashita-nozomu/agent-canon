// @dependency-start
// contract implementation
// responsibility Updates existing experiment registry branch, worktree, and note metadata.
// upstream implementation store.rs owns registry loading and deterministic serialization
// upstream implementation ../path_resolution.rs resolves non-strict paths
// @dependency-end

use super::{store, RegistryValue, CONTEXT_SELECTOR};
use crate::path_resolution::resolve_non_strict;
use crate::python_cli_options::resolve_long_option_prefix;
use crate::python_text::python_strip;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

const OPTIONS: &[(&str, &str)] = &[
    ("--topic", "topic"),
    ("--repo-root", "repo-root"),
    ("--registry", "registry"),
    ("--workspace-root", "workspace-root"),
    ("--branch", "branch"),
    ("--scope-file", "scope-file"),
    ("--branch-note", "branch-note"),
    ("--primary-note", "primary-note"),
    ("--clear-context", "clear-context"),
    ("--help", "help"),
];

fn parse(args: &[String]) -> Result<BTreeMap<String, String>, String> {
    let mut values = BTreeMap::new();
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        let (name, inline) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        let key = if name == "-h" {
            "help"
        } else if let Some((_, key)) = OPTIONS.iter().find(|(option, _)| *option == name) {
            *key
        } else {
            resolve_long_option_prefix(name, OPTIONS)
                .map_err(|error| format!("{error:?}: {name}"))?
        };
        if matches!(key, "clear-context" | "help") {
            if inline.is_some() {
                return Err(format!("argument {name}: ignored explicit argument"));
            }
            values.insert(key.to_owned(), String::new());
            if key == "help" {
                return Ok(values);
            }
        } else {
            let value = if let Some(value) = inline {
                value.to_owned()
            } else {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| format!("argument {name}: expected one argument"))?;
                if value.starts_with("--") {
                    return Err(format!("argument {name}: expected one argument"));
                }
                value.clone()
            };
            values.insert(key.to_owned(), value);
        }
        index += 1;
    }
    if !values.contains_key("topic") {
        return Err("the following arguments are required: --topic".to_owned());
    }
    Ok(values)
}

fn path_value(values: &BTreeMap<String, String>, key: &str) -> Result<Option<PathBuf>, String> {
    values
        .get(key)
        .map(|value| resolve_non_strict(Path::new(value)))
        .transpose()
}

fn relative(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .into_owned()
}

fn execute(values: &BTreeMap<String, String>) -> Result<(), String> {
    let repo_root = match path_value(values, "repo-root")? {
        Some(root) => root,
        None => resolve_non_strict(&super::source_root())?,
    };
    let registry_path = path_value(values, "registry")?
        .unwrap_or_else(|| repo_root.join("experiments/registry.toml"));
    let workspace =
        path_value(values, "workspace-root")?.unwrap_or(resolve_non_strict(Path::new("."))?);
    let mut registry = store::load(&registry_path)?;
    let topic_name = &values["topic"];
    let topic = store::find_topic_mut(&mut registry, topic_name)?.ok_or_else(|| {
        format!(
            "topic {} is missing from {}",
            super::python_repr(&RegistryValue::String(topic_name.clone())),
            registry_path.display()
        )
    })?;
    if values.contains_key("clear-context") {
        for key in [
            "active_branch",
            "active_worktree",
            "scope_file",
            "branch_note",
        ] {
            store::remove(topic, key);
        }
    } else {
        let branch = match values.get("branch").filter(|value| !value.is_empty()) {
            Some(branch) => branch.clone(),
            None => {
                let failure = || {
                    format!(
                        "failed to resolve current branch for {}",
                        workspace.display()
                    )
                };
                let output = Command::new("git")
                    .arg("-C")
                    .arg(&workspace)
                    .args(["rev-parse", "--abbrev-ref", "HEAD"])
                    .output()
                    .map_err(|_| failure())?;
                let branch = String::from_utf8(output.stdout).map_err(|error| error.to_string())?;
                let branch = python_strip(&branch);
                if !output.status.success() || branch.is_empty() {
                    return Err(failure());
                }
                branch.to_owned()
            }
        };
        store::set(topic, "active_branch", RegistryValue::String(branch));
        store::set(
            topic,
            "active_worktree",
            RegistryValue::String(relative(&repo_root, &workspace)),
        );
        let scope = path_value(values, "scope-file")?
            .unwrap_or_else(|| workspace.join("WORKTREE_SCOPE.md"));
        if scope.exists() {
            store::set(
                topic,
                "scope_file",
                RegistryValue::String(relative(&repo_root, &resolve_non_strict(&scope)?)),
            );
        } else {
            store::remove(topic, "scope_file");
        }
        if let Some(note) = values.get("branch-note").filter(|value| !value.is_empty()) {
            store::set(topic, "branch_note", RegistryValue::String(note.clone()));
        }
    }
    if let Some(note) = values.get("primary-note").filter(|value| !value.is_empty()) {
        store::set(topic, "primary_note", RegistryValue::String(note.clone()));
    }
    store::write(&registry_path, &registry)?;
    println!(
        "registry_path={}\ntopic_name={topic_name}",
        registry_path.display()
    );
    Ok(())
}

pub fn run(args: &[String]) -> i32 {
    let values = match parse(args) {
        Ok(values) => values,
        Err(error) => {
            eprintln!("agent-canon {CONTEXT_SELECTOR}: error: {error}");
            return 2;
        }
    };
    if values.contains_key("help") {
        println!("usage: agent-canon {CONTEXT_SELECTOR} --topic TOPIC [--repo-root PATH] [--registry PATH] [--workspace-root PATH] [--branch NAME] [--scope-file PATH] [--branch-note PATH] [--primary-note PATH] [--clear-context]");
        return 0;
    }
    match execute(&values) {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("{error}");
            1
        }
    }
}
