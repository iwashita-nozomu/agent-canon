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
