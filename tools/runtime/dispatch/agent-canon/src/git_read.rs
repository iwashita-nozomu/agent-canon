// @dependency-start
// contract implementation
// responsibility Reads bounded Git command output for native repository diagnostics.
// upstream implementation notebook_quality.rs supplies the existing concurrent pipe-drain pattern
// @dependency-end

use std::io::Read;
use std::path::Path;
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

pub(crate) struct IndexEntry {
    pub mode: String,
    pub object: String,
    pub path: String,
}

pub(crate) fn require_repository_root(root: &Path) -> Result<(), String> {
    if repository_bytes(root, &["rev-parse", "--show-prefix"])?
        .iter()
        .all(u8::is_ascii_whitespace)
    {
        Ok(())
    } else {
        Err("--root must select the repository root".into())
    }
}

pub(crate) fn index_entries(root: &Path) -> Result<Vec<IndexEntry>, String> {
    let output = repository_bytes(root, &["ls-files", "-z", "-s"])?;
    output
        .split(|byte| *byte == 0)
        .filter(|entry| !entry.is_empty())
        .map(|entry| {
            let tab = entry
                .iter()
                .position(|byte| *byte == b'\t')
                .ok_or("git ls-files returned an invalid index entry")?;
            let metadata = std::str::from_utf8(&entry[..tab])
                .map_err(|error| format!("git index metadata: {error}"))?;
            let mut fields = metadata.split_whitespace();
            let (Some(mode), Some(object), Some(_stage), None) =
                (fields.next(), fields.next(), fields.next(), fields.next())
            else {
                return Err("git ls-files returned invalid index metadata".into());
            };
            Ok(IndexEntry {
                mode: mode.to_owned(),
                object: object.to_owned(),
                path: String::from_utf8_lossy(&entry[tab + 1..]).into_owned(),
            })
        })
        .collect()
}

pub(crate) fn repository_bytes(root: &Path, args: &[&str]) -> Result<Vec<u8>, String> {
    let command = args.first().copied().unwrap_or("command");
    let result = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| format!("could not start git {command}: {error}"))?;
    if !result.status.success() {
        return Err(format!(
            "git {command} failed in {}: {}",
            root.display(),
            String::from_utf8_lossy(&result.stderr).trim()
        ));
    }
    Ok(result.stdout)
}

pub fn output(root: &Path, args: &[&str], timeout: Duration) -> Result<Option<String>, String> {
    let mut child = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("could not start git: {error}"))?;
    let mut stdout = child
        .stdout
        .take()
        .ok_or_else(|| "could not capture git output".to_owned())?;
    let reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout.read_to_end(&mut bytes).map(|_| bytes)
    });
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if started.elapsed() < timeout => thread::sleep(Duration::from_millis(10)),
            Ok(None) | Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
        }
    };
    let bytes = reader
        .join()
        .map_err(|_| "could not read git output".to_owned())?
        .map_err(|error| format!("could not read git output: {error}"))?;
    if status.is_none() {
        return Err("git command timed out or failed while waiting".to_owned());
    }
    if !status.is_some_and(|status| status.success()) {
        return Ok(None);
    }
    String::from_utf8(bytes)
        .map(Some)
        .map_err(|error| format!("git output is not UTF-8: {error}"))
}
