#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Attaches a clean detached AgentCanon submodule at the parent gitlink to the requested local branch without rewriting divergent local branch state.
# upstream design ../../documents/agent-canon/agent-canon-update-route.md parent update materialization acceptance
# upstream implementation ../update_agent_canon.sh calls this before planning a parent projection
# downstream implementation ../../tests/agent_tools/test_attach_clean_detached_submodule.py validates clean detached, dirty, mismatch, and branch-collision behavior
# @dependency-end
"""Attach a reconstructible detached submodule checkout to a named branch."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitResult:
    stdout: str
    returncode: int


def run_git(root: Path, *args: str, check: bool = True) -> GitResult:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return GitResult(completed.stdout.strip(), completed.returncode)


def ref_sha(root: Path, ref: str) -> str | None:
    result = run_git(root, "rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    return result.stdout if result.returncode == 0 else None


def attach(root: Path, prefix: str, branch: str) -> int:
    submodule = root / prefix
    tree_entry = run_git(root, "ls-tree", "HEAD", prefix, check=False).stdout
    mode = tree_entry.split(maxsplit=1)[0] if tree_entry else ""
    if mode != "160000":
        print(f"AGENT_CANON_DETACHED_ATTACH=not_submodule:{prefix}")
        return 0

    current_branch = run_git(
        submodule, "symbolic-ref", "--quiet", "--short", "HEAD", check=False
    ).stdout
    if current_branch:
        print(f"AGENT_CANON_DETACHED_ATTACH=already_named:{current_branch}")
        return 0

    status = run_git(
        submodule, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    parent_pin = run_git(root, "rev-parse", f"HEAD:{prefix}").stdout
    worktree_head = run_git(submodule, "rev-parse", "HEAD").stdout

    print("AGENT_CANON_DETACHED_STATE=detached")
    print(f"AGENT_CANON_DETACHED_PARENT_PIN={parent_pin}")
    print(f"AGENT_CANON_DETACHED_WORKTREE_HEAD={worktree_head}")
    print(f"AGENT_CANON_DETACHED_WORKTREE_STATUS={'dirty' if status else 'clean'}")

    if status:
        print("AGENT_CANON_DETACHED_ATTACH=blocked_dirty")
        print("NEXT_ACTION=preserve_or_commit_submodule_worktree_changes_then_rerun_parent_update")
        return 2
    if worktree_head != parent_pin:
        print("AGENT_CANON_DETACHED_ATTACH=blocked_parent_pin_mismatch")
        print("NEXT_ACTION=route_divergent_submodule_history_without_rewriting_the_checkout")
        return 2

    existing_branch_sha = ref_sha(submodule, f"refs/heads/{branch}")
    if existing_branch_sha is not None and existing_branch_sha != worktree_head:
        print(f"AGENT_CANON_DETACHED_LOCAL_BRANCH_SHA={existing_branch_sha}")
        print("AGENT_CANON_DETACHED_ATTACH=blocked_local_branch_collision")
        print("NEXT_ACTION=preserve_existing_local_branch_and_choose_an_explicit_update_route")
        return 2

    if existing_branch_sha is None:
        run_git(submodule, "switch", "-c", branch, worktree_head)
    else:
        run_git(submodule, "switch", branch)

    attached_branch = run_git(
        submodule, "symbolic-ref", "--quiet", "--short", "HEAD"
    ).stdout
    attached_head = run_git(submodule, "rev-parse", "HEAD").stdout
    if attached_branch != branch or attached_head != worktree_head:
        raise RuntimeError("detached submodule attachment readback failed")

    print(f"AGENT_CANON_DETACHED_ATTACH=attached:{branch}")
    print(f"AGENT_CANON_DETACHED_ATTACH_HEAD={attached_head}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--prefix", default="vendor/agent-canon")
    parser.add_argument("--branch", default="main")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    return attach(root, args.prefix, args.branch)


if __name__ == "__main__":
    raise SystemExit(main())
