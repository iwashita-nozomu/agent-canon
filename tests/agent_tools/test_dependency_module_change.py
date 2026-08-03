"""Tests for dependency module topic adapter behavior."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOPIC = "dependency-module-change"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "dependency_module_change.py"


def run_git(path: Path, *args: str) -> str:
    """Run a git command in a repository and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def create_remote(tmp_path: Path) -> Path:
    """Create a bare dependency remote and seed it with one commit."""
    remote = tmp_path / "dep.git"
    source = tmp_path / "dependency-source"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "init", "-b", "main", str(source)], check=True, capture_output=True
    )
    (source / "README.md").write_text("source\n", encoding="utf-8")
    run_git(source, "add", "README.md")
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
            "initial",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(source, "remote", "add", "origin", str(remote))
    run_git(source, "push", "origin", "main")
    return remote


def create_parent(
    tmp_path: Path,
    remote: Path,
    *,
    manifest_branch: str | None = None,
    manifest_url: str | None = None,
) -> Path:
    """Create a parent repository containing a .gitmodules entry for the dependency."""
    parent_source = tmp_path / "parent-source"
    parent_remote = tmp_path / "parent.git"
    subprocess.run(
        ["git", "init", "--bare", str(parent_remote)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "init", "-b", "main", str(parent_source)],
        check=True,
        capture_output=True,
    )
    manifest = [
        '[submodule "dependency-0"]',
        "\tpath = vendor/dep",
        f"\turl = {manifest_url or remote}",
    ]
    if manifest_branch is not None:
        manifest.append(f"\tbranch = {manifest_branch}")
    (parent_source / ".gitmodules").write_text("\n".join(manifest), encoding="utf-8")
    (parent_source / "owner-evidence.md").write_text(
        "source edit required\n", encoding="utf-8"
    )
    run_git(parent_source, "add", ".gitmodules", "owner-evidence.md")
    subprocess.run(
        [
            "git",
            "-C",
            str(parent_source),
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
    run_git(parent_source, "remote", "add", "origin", str(parent_remote))
    run_git(parent_source, "push", "origin", "main")
    selected = tmp_path / "host" / "parent"
    selected.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", str(parent_remote), str(selected)],
        check=True,
        capture_output=True,
    )
    (selected / ".gitmodules").write_text("\n".join(manifest), encoding="utf-8")
    (selected / "owner-evidence.md").write_text(
        "source edit required\n", encoding="utf-8"
    )
    return selected


def invoke(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the dependency module adapter with provided command arguments."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def prepare(
    parent: Path,
    *,
    branch: str = "feature/foo",
    topic: str = TOPIC,
    owner_evidence: str = "owner-evidence.md",
) -> subprocess.CompletedProcess[str]:
    """Invoke prepare command with the current dependency module."""
    return invoke(
        parent,
        "prepare",
        "--topic",
        topic,
        "--module",
        "vendor/dep",
        "--branch",
        branch,
        "--owner-evidence",
        owner_evidence,
    )


def module_clone(parent: Path) -> Path:
    """Return expected module clone path for the selected parent/topic."""
    return parent / "workspace" / TOPIC / "dep"


def test_prepare_reuses_local_existing_module_branch_via_generic_request(
    tmp_path: Path,
) -> None:
    """Existing local branch in clone should be reused through generic prepare."""
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    first = prepare(parent, branch="feature/foo")
    assert first.returncode == 0, first.stderr

    clone = module_clone(parent)
    run_git(clone, "checkout", "-b", "feature/local")
    second = prepare(parent, branch="feature/local")
    assert second.returncode == 0, second.stderr
    assert (
        run_git(clone, "symbolic-ref", "--quiet", "--short", "HEAD") == "feature/local"
    )


def test_prepare_reuses_remote_existing_module_branch_via_generic_request(
    tmp_path: Path,
) -> None:
    """Existing remote branch should be reused via generic prepare path."""
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    scratch = tmp_path / "scratch"
    subprocess.run(
        ["git", "clone", str(remote), str(scratch)], check=True, capture_output=True
    )
    run_git(scratch, "checkout", "-b", "feature/remote")
    subprocess.run(
        [
            "git",
            "-C",
            str(scratch),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "remote branch",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(scratch, "push", "origin", "feature/remote")

    remote_prepare = prepare(parent, branch="feature/remote")
    assert remote_prepare.returncode == 0, remote_prepare.stderr
    assert (
        run_git(module_clone(parent), "symbolic-ref", "--quiet", "--short", "HEAD")
        == "feature/remote"
    )


def test_relative_module_url_and_merge_main_use_generic_lifecycle(
    tmp_path: Path,
) -> None:
    """Relative module URLs and normal main merge remain adapter decorations."""
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote, manifest_url="./dep.git")
    prepared = prepare(parent, branch="feature/merge")
    assert prepared.returncode == 0, prepared.stderr

    clone = module_clone(parent)
    run_git(clone, "config", "user.name", "Test")
    run_git(clone, "config", "user.email", "test@example.invalid")
    (clone / "topic.txt").write_text("topic\n", encoding="utf-8")
    run_git(clone, "add", "topic.txt")
    run_git(clone, "commit", "-m", "topic")

    source = tmp_path / "dependency-source"
    (source / "main.txt").write_text("main\n", encoding="utf-8")
    run_git(source, "add", "main.txt")
    run_git(source, "commit", "-m", "advance main")
    run_git(source, "push", "origin", "main")

    merged = invoke(
        parent,
        "merge-main",
        "--topic",
        TOPIC,
        "--module",
        "vendor/dep",
        "--branch",
        "feature/merge",
        "--owner-evidence",
        "owner-evidence.md",
    )
    assert merged.returncode == 0, merged.stderr
    assert "MERGE_INTEGRATED_SHA=" in merged.stdout
    assert run_git(clone, "merge-base", "--is-ancestor", "origin/main", "HEAD") == ""


def test_cleanup_rejects_adapter_path_identity_before_publication(
    tmp_path: Path,
) -> None:
    """Adapter delegates cleanup only for the lifecycle-owned clone path."""
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    prepared = prepare(parent)
    assert prepared.returncode == 0, prepared.stderr
    wrong = parent / "workspace" / TOPIC / "other"

    result = invoke(
        parent,
        "cleanup",
        "--topic",
        TOPIC,
        "--module",
        "vendor/dep",
        "--branch",
        "feature/foo",
        "--owner-evidence",
        "owner-evidence.md",
        "--expected-clone",
        str(wrong),
        "--candidate-cas",
        str(parent / "missing-cas.json"),
        "--pr-lifecycle",
        str(parent / "missing-lifecycle.json"),
    )
    assert result.returncode == 2
    assert "--expected-clone must equal" in result.stderr


def test_prepare_requires_owner_evidence_and_returns_typed_topic_identity_error(
    tmp_path: Path,
) -> None:
    """Missing owner-evidence must fail with typed identity-required error."""
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)

    missing = invoke(
        parent,
        "prepare",
        "--topic",
        TOPIC,
        "--module",
        "vendor/dep",
        "--branch",
        "feature/foo",
        "--owner-evidence",
        "missing.md",
    )
    assert missing.returncode == 2
    assert "topic-identity-required" in missing.stderr


@pytest.mark.parametrize("forbidden", ("path", "base", "merge", "cleanup"))
def test_prepare_rejects_hidden_cli_selector_aliases(
    tmp_path: Path, forbidden: str
) -> None:
    """Hidden selector aliases should remain unavailable on adapter prepare."""
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    result = invoke(
        parent,
        "prepare",
        "--topic",
        TOPIC,
        "--module",
        "vendor/dep",
        "--branch",
        "feature/foo",
        "--owner-evidence",
        "owner-evidence.md",
        f"--{forbidden}",
        "x",
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_prepare_has_no_workspace_continuation_flag(tmp_path: Path) -> None:
    """workspace-continuation alias/flag must be rejected."""
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    result = invoke(
        parent,
        "prepare",
        "--topic",
        TOPIC,
        "--module",
        "vendor/dep",
        "--branch",
        "feature/foo",
        "--owner-evidence",
        "owner-evidence.md",
        "--placement",
        "workspace-continuation",
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
