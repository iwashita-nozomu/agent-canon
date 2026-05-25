#!/usr/bin/env python3
# @dependency-start
# responsibility Manages the ignored Git clone used for AgentCanon runtime log archives.
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and branch policy
# upstream implementation ./runtime_log_paths.py resolves archive paths and source repo keys
# downstream design ../../documents/runtime-log-archive.md documents this tool as the normal Git workflow
# downstream implementation ../../tests/agent_tools/test_runtime_log_archive_git.py validates clone, branch, status, and push behavior
# @dependency-end
"""Manage the external AgentCanon runtime log archive Git repository."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime_log_paths import (  # noqa: E402
    LOG_ARCHIVE_REMOTE,
    mounted_log_archive_root,
    repo_log_key,
)

DEFAULT_COMMIT_NAME = "AgentCanon Log Archive"
DEFAULT_COMMIT_EMAIL = "agent-canon-log@example.invalid"


@dataclass(frozen=True)
class ArchiveContext:
    """Resolved archive operation context."""

    source_root: Path
    canon_root: Path
    archive_root: Path
    repo_key: str
    branch: str
    remote: str


class ArchiveGitError(RuntimeError):
    """Raised when the archive Git operation cannot proceed safely."""


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Repository whose runtime logs are being written. Defaults to the superproject when AgentCanon is vendored.",
    )
    parser.add_argument(
        "--canon-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="AgentCanon root that owns .agent-canon/log-archive.",
    )
    parser.add_argument(
        "--remote",
        default=LOG_ARCHIVE_REMOTE,
        help="Log archive Git remote. Defaults to the shared agent-canon-log SSH URL.",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        help="Override the archive clone path. Defaults to <canon-root>/.agent-canon/log-archive.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("repo-key", help="Print the source repository key and log branch.")

    ensure = subparsers.add_parser("ensure", help="Clone/fetch the archive and switch to logs/<repo-key>.")
    ensure.add_argument("--no-fetch", action="store_true", help="Do not fetch origin before selecting the branch.")

    status = subparsers.add_parser("status", help="Print archive clone, branch, and dirty state.")
    status.add_argument("--porcelain", action="store_true", help="Include git status --porcelain output.")

    legacy = subparsers.add_parser(
        "import-legacy",
        help="Copy old AgentCanon in-tree hook JSONL into hook-runs/legacy-import.",
    )
    legacy.add_argument(
        "--legacy-root",
        type=Path,
        help="Legacy hook JSONL root. Defaults to <canon-root>/agents/evals/results/hook-runs.",
    )
    legacy.add_argument(
        "--destination-prefix",
        default="hook-runs/legacy-import",
        help="Archive-relative destination prefix for legacy JSONL.",
    )
    legacy.add_argument(
        "--delete-source",
        action="store_true",
        help="Delete imported source JSONL after copying. Tracked files are removed with git rm.",
    )

    push = subparsers.add_parser("push", help="Commit and push append-only logs for this source repository.")
    push.add_argument("--message", help="Commit message. Defaults to 'Append <repo-key> runtime logs'.")
    push.add_argument("--no-pull", action="store_true", help="Do not pull --rebase before pushing.")
    return parser


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one command and return the completed process."""
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        command = " ".join(args)
        detail = result.stderr.strip() or result.stdout.strip()
        raise ArchiveGitError(f"{command} failed: {detail}")
    return result


def git(
    archive_root: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run git inside the archive clone."""
    return run(["git", "-C", str(archive_root), *args], check=check)


def git_root(path: Path) -> Path | None:
    """Return the Git toplevel for one path, if available."""
    result = run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def superproject_root(path: Path) -> Path | None:
    """Return the superproject root when AgentCanon is checked out as a submodule."""
    result = run(
        ["git", "-C", str(path), "rev-parse", "--show-superproject-working-tree"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def default_source_root(canon_root: Path) -> Path:
    """Return the default source repo for branch naming."""
    return superproject_root(canon_root) or git_root(Path.cwd()) or Path.cwd().resolve()


def build_context(args: argparse.Namespace) -> ArchiveContext:
    """Resolve source/canon/archive paths and branch names."""
    canon_root = args.canon_root.resolve()
    source_root = (args.source_root.resolve() if args.source_root else default_source_root(canon_root))
    archive_root = (
        args.archive_root.resolve()
        if args.archive_root
        else mounted_log_archive_root(canon_root).resolve()
    )
    key = repo_log_key(source_root)
    return ArchiveContext(
        source_root=source_root,
        canon_root=canon_root,
        archive_root=archive_root,
        repo_key=key,
        branch=f"logs/{key}",
        remote=args.remote,
    )


def remote_branch_exists(context: ArchiveContext, branch: str) -> bool:
    """Return whether origin/<branch> exists locally after fetch."""
    result = git(context.archive_root, ["rev-parse", "--verify", f"origin/{branch}"], check=False)
    return result.returncode == 0


def local_branch_exists(context: ArchiveContext, branch: str) -> bool:
    """Return whether one local branch exists."""
    result = git(context.archive_root, ["rev-parse", "--verify", branch], check=False)
    return result.returncode == 0


def current_branch(context: ArchiveContext) -> str:
    """Return the current branch name for the archive clone."""
    result = git(context.archive_root, ["branch", "--show-current"])
    return result.stdout.strip()


def porcelain_status(context: ArchiveContext) -> str:
    """Return porcelain status output for the archive clone."""
    return git(context.archive_root, ["status", "--porcelain"], check=False).stdout


def safe_archive_relative_path(value: str) -> Path:
    """Return an archive-relative path or fail for unsafe input."""
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ArchiveGitError(f"archive path must be relative and cannot contain '..': {value}")
    return path


def ensure_commit_identity(context: ArchiveContext) -> None:
    """Ensure the archive clone has a local identity for automated commits."""
    name = git(context.archive_root, ["config", "--get", "user.name"], check=False)
    email = git(context.archive_root, ["config", "--get", "user.email"], check=False)
    if name.returncode != 0 or not name.stdout.strip():
        git(context.archive_root, ["config", "user.name", DEFAULT_COMMIT_NAME])
    if email.returncode != 0 or not email.stdout.strip():
        git(context.archive_root, ["config", "user.email", DEFAULT_COMMIT_EMAIL])


def source_is_tracked(canon_root: Path, path: Path) -> bool:
    """Return whether one source path is tracked by the canon Git repo."""
    try:
        relative = path.resolve().relative_to(canon_root.resolve())
    except ValueError:
        return False
    result = run(
        ["git", "-C", str(canon_root), "ls-files", "--error-unmatch", "--", relative.as_posix()],
        check=False,
    )
    return result.returncode == 0


def delete_source_file(context: ArchiveContext, source: Path) -> None:
    """Delete one imported source file, using git rm when possible."""
    try:
        relative = source.resolve().relative_to(context.canon_root.resolve())
    except ValueError:
        source.unlink()
        return
    if source_is_tracked(context.canon_root, source):
        run(["git", "-C", str(context.canon_root), "rm", "--", relative.as_posix()])
        return
    source.unlink()


def is_archive_clone(path: Path) -> bool:
    """Return whether path is an existing Git worktree."""
    return (path / ".git").exists()


def ensure_origin(context: ArchiveContext) -> None:
    """Ensure origin points at the configured remote."""
    result = git(context.archive_root, ["remote", "get-url", "origin"], check=False)
    if result.returncode != 0:
        git(context.archive_root, ["remote", "add", "origin", context.remote])
        return
    if result.stdout.strip() != context.remote:
        git(context.archive_root, ["remote", "set-url", "origin", context.remote])


def ensure_archive(context: ArchiveContext, *, fetch: bool = True) -> None:
    """Ensure the ignored clone exists and is on the source repo log branch."""
    if not context.archive_root.exists():
        context.archive_root.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", context.remote, str(context.archive_root)])
    if not is_archive_clone(context.archive_root):
        raise ArchiveGitError(f"archive path is not a Git clone: {context.archive_root}")

    ensure_origin(context)
    if fetch:
        git(context.archive_root, ["fetch", "origin"], check=False)

    branch = context.branch
    current = current_branch(context)
    if current == branch:
        return
    if porcelain_status(context).strip():
        raise ArchiveGitError(
            f"archive has local changes; commit or stash before switching to {branch}"
        )
    if local_branch_exists(context, branch):
        git(context.archive_root, ["switch", branch])
        return
    if remote_branch_exists(context, branch):
        git(context.archive_root, ["switch", "--track", "-c", branch, f"origin/{branch}"])
        return
    if remote_branch_exists(context, "main"):
        git(context.archive_root, ["switch", "-c", branch, "origin/main"])
        return
    git(context.archive_root, ["switch", "-c", branch])


def print_context(context: ArchiveContext) -> None:
    """Print stable context lines."""
    print(f"RUNTIME_LOG_ARCHIVE_SOURCE_ROOT={context.source_root}")
    print(f"RUNTIME_LOG_ARCHIVE_CANON_ROOT={context.canon_root}")
    print(f"RUNTIME_LOG_ARCHIVE_ROOT={context.archive_root}")
    print(f"RUNTIME_LOG_ARCHIVE_REMOTE={context.remote}")
    print(f"RUNTIME_LOG_ARCHIVE_REPO_KEY={context.repo_key}")
    print(f"RUNTIME_LOG_ARCHIVE_BRANCH={context.branch}")


def command_repo_key(context: ArchiveContext) -> int:
    """Print repo-key context."""
    print_context(context)
    return 0


def command_ensure(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Ensure archive clone and branch."""
    ensure_archive(context, fetch=not args.no_fetch)
    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_CURRENT_BRANCH={current_branch(context)}")
    print("RUNTIME_LOG_ARCHIVE_ENSURE=pass")
    return 0


def command_status(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Print archive status."""
    print_context(context)
    if not context.archive_root.exists():
        print("RUNTIME_LOG_ARCHIVE_STATUS=missing")
        return 0
    if not is_archive_clone(context.archive_root):
        print("RUNTIME_LOG_ARCHIVE_STATUS=invalid")
        return 1
    status = porcelain_status(context)
    print(f"RUNTIME_LOG_ARCHIVE_CURRENT_BRANCH={current_branch(context)}")
    print(f"RUNTIME_LOG_ARCHIVE_DIRTY={'yes' if status.strip() else 'no'}")
    if args.porcelain:
        for line in status.splitlines():
            print(f"RUNTIME_LOG_ARCHIVE_PORCELAIN={line}")
    print("RUNTIME_LOG_ARCHIVE_STATUS=pass")
    return 0


def command_import_legacy(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Import old in-tree hook JSONL into the archive clone."""
    ensure_archive(context)
    legacy_root = (
        args.legacy_root.resolve()
        if args.legacy_root
        else context.canon_root / "agents" / "evals" / "results" / "hook-runs"
    )
    destination_prefix = safe_archive_relative_path(args.destination_prefix)
    if context.archive_root.resolve() == legacy_root or context.archive_root.resolve() in legacy_root.parents:
        raise ArchiveGitError("legacy root cannot be inside the archive clone")
    if not legacy_root.exists():
        print_context(context)
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_LEGACY_ROOT={legacy_root}")
        print("RUNTIME_LOG_ARCHIVE_IMPORT_FILES=0")
        print("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no")
        print("RUNTIME_LOG_ARCHIVE_IMPORT=pass")
        return 0

    imported = 0
    existing = 0
    for source in sorted(legacy_root.rglob("*.jsonl")):
        if not source.is_file():
            continue
        relative = source.relative_to(legacy_root)
        target = context.archive_root / destination_prefix / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise ArchiveGitError(f"archive destination already exists with different content: {target}")
            existing += 1
        else:
            shutil.copy2(source, target)
            imported += 1
        if args.delete_source:
            delete_source_file(context, source)

    if (context.archive_root / destination_prefix).exists():
        git(context.archive_root, ["add", "--", destination_prefix.as_posix()])

    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_LEGACY_ROOT={legacy_root}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_DESTINATION={destination_prefix.as_posix()}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_FILES={imported + existing}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_NEW_FILES={imported}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EXISTING_FILES={existing}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE={'yes' if args.delete_source else 'no'}")
    print("RUNTIME_LOG_ARCHIVE_IMPORT=pass")
    return 0


def command_push(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Commit and push source repo runtime logs."""
    ensure_archive(context)
    log_paths = [Path("hook-runs") / context.repo_key, Path("hook-runs") / "legacy-import"]
    message = args.message or f"Append {context.repo_key} runtime logs"

    for logs_path in log_paths:
        if (context.archive_root / logs_path).exists():
            git(context.archive_root, ["add", "--", logs_path.as_posix()])
    staged = git(context.archive_root, ["diff", "--cached", "--quiet"], check=False)
    committed = "no"
    if staged.returncode != 0:
        ensure_commit_identity(context)
        git(context.archive_root, ["commit", "-m", message])
        committed = "yes"
    if not args.no_pull and remote_branch_exists(context, context.branch):
        git(context.archive_root, ["pull", "--rebase", "origin", context.branch])
    git(context.archive_root, ["push", "-u", "origin", context.branch])

    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_COMMITTED={committed}")
    print("RUNTIME_LOG_ARCHIVE_PUSH=pass")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the runtime log archive Git helper."""
    parser = build_parser()
    args = parser.parse_args(argv)
    context = build_context(args)
    try:
        if args.command == "repo-key":
            return command_repo_key(context)
        if args.command == "ensure":
            return command_ensure(context, args)
        if args.command == "status":
            return command_status(context, args)
        if args.command == "import-legacy":
            return command_import_legacy(context, args)
        if args.command == "push":
            return command_push(context, args)
    except ArchiveGitError as exc:
        print(f"RUNTIME_LOG_ARCHIVE_ERROR={exc}")
        print("RUNTIME_LOG_ARCHIVE=fail")
        return 1
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
