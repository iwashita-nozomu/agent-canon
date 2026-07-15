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
import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, cast
from urllib.parse import urlparse

from report_artifact_checks import parse_review_identity

MAX_ERROR_CHARS = 4000
REMOTE_SCP_RE = re.compile(r"^[^@]+@[^:]+:(?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$")
PREDECESSOR_INTEGRATION_SCHEMA_VERSION = "agent_canon.predecessor_integration.v1"
PREDECESSOR_INTEGRATION_PRODUCER = (
    "tools/agent_tools/github_publish.py:predecessor-integration"
)
PREDECESSOR_INTEGRATION_UNIT_ID_PATTERN = r"[a-z][a-z0-9_]{0,63}"
PREDECESSOR_TARGET_REMOTE = "origin"
PREDECESSOR_TARGET_BRANCH = "main"
PREDECESSOR_TARGET_MAIN_REF = "refs/remotes/origin/main"
PREDECESSOR_CLI_RESULT_SCHEMA = "agent_canon.predecessor_integration.cli_result.v1"
PREDECESSOR_CLI_SET_RESULT_SCHEMA = (
    "agent_canon.predecessor_integration.cli_set_result.v1"
)
PREDECESSOR_CLI_ERROR_SCHEMA = "agent_canon.predecessor_integration.cli_error.v1"
PREDECESSOR_RECORD_FIELDS = (
    "schema_version",
    "unit_id",
    "design_path",
    "design_sha256",
    "approve_review_path",
    "approve_review_sha256",
    "source_pr_url",
    "source_pr_number",
    "integrated_source_oid",
    "observed_target_main_oid",
    "produced_at",
    "producer",
    "artifact_sha256",
)
PREDECESSOR_DIGEST_FIELDS = PREDECESSOR_RECORD_FIELDS[:-1]
PREDECESSOR_OID_PATTERN = re.compile(r"[0-9a-f]{40}")
PREDECESSOR_SHA_PATTERN = re.compile(r"[0-9a-f]{64}")
PREDECESSOR_TEMP_MODE = 0o600
PREDECESSOR_FILE_MODE = 0o644
PREDECESSOR_RENAME_NOREPLACE = 1
PREDECESSOR_AT_FDCWD = -100
PREDECESSOR_GENERATED_NAME_ATTEMPTS = 8
PREDECESSOR_ERROR_VALUE_MAX_CHARS = 512


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

PredecessorIntegrationErrorCode = Literal[
    "usage_error",
    "invalid_unit_id",
    "duplicate_unit_id",
    "unit_id_mismatch",
    "integrated_source_oid_mismatch",
    "non_ancestor",
    "malformed_json",
    "truncated_json",
    "stale_record",
    "missing_record",
    "schema_version_mismatch",
    "record_shape_mismatch",
    "path_mismatch",
    "filename_mismatch",
    "record_collision",
    "record_hash_mismatch",
    "design_hash_mismatch",
    "review_hash_mismatch",
    "same_sha_approve_mismatch",
    "archive_hash_mismatch",
    "source_pr_mismatch",
    "git_object_missing",
    "process_failure",
    "serialization_failure",
    "publication_failure",
    "cleanup_failure",
    "set_inconsistency",
]
PredecessorIntegrationPhase = Literal[
    "arguments",
    "load",
    "decode",
    "schema",
    "path",
    "review",
    "remote",
    "pr",
    "git",
    "serialize",
    "publish",
    "cleanup",
    "archive",
    "set",
]


@dataclass(frozen=True)
class PredecessorIntegrationRecord:
    """One immutable, canonical post-merge integration record."""

    schema_version: str
    unit_id: str
    design_path: str
    design_sha256: str
    approve_review_path: str
    approve_review_sha256: str
    source_pr_url: str
    source_pr_number: int
    integrated_source_oid: str
    observed_target_main_oid: str
    produced_at: str
    producer: str
    artifact_sha256: str


@dataclass(frozen=True)
class PredecessorIntegrationError(Exception):
    """One closed typed predecessor-integration failure."""

    code: PredecessorIntegrationErrorCode
    phase: PredecessorIntegrationPhase
    unit_id: str | None
    path: str | None
    field: str | None
    expected: str | None
    observed: str | None
    command: tuple[str, ...] | None
    returncode: int | None
    retryable: bool


@dataclass(frozen=True)
class PredecessorIntegrationVerification:
    """Complete verification result for one predecessor record."""

    record: PredecessorIntegrationRecord
    record_path: Path
    archive_manifest_path: Path
    complete_file_sha256: str
    design_sha256_verified: bool
    approve_review_sha256_verified: bool
    same_sha_approve_verified: bool
    source_pr_identity_verified: bool
    integrated_is_ancestor_of_observed_main: bool
    observed_main_is_ancestor_of_current_main: bool


@dataclass(frozen=True)
class PredecessorIntegrationInput:
    """Explicit paths and expected ID for one set member."""

    expected_unit_id: str
    record_path: Path
    archive_manifest_path: Path


@dataclass(frozen=True)
class PredecessorIntegrationSetVerification:
    """Verified ordered predecessor set and its common source commit."""

    verified_records: tuple[PredecessorIntegrationVerification, ...]
    common_integrated_source_oid: str


class _DuplicatePredecessorKey(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


def _predecessor_error(
    code: PredecessorIntegrationErrorCode,
    phase: PredecessorIntegrationPhase,
    *,
    unit_id: str | None = None,
    path: str | None = None,
    field: str | None = None,
    expected: str | None = None,
    observed: str | None = None,
    command: Sequence[str] | None = None,
    returncode: int | None = None,
    retryable: bool = False,
) -> PredecessorIntegrationError:
    def bounded(value: str | None) -> str | None:
        return value[:PREDECESSOR_ERROR_VALUE_MAX_CHARS] if value is not None else None

    return PredecessorIntegrationError(
        code=code,
        phase=phase,
        unit_id=unit_id,
        path=path,
        field=field,
        expected=bounded(expected),
        observed=bounded(observed),
        command=tuple(command) if command is not None else None,
        returncode=returncode,
        retryable=retryable,
    )


def predecessor_integration_filename(unit_id: str) -> str:
    """Return the sole filename derived from one exact predecessor unit ID."""
    if re.fullmatch(PREDECESSOR_INTEGRATION_UNIT_ID_PATTERN, unit_id) is None:
        raise _predecessor_error(
            "invalid_unit_id",
            "arguments",
            unit_id=unit_id,
            field="unit_id",
            expected=PREDECESSOR_INTEGRATION_UNIT_ID_PATTERN,
            observed=unit_id,
        )
    return f"predecessor_integration.{unit_id}.json"


def _canonical_json_line_bytes(mapping: Mapping[str, object]) -> bytes:
    """Serialize one strict canonical JSON object with exactly one terminal LF."""
    return (
        json.dumps(
            mapping,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


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
    publish_pr.add_argument(
        "--allow-main", action="store_true", help="Allow pushing main."
    )

    checks = subparsers.add_parser("checks", help="Show GitHub PR checks.")
    add_publish_arguments(checks)
    checks.add_argument(
        "--pr", help="PR number, URL, or branch. Defaults to current branch."
    )
    checks.add_argument(
        "--watch", action="store_true", help="Watch checks until completion."
    )

    predecessor = subparsers.add_parser(
        "predecessor-integration",
        help="Publish one immutable post-merge predecessor integration record.",
        exit_on_error=False,
    )
    add_predecessor_integration_arguments(predecessor)

    verify_predecessor = subparsers.add_parser(
        "verify-predecessor-integration",
        help="Verify one explicit archived predecessor integration record.",
        exit_on_error=False,
    )
    add_predecessor_verification_arguments(verify_predecessor)

    verify_predecessor_set = subparsers.add_parser(
        "verify-predecessor-integration-set",
        help="Verify an exact ordered set of predecessor integration records.",
        exit_on_error=False,
    )
    add_predecessor_set_verification_arguments(verify_predecessor_set)
    return parser


def add_predecessor_integration_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the frozen single-unit predecessor producer grammar."""
    parser.add_argument("--user-task", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--design-path", required=True)
    parser.add_argument("--approve-review-path", required=True)


def add_predecessor_verification_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the frozen individual predecessor verification grammar."""
    parser.add_argument("--record", required=True)
    parser.add_argument("--archive-manifest", required=True)
    parser.add_argument("--expected-unit-id", required=True)


def add_predecessor_set_verification_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    """Add the frozen ordered predecessor-set verification grammar."""
    parser.add_argument("--required-unit-id", action="append", required=True)
    parser.add_argument("--record", action="append", required=True)
    parser.add_argument("--archive-manifest", action="append", required=True)


def add_publish_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by publish operations."""
    parser.add_argument(
        "--user-task",
        required=True,
        help="The current user task that authorizes this publish operation.",
    )
    parser.add_argument("--repo", help="GitHub repository in owner/name form.")
    parser.add_argument(
        "--remote", default="origin", help="Git remote to verify. Defaults to origin."
    )
    parser.add_argument(
        "--branch", help="Branch to publish. Defaults to the current branch."
    )
    parser.add_argument(
        "--summary-out",
        help="Optional JSON summary path. Stdout remains a compact key/value report.",
    )


def add_pr_arguments(parser: argparse.ArgumentParser) -> None:
    """Add pull-request creation/update arguments."""
    parser.add_argument("--base", default="main", help="Base branch. Defaults to main.")
    parser.add_argument("--title", required=True, help="Pull request title.")
    parser.add_argument(
        "--body-file", required=True, help="Path to a Markdown PR body file."
    )
    parser.add_argument(
        "--draft", action="store_true", help="Create the PR as a draft."
    )
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
    for item in cast(list[object], loaded):
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


def _normalized_predecessor_path(value: str, *, field: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise _predecessor_error(
            "path_mismatch",
            "path",
            path=value,
            field=field,
            expected="normalized repository-relative POSIX path",
            observed=value,
        )
    return path


def _resolve_predecessor_path(
    root: Path,
    value: str | PurePosixPath,
    *,
    field: str,
    require_file: bool,
) -> Path:
    relative = _normalized_predecessor_path(str(value), field=field)
    root = root.resolve()
    lexical = root
    for component in relative.parts:
        lexical /= component
        if lexical.is_symlink():
            raise _predecessor_error(
                "path_mismatch",
                "path",
                path=relative.as_posix(),
                field=field,
                expected="no-symlink path beneath repository root",
                observed=component,
            )
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise _predecessor_error(
            "path_mismatch",
            "path",
            path=relative.as_posix(),
            field=field,
            expected="existing contained repository path",
            observed="missing_or_outside",
        ) from exc
    if require_file and (not resolved.is_file() or resolved.is_symlink()):
        raise _predecessor_error(
            "path_mismatch",
            "path",
            path=relative.as_posix(),
            field=field,
            expected="regular file",
            observed="nonregular",
        )
    return resolved


def _record_payload_mapping(record: PredecessorIntegrationRecord) -> dict[str, object]:
    value = asdict(record)
    return {field: value[field] for field in PREDECESSOR_DIGEST_FIELDS}


def _record_mapping(record: PredecessorIntegrationRecord) -> dict[str, object]:
    value = asdict(record)
    return {field: value[field] for field in PREDECESSOR_RECORD_FIELDS}


def _record_artifact_sha(record: PredecessorIntegrationRecord) -> str:
    return hashlib.sha256(
        _canonical_json_line_bytes(_record_payload_mapping(record))
    ).hexdigest()


def _reject_predecessor_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicatePredecessorKey(key)
        result[key] = value
    return result


def load_predecessor_integration_record(
    record_path: Path,
) -> PredecessorIntegrationRecord:
    """Load the one strict canonical predecessor record representation."""
    path_text = record_path.as_posix()
    if not record_path.exists():
        raise _predecessor_error(
            "missing_record",
            "load",
            path=path_text,
            field="record_path",
            expected="existing immutable record",
            observed="missing",
            retryable=True,
        )
    if record_path.is_symlink() or not record_path.is_file():
        raise _predecessor_error(
            "path_mismatch",
            "path",
            path=path_text,
            field="record_path",
            expected="regular no-symlink record",
            observed="nonregular",
        )
    payload = record_path.read_bytes()
    trailing_lf = len(payload) - len(payload.rstrip(b"\n"))
    if not payload or trailing_lf != 1:
        raise _predecessor_error(
            "truncated_json",
            "decode",
            path=path_text,
            field="record",
            expected="one complete canonical JSON object plus one LF",
            observed=f"bytes={len(payload)} trailing_lf={trailing_lf}",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        code: PredecessorIntegrationErrorCode = (
            "truncated_json"
            if exc.reason == "unexpected end of data"
            else "malformed_json"
        )
        raise _predecessor_error(
            code,
            "decode",
            path=path_text,
            field="record",
            expected="canonical UTF-8 JSON",
            observed=f"{exc.reason}@{exc.start}",
        ) from exc
    try:
        decoded: object = json.loads(
            text,
            object_pairs_hook=_reject_predecessor_duplicate_keys,
        )
    except _DuplicatePredecessorKey as exc:
        raise _predecessor_error(
            "malformed_json",
            "decode",
            path=path_text,
            field="record",
            expected="unique JSON keys",
            observed=f"duplicate:{exc.key}",
        ) from exc
    except json.JSONDecodeError as exc:
        code = (
            "truncated_json"
            if exc.pos >= len(text) - 1 or exc.msg.startswith("Unterminated string")
            else "malformed_json"
        )
        raise _predecessor_error(
            cast(PredecessorIntegrationErrorCode, code),
            "decode",
            path=path_text,
            field="record",
            expected="canonical JSON",
            observed=f"{exc.msg}@{exc.pos}",
        ) from exc
    if not isinstance(decoded, dict):
        raise _predecessor_error(
            "record_shape_mismatch",
            "schema",
            path=path_text,
            field="record",
            expected=",".join(PREDECESSOR_RECORD_FIELDS),
            observed=type(decoded).__name__,
        )
    mapping = cast(dict[object, object], decoded)
    schema = mapping.get("schema_version")
    if schema != PREDECESSOR_INTEGRATION_SCHEMA_VERSION:
        raise _predecessor_error(
            "schema_version_mismatch",
            "schema",
            path=path_text,
            field="schema_version",
            expected=PREDECESSOR_INTEGRATION_SCHEMA_VERSION,
            observed=str(schema),
        )
    if tuple(mapping) != tuple(sorted(PREDECESSOR_RECORD_FIELDS)) or set(
        mapping
    ) != set(PREDECESSOR_RECORD_FIELDS):
        raise _predecessor_error(
            "record_shape_mismatch",
            "schema",
            path=path_text,
            field="record",
            expected=",".join(sorted(PREDECESSOR_RECORD_FIELDS)),
            observed=",".join(str(key) for key in mapping),
        )
    string_fields = tuple(
        field for field in PREDECESSOR_RECORD_FIELDS if field != "source_pr_number"
    )
    invalid_field = next(
        (field for field in string_fields if not isinstance(mapping.get(field), str)),
        None,
    )
    number = mapping.get("source_pr_number")
    if (
        invalid_field is not None
        or not isinstance(number, int)
        or isinstance(number, bool)
    ):
        field = invalid_field or "source_pr_number"
        raise _predecessor_error(
            "record_shape_mismatch",
            "schema",
            path=path_text,
            field=field,
            expected="string" if invalid_field else "positive integer",
            observed=type(mapping.get(field)).__name__,
        )
    record = PredecessorIntegrationRecord(
        schema_version=cast(str, mapping["schema_version"]),
        unit_id=cast(str, mapping["unit_id"]),
        design_path=cast(str, mapping["design_path"]),
        design_sha256=cast(str, mapping["design_sha256"]),
        approve_review_path=cast(str, mapping["approve_review_path"]),
        approve_review_sha256=cast(str, mapping["approve_review_sha256"]),
        source_pr_url=cast(str, mapping["source_pr_url"]),
        source_pr_number=cast(int, mapping["source_pr_number"]),
        integrated_source_oid=cast(str, mapping["integrated_source_oid"]),
        observed_target_main_oid=cast(str, mapping["observed_target_main_oid"]),
        produced_at=cast(str, mapping["produced_at"]),
        producer=cast(str, mapping["producer"]),
        artifact_sha256=cast(str, mapping["artifact_sha256"]),
    )
    predecessor_integration_filename(record.unit_id)
    if record.source_pr_number <= 0:
        raise _predecessor_error(
            "record_shape_mismatch",
            "schema",
            unit_id=record.unit_id,
            path=path_text,
            field="source_pr_number",
            expected="positive integer",
            observed=str(record.source_pr_number),
        )
    for field in ("design_path", "approve_review_path"):
        _normalized_predecessor_path(getattr(record, field), field=field)
    for field in ("design_sha256", "approve_review_sha256", "artifact_sha256"):
        if PREDECESSOR_SHA_PATTERN.fullmatch(getattr(record, field)) is None:
            raise _predecessor_error(
                "record_shape_mismatch",
                "schema",
                unit_id=record.unit_id,
                path=path_text,
                field=field,
                expected="lowercase SHA-256",
                observed=getattr(record, field),
            )
    for field in ("integrated_source_oid", "observed_target_main_oid"):
        if PREDECESSOR_OID_PATTERN.fullmatch(getattr(record, field)) is None:
            raise _predecessor_error(
                "record_shape_mismatch",
                "schema",
                unit_id=record.unit_id,
                path=path_text,
                field=field,
                expected="full lowercase commit OID",
                observed=getattr(record, field),
            )
    if record.producer != PREDECESSOR_INTEGRATION_PRODUCER:
        raise _predecessor_error(
            "record_shape_mismatch",
            "schema",
            unit_id=record.unit_id,
            path=path_text,
            field="producer",
            expected=PREDECESSOR_INTEGRATION_PRODUCER,
            observed=record.producer,
        )
    try:
        if (
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", record.produced_at)
            is None
        ):
            raise ValueError("timestamp is not canonical UTC seconds with Z")
        datetime.strptime(record.produced_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise _predecessor_error(
            "record_shape_mismatch",
            "schema",
            unit_id=record.unit_id,
            path=path_text,
            field="produced_at",
            expected="UTC RFC 3339 timestamp with Z",
            observed=record.produced_at,
        ) from exc
    canonical = _canonical_json_line_bytes(_record_mapping(record))
    if canonical != payload:
        raise _predecessor_error(
            "record_shape_mismatch",
            "schema",
            unit_id=record.unit_id,
            path=path_text,
            field="record",
            expected="canonical JSON bytes",
            observed="noncanonical",
        )
    computed_artifact_sha = _record_artifact_sha(record)
    if record.artifact_sha256 != computed_artifact_sha:
        raise _predecessor_error(
            "record_hash_mismatch",
            "schema",
            unit_id=record.unit_id,
            path=path_text,
            field="artifact_sha256",
            expected=computed_artifact_sha,
            observed=record.artifact_sha256,
        )
    return record


def _run_predecessor_command(
    runner: Runner,
    command: Sequence[str],
    *,
    unit_id: str,
    phase: PredecessorIntegrationPhase,
    field: str,
    allowed_returncodes: frozenset[int] = frozenset({0}),
) -> CommandResult:
    try:
        result = runner(command)
    except OSError as exc:
        raise _predecessor_error(
            "process_failure",
            phase,
            unit_id=unit_id,
            field=field,
            expected="external command launch",
            observed=type(exc).__name__,
            command=command,
            retryable=True,
        ) from exc
    if result.returncode not in allowed_returncodes:
        raise _predecessor_error(
            "process_failure",
            phase,
            unit_id=unit_id,
            field=field,
            expected=f"returncode in {sorted(allowed_returncodes)}",
            observed=str(result.returncode),
            command=result.args,
            returncode=result.returncode,
            retryable=True,
        )
    return result


def _canonical_pr_selector(pr: str, repo: str, unit_id: str) -> str:
    if pr.isdecimal() and int(pr) > 0:
        return pr
    expected_prefix = f"https://github.com/{repo}/pull/"
    parsed = urlparse(pr)
    if (
        not pr.startswith(expected_prefix)
        or parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or not parsed.path.removeprefix(f"/{repo}/pull/").isdecimal()
        or int(parsed.path.rsplit("/", 1)[-1]) <= 0
    ):
        raise _predecessor_error(
            "usage_error",
            "arguments",
            unit_id=unit_id,
            field="pr",
            expected="positive decimal or canonical verified-repository PR URL",
            observed=pr,
        )
    return pr


def _predecessor_pr_metadata(
    *,
    runner: Runner,
    repo: str,
    pr: str,
    unit_id: str,
) -> tuple[str, int, str]:
    selector = _canonical_pr_selector(pr, repo, unit_id)
    command = (
        "gh",
        "pr",
        "view",
        selector,
        "--repo",
        repo,
        "--json",
        "number,url,state,mergedAt,mergeCommit,baseRefName",
    )
    result = _run_predecessor_command(
        runner,
        command,
        unit_id=unit_id,
        phase="pr",
        field="source_pr",
    )
    try:
        value: object = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise _predecessor_error(
            "source_pr_mismatch",
            "pr",
            unit_id=unit_id,
            field="source_pr",
            expected="gh merged PR JSON",
            observed=f"invalid_json@{exc.pos}",
            command=result.args,
            returncode=result.returncode,
        ) from exc
    if not isinstance(value, dict):
        raise _predecessor_error(
            "source_pr_mismatch",
            "pr",
            unit_id=unit_id,
            field="source_pr",
            expected="gh merged PR object",
            observed=type(value).__name__,
            command=result.args,
            returncode=result.returncode,
        )
    metadata = cast(dict[str, object], value)
    number = metadata.get("number")
    url = metadata.get("url")
    merge_commit = metadata.get("mergeCommit")
    merge_mapping = (
        cast(dict[str, object], merge_commit) if isinstance(merge_commit, dict) else {}
    )
    merge_oid = merge_mapping.get("oid")
    expected_url = f"https://github.com/{repo}/pull/{number}"
    checks = (
        isinstance(number, int) and not isinstance(number, bool) and number > 0,
        isinstance(url, str) and url == expected_url,
        metadata.get("state") == "MERGED",
        isinstance(metadata.get("mergedAt"), str) and bool(metadata.get("mergedAt")),
        metadata.get("baseRefName") == PREDECESSOR_TARGET_BRANCH,
        isinstance(merge_oid, str)
        and PREDECESSOR_OID_PATTERN.fullmatch(merge_oid) is not None,
    )
    if not all(checks):
        raise _predecessor_error(
            "source_pr_mismatch",
            "pr",
            unit_id=unit_id,
            field="source_pr",
            expected=f"merged {repo} PR to main with full merge OID",
            observed=json.dumps(metadata, sort_keys=True)[
                :PREDECESSOR_ERROR_VALUE_MAX_CHARS
            ],
            command=result.args,
            returncode=result.returncode,
        )
    if selector.isdecimal() and int(selector) != number:
        raise _predecessor_error(
            "source_pr_mismatch",
            "pr",
            unit_id=unit_id,
            field="source_pr_number",
            expected=selector,
            observed=str(number),
            command=result.args,
            returncode=result.returncode,
        )
    if selector.startswith("https://") and selector != url:
        raise _predecessor_error(
            "source_pr_mismatch",
            "pr",
            unit_id=unit_id,
            field="source_pr_url",
            expected=selector,
            observed=cast(str, url),
            command=result.args,
            returncode=result.returncode,
        )
    return cast(str, url), cast(int, number), cast(str, merge_oid)


def _same_sha_approve(
    *,
    root: Path,
    report_dir: Path,
    design_path: PurePosixPath,
    review_path: PurePosixPath,
    design_sha256: str,
    unit_id: str,
) -> tuple[Path, Path, str]:
    design = _resolve_predecessor_path(
        root,
        design_path,
        field="design_path",
        require_file=True,
    )
    review = _resolve_predecessor_path(
        root,
        review_path,
        field="approve_review_path",
        require_file=True,
    )
    report_dir = report_dir.resolve()
    try:
        design.relative_to(report_dir)
        review.relative_to(report_dir)
    except ValueError as exc:
        raise _predecessor_error(
            "path_mismatch",
            "path",
            unit_id=unit_id,
            path=review_path.as_posix(),
            field="approve_review_path",
            expected=f"same report directory as {design_path.as_posix()}",
            observed=review_path.as_posix(),
        ) from exc
    observed_design_sha = hashlib.sha256(design.read_bytes()).hexdigest()
    if observed_design_sha != design_sha256:
        raise _predecessor_error(
            "design_hash_mismatch",
            "review",
            unit_id=unit_id,
            path=design_path.as_posix(),
            field="design_sha256",
            expected=design_sha256,
            observed=observed_design_sha,
        )
    review_bytes = review.read_bytes()
    review_sha = hashlib.sha256(review_bytes).hexdigest()
    identity = parse_review_identity(review_bytes.decode("utf-8"))
    declared_design = identity.design_artifact_path
    if declared_design is not None:
        declared_path = _normalized_predecessor_path(
            declared_design,
            field="review.design_artifact_path",
        )
        if len(declared_path.parts) == 1:
            declared_path = PurePosixPath(review_path.parent, declared_path)
    else:
        declared_path = None
    if (
        declared_path != design_path
        or identity.review_target_sha256 != design_sha256
        or not identity.decision_approved
    ):
        raise _predecessor_error(
            "same_sha_approve_mismatch",
            "review",
            unit_id=unit_id,
            path=review_path.as_posix(),
            field="review_identity",
            expected=f"path={design_path.as_posix()} sha={design_sha256} decision=APPROVE",
            observed=(
                f"path={declared_path.as_posix() if declared_path else None} "
                f"sha={identity.review_target_sha256} approved={identity.decision_approved}"
            ),
        )
    return design, review, review_sha


def _rename_predecessor_noreplace(source: Path, target: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        function = libc.renameat2
    except AttributeError as exc:
        raise OSError(errno.ENOSYS, os.strerror(errno.ENOSYS)) from exc
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    result = function(
        PREDECESSOR_AT_FDCWD,
        os.fsencode(source),
        PREDECESSOR_AT_FDCWD,
        os.fsencode(target),
        PREDECESSOR_RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _publish_predecessor_record(
    *,
    target: Path,
    payload: bytes,
    unit_id: str,
) -> None:
    temp: Path | None = None
    temp_identity: tuple[int, int] | None = None
    try:
        for _attempt in range(PREDECESSOR_GENERATED_NAME_ATTEMPTS):
            candidate = target.parent / (
                f".{target.name}.tmp.{os.getpid()}.{secrets.token_hex(16)}"
            )
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    PREDECESSOR_TEMP_MODE,
                )
            except FileExistsError:
                continue
            temp = candidate
            status = os.fstat(descriptor)
            temp_identity = (status.st_dev, status.st_ino)
            try:
                with os.fdopen(descriptor, "wb", closefd=True) as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                raise
            break
        if temp is None:
            raise OSError(errno.EEXIST, "predecessor temp name exhausted")
        before = os.lstat(temp)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != PREDECESSOR_TEMP_MODE
            or (before.st_dev, before.st_ino) != temp_identity
            or temp.read_bytes() != payload
        ):
            raise OSError(errno.EIO, "predecessor temp verification failed")
        _rename_predecessor_noreplace(temp, target)
        temp = None
        os.chmod(target, PREDECESSOR_FILE_MODE, follow_symlinks=False)
        descriptor = os.open(
            target.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        if temp is not None and temp_identity is not None:
            try:
                observed = os.lstat(temp)
                if (observed.st_dev, observed.st_ino) == temp_identity:
                    temp.unlink()
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                raise _predecessor_error(
                    "cleanup_failure",
                    "cleanup",
                    unit_id=unit_id,
                    path=str(temp),
                    field="producer_temp",
                    expected=str(temp_identity),
                    observed=type(cleanup_error).__name__,
                ) from cleanup_error
        code: PredecessorIntegrationErrorCode = (
            "record_collision" if exc.errno == errno.EEXIST else "publication_failure"
        )
        raise _predecessor_error(
            code,
            "publish",
            unit_id=unit_id,
            path=str(target),
            field="record_path",
            expected="durable no-replace publication",
            observed=f"errno={exc.errno}",
        ) from exc


def produce_predecessor_integration_record(
    *,
    root: Path,
    report_dir: Path,
    unit_id: str,
    design_path: PurePosixPath,
    approve_review_path: PurePosixPath,
    pr: str,
    remote: RemoteVerification,
    runner: Runner,
) -> Path:
    """Produce one immutable post-merge predecessor integration record."""
    filename = predecessor_integration_filename(unit_id)
    root = root.resolve()
    if remote.remote != PREDECESSOR_TARGET_REMOTE:
        raise _predecessor_error(
            "source_pr_mismatch",
            "remote",
            unit_id=unit_id,
            field="remote",
            expected=PREDECESSOR_TARGET_REMOTE,
            observed=remote.remote,
        )
    report_relative = PurePosixPath(report_dir)
    report = _resolve_predecessor_path(
        root,
        report_relative,
        field="report_dir",
        require_file=False,
    )
    if not report.is_dir():
        raise _predecessor_error(
            "path_mismatch",
            "path",
            unit_id=unit_id,
            path=report_relative.as_posix(),
            field="report_dir",
            expected="existing report directory",
            observed="non-directory",
        )
    source_pr_url, source_pr_number, integrated_oid = _predecessor_pr_metadata(
        runner=runner,
        repo=remote.repo,
        pr=pr,
        unit_id=unit_id,
    )
    _run_predecessor_command(
        runner,
        ("git", "fetch", PREDECESSOR_TARGET_REMOTE, PREDECESSOR_TARGET_BRANCH),
        unit_id=unit_id,
        phase="git",
        field="origin_main_fetch",
    )
    observed_result = _run_predecessor_command(
        runner,
        ("git", "rev-parse", f"{PREDECESSOR_TARGET_MAIN_REF}^{{commit}}"),
        unit_id=unit_id,
        phase="git",
        field="observed_target_main_oid",
    )
    observed_oid = observed_result.stdout.strip()
    if PREDECESSOR_OID_PATTERN.fullmatch(observed_oid) is None:
        raise _predecessor_error(
            "git_object_missing",
            "git",
            unit_id=unit_id,
            field="observed_target_main_oid",
            expected="full origin/main commit OID",
            observed=observed_oid,
            command=observed_result.args,
            returncode=observed_result.returncode,
        )
    ancestor = _run_predecessor_command(
        runner,
        ("git", "merge-base", "--is-ancestor", integrated_oid, observed_oid),
        unit_id=unit_id,
        phase="git",
        field="integrated_source_oid",
        allowed_returncodes=frozenset({0, 1}),
    )
    if ancestor.returncode == 1:
        raise _predecessor_error(
            "non_ancestor",
            "git",
            unit_id=unit_id,
            field="integrated_source_oid",
            expected=f"ancestor of {observed_oid}",
            observed=integrated_oid,
            command=ancestor.args,
            returncode=1,
        )
    design = _resolve_predecessor_path(
        root,
        design_path,
        field="design_path",
        require_file=True,
    )
    design_sha = hashlib.sha256(design.read_bytes()).hexdigest()
    _design, _review, review_sha = _same_sha_approve(
        root=root,
        report_dir=report,
        design_path=design_path,
        review_path=approve_review_path,
        design_sha256=design_sha,
        unit_id=unit_id,
    )
    provisional = PredecessorIntegrationRecord(
        schema_version=PREDECESSOR_INTEGRATION_SCHEMA_VERSION,
        unit_id=unit_id,
        design_path=design_path.as_posix(),
        design_sha256=design_sha,
        approve_review_path=approve_review_path.as_posix(),
        approve_review_sha256=review_sha,
        source_pr_url=source_pr_url,
        source_pr_number=source_pr_number,
        integrated_source_oid=integrated_oid,
        observed_target_main_oid=observed_oid,
        produced_at=datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        producer=PREDECESSOR_INTEGRATION_PRODUCER,
        artifact_sha256="",
    )
    record = replace(
        provisional,
        artifact_sha256=_record_artifact_sha(provisional),
    )
    try:
        payload = _canonical_json_line_bytes(_record_mapping(record))
    except (TypeError, ValueError) as exc:
        raise _predecessor_error(
            "serialization_failure",
            "serialize",
            unit_id=unit_id,
            field="record",
            expected=PREDECESSOR_INTEGRATION_SCHEMA_VERSION,
            observed=type(exc).__name__,
        ) from exc
    target = report / filename
    if os.path.lexists(target):
        try:
            existing = load_predecessor_integration_record(target)
        except PredecessorIntegrationError as exc:
            raise _predecessor_error(
                "record_collision",
                "publish",
                unit_id=unit_id,
                path=str(target),
                field="record_path",
                expected=hashlib.sha256(payload).hexdigest(),
                observed=exc.code,
            ) from exc
        stable_fields = tuple(
            field for field in PREDECESSOR_DIGEST_FIELDS if field != "produced_at"
        )
        if all(
            getattr(existing, field) == getattr(record, field)
            for field in stable_fields
        ):
            return target
        raise _predecessor_error(
            "record_collision",
            "publish",
            unit_id=unit_id,
            path=str(target),
            field="record_path",
            expected=hashlib.sha256(payload).hexdigest(),
            observed=hashlib.sha256(target.read_bytes()).hexdigest(),
        )
    _publish_predecessor_record(target=target, payload=payload, unit_id=unit_id)
    loaded = load_predecessor_integration_record(target)
    if loaded != record:
        raise _predecessor_error(
            "publication_failure",
            "publish",
            unit_id=unit_id,
            path=str(target),
            field="record_path",
            expected=record.artifact_sha256,
            observed=loaded.artifact_sha256,
        )
    return target


def _archive_manifest_complete_sha(
    *,
    manifest_path: Path,
    record_path: Path,
    unit_id: str,
) -> str:
    if (
        manifest_path.parent != record_path.parent
        or manifest_path.name != "archive_manifest.json"
    ):
        raise _predecessor_error(
            "path_mismatch",
            "archive",
            unit_id=unit_id,
            path=str(manifest_path),
            field="archive_manifest_path",
            expected="sibling archive_manifest.json",
            observed=str(manifest_path),
        )
    try:
        value: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _predecessor_error(
            "archive_hash_mismatch",
            "archive",
            unit_id=unit_id,
            path=str(manifest_path),
            field="archive_manifest",
            expected="valid sibling archive manifest",
            observed=type(exc).__name__,
        ) from exc
    if not isinstance(value, dict):
        raise _predecessor_error(
            "archive_hash_mismatch",
            "archive",
            unit_id=unit_id,
            path=str(manifest_path),
            field="files",
            expected=record_path.name,
            observed="missing",
        )
    manifest = cast(dict[str, object], value)
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise _predecessor_error(
            "archive_hash_mismatch",
            "archive",
            unit_id=unit_id,
            path=str(manifest_path),
            field="files",
            expected=record_path.name,
            observed="missing",
        )
    matches: list[dict[str, object]] = []
    for item in cast(list[object], raw_files):
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, object], item)
        if entry.get("path") == record_path.name:
            matches.append(entry)
    if len(matches) != 1 or not isinstance(matches[0].get("sha256"), str):
        raise _predecessor_error(
            "archive_hash_mismatch",
            "archive",
            unit_id=unit_id,
            path=str(manifest_path),
            field="files.sha256",
            expected=f"one entry for {record_path.name}",
            observed=str(len(matches)),
        )
    return cast(str, matches[0]["sha256"])


def _verification_report_files(
    *,
    root: Path,
    record_path: Path,
    record: PredecessorIntegrationRecord,
) -> tuple[Path, Path]:
    design_original = PurePosixPath(record.design_path)
    review_original = PurePosixPath(record.approve_review_path)
    if design_original.parent != review_original.parent:
        raise _predecessor_error(
            "path_mismatch",
            "path",
            unit_id=record.unit_id,
            path=record.approve_review_path,
            field="approve_review_path",
            expected=design_original.parent.as_posix(),
            observed=review_original.parent.as_posix(),
        )
    snapshot_relative = record_path.parent.resolve().relative_to(root.resolve())
    design_snapshot = PurePosixPath(snapshot_relative.as_posix(), design_original.name)
    review_snapshot = PurePosixPath(snapshot_relative.as_posix(), review_original.name)
    return (
        _resolve_predecessor_path(
            root,
            design_snapshot,
            field="design_path",
            require_file=True,
        ),
        _resolve_predecessor_path(
            root,
            review_snapshot,
            field="approve_review_path",
            require_file=True,
        ),
    )


def _verify_record_review_bytes(
    *,
    root: Path,
    record_path: Path,
    record: PredecessorIntegrationRecord,
) -> tuple[bool, bool, bool]:
    design, review = _verification_report_files(
        root=root,
        record_path=record_path,
        record=record,
    )
    design_sha = hashlib.sha256(design.read_bytes()).hexdigest()
    if design_sha != record.design_sha256:
        raise _predecessor_error(
            "design_hash_mismatch",
            "review",
            unit_id=record.unit_id,
            path=record.design_path,
            field="design_sha256",
            expected=record.design_sha256,
            observed=design_sha,
        )
    review_bytes = review.read_bytes()
    review_sha = hashlib.sha256(review_bytes).hexdigest()
    if review_sha != record.approve_review_sha256:
        raise _predecessor_error(
            "review_hash_mismatch",
            "review",
            unit_id=record.unit_id,
            path=record.approve_review_path,
            field="approve_review_sha256",
            expected=record.approve_review_sha256,
            observed=review_sha,
        )
    identity = parse_review_identity(review_bytes.decode("utf-8"))
    declared = identity.design_artifact_path
    if declared is not None:
        declared_path = _normalized_predecessor_path(
            declared,
            field="review.design_artifact_path",
        )
        if len(declared_path.parts) == 1:
            declared_path = PurePosixPath(
                PurePosixPath(record.approve_review_path).parent, declared_path
            )
    else:
        declared_path = None
    if (
        declared_path != PurePosixPath(record.design_path)
        or identity.review_target_sha256 != record.design_sha256
        or not identity.decision_approved
    ):
        raise _predecessor_error(
            "same_sha_approve_mismatch",
            "review",
            unit_id=record.unit_id,
            path=record.approve_review_path,
            field="review_identity",
            expected=f"path={record.design_path} sha={record.design_sha256} decision=APPROVE",
            observed=(
                f"path={declared_path.as_posix() if declared_path else None} "
                f"sha={identity.review_target_sha256} approved={identity.decision_approved}"
            ),
        )
    return True, True, True


def _verify_predecessor_remote(
    runner: Runner,
    *,
    unit_id: str,
) -> RemoteVerification:
    try:
        return verify_remote(
            runner,
            repo=None,
            remote=PREDECESSOR_TARGET_REMOTE,
        )
    except CommandFailure as exc:
        raise _predecessor_error(
            "process_failure",
            "remote",
            unit_id=unit_id,
            field="remote",
            expected="verified origin repository",
            observed=str(exc.result.returncode),
            command=exc.result.args,
            returncode=exc.result.returncode,
            retryable=True,
        ) from exc
    except UserVisibleFailure as exc:
        raise _predecessor_error(
            "source_pr_mismatch",
            "remote",
            unit_id=unit_id,
            field="remote",
            expected="verified origin repository",
            observed=exc.message,
        ) from exc


def _require_git_commit(
    runner: Runner,
    *,
    unit_id: str,
    oid: str,
    field: str,
) -> None:
    command = ("git", "cat-file", "-e", f"{oid}^{{commit}}")
    result = _run_predecessor_command(
        runner,
        command,
        unit_id=unit_id,
        phase="git",
        field=field,
        allowed_returncodes=frozenset({0, 1, 128}),
    )
    if result.returncode != 0:
        raise _predecessor_error(
            "git_object_missing",
            "git",
            unit_id=unit_id,
            field=field,
            expected=oid,
            observed="missing",
            command=result.args,
            returncode=result.returncode,
        )


def verify_predecessor_integration_record(
    *,
    root: Path,
    record_path: Path,
    archive_manifest_path: Path,
    expected_unit_id: str,
    runner: Runner,
) -> PredecessorIntegrationVerification:
    """Verify one immutable predecessor record without fetching or writing."""
    predecessor_integration_filename(expected_unit_id)
    root = root.resolve()
    record_relative = _normalized_predecessor_path(
        record_path.as_posix(),
        field="record_path",
    )
    manifest_relative = _normalized_predecessor_path(
        archive_manifest_path.as_posix(),
        field="archive_manifest_path",
    )
    record_candidate = root.joinpath(*record_relative.parts)
    if not os.path.lexists(record_candidate):
        raise _predecessor_error(
            "missing_record",
            "load",
            unit_id=expected_unit_id,
            path=record_relative.as_posix(),
            field="record_path",
            expected="existing immutable record",
            observed="missing",
            retryable=True,
        )
    record_file = _resolve_predecessor_path(
        root,
        record_relative,
        field="record_path",
        require_file=True,
    )
    manifest_file = _resolve_predecessor_path(
        root,
        manifest_relative,
        field="archive_manifest_path",
        require_file=True,
    )
    record = load_predecessor_integration_record(record_file)
    if record.unit_id != expected_unit_id:
        raise _predecessor_error(
            "unit_id_mismatch",
            "schema",
            unit_id=record.unit_id,
            path=record_relative.as_posix(),
            field="unit_id",
            expected=expected_unit_id,
            observed=record.unit_id,
        )
    expected_filename = predecessor_integration_filename(record.unit_id)
    if record_file.name != expected_filename:
        raise _predecessor_error(
            "filename_mismatch",
            "path",
            unit_id=record.unit_id,
            path=record_relative.as_posix(),
            field="record_path",
            expected=expected_filename,
            observed=record_file.name,
        )
    complete_sha = hashlib.sha256(record_file.read_bytes()).hexdigest()
    archived_sha = _archive_manifest_complete_sha(
        manifest_path=manifest_file,
        record_path=record_file,
        unit_id=record.unit_id,
    )
    if archived_sha != complete_sha:
        raise _predecessor_error(
            "archive_hash_mismatch",
            "archive",
            unit_id=record.unit_id,
            path=manifest_relative.as_posix(),
            field="files.sha256",
            expected=complete_sha,
            observed=archived_sha,
        )
    design_ok, review_ok, same_sha_ok = _verify_record_review_bytes(
        root=root,
        record_path=record_file,
        record=record,
    )
    remote = _verify_predecessor_remote(runner, unit_id=record.unit_id)
    pr_url, pr_number, merge_oid = _predecessor_pr_metadata(
        runner=runner,
        repo=remote.repo,
        pr=record.source_pr_url,
        unit_id=record.unit_id,
    )
    if (
        pr_url != record.source_pr_url
        or pr_number != record.source_pr_number
        or merge_oid != record.integrated_source_oid
    ):
        raise _predecessor_error(
            "source_pr_mismatch",
            "pr",
            unit_id=record.unit_id,
            path=record_relative.as_posix(),
            field="source_pr",
            expected=f"{record.source_pr_url}:{record.source_pr_number}:{record.integrated_source_oid}",
            observed=f"{pr_url}:{pr_number}:{merge_oid}",
        )
    current_result = _run_predecessor_command(
        runner,
        ("git", "rev-parse", f"{PREDECESSOR_TARGET_MAIN_REF}^{{commit}}"),
        unit_id=record.unit_id,
        phase="git",
        field="current_target_main_oid",
    )
    current_oid = current_result.stdout.strip()
    if PREDECESSOR_OID_PATTERN.fullmatch(current_oid) is None:
        raise _predecessor_error(
            "git_object_missing",
            "git",
            unit_id=record.unit_id,
            field="current_target_main_oid",
            expected="full origin/main commit OID",
            observed=current_oid,
            command=current_result.args,
            returncode=current_result.returncode,
        )
    for field, oid in (
        ("integrated_source_oid", record.integrated_source_oid),
        ("observed_target_main_oid", record.observed_target_main_oid),
        ("current_target_main_oid", current_oid),
    ):
        _require_git_commit(
            runner,
            unit_id=record.unit_id,
            oid=oid,
            field=field,
        )
    integrated_ancestor = _run_predecessor_command(
        runner,
        (
            "git",
            "merge-base",
            "--is-ancestor",
            record.integrated_source_oid,
            record.observed_target_main_oid,
        ),
        unit_id=record.unit_id,
        phase="git",
        field="integrated_source_oid",
        allowed_returncodes=frozenset({0, 1}),
    )
    if integrated_ancestor.returncode == 1:
        raise _predecessor_error(
            "non_ancestor",
            "git",
            unit_id=record.unit_id,
            field="integrated_source_oid",
            expected=record.observed_target_main_oid,
            observed=record.integrated_source_oid,
            command=integrated_ancestor.args,
            returncode=1,
        )
    observed_ancestor = _run_predecessor_command(
        runner,
        (
            "git",
            "merge-base",
            "--is-ancestor",
            record.observed_target_main_oid,
            PREDECESSOR_TARGET_MAIN_REF,
        ),
        unit_id=record.unit_id,
        phase="git",
        field="observed_target_main_oid",
        allowed_returncodes=frozenset({0, 1}),
    )
    if observed_ancestor.returncode == 1:
        raise _predecessor_error(
            "stale_record",
            "git",
            unit_id=record.unit_id,
            path=record_relative.as_posix(),
            field="observed_target_main_oid",
            expected=current_oid,
            observed=record.observed_target_main_oid,
            command=observed_ancestor.args,
            returncode=1,
        )
    return PredecessorIntegrationVerification(
        record=record,
        record_path=record_file,
        archive_manifest_path=manifest_file,
        complete_file_sha256=complete_sha,
        design_sha256_verified=design_ok,
        approve_review_sha256_verified=review_ok,
        same_sha_approve_verified=same_sha_ok,
        source_pr_identity_verified=True,
        integrated_is_ancestor_of_observed_main=True,
        observed_main_is_ancestor_of_current_main=True,
    )


def verify_predecessor_integration_set(
    *,
    root: Path,
    inputs: tuple[PredecessorIntegrationInput, ...],
    required_unit_ids: tuple[str, ...],
    runner: Runner,
) -> PredecessorIntegrationSetVerification:
    """Verify one exact ordered predecessor set in memory."""
    if not required_unit_ids:
        raise _predecessor_error(
            "set_inconsistency",
            "set",
            field="required_unit_ids",
            expected="one or more exact unit IDs",
            observed="empty",
        )
    seen: dict[str, int] = {}
    for index, unit_id in enumerate(required_unit_ids):
        predecessor_integration_filename(unit_id)
        if unit_id in seen:
            raise _predecessor_error(
                "duplicate_unit_id",
                "set",
                unit_id=unit_id,
                field="required_unit_ids",
                expected=str(seen[unit_id]),
                observed=str(index),
            )
        seen[unit_id] = index
    input_ids = tuple(value.expected_unit_id for value in inputs)
    if input_ids != required_unit_ids:
        raise _predecessor_error(
            "set_inconsistency",
            "set",
            field="inputs",
            expected=",".join(required_unit_ids),
            observed=",".join(input_ids),
        )
    if len(set(input_ids)) != len(input_ids):
        repeated = next(value for value in input_ids if input_ids.count(value) > 1)
        raise _predecessor_error(
            "duplicate_unit_id",
            "set",
            unit_id=repeated,
            field="inputs",
            expected="unique IDs",
            observed=repeated,
        )
    archive_parents = {value.archive_manifest_path.parent for value in inputs}
    if len(archive_parents) != 1:
        raise _predecessor_error(
            "set_inconsistency",
            "set",
            field="archive_manifest_path",
            expected="one shared archive snapshot directory",
            observed=",".join(sorted(path.as_posix() for path in archive_parents)),
        )
    verified = tuple(
        verify_predecessor_integration_record(
            root=root,
            record_path=value.record_path,
            archive_manifest_path=value.archive_manifest_path,
            expected_unit_id=value.expected_unit_id,
            runner=runner,
        )
        for value in inputs
    )
    verified_ids = tuple(value.record.unit_id for value in verified)
    if verified_ids != required_unit_ids or len(set(verified_ids)) != len(verified_ids):
        raise _predecessor_error(
            "set_inconsistency",
            "set",
            field="verified_unit_ids",
            expected=",".join(required_unit_ids),
            observed=",".join(verified_ids),
        )
    common_oid = verified[0].record.integrated_source_oid
    for value in verified[1:]:
        if value.record.integrated_source_oid != common_oid:
            raise _predecessor_error(
                "integrated_source_oid_mismatch",
                "set",
                unit_id=value.record.unit_id,
                field="integrated_source_oid",
                expected=common_oid,
                observed=value.record.integrated_source_oid,
            )
    return PredecessorIntegrationSetVerification(verified, common_oid)


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


def base_summary(
    args: argparse.Namespace, verification: RemoteVerification, branch: str
) -> dict[str, object]:
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
    lines: list[str] = []
    for key in keys:
        if key in summary:
            value = summary[key]
            if isinstance(value, bool):
                rendered = "yes" if value else "no"
            else:
                rendered = str(value)
            lines.append(f"{key.upper()}={rendered}")
    return lines


class _CommandEvidenceRunner:
    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.evidence: list[dict[str, object]] = []

    def __call__(self, command: Sequence[str]) -> CommandResult:
        result = self.runner(command)
        self.evidence.append(
            {"argv": list(result.args), "returncode": result.returncode}
        )
        return result


def _producer_remote(
    runner: Runner,
    *,
    repo: str,
    unit_id: str,
) -> RemoteVerification:
    try:
        return verify_remote(
            runner,
            repo=repo,
            remote=PREDECESSOR_TARGET_REMOTE,
        )
    except CommandFailure as exc:
        raise _predecessor_error(
            "process_failure",
            "remote",
            unit_id=unit_id,
            field="remote",
            expected="verified origin repository",
            observed=str(exc.result.returncode),
            command=exc.result.args,
            returncode=exc.result.returncode,
            retryable=True,
        ) from exc
    except UserVisibleFailure as exc:
        raise _predecessor_error(
            "source_pr_mismatch",
            "remote",
            unit_id=unit_id,
            field="remote",
            expected=repo,
            observed=exc.message,
        ) from exc


def _parse_unit_bindings(
    values: Sequence[str],
    *,
    field: str,
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for index, value in enumerate(values):
        unit_id, separator, path = value.partition("=")
        if not separator or not path:
            raise _predecessor_error(
                "usage_error",
                "arguments",
                field=field,
                expected="LOWERCASE_SNAKE_UNIT_ID=REPO_RELATIVE_PATH",
                observed=value,
            )
        predecessor_integration_filename(unit_id)
        if unit_id in result:
            raise _predecessor_error(
                "duplicate_unit_id",
                "set",
                unit_id=unit_id,
                field=field,
                expected="first binding",
                observed=f"repeat_index={index}",
            )
        _normalized_predecessor_path(path, field=field)
        result[unit_id] = Path(path)
    return result


def _verification_summary(
    value: PredecessorIntegrationVerification,
    evidence: list[dict[str, object]],
    *,
    root: Path,
) -> dict[str, object]:
    return {
        "action": "verify-predecessor-integration",
        "archive_manifest_path": value.archive_manifest_path.relative_to(
            root
        ).as_posix(),
        "artifact_sha256": value.record.artifact_sha256,
        "command_evidence": evidence,
        "complete_file_sha256": value.complete_file_sha256,
        "integrated_source_oid": value.record.integrated_source_oid,
        "observed_target_main_oid": value.record.observed_target_main_oid,
        "record_path": value.record_path.relative_to(root).as_posix(),
        "schema": PREDECESSOR_CLI_RESULT_SCHEMA,
        "status": "ok",
        "unit_id": value.record.unit_id,
    }


def run_predecessor_action(
    args: argparse.Namespace,
    runner: Runner,
) -> dict[str, object]:
    """Run one frozen predecessor action and buffer its complete result."""
    root = Path(args.root).resolve()
    recording = _CommandEvidenceRunner(runner)
    if args.action == "predecessor-integration":
        unit_id = str(args.unit_id)
        predecessor_integration_filename(unit_id)
        if not str(args.user_task).strip():
            raise _predecessor_error(
                "usage_error",
                "arguments",
                unit_id=unit_id,
                field="user_task",
                expected="nonempty text",
                observed=str(args.user_task),
            )
        report_path = _normalized_predecessor_path(args.report_dir, field="report_dir")
        design_path = _normalized_predecessor_path(
            args.design_path, field="design_path"
        )
        review_path = _normalized_predecessor_path(
            args.approve_review_path,
            field="approve_review_path",
        )
        target = root.joinpath(*report_path.parts) / predecessor_integration_filename(
            unit_id
        )
        existed = os.path.lexists(target)
        remote = _producer_remote(recording, repo=args.repo, unit_id=unit_id)
        path = produce_predecessor_integration_record(
            root=root,
            report_dir=Path(report_path.as_posix()),
            unit_id=unit_id,
            design_path=design_path,
            approve_review_path=review_path,
            pr=args.pr,
            remote=remote,
            runner=recording,
        )
        record = load_predecessor_integration_record(path)
        complete_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "action": "predecessor-integration",
            "artifact_sha256": record.artifact_sha256,
            "command_evidence": recording.evidence,
            "complete_file_sha256": complete_sha,
            "idempotent": existed,
            "path": path.relative_to(root).as_posix(),
            "schema": PREDECESSOR_CLI_RESULT_SCHEMA,
            "status": "ok",
            "unit_id": unit_id,
        }
    if args.action == "verify-predecessor-integration":
        value = verify_predecessor_integration_record(
            root=root,
            record_path=Path(args.record),
            archive_manifest_path=Path(args.archive_manifest),
            expected_unit_id=args.expected_unit_id,
            runner=recording,
        )
        return _verification_summary(
            value,
            recording.evidence,
            root=root,
        )
    if args.action == "verify-predecessor-integration-set":
        required_ids = tuple(str(value) for value in args.required_unit_id)
        records = _parse_unit_bindings(args.record, field="record")
        manifests = _parse_unit_bindings(
            args.archive_manifest,
            field="archive_manifest",
        )
        if set(records) != set(required_ids) or set(manifests) != set(required_ids):
            raise _predecessor_error(
                "set_inconsistency",
                "set",
                field="unit_bindings",
                expected=",".join(required_ids),
                observed=(
                    f"records={','.join(records)} manifests={','.join(manifests)}"
                ),
            )
        inputs = tuple(
            PredecessorIntegrationInput(
                expected_unit_id=unit_id,
                record_path=records[unit_id],
                archive_manifest_path=manifests[unit_id],
            )
            for unit_id in required_ids
        )
        individual_evidence: list[list[dict[str, object]]] = []

        def per_record_runner(command: Sequence[str]) -> CommandResult:
            if tuple(command[:3]) == ("gh", "repo", "view"):
                individual_evidence.append([])
            if not individual_evidence:
                raise AssertionError("individual verification command order is invalid")
            result = runner(command)
            individual_evidence[-1].append(
                {"argv": list(result.args), "returncode": result.returncode}
            )
            return result

        set_value = verify_predecessor_integration_set(
            root=root,
            inputs=inputs,
            required_unit_ids=required_ids,
            runner=per_record_runner,
        )
        if len(individual_evidence) != len(set_value.verified_records):
            raise _predecessor_error(
                "set_inconsistency",
                "set",
                field="command_evidence",
                expected="one consumed verification per required ID",
                observed=str(len(individual_evidence)),
            )
        records_result: list[dict[str, object]] = []
        for index, value in enumerate(set_value.verified_records):
            summary = _verification_summary(
                value,
                individual_evidence[index],
                root=root,
            )
            records_result.append(
                {
                    key: summary[key]
                    for key in (
                        "artifact_sha256",
                        "command_evidence",
                        "complete_file_sha256",
                        "integrated_source_oid",
                        "observed_target_main_oid",
                        "record_path",
                        "unit_id",
                    )
                }
            )
        return {
            "action": "verify-predecessor-integration-set",
            "common_integrated_source_oid": set_value.common_integrated_source_oid,
            "records": records_result,
            "required_unit_ids": list(required_ids),
            "schema": PREDECESSOR_CLI_SET_RESULT_SCHEMA,
            "status": "ok",
        }
    raise _predecessor_error(
        "usage_error",
        "arguments",
        field="action",
        expected="recognized predecessor action",
        observed=str(args.action),
    )


def emit_summary(args: argparse.Namespace, summary: Mapping[str, object]) -> None:
    """Write optional JSON summary and compact stdout."""
    if getattr(args, "action", "") in {
        "predecessor-integration",
        "verify-predecessor-integration",
        "verify-predecessor-integration-set",
    }:
        sys.stdout.buffer.write(_canonical_json_line_bytes(summary))
        return
    summary_out = getattr(args, "summary_out", None)
    if summary_out:
        path = Path(summary_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
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
        part.strip() for part in (exc.result.stderr, exc.result.stdout) if part.strip()
    )
    if detail:
        detail = detail[:MAX_ERROR_CHARS]
        return f"command failed ({exc.result.returncode}): {command}\n{detail}"
    return f"command failed ({exc.result.returncode}): {command}"


def run(
    args: argparse.Namespace, runner: Runner = subprocess_runner
) -> dict[str, object]:
    """Run the selected publish action."""
    os.chdir(args.root)
    if args.action in {
        "predecessor-integration",
        "verify-predecessor-integration",
        "verify-predecessor-integration-set",
    }:
        return run_predecessor_action(args, runner)
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


def _predecessor_exit_code(error: PredecessorIntegrationError) -> int:
    if error.phase == "arguments" or error.code == "invalid_unit_id":
        return 2
    if error.phase == "set" or error.code in {
        "duplicate_unit_id",
        "integrated_source_oid_mismatch",
        "set_inconsistency",
    }:
        return 6
    if error.code in {
        "source_pr_mismatch",
        "git_object_missing",
        "non_ancestor",
        "process_failure",
    }:
        return 4
    if error.code in {
        "serialization_failure",
        "publication_failure",
        "record_collision",
        "cleanup_failure",
    }:
        return 5
    return 3


def _emit_predecessor_error(
    action: str,
    error: PredecessorIntegrationError,
) -> int:
    exit_code = _predecessor_exit_code(error)
    payload: dict[str, object] = {
        "action": action,
        "code": error.code,
        "command": list(error.command) if error.command is not None else None,
        "exit_code": exit_code,
        "expected": error.expected,
        "field": error.field,
        "observed": error.observed,
        "path": error.path,
        "phase": error.phase,
        "retryable": error.retryable,
        "returncode": error.returncode,
        "schema": PREDECESSOR_CLI_ERROR_SCHEMA,
        "status": "error",
        "unit_id": error.unit_id,
    }
    sys.stderr.buffer.write(_canonical_json_line_bytes(payload))
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(argv)
        summary = run(args)
        emit_summary(args, summary)
        return 0
    except (argparse.ArgumentError, SystemExit) as exc:
        tokens = tuple(argv) if argv is not None else tuple(sys.argv[1:])
        action = next(
            (
                value
                for value in tokens
                if value
                in {
                    "predecessor-integration",
                    "verify-predecessor-integration",
                    "verify-predecessor-integration-set",
                }
            ),
            "",
        )
        if action:
            error = _predecessor_error(
                "usage_error",
                "arguments",
                field="arguments",
                expected="frozen predecessor CLI grammar",
                observed=str(exc),
            )
            return _emit_predecessor_error(action, error)
        raise
    except PredecessorIntegrationError as exc:
        action = getattr(args, "action", "predecessor-integration")
        return _emit_predecessor_error(action, exc)
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
        summary = failure_summary(
            args, message=exc.message, next_action=exc.next_action
        )
        if args is not None:
            emit_summary(args, summary)
        else:
            print(json.dumps(asdict(exc), sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
