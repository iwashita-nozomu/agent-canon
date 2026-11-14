//! Native dependency-module adapter over the generic repository-topic lifecycle.

// @dependency-start
// contract implementation
// responsibility Resolves one .gitmodules dependency identity and delegates its topic checkout lifecycle to repository_topic_clone.rs.
// upstream design ../../../../../documents/rule/dependency-module-changes.md owns the adapter identity and parent-state contract
// upstream implementation repository_topic_clone.rs owns computed checkout paths, Git mutation, and cleanup
// downstream test ../../../../../tests/agent_tools/test_dependency_module_change.py drives the native CLI and checks .gitmodules readback
// @dependency-end

use crate::repository_topic_clone::{self, CheckoutMode, RepositoryTopicCloneRequest};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

const USAGE: &str = "usage: agent-canon dependency-module-change [--root ROOT] <prepare|merge-main|status|cleanup> [options]";

#[derive(Clone, Debug, Eq, PartialEq)]
struct DependencyModule {
    path: String,
    url: String,
}

impl DependencyModule {
    fn basename(&self) -> Result<String, String> {
        Path::new(&self.path)
            .file_name()
            .and_then(|value| value.to_str())
            .filter(|value| !value.is_empty())
            .map(str::to_owned)
            .ok_or_else(|| "topic-identity-required: module path has no basename".to_owned())
    }
}

fn git_config(root: &Path, args: &[&str]) -> Result<String, String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| format!("git process unavailable: {error}"))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
    }
    String::from_utf8(output.stdout).map_err(|error| format!("git output is not UTF-8: {error}"))
}

fn parse_gitmodules(root: &Path) -> Result<Vec<DependencyModule>, String> {
    let manifest = root.join(".gitmodules");
    let metadata = std::fs::symlink_metadata(&manifest).map_err(|_| {
        format!(
            "topic-identity-required: missing .gitmodules at {}",
            manifest.display()
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!(
            "topic-identity-required: cannot read {}",
            manifest.display()
        ));
    }
    let manifest_text = manifest.to_string_lossy().into_owned();
    let output = git_config(
        root,
        &["config", "--file", &manifest_text, "--null", "--list"],
    )
    .map_err(|_| {
        format!(
            "topic-identity-required: cannot read {}",
            manifest.display()
        )
    })?;
    let mut values = BTreeMap::<String, BTreeMap<String, String>>::new();
    for record in output.split('\0').filter(|value| !value.is_empty()) {
        let Some((key, value)) = record.split_once('\n') else {
            continue;
        };
        let Some(key) = key.strip_prefix("submodule.") else {
            continue;
        };
        let Some((name, field)) = key.rsplit_once('.') else {
            continue;
        };
        if matches!(field, "path" | "url") {
            values
                .entry(name.to_owned())
                .or_default()
                .insert(field.to_owned(), value.to_owned());
        }
    }
    let mut modules = Vec::new();
    for (_, fields) in values {
        let path = fields
            .get("path")
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                format!(
                    "topic-identity-required: missing path in {}",
                    manifest.display()
                )
            })?;
        let url = fields
            .get("url")
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                format!(
                    "topic-identity-required: missing url in {}",
                    manifest.display()
                )
            })?;
        if path.starts_with('/') {
            return Err(format!(
                "topic-identity-required: submodule path must be relative: {path:?}"
            ));
        }
        modules.push(DependencyModule { path, url });
    }
    if modules.is_empty() {
        return Err(format!(
            "topic-identity-required: no dependency modules found in {}",
            manifest.display()
        ));
    }
    Ok(modules)
}

fn select_module<'a>(
    modules: &'a [DependencyModule],
    path: &str,
) -> Result<&'a DependencyModule, String> {
    modules
        .iter()
        .find(|module| module.path == path)
        .ok_or_else(|| format!("topic-identity-required: unknown --module {path:?}"))
}

fn normalize_url(value: &str) -> String {
    let value = value.trim();
    value.strip_suffix(".git").unwrap_or(value).to_owned()
}

fn resolve_module_url(root: &Path, value: &str) -> Result<String, String> {
    if !value.starts_with("./") && !value.starts_with("../") {
        return Ok(normalize_url(value));
    }
    let parent_remote = git_config(root, &["config", "--get", "remote.origin.url"])?;
    let parent_remote = parent_remote.trim();
    if parent_remote.is_empty() {
        return Err(
            "topic-identity-required: relative module url requires parent remote".to_owned(),
        );
    }
    if parent_remote.contains("://") {
        let parent = parent_remote
            .rsplit_once('/')
            .map(|(prefix, _)| prefix)
            .unwrap_or(parent_remote);
        Ok(normalize_url(&format!("{parent}/{value}")))
    } else {
        let parent_remote_path = PathBuf::from(parent_remote);
        let parent = parent_remote_path.parent().ok_or_else(|| {
            "topic-identity-required: relative module url requires parent remote".to_owned()
        })?;
        let resolved = parent.join(value);
        Ok(normalize_url(&resolved.to_string_lossy()))
    }
}

fn request_from_args(
    root: &Path,
    topic: &str,
    module_path: &str,
    branch: &str,
) -> Result<RepositoryTopicCloneRequest, String> {
    let root = repository_topic_clone::validate_workspace_root(root, false)
        .map_err(|error| error.to_string())?;
    let modules = parse_gitmodules(&root)?;
    let module = select_module(&modules, module_path)?;
    let repository = module.basename()?;
    let topic = repository_topic_clone::topic_slug(topic).map_err(|error| error.to_string())?;
    if repository == topic {
        return Err(
            "topic-identity-required: module basename collides with topic container".to_owned(),
        );
    }
    let url = resolve_module_url(&root, &module.url)?;
    Ok(RepositoryTopicCloneRequest {
        url,
        repository,
        workspace_root: root,
        topic,
        branch: branch.to_owned(),
        checkout_mode: CheckoutMode::IndependentClone,
    })
}

#[derive(Default)]
struct Options {
    values: BTreeMap<String, String>,
    flags: std::collections::BTreeSet<String>,
}

fn parse_options(
    args: &[String],
    allowed_values: &[&str],
    allowed_flags: &[&str],
) -> Result<Options, String> {
    let mut parsed = Options::default();
    let all = allowed_values
        .iter()
        .map(|name| (*name, true))
        .chain(allowed_flags.iter().map(|name| (*name, false)))
        .collect::<Vec<_>>();
    let option_ids = all
        .iter()
        .map(|(name, is_value)| (*name, (*name, *is_value)))
        .collect::<Vec<_>>();
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        let (option, inline) = argument
            .split_once('=')
            .map_or((argument, None), |(key, value)| (key, Some(value)));
        let resolved = crate::python_cli_options::resolve_long_option_prefix(option, &option_ids)
            .map_err(|error| match error {
            crate::python_cli_options::LongOptionError::Unrecognized => {
                format!("unrecognized arguments: {argument}")
            }
            crate::python_cli_options::LongOptionError::Ambiguous(_) => {
                format!("ambiguous option: {option}")
            }
        })?;
        if resolved.1 {
            let value = if let Some(value) = inline {
                value.to_owned()
            } else {
                index += 1;
                args.get(index)
                    .filter(|value| !value.starts_with('-'))
                    .cloned()
                    .ok_or_else(|| format!("argument {option}: expected one argument"))?
            };
            parsed.values.insert(resolved.0.to_owned(), value);
        } else {
            if inline.is_some() {
                return Err(format!("argument {option}: does not take a value"));
            }
            parsed.flags.insert(resolved.0.to_owned());
        }
        index += 1;
    }
    Ok(parsed)
}

fn required(options: &Options, field: &str) -> Result<String, String> {
    options
        .values
        .get(field)
        .cloned()
        .ok_or_else(|| format!("the following arguments are required: {field}"))
}

fn run_command(root: &Path, command: &str, args: &[String]) -> Result<i32, String> {
    match command {
        "prepare" | "merge-main" => {
            let options = parse_options(args, &["--topic", "--module", "--branch"], &[])?;
            let topic = required(&options, "--topic")?;
            let module = required(&options, "--module")?;
            let branch = required(&options, "--branch")?;
            let request = request_from_args(root, &topic, &module, &branch)?;
            if command == "prepare" {
                let receipt = repository_topic_clone::prepare(&request)
                    .map_err(|error| format!("REPOSITORY_TOPIC_CLONE_ERROR={error}"))?;
                println!(
                    "TOPIC_ROOT={}",
                    receipt.clone.parent().unwrap_or(&receipt.clone).display()
                );
                println!("SOURCE_CLONE={}", receipt.clone.display());
                println!("SOURCE_BRANCH={}", receipt.branch);
            } else {
                let receipt = repository_topic_clone::merge_main(&request)
                    .map_err(|error| format!("REPOSITORY_TOPIC_CLONE_ERROR={error}"))?;
                println!("MERGE_CANDIDATE_SHA={}", receipt.candidate_sha);
                println!("MERGE_INTEGRATED_SHA={}", receipt.merged_sha);
            }
            Ok(0)
        }
        "status" => {
            let options = parse_options(args, &["--topic", "--module"], &[])?;
            let modules = parse_gitmodules(root)?;
            let topic = required(&options, "--topic")?;
            let topic =
                repository_topic_clone::topic_slug(&topic).map_err(|error| error.to_string())?;
            let selected = options
                .values
                .get("--module")
                .map(|value| select_module(&modules, value))
                .transpose()?;
            println!("DEPENDENCY_MODULE_CHANGE=status");
            println!("TOPIC={topic}");
            let report = if let Some(module) = selected {
                vec![module]
            } else {
                modules.iter().collect::<Vec<_>>()
            };
            for module in report {
                let name = module.basename()?;
                let clone = repository_topic_clone::projected_clone_path(root, &topic, &name)
                    .map_err(|error| format!("REPOSITORY_TOPIC_CLONE_ERROR={error}"))?;
                let state = if clone.exists() { "ready" } else { "absent" };
                println!("TOPIC_ROOT={}", clone.parent().unwrap_or(&clone).display());
                println!(
                    "MODULE={} STATE={} CLONE={}",
                    module.path,
                    state,
                    clone.display()
                );
            }
            Ok(0)
        }
        "cleanup" => {
            let options = parse_options(
                args,
                &[
                    "--topic",
                    "--module",
                    "--branch",
                    "--candidate-cas",
                    "--pr-lifecycle",
                    "--publication-readback",
                ],
                &["--apply"],
            )?;
            let topic = required(&options, "--topic")?;
            let module = required(&options, "--module")?;
            let branch = required(&options, "--branch")?;
            let request = request_from_args(root, &topic, &module, &branch)?;
            let proof = repository_topic_clone::cleanup(
                &request,
                options.values.get("--candidate-cas").map(Path::new),
                options.values.get("--pr-lifecycle").map(Path::new),
                options.values.get("--publication-readback").map(Path::new),
                options.flags.contains("--apply"),
            )
            .map_err(|error| format!("REPOSITORY_TOPIC_CLONE_ERROR={error}"))?;
            println!(
                "CLEANUP module={} topic={} action={} path={}",
                module,
                repository_topic_clone::topic_slug(&topic).map_err(|error| error.to_string())?,
                if proof.removed {
                    "removed"
                } else {
                    "would-remove"
                },
                proof.clone.display()
            );
            Ok(0)
        }
        _ => Err(format!("invalid command: {command}")),
    }
}

pub fn run(args: &[String]) -> i32 {
    if args.iter().any(|value| value == "--help" || value == "-h") {
        println!("{USAGE}");
        println!("  prepare|merge-main --topic TOPIC --module PATH --branch BRANCH");
        println!("  status --topic TOPIC [--module PATH]");
        println!("  cleanup --topic TOPIC --module PATH --branch BRANCH [--apply]");
        return 0;
    }
    let mut root = PathBuf::from(".");
    let mut command_index = None;
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--root" {
            index += 1;
            let Some(value) = args.get(index) else {
                eprintln!("DEPENDENCY_MODULE_CHANGE_ERROR=argument --root: expected one argument");
                return 2;
            };
            root = PathBuf::from(value);
        } else if let Some(value) = args[index].strip_prefix("--root=") {
            root = PathBuf::from(value);
        } else if matches!(
            args[index].as_str(),
            "prepare" | "merge-main" | "status" | "cleanup"
        ) {
            command_index = Some(index);
            break;
        } else {
            eprintln!("{USAGE}");
            eprintln!("error: unrecognized arguments: {}", args[index]);
            return 2;
        }
        index += 1;
    }
    let Some(command_index) = command_index else {
        eprintln!("{USAGE}");
        eprintln!("error: a command is required");
        return 2;
    };
    let command = args[command_index].as_str();
    let mut command_args = args[command_index + 1..].to_vec();
    if let Some(position) = command_args.iter().position(|value| value == "--root") {
        if let Some(value) = command_args.get(position + 1) {
            root = PathBuf::from(value);
            command_args.drain(position..=position + 1);
        }
    } else if let Some(position) = command_args
        .iter()
        .position(|value| value.starts_with("--root="))
    {
        if let Some(value) = command_args.get(position) {
            root = PathBuf::from(value.trim_start_matches("--root="));
            command_args.remove(position);
        }
    }
    let result = run_command(&root, command, &command_args);
    match result {
        Ok(code) => code,
        Err(error) => {
            if error.starts_with("REPOSITORY_TOPIC_CLONE_ERROR=") {
                eprintln!("{error}");
            } else {
                eprintln!("DEPENDENCY_MODULE_CHANGE_ERROR={error}");
            }
            2
        }
    }
}
