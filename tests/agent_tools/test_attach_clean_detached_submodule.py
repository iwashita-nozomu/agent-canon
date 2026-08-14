# @dependency-start
# contract test
# responsibility Verifies reconstructible detached AgentCanon submodule attachment without weakening dirty, divergent, or branch-collision blockers.
# upstream implementation ../../tools/agent_tools/attach_clean_detached_submodule.py owns attachment behavior
# upstream implementation ../../tools/update_agent_canon.sh preserves nonzero planning diagnostics
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_TOOLS = ROOT / "tools" / "agent_tools"
if str(AGENT_TOOLS) not in sys.path:
    sys.path.insert(0, str(AGENT_TOOLS))

from attach_clean_detached_submodule import attach


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def commit_file(repo: Path, name: str, content: str, message: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        message,
    )
    return git(repo, "rev-parse", "HEAD")


def make_parent(tmp_path: Path) -> tuple[Path, Path, str]:
    child = tmp_path / "child"
    parent = tmp_path / "parent"
    child.mkdir()
    parent.mkdir()
    git(child, "init", "-b", "main")
    pinned = commit_file(child, "tracked.txt", "pinned\n", "child pin")
    git(parent, "init", "-b", "main")
    (parent / ".gitmodules").write_text(
        '[submodule "vendor/agent-canon"]\n'
        '\tpath = vendor/agent-canon\n'
        f'\turl = {child.as_posix()}\n',
        encoding="utf-8",
    )
    (parent / "vendor").mkdir()
    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "-C",
            str(parent),
            "submodule",
            "add",
            child.as_posix(),
            "vendor/agent-canon",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    git(parent, "add", ".gitmodules", "vendor/agent-canon")
    git(
        parent,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "parent pin",
    )
    submodule = parent / "vendor/agent-canon"
    git(submodule, "checkout", "--detach", pinned)
    return parent, submodule, pinned


def make_parent_with_plan_failure(tmp_path: Path) -> Path:
    """Create a parent projection whose configured remote cannot be resolved."""
    source_clone = tmp_path / "source-clone"
    subprocess.run(
        ["git", "clone", "--quiet", str(ROOT), str(source_clone)],
        check=True,
        capture_output=True,
        text=True,
    )

    parent = tmp_path / "plan-parent"
    parent.mkdir()
    git(parent, "init", "-b", "main")
    for relative in (
        "tools/update_agent_canon.sh",
        "tools/lib/repo_paths.sh",
        "tools/lib/update_materialization.sh",
        "tools/lib/git_authority.sh",
    ):
        destination = parent / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)

    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "-C",
            str(parent),
            "submodule",
            "add",
            source_clone.as_posix(),
            "vendor/agent-canon",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    submodule = parent / "vendor/agent-canon"
    git(
        parent,
        "config",
        "-f",
        ".gitmodules",
        "submodule.vendor/agent-canon.url",
        (tmp_path / "missing-agent-canon.git").as_posix(),
    )
    git(parent, "add", ".gitmodules", "tools")
    subprocess.run(
        [
            "git",
            "-C",
            str(parent),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "parent update fixture",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert git(submodule, "rev-parse", "HEAD")
    return parent


def test_clean_detached_at_parent_pin_attaches_requested_branch(tmp_path: Path) -> None:
    parent, submodule, pinned = make_parent(tmp_path)
    git(submodule, "branch", "-D", "main")

    assert attach(parent, "vendor/agent-canon", "main") == 0
    assert git(submodule, "symbolic-ref", "--short", "HEAD") == "main"
    assert git(submodule, "rev-parse", "HEAD") == pinned


def test_dirty_detached_checkout_remains_blocked(tmp_path: Path) -> None:
    parent, submodule, _ = make_parent(tmp_path)
    (submodule / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    assert attach(parent, "vendor/agent-canon", "main") == 2
    assert subprocess.run(
        ["git", "-C", str(submodule), "symbolic-ref", "--quiet", "--short", "HEAD"],
        check=False,
    ).returncode != 0


def test_detached_head_different_from_parent_pin_remains_blocked(tmp_path: Path) -> None:
    parent, submodule, pinned = make_parent(tmp_path)
    next_commit = commit_file(submodule, "other.txt", "next\n", "next")
    assert next_commit != pinned
    git(submodule, "checkout", "--detach", next_commit)

    assert attach(parent, "vendor/agent-canon", "main") == 2


def test_existing_divergent_local_branch_is_not_rewritten(tmp_path: Path) -> None:
    parent, submodule, pinned = make_parent(tmp_path)
    divergent = commit_file(submodule, "branch.txt", "branch\n", "branch")
    assert divergent != pinned
    git(submodule, "branch", "-f", "main", divergent)
    git(submodule, "checkout", "--detach", pinned)

    assert attach(parent, "vendor/agent-canon", "main") == 2
    assert git(submodule, "rev-parse", "refs/heads/main") == divergent


def test_parent_update_prints_nonzero_plan_diagnostics_before_returning(
    tmp_path: Path,
) -> None:
    """Plan diagnostics reach stdout before the wrapper returns its plan status."""
    parent = make_parent_with_plan_failure(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "AGENT_CANON_COMMIT_REQUEST_EVIDENCE": "evidence:" + ("0" * 64),
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "test-approved-update",
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "user_request",
            "AGENT_CANON_BRANCH_WORKTREE_REASON": "test-approved-update",
            "HOME": str(parent / ".agent-canon" / "home"),
            "TMPDIR": str(parent / ".agent-canon" / "tmp" / "update"),
            "TEMP": str(parent / ".agent-canon" / "tmp" / "update"),
            "TMP": str(parent / ".agent-canon" / "tmp" / "update"),
            "XDG_CACHE_HOME": str(parent / ".agent-canon" / "cache"),
            "PYTHONPYCACHEPREFIX": str(
                parent / ".agent-canon" / "cache" / "pycache"
            ),
            "CARGO_HOME": str(parent / ".agent-canon" / "cache" / "cargo-home"),
            "CARGO_TARGET_DIR": str(
                parent / ".agent-canon" / "cache" / "cargo-target"
            ),
            "AGENT_CANON_PARENT_TMPDIR": str(
                parent / ".agent-canon" / "tmp" / "update"
            ),
        }
    )
    latest = subprocess.run(
        ["bash", "tools/update_agent_canon.sh", "latest"],
        cwd=parent,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert latest.returncode == 2, latest.stdout + latest.stderr
    assert any(
        line.startswith("agent_canon_plan_route=")
        for line in latest.stdout.splitlines()
    )
    assert "agent_canon_plan_status=blocked" in latest.stdout
