// @dependency-start
// contract implementation
// responsibility Expands user-home paths from captured platform environment and injected account lookup.
// upstream implementation agent_search.rs shares query-file path expansion
// upstream implementation scip_index.rs expands manifest and receipt overrides
// @dependency-end

#[cfg(unix)]
use nix::unistd::{Uid, User};
use std::env;
use std::ffi::{OsStr, OsString};
use std::fmt;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PathExpansionError {
    UnresolvedHome,
    HomeLookup(String),
}

impl fmt::Display for PathExpansionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnresolvedHome => formatter.write_str("Could not determine home directory."),
            Self::HomeLookup(message) => {
                write!(formatter, "home-directory-lookup-failed:{message}")
            }
        }
    }
}

impl std::error::Error for PathExpansionError {}

#[derive(Debug, Clone, Default)]
pub struct PathExpansionEnvironment {
    pub home: Option<OsString>,
    pub user_profile: Option<OsString>,
    pub home_drive: Option<OsString>,
    pub home_path: Option<OsString>,
    pub user_name: Option<OsString>,
}

impl PathExpansionEnvironment {
    pub fn from_process() -> Self {
        Self {
            home: env::var_os("HOME"),
            user_profile: env::var_os("USERPROFILE"),
            home_drive: env::var_os("HOMEDRIVE"),
            home_path: env::var_os("HOMEPATH"),
            user_name: env::var_os("USERNAME"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PathPlatform {
    Posix,
    Windows,
}

impl PathPlatform {
    pub fn native() -> Self {
        if cfg!(windows) {
            Self::Windows
        } else {
            Self::Posix
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HomeLookupRequest {
    CurrentUser,
    NamedUser(String),
}

fn unresolved_home() -> PathExpansionError {
    PathExpansionError::UnresolvedHome
}

fn lookup_home_directory<F>(
    request: HomeLookupRequest,
    lookup: &mut F,
) -> Result<PathBuf, PathExpansionError>
where
    F: FnMut(HomeLookupRequest) -> Result<Option<PathBuf>, String>,
{
    match lookup(request) {
        Ok(Some(home)) => Ok(home),
        Ok(None) => Err(unresolved_home()),
        Err(error) => Err(PathExpansionError::HomeLookup(error)),
    }
}

/// Expand a leading tilde using explicit platform inputs and an account lookup.
pub fn expand_user_path_with<F>(
    path: &Path,
    platform: PathPlatform,
    environment: &PathExpansionEnvironment,
    mut home_lookup: F,
) -> Result<PathBuf, PathExpansionError>
where
    F: FnMut(HomeLookupRequest) -> Result<Option<PathBuf>, String>,
{
    let Some(value) = path.to_str() else {
        return Ok(path.to_path_buf());
    };
    let Some((username, suffix)) = tilde_path_parts(value, platform) else {
        return Ok(path.to_path_buf());
    };

    match platform {
        PathPlatform::Posix => {
            let home = if username.is_empty() {
                match &environment.home {
                    Some(home) if home.is_empty() => PathBuf::from("/"),
                    Some(home) => PathBuf::from(home),
                    None => {
                        lookup_home_directory(HomeLookupRequest::CurrentUser, &mut home_lookup)?
                    }
                }
            } else {
                lookup_home_directory(
                    HomeLookupRequest::NamedUser(username.to_string()),
                    &mut home_lookup,
                )?
            };
            let suffix = suffix.trim_start_matches('/');
            if suffix.is_empty() {
                Ok(home)
            } else {
                Ok(home.join(suffix))
            }
        }
        PathPlatform::Windows => {
            let mut home = windows_current_home(environment)?;
            if !username.is_empty() {
                let current_user = environment.user_name.as_deref().and_then(OsStr::to_str);
                if current_user != Some(username) {
                    let (parent, basename) = windows_path_split(&home);
                    if current_user != Some(basename.as_str()) {
                        return Err(unresolved_home());
                    }
                    home = windows_path_join(&parent, username);
                }
            }
            let expanded = if suffix.is_empty() {
                home
            } else {
                windows_path_join(&home, suffix)
            };
            Ok(PathBuf::from(expanded.replace('/', "\\")))
        }
    }
}

/// Expand a user-home path using the process environment and native account lookup.
pub fn expand_user_path(path: &Path) -> Result<PathBuf, PathExpansionError> {
    expand_user_path_with(
        path,
        PathPlatform::native(),
        &PathExpansionEnvironment::from_process(),
        native_home_lookup,
    )
}

fn tilde_path_parts(value: &str, platform: PathPlatform) -> Option<(&str, &str)> {
    if !value.starts_with('~') {
        return None;
    }
    match platform {
        PathPlatform::Posix if value.starts_with('/') => return None,
        PathPlatform::Windows if windows_path_is_anchored(value) => return None,
        _ => {}
    }
    let suffix = &value[1..];
    let separator = |character| match platform {
        PathPlatform::Posix => character == '/',
        PathPlatform::Windows => matches!(character, '/' | '\\'),
    };
    let Some((index, character)) = suffix
        .char_indices()
        .find(|(_, character)| separator(*character))
    else {
        return Some((suffix, ""));
    };
    let username = &suffix[..index];
    let suffix_start = index + character.len_utf8();
    let suffix = &suffix[suffix_start..];
    let suffix = match platform {
        PathPlatform::Posix => suffix.trim_start_matches('/'),
        PathPlatform::Windows => suffix.trim_start_matches(['/', '\\']),
    };
    Some((username, suffix))
}

fn windows_path_is_anchored(value: &str) -> bool {
    if value.starts_with('\\') || value.starts_with('/') {
        return true;
    }
    let mut characters = value.chars();
    characters.next();
    characters.next() == Some(':')
}

fn windows_current_home(
    environment: &PathExpansionEnvironment,
) -> Result<String, PathExpansionError> {
    if let Some(user_profile) = &environment.user_profile {
        return user_profile
            .to_str()
            .map(str::to_owned)
            .ok_or_else(unresolved_home);
    }
    let Some(home_path) = &environment.home_path else {
        return Err(unresolved_home());
    };
    let home_path = home_path.to_str().ok_or_else(unresolved_home)?;
    let home_drive = match environment.home_drive.as_deref() {
        Some(home_drive) => home_drive.to_str().ok_or_else(unresolved_home)?,
        None => "",
    };
    Ok(windows_path_join(home_drive, home_path))
}

fn windows_path_join(first: &str, second: &str) -> String {
    let (mut drive, mut root, mut path) = windows_splitroot(first);
    let (second_drive, second_root, second_path) = windows_splitroot(second);
    if !second_root.is_empty() {
        if !second_drive.is_empty() || drive.is_empty() {
            drive = second_drive;
        }
        root = second_root;
        path = second_path;
    } else if !second_drive.is_empty() && !second_drive.eq_ignore_ascii_case(&drive) {
        drive = second_drive;
        root = second_root;
        path = second_path;
    } else {
        if !second_drive.is_empty() {
            drive = second_drive;
        }
        if !path.is_empty() && !path.ends_with('\\') && !path.ends_with('/') {
            path.push('\\');
        }
        path.push_str(&second_path);
    }
    if !path.is_empty()
        && root.is_empty()
        && !drive.is_empty()
        && !drive.ends_with(':')
        && !drive.ends_with('\\')
        && !drive.ends_with('/')
    {
        drive.push('\\');
    }
    format_windows_path(&drive, &root, &path)
}

fn windows_splitroot(path: &str) -> (String, String, String) {
    let normalized = path.replace('/', "\\");
    if normalized.starts_with("\\\\") {
        let unc_prefix = "\\\\?\\UNC\\";
        let start = if normalized
            .get(..unc_prefix.len())
            .is_some_and(|prefix| prefix.eq_ignore_ascii_case(unc_prefix))
        {
            unc_prefix.len()
        } else {
            2
        };
        let Some(first_separator) = normalized[start..].find('\\').map(|index| start + index)
        else {
            return (path.to_string(), String::new(), String::new());
        };
        let Some(second_separator) = normalized[first_separator + 1..]
            .find('\\')
            .map(|index| first_separator + 1 + index)
        else {
            return (path.to_string(), String::new(), String::new());
        };
        return (
            path[..second_separator].to_string(),
            path[second_separator..second_separator + 1].to_string(),
            path[second_separator + 1..].to_string(),
        );
    }
    if path.starts_with('\\') || path.starts_with('/') {
        return (String::new(), path[..1].to_string(), path[1..].to_string());
    }
    let mut characters = path.char_indices();
    let Some((_, _)) = characters.next() else {
        return (String::new(), String::new(), String::new());
    };
    let Some((colon_index, ':')) = characters.next() else {
        return (String::new(), String::new(), path.to_string());
    };
    let drive_end = colon_index + 1;
    let after_drive = &path[drive_end..];
    if after_drive.starts_with('\\') || after_drive.starts_with('/') {
        let root_end = drive_end + 1;
        (
            path[..drive_end].to_string(),
            path[drive_end..root_end].to_string(),
            path[root_end..].to_string(),
        )
    } else {
        (
            path[..drive_end].to_string(),
            String::new(),
            after_drive.to_string(),
        )
    }
}

fn windows_path_split(path: &str) -> (String, String) {
    let (drive, root, tail) = windows_splitroot(path);
    let split_at = tail
        .char_indices()
        .filter(|(_, character)| matches!(character, '\\' | '/'))
        .map(|(index, character)| index + character.len_utf8())
        .next_back()
        .unwrap_or(0);
    let head = tail[..split_at].trim_end_matches(['\\', '/']);
    let directory = if head.is_empty() {
        format!("{drive}{root}")
    } else {
        format!("{drive}{root}{head}")
    };
    (directory, tail[split_at..].to_string())
}

fn format_windows_path(drive: &str, root: &str, path: &str) -> String {
    format!("{drive}{root}{path}")
}

pub fn native_home_lookup(request: HomeLookupRequest) -> Result<Option<PathBuf>, String> {
    #[cfg(unix)]
    {
        let user = match request {
            HomeLookupRequest::CurrentUser => User::from_uid(Uid::current()),
            HomeLookupRequest::NamedUser(username) => User::from_name(&username),
        };
        user.map(|user| user.map(|user| user.dir))
            .map_err(|error| error.to_string())
    }
    #[cfg(not(unix))]
    {
        let _ = request;
        Ok(None)
    }
}
