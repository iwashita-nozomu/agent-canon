//! Read-only checkout identity used at bounded repository workflow transitions.

// @dependency-start
// contract implementation
// responsibility Reads one checkout's cwd, Git root, branch state, HEAD, and normalized remote owner/repository.
// upstream implementation git_read.rs bounds Git read operations
// downstream test ../../../../../tests/agent_tools/test_checkout_identity.py checks the observable CLI contract
// @dependency-end

use crate::git_read;
use serde_json::{Map, Value};
use std::path::{Path, PathBuf};
use std::time::Duration;

const UNKNOWN: &str = "unknown";
const GIT_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CheckoutIdentity {
    pub cwd: String,
    pub git_root: String,
    pub branch: String,
    pub head: String,
    pub remote: String,
}

impl CheckoutIdentity {
    pub fn as_json(&self) -> Value {
        let mut value = Map::new();
        value.insert("branch".to_owned(), Value::String(self.branch.clone()));
        value.insert("cwd".to_owned(), Value::String(self.cwd.clone()));
        value.insert("git_root".to_owned(), Value::String(self.git_root.clone()));
        value.insert("head".to_owned(), Value::String(self.head.clone()));
        value.insert("remote".to_owned(), Value::String(self.remote.clone()));
        Value::Object(value)
    }

    pub fn render(&self) -> String {
        format!(
            "cwd={}\ngit_root={}\nbranch={}\nhead={}\nremote={}",
            self.cwd, self.git_root, self.branch, self.head, self.remote
        )
    }
}

fn git(root: &Path, args: &[&str]) -> Option<String> {
    git_read::output(root, args, GIT_TIMEOUT)
        .ok()
        .flatten()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn normalize_remote(remote: Option<&str>) -> String {
    let Some(value) = remote.map(str::trim).filter(|value| !value.is_empty()) else {
        return UNKNOWN.to_owned();
    };
    let path = if let Some((user_host, path)) = value.split_once(':').filter(|(head, path)| {
        !path.is_empty()
            && !head.contains('/')
            && head
                .rsplit_once('@')
                .is_some_and(|(user, host)| !user.is_empty() && !host.is_empty())
    }) {
        let _ = user_host;
        path
    } else if let Some((_, remainder)) = value.split_once("://") {
        let authority_end = remainder.find(['/', '?', '#']).unwrap_or(remainder.len());
        let authority = &remainder[..authority_end];
        let host_port = authority.rsplit('@').next().unwrap_or(authority);
        let hostname = if let Some(after_open) = host_port.strip_prefix('[') {
            after_open
                .split_once(']')
                .map(|(host, _)| host)
                .unwrap_or("")
        } else {
            host_port.split(':').next().unwrap_or("")
        };
        if hostname.is_empty() {
            return UNKNOWN.to_owned();
        }
        let path_start = &remainder[authority_end..];
        let path_end = path_start.find(['?', '#']).unwrap_or(path_start.len());
        &path_start[..path_end]
    } else {
        return UNKNOWN.to_owned();
    };
    let mut parts = path
        .split('/')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    if parts
        .last()
        .is_some_and(|part| part.to_lowercase().ends_with(".git"))
    {
        if let Some(last) = parts.last_mut() {
            let length = last.len().saturating_sub(4);
            *last = &last[..length];
        }
    }
    if parts.len() < 2 {
        return UNKNOWN.to_owned();
    }
    let owner = parts[parts.len() - 2];
    let repository = parts[parts.len() - 1];
    if owner.is_empty() || repository.is_empty() {
        return UNKNOWN.to_owned();
    }
    format!("{}/{}", owner.to_lowercase(), repository.to_lowercase())
}

pub fn resolve(cwd: &Path) -> Result<CheckoutIdentity, String> {
    let expanded =
        crate::path_expansion::expand_user_path(cwd).map_err(|error| error.to_string())?;
    let absolute_cwd = if expanded.is_absolute() {
        expanded
    } else {
        std::env::current_dir()
            .map_err(|error| format!("current directory: {error}"))?
            .join(expanded)
    };
    let absolute_cwd = crate::path_resolution::resolve_non_strict(&absolute_cwd)?;
    let Some(git_root_value) = git(&absolute_cwd, &["rev-parse", "--show-toplevel"]) else {
        return Ok(CheckoutIdentity {
            cwd: absolute_cwd.to_string_lossy().into_owned(),
            git_root: UNKNOWN.to_owned(),
            branch: UNKNOWN.to_owned(),
            head: UNKNOWN.to_owned(),
            remote: UNKNOWN.to_owned(),
        });
    };
    let git_root_value = PathBuf::from(git_root_value);
    let git_root = crate::path_resolution::resolve_non_strict(&git_root_value)?;
    let branch = git(&git_root, &["symbolic-ref", "--quiet", "--short", "HEAD"])
        .unwrap_or_else(|| "detached".to_owned());
    let head =
        git(&git_root, &["rev-parse", "--verify", "HEAD"]).unwrap_or_else(|| UNKNOWN.to_owned());
    let remote = normalize_remote(git(&git_root, &["remote", "get-url", "origin"]).as_deref());
    Ok(CheckoutIdentity {
        cwd: absolute_cwd.to_string_lossy().into_owned(),
        git_root: git_root.to_string_lossy().into_owned(),
        branch,
        head,
        remote,
    })
}

pub fn run(args: &[String]) -> i32 {
    let mut cwd = PathBuf::from(".");
    let mut format = "lines".to_owned();
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "--help" || argument == "-h" {
            println!("usage: agent-canon checkout-identity [--cwd PATH] [--format json|lines]");
            return 0;
        }
        let (option, inline) = argument
            .split_once('=')
            .map_or((argument, None), |(name, value)| (name, Some(value)));
        let resolved = crate::python_cli_options::resolve_long_option_prefix(
            option,
            &[("--cwd", 0), ("--format", 1)],
        );
        let selected = match resolved {
            Ok(selected) => selected,
            Err(crate::python_cli_options::LongOptionError::Unrecognized) => {
                eprintln!("CHECKOUT_IDENTITY_ERROR=unrecognized argument: {argument}");
                return 2;
            }
            Err(crate::python_cli_options::LongOptionError::Ambiguous(_)) => {
                eprintln!("CHECKOUT_IDENTITY_ERROR=ambiguous option: {option}");
                return 2;
            }
        };
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            match args.get(index).filter(|value| !value.starts_with('-')) {
                Some(value) => value.clone(),
                None => {
                    eprintln!("CHECKOUT_IDENTITY_ERROR=argument {option}: expected one argument");
                    return 2;
                }
            }
        };
        match selected {
            0 => cwd = PathBuf::from(value),
            _ => format = value,
        }
        index += 1;
    }
    let identity = match resolve(&cwd) {
        Ok(identity) => identity,
        Err(error) => {
            eprintln!("CHECKOUT_IDENTITY_ERROR={error}");
            return 1;
        }
    };
    match format.as_str() {
        "json" => {
            let quote = |value: &str| serde_json::to_string(value);
            let fields = [
                ("branch", identity.branch.as_str()),
                ("cwd", identity.cwd.as_str()),
                ("git_root", identity.git_root.as_str()),
                ("head", identity.head.as_str()),
                ("remote", identity.remote.as_str()),
            ];
            let mut rendered = Vec::with_capacity(fields.len());
            for (key, value) in fields {
                let key = match quote(key) {
                    Ok(value) => value,
                    Err(error) => {
                        eprintln!("CHECKOUT_IDENTITY_ERROR={error}");
                        return 1;
                    }
                };
                let value = match quote(value) {
                    Ok(value) => value,
                    Err(error) => {
                        eprintln!("CHECKOUT_IDENTITY_ERROR={error}");
                        return 1;
                    }
                };
                rendered.push(format!("{key}: {value}"));
            }
            println!("{{{}}}", rendered.join(", "));
        }
        "lines" => println!("{}", identity.render()),
        _ => {
            eprintln!("CHECKOUT_IDENTITY_ERROR=invalid format: {format}");
            return 2;
        }
    }
    0
}
