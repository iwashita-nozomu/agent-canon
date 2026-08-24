#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolves repository-qualified GitHub Issues, projects their
# clauses, and transports metadata-only offline packets through the private log.
# upstream design ../../documents/runtime/private-feedback-knowledge.md
# upstream design ../../documents/operations/issue-label-taxonomy.toml GitHub lifecycle labels
# downstream implementation ../../tests/agent_tools/test_issue_sync.py focused GitHub/packet tests
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

GITHUB_URL_RE = re.compile(r"^https://github\.com/(?P<repo>[^/]+/[^/]+)/issues/(?P<number>[1-9][0-9]*)$")
PACKET_SCHEMA = "agent-canon.feedback.issue-packet.v1"
CLAUSE_KINDS = ("problem", "required_action", "done", "close_condition")
FINDING_SCOPES = frozenset({"changed", "user", "owner-bounded", "repo-wide"})


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


def parse_issue_reference(value: str, default_repo: str = "") -> GitHubIssueReference:
    """Parse a full GitHub URL or explicit ``owner/repo#number`` value."""
    text = value.strip()
    match = GITHUB_URL_RE.fullmatch(text)
    if match:
        return GitHubIssueReference(match.group("repo"), match.group("number"))
    ref_match = re.fullmatch(r"(?P<repo>[^/#]+/[^/#]+)#(?P<number>[1-9][0-9]*)", text)
    if ref_match:
        return GitHubIssueReference(ref_match.group("repo"), ref_match.group("number"))
    if default_repo and re.fullmatch(r"[1-9][0-9]*", text):
        return GitHubIssueReference(default_repo, text)
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
        self.default_repo = default_repo

    def _repo(self, reference: GitHubIssueReference) -> str:
        return reference.repo or self.default_repo

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
        "status": "pending",
    }
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
    record = client.create(str(payload["repository"]), str(payload["title"]), body)
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
