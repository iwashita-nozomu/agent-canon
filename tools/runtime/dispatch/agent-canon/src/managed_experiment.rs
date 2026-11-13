// @dependency-start
// contract implementation
// responsibility Owns managed experiment setup, source/config snapshots, external admitted-runner invocation, and result manifests.
// upstream implementation experiment_identity.rs owns canonical topic/variant/run identity
// upstream implementation experiment_registry/store.rs owns registry loading
// upstream implementation execution_resource_plan.rs owns native NVIDIA admission and source freeze evidence
// upstream implementation runtime_boundary.rs owns handle-relative artifact writes
// downstream implementation main.rs exposes run-managed-experiment
// @dependency-end

use crate::experiment_identity::ExperimentIdentity;
use crate::experiment_registry::{store, RegistryValue};
use crate::python_json::{self, JsonObject, JsonString, JsonValue};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

type Result<T> = std::result::Result<T, String>;
pub const SELECTOR: &str = "run-managed-experiment";
#[derive(Default)]
struct Options {
    repo_root: Option<PathBuf>,
    topic: Option<String>,
    variant: Option<String>,
    run_name: Option<String>,
    registry: Option<PathBuf>,
    registered: Option<String>,
    report: Option<PathBuf>,
    skip_report: bool,
    config_json: Option<PathBuf>,
    config: Vec<String>,
    command: Vec<String>,
}
enum ParsedOptions {
    Help,
    Run(Box<Options>),
}
fn parse_options(args: &[String]) -> Result<ParsedOptions> {
    let options = [
        ("--repo-root", 0),
        ("--topic", 1),
        ("--run-name", 2),
        ("--variant", 3),
        ("--registry", 4),
        ("--use-registered-command", 5),
        ("--report-path", 6),
        ("--skip-report-init", 7),
        ("--config-json", 8),
        ("--config", 9),
        ("--help", 10),
    ];
    let mut result = Options::default();
    let mut index = 0;
    while index < args.len() {
        let raw = &args[index];
        if raw == "--" {
            result.command = args[index + 1..].into();
            break;
        }
        if !raw.starts_with('-') {
            result.command = args[index..].into();
            break;
        }
        if raw == "-h" {
            return Ok(ParsedOptions::Help);
        }
        let (option, inline) = raw
            .split_once('=')
            .map_or((raw.as_str(), None), |(name, value)| (name, Some(value)));
        let key = crate::python_cli_options::resolve_long_option_prefix(option, &options)
            .map_err(|_| format!("unrecognized or ambiguous argument: {raw}"))?;
        if key == 10 {
            return Ok(ParsedOptions::Help);
        }
        if key == 7 {
            if inline.is_some() {
                return Err(format!("argument {option}: ignored explicit argument"));
            }
            result.skip_report = true;
            index += 1;
            continue;
        }
        let value = match inline {
            Some(value) => value.to_owned(),
            None => {
                index += 1;
                args.get(index)
                    .cloned()
                    .ok_or_else(|| format!("argument {option}: expected one argument"))?
            }
        };
        match key {
            0 => result.repo_root = Some(value.into()),
            1 => result.topic = Some(value),
            2 => result.run_name = Some(value),
            3 => result.variant = Some(value),
            4 => {
                if !value.is_empty() {
                    result.registry = Some(value.into());
                }
            }
            5 => {
                if !value.is_empty() {
                    result.registered = Some(value);
                }
            }
            6 => {
                if !value.is_empty() {
                    result.report = Some(value.into());
                }
            }
            8 => {
                if !value.is_empty() {
                    result.config_json = Some(value.into());
                }
            }
            9 => result.config.push(value),
            _ => unreachable!(),
        }
        index += 1;
    }
    if result.topic.is_none() || result.variant.is_none() {
        return Err("the following arguments are required: --topic, --variant".into());
    }
    Ok(ParsedOptions::Run(Box::new(result)))
}
#[derive(Clone)]
struct RegistryContext {
    path: PathBuf,
    entry: RegistryValue,
    defaults: RegistryValue,
    available: bool,
}
#[derive(Clone)]
struct RunPaths {
    result: PathBuf,
    raw: PathBuf,
    logs: PathBuf,
    report: PathBuf,
    manifest: PathBuf,
    eval: PathBuf,
    artifacts: PathBuf,
    command: PathBuf,
    environment: PathBuf,
    snapshot: PathBuf,
    source_config: PathBuf,
    config: PathBuf,
    run_log: PathBuf,
    startup: PathBuf,
    stdout: PathBuf,
    stderr: PathBuf,
}
#[derive(Clone)]
struct RunContext {
    root: PathBuf,
    identity: ExperimentIdentity,
    topic: PathBuf,
    paths: RunPaths,
    registry: RegistryContext,
    command: Vec<String>,
    command_source: String,
    registered_match: Option<String>,
    created: String,
    branch: Option<String>,
    commit: Option<String>,
    status: Vec<String>,
}
fn registry_text<'a>(value: &'a RegistryValue, key: &str) -> Option<&'a str> {
    match store::get(value, key) {
        Some(RegistryValue::String(value)) => Some(value),
        _ => None,
    }
}
fn registry_truthy(value: &RegistryValue) -> bool {
    match value {
        RegistryValue::String(value) => !value.is_empty(),
        RegistryValue::Integer(value) => *value != 0,
        RegistryValue::Float(value) => *value != 0.0,
        RegistryValue::Boolean(value) => *value,
        RegistryValue::Array(value) => !value.is_empty(),
        RegistryValue::Table(value) => !value.is_empty(),
        RegistryValue::Other(_) => true,
    }
}
fn load_registry(path: PathBuf, topic: &str) -> Result<RegistryContext> {
    if !path.is_file() {
        return Ok(RegistryContext {
            path,
            entry: RegistryValue::Table(Vec::new()),
            defaults: RegistryValue::Table(Vec::new()),
            available: false,
        });
    }
    let registry = store::load(&path)?;
    let topics = match store::get(&registry, "topics") {
        None => &[][..],
        Some(RegistryValue::Array(values)) => values.as_slice(),
        _ => return Err("experiment registry must contain [[topics]]".into()),
    };
    let entry = topics
        .iter()
        .find(|value| registry_text(value, "name") == Some(topic))
        .cloned()
        .ok_or_else(|| format!("topic {topic:?} is missing from {}", path.display()))?;
    let defaults = store::get(&registry, "defaults")
        .cloned()
        .unwrap_or_else(|| RegistryValue::Table(Vec::new()));
    if !matches!(defaults, RegistryValue::Table(_)) {
        return Err("experiment registry defaults must be a table".into());
    }
    Ok(RegistryContext {
        path,
        entry,
        defaults,
        available: true,
    })
}
fn utc_now() -> Result<String> {
    let now = time::OffsetDateTime::now_utc()
        .replace_nanosecond(0)
        .map_err(|error| error.to_string())?;
    now.format(&time::format_description::well_known::Rfc3339)
        .map_err(|error| error.to_string())
}
fn compact_timestamp() -> String {
    let now = time::OffsetDateTime::now_utc();
    format!(
        "{:04}{:02}{:02}T{:02}{:02}{:02}Z",
        now.year(),
        now.month() as u8,
        now.day(),
        now.hour(),
        now.minute(),
        now.second()
    )
}
fn contained(root: &Path, path: &Path) -> Result<PathBuf> {
    let path = crate::path_resolution::resolve_non_strict(path)?;
    if !path.starts_with(root) {
        return Err(format!(
            "path must be inside repository root: {}",
            path.display()
        ));
    }
    Ok(path)
}
fn git_value(root: &Path, args: &[&str]) -> Option<String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8(output.stdout).ok()?;
    let text = crate::python_text::python_strip(&text);
    if text.is_empty() {
        None
    } else {
        Some(text.into())
    }
}
fn format_tokens(command: Value, placeholders: &BTreeMap<String, String>) -> Result<Vec<String>> {
    let input = serde_json::to_vec(&json!({"command":command,"placeholders":placeholders}))
        .map_err(|error| error.to_string())?;
    let output = crate::reference_materializer::provider("format-command", &input)?;
    output
        .get("command")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            output
                .get("error")
                .and_then(Value::as_str)
                .unwrap_or("command formatting provider returned no argv")
                .to_owned()
        })?
        .iter()
        .map(|value| {
            value
                .as_str()
                .map(str::to_owned)
                .ok_or_else(|| "command formatting provider returned a non-string token".into())
        })
        .collect()
}
fn registered_command(
    entry: &RegistryValue,
    kind: &str,
    placeholders: &BTreeMap<String, String>,
) -> Result<Vec<String>> {
    let key = format!("{kind}_inner_command");
    let raw = registry_text(entry, &key)
        .filter(|value| !value.trim().is_empty())
        .or_else(|| {
            if kind == "default" {
                registry_text(entry, "smoke_inner_command").filter(|value| !value.trim().is_empty())
            } else {
                None
            }
        })
        .ok_or_else(|| format!("registry entry is missing one of {key}"))?;
    format_tokens(json!(raw), placeholders)
}
fn build_context(options: &Options) -> Result<RunContext> {
    let root = match &options.repo_root {
        Some(path) => crate::path_resolution::resolve_non_strict(path)?,
        None => {
            crate::agent_canon_source_root::resolve_source_roots(
                &std::env::current_dir().map_err(|error| error.to_string())?,
                &std::env::vars().collect(),
            )
            .map_err(|error| error.detail)?
            .source_root
        }
    };
    let topic = options.topic.as_deref().ok_or("topic is required")?;
    let variant = options.variant.as_deref().ok_or("variant is required")?;
    let name = options
        .run_name
        .clone()
        .unwrap_or_else(|| format!("{topic}_{variant}_{}", compact_timestamp()));
    let identity = ExperimentIdentity::new(topic, variant, &name)?;
    let registry_path = match &options.registry {
        Some(path) => crate::path_resolution::resolve_non_strict(path)?,
        None => root.join("experiments/registry.toml"),
    };
    let registry = load_registry(registry_path, topic)?;
    let canonical_topic = root.join("experiments").join(topic);
    let topic_path = if registry.available {
        let value = registry_text(&registry.entry, "topic_dir")
            .ok_or_else(|| format!("registry entry for {topic:?} is missing topic_dir"))?;
        contained(&root, &root.join(value))?
    } else {
        contained(&root, &canonical_topic)?
    };
    if topic_path != canonical_topic {
        return Err(format!(
            "topic directory must match canonical identity path: expected {}, got {}",
            canonical_topic.display(),
            topic_path.display()
        ));
    }
    if !topic_path.is_dir() {
        return Err(format!(
            "topic directory does not exist: {}",
            topic_path.display()
        ));
    }
    let expected_report = root.join(identity.report_relative_path());
    let report = if let Some(path) = &options.report {
        contained(&root, &root.join(path))?
    } else if let Some(value) = registry_text(&registry.entry, "report_root")
        .filter(|value| !value.is_empty())
        .or_else(|| registry_text(&registry.defaults, "report_root"))
    {
        contained(
            &root,
            &root.join(value).join(format!("{}.md", identity.run_name)),
        )?
    } else {
        contained(&root, &expected_report)?
    };
    if report != expected_report {
        return Err(format!(
            "report path must match complete identity: expected {}, got {}",
            expected_report.display(),
            report.display()
        ));
    }
    let result = root.join(identity.result_relative_path());
    let raw = root.join(identity.raw_relative_path());
    for path in [&topic_path.join("result"), &result, &raw, &report] {
        if crate::path_resolution::resolve_non_strict(path)? != *path
            || std::fs::symlink_metadata(path).is_ok_and(|metadata| metadata.is_symlink())
        {
            return Err(format!(
                "run path must not escape by symlink: {}",
                path.display()
            ));
        }
    }
    let logs = raw.join("logs");
    let paths = RunPaths {
        manifest: result.join("run_manifest.json"),
        eval: result.join("eval_manifest.json"),
        artifacts: result.join("artifact_manifest.json"),
        command: result.join("command.json"),
        environment: result.join("environment.json"),
        snapshot: result.join("source_snapshot.json"),
        source_config: result.join("config_source.yaml"),
        config: result.join("config.json"),
        run_log: result.join("run.log"),
        startup: logs.join("startup.jsonl"),
        stdout: logs.join("stdout.log"),
        stderr: logs.join("stderr.log"),
        result,
        raw,
        logs,
        report,
    };
    let placeholders = BTreeMap::from([
        ("repo_root".into(), root.to_string_lossy().into_owned()),
        (
            "topic_dir".into(),
            topic_path.to_string_lossy().into_owned(),
        ),
        ("variant".into(), identity.variant.clone()),
        ("run_name".into(), identity.run_name.clone()),
        (
            "run_dir".into(),
            paths.result.to_string_lossy().into_owned(),
        ),
        ("raw_dir".into(), paths.raw.to_string_lossy().into_owned()),
        ("log_dir".into(), paths.logs.to_string_lossy().into_owned()),
        (
            "report_path".into(),
            paths.report.to_string_lossy().into_owned(),
        ),
        (
            "manifest_path".into(),
            paths.manifest.to_string_lossy().into_owned(),
        ),
        (
            "eval_manifest_path".into(),
            paths.eval.to_string_lossy().into_owned(),
        ),
        (
            "artifact_manifest_path".into(),
            paths.artifacts.to_string_lossy().into_owned(),
        ),
        (
            "command_manifest_path".into(),
            paths.command.to_string_lossy().into_owned(),
        ),
        (
            "environment_manifest_path".into(),
            paths.environment.to_string_lossy().into_owned(),
        ),
        (
            "source_snapshot_path".into(),
            paths.snapshot.to_string_lossy().into_owned(),
        ),
        (
            "config_source_path".into(),
            paths.source_config.to_string_lossy().into_owned(),
        ),
        (
            "config_path".into(),
            paths.config.to_string_lossy().into_owned(),
        ),
        (
            "log_path".into(),
            paths.run_log.to_string_lossy().into_owned(),
        ),
        (
            "startup_log_path".into(),
            paths.startup.to_string_lossy().into_owned(),
        ),
        (
            "stdout_log_path".into(),
            paths.stdout.to_string_lossy().into_owned(),
        ),
        (
            "stderr_log_path".into(),
            paths.stderr.to_string_lossy().into_owned(),
        ),
    ]);
    if options.registered.is_some() && !options.command.is_empty() {
        return Err("do not pass both a manual command and --use-registered-command".into());
    }
    let (command, command_source, registered_match) = if let Some(kind) = &options.registered {
        if !registry.available {
            return Err("--use-registered-command requires experiments/registry.toml".into());
        }
        let kind = if kind == "smoke" { "default" } else { kind };
        if !["default", "formal"].contains(&kind) {
            return Err(format!(
                "unsupported registered command {kind:?}; expected default, formal"
            ));
        }
        (
            registered_command(&registry.entry, kind, &placeholders)?,
            format!("registered:{kind}"),
            Some(kind.to_owned()),
        )
    } else {
        let command = format_tokens(json!(options.command), &placeholders)?;
        let matched = ["default", "formal"].iter().find_map(|kind| {
            registered_command(&registry.entry, kind, &placeholders)
                .ok()
                .filter(|candidate| *candidate == command)
                .map(|_| (*kind).to_owned())
        });
        (command, "manual".into(), matched)
    };
    let status = git_value(&root, &["status", "--short"])
        .map(|text| text.lines().map(str::to_owned).collect())
        .unwrap_or_default();
    let branch = git_value(&root, &["branch", "--show-current"]);
    let commit = git_value(&root, &["rev-parse", "HEAD"]);
    Ok(RunContext {
        root,
        identity,
        topic: topic_path,
        paths,
        registry,
        command,
        command_source,
        registered_match,
        created: utc_now()?,
        branch,
        commit,
        status,
    })
}

fn set_field(object: &mut JsonValue, key: &str, value: JsonValue) -> Result<()> {
    let JsonValue::Object(JsonObject(fields)) = object else {
        return Err("JSON object required".into());
    };
    if let Some((_, current)) = fields.iter_mut().find(|(name, _)| name.equals_text(key)) {
        *current = value;
    } else {
        fields.push((JsonString::from_text(key), value));
    }
    Ok(())
}
fn parse_config(options: &Options) -> Result<JsonValue> {
    let mut config = if let Some(path) = &options.config_json {
        let path = crate::path_resolution::resolve_non_strict(path)?;
        let bytes = std::fs::read(&path).map_err(|error| error.to_string())?;
        let value = python_json::parse_json_bytes(&bytes)?;
        if !matches!(value, JsonValue::Object(_)) {
            return Err(format!(
                "--config-json must decode to a JSON object: {}",
                path.display()
            ));
        }
        value
    } else {
        JsonValue::Object(JsonObject(Vec::new()))
    };
    if let JsonValue::Object(JsonObject(fields)) = &config {
        for (key, _) in fields {
            if key
                .to_text()
                .is_some_and(|text| crate::python_text::python_strip(&text).is_empty())
            {
                return Err("--config-json contains an invalid key".into());
            }
        }
    }
    for pair in &options.config {
        let (key, raw) = pair
            .split_once('=')
            .ok_or_else(|| format!("--config must use KEY=JSON form: {pair}"))?;
        let key = crate::python_text::python_strip(key);
        if key.is_empty() {
            return Err(format!("--config has an empty key: {pair}"));
        }
        set_field(
            &mut config,
            key,
            python_json::parse_json(raw).map_err(|error| {
                format!("--config value for {key:?} is not valid JSON: {error}")
            })?,
        )?;
    }
    Ok(config)
}

fn as_python(value: &Value) -> Result<JsonValue> {
    python_json::parse_json(&value.to_string())
}
fn artifact_capability(
    context: &RunContext,
) -> Result<crate::source_mutation::SourceMutationCapability> {
    let relative = |path: &Path| {
        path.strip_prefix(&context.root)
            .map(|path| path.to_string_lossy().into_owned())
            .map_err(|_| "artifact is outside repository root".to_owned())
    };
    let packet = json!({"allowed_paths":[relative(&context.paths.result)?,relative(&context.paths.report)?],"purpose":"managed experiment result and report output","authority":"selected experiment identity"});
    crate::source_mutation::SourceMutationCapability::from_json(
        &context.root,
        Some(&packet.to_string()),
    )
    .map_err(|error| error.to_string())
}
fn write_json(context: &RunContext, path: &Path, value: &JsonValue) -> Result<()> {
    let mut bytes = python_json::python_json_pretty_ascii_bytes(value)?;
    bytes.push(b'\n');
    let text = String::from_utf8(bytes).map_err(|error| error.to_string())?;
    #[cfg(unix)]
    let mode = {
        use std::os::unix::fs::MetadataExt;
        match std::fs::symlink_metadata(path) {
            Ok(metadata) => metadata.mode() & 0o7777,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let status = std::fs::read_to_string("/proc/self/status")
                    .map_err(|error| error.to_string())?;
                let mask = status
                    .lines()
                    .find_map(|line| line.strip_prefix("Umask:"))
                    .ok_or("process umask is unavailable")?;
                0o666 & !u32::from_str_radix(mask.trim(), 8).map_err(|error| error.to_string())?
            }
            Err(error) => return Err(error.to_string()),
        }
    };
    #[cfg(not(unix))]
    let mode = 0o644;
    artifact_capability(context)?
        .atomic_write_text_with_parents(path, &text, mode, true)
        .map_err(|error| error.to_string())
}
fn write_value(context: &RunContext, path: &Path, value: &Value) -> Result<()> {
    write_json(context, path, &as_python(value)?)
}
fn run_environment(context: &RunContext) -> BTreeMap<String, String> {
    let mut environment = std::env::vars().collect::<BTreeMap<_, _>>();
    for (key, value) in [
        ("EXPERIMENT_RUN_NAME", context.identity.run_name.as_str()),
        ("EXPERIMENT_TOPIC", context.identity.topic.as_str()),
        ("EXPERIMENT_VARIANT", context.identity.variant.as_str()),
    ] {
        environment.insert(key.into(), value.into());
    }
    for (key, path) in [
        ("EXPERIMENT_RUN_DIR", &context.paths.result),
        ("EXPERIMENT_RAW_DIR", &context.paths.raw),
        ("EXPERIMENT_LOG_DIR", &context.paths.logs),
        ("EXPERIMENT_REPORT_PATH", &context.paths.report),
        ("EXPERIMENT_RUN_MANIFEST", &context.paths.manifest),
        ("EXPERIMENT_EVAL_MANIFEST", &context.paths.eval),
        ("EXPERIMENT_ARTIFACT_MANIFEST", &context.paths.artifacts),
        ("EXPERIMENT_COMMAND_MANIFEST", &context.paths.command),
        ("EXPERIMENT_CONFIG_PATH", &context.paths.config),
        (
            "EXPERIMENT_SOURCE_CONFIG_PATH",
            &context.paths.source_config,
        ),
        ("EXPERIMENT_SOURCE_SNAPSHOT", &context.paths.snapshot),
        ("EXPERIMENT_RUN_LOG", &context.paths.run_log),
        ("EXPERIMENT_STARTUP_LOG", &context.paths.startup),
        ("EXPERIMENT_STDOUT_LOG", &context.paths.stdout),
        ("EXPERIMENT_STDERR_LOG", &context.paths.stderr),
    ] {
        environment.insert(key.into(), path.to_string_lossy().into_owned());
    }
    environment
}
fn sensitive_key(key: &str) -> bool {
    let upper = key.to_uppercase();
    [
        "API_KEY",
        "AUTH",
        "CREDENTIAL",
        "KEY",
        "PASSWORD",
        "SECRET",
        "TOKEN",
    ]
    .iter()
    .any(|part| upper.contains(part))
}
fn captured_environment(environment: &BTreeMap<String, String>) -> Result<Value> {
    let mut redacted = Vec::new();
    let values = environment
        .iter()
        .map(|(key, value)| {
            let value = if sensitive_key(key) {
                redacted.push(key.clone());
                json!({"present":true,"redacted":true})
            } else {
                json!(value)
            };
            (key.clone(), value)
        })
        .collect::<BTreeMap<_, _>>();
    Ok(
        json!({"captured_at_utc":utc_now()?,"policy":"full_environment_with_key_secret_redaction","key_count":values.len(),"redacted_keys":redacted,"values":values}),
    )
}
fn build_config(context: &RunContext, config: JsonValue) -> Result<JsonValue> {
    let mut value = context.identity.to_value();
    let object = value.as_object_mut().expect("identity object");
    object.insert("paths".into(),json!({"result_dir":context.paths.result,"raw_dir":context.paths.raw,"log_dir":context.paths.logs,"report_path":context.paths.report,"run_manifest":context.paths.manifest,"eval_manifest":context.paths.eval,"artifact_manifest":context.paths.artifacts,"command_manifest":context.paths.command,"environment_manifest":context.paths.environment,"source_snapshot":context.paths.snapshot,"source_config":context.paths.source_config,"config":context.paths.config,"startup_log":context.paths.startup,"stdout_log":context.paths.stdout,"stderr_log":context.paths.stderr}));
    object.insert("command".into(), json!(context.command));
    object.insert("command_source".into(), json!(context.command_source));
    object.insert(
        "registered_command_match".into(),
        json!(context.registered_match),
    );
    let mut value = as_python(&value)?;
    set_field(&mut value, "config", config)?;
    if context.registry.available {
        let entry = &context.registry.entry;
        let mut fields = Vec::new();
        for key in [
            "name",
            "canonical_entrypoint",
            "default_variant",
            "default_inner_command",
            "formal_inner_command",
        ] {
            let raw = if key == "default_inner_command" {
                store::get(entry, key)
                    .filter(|value| registry_truthy(value))
                    .or_else(|| store::get(entry, "smoke_inner_command"))
            } else {
                store::get(entry, key)
            };
            fields.push((
                JsonString::from_text(key),
                raw.map(store::json_value)
                    .transpose()?
                    .unwrap_or(JsonValue::Null),
            ));
        }
        set_field(
            &mut value,
            "registry",
            JsonValue::Object(JsonObject(fields)),
        )?;
    }
    Ok(value)
}
fn command_version(name: &str) -> Option<String> {
    let output = Command::new(name).arg("--version").output().ok()?;
    if !output.status.success() {
        return None;
    }
    let stdout = String::from_utf8(output.stdout).ok()?;
    let stderr = String::from_utf8(output.stderr).ok()?;
    let value = [
        crate::python_text::python_strip(&stdout),
        crate::python_text::python_strip(&stderr),
    ]
    .into_iter()
    .filter(|part| !part.is_empty())
    .collect::<Vec<_>>()
    .join("\n");
    value.lines().next().map(str::to_owned)
}
fn build_manifest(context: &RunContext) -> Result<JsonValue> {
    let metadata = crate::reference_materializer::provider("system-metadata", &[])?;
    let platform = metadata
        .get("platform")
        .and_then(Value::as_str)
        .ok_or("Python runtime system metadata is unavailable")?;
    let hostname = metadata
        .get("hostname")
        .and_then(Value::as_str)
        .ok_or("runtime hostname is unavailable")?;
    let python = metadata
        .get("python_version")
        .and_then(Value::as_str)
        .ok_or("Python runtime version is unavailable")?;
    let mut value = context.identity.to_value();
    let object = value.as_object_mut().expect("identity object");
    object.extend(json!({"status":"running","created_at_utc":context.created,"repo_root":context.root,"topic_dir":context.topic,"result_dir":context.paths.result,"raw_dir":context.paths.raw,"raw_artifacts":{"path":context.identity.raw_relative_path(),"retention":{"state":"unarchived"}},"log_dir":context.paths.logs,"report_path":context.paths.report,"manifest_path":context.paths.manifest,"eval_manifest_path":context.paths.eval,"artifact_manifest_path":context.paths.artifacts,"command_manifest_path":context.paths.command,"environment_manifest_path":context.paths.environment,"source_snapshot_path":context.paths.snapshot,"config_source_path":context.paths.source_config,"startup_log_path":context.paths.startup,"stdout_log_path":context.paths.stdout,"stderr_log_path":context.paths.stderr,"command":context.command,"server_context":{"hostname":hostname,"platform":platform,"cwd":std::env::current_dir().map_err(|error|error.to_string())?,"user":std::env::var("USER").or_else(|_|std::env::var("USERNAME")).unwrap_or_else(|_|"(unknown)".into())},"tool_versions":{"python":python,"codex":command_version("codex"),"docker":command_version("docker")},"command_source":context.command_source,"registered_command_match":context.registered_match,"git":{"branch":context.branch,"commit":context.commit,"dirty":!context.status.is_empty(),"status_short":context.status}}).as_object().expect("manifest object").clone());
    let mut value = as_python(&value)?;
    if context.registry.available {
        let mut registry = store::json_value(&context.registry.entry)?;
        set_field(
            &mut registry,
            "registry_path",
            as_python(&json!(context.registry.path))?,
        )?;
        set_field(&mut value, "registry", registry)?;
    }
    Ok(value)
}
fn startup_event(context: &RunContext, event: &str, payload: Value) -> Result<()> {
    use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
    use std::io::Write;
    let root = crate::source_mutation::open_root_nofollow(&context.root)
        .map_err(|error| error.to_string())?;
    let relative = context
        .paths
        .startup
        .strip_prefix(&context.root)
        .map_err(|error| error.to_string())?;
    let (directory, name) =
        crate::source_mutation::file_parent_from_root(&root, relative, Some(0o777))
            .map_err(|error| error.to_string())?;
    let mut options = cap_std::fs::OpenOptions::new();
    options.append(true).create(true).follow(FollowSymlinks::No);
    let mut file = directory
        .open_with(name, &options)
        .map_err(|error| error.to_string())?;
    let mut value = context.identity.to_value();
    let object = value.as_object_mut().expect("identity object");
    object.insert("timestamp_utc".into(), json!(utc_now()?));
    object.insert("event".into(), json!(event));
    object.extend(
        payload
            .as_object()
            .ok_or("startup event payload must be an object")?
            .clone(),
    );
    let value = as_python(&value)?;
    let mut bytes = python_json::canonical_json_ascii_bytes(&value)?;
    bytes.push(b'\n');
    file.write_all(&bytes).map_err(|error| error.to_string())
}
fn report_stub(context: &RunContext) -> String {
    let command = crate::lean_proof_env::shell_join(&context.command);
    let registry = if context.registry.available {
        context.registry.path.to_string_lossy().into_owned()
    } else {
        "(none)".into()
    };
    format!("# {}\n\n- Topic: {}\n- Variant: {}\n- Created At (UTC): {}\n- Result Dir: {}\n- Raw Dir: {}\n- Log Dir: {}\n- Run Manifest: {}\n- Eval Manifest: {}\n- Artifact Manifest: {}\n- Config: {}\n- Source Config Snapshot: {}\n- Registry: {}\n- Branch: {}\n- Commit: {}\n\n## Question\n\n<!-- What empirical question does this run answer? -->\n\n## Comparison Target\n\n<!-- main, baseline, previous run, or external reference. -->\n\n## Protocol\n\n- Command: `{command}`\n- Report Path: `{}`\n\n## Results\n\n<!-- Fill in summary/summary.json, summary/cases.jsonl, and the main observations after the run. -->\n\n## Reproducibility Record\n\n- `run_manifest.json`\n- `config.json`\n- `config_source.yaml`\n- `eval_manifest.json`\n- `artifact_manifest.json`\n- `command.json`\n- `environment.json`\n- `source_snapshot.json`\n- `run.log`\n- `logs/`\n- `logs/startup.jsonl`\n- `logs/stdout.log`\n- `logs/stderr.log`\n- `summary/summary.json`\n- `summary/cases.jsonl`\n\n## Critical Review Notes\n\n<!-- What this run still does not justify. -->\n",context.identity.run_name,context.identity.topic,context.identity.variant,context.created,context.paths.result.display(),context.paths.raw.display(),context.paths.logs.display(),context.paths.manifest.display(),context.paths.eval.display(),context.paths.artifacts.display(),context.paths.config.display(),context.paths.source_config.display(),registry,context.branch.as_deref().unwrap_or("(unknown)"),context.commit.as_deref().unwrap_or("(unknown)"),context.paths.report.display())
}

struct ReservationReceipt {
    root: cap_std::fs::Dir,
    result: PathBuf,
    raw: PathBuf,
    report: PathBuf,
    marker: PathBuf,
    token: String,
    identity: ExperimentIdentity,
    result_id: (u64, u64),
    raw_id: (u64, u64),
    marker_id: (u64, u64),
    report_id: Option<(u64, u64)>,
    parents: Vec<ReservationParent>,
}
type ReservationParent = (PathBuf, bool, Option<(u64, u64)>);
fn metadata_id(metadata: &cap_std::fs::Metadata) -> (u64, u64) {
    use cap_std::fs::MetadataExt;
    (metadata.dev(), metadata.ino())
}
fn parent_for(
    root: &cap_std::fs::Dir,
    path: &Path,
    create: bool,
) -> Result<(cap_std::fs::Dir, std::ffi::OsString)> {
    crate::source_mutation::file_parent_from_root(root, path, create.then_some(0o777))
        .map_err(|error| error.to_string())
}
fn directory_id(root: &cap_std::fs::Dir, path: &Path) -> Result<(u64, u64)> {
    let (parent, name) = parent_for(root, &path.join(".directory-id"), false)?;
    let _ = name;
    Ok(metadata_id(
        &parent.dir_metadata().map_err(|error| error.to_string())?,
    ))
}
fn remove_empty_owned(root: &cap_std::fs::Dir, path: &Path, expected: (u64, u64)) -> bool {
    use cap_fs_ext::DirExt;
    let Ok((parent, name)) = parent_for(root, path, false) else {
        return false;
    };
    let Ok(metadata) = parent.symlink_metadata(&name) else {
        return false;
    };
    if !metadata.is_dir() || metadata_id(&metadata) != expected {
        return false;
    }
    let Ok(directory) = parent.open_dir_nofollow(&name) else {
        return false;
    };
    let Ok(mut entries) = directory.entries() else {
        return false;
    };
    if entries.next().is_some() {
        return false;
    }
    parent.remove_dir(name).is_ok()
}
impl ReservationReceipt {
    fn owner_matches(&self) -> bool {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use std::io::Read;
        for (path, expected) in [
            (&self.result, self.result_id),
            (&self.raw, self.raw_id),
            (&self.marker, self.marker_id),
        ] {
            let Ok((parent, name)) = parent_for(&self.root, path, false) else {
                return false;
            };
            let Ok(metadata) = parent.symlink_metadata(name) else {
                return false;
            };
            if metadata.file_type().is_symlink() || metadata_id(&metadata) != expected {
                return false;
            }
        }
        let Ok((parent, name)) = parent_for(&self.root, &self.marker, false) else {
            return false;
        };
        let mut options = cap_std::fs::OpenOptions::new();
        options.read(true).follow(FollowSymlinks::No);
        let Ok(mut file) = parent.open_with(name, &options) else {
            return false;
        };
        let mut bytes = Vec::new();
        if file.read_to_end(&mut bytes).is_err() {
            return false;
        }
        let Ok(value) = serde_json::from_slice::<Value>(&bytes) else {
            return false;
        };
        value.as_object().is_some_and(|object| object.len() == 6)
            && value["schema"] == "agentcanon.experiment-reservation/v1"
            && value["state"] == "reserved"
            && value["token"] == self.token
            && value["result_inode"] == self.result_id.1
            && value["raw_inode"] == self.raw_id.1
            && ExperimentIdentity::from_value(&value)
                .is_ok_and(|identity| identity == self.identity)
    }
    fn release_marker(&self) -> bool {
        if !self.owner_matches() {
            return false;
        }
        let Ok((parent, name)) = parent_for(&self.root, &self.marker, false) else {
            return false;
        };
        parent.remove_file(name).is_ok()
    }
    fn rollback(&self) -> bool {
        use cap_fs_ext::DirExt;
        if !self.owner_matches() {
            return false;
        }
        for (path, preexisted, expected) in &self.parents {
            if !preexisted && expected.is_some() && directory_id(&self.root, path).ok() != *expected
            {
                return false;
            }
        }
        let Ok((parent, name)) = parent_for(&self.root, &self.result, false) else {
            return false;
        };
        let Ok(result) = parent.open_dir_nofollow(name) else {
            return false;
        };
        let Ok(entries) = result.entries() else {
            return false;
        };
        let names = entries
            .map(|entry| entry.map(|entry| entry.file_name()))
            .collect::<std::io::Result<std::collections::BTreeSet<_>>>();
        let Ok(names) = names else {
            return false;
        };
        if names
            != std::collections::BTreeSet::from([
                std::ffi::OsString::from("raw"),
                std::ffi::OsString::from(".agentcanon-reservation.json"),
            ])
        {
            return false;
        }
        if let Some(expected) = self.report_id {
            let Ok((parent, name)) = parent_for(&self.root, &self.report, false) else {
                return false;
            };
            let Ok(metadata) = parent.symlink_metadata(name) else {
                return false;
            };
            if !metadata.is_file() || metadata_id(&metadata) != expected {
                return false;
            }
        }
        if !remove_empty_owned(&self.root, &self.raw, self.raw_id) {
            return false;
        }
        let Ok((parent, name)) = parent_for(&self.root, &self.marker, false) else {
            return false;
        };
        if parent.remove_file(name).is_err() {
            return false;
        }
        if !remove_empty_owned(&self.root, &self.result, self.result_id) {
            return false;
        }
        if self.report_id.is_some() {
            let Ok((parent, name)) = parent_for(&self.root, &self.report, false) else {
                return false;
            };
            if parent.remove_file(name).is_err() {
                return false;
            }
        }
        for (path, preexisted, id) in self.parents.iter().rev() {
            if !preexisted {
                if let Some(id) = id {
                    remove_empty_owned(&self.root, path, *id);
                }
            }
        }
        true
    }
}
fn reserve_paths(context: &RunContext, skip_report: bool) -> Result<ReservationReceipt> {
    use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
    use std::io::Write;
    let root = crate::source_mutation::open_root_nofollow(&context.root)
        .map_err(|error| error.to_string())?;
    let relative = |path: &Path| {
        path.strip_prefix(&context.root)
            .map(Path::to_path_buf)
            .map_err(|error| error.to_string())
    };
    let result = relative(&context.paths.result)?;
    let raw = relative(&context.paths.raw)?;
    let report = relative(&context.paths.report)?;
    if root.symlink_metadata(&report).is_ok() {
        return Err(format!(
            "report already exists for identity: {}",
            context.paths.report.display()
        ));
    }
    let mut parents = Vec::new();
    for path in [
        result.parent().ok_or("result parent missing")?,
        raw.parent().ok_or("raw parent missing")?,
        report.parent().ok_or("report parent missing")?,
    ] {
        let existed = directory_id(&root, path).is_ok();
        parents.push((path.to_path_buf(), existed, None));
    }
    let (parent, name) = parent_for(&root, &result, true)?;
    let result_parent_id = metadata_id(&parent.dir_metadata().map_err(|error| error.to_string())?);
    parents[0].2 = Some(result_parent_id);
    if let Err(error) = parent.create_dir(&name) {
        if !parents[0].1 {
            remove_empty_owned(&root, &parents[0].0, result_parent_id);
        }
        return Err(if error.kind() == std::io::ErrorKind::AlreadyExists {
            format!(
                "result directory already exists for identity: {}",
                context.paths.result.display()
            )
        } else {
            error.to_string()
        });
    }
    let result_id = metadata_id(
        &parent
            .symlink_metadata(name)
            .map_err(|error| error.to_string())?,
    );
    let (parent, name) = parent_for(&root, &raw, true)?;
    parents[1].2 = Some(metadata_id(
        &parent.dir_metadata().map_err(|error| error.to_string())?,
    ));
    if let Err(error) = parent.create_dir(&name) {
        remove_empty_owned(&root, &result, result_id);
        if !parents[0].1 {
            remove_empty_owned(&root, &parents[0].0, result_parent_id);
        }
        return Err(if error.kind() == std::io::ErrorKind::AlreadyExists {
            format!(
                "raw directory already exists for identity: {}",
                context.paths.raw.display()
            )
        } else {
            error.to_string()
        });
    }
    let raw_id = metadata_id(
        &parent
            .symlink_metadata(name)
            .map_err(|error| error.to_string())?,
    );
    let mut random = [0u8; 24];
    getrandom::getrandom(&mut random).map_err(|error| error.to_string())?;
    let token = random
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let marker = result.join(".agentcanon-reservation.json");
    let mut payload = context.identity.to_value();
    payload.as_object_mut().expect("identity object").extend(json!({"schema":"agentcanon.experiment-reservation/v1","state":"reserved","token":token,"result_inode":result_id.1,"raw_inode":raw_id.1}).as_object().expect("reservation object").clone());
    let (parent, name) = parent_for(&root, &marker, false)?;
    let mut options = cap_std::fs::OpenOptions::new();
    options
        .write(true)
        .create_new(true)
        .follow(FollowSymlinks::No);
    let mut file = match parent.open_with(&name, &options) {
        Ok(file) => file,
        Err(error) => {
            remove_empty_owned(&root, &raw, raw_id);
            remove_empty_owned(&root, &result, result_id);
            for (path, preexisted, id) in parents.iter().take(2).rev() {
                if !preexisted {
                    if let Some(id) = id {
                        remove_empty_owned(&root, path, *id);
                    }
                }
            }
            return Err(error.to_string());
        }
    };
    let bytes = python_json::python_json_ascii_bytes(&as_python(&payload)?)?;
    file.write_all(&bytes)
        .and_then(|_| file.write_all(b"\n"))
        .and_then(|_| file.sync_all())
        .map_err(|error| error.to_string())?;
    let marker_id = metadata_id(&file.metadata().map_err(|error| error.to_string())?);
    drop(file);
    let mut receipt = ReservationReceipt {
        root,
        result,
        raw,
        report,
        marker,
        token,
        identity: context.identity.clone(),
        result_id,
        raw_id,
        marker_id,
        report_id: None,
        parents,
    };
    if !skip_report {
        let operation = (|| -> Result<()> {
            let (parent, name) = parent_for(&receipt.root, &receipt.report, true)?;
            receipt.parents[2].2 = Some(metadata_id(
                &parent.dir_metadata().map_err(|error| error.to_string())?,
            ));
            let mut file = parent
                .open_with(name, &options)
                .map_err(|error| error.to_string())?;
            receipt.report_id = Some(metadata_id(
                &file.metadata().map_err(|error| error.to_string())?,
            ));
            file.write_all(report_stub(context).as_bytes())
                .and_then(|_| file.sync_all())
                .map_err(|error| error.to_string())
        })();
        if let Err(error) = operation {
            receipt.rollback();
            return Err(error);
        }
    }
    Ok(receipt)
}

struct EvalPatterns {
    required: Vec<String>,
    optional: Vec<String>,
}
fn string_list(value: Option<&RegistryValue>, key: &str) -> Result<Vec<String>> {
    match value {
        None => Ok(Vec::new()),
        Some(RegistryValue::Array(values)) => values
            .iter()
            .enumerate()
            .map(|(index, value)| match value {
                RegistryValue::String(value)
                    if !crate::python_text::python_strip(value).is_empty() =>
                {
                    Ok(crate::python_text::python_strip(value).to_owned())
                }
                _ => Err(format!("{key}[{index}] must be a non-empty string")),
            })
            .collect(),
        _ => Err(format!("{key} must be an array of strings")),
    }
}
fn eval_patterns(registry: &RegistryContext) -> Result<EvalPatterns> {
    let mut required = vec![
        "summary/summary.json".to_owned(),
        "summary/cases.jsonl".into(),
        "config.json".into(),
    ];
    let mut optional = Vec::new();
    for (table, label) in [
        (&registry.defaults, "defaults"),
        (&registry.entry, "topics"),
    ] {
        for (key, target) in [
            ("required_eval_artifacts", &mut required),
            ("optional_eval_artifacts", &mut optional),
        ] {
            for value in string_list(store::get(table, key), &format!("{label}.{key}"))? {
                if Path::new(&value).is_absolute()
                    || Path::new(&value)
                        .components()
                        .any(|component| matches!(component, std::path::Component::ParentDir))
                {
                    return Err(format!(
                        "{key} must stay relative to result/<run_name>: {value}"
                    ));
                }
                if !target.contains(&value) {
                    target.push(value);
                }
            }
        }
    }
    optional.retain(|pattern| !required.contains(pattern));
    Ok(EvalPatterns { required, optional })
}
fn hash_file(root: &Path, path: &Path) -> Result<(String, u64, u64)> {
    use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
    use sha2::{Digest, Sha256};
    use std::io::Read;
    let resolved = contained(root, path)?;
    let directory =
        crate::source_mutation::open_root_nofollow(root).map_err(|error| error.to_string())?;
    let relative = resolved
        .strip_prefix(root)
        .map_err(|error| error.to_string())?;
    let (parent, name) = parent_for(&directory, relative, false)?;
    let mut options = cap_std::fs::OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No);
    let mut file = parent
        .open_with(name, &options)
        .map_err(|error| error.to_string())?;
    if !file
        .metadata()
        .map_err(|error| error.to_string())?
        .is_file()
    {
        return Err(format!(
            "artifact must be a regular file: {}",
            path.display()
        ));
    }
    let mut hash = Sha256::new();
    let mut size = 0u64;
    let mut lines = 0u64;
    let mut last = None;
    let mut bytes = [0u8; 65536];
    loop {
        let count = file.read(&mut bytes).map_err(|error| error.to_string())?;
        if count == 0 {
            break;
        }
        hash.update(&bytes[..count]);
        size += count as u64;
        lines += bytes[..count].iter().filter(|byte| **byte == b'\n').count() as u64;
        last = Some(bytes[count - 1]);
    }
    if last.is_some_and(|byte| byte != b'\n') {
        lines += 1;
    }
    Ok((format!("{:x}", hash.finalize()), size, lines))
}
fn file_record(context: &RunContext, path: &Path, base: &Path) -> Result<Value> {
    let (sha256, bytes, _) = hash_file(&context.root, path)?;
    Ok(
        json!({"relative_path":path.strip_prefix(base).map_err(|error|error.to_string())?,"bytes":bytes,"sha256":sha256}),
    )
}
fn collect_eval_artifacts(context: &RunContext, patterns: &EvalPatterns) -> Result<Value> {
    let reserved = [
        "run_manifest.json",
        "eval_manifest.json",
        "run.log",
        "config_source.yaml",
        "command.json",
        "environment.json",
        "source_snapshot.json",
        "artifact_manifest.json",
        "logs/startup.jsonl",
        "logs/stdout.log",
        "logs/stderr.log",
    ];
    let mut matches = BTreeMap::<PathBuf, Vec<String>>::new();
    let mut missing = Vec::new();
    for (required, group) in [(true, &patterns.required), (false, &patterns.optional)] {
        for pattern in group {
            let expanded = crate::path_resolution::python_pathlib_glob_paths(
                &context.paths.result.join(pattern).to_string_lossy(),
            )?
            .into_iter()
            .filter(|path| {
                path.is_file()
                    && !reserved
                        .iter()
                        .any(|name| path == &context.paths.result.join(name))
            })
            .collect::<Vec<_>>();
            if required && expanded.is_empty() {
                missing.push(pattern.clone());
            }
            for path in expanded {
                matches.entry(path).or_default().push(pattern.clone());
            }
        }
    }
    let mut artifacts = Vec::new();
    for (path, matched) in matches {
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("")
            .to_lowercase();
        let kind = match extension.as_str() {
            "jsonl" => "jsonl",
            "json" => "json",
            "csv" => "csv",
            "txt" | "log" | "md" => "text",
            "png" | "jpg" | "jpeg" | "svg" | "pdf" | "html" => "rendered",
            _ => "file",
        };
        let (hash, size, lines) = hash_file(&context.root, &path)?;
        let mut record = json!({"relative_path":path.strip_prefix(&context.paths.result).map_err(|error|error.to_string())?,"kind":kind,"bytes":size,"sha256":hash,"matched_patterns":matched});
        if ["jsonl", "text", "csv"].contains(&kind) {
            record["line_count"] = json!(lines);
        }
        artifacts.push(record);
    }
    let mut value = context.identity.to_value();
    value.as_object_mut().expect("identity object").extend(json!({"result_dir":context.paths.result,"collected_at_utc":utc_now()?,"required_patterns":patterns.required,"optional_patterns":patterns.optional,"missing_required_patterns":missing,"artifact_count":artifacts.len(),"artifacts":artifacts}).as_object().expect("eval manifest").clone());
    Ok(value)
}
fn artifact_manifest(context: &RunContext) -> Result<Value> {
    let files = crate::path_resolution::python_pathlib_glob_paths(
        &context.paths.result.join("**/*").to_string_lossy(),
    )?
    .into_iter()
    .filter(|path| path.is_file() && path != &context.paths.artifacts)
    .collect::<Vec<_>>();
    let artifacts = files
        .iter()
        .map(|path| file_record(context, path, &context.paths.result))
        .collect::<Result<Vec<_>>>()?;
    let mut value = context.identity.to_value();
    value.as_object_mut().expect("identity object").extend(json!({"schema_version":1,"captured_at_utc":utc_now()?,"result_dir":context.paths.result,"self_excluded":context.paths.artifacts,"artifact_count":artifacts.len(),"artifacts":artifacts}).as_object().expect("artifact manifest").clone());
    Ok(value)
}
fn copy_source_config(context: &RunContext) -> Result<Value> {
    let source = context.topic.join("config.yaml");
    if !source.is_file() {
        return Ok(
            json!({"status":"missing","source_path":source,"snapshot_path":context.paths.source_config}),
        );
    }
    artifact_capability(context)?
        .copy_file_from_root_with_metadata(&context.root, &source, &context.paths.source_config)
        .map_err(|error| error.to_string())?;
    let (sha256, bytes, _) = hash_file(&context.root, &context.paths.source_config)?;
    Ok(
        json!({"status":"copied","source_path":source,"snapshot_path":context.paths.source_config,"sha256":sha256,"bytes":bytes}),
    )
}
fn clone_json(value: &JsonValue) -> Result<JsonValue> {
    python_json::parse_json_bytes(&python_json::python_json_ascii_bytes(value)?)
}
fn write_initial_artifacts(
    context: &RunContext,
    manifest: &mut JsonValue,
    config: &mut JsonValue,
) -> Result<Value> {
    let source_config = copy_source_config(context)?;
    set_field(config, "source_config", as_python(&source_config)?)?;
    set_field(manifest, "source_config", as_python(&source_config)?)?;
    set_field(
        manifest,
        "config_path",
        as_python(&json!(context.paths.config))?,
    )?;
    set_field(manifest, "config", clone_json(config)?)?;
    write_json(context, &context.paths.config, config)?;
    let mut command = context.identity.to_value();
    command.as_object_mut().expect("identity object").extend(json!({"schema_version":1,"created_at_utc":utc_now()?,"command":context.command,"command_text":crate::lean_proof_env::shell_join(&context.command),"command_source":context.command_source,"registered_command_match":context.registered_match,"cwd":context.root,"paths":{"result_dir":context.paths.result,"raw_dir":context.paths.raw,"log_dir":context.paths.logs,"run_log":context.paths.run_log,"stdout_log":context.paths.stdout,"stderr_log":context.paths.stderr,"startup_log":context.paths.startup}}).as_object().expect("command manifest").clone());
    write_value(context, &context.paths.command, &command)?;
    write_value(
        context,
        &context.paths.environment,
        &captured_environment(&run_environment(context))?,
    )?;
    write_json(context, &context.paths.manifest, manifest)?;
    startup_event(
        context,
        "initialized",
        json!({"result_dir":context.paths.result,"raw_dir":context.paths.raw,"command_manifest":context.paths.command,"environment_manifest":context.paths.environment,"source_snapshot":context.paths.snapshot}),
    )?;
    Ok(source_config)
}
fn finalize_manifest(
    context: &RunContext,
    manifest: &mut JsonValue,
    start: std::time::Instant,
    exit_code: i32,
    patterns: &EvalPatterns,
) -> Result<()> {
    let eval = collect_eval_artifacts(context, patterns)?;
    write_value(context, &context.paths.eval, &eval)?;
    let duration = format!("{:.3}", start.elapsed().as_secs_f64())
        .parse::<f64>()
        .map_err(|error| error.to_string())?;
    for (key, value) in [
        ("finished_at_utc", json!(utc_now()?)),
        ("duration_seconds", json!(duration)),
        ("exit_code", json!(exit_code)),
        (
            "status",
            json!(if exit_code == 0 {
                "completed"
            } else {
                "failed"
            }),
        ),
        (
            "eval_artifacts",
            json!({"eval_manifest_path":context.paths.eval,"required_patterns":patterns.required,"optional_patterns":patterns.optional,"collected_artifact_count":eval["artifact_count"],"missing_required_patterns":eval["missing_required_patterns"]}),
        ),
        (
            "artifact_manifest",
            json!({"artifact_manifest_path":context.paths.artifacts,"self_excluded":true}),
        ),
    ] {
        set_field(manifest, key, as_python(&value)?)?;
    }
    write_json(context, &context.paths.manifest, manifest)?;
    write_value(
        context,
        &context.paths.artifacts,
        &artifact_manifest(context)?,
    )
}

const PROVIDER_EXECUTABLE: &str = "experiment-runner-admitted";
fn managed_interface() -> Result<Value> {
    serde_json::from_str(include_str!(
        "../../../../../documents/experiments/gpu-admission-r5-ordered-integration-interface.json"
    ))
    .map_err(|error| error.to_string())
}
fn provider_contract() -> Result<Value> {
    let interface = managed_interface()?;
    Ok(
        json!({"repository":interface["provider_repository"],"commit":interface["provider_commit"],"contract_path":interface["provider_contract_path"],"contract_sha256":interface["provider_contract_sha256"],"invocation":interface["provider_invocation"]}),
    )
}
type AdmissionResult<T> = std::result::Result<T, crate::execution_resource_plan::Failure>;
fn admission_error(code: &str, message: &str) -> crate::execution_resource_plan::Failure {
    crate::execution_resource_plan::Failure::new(code, message)
}
#[derive(Clone, serde::Serialize, serde::Deserialize)]
struct ManagedExecution {
    status: String,
    raw_exit_code: i32,
    failure_kind: Option<String>,
    message: Option<String>,
    source: String,
}
#[derive(Clone, serde::Serialize, serde::Deserialize)]
struct ManagedLifecycle {
    run_id: String,
    terminal_event_id: String,
    observed_at_ns: u64,
    terminal_status: String,
    total_case_count_at_start: u64,
    completion_count_before: u64,
    completion_count_after: u64,
    scheduler_completed: bool,
    admitted_case_count: u64,
    terminal_notification_count: u64,
    child_process_ids: Vec<u64>,
    process_group_ids: Vec<u64>,
    direct_children_quiescent: bool,
    descendant_quiescence: String,
    cleanup_failures: Vec<String>,
    terminal_coverage_complete: bool,
    requested_case_coverage_complete: bool,
    quiescence_complete: bool,
    completion_coverage_complete: bool,
}
impl ManagedLifecycle {
    fn quiescent(&self) -> bool {
        self.quiescence_complete
            && self.direct_children_quiescent
            && ["proved", "no_child"].contains(&self.descendant_quiescence.as_str())
            && self.cleanup_failures.is_empty()
            && self.completion_coverage_complete
    }
}
fn protocol_integer(object: &Value, key: &str) -> AdmissionResult<u64> {
    object.get(key).and_then(Value::as_u64).ok_or_else(|| {
        admission_error(
            "admitted_runner_result_corrupt",
            &format!("provider lifecycle field {key} is invalid"),
        )
    })
}
fn protocol_bool(object: &Value, key: &str) -> AdmissionResult<bool> {
    object.get(key).and_then(Value::as_bool).ok_or_else(|| {
        admission_error(
            "admitted_runner_result_corrupt",
            &format!("provider lifecycle field {key} is invalid"),
        )
    })
}
fn protocol_pids(object: &Value, key: &str) -> AdmissionResult<Vec<u64>> {
    let raw = object.get(key).and_then(Value::as_array).ok_or_else(|| {
        admission_error(
            "admitted_runner_result_corrupt",
            &format!("provider lifecycle field {key} is invalid"),
        )
    })?;
    let pids = raw
        .iter()
        .map(|value| {
            value.as_u64().filter(|pid| *pid > 0).ok_or_else(|| {
                admission_error(
                    "admitted_runner_result_corrupt",
                    &format!("provider lifecycle field {key} contains invalid process IDs"),
                )
            })
        })
        .collect::<AdmissionResult<Vec<_>>>()?;
    if pids.iter().collect::<std::collections::BTreeSet<_>>().len() != pids.len() {
        return Err(admission_error(
            "admitted_runner_result_corrupt",
            &format!("provider lifecycle field {key} contains invalid process IDs"),
        ));
    }
    Ok(pids)
}
fn validate_provider_result(
    path: &Path,
    request: &Value,
    returncode: i32,
) -> AdmissionResult<(ManagedExecution, ManagedLifecycle, Value)> {
    let bytes = std::fs::read(path).map_err(|_| {
        admission_error(
            "admitted_runner_result_corrupt",
            "experiment-runner-admitted result artifact is missing or invalid JSON",
        )
    })?;
    let result: Value = serde_json::from_slice(&bytes).map_err(|_| {
        admission_error(
            "admitted_runner_result_corrupt",
            "experiment-runner-admitted result artifact is missing or invalid JSON",
        )
    })?;
    if !result.is_object() {
        return Err(admission_error(
            "admitted_runner_result_corrupt",
            "experiment-runner-admitted result artifact must be a JSON object",
        ));
    }
    if result.get("schema").and_then(Value::as_str) != Some("agentcanon-managed-run-result/v1") {
        return Err(admission_error(
            "admitted_runner_result_schema_mismatch",
            "experiment-runner-admitted result schema is not the reviewed version",
        ));
    }
    let identity = ExperimentIdentity::from_value(request).map_err(|_| {
        admission_error(
            "admitted_runner_result_identity_invalid",
            "request and result must contain canonical nested experiment identity",
        )
    })?;
    let actual = ExperimentIdentity::from_value(&result).map_err(|_| {
        admission_error(
            "admitted_runner_result_identity_invalid",
            "request and result must contain canonical nested experiment identity",
        )
    })?;
    if actual != identity {
        return Err(admission_error(
            "admitted_runner_result_identity_mismatch",
            "provider result identity does not match the managed request identity",
        ));
    }
    if result.get("request_fingerprint") != request.get("fingerprint") {
        return Err(admission_error(
            "admitted_runner_result_fingerprint_mismatch",
            "result does not reference the request fingerprint",
        ));
    }
    if result.get("run_id") != request.get("run_id") {
        return Err(admission_error(
            "admitted_runner_result_corrupt",
            "result does not reference request run identity",
        ));
    }
    let status = result
        .get("status")
        .and_then(Value::as_str)
        .filter(|value| ["ok", "failed", "rejected"].contains(value))
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_result_corrupt",
                "result status is not part of provider schema",
            )
        })?;
    let worker_pids = protocol_pids(&result, "worker_pids")?;
    if worker_pids
        .first()
        .map(|pid| json!(pid))
        .unwrap_or(Value::Null)
        != result.get("worker_pid").cloned().unwrap_or(Value::Null)
    {
        return Err(admission_error(
            "admitted_runner_result_corrupt",
            "result worker_pid must match the first worker PID or null for no workers",
        ));
    }
    let lifecycle = result
        .get("lifecycle")
        .filter(|value| value.is_object())
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_descendant_quiescence_unproven",
                "result must contain provider lifecycle and quiescence objects",
            )
        })?;
    let quiescence = result
        .get("quiescence")
        .filter(|value| value.is_object())
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_descendant_quiescence_unproven",
                "result must contain provider lifecycle and quiescence objects",
            )
        })?;
    let exit = result
        .get("exit")
        .filter(|value| value.is_object())
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_descendant_quiescence_unproven",
                "result must contain provider lifecycle and quiescence objects",
            )
        })?;
    let run_id = lifecycle
        .get("run_id")
        .and_then(Value::as_str)
        .filter(|value| Some(*value) == request.get("run_id").and_then(Value::as_str))
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_result_corrupt",
                "provider lifecycle identity or status fields are invalid",
            )
        })?;
    let event = lifecycle
        .get("terminal_event_id")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_result_corrupt",
                "provider lifecycle identity or status fields are invalid",
            )
        })?;
    let terminal = lifecycle
        .get("terminal_status")
        .and_then(Value::as_str)
        .filter(|value| ["finished", "failed", "interrupted"].contains(value))
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_result_corrupt",
                "provider lifecycle identity or status fields are invalid",
            )
        })?;
    let descendant = lifecycle
        .get("descendant_quiescence")
        .and_then(Value::as_str)
        .filter(|value| ["proved", "no_child", "unproven"].contains(value))
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_result_corrupt",
                "provider lifecycle identity or status fields are invalid",
            )
        })?;
    let children = protocol_pids(lifecycle, "child_process_ids")?;
    let groups = protocol_pids(lifecycle, "process_group_ids")?;
    if children != worker_pids {
        return Err(admission_error(
            "admitted_runner_result_corrupt",
            "provider lifecycle identity or status fields are invalid",
        ));
    }
    let cleanup = lifecycle
        .get("cleanup_failures")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_result_corrupt",
                "provider lifecycle cleanup_failures must be an array of strings",
            )
        })?
        .iter()
        .map(|value| {
            value
                .as_str()
                .filter(|value| !value.is_empty())
                .map(str::to_owned)
                .ok_or_else(|| {
                    admission_error(
                        "admitted_runner_result_corrupt",
                        "provider lifecycle cleanup_failures must be an array of strings",
                    )
                })
        })
        .collect::<AdmissionResult<Vec<_>>>()?;
    if result.get("descendant_quiescence").and_then(Value::as_str) != Some(descendant)
        || quiescence
            .get("descendant_quiescence")
            .and_then(Value::as_str)
            != Some(descendant)
        || quiescence.get("cleanup_failures") != Some(&json!(cleanup))
    {
        return Err(admission_error(
            "admitted_runner_result_corrupt",
            "provider result and lifecycle quiescence statuses disagree",
        ));
    }
    let evidence = ManagedLifecycle {
        run_id: run_id.into(),
        terminal_event_id: event.into(),
        observed_at_ns: protocol_integer(lifecycle, "observed_at_ns")?,
        terminal_status: terminal.into(),
        total_case_count_at_start: protocol_integer(lifecycle, "total_case_count_at_start")?,
        completion_count_before: protocol_integer(lifecycle, "completion_count_before")?,
        completion_count_after: protocol_integer(lifecycle, "completion_count_after")?,
        scheduler_completed: protocol_bool(lifecycle, "scheduler_completed")?,
        admitted_case_count: protocol_integer(lifecycle, "admitted_case_count")?,
        terminal_notification_count: protocol_integer(lifecycle, "terminal_notification_count")?,
        child_process_ids: children,
        process_group_ids: groups,
        direct_children_quiescent: protocol_bool(quiescence, "direct_children_quiescent")?,
        descendant_quiescence: descendant.into(),
        cleanup_failures: cleanup,
        terminal_coverage_complete: protocol_bool(lifecycle, "terminal_coverage_complete")?,
        requested_case_coverage_complete: protocol_bool(
            lifecycle,
            "requested_case_coverage_complete",
        )?,
        quiescence_complete: protocol_bool(lifecycle, "quiescence_complete")?,
        completion_coverage_complete: protocol_bool(lifecycle, "completion_coverage_complete")?,
    };
    let completions = result
        .get("completions")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_result_corrupt",
                "provider result completions must be an array",
            )
        })?;
    if completions.len() as u64 != evidence.admitted_case_count {
        return Err(admission_error(
            "admitted_runner_result_corrupt",
            "provider completion count does not match admitted case count",
        ));
    }
    if !protocol_bool(quiescence, "complete")?
        || !evidence.quiescent()
        || !evidence.terminal_coverage_complete
        || !evidence.requested_case_coverage_complete
        || !evidence.scheduler_completed
    {
        return Err(admission_error(
            "admitted_runner_descendant_quiescence_unproven",
            "provider terminal result does not prove complete quiescence and completion coverage",
        ));
    }
    let exit_code = exit
        .get("code")
        .and_then(Value::as_i64)
        .filter(|value| *value == i64::from(returncode))
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_exit_mismatch",
                "result exit code does not match admitted CLI process",
            )
        })?;
    let error = exit.get("error").unwrap_or(&Value::Null);
    if result.get("exit_code") != Some(&json!(exit_code))
        || result.get("error").unwrap_or(&Value::Null) != error
    {
        return Err(admission_error(
            "admitted_runner_result_corrupt",
            "provider result exit projection disagrees with its exit record",
        ));
    }
    if (status == "ok") != (exit_code == 0) {
        return Err(admission_error(
            "admitted_runner_exit_mismatch",
            "provider result status disagrees with its exit code",
        ));
    }
    if exit_code != 0 && (error.is_null() || error.as_str() == Some("")) {
        return Err(admission_error(
            "admitted_runner_error_missing",
            "nonzero admitted-runner exit requires typed error evidence",
        ));
    }
    let text = |value: &Value| {
        value
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| value.to_string())
    };
    let execution = ManagedExecution {
        status: if exit_code == 0 { "ok" } else { "failed" }.into(),
        raw_exit_code: returncode,
        failure_kind: if exit_code == 0 {
            None
        } else {
            Some(
                error
                    .get("kind")
                    .map(text)
                    .filter(|value| !value.is_empty())
                    .unwrap_or_else(|| "admitted_runner_failed".into()),
            )
        },
        message: error
            .get("message")
            .map(text)
            .filter(|value| !value.is_empty())
            .or_else(|| {
                if error.is_null() || error.as_str() == Some("") {
                    None
                } else {
                    Some(text(error))
                }
            }),
        source: PROVIDER_EXECUTABLE.into(),
    };
    Ok((execution, evidence, result))
}

#[derive(Default)]
struct ManagedEvidence {
    source: Option<crate::execution_resource_plan::SourceFreezeReceipt>,
    admission: Option<crate::execution_resource_plan::RunGpuAdmissionReceipt>,
    lifecycle: Option<ManagedLifecycle>,
    effective_environment: Option<BTreeMap<String, String>>,
    primary: Option<crate::execution_resource_plan::Failure>,
    secondary: Vec<Value>,
    releases: Vec<crate::execution_resource_plan::FdReleaseEvidence>,
    attempted: std::collections::BTreeSet<&'static str>,
    chunks: Vec<String>,
    exit_code: i32,
    reservation_active: bool,
}
fn normalized_failure(error: &crate::execution_resource_plan::Failure, operation: &str) -> Value {
    json!({"schema_version":"gpu-failure/v1","kind":error.code,"operation":operation,"message":format!("{}: {}",error.code,error.message),"evidence":error.details})
}
fn evidence_fingerprint(value: &Value) -> AdmissionResult<Value> {
    if value.is_null() {
        return Ok(Value::Null);
    }
    for key in [
        "evidence_fingerprint",
        "receipt_fingerprint",
        "readback_fingerprint",
        "fingerprint",
    ] {
        if value.get(key).is_some_and(Value::is_string) {
            return Ok(value[key].clone());
        }
    }
    Ok(json!(
        crate::execution_resource_plan::canonical_fingerprint(value)?
    ))
}
fn cleanup_complete(evidence: &ManagedEvidence) -> bool {
    (!evidence.reservation_active || !evidence.releases.is_empty())
        && evidence
            .releases
            .iter()
            .all(|item| item.close_attempts == 1 && item.error_kind.is_none())
}
fn write_managed_coverage(context: &RunContext, evidence: &ManagedEvidence) -> AdmissionResult<()> {
    use crate::execution_resource_plan::{canonical_fingerprint, write_json_once};
    let source = evidence
        .source
        .as_ref()
        .map(serde_json::to_value)
        .transpose()
        .map_err(|error| admission_error("CompletionCoverageFailure", &error.to_string()))?
        .unwrap_or(Value::Null);
    let admission = evidence
        .admission
        .as_ref()
        .map(serde_json::to_value)
        .transpose()
        .map_err(|error| admission_error("CompletionCoverageFailure", &error.to_string()))?
        .unwrap_or(Value::Null);
    let lifecycle = evidence
        .lifecycle
        .as_ref()
        .map(serde_json::to_value)
        .transpose()
        .map_err(|error| admission_error("CompletionCoverageFailure", &error.to_string()))?;
    let release=evidence.releases.iter().map(|item|json!({"component":item.component,"uuid":item.uuid,"disposition":item.disposition,"close_attempts":item.close_attempts,"error_kind":item.error_kind})).collect::<Vec<_>>();
    let primary = evidence
        .primary
        .as_ref()
        .map(|error| normalized_failure(error, "managed_admission"));
    let plan = admission
        .get("plan_fingerprint")
        .cloned()
        .unwrap_or(Value::Null);
    let admission_fingerprint = admission
        .get("admission_fingerprint")
        .cloned()
        .unwrap_or(Value::Null);
    let mut outcome = json!({"schema_version":"managed-gpu-outcome/v1","run_id":context.identity.run_name,"source_freeze_fingerprint":source.get("receipt_fingerprint").unwrap_or(&Value::Null),"plan_fingerprint":plan,"admission_fingerprint":admission_fingerprint,"planned_chunk_ids":evidence.chunks,"runner_lifecycle_fingerprint":lifecycle.as_ref().map(canonical_fingerprint).transpose()?,"primary_failure":primary,"secondary_failures":evidence.secondary,"release_disposition":release,"context_state":"closed","exit_code":evidence.exit_code});
    outcome["outcome_fingerprint"] = json!(canonical_fingerprint(&outcome)?);
    let names = [
        "source_freeze_evidence",
        "lock_readback",
        "effective_environment",
        "actual_gpu_processes",
        "concurrent_run_evidence",
        "mig_evidence",
        "container_visible_uuid_mapping",
        "os_safe_lock_placement",
        "descendant_retention_evidence",
    ];
    let mut values = BTreeMap::<&str, Value>::new();
    values.insert("source_freeze_evidence", source);
    for name in &names[1..] {
        values.insert(
            name,
            if *name == "effective_environment" {
                evidence
                    .effective_environment
                    .as_ref()
                    .map(|value| json!(value))
                    .unwrap_or_else(|| admission.get(*name).cloned().unwrap_or(Value::Null))
            } else {
                admission.get(*name).cloned().unwrap_or(Value::Null)
            },
        );
    }
    let mut absences = Vec::new();
    let mut missing = Vec::new();
    for name in names {
        if values[name].is_null() {
            missing.push(name);
            let reached = evidence.attempted.contains(name);
            let mut absence = json!({"field_name":name,"disposition":if reached{"failed"}else{"not_reached"},"failure_kind":if reached{evidence.primary.as_ref().map(|error|error.code.as_str())}else{None}});
            if reached && evidence.primary.is_none() {
                return Err(admission_error(
                    "CompletionCoverageFailure",
                    "failed evidence absence requires a failure kind",
                ));
            }
            absence["fingerprint"] = json!(canonical_fingerprint(&absence)?);
            absences.push(absence);
        }
    }
    let processes = values["actual_gpu_processes"]
        .as_array()
        .map(|values| {
            values
                .iter()
                .map(evidence_fingerprint)
                .collect::<AdmissionResult<Vec<_>>>()
        })
        .transpose()?
        .unwrap_or_default();
    let mut input = json!({"schema_version":"completion-coverage/v2","outcome_fingerprint":outcome["outcome_fingerprint"],"planned_chunk_ids":evidence.chunks,"candidate_uuids":admission.get("candidate_uuids").cloned().unwrap_or_else(||json!([])),"occupied_uuids":admission.get("occupied_uuids").cloned().unwrap_or_else(||json!([])),"reserved_uuids":admission.get("reserved_uuids").cloned().unwrap_or_else(||json!([])),"selected_uuids":admission.get("selected_uuids").cloned().unwrap_or_else(||json!([])),"lock_readback":evidence_fingerprint(&values["lock_readback"] )?,"effective_environment":values["effective_environment"],"actual_gpu_processes":processes,"absence_dispositions":absences});
    for name in [
        "concurrent_run_evidence",
        "mig_evidence",
        "container_visible_uuid_mapping",
        "os_safe_lock_placement",
        "descendant_retention_evidence",
        "source_freeze_evidence",
    ] {
        input[name] = evidence_fingerprint(&values[name])?;
    }
    let input_fingerprint = canonical_fingerprint(&input)?;
    let reached_complete = missing.is_empty();
    let cleanup_complete = cleanup_complete(evidence);
    let all_chunks = reached_complete
        && !evidence.chunks.is_empty()
        && evidence.primary.is_none()
        && evidence.exit_code == 0;
    let failure = evidence.primary.as_ref().map(|error| error.code.clone());
    let mut blockers = failure
        .iter()
        .map(|kind| format!("failure:{kind}"))
        .collect::<Vec<_>>();
    blockers.extend(missing.iter().map(|name| format!("evidence_absent:{name}")));
    let mut coverage = json!({"schema_version":"completion-coverage/v2","input_fingerprint":input_fingerprint,"terminal_complete":true,"partial_complete":reached_complete,"cleanup_complete":cleanup_complete,"closeout_complete":cleanup_complete&&reached_complete,"all_planned_chunks_complete":all_chunks,"overall_delivery_complete":reached_complete&&cleanup_complete&&all_chunks,"failure_kind":failure,"unresolved_blockers":blockers});
    coverage["coverage_fingerprint"] = json!(canonical_fingerprint(&coverage)?);
    let runtime = context.paths.result.join("runtime");
    let root = crate::source_mutation::open_root_nofollow(&context.root)
        .map_err(|error| admission_error("CompletionCoverageFailure", &error.to_string()))?;
    parent_for(
        &root,
        runtime
            .join("completion_coverage.json")
            .strip_prefix(&context.root)
            .map_err(|error| admission_error("CompletionCoverageFailure", &error.to_string()))?,
        true,
    )
    .map_err(|error| admission_error("CompletionCoverageFailure", &error))?;
    write_json_once(&runtime.join("completion_coverage.json"), &coverage, false)?;
    let projection = crate::execution_resource_projection::project_terminal_outcome(
        &outcome,
        if admission.is_null() {
            None
        } else {
            Some(&admission)
        },
    )
    .map_err(|error| admission_error("CompletionCoverageFailure", error.message()))?;
    let directory = crate::runtime_boundary::RuntimeDirectory::open_nofollow(&runtime, false)
        .map_err(|error| admission_error("CompletionCoverageFailure", &error.to_string()))?;
    use std::io::Write;
    let mut file = directory
        .create_file_once(Path::new("post_tool_use_projection.json"), 0o666)
        .map_err(|error| admission_error("CompletionCoverageFailure", &error.to_string()))?;
    file.write_all(&projection)
        .map_err(|error| admission_error("CompletionCoverageFailure", &error.to_string()))?;
    Ok(())
}

fn config_field<'a>(config: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    crate::experiment_identity::json_field(config, key)
}
fn config_integer(config: &JsonValue, key: &str, default: u64) -> Result<u64> {
    match config_field(config, key) {
        None => Ok(default),
        Some(JsonValue::Number(crate::python_json::JsonNumber::Integer(value))) => {
            use num_traits::ToPrimitive;
            crate::python_cli_integer::parse(value)
                .and_then(|value| value.to_u64())
                .ok_or_else(|| format!("{key} must be a non-negative integer"))
        }
        _ => Err(format!("{key} must be an integer")),
    }
}
fn config_text(config: &JsonValue, key: &str, default: &str) -> Result<String> {
    match config_field(config, key) {
        None => Ok(default.into()),
        Some(JsonValue::String(value)) => value
            .to_text()
            .ok_or_else(|| format!("{key} must be valid Unicode")),
        Some(value) => String::from_utf8(python_json::python_json_ascii_bytes(value)?)
            .map_err(|error| error.to_string()),
    }
}
fn config_chunks(config: &JsonValue, name: &str) -> Result<Vec<String>> {
    match config_field(config, "requested_chunks") {
        None => Ok(vec![name.into()]),
        Some(JsonValue::Array(values)) if !values.0.is_empty() => values
            .0
            .iter()
            .map(|value| match value {
                JsonValue::String(value) if !value.is_empty() => value
                    .to_text()
                    .ok_or_else(|| "requested_chunks must contain valid Unicode strings".into()),
                _ => Err("requested_chunks must be a non-empty array of strings".into()),
            })
            .collect(),
        _ => Err("requested_chunks must be a non-empty array of strings".into()),
    }
}
fn resource_request(
    context: &RunContext,
    config: &JsonValue,
    observation: &crate::execution_resource_plan::ResourceObservation,
) -> Result<crate::execution_resource_plan::ResourceRequest> {
    let config = config_field(config, "config").unwrap_or(config);
    let gpu = config_integer(config, "gpu_requested_count", 0)?;
    let gpu_count = usize::try_from(gpu).map_err(|error| error.to_string())?;
    let provenance = config_text(config, "gpu_allocation_provenance", "")?;
    if gpu_count > 0
        && ![
            "",
            crate::execution_resource_plan::CALLER_ALLOCATION_PROVENANCE,
        ]
        .contains(&provenance.as_str())
    {
        return Err("gpu_allocation_provenance_conflict: managed GPU execution cannot override canonical scheduler UUID provenance".into());
    }
    let cpus = match config_field(config, "cpu_requested_set") {
        None => observation.cpu_available_set.clone(),
        Some(JsonValue::Array(values)) => {
            use num_traits::ToPrimitive;
            let mut cpus = values
                .0
                .iter()
                .map(|value| match value {
                    JsonValue::Number(crate::python_json::JsonNumber::Integer(value)) => {
                        crate::python_cli_integer::parse(value)
                            .and_then(|value| value.to_u32())
                            .ok_or_else(|| "cpu_requested_set must contain integers".to_owned())
                    }
                    _ => Err("cpu_requested_set must contain integers".to_owned()),
                })
                .collect::<Result<Vec<_>>>()?;
            cpus.sort();
            cpus
        }
        _ => return Err("cpu_requested_set must contain integers".into()),
    };
    let timeout = match config_field(config, "maximum_timeout_seconds") {
        None => 3600.0,
        Some(JsonValue::Number(crate::python_json::JsonNumber::Float(value))) => *value,
        Some(JsonValue::Number(crate::python_json::JsonNumber::Integer(value))) => {
            value.parse::<f64>().map_err(|error| error.to_string())?
        }
        _ => return Err("maximum_timeout_seconds must be a positive number".into()),
    };
    Ok(crate::execution_resource_plan::ResourceRequest {
        integration_contract: managed_interface()?,
        xla_jax_preallocation_values: BTreeMap::new(),
        owner_id: config_text(config, "owner_id", "worker-luna")?,
        parent_id: config_text(config, "parent_id", "parent-sol")?,
        context_id: config_text(config, "context_id", "context-continuation")?,
        maximum_timeout_seconds: timeout,
        argv: context.command.clone(),
        cwd: context.root.clone(),
        environment: run_environment(context),
        plan_id: context.identity.run_name.clone(),
        cpu_requested_set: cpus,
        gpu_requested_count: gpu_count,
        gpu_requested_memory_bytes: config_integer(config, "gpu_requested_memory_bytes", 0)?,
        gpu_allocation_provenance: if gpu_count > 0 {
            crate::execution_resource_plan::CALLER_ALLOCATION_PROVENANCE.into()
        } else {
            String::new()
        },
        host_memory_bytes: 0,
        temp_bytes: config_integer(config, "temp_bytes", 0)?,
        ports: Vec::new(),
        runtime_root: "/var/lib/agent-canon/runtime".into(),
        source_projection_root: Some(PathBuf::from(format!(
            "/workspace/reports/agents/{}/runtime",
            context.identity.run_name
        ))),
        run_id: context.identity.run_name.clone(),
        requested_chunks: config_chunks(config, &context.identity.run_name)?,
        lock_root: "/var/lib/agent-canon/runtime/locks".into(),
        lock_namespace_shared_across_schedulers: true,
        lock_namespace_host_safe: true,
        lock_namespace_visibility_witness: "container-local-shared-lock".into(),
        owner_process_start_identity: String::new(),
    })
}
fn build_provider_request(
    context: &RunContext,
    request: &crate::execution_resource_plan::ResourceRequest,
    plan: &crate::execution_resource_plan::ExecutionResourcePlan,
    environment: &crate::execution_resource_plan::AdmittedEnvironment,
    source_paths: &[String],
) -> AdmissionResult<(PathBuf, PathBuf, Value)> {
    let entrypoint = format!("experiments/{}/run.py", context.identity.topic);
    if !source_paths.contains(&entrypoint) {
        return Err(admission_error(
            "gpu_source_freeze_manifest_incomplete",
            "canonical topic entrypoint is absent from source membership",
        ));
    }
    let absolute = context
        .root
        .join(&entrypoint)
        .to_string_lossy()
        .into_owned();
    let matches = context
        .command
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            if value == &entrypoint || value == &absolute {
                Some(index)
            } else {
                None
            }
        })
        .collect::<Vec<_>>();
    let interpreter = context
        .command
        .first()
        .and_then(|value| Path::new(value).file_name())
        .and_then(|value| value.to_str())
        .unwrap_or("");
    let python = ["python", "python3"].contains(&interpreter)
        || interpreter.strip_prefix("python3.").is_some_and(|version| {
            !version.is_empty() && version.bytes().all(|byte| byte.is_ascii_digit())
        });
    if matches != [1] || !python {
        return Err(admission_error(
            "managed_command_entrypoint_mismatch",
            "selected managed command must invoke the exact topic run.py with Python",
        ));
    }
    let allocation = plan.gpu_allocation();
    let selected = &allocation.selected_ids;
    let exact = environment
        .exact_env_map
        .iter()
        .cloned()
        .collect::<BTreeMap<_, _>>();
    let mut payload = context.identity.to_value();
    payload.as_object_mut().expect("identity object").extend(json!({"schema":"agentcanon-managed-run/v1","run_id":context.identity.run_name,"task":{"module":format!("experiments.{}.run",context.identity.topic),"callable":"main"},"cases":[{"argv":context.command[2..],"entrypoint_relative_path":entrypoint}],"environment":exact,"capacity":{"max_workers":1,"host_memory_bytes":request.host_memory_bytes,"gpu_devices":selected.iter().map(|uuid|json!({"gpu_id":uuid,"memory_bytes":allocation.memory_bytes.get(uuid).copied().unwrap_or(0),"max_slots":1})).collect::<Vec<_>>()},"resource_estimate":{"host_memory_bytes":request.host_memory_bytes,"gpu_count":request.gpu_requested_count,"gpu_memory_bytes":request.gpu_requested_memory_bytes,"gpu_slots":1},"selected_gpu_ids":selected,"metadata":{"agentcanon_provider_contract":provider_contract().map_err(|error|admission_error("admitted_runner_cli_missing",&error))?,"agentcanon_admission_fingerprint":environment.admission_fingerprint,"agentcanon_plan_fingerprint":plan.plan_fingerprint(),"agentcanon_source_paths":source_paths,"agentcanon_source_snapshot_root":context.paths.result.join("source_snapshot"),"agentcanon_working_directory":context.paths.result.join("source_snapshot"),"agentcanon_output_directory":context.paths.result,"agentcanon_lifecycle_artifact_path":context.paths.result.join("runtime/managed-run-lifecycle.json"),"agentcanon_selected_uuids":selected}}).as_object().expect("managed request").clone());
    payload["fingerprint"] = json!(crate::execution_resource_plan::canonical_fingerprint(
        &payload
    )?);
    let request_path = context
        .paths
        .result
        .join("runtime/managed-run-request.json");
    let result_path = context.paths.result.join("runtime/managed-run-result.json");
    write_value(context, &request_path, &payload)
        .map_err(|error| admission_error("admitted_runner_request_write_failed", &error))?;
    Ok((request_path, result_path, payload))
}

fn launch_provider(
    context: &RunContext,
    request_path: &Path,
    result_path: &Path,
    lifecycle_path: &Path,
    request: &Value,
    environment: &BTreeMap<String, String>,
) -> AdmissionResult<(ManagedExecution, ManagedLifecycle)> {
    use std::fs::OpenOptions;
    let configured = std::env::var("AGENT_CANON_EXPERIMENT_RUNNER_ADMITTED")
        .unwrap_or_else(|_| PROVIDER_EXECUTABLE.into());
    let executable = crate::tool_dispatch::find_executable(&configured)
        .or_else(|| {
            let path = Path::new(&configured);
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if path.is_file()
                    && std::fs::metadata(path)
                        .is_ok_and(|metadata| metadata.permissions().mode() & 0o111 != 0)
                {
                    return std::fs::canonicalize(path).ok();
                }
            }
            None
        })
        .ok_or_else(|| {
            admission_error(
                "admitted_runner_cli_missing",
                "experiment-runner-admitted CLI is unavailable",
            )
        })?;
    let stdout = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&context.paths.stdout)
        .map_err(|error| admission_error("admitted_runner_launch_failed", &error.to_string()))?;
    let stderr = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&context.paths.stderr)
        .map_err(|error| admission_error("admitted_runner_launch_failed", &error.to_string()))?;
    let mut process = Command::new(&executable)
        .arg("--request")
        .arg(request_path)
        .arg("--result")
        .arg(result_path)
        .current_dir(context.paths.result.join("source_snapshot"))
        .env_clear()
        .envs(environment)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .map_err(|_| {
            admission_error(
                "admitted_runner_launch_failed",
                "experiment-runner-admitted could not be launched",
            )
        })?;
    let process_status = process
        .wait()
        .map_err(|error| admission_error("admitted_runner_launch_failed", &error.to_string()))?;
    #[cfg(unix)]
    let process_returncode = {
        use std::os::unix::process::ExitStatusExt;
        process_status
            .code()
            .unwrap_or_else(|| -process_status.signal().unwrap_or(1))
    };
    #[cfg(not(unix))]
    let process_returncode = process_status.code().unwrap_or(1);
    let (execution, lifecycle, result) =
        validate_provider_result(result_path, request, process_returncode)?;

    let mut lifecycle_payload = serde_json::to_value(&lifecycle).map_err(|error| {
        admission_error(
            "experiment_runner_lifecycle_write_failed",
            &error.to_string(),
        )
    })?;
    lifecycle_payload
        .as_object_mut()
        .expect("lifecycle object")
        .extend(
            context
                .identity
                .to_value()
                .as_object()
                .expect("identity object")
                .clone(),
        );
    write_value(context, lifecycle_path, &lifecycle_payload)
        .map_err(|error| admission_error("experiment_runner_lifecycle_write_failed", &error))?;
    let result_fingerprint = crate::execution_resource_plan::canonical_fingerprint(&result)
        .map_err(|error| admission_error("admitted_runner_result_corrupt", &error.message))?;
    let receipt = json!({
        "schema_version":"agentcanon-managed-run-receipt/v1",
        "provider_contract":provider_contract().map_err(|error|admission_error("admitted_runner_cli_missing",&error))?,
        "executable":PROVIDER_EXECUTABLE,
        "resolved_executable":executable,
        "argv":[executable,"--request",request_path,"--result",result_path],
        "request_fingerprint":request["fingerprint"],
        "result_content_fingerprint":result_fingerprint,
        "process_returncode":process_returncode,
        "worker_pid":lifecycle.child_process_ids.first().copied(),
        "identity":context.identity.to_value()["identity"],
    });
    let receipt_path = context
        .paths
        .result
        .join("runtime/managed-run-receipt.json");
    write_value(context, &receipt_path, &receipt)
        .map_err(|error| admission_error("managed_run_receipt_write_failed", &error))?;
    Ok((execution, lifecycle))
}

fn execute_managed_run(
    context: &RunContext,
    config: &JsonValue,
) -> AdmissionResult<ManagedExecution> {
    use crate::execution_resource_plan::{
        build_admitted_environment, canonical_fingerprint, discover_resources, process_occupancy,
        AbsolutePosixPath, ExecutionResourcePlan, GpuAllocation, GpuReservationTransaction,
        GpuRunRequest, RunGpuAdmissionReceipt,
    };
    use crate::execution_source_freeze::SourceFreezeOwner;
    use std::os::unix::fs::MetadataExt;

    let mut request = resource_request(
        context,
        config,
        &discover_resources(&run_environment(context), 0)?,
    )
    .map_err(|error| admission_error("managed_resource_request_invalid", &error))?;
    let source_paths = crate::execution_source_freeze::source_path_set(
        &context.root,
        &context.identity.topic,
        &context.command,
    )?;
    let source_request = GpuRunRequest {
        gpu_count: request.gpu_requested_count,
        minimum_memory_bytes_per_unit: request.gpu_requested_memory_bytes,
        max_workers: 1,
        host_memory_bytes: request.host_memory_bytes,
        cuda_runtime_library_path: config_field(
            config_field(config, "config").unwrap_or(config),
            "cuda_runtime_library_path",
        )
        .and_then(|value| match value {
            JsonValue::String(value) => value.to_text(),
            _ => None,
        }),
        environment: request.environment.clone(),
        source_root: AbsolutePosixPath::parse(&context.root.to_string_lossy())?,
        runtime_route: "MANAGED_CONTAINER".into(),
        source_paths: source_paths.clone(),
        planned_chunk_ids: request.requested_chunks.clone(),
    };
    let mut evidence = ManagedEvidence {
        chunks: request.requested_chunks.clone(),
        ..ManagedEvidence::default()
    };
    evidence.attempted.insert("source_freeze_evidence");
    let mut source_owner = SourceFreezeOwner::new(AbsolutePosixPath::parse(
        &context.paths.result.to_string_lossy(),
    )?);
    let mut source_frozen = false;
    let mut reservation_transaction: Option<GpuReservationTransaction> = None;
    let mut runner_started = false;
    let phase_result = (|| -> AdmissionResult<ManagedExecution> {
        let source = source_owner.freeze(&source_request)?;
        source_frozen = true;
        evidence.source = Some(source.clone());

        let initial_observation =
            discover_resources(&request.environment, request.gpu_requested_count)?;
        let mut runtime_route = None;
        let mut namespace_inode = 0u64;
        let mut runtime_identity_fingerprint = String::new();
        let mut admission = None;
        let mut allocation;
        let final_observation;
        if request.gpu_requested_count > 0 {
            runtime_route = request
                .environment
                .get("AGENT_CANON_RUNTIME_ROUTE")
                .cloned();
            if runtime_route.as_deref() != Some("MANAGED_CONTAINER") {
                return Err(admission_error(
                    "runtime_identity_route_invalid",
                    "managed GPU admission requires the selected project runtime route",
                ));
            }
            namespace_inode = std::fs::metadata("/proc/self/ns/pid")
                .map_err(|error| {
                    admission_error("gpu_namespace_identity_unproven", &error.to_string())
                })?
                .ino();
            runtime_identity_fingerprint = canonical_fingerprint(
                &json!({"runtime_route":runtime_route,"namespace_id":format!("pid:[{namespace_inode}]")}),
            )?;
            let inventory = initial_observation
                .nvidia_inventory
                .as_ref()
                .ok_or_else(|| {
                    admission_error(
                        "gpu_inventory_unproven",
                        "GPU admission requires the strict NVIDIA inventory owner output",
                    )
                })?;
            let first = process_occupancy(
                inventory,
                namespace_inode,
                &initial_observation.process_identities,
                &initial_observation.unknown_gpu_ids,
                false,
                if initial_observation.process_identities.is_empty() {
                    "COMPLETE_EMPTY"
                } else {
                    "COMPLETE"
                },
            )?;
            let candidates = initial_observation
                .caller_allocated_ids
                .iter()
                .cloned()
                .collect::<Vec<_>>();
            let occupied = first
                .occupied_uuids
                .iter()
                .cloned()
                .collect::<std::collections::BTreeSet<_>>();
            let unknown = first
                .unknown_uuids
                .iter()
                .cloned()
                .collect::<std::collections::BTreeSet<_>>();
            let eligible = candidates
                .iter()
                .filter(|uuid| {
                    !occupied.contains(*uuid)
                        && !unknown.contains(*uuid)
                        && initial_observation
                            .free_memory_bytes
                            .get(*uuid)
                            .copied()
                            .unwrap_or(0)
                            >= request.gpu_requested_memory_bytes
                })
                .cloned()
                .collect::<Vec<_>>();
            let mut transaction = GpuReservationTransaction::new(
                &AbsolutePosixPath::parse(&request.lock_root.to_string_lossy())?,
                &AbsolutePosixPath::parse(&request.runtime_root.to_string_lossy())?,
            )?;
            evidence.attempted.insert("lock_readback");
            let reservation =
                transaction.try_reserve(&eligible, &occupied, request.gpu_requested_count)?;
            let reservation_ids = transaction.reservation_ids();
            evidence.reservation_active = !reservation.selected_uuids.is_empty();
            reservation_transaction = Some(transaction);
            if reservation.disposition != "ACQUIRED"
                || reservation.selected_uuids.len() != request.gpu_requested_count
            {
                return Err(admission_error(
                    "gpu_candidate_unavailable",
                    "the exact UUID candidate frontier could not satisfy the request",
                ));
            }
            let observed = discover_resources(&request.environment, request.gpu_requested_count)?;
            if observed.observation_event_id == initial_observation.observation_event_id {
                return Err(admission_error(
                    "gpu_run_admission_raced",
                    "final NVIDIA evidence did not provide a new admission snapshot",
                ));
            }
            let final_inventory = observed.nvidia_inventory.as_ref().ok_or_else(|| {
                admission_error(
                    "gpu_inventory_unproven",
                    "GPU admission requires the strict final NVIDIA inventory owner output",
                )
            })?;
            evidence.attempted.insert("actual_gpu_processes");
            let last = process_occupancy(
                final_inventory,
                namespace_inode,
                &observed.process_identities,
                &observed.unknown_gpu_ids,
                false,
                if observed.process_identities.is_empty() {
                    "COMPLETE_EMPTY"
                } else {
                    "COMPLETE"
                },
            )?;
            let occupied_final = last
                .occupied_uuids
                .iter()
                .cloned()
                .collect::<std::collections::BTreeSet<_>>();
            let unknown_final = last
                .unknown_uuids
                .iter()
                .cloned()
                .collect::<std::collections::BTreeSet<_>>();
            if reservation.selected_uuids.iter().any(|uuid| {
                !observed.caller_allocated_ids.contains(uuid)
                    || occupied_final.contains(uuid)
                    || unknown_final.contains(uuid)
                    || observed.free_memory_bytes.get(uuid).copied().unwrap_or(0)
                        < request.gpu_requested_memory_bytes
            }) {
                return Err(admission_error(
                    "gpu_run_admission_raced",
                    "final UUID, occupancy, or memory evidence changed after reservation",
                ));
            }
            let selected = reservation.selected_uuids.clone();
            let readback = reservation.locks.first().cloned().ok_or_else(|| {
                admission_error(
                    "gpu_lock_readback_missing",
                    "GPU reservation returned no lock readback for an acquired reservation",
                )
            })?;
            evidence.attempted.extend([
                "concurrent_run_evidence",
                "mig_evidence",
                "os_safe_lock_placement",
            ]);
            let final_eligible = observed
                .caller_allocated_ids
                .iter()
                .filter(|uuid| {
                    !occupied_final.contains(*uuid)
                        && !unknown_final.contains(*uuid)
                        && observed.free_memory_bytes.get(*uuid).copied().unwrap_or(0)
                            >= request.gpu_requested_memory_bytes
                })
                .cloned()
                .collect::<Vec<_>>();
            let lock_value = json!({
                "reservation_owner":"GpuReservationTransaction",
                "reservation_evidence_fingerprint":reservation.evidence_fingerprint,
                "initial_observation_fingerprint":initial_observation.fingerprint,
                "admission_observation_fingerprint":observed.fingerprint,
                "final_eligible_ids":&final_eligible,
            });
            let readback_fingerprint = canonical_fingerprint(&lock_value)?;
            let memory_bytes = observed
                .gpu_devices
                .iter()
                .filter(|device| selected.contains(&device.uuid))
                .map(|device| (device.uuid.clone(), device.memory_bytes))
                .collect::<BTreeMap<_, _>>();
            allocation = GpuAllocation {
                plan_fingerprint: "pending".into(),
                caller_allocated_ids: candidates.clone(),
                candidate_ids: candidates.clone(),
                occupied_ids: occupied_final
                    .iter()
                    .chain(unknown_final.iter())
                    .cloned()
                    .collect::<std::collections::BTreeSet<_>>()
                    .into_iter()
                    .collect(),
                reserved_ids: Vec::new(),
                eligible_ids: final_eligible.clone(),
                selected_ids: selected.clone(),
                reservation_ids,
                free_memory_bytes: observed.free_memory_bytes.clone(),
                occupied_process_identities: observed.process_identities.clone(),
                process_identities: observed.process_identities.clone(),
                allocation_id: reservation.evidence_fingerprint.clone(),
                lock_root: request.lock_root.clone(),
                selection_order: final_eligible,
                memory_bytes,
                slot_id: None,
                requested_count: request.gpu_requested_count,
                requested_memory_bytes: request.gpu_requested_memory_bytes,
                readback_fingerprint: readback_fingerprint.clone(),
                lock_readback: lock_value,
                allocation_provenance: request.gpu_allocation_provenance.clone(),
                admission_fingerprint: None,
            };
            let mut occupancy_hash = Sha256::new();
            occupancy_hash.update(initial_observation.fingerprint.as_bytes());
            occupancy_hash.update(b"|");
            occupancy_hash.update(observed.fingerprint.as_bytes());
            let mut receipt = RunGpuAdmissionReceipt {
                schema_version: "gpu-admission/v1".into(),
                candidate_uuids: candidates,
                occupied_uuids: occupied_final.iter().cloned().collect(),
                reserved_uuids: allocation.reserved_ids.clone(),
                selected_uuids: selected.clone(),
                inventory_fingerprint: final_inventory.evidence_fingerprint.clone(),
                occupancy_fingerprint: format!("{:x}", occupancy_hash.finalize()),
                reservation_fingerprint: readback_fingerprint,
                runtime_identity_fingerprint: runtime_identity_fingerprint.clone(),
                plan_fingerprint: None,
                admission_fingerprint: String::new(),
                lock_readback: Some(readback.clone()),
                effective_environment: None,
                actual_gpu_processes: Some(vec![first.clone(), last.clone()]),
                concurrent_run_evidence: Some(json!({
                    "initial_snapshot_fingerprint":initial_observation.fingerprint,
                    "admission_snapshot_fingerprint":observed.fingerprint,
                    "final_snapshot_fingerprint":observed.fingerprint,
                    "initial_event_id":initial_observation.observation_event_id,
                    "admission_event_id":observed.observation_event_id,
                    "final_event_id":observed.observation_event_id,
                    "fingerprint":canonical_fingerprint(&json!({"initial":initial_observation.fingerprint,"admission":observed.fingerprint,"final":observed.fingerprint}))?
                })),
                mig_evidence: Some(json!({
                    "parent_by_uuid":final_inventory.joins.iter().map(|join| (join.mig_uuid.clone(), join.parent_uuid.clone())).collect::<BTreeMap<_,_>>(),
                    "executable_leaf_uuids":final_inventory.mig_uuids,
                    "selected_physical_uuids":selected.iter().filter(|uuid| final_inventory.physical_uuids.contains(uuid)).collect::<Vec<_>>(),
                    "fingerprint":canonical_fingerprint(&json!({
                        "parents":final_inventory.joins.iter().map(|join| (join.mig_uuid.clone(), join.parent_uuid.clone())).collect::<Vec<_>>(),
                        "leaves":final_inventory.mig_uuids
                    }))?
                })),
                container_visible_uuid_mapping: None,
                os_safe_lock_placement: Some(json!({
                    "runtime_root":readback.runtime_root,
                    "filesystem_type":readback.filesystem_type,
                    "filesystem_source":request.lock_root,
                    "device":readback.device,
                    "inode":readback.inode,
                    "group_name":"agent-canon-runtime",
                    "mode":"0660",
                    "local_flock_filesystem":true,
                    "fingerprint":canonical_fingerprint(&json!({"runtime_root":readback.runtime_root,"filesystem_type":readback.filesystem_type,"filesystem_source":request.lock_root,"device":readback.device,"inode":readback.inode,"mode":"0660"}))?
                })),
                descendant_retention_evidence: None,
            };
            receipt.refresh_fingerprint()?;
            allocation.admission_fingerprint = Some(receipt.admission_fingerprint.clone());
            admission = Some(receipt);
            evidence.admission = admission.clone();
            final_observation = observed;
        } else {
            final_observation = initial_observation.clone();
            allocation = GpuAllocation {
                plan_fingerprint: "pending".into(),
                caller_allocated_ids: Vec::new(),
                candidate_ids: Vec::new(),
                occupied_ids: Vec::new(),
                reserved_ids: Vec::new(),
                eligible_ids: Vec::new(),
                selected_ids: Vec::new(),
                reservation_ids: Vec::new(),
                free_memory_bytes: BTreeMap::new(),
                occupied_process_identities: Vec::new(),
                process_identities: Vec::new(),
                allocation_id: "none".into(),
                lock_root: request.lock_root.clone(),
                selection_order: Vec::new(),
                memory_bytes: BTreeMap::new(),
                slot_id: None,
                requested_count: 0,
                requested_memory_bytes: 0,
                readback_fingerprint: canonical_fingerprint(&json!("gpu-unrequested"))?,
                lock_readback: json!({"reservation_owner":"GpuReservationTransaction","gpu_requested":false}),
                allocation_provenance: "not_applicable".into(),
                admission_fingerprint: None,
            };
        }
        if request.gpu_requested_count > 0 {
            request.environment.remove("CUDA_VISIBLE_DEVICES");
            request.environment.remove("NVIDIA_VISIBLE_DEVICES");
        }
        request.cwd = context.paths.result.join("source_snapshot");
        let plan = ExecutionResourcePlan::freeze(&request, &final_observation, allocation)?;
        if let Some(receipt) = admission.as_mut() {
            receipt.plan_fingerprint = Some(plan.plan_fingerprint().to_owned());
        }
        evidence.admission = admission.clone();
        evidence.attempted.insert("effective_environment");
        if request.gpu_requested_count > 0 {
            evidence.attempted.insert("container_visible_uuid_mapping");
        }
        let admitted = build_admitted_environment(
            &plan,
            runtime_route.as_deref(),
            admission
                .as_ref()
                .map(|receipt| receipt.admission_fingerprint.as_str()),
        )?;
        let environment = admitted
            .exact_env_map
            .iter()
            .cloned()
            .collect::<BTreeMap<_, _>>();
        evidence.effective_environment = Some(environment.clone());
        if let Some(receipt) = admission.as_mut() {
            receipt.effective_environment = Some(environment.clone());
            let visibility = json!({
                "cuda_visible_devices":admitted.cuda_visible_devices,
                "nvidia_visible_devices":admitted.nvidia_visible_devices,
                "disposition":"explicit",
                "visible_uuids":plan.gpu_allocation().selected_ids,
                "namespace_id":format!("pid:[{namespace_inode}]"),
                "runtime_identity_fingerprint":runtime_identity_fingerprint,
            });
            receipt.container_visible_uuid_mapping = Some(json!({
                "cuda_visible_devices":visibility["cuda_visible_devices"],
                "nvidia_visible_devices":visibility["nvidia_visible_devices"],
                "disposition":visibility["disposition"],
                "visible_uuids":visibility["visible_uuids"],
                "namespace_id":visibility["namespace_id"],
                "runtime_identity_fingerprint":visibility["runtime_identity_fingerprint"],
                "fingerprint":canonical_fingerprint(&visibility)?,
            }));
        }
        evidence.admission = admission.clone();
        evidence.attempted.insert("effective_environment");
        if request.gpu_requested_count > 0 {
            evidence.attempted.insert("os_safe_lock_placement");
        }
        let (request_path, result_path, payload) =
            build_provider_request(context, &request, &plan, &admitted, &source_paths)?;
        let lifecycle_path = context
            .paths
            .result
            .join("runtime/managed-run-lifecycle.json");
        runner_started = true;
        if request.gpu_requested_count > 0 {
            evidence.attempted.insert("descendant_retention_evidence");
        }
        let (execution, lifecycle) = launch_provider(
            context,
            &request_path,
            &result_path,
            &lifecycle_path,
            &payload,
            &environment,
        )?;
        evidence.lifecycle = Some(lifecycle);
        evidence.exit_code = execution.raw_exit_code;
        Ok(execution)
    })();
    let mut result_error = phase_result.as_ref().err().cloned();
    let execution = phase_result.ok();
    if let Some(error) = result_error.as_ref() {
        evidence.primary = Some(error.clone());
        evidence.exit_code = 1;
    } else if let Some(execution) = execution.as_ref() {
        evidence.exit_code = execution.raw_exit_code;
    }
    if runner_started && request.gpu_requested_count > 0 {
        evidence.attempted.insert("descendant_retention_evidence");
        if let Some(receipt) = evidence.admission.as_mut() {
            let lifecycle = evidence.lifecycle.as_ref();
            let quiescent = lifecycle.is_some_and(ManagedLifecycle::quiescent);
            receipt.descendant_retention_evidence = Some(json!({
                "child_process_ids":lifecycle.map(|value| &value.child_process_ids),
                "process_group_ids":lifecycle.map(|value| &value.process_group_ids),
                "descendant_quiescence":if quiescent{"PROVEN"}else{"UNPROVEN"},
                "retained_gpu_process_uuids":[],
                "release_blocked":!quiescent,
                "fingerprint":canonical_fingerprint(&json!({"runner_lifecycle":lifecycle,"quiescent":quiescent}))?
            }));
        }
    }
    if let Some(transaction) = reservation_transaction.as_mut() {
        let safe_to_close = !runner_started
            || evidence
                .lifecycle
                .as_ref()
                .is_some_and(ManagedLifecycle::quiescent);
        if safe_to_close {
            match transaction.close() {
                Ok(releases) => evidence.releases = releases,
                Err(error) => {
                    if result_error.is_none() {
                        result_error = Some(error.clone());
                    }
                    evidence
                        .secondary
                        .push(normalized_failure(&error, "gpu_reservation_close"));
                }
            }
        } else if let Some(transaction) = reservation_transaction.take() {
            drop(transaction);
        }
    }
    if source_frozen {
        if let Err(error) = source_owner.close() {
            if result_error.is_none() {
                result_error = Some(error.clone());
            }
            evidence
                .secondary
                .push(normalized_failure(&error, "source_freeze_close"));
        }
    }
    if let Some(error) = result_error.as_ref() {
        evidence.primary = Some(error.clone());
        evidence.exit_code = 1;
    }
    write_managed_coverage(context, &evidence)?;
    if let Some(error) = result_error {
        return Err(error);
    }
    execution.ok_or_else(|| {
        admission_error(
            "managed_execution_result_missing",
            "managed provider returned no typed execution result",
        )
    })
}

fn run_cli(options: Options) -> Result<i32> {
    use std::time::Instant;
    let context = build_context(&options)?;
    if context.command.is_empty() {
        return Err("a command is required".into());
    }
    let patterns = eval_patterns(&context.registry)?;
    let explicit = parse_config(&options)?;
    let mut manifest = build_manifest(&context)?;
    let mut config = build_config(&context, explicit)?;
    let reservation = reserve_paths(&context, options.skip_report)?;
    let start = Instant::now();
    let source_config = match write_initial_artifacts(&context, &mut manifest, &mut config) {
        Ok(value) => value,
        Err(error) => {
            reservation.rollback();
            return Err(error);
        }
    };
    if !reservation.release_marker() {
        return Err(
            "reservation marker ownership changed before initial artifacts completed".into(),
        );
    }
    if source_config.get("status").and_then(Value::as_str) == Some("missing") {
        let message = format!(
            "missing required source config.yaml: {}; create the checked-in topic config before running a managed experiment",
            context.topic.join("config.yaml").display()
        );
        eprintln!("{message}");
        set_field(
            &mut manifest,
            "preflight_error",
            as_python(&json!({"kind":"missing_source_config","message":message}))?,
        )?;
        startup_event(
            &context,
            "preflight_failed",
            json!({"exit_code":2,"message":message}),
        )?;
        finalize_manifest(&context, &mut manifest, start, 2, &patterns)?;
        return Ok(2);
    }
    startup_event(
        &context,
        "command_start",
        json!({"command":context.command,"command_source":context.command_source}),
    )?;
    let execution = execute_managed_run(&context, &config)
        .map_err(|error| format!("{}: {}", error.code, error.message))?;
    let exit_code = execution.raw_exit_code;
    startup_event(&context, "command_exit", json!({"exit_code":exit_code}))?;
    finalize_manifest(&context, &mut manifest, start, exit_code, &patterns)?;
    Ok(exit_code)
}

pub fn run(args: &[String]) -> i32 {
    match parse_options(args) {
        Ok(ParsedOptions::Help) => {
            println!("usage: agent-canon {SELECTOR} --topic TOPIC --variant VARIANT [options] -- COMMAND ...");
            0
        }
        Ok(ParsedOptions::Run(options)) => match run_cli(*options) {
            Ok(code) => code,
            Err(error) => {
                eprintln!("{error}");
                2
            }
        },
        Err(error) => {
            eprintln!("{error}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    fn reservation_context(root: &Path, run_name: &str) -> RunContext {
        let identity = ExperimentIdentity::new("demo_topic", "formal", run_name).unwrap();
        let topic = root.join("experiments/demo_topic");
        let result = root.join(identity.result_relative_path());
        let raw = root.join(identity.raw_relative_path());
        let logs = raw.join("logs");
        RunContext {
            root: root.to_path_buf(),
            identity,
            topic,
            paths: RunPaths {
                result: result.clone(),
                raw: raw.clone(),
                logs: logs.clone(),
                report: root
                    .join("experiments/demo_topic/report")
                    .join(format!("{run_name}.md")),
                manifest: result.join("run_manifest.json"),
                eval: result.join("eval_manifest.json"),
                artifacts: result.join("artifact_manifest.json"),
                command: result.join("command.json"),
                environment: result.join("environment.json"),
                snapshot: result.join("source_snapshot.json"),
                source_config: result.join("config_source.yaml"),
                config: result.join("config.json"),
                run_log: result.join("run.log"),
                startup: logs.join("startup.jsonl"),
                stdout: logs.join("stdout.log"),
                stderr: logs.join("stderr.log"),
            },
            registry: RegistryContext {
                path: root.join("experiments/registry.toml"),
                entry: RegistryValue::Table(Vec::new()),
                defaults: RegistryValue::Table(Vec::new()),
                available: false,
            },
            command: vec!["python3".into(), "experiments/demo_topic/run.py".into()],
            command_source: "manual".into(),
            registered_match: None,
            created: "2026-01-01T00:00:00Z".into(),
            branch: Some("main".into()),
            commit: Some("a".repeat(40)),
            status: Vec::new(),
        }
    }

    fn protocol_request() -> Value {
        ExperimentIdentity::new("demo_topic", "formal", "managed-run")
            .unwrap()
            .to_value()
            .as_object()
            .map(|identity| {
                let mut request = identity.clone();
                request.extend(json!({"schema":"agentcanon-managed-run/v1","run_id":"managed-run","fingerprint":"a".repeat(64)}).as_object().unwrap().clone());
                Value::Object(request)
            })
            .unwrap()
    }

    fn protocol_result(request: &Value) -> Value {
        let pid = 42u64;
        json!({
            "schema":"agentcanon-managed-run-result/v1",
            "identity":request["identity"],
            "run_id":request["run_id"],
            "request_fingerprint":request["fingerprint"],
            "status":"ok",
            "worker_pid":pid,
            "worker_pids":[pid],
            "lifecycle":{
                "run_id":request["run_id"],
                "terminal_event_id":"terminal-1",
                "observed_at_ns":1,
                "terminal_status":"finished",
                "total_case_count_at_start":1,
                "completion_count_before":0,
                "completion_count_after":1,
                "scheduler_completed":true,
                "admitted_case_count":1,
                "terminal_notification_count":1,
                "child_process_ids":[pid],
                "process_group_ids":[pid],
                "terminal_coverage_complete":true,
                "requested_case_coverage_complete":true,
                "quiescence_complete":true,
                "completion_coverage_complete":true,
                "descendant_quiescence":"proved",
                "cleanup_failures":[]
            },
            "descendant_quiescence":"proved",
            "quiescence":{
                "direct_children_quiescent":true,
                "descendant_quiescence":"proved",
                "complete":true,
                "cleanup_failures":[]
            },
            "exit":{"code":0,"error":null},
            "exit_code":0,
            "error":null,
            "completions":[{"case":{},"result":{"status":"ok"}}]
        })
    }

    fn validate_fixture(result: &Value) -> AdmissionResult<()> {
        let root = tempfile::tempdir()
            .map_err(|error| admission_error("fixture_write_failed", &error.to_string()))?;
        let path = root.path().join("result.json");
        std::fs::write(&path, serde_json::to_vec(result).unwrap())
            .map_err(|error| admission_error("fixture_write_failed", &error.to_string()))?;
        let request = protocol_request();
        validate_provider_result(&path, &request, 0).map(|_| ())
    }

    #[test]
    fn provider_result_accepts_only_matching_schema_identity_fingerprint_and_quiescence() {
        let request = protocol_request();
        let valid = protocol_result(&request);
        assert!(validate_fixture(&valid).is_ok());

        let mut wrong_schema = valid.clone();
        wrong_schema["schema"] = json!("agentcanon-managed-run-result/v2");
        assert_eq!(
            validate_fixture(&wrong_schema).unwrap_err().code,
            "admitted_runner_result_schema_mismatch"
        );

        let mut wrong_fingerprint = valid.clone();
        wrong_fingerprint["request_fingerprint"] = json!("b".repeat(64));
        assert_eq!(
            validate_fixture(&wrong_fingerprint).unwrap_err().code,
            "admitted_runner_result_fingerprint_mismatch"
        );

        let mut wrong_identity = valid.clone();
        wrong_identity["identity"]["run_name"] = json!("other-run");
        assert_eq!(
            validate_fixture(&wrong_identity).unwrap_err().code,
            "admitted_runner_result_identity_mismatch"
        );

        let mut unproven_cleanup = valid;
        unproven_cleanup["lifecycle"]["quiescence_complete"] = json!(false);
        assert_eq!(
            validate_fixture(&unproven_cleanup).unwrap_err().code,
            "admitted_runner_descendant_quiescence_unproven"
        );
    }

    #[test]
    fn unproven_provider_quiescence_keeps_reservation_cleanup_blocked() {
        let mut evidence = ManagedEvidence {
            reservation_active: true,
            ..ManagedEvidence::default()
        };
        assert!(!cleanup_complete(&evidence));
        evidence
            .releases
            .push(crate::execution_resource_plan::FdReleaseEvidence {
                component: "gpu-reservation-lock".into(),
                uuid: Some("GPU-fixture".into()),
                disposition: "released".into(),
                close_attempts: 1,
                error_kind: None,
                fingerprint: "fixture".into(),
            });
        assert!(cleanup_complete(&evidence));
    }

    #[test]
    fn owned_empty_reservation_rolls_back_but_nonempty_result_is_preserved() {
        let temporary = tempfile::tempdir().expect("repository fixture");
        let root = std::fs::canonicalize(temporary.path()).expect("repository resolves");
        std::fs::create_dir_all(root.join("experiments/demo_topic"))
            .expect("topic directory creates");
        let empty = reservation_context(&root, "empty-run");
        let receipt = reserve_paths(&empty, false).expect("reservation creates");
        assert!(empty.paths.result.is_dir());
        assert!(empty.paths.raw.is_dir());
        assert!(empty.paths.report.is_file());
        assert!(receipt.rollback());
        assert!(!empty.paths.result.exists());
        assert!(!empty.paths.raw.exists());
        assert!(!empty.paths.report.exists());

        let nonempty = reservation_context(&root, "nonempty-run");
        let receipt = reserve_paths(&nonempty, false).expect("second reservation creates");
        let artifact = nonempty.paths.result.join("partial.json");
        std::fs::write(&artifact, b"{}\n").expect("partial artifact writes");
        assert!(!receipt.rollback());
        assert_eq!(std::fs::read(&artifact).unwrap(), b"{}\n");
        assert!(nonempty.paths.report.is_file());
    }

    #[test]
    fn reservation_rollback_rejects_same_bytes_marker_replacement() {
        let temporary = tempfile::tempdir().expect("repository fixture");
        let root = std::fs::canonicalize(temporary.path()).expect("repository resolves");
        std::fs::create_dir_all(root.join("experiments/demo_topic"))
            .expect("topic directory creates");
        let context = reservation_context(&root, "replaced-marker");
        let receipt = reserve_paths(&context, true).expect("reservation creates");
        let marker = context.root.join(&receipt.marker);
        let bytes = std::fs::read(&marker).expect("marker reads");
        let replacement = marker.with_file_name("replacement-marker.json");
        std::fs::write(&replacement, bytes).expect("replacement marker writes");
        std::fs::rename(&replacement, &marker).expect("replacement marker swaps in");
        use std::os::unix::fs::MetadataExt;
        assert_ne!(
            std::fs::metadata(&marker).unwrap().ino(),
            receipt.marker_id.1
        );
        assert!(!receipt.rollback());
        assert!(context.paths.result.is_dir());
        assert!(marker.is_file());
    }
}
