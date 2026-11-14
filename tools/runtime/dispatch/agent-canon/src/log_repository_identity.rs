//! Stable, Git-process-free source identity for the hook event hot path.

// @dependency-start
// contract implementation
// responsibility Resolves source-repository identity for local hook events without starting Git.
// downstream implementation hook_event_log.rs derives the hook spool path
// downstream implementation eval_archive_paths.rs derives repository-scoped hook archive paths
// downstream implementation ../tests/hook_event_log_native.rs checks frozen Python identity outputs
// @dependency-end

use crate::python_text::python_strip;
use icu_casemap::CaseMapper;
use sha2::{Digest, Sha256};
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

pub const SOURCE_REMOTE_ENV: &str = "AGENT_CANON_SOURCE_REPOSITORY_REMOTE";
pub const SOURCE_REMOTE_NAME_ENV: &str = "AGENT_CANON_SOURCE_REPOSITORY_REMOTE_NAME";
pub const STABLE_ID_ENV: &str = "AGENT_CANON_SOURCE_REPOSITORY_ID";
pub const STABLE_ID_LENGTH: usize = 96;
pub const UNIDENTIFIED_SOURCE: &str = "unidentified-source";

#[derive(Debug)]
pub enum SourceRepositoryIdentityError {
    Identity(&'static str),
    Io(std::io::Error),
}

impl SourceRepositoryIdentityError {
    pub fn code(&self) -> Option<&'static str> {
        match self {
            Self::Identity(code) => Some(code),
            Self::Io(_) => None,
        }
    }
}

impl fmt::Display for SourceRepositoryIdentityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Identity(code) => formatter.write_str(code),
            Self::Io(error) => write!(formatter, "source remote configuration: {error}"),
        }
    }
}

impl std::error::Error for SourceRepositoryIdentityError {}

fn casefold(value: &str) -> String {
    CaseMapper::new().fold_string(value)
}

pub fn normalize_remote(remote: &str) -> Result<String, SourceRepositoryIdentityError> {
    let value = python_strip(remote);
    if value.is_empty()
        || value.starts_with('/')
        || value.starts_with('.')
        || value.starts_with("file:")
    {
        return Err(SourceRepositoryIdentityError::Identity(
            "source_remote_must_be_network_identity",
        ));
    }

    let (host, path) = if let Some((user_host, path)) = scp_remote(value) {
        let (_, host) = user_host.rsplit_once('@').expect("scp form has a user");
        (host, path)
    } else {
        let (_, authority_path) =
            value
                .split_once("://")
                .ok_or(SourceRepositoryIdentityError::Identity(
                    "source_remote_invalid",
                ))?;
        let path_start = authority_path
            .find(['/', '?', '#'])
            .unwrap_or(authority_path.len());
        let authority = &authority_path[..path_start];
        if authority.is_empty() {
            return Err(SourceRepositoryIdentityError::Identity(
                "source_remote_invalid",
            ));
        }
        let raw_path = &authority_path[path_start..];
        let path_end = raw_path.find(['?', '#']).unwrap_or(raw_path.len());
        let path = &raw_path[..path_end];
        let host_port = authority.rsplit('@').next().unwrap_or(authority);
        let host = if let Some(after_open) = host_port.strip_prefix('[') {
            let close = after_open
                .find(']')
                .ok_or(SourceRepositoryIdentityError::Identity(
                    "source_remote_invalid",
                ))?;
            &after_open[..close]
        } else {
            host_port.split(':').next().unwrap_or(host_port)
        };
        if host.is_empty() {
            return Err(SourceRepositoryIdentityError::Identity(
                "source_remote_invalid",
            ));
        }
        (host, path)
    };

    let mut normalized_path = path
        .split('/')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("/");
    if casefold(&normalized_path).ends_with(".git") {
        normalized_path.truncate(normalized_path.len() - 4);
    }
    normalized_path = normalized_path.trim_matches('/').to_owned();
    if normalized_path.is_empty() {
        return Err(SourceRepositoryIdentityError::Identity(
            "source_remote_missing_repository",
        ));
    }
    Ok(format!(
        "{}/{}",
        casefold(host).trim_end_matches('.'),
        casefold(&normalized_path)
    ))
}

fn scp_remote(value: &str) -> Option<(&str, &str)> {
    let (user_host, path) = value.split_once(':')?;
    if path.is_empty() || user_host.contains('/') {
        return None;
    }
    let (user, host) = user_host.rsplit_once('@')?;
    if user.is_empty() || host.is_empty() || user.contains('@') || user.contains(':') {
        return None;
    }
    Some((user_host, path))
}

pub fn stable_source_repository_id(remote: &str) -> Result<String, SourceRepositoryIdentityError> {
    let identity = normalize_remote(remote)?;
    let mut readable = String::new();
    let mut replacing = false;
    for character in identity.chars() {
        if character.is_ascii_lowercase()
            || character.is_ascii_digit()
            || matches!(character, '.' | '-')
        {
            readable.push(character);
            replacing = false;
        } else if !replacing {
            readable.push('-');
            replacing = true;
        }
    }
    let readable = readable.trim_matches(|character| matches!(character, '-' | '.'));
    let digest = Sha256::digest(identity.as_bytes());
    let digest = digest[..12]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let prefix_length = STABLE_ID_LENGTH.saturating_sub(digest.len() + 1).max(1);
    let prefix = readable
        .chars()
        .take(prefix_length)
        .collect::<String>()
        .trim_end_matches(['-', '.'])
        .to_owned();
    Ok(format!("{prefix}-{digest}"))
}

fn runtime_environment_value<'a>(
    environment: &'a std::collections::BTreeMap<String, String>,
    name: &str,
) -> Option<&'a str> {
    environment.get(name).map(|value| value.as_str())
}

/// Return the configured raw source remote, falling back to the selected Git
/// remote in the supplied source root.
pub fn source_remote_from_runtime_env(
    root: Option<&Path>,
    environment: &std::collections::BTreeMap<String, String>,
) -> Result<String, SourceRepositoryIdentityError> {
    let remote = runtime_environment_value(environment, SOURCE_REMOTE_ENV)
        .map(python_strip)
        .unwrap_or_default();
    if !remote.is_empty() {
        return Ok(remote.to_owned());
    }
    let Some(root) = root else {
        return Ok(String::new());
    };
    let remote_name = runtime_environment_value(environment, SOURCE_REMOTE_NAME_ENV)
        .map(python_strip)
        .unwrap_or("origin");
    remote_from_git_config(
        root,
        if remote_name.is_empty() {
            "origin"
        } else {
            remote_name
        },
    )
}

/// Resolve the raw source remote from process environment and local Git config.
pub fn source_remote(root: &Path) -> Result<String, SourceRepositoryIdentityError> {
    let environment = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
    source_remote_from_runtime_env(Some(root), &environment)
}

pub fn stable_source_id_from_runtime_env(
    root: Option<&Path>,
    environment: &std::collections::BTreeMap<String, String>,
) -> Result<String, SourceRepositoryIdentityError> {
    let remote = source_remote_from_runtime_env(root, environment)?;
    if remote.is_empty() {
        return Ok(UNIDENTIFIED_SOURCE.to_owned());
    }

    let derived = stable_source_repository_id(&remote)?;
    let override_id = runtime_environment_value(environment, STABLE_ID_ENV)
        .map(python_strip)
        .unwrap_or_default();
    if override_id.is_empty() {
        return Ok(derived);
    }
    if !valid_stable_id(override_id) {
        return Err(SourceRepositoryIdentityError::Identity(
            "source_repository_id_invalid",
        ));
    }
    if override_id != derived {
        return Err(SourceRepositoryIdentityError::Identity(
            "source_repository_id_mismatch",
        ));
    }
    Ok(override_id.to_owned())
}

pub fn repo_log_key(
    root: &Path,
    environment: &std::collections::BTreeMap<String, String>,
) -> Result<String, std::io::Error> {
    match stable_source_id_from_runtime_env(Some(root), environment) {
        Ok(identity) => Ok(identity),
        Err(SourceRepositoryIdentityError::Identity(_)) => Ok(UNIDENTIFIED_SOURCE.to_owned()),
        Err(SourceRepositoryIdentityError::Io(error)) => Err(error),
    }
}

fn valid_stable_id(value: &str) -> bool {
    let bytes = value.as_bytes();
    !bytes.is_empty()
        && bytes.len() <= STABLE_ID_LENGTH
        && bytes
            .first()
            .is_some_and(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
        && bytes.iter().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'.' || *byte == b'-'
        })
}

fn remote_from_git_config(
    root: &Path,
    remote_name: &str,
) -> Result<String, SourceRepositoryIdentityError> {
    let root = crate::path_resolution::resolve_non_strict(root).map_err(|_| {
        SourceRepositoryIdentityError::Io(std::io::Error::other(
            "cannot resolve source repository root",
        ))
    })?;
    let git_entry = root.join(".git");
    let git_dir = if git_entry.is_file() {
        let marker_raw =
            fs::read_to_string(&git_entry).map_err(SourceRepositoryIdentityError::Io)?;
        let marker = python_strip(&marker_raw).to_owned();
        if !casefold(&marker).starts_with("gitdir:") {
            return Ok(String::new());
        }
        let target = python_strip(&marker["gitdir:".len()..]);
        let target = PathBuf::from(target);
        let target = if target.is_absolute() {
            target
        } else {
            git_entry.parent().unwrap_or(&root).join(target)
        };
        crate::path_resolution::resolve_non_strict(&target).map_err(|_| {
            SourceRepositoryIdentityError::Io(std::io::Error::other(
                "cannot resolve Git directory path",
            ))
        })?
    } else {
        git_entry
    };
    let config = git_dir.join("config");
    if !config.is_file() {
        return Ok(String::new());
    }
    let contents = fs::read_to_string(config).map_err(SourceRepositoryIdentityError::Io)?;
    let section = format!("[remote \"{remote_name}\"]");
    let mut in_remote = false;
    for raw_line in contents.lines() {
        let line = python_strip(raw_line);
        if line.starts_with('[') {
            in_remote = casefold(line) == casefold(&section);
            continue;
        }
        if in_remote {
            if let Some((key, value)) = line.split_once('=') {
                if casefold(python_strip(key)) == "url" {
                    return Ok(python_strip(value).to_owned());
                }
            }
        }
    }
    Ok(String::new())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    use std::fs;

    #[test]
    fn remote_normalization_collapses_transport_credentials_and_git_suffix() {
        let cases = [
            (
                "git@github.com:iwashita-nozomu/agent-canon.git",
                "github.com/iwashita-nozomu/agent-canon",
            ),
            (
                "ssh://git@github.com/iwashita-nozomu/agent-canon.git",
                "github.com/iwashita-nozomu/agent-canon",
            ),
            (
                "https://reader:credential@example.com:8443/owner/repo.git",
                "example.com/owner/repo",
            ),
            (
                "https://github.com/iwashita-nozomu/agent-canon.GIT",
                "github.com/iwashita-nozomu/agent-canon",
            ),
        ];
        for (remote, expected) in cases {
            assert_eq!(normalize_remote(remote).unwrap(), expected);
        }
    }

    #[test]
    fn remote_identity_rejects_local_and_empty_values() {
        for remote in ["", " /tmp/repo ", "file:///tmp/repo", "owner/repo"] {
            assert!(normalize_remote(remote).is_err(), "remote={remote:?}");
        }
    }

    #[test]
    fn runtime_remote_override_wins_and_stable_id_override_must_match() {
        let remote = "https://example.com/owner/repo.git";
        let derived = stable_source_repository_id(remote).unwrap();
        let mut environment = BTreeMap::from([(SOURCE_REMOTE_ENV.to_owned(), remote.to_owned())]);
        assert_eq!(
            stable_source_id_from_runtime_env(None, &environment).unwrap(),
            derived
        );
        environment.insert(STABLE_ID_ENV.to_owned(), derived.clone());
        assert_eq!(
            stable_source_id_from_runtime_env(None, &environment).unwrap(),
            derived
        );
        environment.insert(STABLE_ID_ENV.to_owned(), "different-id".to_owned());
        assert!(matches!(
            stable_source_id_from_runtime_env(None, &environment),
            Err(SourceRepositoryIdentityError::Identity(
                "source_repository_id_mismatch"
            ))
        ));
    }

    #[test]
    fn git_remote_lookup_uses_the_selected_remote_name_without_git_processes() {
        let temporary = tempfile::tempdir().unwrap();
        fs::create_dir_all(temporary.path().join(".git")).unwrap();
        fs::write(
            temporary.path().join(".git/config"),
            "[remote \"upstream\"]\nurl = ssh://git@example.com/Owner/Repo.git\n",
        )
        .unwrap();
        let environment =
            BTreeMap::from([(SOURCE_REMOTE_NAME_ENV.to_owned(), "upstream".to_owned())]);
        assert_eq!(
            source_remote_from_runtime_env(Some(temporary.path()), &environment).unwrap(),
            "ssh://git@example.com/Owner/Repo.git"
        );
        assert_eq!(
            stable_source_id_from_runtime_env(Some(temporary.path()), &environment).unwrap(),
            stable_source_repository_id("ssh://git@example.com/Owner/Repo.git").unwrap()
        );
    }
}
