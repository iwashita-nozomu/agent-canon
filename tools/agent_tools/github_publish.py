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
    validate_gate_verdict,
    validate_pull_request_lifecycle,
)

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
    viewer_permission = metadata.get("viewerPermission")
    if viewer_permission in {"ADMIN", "MAINTAIN", "WRITE"}:
        permission_state = "verified_true"
    elif isinstance(viewer_permission, str):
        permission_state = "verified_false"
    else:
        permission_state = "unknown"
    permission_evidence = {
        "repo": name_with_owner,
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
    actor_digest = hashlib.sha256(name_with_owner.encode()).hexdigest()
    return RemoteVerification(
        repo=name_with_owner,
        remote=remote,
        remote_url=remote_url,
        remote_slug=remote_slug,
        permission_state=permission_state,
        permission_evidence_id=permission_evidence_id,
        actor_id=f"viewer:{actor_digest}",
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
        "number,url,state,isDraft,baseRefName,headRefName,headRefOid,reviewDecision,reviews",
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
    return validate_pull_request_lifecycle(updated)


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


def build_pull_request_lifecycle(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
    *,
    state: str | None = None,
) -> dict[str, object]:
    """Materialize one immutable user PR topology before any GitHub mutation."""
    base_ref = str(getattr(args, "base", "main") or "main")
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
        "remote": verification.remote,
        "branch": branch,
        "base": base_ref,
    }
    input_digest = _sha256(input_record)
    transaction_id = "tx:" + hashlib.sha256(
        canonical_json_bytes(
            {
                "input_digest": input_digest,
                "candidate_sha": candidate_sha,
                "tree_sha": tree_sha,
            }
        )
    ).hexdigest()
    snapshot_id = "snapshot:" + hashlib.sha256(
        canonical_json_bytes(
            {
                "remote": verification.remote,
                "base_ref": base_ref,
                "base_sha": base_sha,
                "base_tree": base_tree,
            }
        )
    ).hexdigest()
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
    repo_owner, repo_name = verification.repo.split("/", 1)
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
        "kind": "user",
        "binding": binding,
        "state": lifecycle_state,
        "remote_identity": {
            "repo_owner": repo_owner,
            "repo_name": repo_name,
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
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "ref": f"refs/heads/{branch}",
            "commit_sha": candidate_sha,
            "tree_sha": tree_sha,
        },
        "branch": pull_request_branch_table(),
        "user_identity": {
            "actor_id": verification.actor_id,
            "display_name": verification.actor_display_name,
        },
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
    return validate_pull_request_lifecycle(lifecycle)


def materialize_pr_identity_gate(
    lifecycle: Mapping[str, object],
) -> dict[str, object]:
    """Materialize G3 once from the immutable topology and permission evidence."""
    checked = validate_pull_request_lifecycle(lifecycle)
    permission = cast(Mapping[str, object], checked["permission_identity"])
    if permission["permission_state"] != "verified_true":
        raise UserVisibleFailure(
            message="push permission is not verified true for this immutable PR topology",
            next_action="read_verified_remote_permission_and_create_a_successor_lifecycle",
        )
    binding = cast(Mapping[str, object], checked["binding"])
    return materialize_gate_verdict(
        binding=binding,
        gate_id="G3",
        ordered_input_evidence_refs=[cast(str, binding["evidence_ref"])],
        invariant="pr_identity_cas",
        output_digest=_sha256(checked),
        owner=f"{Path(__file__).resolve()}#perform_pr",
        verdict="pass",
        retry_reason=None,
        next_checkpoint=None,
    )


def require_pr_identity_gate(
    lifecycle: Mapping[str, object],
    gate_verdict: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Consume, without recomputing, one exact G3 publication authority."""
    checked = validate_pull_request_lifecycle(lifecycle)
    gate = validate_gate_verdict(gate_verdict)
    if gate["gate_id"] != "G3" or gate["verdict"] != "pass":
        raise UserVisibleFailure(
            message="GitHub mutation requires a passing G3 PR identity/CAS verdict",
            next_action="materialize_the_exact_candidate_permission_and_cas_evidence",
        )
    if binding_identity(checked["binding"]) != binding_identity(gate["binding"]):
        raise UserVisibleFailure(
            message="G3 evidence does not bind the selected PR lifecycle",
            next_action="create_a_successor_lifecycle_for_the_changed_identity",
        )
    return checked, gate


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
    g3_gate: Mapping[str, object] | None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Return one topology/G3 pair, materializing it only when absent."""
    lifecycle = (
        build_pull_request_lifecycle(args, runner, verification, branch)
        if pr_lifecycle is None
        else validate_pull_request_lifecycle(pr_lifecycle)
    )
    gate = materialize_pr_identity_gate(lifecycle) if g3_gate is None else dict(g3_gate)
    return require_pr_identity_gate(lifecycle, gate)


def perform_push(
    args: argparse.Namespace,
    runner: Runner,
    verification: RemoteVerification,
    branch: str,
    *,
    pr_lifecycle: Mapping[str, object] | None = None,
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


def run(args: argparse.Namespace, runner: Runner = subprocess_runner) -> dict[str, object]:
    """Run the selected publish action."""
    os.chdir(args.root)
    branch = selected_branch(runner, args.branch)
    verification = verify_remote(runner, repo=args.repo, remote=args.remote)
    lifecycle = build_pull_request_lifecycle(
        args,
        runner,
        verification,
        branch,
    )
    g3_gate = materialize_pr_identity_gate(lifecycle)
    if args.action == "push":
        return perform_push(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
            g3_gate=g3_gate,
        )
    if args.action == "pr":
        return perform_pr(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
            g3_gate=g3_gate,
        )
    if args.action == "publish-pr":
        push_summary = perform_push(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
            g3_gate=g3_gate,
        )
        pr_summary = perform_pr(
            args,
            runner,
            verification,
            branch,
            pr_lifecycle=lifecycle,
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
