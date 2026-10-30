# @dependency-start
# contract test
# responsibility Tests test check merge structure behavior.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/check_merge_structure.rs native structural integration CLI
# upstream implementation ../../tests/agent_tools/rust_cli_fixture.py external-target native CLI fixture
# @dependency-end

"""Tests for branch integration structure checks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tests.agent_tools.rust_cli_fixture import standalone_agent_canon

AGENT_CANON = standalone_agent_canon()


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one git command in a test repository."""
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Test User"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test User"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def write(path: Path, text: str) -> None:
    """Write one text file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_all(repo: Path, message: str) -> None:
    """Add and commit all tracked changes."""
    add = git(repo, "add", ".")
    assert add.returncode == 0, add.stderr
    commit = git(repo, "commit", "-m", message)
    assert commit.returncode == 0, commit.stderr


def commit_all_with_index_mode(repo: Path, message: str, path: str, mode: str) -> None:
    """Commit all changes with a portable Git index executable-bit choice."""
    add = git(repo, "add", ".")
    assert add.returncode == 0, add.stderr
    set_mode = git(
        repo,
        "update-index",
        f"--chmod={mode}",
        path,
    )
    assert set_mode.returncode == 0, set_mode.stderr
    commit = git(repo, "commit", "-m", message)
    assert commit.returncode == 0, commit.stderr


def run_checker(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the native local structural integration checker."""
    return subprocess.run(
        [
            str(AGENT_CANON),
            "check-merge-structure",
            "--repo-root",
            str(repo),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def init_repo(repo: Path) -> None:
    """Initialize a test repository with a main branch."""
    init = git(repo, "init", "-b", "main")
    assert init.returncode == 0, init.stderr
    write(repo / "alpha.txt", "alpha\n")
    write(repo / "docs" / "guide.md", "guide\n")
    commit_all(repo, "initial")


def tree_mode_and_blob(repo: Path, revision: str, path: str) -> tuple[str, str]:
    """Read one tree entry's Git mode and object id."""
    result = git(repo, "ls-tree", revision, "--", path)
    assert result.returncode == 0, result.stderr
    fields = result.stdout.split("\t", 1)[0].split()
    assert len(fields) == 3, result.stdout
    return fields[0], fields[2]


def test_check_merge_structure_passes_for_merged_structural_changes(tmp_path: Path) -> None:
    """The check should pass when the integration commit preserves the source tree shape."""
    repo = tmp_path / "repo-pass"
    repo.mkdir()
    init_repo(repo)

    assert git(repo, "checkout", "-b", "work/shape-20260408").returncode == 0
    assert git(repo, "mv", "alpha.txt", "beta.txt").returncode == 0
    assert git(repo, "rm", "docs/guide.md").returncode == 0
    os.symlink("beta.txt", repo / "latest.txt")
    commit_all(repo, "reshape files")

    assert git(repo, "checkout", "main").returncode == 0
    write(repo / "unrelated.txt", "keep\n")
    commit_all(repo, "main side change")

    merge = git(repo, "merge", "--no-ff", "work/shape-20260408", "-m", "merge branch")
    assert merge.returncode == 0, merge.stderr

    result = run_checker(
        repo,
        "--source",
        "work/shape-20260408",
        "--target",
        "main^1",
        "--compare-commit",
        "HEAD",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MERGE_STRUCTURE_CHECK=pass" in result.stdout


def test_check_merge_structure_fails_when_old_layout_survives(tmp_path: Path) -> None:
    """The check should fail when the integration tree does not match source-side structure."""
    repo = tmp_path / "repo-fail"
    repo.mkdir()
    init_repo(repo)

    assert git(repo, "checkout", "-b", "work/shape-20260408").returncode == 0
    assert git(repo, "mv", "alpha.txt", "beta.txt").returncode == 0
    assert git(repo, "rm", "docs/guide.md").returncode == 0
    os.symlink("beta.txt", repo / "latest.txt")
    commit_all(repo, "reshape files")

    assert git(repo, "checkout", "main").returncode == 0
    write(repo / "beta.txt", "manual copy\n")
    commit_all(repo, "bad manual pickup")

    result = run_checker(
        repo,
        "--source",
        "work/shape-20260408",
        "--target",
        "main",
        "--compare-commit",
        "HEAD",
    )
    assert result.returncode != 0
    assert "MERGE_STRUCTURE_CHECK=fail" in result.stdout
    assert (
        "alpha.txt" in result.stdout
        or "latest.txt" in result.stdout
        or "docs/guide.md" in result.stdout
    )


def test_check_merge_structure_fails_when_structural_file_mode_differs(tmp_path: Path) -> None:
    """The check must distinguish equal blobs with different Git tree modes."""
    repo = tmp_path / "repo-mode-mismatch"
    repo.mkdir()
    init_repo(repo)
    assert git(repo, "config", "core.filemode", "false").returncode == 0

    assert git(repo, "checkout", "-b", "work/shape-mode-20260408").returncode == 0
    assert git(repo, "mv", "alpha.txt", "beta.txt").returncode == 0
    assert git(repo, "rm", "docs/guide.md").returncode == 0
    os.symlink("beta.txt", repo / "latest.txt")
    commit_all_with_index_mode(repo, "reshape files", "beta.txt", "+x")

    assert git(repo, "checkout", "main").returncode == 0
    assert git(repo, "rm", "alpha.txt").returncode == 0
    assert git(repo, "rm", "docs/guide.md").returncode == 0
    write(repo / "beta.txt", "alpha\n")
    os.symlink("beta.txt", repo / "latest.txt")
    commit_all_with_index_mode(
        repo,
        "manually preserve paths with non-executable mode",
        "beta.txt",
        "-x",
    )

    source_mode, source_blob = tree_mode_and_blob(
        repo, "work/shape-mode-20260408", "beta.txt"
    )
    compare_mode, compare_blob = tree_mode_and_blob(repo, "HEAD", "beta.txt")
    assert source_mode == "100755"
    assert compare_mode == "100644"
    assert source_blob == compare_blob

    result = run_checker(
        repo,
        "--source",
        "work/shape-mode-20260408",
        "--target",
        "main",
        "--compare-commit",
        "HEAD",
    )

    assert result.returncode == 1
    assert "MERGE_STRUCTURE_CHECK=fail" in result.stdout
    assert "beta.txt" in result.stdout
    assert "100755:blob:" in result.stdout
    assert "100644:blob:" in result.stdout
