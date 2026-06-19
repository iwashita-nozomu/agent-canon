#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Persists AgentCanon memory notes into Git commits and optional pushes.
# upstream design ../../agents/workflows/agent-learning-workflow.md defines memory closeout.
# upstream implementation ./log_agent_learning.py appends agent-side memory observations.
# upstream implementation ./log_user_preference.py appends user preference observations.
# downstream implementation ../../tests/agent_tools/test_persist_agent_memory.py tests CLI.
# @dependency-end

"""Persist AgentCanon memory note changes after logging observations."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MEMORY_PATHS = ("memory/AGENT_PHILOSOPHY.md", "memory/USER_PREFERENCES.md")
DEFAULT_COMMIT_MESSAGE = "Record AgentCanon memory observations"
DEFAULT_SUPERPROJECT_MESSAGE = "chore: sync AgentCanon memory"


@dataclass(frozen=True)
class AgentCanonLocation:
    """Resolved AgentCanon checkout and optional superproject context."""

    agent_root: Path
    superproject_root: Path | None
    superproject_prefix: str | None


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Commit and optionally push pending AgentCanon memory note updates."
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Template root or standalone AgentCanon root. Default: current directory.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit pending memory changes inside AgentCanon.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the AgentCanon HEAD to origin/<branch> after committing.",
    )
    parser.add_argument(
        "--commit-superproject",
        action="store_true",
        help="Commit the updated vendor/agent-canon pin in the superproject.",
    )
    parser.add_argument(
        "--push-superproject",
        action="store_true",
        help="Push the superproject HEAD to origin/<branch>.",
    )
    parser.add_argument(
        "--message",
        default=DEFAULT_COMMIT_MESSAGE,
        help=f"AgentCanon commit message. Default: {DEFAULT_COMMIT_MESSAGE!r}.",
    )
    parser.add_argument(
        "--superproject-message",
        default=DEFAULT_SUPERPROJECT_MESSAGE,
        help=f"Superproject commit message. Default: {DEFAULT_SUPERPROJECT_MESSAGE!r}.",
    )
    parser.add_argument(
        "--branch",
        default="",
        help="Branch name to push. Default: current branch or agent-canon.branch/main.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when pending memory changes exist.",
    )
    return parser


def run_git(
    root: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one git command in a repository root."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed in {root}: {detail}")
    return result


def git_output(root: Path, args: list[str], *, check: bool = True) -> str:
    """Return stripped stdout for one git command."""
    return run_git(root, args, check=check).stdout.strip()


def git_lines(root: Path, args: list[str], *, check: bool = True) -> list[str]:
    """Return non-empty stdout lines for one git command."""
    output = git_output(root, args, check=check)
    return [line for line in output.splitlines() if line.strip()]


def git_status_lines(root: Path, args: list[str]) -> list[str]:
    """Return status lines without stripping porcelain status columns."""
    result = run_git(root, args)
    return [line for line in result.stdout.rstrip("\n").splitlines() if line.strip()]


def is_git_checkout(path: Path) -> bool:
    """Return whether a path is a Git checkout or submodule worktree."""
    return (path / ".git").exists()


def find_git_root(path: Path) -> Path:
    """Return the containing Git root."""
    root = git_output(path, ["rev-parse", "--show-toplevel"])
    return Path(root).resolve()


def superproject_root(agent_root: Path) -> Path | None:
    """Return the superproject root for a submodule checkout, if present."""
    output = git_output(agent_root, ["rev-parse", "--show-superproject-working-tree"])
    if not output:
        return None
    return Path(output).resolve()


def resolve_agent_canon(workspace_root: Path) -> AgentCanonLocation:
    """Resolve a standalone or vendored AgentCanon checkout."""
    workspace_root = workspace_root.resolve()
    candidate = workspace_root / "vendor" / "agent-canon"
    if is_git_checkout(candidate):
        agent_root = find_git_root(candidate)
    else:
        agent_root = find_git_root(workspace_root)

    if not (agent_root / "memory").is_dir():
        raise RuntimeError(f"AgentCanon memory directory not found under {agent_root}")

    super_root = superproject_root(agent_root)
    prefix = None
    if super_root is not None:
        prefix = str(agent_root.relative_to(super_root))
    return AgentCanonLocation(
        agent_root=agent_root,
        superproject_root=super_root,
        superproject_prefix=prefix,
    )


def memory_status(agent_root: Path) -> list[str]:
    """Return porcelain status lines for memory note paths."""
    return git_status_lines(
        agent_root,
        ["status", "--short", "--untracked-files=all", "--", *MEMORY_PATHS],
    )


def branch_name(root: Path, requested: str) -> str:
    """Return a branch name suitable for push targets."""
    if requested:
        return requested
    current = git_output(root, ["branch", "--show-current"])
    if current:
        return current
    configured = git_output(root, ["config", "--get", "agent-canon.branch"], check=False)
    return configured or "main"


def commit_memory(agent_root: Path, message: str) -> bool:
    """Commit staged memory changes and return whether a commit was created."""
    run_git(agent_root, ["add", *MEMORY_PATHS])
    diff_result = run_git(
        agent_root,
        ["diff", "--cached", "--quiet", "--", *MEMORY_PATHS],
        check=False,
    )
    if diff_result.returncode == 0:
        return False
    run_git(agent_root, ["commit", "-m", message])
    return True


def push_head(root: Path, branch: str) -> None:
    """Push HEAD to origin/<branch>."""
    run_git(root, ["push", "origin", f"HEAD:refs/heads/{branch}"])


def superproject_status(location: AgentCanonLocation) -> list[str]:
    """Return superproject status lines, if a superproject exists."""
    if location.superproject_root is None:
        return []
    return git_status_lines(
        location.superproject_root,
        ["status", "--short", "--untracked-files=all"],
    )


def status_path(line: str) -> str:
    """Extract the path portion from one porcelain-v1 status line."""
    return line[3:].strip()


def commit_superproject_pin(location: AgentCanonLocation, message: str) -> bool:
    """Commit only the AgentCanon submodule pointer in the superproject."""
    if location.superproject_root is None or location.superproject_prefix is None:
        print("SUPERPROJECT_PIN_STATUS=no_superproject")
        return False

    status_lines = superproject_status(location)
    unexpected = [
        line for line in status_lines if status_path(line) != location.superproject_prefix
    ]
    if unexpected:
        details = "\n".join(unexpected)
        raise RuntimeError(
            "superproject has unrelated changes; commit the AgentCanon memory pin separately:\n"
            f"{details}"
        )

    if not status_lines:
        print("SUPERPROJECT_PIN_STATUS=clean")
        return False

    run_git(location.superproject_root, ["add", location.superproject_prefix])
    staged = run_git(
        location.superproject_root,
        ["diff", "--cached", "--quiet", "--", location.superproject_prefix],
        check=False,
    )
    if staged.returncode == 0:
        print("SUPERPROJECT_PIN_STATUS=unchanged")
        return False
    run_git(location.superproject_root, ["commit", "-m", message])
    print(f"SUPERPROJECT_PIN_COMMITTED={location.superproject_prefix}")
    return True


def main() -> int:
    """Run the persistence workflow."""
    args = build_parser().parse_args()
    try:
        location = resolve_agent_canon(Path(args.workspace_root))
        pending = memory_status(location.agent_root)
        print(f"AGENT_CANON_ROOT={location.agent_root}")
        print(f"AGENT_MEMORY_PENDING={len(pending)}")
        for line in pending:
            print(f"AGENT_MEMORY_PATH={status_path(line)}")

        if args.check and pending:
            print("AGENT_MEMORY_STATUS=dirty")
            return 1

        if args.commit and pending:
            if commit_memory(location.agent_root, str(args.message)):
                print("AGENT_MEMORY_COMMIT=created")
            else:
                print("AGENT_MEMORY_COMMIT=noop")
        elif pending:
            print("AGENT_MEMORY_NEXT=run with --commit to persist memory changes")

        if args.push:
            target_branch = branch_name(location.agent_root, str(args.branch))
            push_head(location.agent_root, target_branch)
            print(f"AGENT_MEMORY_PUSHED=origin/{target_branch}")

        if args.commit_superproject:
            commit_superproject_pin(location, str(args.superproject_message))

        if args.push_superproject and location.superproject_root is not None:
            target_branch = branch_name(location.superproject_root, str(args.branch))
            push_head(location.superproject_root, target_branch)
            print(f"SUPERPROJECT_PUSHED=origin/{target_branch}")

        return 0
    except RuntimeError as exc:
        print(f"persist_agent_memory.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
