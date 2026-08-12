# @dependency-start
# contract test
# responsibility Verifies reconstructible detached AgentCanon submodule attachment without weakening dirty, divergent, or branch-collision blockers.
# upstream implementation ../../tools/agent_tools/attach_clean_detached_submodule.py owns attachment behavior
# upstream implementation ../../tools/update_agent_canon.sh preserves nonzero planning diagnostics
# @dependency-end

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_TOOLS = ROOT / "tools" / "agent_tools"
if str(AGENT_TOOLS) not in sys.path:
    sys.path.insert(0, str(AGENT_TOOLS))

from attach_clean_detached_submodule import attach  # noqa: E402


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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


def test_parent_update_prints_nonzero_plan_diagnostics_before_returning() -> None:
    script = (ROOT / "tools" / "update_agent_canon.sh").read_text(encoding="utf-8")
    capture = 'plan_output="$(cmd_plan "$branch")" || plan_rc=$?'
    emit = "printf '%s\\n' \"$plan_output\""
    guard = 'if [ "$plan_rc" -ne 0 ]; then'

    assert capture in script
    assert emit in script
    assert guard in script
    assert script.index(capture) < script.index(emit) < script.index(guard)
