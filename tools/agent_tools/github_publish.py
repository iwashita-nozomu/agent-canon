#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Publishes GitHub branches and pull requests through a gh-verified remote route.
# upstream design ../../ROOT_AGENTS.md defines PR mutation authority and non-blocking publish policy.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines the AgentCanon PR workflow.
# upstream design ../../documents/agent-canon-github-remote.md defines canonical GitHub remote policy.
# upstream implementation ./update_lifecycle_contract.py owns immutable PR topology and gate identity.
# downstream design ../../documents/tools/github_publish.md documents the public tool contract.
# downstream implementation ../../tests/agent_tools/test_github_publish.py validates command construction.
# @dependency-end
"""Publish GitHub branches and pull requests with explicit gh-backed evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from artifact_identity import canonical_json_bytes
from update_lifecycle_contract import (
    binding_identity,
    materialize_gate_verdict,
    pull_request_branch_table,
    validate_candidate_cas_pr_transition,
    validate_candidate_cas_receipt,
    validate_gate_chain,
    validate_gate_verdict,
    validate_pull_request_lifecycle,
    validate_pull_request_transition,
    validate_record_binding,
)

MAX_ERROR_CHARS = 4000
REMOTE_SCP_RE = re.compile(r"^[^@]+@[^:]+:(?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$")
GITHUB_PUBLICATION_PACKET_SCHEMA = "agent-canon.github-publication-packet.v1"


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
    topology_kind: str = "user"
    head_repo: str = ""
    fork_parent_repo: str = ""
    permission_state: str = "unknown"
    permission_evidence_id: str = ""
    actor_id: str = "viewer:unknown"
    actor_display_name: str = "GitHub authenticated viewer"


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
    command.extend(["--json", "nameWithOwner,url,sshUrl,viewerPermission"])
    result = run_command(
        runner,
        command,
        next_action="authenticate_gh_and_verify_the_target_repository",
    )
    return json_object(result.stdout, command="gh repo view")


def gh_authenticated_actor(runner: Runner) -> tuple[str, str]:
    """Return the authenticated GitHub actor from an identity-owning endpoint."""
    command = ["gh", "api", "user", "--jq", "{id: .id, login: .login, name: .name}"]
    result = run_command(
        runner,
        command,
        next_action="authenticate_gh_and_read_the_verified_actor_identity",
    )
    actor = json_object(result.stdout, command="gh api user")
    actor_number = actor.get("id")
    login = actor.get("login")
    display_name = actor.get("name")
    if not isinstance(actor_number, int) or not isinstance(login, str) or not login:
        raise UserVisibleFailure(
            message="gh api user did not expose immutable actor identity",
            next_action="authenticate_gh_and_read_the_verified_actor_identity",
        )
    display = display_name if isinstance(display_name, str) and display_name else login
    return f"github-user:{actor_number}", display


def gh_head_repo_metadata(runner: Runner, repo: str) -> Mapping[str, object]:
    """Read fork-parent and permission identity for a non-base head repository."""
    command = [
        "gh",
        "repo",
        "view",
        repo,
        "--json",
        "nameWithOwner,url,sshUrl,viewerPermission,parent",
    ]
    result = run_command(
        runner,
        command,
        next_action="verify_the_fork_head_repository_and_parent_identity",
    )
    return json_object(result.stdout, command="gh repo view head")


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
    if remote_slug is None:
        raise UserVisibleFailure(
            message=f"remote {remote!r} has an unrecognized GitHub identity",
            next_action="fix_origin_remote_or_pass_the_correct_--repo_verified_remote_required",
        )
    topology_kind = "user"
    fork_parent_repo = ""
    permission_metadata = metadata
    if remote_slug != name_with_owner:
        head_metadata = gh_head_repo_metadata(runner, remote_slug)
        parent = head_metadata.get("parent")
        parent_name = parent.get("nameWithOwner") if isinstance(parent, Mapping) else None
        if head_metadata.get("nameWithOwner") != remote_slug or parent_name != name_with_owner:
            raise UserVisibleFailure(
                message=(
                    f"remote {remote!r} points at {remote_slug}, which is not a "
                    f"verified fork of {name_with_owner}"
                ),
                next_action="materialize_the_typed_multiple_remotes_or_contributor_lifecycle",
            )
        topology_kind = "fork"
        fork_parent_repo = name_with_owner
        permission_metadata = head_metadata
    viewer_permission = permission_metadata.get("viewerPermission")
    if viewer_permission in {"ADMIN", "MAINTAIN", "WRITE"}:
        permission_state = "verified_true"
    elif isinstance(viewer_permission, str):
        permission_state = "verified_false"
    else:
        permission_state = "unknown"
    permission_evidence = {
        "repo": name_with_owner,
        "head_repo": remote_slug,
        "topology_kind": topology_kind,
        "remote": remote,
        "remote_url_sha256": "sha256:"
        + hashlib.sha256(remote_url.encode()).hexdigest(),
        "viewer_permission": viewer_permission,
        "permission_state": permission_state,
        "authority_source": "gh repo view viewerPermission",
    }
    permission_evidence_id = "evidence:" + hashlib.sha256(
        canonical_json_bytes(permission_evidence)
    ).hexdigest()
    actor_id, actor_display_name = gh_authenticated_actor(runner)
    return RemoteVerification(
        repo=name_with_owner,
        remote=remote,
        remote_url=remote_url,
        remote_slug=remote_slug,
        topology_kind=topology_kind,
        head_repo=remote_slug,
        fork_parent_repo=fork_parent_repo,
        permission_state=permission_state,
        permission_evidence_id=permission_evidence_id,
        actor_id=actor_id,
        actor_display_name=actor_display_name,
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


def pull_request_readback(
    runner: Runner,
    *,
    repo: str,
    selector: str,
) -> Mapping[str, object]:
    """Read one PR identity and retained review history after mutation."""
    command = [
        "gh",
        "pr",
        "view",
        selector,
        "--repo",
        repo,
        "--json",
        "number,url,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,reviewDecision,reviews,mergeCommit",
    ]
    result = run_command(
        runner,
        command,
        next_action="read_back_the_exact_pull_request_identity",
    )
    return json_object(result.stdout, command="gh pr view")


def lifecycle_with_pr_readback(
    lifecycle: Mapping[str, object],
    readback: Mapping[str, object],
) -> dict[str, object]:
    """Preserve Essence/reviews while classifying one typed PR state."""
    checked = validate_pull_request_lifecycle(lifecycle)
    base = cast(Mapping[str, object], checked["base_identity"])
    head = cast(Mapping[str, object], checked["head_identity"])
    if readback.get("baseRefName") != str(base["ref"]).removeprefix("refs/heads/"):
        raise UserVisibleFailure(
            message="pull request base identity changed after publication",
            next_action="materialize_a_conflict_successor_lifecycle",
        )
    if readback.get("baseRefOid") != base["commit_sha"]:
        raise UserVisibleFailure(
            message="pull request base commit changed after publication",
            next_action="materialize_a_conflict_successor_lifecycle",
        )
    if readback.get("headRefName") != str(head["ref"]).removeprefix("refs/heads/"):
        raise UserVisibleFailure(
            message="pull request head ref changed after publication",
            next_action="materialize_a_conflict_successor_lifecycle",
        )
    if readback.get("headRefOid") != head["commit_sha"]:
        raise UserVisibleFailure(
            message="pull request head commit differs from the frozen candidate",
            next_action="materialize_a_conflict_successor_lifecycle",
        )
    head_repository = readback.get("headRepository")
    expected_head_repo = f"{head['repo_owner']}/{head['repo_name']}"
    if (
        not isinstance(head_repository, Mapping)
        or head_repository.get("nameWithOwner") != expected_head_repo
    ):
        raise UserVisibleFailure(
            message="pull request head repository changed after publication",
            next_action="materialize_a_conflict_successor_lifecycle",
        )
    remote_state = str(readback.get("state", "")).upper()
    review_decision = str(readback.get("reviewDecision", "")).upper()
    if remote_state == "MERGED":
        state = "merged"
    elif remote_state == "CLOSED":
        state = "closed_head"
    elif readback.get("isDraft") is True:
        state = "draft"
    elif review_decision == "CHANGES_REQUESTED":
        state = "changes_requested"
    elif review_decision == "REVIEW_REQUIRED":
        state = "external_review"
    else:
        state = "ready"
    retained_reviews = list(cast(Sequence[object], checked["reviews"]))
    remote_reviews = readback.get("reviews")
    if isinstance(remote_reviews, list):
        for index, item in enumerate(remote_reviews):
            if not isinstance(item, Mapping):
                continue
            author = item.get("author")
            reviewer = "unknown"
            if isinstance(author, Mapping) and isinstance(author.get("login"), str):
                reviewer = cast(str, author["login"])
            raw_state = str(item.get("state", "COMMENTED")).lower()
            if raw_state not in {
                "approved",
                "changes_requested",
                "commented",
                "dismissed",
            }:
                raw_state = "commented"
            body = str(item.get("body", ""))
            review = {
                "review_id": str(item.get("id") or f"readback:{index}:{reviewer}"),
                "reviewer_id": reviewer,
                "state": raw_state,
                "body_digest": _sha256(body),
            }
            if review not in retained_reviews:
                retained_reviews.append(review)
    updated = dict(checked)
    updated["state"] = state
    updated["reviews"] = retained_reviews
    updated_binding = dict(cast(Mapping[str, object], checked["binding"]))
    readback_ref = _evidence_ref(
        {
            "predecessor_evidence_ref": updated_binding["evidence_ref"],
            "readback": readback,
            "state": state,
            "reviews": retained_reviews,
        }
    )
    updated_binding["evidence_ref"] = readback_ref
    updated_binding["evidence_digest"] = "sha256:" + readback_ref.removeprefix(
        "evidence:"
    )
    updated["binding"] = updated_binding
    return validate_pull_request_transition(checked, updated)


def string_field(mapping: Mapping[str, object], key: str) -> str:
    """Return a mapping field as a string."""
    value = mapping.get(key)
    return value if isinstance(value, str) else ""


def int_field(mapping: Mapping[str, object], key: str) -> int | None:
    """Return a mapping field as an int."""
    value = mapping.get(key)
    return value if isinstance(value, int) else None


def _sha256(value: object) -> str:
    """Return one canonical prefixed digest."""
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _evidence_ref(value: object) -> str:
    """Return one canonical evidence identity."""
    return "evidence:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _git_object_id(runner: Runner, revision: str, *, next_action: str) -> str:
    """Read one exact Git object identity."""
    result = run_command(
        runner,
        ["git", "rev-parse", revision],
        next_action=next_action,
    )
    value = result.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise UserVisibleFailure(
            message=f"git revision did not resolve to a commit/tree identity: {revision}",
            next_action=next_action,
        )
    return value


def _permission_identity(verification: RemoteVerification) -> dict[str, object]:
    """Return verified or explicitly unknown push authority evidence."""
    evidence_id = verification.permission_evidence_id
    if not re.fullmatch(r"evidence:[0-9a-f]{64}", evidence_id):
        evidence_id = _evidence_ref(
            {
                "repo": verification.repo,
                "remote": verification.remote,
                "permission_state": "unknown",
            }
        )
    return {
        "actor_id": verification.actor_id,
        "permission_state": verification.permission_state,
        "permission_evidence_id": evidence_id,
        "authority_source": "verified gh repository metadata",
        "assumption_forbidden": True,
    }


def _github_base_identity(
    runner: Runner,
    *,
    repo: str,
    ref: str,
) -> tuple[str, str]:
    """Read an exact base commit/tree when the head remote is a fork."""
    command = [
        "gh",
        "api",
        f"repos/{repo}/commits/{ref}",
        "--jq",
        "{commit_sha: .sha, tree_sha: .commit.tree.sha}",
    ]
    result = run_command(
        runner,
        command,
        next_action="read_the_exact_pull_request_base_commit_and_tree",
    )
    identity = json_object(result.stdout, command="gh api base commit")
    commit_sha = string_field(identity, "commit_sha")
    tree_sha = string_field(identity, "tree_sha")
    if (
        re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None
        or re.fullmatch(r"[0-9a-f]{40}", tree_sha) is None
    ):
        raise UserVisibleFailure(
            message="GitHub base identity is incomplete",
            next_action="read_the_exact_pull_request_base_commit_and_tree",
        )
    return commit_sha, tree_sha


def build_pull_request_lifecycle(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
    *,
    state: str | None = None,
    topology_kind: str | None = None,
    contributor_identity: Mapping[str, object] | None = None,
    contributor_diff: Mapping[str, object] | None = None,
    lifecycle_binding: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Materialize one immutable user/fork/contributor PR topology."""
    base_ref = str(getattr(args, "base", "main") or "main")
    kind = topology_kind or verification.topology_kind
    if kind not in {"user", "fork", "contributor"}:
        raise UserVisibleFailure(
            message=f"unsupported pull-request topology: {kind}",
            next_action="materialize_a_typed_user_fork_or_contributor_lifecycle",
        )
    candidate_sha = _git_object_id(
        runner,
        branch,
        next_action="freeze_the_local_candidate_before_github_publication",
    )
    tree_sha = _git_object_id(
        runner,
        f"{candidate_sha}^{{tree}}",
        next_action="freeze_the_local_candidate_tree_before_github_publication",
    )
    external_binding = (
        None
        if lifecycle_binding is None
        else validate_record_binding(lifecycle_binding)
    )
    if external_binding is not None and (
        external_binding["candidate_sha"] != candidate_sha
        or external_binding["tree_sha"] != tree_sha
    ):
        raise UserVisibleFailure(
            message="transaction binding differs from the selected candidate",
            next_action="materialize_a_successor_for_the_changed_candidate",
        )
    if kind == "user" and verification.remote_slug == verification.repo:
        base_sha = _git_object_id(
            runner,
            f"{verification.remote}/{base_ref}",
            next_action="fetch_and_rebind_the_exact_pull_request_base",
        )
        base_tree = _git_object_id(
            runner,
            f"{base_sha}^{{tree}}",
            next_action="read_the_exact_pull_request_base_tree",
        )
    else:
        base_sha, base_tree = _github_base_identity(
            runner,
            repo=verification.repo,
            ref=base_ref,
        )
    body_text = ""
    body_path = getattr(args, "body_file", None)
    if isinstance(body_path, str) and body_path:
        body = require_body_file(body_path)
        body_text = body.read_text(encoding="utf-8")
    input_record = {
        "user_task": str(args.user_task),
        "title": str(getattr(args, "title", "") or ""),
        "body_sha256": _sha256(body_text),
        "repo": verification.repo,
        "head_repo": verification.head_repo or verification.remote_slug,
        "remote": verification.remote,
        "branch": branch,
        "base": base_ref,
        "kind": kind,
    }
    input_digest = (
        _sha256(input_record)
        if external_binding is None
        else cast(str, external_binding["input_digest"])
    )
    transaction_id = (
        "tx:"
        + hashlib.sha256(
            canonical_json_bytes(
                {
                    "input_digest": input_digest,
                    "candidate_sha": candidate_sha,
                    "tree_sha": tree_sha,
                }
            )
        ).hexdigest()
        if external_binding is None
        else cast(str, external_binding["transaction_id"])
    )
    snapshot_id = (
        "snapshot:"
        + hashlib.sha256(
            canonical_json_bytes(
                {
                    "remote": verification.remote,
                    "base_ref": base_ref,
                    "base_sha": base_sha,
                    "base_tree": base_tree,
                }
            )
        ).hexdigest()
        if external_binding is None
        else cast(str, external_binding["snapshot_id"])
    )
    observed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    evidence_seed = {
        "transaction_id": transaction_id,
        "snapshot_id": snapshot_id,
        "candidate_sha": candidate_sha,
        "tree_sha": tree_sha,
        "input_digest": input_digest,
        "permission": _permission_identity(verification),
    }
    evidence_ref = _evidence_ref(evidence_seed)
    binding = {
        "transaction_id": transaction_id,
        "snapshot_id": snapshot_id,
        "candidate_sha": candidate_sha,
        "tree_sha": tree_sha,
        "input_digest": input_digest,
        "tool_id": "github-publish",
        "tool_version": "agent-canon.pull-request-lifecycle.v1",
        "evidence_ref": evidence_ref,
        "evidence_digest": _sha256(evidence_seed),
        "timing": {
            "started_at": observed_at,
            "finished_at": observed_at,
            "last_attempt_at": observed_at,
            "duration_ms": 0,
            "attempt": 1,
            "replayed": False,
        },
    }
    if external_binding is not None:
        binding = dict(external_binding)
        binding["evidence_ref"] = evidence_ref
        binding["evidence_digest"] = _sha256(evidence_seed)
        binding["timing"] = {
            "started_at": observed_at,
            "finished_at": observed_at,
            "last_attempt_at": observed_at,
            "duration_ms": 0,
            "attempt": 1,
            "replayed": False,
        }
    repo_owner, repo_name = verification.repo.split("/", 1)
    head_repo = verification.head_repo or verification.remote_slug
    head_owner, head_name = head_repo.split("/", 1)
    permission = _permission_identity(verification)
    lifecycle_state = state
    if lifecycle_state is None:
        if permission["permission_state"] == "unknown":
            lifecycle_state = "permission_unknown"
        elif permission["permission_state"] == "verified_false":
            lifecycle_state = "permission_denied"
        elif bool(getattr(args, "draft", False)):
            lifecycle_state = "draft"
        else:
            lifecycle_state = "ready"
    essence_evidence = _evidence_ref(
        {
            "problem": args.user_task,
            "title": getattr(args, "title", ""),
            "body_sha256": _sha256(body_text),
        }
    )
    lifecycle = {
        "schema": "agent-canon.pull-request-lifecycle.v1",
        "kind": kind,
        "binding": binding,
        "state": lifecycle_state,
        "remote_identity": {
            "repo_owner": head_owner,
            "repo_name": head_name,
            "remote_name": verification.remote,
            "url_digest": _sha256(verification.remote_url),
            "ref": f"refs/heads/{branch}",
            "commit_sha": candidate_sha,
            "tree_sha": tree_sha,
        },
        "base_identity": {
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "ref": f"refs/heads/{base_ref}",
            "commit_sha": base_sha,
            "tree_sha": base_tree,
        },
        "head_identity": {
            "repo_owner": head_owner,
            "repo_name": head_name,
            "ref": f"refs/heads/{branch}",
            "commit_sha": candidate_sha,
            "tree_sha": tree_sha,
        },
        "branch": pull_request_branch_table(),
        "permission_identity": permission,
        "pr_essence": {
            "problem": str(args.user_task),
            "intent": str(getattr(args, "title", "") or args.user_task),
            "canonical_owner": "agents/workflows/agent-canon-pr-workflow.md",
            "contract_delta": str(getattr(args, "title", "") or args.user_task),
            "evidence_refs": [essence_evidence],
        },
        "reviews": [],
    }
    if kind == "user":
        lifecycle["user_identity"] = {
            "actor_id": verification.actor_id,
            "display_name": verification.actor_display_name,
        }
    elif kind == "fork":
        parent_repo = verification.fork_parent_repo or verification.repo
        parent_owner, parent_name = parent_repo.split("/", 1)
        lifecycle["fork_identity"] = {
            "repo_owner": head_owner,
            "repo_name": head_name,
            "parent_repo_owner": parent_owner,
            "parent_repo_name": parent_name,
            "ref": f"refs/heads/{branch}",
        }
    else:
        if contributor_identity is None or contributor_diff is None:
            raise UserVisibleFailure(
                message="contributor lifecycle requires immutable actor and diff identity",
                next_action="read_the_contributor_pr_head_and_diff_before_processing",
            )
        lifecycle["contributor_identity"] = dict(contributor_identity)
        lifecycle["contributor_diff"] = dict(contributor_diff)
    return validate_pull_request_lifecycle(lifecycle)


def materialize_pr_identity_gate(
    lifecycle: Mapping[str, object],
    candidate_cas_receipt: Mapping[str, object],
    upstream_gate_verdicts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Materialize G3 from G1/G2, exact CAS, topology, and permission."""
    checked = validate_pull_request_lifecycle(lifecycle)
    cas = validate_candidate_cas_receipt(candidate_cas_receipt)
    validate_candidate_cas_pr_transition(cas, checked)
    upstream = validate_gate_chain(
        list(upstream_gate_verdicts),
        expected_gate_ids=("G1", "G2"),
        require_pass=True,
    )
    if any(
        binding_identity(item["binding"]) != binding_identity(checked["binding"])
        for item in (*upstream, cas)
    ):
        raise UserVisibleFailure(
            message="G1/G2/CAS evidence does not bind the selected PR topology",
            next_action="materialize_a_successor_for_the_changed_candidate_or_base",
        )
    permission = cast(Mapping[str, object], checked["permission_identity"])
    if permission["permission_state"] != "verified_true":
        raise UserVisibleFailure(
            message="push permission is not verified true for this immutable PR topology",
            next_action="read_verified_remote_permission_and_create_a_successor_lifecycle",
        )
    binding = cast(Mapping[str, object], checked["binding"])
    upstream_refs = [
        cast(str, cast(Mapping[str, object], item["binding"])["evidence_ref"])
        for item in upstream
    ]
    cas_binding = cast(Mapping[str, object], cas["binding"])
    return materialize_gate_verdict(
        binding=binding,
        gate_id="G3",
        ordered_input_evidence_refs=[
            *upstream_refs,
            cast(str, cas_binding["evidence_ref"]),
            cast(str, binding["evidence_ref"]),
        ],
        invariant="pr_identity_cas",
        output_digest=_sha256({"lifecycle": checked, "cas": cas}),
        owner=f"{Path(__file__).resolve()}#materialize_pr_identity_gate",
        verdict="pass",
        retry_reason=None,
        next_checkpoint=None,
    )


def require_pr_identity_gate(
    lifecycle: Mapping[str, object],
    candidate_cas_receipt: Mapping[str, object],
    upstream_gate_verdicts: Sequence[Mapping[str, object]],
    gate_verdict: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Consume, without recomputing, one exact G3 publication authority."""
    checked = validate_pull_request_lifecycle(lifecycle)
    cas = validate_candidate_cas_receipt(candidate_cas_receipt)
    validate_candidate_cas_pr_transition(cas, checked)
    gate = validate_gate_verdict(gate_verdict)
    if gate["gate_id"] != "G3" or gate["verdict"] != "pass":
        raise UserVisibleFailure(
            message="GitHub mutation requires a passing G3 PR identity/CAS verdict",
            next_action="materialize_the_exact_candidate_permission_and_cas_evidence",
        )
    try:
        validate_gate_chain(
            [*upstream_gate_verdicts, gate],
            expected_gate_ids=("G1", "G2", "G3"),
            require_pass=True,
        )
    except ValueError as exc:
        raise UserVisibleFailure(
            message=f"G3 predecessor chain is invalid: {exc}",
            next_action="materialize_G1_G2_and_CAS_for_the_exact_candidate",
        ) from exc
    cas_binding = cast(Mapping[str, object], cas["binding"])
    gate_inputs = cast(Sequence[object], gate["ordered_input_evidence_refs"])
    if (
        binding_identity(checked["binding"]) != binding_identity(gate["binding"])
        or binding_identity(cas_binding) != binding_identity(gate["binding"])
        or cast(str, cas_binding["evidence_ref"]) not in gate_inputs
    ):
        raise UserVisibleFailure(
            message="G3 evidence does not bind the selected PR lifecycle",
            next_action="create_a_successor_lifecycle_for_the_changed_identity",
        )
    return checked, gate


def materialize_github_publication_packet(
    *,
    lifecycle: Mapping[str, object],
    candidate_cas_receipt: Mapping[str, object],
    upstream_gate_verdicts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Materialize the sole machine packet consumed by GitHub mutations."""
    checked_lifecycle = validate_pull_request_lifecycle(lifecycle)
    checked_cas = validate_candidate_cas_receipt(candidate_cas_receipt)
    upstream = validate_gate_chain(
        list(upstream_gate_verdicts),
        expected_gate_ids=("G1", "G2"),
        require_pass=True,
    )
    gate = materialize_pr_identity_gate(checked_lifecycle, checked_cas, upstream)
    return {
        "schema": GITHUB_PUBLICATION_PACKET_SCHEMA,
        "pull_request_lifecycle": checked_lifecycle,
        "candidate_cas_receipt": checked_cas,
        "upstream_gate_verdicts": list(upstream),
        "g3_gate": gate,
    }


def validate_github_publication_packet(value: object) -> dict[str, object]:
    """Validate one immutable publication packet without rebuilding evidence."""
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "pull_request_lifecycle",
        "candidate_cas_receipt",
        "upstream_gate_verdicts",
        "g3_gate",
    }:
        raise UserVisibleFailure(
            message="GitHub publication packet fields are invalid",
            next_action="materialize_the_canonical_github_publication_packet",
        )
    if value.get("schema") != GITHUB_PUBLICATION_PACKET_SCHEMA:
        raise UserVisibleFailure(
            message="GitHub publication packet schema is invalid",
            next_action="materialize_the_canonical_github_publication_packet",
        )
    upstream_value = value["upstream_gate_verdicts"]
    if not isinstance(upstream_value, Sequence) or isinstance(
        upstream_value, (str, bytes)
    ):
        raise UserVisibleFailure(
            message="GitHub publication predecessor gates are invalid",
            next_action="materialize_G1_and_G2_for_the_exact_candidate",
        )
    lifecycle, gate = require_pr_identity_gate(
        cast(Mapping[str, object], value["pull_request_lifecycle"]),
        cast(Mapping[str, object], value["candidate_cas_receipt"]),
        cast(Sequence[Mapping[str, object]], upstream_value),
        cast(Mapping[str, object], value["g3_gate"]),
    )
    return {
        "schema": GITHUB_PUBLICATION_PACKET_SCHEMA,
        "pull_request_lifecycle": lifecycle,
        "candidate_cas_receipt": validate_candidate_cas_receipt(
            value["candidate_cas_receipt"]
        ),
        "upstream_gate_verdicts": list(
            validate_gate_chain(
                list(upstream_value),
                expected_gate_ids=("G1", "G2"),
                require_pass=True,
            )
        ),
        "g3_gate": gate,
    }


def base_summary(args: argparse.Namespace, verification: RemoteVerification, branch: str) -> dict[str, object]:
    """Return common summary fields."""
    return {
        "user_task": args.user_task,
        "remote_verified": True,
        "repo": verification.repo,
        "remote": verification.remote,
        "remote_url": verification.remote_url,
        "branch": branch,
        "permission_state": verification.permission_state,
        "permission_evidence_id": verification.permission_evidence_id,
        "verified_remote_policy": "gh_verified_remote_required",
    }


def publication_context(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
    *,
    pr_lifecycle: Mapping[str, object] | None,
    candidate_cas_receipt: Mapping[str, object] | None,
    upstream_gate_verdicts: Sequence[Mapping[str, object]],
    g3_gate: Mapping[str, object] | None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Return one topology/G3 pair, materializing it only when absent."""
    lifecycle = (
        build_pull_request_lifecycle(args, runner, verification, branch)
        if pr_lifecycle is None
        else validate_pull_request_lifecycle(pr_lifecycle)
    )
    if candidate_cas_receipt is None:
        raise UserVisibleFailure(
            message="GitHub publication requires the exact reviewed CAS receipt",
            next_action="materialize_CandidateCasReceipt_after_independent_review",
        )
    gate = (
        materialize_pr_identity_gate(
            lifecycle,
            candidate_cas_receipt,
            upstream_gate_verdicts,
        )
        if g3_gate is None
        else dict(g3_gate)
    )
    return require_pr_identity_gate(
        lifecycle,
        candidate_cas_receipt,
        upstream_gate_verdicts,
        gate,
    )


def perform_push(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
    *,
    pr_lifecycle: Mapping[str, object] | None = None,
    candidate_cas_receipt: Mapping[str, object] | None = None,
    upstream_gate_verdicts: Sequence[Mapping[str, object]] = (),
    g3_gate: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Push the verified branch to origin."""
    if branch == "main" and not getattr(args, "allow_main", False):
        raise UserVisibleFailure(
            message="refusing to push main without --allow-main",
            next_action="publish_a_topic_branch_or_pass_--allow-main_with_explicit_authority",
        )
    lifecycle, gate = publication_context(
        args,
        runner,
        verification,
        branch,
        pr_lifecycle=pr_lifecycle,
        candidate_cas_receipt=candidate_cas_receipt,
        upstream_gate_verdicts=upstream_gate_verdicts,
        g3_gate=g3_gate,
    )
    if lifecycle["state"] not in {
        "draft",
        "ready",
        "changes_requested",
        "external_review",
    }:
        raise UserVisibleFailure(
            message=f"PR lifecycle state does not permit push: {lifecycle['state']}",
            next_action="resolve_permission_remote_or_successor_state_before_push",
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
            "pull_request_lifecycle": lifecycle,
            "g3_gate": gate,
            "status": "ok",
        }
    )
    return summary


def perform_pr(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
    *,
    pr_lifecycle: Mapping[str, object] | None = None,
    candidate_cas_receipt: Mapping[str, object] | None = None,
    upstream_gate_verdicts: Sequence[Mapping[str, object]] = (),
    g3_gate: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Create or update a pull request for the verified branch."""
    body_file = require_body_file(args.body_file)
    lifecycle, gate = publication_context(
        args,
        runner,
        verification,
        branch,
        pr_lifecycle=pr_lifecycle,
        candidate_cas_receipt=candidate_cas_receipt,
        upstream_gate_verdicts=upstream_gate_verdicts,
        g3_gate=g3_gate,
    )
    if lifecycle["state"] not in {
        "draft",
        "ready",
        "changes_requested",
        "external_review",
    }:
        raise UserVisibleFailure(
            message=f"PR lifecycle state does not permit PR mutation: {lifecycle['state']}",
            next_action="resolve_permission_remote_or_successor_state_before_pr_mutation",
        )
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
            readback = pull_request_readback(
                runner, repo=verification.repo, selector=str(number)
            )
            lifecycle = lifecycle_with_pr_readback(lifecycle, readback)
            summary.update(
                {
                    "action": "pr-update",
                    "status": "ok",
                    "pr_number": number,
                    "pr_url": string_field(existing, "url"),
                    "command": command,
                    "gh_stdout": result.stdout.strip(),
                    "pull_request_lifecycle": lifecycle,
                    "g3_gate": gate,
                }
            )
            return summary
        readback = pull_request_readback(
            runner,
            repo=verification.repo,
            selector=str(number) if number is not None else branch,
        )
        lifecycle = lifecycle_with_pr_readback(lifecycle, readback)
        summary.update(
            {
                "action": "pr-existing",
                "status": "ok",
                "pr_number": number,
                "pr_url": string_field(existing, "url"),
                "next_action": "use_existing_pr_or_pass_--update-existing",
                "pull_request_lifecycle": lifecycle,
                "g3_gate": gate,
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
    readback = pull_request_readback(
        runner,
        repo=verification.repo,
        selector=branch,
    )
    lifecycle = lifecycle_with_pr_readback(lifecycle, readback)
    summary.update(
        {
            "action": "pr-create",
            "status": "ok",
            "pr_url": result.stdout.strip(),
            "command": command,
            "pr_number": int_field(readback, "number"),
            "pull_request_lifecycle": lifecycle,
            "g3_gate": gate,
        }
    )
    return summary


def perform_checks(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
    *,
    pr_lifecycle: Mapping[str, object] | None = None,
    candidate_cas_receipt: Mapping[str, object] | None = None,
    upstream_gate_verdicts: Sequence[Mapping[str, object]] = (),
    g3_gate: Mapping[str, object] | None = None,
    g5_gate: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Show pull-request checks through gh."""
    lifecycle, gate = publication_context(
        args,
        runner,
        verification,
        branch,
        pr_lifecycle=pr_lifecycle,
        candidate_cas_receipt=candidate_cas_receipt,
        upstream_gate_verdicts=upstream_gate_verdicts,
        g3_gate=g3_gate,
    )
    checked_g5: dict[str, object] | None = None
    if g5_gate is not None:
        checked_g5 = validate_gate_verdict(g5_gate)
        if checked_g5["gate_id"] != "G5" or checked_g5["verdict"] != "pass":
            raise UserVisibleFailure(
                message="publication readback evidence is not a passing G5 verdict",
                next_action="read_back_the_exact_remote_publication_identity",
            )
        if binding_identity(lifecycle["binding"]) != binding_identity(
            checked_g5["binding"]
        ):
            raise UserVisibleFailure(
                message="G5 evidence does not bind the selected PR lifecycle",
                next_action="create_a_successor_lifecycle_for_the_changed_identity",
            )
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
            "pull_request_lifecycle": lifecycle,
            "g3_gate": gate,
            "g5_gate": checked_g5,
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
        "permission_state",
        "permission_evidence_id",
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


def run(
    args: argparse.Namespace,
    runner: Runner = subprocess_runner,
    *,
    publication_packet: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Run the selected publish action."""
    os.chdir(args.root)
    branch = selected_branch(runner, args.branch)
    verification = verify_remote(runner, repo=args.repo, remote=args.remote)
    if publication_packet is None:
        packet_path = Path(
            ".agent-canon/update-lifecycle/state/github-publication.json"
        )
        if not packet_path.is_file():
            raise UserVisibleFailure(
                message="canonical GitHub publication packet is missing",
                next_action="materialize_reviewed_CAS_and_G1_G2_G3_before_mutation",
            )
        loaded = json.loads(packet_path.read_text(encoding="utf-8"))
        publication_packet = cast(Mapping[str, object], loaded)
    packet = validate_github_publication_packet(publication_packet)
    lifecycle = cast(Mapping[str, object], packet["pull_request_lifecycle"])
    cas = cast(Mapping[str, object], packet["candidate_cas_receipt"])
    upstream = cast(
        Sequence[Mapping[str, object]], packet["upstream_gate_verdicts"]
    )
    g3_gate = cast(Mapping[str, object], packet["g3_gate"])
    remote_identity = cast(Mapping[str, object], lifecycle["remote_identity"])
    base_identity = cast(Mapping[str, object], lifecycle["base_identity"])
    permission = cast(Mapping[str, object], lifecycle["permission_identity"])
    expected_head_repo = verification.head_repo or verification.remote_slug
    if (
        f"{remote_identity['repo_owner']}/{remote_identity['repo_name']}"
        != expected_head_repo
        or remote_identity["remote_name"] != verification.remote
        or remote_identity["ref"] != f"refs/heads/{branch}"
        or f"{base_identity['repo_owner']}/{base_identity['repo_name']}"
        != verification.repo
        or permission["actor_id"] != verification.actor_id
        or permission["permission_evidence_id"]
        != verification.permission_evidence_id
    ):
        raise UserVisibleFailure(
            message="publication packet differs from verified immutable GitHub topology",
            next_action="materialize_a_successor_publication_packet",
        )
    if args.action == "push":
        return perform_push(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            upstream_gate_verdicts=upstream,
            g3_gate=g3_gate,
        )
    if args.action == "pr":
        return perform_pr(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            upstream_gate_verdicts=upstream,
            g3_gate=g3_gate,
        )
    if args.action == "publish-pr":
        push_summary = perform_push(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            upstream_gate_verdicts=upstream,
            g3_gate=g3_gate,
        )
        pr_summary = perform_pr(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            upstream_gate_verdicts=upstream,
            g3_gate=g3_gate,
        )
        summary = dict(pr_summary)
        summary["action"] = "publish-pr"
        summary["push"] = push_summary
        return summary
    if args.action == "checks":
        return perform_checks(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            upstream_gate_verdicts=upstream,
            g3_gate=g3_gate,
        )
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
