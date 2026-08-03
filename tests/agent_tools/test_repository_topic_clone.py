"""Tests for repository-topic clone lifecycle semantics."""
# ruff: noqa: D103,D104,D107

# @dependency-start
# contract test
# responsibility Verifies repository-topic clone prepare, merge-main, and cleanup gates.
# upstream design ../../documents/rule/repository-topic-clone.md repository-topic clone lifecycle contract
# downstream implementation ../../tools/agent_tools/repository_topic_clone.py owns lifecycle behavior exercised by this test
# downstream implementation ../../tools/agent_tools/check_dependency_headers.py validates this test header
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import tools.agent_tools.repository_topic_clone as rtc

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = PROJECT_ROOT / "tools" / "agent_tools" / "repository_topic_clone.py"
sys.path.insert(0, str(TOOL_PATH.parent))

from update_lifecycle_contract import (  # noqa: E402
    materialize_publication_readback_receipt,
    pull_request_branch_table,
)


def run_git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def init_remote(tmp_path: Path) -> tuple[Path, str]:
    remote = tmp_path / "repo.git"
    source = tmp_path / "source"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "init", "-b", "main", str(source)], check=True, capture_output=True
    )
    (source / "base.txt").write_text("base\n", encoding="utf-8")
    run_git(source, "add", "base.txt")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "init",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(source, "remote", "add", "origin", str(remote))
    run_git(source, "push", "origin", "main")
    return remote, str(remote)


def init_file(path: Path, filename: str, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_evidence(tmp_path: Path) -> Path:
    evidence = tmp_path / "owner-evidence.md"
    evidence.write_text("evidence\n", encoding="utf-8")
    return evidence


def lifecycle_binding(candidate_sha: str, candidate_tree: str) -> dict[str, object]:
    return {
        "transaction_id": "tx:" + "1" * 64,
        "snapshot_id": "snapshot:" + "2" * 64,
        "candidate_sha": candidate_sha,
        "tree_sha": candidate_tree,
        "input_digest": "sha256:" + "5" * 64,
        "tool_id": "publication-integrator",
        "tool_version": "test.v1",
        "evidence_ref": "evidence:" + "6" * 64,
        "evidence_digest": "sha256:" + "7" * 64,
        "timing": {
            "started_at": "2026-07-18T00:00:00Z",
            "finished_at": "2026-07-18T00:00:00Z",
            "last_attempt_at": "2026-07-18T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": False,
        },
    }


def publication_artifacts(
    clone: Path,
    *,
    branch: str,
    repo_name: str,
    state: str,
    merge_sha: str | None = None,
    merge_tree: str | None = None,
) -> tuple[dict[str, object], dict[str, object], dict[str, object] | None]:
    """Build canonical CAS, PR lifecycle, and optional merged readback."""
    candidate_sha = run_git(clone, "rev-parse", "HEAD")
    candidate_tree = run_git(clone, "rev-parse", "HEAD^{tree}")
    base_sha = run_git(clone, "rev-parse", "origin/main")
    base_tree = run_git(clone, "rev-parse", "origin/main^{tree}")
    binding = lifecycle_binding(candidate_sha, candidate_tree)
    cas_binding = dict(binding)
    cas_binding["evidence_ref"] = "evidence:" + "8" * 64
    cas_binding["evidence_digest"] = "sha256:" + "8" * 64
    cas: dict[str, object] = {
        "schema": "agent-canon.candidate-cas-receipt.v1",
        "cas_receipt_id": "cas:" + "9" * 64,
        "binding": cas_binding,
        "predecessor_evidence_id": binding["evidence_ref"],
        "rebind_receipt_evidence_id": "rebind:" + "a" * 64,
        "candidate_identity": {
            "candidate_sha": candidate_sha,
            "tree_sha": candidate_tree,
        },
        "cas_base_identity": {"commit_sha": base_sha, "tree_sha": base_tree},
        "cas_evidence_ref": "evidence:" + "8" * 64,
        "cas_stage": "cas",
    }
    lifecycle_binding_value = dict(cas_binding)
    lifecycle_binding_value["evidence_ref"] = "evidence:" + "b" * 64
    lifecycle_binding_value["evidence_digest"] = "sha256:" + "b" * 64
    ref = f"refs/heads/{branch}"
    lifecycle: dict[str, object] = {
        "schema": "agent-canon.pull-request-lifecycle.v1",
        "kind": "user",
        "binding": lifecycle_binding_value,
        "state": state,
        "remote_identity": {
            "repo_owner": "owner",
            "repo_name": repo_name,
            "remote_name": "origin",
            "url_digest": "sha256:" + "c" * 64,
            "ref": ref,
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree,
        },
        "base_identity": {
            "repo_owner": "owner",
            "repo_name": repo_name,
            "ref": "refs/heads/main",
            "commit_sha": base_sha,
            "tree_sha": base_tree,
        },
        "head_identity": {
            "repo_owner": "owner",
            "repo_name": repo_name,
            "ref": ref,
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree,
        },
        "branch": pull_request_branch_table(),
        "permission_identity": {
            "actor_id": "github-user:7",
            "permission_state": "verified_true",
            "permission_evidence_id": "evidence:" + "d" * 64,
            "authority_source": "fixture GitHub readback",
            "assumption_forbidden": True,
        },
        "pr_essence": {
            "problem": "topic source change",
            "intent": "publish exact topic head",
            "canonical_owner": "repository-topic-clone",
            "contract_delta": "generic lifecycle fixture",
            "evidence_refs": ["evidence:" + "e" * 64],
        },
        "reviews": [],
        "user_identity": {
            "actor_id": "github-user:7",
            "display_name": "Lifecycle Test",
        },
    }
    if state != "merged":
        return cas, lifecycle, None
    assert merge_sha is not None and merge_tree is not None
    readback = materialize_publication_readback_receipt(
        candidate_cas_receipt=cas,
        pull_request_lifecycle=lifecycle,
        authoritative_pr_readback={
            "number": 7,
            "state": "MERGED",
            "baseRefName": "main",
            "baseRefOid": merge_sha,
            "mergeCasBaseOid": base_sha,
            "mergeCasBaseTreeOid": base_tree,
            "headRefName": branch,
            "headRefOid": candidate_sha,
            "headRepository": {"nameWithOwner": f"owner/{repo_name}"},
            "mergeCommit": {"oid": merge_sha},
            "mergeTreeOid": merge_tree,
        },
    )
    return cas, lifecycle, readback


def test_request_reuses_local_and_remote_branch(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    workspace.mkdir()

    repo_name = "repo-one"
    topic = "topic-one"

    initial = rtc.request(
        remote_url, repo_name, workspace, topic, "feature/local", evidence
    )
    run_git(initial.clone, "config", "user.name", "Test")
    run_git(initial.clone, "config", "user.email", "test@example.invalid")
    reused_local = rtc.request(
        remote_url,
        repo_name,
        workspace,
        topic,
        "feature/local",
        evidence,
    )
    assert reused_local.clone == initial.clone
    assert reused_local.branch == "feature/local"
    assert reused_local.candidate_sha == run_git(
        reused_local.clone, "rev-parse", "feature/local"
    )
    assert run_git(
        reused_local.clone, "config", "--get", "repository-topic-clone.branch-source"
    )

    source = Path(tmp_path / "source")
    run_git(source, "checkout", "-b", "feature/remote")
    run_git(source, "push", "origin", "HEAD:refs/heads/feature/remote")

    reused_remote = rtc.request(
        remote_url, repo_name, workspace, topic, "feature/remote", evidence
    )
    assert reused_remote.branch == "feature/remote"
    assert (
        run_git(reused_remote.clone, "symbolic-ref", "--short", "HEAD")
        == "feature/remote"
    )
    assert (
        run_git(reused_remote.clone, "rev-parse", "--abbrev-ref", "@{upstream}")
        == "origin/feature/remote"
    )


def test_prepare_rejects_unsafe_repository_name_and_symlink_workspace(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    workspace.mkdir()

    with pytest.raises(rtc.RepositoryTopicCloneError, match="safe path component"):
        rtc.request(
            remote_url, "../repo", workspace, "topic", "feature/topic", evidence
        )

    external = tmp_path / "external"
    external.mkdir()
    (workspace / "workspace").symlink_to(external, target_is_directory=True)
    with pytest.raises(rtc.RepositoryTopicCloneError, match="symlink"):
        rtc.request(remote_url, "repo", workspace, "topic", "feature/topic", evidence)
    assert list(external.iterdir()) == []


def test_merge_main_before_publication_receipt_is_created(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    workspace.mkdir()

    topic = "topic-merge"
    repo_name = "repo-two"
    source = Path(tmp_path / "source")

    receipt = rtc.request(
        remote_url, repo_name, workspace, topic, "feature/merge", evidence
    )
    run_git(receipt.clone, "config", "user.name", "Test")
    run_git(receipt.clone, "config", "user.email", "test@example.invalid")
    (receipt.clone / "topic.txt").write_text("topic-change\n", encoding="utf-8")
    run_git(receipt.clone, "add", "topic.txt")
    subprocess.run(
        [
            "git",
            "-C",
            str(receipt.clone),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "topic change",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(receipt.clone, "push", "origin", "HEAD:refs/heads/feature/merge")

    (source / "upstream.txt").write_text("upstream\n", encoding="utf-8")
    run_git(source, "add", "upstream.txt")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "upstream",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(source, "push", "origin", "main")

    merged = rtc.merge_main(receipt.request)
    assert merged.merged_sha != merged.candidate_sha
    assert (
        run_git(receipt.clone, "merge-base", "--is-ancestor", "origin/main", "HEAD")
        == ""
    )


def test_merge_main_preserves_conflict_with_typed_state(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    workspace.mkdir()
    source = tmp_path / "source"

    receipt = rtc.request(
        remote_url,
        "repo-conflict",
        workspace,
        "topic-conflict",
        "feature/conflict",
        evidence,
    )
    run_git(receipt.clone, "config", "user.name", "Test")
    run_git(receipt.clone, "config", "user.email", "test@example.invalid")
    (receipt.clone / "base.txt").write_text("topic\n", encoding="utf-8")
    run_git(receipt.clone, "add", "base.txt")
    run_git(receipt.clone, "commit", "-m", "topic conflict")

    (source / "base.txt").write_text("main\n", encoding="utf-8")
    run_git(source, "add", "base.txt")
    run_git(source, "commit", "-m", "main conflict")
    run_git(source, "push", "origin", "main")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-conflict-preserve"):
        rtc.merge_main(receipt.request)
    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-conflict-preserve"):
        rtc.request(
            remote_url,
            "repo-conflict",
            workspace,
            "topic-conflict",
            "feature/conflict",
            evidence,
        )


def test_cleanup_uses_canonical_pr_and_merged_receipts_and_preserves_siblings(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    workspace.mkdir()

    repo_name = "repo-three"
    topic = "topic-cleanup"

    request = rtc.request(
        remote_url, repo_name, workspace, topic, "feature/cleanup", evidence
    )
    run_git(request.clone, "config", "user.name", "Test")
    run_git(request.clone, "config", "user.email", "test@example.invalid")
    (request.clone / "topic.txt").write_text("topic\n", encoding="utf-8")
    run_git(request.clone, "add", "topic.txt")
    run_git(request.clone, "commit", "-m", "topic change")
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")

    topic_root = workspace / "workspace" / topic
    sibling = topic_root / "keep.txt"
    sibling.write_text("keep", encoding="utf-8")

    cas, lifecycle, _ = publication_artifacts(
        request.clone,
        branch="feature/cleanup",
        repo_name=repo_name,
        state="ready",
    )
    cas_path = tmp_path / "candidate-cas.json"
    lifecycle_path = tmp_path / "pr-lifecycle.json"
    cas_path.write_text(json.dumps(cas), encoding="utf-8")
    lifecycle_path.write_text(json.dumps(lifecycle), encoding="utf-8")

    proof = rtc.cleanup(
        request.request,
        expected_clone=request.clone,
        candidate_cas=cas_path,
        pr_lifecycle=lifecycle_path,
        apply=False,
    )
    assert not proof.removed
    assert proof.evidence == "publication-head"

    run_git(
        request.clone,
        "config",
        "repository-topic-clone.repository",
        "different-repository",
    )
    with pytest.raises(rtc.RepositoryTopicCloneError, match="repository-mismatch"):
        rtc.cleanup(
            request.request,
            expected_clone=request.clone,
            candidate_cas=cas_path,
            pr_lifecycle=lifecycle_path,
            apply=False,
        )
    run_git(
        request.clone,
        "config",
        "repository-topic-clone.repository",
        repo_name,
    )

    source = tmp_path / "source"
    run_git(source, "fetch", "origin", "feature/cleanup")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "merge",
            "--no-ff",
            "--no-edit",
            "origin/feature/cleanup",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(source, "push", "origin", "main")
    merge_sha = run_git(source, "rev-parse", "HEAD")
    merge_tree = run_git(source, "rev-parse", "HEAD^{tree}")
    cas, lifecycle, readback = publication_artifacts(
        request.clone,
        branch="feature/cleanup",
        repo_name=repo_name,
        state="merged",
        merge_sha=merge_sha,
        merge_tree=merge_tree,
    )
    assert readback is not None
    cas_path.write_text(json.dumps(cas), encoding="utf-8")
    lifecycle_path.write_text(json.dumps(lifecycle), encoding="utf-8")
    readback_path = tmp_path / "publication-readback.json"
    readback_path.write_text(json.dumps(readback), encoding="utf-8")

    with pytest.raises(
        rtc.RepositoryTopicCloneError,
        match="merged state requires publication readback",
    ):
        rtc.cleanup(
            request.request,
            expected_clone=request.clone,
            candidate_cas=cas_path,
            pr_lifecycle=lifecycle_path,
            apply=False,
        )

    proof = rtc.cleanup(
        request.request,
        expected_clone=request.clone,
        candidate_cas=cas_path,
        pr_lifecycle=lifecycle_path,
        publication_readback=readback_path,
        apply=True,
    )
    assert proof.removed
    assert proof.evidence == "integrated-publication"
    assert not request.clone.exists()
    assert sibling.exists()


def test_failure_when_receipt_is_arbitrary_mapping_or_missing(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    workspace.mkdir()

    request = rtc.request(
        remote_url, "repo-four", workspace, "topic-fail", "feature/fail", evidence
    )
    run_git(request.clone, "config", "user.name", "Test")
    run_git(request.clone, "config", "user.email", "test@example.invalid")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.verify_publication(
            request.request,
            candidate_cas=invalid,
            pr_lifecycle=invalid,
        )

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.cleanup(
            request.request,
            expected_clone=request.clone,
            candidate_cas=invalid,
            pr_lifecycle=invalid,
            apply=False,
        )

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.cleanup(
            request.request,
            expected_clone=request.clone,
            apply=False,
        )


def test_prepare_dirty_collision_and_cleanup_rejects_detached_branch(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    workspace.mkdir()

    clone = rtc.request(
        remote_url, "repo-five", workspace, "topic-clean", "feature/clean", evidence
    )
    (clone.clone / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(
        rtc.RepositoryTopicCloneError, match="dirty-worktree-index-or-untracked"
    ):
        rtc.request(
            remote_url, "repo-five", workspace, "topic-clean", "feature/clean", evidence
        )

    (clone.clone / "dirty.txt").unlink()
    run_git(clone.clone, "checkout", "--detach", "HEAD")
    with pytest.raises(rtc.RepositoryTopicCloneError, match="detached"):
        rtc.request(
            remote_url, "repo-five", workspace, "topic-clean", "feature/clean", evidence
        )


def test_repository_policy_decorator_runs_for_prepare_merge_only(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    workspace.mkdir()

    events: list[str] = []

    class Spy:
        def apply(
            self,
            *,
            operation: str,
            request: rtc.RepositoryTopicCloneRequest,
            receipt: object,
        ) -> None:
            events.append(f"{operation}:{type(receipt).__name__}")

    request = rtc.request(
        remote_url,
        "repo-six",
        workspace,
        "topic-decor",
        "feature/decor",
        evidence,
        policy=Spy(),
    )
    rtc.merge_main(request.request, policy=Spy())
    assert events == ["prepare:PrepareReceipt", "merge_main:MergeMainReceipt"]
