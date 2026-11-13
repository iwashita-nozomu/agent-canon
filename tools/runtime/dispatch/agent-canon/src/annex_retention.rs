//! Deterministic, append-only retention of one raw experiment tree.

use crate::experiment_identity::{identity_from_json, json_field, json_text, ExperimentIdentity};
use crate::python_json::{parse_json_bytes_unique_keys, to_serde_json_value};
use crate::source_mutation::{open_root_nofollow, SourceMutationCapability};
use cap_fs_ext::{DirExt, OpenOptionsFollowExt};
use cap_primitives::fs::FollowSymlinks;
use cap_std::fs::{Dir, OpenOptions};
use flate2::{read::GzDecoder, Compression, GzBuilder};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Command;

const MANIFEST: &str = "annex_retention_manifest.json";
const USAGE: &str = "usage: agent-canon save-experiment-result-annex --raw-dir PATH [--annex-repo PATH] [--source-repo-root PATH]";

#[derive(Clone)]
struct Evidence {
    relative: PathBuf,
    size: u64,
    hash: String,
    executable: bool,
}
impl Evidence {
    fn value(&self) -> Value {
        json!({"path":posix(&self.relative),"size":self.size,"sha256":self.hash,"mode":if self.executable {"executable"} else {"regular"}})
    }
}

struct Entry {
    relative: PathBuf,
    directory: bool,
    size: u64,
    hash: String,
    executable: bool,
}
pub struct RawArchive {
    source_root: PathBuf,
    source: Dir,
    identity: ExperimentIdentity,
    raw_relative: PathBuf,
    entries: BTreeMap<String, Entry>,
    summary: Evidence,
    run_manifest: Evidence,
    branch: String,
    commit: String,
    dirty: Vec<String>,
}

pub struct GitOutput {
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
}
pub trait GitRunner {
    fn execute(&mut self, root: &Path, arguments: &[&str]) -> Result<GitOutput, String>;
}
pub struct SystemGit;
impl GitRunner for SystemGit {
    fn execute(&mut self, root: &Path, arguments: &[&str]) -> Result<GitOutput, String> {
        let result = Command::new("git")
            .args(arguments)
            .current_dir(root)
            .output()
            .map_err(|error| error.to_string())?;
        Ok(GitOutput {
            code: result.status.code().unwrap_or(1),
            stdout: String::from_utf8_lossy(&result.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&result.stderr).into_owned(),
        })
    }
}

fn git(
    runner: &mut impl GitRunner,
    root: &Path,
    arguments: &[&str],
    checked: bool,
) -> Result<String, String> {
    let result = runner.execute(root, arguments)?;
    if checked && result.code != 0 {
        let detail = if result.stderr.trim().is_empty() {
            result.stdout.trim()
        } else {
            result.stderr.trim()
        };
        return Err(format!("git {} failed: {detail}", arguments.join(" ")));
    }
    Ok(crate::python_text::python_strip(&result.stdout).into())
}

fn posix(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}
fn io_error(error: impl std::fmt::Display) -> io::Error {
    io::Error::other(error.to_string())
}
fn lexical_absolute(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_owned()
    } else {
        std::env::current_dir()
            .map_err(|error| error.to_string())?
            .join(path)
    };
    let mut result = PathBuf::new();
    for part in absolute.components() {
        match part {
            Component::ParentDir => {
                result.pop();
            }
            Component::CurDir => {}
            other => result.push(other.as_os_str()),
        }
    }
    Ok(result)
}

fn open_regular(root: &Dir, relative: &Path) -> io::Result<cap_std::fs::File> {
    let parts: Vec<_> = relative.components().collect();
    let mut parent = root.try_clone()?;
    for part in &parts[..parts.len().saturating_sub(1)] {
        let Component::Normal(name) = part else {
            return Err(io_error("invalid source-relative path"));
        };
        parent = parent.open_dir_nofollow(name)?;
    }
    let Some(Component::Normal(name)) = parts.last() else {
        return Err(io_error("invalid source-relative path"));
    };
    let metadata = parent.symlink_metadata(name)?;
    if metadata.is_symlink() {
        return Err(io_error(format!(
            "source contains a symlink: {}",
            relative.display()
        )));
    }
    if !metadata.is_file() {
        return Err(io_error(format!(
            "source contains a special file: {}",
            relative.display()
        )));
    }
    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No);
    parent.open_with(name, &options)
}

fn executable(metadata: &cap_std::fs::Metadata) -> bool {
    #[cfg(unix)]
    {
        use cap_std::fs::PermissionsExt;
        metadata.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        let _ = metadata;
        false
    }
}

fn hash_reader(reader: &mut impl Read) -> io::Result<(u64, String)> {
    let mut hash = Sha256::new();
    let mut size = 0;
    let mut bytes = vec![0; 1024 * 1024];
    loop {
        let count = reader.read(&mut bytes)?;
        if count == 0 {
            break;
        }
        size += count as u64;
        hash.update(&bytes[..count]);
    }
    Ok((size, format!("{:x}", hash.finalize())))
}

fn lfs_pointer(prefix: &[u8]) -> bool {
    if !prefix.starts_with(b"version https://git-lfs.github.com/spec/v1\n") {
        return false;
    }
    let lines: Vec<_> = prefix.split(|byte| *byte == b'\n').collect();
    if lines.len() < 3 {
        return false;
    }
    let Some(oid) = lines[1].strip_prefix(b"oid sha256:") else {
        return false;
    };
    let Some(size) = lines[2].strip_prefix(b"size ") else {
        return false;
    };
    let (oid, size) = (oid.trim_ascii(), size.trim_ascii());
    !oid.is_empty()
        && !size.is_empty()
        && oid.iter().all(u8::is_ascii_alphanumeric)
        && size.iter().all(u8::is_ascii_digit)
}

fn source_evidence(
    root: &Path,
    source: &Dir,
    relative: &Path,
    label: &str,
) -> Result<Evidence, String> {
    let mut file = open_regular(source, relative).map_err(|error| format!("{label}: {error}"))?;
    let metadata = file.metadata().map_err(|error| error.to_string())?;
    let mut prefix = vec![0; 4096];
    let count = file.read(&mut prefix).map_err(|error| error.to_string())?;
    prefix.truncate(count);
    if lfs_pointer(&prefix) {
        return Err(format!(
            "{label} contains a Git-LFS pointer: {}",
            relative.display()
        ));
    }
    let relative_text = posix(relative);
    let mut runner = SystemGit;
    if runner
        .execute(root, &["ls-files", "--error-unmatch", "--", &relative_text])?
        .code
        != 0
    {
        return Err(format!("{label} must be tracked: {relative_text}"));
    }
    if runner
        .execute(root, &["diff", "--quiet", "HEAD", "--", &relative_text])?
        .code
        != 0
    {
        return Err(format!(
            "{label} must match source commit before retention: {relative_text}"
        ));
    }
    file.seek(SeekFrom::Start(0))
        .map_err(|error| error.to_string())?;
    let (size, hash) = hash_reader(&mut file).map_err(|error| error.to_string())?;
    Ok(Evidence {
        relative: relative.into(),
        size,
        hash,
        executable: executable(&metadata),
    })
}

impl RawArchive {
    pub fn prepare(source_root: &Path, raw_dir: &Path) -> Result<Self, String> {
        let source_root = fs::canonicalize(source_root).map_err(|error| error.to_string())?;
        let source = open_root_nofollow(&source_root).map_err(|error| error.to_string())?;
        let raw_dir = lexical_absolute(raw_dir)?;
        let raw_relative = raw_dir
            .strip_prefix(&source_root)
            .map_err(|_| "raw-dir must be inside source repo root")?
            .to_owned();
        let parts: Vec<_> = raw_relative.components().collect();
        if parts.len() != 5
            || parts[0].as_os_str() != "experiments"
            || parts[2].as_os_str() != "result"
            || parts[4].as_os_str() != "raw"
        {
            return Err("raw path must be experiments/<topic>/result/<run_name>/raw".into());
        }
        let mut raw_handle = source.try_clone().map_err(|error| error.to_string())?;
        for part in &parts {
            let Component::Normal(name) = part else {
                return Err("source-relative path is invalid".into());
            };
            let metadata = raw_handle
                .symlink_metadata(name)
                .map_err(|error| error.to_string())?;
            if metadata.is_symlink() {
                return Err(format!(
                    "source path contains a symlink: {}",
                    raw_dir.display()
                ));
            }
            raw_handle = raw_handle
                .open_dir_nofollow(name)
                .map_err(|error| error.to_string())?;
        }
        let result_relative = raw_relative.parent().expect("five-component raw path");
        let summary = source_evidence(
            &source_root,
            &source,
            &result_relative.join("summary/summary.json"),
            "summary evidence",
        )?;
        let run_manifest = source_evidence(
            &source_root,
            &source,
            &result_relative.join("run_manifest.json"),
            "run manifest evidence",
        )?;
        let read_json = |relative: &Path| -> Result<crate::python_json::JsonValue, String> {
            let mut file = open_regular(&source, relative).map_err(|error| error.to_string())?;
            let mut bytes = Vec::new();
            file.read_to_end(&mut bytes)
                .map_err(|error| error.to_string())?;
            parse_json_bytes_unique_keys(&bytes)
        };
        let summary_payload =
            read_json(&summary.relative).map_err(|_| "summary evidence must be strict JSON")?;
        let payload = read_json(&run_manifest.relative)
            .map_err(|_| "run manifest evidence must be strict JSON")?;
        if !matches!(summary_payload, crate::python_json::JsonValue::Object(_)) {
            return Err("summary evidence must be a JSON object".into());
        }
        if !matches!(payload, crate::python_json::JsonValue::Object(_)) {
            return Err("run manifest evidence must be a JSON object".into());
        }
        let manifest_identity =
            identity_from_json(&payload).map_err(|_| "run manifest identity is invalid")?;
        let identity =
            ExperimentIdentity::from_raw_relative_path(&raw_relative, &manifest_identity.variant)?;
        if manifest_identity != identity {
            return Err("run manifest identity does not match raw-dir identity".into());
        }
        if json_field(&summary_payload, "run_id")
            .and_then(json_text)
            .as_deref()
            != Some(&identity.run_name)
        {
            return Err("summary run_id does not match raw-dir identity".into());
        }
        let binding = json_field(&payload, "raw_artifacts")
            .ok_or("run manifest must contain the canonical raw_artifacts binding")?;
        let binding = to_serde_json_value(binding)
            .map_err(|_| "run manifest raw retention state is invalid")?;
        let object = binding
            .as_object()
            .ok_or("run manifest must contain the canonical raw_artifacts binding")?;
        if object.len() != 2 || !object.contains_key("path") || !object.contains_key("retention") {
            return Err("run manifest must contain the canonical raw_artifacts binding".into());
        }
        if binding["path"] != posix(&raw_relative) {
            return Err("run manifest raw path does not match raw-dir identity".into());
        }
        let retention = binding["retention"]
            .as_object()
            .ok_or("run manifest raw retention state is invalid")?;
        if retention.len() != 1 || !retention.contains_key("state") {
            return Err("run manifest raw retention state is invalid".into());
        }
        if retention["state"] != "unarchived" {
            return Err("run manifest raw retention state must be unarchived".into());
        }
        let mut runner = SystemGit;
        let branch = git(
            &mut runner,
            &source_root,
            &["symbolic-ref", "--quiet", "--short", "HEAD"],
            false,
        )?;
        let branch = if branch.is_empty() {
            "HEAD".into()
        } else {
            branch
        };
        let commit = git(&mut runner, &source_root, &["rev-parse", "HEAD"], true)?;
        let status = git(
            &mut runner,
            &source_root,
            &["status", "--porcelain=v1", "--untracked-files=all"],
            true,
        )?;
        let mut dirty: Vec<_> = status
            .lines()
            .filter(|line| line.chars().count() >= 4)
            .map(|line| {
                let path: String = line.chars().skip(3).collect();
                path.split_once(" -> ")
                    .map_or(path.clone(), |(_, target)| target.into())
            })
            .collect();
        dirty.sort();
        let mut archive = Self {
            source_root,
            source,
            identity,
            raw_relative,
            entries: BTreeMap::new(),
            summary,
            run_manifest,
            branch,
            commit,
            dirty,
        };
        archive.scan(&raw_handle, &archive.raw_relative.clone())?;
        if !archive.entries.values().any(|entry| !entry.directory) {
            return Err("raw directory is empty".into());
        }
        for parent in archive
            .raw_relative
            .ancestors()
            .skip(1)
            .filter(|path| !path.as_os_str().is_empty())
        {
            archive.entries.insert(
                posix(parent),
                Entry {
                    relative: parent.into(),
                    directory: true,
                    size: 0,
                    hash: String::new(),
                    executable: false,
                },
            );
        }
        Ok(archive)
    }

    fn scan(&mut self, directory: &Dir, relative: &Path) -> Result<(), String> {
        self.entries.insert(
            posix(relative),
            Entry {
                relative: relative.into(),
                directory: true,
                size: 0,
                hash: String::new(),
                executable: false,
            },
        );
        let mut names = directory
            .entries()
            .map_err(|error| error.to_string())?
            .map(|entry| entry.map(|entry| entry.file_name()))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        names.sort();
        for name in names {
            let text = name.to_str().ok_or("raw path must be valid UTF-8")?;
            let path = relative.join(&name);
            if text == MANIFEST {
                return Err(format!("raw tree reserves {MANIFEST}: {}", path.display()));
            }
            let metadata = directory
                .symlink_metadata(&name)
                .map_err(|error| error.to_string())?;
            if metadata.is_symlink() {
                return Err(format!("raw tree contains a symlink: {}", path.display()));
            }
            if metadata.is_dir() {
                self.scan(
                    &directory
                        .open_dir_nofollow(&name)
                        .map_err(|error| error.to_string())?,
                    &path,
                )?;
                continue;
            }
            if !metadata.is_file() {
                return Err(format!(
                    "raw tree contains a special file: {}",
                    path.display()
                ));
            }
            let mut file = open_regular(&self.source, &path).map_err(|error| error.to_string())?;
            let mut prefix = vec![0; 4096];
            let count = file.read(&mut prefix).map_err(|error| error.to_string())?;
            prefix.truncate(count);
            if lfs_pointer(&prefix) {
                return Err(format!(
                    "raw tree contains a Git-LFS pointer: {}",
                    path.display()
                ));
            }
            file.seek(SeekFrom::Start(0))
                .map_err(|error| error.to_string())?;
            let (size, hash) = hash_reader(&mut file).map_err(|error| error.to_string())?;
            self.entries.insert(
                posix(&path),
                Entry {
                    relative: path,
                    directory: false,
                    size,
                    hash,
                    executable: executable(&metadata),
                },
            );
        }
        Ok(())
    }

    fn archive_relative(&self) -> PathBuf {
        Path::new("experiments")
            .join(&self.identity.topic)
            .join("raw")
            .join(&self.identity.variant)
            .join(format!("{}.tar.gz", self.identity.run_name))
    }
    fn manifest_path(&self) -> String {
        posix(&self.raw_relative.join(MANIFEST))
    }
    fn manifest(&self) -> Vec<u8> {
        let files: Vec<_> = self.entries.values().filter(|entry| !entry.directory).map(|entry| json!({"path":posix(&entry.relative),"size":entry.size,"sha256":entry.hash,"mode":if entry.executable {"executable"} else {"regular"}})).collect();
        let directories: Vec<_> = self
            .entries
            .values()
            .filter(|entry| entry.directory && entry.relative.starts_with(&self.raw_relative))
            .map(|entry| posix(&entry.relative))
            .collect();
        let value = json!({"schema":"git-annex-raw-retention/v1","append_only":true,"identity":self.identity.to_value()["identity"],"archive":{"compression":"gzip","gzip_filename":"","gzip_level":9,"gzip_mtime":0,"path":posix(&self.archive_relative()),"tar_format":"pax"},"raw":{"directory":posix(&self.raw_relative),"directories":directories,"files":files},"source":{"branch":self.branch,"commit":self.commit,"dirty_paths":self.dirty},"tracked_result_evidence":{"directory":posix(&self.identity.result_relative_path()),"run_manifest":self.run_manifest.value(),"summary":self.summary.value()}});
        let mut bytes = serde_json::to_vec(&value).expect("retention manifest is JSON");
        bytes.push(b'\n');
        bytes
    }

    pub fn write(&self, writer: &mut impl Write) -> io::Result<()> {
        let compressed = GzBuilder::new()
            .mtime(0)
            .operating_system(255)
            .write(writer, Compression::best());
        let mut archive = tar::Builder::new(compressed);
        let manifest = self.manifest();
        let manifest_path = self.manifest_path();
        let mut names: BTreeSet<_> = self.entries.keys().cloned().collect();
        names.insert(manifest_path.clone());
        for name in names {
            let entry = self.entries.get(&name);
            let directory = entry.is_some_and(|entry| entry.directory);
            let size = if name == manifest_path {
                manifest.len() as u64
            } else {
                entry.map_or(0, |entry| entry.size)
            };
            let mode = if directory || entry.is_some_and(|entry| entry.executable) {
                0o755
            } else {
                0o644
            };
            let large = size >= 8_u64.pow(11);
            let mut header = tar::Header::new_ustar();
            header.set_uid(0);
            header.set_gid(0);
            header.set_mtime(0);
            header.set_mode(mode);
            header.set_size(if large { 0 } else { size });
            header.set_entry_type(if directory {
                tar::EntryType::Directory
            } else {
                tar::EntryType::Regular
            });
            let size_text = size.to_string();
            let mut extensions = Vec::new();
            if name.len() > 100 || !name.is_ascii() {
                extensions.push(("path", name.as_bytes()));
                header.set_path("PaxPayload")?;
            } else {
                header.set_path(&name)?;
            }
            if large {
                extensions.push(("size", size_text.as_bytes()));
            }
            if !extensions.is_empty() {
                archive.append_pax_extensions(extensions)?;
            }
            header.set_cksum();
            if directory {
                archive.append(&header, io::empty())?;
            } else if name == manifest_path {
                archive.append(&header, manifest.as_slice())?;
            } else {
                archive.append(
                    &header,
                    open_regular(&self.source, &entry.expect("source entry").relative)?.take(size),
                )?;
            }
        }
        archive.into_inner()?.finish()?.flush()
    }

    pub fn verify(&self, reader: &mut (impl Read + Seek)) -> Result<(u64, String), String> {
        reader
            .seek(SeekFrom::Start(0))
            .map_err(|error| error.to_string())?;
        let identity = hash_reader(reader).map_err(|error| error.to_string())?;
        reader
            .seek(SeekFrom::Start(0))
            .map_err(|error| error.to_string())?;
        let mut archive = tar::Archive::new(GzDecoder::new(reader));
        let mut seen = BTreeSet::new();
        let manifest_path = self.manifest_path();
        let manifest = self.manifest();
        for member in archive.entries().map_err(|error| error.to_string())? {
            let mut member = member.map_err(|error| error.to_string())?;
            let kind = member.header().entry_type();
            if kind.is_pax_local_extensions() || kind.is_pax_global_extensions() {
                continue;
            }
            let path = member.path().map_err(|error| error.to_string())?;
            let path = posix(&path).trim_end_matches('/').to_owned();
            if !seen.insert(path.clone()) {
                return Err(format!("archive contains duplicate member: {path}"));
            }
            let mode = member.header().mode().map_err(|error| error.to_string())?;
            if path == manifest_path {
                let mut bytes = Vec::new();
                member
                    .read_to_end(&mut bytes)
                    .map_err(|error| error.to_string())?;
                if !kind.is_file() || mode != 0o644 || bytes != manifest {
                    return Err("archive manifest bytes or metadata are not canonical".into());
                }
                continue;
            }
            let expected = self
                .entries
                .get(&path)
                .ok_or_else(|| format!("archive contains unexpected member: {path}"))?;
            if expected.directory {
                if !kind.is_dir() || mode != 0o755 {
                    return Err(format!("archive directory metadata mismatch: {path}"));
                }
            } else {
                if !kind.is_file() || mode != if expected.executable { 0o755 } else { 0o644 } {
                    return Err(format!("archive member mode mismatch: {path}"));
                }
                let (size, hash) = hash_reader(&mut member).map_err(|error| error.to_string())?;
                if size != expected.size || hash != expected.hash {
                    return Err(format!("archive member hash mismatch: {path}"));
                }
            }
        }
        let mut expected: BTreeSet<_> = self.entries.keys().cloned().collect();
        expected.insert(manifest_path);
        if seen != expected {
            return Err("archive is missing members".into());
        }
        Ok(identity)
    }
}

#[derive(Debug)]
pub struct ArchiveResult {
    pub path: PathBuf,
    pub commit: String,
    pub key: String,
    pub size: u64,
    pub sha256: String,
}
struct AnnexState {
    head: String,
    branch: String,
    attributes: Option<(Vec<u8>, u32)>,
    created: Vec<PathBuf>,
}

fn validate_visible(root: &Path, directory: &Dir, relative: &Path) -> Result<(), String> {
    for entry in directory.entries().map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let name = entry.file_name();
        let path = relative.join(&name);
        let metadata = directory
            .symlink_metadata(&name)
            .map_err(|error| error.to_string())?;
        if relative.as_os_str().is_empty() && name == ".git" && metadata.is_dir() {
            continue;
        }
        let parts: Vec<_> = path.components().collect();
        if metadata.is_dir() {
            if parts.is_empty()
                || parts.len() > 4
                || parts[0].as_os_str() != "experiments"
                || parts.len() >= 3 && parts[2].as_os_str() != "raw"
            {
                return Err(format!(
                    "annex repo contains an unexpected visible directory: {}",
                    posix(&path)
                ));
            }
            validate_visible(
                root,
                &directory
                    .open_dir_nofollow(&name)
                    .map_err(|error| error.to_string())?,
                &path,
            )?;
        } else {
            if metadata.is_symlink()
                && directory
                    .metadata(&name)
                    .is_ok_and(|metadata| metadata.is_dir())
            {
                return Err(format!(
                    "annex repo contains an unexpected symlink: {}",
                    root.join(&path).display()
                ));
            }
            let accepted = path == Path::new(".gitattributes")
                || parts.len() == 5
                    && parts[0].as_os_str() == "experiments"
                    && parts[2].as_os_str() == "raw"
                    && name.to_string_lossy().ends_with(".tar.gz")
                    && name != ".tar.gz";
            if !accepted {
                return Err(format!(
                    "annex repo contains an unexpected visible path: {}",
                    root.join(path).display()
                ));
            }
        }
    }
    Ok(())
}

fn annex_state(
    runner: &mut impl GitRunner,
    root: &Path,
    directory: &Dir,
) -> Result<AnnexState, String> {
    if git(runner, root, &["rev-parse", "--is-inside-work-tree"], true)? != "true"
        || git(runner, root, &["rev-parse", "--is-bare-repository"], true)? != "false"
    {
        return Err("annex repo must be a non-bare worktree".into());
    }
    let branch = git(runner, root, &["branch", "--show-current"], true)?;
    if branch.is_empty() || branch.starts_with("experiment-results/") {
        return Err("annex repo must be on a normal branch".into());
    }
    if !git(
        runner,
        root,
        &["status", "--porcelain=v1", "--untracked-files=all"],
        true,
    )?
    .is_empty()
    {
        return Err("annex repo must have a clean index and worktree".into());
    }
    if git(
        runner,
        root,
        &["for-each-ref", "--format=%(refname)", "refs/"],
        true,
    )?
    .lines()
    .any(|name| name.contains("/experiment-results/") || name.ends_with("/experiment-results"))
    {
        return Err("annex repo must not contain experiment-results/* refs".into());
    }
    let attributes = match directory.symlink_metadata(".gitattributes") {
        Ok(metadata) if metadata.is_file() && !metadata.is_symlink() => {
            let mut file = open_regular(directory, Path::new(".gitattributes"))
                .map_err(|error| error.to_string())?;
            let mut bytes = Vec::new();
            file.read_to_end(&mut bytes)
                .map_err(|error| error.to_string())?;
            #[cfg(unix)]
            let mode = {
                use cap_std::fs::PermissionsExt;
                metadata.permissions().mode() & 0o777
            };
            #[cfg(not(unix))]
            let mode = 0o644;
            Some((bytes, mode))
        }
        Ok(_) => return Err("annex repo .gitattributes must be a regular file".into()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => None,
        Err(error) => return Err(error.to_string()),
    };
    validate_visible(root, directory, Path::new(""))?;
    Ok(AnnexState {
        head: git(runner, root, &["rev-parse", "HEAD"], true)?,
        branch,
        attributes,
        created: Vec::new(),
    })
}

fn annex_verify(
    runner: &mut impl GitRunner,
    root: &Path,
    relative: &str,
    size: u64,
    hash: &str,
) -> Result<String, String> {
    let key = git(runner, root, &["annex", "lookupkey", "--", relative], true)?;
    let body = key
        .strip_prefix("SHA256E-s")
        .ok_or_else(|| format!("annex key is not SHA256E: {key}"))?;
    let (key_size, digest) = body
        .split_once("--")
        .ok_or_else(|| format!("invalid SHA256E key: {key}"))?;
    let digest = digest.split('.').next().unwrap_or("");
    if key_size.parse::<u64>().ok() != Some(size) || digest != hash {
        return Err("annex SHA256E key does not match the archive".into());
    }
    let location = git(runner, root, &["annex", "contentlocation", &key], true)?;
    if location.is_empty() {
        return Err("annex contentlocation is empty".into());
    }
    let path = fs::canonicalize(if Path::new(&location).is_absolute() {
        PathBuf::from(location)
    } else {
        root.join(location)
    })
    .map_err(|error| error.to_string())?;
    let mut file = fs::File::open(&path).map_err(|error| error.to_string())?;
    if !file
        .metadata()
        .map_err(|error| error.to_string())?
        .is_file()
        || hash_reader(&mut file).map_err(|error| error.to_string())? != (size, hash.into())
    {
        return Err("annex contentlocation bytes do not match the archive".into());
    }
    git(runner, root, &["annex", "fsck", "--", relative], true)?;
    Ok(key)
}

fn rollback(
    runner: &mut impl GitRunner,
    root: &Path,
    directory: &Dir,
    capability: &SourceMutationCapability,
    relative: &str,
    state: &AnnexState,
    linked: bool,
) -> Result<(), String> {
    let _ = git(
        runner,
        root,
        &["update-index", "--force-remove", "--", relative],
        false,
    );
    if linked {
        directory
            .remove_file(relative)
            .map_err(|error| error.to_string())?;
    }
    let current = directory.symlink_metadata(".gitattributes").is_ok();
    let _ = git(
        runner,
        root,
        &["update-index", "--force-remove", "--", ".gitattributes"],
        false,
    );
    if let Some((bytes, mode)) = &state.attributes {
        capability
            .atomic_write_bytes(&root.join(".gitattributes"), bytes, *mode)
            .map_err(|error| error.to_string())?;
        git(runner, root, &["add", "--", ".gitattributes"], true)?;
    } else if current {
        capability
            .remove_file(&root.join(".gitattributes"))
            .map_err(|error| error.to_string())?;
    }
    for path in state.created.iter().rev() {
        let _ = directory.remove_dir(path);
    }
    Ok(())
}

fn retain_with(
    plan: &RawArchive,
    annex_root: &Path,
    runner: &mut impl GitRunner,
    mut verify: impl FnMut(&RawArchive, &mut cap_std::fs::File) -> Result<(u64, String), String>,
) -> Result<ArchiveResult, String> {
    let root = fs::canonicalize(annex_root).map_err(|error| error.to_string())?;
    if root == plan.source_root
        || root.starts_with(&plan.source_root)
        || plan.source_root.starts_with(&root)
    {
        return Err(
            "source repo root and annex repo root must differ and must not contain one another"
                .into(),
        );
    }
    let directory = open_root_nofollow(&root).map_err(|error| error.to_string())?;
    let mut state = annex_state(runner, &root, &directory)?;
    let relative = plan.archive_relative();
    let relative_text = posix(&relative);
    let path = root.join(&relative);
    if directory.symlink_metadata(&relative).is_ok() {
        return Err(format!("archive target already exists: {}", path.display()));
    }
    let raw_capability = json!({"allowed_paths":[relative_text,".gitattributes"],"purpose":"save-experiment-result-annex","authority":"explicit annex-repo and raw-dir arguments"}).to_string();
    let mut linked = false;
    let attempt = (|| {
        let mut parent = directory.try_clone().map_err(|error| error.to_string())?;
        let mut prefix = PathBuf::new();
        for component in relative
            .parent()
            .expect("archive structural parents")
            .components()
        {
            let Component::Normal(name) = component else {
                return Err("invalid archive parent".into());
            };
            prefix.push(name);
            match parent.symlink_metadata(name) {
                Ok(metadata) if metadata.is_dir() && !metadata.is_symlink() => {}
                Ok(_) => {
                    return Err(format!(
                        "archive parent is not a directory: {}",
                        root.join(&prefix).display()
                    ))
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    parent.create_dir(name).map_err(|error| error.to_string())?;
                    state.created.push(prefix.clone());
                }
                Err(error) => return Err(error.to_string()),
            }
            parent = parent
                .open_dir_nofollow(name)
                .map_err(|error| error.to_string())?;
        }
        let capability = SourceMutationCapability::from_json(&root, Some(&raw_capability))
            .map_err(|error| error.to_string())?;
        let mut archive_identity = None;
        capability
            .publish_noreplace_with(&path, 0o600, |file| {
                plan.write(file)?;
                archive_identity = Some(verify(plan, file).map_err(io_error)?);
                Ok(())
            })
            .map_err(|error| error.to_string())?;
        linked = true;
        let (size, sha256) =
            archive_identity.ok_or("archive verification did not produce identity")?;
        git(
            runner,
            &root,
            &["annex", "add", "--backend=SHA256E", "--", &relative_text],
            true,
        )?;
        let status = git(
            runner,
            &root,
            &["status", "--porcelain=v1", "--untracked-files=all"],
            true,
        )?;
        let changed: BTreeSet<String> = status
            .lines()
            .filter(|line| line.chars().count() >= 4)
            .map(|line| line.chars().skip(3).collect())
            .collect();
        let unexpected: Vec<_> = changed
            .iter()
            .filter(|path| path.as_str() != relative_text && path.as_str() != ".gitattributes")
            .cloned()
            .collect();
        if !unexpected.is_empty() {
            return Err(format!(
                "annex add changed unexpected paths: {}",
                unexpected.join(", ")
            ));
        }
        let key = annex_verify(runner, &root, &relative_text, size, &sha256)?;
        let message = format!(
            "Retain experiment raw archive: {}/{}/{}",
            plan.identity.topic, plan.identity.variant, plan.identity.run_name
        );
        let mut commit_arguments = vec![
            "commit",
            "--only",
            "--message",
            message.as_str(),
            "--",
            relative_text.as_str(),
        ];
        if changed.contains(".gitattributes") {
            commit_arguments.push(".gitattributes");
        }
        git(runner, &root, &commit_arguments, true)?;
        let commit = git(runner, &root, &["rev-parse", "HEAD"], true)?;
        if commit == state.head
            || git(runner, &root, &["rev-parse", &format!("{commit}^")], true)? != state.head
        {
            return Err("annex commit count is not exactly one".into());
        }
        annex_verify(runner, &root, &relative_text, size, &sha256)?;
        let mut reread =
            cap_std::fs::File::from_std(fs::File::open(&path).map_err(|error| error.to_string())?);
        if verify(plan, &mut reread)? != (size, sha256.clone()) {
            return Err("postcommit archive reread differs from precommit archive".into());
        }
        if git(runner, &root, &["branch", "--show-current"], true)? != state.branch {
            return Err("annex branch changed during retention".into());
        }
        if !git(
            runner,
            &root,
            &["status", "--porcelain=v1", "--untracked-files=all"],
            true,
        )?
        .is_empty()
        {
            return Err("annex worktree is not clean after commit".into());
        }
        Ok(ArchiveResult {
            path: path.clone(),
            commit,
            key,
            size,
            sha256,
        })
    })();
    if let Err(error) = attempt {
        let head = git(runner, &root, &["rev-parse", "HEAD"], false).unwrap_or_default();
        if head != state.head {
            return Err(format!("archive committed but verification failed; retained commit {head}: {error}; commit is retained and must not be rewound"));
        }
        let capability = SourceMutationCapability::from_json(&root, Some(&raw_capability))
            .map_err(|error| error.to_string())?;
        rollback(
            runner,
            &root,
            &directory,
            &capability,
            &relative_text,
            &state,
            linked,
        )?;
        return Err(error);
    }
    attempt
}

pub fn retain(plan: &RawArchive, annex_root: &Path) -> Result<ArchiveResult, String> {
    retain_with(plan, annex_root, &mut SystemGit, |plan, file| {
        plan.verify(file)
    })
}

pub fn run(args: &[String]) -> i32 {
    if args
        .iter()
        .any(|argument| argument == "--help" || argument == "-h")
    {
        println!("{USAGE}");
        return 0;
    }
    let mut source = std::env::current_dir().unwrap_or_default();
    let mut annex = std::env::var_os("EXPERIMENT_RAW_ANNEX_REPO").map(PathBuf::from);
    let mut raw = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let (key, inline) = args[index]
            .split_once('=')
            .map_or((args[index].as_str(), None), |(key, value)| {
                (key, Some(value))
            });
        if !["--raw-dir", "--annex-repo", "--source-repo-root"].contains(&key) {
            eprintln!(
                "{USAGE}\nunrecognized arguments: {}",
                args[index..].join(" ")
            );
            return 2;
        }
        let value = if let Some(value) = inline {
            value
        } else {
            index += 1;
            let Some(value) = args.get(index) else {
                eprintln!("{key} requires a value");
                return 2;
            };
            value
        };
        match key {
            "--raw-dir" => raw.push(PathBuf::from(value)),
            "--annex-repo" => annex = Some(value.into()),
            _ => source = value.into(),
        }
        index += 1;
    }
    if raw.len() != 1 {
        eprintln!("exactly one --raw-dir is required");
        return 2;
    }
    let Some(annex) = annex else {
        eprintln!("--annex-repo or EXPERIMENT_RAW_ANNEX_REPO is required");
        return 2;
    };
    let result = RawArchive::prepare(&source, &raw[0]).and_then(|plan| retain(&plan, &annex));
    match result {
        Ok(result) => {
            println!("EXPERIMENT_RAW_STATUS=complete\nEXPERIMENT_RAW_ARCHIVE_PATH={}\nEXPERIMENT_RAW_COMMIT={}\nEXPERIMENT_RAW_ANNEX_KEY={}\nEXPERIMENT_RAW_ARCHIVE_SIZE={}\nEXPERIMENT_RAW_ARCHIVE_SHA256={}", result.path.display(), result.commit, result.key, result.size, result.sha256);
            0
        }
        Err(error) => {
            eprintln!("{error}");
            2
        }
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::fs::{symlink, PermissionsExt};

    fn command(root: &Path, args: &[&str]) -> String {
        git(&mut SystemGit, root, args, true).expect("fixture Git command")
    }
    fn init_repository(root: &Path) {
        fs::create_dir_all(root).unwrap();
        command(root, &["init", "-q"]);
        command(root, &["checkout", "-q", "-b", "main"]);
        command(root, &["config", "user.name", "Annex Test"]);
        command(
            root,
            &["config", "user.email", "annex-test@example.invalid"],
        );
    }
    fn source(root: &Path) -> PathBuf {
        init_repository(root);
        let result = root.join("experiments/demo/result/run-a");
        let raw = result.join("raw");
        fs::create_dir_all(raw.join("nested")).unwrap();
        fs::create_dir_all(result.join("summary")).unwrap();
        fs::create_dir_all(root.join("experiments/demo/report")).unwrap();
        fs::write(raw.join(".gitignore"), "*\n!.gitignore\n").unwrap();
        fs::write(raw.join("samples.bin"), b"\0\x01raw-samples\n").unwrap();
        fs::write(raw.join("nested/collect.sh"), "#!/bin/sh\nprintf raw\n").unwrap();
        fs::set_permissions(
            raw.join("nested/collect.sh"),
            fs::Permissions::from_mode(0o755),
        )
        .unwrap();
        fs::write(
            result.join("summary/summary.json"),
            "{\"case_count\": 1, \"run_id\": \"run-a\", \"status\": \"success\"}\n",
        )
        .unwrap();
        fs::write(result.join("run_manifest.json"), "{\"identity\": {\"run_name\": \"run-a\", \"schema\": \"agentcanon.experiment-run-identity/v2\", \"topic\": \"demo\", \"variant\": \"formal\"}, \"raw_artifacts\": {\"path\": \"experiments/demo/result/run-a/raw\", \"retention\": {\"state\": \"unarchived\"}}, \"status\": \"completed\"}\n").unwrap();
        fs::write(
            root.join("experiments/demo/report/run-a.md"),
            "# compact reader report\n",
        )
        .unwrap();
        command(root, &["add", "experiments"]);
        command(root, &["commit", "-qm", "source evidence"]);
        fs::write(root.join("source-dirty.txt"), "dirty\n").unwrap();
        raw.canonicalize().unwrap()
    }
    fn annex(root: &Path) {
        init_repository(root);
        command(root, &["commit", "--allow-empty", "-qm", "initial"]);
    }

    #[derive(Default)]
    struct AnnexProvider {
        archive: Option<String>,
        fsck: usize,
        fail_fsck: bool,
    }
    impl GitRunner for AnnexProvider {
        fn execute(&mut self, root: &Path, args: &[&str]) -> Result<GitOutput, String> {
            if args.first() != Some(&"annex") {
                return SystemGit.execute(root, args);
            }
            let output = match args.get(1).copied() {
                Some("add") => {
                    let path = args.last().ok_or("archive argument")?;
                    self.archive = Some((*path).into());
                    return SystemGit.execute(root, &["add", "--", path]);
                }
                Some("lookupkey") => {
                    let mut file = fs::File::open(root.join(args.last().ok_or("archive path")?))
                        .map_err(|error| error.to_string())?;
                    let (size, hash) = hash_reader(&mut file).map_err(|error| error.to_string())?;
                    format!("SHA256E-s{size}--{hash}.tar.gz")
                }
                Some("contentlocation") => self.archive.clone().ok_or("archive was not added")?,
                Some("fsck") => {
                    self.fsck += 1;
                    if self.fail_fsck {
                        return Ok(GitOutput {
                            code: 1,
                            stdout: String::new(),
                            stderr: "injected fsck failure".into(),
                        });
                    }
                    String::new()
                }
                other => return Err(format!("unexpected provider command: {other:?}")),
            };
            Ok(GitOutput {
                code: 0,
                stdout: output,
                stderr: String::new(),
            })
        }
    }

    #[test]
    fn raw_archive_excludes_compact_evidence_and_is_reproducible() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("source");
        let raw = source(&root);
        let plan = RawArchive::prepare(&root, &raw).unwrap();
        let mut first = Vec::new();
        let mut second = Vec::new();
        plan.write(&mut first).unwrap();
        plan.write(&mut second).unwrap();
        assert_eq!(first, second);
        let mut archive = tar::Archive::new(GzDecoder::new(first.as_slice()));
        let mut names = BTreeSet::new();
        let mut manifest = None;
        for member in archive.entries().unwrap() {
            let mut member = member.unwrap();
            let name = posix(&member.path().unwrap());
            assert_eq!(member.header().uid().unwrap(), 0);
            assert_eq!(member.header().gid().unwrap(), 0);
            assert_eq!(member.header().mtime().unwrap(), 0);
            assert!(member.header().username().unwrap().unwrap_or("").is_empty());
            assert!(member
                .header()
                .groupname()
                .unwrap()
                .unwrap_or("")
                .is_empty());
            assert!(
                !name.contains("/summary/")
                    && !name.contains("/report/")
                    && !name.ends_with("summary.json")
            );
            if name.ends_with(MANIFEST) {
                let mut bytes = Vec::new();
                member.read_to_end(&mut bytes).unwrap();
                manifest = Some(serde_json::from_slice::<Value>(&bytes).unwrap());
            }
            names.insert(name);
        }
        assert!(names.contains("experiments/demo/result/run-a/raw/samples.bin"));
        assert!(names.contains("experiments/demo/result/run-a/raw/nested/collect.sh"));
        let manifest = manifest.unwrap();
        assert_eq!(manifest["schema"], "git-annex-raw-retention/v1");
        assert_eq!(
            manifest["raw"]["directory"],
            "experiments/demo/result/run-a/raw"
        );
        assert_eq!(
            manifest["tracked_result_evidence"]["summary"]["path"],
            "experiments/demo/result/run-a/summary/summary.json"
        );
        assert_eq!(
            manifest["tracked_result_evidence"]["run_manifest"]["path"],
            "experiments/demo/result/run-a/run_manifest.json"
        );
        assert_eq!(
            manifest["tracked_result_evidence"]["summary"]["sha256"]
                .as_str()
                .unwrap()
                .len(),
            64
        );
        assert!(manifest["source"]["dirty_paths"]
            .as_array()
            .unwrap()
            .contains(&json!("source-dirty.txt")));
    }

    #[test]
    fn tracked_evidence_and_raw_binding_are_required() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("source");
        let raw = source(&root);
        let manifest = root.join("experiments/demo/result/run-a/run_manifest.json");
        let content = fs::read_to_string(&manifest).unwrap().replace(
            "experiments/demo/result/run-a/raw",
            "experiments/demo/result/other/raw",
        );
        fs::write(&manifest, &content).unwrap();
        assert!(RawArchive::prepare(&root, &raw)
            .err()
            .unwrap()
            .contains("must match source commit"));
        command(
            &root,
            &["add", "experiments/demo/result/run-a/run_manifest.json"],
        );
        command(&root, &["commit", "-qm", "mismatched binding"]);
        assert!(RawArchive::prepare(&root, &raw)
            .err()
            .unwrap()
            .contains("raw path does not match"));
        command(
            &root,
            &[
                "rm",
                "--cached",
                "experiments/demo/result/run-a/summary/summary.json",
            ],
        );
        assert!(RawArchive::prepare(&root, &raw)
            .err()
            .unwrap()
            .contains("must be tracked"));
    }

    #[test]
    fn raw_empty_symlink_special_pointer_and_reserved_entries_are_rejected() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("source");
        let raw = source(&root);
        fs::remove_dir_all(&raw).unwrap();
        fs::create_dir(&raw).unwrap();
        assert!(RawArchive::prepare(&root, &raw)
            .err()
            .unwrap()
            .contains("raw directory is empty"));
        fs::write(raw.join("target"), "target\n").unwrap();
        symlink("target", raw.join("link")).unwrap();
        assert!(RawArchive::prepare(&root, &raw)
            .err()
            .unwrap()
            .contains("symlink"));
        fs::remove_file(raw.join("link")).unwrap();
        assert!(Command::new("mkfifo")
            .arg(raw.join("fifo"))
            .status()
            .unwrap()
            .success());
        assert!(RawArchive::prepare(&root, &raw)
            .err()
            .unwrap()
            .contains("special file"));
        fs::remove_file(raw.join("fifo")).unwrap();
        fs::write(
            raw.join("target"),
            format!(
                "version https://git-lfs.github.com/spec/v1\noid sha256:{}\nsize 42\n",
                "a".repeat(64)
            ),
        )
        .unwrap();
        assert!(RawArchive::prepare(&root, &raw)
            .err()
            .unwrap()
            .contains("Git-LFS pointer"));
        fs::remove_file(raw.join("target")).unwrap();
        fs::write(raw.join(MANIFEST), "reserved\n").unwrap();
        assert!(RawArchive::prepare(&root, &raw)
            .err()
            .unwrap()
            .contains("reserves"));
    }

    #[test]
    fn retention_is_append_only_and_fsck_surrounds_one_commit() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("source");
        let raw = source(&root);
        let annex_root = temporary.path().join("annex");
        annex(&annex_root);
        let before = command(&annex_root, &["rev-parse", "HEAD"]);
        let plan = RawArchive::prepare(&root, &raw).unwrap();
        let mut provider = AnnexProvider::default();
        let result = retain_with(&plan, &annex_root, &mut provider, |plan, file| {
            plan.verify(file)
        })
        .unwrap();
        assert_eq!(provider.fsck, 2);
        assert_eq!(
            command(&annex_root, &["rev-parse", &format!("{}^", result.commit)]),
            before
        );
        let bytes = fs::read(&result.path).unwrap();
        assert!(
            retain_with(&plan, &annex_root, &mut provider, |plan, file| plan
                .verify(file))
            .unwrap_err()
            .contains("archive target already exists")
        );
        assert_eq!(command(&annex_root, &["rev-parse", "HEAD"]), result.commit);
        assert_eq!(fs::read(&result.path).unwrap(), bytes);
        assert!(command(
            &annex_root,
            &["status", "--porcelain=v1", "--untracked-files=all"]
        )
        .is_empty());
    }

    #[test]
    fn precommit_failure_removes_only_owned_changes() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("source");
        let raw = source(&root);
        let annex_root = temporary.path().join("annex");
        annex(&annex_root);
        let before = command(&annex_root, &["rev-parse", "HEAD"]);
        let plan = RawArchive::prepare(&root, &raw).unwrap();
        let mut provider = AnnexProvider {
            fail_fsck: true,
            ..AnnexProvider::default()
        };
        assert!(
            retain_with(&plan, &annex_root, &mut provider, |plan, file| plan
                .verify(file))
            .unwrap_err()
            .contains("injected fsck failure")
        );
        assert_eq!(command(&annex_root, &["rev-parse", "HEAD"]), before);
        assert!(!annex_root.join(plan.archive_relative()).exists());
        assert!(command(
            &annex_root,
            &["status", "--porcelain=v1", "--untracked-files=all"]
        )
        .is_empty());
    }

    #[test]
    fn postcommit_reread_failure_keeps_the_completed_commit() {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().join("source");
        let raw = source(&root);
        let annex_root = temporary.path().join("annex");
        annex(&annex_root);
        let before = command(&annex_root, &["rev-parse", "HEAD"]);
        let plan = RawArchive::prepare(&root, &raw).unwrap();
        let mut provider = AnnexProvider::default();
        let mut reads = 0;
        let error = retain_with(&plan, &annex_root, &mut provider, |plan, file| {
            reads += 1;
            if reads == 2 {
                Err("injected postcommit reread failure".into())
            } else {
                plan.verify(file)
            }
        })
        .unwrap_err();
        assert!(error.contains("retained commit"));
        let after = command(&annex_root, &["rev-parse", "HEAD"]);
        assert_ne!(before, after);
        assert_eq!(
            command(&annex_root, &["rev-parse", &format!("{after}^")]),
            before
        );
    }
}
