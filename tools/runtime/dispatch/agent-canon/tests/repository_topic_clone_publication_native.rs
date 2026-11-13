// @dependency-start
// contract test
// responsibility Exercises native cleanup admission with valid publication receipts and independent Git/filesystem readback.
// upstream implementation ../src/repository_topic_clone.rs owns cleanup and publication admission
// upstream implementation ../src/update_lifecycle_contract.rs materializes publication readback receipts
// @dependency-end

use agent_canon::repository_topic_clone::{prepare, CheckoutMode, RepositoryTopicCloneRequest};
use agent_canon::update_lifecycle_contract::{
    materialize_publication_readback_receipt, pull_request_branch_table,
};
use serde_json::{json, Value};
use std::fs;
use std::path::Path;
use std::process::{Command, Output};

fn git(root: &Path, args: &[&str]) -> Output {
    Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .expect("run fixture Git command")
}

fn git_ok(root: &Path, args: &[&str]) -> Output {
    let output = git(root, args);
    assert!(
        output.status.success(),
        "git {args:?} failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    output
}

fn git_stdout(root: &Path, args: &[&str]) -> String {
    String::from_utf8(git_ok(root, args).stdout)
        .expect("Git output is UTF-8")
        .trim()
        .to_owned()
}

fn init_repository(root: &Path, branch: &str) {
    fs::create_dir_all(root).expect("create fixture repository");
    let output = Command::new("git")
        .args(["init", "-q", "--initial-branch", branch])
        .arg(root)
        .output()
        .expect("initialize fixture repository");
    assert!(
        output.status.success(),
        "git init failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    git_ok(root, &["config", "user.name", "AgentCanon test"]);
    git_ok(root, &["config", "user.email", "test@example.invalid"]);
}

fn commit_all(root: &Path, message: &str) {
    git_ok(root, &["add", "-A"]);
    git_ok(root, &["commit", "-m", message]);
}

fn publication_receipts(
    candidate_sha: &str,
    candidate_tree: &str,
    base_sha: &str,
    base_tree: &str,
    branch: &str,
    repository: &str,
) -> (Value, Value, Value) {
    let binding = json!({
        "transaction_id": format!("tx:{}", "1".repeat(64)),
        "snapshot_id": format!("snapshot:{}", "2".repeat(64)),
        "candidate_sha": candidate_sha,
        "tree_sha": candidate_tree,
        "input_digest": format!("sha256:{}", "5".repeat(64)),
        "tool_id": "publication-integrator",
        "tool_version": "test.v1",
        "evidence_ref": format!("evidence:{}", "6".repeat(64)),
        "evidence_digest": format!("sha256:{}", "7".repeat(64)),
        "timing": {
            "started_at": "2026-07-18T00:00:00Z",
            "finished_at": "2026-07-18T00:00:00Z",
            "last_attempt_at": "2026-07-18T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": false,
        }
    });
    let mut cas_binding = binding.clone();
    cas_binding["evidence_ref"] = json!(format!("evidence:{}", "8".repeat(64)));
    cas_binding["evidence_digest"] = json!(format!("sha256:{}", "8".repeat(64)));
    let cas = json!({
        "schema": "agent-canon.candidate-cas-receipt.v1",
        "cas_receipt_id": format!("cas:{}", "9".repeat(64)),
        "binding": cas_binding,
        "predecessor_evidence_id": binding["evidence_ref"],
        "rebind_receipt_evidence_id": format!("rebind:{}", "a".repeat(64)),
        "candidate_identity": {
            "candidate_sha": candidate_sha,
            "tree_sha": candidate_tree,
        },
        "cas_base_identity": {"commit_sha": base_sha, "tree_sha": base_tree},
        "cas_evidence_ref": format!("evidence:{}", "8".repeat(64)),
        "cas_stage": "cas",
    });
    let mut lifecycle_binding = cas["binding"].clone();
    lifecycle_binding["evidence_ref"] = json!(format!("evidence:{}", "b".repeat(64)));
    lifecycle_binding["evidence_digest"] = json!(format!("sha256:{}", "b".repeat(64)));
    let branch_ref = format!("refs/heads/{branch}");
    let lifecycle = json!({
        "schema": "agent-canon.pull-request-lifecycle.v1",
        "kind": "user",
        "binding": lifecycle_binding,
        "state": "merged",
        "remote_identity": {
            "repo_owner": "owner",
            "repo_name": repository,
            "remote_name": "origin",
            "url_digest": format!("sha256:{}", "c".repeat(64)),
            "ref": branch_ref,
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree,
        },
        "base_identity": {
            "repo_owner": "owner",
            "repo_name": repository,
            "ref": "refs/heads/main",
            "commit_sha": base_sha,
            "tree_sha": base_tree,
        },
        "head_identity": {
            "repo_owner": "owner",
            "repo_name": repository,
            "ref": branch_ref,
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree,
        },
        "branch": pull_request_branch_table(),
        "permission_identity": {
            "actor_id": "github-user:7",
            "permission_state": "verified_true",
            "permission_evidence_id": format!("evidence:{}", "d".repeat(64)),
            "authority_source": "fixture GitHub readback",
            "assumption_forbidden": true,
        },
        "pr_essence": {
            "problem": "topic source change",
            "intent": "publish exact topic head",
            "canonical_owner": "repository-topic-clone",
            "contract_delta": "generic lifecycle fixture",
            "evidence_refs": [format!("evidence:{}", "e".repeat(64))],
        },
        "reviews": [],
        "user_identity": {
            "actor_id": "github-user:7",
            "display_name": "Lifecycle Test",
        },
    });
    let authoritative_readback = json!({
        "number": 7,
        "state": "MERGED",
        "baseRefName": "main",
        "baseRefOid": "1".repeat(40),
        "mergeCasBaseOid": base_sha,
        "mergeCasBaseTreeOid": base_tree,
        "headRefName": branch,
        "headRefOid": candidate_sha,
        "headRepository": {"nameWithOwner": format!("owner/{repository}")},
        "mergeCommit": {"oid": "1".repeat(40)},
        "mergeTreeOid": "2".repeat(40),
    });
    let readback = materialize_publication_readback_receipt(&cas, &lifecycle, &authoritative_readback)
        .expect("native lifecycle owner materializes valid publication readback");
    (cas, lifecycle, readback)
}

#[test]
fn native_cleanup_cli_accepts_merged_receipts_and_preserves_sibling_content() {
    let temporary = tempfile::tempdir().expect("temporary root");
    let remote = temporary.path().join("repo.git");
    let source = temporary.path().join("source");
    let parent = temporary.path().join("parent");
    let branch = "feature/cleanup";
    let repository = "repo-three";
    let topic = "topic-cleanup";

    let output = Command::new("git")
        .args(["init", "-q", "--bare"])
        .arg(&remote)
        .output()
        .expect("create bare remote");
    assert!(output.status.success(), "bare init failed");
    init_repository(&source, "main");
    fs::write(source.join("base.txt"), "base\n").unwrap();
    commit_all(&source, "initial");
    git_ok(&source, &["remote", "add", "origin", remote.to_str().unwrap()]);
    git_ok(&source, &["push", "origin", "main"]);
    git_ok(&remote, &["symbolic-ref", "HEAD", "refs/heads/main"]);

    init_repository(&parent, "main");
    fs::write(parent.join(".gitignore"), "workspace/\n").unwrap();
    fs::write(parent.join("parent.txt"), "parent\n").unwrap();
    commit_all(&parent, "parent");
    let request = RepositoryTopicCloneRequest {
        url: remote.to_string_lossy().into_owned(),
        repository: repository.to_owned(),
        workspace_root: parent.clone(),
        topic: topic.to_owned(),
        branch: branch.to_owned(),
        checkout_mode: CheckoutMode::IndependentClone,
    };
    let prepared = prepare(&request).expect("prepare independent clone fixture");
    git_ok(&prepared.clone, &["config", "user.name", "AgentCanon test"]);
    git_ok(&prepared.clone, &["config", "user.email", "test@example.invalid"]);
    fs::write(prepared.clone.join("topic.txt"), "topic\n").unwrap();
    git_ok(&prepared.clone, &["add", "topic.txt"]);
    git_ok(&prepared.clone, &["commit", "-m", "topic change"]);
    git_ok(&prepared.clone, &["push", "-u", "origin", branch]);
    let candidate_sha = git_stdout(&prepared.clone, &["rev-parse", "HEAD"]);
    let candidate_tree = git_stdout(&prepared.clone, &["rev-parse", "HEAD^{tree}"]);
    let base_sha = git_stdout(&prepared.clone, &["rev-parse", "origin/main"]);
    let base_tree = git_stdout(&prepared.clone, &["rev-parse", "origin/main^{tree}"]);

    let topic_root = parent.join("workspace").join(topic);
    let sibling = topic_root.join("keep.txt");
    fs::write(&sibling, "keep\n").unwrap();
    fs::write(parent.join(".gitignore"), "# drift\n").unwrap();
    let ignore_after_drift = fs::read(parent.join(".gitignore")).unwrap();

    let (cas, lifecycle, readback) = publication_receipts(
        &candidate_sha,
        &candidate_tree,
        &base_sha,
        &base_tree,
        branch,
        repository,
    );
    let cas_path = temporary.path().join("candidate-cas.json");
    let lifecycle_path = temporary.path().join("pr-lifecycle.json");
    let readback_path = temporary.path().join("publication-readback.json");
    fs::write(&cas_path, serde_json::to_vec(&cas).unwrap()).unwrap();
    fs::write(&lifecycle_path, serde_json::to_vec(&lifecycle).unwrap()).unwrap();
    fs::write(&readback_path, serde_json::to_vec(&readback).unwrap()).unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "repository-topic-clone",
            "cleanup",
            "--url",
            request.url.as_str(),
            "--repo-name",
            repository,
            "--workspace-root",
            parent.to_str().unwrap(),
            "--topic",
            topic,
            "--branch",
            branch,
            "--checkout-mode",
            "independent-clone",
            "--candidate-cas",
            cas_path.to_str().unwrap(),
            "--pr-lifecycle",
            lifecycle_path.to_str().unwrap(),
            "--publication-readback",
            readback_path.to_str().unwrap(),
            "--apply",
        ])
        .output()
        .expect("run native cleanup CLI");

    assert!(
        output.status.success(),
        "native cleanup CLI failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("CLEANUP="));
    assert!(!prepared.clone.exists());
    assert_eq!(fs::read(&sibling).unwrap(), b"keep\n");
    assert_eq!(fs::read(parent.join(".gitignore")).unwrap(), ignore_after_drift);
}
