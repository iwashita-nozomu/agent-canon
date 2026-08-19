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

from parent_root_side_effects import (  # noqa: E402
    ParentRootAttestationRequest,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
)
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


def test_computed_clone_path_uses_parent_boundary_for_escaping_symlinks(
    tmp_path: Path,
) -> None:
    """Clone projection rejects a topic path whose symlink leaves the parent."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (workspace / "topic").symlink_to(outside, target_is_directory=True)
    receipt = ParentRootSideEffectBoundary().attest(
        ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, purpose="repository-topic-clone"
        )
    )
    with pytest.raises(ParentRootSideEffectError) as rejected:
        ParentRootSideEffectBoundary().resolve_parent_owned_path(
            receipt, "workspace/topic/agent-canon", "repository-topic-clone"
        )
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE


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


def init_workspace_parent(
    path: Path,
    *,
    ignore_content: str = "workspace/\n",
    tracked_ignore: bool = True,
    global_ignore: bool = False,
    info_ignore: bool = False,
) -> None:
    """Create a selected parent repository with its workspace ownership evidence."""
    path.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(path)], check=True, capture_output=True
    )
    (path / ".gitignore").write_text(ignore_content, encoding="utf-8")
    (path / "parent.txt").write_text("parent\n", encoding="utf-8")
    run_git(path, "add", "parent.txt", *(('.gitignore',) if tracked_ignore else ()))
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "parent",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if global_ignore:
        global_file = path / "global-excludes"
        global_file.write_text("workspace/\n", encoding="utf-8")
        run_git(path, "config", "core.excludesFile", str(global_file))
    if info_ignore:
        (path / ".git" / "info" / "exclude").write_text(
            "workspace/\n", encoding="utf-8"
        )


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


def install_legacy_module_markers(
    clone: Path,
    request: rtc.RepositoryTopicCloneRequest,
    owner_sha: str,
    *,
    role: str = "module",
    module: str | None = None,
    placement: str = "workspace-continuation",
) -> None:
    """Replace canonical markers with the historical module marker namespace."""
    for field in (*rtc.CANONICAL_MARKER_FIELDS, "branch-source"):
        subprocess.run(
            [
                "git",
                "-C",
                str(clone),
                "config",
                "--local",
                "--unset-all",
                f"{rtc.MARKER_PREFIX}.{field}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    values = {
        "topic": rtc.topic_slug(request.topic),
        "role": role,
        "module": module or f"vendor/{request.repository}",
        "url": request.url.removesuffix(".git"),
        "branch": request.branch,
        "placement": placement,
        "owner-evidence-sha256": owner_sha,
    }
    for field, value in values.items():
        run_git(
            clone,
            "config",
            "--local",
            f"{rtc.LEGACY_MARKER_PREFIX}.{field}",
            value,
        )


def test_request_reuses_local_and_remote_branch(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

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


def test_local_branch_reuse_does_not_fetch_main_when_main_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing clean local branches remain reusable without an origin/main fetch."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    initial = rtc.request(
        remote_url, "repo-offline", workspace, "topic-offline", "feature/local", evidence
    )
    original_run_git = rtc._run_git

    def fail_main_fetch(path: Path, args: list[str]) -> str:
        if list(args) == ["fetch", "origin", "main"]:
            raise rtc.GitCommandError(path, args, "offline")
        return original_run_git(path, args)

    monkeypatch.setattr(rtc, "_run_git", fail_main_fetch)
    reused = rtc.request(
        remote_url, "repo-offline", workspace, "topic-offline", "feature/local", evidence
    )
    assert reused.clone == initial.clone

    with pytest.raises(rtc.GitCommandError, match="offline"):
        rtc.request(
            remote_url, "repo-offline", workspace, "topic-offline", "feature/new", evidence
        )


def test_prepare_rejects_unsafe_repository_name_and_symlink_workspace(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

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


def test_clone_failure_aborts_partial_target_and_preserves_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed clone removes only its newly reserved target, including residue."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    sibling = workspace / "workspace" / "topic-failure" / "sibling"
    sibling.mkdir(parents=True)
    (sibling / "keep.txt").write_text("keep\n", encoding="utf-8")
    original_run_git = rtc._run_git

    def fail_clone(
        path: Path, args: list[str], *, pass_fds: tuple[int, ...] = ()
    ) -> str:
        if args and args[0] == "clone":
            target = Path(args[-1])
            (target / "partial" / "nested").mkdir(parents=True)
            (target / "partial" / "nested" / "residue.txt").write_text(
                "residue\n", encoding="utf-8"
            )
            raise rtc.GitCommandError(path, args, "injected clone failure")
        return original_run_git(path, args, pass_fds=pass_fds)

    monkeypatch.setattr(rtc, "_run_git", fail_clone)
    with pytest.raises(rtc.GitCommandError, match="injected clone failure"):
        rtc.request(
            remote_url,
            "repo-failure",
            workspace,
            "topic-failure",
            "feature/failure",
            evidence,
        )

    clone = workspace / "workspace" / "topic-failure" / "repo-failure"
    assert not clone.exists()
    assert (sibling / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_unrelated_dirty_module_does_not_trigger_managed_relation(
    tmp_path: Path,
) -> None:
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    vendor = workspace / "vendor" / "agent-canon"
    subprocess.run(["git", "clone", "-q", remote_url, str(vendor)], check=True)
    (vendor / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    (workspace / ".gitmodules").write_text(
        '[submodule "vendor/agent-canon"]\n'
        "\tpath = vendor/agent-canon\n"
        "\turl = https://example.invalid/unrelated.git\n",
        encoding="utf-8",
    )
    source_sha = run_git(vendor, "rev-parse", "HEAD")
    run_git(workspace, "add", ".gitmodules", "vendor/agent-canon")
    run_git(
        workspace,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{source_sha},vendor/agent-canon",
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "module",
        ],
        check=True,
        capture_output=True,
    )

    prepared = rtc.request(
        remote_url, "requested-repo", workspace, "topic", "feature/topic", evidence
    )
    assert prepared.clone.is_dir()


def test_matching_but_unmanaged_module_uses_generic_relation(
    tmp_path: Path,
) -> None:
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    vendor = workspace / "vendor" / "requested-repo"
    subprocess.run(["git", "clone", "-q", remote_url, str(vendor)], check=True)
    (workspace / ".gitmodules").write_text(
        '[submodule "vendor/requested-repo"]\n'
        "\tpath = vendor/requested-repo\n"
        f"\turl = {remote_url}\n",
        encoding="utf-8",
    )
    source_sha = run_git(vendor, "rev-parse", "HEAD")
    run_git(workspace, "add", ".gitmodules", "vendor/requested-repo")
    run_git(
        workspace,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{source_sha},vendor/requested-repo",
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "module",
        ],
        check=True,
        capture_output=True,
    )
    prepared = rtc.request(
        remote_url, "requested-repo", workspace, "topic", "feature/topic", evidence
    )
    assert prepared.clone.is_dir()
    run_git(prepared.clone, "push", "-u", "origin", "feature/topic")
    removed = rtc.cleanup(prepared.request, apply=True)
    assert removed.removed
    assert not prepared.clone.exists()


@pytest.mark.parametrize(
    "root_kind",
    ("non-repository", "nested", "missing-ignore", "untracked-ignore", "global-ignore", "info-ignore"),
)
def test_prepare_rejects_invalid_workspace_roots_before_creation(
    tmp_path: Path, root_kind: str
) -> None:
    """Reject every non-canonical parent before creating workspace/topic paths."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    if root_kind == "non-repository":
        workspace = tmp_path / "non-repository"
        workspace.mkdir()
    elif root_kind == "nested":
        parent = tmp_path / "parent"
        init_workspace_parent(parent)
        workspace = parent / "nested"
        workspace.mkdir()
    elif root_kind == "missing-ignore":
        workspace = tmp_path / "parent"
        init_workspace_parent(workspace)
        (workspace / ".gitignore").unlink()
    elif root_kind == "untracked-ignore":
        workspace = tmp_path / "parent"
        init_workspace_parent(workspace, tracked_ignore=False)
    elif root_kind == "global-ignore":
        workspace = tmp_path / "parent"
        init_workspace_parent(
            workspace, ignore_content="# repository has no workspace rule\n", global_ignore=True
        )
    else:
        workspace = tmp_path / "parent"
        init_workspace_parent(
            workspace, ignore_content="# repository has no workspace rule\n", info_ignore=True
        )

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.request(
            remote_url,
            "invalid-root",
            workspace,
            f"invalid-{root_kind}",
            "feature/invalid",
            evidence,
        )
    assert not (workspace / "workspace").exists()


def test_merge_main_before_publication_receipt_is_created(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

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
    init_workspace_parent(workspace)
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


def test_cleanup_without_publication_packet_matches_remote_head(tmp_path: Path) -> None:
    """A clean pushed topic head is sufficient for dry-run and apply cleanup."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url, "repo-no-packet", workspace, "topic-no-packet", "feature/cleanup", evidence
    )
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")

    dry_run = rtc.cleanup(request.request, apply=False)
    assert not dry_run.removed
    assert dry_run.evidence == "remote-head"
    assert request.clone.exists()

    removed = rtc.cleanup(request.request, apply=True)
    assert removed.removed
    assert removed.evidence == "remote-head"
    assert not request.clone.exists()


def test_stale_binding_directory_does_not_promote_generic_cleanup(
    tmp_path: Path,
) -> None:
    """Stale historical binding artifacts do not select managed cleanup."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    request = rtc.request(
        remote_url,
        "repo-managed-partial",
        workspace,
        "topic-managed-partial",
        "feature/cleanup",
        evidence,
    )
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")
    binding_dir = (
        workspace
        / ".agent-canon"
        / "parent-bindings"
        / rtc.topic_slug(request.request.topic)
        / request.request.repository
    )
    binding_dir.mkdir(parents=True)
    stale = binding_dir / "stale.json"
    stale.write_text("stale\n", encoding="utf-8")
    removed = rtc.cleanup(request.request, apply=True)
    assert removed.removed
    assert not request.clone.exists()
    assert stale.read_text(encoding="utf-8") == "stale\n"


def test_cleanup_accepts_exact_legacy_module_markers_read_only(
    tmp_path: Path,
) -> None:
    """Historical module markers authorize cleanup without being rewritten."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url, "repo-legacy", workspace, "topic-legacy", "feature/cleanup", evidence
    )
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")
    owner_sha = rtc._evidence_sha256(evidence)
    install_legacy_module_markers(request.clone, request.request, owner_sha)
    before = run_git(request.clone, "config", "--local", "--list")

    dry_run = rtc.cleanup(request.request, apply=False)
    assert not dry_run.removed
    assert dry_run.evidence == "remote-head"
    assert run_git(request.clone, "config", "--local", "--list") == before

    removed = rtc.cleanup(request.request, apply=True)
    assert removed.removed
    assert not request.clone.exists()


def test_cleanup_rejects_partial_or_mismatched_legacy_module_markers(
    tmp_path: Path,
) -> None:
    """Legacy compatibility is exact and never accepts unknown role/placement."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url, "repo-legacy-invalid", workspace, "topic-legacy-invalid", "feature/cleanup", evidence
    )
    owner_sha = rtc._evidence_sha256(evidence)

    install_legacy_module_markers(
        request.clone, request.request, owner_sha, role="unknown"
    )
    with pytest.raises(rtc.RepositoryTopicCloneError, match="legacy-marker-mismatch"):
        rtc.cleanup(request.request, apply=False)

    install_legacy_module_markers(
        request.clone, request.request, owner_sha, placement="unknown"
    )
    with pytest.raises(rtc.RepositoryTopicCloneError, match="legacy-marker-mismatch"):
        rtc.cleanup(request.request, apply=False)

    install_legacy_module_markers(
        request.clone, request.request, owner_sha, module="vendor/other"
    )
    with pytest.raises(rtc.RepositoryTopicCloneError, match="legacy-marker-mismatch"):
        rtc.cleanup(request.request, apply=False)

    install_legacy_module_markers(request.clone, request.request, owner_sha)
    run_git(
        request.clone,
        "config",
        "--local",
        "--unset-all",
        f"{rtc.LEGACY_MARKER_PREFIX}.placement",
    )
    with pytest.raises(rtc.RepositoryTopicCloneError, match="legacy-marker-incomplete"):
        rtc.cleanup(request.request, apply=False)


def test_cleanup_rejects_remote_head_mismatch_without_publication_packet(
    tmp_path: Path,
) -> None:
    """A remote branch advance is a reconstructibility hold, not a delete signal."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url, "repo-remote-mismatch", workspace, "topic-remote-mismatch", "feature/cleanup", evidence
    )
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")

    source = tmp_path / "source"
    run_git(source, "fetch", "origin", "feature/cleanup")
    run_git(source, "checkout", "-B", "feature/cleanup", "origin/feature/cleanup")
    run_git(source, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "remote advance")
    run_git(source, "push", "origin", "feature/cleanup")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="remote branch head mismatch"):
        rtc.cleanup(request.request, apply=False)
    assert request.clone.exists()


def test_cleanup_rejects_partial_optional_publication_packet(tmp_path: Path) -> None:
    """Lifecycle packet fields are optional together, never as an invented half-set."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url, "repo-partial", workspace, "topic-partial", "feature/cleanup", evidence
    )
    with pytest.raises(
        rtc.RepositoryTopicCloneError,
        match="candidate CAS and PR lifecycle evidence must be provided together",
    ):
        rtc.cleanup(
            request.request,
            candidate_cas=tmp_path / "missing-cas.json",
            apply=False,
        )


def test_cleanup_uses_canonical_pr_and_merged_receipts_after_root_ignore_drifts(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

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
    (workspace / ".gitignore").write_text("# placement ownership drift\n", encoding="utf-8")
    drift_probe = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "core.excludesFile=/dev/null",
            "check-ignore",
            "-v",
            "--no-index",
            "--",
            "workspace/.agent-canon-workspace-probe",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert drift_probe.returncode == 1, drift_probe.stdout + drift_probe.stderr

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
            candidate_cas=cas_path,
            pr_lifecycle=lifecycle_path,
            apply=False,
        )

    proof = rtc.cleanup(
        request.request,
        candidate_cas=cas_path,
        pr_lifecycle=lifecycle_path,
        publication_readback=readback_path,
        apply=True,
    )
    assert proof.removed
    assert proof.evidence == "integrated-publication"
    assert not request.clone.exists()
    assert sibling.exists()


def test_failure_when_receipt_is_arbitrary_mapping_or_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url, "repo-four", workspace, "topic-fail", "feature/fail", evidence
    )
    run_git(request.clone, "config", "user.name", "Test")
    run_git(request.clone, "config", "user.email", "test@example.invalid")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    original_run_git = rtc._run_git
    calls: list[tuple[str, ...]] = []

    def track_git(path: Path, args: list[str]) -> str:
        calls.append(tuple(args))
        return original_run_git(path, args)

    monkeypatch.setattr(rtc, "_run_git", track_git)

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.verify_publication(
            request.request,
            candidate_cas=invalid,
            pr_lifecycle=invalid,
        )

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.cleanup(
            request.request,
            candidate_cas=invalid,
            pr_lifecycle=invalid,
            apply=False,
        )
    assert not any(call[:2] == ("fetch", "origin") for call in calls)

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.cleanup(
            request.request,
            apply=False,
        )


def test_prepare_dirty_collision_and_cleanup_rejects_detached_branch(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

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
    init_workspace_parent(workspace)

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
