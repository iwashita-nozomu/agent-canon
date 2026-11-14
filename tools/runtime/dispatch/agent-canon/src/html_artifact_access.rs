//! Render browser/server/tunnel argv for an existing HTML artifact.

use crate::lean_proof_env::shell_join;
use crate::path_expansion::expand_user_path;
use crate::path_resolution::resolve_non_strict;
use crate::python_cli_options::resolve_long_option_prefix;
use serde_json::{json, Value};
use std::net::ToSocketAddrs;
use std::path::Path;
use std::process::Command;

fn runtime_ip() -> Result<String, String> {
    let output = Command::new("hostname")
        .output()
        .map_err(|error| error.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().into());
    }
    let hostname = String::from_utf8(output.stdout).map_err(|error| error.to_string())?;
    let hostname = hostname.trim();
    let addresses: Vec<_> = (hostname, 0)
        .to_socket_addrs()
        .map_err(|error| error.to_string())?
        .filter_map(|address| match address.ip() {
            std::net::IpAddr::V4(address) => Some(address.to_string()),
            _ => None,
        })
        .collect();
    Ok(addresses
        .iter()
        .find(|address| !address.starts_with("127."))
        .or_else(|| addresses.first())
        .cloned()
        .unwrap_or_else(|| hostname.into()))
}

fn plan(args: &[String]) -> Result<(Value, bool), String> {
    let options = [
        ("--ssh-host", 0),
        ("--port", 1),
        ("--bind", 2),
        ("--tunnel-target", 3),
        ("--use-container-ip", 4),
        ("--format", 5),
    ];
    let mut values = [
        String::new(),
        "8765".to_owned(),
        String::new(),
        String::new(),
        String::new(),
        "text".to_owned(),
    ];
    let mut report = None;
    let mut container = false;
    let mut positional = false;
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if argument == "--" && !positional {
            positional = true;
            index += 1;
            continue;
        }
        if argument.starts_with("--") && !positional {
            let (key, inline) = argument
                .split_once('=')
                .map_or((argument.as_str(), None), |(key, value)| (key, Some(value)));
            let field = resolve_long_option_prefix(key, &options)
                .map_err(|_| format!("unrecognized or ambiguous option: {key}"))?;
            if field == 4 {
                if inline.is_some() {
                    return Err(format!("{key} takes no value"));
                }
                container = true;
            } else {
                let value = if let Some(value) = inline {
                    value
                } else {
                    index += 1;
                    args.get(index)
                        .map(String::as_str)
                        .ok_or_else(|| format!("{key} requires a value"))?
                };
                values[field] = if field == 1 {
                    crate::python_cli_integer::parse(value)
                        .map(|value| value.to_string())
                        .ok_or_else(|| format!("invalid port: {value}"))?
                } else {
                    value.into()
                };
            }
        } else if report.replace(argument.clone()).is_some() {
            return Err("only one report_path is accepted".into());
        }
        index += 1;
    }
    let report = report.ok_or("report_path is required")?;
    if values[5] != "text" && values[5] != "json" {
        return Err("--format must be text or json".into());
    }
    let report = expand_user_path(Path::new(&report)).map_err(|error| error.to_string())?;
    let report = resolve_non_strict(&report)?;
    let directory = report
        .parent()
        .unwrap_or(&report)
        .to_string_lossy()
        .into_owned();
    let ssh_host = if !values[0].is_empty() {
        values[0].clone()
    } else if let Some(value) = std::env::var("AGENT_CANON_SSH_HOST")
        .ok()
        .filter(|value| !value.is_empty())
    {
        value
    } else {
        let connection = std::env::var("SSH_CONNECTION").unwrap_or_default();
        if let Some(host) = connection.split_whitespace().nth(2) {
            let user = std::env::var("USER").unwrap_or_default();
            if user.is_empty() {
                host.into()
            } else {
                format!("{user}@{host}")
            }
        } else {
            "<ssh-host>".into()
        }
    };
    let bind = if !values[2].is_empty() {
        values[2].clone()
    } else if container {
        "0.0.0.0".into()
    } else {
        "127.0.0.1".into()
    };
    let target = if !values[3].is_empty() {
        values[3].clone()
    } else if container {
        runtime_ip()?
    } else {
        "127.0.0.1".into()
    };
    let port = &values[1];
    let url = format!(
        "http://127.0.0.1:{port}/{}",
        report.file_name().unwrap_or_default().to_string_lossy()
    );
    let server = shell_join(&[
        "python3".into(),
        "-m".into(),
        "http.server".into(),
        port.clone(),
        "--bind".into(),
        bind,
        "--directory".into(),
        directory.clone(),
    ]);
    let tunnel = shell_join(&[
        "ssh".into(),
        "-N".into(),
        "-L".into(),
        format!("{port}:{target}:{port}"),
        ssh_host.clone(),
    ]);
    Ok((
        json!({"mode":"python-http-server", "report_path":report, "server_directory":directory, "ssh_host":ssh_host, "tunnel_target":target, "local_url":url, "server_command":server, "tunnel_command":tunnel, "local_open_macos":shell_join(&["open".into(), url.clone()]), "local_open_linux":shell_join(&["xdg-open".into(), url.clone()]), "local_open_windows":format!("start {url}"), "note":"Run the server command where the HTML file exists, then run the tunnel on the local PC."}),
        values[5] == "json",
    ))
}

pub fn run(args: &[String]) -> i32 {
    if args
        .iter()
        .any(|argument| argument == "--help" || argument == "-h")
    {
        println!("usage: agent-canon html-artifact-access REPORT_PATH [--ssh-host HOST] [--port PORT] [--bind ADDRESS] [--tunnel-target HOST] [--use-container-ip] [--format text|json]");
        return 0;
    }
    let (value, json) = match plan(args) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("html-artifact-access: {error}");
            return 2;
        }
    };
    if json {
        let parsed = crate::python_json::parse_json(&value.to_string())
            .expect("plan contains JSON strings only");
        let bytes = crate::python_json::python_json_pretty_ascii_bytes(&parsed)
            .expect("plan JSON serializes");
        println!("{}", String::from_utf8(bytes).expect("ASCII JSON"));
    } else {
        for (key, field) in [
            ("MODE", "mode"),
            ("REPORT_PATH", "report_path"),
            ("SERVER_DIRECTORY", "server_directory"),
            ("SSH_HOST", "ssh_host"),
            ("TUNNEL_TARGET", "tunnel_target"),
            ("SERVER_COMMAND", "server_command"),
            ("TUNNEL_COMMAND", "tunnel_command"),
            ("LOCAL_URL", "local_url"),
            ("OPEN_MACOS", "local_open_macos"),
            ("OPEN_LINUX", "local_open_linux"),
            ("OPEN_WINDOWS", "local_open_windows"),
            ("NOTE", "note"),
        ] {
            println!(
                "HTML_ARTIFACT_{key}={}",
                value[field].as_str().unwrap_or("")
            );
        }
    }
    0
}
