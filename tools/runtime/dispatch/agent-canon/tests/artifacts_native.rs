//! Native artifact boundary and identity oracles over the production modules.
// @dependency-start
// contract test
// responsibility Checks runtime artifact authority, source replay identity, and external projection binding.
// upstream implementation ../src/lib.rs exports the shared production modules
// upstream implementation ../src/runtime_boundary.rs owns runtime root and spool capabilities
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical artifact identity
// upstream implementation ../src/artifacts/external_artifact_binding.rs owns external projection acknowledgements
// @dependency-end

use agent_canon::artifacts::artifact_identity::{
    canonical_json_bytes, git_blob_oid, materialize_artifact_identity, verify_identity_record,
};
use agent_canon::artifacts::external_artifact_binding::{
    materialize_external_projection_acknowledgement, verify_external_projection_acknowledgement,
    LOCAL_EVENT_SCHEMA,
};
use agent_canon::runtime_boundary::{
    root_capability_environment, RuntimeArtifactBoundary, RuntimeSpoolBoundary, RUNTIME_ROOT_ENV,
};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

struct TempTree(PathBuf);

impl TempTree {
    fn new(label: &str) -> Self {
        let path = std::env::temp_dir().join(format!(
            "agent-canon-artifacts-{label}-{}-{}",
            std::process::id(),
            NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).expect("create temporary fixture root");
        Self(fs::canonicalize(path).expect("resolve physical temporary fixture root"))
    }
}

impl Drop for TempTree {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn run(command: &mut Command) -> Output {
    command.output().expect("run fixture command")
}

fn git(root: &Path, args: &[&str]) -> Output {
    run(Command::new("git").arg("-C").arg(root).args(args))
}

fn init_repository(root: &Path) {
    fs::create_dir_all(root).expect("create repository");
    assert!(git(root, &["init", "-q"]).status.success());
    assert!(git(root, &["config", "user.name", "Artifact Test"])
        .status
        .success());
    assert!(
        git(root, &["config", "user.email", "artifact@example.invalid"])
            .status
            .success()
    );
    let owner = root.join("tools/runtime/artifacts/artifact_identity.py");
    fs::create_dir_all(owner.parent().unwrap()).expect("create artifact owner directory");
    fs::write(&owner, b"# committed fixture owner\n").expect("write owner fixture");
    fs::write(root.join("tracked.md"), b"committed bytes\n").expect("write tracked fixture");
    assert!(git(root, &["add", "."]).status.success());
    assert!(git(root, &["commit", "-qm", "fixture"]).status.success());
}

fn local_event() -> Value {
    json!({
        "schema": LOCAL_EVENT_SCHEMA,
        "aggregate_identity": "aggregate-1",
        "event_kind": "terminal_resume_dispatch_observed",
        "resume_event_id": "resume-event-1",
        "resume_event_body_sha256": "event-hash-1",
        "event_order_index": 1,
        "review_lineage_id": "lineage-1",
        "review_request_id": "request-1",
        "review_context_id": "context-1",
        "review_frame_id": null,
        "candidate_id": "candidate-1",
        "candidate_revision": 1,
        "candidate_body_sha256": "candidate-hash-1",
        "candidate_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "candidate_tree": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    })
}

fn codex_readback() -> Value {
    json!({
        "provider_kind": "codex_runtime",
        "provider_status": "running",
        "provider_instance_id": "reviewer-instance-1",
        "provider_object_id": "runtime-object-1",
        "provider_object_version": "1",
        "provider_object_kind": "review_dispatch",
        "provider_parent_object_id": "runtime-parent-1",
        "acknowledgement_order_index": 1
    })
}

#[test]
fn external_runtime_root_writes_atomically_and_rejects_source_escape() {
    let temp = TempTree::new("external");
    let source = temp.0.join("source");
    let runtime = temp.0.join("runtime");
    fs::create_dir_all(&source).expect("create source");
    fs::write(source.join("tracked.txt"), b"source bytes\n").expect("write source file");
    let source_before = fs::read(source.join("tracked.txt")).expect("read source file");
    let boundary = RuntimeArtifactBoundary::for_source(&source, Some(&runtime), true)
        .expect("open explicit external boundary");

    let target = boundary
        .atomic_write_text(Path::new("tasks/run/receipt.json"), "runtime\n", 0o600)
        .expect("publish external file");

    assert_eq!(target, runtime.join("tasks/run/receipt.json"));
    assert_eq!(
        fs::read(&target).expect("read published file"),
        b"runtime\n"
    );
    assert_eq!(fs::read(source.join("tracked.txt")).unwrap(), source_before);
    let mode_target = boundary
        .atomic_write_bytes(Path::new("tasks/run/mode.txt"), b"mode\n", 0o640)
        .expect("publish artifact with requested mode");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(mode_target)
                .expect("stat mode fixture")
                .permissions()
                .mode()
                & 0o777,
            0o640
        );
    }
    #[cfg(not(unix))]
    let _ = mode_target;
    assert_eq!(
        boundary
            .digest(Path::new("tasks/run/receipt.json"))
            .unwrap(),
        "fae9d8f386d67956867dedef7c89476199a4a25ee9ffe13560a6bfae7ae6c407"
    );
    assert!(boundary.resolve(Path::new("../outside/file")).is_err());
    assert!(RuntimeArtifactBoundary::for_source(&source, Some(&source), true).is_err());
    assert!(
        RuntimeArtifactBoundary::for_source(&source, Some(&source.join(".runtime")), true).is_err()
    );
    let manifest = boundary
        .atomic_write_json(
            Path::new("tasks/run/manifest.json"),
            &json!({ "z": 1, "a": true }),
            0o600,
        )
        .expect("write JSON artifact");
    assert_eq!(
        fs::read(manifest).expect("read JSON artifact"),
        b"{\n  \"a\": true,\n  \"z\": 1\n}\n"
    );
    boundary
        .append_bytes(Path::new("tasks/run/events.jsonl"), b"one\n", 0o600)
        .expect("append first receipt");
    boundary
        .append_bytes(Path::new("tasks/run/events.jsonl"), b"two\n", 0o600)
        .expect("append second receipt");
    assert_eq!(
        fs::read(runtime.join("tasks/run/events.jsonl")).unwrap(),
        b"one\ntwo\n"
    );
    assert!(fs::read_dir(runtime.join("tasks/run"))
        .expect("read artifact output directory")
        .all(|entry| !entry
            .expect("read artifact entry")
            .file_name()
            .to_string_lossy()
            .ends_with(".tmp")));
    #[cfg(unix)]
    {
        let outside = temp.0.join("outside");
        fs::create_dir_all(&outside).expect("create outside directory");
        std::os::unix::fs::symlink(&outside, runtime.join("link"))
            .expect("create external runtime symlink");
        assert!(boundary
            .atomic_write_text(Path::new("link/escape.json"), "must-fail\n", 0o600)
            .is_err());
        assert!(!outside.join("escape.json").exists());
    }
}

#[test]
fn explicit_tilde_runtime_root_resolves_to_current_home_without_writing_there() {
    let temp = TempTree::new("tilde-root");
    let source = temp.0.join("source");
    fs::create_dir_all(&source).expect("create source fixture");
    #[cfg(windows)]
    let home = std::env::var_os("USERPROFILE")
        .or_else(|| {
            let mut drive = std::env::var_os("HOMEDRIVE").unwrap_or_default();
            drive.push(std::env::var_os("HOMEPATH")?);
            Some(drive)
        })
        .expect("current home root");
    #[cfg(not(windows))]
    let home = std::env::var_os("HOME").expect("current home root");
    let expected = fs::canonicalize(PathBuf::from(home)).expect("canonicalize current home");

    let boundary = RuntimeArtifactBoundary::for_source(&source, Some(Path::new("~")), false)
        .expect("resolve explicit current-home runtime root");

    assert_eq!(boundary.root(), expected.as_path());
}

#[test]
fn spool_boundary_admits_only_locks_and_spool_for_exact_source_runtime() {
    let temp = TempTree::new("spool");
    let source = temp.0.join("source");
    fs::create_dir_all(&source).expect("create source");
    let root = source.join(".runtime");
    let spool = RuntimeSpoolBoundary::for_source(&source, Some(&root), true)
        .expect("open exact source spool boundary");

    assert_eq!(spool.boundary().root(), root);
    assert_eq!(
        spool.boundary().resolve(Path::new("spool/events")),
        Ok(root.join("spool/events"))
    );
    assert_eq!(
        spool.boundary().resolve(Path::new("locks/archive.lock")),
        Ok(root.join("locks/archive.lock"))
    );
    assert!(spool
        .boundary()
        .resolve(Path::new("archive/report.json"))
        .is_err());
    assert!(spool
        .boundary()
        .resolve(Path::new("tasks/request.json"))
        .is_err());
    assert!(
        RuntimeSpoolBoundary::for_source(&source, Some(&source.join("nested/.runtime")), true)
            .is_err()
    );
    #[cfg(unix)]
    {
        let outside = temp.0.join("outside");
        fs::create_dir_all(&outside).expect("create outside directory");
        fs::create_dir_all(root.join("spool")).expect("create spool directory");
        std::os::unix::fs::symlink(&outside, root.join("spool/escape"))
            .expect("create runtime symlink");
        assert!(spool
            .boundary()
            .resolve(Path::new("spool/escape/receipt.json"))
            .is_err());
    }
}

#[test]
fn source_runtime_alias_and_external_spool_paths_are_rejected_or_restricted() {
    let temp = TempTree::new("spool-roots");
    let source = temp.0.join("source");
    let outside = temp.0.join("outside");
    let external_runtime = temp.0.join("external-runtime");
    fs::create_dir_all(&source).expect("create source");
    fs::create_dir_all(&outside).expect("create outside directory");
    let _external = RuntimeSpoolBoundary::for_source(&source, Some(&external_runtime), true)
        .expect("open external spool boundary");
    let external = _external.boundary();
    assert!(external.resolve(Path::new("spool/events")).is_ok());
    for path in [
        "archive/report.json",
        "reports/agents/run/report.md",
        "tasks/request.json",
    ] {
        assert!(external.resolve(Path::new(path)).is_err());
    }
    #[cfg(unix)]
    {
        let source_runtime_link = source.join(".runtime");
        std::os::unix::fs::symlink(&outside, &source_runtime_link)
            .expect("create source runtime alias");
        assert!(
            RuntimeSpoolBoundary::for_source(&source, Some(&source_runtime_link), true).is_err()
        );
    }
}

#[test]
fn child_environment_filters_secrets_and_carries_only_root_identity_metadata() {
    let temp = TempTree::new("environment");
    let runtime = temp.0.join("runtime");
    fs::create_dir_all(&runtime).expect("create environment root");
    let base = BTreeMap::from([
        ("PATH".to_string(), "/usr/bin".to_string()),
        ("LANG".to_string(), "C.UTF-8".to_string()),
        ("LC_NUMERIC".to_string(), "C".to_string()),
        (
            "CARGO_TARGET_DIR".to_string(),
            "/tmp/agent-canon-target".to_string(),
        ),
        ("OPENAI_API_KEY".to_string(), "fixture-secret".to_string()),
        (
            "HTTPS_PROXY".to_string(),
            "https://user:pass@example.invalid".to_string(),
        ),
        ("GITHUB_TOKEN".to_string(), "fixture-token".to_string()),
    ]);
    let child =
        root_capability_environment(Path::new("~"), &runtime, Some(&base), Some(Path::new("~/")))
            .expect("build filtered child environment from current-home paths");

    assert_eq!(child.get("PATH").map(String::as_str), Some("/usr/bin"));
    assert_eq!(child.get("LANG").map(String::as_str), Some("C.UTF-8"));
    assert_eq!(child.get("LC_NUMERIC").map(String::as_str), Some("C"));
    assert_eq!(
        child.get("CARGO_TARGET_DIR").map(String::as_str),
        Some("/tmp/agent-canon-target")
    );
    assert_eq!(
        child.get(RUNTIME_ROOT_ENV).map(String::as_str),
        Some(runtime.to_str().unwrap())
    );
    assert!(!child.contains_key("OPENAI_API_KEY"));
    assert!(!child.contains_key("HTTPS_PROXY"));
    assert!(!child.contains_key("GITHUB_TOKEN"));
    let parent: Value = serde_json::from_str(&child["AGENT_CANON_PARENT_ROOT_CAPABILITY"])
        .expect("parse parent root identity metadata");
    assert_eq!(parent["kind"], "parent-root");
    let root = parent["root"].as_str().expect("canonical home root string");
    assert_eq!(child["AGENT_CANON_PARENT_ROOT"].as_str(), root);
    assert_eq!(child["AGENT_CANON_TARGET_ROOT"].as_str(), root);
    assert!(Path::new(root).is_absolute());
    assert!(parent["dev"].as_str().is_some());
    assert!(parent["ino"].as_str().is_some());
}

#[test]
fn artifact_identity_replays_head_bytes_and_reads_untracked_files_safely() {
    let temp = TempTree::new("identity");
    let repo = temp.0.join("repo");
    init_repository(&repo);
    let original = b"committed bytes\n";
    fs::write(
        repo.join("tracked.md"),
        b"working-tree replacement is ignored\n",
    )
    .expect("modify tracked file");
    let record = materialize_artifact_identity(&repo, Path::new("tracked.md"))
        .expect("materialize tracked identity");
    assert_eq!(record["source_binding"]["kind"], "git_commit_path");
    assert_eq!(record["sha256"], hex_sha256(original));
    assert_eq!(record["git_blob"], git_blob_oid(original));
    let verified = verify_identity_record(&repo, &record).expect("verify tracked identity");
    assert_eq!(verified["identity_record_id"], record["identity_record_id"]);

    let untracked = repo.join("reports/untracked.json");
    fs::create_dir_all(untracked.parent().unwrap()).expect("create untracked parent");
    fs::write(&untracked, b"{\"ok\":true}\n").expect("write untracked artifact");
    let untracked_record =
        materialize_artifact_identity(&repo, &untracked).expect("materialize filesystem identity");
    assert_eq!(
        untracked_record["source_binding"]["kind"],
        "filesystem_immutable"
    );
    assert!(verify_identity_record(&repo, &untracked_record).is_ok());
    #[cfg(unix)]
    {
        let outside_file = temp.0.join("outside.txt");
        fs::write(&outside_file, b"outside bytes").expect("write outside fixture");
        std::os::unix::fs::symlink(&outside_file, repo.join("outside-link"))
            .expect("create external source link");
        std::os::unix::fs::symlink(temp.0.join("missing-outside"), repo.join("dangling-link"))
            .expect("create dangling external source link");
        for link in ["outside-link", "dangling-link"] {
            assert_eq!(
                materialize_artifact_identity(&repo, Path::new(link))
                    .unwrap_err()
                    .code,
                "artifact_identity:path_outside_repository"
            );
        }
    }

    let git_output = Command::new("git")
        .arg("-C")
        .arg(&repo)
        .args(["hash-object", "--stdin"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start independent Git blob oracle");
    let mut child = git_output;
    child
        .stdin
        .take()
        .unwrap()
        .write_all(original)
        .expect("write Git blob bytes");
    let git_output = child.wait_with_output().expect("wait for Git blob oracle");
    assert!(git_output.status.success());
    assert_eq!(
        String::from_utf8(git_output.stdout).unwrap().trim(),
        git_blob_oid(original)
    );
}

#[test]
fn canonical_json_rejects_floats_and_external_ack_binds_local_event() {
    assert_eq!(
        canonical_json_bytes(&json!({ "value": 1.5 }))
            .unwrap_err()
            .code,
        "artifact_identity:float_forbidden"
    );
    let event = local_event();
    let acknowledgement =
        materialize_external_projection_acknowledgement(&event, &codex_readback())
            .expect("materialize Codex acknowledgement");
    let verified = verify_external_projection_acknowledgement(&event, &acknowledgement)
        .expect("verify Codex acknowledgement");
    assert_eq!(verified["provider_status"], "running");
    assert!(acknowledgement
        .get("provider_receipt_bytes_sha256")
        .is_none());

    let mut forbidden = codex_readback();
    forbidden["nested"] = json!({ "dispatch_receipt_sha256": "forbidden" });
    let error = materialize_external_projection_acknowledgement(&event, &forbidden)
        .expect_err("reject receipt byte identity");
    assert_eq!(
        error.code,
        "external_projection:receipt_byte_identity_forbidden"
    );
}

#[test]
fn github_head_projection_replays_candidate_and_status_rules() {
    let mut event = local_event();
    event["event_kind"] = json!("candidate_materialized");
    let provider = json!({
        "provider_kind": "github",
        "provider_status": "pending",
        "provider_repository_id": "repository-1",
        "provider_object_id": "pull-1",
        "provider_object_version": "etag-1",
        "provider_object_kind": "pull_request",
        "head_ref": "feat/candidate",
        "head_oid": event["candidate_commit"],
        "head_tree": event["candidate_tree"],
        "acknowledgement_order_index": 2
    });
    let acknowledgement = materialize_external_projection_acknowledgement(&event, &provider)
        .expect("materialize GitHub head projection");
    assert_eq!(acknowledgement["projection_kind"], "github_pr_head");
    assert!(verify_external_projection_acknowledgement(&event, &acknowledgement).is_ok());

    let mut bad_head = provider.clone();
    bad_head["head_oid"] = json!("c".repeat(40));
    assert_eq!(
        materialize_external_projection_acknowledgement(&event, &bad_head)
            .unwrap_err()
            .code,
        "external_projection:head_mismatch"
    );
    let mut bad_status = provider;
    bad_status["provider_status"] = json!("unknown");
    assert_eq!(
        materialize_external_projection_acknowledgement(&event, &bad_status)
            .unwrap_err()
            .code,
        "external_projection:provider_status_invalid"
    );
}

fn hex_sha256(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
