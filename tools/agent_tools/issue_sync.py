#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates local AgentCanon issue files and mirrors them to GitHub Issues.
# upstream design ../../issues/README.md durable local issue convention
# upstream design ../../documents/design/responsibility-scope-management.md local/GitHub issue sync policy
# upstream design ../../tools/README.md tool entrypoint index
# upstream design ../../documents/tools/README.md user-facing tool index
# downstream implementation ../../tools/ci/run_all_checks.sh runs offline issue validation
# downstream implementation ../../tests/agent_tools/test_issue_sync.py tests issue validation
# @dependency-end
"""Validate local AgentCanon issues and plan or run GitHub Issue synchronization."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from .parent_root_side_effects import (
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )
except ImportError:
    from parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )

REQUIRED_FIELDS = (
    "issue_id",
    "status",
    "source",
    "severity",
    "evidence",
    "affected_surfaces",
    "edit_scope",
    "required_action",
    "close_condition",
)
MINIMUM_ISSUE_FIELDS = ("issue_id", "status", "source", "severity", "evidence")
MINIMUM_ISSUE_CONTENT_FIELDS = ("problem", "done")
FINDING_SCOPES = frozenset({"changed", "user", "owner-bounded", "repo-wide"})
GITHUB_ISSUE_MARKERS = frozenset({"pending", "not-created"})
OPEN_STATUSES = {"open", "in_progress", "deferred"}
CLOSED_STATUSES = {"resolved", "wontfix", "deferred"}
ISSUE_ID_RE = re.compile(r"^AC-\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
ISSUE_CLAUSE_KINDS = (
    "problem",
    "required_action",
    "done",
    "close_condition",
)
ISSUE_AUTHORITY_KINDS = frozenset(
    {"user_request", "preexisting_public_contract", "reproduced_failure", "external_decision"}
)


def _write_issue_output(path: Path, payload: bytes, purpose: str) -> None:
    """Publish issue evidence/source updates through the parent root."""
    configured = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
    if configured:
        parent = Path(configured).resolve(strict=True)
        attestation = attest_parent_root(
            ParentRootAttestationRequest(cwd=parent, explicit_root=parent, purpose=purpose)
        )
        ParentRootSideEffectBoundary().write_parent_owned_file(attestation, path, payload, purpose)
        return
    raise ParentRootSideEffectError(
        ParentRootReject.HANDOFF_INVALID,
        f"{purpose}: explicit parent root is required for publication",
    )


@dataclass(frozen=True)
class Finding:
    """One issue sync finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"ISSUE_SYNC_FINDING={self.check}:{self.path}:{self.detail}"


def normalize_finding(record: Mapping[str, object], *, default_scope: str = "changed") -> dict[str, object]:
    """Normalize one tool or issue finding at the shared pipeline boundary.

    Findings default to the changed/user/owner-bounded view.  Repo-wide scope
    is accepted only when explicitly supplied by the caller; no path-based
    inference silently broadens a run.
    """
    scope_value = record.get("scope", default_scope)
    if not isinstance(scope_value, str):
        raise ValueError("finding scope must be a string")
    scope = scope_value.strip().lower().replace("_", "-")
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
        "path": str(record.get("path", "")).strip(),
    }


def group_findings(
    records: Iterable[Mapping[str, object]],
    *,
    scope: str = "changed",
) -> tuple[dict[str, object], ...]:
    """Group findings by owner, root cause, and fix into one issue candidate.

    Multiple agents or paths describing the same repair remain one candidate;
    this owner deliberately does not partition a group into agents.
    """
    normalized = [normalize_finding(record, default_scope=scope) for record in records]
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for finding in normalized:
        key = (
            str(finding["owner"]),
            str(finding["root_cause"]),
            str(finding["fix"]),
        )
        current = grouped.setdefault(
            key,
            {
                "owner": key[0],
                "root_cause": key[1],
                "fix": key[2],
                "scope": finding["scope"],
                "status": finding["status"],
                "actionable": finding["actionable"],
                "evidence": [],
                "paths": [],
            },
        )
        evidence = current["evidence"]
        paths = current["paths"]
        if isinstance(evidence, list) and finding["evidence"] and finding["evidence"] not in evidence:
            evidence.append(finding["evidence"])
        path = finding.get("path")
        if isinstance(paths, list) and isinstance(path, str) and path and path not in paths:
            paths.append(path)
        if finding["status"] == "blocking":
            current["status"] = "blocking"
        current["actionable"] = bool(current["actionable"] or finding["actionable"])
    return tuple(grouped[key] for key in sorted(grouped))


@dataclass(frozen=True)
class IssueRecord:
    """One parsed local issue file."""

    path: Path
    directory_state: str
    fields: dict[str, str]
    body: str = ""
    github_issue_values: tuple[str, ...] = ()

    @property
    def issue_id(self) -> str:
        """Return the issue id."""
        return self.fields.get("issue_id", "")

    @property
    def github_issue(self) -> str:
        """Return the linked GitHub Issue URL or marker."""
        if self.github_issue_values:
            return canonical_github_issue(self.github_issue_values)
        return self.fields.get("github_issue", "")


@dataclass(frozen=True)
class GitHubIssueReference:
    """Parsed GitHub Issue mirror reference."""

    repo: str
    number: str


@dataclass(frozen=True)
class GitHubIssueSnapshot:
    """One GitHub Issue snapshot read through gh."""

    number: str
    title: str
    body: str
    state: str
    url: str


@dataclass(frozen=True)
class IssueSyncReport:
    """Issue sync validation report."""

    issues: tuple[IssueRecord, ...]
    findings: tuple[Finding, ...]
    sync_plan: tuple[str, ...]
    github_checked: int = 0
    github_missing_links: int = 0
    github_drift: int = 0
    github_unavailable: int = 0


@dataclass
class GitHubIssueCreator:
    """Stateful GitHub Issue creator for explicit apply mode."""

    repo: str
    created_url: str = ""

    def create(self, issue: IssueRecord) -> None:
        """Create one GitHub Issue from a local issue file."""
        if not self.repo:
            raise ValueError("--repo is required with --apply")
        title = issue_title(issue.path)
        body = issue.path.read_text(encoding="utf-8")
        result = subprocess.run(
            ["gh", "issue", "create", "--repo", self.repo, "--title", title, "--body", body],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        self.created_url = result.stdout.strip()


@dataclass
class GitHubIssueClient:
    """Small gh-backed client for GitHub Issue mirror reads and writes."""

    default_repo: str

    def repo_for(self, reference: GitHubIssueReference) -> str:
        """Return the repository for one issue reference."""
        return reference.repo or self.default_repo

    def read(self, reference: GitHubIssueReference) -> GitHubIssueSnapshot:
        """Read one GitHub Issue."""
        result = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                reference.number,
                "--repo",
                self.repo_for(reference),
                "--json",
                "number,title,body,state,url",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        data = json.loads(result.stdout)
        return GitHubIssueSnapshot(
            number=str(data.get("number") or reference.number),
            title=str(data.get("title") or ""),
            body=str(data.get("body") or ""),
            state=str(data.get("state") or ""),
            url=str(data.get("url") or ""),
        )

    def edit_body_and_title(self, reference: GitHubIssueReference, issue: IssueRecord) -> None:
        """Update one GitHub Issue title and body from the local issue file."""
        result = subprocess.run(
            [
                "gh",
                "issue",
                "edit",
                reference.number,
                "--repo",
                self.repo_for(reference),
                "--title",
                issue_title(issue.path),
                "--body-file",
                str(issue.path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    def set_state(self, reference: GitHubIssueReference, expected_state: str) -> None:
        """Set one GitHub Issue open/closed state."""
        command = "close" if expected_state == "CLOSED" else "reopen"
        result = subprocess.run(
            ["gh", "issue", command, reference.number, "--repo", self.repo_for(reference)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--repo", default="", help="GitHub repository owner/name.")
    parser.add_argument("--require-github-link", action="store_true")
    parser.add_argument("--github-check", action="store_true", help="Read linked GitHub Issues and report mirror drift.")
    parser.add_argument(
        "--allow-github-auth-unavailable",
        action="store_true",
        help="Report GitHub auth failures as unavailable instead of failing the read-only check.",
    )
    parser.add_argument("--apply", action="store_true", help="Create missing GitHub Issues with gh.")
    parser.add_argument("--sync-github", action="store_true", help="Update linked GitHub Issues to match local issue files.")
    parser.add_argument("--summary-file", type=Path, help="Append a Markdown summary to this path.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def agent_canon_root(root: Path) -> Path:
    """Return the explicitly selected AgentCanon source checkout."""
    return root.resolve()


def relative(root: Path, path: Path) -> str:
    """Return a stable root-relative path."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def parse_fields(text: str) -> dict[str, str]:
    """Parse machine-readable issue fields from Markdown text."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = FIELD_RE.match(line.strip())
        if match and match.group(1) not in fields:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def compact_issue_sections(text: str) -> dict[str, str]:
    """Read the compact Problem/Evidence/Done headings from an issue body."""
    sections: dict[str, str] = {}
    heading: str | None = None
    content: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^##+\s+(.+?)\s*$", line)
        if match:
            if heading is not None:
                sections[heading] = "\n".join(content).strip()
            heading = match.group(1).strip().lower().replace("-", " ")
            content = []
            continue
        if heading is not None:
            content.append(line)
    if heading is not None:
        sections[heading] = "\n".join(content).strip()
    return sections


def project_issue_clauses(issue: IssueRecord) -> tuple[dict[str, object], ...]:
    """Project Issue clauses to owner-local, non-authoritative trace records.

    Problem/action/completion prose is retained for routing, but only an
    external authority and owner receipt can ground a clause.  Issue state,
    labels, authorship, PR references, and repeated agent text do not upgrade
    an ``advisory`` or ``unproven`` clause.
    """
    sections = compact_issue_sections(issue.body)
    owner_ref = issue.fields.get("owner_ref", issue.fields.get("owner", "")).strip()
    authority_kind = issue.fields.get("authority_kind", "").strip()
    authority_ref = issue.fields.get("authority_ref", "").strip()
    receipt_ref = issue.fields.get("owner_receipt_ref", "").strip()
    projected: list[dict[str, object]] = []
    for clause_kind in ISSUE_CLAUSE_KINDS:
        text = issue.fields.get(clause_kind, "").strip() or sections.get(clause_kind, "")
        if not text:
            continue
        grounded = (
            bool(owner_ref)
            and authority_kind in ISSUE_AUTHORITY_KINDS
            and bool(authority_ref)
            and (clause_kind != "problem" or bool(issue.fields.get("evidence", "").strip()))
            and (clause_kind == "problem" or bool(receipt_ref))
        )
        state = "grounded" if grounded else ("advisory" if clause_kind != "problem" else "unproven")
        projected.append(
            {
                "issue_repository": issue.fields.get("issue_repository", "").strip(),
                "issue_number": issue.fields.get("issue_number", "").strip(),
                "owner_ref": owner_ref,
                "clause_ref": f"{issue.path.as_posix()}#{clause_kind}",
                "clause_kind": clause_kind,
                "clause_text": text,
                "authority_kind": authority_kind,
                "authority_ref": authority_ref,
                "owner_receipt_ref": receipt_ref,
                "state": state,
            }
        )
    return tuple(projected)


def issue_files(root: Path) -> tuple[Path, ...]:
    """Return local issue files under open and closed directories."""
    paths: list[Path] = []
    for state in ("open", "closed"):
        directory = root / "issues" / state
        if directory.is_dir():
            paths.extend(path for path in sorted(directory.glob("*.md")) if path.name != "README.md")
    return tuple(paths)


def read_issues(root: Path) -> tuple[IssueRecord, ...]:
    """Read all local issue records."""
    records: list[IssueRecord] = []
    for path in issue_files(root):
        directory_state = path.parent.name
        body = path.read_text(encoding="utf-8")
        records.append(
            IssueRecord(
                path=path,
                directory_state=directory_state,
                fields=parse_fields(body),
                body=body,
                github_issue_values=parse_github_issue_values(body),
            )
        )
    return tuple(records)


def validate_required_fields(root: Path, issue: IssueRecord) -> list[Finding]:
    """Validate legacy metadata or the compact problem/evidence/done form."""
    rel_path = relative(root, issue.path)
    findings = [
        Finding("field", rel_path, f"missing:{field}")
        for field in MINIMUM_ISSUE_FIELDS
        if not issue.fields.get(field)
    ]
    has_extended = all(issue.fields.get(field) for field in (
        "affected_surfaces", "edit_scope", "required_action", "close_condition"
    ))
    compact_sections = compact_issue_sections(issue.body)
    has_compact = all(
        issue.fields.get(field) or compact_sections.get(field)
        for field in MINIMUM_ISSUE_CONTENT_FIELDS
    )
    if not has_extended and not has_compact:
        extended_fields = (
            "affected_surfaces",
            "edit_scope",
            "required_action",
            "close_condition",
        )
        if any(issue.fields.get(field) for field in extended_fields):
            findings.extend(
                Finding("field", rel_path, f"missing:{field}")
                for field in extended_fields
                if not issue.fields.get(field)
            )
        else:
            findings.append(
                Finding(
                    "field",
                    rel_path,
                    "missing:problem-evidence-done-or-extended-fields",
                )
            )
    if issue.directory_state == "closed" and not issue.fields.get("resolved_by"):
        findings.append(Finding("field", rel_path, "missing:resolved_by"))
    return findings


def validate_issue_identity(root: Path, issue: IssueRecord) -> list[Finding]:
    """Validate issue id, filename, and status."""
    rel_path = relative(root, issue.path)
    issue_id = issue.issue_id
    findings: list[Finding] = []
    if not ISSUE_ID_RE.fullmatch(issue_id):
        findings.append(Finding("identity", rel_path, "invalid-issue-id"))
    expected_name = f"{issue_id}.md" if issue_id else ""
    if expected_name and issue.path.name != expected_name:
        findings.append(Finding("identity", rel_path, f"filename-mismatch:{expected_name}"))
    status = issue.fields.get("status", "")
    if issue.directory_state == "open" and status not in OPEN_STATUSES:
        findings.append(Finding("status", rel_path, f"invalid-open-status:{status}"))
    if issue.directory_state == "closed" and status not in CLOSED_STATUSES:
        findings.append(Finding("status", rel_path, f"invalid-closed-status:{status}"))
    return findings


def github_link_findings(root: Path, issue: IssueRecord, required: bool) -> list[Finding]:
    """Validate optional GitHub Issue link fields."""
    value = issue.github_issue
    if value and value not in GITHUB_ISSUE_MARKERS and github_issue_reference(value, "") is None:
        return [Finding("github", relative(root, issue.path), "invalid-github_issue")]
    if not required:
        return []
    if github_issue_reference(value, "") is not None:
        return []
    return [Finding("github", relative(root, issue.path), "missing-github_issue")]


def duplicate_id_findings(root: Path, issues: Sequence[IssueRecord]) -> list[Finding]:
    """Return findings for duplicate local issue ids."""
    findings: list[Finding] = []
    seen: dict[str, Path] = {}
    for issue in issues:
        issue_id = issue.issue_id
        if not issue_id:
            continue
        previous = seen.get(issue_id)
        if previous is not None:
            findings.append(
                Finding(
                    "identity",
                    relative(root, issue.path),
                    f"duplicate-id:{relative(root, previous)}",
                )
            )
        seen[issue_id] = issue.path
    return findings


def plan_lines(root: Path, issues: Sequence[IssueRecord], repo: str) -> tuple[str, ...]:
    """Return a deterministic GitHub sync plan for unlinked issues."""
    lines: list[str] = []
    for issue in issues:
        if issue.github_issue and issue.github_issue not in GITHUB_ISSUE_MARKERS:
            continue
        title = issue_title(issue.path)
        command = f"gh issue create --repo {repo or '<owner/name>'} --title {json.dumps(title)} --body-file {relative(root, issue.path)}"
        lines.append(f"{issue.issue_id}:{command}")
    return tuple(lines)


def issue_title(path: Path) -> str:
    """Return a local issue title from the first Markdown heading."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return path.stem


def parse_github_issue_values(text: str) -> tuple[str, ...]:
    """Parse all github_issue values from issue text."""
    values: list[str] = []
    for line in text.splitlines():
        if line.startswith("github_issue:"):
            value = line.split(":", 1)[1].strip()
            if value:
                values.append(value)
    return tuple(values)


def canonical_github_issue(values: Sequence[str]) -> str:
    """Return canonical github_issue value preferring a resolvable URL."""
    for value in values:
        if github_issue_reference(value, "") is not None:
            return value
    for value in values:
        if value:
            return value
    return ""


def github_issue_reference(value: str, default_repo: str) -> GitHubIssueReference | None:
    """Parse a GitHub Issue URL or issue number."""
    if not value or value in GITHUB_ISSUE_MARKERS:
        return None
    url_match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/issues/(\d+)", value)
    if url_match is not None:
        return GitHubIssueReference(repo=url_match.group(1), number=url_match.group(2))
    if value.isdigit() and default_repo:
        return GitHubIssueReference(repo=default_repo, number=value)
    return None


def expected_github_state(issue: IssueRecord) -> str:
    """Return the GitHub Issue state expected from local state."""
    if issue.directory_state == "closed":
        return "CLOSED"
    return "OPEN"


def is_github_auth_unavailable(error: Exception) -> bool:
    """Return whether a gh failure is an authentication infrastructure problem."""
    text = str(error)
    return "HTTP 401" in text or "Bad credentials" in text or "gh auth login" in text


def github_mirror_findings(
    root: Path,
    issues: Sequence[IssueRecord],
    repo: str,
    *,
    allow_auth_unavailable: bool = False,
) -> tuple[list[Finding], int, int, int]:
    """Return findings from read-only GitHub Issue mirror checks."""
    findings: list[Finding] = []
    checked = 0
    drift = 0
    unavailable = 0
    client = GitHubIssueClient(repo)
    for issue in issues:
        # Read-only checks require a canonical URL. Numeric shorthand remains
        # available only to the explicit sync client compatibility path.
        reference = github_issue_reference(issue.github_issue, "")
        if reference is None:
            marker = issue.github_issue or "empty"
            findings.append(
                Finding("github", relative(root, issue.path), f"unresolved-github_issue:{marker}")
            )
            drift += 1
            continue
        rel_path = relative(root, issue.path)
        try:
            snapshot = client.read(reference)
        except (RuntimeError, json.JSONDecodeError) as error:
            if allow_auth_unavailable and is_github_auth_unavailable(error):
                unavailable += 1
                continue
            findings.append(Finding("github", rel_path, f"gh-read-failed:{error}"))
            drift += 1
            continue
        checked += 1
        expected_state = expected_github_state(issue)
        if snapshot.state != expected_state:
            findings.append(
                Finding(
                    "github",
                    rel_path,
                    f"state-drift:expected={expected_state}:actual={snapshot.state}",
                )
            )
            drift += 1
        expected_title = issue_title(issue.path)
        if snapshot.title != expected_title:
            findings.append(Finding("github", rel_path, "title-drift"))
            drift += 1
        expected_body = issue.path.read_text(encoding="utf-8")
        if snapshot.body != expected_body:
            findings.append(Finding("github", rel_path, "body-drift"))
            drift += 1
    return findings, checked, drift, unavailable


def github_missing_link_count(issues: Sequence[IssueRecord]) -> int:
    """Return how many local issue files have no GitHub mirror link."""
    return sum(
        1
        for issue in issues
        if not issue.github_issue or issue.github_issue in GITHUB_ISSUE_MARKERS
    )


def replace_github_issue(path: Path, url: str) -> None:
    """Replace any marker/link with one canonical GitHub Issue field."""
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    filtered: list[str] = []
    for line in lines:
        if line.startswith("github_issue:"):
            if not replaced:
                filtered.append(f"github_issue: {url}")
                replaced = True
            continue
        filtered.append(line)
    lines = filtered
    if replaced:
        _write_issue_output(path, ("\n".join(lines) + "\n").encode("utf-8"), "issue-sync-source")
        return
    for index, line in enumerate(lines):
        if line.startswith("evidence:"):
            lines.insert(index + 1, f"github_issue: {url}")
            _write_issue_output(path, ("\n".join(lines) + "\n").encode("utf-8"), "issue-sync-source")
            return
    _write_issue_output(
        path,
        ("\n".join([*lines, f"github_issue: {url}"]) + "\n").encode("utf-8"),
        "issue-sync-source",
    )


def apply_missing_links(issues: Sequence[IssueRecord], repo: str) -> tuple[str, ...]:
    """Create GitHub Issues for empty or temporary-marker local issues."""
    creator = GitHubIssueCreator(repo)
    created: list[str] = []
    for issue in issues:
        canonical = canonical_github_issue(issue.github_issue_values)
        has_multiple_links = len(issue.github_issue_values) > 1
        if canonical and canonical not in GITHUB_ISSUE_MARKERS:
            if canonical != issue.github_issue or has_multiple_links:
                replace_github_issue(issue.path, canonical)
            continue
        if issue.github_issue != canonical:
            replace_github_issue(issue.path, canonical or "pending")
        creator.create(issue)
        if github_issue_reference(creator.created_url, "") is None:
            raise RuntimeError(
                f"gh issue create returned a non-URL for {issue.issue_id}: {creator.created_url!r}"
            )
        replace_github_issue(issue.path, creator.created_url)
        created.append(f"{issue.issue_id}:{creator.created_url}")
    return tuple(created)


def sync_linked_github_issues(issues: Sequence[IssueRecord], repo: str) -> tuple[str, ...]:
    """Update linked GitHub Issues to match local title, body, and state."""
    client = GitHubIssueClient(repo)
    synced: list[str] = []
    for issue in issues:
        reference = github_issue_reference(issue.github_issue, repo)
        if reference is None:
            continue
        snapshot = client.read(reference)
        expected_state = expected_github_state(issue)
        expected_body = issue.path.read_text(encoding="utf-8")
        if snapshot.title != issue_title(issue.path) or snapshot.body != expected_body:
            client.edit_body_and_title(reference, issue)
            synced.append(f"{issue.issue_id}:title-body")
        if snapshot.state != expected_state:
            client.set_state(reference, expected_state)
            synced.append(f"{issue.issue_id}:state:{expected_state.lower()}")
    return tuple(synced)


def validate(
    root: Path,
    require_github_link: bool,
    repo: str = "",
    github_check: bool = False,
    allow_github_auth_unavailable: bool = False,
) -> IssueSyncReport:
    """Validate local issue sync state."""
    canon_root = agent_canon_root(root.resolve())
    issues = read_issues(canon_root)
    findings: list[Finding] = []
    if not issues:
        findings.append(Finding("directory", "issues", "no-issue-files"))
    for issue in issues:
        findings.extend(validate_required_fields(canon_root, issue))
        findings.extend(validate_issue_identity(canon_root, issue))
        findings.extend(github_link_findings(canon_root, issue, require_github_link))
    findings.extend(duplicate_id_findings(canon_root, issues))
    github_checked = 0
    github_drift = 0
    github_unavailable = 0
    if github_check and not findings:
        github_findings, github_checked, github_drift, github_unavailable = github_mirror_findings(
            canon_root,
            issues,
            repo,
            allow_auth_unavailable=allow_github_auth_unavailable,
        )
        findings.extend(github_findings)
    return IssueSyncReport(
        issues=issues,
        findings=tuple(sorted(findings, key=lambda item: (item.check, item.path, item.detail))),
        sync_plan=(),
        github_checked=github_checked,
        github_missing_links=github_missing_link_count(issues),
        github_drift=github_drift,
        github_unavailable=github_unavailable,
    )


def report_with_plan(report: IssueSyncReport, root: Path, repo: str) -> IssueSyncReport:
    """Attach a GitHub sync plan to a report."""
    canon_root = agent_canon_root(root.resolve())
    return IssueSyncReport(
        issues=report.issues,
        findings=report.findings,
        sync_plan=plan_lines(canon_root, report.issues, repo),
        github_checked=report.github_checked,
        github_missing_links=report.github_missing_links,
        github_drift=report.github_drift,
        github_unavailable=report.github_unavailable,
    )


def render_json(report: IssueSyncReport) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "pass" if not report.findings else "fail",
            "findings": [asdict(item) for item in report.findings],
            "issues": [
                {
                    "path": str(issue.path),
                    "directory_state": issue.directory_state,
                    "issue_id": issue.issue_id,
                    "github_issue": issue.github_issue,
                    "clauses": list(project_issue_clauses(issue)),
                }
                for issue in report.issues
            ],
            "sync_plan": list(report.sync_plan),
            "github_checked": report.github_checked,
            "github_missing_links": report.github_missing_links,
            "github_drift": report.github_drift,
            "github_unavailable": report.github_unavailable,
        },
        indent=2,
        sort_keys=True,
    )


def render_markdown_summary(report: IssueSyncReport) -> str:
    """Render a compact GitHub Actions Markdown summary."""
    status = "pass" if not report.findings else "fail"
    lines = [
        "## Issue Mirror Check",
        "",
        f"- status: `{status}`",
        f"- local_issues: `{len(report.issues)}`",
        f"- missing_github_links: `{report.github_missing_links}`",
        f"- github_checked: `{report.github_checked}`",
        f"- github_drift: `{report.github_drift}`",
        f"- github_unavailable: `{report.github_unavailable}`",
        f"- findings: `{len(report.findings)}`",
        f"- planned_sync_commands: `{len(report.sync_plan)}`",
    ]
    if report.findings:
        lines.extend(["", "### Findings", ""])
        lines.extend(f"- `{finding.check}` `{finding.path}` `{finding.detail}`" for finding in report.findings)
    if report.sync_plan:
        lines.extend(["", "### Planned Sync Commands", "", "```text"])
        lines.extend(report.sync_plan)
        lines.append("```")
    return "\n".join(lines) + "\n"


def append_summary(path: Path, report: IssueSyncReport) -> None:
    """Append Markdown summary output to a file."""
    rendered = render_markdown_summary(report)
    configured = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
    if configured:
        parent = Path(configured).resolve(strict=True)
        attestation = attest_parent_root(
            ParentRootAttestationRequest(cwd=parent, explicit_root=parent, purpose="issue-sync-summary")
        )
        boundary = ParentRootSideEffectBoundary()
        with boundary.open_parent_owned_file(
            attestation,
            path,
            "issue-sync-summary",
            create=True,
            mode="a+",
        ) as handle:
            handle.write(rendered)
        return
    raise ParentRootSideEffectError(
        ParentRootReject.HANDOFF_INVALID,
        "issue-sync-summary: explicit parent root is required",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run issue validation and optional GitHub sync planning."""
    args = build_parser().parse_args(argv)
    report = validate(
        args.root,
        args.require_github_link and not args.apply,
        args.repo,
        github_check=False,
    )
    try:
        if args.apply and not report.findings:
            created = apply_missing_links(report.issues, args.repo)
            print(f"ISSUE_SYNC_CREATED={len(created)}")
            for item in created:
                print(f"ISSUE_SYNC_CREATED_ITEM={item}")
            report = validate(args.root, args.require_github_link, args.repo, github_check=False)
            if created and not report.findings:
                created_ids = {item.split(":", 1)[0] for item in created if ":" in item}
                synced = sync_linked_github_issues(
                    tuple(issue for issue in report.issues if issue.issue_id in created_ids),
                    args.repo,
                )
                print(f"ISSUE_SYNC_GITHUB_SYNCED={len(synced)}")
                for item in synced:
                    print(f"ISSUE_SYNC_GITHUB_SYNCED_ITEM={item}")
        if args.sync_github and not report.findings:
            synced = sync_linked_github_issues(report.issues, args.repo)
            print(f"ISSUE_SYNC_GITHUB_SYNCED={len(synced)}")
            for item in synced:
                print(f"ISSUE_SYNC_GITHUB_SYNCED_ITEM={item}")
    except (RuntimeError, ValueError, OSError) as error:
        print(f"ISSUE_SYNC_APPLY_ERROR={error}")
        return 1
    report = validate(
        args.root,
        args.require_github_link,
        args.repo,
        args.github_check or args.sync_github,
        allow_github_auth_unavailable=args.allow_github_auth_unavailable and not args.sync_github,
    )
    report = report_with_plan(report, args.root, args.repo)
    if args.summary_file:
        append_summary(args.summary_file, report)
    if args.format == "json":
        print(render_json(report))
    else:
        for finding in report.findings:
            print(finding.render())
        for line in report.sync_plan:
            print(f"ISSUE_SYNC_PLAN={line}")
        print(f"ISSUE_SYNC_LOCAL_ISSUES={len(report.issues)}")
        print(f"ISSUE_SYNC_GITHUB_MISSING_LINKS={report.github_missing_links}")
        print(f"ISSUE_SYNC_GITHUB_CHECKED={report.github_checked}")
        print(f"ISSUE_SYNC_GITHUB_DRIFT={report.github_drift}")
        print(f"ISSUE_SYNC_GITHUB_UNAVAILABLE={report.github_unavailable}")
        print(f"ISSUE_SYNC_FINDINGS={len(report.findings)}")
        print(f"ISSUE_SYNC={'pass' if not report.findings else 'fail'}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
