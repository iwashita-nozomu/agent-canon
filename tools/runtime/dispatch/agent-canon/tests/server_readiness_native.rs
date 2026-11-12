// @dependency-start
// contract test
// responsibility Verifies native server readiness and opt-in host layout requirements.
// upstream implementation ../src/server_readiness.rs native readiness owner
// upstream design ../../../../../documents/contracts/server-host-contract.md server host requirements
// @dependency-end

use agent_canon::server_readiness::{
    evaluate, parse_layout, parse_mounts_text, CommandStatus, Context, MountInfo, Report,
};
use std::collections::BTreeMap;
use std::path::PathBuf;

const LAYOUT: &str = include_str!("../../../../../tests/fixtures/server_readiness/layout.toml");
const MOUNTS: &str = include_str!("../../../../../tests/fixtures/server_readiness/mounts.txt");

fn context() -> Context {
    Context {
        host_kind: "linux".to_owned(),
        kernel: "Linux fixture 6.0".to_owned(),
        username: "server-user".to_owned(),
        active_groups: Vec::new(),
        commands: BTreeMap::from([
            ("git".to_owned(), true),
            ("codex".to_owned(), false),
            ("python3".to_owned(), false),
            ("docker".to_owned(), false),
            ("podman".to_owned(), false),
        ]),
        mounts: parse_mounts_text(MOUNTS),
        mount_table_error: None,
        docker_socket_exists: false,
        docker_socket_accessible: false,
        docker_version: None,
        docker_group_members: Default::default(),
        workspace_root: None,
    }
}

fn has_finding(report: &Report, level: &str, fragment: &str) -> bool {
    report
        .findings
        .iter()
        .any(|finding| finding.level == level && finding.message.contains(fragment))
}

#[test]
fn native_cli_readiness_does_not_require_host_python_or_a_container_runtime_by_default() {
    let report = evaluate(None, &context());

    assert_eq!(report.exit_code(), 0);
    assert!(has_finding(
        &report,
        "warning",
        "no container CLI is available"
    ));
    assert!(!report.findings.iter().any(|finding| {
        finding.level == "error"
            && (finding.message.contains("python") || finding.message.contains("docker"))
    }));
}

#[test]
fn explicit_layout_provider_requirements_are_checked() {
    let layout = parse_layout(LAYOUT).expect("controlled layout fixture is valid");
    let report = evaluate(Some(&layout), &context());

    assert_eq!(report.exit_code(), 1);
    assert!(has_finding(&report, "error", "codex is not available"));
    assert!(has_finding(&report, "error", "python3 is not available"));
    assert!(has_finding(&report, "error", "docker is not available"));
    assert!(has_finding(
        &report,
        "ok",
        "workspace_root mount type matches: cifs"
    ));
}

#[test]
fn explicitly_selected_docker_requires_a_usable_daemon() {
    let layout = parse_layout(LAYOUT).expect("controlled layout fixture is valid");
    let mut host = context();
    host.commands.insert("codex".to_owned(), true);
    host.commands.insert("python3".to_owned(), true);
    host.commands.insert("docker".to_owned(), true);
    host.docker_version = Some(CommandStatus {
        succeeded: false,
        detail: "daemon unavailable".to_owned(),
    });
    host.docker_socket_exists = true;

    let report = evaluate(Some(&layout), &host);

    assert!(has_finding(
        &report,
        "error",
        "docker version failed: daemon unavailable"
    ));
    assert!(has_finding(
        &report,
        "error",
        "docker socket exists but is not accessible"
    ));
}

#[test]
fn required_mount_mismatch_is_an_error_and_optional_mismatch_is_a_warning() {
    let layout = parse_layout(LAYOUT).expect("controlled layout fixture is valid");
    let mut host = context();
    host.mounts.insert(
        PathBuf::from("/srv/workspace"),
        MountInfo {
            source: "/dev/workspace".to_owned(),
            fs_type: "ext4".to_owned(),
        },
    );
    host.mounts.insert(
        PathBuf::from("/srv/local-state"),
        MountInfo {
            source: "/dev/state".to_owned(),
            fs_type: "cifs".to_owned(),
        },
    );

    let report = evaluate(Some(&layout), &host);

    assert!(has_finding(
        &report,
        "error",
        "workspace_root mount type mismatch"
    ));
    assert!(has_finding(
        &report,
        "warning",
        "local_state_root mount type mismatch"
    ));
}

#[test]
fn workspace_path_is_inspected_only_when_explicitly_supplied() {
    let mut host = context();
    let report = evaluate(None, &host);
    assert!(!report
        .findings
        .iter()
        .any(|finding| finding.message.contains("workspace_root")));

    let workspace = tempfile::tempdir().expect("temporary workspace fixture is created");
    host.workspace_root = Some(workspace.path().to_path_buf());
    let report = evaluate(None, &host);

    assert!(has_finding(&report, "ok", "workspace_root exists"));
}
