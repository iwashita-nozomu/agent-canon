"""Tests for topic dependency source clone lifecycle semantics."""

# @dependency-start
# contract test
# responsibility Verifies topic naming, clone membership, clone handback, and cleanup gates.
# upstream design ../../documents/rule/dependency-module-changes.md topic-root policy
# upstream implementation ../../tools/agent_tools/dependency_module_change.py lifecycle tool
# downstream implementation ../../tools/agent_tools/check_dependency_headers.py validates this test header
# @dependency-end

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tools.agent_tools import dependency_module_change as lifecycle

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "dependency_module_change.py"
TOPIC = "dependency-module-change"


def run_git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def create_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "dep.git"
    source = tmp_path / "dependency-source"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(source)], check=True, capture_output=True)
    (source / "README.md").write_text("source\n", encoding="utf-8")
    run_git(source, "add", "README.md")
    subprocess.run(
        [
            "git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-m", "initial",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(source, "remote", "add", "origin", str(remote))
    run_git(source, "push", "origin", "main")
    run_git(source, "checkout", "-b", "feature/foo")
    run_git(source, "push", "origin", "feature/foo")
    run_git(source, "checkout", "main")
    return remote


def advance_remote_main(tmp_path: Path) -> str:
    source = tmp_path / "dependency-source"
    (source / "latest.txt").write_text("latest\n", encoding="utf-8")
    run_git(source, "add", "latest.txt")
    subprocess.run(
        [
            "git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-m", "latest main",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(source, "push", "origin", "main")
    return run_git(source, "rev-parse", "HEAD")


def create_parent(
    tmp_path: Path,
    remote: Path,
    *,
    paths: tuple[str, ...] = ("vendor/dep",),
    manifest_branch: str | None = "main",
    manifest_url: str | None = None,
) -> Path:
    parent_source = tmp_path / "parent-source"
    parent_remote = tmp_path / "parent.git"
    subprocess.run(["git", "init", "--bare", str(parent_remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(parent_source)], check=True, capture_output=True)
    lines: list[str] = []
    for index, path in enumerate(paths):
        url = manifest_url if manifest_url is not None else str(remote)
        lines.extend([f'[submodule "dependency-{index}"]', f"\tpath = {path}", f"\turl = {url}"])
        if manifest_branch is not None:
            lines.append(f"\tbranch = {manifest_branch}")
        lines.append("")
    (parent_source / ".gitmodules").write_text("\n".join(lines), encoding="utf-8")
    (parent_source / "owner-evidence.md").write_text("source edit required\n", encoding="utf-8")
    paths_to_stage = [".gitmodules", "owner-evidence.md"]
    run_git(parent_source, "add", *paths_to_stage)
    subprocess.run(
        [
            "git", "-C", str(parent_source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-m", "parent",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(parent_source, "remote", "add", "origin", str(parent_remote))
    run_git(parent_source, "push", "origin", "main")
    run_git(parent_remote, "symbolic-ref", "HEAD", "refs/heads/main")
    selected = tmp_path / "host" / "parent"
    selected.parent.mkdir()
    subprocess.run(["git", "clone", str(parent_remote), str(selected)], check=True, capture_output=True)
    return selected


def invoke(root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        env=merged_env,
    )


def cleanup_env() -> dict[str, str]:
    return {
        "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "agent_canon_workflow",
        "AGENT_CANON_BRANCH_WORKTREE_REASON": "test",
        "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
        "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "test",
    }


def owner_evidence_sha(parent: Path) -> str:
    return hashlib.sha256((parent / "owner-evidence.md").read_bytes()).hexdigest()


def git_submodule_resolved_url(
    parent: Path, parent_remote: str, dependency_remote: Path, suffix: str
) -> str:
    """Ask Git's submodule init to resolve the manifest URL in an oracle clone."""
    oracle = parent.parent / f"submodule-resolution-oracle-{suffix}"
    subprocess.run(
        ["git", "clone", str(parent.parent.parent / "parent.git"), str(oracle)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(oracle, "remote", "set-url", "origin", parent_remote)
    dependency_sha = run_git(dependency_remote, "rev-parse", "refs/heads/main")
    run_git(
        oracle,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{dependency_sha},vendor/dep",
    )
    run_git(oracle, "submodule", "init", "--", "vendor/dep")
    return run_git(oracle, "config", "--local", "--get", "submodule.dependency-0.url")


def prepare(
    parent: Path,
    branch: str = "feature/foo",
    parent_branch: str | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [
        "prepare",
        "--topic",
        TOPIC,
        "--module",
        "vendor/dep",
        "--branch",
        branch,
        "--owner-evidence",
        "owner-evidence.md",
    ]
    if parent_branch is not None:
        args.extend(("--parent-branch", parent_branch))
    return invoke(
        parent,
        *args,
    )


def prepare_workspace(
    parent: Path,
    *,
    topic: str = "parallel-clones",
    branch: str = "feature/parallel-clones",
    owner_evidence: str = "owner-evidence.md",
) -> subprocess.CompletedProcess[str]:
    return invoke(
        parent,
        "prepare",
        "--placement",
        "workspace",
        "--topic",
        topic,
        "--module",
        "vendor/dep",
        "--branch",
        branch,
        "--owner-evidence",
        owner_evidence,
    )


def prepare_workspace_continuation(
    parent: Path,
    *,
    topic: str = "parallel-clones",
    branch: str = "feature/foo",
    owner_evidence: str = "owner-evidence.md",
) -> subprocess.CompletedProcess[str]:
    return invoke(
        parent,
        "prepare",
        "--placement",
        "workspace-continuation",
        "--topic",
        topic,
        "--module",
        "vendor/dep",
        "--branch",
        branch,
        "--owner-evidence",
        owner_evidence,
    )


def topic_root(parent: Path) -> Path:
    return parent / "workspace" / "dependency-module-change"


def topic_parent(parent: Path) -> Path:
    return topic_root(parent) / parent.name


def module_clone(parent: Path) -> Path:
    return topic_root(parent) / "dep"


def workspace_module_clone(parent: Path, topic: str = "parallel-clones") -> Path:
    return parent / "workspace" / topic / "dep"


def test_prepare_creates_topic_parent_and_reuses_matching_branch_clone(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)

    missing_branch = invoke(parent, "prepare", "--topic", TOPIC, "--module", "vendor/dep", "--owner-evidence", "owner-evidence.md")
    assert missing_branch.returncode == 2

    prepared = prepare(parent)
    assert prepared.returncode == 0, prepared.stderr
    assert topic_parent(parent).is_dir()
    clone = module_clone(parent)
    assert clone.is_dir()
    assert run_git(clone, "symbolic-ref", "--short", "HEAD") == "feature/foo"
    assert run_git(clone, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/feature/foo"
    assert run_git(clone, "config", "--local", "--get", "agent-canon.topic.module") == "vendor/dep"
    assert f"PARENT_ROOT={topic_parent(parent)}" in prepared.stdout
    assert f"SOURCE_CLONE={clone}" in prepared.stdout
    assert f"CONTINUE_PATH={clone}" in prepared.stdout
    assert len(prepared.stdout.splitlines()) == 3

    reused = prepare(topic_parent(parent))
    assert reused.returncode == 0, reused.stderr
    assert reused.stdout == prepared.stdout


def test_prepare_creates_task_branch_from_manifest_or_remote_head(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote, manifest_branch=None)

    prepared = prepare(parent, "task/new-source")

    assert prepared.returncode == 0, prepared.stderr
    clone = module_clone(parent)
    assert run_git(clone, "symbolic-ref", "--short", "HEAD") == "task/new-source"
    upstream = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "--abbrev-ref", "@{upstream}"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert upstream.returncode != 0


def test_workspace_placement_uses_latest_main_and_only_computed_clone(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    latest_main = advance_remote_main(tmp_path)

    prepared = prepare_workspace(parent)
    clone = workspace_module_clone(parent)

    assert prepared.returncode == 0, prepared.stderr
    assert clone.is_dir()
    assert not topic_parent(parent).exists()
    assert run_git(clone, "symbolic-ref", "--short", "HEAD") == "feature/parallel-clones"
    assert run_git(clone, "rev-parse", "HEAD") == latest_main
    assert run_git(clone, "rev-parse", "origin/main") == latest_main
    assert f"SOURCE_CLONE={clone}" in prepared.stdout
    assert "SOURCE_BASE_REF=origin/main" in prepared.stdout
    assert f"SOURCE_BASE_SHA={latest_main}" in prepared.stdout
    assert f"SOURCE_OWNER_EVIDENCE_SHA256={owner_evidence_sha(parent)}" in prepared.stdout
    assert "SOURCE_REMOTE=" in prepared.stdout


def test_workspace_placement_reuses_exact_identity_and_refuses_changes(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    first = prepare_workspace(parent)
    assert first.returncode == 0, first.stderr

    reused = prepare_workspace(parent)
    assert reused.returncode == 2
    assert "already exists locally" in reused.stderr

    changed_branch = prepare_workspace(parent, branch="feature/other")
    assert changed_branch.returncode == 2
    assert "computed clone is occupied" in changed_branch.stderr

    (parent / "owner-evidence.md").write_text("different owner\n", encoding="utf-8")
    changed_evidence = prepare_workspace(parent, branch="feature/other")
    assert changed_evidence.returncode == 2
    assert "owner-evidence-mismatch" in changed_evidence.stderr


def test_workspace_fresh_refuses_existing_branch_and_requires_continuation_route(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)

    fresh = prepare_workspace(parent, branch="feature/foo")
    assert fresh.returncode == 2
    assert "already exists remotely" in fresh.stderr
    assert not workspace_module_clone(parent).exists()

    continuation = prepare_workspace_continuation(parent)
    assert continuation.returncode == 0, continuation.stderr
    assert "PLACEMENT=workspace-continuation" in continuation.stdout
    assert run_git(workspace_module_clone(parent), "symbolic-ref", "--short", "HEAD") == "feature/foo"

    continued_again = prepare_workspace_continuation(parent)
    assert continued_again.returncode == 0, continued_again.stderr
    assert continued_again.stdout == continuation.stdout


def test_workspace_rejects_symlinked_ancestors_and_external_cleanup_target(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("external\n", encoding="utf-8")

    (parent / "workspace").symlink_to(external, target_is_directory=True)
    workspace_link = prepare_workspace(parent)
    assert workspace_link.returncode == 2
    assert sentinel.read_text(encoding="utf-8") == "external\n"

    (parent / "workspace").unlink()
    (parent / "workspace").mkdir()
    (parent / "workspace" / "parallel-clones").symlink_to(external, target_is_directory=True)
    topic_link = prepare_workspace(parent)
    assert topic_link.returncode == 2
    assert sentinel.read_text(encoding="utf-8") == "external\n"

    (parent / "workspace" / "parallel-clones").unlink()
    (parent / "workspace" / "parallel-clones").mkdir()
    module_link = parent / "workspace" / "parallel-clones" / "dep"
    module_link.symlink_to(external, target_is_directory=True)
    module_link_result = prepare_workspace(parent)
    assert module_link_result.returncode == 2
    assert sentinel.read_text(encoding="utf-8") == "external\n"

    cleanup_link = invoke(
        parent,
        "cleanup",
        "--placement",
        "workspace",
        "--topic",
        "parallel-clones",
        "--module",
        "vendor/dep",
        "--expected-clone",
        str(module_link),
        "--owner-evidence-sha256",
        owner_evidence_sha(parent),
        "--apply",
        env=cleanup_env(),
    )
    assert cleanup_link.returncode == 2
    assert sentinel.read_text(encoding="utf-8") == "external\n"


def test_workspace_resolves_relative_gitmodules_url_against_parent_origin(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote, manifest_url="../dep.git")

    prepared = prepare_workspace(parent, topic="relative-url")
    clone = workspace_module_clone(parent, topic="relative-url")

    assert prepared.returncode == 0, prepared.stderr
    assert run_git(clone, "config", "--local", "--get", "remote.origin.url") == str(remote)
    assert run_git(clone, "config", "--local", "--get", "agent-canon.topic.url") == str(remote)[:-4]
    assert f"SOURCE_REMOTE={remote}" in prepared.stdout


def test_relative_gitmodules_url_matches_git_for_filesystem_https_and_scp(
    tmp_path: Path,
) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote, manifest_url="../dep.git")
    cases = (
        ("filesystem", str(tmp_path / "repos" / "project.git")),
        ("https", "https://example.invalid/org/project.git"),
        ("scp", "git@example.invalid:org/project.git"),
    )

    for suffix, parent_remote in cases:
        run_git(parent, "remote", "set-url", "origin", parent_remote)
        expected = git_submodule_resolved_url(parent, parent_remote, remote, suffix)
        assert lifecycle._resolve_module_url(parent, "../dep.git") == expected


def test_container_layout_status_and_cleanup_use_canonical_topic_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    remote = create_remote(tmp_path)
    create_parent(tmp_path, remote)
    container_root = tmp_path / "container-workspace"
    container_root.mkdir()
    parent_root = container_root / "agent-canon"
    subprocess.run(
        ["git", "clone", str(tmp_path / "parent.git"), str(parent_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setattr(lifecycle, "CONTAINER_WORKSPACE_ROOT", container_root)
    monkeypatch.setenv("AGENT_CANON_WORKSPACE_ROOT", str(container_root))

    lifecycle._prepare_workspace(
        parent_root,
        "container-topic",
        "vendor/dep",
        "feature/container",
        "owner-evidence.md",
        None,
        placement="workspace",
    )
    clone = container_root / "dep"
    assert clone.is_dir()
    assert clone.parent == container_root

    lifecycle._status_workspace(parent_root, "container-topic", "workspace")
    status_output = capsys.readouterr().out
    assert f"CLONE={clone}" in status_output
    assert "STATE=ready" in status_output

    monkeypatch.setenv("AGENT_CANON_BRANCH_WORKTREE_AUTHORITY", "agent_canon_workflow")
    monkeypatch.setenv("AGENT_CANON_BRANCH_WORKTREE_REASON", "test")
    monkeypatch.setenv("AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY", "explicit_user_approval")
    monkeypatch.setenv("AGENT_CANON_DESTRUCTIVE_GIT_REASON", "test")
    lifecycle._cleanup_workspace(
        parent_root,
        "container-topic",
        lifecycle._parse_gitmodules(parent_root)[0],
        clone,
        True,
        "workspace",
        owner_evidence_sha(parent_root),
    )
    assert not clone.exists()


def test_container_layout_rejects_symlinked_sibling_cleanup_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = create_remote(tmp_path)
    create_parent(tmp_path, remote)
    container_root = tmp_path / "container-workspace"
    container_root.mkdir()
    parent_root = container_root / "agent-canon"
    subprocess.run(
        ["git", "clone", str(tmp_path / "parent.git"), str(parent_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setattr(lifecycle, "CONTAINER_WORKSPACE_ROOT", container_root)
    monkeypatch.setenv("AGENT_CANON_WORKSPACE_ROOT", str(container_root))
    lifecycle._prepare_workspace(
        parent_root,
        "container-topic",
        "vendor/dep",
        "feature/container",
        "owner-evidence.md",
        None,
        placement="workspace",
    )
    clone = container_root / "dep"
    shutil.rmtree(clone)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("external\n", encoding="utf-8")
    clone.symlink_to(external, target_is_directory=True)
    module = lifecycle._parse_gitmodules(parent_root)[0]

    with pytest.raises(lifecycle.DependencyModuleChangeError, match="symlink"):
        lifecycle._status_workspace(parent_root, "container-topic", "workspace")
    with pytest.raises(lifecycle.DependencyModuleChangeError, match="symlink"):
        lifecycle._cleanup_workspace(
            parent_root,
            "container-topic",
            module,
            clone,
            True,
            "workspace",
            owner_evidence_sha(parent_root),
        )
    assert sentinel.read_text(encoding="utf-8") == "external\n"


def test_workspace_cleanup_requires_exact_evidence_sha_and_marker(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    assert prepare_workspace(parent).returncode == 0
    clone = workspace_module_clone(parent)

    missing = invoke(
        parent,
        "cleanup",
        "--placement",
        "workspace",
        "--topic",
        "parallel-clones",
        "--module",
        "vendor/dep",
        "--expected-clone",
        str(clone),
    )
    assert missing.returncode == 2
    assert clone.exists()

    wrong = invoke(
        parent,
        "cleanup",
        "--placement",
        "workspace",
        "--topic",
        "parallel-clones",
        "--module",
        "vendor/dep",
        "--expected-clone",
        str(clone),
        "--owner-evidence-sha256",
        "0" * 64,
        "--apply",
        env=cleanup_env(),
    )
    assert wrong.returncode == 0
    assert "owner-evidence-mismatch" in wrong.stdout
    assert clone.exists()

    run_git(clone, "config", "--local", "agent-canon.topic.owner-evidence-sha256", "0" * 64)
    marker_mismatch = invoke(
        parent,
        "cleanup",
        "--placement",
        "workspace",
        "--topic",
        "parallel-clones",
        "--module",
        "vendor/dep",
        "--expected-clone",
        str(clone),
        "--owner-evidence-sha256",
        owner_evidence_sha(parent),
        "--apply",
        env=cleanup_env(),
    )
    assert marker_mismatch.returncode == 0
    assert "owner-evidence-mismatch" in marker_mismatch.stdout
    assert clone.exists()


def test_workspace_placement_cleanup_uses_exact_computed_clone(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    assert prepare_workspace(parent).returncode == 0
    clone = workspace_module_clone(parent)

    dry_run = invoke(
        parent,
        "cleanup",
        "--placement",
        "workspace",
        "--topic",
        "parallel-clones",
        "--module",
        "vendor/dep",
        "--expected-clone",
        str(clone),
        "--owner-evidence-sha256",
        owner_evidence_sha(parent),
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "action=would-remove" in dry_run.stdout

    removed = invoke(
        parent,
        "cleanup",
        "--placement",
        "workspace",
        "--topic",
        "parallel-clones",
        "--module",
        "vendor/dep",
        "--expected-clone",
        str(clone),
        "--owner-evidence-sha256",
        owner_evidence_sha(parent),
        "--apply",
        env=cleanup_env(),
    )
    assert removed.returncode == 0, removed.stderr
    assert not clone.exists()


def test_prepare_can_create_and_reuse_parent_pin_branch(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)

    prepared = prepare(parent, parent_branch="pin/topic")

    assert prepared.returncode == 0, prepared.stderr
    assert run_git(topic_parent(parent), "symbolic-ref", "--short", "HEAD") == "pin/topic"
    assert run_git(topic_parent(parent), "config", "--local", "--get", "agent-canon.topic.branch") == "pin/topic"


def test_same_topic_branch_change_is_refused(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    assert prepare(parent).returncode == 0
    changed = prepare(topic_parent(parent), "feature-foo")
    assert changed.returncode == 2
    assert "different topic" in changed.stderr


def test_basename_collision_is_refused(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote, paths=("one/dep", "two/dep"))
    result = invoke(parent, "prepare", "--topic", TOPIC, "--module", "one/dep", "--branch", "feature/foo", "--owner-evidence", "owner-evidence.md")
    assert result.returncode == 2
    assert "basename collision" in result.stderr


def test_cleanup_holds_dirty_and_url_mismatch(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    assert prepare(parent).returncode == 0
    clone = module_clone(parent)
    (clone / "local.txt").write_text("dirty\n", encoding="utf-8")
    dirty = invoke(
        topic_parent(parent), "cleanup", "--topic", TOPIC, "--module", "vendor/dep",
        "--expected-clone", str(clone), "--apply", env=cleanup_env(),
    )
    assert dirty.returncode == 0, dirty.stderr
    assert "dirty-worktree-index-or-untracked" in dirty.stdout
    assert clone.exists()
    (clone / "local.txt").unlink()
    run_git(clone, "remote", "set-url", "origin", str(tmp_path / "other.git"))
    mismatch = invoke(topic_parent(parent), "cleanup", "--topic", TOPIC, "--module", "vendor/dep", "--expected-clone", str(clone))
    assert mismatch.returncode == 0, mismatch.stderr
    assert "url-mismatch" in mismatch.stdout


def test_cleanup_removes_reconstructible_module_then_parent_and_topic(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    assert prepare(parent).returncode == 0
    clone = module_clone(parent)
    removed = invoke(
        topic_parent(parent), "cleanup", "--topic", TOPIC, "--module", "vendor/dep",
        "--expected-clone", str(clone), "--apply", env=cleanup_env(),
    )
    assert removed.returncode == 0, removed.stderr
    assert not clone.exists()
    parent_removed = invoke(
        topic_parent(parent), "cleanup", "--topic", TOPIC, "--parent",
        "--expected-parent", str(topic_parent(parent)), "--apply", env=cleanup_env(),
    )
    assert parent_removed.returncode == 0, parent_removed.stderr
    assert not topic_root(parent).exists()


def test_parent_cleanup_refuses_identity_invalid_expected_module_path(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    assert prepare(parent).returncode == 0
    run_git(module_clone(parent), "config", "--local", "agent-canon.topic.branch", "wrong/branch")

    result = invoke(
        topic_parent(parent),
        "cleanup",
        "--topic",
        TOPIC,
        "--parent",
        "--expected-parent",
        str(topic_parent(parent)),
        "--apply",
        env=cleanup_env(),
    )

    assert result.returncode == 2
    assert "expected module paths exist" in result.stderr
    assert topic_parent(parent).exists()


def test_parent_cleanup_refuses_unknown_topic_entry(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    assert prepare(parent).returncode == 0
    shutil.rmtree(module_clone(parent))
    (topic_root(parent) / "unknown-clone").mkdir()

    result = invoke(
        topic_parent(parent),
        "cleanup",
        "--topic",
        TOPIC,
        "--parent",
        "--expected-parent",
        str(topic_parent(parent)),
        "--apply",
        env=cleanup_env(),
    )

    assert result.returncode == 2
    assert "unknown topic entries" in result.stderr
    assert (topic_root(parent) / "unknown-clone").exists()


def test_status_does_not_create_topic_or_clone(tmp_path: Path) -> None:
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    result = invoke(parent, "status", "--topic", TOPIC)
    assert result.returncode == 2
    assert not topic_root(parent).exists()
    assert not module_clone(parent).exists()
