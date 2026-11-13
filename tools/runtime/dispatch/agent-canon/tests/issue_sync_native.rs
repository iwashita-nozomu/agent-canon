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
