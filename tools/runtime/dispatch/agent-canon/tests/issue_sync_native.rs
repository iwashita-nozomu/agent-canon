// @dependency-start
// contract test
// responsibility Verifies Issue readback projection and body-free runtime staging through the public native CLI.
// upstream implementation ../src/issue_sync.rs owns Issue and receipt behavior
// @dependency-end

use serde_json::{json, Value};
use std::fs;
use std::path::Path;
use std::process::{Command, Output};

fn run(root: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .arg("issue-sync")
        .args(args)
        .current_dir(root)
        .output()
        .unwrap()
}
fn fixture() -> tempfile::TempDir {
    let temporary = tempfile::tempdir().unwrap();
    let root = temporary.path();
    assert!(Command::new("git")
        .args(["init", "-q", "-b", "main"])
        .arg(root)
        .status()
        .unwrap()
        .success());
    for (key, value) in [
        ("user.name", "Issue Test"),
        ("user.email", "issue@example.invalid"),
    ] {
        assert!(Command::new("git")
            .arg("-C")
            .arg(root)
            .args(["config", key, value])
            .status()
            .unwrap()
            .success());
    }
    assert!(Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["commit", "--allow-empty", "-qm", "fixture"])
        .status()
        .unwrap()
        .success());
    temporary
}

#[test]
fn staging_keeps_body_free_stable_identity_and_noop_time() {
    let temporary = fixture();
    let root = temporary.path().canonicalize().unwrap();
    let runtime = tempfile::tempdir().unwrap();
    let runtime = runtime.path().canonicalize().unwrap();
    let mut args = vec![
        "--repo",
        "owner/repo",
        "--runtime-root",
        runtime.to_str().unwrap(),
        "--stage-publication-receipt",
        "--receipt-number",
        "45",
        "--receipt-url",
        "https://github.com/owner/repo/issues/45",
        "--receipt-state",
        "OPEN",
        "--receipt-action",
        "create",
        "--receipt-timestamp",
        "2026-08-27T00:00:00Z",
    ];
    let result = run(&root, &args);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let reply: Value = serde_json::from_slice(&result.stdout).unwrap();
    let receipt = std::path::PathBuf::from(reply["receipt"].as_str().unwrap());
    let payload: Value = serde_json::from_slice(&fs::read(&receipt).unwrap()).unwrap();
    assert_eq!(payload["state"], "open");
    assert_eq!(payload["repository"], "owner/repo");
    assert_eq!(payload["timestamp"], "2026-08-27T00:00:00Z");
    assert!(payload.get("body").is_none());
    let action = args
        .iter()
        .position(|value| *value == "--receipt-action")
        .unwrap()
        + 1;
    args[action] = "noop";
    let timestamp = args
        .iter()
        .position(|value| *value == "--receipt-timestamp")
        .unwrap()
        + 1;
    args[timestamp] = "2026-08-28T00:00:00Z";
    let result = run(&root, &args);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let after: Value = serde_json::from_slice(&fs::read(&receipt).unwrap()).unwrap();
    assert_eq!(after["action"], "noop");
    assert!(root
        .read_dir()
        .unwrap()
        .all(|entry| entry.unwrap().file_name() != "feedback"));
}

#[test]
fn invalid_receipt_identity_is_rejected_without_publication() {
    let temporary = fixture();
    let root = temporary.path().canonicalize().unwrap();
    let runtime = tempfile::tempdir().unwrap();
    let runtime = runtime.path().canonicalize().unwrap();
    let result = run(
        &root,
        &[
            "--repo",
            "owner/repo",
            "--runtime-root",
            runtime.to_str().unwrap(),
            "--stage-publication-receipt",
            "--receipt-number",
            "45",
            "--receipt-url",
            "https://github.com/other/repo/issues/45",
            "--receipt-state",
            "open",
            "--receipt-action",
            "create",
        ],
    );
    assert_eq!(result.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&result.stderr).contains("issue_receipt_identity_mismatch"));
    assert!(!runtime.join("spool/private-feedback/feedback").exists());
}

#[cfg(unix)]
#[test]
fn runtime_symlink_output_preserves_referent() {
    use std::os::unix::fs::symlink;
    let temporary = fixture();
    let root = temporary.path().canonicalize().unwrap();
    let runtime = tempfile::tempdir().unwrap();
    let runtime = runtime.path().canonicalize().unwrap();
    let published =
        runtime.join("spool/private-feedback/feedback/issue-packets/published/owner/repo");
    fs::create_dir_all(&published).unwrap();
    let outside = runtime.join("outside.json");
    fs::write(&outside, "preserve").unwrap();
    symlink(&outside, published.join("45.json")).unwrap();
    let result = run(
        &root,
        &[
            "--repo",
            "owner/repo",
            "--runtime-root",
            runtime.to_str().unwrap(),
            "--stage-publication-receipt",
            "--receipt-number",
            "45",
            "--receipt-url",
            "https://github.com/owner/repo/issues/45",
            "--receipt-state",
            "open",
            "--receipt-action",
            "create",
        ],
    );
    assert_eq!(result.status.code(), Some(2));
    assert_eq!(fs::read_to_string(outside).unwrap(), "preserve");
}

#[test]
fn pending_packet_is_metadata_only_with_existing_name_grammar() {
    let temporary = fixture();
    let root = temporary.path().canonicalize().unwrap();
    let log = tempfile::tempdir().unwrap();
    let log = log.path().canonicalize().unwrap();
    let body = log.join("private-body.md");
    fs::write(&body, "private body must stay private\n").unwrap();
    let result = run(
        &root,
        &[
            "--repo",
            "owner/repo",
            "--offline-title",
            "Private finding",
            "--body-locator",
            body.to_str().unwrap(),
            "--body-digest",
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--log-root",
            log.to_str().unwrap(),
            "--run",
            "run-1",
            "--task",
            "task-1",
        ],
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let reply: Value = serde_json::from_slice(&result.stdout).unwrap();
    let path = std::path::PathBuf::from(reply["packet"].as_str().unwrap());
    assert_eq!(
        path.file_name().unwrap(),
        "private-finding-aaaaaaaaaaaaaaaa.json"
    );
    let raw = fs::read_to_string(&path).unwrap();
    assert!(!raw.contains("private body must"));
    let payload: Value = serde_json::from_str(&raw).unwrap();
    assert_eq!(payload["body_locator"], json!(body));
    assert_eq!(payload["run"], "run-1");
}

#[test]
fn candidate_qualification_preserves_authority_and_transient_finding_boundaries() {
    use agent_canon::issue_sync::qualify_finding;
    let base = json!({"repository":"owner/repo","owner":"issue-owner","fix":"repair route","actionable":true,"occurrence_locations":[{"path":"tools/route.py","locator":"route"}],"decision":"same owner"});
    let qualified = qualify_finding(&base, "owner/repo");
    assert_eq!(qualified["status"], "qualified");
    assert_eq!(
        qualified["occurrence_locations"],
        json!(["tools/route.py::route"])
    );
    assert_eq!(
        qualified["responsibility"],
        json!(["issue-owner", "same owner"])
    );
    for (field, value, status, reason) in [
        ("actionable", json!(false), "no-action", "not-actionable"),
        (
            "finding_kind",
            json!("raw_count"),
            "no-action",
            "non-durable-finding-kind",
        ),
        (
            "closed_by_active_repair",
            json!(true),
            "no-action",
            "current-scope-resolved",
        ),
        (
            "repository",
            json!("other/repo"),
            "handoff",
            "other-repository",
        ),
        ("owner", json!(""), "handoff", "owner-unresolved"),
        ("fix", json!(""), "handoff", "fix-unresolved"),
        (
            "durable_follow_up",
            json!(false),
            "no-action",
            "durable-follow-up-not-established",
        ),
    ] {
        let mut candidate = base.clone();
        candidate[field] = value;
        let result = qualify_finding(&candidate, "owner/repo");
        assert_eq!(result["status"], status);
        assert_eq!(result["reason"], reason);
    }
    assert_eq!(
        qualify_finding(&base, "")["reason"],
        "checkout-identity-unresolved"
    );
}

#[test]
fn cli_preserves_unique_prefix_equals_and_rejects_flag_values() {
    let root = fixture();
    let log = tempfile::tempdir().unwrap();
    let output = run(
        root.path(),
        &[
            "--repo=owner/repo",
            "--offline-t=Alias finding",
            "--body-locator=/private/body.md",
            "--body-digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--log-root",
            log.path().to_str().unwrap(),
        ],
    );
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["title"], "Alias finding");
    assert_eq!(
        run(root.path(), &["--receipt-preflight=yes"]).status.code(),
        Some(2)
    );
    assert_eq!(run(root.path(), &["--receipt"]).status.code(), Some(2));
}

#[cfg(unix)]
#[test]
fn failed_resident_preflight_preserves_packet_before_any_github_operation() {
    use std::os::unix::fs::PermissionsExt;
    let root = fixture();
    assert!(Command::new("git")
        .arg("-C")
        .arg(root.path())
        .args([
            "remote",
            "add",
            "origin",
            "https://github.com/owner/repo.git"
        ])
        .status()
        .unwrap()
        .success());
    let private = tempfile::tempdir().unwrap();
    let body = private.path().join("body.md");
    fs::write(&body, b"Issue body\n").unwrap();
    let log = private.path().join("log");
    let pending = log.join("feedback/issue-packets/pending/input.json");
    fs::create_dir_all(pending.parent().unwrap()).unwrap();
    use sha2::{Digest, Sha256};
    fs::write(
        &pending,
        serde_json::to_vec(&json!({
            "schema":"agent-canon.feedback.issue-packet.v1","status":"pending",
            "repository":"owner/repo","title":"Finding","body_locator":body,
            "body_digest":format!("sha256:{:x}",Sha256::digest(b"Issue body\n")),
            "route":"issue-publication","input_mode":"issue-publication-initial"
        }))
        .unwrap(),
    )
    .unwrap();
    let trace = private.path().join("commands");
    let bootstrap = private.path().join("bootstrap.sh");
    fs::write(
        &bootstrap,
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$TRACE\"\nexit 9\n",
    )
    .unwrap();
    fs::set_permissions(&bootstrap, fs::Permissions::from_mode(0o700)).unwrap();
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .unwrap();
    let result = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(["issue-sync", "--sync-pending", "--log-root"])
        .arg(&log)
        .arg("--runtime-root")
        .arg(private.path().join("runtime"))
        .current_dir(root.path())
        .env("AGENT_CANON_SOURCE_ROOT", source)
        .env_remove("AGENT_CANON_ROOT")
        .env("AGENT_CANON_BOOTSTRAP", &bootstrap)
        .env("TRACE", &trace)
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&result.stderr).contains("issue_receipt_route_unavailable"));
    assert!(pending.is_file());
    let args = fs::read_to_string(trace).unwrap();
    assert!(args.contains("tool\nrun\n--root\n"));
    assert!(args.contains("issue-sync\n--\n--receipt-preflight\n"));
    assert!(args.contains("--checkout-repository\nowner/repo\n"));
}

#[cfg(unix)]
#[test]
fn github_read_projects_clauses_and_saves_the_same_summary() {
    use std::os::unix::fs::PermissionsExt;
    let root = fixture();
    let tools = tempfile::tempdir().unwrap();
    let gh = tools.path().join("gh");
    fs::write(&gh,"#!/bin/sh\nprintf '%s\\n' '{\"number\":882,\"title\":\"Issue authority\",\"body\":\"## Problem\\nEvidence: run-1.\\n\\n## Done\\nAdvisory cleanup.\",\"state\":\"OPEN\",\"url\":\"https://github.com/owner/repo/issues/882\"}'\n").unwrap();
    fs::set_permissions(&gh, fs::Permissions::from_mode(0o700)).unwrap();
    let summary = tools.path().join("nested/summary.json");
    let result = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "issue-sync",
            "--repo=owner/repo",
            "--issue-url=882",
            "--github-check",
            "--summary-file",
        ])
        .arg(&summary)
        .env("PATH", tools.path())
        .current_dir(root.path())
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(fs::read(&summary).unwrap(), result.stdout);
    let report: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(report["github_checked"], 1);
    assert_eq!(report["issues"][0]["state"], "open");
    assert_eq!(report["issues"][0]["clauses"][0]["state"], "grounded");
    assert_eq!(report["issues"][0]["clauses"][2]["state"], "advisory");
    assert_eq!(
        report["issues"][0]["clauses"][0]["repository"],
        "owner/repo"
    );
}

#[cfg(unix)]
#[test]
fn retry_uses_exact_readback_and_keeps_packet_when_receipt_staging_fails() {
    use sha2::{Digest, Sha256};
    use std::os::unix::fs::PermissionsExt;
    let root = fixture();
    assert!(Command::new("git")
        .arg("-C")
        .arg(root.path())
        .args(["remote", "add", "origin", "git@github.com:owner/repo.git"])
        .status()
        .unwrap()
        .success());
    let private = tempfile::tempdir().unwrap();
    let log = private.path().join("log");
    let pending = log.join("feedback/issue-packets/pending/input.json");
    fs::create_dir_all(pending.parent().unwrap()).unwrap();
    let body = private.path().join("body.md");
    fs::write(&body, b"Issue body\n").unwrap();
    let packet = json!({"schema":"agent-canon.feedback.issue-packet.v1","status":"pending",
        "repository":"owner/repo","title":"Finding","body_locator":body,
        "body_digest":format!("sha256:{:x}",Sha256::digest(b"Issue body\n")),
        "route":"issue-publication","input_mode":"structured-log"});
    fs::write(&pending, serde_json::to_vec(&packet).unwrap()).unwrap();
    let record = private.path().join("record.json");
    fs::write(
        &record,
        serde_json::to_vec(&json!({"number":42,"title":"Finding","body":"Issue body\n",
        "state":"OPEN","url":"https://github.com/owner/repo/issues/42"}))
        .unwrap(),
    )
    .unwrap();
    let gh = private.path().join("gh");
    fs::write(&gh,"#!/bin/sh\nprintf '%s ' \"$@\" >> \"$TRACE\"\nprintf '\\n' >> \"$TRACE\"\ncase \"$2\" in list) printf '[{\"number\":42}]\\n';; view) /bin/cat \"$RECORD\";; *) exit 77;; esac\n").unwrap();
    let bootstrap = private.path().join("bootstrap.sh");
    fs::write(&bootstrap,"#!/bin/sh\nprintf '%s ' \"$@\" >> \"$TRACE\"\nprintf '\\n' >> \"$TRACE\"\ncase \" $* \" in *' --stage-publication-receipt '*) exit \"$STAGE_EXIT\";; *) exit 0;; esac\n").unwrap();
    for script in [&gh, &bootstrap] {
        fs::set_permissions(script, fs::Permissions::from_mode(0o700)).unwrap();
    }
    let trace = private.path().join("trace");
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .unwrap();
    let path = std::env::join_paths(std::iter::once(private.path().to_path_buf()).chain(
        std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()),
    ))
    .unwrap();
    let invoke = |stage_exit: &str| {
        Command::new(env!("CARGO_BIN_EXE_agent-canon"))
            .args(["issue-sync", "--sync-pending", "--log-root"])
            .arg(&log)
            .arg("--runtime-root")
            .arg(private.path().join("runtime"))
            .current_dir(root.path())
            .env("PATH", &path)
            .env("TRACE", &trace)
            .env("RECORD", &record)
            .env("STAGE_EXIT", stage_exit)
            .env("AGENT_CANON_BOOTSTRAP", &bootstrap)
            .env("AGENT_CANON_SOURCE_ROOT", source)
            .env_remove("AGENT_CANON_ROOT")
            .output()
            .unwrap()
    };
    let failed = invoke("8");
    assert_eq!(
        failed.status.code(),
        Some(2),
        "{}",
        String::from_utf8_lossy(&failed.stderr)
    );
    assert!(String::from_utf8_lossy(&failed.stderr).contains("issue_receipt_write_failed"));
    assert!(pending.is_file());
    let succeeded = invoke("0");
    assert!(
        succeeded.status.success(),
        "{}",
        String::from_utf8_lossy(&succeeded.stderr)
    );
    assert!(!pending.exists());
    let trace = fs::read_to_string(trace).unwrap();
    assert!(!trace.contains("issue create"));
    assert!(trace.contains("--receipt-action noop"));
    assert!(!trace.contains("Issue body"));
}
