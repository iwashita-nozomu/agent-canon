// @dependency-start
// contract implementation
// responsibility Exposes the private feedback/knowledge command family from the Rust CLI.
// upstream design ../../../../../documents/runtime/private-feedback-knowledge.md private feedback command and storage contract
// upstream implementation ../../../archive/private_feedback.py owns private storage and sync semantics
// downstream implementation ../../../../../tests/agent_tools/test_private_feedback.py validates metadata/redaction boundaries
// @dependency-end

//! Rust-owned public command boundary for private feedback and knowledge.
//!
//! Storage remains in the Python adapter because it shares the host archive
//! Git adapter and annex capability probes.  The public executable and its
//! short aliases remain Rust-owned, so callers do not acquire a flat Python
//! executable or a second command namespace.

use std::env;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const ADAPTER_RELATIVE: &str = "tools/runtime/archive/private_feedback.py";
const INSTALLED_ADAPTER_RELATIVE: &str = "share/agent-canon/private_feedback.py";

fn adapter_path() -> Option<PathBuf> {
    let mut candidates = Vec::new();
    let executable = env::current_exe().ok();
    if let Some(executable) = &executable {
        if let Some(bin_dir) = executable.parent() {
            if let Some(prefix) = bin_dir.parent() {
                candidates.push(prefix.join(INSTALLED_ADAPTER_RELATIVE));
            }
        }
    }
    candidates.extend(
        [
            env::var_os("AGENT_CANON_RUNTIME_TOOLS_ROOT")
                .map(PathBuf::from)
                .map(|root| root.join(ADAPTER_RELATIVE)),
            env::var_os("AGENT_CANON_SOURCE_ROOT")
                .map(PathBuf::from)
                .map(|root| root.join(ADAPTER_RELATIVE)),
        ]
        .into_iter()
        .flatten(),
    );
    if let Some(executable) = executable {
        candidates.extend(
            executable
                .ancestors()
                .map(|ancestor| ancestor.join(ADAPTER_RELATIVE)),
        );
    }
    candidates.into_iter().find(|path| Path::is_file(path))
}

pub fn run(args: &[String]) -> i32 {
    let Some(adapter) = adapter_path() else {
        eprintln!("PRIVATE_FEEDBACK=fail error=adapter_unavailable");
        return 2;
    };
    let python = env::var_os("AGENT_CANON_PYTHON").unwrap_or_else(|| {
        if cfg!(windows) {
            "python".into()
        } else {
            "python3".into()
        }
    });
    let mut command = Command::new(python);
    command.arg(adapter).args(args);
    command.stdin(Stdio::inherit());
    command.stdout(Stdio::inherit());
    command.stderr(Stdio::inherit());
    match command.status() {
        Ok(status) => status.code().unwrap_or(1),
        Err(error) => {
            eprintln!("PRIVATE_FEEDBACK=fail error=adapter_exec:{error}");
            2
        }
    }
}
