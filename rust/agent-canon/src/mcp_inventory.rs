// @dependency-start
// responsibility Checks and scopes AgentCanon repo MCP preflight behavior.
// upstream design ../../../.codex/README.md documents MCP inventory preflight
// upstream design ../../../mcp/README.md documents repo MCP ownership
// upstream design ../../../issues/open/AC-20260517-mcp-inventory-preflight-cache.md records scoped preflight issue
// downstream implementation ../../../tools/bin/agent-canon invokes this command through the CLI wrapper
// @dependency-end

use serde_json::{json, Value};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

const CACHE_SCHEMA_VERSION: u64 = 1;
const DEFAULT_CACHE_TTL_SECONDS: u64 = 86_400;
const DEFAULT_SESSION_CACHE: &str = "reports/agents/.mcp_inventory_cache.json";
const FINGERPRINT_PATHS: &[&str] = &[
    ".codex/config.toml",
    "mcp",
    "rust/agent-canon/src/mcp_inventory.rs",
    "tools/agent_tools/check_mcp_inventory.py",
];

#[derive(Debug, Clone, PartialEq, Eq)]
struct Server {
    name: String,
    status: String,
    command: String,
    args: Vec<String>,
    cwd: String,
}

#[derive(Debug, PartialEq, Eq)]
struct InventoryArgs {
    root: PathBuf,
    required: Vec<String>,
    allow_empty: bool,
    codex_bin: String,
    cache_path: Option<PathBuf>,
    session_cache: bool,
    cache_ttl_seconds: u64,
    refresh_cache: bool,
}

#[derive(Debug, PartialEq, Eq)]
struct PolicyArgs {
    request_kind: String,
}

pub fn run_inventory(args: &[String]) -> i32 {
    match InventoryArgs::parse(args) {
        Ok(parsed) => run_inventory_checked(&parsed),
        Err(message) => {
            eprintln!("MCP_INVENTORY=fail");
            eprintln!("MCP_INVENTORY_ERROR={message}");
            2
        }
    }
}

pub fn run_policy(args: &[String]) -> i32 {
    match PolicyArgs::parse(args) {
        Ok(parsed) => {
            let decision = preflight_decision(&parsed.request_kind);
            println!("MCP_PREFLIGHT_POLICY=pass");
            println!("MCP_PREFLIGHT_SCOPE={}", parsed.request_kind);
            println!("MCP_PREFLIGHT_DECISION={}", decision.decision);
            println!("MCP_PREFLIGHT_REASON={}", decision.reason);
            0
        }
        Err(message) => {
            eprintln!("MCP_PREFLIGHT_POLICY=fail");
            eprintln!("MCP_PREFLIGHT_ERROR={message}");
            2
        }
    }
}

impl InventoryArgs {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut parsed = Self {
            root: PathBuf::from("."),
            required: Vec::new(),
            allow_empty: false,
            codex_bin: "codex".to_string(),
            cache_path: None,
            session_cache: false,
            cache_ttl_seconds: DEFAULT_CACHE_TTL_SECONDS,
            refresh_cache: false,
        };
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    parsed.root = value_path(args, index, "--root")?;
                    index += 2;
                }
                "--require" => {
                    parsed
                        .required
                        .push(value_string(args, index, "--require")?);
                    index += 2;
                }
                "--allow-empty" => {
                    parsed.allow_empty = true;
                    index += 1;
                }
                "--codex-bin" => {
                    parsed.codex_bin = value_string(args, index, "--codex-bin")?;
                    index += 2;
                }
                "--cache-path" => {
                    parsed.cache_path = Some(value_path(args, index, "--cache-path")?);
                    index += 2;
                }
                "--session-cache" => {
                    parsed.session_cache = true;
                    index += 1;
                }
                "--cache-ttl-seconds" => {
                    let raw = value_string(args, index, "--cache-ttl-seconds")?;
                    parsed.cache_ttl_seconds = raw.parse::<u64>().map_err(|_| {
                        format!("--cache-ttl-seconds must be an integer, got {raw}")
                    })?;
                    index += 2;
                }
                "--refresh-cache" => {
                    parsed.refresh_cache = true;
                    index += 1;
                }
                unknown => return Err(format!("unknown argument {unknown}")),
            }
        }
        Ok(parsed)
    }

    fn cache_file(&self) -> Option<PathBuf> {
        let configured = if self.session_cache {
            Some(PathBuf::from(DEFAULT_SESSION_CACHE))
        } else {
            self.cache_path.clone()
        }?;
        Some(resolve_under_root(&self.root, &configured))
    }
}

impl PolicyArgs {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut request_kind = "repository-task".to_string();
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--request-kind" => {
                    request_kind = value_string(args, index, "--request-kind")?;
                    index += 2;
                }
                unknown => return Err(format!("unknown argument {unknown}")),
            }
        }
        Ok(Self { request_kind })
    }
}

struct Decision {
    decision: &'static str,
    reason: &'static str,
}

fn preflight_decision(request_kind: &str) -> Decision {
    match request_kind {
        "consultation" | "brainstorming" | "routing-only" | "explanation-only" => Decision {
            decision: "skip",
            reason: "conversation_only",
        },
        "github-read" | "github-actions-read" | "ci-read" | "pr-read" | "issue-read" => Decision {
            decision: "skip",
            reason: "github_only_read_inspection",
        },
        "repo-read" | "repo-write" | "validation" | "implementation" | "pr-mutation"
        | "issue-sync" | "agent-canon-sync" | "adaptive-loop" | "repository-task" => Decision {
            decision: "required",
            reason: "local_repo_state_or_mutation",
        },
        _ => Decision {
            decision: "required",
            reason: "unknown_kind_defaults_fail_closed",
        },
    }
}

fn run_inventory_checked(args: &InventoryArgs) -> i32 {
    let root = args.root.clone();
    let fingerprint = surface_fingerprint(&root);
    if let Some(cache_file) = args.cache_file() {
        if !args.refresh_cache {
            if let Some(servers) = read_cache(&cache_file, args, &root, &fingerprint) {
                render_servers(&servers);
                println!("MCP_INVENTORY_CACHE=hit");
                println!("MCP_INVENTORY=pass");
                return 0;
            }
        }
    }

    let servers = match load_inventory(&args.codex_bin) {
        Ok(servers) => servers,
        Err(message) => {
            println!("MCP_INVENTORY=fail");
            println!("MCP_INVENTORY_ERROR={message}");
            return 1;
        }
    };

    render_servers(&servers);
    match validate_inventory(args, &root, &servers) {
        Ok(()) => {
            if let Some(cache_file) = args.cache_file() {
                if write_cache(&cache_file, args, &root, &fingerprint, &servers).is_ok() {
                    println!("MCP_INVENTORY_CACHE=written");
                }
            }
            println!("MCP_INVENTORY=pass");
            0
        }
        Err(lines) => {
            println!("MCP_INVENTORY=fail");
            for line in lines {
                println!("{line}");
            }
            1
        }
    }
}

fn validate_inventory(
    args: &InventoryArgs,
    root: &Path,
    servers: &[Server],
) -> Result<(), Vec<String>> {
    let configured: Vec<String> = servers.iter().map(|server| server.name.clone()).collect();
    let missing: Vec<String> = args
        .required
        .iter()
        .filter(|name| !configured.contains(name))
        .cloned()
        .collect();
    if !missing.is_empty() {
        return Err(missing_server_lines(root, &missing));
    }
    let launcher_issues: Vec<String> = servers
        .iter()
        .filter(|server| args.required.contains(&server.name))
        .flat_map(|server| launcher_errors(server, root))
        .collect();
    if !launcher_issues.is_empty() {
        let mut lines: Vec<String> = launcher_issues
            .into_iter()
            .map(|issue| format!("MCP_LAUNCHER_ERROR={issue}"))
            .collect();
        lines.push("NEXT_ACTION=fix_required_mcp_launcher_before_work".to_string());
        return Err(lines);
    }
    if servers.is_empty() && !args.allow_empty && args.required.is_empty() {
        return Err(vec![
            "MCP_INVENTORY_EMPTY=yes".to_string(),
            "NEXT_ACTION=pass_--allow-empty_or_--require_expected_servers".to_string(),
        ]);
    }
    Ok(())
}

fn missing_server_lines(root: &Path, missing: &[String]) -> Vec<String> {
    let declared = project_config_server_names(root);
    let ignored: Vec<String> = missing
        .iter()
        .filter(|name| declared.contains(*name))
        .cloned()
        .collect();
    let mut lines = vec![format!("MISSING_MCP_SERVERS={}", missing.join(","))];
    if ignored.is_empty() {
        lines.push("NEXT_ACTION=configure_required_mcp_servers_before_work".to_string());
        return lines;
    }
    lines.push("PROJECT_CODEX_CONFIG_DECLARES_MISSING_MCP=yes".to_string());
    lines.push(format!("PROJECT_CONFIG_MCP_SERVERS={}", declared.join(",")));
    lines.push("LIKELY_CAUSE=project_config_not_loaded_or_project_not_trusted".to_string());
    if ignored.iter().any(|name| name == "repo_mcp_server") {
        lines.push(
            "EXPECTED_REPO_MCP_LAUNCHER=.codex/config.toml -> bash mcp/repo_mcp_server.sh"
                .to_string(),
        );
        lines.push("REPAIR_REPO_MCP=trust_project_or_restore_.codex_and_mcp_link_root".to_string());
    }
    lines.push("NEXT_ACTION=trust_project_or_fix_codex_config_loading_before_work".to_string());
    lines
}

fn load_inventory(codex_bin: &str) -> Result<Vec<Server>, String> {
    let output = Command::new(codex_bin)
        .args(["mcp", "list", "--json"])
        .output()
        .map_err(|error| format!("`{codex_bin} mcp list --json` failed: {error}"))?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let fallback = String::from_utf8_lossy(&output.stdout).trim().to_string();
        return Err(format!(
            "`{codex_bin} mcp list --json` failed: {}",
            if detail.is_empty() { fallback } else { detail }
        ));
    }
    let text = String::from_utf8_lossy(&output.stdout);
    parse_inventory_json(&text)
}

fn parse_inventory_json(text: &str) -> Result<Vec<Server>, String> {
    let value: Value = serde_json::from_str(text)
        .map_err(|_| "`codex mcp list --json` returned invalid JSON".to_string())?;
    let array = value
        .as_array()
        .ok_or_else(|| "Codex MCP inventory JSON must be a list".to_string())?;
    Ok(array.iter().filter_map(server_from_value).collect())
}

fn server_from_value(value: &Value) -> Option<Server> {
    let object = value.as_object()?;
    let name = object.get("name")?.as_str()?.to_string();
    let status = object
        .get("status")
        .and_then(Value::as_str)
        .map(str::to_string)
        .unwrap_or_else(|| enabled_status(object.get("enabled")));
    let transport = object.get("transport").and_then(Value::as_object);
    let command = string_field(object.get("command"))
        .or_else(|| transport.and_then(|item| string_field(item.get("command"))))
        .unwrap_or_default();
    let args = string_array(object.get("args"))
        .or_else(|| transport.and_then(|item| string_array(item.get("args"))))
        .unwrap_or_default();
    let cwd = string_field(object.get("cwd"))
        .or_else(|| transport.and_then(|item| string_field(item.get("cwd"))))
        .unwrap_or_default();
    Some(Server {
        name,
        status,
        command,
        args,
        cwd,
    })
}

fn enabled_status(value: Option<&Value>) -> String {
    match value.and_then(Value::as_bool) {
        Some(true) => "enabled".to_string(),
        Some(false) => "disabled".to_string(),
        None => String::new(),
    }
}

fn string_field(value: Option<&Value>) -> Option<String> {
    value.and_then(Value::as_str).map(str::to_string)
}

fn string_array(value: Option<&Value>) -> Option<Vec<String>> {
    let array = value?.as_array()?;
    Some(
        array
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect(),
    )
}

fn render_servers(servers: &[Server]) {
    for server in servers {
        let status = if server.status.is_empty() {
            "(unknown)"
        } else {
            &server.status
        };
        let command = if server.command.is_empty() {
            "(unknown)"
        } else {
            &server.command
        };
        let args = if server.args.is_empty() {
            "(none)".to_string()
        } else {
            server.args.join(" ")
        };
        let cwd = if server.cwd.is_empty() {
            "(default)"
        } else {
            &server.cwd
        };
        println!(
            "MCP_SERVER={}\tstatus={status}\tcommand={command}\targs={args}\tcwd={cwd}",
            server.name
        );
    }
}

fn project_config_server_names(root: &Path) -> Vec<String> {
    let path = root.join(".codex/config.toml");
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let mut names: Vec<String> = text
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            trimmed
                .strip_prefix("[mcp_servers.")
                .and_then(|value| value.strip_suffix(']'))
                .map(|value| value.trim_matches('"').trim_matches('\'').to_string())
        })
        .filter(|name| !name.is_empty() && !name.chars().any(char::is_whitespace))
        .collect();
    names.sort();
    names.dedup();
    names
}

fn launcher_errors(server: &Server, root: &Path) -> Vec<String> {
    let (launch_root, mut errors) = launcher_root(server, root);
    if server.command.is_empty() {
        errors.push(format!("{}: missing launcher command", server.name));
        return errors;
    }
    if let Some(error) = command_error(server, &launch_root) {
        errors.push(error);
    }
    errors.extend(argument_errors(server, &launch_root));
    errors
}

fn launcher_root(server: &Server, root: &Path) -> (PathBuf, Vec<String>) {
    if server.cwd.is_empty() {
        return (root.to_path_buf(), Vec::new());
    }
    let cwd = resolve_under_root(root, &PathBuf::from(&server.cwd));
    if !cwd.exists() {
        return (
            root.to_path_buf(),
            vec![format!(
                "{}: launcher cwd path not found: {}",
                server.name, server.cwd
            )],
        );
    }
    if !cwd.is_dir() {
        return (
            root.to_path_buf(),
            vec![format!(
                "{}: launcher cwd is not a directory: {}",
                server.name, server.cwd
            )],
        );
    }
    (cwd, Vec::new())
}

fn command_error(server: &Server, launch_root: &Path) -> Option<String> {
    if server.command.contains('/') {
        let path = resolve_under_root(launch_root, &PathBuf::from(&server.command));
        if !path.exists() {
            return Some(format!(
                "{}: launcher command path not found: {}",
                server.name, server.command
            ));
        }
        return None;
    }
    if command_on_path(&server.command) {
        None
    } else {
        Some(format!(
            "{}: launcher command not found on PATH: {}",
            server.name, server.command
        ))
    }
}

fn argument_errors(server: &Server, launch_root: &Path) -> Vec<String> {
    server
        .args
        .iter()
        .filter(|arg| !arg.starts_with('-') && arg.contains('/'))
        .filter_map(|arg| {
            let path = resolve_under_root(launch_root, &PathBuf::from(arg));
            if path.exists() {
                None
            } else {
                Some(format!(
                    "{}: launcher argument path not found: {arg}",
                    server.name
                ))
            }
        })
        .collect()
}

fn command_on_path(command: &str) -> bool {
    env::var_os("PATH")
        .map(|paths| env::split_paths(&paths).any(|path| path.join(command).exists()))
        .unwrap_or(false)
}

fn surface_fingerprint(root: &Path) -> String {
    let mut state = 0xcbf2_9ce4_8422_2325_u64;
    for relative in FINGERPRINT_PATHS {
        let path = root.join(relative);
        if path.is_dir() {
            for child in sorted_files(&path) {
                hash_file(&mut state, root, &child);
            }
        } else {
            hash_file(&mut state, root, &path);
        }
    }
    format!("{state:016x}")
}

fn sorted_files(path: &Path) -> Vec<PathBuf> {
    let mut files = Vec::new();
    collect_files(path, &mut files);
    files.sort();
    files
}

fn collect_files(path: &Path, files: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(path) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_files(&path, files);
        } else if path.is_file() {
            files.push(path);
        }
    }
}

fn hash_file(state: &mut u64, root: &Path, path: &Path) {
    let relative = path.strip_prefix(root).unwrap_or(path).to_string_lossy();
    fnv_update(state, relative.as_bytes());
    if let Ok(bytes) = fs::read(path) {
        fnv_update(state, b"\0present\0");
        fnv_update(state, &bytes);
    } else {
        fnv_update(state, b"\0missing");
    }
}

fn fnv_update(state: &mut u64, bytes: &[u8]) {
    for byte in bytes {
        *state ^= u64::from(*byte);
        *state = state.wrapping_mul(0x0000_0100_0000_01b3);
    }
}

fn read_cache(
    path: &Path,
    args: &InventoryArgs,
    root: &Path,
    fingerprint: &str,
) -> Option<Vec<Server>> {
    let text = fs::read_to_string(path).ok()?;
    let value: Value = serde_json::from_str(&text).ok()?;
    if value.get("schema_version")?.as_u64()? != CACHE_SCHEMA_VERSION {
        return None;
    }
    if value.get("root")?.as_str()? != root_string(root) {
        return None;
    }
    if value.get("codex_bin")?.as_str()? != args.codex_bin {
        return None;
    }
    if value.get("fingerprint")?.as_str()? != fingerprint {
        return None;
    }
    if cached_required(&value)? != sorted_required(&args.required) {
        return None;
    }
    if !cache_age_valid(&value, args.cache_ttl_seconds) {
        return None;
    }
    let servers = value.get("servers")?.as_array()?;
    Some(servers.iter().filter_map(server_from_value).collect())
}

fn cached_required(value: &Value) -> Option<Vec<String>> {
    let mut required: Vec<String> = value
        .get("required")?
        .as_array()?
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect();
    required.sort();
    Some(required)
}

fn cache_age_valid(value: &Value, ttl_seconds: u64) -> bool {
    let Some(created_at) = value.get("created_at").and_then(Value::as_u64) else {
        return false;
    };
    now_seconds()
        .checked_sub(created_at)
        .map(|age| age <= ttl_seconds)
        .unwrap_or(false)
}

fn write_cache(
    path: &Path,
    args: &InventoryArgs,
    root: &Path,
    fingerprint: &str,
    servers: &[Server],
) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let payload = json!({
        "schema_version": CACHE_SCHEMA_VERSION,
        "root": root_string(root),
        "required": sorted_required(&args.required),
        "codex_bin": args.codex_bin,
        "fingerprint": fingerprint,
        "created_at": now_seconds(),
        "servers": servers.iter().map(server_json).collect::<Vec<Value>>(),
    });
    fs::write(
        path,
        serde_json::to_string_pretty(&payload).map_err(|error| error.to_string())? + "\n",
    )
    .map_err(|error| error.to_string())
}

fn server_json(server: &Server) -> Value {
    json!({
        "name": server.name,
        "status": server.status,
        "command": server.command,
        "args": server.args,
        "cwd": server.cwd,
    })
}

fn now_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0)
}

fn sorted_required(required: &[String]) -> Vec<String> {
    let mut values = required.to_vec();
    values.sort();
    values.dedup();
    values
}

fn root_string(root: &Path) -> &str {
    root.to_str().unwrap_or(".")
}

fn resolve_under_root(root: &Path, path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        root.join(path)
    }
}

fn value_string(args: &[String], index: usize, name: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{name} requires a value"))
}

fn value_path(args: &[String], index: usize, name: &str) -> Result<PathBuf, String> {
    Ok(PathBuf::from(value_string(args, index, name)?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_nested_transport_inventory() {
        let servers = parse_inventory_json(
            r#"[{"name":"repo_mcp_server","enabled":true,"transport":{"command":"bash","args":["mcp/repo_mcp_server.sh"],"cwd":"."}}]"#,
        )
        .expect("inventory should parse");

        assert_eq!(servers[0].name, "repo_mcp_server");
        assert_eq!(servers[0].status, "enabled");
        assert_eq!(servers[0].command, "bash");
        assert_eq!(servers[0].args, vec!["mcp/repo_mcp_server.sh"]);
        assert_eq!(servers[0].cwd, ".");
    }

    #[test]
    fn policy_skips_github_only_read_inspection() {
        let decision = preflight_decision("github-actions-read");

        assert_eq!(decision.decision, "skip");
        assert_eq!(decision.reason, "github_only_read_inspection");
    }

    #[test]
    fn policy_requires_repo_mutation() {
        let decision = preflight_decision("implementation");

        assert_eq!(decision.decision, "required");
        assert_eq!(decision.reason, "local_repo_state_or_mutation");
    }

    #[test]
    fn cache_round_trip_reuses_valid_inventory() {
        let root = fixture_root("cache-round-trip");
        write_fixture(&root);
        let args = InventoryArgs {
            root: root.clone(),
            required: vec!["repo_mcp_server".to_string()],
            allow_empty: false,
            codex_bin: "codex".to_string(),
            cache_path: Some(PathBuf::from("cache.json")),
            session_cache: false,
            cache_ttl_seconds: DEFAULT_CACHE_TTL_SECONDS,
            refresh_cache: false,
        };
        let servers = vec![Server {
            name: "repo_mcp_server".to_string(),
            status: "enabled".to_string(),
            command: "bash".to_string(),
            args: vec!["mcp/repo_mcp_server.sh".to_string()],
            cwd: ".".to_string(),
        }];
        let fingerprint = surface_fingerprint(&root);
        let cache = args.cache_file().expect("cache path");

        write_cache(&cache, &args, &root, &fingerprint, &servers).expect("write cache");
        let cached = read_cache(&cache, &args, &root, &fingerprint).expect("read cache");

        assert_eq!(cached, servers);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn cache_invalidates_when_mcp_surface_changes() {
        let root = fixture_root("cache-invalidates");
        write_fixture(&root);
        let args = InventoryArgs {
            root: root.clone(),
            required: vec!["repo_mcp_server".to_string()],
            allow_empty: false,
            codex_bin: "codex".to_string(),
            cache_path: Some(PathBuf::from("cache.json")),
            session_cache: false,
            cache_ttl_seconds: DEFAULT_CACHE_TTL_SECONDS,
            refresh_cache: false,
        };
        let servers = vec![Server {
            name: "repo_mcp_server".to_string(),
            status: "enabled".to_string(),
            command: "bash".to_string(),
            args: vec!["mcp/repo_mcp_server.sh".to_string()],
            cwd: ".".to_string(),
        }];
        let before = surface_fingerprint(&root);
        let cache = args.cache_file().expect("cache path");
        write_cache(&cache, &args, &root, &before, &servers).expect("write cache");
        fs::write(root.join(".codex/config.toml"), "[mcp_servers.other]\n").expect("mutate config");
        let after = surface_fingerprint(&root);

        assert_ne!(before, after);
        assert!(read_cache(&cache, &args, &root, &after).is_none());
        let _ = fs::remove_dir_all(root);
    }

    fn fixture_root(label: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        env::temp_dir().join(format!("agent-canon-mcp-{label}-{suffix}"))
    }

    fn write_fixture(root: &Path) {
        fs::create_dir_all(root.join(".codex")).expect("mkdir codex");
        fs::create_dir_all(root.join("mcp")).expect("mkdir mcp");
        fs::create_dir_all(root.join("rust/agent-canon/src")).expect("mkdir rust src");
        fs::create_dir_all(root.join("tools/agent_tools")).expect("mkdir tools");
        fs::write(
            root.join(".codex/config.toml"),
            "[mcp_servers.repo_mcp_server]\ncommand = \"bash\"\n",
        )
        .expect("write config");
        fs::write(root.join("mcp/repo_mcp_server.sh"), "#!/usr/bin/env bash\n")
            .expect("write launcher");
        fs::write(
            root.join("rust/agent-canon/src/mcp_inventory.rs"),
            "fixture\n",
        )
        .expect("write rust source");
        fs::write(
            root.join("tools/agent_tools/check_mcp_inventory.py"),
            "fixture\n",
        )
        .expect("write python source");
    }
}
