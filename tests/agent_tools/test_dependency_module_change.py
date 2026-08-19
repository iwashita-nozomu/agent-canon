"""Tests for dependency module topic adapter behavior."""

# @dependency-start
# contract test
# responsibility Verifies dependency identity decoration over the generic repository topic lifecycle.
# upstream design ../../documents/rule/repository-topic-clone.md generic repository topic lifecycle
# upstream design ../../documents/rule/dependency-module-changes.md dependency adapter responsibility
# downstream implementation ../../tools/agent_tools/dependency_module_change.py applies dependency policy
# downstream implementation ../../tools/agent_tools/repository_topic_clone.py owns clone lifecycle behavior
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOPIC = "dependency-module-change"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "dependency_module_change.py"
GENERIC_TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "repository_topic_clone.py"


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
    (parent_source / ".gitignore").write_text("workspace/\n", encoding="utf-8")
    run_git(
        parent_source,
        "add",
        ".gitmodules",
        ".gitignore",
        "owner-evidence.md",
    )
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
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def install_public_cli_surface(root: Path, *, derived: bool) -> Path:
    """Install the canonical CLI/library pair in one fresh source surface."""
    tools_root = root / "tools"
    source_tools = root / "vendor" / "agent-canon" / "tools" if derived else tools_root
    agent_tools = source_tools / "agent_tools"
    agent_tools.mkdir(parents=True)
    shutil.copy2(TOOL, agent_tools / TOOL.name)
    shutil.copy2(GENERIC_TOOL, agent_tools / GENERIC_TOOL.name)
    shutil.copy2(TOOL.parent / "parent_root_side_effects.py", agent_tools / "parent_root_side_effects.py")
    if derived:
        tools_root.mkdir(parents=True)
        (tools_root / "agent-canon").symlink_to(
            Path("../vendor/agent-canon/tools"),
            target_is_directory=True,
        )
        source_tools = tools_root / "agent-canon"
    return source_tools / "agent_tools" / TOOL.name


@pytest.mark.parametrize("derived", (False, True))
def test_public_cli_help_and_status_from_fresh_source_surfaces(
    tmp_path: Path,
    derived: bool,
) -> None:
    """Run public help and status without ambient package context."""
    root = tmp_path / ("derived" if derived else "standalone")
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    executable = install_public_cli_surface(root, derived=derived)
    (root / ".gitmodules").write_text(
        '[submodule "dependency-0"]\n'
        "\tpath = vendor/dep\n"
        "\turl = https://example.invalid/dep.git\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    help_result = subprocess.run(
        [sys.executable, str(executable), "--help"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "prepare" in help_result.stdout
    assert "cleanup" in help_result.stdout

    status_result = subprocess.run(
        [
            sys.executable,
            str(executable),
            "--root",
            str(root),
            "status",
            "--topic",
            TOPIC,
            "--module",
            "vendor/dep",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert status_result.returncode == 0, status_result.stderr
    assert "MODULE=vendor/dep STATE=absent" in status_result.stdout


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


def test_cleanup_without_publication_packet_uses_computed_clone(
    tmp_path: Path,
) -> None:
    """Adapter cleanup needs no materialized packet or duplicated clone path."""
    remote = create_remote(tmp_path)
    parent = create_parent(tmp_path, remote)
    prepared = prepare(parent)
    assert prepared.returncode == 0, prepared.stderr
    clone = module_clone(parent)
    run_git(clone, "push", "-u", "origin", "feature/foo")

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
        "--apply",
    )
    assert result.returncode == 0, result.stderr
    assert "action=removed" in result.stdout
    assert not clone.exists()


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
    assert "owner evidence must be a non-empty file" in missing.stderr


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
