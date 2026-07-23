#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Publishes AgentCanon wiki page sets to owner/repo.wiki.git with deterministic gates and exact readback.
# upstream design ../../agents/skills/wiki-publication.md owns wiki publication workflow and source-binding contract.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md owns publication evidence ordering.
# upstream design ../../documents/agent-canon-github-remote.md defines verified GitHub remote policy.
# downstream design ../../documents/tools/wiki_publish.md documents the public tool contract.
# downstream implementation ../../tests/agent_tools/test_wiki_publish.py validates command shape and failure boundaries.
# @dependency-end

"""Publish an AgentCanon wiki sidecar page-set to a default-branch-only wiki remote."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_ERROR_CHARS = 4000
REMOTE_UNINITIALIZED = "REMOTE_UNINITIALIZED"
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
    parser.add_argument("--wiki-root", required=True, type=Path, help="Local wiki sidecar root.")
    parser.add_argument("--source-root", required=True, type=Path, help="Source repo root used for commit validation.")
    parser.add_argument(
        "--source-commit",
        required=True,
        help="Exact source commit SHA1 bound to the wiki page set.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Source repository slug, e.g. iwashita-nozomu/agent-canon.",
    )
    parser.add_argument("--writer", required=True, help="Writer identity for this publication.")
    parser.add_argument(
        "--reviewer",
        required=True,
        help="Independent reviewer identity for this publication.",
    )
    parser.add_argument(
        "--expected-page-set-digest",
        help="Reviewer-approved SHA-256 digest of the prepared page-set. Omitting runs prepare/check mode.",
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
    return f"https://github.com/{slug}.wiki.git"


def git(command: Sequence[str], repo_root: Path, *, runner: Runner, next_action: str) -> str:
    result = run_command(runner, ["git", *command], repo_root, next_action=next_action)
    return result.stdout.strip()


def validate_source_commit(runner: Runner, source_root: Path, source_commit: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise UserVisibleFailure(
            message=f"invalid source commit identity: {source_commit!r}",
            next_action="pin_an_exact_full_sha1_source_commit",
        )
    kind = git(
        ["cat-file", "-t", source_commit],
        source_root,
        runner=runner,
        next_action="source_commit_not_found_in_source_repo",
    )
    if kind != "commit":
        raise UserVisibleFailure(
            message=f"source commit {source_commit!r} is not a commit in source repo",
            next_action="source_commit_not_found_in_source_repo",
        )
    return source_commit


def resolve_default_wiki_branch(runner: Runner, remote_url: str) -> str:
    result = run_command(
        runner,
        ["git", "ls-remote", "--symref", remote_url, "HEAD"],
        Path.cwd(),
        next_action="default_branch_unavailable",
    ).stdout
    for line in result.splitlines():
        if not line.startswith("ref:"):
            continue
        match = re.match(r"^ref:\s*refs/heads/(?P<branch>[^\t\s]+)\tHEAD$", line)
        if match:
            return match.group("branch")
    raise UserVisibleFailure(
        message="default wiki branch is unavailable from remote symref",
        next_action="default_branch_unavailable",
    )


def required_wiki_remote(slug: str) -> str:
    return wiki_url(slug)


def ensure_wiki_root(
    *,
    runner: Runner,
    repo_root: Path,
    remote_url: str,
    default_branch: str,
    wiki_root: Path,
) -> None:
    if not wiki_root.exists():
        run_command(
            runner,
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                default_branch,
                remote_url,
                str(wiki_root),
            ],
            repo_root,
            next_action="prepare_wiki_sidecar_clone",
        )
        return

    current = git(
        ["rev-parse", "--is-inside-work-tree"],
        wiki_root,
        runner=runner,
        next_action="wiki_root_not_a_git_worktree",
    )
    if current != "true":
        raise UserVisibleFailure(
            message=f"wiki_root is not a git repository: {wiki_root}",
            next_action="wiki_root_not_a_git_worktree",
        )

    current_branch = git(
        ["branch", "--show-current"],
        wiki_root,
        runner=runner,
        next_action="ensure_default_wiki_branch_is_active",
    )
    if current_branch != default_branch:
        raise UserVisibleFailure(
            message=f"expected default branch {default_branch!r}, but checked out {current_branch!r}",
            next_action="checkout_default_wiki_branch_before_publish",
        )


def iter_top_level_markdown_pages(wiki_root: Path) -> list[Path]:
    pages: list[Path] = []
    for entry in sorted(wiki_root.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() != ".md":
            continue
        pages.append(entry)
    return pages


def extract_source_marker(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(WIKI_SOURCE_MARKER_PREFIX):
            return line.removeprefix(WIKI_SOURCE_MARKER_PREFIX).removesuffix("-->")
    return None


def normalize_for_digest(text: str, source_commit: str, *, path: str) -> tuple[str, bytes]:
    if extract_source_marker(text) != source_commit:
        raise UserVisibleFailure(
            message=f"wiki source marker mismatch for {path!r}: observed={extract_source_marker(text)!r}, expected={source_commit!r}",
            next_action="rewrite_source_marker_before_publish",
        )
    return path, text.encode("utf-8")


def format_page_for_publish(
    source_root: Path,
    runner: Runner,
    page: Path,
) -> bytes:
    with tempfile.TemporaryDirectory() as page_tmp:
        temp_page = Path(page_tmp) / "page.md"
        temp_page.write_text(page.read_text(encoding="utf-8"), encoding="utf-8")
        run_command(
            runner,
            [str(AGENT_CANON_BIN), "docs", "format", str(temp_page)],
            source_root,
            next_action="format_source_page",
        )
        return temp_page.read_bytes()


def prepare_page_set(
    *,
    source_root: Path,
    source_commit: str,
    wiki_root: Path,
    runner: Runner,
) -> tuple[str, dict[Path, bytes]]:
    pages = iter_top_level_markdown_pages(wiki_root)
    if not pages:
        raise UserVisibleFailure(
            message="no top-level markdown pages found in wiki root",
            next_action="inventory_wiki_markdown_pages",
        )

    required_pages = {"Home.md", "_Sidebar.md", "_Footer.md"}
    found = {p.name for p in pages}
    missing = required_pages - found
    if missing:
        raise UserVisibleFailure(
            message=f"required wiki pages are missing: {', '.join(sorted(missing))}",
            next_action="add_required_wiki_pages",
        )

    prepared: dict[Path, bytes] = {}
    hasher = hashlib.sha256()
    for path in sorted(pages):
        formatted = format_page_for_publish(source_root, runner, path)
        text = formatted.decode("utf-8")
        rel = path.name
        key, page_bytes = normalize_for_digest(text, source_commit, path=rel)
        rel_data = f"{key}\0{len(page_bytes)}\0".encode("utf-8")
        hasher.update(rel_data)
        hasher.update(page_bytes)
        prepared[path] = page_bytes

    return hasher.hexdigest(), prepared


def publish_prepared_pages(
    *,
    runner: Runner,
    source_root: Path,
    wiki_root: Path,
    prepared: dict[Path, bytes],
    writer: str,
    source_commit: str,
    default_branch: str,
    remote_url: str,
) -> tuple[str, str]:
    for path, data in prepared.items():
        path.write_bytes(data)

    run_command(
        runner,
        ["git", "config", "user.name", writer],
        wiki_root,
        next_action="set_git_user_name",
    )
    run_command(
        runner,
        ["git", "config", "user.email", f"{writer}@example.invalid"],
        wiki_root,
        next_action="set_git_user_email",
    )

    run_command(
        runner,
        ["git", "add"] + [str(path.relative_to(wiki_root)) for path in sorted(prepared.keys())],
        wiki_root,
        next_action="stage_wiki_page_set",
    )
    status = run_command(
        runner,
        ["git", "status", "--porcelain"],
        wiki_root,
        next_action="inspect_git_status",
    ).stdout.strip()
    if status:
        run_command(
            runner,
            [
                "git",
                "commit",
                "-m",
                f"Publish wiki pages for source {source_commit}",
            ],
            wiki_root,
            next_action="commit_formatted_wiki_pages",
        )

    local_head = git(
        ["rev-parse", "HEAD"],
        wiki_root,
        runner=runner,
        next_action="read_local_wiki_head",
    )
    run_command(
        runner,
        ["git", "push", "origin", f"HEAD:{default_branch}"],
        wiki_root,
        next_action="push_default_wiki_branch",
    )
    remote_head = git(
        ["ls-remote", remote_url, f"refs/heads/{default_branch}"],
        Path.cwd(),
        runner=runner,
        next_action="read_remote_wiki_head",
    ).split()[0]

    if remote_head != local_head:
        raise UserVisibleFailure(
            message=f"remote readback {remote_head!r} does not match local {local_head!r}",
            next_action="retry_with_exact_default_branch_readback",
        )

    return local_head, remote_head


def publish_to_wiki(
    args: argparse.Namespace,
    *,
    runner: Runner = subprocess_runner,
    wiki_temp_root: Path | None = None,
) -> dict[str, Any]:
    source_root = Path(args.source_root).resolve()
    wiki_root = Path(args.wiki_root).resolve()
    if args.writer == args.reviewer:
        raise UserVisibleFailure(
            message="writer and reviewer must be different identities",
            next_action="set_an_independent_reviewer",
        )

    source_commit = validate_source_commit(runner, source_root, args.source_commit)

    slug = normalized_slug(args.repo)
    if not slug:
        raise UserVisibleFailure(
            message="invalid source repository slug",
            next_action="pass_repo_in_owner_name_form",
        )
    target_remote = required_wiki_remote(slug)

    default_branch = resolve_default_wiki_branch(runner, target_remote)
    if not default_branch:
        return {
            "action": "publish",
            "state": REMOTE_UNINITIALIZED,
            "repo": slug,
            "wiki_remote": target_remote,
            "writer": args.writer,
            "reviewer": args.reviewer,
            "source_commit": source_commit,
            "next_action": "initialize_wiki_sidecar_and_retry",
        }

    work_root = wiki_temp_root if wiki_temp_root is not None else wiki_root

    try:
        ensure_wiki_root(
            runner=runner,
            repo_root=source_root,
            remote_url=target_remote,
            default_branch=default_branch,
            wiki_root=work_root,
        )

        page_set_digest, prepared_pages = prepare_page_set(
            source_root=source_root,
            source_commit=source_commit,
            wiki_root=work_root,
            runner=runner,
        )

        summary: dict[str, Any] = {
            "action": "publish",
            "repo": slug,
            "wiki_root": str(wiki_root),
            "wiki_remote": target_remote,
            "default_branch": default_branch,
            "source_commit": source_commit,
            "page_set_digest": page_set_digest,
            "page_count": len(prepared_pages),
            "writer": args.writer,
            "reviewer": args.reviewer,
        }

        if not args.expected_page_set_digest:
            summary["state"] = "PREPARE_OK"
            summary["next_action"] = "obtain_independent_reviewer_approval_for_page_set_digest"
            return summary

        if args.expected_page_set_digest != page_set_digest:
            raise UserVisibleFailure(
                message="wiki page-set digest does not match reviewer-approved digest",
                next_action="page_set_digest_mismatch",
            )

        local_head, remote_head = publish_prepared_pages(
            runner=runner,
            source_root=source_root,
            wiki_root=work_root,
            prepared=prepared_pages,
            writer=args.writer,
            source_commit=source_commit,
            default_branch=default_branch,
            remote_url=target_remote,
        )

        summary.update(
            {
                "state": "PUBLISHED",
                "local_head": local_head,
                "remote_head": remote_head,
                "next_action": "read_exact_remote_page_set_head",
            }
        )
        return summary
    finally:
        pass


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
