use serde_json::json;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const NATIVE: &str = env!("CARGO_BIN_EXE_agent-canon");

fn git(root: &Path, args: &[&str]) {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}

fn init_repo(root: &Path) {
    fs::create_dir_all(root).unwrap();
    git(root, &["init", "-q", "-b", "main"]);
    git(root, &["config", "user.name", "Runtime Archive Test"]);
    git(
        root,
        &[
            "config",
            "user.email",
            "runtime-archive-test@example.invalid",
        ],
    );
    fs::write(root.join("README.md"), "runtime archive fixture\n").unwrap();
    git(root, &["add", "README.md"]);
    git(root, &["commit", "-m", "fixture source"]);
}

fn archive_command(
    source: &Path,
    canon: &Path,
    archive: &Path,
    runtime: &Path,
    remote: &str,
    args: &[&str],
    session_root: Option<&Path>,
) -> Output {
    let mut command = Command::new(NATIVE);
    command
        .arg("runtime-log-archive-git")
        .arg("--source-root")
        .arg(source)
        .arg("--canon-root")
        .arg(canon)
        .arg("--archive-root")
        .arg(archive)
        .arg("--runtime-root")
        .arg(runtime)
        .arg("--remote")
        .arg(remote)
        .args(args);
    if let Some(root) = session_root {
        command.env("AGENT_CANON_CODEX_SESSION_ROOT", root);
    } else {
        command.env_remove("AGENT_CANON_CODEX_SESSION_ROOT");
    }
    command.output().unwrap()
}

fn fixture() -> (
    tempfile::TempDir,
    PathBuf,
    PathBuf,
    PathBuf,
    PathBuf,
    PathBuf,
) {
    let temporary = tempfile::tempdir().unwrap();
    let root = temporary.path();
    let source = root.join("source");
    let canon = root.join("agent-canon");
    let archive = root.join("archive");
    let runtime = root.join("runtime");
    let sessions = root.join("sessions");
    init_repo(&source);
    init_repo(&canon);
    fs::create_dir_all(&runtime).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&runtime, fs::Permissions::from_mode(0o700)).unwrap();
    }
    fs::create_dir_all(&sessions).unwrap();
    git(
        &source,
        &[
            "remote",
            "add",
            "origin",
            "https://github.com/example/source.git",
        ],
    );
    (temporary, source, canon, archive, runtime, sessions)
}

#[test]
fn native_cli_exposes_all_archive_subcommands() {
    let output = Command::new(NATIVE)
        .args(["runtime-log-archive-git", "--help"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let help = String::from_utf8_lossy(&output.stdout);
    for command in [
        "append-context-discovery",
        "materialize-runtime-event",
        "repo-key",
        "ensure",
        "status",
        "check-clean",
        "archive-agent-reports",
        "import-legacy",
        "import-eval-results",
        "archive-eval",
        "archive-agent-report",
        "push",
        "sync",
    ] {
        assert!(help.contains(command), "missing {command} in {help}");
    }
}

#[test]
fn append_and_materialize_bind_the_exact_rollout_or_reject_unsupported_publication() {
    let (_temporary, source, canon, archive, runtime, sessions) = fixture();
    let context_id = "11111111-1111-4111-8111-111111111111";
    let parent_id = "22222222-2222-4222-8222-222222222222";
    let turn_id = "33333333-3333-4333-8333-333333333333";
    let session = json!({
        "type":"session_meta",
        "payload":{
            "id":context_id,
            "parent_thread_id":parent_id,
            "agent_role":"reviewer",
            "cwd":source.to_string_lossy(),
            "source":{"subagent":{"thread_spawn":{"parent_thread_id":parent_id,"agent_role":"reviewer"}}}
        }
    });
    let complete = json!({"type":"event_msg","payload":{"type":"task_complete","turn_id":turn_id}});
    let mut rollout = serde_json::to_vec(&session).unwrap();
    rollout.push(b'\n');
    rollout.extend_from_slice(&serde_json::to_vec(&complete).unwrap());
    rollout.push(b'\n');
    let date = sessions.join("2026/11/13");
    fs::create_dir_all(&date).unwrap();
    let rollout_path = date.join(format!("rollout-2026-11-13T09-27-36Z-{context_id}.jsonl"));
    fs::write(&rollout_path, rollout).unwrap();

    let run_id = "run-native-1";
    let active = source.join("reports/agents").join(run_id);
    fs::create_dir_all(&active).unwrap();
    fs::write(
        source.join("reports/agents/.active_run"),
        format!("{run_id}\n"),
    )
    .unwrap();
    let design = source.join("docs/design.md");
    fs::create_dir_all(design.parent().unwrap()).unwrap();
    fs::write(&design, "# Design\n\nReviewed architecture.\n").unwrap();
    let design_sha = {
        use sha2::{Digest, Sha256};
        Sha256::digest(fs::read(&design).unwrap())
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    };
    fs::write(
        active.join("change_review.md"),
        format!("# Change Review\n\n- Design artifact path: `docs/design.md`\n- review_target_sha256={design_sha}\n\n## Decision\n\nAPPROVE\n\n## Evidence\n\nSource-bound native review fixture.\n"),
    ).unwrap();
    git(&source, &["add", "reports/agents", "docs/design.md"]);
    git(&source, &["commit", "-m", "fixture review evidence"]);

    let append = archive_command(
        &source,
        &canon,
        &archive,
        &runtime,
        "https://example.com/agent-canon-log.git",
        &[
            "append-context-discovery",
            "--run-id",
            run_id,
            "--agent-context-id",
            context_id,
            "--turn-id",
            turn_id,
        ],
        Some(&sessions),
    );
    if !cfg!(target_os = "linux") {
        assert!(!append.status.success());
        assert!(String::from_utf8_lossy(&append.stdout)
            .contains("CONTEXT_DISCOVERY_ERROR_CODE=context_publication_failure"));
        assert!(!fs::read_dir(&active).unwrap().any(|entry| entry
            .unwrap()
            .file_name()
            .to_string_lossy()
            .starts_with("context_discovery.")));
        return;
    }
    assert!(
        append.status.success(),
        "{}",
        String::from_utf8_lossy(&append.stdout)
    );
    let append_stdout = String::from_utf8_lossy(&append.stdout);
    assert!(append_stdout.contains("CONTEXT_DISCOVERY_APPEND=pass"));
    let certificate = fs::read_dir(&active)
        .unwrap()
        .map(Result::unwrap)
        .map(|entry| entry.path())
        .find(|path| {
            path.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("context_discovery.")
        })
        .unwrap();
    let certificate_value: serde_json::Value =
        serde_json::from_slice(&fs::read(&certificate).unwrap()).unwrap();
    assert_eq!(
        certificate_value["rollout"]["path"],
        rollout_path.to_string_lossy().as_ref()
    );
    assert_eq!(certificate_value["context"]["turn_id"], turn_id);

    let materialize = archive_command(
        &source,
        &canon,
        &archive,
        &runtime,
        "https://example.com/agent-canon-log.git",
        &[
            "materialize-runtime-event",
            "--result-family",
            "review",
            "--run-id",
            run_id,
            "--gate-id",
            "change-review",
            "--base-ref",
            "HEAD",
        ],
        Some(&sessions),
    );
    assert!(
        materialize.status.success(),
        "{}{}",
        String::from_utf8_lossy(&materialize.stdout),
        String::from_utf8_lossy(&materialize.stderr)
    );
    let output = String::from_utf8_lossy(&materialize.stdout);
    assert!(output.contains("RUNTIME_EVENT_OUTCOME=committed"));
    let unit = output
        .lines()
        .find_map(|line| line.strip_prefix("RUNTIME_EVENT_UNIT_ID="))
        .unwrap();
    let event = active.join(format!("runtime_event.{unit}.json"));
    let event_value: serde_json::Value = serde_json::from_slice(&fs::read(event).unwrap()).unwrap();
    assert_eq!(
        event_value["source_event"]["record_sha256"],
        certificate_value["rollout"]["task_complete"]["record_sha256"]
    );
    assert_eq!(event_value["gate"]["result"], "APPROVE");
    assert_eq!(
        event_value["publication_intent"]["prepared_state"],
        "prepared"
    );
}

#[test]
fn sync_publishes_to_the_selected_local_archive_branch_and_reads_back_clean_state() {
    let temporary = tempfile::tempdir().unwrap();
    let root = temporary.path();
    let source = root.join("source");
    let canon = root.join("agent-canon");
    let runtime = root.join("runtime");
    let archive = root.join("archive-clone");
    let remote = root.join("archive-remote.git");
    init_repo(&source);
    init_repo(&canon);
    fs::create_dir_all(&runtime).unwrap();
    git(
        &source,
        &[
            "remote",
            "add",
            "origin",
            "https://github.com/example/source.git",
        ],
    );
    Command::new("git")
        .args(["init", "-q", "--bare", remote.to_str().unwrap()])
        .status()
        .unwrap();
    let seed = root.join("archive-seed");
    init_repo(&seed);
    git(
        &seed,
        &["remote", "add", "origin", remote.to_str().unwrap()],
    );
    git(&seed, &["push", "-u", "origin", "main"]);

    let ensure = archive_command(
        &source,
        &canon,
        &archive,
        &runtime,
        remote.to_str().unwrap(),
        &["ensure"],
        None,
    );
    assert!(
        ensure.status.success(),
        "{}",
        String::from_utf8_lossy(&ensure.stdout)
    );
    assert!(String::from_utf8_lossy(&ensure.stdout).contains("RUNTIME_LOG_ARCHIVE_ENSURE=pass"));

    let sync = archive_command(
        &source,
        &canon,
        &archive,
        &runtime,
        remote.to_str().unwrap(),
        &["sync", "--no-agent-reports"],
        None,
    );
    assert!(
        sync.status.success(),
        "{}",
        String::from_utf8_lossy(&sync.stdout)
    );
    assert!(String::from_utf8_lossy(&sync.stdout).contains("RUNTIME_LOG_ARCHIVE_SYNC=pass"));
    assert!(
        String::from_utf8_lossy(&sync.stdout).contains("RUNTIME_LOG_ARCHIVE_PUSH_STATUS=committed")
    );

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let tools = root.join("tools");
        let calls = root.join("github-calls");
        fs::create_dir(&tools).unwrap();
        let gh = tools.join("gh");
        fs::write(
            &gh,
            r#"#!/bin/sh
set -eu
printf '%s\n' "$4" >> "$GH_CALLS"
case "$4" in
  repos/example/source) printf '{"id":42}\n';;
  repos/example/source/actions/workflows/agent-canon-static-gates.yml)
    printf '{"id":19,"path":".github/workflows/agent-canon-static-gates.yml"}\n';;
  repos/example/source/actions/artifacts\?*) printf '{"artifacts":[]}\n';;
  *) exit 2;;
esac
"#,
        )
        .unwrap();
        fs::set_permissions(&gh, fs::Permissions::from_mode(0o700)).unwrap();
        fs::create_dir_all(canon.join("bootstrap/host")).unwrap();
        fs::write(
            canon.join("bootstrap/host/manifest.toml"),
            include_bytes!("../../../../../bootstrap/host/manifest.toml"),
        )
        .unwrap();
        let result = Command::new(NATIVE)
            .args(["runtime-log-archive-git", "--source-root"])
            .arg(&source)
            .arg("--canon-root")
            .arg(&canon)
            .arg("--archive-root")
            .arg(&archive)
            .arg("--runtime-root")
            .arg(&runtime)
            .arg("--remote")
            .arg(&remote)
            .args(["sync", "--no-agent-reports", "--include-main-evals"])
            .env(
                "PATH",
                format!(
                    "{}:{}",
                    tools.display(),
                    std::env::var("PATH").unwrap_or_default()
                ),
            )
            .env("GH_CALLS", &calls)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}\n{}",
            String::from_utf8_lossy(&result.stdout),
            String::from_utf8_lossy(&result.stderr)
        );
        assert!(fs::read_to_string(calls)
            .unwrap()
            .lines()
            .any(|line| line
                == "repos/example/source/actions/workflows/agent-canon-static-gates.yml"));
    }

    let status = archive_command(
        &source,
        &canon,
        &archive,
        &runtime,
        remote.to_str().unwrap(),
        &["check-clean", "--porcelain"],
        None,
    );
    assert!(
        status.status.success(),
        "{}",
        String::from_utf8_lossy(&status.stdout)
    );
    assert!(
        String::from_utf8_lossy(&status.stdout).contains("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass")
    );
}
