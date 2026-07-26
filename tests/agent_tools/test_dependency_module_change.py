"""Tests for topic dependency source clone lifecycle semantics."""

# @dependency-start
# contract test
# responsibility Verifies topic naming, clone membership, clone handback, and cleanup gates.
# upstream design ../../documents/rule/dependency-module-changes.md topic-root policy
# upstream implementation ../../tools/agent_tools/dependency_module_change.py lifecycle tool
# downstream implementation ../../tools/agent_tools/check_dependency_headers.py validates this test header
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "dependency_module_change.py"
TOPIC = "dependency-module-change"


def run_git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def create_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "dependency.git"
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


def create_parent(
    tmp_path: Path,
    remote: Path,
    *,
    paths: tuple[str, ...] = ("vendor/dep",),
    manifest_branch: str | None = "main",
) -> Path:
    parent_source = tmp_path / "parent-source"
    parent_remote = tmp_path / "parent.git"
    subprocess.run(["git", "init", "--bare", str(parent_remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(parent_source)], check=True, capture_output=True)
    lines: list[str] = []
    for index, path in enumerate(paths):
        lines.extend([f'[submodule "dependency-{index}"]', f"\tpath = {path}", f"\turl = {remote}"])
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


def topic_root(parent: Path) -> Path:
    return parent.parent.parent / "workspace-dependency-module-change"


def topic_parent(parent: Path) -> Path:
    return topic_root(parent) / parent.name


def module_clone(parent: Path) -> Path:
    return topic_root(parent) / "dep"


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
