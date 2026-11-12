// @dependency-start
// contract implementation
// responsibility Reports main server host readiness from the native CLI and an optional layout.
// upstream design ../../../../../documents/contracts/server-host-contract.md current server host requirements
// downstream implementation ../../../../../tools/bin/agent-canon exposes the native command
// downstream test ../tests/server_readiness_native.rs checks controlled host snapshots
// @dependency-end

use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output};

const WORKSPACE_ROOT_ENV: &str = "AGENT_CANON_HOST_WORKSPACE_ROOT";
const DOCKER_SOCKET: &str = "/var/run/docker.sock";
pub const SELECTOR: &str = "server-readiness";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Finding {
    pub level: &'static str,
    pub message: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MountInfo {
    pub source: String,
    pub fs_type: String,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
pub struct Layout {
    pub(crate) server: ServerLayout,
    pub(crate) paths: BTreeMap<String, String>,
    pub(crate) mounts: BTreeMap<String, MountExpectation>,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
pub(crate) struct ServerLayout {
    pub(crate) host_kind: Option<String>,
    pub(crate) container_builder: Option<String>,
    pub(crate) codex_cli_required: bool,
    pub(crate) python_bin: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
pub(crate) struct MountExpectation {
    #[serde(rename = "type")]
    pub(crate) fs_type: Option<String>,
    pub(crate) required: bool,
}

#[derive(Clone, Debug, Default)]
pub struct Context {
    pub host_kind: String,
    pub kernel: String,
    pub username: String,
    pub active_groups: Vec<String>,
    pub commands: BTreeMap<String, bool>,
    pub mounts: BTreeMap<PathBuf, MountInfo>,
    pub mount_table_error: Option<String>,
    pub docker_socket_exists: bool,
    pub docker_socket_accessible: bool,
    pub docker_version: Option<CommandStatus>,
    pub docker_group_members: BTreeSet<String>,
    pub workspace_root: Option<PathBuf>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CommandStatus {
    pub succeeded: bool,
    pub detail: String,
}

#[derive(Clone, Debug, Default)]
pub struct Report {
    pub(crate) summary: Vec<String>,
    pub findings: Vec<Finding>,
}

impl Report {
    pub fn exit_code(&self) -> i32 {
        if self.findings.iter().any(|finding| finding.level == "error") {
            1
        } else {
            0
        }
    }
}

enum ParsedArgs {
    Help,
    Options(Option<PathBuf>),
}

/// Run `agent-canon server-readiness`.
pub fn run(args: &[String]) -> i32 {
    let layout_path = match parse_args(args) {
        Ok(ParsedArgs::Help) => {
            print_help();
            return 0;
        }
        Ok(ParsedArgs::Options(path)) => path,
        Err(error) => {
            eprintln!("usage: agent-canon {SELECTOR} [--layout <layout.toml>]");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };

    let layout = match layout_path.as_deref().map(load_layout).transpose() {
        Ok(layout) => layout,
        Err(error) => {
            eprintln!("{error}");
            return 2;
        }
    };
    let context = Context::capture(layout.as_ref());
    let report = evaluate(layout.as_ref(), &context);
    for line in &report.summary {
        println!("{line}");
    }
    for finding in &report.findings {
        println!(
            "{}: {}",
            finding.level.to_ascii_uppercase(),
            finding.message
        );
    }
    report.exit_code()
}

fn parse_args(args: &[String]) -> Result<ParsedArgs, String> {
    let mut layout = None;
    let mut index = 0;
    while index < args.len() {
        let token = args[index].as_str();
        let (option, inline_value) = token
            .split_once('=')
            .map_or((token, None), |(option, value)| (option, Some(value)));
        match option {
            "-h" | "--help" if inline_value.is_none() => return Ok(ParsedArgs::Help),
            option
                if option.starts_with("--")
                    && option.len() > 2
                    && "--layout".starts_with(option) =>
            {
                let value = if let Some(value) = inline_value {
                    value
                } else {
                    index += 1;
                    args.get(index)
                        .ok_or_else(|| "argument --layout: expected one path".to_owned())?
                };
                layout = Some(PathBuf::from(value));
            }
            _ => return Err(format!("unrecognized argument: {token}")),
        }
        index += 1;
    }
    Ok(ParsedArgs::Options(layout))
}

fn print_help() {
    println!(
        "Inspect host readiness for a main server.\n\n\
         usage: agent-canon {SELECTOR} [--layout <layout.toml>]\n\n\
         options:\n\
         -h, --help       Print help and exit\n\
         --layout PATH   Check paths, mounts, and explicitly selected providers"
    );
}

fn load_layout(path: &Path) -> Result<Layout, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    parse_layout(&text).map_err(|error| format!("{}: {error}", path.display()))
}

pub fn parse_layout(text: &str) -> Result<Layout, String> {
    toml_edit::de::from_str(text).map_err(|error| format!("invalid server layout: {error}"))
}

impl Context {
    fn capture(layout: Option<&Layout>) -> Self {
        let uname = command_output("uname", &["-a"]);
        let kernel = uname
            .as_ref()
            .map(output_detail)
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| env::consts::OS.to_owned());
        let lower_kernel = kernel.to_ascii_lowercase();
        let host_kind = if lower_kernel.contains("microsoft") || lower_kernel.contains("wsl") {
            "wsl2".to_owned()
        } else {
            env::consts::OS.to_owned()
        };
        let username = env::var("USER")
            .ok()
            .filter(|value| !value.is_empty())
            .or_else(|| command_text("id", &["-un"]))
            .unwrap_or_else(|| "unknown".to_owned());
        let active_groups = command_text("id", &["-Gn"])
            .map(|value| value.split_whitespace().map(str::to_owned).collect())
            .unwrap_or_default();

        let mut requested_commands =
            BTreeSet::from(["git".to_owned(), "docker".to_owned(), "podman".to_owned()]);
        if let Some(layout) = layout {
            if layout.server.codex_cli_required {
                requested_commands.insert("codex".to_owned());
            }
            if let Some(python_bin) = &layout.server.python_bin {
                requested_commands.insert(python_bin.clone());
            }
            if let Some(builder) = &layout.server.container_builder {
                requested_commands.insert(builder.clone());
            }
        }
        let commands = requested_commands
            .into_iter()
            .map(|name| {
                let available = command_exists(&name);
                (name, available)
            })
            .collect::<BTreeMap<_, _>>();

        let docker_socket_path = Path::new(DOCKER_SOCKET);
        let docker_socket_exists = docker_socket_path.exists();
        let docker_socket_accessible =
            docker_socket_exists && path_is_read_write(docker_socket_path);
        let mounts_result = parse_mounts_file(Path::new("/proc/mounts"));
        let (mounts, mount_table_error) = match mounts_result {
            Ok(mounts) => (mounts, None),
            Err(error) => (BTreeMap::new(), Some(error)),
        };
        let docker_version = commands
            .get("docker")
            .copied()
            .filter(|exists| *exists)
            .and_then(|_| command_output("docker", &["version"]))
            .map(|output| CommandStatus {
                succeeded: output.status.success(),
                detail: output_detail(&output),
            });
        let docker_group_members = command_text("getent", &["group", "docker"])
            .and_then(|line| line.rsplit(':').next().map(str::to_owned))
            .map(|members| {
                members
                    .split(',')
                    .filter(|member| !member.is_empty())
                    .map(str::to_owned)
                    .collect()
            })
            .unwrap_or_default();

        Self {
            host_kind,
            kernel,
            username,
            active_groups,
            commands,
            mounts,
            mount_table_error,
            docker_socket_exists,
            docker_socket_accessible,
            docker_version,
            docker_group_members,
            workspace_root: env::var_os(WORKSPACE_ROOT_ENV).map(PathBuf::from),
        }
    }
}

pub fn evaluate(layout: Option<&Layout>, context: &Context) -> Report {
    let mut report = Report::default();
    report
        .summary
        .push(format!("host_kind={}", context.host_kind));
    report.summary.push(format!("kernel={}", context.kernel));
    report.summary.push(format!("user={}", context.username));
    report
        .summary
        .push(format!("active_groups={}", context.active_groups.join(",")));

    add_command_finding(&mut report, context, "git", true);
    let server = layout.map(|value| &value.server);
    if server.is_some_and(|value| value.codex_cli_required) {
        add_command_finding(&mut report, context, "codex", true);
    }
    if let Some(python_bin) = server.and_then(|value| value.python_bin.as_deref()) {
        add_command_finding(&mut report, context, python_bin, true);
    }

    let expected_builder = server.and_then(|value| value.container_builder.as_deref());
    if let Some(builder) = expected_builder {
        add_command_finding(&mut report, context, builder, true);
    }
    report_container_runtime(&mut report, context, expected_builder);

    if let Some(workspace_root) = &context.workspace_root {
        check_optional_path(&mut report, context, "workspace_root", workspace_root);
    }

    if let Some(layout) = layout {
        if let Some(expected_host_kind) = &layout.server.host_kind {
            if expected_host_kind != &context.host_kind {
                report.findings.push(Finding {
                    level: "warning",
                    message: format!(
                        "layout host_kind={expected_host_kind} but detected host_kind={}",
                        context.host_kind
                    ),
                });
            }
        }
        for (key, raw_path) in &layout.paths {
            let path = PathBuf::from(raw_path);
            check_path(&mut report, key, &path);
            let expected_mount = layout.mounts.get(key);
            report_mount_for_path(&mut report, context, key, &path, expected_mount);
        }
    }
    report
}

fn add_command_finding(report: &mut Report, context: &Context, name: &str, required: bool) {
    if context.commands.get(name).copied().unwrap_or(false) {
        report.findings.push(Finding {
            level: "ok",
            message: format!("{name} is available"),
        });
    } else {
        report.findings.push(Finding {
            level: if required { "error" } else { "warning" },
            message: format!("{name} is not available"),
        });
    }
}

fn report_container_runtime(
    report: &mut Report,
    context: &Context,
    expected_builder: Option<&str>,
) {
    let docker_exists = context.commands.get("docker").copied().unwrap_or(false);
    let podman_exists = context.commands.get("podman").copied().unwrap_or(false);
    if docker_exists {
        report.findings.push(Finding {
            level: "ok",
            message: "docker CLI is available".to_owned(),
        });
    } else if podman_exists {
        report.findings.push(Finding {
            level: "warning",
            message: "docker CLI is absent but podman is available".to_owned(),
        });
    } else {
        report.findings.push(Finding {
            level: "warning",
            message: "no container CLI is available; a builder is required only when selected by the layout".to_owned(),
        });
    }

    let docker_required = expected_builder == Some("docker");
    if context.docker_socket_exists {
        if let Some((_, mount)) = mount_for_path(Path::new(DOCKER_SOCKET), &context.mounts) {
            report
                .summary
                .push(format!("docker_socket_fs={}", mount.fs_type));
        }
        if context.docker_socket_accessible {
            report.findings.push(Finding {
                level: "ok",
                message: "docker socket is accessible from the current shell".to_owned(),
            });
        } else {
            report.findings.push(Finding {
                level: if docker_required
                    && context
                        .docker_version
                        .as_ref()
                        .is_none_or(|result| !result.succeeded)
                {
                    "error"
                } else {
                    "warning"
                },
                message: "docker socket exists but is not accessible from the current shell"
                    .to_owned(),
            });
        }
        if context.docker_group_members.contains(&context.username)
            && context
                .docker_version
                .as_ref()
                .is_some_and(|result| !result.succeeded)
            && !context.active_groups.iter().any(|group| group == "docker")
        {
            report.findings.push(Finding {
                level: "warning",
                message:
                    "user is listed in docker group but the current shell does not have that group"
                        .to_owned(),
            });
        }
    } else {
        report.findings.push(Finding {
            level: "warning",
            message: format!("{DOCKER_SOCKET} is absent"),
        });
    }

    if let Some(result) = &context.docker_version {
        if result.succeeded {
            report.findings.push(Finding {
                level: "ok",
                message: "docker version succeeded".to_owned(),
            });
        } else {
            report.findings.push(Finding {
                level: if docker_required { "error" } else { "warning" },
                message: format!("docker version failed: {}", result.detail),
            });
        }
    }
}

fn check_path(report: &mut Report, label: &str, path: &Path) {
    let (level, status) = if path.exists() {
        ("ok", "exists")
    } else {
        ("warning", "does not exist")
    };
    report.findings.push(Finding {
        level,
        message: format!("{label} {status}: {}", path.display()),
    });
}

fn check_optional_path(report: &mut Report, context: &Context, label: &str, path: &Path) {
    if path.exists() {
        let mount_label = mount_for_path(path, &context.mounts)
            .map(|(_, mount)| format!("{} from {}", mount.fs_type, mount.source))
            .unwrap_or_else(|| "unknown".to_owned());
        report.findings.push(Finding {
            level: "ok",
            message: format!("{label} exists ({mount_label})"),
        });
    } else {
        report.findings.push(Finding {
            level: "warning",
            message: format!("{label} does not exist: {}", path.display()),
        });
    }
}

fn report_mount_for_path(
    report: &mut Report,
    context: &Context,
    key: &str,
    path: &Path,
    expectation: Option<&MountExpectation>,
) {
    let Some(expectation) = expectation else {
        return;
    };
    let required = expectation.required;
    let Some((_, actual)) = mount_for_path(path, &context.mounts) else {
        if required {
            let detail = context
                .mount_table_error
                .as_deref()
                .map(|error| format!(" ({error})"))
                .unwrap_or_default();
            report.findings.push(Finding {
                level: "error",
                message: format!(
                    "no mount information found for required path: {}{detail}",
                    path.display()
                ),
            });
        }
        return;
    };
    if let Some(expected_type) = &expectation.fs_type {
        if expected_type != &actual.fs_type {
            report.findings.push(Finding {
                level: if required { "error" } else { "warning" },
                message: format!(
                    "{key} mount type mismatch: expected {expected_type}, got {}",
                    actual.fs_type
                ),
            });
            return;
        }
    }
    report.findings.push(Finding {
        level: "ok",
        message: format!("{key} mount type matches: {}", actual.fs_type),
    });
}

fn parse_mounts_file(path: &Path) -> Result<BTreeMap<PathBuf, MountInfo>, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    Ok(parse_mounts_text(&text))
}

pub fn parse_mounts_text(text: &str) -> BTreeMap<PathBuf, MountInfo> {
    text.lines()
        .filter_map(|line| {
            let mut fields = line.split_whitespace();
            let source = fields.next()?;
            let mountpoint = fields.next()?;
            let fs_type = fields.next()?;
            Some((
                PathBuf::from(unescape_mount_field(mountpoint)),
                MountInfo {
                    source: unescape_mount_field(source),
                    fs_type: fs_type.to_owned(),
                },
            ))
        })
        .collect()
}

fn unescape_mount_field(value: &str) -> String {
    value
        .replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
}

fn mount_for_path<'a>(
    path: &Path,
    mounts: &'a BTreeMap<PathBuf, MountInfo>,
) -> Option<(&'a PathBuf, &'a MountInfo)> {
    let resolved = normalized_path(path);
    mounts
        .iter()
        .filter(|(mountpoint, _)| resolved.starts_with(mountpoint))
        .max_by_key(|(mountpoint, _)| mountpoint.components().count())
}

fn normalized_path(path: &Path) -> PathBuf {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    };
    if let Ok(canonical) = absolute.canonicalize() {
        return canonical;
    }
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

fn command_exists(name: &str) -> bool {
    let path = Path::new(name);
    if path.components().count() > 1 {
        return is_executable(path);
    }
    env::var_os("PATH")
        .into_iter()
        .flat_map(|paths| env::split_paths(&paths).collect::<Vec<_>>())
        .map(|directory| directory.join(name))
        .any(|candidate| is_executable(&candidate))
}

fn is_executable(path: &Path) -> bool {
    let Ok(metadata) = fs::metadata(path) else {
        return false;
    };
    if !metadata.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        true
    }
}

fn command_output(command: &str, args: &[&str]) -> Option<Output> {
    Command::new(command).args(args).output().ok()
}

fn command_text(command: &str, args: &[&str]) -> Option<String> {
    let output = command_output(command, args)?;
    output.status.success().then(|| output_detail(&output))
}

fn output_detail(output: &Output) -> String {
    let stderr = String::from_utf8_lossy(&output.stderr);
    let stderr = stderr.trim();
    if !stderr.is_empty() {
        return stderr.lines().next().unwrap_or("(no output)").to_owned();
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stdout = stdout.trim();
    if !stdout.is_empty() {
        return stdout.lines().next().unwrap_or("(no output)").to_owned();
    }
    "(no output)".to_owned()
}

fn path_is_read_write(path: &Path) -> bool {
    #[cfg(unix)]
    {
        Command::new("test")
            .arg("-r")
            .arg(path)
            .arg("-a")
            .arg("-w")
            .arg(path)
            .status()
            .is_ok_and(|status| status.success())
    }
    #[cfg(not(unix))]
    {
        let _ = path;
        false
    }
}

#[cfg(test)]
mod tests {
    use super::{mount_for_path, parse_args, parse_mounts_text, MountInfo, ParsedArgs};
    use std::collections::BTreeMap;
    use std::path::{Path, PathBuf};

    #[test]
    fn mount_for_path_selects_the_longest_component_prefix() {
        let mounts = BTreeMap::from([
            (
                PathBuf::from("/srv"),
                MountInfo {
                    source: "/dev/root".to_owned(),
                    fs_type: "ext4".to_owned(),
                },
            ),
            (
                PathBuf::from("/srv/workspace"),
                MountInfo {
                    source: "//files/workspace".to_owned(),
                    fs_type: "cifs".to_owned(),
                },
            ),
        ]);

        let (mountpoint, info) =
            mount_for_path(PathBuf::from("/srv/workspace/repo").as_path(), &mounts)
                .expect("the nested workspace mount must be selected");
        assert_eq!(mountpoint, &PathBuf::from("/srv/workspace"));
        assert_eq!(info.fs_type, "cifs");
        assert!(
            mount_for_path(PathBuf::from("/srv/workspace-old").as_path(), &mounts).is_some_and(
                |(mountpoint, info)| {
                    mountpoint == &PathBuf::from("/srv") && info.fs_type == "ext4"
                }
            )
        );
    }

    #[test]
    fn mount_parser_unescapes_linux_mount_fields() {
        let mounts = parse_mounts_text("//files/team\\040share /srv/team\\040share cifs rw 0 0\n");
        assert_eq!(
            mounts
                .get(&PathBuf::from("/srv/team share"))
                .map(|info| info.fs_type.as_str()),
            Some("cifs")
        );
        assert_eq!(
            mounts
                .get(&PathBuf::from("/srv/team share"))
                .map(|info| info.source.as_str()),
            Some("//files/team share")
        );
    }

    #[test]
    fn layout_option_accepts_argparse_prefix_and_equals_forms() {
        let prefix = vec!["--lay".to_owned(), "server.toml".to_owned()];
        let equals = vec!["--layout=server.toml".to_owned()];

        assert!(matches!(
            parse_args(&prefix),
            Ok(ParsedArgs::Options(Some(path))) if path == Path::new("server.toml")
        ));
        assert!(matches!(
            parse_args(&equals),
            Ok(ParsedArgs::Options(Some(path))) if path == Path::new("server.toml")
        ));
    }
}
