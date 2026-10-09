"""Tests for repository-topic clone lifecycle semantics."""
# ruff: noqa: D103,D104,D107

# @dependency-start
# contract test
# responsibility Verifies repository-topic clone prepare, merge-main, and cleanup gates.
# upstream design ../../documents/rule/repository-topic-clone.md repository-topic clone lifecycle contract
# downstream implementation ../../tools/repository/workspace/repository_topic_clone.py owns lifecycle behavior exercised by this test
# downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates this test header
# @dependency-end

from __future__ import annotations

from collections.abc import Sequence
import json
import subprocess
import sys
from pathlib import Path

import pytest
import tools.repository.workspace.repository_topic_clone as rtc
from tools.runtime.authority.checkout_identity import CheckoutIdentity
from tools.runtime.authority.writer_target import read_writer_target_packet

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = (
    PROJECT_ROOT / "tools" / "repository" / "workspace" / "repository_topic_clone.py"
)
sys.path.insert(0, str(TOOL_PATH.parent))

from tools.repository.workspace.parent_root_side_effects import (  # noqa: E402
    ParentRootAttestationRequest,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
)
from tools.runtime.lifecycle.update_lifecycle_contract import (  # noqa: E402
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


def git_metadata_path(root: Path, name: str) -> Path:
    """Resolve one Git metadata path relative to the observed gitdir."""
    value = Path(run_git(root, "rev-parse", "--git-path", name))
    if value.is_absolute():
        return value
    return Path(run_git(root, "rev-parse", "--absolute-git-dir")) / value


def patch_linked_checkout_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the normalized remote identity expected by writer-target packets."""

    def fake_identity(path: Path) -> CheckoutIdentity:
        root = path.resolve()
        return CheckoutIdentity(
            cwd=str(root),
            git_root=str(root),
            branch=run_git(root, "symbolic-ref", "--short", "HEAD"),
            head=run_git(root, "rev-parse", "HEAD"),
            remote="owner/repo",
        )

    monkeypatch.setattr(rtc, "resolve_checkout_identity", fake_identity)


def snapshot_checkout_files(root: Path) -> dict[str, bytes]:
    """Read checkout files except Git metadata and the reserved writer packet."""
    snapshot: dict[str, bytes] = {}
    reserved_packet = rtc.WRITER_TARGET_PACKET_RELATIVE
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".git" in relative.parts or relative == reserved_packet or path.is_symlink():
            continue
        if path.is_file():
            snapshot[relative.as_posix()] = path.read_bytes()
    return snapshot


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
    run_git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
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
    run_git(path, "add", "parent.txt", *((".gitignore",) if tracked_ignore else ()))
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
        remote_url,
        repo_name,
        workspace,
        topic,
        "feature/local",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        repo_name,
        workspace,
        topic,
        "feature/remote",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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


def test_request_and_merge_preserve_existing_writer_target_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    def fake_identity(path: Path) -> CheckoutIdentity:
        root = path.resolve()
        return CheckoutIdentity(
            cwd=str(root),
            git_root=str(root),
            branch=run_git(root, "symbolic-ref", "--short", "HEAD"),
            head=run_git(root, "rev-parse", "HEAD"),
            remote="local/repo",
        )

    monkeypatch.setattr(rtc, "resolve_checkout_identity", fake_identity)
    prepared = rtc.request(
        remote_url,
        "repo-target",
        workspace,
        "topic-target",
        "feature/target",
        evidence,
        allowed_paths=("src/owned.py",),
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    packet, _identity = read_writer_target_packet(prepared.clone)
    assert packet.allowed_paths == ("src/owned.py",)
    reused = rtc.request(
        remote_url,
        "repo-target",
        workspace,
        "topic-target",
        "feature/target",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    assert reused.request.allowed_paths == ("src/owned.py",)
    merged = rtc.merge_main(reused.request)
    assert merged.request.allowed_paths == ("src/owned.py",)
    after, _identity = read_writer_target_packet(prepared.clone)
    assert after.allowed_paths == ("src/owned.py",)
    revised = rtc.request(
        remote_url,
        "repo-target",
        workspace,
        "topic-target",
        "feature/target",
        evidence,
        allowed_paths=("src/owned.py", "tests/test_owned.py"),
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    updated, _identity = read_writer_target_packet(revised.clone)
    assert updated.allowed_paths == ("src/owned.py", "tests/test_owned.py")


def test_merge_main_keeps_dirty_independent_checkout_hold_after_metadata_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata reuse does not let merge-main proceed on a dirty independent clone."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    def fake_identity(path: Path) -> CheckoutIdentity:
        root = path.resolve()
        return CheckoutIdentity(
            cwd=str(root),
            git_root=str(root),
            branch=run_git(root, "symbolic-ref", "--short", "HEAD"),
            head=run_git(root, "rev-parse", "HEAD"),
            remote="local/repo",
        )

    monkeypatch.setattr(rtc, "resolve_checkout_identity", fake_identity)
    request = dict(
        url=remote_url,
        repository="repo-independent-dirty-metadata",
        workspace_root=workspace,
        topic="topic-independent-dirty-metadata",
        branch="feature/independent-dirty-metadata",
        owner_evidence=evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    prepared = rtc.request(**request, allowed_paths=("old.py",))
    dirty = prepared.clone / "untracked.txt"
    dirty.write_text("preserve\n", encoding="utf-8")

    updated = rtc.request(**request, allowed_paths=("current.py",))
    target, _identity = read_writer_target_packet(updated.clone)
    assert target.allowed_paths == ("current.py",)
    assert dirty.read_text(encoding="utf-8") == "preserve\n"
    with pytest.raises(
        rtc.RepositoryTopicCloneError,
        match="merge-main hold: dirty-worktree-index-or-untracked",
    ):
        rtc.merge_main(updated.request)

    assert dirty.read_text(encoding="utf-8") == "preserve\n"
    assert updated.clone.is_dir()


@pytest.mark.parametrize("mode", [0o700, 0o755])
def test_linked_worktrees_use_native_common_dir_and_per_worktree_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int
) -> None:
    """Linked topics share Git objects but keep indexes, markers, and packets separate."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    workspace.chmod(mode)
    run_git(workspace, "remote", "add", "origin", remote_url)

    def fake_identity(path: Path) -> CheckoutIdentity:
        root = path.resolve()
        return CheckoutIdentity(
            cwd=str(root),
            git_root=str(root),
            branch=run_git(root, "symbolic-ref", "--short", "HEAD"),
            head=run_git(root, "rev-parse", "HEAD"),
            remote="owner/repo",
        )

    monkeypatch.setattr(rtc, "resolve_checkout_identity", fake_identity)

    first = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-first",
        "feature/first",
        evidence,
        allowed_paths=("first.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    second = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-second",
        "feature/second",
        evidence,
        allowed_paths=("second.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )

    assert first.clone != second.clone
    assert (first.clone.stat().st_mode & 0o777) == mode
    assert (second.clone.stat().st_mode & 0o777) == mode
    assert run_git(first.clone, "rev-parse", "--git-common-dir") == run_git(
        second.clone, "rev-parse", "--git-common-dir"
    )
    assert run_git(first.clone, "rev-parse", "--git-path", "index") != run_git(
        second.clone, "rev-parse", "--git-path", "index"
    )
    assert (
        run_git(
            first.clone,
            "config",
            "--worktree",
            "--get",
            f"{rtc.MARKER_PREFIX}.topic",
        )
        == "topic-first"
    )
    assert (
        run_git(
            second.clone,
            "config",
            "--worktree",
            "--get",
            f"{rtc.MARKER_PREFIX}.topic",
        )
        == "topic-second"
    )
    with pytest.raises(subprocess.CalledProcessError):
        run_git(
            first.clone,
            "config",
            "--local",
            "--get",
            f"{rtc.MARKER_PREFIX}.topic",
        )
    first_packet, _ = read_writer_target_packet(first.clone)
    second_packet, _ = read_writer_target_packet(second.clone)
    assert first_packet.allowed_paths == ("first.py",)
    assert second_packet.allowed_paths == ("second.py",)
    assert (
        run_git(first.clone, "config", "--get", "extensions.worktreeConfig") == "true"
    )
    assert run_git(workspace, "status", "--porcelain") == ""
    assert remote.exists()


def test_linked_anchor_resolution_accepts_explicit_linked_workspace_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit linked anchor remains the stable parent for nested topics."""
    _, remote_url = init_remote(tmp_path)
    parent = tmp_path / "parent"
    init_workspace_parent(parent)
    run_git(parent, "remote", "add", "origin", remote_url)
    anchor = tmp_path / "anchor"
    run_git(parent, "worktree", "add", "-b", "anchor", anchor, "main")
    evidence = anchor / "parent.txt"

    def fake_identity(path: Path) -> CheckoutIdentity:
        root = path.resolve()
        return CheckoutIdentity(
            cwd=str(root),
            git_root=str(root),
            branch=run_git(root, "symbolic-ref", "--short", "HEAD"),
            head=run_git(root, "rev-parse", "HEAD"),
            remote="owner/repo",
        )

    monkeypatch.setattr(rtc, "resolve_checkout_identity", fake_identity)
    prepared = rtc.request(
        remote_url,
        "repo-linked",
        anchor,
        "topic-nested",
        "feature/nested",
        evidence,
        allowed_paths=("nested.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    assert prepared.clone == anchor / "workspace" / "topic-nested" / "repo-linked"
    assert run_git(prepared.clone, "rev-parse", "--git-common-dir") == run_git(
        anchor, "rev-parse", "--git-common-dir"
    )
    assert run_git(anchor, "status", "--porcelain") == ""


def test_linked_url_mismatch_is_rejected_before_worktree_mutation(
    tmp_path: Path,
) -> None:
    """A dependency URL mismatch cannot create a topic directory or branch."""
    _, remote_url = init_remote(tmp_path)
    wrong_remote = tmp_path / "wrong.git"
    subprocess.run(["git", "init", "--bare", str(wrong_remote)], check=True)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    target = workspace / "workspace" / "topic-mismatch" / "repo-linked"
    before_worktrees = run_git(workspace, "worktree", "list", "--porcelain")
    before_refs = run_git(workspace, "show-ref")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="anchor-origin-mismatch"):
        rtc.request(
            str(wrong_remote),
            "repo-linked",
            workspace,
            "topic-mismatch",
            "feature/mismatch",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_LINKED,
        )

    assert not target.exists()
    assert not (workspace / "workspace").exists()
    assert run_git(workspace, "worktree", "list", "--porcelain") == before_worktrees
    assert run_git(workspace, "show-ref") == before_refs


def test_request_requires_explicit_checkout_mode(tmp_path: Path) -> None:
    """The public request API cannot silently select a checkout implementation."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    with pytest.raises(TypeError):
        rtc.request(
            remote_url,
            "repo-required-mode",
            workspace,
            "topic-required-mode",
            "feature/required-mode",
            evidence,
        )

    required_args = [
        "prepare",
        "--url",
        remote_url,
        "--repo-name",
        "repo-required-mode",
        "--workspace-root",
        str(workspace),
        "--topic",
        "topic-required-mode",
        "--branch",
        "feature/required-mode",
        "--owner-evidence",
        str(evidence),
    ]
    with pytest.raises(SystemExit):
        rtc._parse_args(required_args)


def test_linked_foreign_occupant_does_not_mutate_common_git_state(
    tmp_path: Path,
) -> None:
    """An unverified linked occupant is rejected before config or lifecycle mutation."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    target = workspace / "workspace" / "foreign-topic" / "repo-foreign"
    target.parent.mkdir(parents=True)
    run_git(workspace, "branch", "feature/foreign")
    run_git(workspace, "worktree", "add", target, "feature/foreign")
    common_dir = Path(run_git(target, "rev-parse", "--git-common-dir"))
    common_config = common_dir / "config"
    before_config = common_config.read_bytes()
    before_worktrees = run_git(workspace, "worktree", "list", "--porcelain")
    before_refs = run_git(workspace, "show-ref")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="repository-mismatch"):
        rtc.request(
            remote_url,
            "repo-foreign",
            workspace,
            "foreign-topic",
            "feature/request",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_LINKED,
        )

    foreign_request = rtc.RepositoryTopicCloneRequest(
        url=remote_url,
        repository="repo-foreign",
        workspace_root=workspace,
        topic="foreign-topic",
        branch="feature/request",
        owner_evidence=evidence,
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    with pytest.raises(rtc.RepositoryTopicCloneError, match="branch mismatch"):
        rtc.finalize_merge_main(foreign_request)

    assert common_config.read_bytes() == before_config
    assert run_git(workspace, "worktree", "list", "--porcelain") == before_worktrees
    assert run_git(workspace, "show-ref") == before_refs
    assert target.is_dir()
    assert run_git(target, "symbolic-ref", "--short", "HEAD") == "feature/foreign"


def test_linked_reuse_never_switches_and_preserves_branch_in_use_and_dirty_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linked reuse is read-only with native branch-in-use and dirty failures."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)

    def fake_identity(path: Path) -> CheckoutIdentity:
        root = path.resolve()
        return CheckoutIdentity(
            cwd=str(root),
            git_root=str(root),
            branch=run_git(root, "symbolic-ref", "--short", "HEAD"),
            head=run_git(root, "rev-parse", "HEAD"),
            remote="owner/repo",
        )

    monkeypatch.setattr(rtc, "resolve_checkout_identity", fake_identity)
    request = dict(
        url=remote_url,
        repository="repo-linked",
        workspace_root=workspace,
        topic="topic-first",
        branch="feature/first",
        owner_evidence=evidence,
        allowed_paths=("first.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    prepared = rtc.request(**request)
    reused = rtc.request(**request)
    assert reused.clone == prepared.clone
    assert run_git(prepared.clone, "symbolic-ref", "--short", "HEAD") == "feature/first"

    with pytest.raises(rtc.GitCommandError, match="already (checked out|used)"):
        rtc.request(
            remote_url,
            "repo-linked",
            workspace,
            "topic-second",
            "feature/first",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_LINKED,
        )

    dirty = prepared.clone / "dirty.txt"
    dirty.write_text("preserve\n", encoding="utf-8")
    with pytest.raises(rtc.RepositoryTopicCloneError, match="dirty-worktree"):
        rtc.request(**request)
    assert dirty.read_text(encoding="utf-8") == "preserve\n"


def test_prepare_updates_dirty_linked_target_without_touching_checkout_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit current target changes only reserved prepare metadata."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    patch_linked_checkout_identity(monkeypatch)
    request = dict(
        url=remote_url,
        repository="repo-dirty-target-extension",
        workspace_root=workspace,
        topic="topic-dirty-target-extension",
        branch="feature/dirty-target-extension",
        owner_evidence=evidence,
        allowed_paths=("first.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    prepared = rtc.request(**request)
    packet_path = prepared.writer_target_packet
    assert packet_path is not None
    old_packet_bytes = packet_path.read_bytes()

    tracked = prepared.clone / "base.txt"
    tracked.write_text("tracked WIP\n", encoding="utf-8")
    staged = prepared.clone / "staged.txt"
    staged.write_text("staged WIP\n", encoding="utf-8")
    run_git(prepared.clone, "add", "staged.txt")
    known_wip = prepared.clone / "tools" / "analysis" / "documents" / "wip.md"
    known_wip.parent.mkdir(parents=True)
    known_wip.write_text("owned WIP\n", encoding="utf-8")
    unknown_wip = prepared.clone / "unknown-user-data.txt"
    unknown_wip.write_text("preserve unknown data\n", encoding="utf-8")
    ignored = prepared.clone / "ignored-output.bin"
    exclude_path = git_metadata_path(prepared.clone, "info/exclude")
    old_excludes = exclude_path.read_bytes()
    exclude_path.write_bytes(old_excludes + b"ignored-output.bin\n")
    ignored.write_bytes(b"ignored WIP\n")
    assert (
        run_git(prepared.clone, "check-ignore", "--quiet", "--", "ignored-output.bin")
        == ""
    )

    index_path = git_metadata_path(prepared.clone, "index")
    config_path = git_metadata_path(prepared.clone, "config.worktree")
    before_files = snapshot_checkout_files(prepared.clone)
    before_index = index_path.read_bytes()
    before_config = config_path.read_bytes()
    before_excludes = exclude_path.read_bytes()
    before_status = run_git(
        prepared.clone,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    before_head = run_git(prepared.clone, "rev-parse", "HEAD")
    before_branch = run_git(prepared.clone, "symbolic-ref", "--short", "HEAD")

    current_paths = ("tools/analysis/documents",)
    updated = rtc.request(**{**request, "allowed_paths": current_paths})

    updated_target, _updated_identity = read_writer_target_packet(updated.clone)
    assert updated.request.allowed_paths == current_paths
    assert updated_target.allowed_paths == current_paths
    assert updated_target.normalized_root == str(updated.clone.resolve())
    assert updated_target.branch == before_branch
    assert updated_target.normalized_remote == "owner/repo"
    assert packet_path.read_bytes() != old_packet_bytes
    assert snapshot_checkout_files(updated.clone) == before_files
    assert index_path.read_bytes() == before_index
    assert config_path.read_bytes() == before_config
    assert exclude_path.read_bytes() == before_excludes
    assert (
        run_git(
            updated.clone,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        == before_status
    )
    assert run_git(updated.clone, "rev-parse", "HEAD") == before_head
    assert run_git(updated.clone, "symbolic-ref", "--short", "HEAD") == before_branch
    assert tracked.read_text(encoding="utf-8") == "tracked WIP\n"
    assert staged.read_text(encoding="utf-8") == "staged WIP\n"
    assert known_wip.read_text(encoding="utf-8") == "owned WIP\n"
    assert unknown_wip.read_text(encoding="utf-8") == "preserve unknown data\n"
    assert ignored.read_bytes() == b"ignored WIP\n"

    updated_packet_bytes = packet_path.read_bytes()
    with pytest.raises(
        rtc.RepositoryTopicCloneError, match="dirty-worktree-index-or-untracked"
    ):
        rtc.request(**{**request, "branch": "feature/other"})
    with pytest.raises(
        rtc.RepositoryTopicCloneError, match="dirty-worktree-index-or-untracked"
    ):
        rtc.request(
            **{
                **request,
                "allowed_paths": ("first.py", "../escape"),
            }
        )
    assert packet_path.read_bytes() == updated_packet_bytes
    assert snapshot_checkout_files(updated.clone) == before_files
    assert index_path.read_bytes() == before_index

    with pytest.raises(
        rtc.RepositoryTopicCloneError, match="merge-main hold: dirty-worktree"
    ):
        rtc.merge_main(updated.request)
    with pytest.raises(
        rtc.RepositoryTopicCloneError,
        match="cleanup hold: dirty-worktree-index-or-untracked",
    ):
        rtc.cleanup(updated.request, apply=True)
    assert updated.clone.is_dir()
    assert packet_path.read_bytes() != old_packet_bytes
    assert snapshot_checkout_files(updated.clone) == before_files
    assert index_path.read_bytes() == before_index


def test_prepare_holds_symlinked_writer_packet_without_mutating_outside_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ignored packet symlink cannot redirect the reserved metadata write."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    patch_linked_checkout_identity(monkeypatch)
    request = dict(
        url=remote_url,
        repository="repo-symlinked-writer-packet",
        workspace_root=workspace,
        topic="topic-symlinked-writer-packet",
        branch="feature/symlinked-writer-packet",
        owner_evidence=evidence,
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    prepared = rtc.request(**request, allowed_paths=("first.py",))
    packet_path = prepared.writer_target_packet
    assert packet_path is not None
    packet_contents = packet_path.read_bytes()
    outside_packet = tmp_path / "outside-writer-target.json"
    outside_packet.write_bytes(packet_contents)
    packet_path.unlink()
    packet_path.symlink_to(outside_packet)
    assert not run_git(
        prepared.clone,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )

    with pytest.raises(
        rtc.RepositoryTopicCloneError,
        match="writer_target_packet_path_unsafe",
    ):
        rtc.request(**request, allowed_paths=("replacement.py",))

    assert packet_path.is_symlink()
    assert outside_packet.read_bytes() == packet_contents


def test_prepare_refreshes_changed_owner_evidence_and_current_writer_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exact clean reuse advances evidence and carries or updates the writer target."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    patch_linked_checkout_identity(monkeypatch)
    request = dict(
        url=remote_url,
        repository="repo-evidence-refresh",
        workspace_root=workspace,
        topic="topic-evidence-refresh",
        branch="feature/evidence-refresh",
        owner_evidence=evidence,
        allowed_paths=("first.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )

    prepared = rtc.request(**request)
    original_sha = run_git(
        prepared.clone,
        "config",
        "--worktree",
        "--get",
        f"{rtc.MARKER_PREFIX}.owner-evidence-sha256",
    )
    evidence.write_text("updated task evidence\n", encoding="utf-8")
    with pytest.raises(
        rtc.RepositoryTopicCloneError,
        match="cleanup hold: owner-evidence-mismatch",
    ):
        rtc.cleanup(prepared.request, apply=True)
    assert prepared.clone.is_dir()

    continued = rtc.request(**{**request, "allowed_paths": ()})
    assert continued.clone == prepared.clone
    assert continued.request.allowed_paths == ("first.py",)
    current_sha = rtc._evidence_sha256(evidence)
    assert current_sha != original_sha
    assert (
        run_git(
            continued.clone,
            "config",
            "--worktree",
            "--get",
            f"{rtc.MARKER_PREFIX}.owner-evidence-sha256",
        )
        == current_sha
    )
    retained_target, _ = read_writer_target_packet(continued.clone)
    assert retained_target.allowed_paths == ("first.py",)

    updated_scope = rtc.request(**{**request, "allowed_paths": ("current.py",)})
    updated_target, _ = read_writer_target_packet(updated_scope.clone)
    assert updated_target.allowed_paths == ("current.py",)
    proof = rtc.cleanup(updated_scope.request, apply=False)
    assert not proof.removed
    assert proof.evidence == "linked-superproject-head"


def test_prepare_refreshes_exact_target_metadata_without_rewriting_dirty_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current exact identity can refresh metadata without adopting dirty content."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    patch_linked_checkout_identity(monkeypatch)
    request = dict(
        url=remote_url,
        repository="repo-dirty-evidence",
        workspace_root=workspace,
        topic="topic-dirty-evidence",
        branch="feature/dirty-evidence",
        owner_evidence=evidence,
        allowed_paths=("first.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )

    prepared = rtc.request(**request)
    original_sha = run_git(
        prepared.clone,
        "config",
        "--worktree",
        "--get",
        f"{rtc.MARKER_PREFIX}.owner-evidence-sha256",
    )
    evidence.write_text("updated task evidence\n", encoding="utf-8")
    dirty = prepared.clone / "untracked.txt"
    dirty.write_text("preserve\n", encoding="utf-8")

    continued = rtc.request(**request)

    current_sha = rtc._evidence_sha256(evidence)
    assert current_sha != original_sha
    assert continued.request.allowed_paths == ("first.py",)
    assert dirty.read_text(encoding="utf-8") == "preserve\n"
    assert (
        run_git(
            continued.clone,
            "config",
            "--worktree",
            "--get",
            f"{rtc.MARKER_PREFIX}.owner-evidence-sha256",
        )
        == current_sha
    )
    assert run_git(
        continued.clone,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )


def test_prepare_owner_evidence_refresh_preserves_unknown_marker_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidence refresh does not adopt a checkout with mismatched topic metadata."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    patch_linked_checkout_identity(monkeypatch)
    request = dict(
        url=remote_url,
        repository="repo-unknown-owner",
        workspace_root=workspace,
        topic="topic-unknown-owner",
        branch="feature/unknown-owner",
        owner_evidence=evidence,
        allowed_paths=("first.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )

    prepared = rtc.request(**request)
    original_sha = run_git(
        prepared.clone,
        "config",
        "--worktree",
        "--get",
        f"{rtc.MARKER_PREFIX}.owner-evidence-sha256",
    )
    run_git(
        prepared.clone,
        "config",
        "--worktree",
        f"{rtc.MARKER_PREFIX}.topic",
        "foreign-topic",
    )
    evidence.write_text("updated task evidence\n", encoding="utf-8")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="topic-mismatch"):
        rtc.request(**request)

    assert (
        run_git(
            prepared.clone,
            "config",
            "--worktree",
            "--get",
            f"{rtc.MARKER_PREFIX}.owner-evidence-sha256",
        )
        == original_sha
    )
    assert (
        run_git(
            prepared.clone,
            "config",
            "--worktree",
            "--get",
            f"{rtc.MARKER_PREFIX}.topic",
        )
        == "foreign-topic"
    )


def test_linked_merge_conflict_uses_worktree_git_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conflict preservation resolves MERGE_HEAD and info/exclude via Git paths."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)

    def fake_identity(path: Path) -> CheckoutIdentity:
        root = path.resolve()
        return CheckoutIdentity(
            cwd=str(root),
            git_root=str(root),
            branch=run_git(root, "symbolic-ref", "--short", "HEAD"),
            head=run_git(root, "rev-parse", "HEAD"),
            remote="owner/repo",
        )

    monkeypatch.setattr(rtc, "resolve_checkout_identity", fake_identity)
    request = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-conflict",
        "feature/conflict",
        evidence,
        allowed_paths=("base.txt",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    clone = request.clone
    run_git(clone, "config", "user.name", "Test")
    run_git(clone, "config", "user.email", "test@example.invalid")
    (clone / "base.txt").write_text("topic\n", encoding="utf-8")
    run_git(clone, "add", "base.txt")
    run_git(clone, "commit", "-m", "topic")
    source = tmp_path / "source"
    (source / "base.txt").write_text("main\n", encoding="utf-8")
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
            "main",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(source, "push", "origin", "main")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-conflict-preserve"):
        rtc.merge_main(request.request)
    merge_head = Path(run_git(clone, "rev-parse", "--git-path", "MERGE_HEAD"))
    info_exclude = Path(run_git(clone, "rev-parse", "--git-path", "info/exclude"))
    assert merge_head.is_file()
    assert info_exclude.is_file()
    assert (clone / ".agent-canon" / "conflict-preservation.json").is_file()
    assert run_git(clone, "status", "--porcelain")


def test_linked_cleanup_removes_one_worktree_and_keeps_branch_and_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native cleanup unregisters one worktree without deleting its branch or sibling."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)

    def fake_identity(path: Path) -> CheckoutIdentity:
        root = path.resolve()
        return CheckoutIdentity(
            cwd=str(root),
            git_root=str(root),
            branch=run_git(root, "symbolic-ref", "--short", "HEAD"),
            head=run_git(root, "rev-parse", "HEAD"),
            remote="owner/repo",
        )

    monkeypatch.setattr(rtc, "resolve_checkout_identity", fake_identity)
    first = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-first",
        "feature/first",
        evidence,
        allowed_paths=("first.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    second = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-second",
        "feature/second",
        evidence,
        allowed_paths=("second.py",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    run_git(first.clone, "push", "origin", "feature/first")
    run_git(second.clone, "push", "origin", "feature/second")
    run_git(tmp_path / "source", "push", "origin", "--delete", "feature/first")
    proof = rtc.cleanup(first.request, apply=True)
    assert proof.removed
    assert proof.evidence == "linked-superproject-head"
    assert not first.clone.exists()
    assert second.clone.is_dir()
    assert run_git(workspace, "show-ref", "--verify", "refs/heads/feature/first")
    assert (
        run_git(workspace, "cat-file", "-e", f"{first.candidate_sha}^{{commit}}") == ""
    )
    worktree_list = run_git(workspace, "worktree", "list")
    assert str(first.clone) not in worktree_list
    assert str(second.clone) in worktree_list
    assert not first.clone.parent.exists()


def test_linked_cleanup_requires_external_retention_for_local_only_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task-owner retention preserves ignored files and local submodule objects."""
    _, remote_url = init_remote(tmp_path)
    submodule_root = tmp_path / "submodule-source"
    submodule_root.mkdir()
    _, submodule_url = init_remote(submodule_root)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    patch_linked_checkout_identity(monkeypatch)

    first = rtc.request(
        remote_url,
        "repo-submodule-cleanup",
        workspace,
        "topic-submodule-cleanup",
        "feature/submodule-cleanup",
        evidence,
        allowed_paths=("src/",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    sibling = rtc.request(
        remote_url,
        "repo-submodule-cleanup",
        workspace,
        "topic-submodule-sibling",
        "feature/submodule-sibling",
        evidence,
        allowed_paths=("tests/",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    retained_root = tmp_path / "retained-content"
    retained_root.mkdir()
    subprocess.run(
        [
            "git",
            "-C",
            str(first.clone),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            submodule_url,
            "vendor/submodule",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    submodule_checkout = first.clone / "vendor" / "submodule"
    submodule_only_file = submodule_checkout / "local-only.txt"
    submodule_only_file.write_text("local submodule content\n", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "-C",
            str(submodule_checkout),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "add",
            "local-only.txt",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(submodule_checkout),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "local-only submodule commit",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    submodule_branch = run_git(submodule_checkout, "symbolic-ref", "--short", "HEAD")
    submodule_commit = run_git(submodule_checkout, "rev-parse", "HEAD")
    remote_commit = subprocess.run(
        [
            "git",
            "-C",
            str(submodule_root / "repo.git"),
            "cat-file",
            "-e",
            submodule_commit,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert remote_commit.returncode != 0
    submodule_bundle = retained_root / "submodule.bundle"
    run_git(submodule_checkout, "bundle", "create", str(submodule_bundle), "--all")

    ignored_file = first.clone / "caller-retained.bin"
    ignored_file.write_bytes(b"ignored local-only content\n")
    exclude_path = git_metadata_path(first.clone, "info/exclude")
    with exclude_path.open("a", encoding="utf-8") as stream:
        stream.write("caller-retained.bin\n")
    retained_ignored_file = retained_root / "caller-retained.bin"
    retained_ignored_file.write_bytes(ignored_file.read_bytes())

    run_git(first.clone, "add", ".gitmodules", "vendor/submodule")
    subprocess.run(
        [
            "git",
            "-C",
            str(first.clone),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "add clean submodule",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    retained_head = run_git(first.clone, "rev-parse", "HEAD")
    assert (
        run_git(first.clone, "check-ignore", "--quiet", "--", "caller-retained.bin")
        == ""
    )
    assert not run_git(
        first.clone,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )

    proof = rtc.cleanup(first.request, apply=True)

    assert proof.removed
    assert proof.evidence == "linked-superproject-head"
    assert not first.clone.exists()
    assert retained_ignored_file.read_bytes() == b"ignored local-only content\n"
    restore = tmp_path / "submodule-restore"
    subprocess.run(
        ["git", "init", str(restore)], check=True, capture_output=True, text=True
    )
    run_git(
        restore,
        "fetch",
        str(submodule_bundle),
        f"refs/heads/{submodule_branch}",
    )
    assert (
        run_git(restore, "show", f"{submodule_commit}:local-only.txt")
        == "local submodule content"
    )
    assert sibling.clone.is_dir()
    assert (
        run_git(
            workspace,
            "show-ref",
            "--verify",
            "refs/heads/feature/submodule-cleanup",
        )
        == retained_head
    )
    assert run_git(workspace, "cat-file", "-e", f"{retained_head}^{{commit}}") == ""
    worktree_list = run_git(workspace, "worktree", "list")
    assert str(first.clone) not in worktree_list
    assert str(sibling.clone) in worktree_list


def test_linked_cleanup_holds_dirty_submodule_before_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dirty submodule content remains in place when cleanup is requested."""
    _, remote_url = init_remote(tmp_path)
    submodule_root = tmp_path / "submodule-source"
    submodule_root.mkdir()
    _, submodule_url = init_remote(submodule_root)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    patch_linked_checkout_identity(monkeypatch)
    prepared = rtc.request(
        remote_url,
        "repo-dirty-submodule",
        workspace,
        "topic-dirty-submodule",
        "feature/dirty-submodule",
        evidence,
        allowed_paths=("src/",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(prepared.clone),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            submodule_url,
            "vendor/submodule",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(prepared.clone, "add", ".gitmodules", "vendor/submodule")
    subprocess.run(
        [
            "git",
            "-C",
            str(prepared.clone),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "add clean submodule",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dirty = prepared.clone / "vendor" / "submodule" / "untracked.txt"
    dirty.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(
        rtc.RepositoryTopicCloneError, match="dirty-worktree-index-or-untracked"
    ):
        rtc.cleanup(prepared.request, apply=True)

    assert dirty.read_text(encoding="utf-8") == "preserve\n"
    assert prepared.clone.is_dir()
    assert run_git(
        workspace, "show-ref", "--verify", "refs/heads/feature/dirty-submodule"
    )


def test_linked_cleanup_surfaces_native_remove_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native removal errors remain visible and keep the registered worktree."""
    _, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    patch_linked_checkout_identity(monkeypatch)
    prepared = rtc.request(
        remote_url,
        "repo-unknown-remove-error",
        workspace,
        "topic-unknown-remove-error",
        "feature/unknown-remove-error",
        evidence,
        allowed_paths=("src/",),
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    original_run_git = rtc._run_git

    def reject_native_remove(
        repo: Path, args: Sequence[str], *, pass_fds: tuple[int, ...] = ()
    ) -> str:
        if tuple(args[:2]) == ("worktree", "remove"):
            assert args[2] == "--force"
            raise rtc.GitCommandError(repo, args, "fatal: permission denied")
        return original_run_git(repo, args, pass_fds=pass_fds)

    monkeypatch.setattr(rtc, "_run_git", reject_native_remove)
    with pytest.raises(rtc.RepositoryTopicCloneError, match="permission denied"):
        rtc.cleanup(prepared.request, apply=True)

    assert prepared.clone.is_dir()
    assert str(prepared.clone) in run_git(workspace, "worktree", "list")
    assert run_git(
        workspace, "show-ref", "--verify", "refs/heads/feature/unknown-remove-error"
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
        remote_url,
        "repo-offline",
        workspace,
        "topic-offline",
        "feature/local",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    original_run_git = rtc._run_git

    def fail_main_fetch(path: Path, args: list[str]) -> str:
        if list(args) == ["fetch", "origin", "main"]:
            raise rtc.GitCommandError(path, args, "offline")
        return original_run_git(path, args)

    monkeypatch.setattr(rtc, "_run_git", fail_main_fetch)
    reused = rtc.request(
        remote_url,
        "repo-offline",
        workspace,
        "topic-offline",
        "feature/local",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    assert reused.clone == initial.clone

    with pytest.raises(rtc.GitCommandError, match="offline"):
        rtc.request(
            remote_url,
            "repo-offline",
            workspace,
            "topic-offline",
            "feature/new",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
            remote_url,
            "../repo",
            workspace,
            "topic",
            "feature/topic",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )

    external = tmp_path / "external"
    external.mkdir()
    (workspace / "workspace").symlink_to(external, target_is_directory=True)
    with pytest.raises(rtc.RepositoryTopicCloneError, match="symlink"):
        rtc.request(
            remote_url,
            "repo",
            workspace,
            "topic",
            "feature/topic",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )
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
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        "requested-repo",
        workspace,
        "topic",
        "feature/topic",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        "requested-repo",
        workspace,
        "topic",
        "feature/topic",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    assert prepared.clone.is_dir()
    run_git(prepared.clone, "push", "-u", "origin", "feature/topic")
    removed = rtc.cleanup(prepared.request, apply=True)
    assert removed.removed
    assert not prepared.clone.exists()


@pytest.mark.parametrize(
    "root_kind",
    (
        "non-repository",
        "nested",
        "missing-ignore",
        "untracked-ignore",
        "global-ignore",
        "info-ignore",
    ),
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
            workspace,
            ignore_content="# repository has no workspace rule\n",
            global_ignore=True,
        )
    else:
        workspace = tmp_path / "parent"
        init_workspace_parent(
            workspace,
            ignore_content="# repository has no workspace rule\n",
            info_ignore=True,
        )

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.request(
            remote_url,
            "invalid-root",
            workspace,
            f"invalid-{root_kind}",
            "feature/invalid",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        repo_name,
        workspace,
        topic,
        "feature/merge",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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

    with pytest.raises(
        rtc.RepositoryTopicCloneError, match="merge-conflict-preserve"
    ) as raised:
        rtc.merge_main(receipt.request)
    inventory_path = receipt.clone / ".agent-canon" / "conflict-preservation.json"
    assert inventory_path.is_file()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert inventory["conflict_paths"] == ["base.txt"]
    assert "inventory=" in str(raised.value)
    assert "base" in inventory["paths"][0]["stages"]
    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-conflict-preserve"):
        rtc.request(
            remote_url,
            "repo-conflict",
            workspace,
            "topic-conflict",
            "feature/conflict",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )


def test_finalize_merge_requires_preservation_plan_and_readback(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    source = tmp_path / "source"
    receipt = rtc.request(
        remote_url,
        "repo-finalize",
        workspace,
        "topic-finalize",
        "feature/finalize",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    run_git(receipt.clone, "config", "user.name", "Test")
    run_git(receipt.clone, "config", "user.email", "test@example.invalid")
    (receipt.clone / "base.txt").write_text("topic\n", encoding="utf-8")
    run_git(receipt.clone, "add", "base.txt")
    run_git(receipt.clone, "commit", "-m", "topic conflict")
    run_git(receipt.clone, "push", "-u", "origin", "feature/finalize")

    (source / "base.txt").write_text("main\n", encoding="utf-8")
    run_git(source, "add", "base.txt")
    run_git(source, "commit", "-m", "main conflict")
    run_git(source, "push", "origin", "main")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-conflict-preserve"):
        rtc.merge_main(receipt.request)
    inventory_path = receipt.clone / ".agent-canon" / "conflict-preservation.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    with pytest.raises(rtc.RepositoryTopicCloneError, match="preservation plan"):
        rtc.finalize_merge_main(receipt.request)

    source_hunk = inventory["paths"][0]["hunks"]["base_to_ours"][0]
    plan = {
        "repository": inventory["repository"],
        "base": inventory["base"]["commit"],
        "head": inventory["ours"]["commit"],
        "merge_base": inventory["merge_base"],
        "selected_cause": "the two branch edits target one line",
        "expected_mechanism": "resolve the line manually and keep the candidate value",
        "exact_edit_delta": "retain base.txt line one from ours",
        "paths": [
            {
                "path": "base.txt",
                "owner": "integration_executor",
                "disposition": "manual",
                "operation": "manual",
                "rationale": "the captured stages are reviewed before manual resolution",
                "expected_edit_delta": "retain topic line",
                "unaffected_content": [
                    {
                        "path": "base.txt",
                        "hunk_identity": {
                            "source_sha256": source_hunk["sha256"],
                            "source_header": source_hunk["header"],
                            "required_lines": ["+topic\n"],
                        },
                    }
                ],
            }
        ],
    }
    plan_path = receipt.clone / ".agent-canon" / "conflict-preservation-plan.json"
    plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
    (receipt.clone / "base.txt").write_text("topic\n", encoding="utf-8")
    run_git(receipt.clone, "add", "base.txt")
    finalized = rtc.finalize_merge_main(receipt.request)
    assert finalized.merged_sha != finalized.candidate_sha
    assert run_git(receipt.clone, "status", "--porcelain") == ""


def test_cleanup_without_publication_packet_matches_remote_head(tmp_path: Path) -> None:
    """A clean pushed topic head is sufficient for dry-run and apply cleanup."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-no-packet",
        workspace,
        "topic-no-packet",
        "feature/cleanup",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        "repo-legacy",
        workspace,
        "topic-legacy",
        "feature/cleanup",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        "repo-legacy-invalid",
        workspace,
        "topic-legacy-invalid",
        "feature/cleanup",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        "repo-remote-mismatch",
        workspace,
        "topic-remote-mismatch",
        "feature/cleanup",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")

    source = tmp_path / "source"
    run_git(source, "fetch", "origin", "feature/cleanup")
    run_git(source, "checkout", "-B", "feature/cleanup", "origin/feature/cleanup")
    run_git(
        source,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "remote advance",
    )
    run_git(source, "push", "origin", "feature/cleanup")

    with pytest.raises(
        rtc.RepositoryTopicCloneError, match="remote branch head mismatch"
    ):
        rtc.cleanup(request.request, apply=False)
    assert request.clone.exists()


def test_cleanup_rejects_partial_optional_publication_packet(tmp_path: Path) -> None:
    """Lifecycle packet fields are optional together, never as an invented half-set."""
    remote, remote_url = init_remote(tmp_path)
    evidence = write_evidence(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-partial",
        workspace,
        "topic-partial",
        "feature/cleanup",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        repo_name,
        workspace,
        topic,
        "feature/cleanup",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
    (workspace / ".gitignore").write_text(
        "# placement ownership drift\n", encoding="utf-8"
    )
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
        remote_url,
        "repo-four",
        workspace,
        "topic-fail",
        "feature/fail",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        remote_url,
        "repo-five",
        workspace,
        "topic-clean",
        "feature/clean",
        evidence,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    (clone.clone / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(
        rtc.RepositoryTopicCloneError, match="dirty-worktree-index-or-untracked"
    ):
        rtc.request(
            remote_url,
            "repo-five",
            workspace,
            "topic-clean",
            "feature/clean",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )

    (clone.clone / "dirty.txt").unlink()
    run_git(clone.clone, "checkout", "--detach", "HEAD")
    with pytest.raises(rtc.RepositoryTopicCloneError, match="detached"):
        rtc.request(
            remote_url,
            "repo-five",
            workspace,
            "topic-clean",
            "feature/clean",
            evidence,
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
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
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    rtc.merge_main(request.request, policy=Spy())
    assert events == ["prepare:PrepareReceipt", "merge_main:MergeMainReceipt"]
