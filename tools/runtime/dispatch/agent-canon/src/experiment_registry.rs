// @dependency-start
// contract implementation
// responsibility Validates consumer experiment registry structure, paths, commands, refs, and eval artifacts.
// upstream design ../../../../../documents/experiments/experiment-registry.md defines the registry contract
// upstream implementation experiment_identity.rs owns safe topic and variant segments
// upstream implementation path_resolution.rs owns non-strict path resolution
// upstream implementation python_cli_options.rs owns argparse-compatible option prefixes
// downstream implementation main.rs exposes the native experiment-registry command
// downstream test ../tests/experiment_registry_native.rs preserves registry and CLI oracles
// @dependency-end

use crate::experiment_identity::validate_segment;
use crate::path_resolution::resolve_non_strict;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::python_text::python_strip;
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output};
use toml_edit::{DocumentMut, Item, TableLike, Value as TomlValue};

pub const SELECTOR: &str = "experiment-registry";
pub mod context;
pub mod create_experiment_topic;
pub(crate) mod store;
pub(crate) const CONTEXT_SELECTOR: &str = "sync-experiment-registry-context";
const MANAGED_RUN_ARTIFACTS: &[&str] = &[
    "run_manifest.json",
    "eval_manifest.json",
    "run.log",
    "artifact_manifest.json",
    "command.json",
    "config_source.yaml",
    "environment.json",
    "source_snapshot.json",
    "logs/startup.jsonl",
    "logs/stdout.log",
    "logs/stderr.log",
];

#[derive(Clone, Debug, Eq, PartialEq)]
struct Finding {
    level: &'static str,
    message: String,
}

#[derive(Clone, Debug)]
pub(crate) enum RegistryValue {
    String(String),
    Integer(i64),
    Float(f64),
    Boolean(bool),
    Array(Vec<RegistryValue>),
    Table(Vec<(String, RegistryValue)>),
    Other(String),
}

#[derive(Clone, Copy)]
enum OptionKind {
    RepoRoot,
    Registry,
}

enum ParsedArgs {
    Help,
    Values {
        repo_root: Option<PathBuf>,
        registry: Option<PathBuf>,
    },
}

/// Validate one consumer registry and return findings in declaration order.
fn collect_findings(repo_root: &Path, registry_path: &Path) -> Result<Vec<Finding>, String> {
    if !registry_path.is_file() {
        return Ok(vec![Finding {
            level: "error",
            message: format!("registry file is missing: {}", registry_path.display()),
        }]);
    }
    let text = fs::read_to_string(registry_path)
        .map_err(|error| format!("{}: {error}", registry_path.display()))?;
    let registry = parse_registry(&text).map_err(|error| error.to_string())?;
    let registry_table = table(&registry).ok_or_else(|| "registry must be a table".to_owned())?;
    let mut findings = Vec::new();

    let schema_version = table_get(registry_table, "schema_version");
    if !schema_version_is_one(schema_version) {
        findings.push(Finding {
            level: "error",
            message: format!(
                "schema_version must be 1, got {}",
                schema_version
                    .map(python_repr)
                    .unwrap_or_else(|| "None".to_owned())
            ),
        });
    }

    let empty_defaults = Vec::new();
    let defaults = match table_get(registry_table, "defaults") {
        None => &empty_defaults,
        Some(RegistryValue::Table(defaults)) => defaults,
        Some(_) => {
            findings.push(Finding {
                level: "error",
                message: "defaults must be a table".to_owned(),
            });
            &empty_defaults
        }
    };

    if let Some(managed_runner) = string_value(table_get(defaults, "managed_runner")) {
        let managed_runner_path = repo_root.join(managed_runner);
        if !managed_runner_path.is_file() {
            findings.push(Finding {
                level: "error",
                message: format!(
                    "defaults.managed_runner is missing: {}",
                    managed_runner_path.display()
                ),
            });
        }
    } else {
        findings.push(Finding {
            level: "error",
            message: "defaults.managed_runner must be a string".to_owned(),
        });
    }

    if let Some(topic_template_dir) = string_value(table_get(defaults, "topic_template_dir")) {
        let resolved_template_dir = repo_root.join(topic_template_dir);
        if !resolved_template_dir.is_dir() {
            findings.push(Finding {
                level: "error",
                message: format!(
                    "defaults.topic_template_dir is missing: {}",
                    resolved_template_dir.display()
                ),
            });
        }
    }

    validate_eval_artifact_lists(&mut findings, "defaults", defaults);

    let topics = normalize_topics(table_get(registry_table, "topics"), "topics")?;
    let branch_topics =
        normalize_topics(table_get(registry_table, "branch_topics"), "branch_topics")?;
    let mut seen_names = BTreeSet::new();
    for topic in topics {
        if let Some(name) = string_value(table_get(topic, "name")) {
            if !seen_names.insert(name.to_owned()) {
                findings.push(Finding {
                    level: "error",
                    message: format!("duplicate topic name: {name}"),
                });
            }
        }
        validate_topic(repo_root, defaults, topic, &mut findings)?;
    }
    for topic in branch_topics {
        if let Some(name) = string_value(table_get(topic, "name")) {
            if !seen_names.insert(name.to_owned()) {
                findings.push(Finding {
                    level: "error",
                    message: format!("duplicate topic name: {name}"),
                });
            }
        }
        validate_branch_topic(repo_root, topic, &mut findings)?;
    }
    Ok(findings)
}

/// Run `agent-canon experiment-registry`.
pub fn run(args: &[String]) -> i32 {
    let parsed = match parse_args(args) {
        Ok(parsed) => parsed,
        Err(error) => {
            print_usage();
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let ParsedArgs::Values {
        repo_root: requested_root,
        registry: requested_registry,
    } = parsed
    else {
        print_help();
        return 0;
    };

    let repo_root = match requested_root {
        Some(path) => resolve_non_strict(&path),
        None => default_repo_root(),
    };
    let repo_root = match repo_root {
        Ok(path) => path,
        Err(error) => {
            eprintln!("{error}");
            return 2;
        }
    };
    let registry_path = match requested_registry {
        Some(path) => resolve_non_strict(&path),
        None => Ok(repo_root.join("experiments/registry.toml")),
    };
    let registry_path = match registry_path {
        Ok(path) => path,
        Err(error) => {
            eprintln!("{error}");
            return 2;
        }
    };
    let findings = match collect_findings(&repo_root, &registry_path) {
        Ok(findings) => findings,
        Err(error) => {
            eprintln!("{error}");
            return 2;
        }
    };

    println!("repo_root={}", repo_root.display());
    println!("registry_path={}", registry_path.display());
    for finding in &findings {
        println!(
            "{}: {}",
            finding.level.to_ascii_uppercase(),
            finding.message
        );
    }
    if findings.iter().any(|finding| finding.level == "error") {
        return 1;
    }
    println!("OK: experiment registry is valid");
    0
}

fn parse_args(args: &[String]) -> Result<ParsedArgs, String> {
    let mut repo_root = None;
    let mut registry = None;
    let options = [
        ("--repo-root", OptionKind::RepoRoot),
        ("--registry", OptionKind::Registry),
    ];
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if matches!(token.as_str(), "-h" | "--help") {
            return Ok(ParsedArgs::Help);
        }
        let (name, inline_value) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(name, value)| (name, Some(value)));
        let option = resolve_long_option_prefix(name, &options).map_err(|error| match error {
            LongOptionError::Unrecognized => format!("unrecognized argument: {token}"),
            LongOptionError::Ambiguous(matches) => format!(
                "ambiguous option: {name} could match {}",
                matches.join(", ")
            ),
        })?;
        let value = if let Some(value) = inline_value {
            value.to_owned()
        } else {
            index += 1;
            args.get(index)
                .cloned()
                .ok_or_else(|| format!("argument {name}: expected one value"))?
        };
        match option {
            OptionKind::RepoRoot => repo_root = Some(PathBuf::from(value)),
            OptionKind::Registry => registry = Some(PathBuf::from(value)),
        }
        index += 1;
    }
    Ok(ParsedArgs::Values {
        repo_root,
        registry,
    })
}

fn print_usage() {
    eprintln!("usage: agent-canon {SELECTOR} [--repo-root PATH] [--registry PATH]");
}

fn print_help() {
    println!(
        "Validate an experiment registry.\n\n\
         usage: agent-canon {SELECTOR} [--repo-root PATH] [--registry PATH]\n\n\
         options:\n\
         -h, --help       Print help and exit\n\
         --repo-root PATH\n\
         --registry PATH  Optional registry path; defaults to <repo-root>/experiments/registry.toml"
    );
}

fn default_repo_root() -> Result<PathBuf, String> {
    let current_dir = env::current_dir().map_err(|error| format!("current directory: {error}"))?;
    if let Some(root) = extract_git_root(run_git_root_lookup(&current_dir)?) {
        return resolve_non_strict(&root);
    }
    resolve_non_strict(&source_root())
}

fn source_root() -> PathBuf {
    if let Some(value) = env::var_os("AGENT_CANON_SOURCE_ROOT") {
        let value = PathBuf::from(value);
        if !value.as_os_str().is_empty() {
            return value;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")))
        .to_path_buf()
}

fn run_git_root_lookup(cwd: &Path) -> Result<Output, String> {
    Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(cwd)
        .output()
        .map_err(|error| format!("git root lookup failed: {error}"))
}

fn extract_git_root(output: Output) -> Option<PathBuf> {
    if !output.status.success() {
        return None;
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let root = python_strip(&stdout);
    (!root.is_empty()).then(|| PathBuf::from(root))
}

pub(crate) fn parse_registry(text: &str) -> Result<RegistryValue, String> {
    let document = text
        .parse::<DocumentMut>()
        .map_err(|error| error.to_string())?;
    Ok(table_value(document.as_table()))
}

fn table_value(table: &dyn TableLike) -> RegistryValue {
    RegistryValue::Table(
        table
            .iter()
            .map(|(name, item)| (name.to_owned(), item_value(item)))
            .collect(),
    )
}

fn item_value(item: &Item) -> RegistryValue {
    if let Some(tables) = item.as_array_of_tables() {
        return RegistryValue::Array(
            tables
                .iter()
                .map(|table| table_value(table as &dyn TableLike))
                .collect(),
        );
    }
    if let Some(table) = item.as_table_like() {
        return table_value(table);
    }
    if let Some(array) = item.as_array() {
        return RegistryValue::Array(array.iter().map(toml_value).collect());
    }
    item.as_value()
        .map(toml_value)
        .unwrap_or_else(|| RegistryValue::Other(item.to_string()))
}

fn toml_value(value: &TomlValue) -> RegistryValue {
    if let Some(table) = value.as_inline_table() {
        return table_value(table);
    }
    if let Some(array) = value.as_array() {
        return RegistryValue::Array(array.iter().map(toml_value).collect());
    }
    if let Some(value) = value.as_str() {
        return RegistryValue::String(value.to_owned());
    }
    if let Some(value) = value.as_integer() {
        return RegistryValue::Integer(value);
    }
    if let Some(value) = value.as_float() {
        return RegistryValue::Float(value);
    }
    if let Some(value) = value.as_bool() {
        return RegistryValue::Boolean(value);
    }
    RegistryValue::Other(value.to_string())
}

fn table(value: &RegistryValue) -> Option<&[(String, RegistryValue)]> {
    match value {
        RegistryValue::Table(values) => Some(values),
        _ => None,
    }
}

fn table_get<'a>(table: &'a [(String, RegistryValue)], key: &str) -> Option<&'a RegistryValue> {
    table
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, value)| value)
}

fn string_value(value: Option<&RegistryValue>) -> Option<&str> {
    match value {
        Some(RegistryValue::String(value)) => Some(value),
        _ => None,
    }
}

fn require_string<'a>(table: &'a [(String, RegistryValue)], key: &str) -> Option<&'a str> {
    string_value(table_get(table, key)).filter(|value| !python_strip(value).is_empty())
}

fn maybe_string(table: &[(String, RegistryValue)], key: &str) -> Option<String> {
    string_value(table_get(table, key))
        .map(python_strip)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
}

fn schema_version_is_one(value: Option<&RegistryValue>) -> bool {
    match value {
        Some(RegistryValue::Integer(value)) => *value == 1,
        Some(RegistryValue::Float(value)) => *value == 1.0,
        Some(RegistryValue::Boolean(value)) => *value,
        _ => false,
    }
}

fn python_repr(value: &RegistryValue) -> String {
    match value {
        RegistryValue::String(value) => python_string_repr(value),
        RegistryValue::Integer(value) => value.to_string(),
        RegistryValue::Float(value) => {
            if value.is_nan() {
                return "nan".to_owned();
            }
            if value.is_infinite() {
                return if value.is_sign_negative() {
                    "-inf".to_owned()
                } else {
                    "inf".to_owned()
                };
            }
            let rendered = value.to_string();
            if !rendered.contains('.') && !rendered.contains('e') && !rendered.contains('E') {
                format!("{rendered}.0")
            } else {
                rendered
            }
        }
        RegistryValue::Boolean(true) => "True".to_owned(),
        RegistryValue::Boolean(false) => "False".to_owned(),
        RegistryValue::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(python_repr)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        RegistryValue::Table(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| format!("{}: {}", python_string_repr(key), python_repr(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        RegistryValue::Other(value) => value.clone(),
    }
}

fn python_string_repr(value: &str) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut rendered = String::from(quote);
    for character in value.chars() {
        match character {
            '\\' => rendered.push_str("\\\\"),
            '\n' => rendered.push_str("\\n"),
            '\r' => rendered.push_str("\\r"),
            '\t' => rendered.push_str("\\t"),
            value if value == quote => {
                rendered.push('\\');
                rendered.push(value);
            }
            value if value.is_control() => rendered.push_str(&format!("\\x{:02x}", value as u32)),
            value => rendered.push(value),
        }
    }
    rendered.push(quote);
    rendered
}

fn normalize_topics<'a>(
    value: Option<&'a RegistryValue>,
    table_name: &str,
) -> Result<Vec<&'a [(String, RegistryValue)]>, String> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let RegistryValue::Array(values) = value else {
        return Err(if table_name == "topics" {
            "registry must contain [[topics]]".to_owned()
        } else {
            "registry branch_topics must be an array of tables".to_owned()
        });
    };
    values
        .iter()
        .enumerate()
        .map(|(index, value)| {
            table(value).ok_or_else(|| format!("{table_name}[{index}] must be a table"))
        })
        .collect()
}

fn required_field_finding(topic_name: &str, key: &str) -> Finding {
    Finding {
        level: "error",
        message: format!("{topic_name}: missing required string field: {key}"),
    }
}

fn required_topic_values(topic: &[(String, RegistryValue)]) -> Vec<(&'static str, Option<String>)> {
    [
        "status",
        "topic_dir",
        "topic_readme",
        "canonical_entrypoint",
        "result_root",
        "report_root",
        "default_variant",
    ]
    .into_iter()
    .map(|key| (key, require_string(topic, key).map(str::to_owned)))
    .collect()
}

fn append_missing_required_field_findings(
    findings: &mut Vec<Finding>,
    topic_name: &str,
    values: &[(&'static str, Option<String>)],
) {
    for (key, value) in values {
        if value.is_none() {
            findings.push(required_field_finding(topic_name, key));
        }
    }
}

fn complete_required_values(
    values: &[(&'static str, Option<String>)],
) -> Option<Vec<(&'static str, String)>> {
    if values.iter().any(|(_, value)| value.is_none()) {
        return None;
    }
    Some(
        values
            .iter()
            .map(|(key, value)| (*key, value.clone().expect("checked required value")))
            .collect(),
    )
}

fn required_value<'a>(values: &'a [(&'static str, String)], key: &str) -> &'a str {
    values
        .iter()
        .find(|(name, _)| *name == key)
        .map(|(_, value)| value.as_str())
        .expect("required topic field is present")
}

fn normalize_string_list(value: Option<&RegistryValue>) -> Vec<String> {
    let Some(RegistryValue::Array(values)) = value else {
        return Vec::new();
    };
    values
        .iter()
        .filter_map(|value| string_value(Some(value)))
        .map(python_strip)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect()
}

fn optional_string_list_findings(
    scope_name: &str,
    key: &str,
    value: Option<&RegistryValue>,
) -> Vec<Finding> {
    let Some(value) = value else {
        return Vec::new();
    };
    let RegistryValue::Array(values) = value else {
        return vec![Finding {
            level: "error",
            message: format!("{scope_name}: {key} must be an array of strings"),
        }];
    };
    values
        .iter()
        .enumerate()
        .filter(|(_, value)| {
            string_value(Some(value))
                .filter(|value| !python_strip(value).is_empty())
                .is_none()
        })
        .map(|(index, _)| Finding {
            level: "error",
            message: format!("{scope_name}: {key}[{index}] must be a non-empty string"),
        })
        .collect()
}

fn validate_eval_patterns(
    findings: &mut Vec<Finding>,
    scope_name: &str,
    key: &str,
    patterns: &[String],
) {
    for pattern in patterns {
        let path = Path::new(pattern);
        if path.is_absolute() {
            findings.push(Finding {
                level: "error",
                message: format!(
                    "{scope_name}: {key} must stay relative to result/<run_name>: {pattern}"
                ),
            });
        }
        if path
            .components()
            .any(|component| component == Component::ParentDir)
        {
            findings.push(Finding {
                level: "error",
                message: format!(
                    "{scope_name}: {key} must not escape result/<run_name>: {pattern}"
                ),
            });
        }
        if MANAGED_RUN_ARTIFACTS.contains(&pattern.as_str()) {
            findings.push(Finding {
                level: "error",
                message: format!(
                    "{scope_name}: {key} must not target reserved managed artifacts: {pattern}"
                ),
            });
        }
    }
}

fn validate_eval_artifact_lists(
    findings: &mut Vec<Finding>,
    scope_name: &str,
    table_value: &[(String, RegistryValue)],
) {
    let required_raw = table_get(table_value, "required_eval_artifacts");
    findings.extend(optional_string_list_findings(
        scope_name,
        "required_eval_artifacts",
        required_raw,
    ));
    let required = normalize_string_list(required_raw);
    let optional_raw = table_get(table_value, "optional_eval_artifacts");
    findings.extend(optional_string_list_findings(
        scope_name,
        "optional_eval_artifacts",
        optional_raw,
    ));
    let optional = normalize_string_list(optional_raw);
    validate_eval_patterns(findings, scope_name, "required_eval_artifacts", &required);
    validate_eval_patterns(findings, scope_name, "optional_eval_artifacts", &optional);
}

fn validate_topic_layout(
    repo_root: &Path,
    defaults: &[(String, RegistryValue)],
    topic_name: &str,
    fields: &[(&'static str, String)],
    findings: &mut Vec<Finding>,
) {
    let status = required_value(fields, "status");
    let topic_dir_raw = required_value(fields, "topic_dir");
    let readme_raw = required_value(fields, "topic_readme");
    let entrypoint_raw = required_value(fields, "canonical_entrypoint");
    let result_root_raw = required_value(fields, "result_root");
    let report_root_raw = required_value(fields, "report_root");
    for (field, value) in [
        ("topic", topic_name),
        ("default_variant", required_value(fields, "default_variant")),
    ] {
        if let Err(error) = validate_segment(value, field) {
            findings.push(Finding {
                level: "error",
                message: format!("{topic_name}: {error}"),
            });
        }
    }
    if !["template", "draft", "active", "paused", "archived"].contains(&status) {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: unsupported status {}; expected one of ['active', 'archived', 'draft', 'paused', 'template']",
                python_string_repr(status)
            ),
        });
    }

    let topic_dir = repo_root.join(topic_dir_raw);
    let topic_readme = repo_root.join(readme_raw);
    let result_root = repo_root.join(result_root_raw);
    let report_root = repo_root.join(report_root_raw);
    let topic_template_dir = string_value(table_get(defaults, "topic_template_dir"));
    let expected_topic_dir_raw = if topic_name == "_template" {
        topic_template_dir
            .unwrap_or("experiments/_template")
            .to_owned()
    } else {
        format!("experiments/{topic_name}")
    };
    let expected_topic_dir = repo_root.join(&expected_topic_dir_raw);
    let expected_entrypoint_raw = format!("{expected_topic_dir_raw}/run.py");
    let expected_config_raw = format!("{expected_topic_dir_raw}/config.yaml");
    let expected_result_root_raw = format!("{expected_topic_dir_raw}/result");
    let expected_report_root_raw = format!("{expected_topic_dir_raw}/report");
    let expected_entrypoint = repo_root.join(&expected_entrypoint_raw);
    let expected_config = repo_root.join(&expected_config_raw);

    if topic_dir != expected_topic_dir {
        findings.push(Finding {
            level: "warning",
            message: format!(
                "{topic_name}: topic_dir is {topic_dir_raw}, expected {expected_topic_dir_raw} for the default layout"
            ),
        });
    }
    if entrypoint_raw != expected_entrypoint_raw {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: canonical_entrypoint must be the topic-local run.py ({expected_entrypoint_raw}), got {entrypoint_raw}"
            ),
        });
    }
    if result_root_raw != expected_result_root_raw {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: result_root must be {expected_result_root_raw} (run names are appended by the lifecycle owner; variant is metadata), got {result_root_raw}"
            ),
        });
    }
    if report_root_raw != expected_report_root_raw {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: report_root must be {expected_report_root_raw} (the run name is appended directly), got {report_root_raw}"
            ),
        });
    }
    if !topic_dir.is_dir() {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: topic_dir is missing: {}",
                topic_dir.display()
            ),
        });
    }
    if !topic_readme.is_file() {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: topic_readme is missing: {}",
                topic_readme.display()
            ),
        });
    }
    if !expected_entrypoint.is_file() {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: canonical_entrypoint is missing: {}",
                expected_entrypoint.display()
            ),
        });
    }
    if !expected_config.is_file() {
        findings.push(Finding {
            level: "error",
            message: format!("{topic_name}: topic config is missing: {expected_config_raw}"),
        });
    }
    if !result_root.is_dir() {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: result_root is missing: {}",
                result_root.display()
            ),
        });
    }
    if !report_root.is_dir() {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: report_root is missing: {}",
                report_root.display()
            ),
        });
    }
}

fn validate_topic_commands(
    defaults: &[(String, RegistryValue)],
    topic_name: &str,
    topic: &[(String, RegistryValue)],
    entrypoint_raw: &str,
    default_command: &str,
    findings: &mut Vec<Finding>,
) {
    let managed_runner = string_value(table_get(defaults, "managed_runner"));
    let mut registered_commands = vec![("default", default_command.to_owned())];
    if let Some(formal_command) = maybe_string(topic, "formal_inner_command") {
        registered_commands.push(("formal", formal_command));
    }
    for (command_kind, command_text) in registered_commands {
        if !command_text.contains(entrypoint_raw) {
            findings.push(Finding {
                level: "error",
                message: format!(
                    "{topic_name}: {command_kind}_inner_command must mention canonical_entrypoint {entrypoint_raw}"
                ),
            });
        }
        if !command_text.contains("{config_path}") {
            findings.push(Finding {
                level: "error",
                message: format!(
                    "{topic_name}: {command_kind}_inner_command must include {{config_path}} so managed runs consume the saved config snapshot"
                ),
            });
        }
        let managed_runner_module =
            managed_runner
                .filter(|runner| runner.ends_with(".py"))
                .map(|runner| {
                    runner
                        .strip_suffix(".py")
                        .unwrap_or(runner)
                        .replace('/', ".")
                });
        if command_text.contains("run-managed-experiment")
            || managed_runner.is_some_and(|runner| command_text.contains(runner))
            || managed_runner_module
                .as_ref()
                .is_some_and(|runner| command_text.contains(runner))
        {
            findings.push(Finding {
                level: "error",
                message: format!(
                    "{topic_name}: {command_kind}_inner_command must not call the managed runner recursively"
                ),
            });
        }
    }
}

fn registered_command_value(
    topic: &[(String, RegistryValue)],
    command_kind: &str,
) -> Option<String> {
    let key = format!("{command_kind}_inner_command");
    maybe_string(topic, &key).or_else(|| {
        (command_kind == "default")
            .then(|| maybe_string(topic, "smoke_inner_command"))
            .flatten()
    })
}

fn registered_command_finding(topic_name: &str, command_kind: &str) -> Finding {
    Finding {
        level: "error",
        message: format!("{topic_name}: missing registered command field for {command_kind}"),
    }
}

fn validate_topic_variant(
    topic_name: &str,
    topic: &[(String, RegistryValue)],
    default_variant: &str,
    findings: &mut Vec<Finding>,
) {
    let formal_command = maybe_string(topic, "formal_inner_command");
    if let Err(error) = validate_segment(default_variant, "default_variant") {
        findings.push(Finding {
            level: "error",
            message: format!("{topic_name}: {error}"),
        });
    }
    if default_variant == "formal" && formal_command.is_none() {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: default_variant is formal but formal_inner_command is missing"
            ),
        });
    }
}

fn git_output(repo_root: &Path, args: &[&str]) -> Result<Output, String> {
    Command::new("git")
        .args(args)
        .current_dir(repo_root)
        .output()
        .map_err(|error| format!("git {} failed: {error}", args.join(" ")))
}

fn git_branch_exists(repo_root: &Path, branch_name: &str) -> Result<bool, String> {
    let output = git_output(repo_root, &["branch", "--list", branch_name])?;
    Ok(!python_strip(&String::from_utf8_lossy(&output.stdout)).is_empty())
}

fn git_ref_exists(repo_root: &Path, ref_name: &str) -> Result<bool, String> {
    let candidates = [
        ref_name.to_owned(),
        format!("refs/heads/{ref_name}"),
        format!("refs/remotes/{ref_name}"),
    ];
    for candidate in candidates {
        let status = Command::new("git")
            .arg("show-ref")
            .arg("--verify")
            .arg("--quiet")
            .arg(&candidate)
            .current_dir(repo_root)
            .status()
            .map_err(|error| format!("git show-ref failed: {error}"))?;
        if status.success() {
            return Ok(true);
        }
    }
    Ok(false)
}

fn git_commit_exists(repo_root: &Path, commit: &str) -> Result<bool, String> {
    let spec = format!("{commit}^{{commit}}");
    let status = Command::new("git")
        .arg("cat-file")
        .arg("-e")
        .arg(&spec)
        .current_dir(repo_root)
        .status()
        .map_err(|error| format!("git cat-file failed: {error}"))?;
    Ok(status.success())
}

fn validate_topic_references(
    repo_root: &Path,
    topic_name: &str,
    topic: &[(String, RegistryValue)],
    findings: &mut Vec<Finding>,
) -> Result<(), String> {
    if let Some(active_branch) = maybe_string(topic, "active_branch") {
        if !git_branch_exists(repo_root, &active_branch)? {
            findings.push(Finding {
                level: "warning",
                message: format!(
                    "{topic_name}: active_branch does not exist in the current repo: {active_branch}"
                ),
            });
        }
    }
    for key in [
        "active_worktree",
        "scope_file",
        "branch_note",
        "primary_note",
    ] {
        let Some(optional_path) = maybe_string(topic, key) else {
            continue;
        };
        let resolved = repo_root.join(optional_path);
        if !resolved.exists() {
            findings.push(Finding {
                level: "warning",
                message: format!(
                    "{topic_name}: {key} is set but missing: {}",
                    resolved.display()
                ),
            });
        }
    }
    Ok(())
}

fn validate_topic_eval_artifacts(
    topic_name: &str,
    topic: &[(String, RegistryValue)],
    findings: &mut Vec<Finding>,
) {
    validate_eval_artifact_lists(findings, topic_name, topic);
}

fn validate_topic(
    repo_root: &Path,
    defaults: &[(String, RegistryValue)],
    topic: &[(String, RegistryValue)],
    findings: &mut Vec<Finding>,
) -> Result<(), String> {
    let Some(topic_name) = require_string(topic, "name") else {
        findings.push(required_field_finding("<unknown>", "name"));
        return Ok(());
    };
    let required_values = required_topic_values(topic);
    append_missing_required_field_findings(findings, topic_name, &required_values);
    let default_command = registered_command_value(topic, "default");
    if default_command.is_none() {
        findings.push(registered_command_finding(topic_name, "default"));
    }
    let Some(complete_values) = complete_required_values(&required_values) else {
        return Ok(());
    };
    let Some(default_command) = default_command else {
        return Ok(());
    };

    validate_topic_layout(repo_root, defaults, topic_name, &complete_values, findings);
    validate_topic_commands(
        defaults,
        topic_name,
        topic,
        required_value(&complete_values, "canonical_entrypoint"),
        &default_command,
        findings,
    );
    validate_topic_variant(
        topic_name,
        topic,
        required_value(&complete_values, "default_variant"),
        findings,
    );
    validate_topic_references(repo_root, topic_name, topic, findings)?;
    validate_topic_eval_artifacts(topic_name, topic, findings);
    Ok(())
}

fn validate_branch_topic(
    repo_root: &Path,
    topic: &[(String, RegistryValue)],
    findings: &mut Vec<Finding>,
) -> Result<(), String> {
    let Some(topic_name) = require_string(topic, "name") else {
        findings.push(required_field_finding("<unknown>", "name"));
        return Ok(());
    };
    let required_values = ["status", "remote_branch", "primary_note"]
        .into_iter()
        .map(|key| (key, require_string(topic, key).map(str::to_owned)))
        .collect::<Vec<_>>();
    append_missing_required_field_findings(findings, topic_name, &required_values);
    let Some(complete_values) = complete_required_values(&required_values) else {
        return Ok(());
    };
    let status = required_value(&complete_values, "status");
    let remote_branch = required_value(&complete_values, "remote_branch");
    let primary_note = required_value(&complete_values, "primary_note");
    if !["active", "paused", "archived"].contains(&status) {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: unsupported branch topic status {}; expected one of ['active', 'archived', 'paused']",
                python_string_repr(status)
            ),
        });
    }
    if !git_ref_exists(repo_root, remote_branch)? {
        findings.push(Finding {
            level: "warning",
            message: format!(
                "{topic_name}: remote_branch does not exist in the current repo: {remote_branch}"
            ),
        });
    }
    let primary_note_path = repo_root.join(primary_note);
    if !primary_note_path.is_file() {
        findings.push(Finding {
            level: "error",
            message: format!(
                "{topic_name}: primary_note is missing: {}",
                primary_note_path.display()
            ),
        });
    }
    if let Some(branch_note) = maybe_string(topic, "branch_note") {
        let branch_note_path = repo_root.join(&branch_note);
        if !branch_note_path.is_file() {
            findings.push(Finding {
                level: "warning",
                message: format!(
                    "{topic_name}: branch_note is set but missing: {}",
                    branch_note_path.display()
                ),
            });
        }
    }
    if let Some(source_commit) = maybe_string(topic, "source_commit") {
        if !git_commit_exists(repo_root, &source_commit)? {
            findings.push(Finding {
                level: "warning",
                message: format!(
                    "{topic_name}: source_commit does not exist in the current repo: {source_commit}"
                ),
            });
        }
    }
    Ok(())
}
