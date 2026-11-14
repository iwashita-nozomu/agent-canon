"""Tests for repository-topic clone lifecycle semantics."""
# ruff: noqa: D103,D104,D107

# @dependency-start
# contract test
# responsibility Verifies repository-topic clone CLI preparation, Git integration, publication readback, and cleanup.
# upstream design ../../documents/rule/repository-topic-clone.md repository-topic clone lifecycle contract
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/repository_topic_clone.rs owns lifecycle behavior exercised by this test
# downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_headers.rs validates this test header
# @dependency-end

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE = (
    os.environ.get("AGENT_CANON_NATIVE_BIN")
    or os.environ.get("AGENT_CANON_CLI")
    or str(PROJECT_ROOT / "tools" / "bin" / "agent-canon")
)
CHECKOUT_MODE_LINKED = "linked-worktree"
CHECKOUT_MODE_INDEPENDENT = "independent-clone"
MARKER_PREFIX = "repository-topic-clone"
LEGACY_MARKER_PREFIX = "agent-canon.topic"
CANONICAL_MARKER_FIELDS = ("repository", "topic", "branch", "url")
LEGACY_MARKER_FIELDS = ("topic", "role", "module", "url", "branch", "placement")


class RepositoryTopicCloneError(RuntimeError):
    """A failed native lifecycle invocation reported by the command adapter."""


class GitCommandError(RepositoryTopicCloneError):
    """A native lifecycle Git command failed."""


@dataclass(frozen=True)
class RepositoryTopicCloneRequest:
    url: str
    repository: str
    workspace_root: Path
    topic: str
    branch: str
    checkout_mode: str


@dataclass(frozen=True)
class PrepareReceipt:
    request: RepositoryTopicCloneRequest
    clone: Path
    branch: str
    candidate_sha: str
    candidate_tree: str
    clone_dev: int | None = None
    clone_ino: int | None = None


@dataclass(frozen=True)
class MergeMainReceipt:
    request: RepositoryTopicCloneRequest
    clone: Path
    candidate_sha: str
    candidate_tree: str
    merged_sha: str
    merged_tree: str
    origin_main_sha: str


@dataclass(frozen=True)
class CleanupProof:
    request: RepositoryTopicCloneRequest
    clone: Path
    removed: bool
    evidence: str


def _run_native(command: str, request: RepositoryTopicCloneRequest, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            NATIVE,
            "repository-topic-clone",
            command,
            "--url",
            request.url,
            "--repo-name",
            request.repository,
            "--workspace-root",
            str(request.workspace_root),
            "--topic",
            request.topic,
            "--branch",
            request.branch,
            "--checkout-mode",
            request.checkout_mode,
            *options,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _fields(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        error_type = GitCommandError if "git -C " in detail else RepositoryTopicCloneError
        raise error_type(detail)
    return dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line
    )


def request(
    url: str,
    repository: str,
    workspace_root: Path | str,
    topic: str,
    branch: str,
    *,
    checkout_mode: str,
) -> PrepareReceipt:
    request_state = RepositoryTopicCloneRequest(
        url, repository, Path(workspace_root), topic, branch, checkout_mode
    )
    fields = _fields(_run_native("prepare", request_state))
    clone = Path(fields["REQUEST_CLONE"])
    identity = clone.stat()
    request_state = RepositoryTopicCloneRequest(
        url, repository, Path(workspace_root).resolve(), topic, fields["REQUEST_BRANCH"], checkout_mode
    )
    return PrepareReceipt(
        request_state,
        clone,
        fields["REQUEST_BRANCH"],
        fields["REQUEST_CANDIDATE_SHA"],
        fields["REQUEST_CANDIDATE_TREE"],
        identity.st_dev,
        identity.st_ino,
    )


def merge_main(request_state: RepositoryTopicCloneRequest) -> MergeMainReceipt:
    fields = _fields(_run_native("merge-main", request_state))
    return MergeMainReceipt(
        request_state,
        Path(fields["MERGE_CLONE"]),
        fields["MERGE_CANDIDATE_SHA"],
        fields["MERGE_CANDIDATE_TREE"],
        fields["MERGE_INTEGRATED_SHA"],
        fields["MERGE_INTEGRATED_TREE"],
        fields["MERGE_ORIGIN_MAIN_SHA"],
    )


def finalize_merge_main(request_state: RepositoryTopicCloneRequest) -> MergeMainReceipt:
    fields = _fields(_run_native("finalize-merge", request_state))
    return MergeMainReceipt(
        request_state,
        Path(fields["MERGE_CLONE"]),
        fields["MERGE_CANDIDATE_SHA"],
        fields["MERGE_CANDIDATE_TREE"],
        fields["MERGE_INTEGRATED_SHA"],
        fields["MERGE_INTEGRATED_TREE"],
        fields["MERGE_ORIGIN_MAIN_SHA"],
    )


def cleanup(
    request_state: RepositoryTopicCloneRequest,
    *,
    candidate_cas: Path | str | None = None,
    pr_lifecycle: Path | str | None = None,
    publication_readback: Path | str | None = None,
    apply: bool,
) -> CleanupProof:
    options: list[str] = []
    for name, value in (
        ("--candidate-cas", candidate_cas),
        ("--pr-lifecycle", pr_lifecycle),
        ("--publication-readback", publication_readback),
    ):
        if value is not None:
            options.extend((name, str(value)))
    if apply:
        options.append("--apply")
    fields = _fields(_run_native("cleanup", request_state, *options))
    value = fields["CLEANUP"]
    path, action = value.rsplit(":", 1)
    return CleanupProof(request_state, Path(path), action == "removed", "native")


def verify_publication(
    request_state: RepositoryTopicCloneRequest,
    *,
    candidate_cas: Path | str,
    pr_lifecycle: Path | str,
    publication_readback: Path | str | None = None,
) -> dict[str, object]:
    options = ["--candidate-cas", str(candidate_cas), "--pr-lifecycle", str(pr_lifecycle)]
    if publication_readback is not None:
        options.extend(("--publication-readback", str(publication_readback)))
    fields = _fields(_run_native("verify-publication", request_state, *options))
    return {"state": fields.get("PUBLICATION_STATE", "")}


def topic_slug(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()


def _parse_args(argv: list[str]) -> object:
    return subprocess.run(
        [NATIVE, "repository-topic-clone", *argv],
        check=False,
        capture_output=True,
        text=True,
    )


rtc = SimpleNamespace(
    CHECKOUT_MODE_LINKED=CHECKOUT_MODE_LINKED,
    CHECKOUT_MODE_INDEPENDENT=CHECKOUT_MODE_INDEPENDENT,
    MARKER_PREFIX=MARKER_PREFIX,
    LEGACY_MARKER_PREFIX=LEGACY_MARKER_PREFIX,
    CANONICAL_MARKER_FIELDS=CANONICAL_MARKER_FIELDS,
    LEGACY_MARKER_FIELDS=LEGACY_MARKER_FIELDS,
    RepositoryTopicCloneError=RepositoryTopicCloneError,
    GitCommandError=GitCommandError,
    RepositoryTopicCloneRequest=RepositoryTopicCloneRequest,
    PrepareReceipt=PrepareReceipt,
    MergeMainReceipt=MergeMainReceipt,
    CleanupProof=CleanupProof,
    request=request,
    merge_main=merge_main,
    finalize_merge_main=finalize_merge_main,
    cleanup=cleanup,
    verify_publication=verify_publication,
    topic_slug=topic_slug,
    _parse_args=_parse_args,
)


def run_git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def install_git_shim(
    tmp_path: Path, extra_cases: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Put a narrow Git fixture on PATH while delegating all other calls."""
    real_git = shutil.which("git")
    assert real_git
    shim_root = tmp_path / "git-shim"
    shim_root.mkdir(exist_ok=True)
    shim = shim_root / "git"
    shim.write_text(
        "#!/bin/sh\n"
        f"real_git={shlex.quote(real_git)}\n"
        "repo=\n"
        "if [ \"${1:-}\" = \"-C\" ]; then repo=$2; shift 2; fi\n"
        + extra_cases
        + "if [ -n \"$repo\" ]; then exec \"$real_git\" -C \"$repo\" \"$@\"; fi\n"
        + "exec \"$real_git\" \"$@\"\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim_root}{os.pathsep}{os.environ['PATH']}")


def git_metadata_path(root: Path, name: str) -> Path:
    """Resolve a Git path from this checkout, preserving absolute results."""
    value = Path(run_git(root, "rev-parse", "--git-path", name))
    return root / value


def use_symlinked_git_directory(root: Path) -> None:
    """Represent the existing Git admin directory with a relative .git symlink."""
    admin = Path(run_git(root, "rev-parse", "--absolute-git-dir"))
    git_entry = root / ".git"
    git_entry.unlink()
    git_entry.symlink_to(os.path.relpath(admin, root), target_is_directory=True)


def snapshot_checkout_files(root: Path) -> dict[str, bytes]:
    """Read checkout files except Git metadata and symbolic links."""
    snapshot: dict[str, bytes] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".git" in relative.parts or path.is_symlink():
            continue
        if path.is_file():
            snapshot[relative.as_posix()] = path.read_bytes()
    return snapshot


def test_computed_clone_path_uses_parent_boundary_for_escaping_symlinks(
    tmp_path: Path,
) -> None:
    """Clone projection rejects a topic path whose symlink leaves the parent."""
    parent = tmp_path / "parent"
    init_workspace_parent(parent)
    workspace = parent / "workspace"
    workspace.mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (workspace / "topic").symlink_to(outside, target_is_directory=True)
    request = dict(
        url="https://example.invalid/repo.git",
        repository="repo",
        workspace_root=parent,
        topic="topic",
        branch="feature/topic",
        checkout_mode=CHECKOUT_MODE_INDEPENDENT,
    )
    with pytest.raises(RepositoryTopicCloneError, match="symlinked path component"):
        rtc.request(**request)
    assert not list(outside.iterdir())
    assert run_git(parent, "status", "--porcelain") == ""


def init_remote(tmp_path: Path) -> tuple[Path, str]:
    remote = tmp_path / "repo.git"
    source = tmp_path / "source"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "init", "-b", "main", str(source)], check=True, capture_output=True
    )
    run_git(source, "config", "user.name", "Test")
    run_git(source, "config", "user.email", "test@example.invalid")
    (source / "base.txt").write_text("base\n", encoding="utf-8")
    run_git(source, "add", "base.txt")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
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


def install_legacy_module_markers(
    clone: Path,
    request: rtc.RepositoryTopicCloneRequest,
    *,
    role: str = "module",
    module: str | None = None,
    placement: str = "workspace-continuation",
) -> None:
    """Replace canonical markers with the historical module marker namespace."""
    for field in (
        *rtc.CANONICAL_MARKER_FIELDS,
        "owner-evidence-sha256",
        "branch-source",
    ):
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
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    assert not (initial.clone / ".agent-canon" / "writer-target.json").exists()
    run_git(initial.clone, "config", "user.name", "Test")
    run_git(initial.clone, "config", "user.email", "test@example.invalid")
    reused_local = rtc.request(
        remote_url,
        repo_name,
        workspace,
        topic,
        "feature/local",
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


def test_prepare_rejects_nested_parent_repo_without_mutating_ancestor(
    tmp_path: Path,
) -> None:
    """A computed directory inside the anchor repo cannot inherit its Git identity."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    branch = run_git(workspace, "symbolic-ref", "--short", "HEAD")
    request = dict(
        url=remote_url,
        repository="repo-nested-parent",
        workspace_root=workspace,
        topic="topic-nested-parent",
        branch=branch,
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    nested = (
        workspace
        / "workspace"
        / rtc.topic_slug(request["topic"])
        / request["repository"]
    )
    nested.mkdir(parents=True)
    local_data = nested / "local-data.txt"
    local_data.write_text("preserve ancestor-owned checkout data\n", encoding="utf-8")
    assert not run_git(workspace, "status", "--porcelain")
    common_config = git_metadata_path(workspace, "config")
    index_path = git_metadata_path(workspace, "index")
    exclude_path = git_metadata_path(workspace, "info/exclude")
    before_config = common_config.read_bytes()
    before_index = index_path.read_bytes()
    before_exclude = exclude_path.read_bytes()
    before_refs = run_git(workspace, "show-ref")
    before_head = run_git(workspace, "rev-parse", "HEAD")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="repository-mismatch"):
        rtc.request(**request)

    assert (
        local_data.read_text(encoding="utf-8")
        == "preserve ancestor-owned checkout data\n"
    )
    assert not (nested / ".git").exists()
    assert common_config.read_bytes() == before_config
    assert index_path.read_bytes() == before_index
    assert exclude_path.read_bytes() == before_exclude
    assert run_git(workspace, "show-ref") == before_refs
    assert run_git(workspace, "rev-parse", "HEAD") == before_head
    assert not run_git(workspace, "status", "--porcelain")


@pytest.mark.parametrize(
    "symlink_git_entry", [False, True], ids=["gitfile", "gitdir-symlink"]
)
@pytest.mark.parametrize("worktree_config_enabled", [False, True])
def test_prepare_reuses_unmarked_linked_worktree_from_exact_git_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symlink_git_entry: bool,
    worktree_config_enabled: bool,
) -> None:
    """A clean unmarked native worktree is identified by its path and Git facts."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    request = dict(
        url=remote_url,
        repository="repo-unmarked-linked",
        workspace_root=workspace,
        topic="topic-unmarked-linked",
        branch="feature/unmarked-linked",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    clone = (
        workspace
        / "workspace"
        / rtc.topic_slug(request["topic"])
        / request["repository"]
    )
    clone.parent.mkdir(parents=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "worktree",
            "add",
            "-b",
            request["branch"],
            str(clone),
            "main",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if worktree_config_enabled:
        run_git(clone, "config", "extensions.worktreeConfig", "true")
    if symlink_git_entry:
        use_symlinked_git_directory(clone)
    config_path = git_metadata_path(clone, "config.worktree")
    index_path = git_metadata_path(clone, "index")
    before_index = index_path.read_bytes()
    before_files = snapshot_checkout_files(clone)
    before_head = run_git(clone, "rev-parse", "HEAD")
    assert not config_path.exists()

    with pytest.raises(rtc.RepositoryTopicCloneError, match="actual-branch-mismatch"):
        rtc.request(**{**request, "branch": "feature/unmatched"})

    assert not config_path.exists()
    assert index_path.read_bytes() == before_index
    assert snapshot_checkout_files(clone) == before_files

    prepared = rtc.request(**request)

    assert prepared.clone == clone
    assert not (clone / ".agent-canon" / "writer-target.json").exists()
    assert config_path.is_file()
    assert (
        run_git(
            clone,
            "config",
            "--worktree",
            "--get",
            f"{rtc.MARKER_PREFIX}.branch",
        )
        == request["branch"]
    )
    assert run_git(clone, "rev-parse", "HEAD") == before_head
    assert index_path.read_bytes() == before_index
    assert snapshot_checkout_files(clone) == before_files
    assert not run_git(clone, "status", "--porcelain")


@pytest.mark.parametrize(
    "symlink_git_entry", [False, True], ids=["gitfile", "gitdir-symlink"]
)
def test_prepare_holds_unmarked_linked_worktree_from_foreign_common_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, symlink_git_entry: bool
) -> None:
    """Matching branch and remote do not adopt a worktree registered elsewhere."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    foreign_workspace = tmp_path / "foreign-parent"
    init_workspace_parent(foreign_workspace)
    run_git(foreign_workspace, "remote", "add", "origin", remote_url)
    request = dict(
        url=remote_url,
        repository="repo-foreign-common-dir",
        workspace_root=workspace,
        topic="topic-foreign-common-dir",
        branch="feature/foreign-common-dir",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    clone = (
        workspace
        / "workspace"
        / rtc.topic_slug(request["topic"])
        / request["repository"]
    )
    clone.parent.mkdir(parents=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(foreign_workspace),
            "worktree",
            "add",
            "-b",
            request["branch"],
            str(clone),
            "main",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(clone, "config", "extensions.worktreeConfig", "true")
    if symlink_git_entry:
        use_symlinked_git_directory(clone)
    before_status = run_git(clone, "status", "--porcelain")
    assert not before_status

    with pytest.raises(rtc.RepositoryTopicCloneError, match="checkout-mode-mismatch"):
        rtc.request(**request)

    assert clone.is_dir()
    assert run_git(clone, "symbolic-ref", "--short", "HEAD") == request["branch"]
    assert run_git(clone, "status", "--porcelain") == before_status


def test_prepare_and_merge_main_hold_dirty_independent_checkout_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dirty user files remain untouched and block checkout reuse or merge."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    request = dict(
        url=remote_url,
        repository="repo-independent-dirty-metadata",
        workspace_root=workspace,
        topic="topic-independent-dirty-metadata",
        branch="feature/independent-dirty-metadata",
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    prepared = rtc.request(**request)
    dirty = prepared.clone / "untracked.txt"
    dirty.write_text("preserve\n", encoding="utf-8")
    before_config = git_metadata_path(prepared.clone, "config").read_bytes()

    with pytest.raises(
        rtc.RepositoryTopicCloneError,
        match="prepare collision: dirty-worktree-index-or-untracked",
    ):
        rtc.request(**request)
    assert dirty.read_text(encoding="utf-8") == "preserve\n"
    with pytest.raises(
        rtc.RepositoryTopicCloneError,
        match="merge-main hold: dirty-worktree-index-or-untracked",
    ):
        rtc.merge_main(prepared.request)

    assert dirty.read_text(encoding="utf-8") == "preserve\n"
    assert git_metadata_path(prepared.clone, "config").read_bytes() == before_config
    assert prepared.clone.is_dir()


@pytest.mark.parametrize("mode", [0o700, 0o755])
def test_linked_worktrees_use_native_common_dir_and_per_worktree_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int
) -> None:
    """Linked topics share Git objects but keep indexes and markers separate."""
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    workspace.chmod(mode)
    run_git(workspace, "remote", "add", "origin", remote_url)

    first = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-first",
        "feature/first",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    second = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-second",
        "feature/second",
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
    prepared = rtc.request(
        remote_url,
        "repo-linked",
        anchor,
        "topic-nested",
        "feature/nested",
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
            checkout_mode=rtc.CHECKOUT_MODE_LINKED,
        )

    assert not target.exists()
    assert not (workspace / "workspace").exists()
    assert run_git(workspace, "worktree", "list", "--porcelain") == before_worktrees
    assert run_git(workspace, "show-ref") == before_refs


def test_request_requires_explicit_checkout_mode(tmp_path: Path) -> None:
    """The public request API cannot silently select a checkout implementation."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    with pytest.raises(TypeError):
        rtc.request(
            remote_url,
            "repo-required-mode",
            workspace,
            "topic-required-mode",
            "feature/required-mode",
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
    ]
    result = rtc._parse_args(required_args)
    assert result.returncode == 2
    assert "required" in result.stderr


def test_linked_foreign_occupant_does_not_mutate_common_git_state(
    tmp_path: Path,
) -> None:
    """An unverified linked occupant is rejected before config or lifecycle mutation."""
    _, remote_url = init_remote(tmp_path)
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

    with pytest.raises(rtc.RepositoryTopicCloneError, match="actual-branch-mismatch"):
        rtc.request(
            remote_url,
            "repo-foreign",
            workspace,
            "foreign-topic",
            "feature/request",
            checkout_mode=rtc.CHECKOUT_MODE_LINKED,
        )

    foreign_request = rtc.RepositoryTopicCloneRequest(
        url=remote_url,
        repository="repo-foreign",
        workspace_root=workspace,
        topic="foreign-topic",
        branch="feature/request",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    with pytest.raises(rtc.RepositoryTopicCloneError, match="branch mismatch"):
        rtc.finalize_merge_main(foreign_request)

    assert common_config.read_bytes() == before_config
    assert run_git(workspace, "worktree", "list", "--porcelain") == before_worktrees
    assert run_git(workspace, "show-ref") == before_refs
    assert target.is_dir()
    assert run_git(target, "symbolic-ref", "--short", "HEAD") == "feature/foreign"


def test_linked_reuse_preserves_branch_and_holds_dirty_wip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exact linked reuse keeps its branch and refuses to adopt dirty checkout data."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    request = dict(
        url=remote_url,
        repository="repo-linked",
        workspace_root=workspace,
        topic="topic-first",
        branch="feature/first",
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
            checkout_mode=rtc.CHECKOUT_MODE_LINKED,
        )

    dirty = prepared.clone / "first.py"
    dirty.write_text("preserve\n", encoding="utf-8")
    before_files = snapshot_checkout_files(prepared.clone)
    index_path = git_metadata_path(prepared.clone, "index")
    config_path = git_metadata_path(prepared.clone, "config.worktree")
    exclude_path = git_metadata_path(prepared.clone, "info/exclude")
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

    with pytest.raises(rtc.RepositoryTopicCloneError, match="dirty-worktree-index-or-untracked"):
        rtc.request(**request)
    assert dirty.read_text(encoding="utf-8") == "preserve\n"
    assert snapshot_checkout_files(prepared.clone) == before_files
    assert index_path.read_bytes() == before_index
    assert config_path.read_bytes() == before_config
    assert exclude_path.read_bytes() == before_excludes
    assert (
        run_git(
            prepared.clone,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        == before_status
    )
    assert run_git(prepared.clone, "rev-parse", "HEAD") == before_head
    assert (
        run_git(prepared.clone, "symbolic-ref", "--short", "HEAD") == before_branch
    )


def test_cleanup_ignores_retired_marker_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retired marker field cannot change exact checkout cleanup authority."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    request = dict(
        url=remote_url,
        repository="repo-evidence-refresh",
        workspace_root=workspace,
        topic="topic-evidence-refresh",
        branch="feature/evidence-refresh",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )

    prepared = rtc.request(**request)
    run_git(
        prepared.clone,
        "config",
        "--worktree",
        f"{rtc.MARKER_PREFIX}.owner-evidence-sha256",
        "stale-from-older-marker",
    )

    continued = rtc.request(**request)
    assert continued.clone == prepared.clone
    proof = rtc.cleanup(continued.request, apply=False)
    assert not proof.removed
    removed = rtc.cleanup(continued.request, apply=True)
    assert removed.removed
    assert not continued.clone.exists()


def test_prepare_holds_dirty_linked_checkout_without_rewriting_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dirty checkout content is preserved and prepare refuses to mutate it."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    request = dict(
        url=remote_url,
        repository="repo-dirty-evidence",
        workspace_root=workspace,
        topic="topic-dirty-evidence",
        branch="feature/dirty-evidence",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )

    prepared = rtc.request(**request)
    dirty = prepared.clone / "untracked.txt"
    dirty.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(rtc.RepositoryTopicCloneError, match="dirty-worktree-index-or-untracked"):
        rtc.request(**request)

    assert dirty.read_text(encoding="utf-8") == "preserve\n"
    assert run_git(
        prepared.clone,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )


@pytest.mark.parametrize(
    "linked_workspace_root", [False, True], ids=["main-parent", "linked-parent"]
)
@pytest.mark.parametrize(
    "symlink_git_entry", [False, True], ids=["gitfile", "gitdir-symlink"]
)
def test_prepare_holds_external_info_exclude_symlink_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    linked_workspace_root: bool,
    symlink_git_entry: bool,
) -> None:
    """Preparing a checkout never writes through Git's info/exclude symlink."""
    _, remote_url = init_remote(tmp_path)
    anchor = tmp_path / "parent"
    init_workspace_parent(anchor)
    run_git(anchor, "remote", "add", "origin", remote_url)
    workspace = anchor
    if linked_workspace_root:
        workspace = tmp_path / "parent-linked"
        run_git(anchor, "worktree", "add", "--detach", str(workspace), "HEAD")
    request = dict(
        url=remote_url,
        repository="repo-external-exclude",
        workspace_root=workspace,
        topic="topic-external-exclude",
        branch="feature/external-exclude",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )

    prepared = rtc.request(**request)
    if symlink_git_entry:
        use_symlinked_git_directory(prepared.clone)
    exclude = git_metadata_path(prepared.clone, "info/exclude")
    external_exclude = tmp_path / "outside-info-exclude"
    external_before = b".agent-canon/*\n"
    external_exclude.write_bytes(external_before)
    exclude.unlink()
    exclude.symlink_to(external_exclude)

    index = git_metadata_path(prepared.clone, "index")
    config = git_metadata_path(prepared.clone, "config.worktree")
    before_index = index.read_bytes()
    before_config = config.read_bytes()
    before_files = snapshot_checkout_files(prepared.clone)
    before_head = run_git(prepared.clone, "rev-parse", "HEAD")
    before_branch = run_git(prepared.clone, "symbolic-ref", "--short", "HEAD")
    before_status = run_git(prepared.clone, "status", "--porcelain=v1")
    assert before_status == ""

    reused = rtc.request(**request)

    assert reused.clone == prepared.clone
    assert external_exclude.read_bytes() == external_before
    assert exclude.is_symlink()
    assert exclude.resolve() == external_exclude.resolve()
    assert index.read_bytes() == before_index
    assert config.read_bytes() == before_config
    assert snapshot_checkout_files(prepared.clone) == before_files
    assert run_git(prepared.clone, "rev-parse", "HEAD") == before_head
    assert run_git(prepared.clone, "symbolic-ref", "--short", "HEAD") == before_branch
    assert run_git(prepared.clone, "status", "--porcelain=v1") == before_status


def test_prepare_rejects_foreign_topic_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mismatched topic marker remains a collision regardless of other metadata."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    request = dict(
        url=remote_url,
        repository="repo-unknown-owner",
        workspace_root=workspace,
        topic="topic-unknown-owner",
        branch="feature/unknown-owner",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )

    prepared = rtc.request(**request)
    run_git(
        prepared.clone,
        "config",
        "--worktree",
        f"{rtc.MARKER_PREFIX}.topic",
        "foreign-topic",
    )

    with pytest.raises(rtc.RepositoryTopicCloneError, match="topic-mismatch"):
        rtc.request(**request)

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


def test_linked_merge_conflict_keeps_native_merge_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A linked checkout retains merge state in the native Git index."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    request = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-conflict",
        "feature/conflict",
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

    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-conflict"):
        rtc.merge_main(request.request)
    assert run_git(clone, "rev-parse", "MERGE_HEAD")
    assert run_git(clone, "ls-files", "-u")
    assert run_git(clone, "status", "--porcelain")


def test_linked_cleanup_removes_one_worktree_and_keeps_branch_and_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native cleanup unregisters one worktree without deleting its branch or sibling."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    first = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-first",
        "feature/first",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    second = rtc.request(
        remote_url,
        "repo-linked",
        workspace,
        "topic-second",
        "feature/second",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    run_git(first.clone, "push", "origin", "feature/first")
    run_git(second.clone, "push", "origin", "feature/second")
    run_git(tmp_path / "source", "push", "origin", "--delete", "feature/first")
    proof = rtc.cleanup(first.request, apply=True)
    assert proof.removed
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
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)

    first = rtc.request(
        remote_url,
        "repo-submodule-cleanup",
        workspace,
        "topic-submodule-cleanup",
        "feature/submodule-cleanup",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    sibling = rtc.request(
        remote_url,
        "repo-submodule-cleanup",
        workspace,
        "topic-submodule-sibling",
        "feature/submodule-sibling",
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
            "--hash",
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
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    prepared = rtc.request(
        remote_url,
        "repo-dirty-submodule",
        workspace,
        "topic-dirty-submodule",
        "feature/dirty-submodule",
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
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    run_git(workspace, "remote", "add", "origin", remote_url)
    prepared = rtc.request(
        remote_url,
        "repo-unknown-remove-error",
        workspace,
        "topic-unknown-remove-error",
        "feature/unknown-remove-error",
        checkout_mode=rtc.CHECKOUT_MODE_LINKED,
    )
    install_git_shim(
        tmp_path,
        'if [ "${1:-}:${2:-}" = "worktree:remove" ]; then echo "fatal: permission denied" >&2; exit 128; fi\n',
        monkeypatch,
    )
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
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    initial = rtc.request(
        remote_url,
        "repo-offline",
        workspace,
        "topic-offline",
        "feature/local",
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    install_git_shim(
        tmp_path,
        'if [ "${1:-}:${2:-}:${3:-}" = "fetch:origin:main" ]; then echo "offline" >&2; exit 1; fi\n',
        monkeypatch,
    )
    reused = rtc.request(
        remote_url,
        "repo-offline",
        workspace,
        "topic-offline",
        "feature/local",
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
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )


def test_prepare_rejects_unsafe_repository_name_and_symlink_workspace(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    with pytest.raises(rtc.RepositoryTopicCloneError, match="safe path component"):
        rtc.request(
            remote_url,
            "../repo",
            workspace,
            "topic",
            "feature/topic",
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
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )
    assert list(external.iterdir()) == []


def test_clone_failure_aborts_partial_target_and_preserves_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed clone removes only its newly reserved target, including residue."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    sibling = workspace / "workspace" / "topic-failure" / "sibling"
    sibling.mkdir(parents=True)
    (sibling / "keep.txt").write_text("keep\n", encoding="utf-8")
    install_git_shim(
        tmp_path,
        'if [ "${1:-}" = "clone" ]; then target=$3; mkdir -p "$target/partial/nested"; printf "residue\\n" > "$target/partial/nested/residue.txt"; echo "injected clone failure" >&2; exit 2; fi\n',
        monkeypatch,
    )
    with pytest.raises(rtc.GitCommandError, match="injected clone failure"):
        rtc.request(
            remote_url,
            "repo-failure",
            workspace,
            "topic-failure",
            "feature/failure",
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )

    clone = workspace / "workspace" / "topic-failure" / "repo-failure"
    assert not clone.exists()
    assert (sibling / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_unrelated_dirty_module_does_not_trigger_managed_relation(
    tmp_path: Path,
) -> None:
    _, remote_url = init_remote(tmp_path)
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
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    assert prepared.clone.is_dir()


def test_matching_but_unmanaged_module_uses_generic_relation(
    tmp_path: Path,
) -> None:
    _, remote_url = init_remote(tmp_path)
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
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )
    assert not (workspace / "workspace").exists()


def test_merge_main_before_publication_receipt_is_created(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
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


def test_merge_main_leaves_actual_conflict_in_native_git_state(tmp_path: Path) -> None:
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    source = tmp_path / "source"

    receipt = rtc.request(
        remote_url,
        "repo-conflict",
        workspace,
        "topic-conflict",
        "feature/conflict",
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

    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-conflict"):
        rtc.merge_main(receipt.request)
    assert run_git(receipt.clone, "rev-parse", "MERGE_HEAD")
    unmerged = run_git(receipt.clone, "ls-files", "-u")
    assert "base.txt" in unmerged
    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-in-progress"):
        rtc.request(
            remote_url,
            "repo-conflict",
            workspace,
            "topic-conflict",
            "feature/conflict",
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )


def test_finalize_merge_uses_native_index_and_readback(tmp_path: Path) -> None:
    """A resolved native index can finish after main advances, then catch up."""
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    source = tmp_path / "source"
    receipt = rtc.request(
        remote_url,
        "repo-finalize",
        workspace,
        "topic-finalize",
        "feature/finalize",
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

    with pytest.raises(rtc.RepositoryTopicCloneError, match="merge-conflict"):
        rtc.merge_main(receipt.request)
    captured_main_sha = run_git(receipt.clone, "rev-parse", "MERGE_HEAD")
    assert "base.txt" in run_git(receipt.clone, "ls-files", "-u")
    with pytest.raises(rtc.GitCommandError):
        rtc.finalize_merge_main(receipt.request)

    (receipt.clone / "base.txt").write_text("topic\n", encoding="utf-8")
    run_git(receipt.clone, "add", "base.txt")
    (source / "later-main.txt").write_text(
        "advanced after conflict capture\n", encoding="utf-8"
    )
    run_git(source, "add", "later-main.txt")
    run_git(
        source,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "advance main after conflict capture",
    )
    run_git(source, "push", "origin", "main")
    latest_main_sha = run_git(source, "rev-parse", "HEAD")
    assert latest_main_sha != captured_main_sha

    finalized = rtc.finalize_merge_main(receipt.request)
    assert finalized.origin_main_sha == captured_main_sha
    assert finalized.merged_sha != finalized.candidate_sha
    assert run_git(receipt.clone, "show", "-s", "--format=%P", "HEAD").split() == [
        finalized.candidate_sha,
        captured_main_sha,
    ]
    assert finalized.merged_tree == run_git(receipt.clone, "rev-parse", "HEAD^{tree}")
    assert run_git(receipt.clone, "status", "--porcelain") == ""
    assert run_git(receipt.clone, "rev-parse", "origin/main") == captured_main_sha

    advanced = rtc.merge_main(receipt.request)
    assert advanced.origin_main_sha == latest_main_sha
    assert (receipt.clone / "later-main.txt").read_text(
        encoding="utf-8"
    ) == "advanced after conflict capture\n"
    assert (
        run_git(
            receipt.clone,
            "merge-base",
            "--is-ancestor",
            latest_main_sha,
            advanced.merged_sha,
        )
        == ""
    )
    assert run_git(receipt.clone, "status", "--porcelain") == ""


def test_cleanup_without_publication_packet_matches_remote_head(tmp_path: Path) -> None:
    """A clean pushed topic head is sufficient for dry-run and apply cleanup."""
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-no-packet",
        workspace,
        "topic-no-packet",
        "feature/cleanup",
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")

    dry_run = rtc.cleanup(request.request, apply=False)
    assert not dry_run.removed
    assert request.clone.exists()

    removed = rtc.cleanup(request.request, apply=True)
    assert removed.removed
    assert not request.clone.exists()


def test_stale_binding_directory_does_not_promote_generic_cleanup(
    tmp_path: Path,
) -> None:
    """Stale historical binding artifacts do not select managed cleanup."""
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)
    request = rtc.request(
        remote_url,
        "repo-managed-partial",
        workspace,
        "topic-managed-partial",
        "feature/cleanup",
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


def test_cleanup_accepts_identity_complete_legacy_module_markers_read_only(
    tmp_path: Path,
) -> None:
    """Legacy identity markers remain usable without the retired evidence digest."""
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-legacy",
        workspace,
        "topic-legacy",
        "feature/cleanup",
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")
    install_legacy_module_markers(request.clone, request.request)
    run_git(
        request.clone,
        "config",
        "--local",
        f"{rtc.LEGACY_MARKER_PREFIX}.owner-evidence-sha256",
        "stale-from-older-marker",
    )
    before = run_git(request.clone, "config", "--local", "--list")

    dry_run = rtc.cleanup(request.request, apply=False)
    assert not dry_run.removed
    assert run_git(request.clone, "config", "--local", "--list") == before

    removed = rtc.cleanup(request.request, apply=True)
    assert removed.removed
    assert not request.clone.exists()


def test_cleanup_rejects_legacy_namespace_with_only_retired_digest(
    tmp_path: Path,
) -> None:
    """A legacy namespace with no retained identity fields remains incomplete."""
    _, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-legacy-partial",
        workspace,
        "topic-legacy-partial",
        "feature/cleanup",
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    run_git(request.clone, "push", "-u", "origin", "feature/cleanup")
    install_legacy_module_markers(request.clone, request.request)
    for field in rtc.LEGACY_MARKER_FIELDS:
        run_git(
            request.clone,
            "config",
            "--local",
            "--unset-all",
            f"{rtc.LEGACY_MARKER_PREFIX}.{field}",
        )
    run_git(
        request.clone,
        "config",
        "--local",
        f"{rtc.LEGACY_MARKER_PREFIX}.owner-evidence-sha256",
        "stale-from-older-marker",
    )

    with pytest.raises(rtc.RepositoryTopicCloneError, match="legacy-marker-incomplete"):
        rtc.cleanup(request.request, apply=False)


def test_cleanup_rejects_partial_or_mismatched_legacy_module_markers(
    tmp_path: Path,
) -> None:
    """Legacy compatibility is exact and never accepts unknown role/placement."""
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-legacy-invalid",
        workspace,
        "topic-legacy-invalid",
        "feature/cleanup",
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    install_legacy_module_markers(request.clone, request.request, role="unknown")
    with pytest.raises(rtc.RepositoryTopicCloneError, match="legacy-marker-mismatch"):
        rtc.cleanup(request.request, apply=False)

    install_legacy_module_markers(request.clone, request.request, placement="unknown")
    with pytest.raises(rtc.RepositoryTopicCloneError, match="legacy-marker-mismatch"):
        rtc.cleanup(request.request, apply=False)

    install_legacy_module_markers(request.clone, request.request, module="vendor/other")
    with pytest.raises(rtc.RepositoryTopicCloneError, match="legacy-marker-mismatch"):
        rtc.cleanup(request.request, apply=False)

    install_legacy_module_markers(request.clone, request.request)
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
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-remote-mismatch",
        workspace,
        "topic-remote-mismatch",
        "feature/cleanup",
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
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-partial",
        workspace,
        "topic-partial",
        "feature/cleanup",
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


def test_cleanup_holds_repository_mismatch_after_root_ignore_drifts(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
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

    proof = rtc.cleanup(request.request, apply=False)
    assert not proof.removed

    run_git(
        request.clone,
        "config",
        "repository-topic-clone.repository",
        "different-repository",
    )
    with pytest.raises(rtc.RepositoryTopicCloneError, match="repository-mismatch"):
        rtc.cleanup(
            request.request,
            apply=False,
        )
    run_git(
        request.clone,
        "config",
        "repository-topic-clone.repository",
        repo_name,
    )

    assert request.clone.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"


def test_failure_when_receipt_is_arbitrary_mapping_or_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    request = rtc.request(
        remote_url,
        "repo-four",
        workspace,
        "topic-fail",
        "feature/fail",
        checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
    )
    run_git(request.clone, "config", "user.name", "Test")
    run_git(request.clone, "config", "user.email", "test@example.invalid")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    calls = tmp_path / "git-calls.txt"
    install_git_shim(
        tmp_path,
        f'if [ "${{1:-}}" = "fetch" ]; then printf "%s\\n" "$*" >> {shlex.quote(str(calls))}; fi\n',
        monkeypatch,
    )

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
    assert not calls.exists()

    with pytest.raises(rtc.RepositoryTopicCloneError):
        rtc.cleanup(
            request.request,
            apply=False,
        )


def test_prepare_dirty_collision_and_cleanup_rejects_detached_branch(
    tmp_path: Path,
) -> None:
    remote, remote_url = init_remote(tmp_path)
    workspace = tmp_path / "parent"
    init_workspace_parent(workspace)

    clone = rtc.request(
        remote_url,
        "repo-five",
        workspace,
        "topic-clean",
        "feature/clean",
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
            checkout_mode=rtc.CHECKOUT_MODE_INDEPENDENT,
        )
