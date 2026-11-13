//! Native CLI contracts for the resident lifecycle controller.

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::TempDir;

struct Fixture {
    _temporary: TempDir,
    control: PathBuf,
    runtime: PathBuf,
    private_log: PathBuf,
    repository: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let temporary = tempfile::tempdir().expect("temporary runtime fixture");
        let control = temporary.path().join("control");
        let runtime = control.join("runtime");
        let private_log = temporary.path().join("private-log");
        fs::create_dir_all(&control).expect("control root");
        fs::create_dir_all(&private_log).expect("private log mount");
        let repository = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../../")
            .canonicalize()
            .expect("repository root");
        Self {
            _temporary: temporary,
            control,
            runtime,
            private_log,
            repository,
        }
    }

    fn run(&self, arguments: &[&str], extra: &[(&str, &str)]) -> Output {
        let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
        command
            .arg("bootstrap-runtime")
            .arg("--repository-root")
            .arg(&self.repository)
            .arg("--control-parent-root")
            .arg(&self.control)
            .arg("--runtime-root")
            .arg(&self.runtime)
            .args(arguments)
            .env("AGENT_CANON_PRIVATE_LOG_ROOT", &self.private_log)
            .env_remove("AGENT_CANON_HOST_INSTALL_ROOT")
            .env_remove("AGENT_CANON_HOST_CODEX_HOME_ROOT")
            .env_remove("AGENT_CANON_HOST_SPOOL_ROOT")
            .env_remove("AGENT_CANON_HOST_ARCHIVE_ROOT")
            .env_remove("AGENT_CANON_HOST_CACHE_ROOT")
            .env_remove("AGENT_CANON_EXCHANGE_ROOT")
            .env_remove("AGENT_CANON_CONTROL_ROOT_DIGEST")
            .env_remove("AGENT_CANON_CONTAINER_ID")
            .env_remove("AGENT_CANON_IMAGE_ID")
            .env_remove("AGENT_CANON_IMAGE_REF")
            .env_remove("AGENT_CANON_TARGET_DIGEST")
            .env_remove("AGENT_CANON_TARGET_HOST_ROOT")
            .env_remove("AGENT_CANON_TARGET_CONTAINER_ROOT")
            .env_remove("AGENT_CANON_PREVIOUS_IMAGE_ID")
            .env_remove("AGENT_CANON_PREVIOUS_IMAGE_REF")
            .env_remove("AGENT_CANON_RESTORE_IMAGE_ID")
            .env_remove("AGENT_CANON_RESTORE_IMAGE_REF")
            .env_remove("AGENT_CANON_CURRENT_IMAGE_ID")
            .env_remove("AGENT_CANON_CURRENT_IMAGE_REF");
        for (key, value) in extra {
            command.env(key, value);
        }
        command.output().expect("native bootstrap CLI starts")
    }
}

fn payload(output: &Output) -> Value {
    serde_json::from_slice(if output.status.success() {
        &output.stdout
    } else {
        &output.stderr
    })
    .expect("controller emits a JSON payload")
}

#[test]
fn status_is_native_and_does_not_require_docker() {
    let fixture = Fixture::new();
    let output = fixture.run(&["status"], &[("AGENT_CANON_DOCKER", "missing-docker")]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let receipt = payload(&output);
    assert_eq!(receipt["operation"], "status");
    assert_eq!(receipt["code"], "status");
    assert!(fixture.runtime.join("receipts").is_dir());
}

#[test]
fn target_task_and_gc_operations_share_one_native_state_owner() {
    let fixture = Fixture::new();
    let target = fixture._temporary.path().join("target");
    fs::create_dir_all(&target).expect("target directory");
    let installed = fixture.run(&["install"], &[]);
    assert!(
        installed.status.success(),
        "{}",
        String::from_utf8_lossy(&installed.stderr)
    );

    let target_output = fixture.run(
        &[
            "target",
            "add",
            "--root",
            target.to_str().unwrap(),
            "--mode",
            "read-only",
        ],
        &[],
    );
    assert!(
        target_output.status.success(),
        "{}",
        String::from_utf8_lossy(&target_output.stderr)
    );
    assert_eq!(payload(&target_output)["operation"], "target_add");

    let admitted = fixture.run(
        &[
            "task",
            "admit",
            "--task-id",
            "fixture-task",
            "--root",
            target.to_str().unwrap(),
        ],
        &[],
    );
    assert!(
        admitted.status.success(),
        "{}",
        String::from_utf8_lossy(&admitted.stderr)
    );
    assert_eq!(payload(&admitted)["code"], "task_reserved");

    let released = fixture.run(&["task", "release", "--task-id", "fixture-task"], &[]);
    assert!(
        released.status.success(),
        "{}",
        String::from_utf8_lossy(&released.stderr)
    );
    assert_eq!(payload(&released)["code"], "task_released");

    let planned = fixture.run(&["gc", "--dry-run"], &[]);
    assert!(
        planned.status.success(),
        "{}",
        String::from_utf8_lossy(&planned.stderr)
    );
    assert_eq!(payload(&planned)["code"], "gc_plan");
}

#[test]
fn structured_exec_requires_the_authenticated_target_digest() {
    let fixture = Fixture::new();
    let request = r#"{"schema":"agent-canon.tool-exec-request.v1"}"#;
    let output = fixture.run(
        &[
            "exec",
            "--target-digest",
            "fixture",
            "--request-json",
            request,
        ],
        &[],
    );
    assert_eq!(output.status.code(), Some(2));
    assert_eq!(payload(&output)["code"], "invalid_exec_request");
}

#[test]
fn exec_rejects_project_commands_before_target_admission() {
    let fixture = Fixture::new();
    let output = fixture.run(&["exec", "--root", "/tmp", "--", "/bin/false"], &[]);
    assert_eq!(output.status.code(), Some(2));
    assert_eq!(payload(&output)["code"], "tool_plane_command_rejected");
    assert!(!fixture.runtime.join("tasks").join("exec-").exists());
}
