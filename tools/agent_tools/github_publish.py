#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Publishes GitHub branches and pull requests through a gh-verified remote route.
# upstream design ../../ROOT_AGENTS.md defines PR mutation authority and non-blocking publish policy.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines the AgentCanon PR workflow.
# upstream design ../../documents/agent-canon-github-remote.md defines canonical GitHub remote policy.
# downstream design ../../documents/tools/github_publish.md documents the public tool contract.
# downstream implementation ../../tests/agent_tools/test_github_publish.py validates command construction.
# @dependency-end
"""Publish GitHub branches and pull requests with explicit gh-backed evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

MAX_ERROR_CHARS = 4000
REMOTE_SCP_RE = re.compile(r"^[^@]+@[^:]+:(?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class CommandResult:
    """Captured subprocess result."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CommandFailure(Exception):
    """Raised when an external command fails."""

    result: CommandResult
    next_action: str


@dataclass(frozen=True)
class UserVisibleFailure(Exception):
    """Raised when user-facing tool preconditions are not met."""

    message: str
    next_action: str


@dataclass(frozen=True)
class RemoteVerification:
    """Verified GitHub repository and git remote pair."""

    repo: str
    remote: str
    remote_url: str
    remote_slug: str


Runner = Callable[[Sequence[str]], CommandResult]


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root. Defaults to the current working directory.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    push = subparsers.add_parser("push", help="Push a verified branch to origin.")
    add_publish_arguments(push)
    push.add_argument("--allow-main", action="store_true", help="Allow pushing main.")

    pr = subparsers.add_parser("pr", help="Create or update a GitHub pull request.")
    add_publish_arguments(pr)
    add_pr_arguments(pr)

    publish_pr = subparsers.add_parser(
        "publish-pr",
        help="Push the branch and create or update its GitHub pull request.",
    )
    add_publish_arguments(publish_pr)
    add_pr_arguments(publish_pr)
    publish_pr.add_argument("--allow-main", action="store_true", help="Allow pushing main.")

    checks = subparsers.add_parser("checks", help="Show GitHub PR checks.")
    add_publish_arguments(checks)
    checks.add_argument("--pr", help="PR number, URL, or branch. Defaults to current branch.")
    checks.add_argument("--watch", action="store_true", help="Watch checks until completion.")
    return parser


def add_publish_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by publish operations."""
    parser.add_argument(
        "--user-task",
        required=True,
        help="The current user task that authorizes this publish operation.",
    )
    parser.add_argument("--repo", help="GitHub repository in owner/name form.")
    parser.add_argument("--remote", default="origin", help="Git remote to verify. Defaults to origin.")
    parser.add_argument("--branch", help="Branch to publish. Defaults to the current branch.")
    parser.add_argument(
        "--summary-out",
        help="Optional JSON summary path. Stdout remains a compact key/value report.",
    )


def add_pr_arguments(parser: argparse.ArgumentParser) -> None:
    """Add pull-request creation/update arguments."""
    parser.add_argument("--base", default="main", help="Base branch. Defaults to main.")
    parser.add_argument("--title", required=True, help="Pull request title.")
    parser.add_argument("--body-file", required=True, help="Path to a Markdown PR body file.")
    parser.add_argument("--draft", action="store_true", help="Create the PR as a draft.")
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update an existing open PR for the branch instead of reporting it.",
    )


def subprocess_runner(command: Sequence[str]) -> CommandResult:
    """Run one command and capture bounded output for the caller."""
    completed = subprocess.run(
        list(command),
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


def run_command(
    runner: Runner,
    command: Sequence[str],
    *,
    next_action: str,
) -> CommandResult:
    """Run a command and raise a user-visible failure on non-zero exit."""
    result = runner(command)
    if result.returncode != 0:
        raise CommandFailure(result=result, next_action=next_action)
    return result


def json_object(text: str, *, command: str) -> Mapping[str, object]:
    """Parse a JSON object emitted by gh."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserVisibleFailure(
            message=f"{command} did not return JSON: {exc}",
            next_action="rerun_gh_command_and_fix_auth_or_cli_output",
        ) from exc
    if not isinstance(loaded, Mapping):
        raise UserVisibleFailure(
            message=f"{command} returned non-object JSON",
            next_action="rerun_gh_command_and_fix_auth_or_cli_output",
        )
    return cast(Mapping[str, object], loaded)


def json_list(text: str, *, command: str) -> list[Mapping[str, object]]:
    """Parse a JSON list emitted by gh."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserVisibleFailure(
            message=f"{command} did not return JSON: {exc}",
            next_action="rerun_gh_command_and_fix_auth_or_cli_output",
        ) from exc
    if not isinstance(loaded, list):
        raise UserVisibleFailure(
            message=f"{command} returned non-list JSON",
            next_action="rerun_gh_command_and_fix_auth_or_cli_output",
        )
    result: list[Mapping[str, object]] = []
    for item in loaded:
        if isinstance(item, Mapping):
            result.append(cast(Mapping[str, object], item))
    return result


def normalized_repo_slug(value: str) -> str | None:
    """Return owner/name from common GitHub remote URL forms."""
    remote = value.strip()
    if not remote:
        return None
    scp_match = REMOTE_SCP_RE.match(remote)
    if scp_match is not None:
        return clean_slug(scp_match.group("slug"))

    parsed = urlparse(remote)
    if parsed.scheme in {"http", "https", "ssh"} and parsed.path:
        return clean_slug(parsed.path.lstrip("/"))

    if "/" in remote and "://" not in remote and ":" not in remote:
        return clean_slug(remote)
    return None


def clean_slug(slug: str) -> str | None:
    """Normalize one owner/name slug."""
    cleaned = slug.strip().removesuffix(".git").strip("/")
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) < 2:
        return None
    return "/".join(parts[-2:])


def gh_repo_metadata(runner: Runner, repo: str | None) -> Mapping[str, object]:
    """Return repository metadata from gh without git config parsing."""
    command = ["gh", "repo", "view"]
    if repo:
        command.append(repo)
    command.extend(["--json", "nameWithOwner,url,sshUrl"])
    result = run_command(
        runner,
        command,
        next_action="authenticate_gh_and_verify_the_target_repository",
    )
    return json_object(result.stdout, command="gh repo view")


def verify_remote(
    runner: Runner,
    *,
    repo: str | None,
    remote: str,
) -> RemoteVerification:
    """Verify that a git remote points at the same repository gh sees."""
    metadata = gh_repo_metadata(runner, repo)
    name_with_owner = metadata.get("nameWithOwner")
    if not isinstance(name_with_owner, str) or "/" not in name_with_owner:
        raise UserVisibleFailure(
            message="gh repo view did not expose nameWithOwner",
            next_action="authenticate_gh_and_verify_the_target_repository",
        )
    remote_result = run_command(
        runner,
        ["git", "remote", "get-url", remote],
        next_action="configure_origin_remote_for_the_user_task",
    )
    remote_url = remote_result.stdout.strip()
    remote_slug = normalized_repo_slug(remote_url)
    if remote_slug is None or remote_slug != name_with_owner:
        raise UserVisibleFailure(
            message=(
                f"remote {remote!r} points at {remote_slug or '<unrecognized>'}, "
                f"but gh resolved {name_with_owner}"
            ),
            next_action="fix_origin_remote_or_pass_the_correct_--repo_verified_remote_required",
        )
    return RemoteVerification(
        repo=name_with_owner,
        remote=remote,
        remote_url=remote_url,
        remote_slug=remote_slug,
    )


def current_branch(runner: Runner) -> str:
    """Return the current branch name."""
    result = run_command(
        runner,
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        next_action="checkout_a_named_branch_before_publishing",
    )
    branch = result.stdout.strip()
    if not branch:
        raise UserVisibleFailure(
            message="current branch is empty",
            next_action="checkout_a_named_branch_before_publishing",
        )
    return branch


def selected_branch(runner: Runner, branch: str | None) -> str:
    """Return requested branch or current branch."""
    return branch.strip() if branch and branch.strip() else current_branch(runner)


def worktree_dirty(runner: Runner) -> bool:
    """Return whether the worktree has uncommitted content."""
    result = run_command(
        runner,
        ["git", "status", "--short", "--untracked-files=all"],
        next_action="inspect_git_status_before_publishing",
    )
    return bool(result.stdout.strip())


def require_body_file(path_text: str) -> Path:
    """Return a PR body file path after validating it exists."""
    path = Path(path_text)
    if not path.is_file():
        raise UserVisibleFailure(
            message=f"PR body file does not exist: {path}",
            next_action="write_a_pr_body_file_for_the_user_task",
        )
    return path


def existing_open_pr(
    runner: Runner,
    *,
    repo: str,
    branch: str,
) -> Mapping[str, object] | None:
    """Return an existing open PR for the branch, if any."""
    command = [
        "gh",
        "pr",
        "list",
        "--repo",
        repo,
        "--head",
        branch,
        "--state",
        "open",
        "--json",
        "number,url,title,headRefName,baseRefName",
    ]
    result = run_command(
        runner,
        command,
        next_action="authenticate_gh_and_inspect_existing_pull_requests",
    )
    rows = json_list(result.stdout, command="gh pr list")
    return rows[0] if rows else None


def string_field(mapping: Mapping[str, object], key: str) -> str:
    """Return a mapping field as a string."""
    value = mapping.get(key)
    return value if isinstance(value, str) else ""


def int_field(mapping: Mapping[str, object], key: str) -> int | None:
    """Return a mapping field as an int."""
    value = mapping.get(key)
    return value if isinstance(value, int) else None


def base_summary(args: argparse.Namespace, verification: RemoteVerification, branch: str) -> dict[str, object]:
    """Return common summary fields."""
    return {
        "user_task": args.user_task,
        "remote_verified": True,
        "repo": verification.repo,
        "remote": verification.remote,
        "remote_url": verification.remote_url,
        "branch": branch,
        "verified_remote_policy": "gh_verified_remote_required",
    }


def perform_push(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
) -> dict[str, object]:
    """Push the verified branch to origin."""
    if branch == "main" and not getattr(args, "allow_main", False):
        raise UserVisibleFailure(
            message="refusing to push main without --allow-main",
            next_action="publish_a_topic_branch_or_pass_--allow-main_with_explicit_authority",
        )
    dirty = worktree_dirty(runner)
    push_ref = "main" if branch == "main" else branch
    command = ["git", "push", "-u", verification.remote, push_ref]
    if branch == "main":
        command = ["git", "push", verification.remote, "main"]
    result = run_command(
        runner,
        command,
        next_action="fix_git_push_auth_or_remote_before_retrying_verified_push",
    )
    summary = base_summary(args, verification, branch)
    summary.update(
        {
            "action": "push",
            "worktree_dirty": dirty,
            "command": command,
            "git_push_stdout": result.stdout.strip(),
            "git_push_stderr": result.stderr.strip(),
            "status": "ok",
        }
    )
    return summary


def perform_pr(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
) -> dict[str, object]:
    """Create or update a pull request for the verified branch."""
    body_file = require_body_file(args.body_file)
    existing = existing_open_pr(runner, repo=verification.repo, branch=branch)
    summary = base_summary(args, verification, branch)
    if existing is not None:
        number = int_field(existing, "number")
        if args.update_existing and number is not None:
            command = [
                "gh",
                "pr",
                "edit",
                str(number),
                "--repo",
                verification.repo,
                "--title",
                args.title,
                "--body-file",
                str(body_file),
            ]
            result = run_command(
                runner,
                command,
                next_action="fix_gh_pr_edit_auth_or_update_the_pr_body_manually",
            )
            summary.update(
                {
                    "action": "pr-update",
                    "status": "ok",
                    "pr_number": number,
                    "pr_url": string_field(existing, "url"),
                    "command": command,
                    "gh_stdout": result.stdout.strip(),
                }
            )
            return summary
        summary.update(
            {
                "action": "pr-existing",
                "status": "ok",
                "pr_number": number,
                "pr_url": string_field(existing, "url"),
                "next_action": "use_existing_pr_or_pass_--update-existing",
            }
        )
        return summary

    command = [
        "gh",
        "pr",
        "create",
        "--repo",
        verification.repo,
        "--base",
        args.base,
        "--head",
        branch,
        "--title",
        args.title,
        "--body-file",
        str(body_file),
    ]
    if args.draft:
        command.append("--draft")
    result = run_command(
        runner,
        command,
        next_action="fix_gh_pr_create_auth_or_repository_permissions_before_retrying_verified_pr_create",
    )
    summary.update(
        {
            "action": "pr-create",
            "status": "ok",
            "pr_url": result.stdout.strip(),
            "command": command,
        }
    )
    return summary


def perform_checks(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
) -> dict[str, object]:
    """Show pull-request checks through gh."""
    pr_selector = args.pr or branch
    command = ["gh", "pr", "checks", pr_selector, "--repo", verification.repo]
    if args.watch:
        command.append("--watch")
    else:
        command.append("--watch=false")
    result = runner(command)
    if result.returncode not in {0, 8}:
        raise CommandFailure(
            result=result,
            next_action="fix_gh_pr_checks_auth_or_wait_for_github_checks",
        )
    summary = base_summary(args, verification, branch)
    summary.update(
        {
            "action": "checks",
            "status": "pending" if result.returncode == 8 else "ok",
            "pr_selector": pr_selector,
            "command": command,
            "checks_stdout": result.stdout.strip(),
        }
    )
    if result.returncode == 8:
        summary["next_action"] = "wait_for_github_checks_or_rerun_with_--watch"
    return summary


def summary_lines(summary: Mapping[str, object]) -> list[str]:
    """Return compact key/value output for agent consumption."""
    keys = [
        "status",
        "action",
        "user_task",
        "remote_verified",
        "repo",
        "remote",
        "branch",
        "worktree_dirty",
        "pr_number",
        "pr_url",
        "pr_selector",
        "next_action",
        "verified_remote_policy",
    ]
    lines = []
    for key in keys:
        if key in summary:
            value = summary[key]
            if isinstance(value, bool):
                rendered = "yes" if value else "no"
            else:
                rendered = str(value)
            lines.append(f"{key.upper()}={rendered}")
    return lines


def emit_summary(args: argparse.Namespace, summary: Mapping[str, object]) -> None:
    """Write optional JSON summary and compact stdout."""
    summary_out = getattr(args, "summary_out", None)
    if summary_out:
        path = Path(summary_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for line in summary_lines(summary):
        print(line)


def failure_summary(
    args: argparse.Namespace | None,
    *,
    message: str,
    next_action: str,
) -> dict[str, object]:
    """Return a compact failure summary."""
    user_task = getattr(args, "user_task", "") if args is not None else ""
    return {
        "status": "fail",
        "user_task": user_task,
        "remote_verified": False,
        "error": message[:MAX_ERROR_CHARS],
        "next_action": next_action,
        "verified_remote_policy": "gh_verified_remote_required",
    }


def command_failure_message(exc: CommandFailure) -> str:
    """Return a bounded command failure message."""
    command = " ".join(exc.result.args)
    detail = "\n".join(
        part.strip()
        for part in (exc.result.stderr, exc.result.stdout)
        if part.strip()
    )
    if detail:
        detail = detail[:MAX_ERROR_CHARS]
        return f"command failed ({exc.result.returncode}): {command}\n{detail}"
    return f"command failed ({exc.result.returncode}): {command}"


def run(args: argparse.Namespace, runner: Runner = subprocess_runner) -> dict[str, object]:
    """Run the selected publish action."""
    os.chdir(args.root)
    branch = selected_branch(runner, args.branch)
    verification = verify_remote(runner, repo=args.repo, remote=args.remote)
    if args.action == "push":
        return perform_push(args, runner, verification, branch)
    if args.action == "pr":
        return perform_pr(args, runner, verification, branch)
    if args.action == "publish-pr":
        push_summary = perform_push(args, runner, verification, branch)
        pr_summary = perform_pr(args, runner, verification, branch)
        summary = dict(pr_summary)
        summary["action"] = "publish-pr"
        summary["push"] = push_summary
        return summary
    if args.action == "checks":
        return perform_checks(args, runner, verification, branch)
    raise UserVisibleFailure(
        message=f"unknown action: {args.action}",
        next_action="choose_push_pr_publish-pr_or_checks",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(argv)
        summary = run(args)
        emit_summary(args, summary)
        return 0
    except CommandFailure as exc:
        summary = failure_summary(
            args,
            message=command_failure_message(exc),
            next_action=exc.next_action,
        )
        if args is not None:
            emit_summary(args, summary)
        else:
            print(json.dumps(summary, sort_keys=True))
        return 1
    except UserVisibleFailure as exc:
        summary = failure_summary(args, message=exc.message, next_action=exc.next_action)
        if args is not None:
            emit_summary(args, summary)
        else:
            print(json.dumps(asdict(exc), sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
