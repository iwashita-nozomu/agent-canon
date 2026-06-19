#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates local AgentCanon issue files and mirrors them to GitHub Issues.
# upstream design ../../issues/README.md durable local issue convention
# upstream design ../../documents/responsibility-scope-management.md local/GitHub issue sync policy
# upstream design ../../tools/README.md tool entrypoint index
# upstream design ../../documents/tools/README.md user-facing tool index
# downstream implementation ../../tools/ci/run_all_checks.sh runs offline issue validation
# downstream implementation ../../tests/agent_tools/test_issue_sync.py tests issue validation
# @dependency-end
"""Validate local AgentCanon issues and plan or run GitHub Issue synchronization."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

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
OPEN_STATUSES = {"open", "in_progress", "deferred"}
CLOSED_STATUSES = {"resolved", "wontfix", "deferred"}
ISSUE_ID_RE = re.compile(r"^AC-\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")


@dataclass(frozen=True)
class Finding:
    """One issue sync finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"ISSUE_SYNC_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class IssueRecord:
    """One parsed local issue file."""

    path: Path
    directory_state: str
    fields: dict[str, str]

    @property
    def issue_id(self) -> str:
        """Return the issue id."""
        return self.fields.get("issue_id", "")

    @property
    def github_issue(self) -> str:
        """Return the linked GitHub Issue URL or marker."""
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
        title = issue.path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
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
    """Return AgentCanon source root for standalone or parent invocation."""
    vendored = root / "vendor" / "agent-canon"
    if (vendored / "issues" / "README.md").is_file():
        return vendored
    return root


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
        records.append(
            IssueRecord(
                path=path,
                directory_state=directory_state,
                fields=parse_fields(path.read_text(encoding="utf-8")),
            )
        )
    return tuple(records)


def validate_required_fields(root: Path, issue: IssueRecord) -> list[Finding]:
    """Validate required local issue fields."""
    rel_path = relative(root, issue.path)
    findings = [
        Finding("field", rel_path, f"missing:{field}")
        for field in REQUIRED_FIELDS
        if not issue.fields.get(field)
    ]
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
    if value and value not in {"pending", "not-created"} and github_issue_reference(value, "") is None:
        return [Finding("github", relative(root, issue.path), "invalid-github_issue")]
    if not required:
        return []
    if value.startswith("https://github.com/") or value in {"pending", "not-created"}:
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
        if issue.github_issue:
            continue
        title = issue.path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        command = f"gh issue create --repo {repo or '<owner/name>'} --title {json.dumps(title)} --body-file {relative(root, issue.path)}"
        lines.append(f"{issue.issue_id}:{command}")
    return tuple(lines)


def issue_title(path: Path) -> str:
    """Return a local issue title from the first Markdown heading."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return path.stem


def github_issue_reference(value: str, default_repo: str) -> GitHubIssueReference | None:
    """Parse a GitHub Issue URL or issue number."""
    if not value or value in {"pending", "not-created"}:
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
        reference = github_issue_reference(issue.github_issue, repo)
        if reference is None:
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
    return sum(1 for issue in issues if not issue.github_issue)


def insert_github_issue(path: Path, url: str) -> None:
    """Insert a github_issue field into one local issue file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("evidence:"):
            lines.insert(index + 1, f"github_issue: {url}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    path.write_text("\n".join([*lines, f"github_issue: {url}"]) + "\n", encoding="utf-8")


def apply_missing_links(issues: Sequence[IssueRecord], repo: str) -> tuple[str, ...]:
    """Create GitHub Issues for unlinked local issues."""
    creator = GitHubIssueCreator(repo)
    created: list[str] = []
    for issue in issues:
        if issue.github_issue:
            continue
        creator.create(issue)
        insert_github_issue(issue.path, creator.created_url)
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(render_markdown_summary(report))


def main(argv: Sequence[str] | None = None) -> int:
    """Run issue validation and optional GitHub sync planning."""
    args = build_parser().parse_args(argv)
    report = validate(args.root, args.require_github_link, args.repo, github_check=False)
    if args.apply and not report.findings:
        created = apply_missing_links(report.issues, args.repo)
        print(f"ISSUE_SYNC_CREATED={len(created)}")
        for item in created:
            print(f"ISSUE_SYNC_CREATED_ITEM={item}")
        report = validate(args.root, args.require_github_link, args.repo, github_check=False)
    if args.sync_github and not report.findings:
        synced = sync_linked_github_issues(report.issues, args.repo)
        print(f"ISSUE_SYNC_GITHUB_SYNCED={len(synced)}")
        for item in synced:
            print(f"ISSUE_SYNC_GITHUB_SYNCED_ITEM={item}")
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
