#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Publishes one Markdown wiki page to repo.wiki.git with deterministic gates and exact readback.
# upstream design ../../agents/skills/wiki-publication.md owns wiki publication workflow and source-binding contract.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md owns publication evidence ordering.
# upstream design ../../documents/agent-canon-github-remote.md defines verified GitHub remote policy.
# downstream design ../../documents/tools/wiki_publish.md documents the public tool contract.
# downstream implementation ../../tests/agent_tools/test_wiki_publish.py validates command shape and failure boundaries.
# @dependency-end

"""Publish one page from an AgentCanon source file into a dedicated wiki sidecar."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_ERROR_CHARS = 4000
REMOTE_UNINITIALIZED = "REMOTE_UNINITIALIZED"
DEFAULT_SOURCE_BRANCH = "main"
DEFAULT_PAGE_NAME = "Home.md"
WIKI_SOURCE_MARKER_PREFIX = "<!-- AGENT_CANON_WIKI_SOURCE_COMMIT="
AGENT_CANON_BIN = Path("tools/bin/agent-canon")


@dataclass(frozen=True)
class CommandResult:
    """One captured external command result."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class UserVisibleFailure(Exception):
    """Raised when an explicit precondition blocks publication."""

    message: str
    next_action: str


Runner = Callable[[Sequence[str], Path], CommandResult]


def run_command(
    runner: Runner,
    command: Sequence[str],
    workdir: Path,
    *,
    next_action: str,
) -> CommandResult:
    result = runner(command, workdir)
    if result.returncode != 0:
        raise UserVisibleFailure(
            message=f"command failed: {' '.join(command)}\n{result.stderr[:MAX_ERROR_CHARS]}",
            next_action=next_action,
        )
    return result


def subprocess_runner(command: Sequence[str], workdir: Path) -> CommandResult:
    completed = subprocess.run(
        list(command),
        cwd=workdir,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        args=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Source repository root")
    parser.add_argument(
        "--repo",
        required=True,
        help="Source repository slug, e.g. iwashita-nozomu/agent-canon.",
    )
    parser.add_argument(
        "--source-branch",
        default=DEFAULT_SOURCE_BRANCH,
        help="Source branch that owns the publication source content.",
    )
    parser.add_argument(
        "--source-page",
        required=True,
        type=Path,
        help="Source markdown page relative to --root.",
    )
    parser.add_argument(
        "--page-name",
        default=DEFAULT_PAGE_NAME,
        help="Target wiki page file name.",
    )
    parser.add_argument("--writer", required=True, help="Writer identity for this publication.")
    parser.add_argument(
        "--reviewer",
        required=True,
        help="Independent reviewer identity for this publication.",
    )
    parser.add_argument(
        "--summary-out",
        help="Optional JSON summary output path.",
    )
    return parser


def normalized_slug(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("git@github.com:"):
        value = value.split(":", 1)[1]
    elif value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    return value.removesuffix(".git")


def wiki_url(slug: str) -> str:
    return f"git@github.com:{slug}.wiki.git"


def git(command: Sequence[str], repo_root: Path, *, runner: Runner, next_action: str) -> str:
    result = run_command(runner, ["git", *command], repo_root, next_action=next_action)
    return result.stdout.strip()


def resolve_default_wiki_branch(runner: Runner, remote_url: str) -> str:
    try:
        result = run_command(
            runner,
            ["git", "ls-remote", "--symref", remote_url, "HEAD"],
            Path.cwd(),
            next_action="read_wiki_default_branch_with_symref",
        ).stdout
    except UserVisibleFailure:
        return ""
    default_branch = ""
    for line in result.splitlines():
        if line.startswith("ref:"):
            match = re.match(r"^ref:\s*refs/heads/(?P<branch>[^\t\s]+)\tHEAD$", line)
            if match:
                default_branch = match.group("branch")
                break
    if default_branch:
        return default_branch
    # Fallback to first non-empty refs/heads entry.
    refs = git(
        ["ls-remote", "--heads", remote_url],
        Path.cwd(),
        runner=runner,
        next_action="read_wiki_head_refs",
    ).splitlines()
    for line in refs:
        if line.strip().endswith("/refs/heads/"):
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            return parts[1].removeprefix("refs/heads/")
    return ""


def append_source_marker(text: str, source_commit: str) -> str:
    marker = f"{WIKI_SOURCE_MARKER_PREFIX}{source_commit}-->"
    lines = text.rstrip().splitlines()
    for line in lines:
        if line.startswith(WIKI_SOURCE_MARKER_PREFIX):
            return "\n".join(lines)
    lines.append("")
    lines.append(marker)
    return "\n".join(lines) + "\n"


def extract_source_marker(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(WIKI_SOURCE_MARKER_PREFIX):
            return line.removeprefix(WIKI_SOURCE_MARKER_PREFIX).removesuffix("-->")
    return None


def check_source_marker(text: str, source_commit: str) -> None:
    observed = extract_source_marker(text)
    if observed != source_commit:
        raise UserVisibleFailure(
            message=f"wiki source marker mismatch: observed={observed!r}, expected={source_commit!r}",
            next_action="rewrite_source_page_with_exact_source_marker",
        )


def publish_to_wiki(
    args: argparse.Namespace,
    *,
    runner: Runner = subprocess_runner,
    temp_root: Path | None = None,
) -> dict[str, Any]:
    source_root = Path(args.root).resolve()
    if args.writer == args.reviewer:
        raise UserVisibleFailure(
            message="writer and reviewer must be different identities",
            next_action="set_an_independent_reviewer",
        )

    source_page = (source_root / args.source_page).resolve()
    if not source_page.exists():
        raise UserVisibleFailure(
            message=f"source page not found: {source_page}",
            next_action="point_to_an_existing_source_page",
        )

    source_commit = git(
        ["rev-parse", args.source_branch],
        source_root,
        runner=runner,
        next_action="fetch_source_head_commit",
    )
    if len(source_commit) != 40 or any(ch not in "0123456789abcdef" for ch in source_commit.lower()):
        raise UserVisibleFailure(
            message=f"invalid source commit identity: {source_commit!r}",
            next_action="pin_an_exact_full_sha1_source_commit",
        )

    slug = normalized_slug(args.repo)
    if not slug:
        raise UserVisibleFailure(
            message="invalid source repository slug",
            next_action="pass_repo_in_owner_name_form",
        )
    target_remote = wiki_url(slug)

    default_branch = resolve_default_wiki_branch(runner, target_remote)
    if not default_branch:
        return {
            "action": "publish",
            "state": REMOTE_UNINITIALIZED,
            "repo": slug,
            "wiki_remote": target_remote,
            "page_name": args.page_name,
            "source_branch": args.source_branch,
            "source_commit": source_commit,
            "next_action": "initialize_default_wiki_page_and_retry",
            "writer": args.writer,
            "reviewer": args.reviewer,
        }

    sidecar = temp_root or Path(tempfile.mkdtemp(prefix="agent-canon-wiki-"))
    remove_sidecar = temp_root is None

    try:
        run_command(
            runner,
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                default_branch,
                target_remote,
                str(sidecar),
            ],
            Path.cwd(),
            next_action="prepare_wiki_sidecar_clone",
        )

        current = git(
            ["branch", "--show-current"],
            sidecar,
            runner=runner,
            next_action="ensure_default_branch_is_active",
        )
        if current != default_branch:
            raise UserVisibleFailure(
                message=f"expected default branch {default_branch!r}, but checked out {current!r}",
                next_action="checkout_default_wiki_branch_before_publish",
            )

        staged = sidecar / args.page_name
        shutil.copyfile(source_page, staged)

        run_command(
            runner,
            [str(AGENT_CANON_BIN), "docs", "format", str(staged)],
            source_root,
            next_action="format_source_page",
        )

        formatted = append_source_marker(staged.read_text(encoding="utf-8"), source_commit)
        staged.write_text(formatted, encoding="utf-8")
        check_source_marker(formatted, source_commit)

        run_command(
            runner,
            ["git", "config", "user.name", args.writer],
            sidecar,
            next_action="set_git_user_name",
        )
        run_command(
            runner,
            ["git", "config", "user.email", f"{args.writer}@example.invalid"],
            sidecar,
            next_action="set_git_user_email",
        )

        run_command(
            runner,
            ["git", "add", str(staged)],
            sidecar,
            next_action="stage_wiki_page",
        )

        status = run_command(
            runner,
            ["git", "status", "--porcelain"],
            sidecar,
            next_action="inspect_git_status",
        ).stdout.strip()

        if status:
            run_command(
                runner,
                [
                    "git",
                    "commit",
                    "-m",
                    f"Publish wiki page {args.page_name} from {source_commit}",
                ],
                sidecar,
                next_action="commit_formatted_wiki_page",
            )

        local_head = git(
            ["rev-parse", "HEAD"],
            sidecar,
            runner=runner,
            next_action="read_local_wiki_head",
        )
        run_command(
            runner,
            ["git", "push", "origin", "HEAD:" + default_branch],
            sidecar,
            next_action="push_default_wiki_branch",
        )
        remote_head = git(
            ["ls-remote", target_remote, f"refs/heads/{default_branch}"],
            Path.cwd(),
            runner=runner,
            next_action="read_remote_wiki_head",
        ).split()[0]

        if remote_head != local_head:
            raise UserVisibleFailure(
                message=f"remote readback {remote_head!r} does not match local {local_head!r}",
                next_action="retry_with_exact_default_branch_readback",
            )

        return {
            "action": "publish",
            "repo": slug,
            "wiki_remote": target_remote,
            "default_branch": default_branch,
            "page_name": args.page_name,
            "source_branch": args.source_branch,
            "source_commit": source_commit,
            "local_head": local_head,
            "remote_head": remote_head,
            "writer": args.writer,
            "reviewer": args.reviewer,
            "state": "PUBLISHED",
            "next_action": "read_exact_remote_page_commit",
        }
    finally:
        if remove_sidecar:
            shutil.rmtree(sidecar, ignore_errors=True)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        summary = publish_to_wiki(args)
        if args.summary_out:
            Path(args.summary_out).write_text(
                json.dumps(summary, sort_keys=True, indent=2),
                encoding="utf-8",
            )
        print(json.dumps(summary, sort_keys=True))
        return 0
    except UserVisibleFailure as exc:
        print(json.dumps({"message": exc.message, "next_action": exc.next_action}))
        return 1
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"message": str(exc), "next_action": "investigate_failure"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
