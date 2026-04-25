# @dependency-start
# @dependency-end

"""Tests for branch integration structure checks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "check_merge_structure.py"


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


def init_repo(repo: Path) -> None:
    """Initialize a test repository with a main branch."""
    init = git(repo, "init", "-b", "main")
    assert init.returncode == 0, init.stderr
    write(repo / "alpha.txt", "alpha\n")
    write(repo / "docs" / "guide.md", "guide\n")
    commit_all(repo, "initial")


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

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--source",
            "work/shape-20260408",
            "--target",
            "main^1",
            "--compare-commit",
            "HEAD",
        ],
        check=False,
        capture_output=True,
        text=True,
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

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--source",
            "work/shape-20260408",
            "--target",
            "main",
            "--compare-commit",
            "HEAD",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "MERGE_STRUCTURE_CHECK=fail" in result.stdout
    assert (
        "alpha.txt" in result.stdout
        or "latest.txt" in result.stdout
        or "docs/guide.md" in result.stdout
    )
