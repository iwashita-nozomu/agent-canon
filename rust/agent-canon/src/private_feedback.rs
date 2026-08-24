// @dependency-start
// contract implementation
// responsibility Exposes the private feedback/knowledge command family from the Rust CLI.
// upstream design ../../../documents/runtime/private-feedback-knowledge.md
// upstream implementation ../../../tools/agent_tools/private_feedback.py owns private storage and sync semantics
// downstream implementation ../../../tests/agent_tools/test_private_feedback.py validates metadata/redaction boundaries
// @dependency-end

//! Rust-owned public command boundary for private feedback and knowledge.
//!
//! Storage remains in the Python adapter because it shares the host archive
//! Git adapter and annex capability probes.  The public executable and its
//! short aliases remain Rust-owned, so callers do not acquire a flat Python
//! executable or a second command namespace.

use std::env;
use std::path::PathBuf;
use std::process::{Command, Stdio};

fn adapter_path() -> Option<PathBuf> {
    let candidates = [
        env::var_os("AGENT_CANON_RUNTIME_TOOLS_ROOT")
            .map(PathBuf::from)
            .map(|root| root.join("tools/agent_tools/private_feedback.py")),
        env::var_os("AGENT_CANON_SOURCE_ROOT")
            .map(PathBuf::from)
            .map(|root| root.join("tools/agent_tools/private_feedback.py")),
        Some(PathBuf::from("tools/agent_tools/private_feedback.py")),
    ];
    candidates.into_iter().flatten().find(|path| path.is_file())
}

pub fn run(args: &[String]) -> i32 {
    let Some(adapter) = adapter_path() else {
        eprintln!("PRIVATE_FEEDBACK=fail error=adapter_unavailable");
        return 2;
    };
    let mut command = Command::new("python3");
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
