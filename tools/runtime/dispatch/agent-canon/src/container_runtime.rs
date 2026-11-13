// @dependency-start
// contract implementation
// responsibility Builds and executes project-owned container pack commands through configured Docker or Podman CLIs.
// upstream implementation path_resolution.rs owns physical path resolution
// downstream test ../tests/container_runtime_native.rs checks command construction and external process behavior
// @dependency-end

use crate::path_resolution::resolve_non_strict;
use serde_json::Value;
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const PROFILES: &[&str] = &[
    "host-zshrc",
    "host-git",
    "host-secrets",
    "host-credentials",
    "ssh-agent",
    "docker-host",
    "linked-data-roots",
];

#[derive(Clone, Debug)]
pub struct ContainerPack {
    pub dockerfile: String,
    pub context: String,
    pub target: Option<String>,
    pub image_tag: String,
    pub platform: Option<String>,
    pub smoke_shell: String,
    pub smoke_commands: Vec<String>,
    pub shell: String,
    pub workdir: String,
    pub workspace_mount: String,
    pub env: Vec<String>,
    pub gpus: Option<String>,
    pub profiles: Vec<String>,
    pub linked_roots: Vec<(String, String)>,
    pub linked_declared: bool,
}

fn absolute(root: &Path, value: impl AsRef<Path>) -> Result<PathBuf, String> {
    let value = value.as_ref();
    resolve_non_strict(&if value.is_absolute() {
        value.to_path_buf()
    } else {
        root.join(value)
    })
}

fn container_relative(root: &Path, path: &Path) -> Result<String, String> {
    Ok(path
        .strip_prefix(root)
        .map_err(|error| error.to_string())?
        .iter()
        .map(|component| component.to_string_lossy())
        .collect::<Vec<_>>()
        .join("/"))
}

fn text(section: &Value, key: &str, default: Option<&str>) -> Result<String, String> {
    match section.get(key) {
        Some(Value::String(value)) => Ok(value.clone()),
        None => default
            .map(str::to_owned)
            .ok_or_else(|| format!("missing string: {key}")),
        _ => Err(format!("{key} must be a string")),
    }
}

fn optional(section: &Value, key: &str) -> Result<Option<String>, String> {
    section
        .get(key)
        .map(|_| text(section, key, None))
        .transpose()
}

fn strings(section: &Value, key: &str) -> Result<Vec<String>, String> {
    match section.get(key) {
        None => Ok(Vec::new()),
        Some(Value::Array(items)) => items
            .iter()
            .map(|item| {
                item.as_str()
                    .map(str::to_owned)
                    .ok_or_else(|| format!("{key} must be a string array"))
            })
            .collect(),
        _ => Err(format!("{key} must be a string array")),
    }
}

fn toml_file(path: &Path) -> Result<Value, String> {
    let source =
        fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    toml_edit::de::from_str(&source).map_err(|error| format!("{}: {error}", path.display()))
}

fn validate_profiles(profiles: &[String]) -> Result<(), String> {
    let mut seen = BTreeSet::new();
    for profile in profiles {
        if !PROFILES.contains(&profile.as_str()) || !seen.insert(profile) {
            return Err(format!(
                "unknown or duplicate optional mount profile: {profile}"
            ));
        }
    }
    Ok(())
}

impl ContainerPack {
    pub fn load(root: &Path, path: Option<&str>) -> Result<Self, String> {
        let Some(path) = path else {
            let name = root
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_lowercase();
            let name = regex::Regex::new("[^a-z0-9._-]+")
                .expect("literal regex")
                .replace_all(&name, "-");
            let name = name.trim_matches(['-', '.']);
            return Ok(Self {
                dockerfile: "docker/Dockerfile".into(),
                context: ".".into(),
                target: None,
                image_tag: format!(
                    "{}:agent-canon",
                    if name.is_empty() { "repository" } else { name }
                ),
                platform: None,
                smoke_shell: "/bin/bash".into(),
                smoke_commands: vec![],
                shell: "/bin/bash".into(),
                workdir: "/workspace".into(),
                workspace_mount: "/workspace".into(),
                env: vec![],
                gpus: None,
                profiles: vec![],
                linked_roots: vec![],
                linked_declared: false,
            });
        };
        let source = absolute(root, path)?;
        let data = toml_file(&source)?;
        let empty = Value::Object(Default::default());
        let pack = data.get("pack").unwrap_or(&empty);
        let smoke = data.get("smoke").unwrap_or(&empty);
        let runtime = data.get("runtime").unwrap_or(&empty);
        if ![pack, smoke, runtime].iter().all(|value| value.is_object()) {
            return Err("pack, smoke, and runtime sections must be tables".into());
        }
        let _name = text(pack, "name", None)?;
        let profiles = strings(runtime, "optional_mount_profiles")?;
        validate_profiles(&profiles)?;
        if !strings(runtime, "mounts")?.is_empty() {
            return Err(
                "[runtime].mounts is not supported; use an explicit optional mount profile".into(),
            );
        }
        let linked_declared = runtime.get("linked_data_roots").is_some();
        let mut linked_roots = vec![];
        let mut links = BTreeSet::new();
        let mut targets = BTreeSet::new();
        if let Some(value) = runtime.get("linked_data_roots") {
            let rows = value
                .as_array()
                .filter(|rows| !rows.is_empty())
                .ok_or("linked_data_roots must be a non-empty inline table array")?;
            let pack_root = source
                .ancestors()
                .nth(3)
                .ok_or("pack has no repository root")?;
            let target_pattern = regex::Regex::new(r"^/mnt/[a-z]/[^/].*$").expect("literal regex");
            for row in rows {
                if row.as_object().is_none_or(|row| {
                    row.len() != 2 || !row.contains_key("link") || !row.contains_key("target")
                }) {
                    return Err("linked_data_roots entry must contain only link and target".into());
                }
                let link = text(row, "link", None)?;
                let target = text(row, "target", None)?;
                let normalized_link = !link.is_empty()
                    && !link.starts_with('/')
                    && !link.contains([':', ','])
                    && !link.chars().any(char::is_control)
                    && link.split('/').all(|part| !matches!(part, "" | "." | ".."));
                let valid_target = target_pattern.is_match(&target)
                    && !target.contains([':', ','])
                    && !target.chars().any(char::is_control)
                    && target[1..]
                        .split('/')
                        .all(|part| !matches!(part, "" | "." | ".."));
                if !normalized_link
                    || !pack_root.join(&link).is_symlink()
                    || !valid_target
                    || !links.insert(link.clone())
                    || !targets.insert(target.clone())
                {
                    return Err("invalid or duplicate linked_data_roots link or target".into());
                }
                linked_roots.push((link, target));
            }
        }
        if profiles
            .iter()
            .any(|profile| profile == "linked-data-roots")
            != linked_declared
        {
            return Err("linked-data-roots profile and linked_data_roots list must both be present or absent".into());
        }
        Ok(Self {
            dockerfile: text(pack, "dockerfile", None)?,
            context: text(pack, "context", None)?,
            target: optional(pack, "target")?,
            image_tag: text(pack, "image_tag", None)?,
            platform: optional(pack, "platform")?,
            smoke_shell: text(smoke, "shell", Some("/bin/bash"))?,
            smoke_commands: strings(smoke, "commands")?,
            shell: text(runtime, "shell", Some("/bin/bash"))?,
            workdir: text(runtime, "workdir", Some("/workspace"))?,
            workspace_mount: text(runtime, "workspace_mount", Some("/workspace"))?,
            env: strings(runtime, "env")?,
            gpus: optional(runtime, "gpus")?,
            profiles,
            linked_roots,
            linked_declared,
        })
    }

    pub fn build_command(
        &self,
        root: &Path,
        builder: &str,
        pull: bool,
        no_cache: bool,
    ) -> Result<Vec<String>, String> {
        let mut command = vec![
            builder.into(),
            "build".into(),
            "-f".into(),
            absolute(root, &self.dockerfile)?.display().to_string(),
            "-t".into(),
            self.image_tag.clone(),
        ];
        if pull {
            command.push("--pull".into());
        }
        if no_cache {
            command.push("--no-cache".into());
        }
        for (flag, value) in [("--target", &self.target), ("--platform", &self.platform)] {
            if let Some(value) = value {
                command.extend([flag.into(), value.clone()]);
            }
        }
        command.push(absolute(root, &self.context)?.display().to_string());
        Ok(command)
    }
}

#[derive(Default, Debug)]
pub struct RunOptions {
    pub shell: Option<String>,
    pub workdir: Option<String>,
    pub workspace: Option<String>,
    pub env: Vec<String>,
    pub mounts: Vec<String>,
    pub ports: Vec<String>,
    pub gpus: Option<String>,
    pub user: Option<String>,
    pub tty: bool,
}

fn git_output(root: &Path, args: &[&str]) -> Option<String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn selected_profiles(pack: &ContainerPack) -> Result<Vec<String>, String> {
    let mut profiles = pack.profiles.clone();
    if let Some(value) = env::var_os("AGENT_CANON_OPTIONAL_MOUNTS") {
        let value = value
            .to_str()
            .ok_or("AGENT_CANON_OPTIONAL_MOUNTS must be UTF-8")?;
        let extra: Vec<_> = value.split(',').map(str::to_owned).collect();
        validate_profiles(&extra)?;
        for profile in extra {
            if !profiles.contains(&profile) {
                profiles.push(profile);
            }
        }
    }
    Ok(profiles)
}

fn mount_destination(mount: &str) -> Result<Option<PathBuf>, String> {
    let fields: Vec<_> = mount.split(',').collect();
    let long = fields.iter().any(|field| {
        matches!(
            field.split('=').next(),
            Some("type" | "source" | "src" | "target" | "dst" | "destination")
        )
    });
    let target = if long {
        Some(
            fields
                .iter()
                .find_map(|field| {
                    field
                        .split_once('=')
                        .filter(|(key, _)| matches!(*key, "target" | "dst" | "destination"))
                        .map(|(_, value)| value)
                })
                .ok_or(
                    "unsupported long Docker mount syntax; target, dst, or destination is required",
                )?,
        )
    } else {
        mount.split(':').nth(1)
    };
    target
        .filter(|target| Path::new(target).is_absolute())
        .map(|target| absolute(Path::new("/"), target))
        .transpose()
}

pub fn run_command(
    pack: &ContainerPack,
    root: &Path,
    builder: &str,
    payload: &[String],
    options: &RunOptions,
) -> Result<Vec<String>, String> {
    let root = root.canonicalize().map_err(|error| error.to_string())?;
    let profiles = selected_profiles(pack)?;
    if profiles
        .iter()
        .any(|profile| profile == "linked-data-roots")
        != pack.linked_declared
    {
        return Err("linked-data-roots profile and linked_data_roots list must match".into());
    }
    let mut mounts: Vec<String> = vec![];
    let mut protected: Vec<PathBuf> = vec![];
    if root.join(".git").is_file() {
        let common = git_output(&root, &["rev-parse", "--git-common-dir"])
            .ok_or("linked worktree Git metadata cannot be resolved")?;
        let git_dir = git_output(&root, &["rev-parse", "--git-dir"])
            .ok_or("linked worktree Git metadata cannot be resolved")?;
        let common = absolute(&root, common)?;
        if common != absolute(&root, git_dir)? {
            if !common.is_dir() {
                return Err("linked worktree Git common directory does not exist".into());
            }
            mounts.push(format!("{0}:{0}:ro", common.display()));
            protected.push(common);
        }
    }
    let mut sources = BTreeSet::new();
    for (link, target) in &pack.linked_roots {
        let source = root
            .join(link)
            .canonicalize()
            .map_err(|_| format!("linked_data_roots source does not resolve: {link}"))?;
        if !source.is_dir() || source != Path::new(target) || !sources.insert(source.clone()) {
            return Err(format!(
                "linked_data_roots target does not match resolved source: {link}"
            ));
        }
        mounts.push(format!("{}:{target}", source.display()));
        protected.push(source);
    }
    let docker_host = profiles.iter().any(|profile| profile == "docker-host");
    if docker_host {
        #[cfg(unix)]
        {
            use std::os::unix::fs::FileTypeExt;
            if !fs::metadata("/var/run/docker.sock")
                .is_ok_and(|metadata| metadata.file_type().is_socket())
            {
                return Err(
                    "docker-host profile requires an existing Unix socket: /var/run/docker.sock"
                        .into(),
                );
            }
            mounts.push("/var/run/docker.sock:/var/run/docker.sock".into());
        }
        #[cfg(not(unix))]
        return Err(
            "docker-host profile requires an existing Unix socket: /var/run/docker.sock".into(),
        );
    }
    for mount in &options.mounts {
        if let Some(destination) = mount_destination(mount)? {
            if protected
                .iter()
                .any(|target| destination.starts_with(target) || target.starts_with(&destination))
            {
                return Err("CLI mount destination collides with a linked-data-roots target or linked worktree Git metadata target".into());
            }
            if docker_host && destination == absolute(Path::new("/"), "/var/run/docker.sock")? {
                return Err("CLI mount destination collides with docker-host socket target".into());
            }
        }
        mounts.push(mount.clone());
    }
    let mut command = vec![builder.into(), "run".into(), "--rm".into()];
    if options.tty {
        command.extend(["-i".into(), "-t".into()]);
    }
    for (flag, value) in [
        ("--user", options.user.as_ref()),
        ("--gpus", options.gpus.as_ref().or(pack.gpus.as_ref())),
    ] {
        if let Some(value) = value {
            command.extend([flag.into(), value.clone()]);
        }
    }
    command.extend([
        "-v".into(),
        format!(
            "{}:{}",
            root.display(),
            options.workspace.as_ref().unwrap_or(&pack.workspace_mount)
        ),
    ]);
    for mount in mounts {
        command.extend(["-v".into(), mount]);
    }
    for port in &options.ports {
        command.extend(["-p".into(), port.clone()]);
    }
    let mut environment: Vec<(String, String)> = vec![];
    for item in pack.env.iter().chain(&options.env) {
        if let Some((key, value)) = item.split_once('=') {
            if let Some(old) = environment.iter_mut().find(|(name, _)| name == key) {
                old.1 = value.into();
            } else {
                environment.push((key.into(), value.into()));
            }
        }
    }
    for (key, value) in environment {
        command.extend(["-e".into(), format!("{key}={value}")]);
    }
    command.extend([
        "-w".into(),
        options.workdir.as_ref().unwrap_or(&pack.workdir).clone(),
        pack.image_tag.clone(),
    ]);
    if payload.is_empty() {
        command.push(options.shell.as_ref().unwrap_or(&pack.shell).clone());
    } else {
        command.extend_from_slice(payload);
    }
    Ok(command)
}

fn available(program: &str) -> bool {
    env::split_paths(&env::var_os("PATH").unwrap_or_default()).any(|directory| {
        directory.join(program).is_file()
            || cfg!(windows) && directory.join(format!("{program}.exe")).is_file()
    })
}

fn readiness(program: &str, root: &Path) -> Result<(), String> {
    use std::io::Read;
    let mut child = Command::new(program)
        .arg("info")
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;
    let read = |mut pipe: Box<dyn Read + Send>| {
        std::thread::spawn(move || {
            let mut bytes = vec![];
            pipe.read_to_end(&mut bytes).map(|_| bytes)
        })
    };
    let stdout = read(Box::new(
        child.stdout.take().ok_or("builder stdout unavailable")?,
    ));
    let stderr = read(Box::new(
        child.stderr.take().ok_or("builder stderr unavailable")?,
    ));
    let start = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) if start.elapsed() < Duration::from_secs(15) => {}
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(format!("{program} info timed out"));
            }
        }
        std::thread::sleep(Duration::from_millis(10));
    };
    let stdout = stdout
        .join()
        .map_err(|_| "builder stdout reader failed")?
        .map_err(|error| error.to_string())?;
    let stderr = stderr
        .join()
        .map_err(|_| "builder stderr reader failed")?
        .map_err(|error| error.to_string())?;
    if status?.success() {
        return Ok(());
    }
    let detail = if stderr.iter().any(|byte| !byte.is_ascii_whitespace()) {
        String::from_utf8_lossy(&stderr)
    } else {
        String::from_utf8_lossy(&stdout)
    };
    let detail = detail.trim().lines().next().unwrap_or("unknown error");
    if program == "docker" && detail.to_lowercase().contains("permission denied") {
        return Err("docker is installed but the daemon socket is not accessible. Use a user with docker access, switch to --builder podman, or run with --print-only.".into());
    }
    Err(format!("{program} is installed but not ready: {detail}"))
}

fn builder(requested: &str, preview: bool, root: &Path) -> Result<String, String> {
    let candidates = if requested == "auto" {
        vec!["docker", "podman"]
    } else {
        vec![requested]
    };
    let mut failures = vec![];
    for candidate in candidates {
        if !available(candidate) {
            continue;
        }
        if preview {
            return Ok(candidate.into());
        }
        match readiness(candidate, root) {
            Ok(()) => return Ok(candidate.into()),
            Err(error) => failures.push(error),
        }
    }
    if preview && requested == "auto" {
        return Ok("docker".into());
    }
    if preview {
        return Ok(requested.into());
    }
    Err(if failures.is_empty() {
        format!("Requested builder is not available: {requested}")
    } else {
        failures.join("; ")
    })
}

fn shell_quote(value: &str) -> String {
    if !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_@%+=:,./-".contains(&byte))
    {
        value.into()
    } else {
        format!("'{}'", value.replace('\'', "'\"'\"'"))
    }
}

fn print_command(label: &str, command: &[String]) {
    println!(
        "{label}:\n{}",
        command
            .iter()
            .map(|value| shell_quote(value))
            .collect::<Vec<_>>()
            .join(" ")
    );
}

fn execute(command: &[String], root: &Path) -> Result<i32, String> {
    Command::new(&command[0])
        .args(&command[1..])
        .current_dir(root)
        .status()
        .map(|status| {
            #[cfg(unix)]
            {
                use std::os::unix::process::ExitStatusExt;
                status
                    .code()
                    .unwrap_or_else(|| -status.signal().unwrap_or(1))
            }
            #[cfg(not(unix))]
            {
                status.code().unwrap_or(1)
            }
        })
        .map_err(|error| error.to_string())
}

#[derive(Default)]
struct Options {
    values: std::collections::BTreeMap<String, String>,
    flags: BTreeSet<String>,
    run: RunOptions,
    tail: Vec<String>,
}

fn parse(mode: &str, args: &[String]) -> Result<Option<Options>, String> {
    let mut options = Options::default();
    let mut index = 0;
    let value_options = [
        "pack",
        "builder",
        "dockerfile",
        "context",
        "target",
        "tag",
        "workspace-root",
        "container-workspace",
        "workdir",
        "shell",
        "env",
        "mount",
        "port",
        "gpus",
        "user",
        "rules",
    ];
    let flag_options = [
        "pull",
        "no-cache",
        "build-only",
        "skip-build",
        "print-only",
        "tty",
        "shell-session",
        "skip-run",
        "skip-env-check",
    ];
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "--help" | "-h") {
            return Ok(None);
        }
        if argument == "--" {
            options.tail.extend_from_slice(&args[index + 1..]);
            break;
        }
        if !argument.starts_with('-') {
            options.tail.push(argument.clone());
            if mode != "run-python-in-dockerfile" {
                options.tail.extend_from_slice(&args[index + 1..]);
                break;
            }
            index += 1;
            continue;
        }
        let (name, inline) = argument
            .trim_start_matches("--")
            .split_once('=')
            .map_or((argument.trim_start_matches("--"), None), |(key, value)| {
                (key, Some(value))
            });
        let candidates: Vec<_> = value_options
            .iter()
            .chain(&flag_options)
            .filter(|known| known.starts_with(name))
            .copied()
            .collect();
        let key = if value_options.contains(&name) || flag_options.contains(&name) {
            name
        } else if candidates.len() == 1 {
            candidates[0]
        } else {
            return Err(format!("unrecognized or ambiguous argument: {argument}"));
        };
        if flag_options.contains(&key) {
            if inline.is_some() {
                return Err(format!("{argument} does not take a value"));
            }
            options.flags.insert(key.into());
        } else {
            let value = if let Some(value) = inline {
                value.to_owned()
            } else {
                index += 1;
                args.get(index)
                    .cloned()
                    .ok_or_else(|| format!("--{key}: expected one argument"))?
            };
            match key {
                "env" => options.run.env.push(value),
                "mount" => options.run.mounts.push(value),
                "port" => options.run.ports.push(value),
                _ => {
                    options.values.insert(key.into(), value);
                }
            }
        }
        index += 1;
    }
    Ok(Some(options))
}

const ENV_CHECK: &str = "set -euo pipefail\npython3 --version\npython3 -m pip --version\nbash tools/validation/dependencies/docker_dependency_validator.sh\nif command -v cmake >/dev/null 2>&1; then cmake --version; fi\nif command -v ninja >/dev/null 2>&1; then ninja --version; fi\nif command -v docker >/dev/null 2>&1; then docker --version; fi";

fn run_inner(mode: &str, args: &[String]) -> Result<i32, String> {
    let Some(mut options) = parse(mode, args)? else {
        println!("usage: agent-canon {mode} [--pack PACK] [--builder auto|docker|podman] [--print-only] [options] [-- command ...]");
        return Ok(0);
    };
    let cwd = env::current_dir().map_err(|error| error.to_string())?;
    let default_root = git_output(&cwd, &["rev-parse", "--show-toplevel"])
        .map(PathBuf::from)
        .unwrap_or(cwd);
    let root = absolute(
        &default_root,
        options
            .values
            .get("workspace-root")
            .map_or(".", String::as_str),
    )?;
    let mut pack_path = options.values.get("pack").cloned();
    let mut payload = options.tail.clone();
    let program_mode = matches!(mode, "run-repo-program" | "run-python-in-dockerfile");
    let mut python_bin = "python3".to_string();
    let mut rule_workdir = None;
    let mut program_path = None;
    if program_mode {
        if mode == "run-python-in-dockerfile" {
            if payload.len() < 2 {
                return Err("dockerfile and python_file are required".into());
            }
            options
                .values
                .insert("dockerfile".into(), payload.remove(0));
        }
        let program = payload.first().ok_or("program is required")?;
        let selected = absolute(&root, program)?;
        if mode == "run-python-in-dockerfile" && !selected.is_file() {
            return Ok({
                eprintln!("Python file not found: {}", selected.display());
                1
            });
        }
        if selected.is_file() {
            program_path = Some(selected.clone());
        }
        if selected
            .extension()
            .is_some_and(|extension| extension == "py")
            && selected.is_file()
        {
            if let Some(rules) = options.values.get("rules") {
                let data = toml_file(&absolute(&root, rules)?)?;
                let empty = Value::Object(Default::default());
                let defaults = data.get("defaults").unwrap_or(&empty);
                if !defaults.is_object() {
                    return Err("[defaults] must be a table".into());
                }
                let default_pack =
                    text(defaults, "default_pack", Some("docker/packs/default.toml"))?;
                let rows = match data.get("rule") {
                    None => &[][..],
                    Some(Value::Array(rows)) => rows.as_slice(),
                    _ => return Err("[[rule]] entries must form a list".into()),
                };
                let relative = container_relative(&root, &selected)?;
                for row in rows {
                    if !row.is_object() {
                        return Err("rule entries must be tables".into());
                    }
                    let prefixes = strings(row, "match_roots")?;
                    if absolute(&root, text(row, "dockerfile", Some(""))?)?
                        == absolute(
                            &root,
                            options
                                .values
                                .get("dockerfile")
                                .map_or("docker/Dockerfile", String::as_str),
                        )?
                        && prefixes.iter().any(|prefix| relative.starts_with(prefix))
                    {
                        if pack_path.is_none() {
                            pack_path = Some(text(row, "pack", Some(&default_pack))?);
                        }
                        python_bin = text(row, "python_bin", Some("python3"))?;
                        rule_workdir = optional(row, "workdir")?;
                        break;
                    }
                }
            }
        }
    }
    let mut pack = ContainerPack::load(&root, pack_path.as_deref())?;
    for (key, target) in [
        ("dockerfile", &mut pack.dockerfile),
        ("context", &mut pack.context),
        ("tag", &mut pack.image_tag),
    ] {
        if let Some(value) = options.values.get(key) {
            *target = value.clone();
        }
    }
    if program_mode && !options.values.contains_key("dockerfile") {
        pack.dockerfile = "docker/Dockerfile".into();
    }
    if let Some(value) = options.values.get("target") {
        pack.target = Some(value.clone());
    }
    options.run.shell = options.values.get("shell").cloned();
    options.run.workdir = options.values.get("workdir").cloned();
    options.run.workspace = options.values.get("container-workspace").cloned();
    options.run.gpus = options.values.get("gpus").cloned();
    options.run.user = options.values.get("user").cloned();
    options.run.tty = options.flags.contains("tty");
    if program_mode {
        let program = payload.remove(0);
        if payload.first().is_some_and(|value| value == "--") {
            payload.remove(0);
        }
        let executable = if let Some(path) = &program_path {
            format!(
                "{}/{}",
                pack.workspace_mount.trim_end_matches('/'),
                container_relative(&root, path)?
            )
        } else {
            program
        };
        let mut prefix = match program_path
            .as_ref()
            .and_then(|path| path.extension())
            .and_then(|value| value.to_str())
        {
            Some("py") => vec![python_bin],
            Some("sh" | "bash") => vec![options
                .run
                .shell
                .clone()
                .unwrap_or_else(|| "/bin/bash".into())],
            _ => vec![],
        };
        prefix.push(executable);
        prefix.extend(payload);
        payload = prefix;
        if options.run.workdir.is_none() {
            options.run.workdir = rule_workdir.or_else(|| {
                (mode == "run-repo-program").then(|| {
                    let mount = pack.workspace_mount.trim_end_matches('/');
                    if mount.is_empty() {
                        "/".into()
                    } else {
                        mount.into()
                    }
                })
            });
        }
    }
    if options.flags.contains("shell-session") {
        payload.clear();
    }
    let preview = options.flags.contains("print-only");
    let selected_builder = options.values.get("builder").map_or("auto", String::as_str);
    if !matches!(selected_builder, "auto" | "docker" | "podman") {
        return Err("--builder must be auto, docker, or podman".into());
    }
    let builder = builder(selected_builder, preview, &root)?;
    let build = pack.build_command(
        &root,
        &builder,
        options.flags.contains("pull"),
        options.flags.contains("no-cache"),
    )?;
    let force = mode == "run-container-pack"
        || options.flags.contains("build-only")
        || options.flags.contains("pull")
        || options.flags.contains("no-cache");
    let build_requested = if preview || options.flags.contains("skip-build") {
        false
    } else if force {
        true
    } else {
        let image = Command::new(&builder)
            .args(["image", "inspect", "--format", "{{.Id}}", &pack.image_tag])
            .current_dir(&root)
            .stderr(Stdio::null())
            .output()
            .map_err(|error| error.to_string())?;
        !image.status.success() || image.stdout.iter().all(u8::is_ascii_whitespace)
    };
    print_command("build", &build);
    let mut commands = vec![];
    if mode == "run-container-pack" {
        let script = std::iter::once("set -euo pipefail")
            .chain(pack.smoke_commands.iter().map(String::as_str))
            .filter(|line| !line.trim().is_empty())
            .collect::<Vec<_>>()
            .join("\n");
        let smoke = run_command(
            &pack,
            &root,
            &builder,
            &[pack.smoke_shell.clone(), "-lc".into(), script],
            &RunOptions::default(),
        )?;
        print_command("smoke", &smoke);
        if !options.flags.contains("skip-run") {
            commands.push(smoke);
        }
    } else {
        if mode == "run-repo-program" && !options.flags.contains("skip-env-check") {
            let check = run_command(
                &pack,
                &root,
                &builder,
                &["/bin/bash".into(), "-lc".into(), ENV_CHECK.into()],
                &RunOptions {
                    env: options.run.env.clone(),
                    mounts: options.run.mounts.clone(),
                    ..Default::default()
                },
            )?;
            print_command("env-check", &check);
            commands.push(check);
        }
        if !options.flags.contains("build-only") {
            let run = run_command(&pack, &root, &builder, &payload, &options.run)?;
            print_command("run", &run);
            commands.push(run);
        }
    }
    if preview {
        return Ok(0);
    }
    if build_requested {
        let code = execute(&build, &root)?;
        if code != 0 {
            return Ok(code);
        }
    }
    for command in commands {
        let code = execute(&command, &root)?;
        if code != 0 {
            return Ok(code);
        }
    }
    Ok(0)
}

pub fn run(mode: &str, args: &[String]) -> i32 {
    match run_inner(mode, args) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("{error}");
            2
        }
    }
}
