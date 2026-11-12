// @dependency-start
// contract implementation
// responsibility Materializes a canonical experiment topic and appends its registry entry.
// upstream design ../../../../../../documents/experiments/experiment-registry.md defines the consumer registry contract
// upstream design ../../../../../../documents/design/experiment-topic-template.md defines the Python and C++ template profiles
// upstream implementation ../experiment_registry.rs provides source-root and Python-compatible value helpers
// upstream implementation ../experiment_identity.rs validates topic and variant segments
// upstream implementation ../path_resolution.rs resolves repository and template paths
// upstream implementation ../template_bundle.rs owns shared staged template-file publication
// upstream implementation store.rs owns registry values and deterministic serialization
// downstream implementation ../../../../../../templates/experiments/_template preserves the consumer Python/JAX package
// downstream implementation ../../../../../../templates/experiments/_cpp_template preserves the C++ package profiles
// downstream test ../../tests/experiment_registry_native.rs covers the public native registry CLI
// @dependency-end

use super::{python_repr, source_root, store, RegistryValue};
use crate::experiment_identity::validate_segment;
use crate::path_resolution::resolve_non_strict;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use cap_fs_ext::MetadataExt as CapabilityMetadataExt;
use std::env;
use std::ffi::OsStr;
use std::fs::{self, Metadata};
use std::io;
use std::path::{Component, Path, PathBuf};
use tempfile::{Builder, TempDir};

const AGENT_CANON_TEMPLATE_DIR: &str = "vendor/agent-canon/templates/experiments/_template";
const CPP_TEMPLATE_DIR: &str = "templates/experiments/_cpp_template";
const USAGE: &str = "Usage: agent-canon create-experiment-topic <topic> [--repo-root PATH] [--template-profile {python,cpp}] [--cmake-profile {root-aggregate,consumer-local}] [--multi-case] [--registry PATH] [--status STATUS] [--default-variant VARIANT] [--primary-note PATH] [--active-branch BRANCH] [--force] [--dry-run]";

#[derive(Clone, Copy)]
enum OptionKey {
    Help,
    RepoRoot,
    TemplateProfile,
    CmakeProfile,
    MultiCase,
    Registry,
    Status,
    DefaultVariant,
    PrimaryNote,
    ActiveBranch,
    Force,
    DryRun,
}

const OPTIONS: &[(&str, OptionKey)] = &[
    ("--repo-root", OptionKey::RepoRoot),
    ("--template-profile", OptionKey::TemplateProfile),
    ("--cmake-profile", OptionKey::CmakeProfile),
    ("--multi-case", OptionKey::MultiCase),
    ("--registry", OptionKey::Registry),
    ("--status", OptionKey::Status),
    ("--default-variant", OptionKey::DefaultVariant),
    ("--primary-note", OptionKey::PrimaryNote),
    ("--active-branch", OptionKey::ActiveBranch),
    ("--force", OptionKey::Force),
    ("--dry-run", OptionKey::DryRun),
    ("--help", OptionKey::Help),
];

#[derive(Debug)]
struct CreateOptions {
    topic: String,
    repo_root: Option<PathBuf>,
    template_profile: String,
    cmake_profile: Option<String>,
    multi_case: bool,
    registry: Option<PathBuf>,
    status: String,
    default_variant: String,
    primary_note: Option<String>,
    active_branch: Option<String>,
    force: bool,
    dry_run: bool,
}

fn option_key(name: &str) -> Result<OptionKey, String> {
    if name == "-h" {
        return Ok(OptionKey::Help);
    }
    resolve_long_option_prefix(name, OPTIONS).map_err(|error| match error {
        LongOptionError::Unrecognized => format!("unrecognized arguments: {name}"),
        LongOptionError::Ambiguous(matches) => {
            format!(
                "ambiguous option: {name} could match {}",
                matches.join(", ")
            )
        }
    })
}

fn parse_value(args: &[String], index: &mut usize, name: &str) -> Result<String, String> {
    *index += 1;
    let Some(value) = args.get(*index) else {
        return Err(format!("argument {name}: expected one argument"));
    };
    if value.starts_with('-') && value != "-" {
        return Err(format!("argument {name}: expected one argument"));
    }
    Ok(value.clone())
}

fn parse(args: &[String]) -> Result<Option<CreateOptions>, String> {
    let mut topic = None;
    let mut repo_root = None;
    let mut template_profile = "python".to_owned();
    let mut cmake_profile = None;
    let mut multi_case = false;
    let mut registry = None;
    let mut status = "draft".to_owned();
    let mut default_variant = "default".to_owned();
    let mut primary_note = None;
    let mut active_branch = None;
    let mut force = false;
    let mut dry_run = false;
    let mut options_ended = false;
    let mut index = 0;

    while index < args.len() {
        let argument = &args[index];
        if !options_ended && argument == "--" {
            options_ended = true;
            index += 1;
            continue;
        }
        if !options_ended && (argument == "-h" || argument.starts_with("--")) {
            let (name, inline_value) = argument
                .split_once('=')
                .map_or((argument.as_str(), None), |(name, value)| {
                    (name, Some(value.to_owned()))
                });
            let key = option_key(name)?;
            match key {
                OptionKey::Help => {
                    if inline_value.is_some() {
                        return Err(format!("argument {name}: ignored explicit argument"));
                    }
                    return Ok(None);
                }
                OptionKey::MultiCase | OptionKey::Force | OptionKey::DryRun => {
                    if inline_value.is_some() {
                        return Err(format!("argument {name}: ignored explicit argument"));
                    }
                    match key {
                        OptionKey::MultiCase => multi_case = true,
                        OptionKey::Force => force = true,
                        OptionKey::DryRun => dry_run = true,
                        _ => unreachable!(),
                    }
                }
                OptionKey::RepoRoot
                | OptionKey::TemplateProfile
                | OptionKey::CmakeProfile
                | OptionKey::Registry
                | OptionKey::Status
                | OptionKey::DefaultVariant
                | OptionKey::PrimaryNote
                | OptionKey::ActiveBranch => {
                    let value = match inline_value {
                        Some(value) => value,
                        None => parse_value(args, &mut index, name)?,
                    };
                    match key {
                        OptionKey::RepoRoot => repo_root = Some(PathBuf::from(value)),
                        OptionKey::TemplateProfile => template_profile = value,
                        OptionKey::CmakeProfile => cmake_profile = Some(value),
                        OptionKey::Registry => registry = Some(PathBuf::from(value)),
                        OptionKey::Status => status = value,
                        OptionKey::DefaultVariant => default_variant = value,
                        OptionKey::PrimaryNote => primary_note = Some(value),
                        OptionKey::ActiveBranch => active_branch = Some(value),
                        _ => unreachable!(),
                    }
                }
            }
            index += 1;
            continue;
        }
        if !options_ended && argument.starts_with('-') && argument != "-" {
            return Err(format!("unrecognized arguments: {argument}"));
        }
        if topic.is_some() {
            return Err(format!("unrecognized arguments: {argument}"));
        }
        topic = Some(argument.clone());
        index += 1;
    }

    let topic = topic.ok_or_else(|| "the following arguments are required: topic".to_owned())?;
    if !matches!(template_profile.as_str(), "python" | "cpp") {
        return Err(format!(
            "argument --template-profile: invalid choice: {template_profile:?} (choose from 'python', 'cpp')"
        ));
    }
    if let Some(profile) = &cmake_profile {
        if !matches!(profile.as_str(), "root-aggregate" | "consumer-local") {
            return Err(format!(
                "argument --cmake-profile: invalid choice: {profile:?} (choose from 'root-aggregate', 'consumer-local')"
            ));
        }
    }
    Ok(Some(CreateOptions {
        topic,
        repo_root,
        template_profile,
        cmake_profile,
        multi_case,
        registry,
        status,
        default_variant,
        primary_note,
        active_branch,
        force,
        dry_run,
    }))
}

fn absolute_lexical(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|error| format!("current directory: {error}"))?
            .join(path)
    };
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            Component::Normal(value) => normalized.push(value),
        }
    }
    Ok(normalized)
}

fn resolve_repo_root(options: &CreateOptions) -> Result<(PathBuf, Option<PathBuf>), String> {
    let active_target = env::var_os("AGENT_CANON_OUTPUT_ROOT")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .map(|path| resolve_non_strict(&path))
        .transpose()?;
    let requested_root = options
        .repo_root
        .as_deref()
        .or(active_target.as_deref())
        .map(Path::to_path_buf)
        .unwrap_or_else(source_root);
    let repo_root = resolve_non_strict(&requested_root)?;
    if active_target
        .as_ref()
        .is_some_and(|target| target != &repo_root)
    {
        return Err("--repo-root must match the active explicit target".to_owned());
    }
    Ok((repo_root, active_target))
}

fn resolve_registry_path(options: &CreateOptions, repo_root: &Path) -> Result<PathBuf, String> {
    match options.registry.as_deref() {
        Some(path) => absolute_lexical(path),
        None => Ok(repo_root.join("experiments/registry.toml")),
    }
}

fn reject_symlink(path: &Path, label: &str) -> Result<Option<Metadata>, String> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            Err(format!("{label} is a symlink: {}", path.display()))
        }
        Ok(metadata) => Ok(Some(metadata)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!(
            "cannot inspect {label} {}: {error}",
            path.display()
        )),
    }
}

fn empty_registry() -> RegistryValue {
    RegistryValue::Table(vec![
        ("defaults".to_owned(), RegistryValue::Table(Vec::new())),
        ("topics".to_owned(), RegistryValue::Array(Vec::new())),
    ])
}

fn resolve_canon_path(repo_root: &Path, logical_path: &str) -> Result<PathBuf, String> {
    let source_root = resolve_non_strict(&source_root())?;
    let vendor_root = repo_root.join("vendor/agent-canon");
    let candidates = if vendor_root.exists() {
        vec![
            vendor_root.join(logical_path),
            repo_root.join(logical_path),
            source_root.join(logical_path),
        ]
    } else {
        vec![repo_root.join(logical_path), source_root.join(logical_path)]
    };
    Ok(candidates
        .iter()
        .find(|candidate| candidate.exists())
        .cloned()
        .unwrap_or_else(|| candidates[0].clone()))
}

fn resolve_topic_template_dir(repo_root: &Path, configured_path: &str) -> Result<PathBuf, String> {
    let configured = configured_path
        .strip_prefix("vendor/agent-canon/")
        .unwrap_or(configured_path);
    let configured = resolve_canon_path(repo_root, configured)?;
    if configured.is_dir() {
        return Ok(configured);
    }
    resolve_canon_path(repo_root, "templates/experiments/_template")
}

fn required_templates(
    template_dir: &Path,
    template_profile: &str,
    cmake_profile: Option<&str>,
    multi_case: bool,
) -> Vec<PathBuf> {
    let mut required = vec![
        template_dir.to_path_buf(),
        template_dir.join("README.md"),
        template_dir.join("provenance.toml"),
    ];
    if template_profile == "cpp" {
        let cmake_source = match cmake_profile {
            Some("consumer-local") => "consumer-local.CMakeLists.txt",
            _ => "root-aggregate.registration.cmake",
        };
        required.extend([
            template_dir.join("config.yaml"),
            template_dir.join("topic.cpp"),
            template_dir.join("run.py"),
            template_dir.join("visualization.py"),
            template_dir.join("cmake").join(cmake_source),
            template_dir.join("report/.gitkeep"),
            template_dir.join("result/.gitkeep"),
        ]);
        if multi_case {
            required.push(template_dir.join("optional/cases.py"));
        }
    }
    required
}

fn validate_profile(options: &CreateOptions) -> Result<(), String> {
    if options.template_profile == "cpp" {
        if options.cmake_profile.is_none() {
            return Err("--cmake-profile is required with --template-profile cpp".to_owned());
        }
        if options.status != "draft" {
            return Err(
                "C++ starter topics must remain draft until native work is implemented".to_owned(),
            );
        }
    } else {
        if options.cmake_profile.is_some() {
            return Err("--cmake-profile is only valid with --template-profile cpp".to_owned());
        }
        if options.multi_case {
            return Err("--multi-case is only valid with --template-profile cpp".to_owned());
        }
    }
    Ok(())
}

fn planned_files(options: &CreateOptions) -> String {
    if options.template_profile == "cpp" {
        let cmake_file = match options.cmake_profile.as_deref() {
            Some("consumer-local") => "CMakeLists.txt",
            _ => "cmake-registration.cmake",
        };
        let mut files = format!(
            "README.md,provenance.toml,config.yaml,<topic>.cpp,run.py,visualization.py,{cmake_file},report/.gitkeep,result/.gitkeep"
        );
        if options.multi_case {
            files = files.replace("run.py,", "run.py,cases.py,");
        }
        files
    } else {
        "README.md,provenance.toml,run.py,cases.py,visualization.py,config.yaml,report/.gitkeep,result/.gitkeep".to_owned()
    }
}

fn run_dry_run(
    options: &CreateOptions,
    template_dir: &Path,
    topic_dir: &Path,
    registry_path: &Path,
) {
    println!("dry_run=true");
    println!("template_dir={}", template_dir.display());
    println!("topic_dir={}", topic_dir.display());
    println!("registry_path={}", registry_path.display());
    if topic_dir.exists() {
        println!("force_replaces_existing_topic={}", topic_dir.display());
    }
    if options.template_profile == "cpp" {
        println!("template_profile=cpp");
        if let Some(profile) = &options.cmake_profile {
            println!("cmake_profile={profile}");
        }
    }
    println!("planned_topic_files={}", planned_files(options));
}

fn configured_python_template(registry: &RegistryValue) -> Result<String, String> {
    let defaults = store::get(registry, "defaults");
    match defaults {
        Some(RegistryValue::Table(_)) | None => {}
        Some(_) => return Err("registry defaults must be a table".to_owned()),
    }
    match defaults.and_then(|value| store::get(value, "topic_template_dir")) {
        Some(RegistryValue::String(path)) => Ok(path.clone()),
        Some(_) => Err("defaults.topic_template_dir must be a string when present".to_owned()),
        None => Ok(AGENT_CANON_TEMPLATE_DIR.to_owned()),
    }
}

fn new_topic_entry(options: &CreateOptions) -> RegistryValue {
    let topic = &options.topic;
    let default_inner_command = format!(
        "/usr/bin/python /workspace/experiments/{topic}/run.py --config {{config_path}}{}",
        if options.template_profile == "cpp" && options.multi_case {
            " --multi-case"
        } else {
            ""
        }
    );
    let mut fields = vec![
        ("name".to_owned(), RegistryValue::String(topic.clone())),
        (
            "status".to_owned(),
            RegistryValue::String(options.status.clone()),
        ),
        (
            "topic_dir".to_owned(),
            RegistryValue::String(format!("experiments/{topic}")),
        ),
        (
            "topic_readme".to_owned(),
            RegistryValue::String(format!("experiments/{topic}/README.md")),
        ),
        (
            "topic_provenance".to_owned(),
            RegistryValue::String(format!("experiments/{topic}/provenance.toml")),
        ),
        (
            "canonical_entrypoint".to_owned(),
            RegistryValue::String(format!("experiments/{topic}/run.py")),
        ),
        (
            "result_root".to_owned(),
            RegistryValue::String(format!("experiments/{topic}/result")),
        ),
        (
            "report_root".to_owned(),
            RegistryValue::String(format!("experiments/{topic}/report")),
        ),
        (
            "default_variant".to_owned(),
            RegistryValue::String(options.default_variant.clone()),
        ),
        (
            "default_inner_command".to_owned(),
            RegistryValue::String(default_inner_command),
        ),
    ];
    if let Some(note) = options
        .primary_note
        .as_ref()
        .filter(|note| !note.is_empty())
    {
        fields.push((
            "primary_note".to_owned(),
            RegistryValue::String(note.clone()),
        ));
    }
    if let Some(branch) = options
        .active_branch
        .as_ref()
        .filter(|branch| !branch.is_empty())
    {
        fields.push((
            "active_branch".to_owned(),
            RegistryValue::String(branch.clone()),
        ));
    }
    RegistryValue::Table(fields)
}

fn execute(options: &CreateOptions) -> Result<(), String> {
    validate_segment(&options.topic, "topic")?;
    validate_segment(&options.default_variant, "default_variant")?;

    let (repo_root, active_target) = resolve_repo_root(options)?;
    let registry_path = resolve_registry_path(options, &repo_root)?;
    if let Some(target) = active_target.as_ref() {
        if registry_path != target.join("experiments/registry.toml") {
            return Err(
                "--registry must name the active target's experiments/registry.toml".to_owned(),
            );
        }
    }
    let experiments_root = repo_root.join("experiments");
    reject_symlink(&experiments_root, "experiments directory")?;
    let registry_metadata = reject_symlink(&registry_path, "registry path")?;

    let mut registry = match registry_metadata {
        Some(_) => store::load(&registry_path)?,
        None if options.dry_run => empty_registry(),
        None => {
            return Err(format!(
                "registry is required for topic creation: {}",
                registry_path.display()
            ));
        }
    };

    let topic_exists_in_registry = store::find_topic_mut(&mut registry, &options.topic)?.is_some();
    if topic_exists_in_registry {
        return Err(format!(
            "topic {} already exists in {}",
            python_repr(&RegistryValue::String(options.topic.clone())),
            registry_path.display()
        ));
    }

    let defaults = store::get(&registry, "defaults");
    if let Some(value) = defaults {
        if !matches!(value, RegistryValue::Table(_)) {
            return Err("registry defaults must be a table".to_owned());
        }
    }
    validate_profile(options)?;

    let template_dir = if options.template_profile == "cpp" {
        resolve_topic_template_dir(&repo_root, CPP_TEMPLATE_DIR)?
    } else {
        let configured = configured_python_template(&registry)?;
        resolve_topic_template_dir(&repo_root, &configured)?
    };
    let required = required_templates(
        &template_dir,
        &options.template_profile,
        options.cmake_profile.as_deref(),
        options.multi_case,
    );
    let missing = required
        .iter()
        .filter(|path| !path.exists())
        .map(|path| path.display().to_string())
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(format!(
            "canonical experiment templates are missing: {}",
            missing.join(", ")
        ));
    }

    let topic_dir = experiments_root.join(&options.topic);
    let topic_metadata = reject_symlink(&topic_dir, "topic directory")?;
    if let Some(metadata) = topic_metadata.as_ref() {
        if !options.force {
            return Err(format!(
                "topic directory already exists: {}",
                topic_dir.display()
            ));
        }
        if !metadata.is_dir() {
            return Err(format!(
                "topic path is not a directory: {}",
                topic_dir.display()
            ));
        }
    }

    if options.dry_run {
        run_dry_run(options, &template_dir, &topic_dir, &registry_path);
        return Ok(());
    }

    store::topics_mut(&mut registry)?.push(new_topic_entry(options));
    match publish_topic_and_registry(
        &topic_dir,
        &template_dir,
        &registry_path,
        &registry,
        options,
    ) {
        Ok(()) => {}
        Err(PublicationError::Failed(error)) => {
            return Err(format!("topic and registry were not published: {error}"));
        }
        Err(PublicationError::Incomplete(error)) => return Err(error),
    }

    println!("topic_dir={}", topic_dir.display());
    println!("registry_path={}", registry_path.display());
    println!("topic_name={}", options.topic);
    Ok(())
}

fn copy_template_tree(source: &Path, destination: &Path) -> Result<(), String> {
    let source_metadata = fs::metadata(source)
        .map_err(|error| format!("cannot inspect template {}: {error}", source.display()))?;
    if !source_metadata.is_dir() {
        return Err(format!(
            "template path is not a directory: {}",
            source.display()
        ));
    }
    fs::create_dir(destination).map_err(|error| {
        format!(
            "cannot create staged template {}: {error}",
            destination.display()
        )
    })?;
    let mut entries = fs::read_dir(source)
        .map_err(|error| {
            format!(
                "cannot read template directory {}: {error}",
                source.display()
            )
        })?
        .map(|entry| entry.map(|entry| entry.path()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| format!("cannot read template entry: {error}"))?;
    entries.sort();
    for source_path in entries {
        let name = source_path
            .file_name()
            .ok_or_else(|| format!("template path has no file name: {}", source_path.display()))?;
        let destination_path = destination.join(name);
        let metadata = fs::metadata(&source_path).map_err(|error| {
            format!(
                "cannot inspect template entry {}: {error}",
                source_path.display()
            )
        })?;
        if metadata.is_dir() {
            copy_template_tree(&source_path, &destination_path)?;
            continue;
        }
        let bytes = fs::read(&source_path)
            .map_err(|error| format!("cannot read template {}: {error}", source_path.display()))?;
        crate::template_bundle::write_output_file(&destination_path, &bytes, 0o644)
            .map_err(|error| error.0)?;
        fs::set_permissions(&destination_path, metadata.permissions()).map_err(|error| {
            format!(
                "cannot preserve template permissions {}: {error}",
                destination_path.display()
            )
        })?;
    }
    fs::set_permissions(destination, source_metadata.permissions()).map_err(|error| {
        format!(
            "cannot preserve template directory permissions {}: {error}",
            destination.display()
        )
    })?;
    Ok(())
}

fn replace_topic_tokens(path: &Path, topic_name: &str) -> Result<(), String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("cannot read staged template {}: {error}", path.display()))?;
    let mut text = text
        .replace("<topic>", topic_name)
        .replace("<Experiment topic>", topic_name);
    if path.file_name() == Some(OsStr::new("README.md"))
        && text.starts_with("# Experiment Topic Template")
    {
        text = text.replacen("# Experiment Topic Template", &format!("# {topic_name}"), 1);
    }
    fs::write(path, text)
        .map_err(|error| format!("cannot update staged template {}: {error}", path.display()))
}

fn update_copied_files(topic_dir: &Path, topic_name: &str) -> Result<(), String> {
    for relative in ["README.md", "provenance.toml"] {
        replace_topic_tokens(&topic_dir.join(relative), topic_name)?;
    }
    Ok(())
}

fn collect_template_files(root: &Path, output: &mut Vec<PathBuf>) -> Result<(), String> {
    let mut entries = fs::read_dir(root)
        .map_err(|error| {
            format!(
                "cannot read staged template directory {}: {error}",
                root.display()
            )
        })?
        .map(|entry| entry.map(|entry| entry.path()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| format!("cannot read staged template entry: {error}"))?;
    entries.sort();
    for path in entries {
        if fs::metadata(&path)
            .map_err(|error| format!("cannot inspect staged template {}: {error}", path.display()))?
            .is_dir()
        {
            collect_template_files(&path, output)?;
        } else {
            output.push(path);
        }
    }
    Ok(())
}

fn update_cpp_topic(
    topic_dir: &Path,
    topic_name: &str,
    cmake_profile: &str,
    multi_case: bool,
) -> Result<(), String> {
    let mut files = Vec::new();
    collect_template_files(topic_dir, &mut files)?;
    files.sort();
    for path in files {
        replace_topic_tokens(&path, topic_name)?;
        let text = fs::read_to_string(&path)
            .map_err(|error| format!("cannot read staged template {}: {error}", path.display()))?;
        let text = text
            .replace("<cmake-profile>", cmake_profile)
            .replace("<case-mode>", if multi_case { "multi" } else { "single" });
        fs::write(&path, text).map_err(|error| {
            format!("cannot update staged template {}: {error}", path.display())
        })?;
    }

    fs::rename(
        topic_dir.join("topic.cpp"),
        topic_dir.join(format!("{topic_name}.cpp")),
    )
    .map_err(|error| format!("cannot rename staged topic source: {error}"))?;
    let (cmake_source, cmake_output) = match cmake_profile {
        "consumer-local" => ("consumer-local.CMakeLists.txt", "CMakeLists.txt"),
        "root-aggregate" => (
            "root-aggregate.registration.cmake",
            "cmake-registration.cmake",
        ),
        _ => return Err(format!("unsupported CMake profile: {cmake_profile}")),
    };
    let cmake_dir = topic_dir.join("cmake");
    fs::rename(cmake_dir.join(cmake_source), topic_dir.join(cmake_output))
        .map_err(|error| format!("cannot select staged CMake profile: {error}"))?;
    fs::remove_dir_all(&cmake_dir)
        .map_err(|error| format!("cannot remove unselected staged CMake files: {error}"))?;

    let optional_dir = topic_dir.join("optional");
    if multi_case {
        fs::rename(optional_dir.join("cases.py"), topic_dir.join("cases.py"))
            .map_err(|error| format!("cannot select staged multi-case adapter: {error}"))?;
    }
    fs::remove_dir_all(&optional_dir)
        .map_err(|error| format!("cannot remove unselected staged optional files: {error}"))?;
    Ok(())
}

enum PublicationError {
    Failed(String),
    Incomplete(String),
}

fn temp_dir(parent: &Path, prefix: &str) -> Result<TempDir, String> {
    Builder::new()
        .prefix(prefix)
        .tempdir_in(parent)
        .map_err(|error| {
            format!(
                "cannot create staging directory in {}: {error}",
                parent.display()
            )
        })
}

fn close_temp_dir(directory: TempDir, label: &str) {
    let path = directory.path().to_path_buf();
    if matches!(fs::symlink_metadata(&path), Err(error) if error.kind() == io::ErrorKind::NotFound)
    {
        drop(directory);
        return;
    }
    if let Err(error) = directory.close() {
        eprintln!("warning: {label} remains at {}: {error}", path.display());
    }
}

fn path_exists_or_symlink(path: &Path) -> Result<bool, String> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(format!("cannot inspect {}: {error}", path.display())),
    }
}

fn published_identity(path: &Path) -> Result<(u64, u64), String> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        format!(
            "cannot identify published topic {}: {error}",
            path.display()
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(format!(
            "published topic is not a directory: {}",
            path.display()
        ));
    }
    let directory = cap_std::fs::Dir::open_ambient_dir(path, cap_std::ambient_authority())
        .map_err(|error| format!("cannot open published topic {}: {error}", path.display()))?;
    let metadata = directory.dir_metadata().map_err(|error| {
        format!(
            "cannot read published topic metadata {}: {error}",
            path.display()
        )
    })?;
    Ok((
        CapabilityMetadataExt::dev(&metadata),
        CapabilityMetadataExt::ino(&metadata),
    ))
}

fn rollback_publication(
    topic_dir: &Path,
    topic_published: bool,
    expected_published_identity: Option<(u64, u64)>,
    backup_topic: Option<&Path>,
) -> Option<String> {
    let mut rollback_error = None;
    if topic_published {
        if let Some(expected_identity) = expected_published_identity {
            match path_exists_or_symlink(topic_dir) {
                Ok(false) => {}
                Ok(true) => match published_identity(topic_dir) {
                    Ok(identity) if identity == expected_identity => {
                        if let Err(error) = fs::remove_dir_all(topic_dir) {
                            rollback_error = Some(error.to_string());
                        }
                    }
                    Ok(_) => {}
                    Err(error) => rollback_error = Some(error),
                },
                Err(error) => rollback_error = Some(error),
            }
        }
    }

    if let Some(backup_topic) = backup_topic {
        match path_exists_or_symlink(backup_topic) {
            Ok(true) => match path_exists_or_symlink(topic_dir) {
                Ok(true) => {
                    rollback_error.get_or_insert_with(|| {
                        format!(
                            "cannot restore prior topic over existing path: {}",
                            topic_dir.display()
                        )
                    });
                }
                Ok(false) => {
                    if let Err(error) = fs::rename(backup_topic, topic_dir) {
                        rollback_error.get_or_insert_with(|| error.to_string());
                    }
                }
                Err(error) => {
                    rollback_error.get_or_insert(error);
                }
            },
            Ok(false) => {}
            Err(error) => {
                rollback_error.get_or_insert(error);
            }
        }
    }
    rollback_error
}

fn publish_topic_and_registry(
    topic_dir: &Path,
    template_dir: &Path,
    registry_path: &Path,
    registry: &RegistryValue,
    options: &CreateOptions,
) -> Result<(), PublicationError> {
    let topic_parent = topic_dir
        .parent()
        .ok_or_else(|| PublicationError::Failed("topic directory has no parent".to_owned()))?;
    let registry_parent = registry_path
        .parent()
        .ok_or_else(|| PublicationError::Failed("registry path has no parent".to_owned()))?;
    let topic_stage_root = temp_dir(topic_parent, &format!(".{}.stage-", options.topic))
        .map_err(PublicationError::Failed)?;
    let mut registry_stage_root = None;
    let mut backup_root = None;
    let mut backup_topic = None;
    let mut topic_published = false;
    let mut transaction_committed = false;
    let mut published_topic_identity = None;

    let operation = (|| -> Result<(), String> {
        let staged_topic = topic_stage_root.path().join(&options.topic);
        copy_template_tree(template_dir, &staged_topic)?;
        if options.template_profile == "cpp" {
            let cmake_profile = options.cmake_profile.as_deref().ok_or_else(|| {
                "C++ template materialization requires a CMake profile".to_owned()
            })?;
            update_cpp_topic(
                &staged_topic,
                &options.topic,
                cmake_profile,
                options.multi_case,
            )?;
        } else {
            update_copied_files(&staged_topic, &options.topic)?;
        }

        let registry_prefix = format!(
            ".{}.stage-",
            registry_path
                .file_name()
                .unwrap_or(OsStr::new("registry.toml"))
                .to_string_lossy()
        );
        registry_stage_root = Some(temp_dir(registry_parent, &registry_prefix)?);
        let registry_file_name = registry_path.file_name().ok_or_else(|| {
            format!(
                "registry path has no file name: {}",
                registry_path.display()
            )
        })?;
        let staged_registry = registry_stage_root
            .as_ref()
            .expect("registry staging directory was created")
            .path()
            .join(registry_file_name);
        store::write(&staged_registry, registry)?;
        if registry_path.exists() {
            let metadata = fs::symlink_metadata(registry_path).map_err(|error| {
                format!(
                    "cannot inspect registry {}: {error}",
                    registry_path.display()
                )
            })?;
            if metadata.file_type().is_symlink() {
                return Err(format!(
                    "registry path is a symlink: {}",
                    registry_path.display()
                ));
            }
            fs::set_permissions(&staged_registry, metadata.permissions()).map_err(|error| {
                format!(
                    "cannot preserve registry permissions {}: {error}",
                    registry_path.display()
                )
            })?;
        }

        if let Some(metadata) = reject_symlink(topic_dir, "topic directory")? {
            if !options.force {
                return Err(format!(
                    "topic directory already exists: {}",
                    topic_dir.display()
                ));
            }
            if !metadata.is_dir() {
                return Err(format!(
                    "topic path is not a directory: {}",
                    topic_dir.display()
                ));
            }
            let root = temp_dir(topic_parent, &format!(".{}.replaced-", options.topic))?;
            let backup = root.path().join(&options.topic);
            backup_root = Some(root);
            backup_topic = Some(backup.clone());
            fs::rename(topic_dir, backup).map_err(|error| {
                format!(
                    "cannot back up existing topic {}: {error}",
                    topic_dir.display()
                )
            })?;
        }

        fs::rename(&staged_topic, topic_dir).map_err(|error| {
            format!(
                "cannot publish topic directory {}: {error}",
                topic_dir.display()
            )
        })?;
        topic_published = true;
        fs::remove_dir(topic_stage_root.path()).map_err(|error| {
            format!(
                "cannot remove topic staging directory {}: {error}",
                topic_stage_root.path().display()
            )
        })?;
        published_topic_identity = Some(published_identity(topic_dir)?);
        let staged_registry = registry_stage_root
            .as_ref()
            .expect("registry staging directory was created")
            .path()
            .join(
                registry_path
                    .file_name()
                    .expect("registry path has a file name"),
            );
        fs::rename(&staged_registry, registry_path).map_err(|error| {
            format!(
                "cannot publish registry {}: {error}",
                registry_path.display()
            )
        })?;
        transaction_committed = true;
        Ok(())
    })();

    let (failure, rollback_incomplete) = match operation {
        Ok(()) => (None, false),
        Err(primary_error) => {
            let rollback_error = rollback_publication(
                topic_dir,
                topic_published,
                published_topic_identity,
                backup_topic.as_deref(),
            );
            match rollback_error {
                Some(rollback_error) => {
                    let backup_note = backup_topic
                        .as_ref()
                        .filter(|path| path_exists_or_symlink(path).is_ok_and(|exists| exists))
                        .map(|path| format!("; prior topic remains at {}", path.display()))
                        .unwrap_or_default();
                    (
                        Some(format!(
                            "publication failed and rollback was incomplete{backup_note}: {rollback_error}"
                        )),
                        true,
                    )
                }
                None => (Some(primary_error), false),
            }
        }
    };

    if transaction_committed {
        if let Some(root) = backup_root.take() {
            close_temp_dir(root, "replaced topic backup");
        }
    } else if let Some(root) = backup_root.take() {
        if let Some(backup_topic) = backup_topic.as_deref() {
            if path_exists_or_symlink(backup_topic).unwrap_or(true) {
                let backup_path = root.keep();
                if failure.as_ref().is_some_and(|message| {
                    message.starts_with("publication failed and rollback was incomplete")
                }) {
                    eprintln!(
                        "warning: replaced topic backup remains at {}",
                        backup_path.display()
                    );
                }
            } else {
                close_temp_dir(root, "replaced topic backup");
            }
        } else {
            close_temp_dir(root, "replaced topic backup");
        }
    }

    if let Some(root) = registry_stage_root {
        close_temp_dir(root, "registry staging path");
    }
    close_temp_dir(topic_stage_root, "topic staging path");

    match failure {
        None => Ok(()),
        Some(error) if rollback_incomplete => Err(PublicationError::Incomplete(error)),
        Some(error) => Err(PublicationError::Failed(error)),
    }
}

fn print_parse_error(error: &str) {
    eprintln!("{USAGE}");
    eprintln!("agent-canon create-experiment-topic: error: {error}");
}

/// Create one experiment topic and add its registry entry.
pub fn run(args: &[String]) -> i32 {
    let options = match parse(args) {
        Ok(None) => {
            println!("{USAGE}");
            return 0;
        }
        Ok(Some(options)) => options,
        Err(error) => {
            print_parse_error(&error);
            return 2;
        }
    };
    match execute(&options) {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("{error}");
            1
        }
    }
}
