#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Reads and transports repository-qualified GitHub Issue metadata through the private log.
# upstream design ../../documents/runtime/private-feedback-knowledge.md private packet policy
# upstream design ../../documents/operations/issue-label-taxonomy.toml GitHub lifecycle labels
# downstream implementation ../../tests/agent_tools/test_issue_sync.py focused GitHub and packet tests
# @dependency-end
"""Host-side GitHub Issue adapter with a private metadata-only offline route.

GitHub Issues are the only durable Issue authority. This module never scans,
creates, edits, or validates an ``issues/`` directory. Offline mode stores a
packet containing a private body locator and digest under the external
``agent-canon-log`` checkout; the body itself never enters AgentCanon source or
the packet. Successful publisher readback is recorded separately as one stable,
body-free receipt under the private log's published Issue-packet namespace;
pending packets are consumed only after that receipt is read back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from .checkout_identity import resolve_checkout_identity
else:
    from checkout_identity import resolve_checkout_identity  # type: ignore[no-redef]

GITHUB_URL_RE = re.compile(r"^https://github\.com/(?P<repo>[^/]+/[^/]+)/issues/(?P<number>[1-9][0-9]*)$")
UTC = timezone.utc
PACKET_SCHEMA = "agent-canon.feedback.issue-packet.v1"
CLAUSE_KINDS = ("problem", "required_action", "done", "close_condition")
FINDING_SCOPES = frozenset({"changed", "user", "owner-bounded", "repo-wide"})
ISSUE_WORKER_HANDOFF_SCHEMA = "agent-canon.issue-worker-handoff.v1"
ISSUE_PUBLICATION_RECEIPT_FIELDS = (
    "repository",
    "number",
    "url",
    "state",
    "action",
    "responsibility",
    "occurrence_locations",
    "source_finding_kind",
    "timestamp",
)
PRIVATE_FEEDBACK_SPOOL_RELATIVE = Path("spool") / "private-feedback"
PRIVATE_FEEDBACK_SYNC_REQUEST_NAME = "sync-request.json"
PRIVATE_FEEDBACK_SYNC_REQUEST_SCHEMA = "agent-canon.private-feedback-sync-request.v1"
NON_DURABLE_FINDING_KINDS = frozenset({
    "count",
    "raw-count",
    "raw_count",
    "status",
    "one-off",
    "one_off",
    "selection",
    "selection-miss",
    "selection_miss",
})


def normalize_repository(value: str) -> str:
    """Normalize GitHub owner/repository values across common transports."""
    text = value.strip()
    if not text:
        return ""
    if "://" in text:
        text = urlsplit(text).path
    elif text.startswith("git@") and ":" in text:
        text = text.split(":", 1)[1]
    text = text.strip("/")
    if text.casefold().endswith(".git"):
        text = text[:-4]
    parts = [part for part in text.split("/") if part]
    if len(parts) >= 2:
        return "/".join(parts[-2:]).casefold()
    return text.casefold()


def normalize_issue_state(value: str) -> str:
    """Normalize GitHub Issue state to the exact ``open``/``closed`` set."""
    state = value.strip().casefold()
    if state not in {"open", "closed"}:
        raise IssueSyncError("issue_state_invalid", "GitHub Issue state must be open or closed")
    return state


class IssueSyncError(RuntimeError):
    """Raised for a typed GitHub/packet boundary failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class GitHubIssueReference:
    """Repository-qualified GitHub Issue identity."""

    repo: str
    number: str

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo}/issues/{self.number}"


@dataclass(frozen=True)
class GitHubIssueRecord:
    """One Issue fetched through the host GitHub adapter."""

    repository: str
    number: str
    title: str
    body: str
    state: str
    url: str

    @property
    def reference(self) -> GitHubIssueReference:
        return GitHubIssueReference(self.repository, self.number)


@dataclass(frozen=True)
class Finding:
    """One owner-routed finding retained independently of GitHub state."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        return f"ISSUE_SYNC_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class IssueSyncReport:
    """Focused report for GitHub records or an explicit lookup requirement."""

    issues: tuple[GitHubIssueRecord, ...]
    findings: tuple[Finding, ...]
    pending_packets: tuple[str, ...] = ()
    github_checked: int = 0
    github_unavailable: int = 0


@dataclass(frozen=True)
class ContainerReceiptStager:
    """Injected executable container route for body-free receipt staging."""

    command_builder: object
    preflight_command: Sequence[str]
    command_runner: object

    def _run(self, command: Sequence[str], failure_code: str) -> object:
        runner = self.command_runner
        if not callable(runner):
            raise IssueSyncError("issue_receipt_route_unavailable", "container command runner is unavailable")
        try:
            result = runner(tuple(command))
        except Exception as exc:
            raise IssueSyncError(failure_code, "container receipt command could not execute") from exc
        returncode = getattr(result, "returncode", result)
        if returncode != 0:
            raise IssueSyncError(failure_code, "container receipt command failed")
        return result

    def preflight(self) -> None:
        """Execute the resident route preflight before GitHub mutation."""
        if not callable(self.command_builder) or not self.preflight_command:
            raise IssueSyncError("issue_receipt_route_unavailable", "container receipt command is unavailable")
        self._run(self.preflight_command, "issue_receipt_route_unavailable")

    def __call__(
        self,
        record: GitHubIssueRecord,
        action: str,
        handoff: IssueWorkerHandoff,
    ) -> object:
        """Execute the resident command after GitHub readback."""
        builder = self.command_builder
        if not callable(builder):
            raise IssueSyncError("issue_receipt_route_unavailable", "container receipt command builder is unavailable")
        try:
            command = builder(record, action, handoff)
        except Exception as exc:
            raise IssueSyncError("issue_receipt_route_unavailable", "container receipt command could not be built") from exc
        if not isinstance(command, (tuple, list)) or not command:
            raise IssueSyncError("issue_receipt_route_unavailable", "container receipt command is empty")
        return self._run(tuple(command), "issue_receipt_write_failed")


def _issue_publication_repo_path(repository: str) -> tuple[str, str]:
    """Return safe owner/repository path components for one Issue receipt."""
    raw_parts = repository.strip().replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise IssueSyncError(
            "issue_receipt_repository_invalid",
            "publication receipt repository contains an empty or dot path component",
        )
    normalized = normalize_repository(repository)
    parts = normalized.split("/")
    if (
        len(parts) != 2
        or not all(re.fullmatch(r"[a-z0-9_.-]+", part) for part in parts)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise IssueSyncError(
            "issue_receipt_repository_invalid",
            "publication receipt repository must be owner/repository",
        )
    return parts[0], parts[1]


def issue_publication_receipt_path(
    log_root: Path,
    repository: str,
    number: str,
) -> Path:
    """Return the stable private-log path for one repository-qualified Issue."""
    owner, repo = _issue_publication_repo_path(repository)
    if not re.fullmatch(r"[1-9][0-9]*", str(number)):
        raise IssueSyncError("issue_receipt_number_invalid", "Issue number is invalid")
    root = log_root.expanduser().resolve(strict=False)
    path = (
        root
        / "feedback"
        / "issue-packets"
        / "published"
        / owner
        / repo
        / f"{number}.json"
    )
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise IssueSyncError(
            "issue_receipt_path_escape",
            "publication receipt path escapes the private log root",
        ) from exc
    return path


def _issue_publication_receipt_payload(
    record: GitHubIssueRecord,
    *,
    action: str,
    handoff: IssueWorkerHandoff | None,
    source_finding_kind: str = "",
    timestamp: str | None = None,
) -> dict[str, object]:
    """Build the body-free, stable-field Issue publication receipt."""
    repository = normalize_repository(record.repository)
    reference = parse_issue_reference(record.url, repository)
    if reference.repo != repository or reference.number != str(record.number):
        raise IssueSyncError(
            "issue_receipt_identity_mismatch",
            "Issue publication receipt URL does not match the readback record",
        )
    if action not in {"create", "update", "reopen", "reorganize", "noop"}:
        raise IssueSyncError("issue_receipt_action_invalid", "Issue publication action is invalid")
    value = source_finding_kind
    if not value and handoff is not None:
        value = handoff.source_finding_kind
    responsibility = list(_receipt_responsibility(handoff))
    return {
        "repository": repository,
        "number": str(record.number),
        "url": record.url,
        "state": normalize_issue_state(record.state),
        "action": action,
        "responsibility": responsibility,
        "occurrence_locations": list(handoff.occurrence_locations) if handoff is not None else [],
        "source_finding_kind": value,
        "timestamp": timestamp
        or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _receipt_responsibility(
    handoff: IssueWorkerHandoff | None,
) -> tuple[str, ...]:
    """Return the exact responsibility tuple persisted in a receipt."""
    if handoff is None:
        return ()
    values = list(handoff.responsibility)
    if handoff.fix and handoff.fix not in values:
        values.append(handoff.fix)
    return tuple(values)


def write_issue_publication_receipt(
    log_root: Path,
    record: GitHubIssueRecord,
    *,
    action: str,
    handoff: IssueWorkerHandoff | None = None,
    source_finding_kind: str = "",
    timestamp: str | None = None,
) -> Path:
    """Persist and read back one metadata-only Issue publication result.

    The path is stable per repository/Issue.  A successful ``noop`` reuses an
    identical existing receipt, while a later update/reopen/reorganization
    replaces the same file so archive Git history records the transition.
    """
    payload = _issue_publication_receipt_payload(
        record,
        action=action,
        handoff=handoff,
        source_finding_kind=source_finding_kind,
        timestamp=timestamp,
    )
    path = issue_publication_receipt_path(log_root, record.repository, record.number)
    temporary: Path | None = None
    prior: bytes | None = None
    prior_mode = 0o600
    replaced = False

    def restore_prior() -> None:
        """Restore the previous bytes atomically, or remove a new file."""
        if prior is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        restore_handle = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.restore.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        )
        restore_path = Path(restore_handle.name)
        try:
            restore_handle.write(prior)
            restore_handle.flush()
            os.fsync(restore_handle.fileno())
        finally:
            restore_handle.close()
        try:
            restore_path.chmod(prior_mode)
            os.replace(restore_path, path)
        finally:
            restore_path.unlink(missing_ok=True)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise IssueSyncError("issue_receipt_conflict", "receipt target is not a regular file")
        root = log_root.expanduser().resolve(strict=False)
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise IssueSyncError(
                    "issue_receipt_path_invalid",
                    "receipt path contains a symlink component",
                )
        if path.exists():
            prior = path.read_bytes()
            prior_mode = path.stat().st_mode & 0o777
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                raise IssueSyncError("issue_receipt_conflict", "existing receipt is not an object")
            immutable = tuple(key for key in ISSUE_PUBLICATION_RECEIPT_FIELDS if key != "timestamp")
            if action == "noop" and all(existing.get(key) == payload[key] for key in immutable):
                payload = {key: existing[key] for key in ISSUE_PUBLICATION_RECEIPT_FIELDS}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        temporary_handle = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        )
        temporary = Path(temporary_handle.name)
        try:
            temporary_handle.write(encoded.encode("utf-8"))
            temporary_handle.flush()
            os.fsync(temporary_handle.fileno())
        finally:
            temporary_handle.close()
        temporary.chmod(0o600)
        observed = json.loads(temporary.read_text(encoding="utf-8"))
        if observed != payload or set(observed) != set(ISSUE_PUBLICATION_RECEIPT_FIELDS):
            raise IssueSyncError("issue_receipt_readback_failed", "publication receipt temp readback differs")
        os.replace(temporary, path)
        temporary = None
        replaced = True
        observed = json.loads(path.read_text(encoding="utf-8"))
    except IssueSyncError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if replaced:
            restore_prior()
        raise
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if replaced:
            restore_prior()
        raise IssueSyncError("issue_receipt_write_failed", "publication receipt could not be written") from exc
    if observed != payload or set(observed) != set(ISSUE_PUBLICATION_RECEIPT_FIELDS):
        if replaced:
            restore_prior()
        raise IssueSyncError("issue_receipt_readback_failed", "publication receipt readback differs")
    return path


def read_issue_publication_receipt(
    log_root: Path,
    repository: str,
    number: str,
) -> dict[str, object] | None:
    """Read one canonical receipt, rejecting path/content identity drift."""
    path = issue_publication_receipt_path(log_root, repository, number)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise IssueSyncError("issue_receipt_invalid", "publication receipt is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IssueSyncError("issue_receipt_invalid", "publication receipt is not valid JSON") from exc
    if not isinstance(value, dict) or set(value) != set(ISSUE_PUBLICATION_RECEIPT_FIELDS):
        raise IssueSyncError("issue_receipt_invalid", "publication receipt fields are invalid")
    payload = dict(value)
    if (
        not isinstance(payload.get("responsibility"), list)
        or not isinstance(payload.get("occurrence_locations"), list)
        or not all(isinstance(item, str) for item in payload["responsibility"])
        or not all(isinstance(item, str) for item in payload["occurrence_locations"])
        or not isinstance(payload.get("repository"), str)
        or not isinstance(payload.get("number"), str)
        or not isinstance(payload.get("url"), str)
        or not isinstance(payload.get("state"), str)
        or not isinstance(payload.get("action"), str)
        or not isinstance(payload.get("source_finding_kind"), str)
        or not isinstance(payload.get("timestamp"), str)
    ):
        raise IssueSyncError("issue_receipt_invalid", "publication receipt values are invalid")
    if payload["action"] not in {"create", "update", "reopen", "reorganize", "noop"}:
        raise IssueSyncError("issue_receipt_invalid", "publication receipt action is invalid")
    if payload["state"] != normalize_issue_state(str(payload["state"])):
        raise IssueSyncError("issue_receipt_invalid", "publication receipt state is not canonical")
    identity = parse_issue_reference(str(payload.get("url") or ""), repository)
    if identity.repo != normalize_repository(repository) or identity.number != str(number):
        raise IssueSyncError("issue_receipt_identity_mismatch", "publication receipt identity differs")
    if payload.get("repository") != normalize_repository(repository):
        raise IssueSyncError("issue_receipt_identity_mismatch", "publication receipt repository differs")
    return payload


def find_issue_publication_receipt(
    log_root: Path,
    repository: str,
    *,
    handoff: IssueWorkerHandoff | None = None,
    number: str = "",
) -> dict[str, object] | None:
    """Find a prior stable receipt for retry idempotency without body matching."""
    if number:
        receipt = read_issue_publication_receipt(log_root, repository, number)
        if receipt is None or handoff is None:
            return receipt
        expected_responsibility = _receipt_responsibility(handoff)
        if (
            tuple(receipt.get("responsibility", ())) != expected_responsibility
            or tuple(receipt.get("occurrence_locations", ())) != handoff.occurrence_locations
            or receipt.get("source_finding_kind") != handoff.source_finding_kind
        ):
            return None
        return receipt
    if handoff is None:
        return None
    published = log_root.expanduser().resolve(strict=False) / "feedback" / "issue-packets" / "published"
    if not published.is_dir() or published.is_symlink():
        return None
    matches: list[dict[str, object]] = []
    expected_responsibility = _receipt_responsibility(handoff)
    for path in sorted(published.rglob("*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get("repository") != normalize_repository(repository):
            continue
        number_value = str(value.get("number") or "")
        try:
            canonical = issue_publication_receipt_path(
                log_root,
                str(value.get("repository") or ""),
                number_value,
            )
        except IssueSyncError:
            continue
        if path.resolve(strict=False) != canonical.resolve(strict=False):
            continue
        if handoff is not None:
            if tuple(value.get("responsibility", ())) != expected_responsibility:
                continue
            if tuple(value.get("occurrence_locations", ())) != handoff.occurrence_locations:
                continue
            if value.get("source_finding_kind") != handoff.source_finding_kind:
                continue
        try:
            validated = read_issue_publication_receipt(
                log_root,
                repository,
                number_value,
            )
        except IssueSyncError:
            continue
        if validated is not None:
            matches.append(validated)
    if len(matches) == 1:
        return matches[0]
    return None


def _runtime_root(explicit: Path | None = None) -> Path:
    """Resolve the explicit external runtime root for resident staging."""
    candidate = explicit
    if candidate is None:
        configured = os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
        candidate = Path(configured) if configured else None
    if candidate is None:
        raise IssueSyncError(
            "runtime-root-required",
            "publication receipt staging requires the external runtime root",
        )
    root = candidate.expanduser().resolve(strict=False)
    if not root.is_absolute() or root.name in {"", ".", ".."}:
        raise IssueSyncError("runtime-root-invalid", "publication receipt runtime root is invalid")
    return root


def issue_publication_receipt_spool_path(
    runtime_root: Path,
    repository: str,
    number: str,
) -> Path:
    """Return the resident-container staging path for one Issue receipt."""
    return issue_publication_receipt_path(
        _runtime_root(runtime_root) / PRIVATE_FEEDBACK_SPOOL_RELATIVE,
        repository,
        number,
    )


def _checkout_identity_value(identity: object | None, key: str) -> str:
    """Read one non-empty field from a checkout identity mapping/object."""
    if identity is None:
        return ""
    if isinstance(identity, Mapping):
        value = identity.get(key)
    else:
        value = getattr(identity, key, "")
    return str(value or "").strip()


def _source_commit_for_sync(
    checkout_identity: object | None = None,
    source_root: Path | None = None,
) -> str:
    """Resolve the source HEAD carried by identity or the explicit checkout."""
    identity_head = _checkout_identity_value(checkout_identity, "head")
    if re.fullmatch(r"[0-9a-f]{40,64}", identity_head):
        return identity_head
    configured = os.environ.get("AGENT_CANON_SOURCE_COMMIT", "").strip()
    if re.fullmatch(r"[0-9a-f]{40,64}", configured):
        return configured
    root = source_root or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value) else ""


def _ensure_private_feedback_sync_request(
    runtime_root: Path,
    *,
    checkout_identity: object | None = None,
    source_root: Path | None = None,
) -> Path:
    """Create the existing body-free private-feedback host sync request."""
    spool = _runtime_root(runtime_root) / PRIVATE_FEEDBACK_SPOOL_RELATIVE
    spool.mkdir(parents=True, exist_ok=True)
    spool.chmod(0o700)
    request = spool / PRIVATE_FEEDBACK_SYNC_REQUEST_NAME
    source_commit = _source_commit_for_sync(checkout_identity, source_root)
    if not source_commit:
        raise IssueSyncError(
            "private-feedback-sync-request-invalid",
            "checkout source commit is unavailable",
        )
    payload = {
        "schema": PRIVATE_FEEDBACK_SYNC_REQUEST_SCHEMA,
        "operation": "sync",
        "execution_plane": "agentcanon_tool_container",
        "requested_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
    }
    if request.is_symlink() or (request.exists() and not request.is_file()):
        raise IssueSyncError("private-feedback-sync-request-invalid", "sync request is not a regular file")
    if request.exists():
        try:
            existing = json.loads(request.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IssueSyncError("private-feedback-sync-request-invalid", "sync request is invalid") from exc
        required = {
            "schema", "operation", "execution_plane", "requested_at", "source_commit"
        }
        if not isinstance(existing, Mapping) or set(existing) != required:
            raise IssueSyncError("private-feedback-sync-request-invalid", "sync request fields are incomplete")
        if (
            existing.get("schema") != PRIVATE_FEEDBACK_SYNC_REQUEST_SCHEMA
            or existing.get("operation") != "sync"
            or existing.get("execution_plane") != "agentcanon_tool_container"
            or not isinstance(existing.get("requested_at"), str)
            or not isinstance(existing.get("source_commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40,64}", str(existing["source_commit"]))
        ):
            raise IssueSyncError("private-feedback-sync-request-invalid", "sync request values are invalid")
        return request
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if not request.exists():
        request.write_text(encoded, encoding="utf-8")
        request.chmod(0o600)
    return request


def stage_issue_publication_receipt(
    runtime_root: Path,
    record: GitHubIssueRecord,
    *,
    action: str,
    handoff: IssueWorkerHandoff | None = None,
    source_finding_kind: str = "",
    timestamp: str | None = None,
    checkout_identity: object | None = None,
    source_root: Path | None = None,
) -> Path:
    """Stage a receipt in the resident private-feedback spool and read it back."""
    root = _runtime_root(runtime_root)
    path = issue_publication_receipt_spool_path(root, record.repository, record.number)
    _ensure_private_feedback_sync_request(
        root,
        checkout_identity=checkout_identity,
        source_root=source_root,
    )
    return write_issue_publication_receipt(
        root / PRIVATE_FEEDBACK_SPOOL_RELATIVE,
        record,
        action=action,
        handoff=handoff,
        source_finding_kind=source_finding_kind,
        timestamp=timestamp,
    )


def build_container_receipt_stager(
    *,
    runtime_root: Path,
    checkout_identity: object | None = None,
    source_root: Path | None = None,
    command_runner: object = subprocess.run,
    bootstrap: str | None = None,
    execution: str = "run",
) -> ContainerReceiptStager:
    """Build the executable resident-container receipt route."""
    try:
        from .tool_calls import build_issue_receipt_stage_command
    except ImportError:  # pragma: no cover - direct script execution
        from tool_calls import build_issue_receipt_stage_command

    identity = (
        checkout_identity.as_dict()
        if hasattr(checkout_identity, "as_dict")
        else dict(checkout_identity)
        if isinstance(checkout_identity, Mapping)
        else {}
    )
    root = _runtime_root(runtime_root)
    bootstrap_path = bootstrap or os.environ.get("AGENT_CANON_BOOTSTRAP", "").strip()
    if not bootstrap_path:
        bootstrap_path = str(Path(__file__).resolve().parents[2] / "bootstrap.sh")
    project_root = source_root or Path(str(identity.get("git_root") or Path.cwd()))
    control_parent = os.environ.get(
        "AGENT_CANON_CONTROL_PARENT_ROOT", "<control-parent-root>"
    )

    def command_builder(
        record: GitHubIssueRecord,
        action: str,
        handoff: IssueWorkerHandoff,
    ) -> tuple[str, ...]:
        return build_issue_receipt_stage_command(
            repository=record.repository,
            runtime_root=str(root),
            source_root=str(project_root),
            control_parent_root=control_parent,
            checkout_identity=identity,
            number=record.number,
            url=record.url,
            state=record.state,
            action=action,
            responsibility=_receipt_responsibility(handoff),
            occurrence_locations=handoff.occurrence_locations,
            source_finding_kind=handoff.source_finding_kind,
            execution=execution,
            bootstrap=bootstrap_path,
        )

    preflight_command = build_issue_receipt_stage_command(
        repository=str(identity.get("remote") or "<checkout-repository>"),
        runtime_root=str(root),
        source_root=str(project_root),
        control_parent_root=control_parent,
        checkout_identity=identity,
        execution=execution,
        bootstrap=bootstrap_path,
        preflight=True,
    )

    def run(command: Sequence[str]) -> object:
        if command_runner is subprocess.run:
            return subprocess.run(
                list(command),
                check=False,
                capture_output=True,
                text=True,
            )
        if not callable(command_runner):
            raise IssueSyncError("issue_receipt_route_unavailable", "container command runner is unavailable")
        return command_runner(tuple(command))

    return ContainerReceiptStager(command_builder, preflight_command, run)


@dataclass(frozen=True)
class IssueWorkerHandoff:
    """Typed result of qualifying one finding for the IssueWorker stage.

    ``qualified`` is the only status that authorizes the logical IssueWorker
    to inspect and mutate GitHub Issues.  ``handoff`` preserves a
    no-mutation route when repository, owner, fix, or checkout identity is
    unavailable, while ``no-action`` preserves the #638 boundary for
    transient or current-scope findings.
    """

    status: str
    reason: str
    repository: str
    owner: str
    fix: str
    occurrence_locations: tuple[str, ...]
    related_issue_refs: tuple[str, ...] = ()
    responsibility: tuple[str, ...] = ()
    schema: str = ISSUE_WORKER_HANDOFF_SCHEMA
    source_finding_kind: str = ""

    @property
    def qualifies(self) -> bool:
        """Return whether this finding should be handed to IssueWorker."""
        return self.status == "qualified"

    @property
    def can_route(self) -> bool:
        """Return whether the same-repository publisher should investigate it."""
        return self.qualifies or self.reason in {"owner-unresolved", "fix-unresolved"}

    def as_dict(self) -> dict[str, object]:
        """Return the stable machine-readable handoff projection."""
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "repository": self.repository,
            "owner": self.owner,
            "fix": self.fix,
            "occurrence_locations": list(self.occurrence_locations),
            "related_issue_refs": list(self.related_issue_refs),
            "responsibility": list(self.responsibility),
            "source_finding_kind": self.source_finding_kind,
        }


@dataclass(frozen=True)
class IssueWorkerPlan:
    """Read-only publication plan returned to the host publisher.

    The plan describes whether an explicit candidate creates, updates, or
    reorganizes an existing related Issue.  It does not perform GitHub
    mutation; the publisher applies the selected operation through
    ``GitHubIssueClient`` and keeps the URL/body/state readback.
    """

    action: str
    handoff: IssueWorkerHandoff
    related_issue_refs: tuple[str, ...] = ()
    destination_issue_ref: str = ""
    foreign_issue_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return the machine-readable, mutation-free plan projection."""
        return {
            "schema": ISSUE_WORKER_HANDOFF_SCHEMA,
            "action": self.action,
            "handoff": self.handoff.as_dict(),
            "related_issue_refs": list(self.related_issue_refs),
            "destination_issue_ref": self.destination_issue_ref,
            "foreign_issue_refs": list(self.foreign_issue_refs),
        }


def _record_text(record: Mapping[str, object], *keys: str) -> str:
    """Return the first non-empty textual field from a finding record."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _record_bool(record: Mapping[str, object], *keys: str) -> bool | None:
    """Return an explicitly supplied boolean without guessing missing evidence."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, bool):
            return value
    return None


def _occurrence_locations(record: Mapping[str, object]) -> tuple[str, ...]:
    """Return occurrence locators explicitly carried by a candidate."""
    value = record.get("occurrence_locations", record.get("occurrence_location"))
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if not isinstance(value, (list, tuple)):
        return ()
    locations: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            locations.append(item.strip())
            continue
        if not isinstance(item, Mapping):
            continue
        path = _record_text(item, "path")
        locator = _record_text(item, "locator", "symbol", "heading")
        if path and locator:
            locations.append(f"{path}::{locator}")
    return tuple(dict.fromkeys(locations))


def _responsibility_tuple(record: Mapping[str, object]) -> tuple[str, ...]:
    """Return the explicit owner/decision/mechanism responsibility tuple."""
    values: list[str] = []
    nested = record.get("responsibility")
    if isinstance(nested, Mapping):
        source = nested
    else:
        source = record
    for key in ("owner", "decision", "mechanism", "validation", "completion"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return tuple(dict.fromkeys(values))


def _make_handoff(
    status: str,
    reason: str,
    repository: str,
    owner: str,
    fix: str,
    occurrence: tuple[str, ...],
    related_refs: tuple[str, ...],
    responsibility: tuple[str, ...],
    source_finding_kind: str,
) -> IssueWorkerHandoff:
    """Construct one handoff while keeping qualification fields together."""
    return IssueWorkerHandoff(
        status,
        reason,
        repository,
        owner,
        fix,
        occurrence,
        related_refs,
        responsibility,
        ISSUE_WORKER_HANDOFF_SCHEMA,
        source_finding_kind,
    )


def qualify_issue_worker_finding(
    record: Mapping[str, object],
    *,
    authenticated_repository: str = "",
) -> IssueWorkerHandoff:
    """Classify one finding for the logical IssueWorker stage.

    Qualification is deliberately candidate-first.  The checkout identity
    supplied by #938 is the repository authority; candidate confirmation flags
    are not a second authority.  Counts, status-only observations, one-offs,
    and findings already closed by the active repair remain local under #638.
    """
    repository = normalize_repository(_record_text(record, "repository", "repo"))
    owner = _record_text(record, "owner", "owner_id")
    fix = _record_text(record, "fix", "required_action", "action")
    status = _record_text(record, "status", "resolution").casefold().replace("_", "-")
    kind = _record_text(
        record,
        "finding_kind",
        "source_finding_kind",
        "kind",
        "category",
    ).casefold().replace("_", "-")
    occurrence = _occurrence_locations(record)
    related = record.get("related_issue_refs", record.get("issue_refs", ()))
    related_refs = tuple(
        value.strip()
        for value in related
        if isinstance(value, str) and value.strip()
    ) if isinstance(related, (list, tuple)) else ()
    responsibility = _responsibility_tuple(record)

    def finish(status_value: str, reason_value: str) -> IssueWorkerHandoff:
        return _make_handoff(
            status_value,
            reason_value,
            repository,
            owner,
            fix,
            occurrence,
            related_refs,
            responsibility,
            kind,
        )

    actionable = _record_bool(record, "actionable")
    if actionable is False:
        return finish("no-action", "not-actionable")
    if kind in NON_DURABLE_FINDING_KINDS:
        return finish("no-action", "non-durable-finding-kind")
    if status in {"resolved", "closed", "current-scope-resolved", "current-scope-closed"}:
        return finish("no-action", "current-scope-resolved")
    if _record_bool(record, "current_scope_resolved", "closed_by_active_repair") is True:
        return finish("no-action", "current-scope-resolved")

    if not repository:
        return finish("handoff", "repository-unresolved")
    if not authenticated_repository:
        return finish("handoff", "checkout-identity-unresolved")
    if repository != normalize_repository(authenticated_repository):
        return finish("handoff", "other-repository")
    if not owner:
        return finish("handoff", "owner-unresolved")
    if not fix:
        return finish("handoff", "fix-unresolved")

    durable = _record_bool(record, "durable_follow_up", "needs_durable_follow_up", "recurrent", "repeatable")
    if durable is False:
        return finish("no-action", "durable-follow-up-not-established")
    return finish("qualified", "user-owned-candidate")


class IssueWorker:
    """Logical IssueWorker boundary over the existing GitHub host adapter."""

    def __init__(self, client: GitHubIssueClient, authenticated_repository: str) -> None:
        self.client = client
        self.authenticated_repository = normalize_repository(authenticated_repository)

    def qualify(self, record: Mapping[str, object]) -> IssueWorkerHandoff:
        """Return a qualification handoff without mutating GitHub."""
        return qualify_issue_worker_finding(
            record, authenticated_repository=self.authenticated_repository
        )

    def related_issue_set(
        self, references: Iterable[str]
    ) -> tuple[GitHubIssueRecord, ...]:
        """Read the repository-qualified open/closed related Issue set."""
        records: list[GitHubIssueRecord] = []
        for value in references:
            reference = parse_issue_reference(value, self.authenticated_repository)
            if normalize_repository(reference.repo) != self.authenticated_repository:
                continue
            records.append(self.client.read(reference))
        return tuple(records)

    def search_related_issue_set(
        self,
        handoff: IssueWorkerHandoff,
    ) -> tuple[GitHubIssueRecord, ...]:
        """Fresh-read candidate Issues before any create operation."""
        search = getattr(self.client, "search", None)
        if not callable(search):
            return ()
        terms = tuple(
            value
            for value in (handoff.owner, handoff.fix, *handoff.responsibility)
            if value.strip()
        )
        records = search(handoff.repository, terms)
        return tuple(
            record
            for record in records
            if normalize_repository(record.repository) == self.authenticated_repository
        )

    @staticmethod
    def _cohesive_issue(
        issue: GitHubIssueRecord,
        handoff: IssueWorkerHandoff,
    ) -> bool:
        """Return whether an Issue contains the candidate responsibility tuple."""
        sections = parse_sections(issue.body)
        if not any(sections.get(kind, "") for kind in (*CLAUSE_KINDS, "finding")):
            return False
        terms = handoff.responsibility or (handoff.owner,)
        responsibility = sections.get("responsibility_boundary", "").casefold()
        if not all(term.casefold() in responsibility for term in terms if term):
            return False
        return any(
            handoff.fix.casefold() in sections.get(kind, "").casefold()
            for kind in ("required_fix", "required_action", "required_investigation_or_fix")
        )

    def _filter_related_issues(
        self,
        handoff: IssueWorkerHandoff,
        related_issues: Iterable[GitHubIssueRecord],
    ) -> tuple[tuple[GitHubIssueRecord, ...], tuple[str, ...]]:
        """Keep only active-checkout Issues; retain foreign refs as handoffs."""
        active = self.authenticated_repository
        candidate = normalize_repository(handoff.repository)
        trusted: list[GitHubIssueRecord] = []
        foreign: list[str] = []
        for issue in related_issues:
            issue_repo = normalize_repository(issue.repository)
            if issue_repo == active and issue_repo == candidate:
                trusted.append(issue)
            else:
                foreign.append(issue.url)
        return tuple(trusted), tuple(dict.fromkeys(foreign))

    def plan_publication(
        self,
        handoff: IssueWorkerHandoff,
        related_issues: Iterable[GitHubIssueRecord] = (),
    ) -> IssueWorkerPlan:
        """Plan one publisher operation after reading related Issues.

        The input may contain both open and closed Issues.  A single exact
        destination is updated or left alone; multiple related Issues are
        returned as a reorganization plan so the publisher can narrow clauses
        and transfer backlinks before any lifecycle change.  No duplicate
        Issue is created by a rerun when an exact destination is already
        present.
        """
        records = tuple(related_issues)
        if not records and handoff.related_issue_refs:
            records = self.related_issue_set(handoff.related_issue_refs)
        refs = tuple(record.url for record in records)
        if not handoff.qualifies:
            return IssueWorkerPlan("no-action", handoff, refs)
        records, foreign_refs = self._filter_related_issues(handoff, records)
        if not records:
            return IssueWorkerPlan("create", handoff, refs, foreign_issue_refs=foreign_refs)
        exact = tuple(
            record
            for record in records
            if normalize_repository(record.repository) == handoff.repository
            and self._cohesive_issue(record, handoff)
        )
        if len(records) > 1:
            destination = exact[0].url if exact else records[0].url
            return IssueWorkerPlan(
                "reorganize", handoff, refs, destination, foreign_refs
            )
        destination = exact[0].url if exact else records[0].url
        if exact:
            if foreign_refs:
                action = "update"
            else:
                action = "reopen" if exact[0].state.upper() == "CLOSED" else "noop"
        else:
            action = "update"
        return IssueWorkerPlan(action, handoff, refs, destination, foreign_refs)

    @staticmethod
    def _append_relation(body: str, relation: str) -> str:
        """Add one idempotent clause-transfer backlink to an Issue body."""
        if relation in body:
            return body
        heading = "## Relations And Clause Transfers"
        if heading in body:
            return f"{body.rstrip()}\n- {relation}\n"
        return f"{body.rstrip()}\n\n{heading}\n\n- {relation}\n"

    @staticmethod
    def _remove_transferred_clauses(
        source_body: str,
        destination_body: str,
    ) -> str:
        """Remove clause lines copied to the destination Issue."""
        destination_sections = parse_sections(destination_body)
        transferred_by_section = {
            kind: {
                line.strip()
                for line in destination_sections.get(kind, "").splitlines()
                if line.strip()
            }
            for kind in (
                *CLAUSE_KINDS,
                "finding",
                "required_fix",
                "required_action",
                "required_investigation_or_fix",
            )
        }
        transferred_by_section = {
            kind: values for kind, values in transferred_by_section.items() if values
        }
        if not transferred_by_section:
            return source_body
        remaining: list[str] = []
        section = ""
        for line in source_body.splitlines():
            match = re.match(r"^##\s+(.+?)\s*$", line)
            if match:
                section = match.group(1).strip().casefold().replace(" ", "_")
            if (
                line.strip()
                and line.strip() in transferred_by_section.get(section, set())
            ):
                continue
            remaining.append(line)
        compact: list[str] = []
        index = 0
        while index < len(remaining):
            line = remaining[index]
            match = re.match(r"^##\s+(.+?)\s*$", line)
            if match:
                kind = match.group(1).strip().casefold().replace(" ", "_")
                end = index + 1
                while end < len(remaining) and not re.match(
                    r"^##\s+(.+?)\s*$", remaining[end]
                ):
                    end += 1
                if kind in (
                    *CLAUSE_KINDS,
                    "finding",
                    "required_fix",
                    "required_action",
                    "required_investigation_or_fix",
                ) and not any(
                    item.strip() for item in remaining[index + 1 : end]
                ):
                    index = end
                    continue
            compact.append(line)
            index += 1
        return "\n".join(compact).strip() + "\n"

    def publish(
        self,
        handoff: IssueWorkerHandoff,
        *,
        title: str,
        body: str,
        related_issues: Iterable[GitHubIssueRecord] = (),
        defer_log_root: Path | None = None,
        body_locator: str = "",
        body_digest: str = "",
        run: str = "",
        task: str = "",
        receipt_stager: ContainerReceiptStager | object | None = None,
        allow_create: bool = True,
    ) -> GitHubIssueRecord:
        """Publish and enqueue a metadata-only retry packet on failure."""
        try:
            if receipt_stager is None or not callable(receipt_stager):
                raise IssueSyncError(
                    "issue_receipt_route_unavailable",
                    "injected resident receipt stager is required before GitHub mutation",
                )
            preflight = getattr(receipt_stager, "preflight", None)
            if not callable(preflight):
                raise IssueSyncError(
                    "issue_receipt_route_unavailable",
                    "receipt stager preflight is unavailable before GitHub mutation",
                )
            try:
                preflight()
            except IssueSyncError:
                raise
            except Exception as exc:
                raise IssueSyncError(
                    "issue_receipt_route_unavailable",
                    "receipt stager preflight failed before GitHub mutation",
                ) from exc
            record, action = self._publish(
                handoff,
                title=title,
                body=body,
                related_issues=related_issues,
                allow_create=allow_create,
            )
            try:
                receipt_stager(record, action, handoff)
            except IssueSyncError:
                raise
            except Exception as exc:
                raise IssueSyncError(
                    "issue_receipt_write_failed",
                    "injected receipt stager failed after GitHub readback",
                ) from exc
            return record
        except IssueSyncError as error:
            if (
                defer_log_root is not None
                and body_locator
                and body_digest
                and error.code != "issue_worker_not_qualified"
            ):
                write_pending_packet(
                    log_root=defer_log_root,
                    repository=handoff.repository,
                    title=title,
                    body_locator=body_locator,
                    body_digest=body_digest,
                    run=run,
                    task=task,
                    input_mode="issue-worker-deferred",
                    reason=error.code,
                    route="issue-worker",
                    handoff=handoff.as_dict(),
                )
            raise

    def _publish(
        self,
        handoff: IssueWorkerHandoff,
        *,
        title: str,
        body: str,
        related_issues: Iterable[GitHubIssueRecord] = (),
        allow_create: bool = True,
    ) -> tuple[GitHubIssueRecord, str]:
        """Apply one planned operation through the host GitHub adapter.

        This method is intentionally owned by the publisher role.  Dashboard,
        resident runtime, and qualification callers use ``plan_publication``
        only and therefore cannot mutate GitHub.
        """
        if not handoff.qualifies:
            raise IssueSyncError(
                "issue_worker_not_qualified",
                f"IssueWorker handoff is {handoff.status}:{handoff.reason}",
            )
        if not title.strip() or not body.strip():
            raise IssueSyncError("issue_worker_content_required", "Issue title and body are required")
        if handoff.repository != self.authenticated_repository:
            raise IssueSyncError(
                "checkout-repository-mismatch",
                "candidate repository does not match the active checkout identity",
            )
        all_records = tuple(related_issues)
        if not all_records and handoff.related_issue_refs:
            all_records = self.related_issue_set(handoff.related_issue_refs)
        discovered = (
            self.search_related_issue_set(handoff)
            if not all_records
            else ()
        )
        by_url = {record.url: record for record in all_records}
        by_url.update({record.url: record for record in discovered})
        all_records = tuple(by_url.values())
        records, _foreign_refs = self._filter_related_issues(handoff, all_records)
        plan = self.plan_publication(handoff, all_records)
        if plan.action == "create":
            if not allow_create:
                raise IssueSyncError(
                    "issue_worker_retry_unresolved",
                    "retry search found no exact same-responsibility Issue",
                )
            candidate_body = body
            for foreign_ref in plan.foreign_issue_refs:
                candidate_body = self._append_relation(
                    candidate_body,
                    f"handoff relation: foreign Issue {foreign_ref}",
                )
            return self.client.create(handoff.repository, title, candidate_body), "create"
        destination = next(
            (record for record in records if record.url == plan.destination_issue_ref),
            None,
        )
        if destination is None:
            destination = self.client.read(
                parse_issue_reference(plan.destination_issue_ref, handoff.repository)
            )
        if plan.action == "noop":
            return destination, "noop"
        if plan.action == "update":
            updated_body = body
            for foreign_ref in plan.foreign_issue_refs:
                updated_body = self._append_relation(
                    updated_body,
                    f"handoff relation: foreign Issue {foreign_ref}",
                )
            if destination.title == title and destination.body == updated_body:
                return destination, "noop"
            return self.client.edit(destination, title=title, body=updated_body), "update"
        if plan.action == "reopen":
            updated = self.client.edit(destination, title=title, body=body)
            return self.client.set_state(updated, "OPEN"), "reopen"
        if plan.action == "reorganize":
            destination_body = body
            for source in records:
                if source.url != destination.url:
                    destination_body = self._append_relation(
                        destination_body,
                        f"transfer receipt: transferred from {source.url} to {destination.url}",
                    )
            for foreign_ref in plan.foreign_issue_refs:
                destination_body = self._append_relation(
                    destination_body,
                    f"handoff relation: foreign Issue {foreign_ref}",
                )
            updated = destination
            if updated.title != title or updated.body != destination_body:
                updated = self.client.edit(
                    updated, title=title, body=destination_body
                )
            if updated.state.upper() == "CLOSED":
                updated = self.client.set_state(updated, "OPEN")
            for source in records:
                if source.url == destination.url:
                    continue
                source_body = self._remove_transferred_clauses(
                    source.body,
                    destination_body,
                )
                source_body = self._append_relation(
                    source_body,
                    f"transfer receipt: clauses transferred to {destination.url}",
                )
                if source_body != source.body:
                    self.client.edit(source, title=source.title, body=source_body)
            return updated, "reorganize"
        raise IssueSyncError("issue_worker_plan_invalid", f"unsupported action: {plan.action}")


def parse_issue_reference(value: str, default_repo: str = "") -> GitHubIssueReference:
    """Parse a full GitHub URL or explicit ``owner/repo#number`` value."""
    text = value.strip()
    match = GITHUB_URL_RE.fullmatch(text)
    if match:
        return GitHubIssueReference(normalize_repository(match.group("repo")), match.group("number"))
    ref_match = re.fullmatch(r"(?P<repo>[^/#]+/[^/#]+)#(?P<number>[1-9][0-9]*)", text)
    if ref_match:
        return GitHubIssueReference(normalize_repository(ref_match.group("repo")), ref_match.group("number"))
    if default_repo and re.fullmatch(r"[1-9][0-9]*", text):
        return GitHubIssueReference(normalize_repository(default_repo), text)
    raise IssueSyncError("github_issue_invalid", "Issue identity must be a GitHub URL or owner/repo#number")


def normalize_finding(record: Mapping[str, object], *, default_scope: str = "changed") -> dict[str, object]:
    """Normalize one owner/root-cause/fix finding without local Issue paths."""
    scope = str(record.get("scope", default_scope)).strip().lower().replace("_", "-")
    if scope not in FINDING_SCOPES:
        raise ValueError(f"unsupported finding scope: {scope}")
    owner = str(record.get("owner", "")).strip()
    root_cause = str(record.get("root_cause", record.get("cause", ""))).strip()
    fix = str(record.get("fix", record.get("required_action", ""))).strip()
    if not owner or not root_cause or not fix:
        raise ValueError("finding owner, root_cause, and fix are required")
    status = str(record.get("status", "warning")).strip().lower().replace("_", "-")
    return {
        "owner": owner,
        "root_cause": root_cause,
        "fix": fix,
        "scope": scope,
        "status": status,
        "evidence": str(record.get("evidence", "")).strip(),
        "actionable": bool(record.get("actionable", status in {"blocking", "error", "warning"})),
        "path": "",
    }


def group_findings(records: Iterable[Mapping[str, object]], *, scope: str = "changed") -> tuple[dict[str, object], ...]:
    """Group observations by owner, cause, and mechanism."""
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for record in records:
        finding = normalize_finding(record, default_scope=scope)
        key = (str(finding["owner"]), str(finding["root_cause"]), str(finding["fix"]))
        current = grouped.setdefault(
            key,
            {
                "owner": key[0], "root_cause": key[1], "fix": key[2],
                "scope": finding["scope"], "status": finding["status"],
                "actionable": finding["actionable"], "evidence": [],
            },
        )
        evidence = current["evidence"]
        if isinstance(evidence, list) and finding["evidence"] and finding["evidence"] not in evidence:
            evidence.append(finding["evidence"])
        if finding["status"] == "blocking":
            current["status"] = "blocking"
        current["actionable"] = bool(current["actionable"] or finding["actionable"])
    return tuple(grouped[key] for key in sorted(grouped))


class GitHubIssueClient:
    """Minimal host adapter for Issue read/create/edit/close/readback."""

    def __init__(self, default_repo: str = "") -> None:
        self.default_repo = normalize_repository(default_repo)

    def _repo(self, reference: GitHubIssueReference) -> str:
        return normalize_repository(reference.repo or self.default_repo)

    @staticmethod
    def _run(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(list(argv), check=False, capture_output=True, text=True)
        if result.returncode:
            detail = (result.stderr or result.stdout or "GitHub adapter failed").strip().splitlines()[-1]
            raise IssueSyncError("github_adapter_failed", detail[:240])
        return result

    def read(self, reference: GitHubIssueReference) -> GitHubIssueRecord:
        result = self._run(
            ["gh", "issue", "view", reference.number, "--repo", self._repo(reference), "--json", "number,title,body,state,url"]
        )
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise IssueSyncError("github_readback_invalid", "gh returned invalid Issue JSON") from exc
        try:
            state = normalize_issue_state(str(value.get("state") or ""))
        except IssueSyncError as exc:
            raise IssueSyncError(
                "github_readback_invalid",
                "GitHub returned an unsupported Issue state",
            ) from exc
        return GitHubIssueRecord(
            repository=self._repo(reference),
            number=str(value.get("number") or reference.number),
            title=str(value.get("title") or ""),
            body=str(value.get("body") or ""),
            state=state,
            url=str(value.get("url") or reference.url),
        )

    def search(
        self,
        repository: str,
        terms: Sequence[str],
    ) -> tuple[GitHubIssueRecord, ...]:
        """Read all open/closed Issues matching one responsibility search."""
        words = tuple(term.strip() for term in terms if term.strip())
        if not words:
            return ()
        query = " ".join(f'"{term}"' for term in words)
        result = self._run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                normalize_repository(repository),
                "--state",
                "all",
                "--search",
                query,
                "--limit",
                "100",
                "--json",
                "number,title,body,state,url",
            ]
        )
        try:
            values = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise IssueSyncError("github_readback_invalid", "gh returned invalid Issue search JSON") from exc
        if not isinstance(values, list):
            raise IssueSyncError("github_readback_invalid", "gh Issue search did not return a list")
        records: list[GitHubIssueRecord] = []
        for value in values:
            if not isinstance(value, Mapping):
                continue
            number = str(value.get("number") or "")
            url = str(value.get("url") or "")
            if not number or not url:
                continue
            records.append(
                GitHubIssueRecord(
                    repository=normalize_repository(repository),
                    number=number,
                    title=str(value.get("title") or ""),
                    body=str(value.get("body") or ""),
                    state=str(value.get("state") or ""),
                    url=url,
                )
            )
        return tuple(records)

    def create(self, repo: str, title: str, body: str) -> GitHubIssueRecord:
        result = self._run(["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body])
        url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        record = self.read(parse_issue_reference(url, repo))
        if record.title != title or record.body != body:
            raise IssueSyncError("github_readback_mismatch", "created Issue title/body readback differs")
        return record

    def edit(self, issue: GitHubIssueRecord, *, title: str, body: str) -> GitHubIssueRecord:
        self._run(["gh", "issue", "edit", issue.number, "--repo", issue.repository, "--title", title, "--body", body])
        record = self.read(issue.reference)
        if record.title != title or record.body != body:
            raise IssueSyncError("github_readback_mismatch", "edited Issue title/body readback differs")
        return record

    def set_state(self, issue: GitHubIssueRecord, state: str) -> GitHubIssueRecord:
        command = "close" if state.upper() == "CLOSED" else "reopen"
        self._run(["gh", "issue", command, issue.number, "--repo", issue.repository])
        record = self.read(issue.reference)
        if record.state.upper() != state.upper():
            raise IssueSyncError("github_readback_mismatch", "Issue state readback differs")
        return record


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _log_root(explicit: Path | None) -> Path:
    if explicit:
        return explicit.expanduser().resolve()
    configured = os.environ.get("AGENT_CANON_LOG_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    parent = os.environ.get("AGENT_CANON_CONTROL_PARENT_ROOT", "").strip()
    if parent:
        return (Path(parent) / "agent-canon-log").resolve()
    raise IssueSyncError("private_log_root_required", "offline Issue packets require an explicit private log root")


def _packet_path(log_root: Path, title: str, digest: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80] or "issue"
    return log_root / "feedback" / "issue-packets" / "pending" / f"{slug}-{digest[:16]}.json"


def write_pending_packet(
    *,
    log_root: Path,
    repository: str,
    title: str,
    body_locator: str,
    body_digest: str,
    run: str = "",
    task: str = "",
    input_mode: str = "structured-log",
    reason: str = "",
    route: str = "issue-publication",
    handoff: Mapping[str, object] | None = None,
    source_finding_kind: str = "",
) -> Path:
    """Write metadata-only packet; body remains at its private locator."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", body_digest):
        raise IssueSyncError("body_digest_invalid", "body digest must be sha256:<64 hex>")
    if not body_locator or Path(body_locator).name in {"", ".", ".."}:
        raise IssueSyncError("body_locator_invalid", "private body locator is required")
    target = _packet_path(log_root, title, body_digest.removeprefix("sha256:"))
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": PACKET_SCHEMA,
        "repository": repository,
        "title": title,
        "body_locator": body_locator,
        "body_digest": body_digest,
        "run": run,
        "task": task,
        "input_mode": input_mode,
        "reason": reason,
        "route": route,
        "status": "pending",
    }
    if source_finding_kind:
        payload["source_finding_kind"] = source_finding_kind
    if handoff is not None:
        payload["handoff"] = dict(handoff)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != encoded:
        raise IssueSyncError("packet_conflict", "pending packet already contains different metadata")
    target.write_text(encoded, encoding="utf-8")
    target.chmod(0o600)
    return target


def _read_private_body(locator: str, digest: str) -> str:
    path = Path(locator).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise IssueSyncError("body_locator_missing", "private body locator is unavailable")
    if f"sha256:{_sha256(path)}" != digest:
        raise IssueSyncError("body_digest_mismatch", "private body digest does not match packet")
    return path.read_text(encoding="utf-8")


def checkout_repository(identity: object | None) -> str:
    """Read normalized repository only from an explicit #938 identity block."""
    if identity is None:
        return ""
    if isinstance(identity, Mapping):
        return normalize_repository(str(identity.get("remote") or ""))
    return normalize_repository(str(getattr(identity, "remote", "")))


def sync_pending_packet(
    path: Path,
    client: GitHubIssueClient,
    *,
    checkout_identity: object | None = None,
    runtime_root: Path | None = None,
    receipt_stager: ContainerReceiptStager | object | None = None,
) -> GitHubIssueRecord:
    """Publish one packet through the host adapter and remove it after readback."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IssueSyncError("packet_invalid", "pending packet is not valid JSON") from exc
    if payload.get("schema") != PACKET_SCHEMA or payload.get("status") != "pending":
        raise IssueSyncError("packet_invalid", "pending packet schema/status is invalid")
    current_repository = checkout_repository(checkout_identity)
    if not current_repository:
        raise IssueSyncError(
            "checkout-identity-unresolved",
            "pending Issue publication requires the current #938 checkout identity",
        )
    packet_repository = normalize_repository(str(payload["repository"]))
    if not packet_repository or packet_repository != current_repository:
        raise IssueSyncError(
            "checkout-repository-mismatch",
            "pending Issue repository does not match the current checkout identity",
        )
    body = _read_private_body(str(payload["body_locator"]), str(payload["body_digest"]))
    configured_runtime = runtime_root
    if configured_runtime is None:
        raw_runtime = os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
        configured_runtime = Path(raw_runtime) if raw_runtime else None
    if configured_runtime is None:
        raise IssueSyncError(
            "issue_receipt_route_unavailable",
            "resident runtime receipt route is required before GitHub mutation",
        )
    configured_runtime = _runtime_root(configured_runtime)
    receipt_root = configured_runtime / PRIVATE_FEEDBACK_SPOOL_RELATIVE
    identity_root = _checkout_identity_value(checkout_identity, "git_root")
    if receipt_stager is None:
        receipt_stager = build_container_receipt_stager(
            runtime_root=configured_runtime,
            checkout_identity=checkout_identity,
            source_root=Path(identity_root)
            if identity_root and identity_root != "unknown"
            else Path.cwd(),
        )
    if not callable(receipt_stager) or not callable(getattr(receipt_stager, "preflight", None)):
        raise IssueSyncError(
            "issue_receipt_route_unavailable",
            "injected container receipt stager is unavailable",
        )
    receipt_stager.preflight()
    raw_handoff = payload.get("handoff")
    handoff = (
        qualify_issue_worker_finding(
            raw_handoff,
            authenticated_repository=current_repository,
        )
        if payload.get("route") == "issue-worker" and isinstance(raw_handoff, Mapping)
        else None
    )
    existing = find_issue_publication_receipt(
        receipt_root,
        packet_repository,
        handoff=handoff,
        number=str(payload.get("number") or ""),
    )
    if existing is None and configured_runtime is not None:
        existing = find_issue_publication_receipt(
            path.parents[3],
            packet_repository,
            handoff=handoff,
            number=str(payload.get("number") or ""),
        )
    if existing is not None:
        record = client.read(
            parse_issue_reference(str(existing["url"]), packet_repository)
        )
        path.unlink()
        return record
    repository = current_repository
    if handoff is not None:
        worker = IssueWorker(client, repository)
        discovered = worker.search_related_issue_set(handoff)
        if len(discovered) > 1:
            raise IssueSyncError(
                "issue_worker_retry_unresolved",
                "retry requires exactly one same-responsibility Issue readback",
            )
        if not discovered and payload.get("input_mode") != "issue-publication-initial":
            raise IssueSyncError(
                "issue_worker_retry_unresolved",
                "retry requires one same-responsibility Issue or an initial publication packet",
            )
        record = worker.publish(
            handoff,
            title=str(payload["title"]),
            body=body,
            related_issues=discovered,
            receipt_stager=receipt_stager,
            allow_create=not bool(discovered),
        )
    else:
        packet_number = str(payload.get("number") or "")
        if packet_number:
            record = client.read(
                parse_issue_reference(packet_number, repository)
            )
            receipt_stager(
                record,
                "noop",
                IssueWorkerHandoff(
                    status="qualified",
                    reason="published-readback",
                    repository=repository,
                    owner="",
                    fix="",
                    occurrence_locations=(),
                ),
            )
            path.unlink()
            return record
        search = getattr(client, "search", None)
        candidates = (
            tuple(search(repository, (str(payload["title"]),)))
            if callable(search)
            else ()
        )
        if len(candidates) > 1:
            raise IssueSyncError(
                "issue_worker_retry_unresolved",
                "ordinary packet has multiple related Issues",
            )
        if len(candidates) == 1:
            record = client.read(candidates[0].reference)
            receipt_stager(
                record,
                "noop",
                IssueWorkerHandoff(
                    status="qualified",
                    reason="published-readback",
                    repository=repository,
                    owner="",
                    fix="",
                    occurrence_locations=(),
                ),
            )
            path.unlink()
            return record
        if payload.get("input_mode") != "issue-publication-initial":
            raise IssueSyncError(
                "issue_worker_retry_unresolved",
                "ordinary packet requires one related Issue before acknowledgement",
            )
        record = client.create(repository, str(payload["title"]), body)
        receipt_stager(
            record,
            "create",
            IssueWorkerHandoff(
                status="qualified",
                reason="published-readback",
                repository=repository,
                owner="",
                fix="",
                occurrence_locations=(),
                source_finding_kind=str(payload.get("source_finding_kind") or ""),
            ),
        )
    path.unlink()
    return record


def parse_sections(body: str) -> dict[str, str]:
    """Extract clause headings used by distributed Issue projection."""
    sections: dict[str, list[str]] = {}
    current = ""
    for line in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1).strip().lower().replace(" ", "_")
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def project_issue_clauses(issue: GitHubIssueRecord) -> tuple[dict[str, object], ...]:
    """Project clauses without treating Issue state/authorship as evidence."""
    sections = parse_sections(issue.body)
    result: list[dict[str, object]] = []
    for kind in CLAUSE_KINDS:
        value = sections.get(kind, "")
        grounded = bool(value and ("evidence" in value.lower() or "user" in value.lower()))
        result.append(
            {
                "repository": issue.repository,
                "issue_number": issue.number,
                "issue_url": issue.url,
                "clause_kind": kind,
                "clause": value,
                "state": "grounded" if grounded else ("advisory" if kind != "problem" else "unproven"),
                "authority": "github-issue-body",
            }
        )
    return tuple(result)


def validate_issue(issue: GitHubIssueRecord) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    try:
        reference = parse_issue_reference(issue.url)
    except IssueSyncError:
        findings.append(Finding("identity", issue.url, "invalid-github-url"))
    else:
        if reference.repo != issue.repository or reference.number != issue.number:
            findings.append(Finding("identity", issue.url, "repository-number-mismatch"))
    if not issue.title.strip():
        findings.append(Finding("field", issue.url, "missing-title"))
    if not issue.body.strip():
        findings.append(Finding("field", issue.url, "missing-body"))
    return tuple(findings)


def report_for_issues(issues: Sequence[GitHubIssueRecord], *, github_checked: int = 0) -> IssueSyncReport:
    findings = tuple(sorted((finding for issue in issues for finding in validate_issue(issue)), key=lambda item: (item.check, item.path, item.detail)))
    return IssueSyncReport(tuple(issues), findings, github_checked=github_checked)


def render_json(report: IssueSyncReport) -> str:
    return json.dumps(
        {
            "status": "pass" if not report.findings else "fail",
            "issues": [
                {
                    "repository": issue.repository,
                    "number": issue.number,
                    "title": issue.title,
                    "state": issue.state,
                    "url": issue.url,
                    "clauses": list(project_issue_clauses(issue)),
                }
                for issue in report.issues
            ],
            "findings": [finding.__dict__ for finding in report.findings],
            "github_checked": report.github_checked,
            "github_unavailable": report.github_unavailable,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Host-side GitHub Issue adapter")
    parser.add_argument("--repo", default="")
    parser.add_argument("--issue-url", action="append", default=[])
    parser.add_argument("--offline-title")
    parser.add_argument("--body-locator")
    parser.add_argument("--body-digest")
    parser.add_argument("--log-root", type=Path)
    parser.add_argument("--run", default="")
    parser.add_argument("--task", default="")
    parser.add_argument("--github-check", action="store_true")
    parser.add_argument("--sync-pending", action="store_true")
    parser.add_argument("--summary-file", type=Path)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        help="External runtime root used by the resident receipt staging route.",
    )
    parser.add_argument(
        "--stage-publication-receipt",
        "--record-publication-receipt",
        action="store_true",
        help="Stage a body-free publication receipt in the resident private-feedback spool.",
    )
    parser.add_argument(
        "--receipt-preflight",
        action="store_true",
        help="Verify the resident receipt route without publishing a receipt.",
    )
    parser.add_argument("--receipt-number")
    parser.add_argument("--receipt-url")
    parser.add_argument("--receipt-state", default="")
    parser.add_argument("--receipt-action", choices=("create", "update", "reopen", "reorganize", "noop"))
    parser.add_argument("--receipt-responsibility", action="append", default=[])
    parser.add_argument("--receipt-occurrence-location", action="append", default=[])
    parser.add_argument("--receipt-source-finding-kind", default="")
    parser.add_argument("--receipt-timestamp")
    parser.add_argument("--checkout-head", default="")
    parser.add_argument("--checkout-root", type=Path)
    parser.add_argument("--checkout-repository", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.receipt_preflight:
            root = _runtime_root(args.runtime_root)
            checkout_identity = {
                "head": args.checkout_head,
                "git_root": str(args.checkout_root) if args.checkout_root else "",
                "remote": args.checkout_repository,
            }
            _ensure_private_feedback_sync_request(
                root,
                checkout_identity=checkout_identity,
                source_root=args.checkout_root,
            )
            print(json.dumps({"status": "preflight", "runtime_root": str(root)}, sort_keys=True))
            return 0
        if args.stage_publication_receipt:
            required = (
                args.repo,
                args.receipt_number,
                args.receipt_url,
                args.receipt_action,
            )
            if not all(required):
                raise IssueSyncError(
                    "issue_receipt_arguments_invalid",
                    "--repo, --receipt-number, --receipt-url, and --receipt-action are required",
                )
            handoff = IssueWorkerHandoff(
                status="qualified",
                reason="published-readback",
                repository=normalize_repository(args.repo),
                owner="",
                fix="",
                occurrence_locations=tuple(args.receipt_occurrence_location),
                responsibility=tuple(args.receipt_responsibility),
                source_finding_kind=args.receipt_source_finding_kind,
            )
            checkout_identity = {
                "head": args.checkout_head,
                "git_root": str(args.checkout_root) if args.checkout_root else "",
                "remote": args.checkout_repository,
            }
            if args.checkout_repository and normalize_repository(args.checkout_repository) != normalize_repository(args.repo):
                raise IssueSyncError(
                    "checkout-repository-mismatch",
                    "receipt staging checkout repository differs from Issue repository",
                )
            record = GitHubIssueRecord(
                repository=normalize_repository(args.repo),
                number=str(args.receipt_number),
                title="",
                body="",
                state=args.receipt_state,
                url=args.receipt_url,
            )
            path = stage_issue_publication_receipt(
                _runtime_root(args.runtime_root),
                record,
                action=args.receipt_action,
                handoff=handoff,
                timestamp=args.receipt_timestamp,
                checkout_identity=checkout_identity,
                source_root=args.checkout_root,
            )
            print(json.dumps({"status": "staged", "receipt": str(path)}, sort_keys=True))
            return 0
        log_root = _log_root(args.log_root) if (args.log_root or args.offline_title or args.sync_pending) else None
        if args.offline_title:
            if not args.body_locator or not args.body_digest or not args.repo:
                raise IssueSyncError("offline_packet_incomplete", "--repo, --offline-title, --body-locator, and --body-digest are required")
            packet = write_pending_packet(
                log_root=log_root or _log_root(None), repository=args.repo,
                title=args.offline_title, body_locator=args.body_locator,
                body_digest=args.body_digest, run=args.run, task=args.task,
            )
            print(json.dumps({"schema": PACKET_SCHEMA, "status": "pending", "packet": str(packet), "repository": args.repo, "title": args.offline_title}, sort_keys=True))
            return 0
        client = GitHubIssueClient(args.repo)
        if args.sync_pending:
            root = log_root or _log_root(None)
            packets = sorted((root / "feedback/issue-packets/pending").glob("*.json"))
            identity = resolve_checkout_identity(Path.cwd())
            records = [
                sync_pending_packet(
                    path,
                    client,
                    checkout_identity=identity,
                    runtime_root=args.runtime_root,
                )
                for path in packets
            ]
            print(json.dumps({"schema": PACKET_SCHEMA, "status": "synced", "issues": [record.url for record in records]}, sort_keys=True))
            return 0
        if not args.issue_url:
            print("GITHUB_ISSUE_LOOKUP_REQUIRED=1")
            return 2
        records: list[GitHubIssueRecord] = []
        for value in args.issue_url:
            records.append(client.read(parse_issue_reference(value, args.repo)))
        report = report_for_issues(records, github_checked=len(records) if args.github_check else 0)
        output = render_json(report)
        if args.summary_file:
            args.summary_file.parent.mkdir(parents=True, exist_ok=True)
            args.summary_file.write_text(output + "\n", encoding="utf-8")
        print(output)
        return 1 if report.findings else 0
    except IssueSyncError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "detail": exc.detail}, sort_keys=True), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
