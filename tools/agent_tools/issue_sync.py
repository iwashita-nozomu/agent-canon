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
the packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

GITHUB_URL_RE = re.compile(r"^https://github\.com/(?P<repo>[^/]+/[^/]+)/issues/(?P<number>[1-9][0-9]*)$")
PACKET_SCHEMA = "agent-canon.feedback.issue-packet.v1"
CLAUSE_KINDS = ("problem", "required_action", "done", "close_condition")
FINDING_SCOPES = frozenset({"changed", "user", "owner-bounded", "repo-wide"})
ISSUE_WORKER_HANDOFF_SCHEMA = "agent-canon.issue-worker-handoff.v1"
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

    def as_dict(self) -> dict[str, object]:
        """Return the machine-readable, mutation-free plan projection."""
        return {
            "schema": ISSUE_WORKER_HANDOFF_SCHEMA,
            "action": self.action,
            "handoff": self.handoff.as_dict(),
            "related_issue_refs": list(self.related_issue_refs),
            "destination_issue_ref": self.destination_issue_ref,
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
    kind = _record_text(record, "finding_kind", "kind", "category").casefold().replace("_", "-")
    occurrence = _occurrence_locations(record)
    related = record.get("related_issue_refs", record.get("issue_refs", ()))
    related_refs = tuple(
        value.strip()
        for value in related
        if isinstance(value, str) and value.strip()
    ) if isinstance(related, (list, tuple)) else ()
    responsibility = _responsibility_tuple(record)

    actionable = _record_bool(record, "actionable")
    if actionable is False:
        return _make_handoff("no-action", "not-actionable", repository, owner, fix, occurrence, related_refs, responsibility)
    if kind in NON_DURABLE_FINDING_KINDS:
        return _make_handoff("no-action", "non-durable-finding-kind", repository, owner, fix, occurrence, related_refs, responsibility)
    if status in {"resolved", "closed", "current-scope-resolved", "current-scope-closed"}:
        return _make_handoff("no-action", "current-scope-resolved", repository, owner, fix, occurrence, related_refs, responsibility)
    if _record_bool(record, "current_scope_resolved", "closed_by_active_repair") is True:
        return _make_handoff("no-action", "current-scope-resolved", repository, owner, fix, occurrence, related_refs, responsibility)

    if not repository:
        return _make_handoff("handoff", "repository-unresolved", repository, owner, fix, occurrence, related_refs, responsibility)
    if not authenticated_repository:
        return _make_handoff("handoff", "checkout-identity-unresolved", repository, owner, fix, occurrence, related_refs, responsibility)
    if repository != normalize_repository(authenticated_repository):
        return _make_handoff("handoff", "other-repository", repository, owner, fix, occurrence, related_refs, responsibility)
    if not owner:
        return _make_handoff("handoff", "owner-unresolved", repository, owner, fix, occurrence, related_refs, responsibility)
    if not fix:
        return _make_handoff("handoff", "fix-unresolved", repository, owner, fix, occurrence, related_refs, responsibility)

    durable = _record_bool(record, "durable_follow_up", "needs_durable_follow_up", "recurrent", "repeatable")
    if durable is False:
        return _make_handoff("no-action", "durable-follow-up-not-established", repository, owner, fix, occurrence, related_refs, responsibility)
    return _make_handoff("qualified", "user-owned-candidate", repository, owner, fix, occurrence, related_refs, responsibility)


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

    @staticmethod
    def _cohesive_issue(
        issue: GitHubIssueRecord,
        handoff: IssueWorkerHandoff,
    ) -> bool:
        """Return whether an Issue contains the candidate responsibility tuple."""
        sections = parse_sections(issue.body)
        if not any(
            sections.get(kind, "") for kind in (*CLAUSE_KINDS, "finding")
        ):
            return False
        terms = handoff.responsibility or (handoff.owner,)
        body = issue.body.casefold()
        return all(term.casefold() in body for term in terms if term)

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
        if not records:
            return IssueWorkerPlan("create", handoff)
        exact = tuple(
            record
            for record in records
            if normalize_repository(record.repository) == handoff.repository
            and self._cohesive_issue(record, handoff)
        )
        if len(records) > 1:
            destination = exact[0].url if exact else records[0].url
            return IssueWorkerPlan("reorganize", handoff, refs, destination)
        destination = exact[0].url if exact else records[0].url
        if exact:
            action = "reopen" if exact[0].state.upper() == "CLOSED" else "noop"
        else:
            action = "update"
        return IssueWorkerPlan(action, handoff, refs, destination)

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
        transferred = {
            line.strip()
            for kind in (*CLAUSE_KINDS, "finding")
            for line in destination_sections.get(kind, "").splitlines()
            if line.strip()
        }
        if not transferred:
            return source_body
        remaining = [
            line
            for line in source_body.splitlines()
            if not line.strip() or line.strip() not in transferred
        ]
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
                if kind in (*CLAUSE_KINDS, "finding") and not any(
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
    ) -> GitHubIssueRecord:
        """Publish and enqueue a metadata-only retry packet on failure."""
        try:
            return self._publish(
                handoff,
                title=title,
                body=body,
                related_issues=related_issues,
            )
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
    ) -> GitHubIssueRecord:
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
        records = tuple(related_issues)
        if not records and handoff.related_issue_refs:
            records = self.related_issue_set(handoff.related_issue_refs)
        plan = self.plan_publication(handoff, records)
        if plan.action == "create":
            return self.client.create(handoff.repository, title, body)
        destination = next(
            (record for record in records if record.url == plan.destination_issue_ref),
            None,
        )
        if destination is None:
            destination = self.client.read(
                parse_issue_reference(plan.destination_issue_ref, handoff.repository)
            )
        if plan.action == "noop":
            return destination
        if plan.action == "update":
            return self.client.edit(destination, title=title, body=body)
        if plan.action == "reopen":
            updated = self.client.edit(destination, title=title, body=body)
            return self.client.set_state(updated, "OPEN")
        if plan.action == "reorganize":
            destination_body = body
            for source in records:
                if source.url != destination.url:
                    destination_body = self._append_relation(
                        destination_body,
                        f"transfer receipt: transferred from {source.url} to {destination.url}",
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
            return updated
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
        return GitHubIssueRecord(
            repository=self._repo(reference),
            number=str(value.get("number") or reference.number),
            title=str(value.get("title") or ""),
            body=str(value.get("body") or ""),
            state=str(value.get("state") or ""),
            url=str(value.get("url") or reference.url),
        )

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


def sync_pending_packet(path: Path, client: GitHubIssueClient) -> GitHubIssueRecord:
    """Publish one packet through the host adapter and remove it after readback."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IssueSyncError("packet_invalid", "pending packet is not valid JSON") from exc
    if payload.get("schema") != PACKET_SCHEMA or payload.get("status") != "pending":
        raise IssueSyncError("packet_invalid", "pending packet schema/status is invalid")
    body = _read_private_body(str(payload["body_locator"]), str(payload["body_digest"]))
    repository = normalize_repository(str(payload["repository"]))
    raw_handoff = payload.get("handoff")
    if payload.get("route") == "issue-worker" and isinstance(raw_handoff, Mapping):
        handoff = qualify_issue_worker_finding(
            raw_handoff,
            authenticated_repository=repository,
        )
        record = IssueWorker(client, repository).publish(
            handoff,
            title=str(payload["title"]),
            body=body,
        )
    else:
        record = client.create(repository, str(payload["title"]), body)
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
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
            records = [sync_pending_packet(path, client) for path in packets]
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
