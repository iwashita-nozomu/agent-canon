#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Tests repository-qualified GitHub Issue parsing, private packet transport, host readback, and clause routing.
# upstream implementation ../../tools/agent_tools/issue_sync.py owns the host adapter
# upstream design ../../documents/runtime/private-feedback-knowledge.md owns the private packet path
# @dependency-end
"""Focused GitHub Issue authority tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import issue_sync  # noqa: E402


def test_github_reference_requires_repository_and_number() -> None:
    ref = issue_sync.parse_issue_reference("https://github.com/owner/repo/issues/882")
    assert ref.repo == "owner/repo"
    assert ref.number == "882"
    assert issue_sync.parse_issue_reference("882", "owner/repo").url.endswith("/882")
    with pytest.raises(issue_sync.IssueSyncError):
        issue_sync.parse_issue_reference("#882")


def test_github_record_and_clause_projection_preserve_repository_identity() -> None:
    issue = issue_sync.GitHubIssueRecord(
        repository="owner/repo",
        number="882",
        title="Issue authority",
        body="## Problem\nObserved failure. Evidence: run-1.\n\n## Done\nAdvisory cleanup.",
        state="OPEN",
        url="https://github.com/owner/repo/issues/882",
    )
    clauses = issue_sync.project_issue_clauses(issue)
    assert clauses[0]["state"] == "grounded"
    assert clauses[0]["repository"] == "owner/repo"
    assert clauses[0]["issue_number"] == "882"
    assert clauses[2]["state"] == "advisory"


def test_issue_state_is_normalized_to_open_or_closed() -> None:
    assert issue_sync.normalize_issue_state("OPEN") == "open"
    assert issue_sync.normalize_issue_state("closed") == "closed"
    with pytest.raises(issue_sync.IssueSyncError, match="issue_state_invalid"):
        issue_sync.normalize_issue_state("pending")


def test_offline_packet_contains_locator_and_digest_but_not_body(tmp_path: Path) -> None:
    body = tmp_path / "private-body.md"
    body.write_text("private body must stay private\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(body.read_bytes()).hexdigest()
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "agent-canon-log",
        repository="owner/repo",
        title="Private finding",
        body_locator=str(body),
        body_digest=digest,
        run="run-1",
        task="task-1",
    )
    payload = json.loads(packet.read_text(encoding="utf-8"))
    assert payload["body_locator"] == str(body)
    assert payload["body_digest"] == digest
    assert "private body" not in packet.read_text(encoding="utf-8")
    assert "issues/" not in str(packet)


def test_pending_packet_online_create_readback_removes_packet(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Issue body\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(body.read_bytes()).hexdigest()
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="Online packet",
        body_locator=str(body),
        body_digest=digest,
        input_mode="issue-publication-initial",
    )
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="42", title="Online packet",
        body="Issue body\n", state="OPEN",
        url="https://github.com/owner/repo/issues/42",
    )
    client = issue_sync.GitHubIssueClient("owner/repo")
    with (
        patch.object(client, "create", return_value=record) as create,
        patch.object(client, "search", return_value=()),
    ):
        result = issue_sync.sync_pending_packet(
            packet,
            client,
            checkout_identity={"remote": "owner/repo"},
            runtime_root=tmp_path / "runtime",
            receipt_stager=_spooling_stager(tmp_path / "runtime"),
        )
    assert result.url.endswith("/42")
    create.assert_called_once_with("owner/repo", "Online packet", "Issue body\n")
    assert not packet.exists()


def test_pending_packet_success_writes_body_free_publication_receipt(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("private Issue body\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(body.read_bytes()).hexdigest()
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="Receipt packet",
        body_locator=str(body),
        body_digest=digest,
        input_mode="issue-publication-initial",
        source_finding_kind="recurrent-failure",
    )
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="42", title="Receipt packet",
        body="private Issue body\n", state="OPEN",
        url="https://github.com/owner/repo/issues/42",
    )
    client = issue_sync.GitHubIssueClient("owner/repo")
    with (
        patch.object(client, "create", return_value=record),
        patch.object(client, "search", return_value=()),
    ):
        issue_sync.sync_pending_packet(
            packet,
            client,
            checkout_identity={"remote": "owner/repo"},
            runtime_root=tmp_path / "runtime",
            receipt_stager=_spooling_stager(
                tmp_path / "runtime", source_finding_kind="recurrent-failure"
            ),
        )
    receipt_path = issue_sync.issue_publication_receipt_spool_path(
        tmp_path / "runtime", "owner/repo", "42"
    )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert set(payload) == set(issue_sync.ISSUE_PUBLICATION_RECEIPT_FIELDS)
    assert payload["repository"] == "owner/repo"
    assert payload["number"] == "42"
    assert payload["url"] == record.url
    assert payload["action"] == "create"
    assert payload["source_finding_kind"] == "recurrent-failure"
    assert "private Issue body" not in receipt_path.read_text(encoding="utf-8")
    assert not packet.exists()


def test_publication_receipt_noop_updates_stable_file(tmp_path: Path) -> None:
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="42", title="Receipt", body="body",
        state="OPEN", url="https://github.com/owner/repo/issues/42",
    )
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(finding_kind="recurrent-failure"),
        authenticated_repository="owner/repo",
    )
    path = issue_sync.write_issue_publication_receipt(
        tmp_path / "log", record, action="update", handoff=handoff,
        timestamp="2026-08-27T00:00:00Z",
    )
    issue_sync.write_issue_publication_receipt(
        tmp_path / "log", record, action="noop", handoff=handoff,
        timestamp="2026-08-27T01:00:00Z",
    )
    assert path == issue_sync.issue_publication_receipt_path(tmp_path / "log", "owner/repo", "42")
    assert json.loads(path.read_text(encoding="utf-8"))["action"] == "noop"


def test_stage_publication_receipt_uses_external_private_feedback_spool(tmp_path: Path) -> None:
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="44", title="Receipt", body="private",
        state="OPEN", url="https://github.com/owner/repo/issues/44",
    )
    path = issue_sync.stage_issue_publication_receipt(
        tmp_path / "runtime",
        record,
        action="create",
        source_finding_kind="recurrent-failure",
    )
    assert path == (
        tmp_path / "runtime" / "spool" / "private-feedback" / "feedback"
        / "issue-packets" / "published" / "owner" / "repo" / "44.json"
    )
    assert path.is_file()
    assert not (tmp_path / "agent-canon-log").exists()
    assert "private" not in path.read_text(encoding="utf-8")
    request = tmp_path / "runtime" / "spool" / "private-feedback" / "sync-request.json"
    request_payload = json.loads(request.read_text(encoding="utf-8"))
    assert set(request_payload) == {
        "execution_plane",
        "operation",
        "requested_at",
        "schema",
        "source_commit",
    }
    assert request_payload["source_commit"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()


def test_stage_publication_receipt_cli_is_body_free(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert issue_sync.main(
        [
            "--repo", "owner/repo",
            "--runtime-root", str(tmp_path / "runtime"),
            "--stage-publication-receipt",
            "--receipt-number", "45",
            "--receipt-url", "https://github.com/owner/repo/issues/45",
            "--receipt-state", "OPEN",
            "--receipt-action", "create",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert '"status": "staged"' in output
    assert "body" not in output


def test_container_receipt_stager_runs_resident_cli_argv(tmp_path: Path) -> None:
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="49", title="Receipt", body="private",
        state="OPEN", url="https://github.com/owner/repo/issues/49",
    )
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(finding_kind="recurrent-failure"),
        authenticated_repository="owner/repo",
    )
    commands: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        inner = command[command.index("--") + 1 :]
        return subprocess.CompletedProcess(
            command,
            issue_sync.main(inner),
            "",
            "",
        )

    stager = issue_sync.build_container_receipt_stager(
        runtime_root=tmp_path / "runtime",
        checkout_identity={
            "git_root": str(PROJECT_ROOT),
            "head": subprocess.check_output(
                ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
                text=True,
            ).strip(),
            "remote": "owner/repo",
        },
        source_root=PROJECT_ROOT,
        command_runner=runner,
    )
    stager.preflight()
    stager(record, "create", handoff)
    assert len(commands) == 2
    assert all("issue-sync" in command for command in commands)
    assert "--receipt-preflight" in commands[0]
    assert "--stage-publication-receipt" in commands[1]
    assert issue_sync.issue_publication_receipt_spool_path(
        tmp_path / "runtime", "owner/repo", "49"
    ).is_file()


def test_publication_receipt_replace_failure_preserves_prior_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="46", title="Receipt", body="private",
        state="OPEN", url="https://github.com/owner/repo/issues/46",
    )
    path = issue_sync.write_issue_publication_receipt(
        tmp_path / "log", record, action="create", timestamp="2026-08-27T00:00:00Z"
    )
    before = path.read_bytes()

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(issue_sync.os, "replace", fail_replace)
    with pytest.raises(issue_sync.IssueSyncError, match="issue_receipt_write_failed"):
        issue_sync.write_issue_publication_receipt(
            tmp_path / "log", record, action="update", timestamp="2026-08-27T01:00:00Z"
        )
    assert path.read_bytes() == before
    assert not tuple(path.parent.glob(".*.tmp"))


def test_retry_receipt_match_requires_full_responsibility_tuple(tmp_path: Path) -> None:
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="47", title="Receipt", body="private",
        state="OPEN", url="https://github.com/owner/repo/issues/47",
    )
    first = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(fix="first fix", finding_kind="recurrent-failure"),
        authenticated_repository="owner/repo",
    )
    second = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(fix="second fix", finding_kind="recurrent-failure"),
        authenticated_repository="owner/repo",
    )
    root = tmp_path / "runtime" / "spool" / "private-feedback"
    issue_sync.write_issue_publication_receipt(
        root, record, action="create", handoff=first,
    )
    assert issue_sync.find_issue_publication_receipt(root, "owner/repo") is None
    assert issue_sync.find_issue_publication_receipt(
        root, "owner/repo", handoff=second, number="47"
    ) is None


def test_publication_receipt_post_replace_readback_failure_removes_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="48", title="Receipt", body="private",
        state="OPEN", url="https://github.com/owner/repo/issues/48",
    )
    target = issue_sync.issue_publication_receipt_path(
        tmp_path / "log", "owner/repo", "48"
    )
    original_read_text = Path.read_text

    def fail_final_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == target:
            return "not-json"
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_final_read)
    with pytest.raises(issue_sync.IssueSyncError, match="issue_receipt_write_failed"):
        issue_sync.write_issue_publication_receipt(
            tmp_path / "log", record, action="create"
        )
    assert not target.exists()
    assert not tuple(target.parent.glob(".*.tmp"))


def test_foreign_or_nonqualified_issue_worker_has_no_publication_receipt(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(repository="other/repo"),
        authenticated_repository="owner/repo",
    )
    assert not handoff.qualifies
    assert not tuple((tmp_path / "log").rglob("*.json"))


def test_pending_packet_digest_mismatch_is_retained(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("changed body\n", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="Retain packet",
        body_locator=str(body),
        body_digest="sha256:" + "0" * 64,
    )
    with pytest.raises(issue_sync.IssueSyncError, match="body_digest_mismatch"):
        issue_sync.sync_pending_packet(
            packet,
            issue_sync.GitHubIssueClient("owner/repo"),
            checkout_identity={"remote": "owner/repo"},
        )
    assert packet.exists()


def test_pending_packet_receipt_failure_retains_packet(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("private body\n", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="Receipt failure",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
        input_mode="issue-publication-initial",
    )
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="43", title="Receipt failure",
        body="private body\n", state="OPEN",
        url="https://github.com/owner/repo/issues/43",
    )
    client = issue_sync.GitHubIssueClient("owner/repo")
    stager = _FakeReceiptStager(
        lambda record, action, handoff: issue_sync.stage_issue_publication_receipt(
            tmp_path / "runtime", record, action=action, handoff=handoff
        )
    )
    with (
        patch.object(client, "create", return_value=record),
        patch.object(client, "search", return_value=()),
        patch.object(
            issue_sync,
            "stage_issue_publication_receipt",
            side_effect=issue_sync.IssueSyncError(
                "issue_receipt_write_failed", "archive unavailable"
            ),
        ),
        pytest.raises(issue_sync.IssueSyncError, match="issue_receipt_write_failed"),
    ):
        issue_sync.sync_pending_packet(
            packet,
            client,
            checkout_identity={"remote": "owner/repo"},
            runtime_root=tmp_path / "runtime",
            receipt_stager=stager,
        )
    assert packet.exists()
    assert not (tmp_path / "runtime" / "spool" / "private-feedback" / "feedback" / "issue-packets" / "published").exists()


def test_pending_packet_requires_current_checkout_identity(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("body\n", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="identity required",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
    )
    with pytest.raises(issue_sync.IssueSyncError, match="checkout-identity-unresolved"):
        issue_sync.sync_pending_packet(packet, issue_sync.GitHubIssueClient())
    assert packet.exists()


def test_pending_packet_rejects_different_current_checkout(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("body\n", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="identity mismatch",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
    )
    with pytest.raises(issue_sync.IssueSyncError, match="checkout-repository-mismatch"):
        issue_sync.sync_pending_packet(
            packet,
            issue_sync.GitHubIssueClient(),
            checkout_identity={"remote": "other/repo"},
        )
    assert packet.exists()


def test_github_adapter_mock_readback_is_host_only() -> None:
    payload = json.dumps({
        "number": 882,
        "title": "Readback",
        "body": "body",
        "state": "OPEN",
        "url": "https://github.com/owner/repo/issues/882",
    })
    result = __import__("subprocess").CompletedProcess([], 0, payload, "")
    client = issue_sync.GitHubIssueClient("owner/repo")
    with patch.object(issue_sync.subprocess, "run", return_value=result) as run:
        record = client.read(issue_sync.parse_issue_reference("owner/repo#882"))
    assert record.repository == "owner/repo"
    assert run.call_args.args[0][:3] == ["gh", "issue", "view"]


def test_no_issue_url_reports_lookup_required_without_local_scan(capsys: pytest.CaptureFixture[str]) -> None:
    assert issue_sync.main([]) == 2
    assert "GITHUB_ISSUE_LOOKUP_REQUIRED=1" in capsys.readouterr().out


def test_group_findings_keeps_owner_clause_routing_without_path_records() -> None:
    grouped = issue_sync.group_findings([
        {"owner": "github-adapter", "root_cause": "local mirror", "fix": "use URL/number", "evidence": "run-1"},
        {"owner": "github-adapter", "root_cause": "local mirror", "fix": "use URL/number", "evidence": "run-2"},
    ])
    assert len(grouped) == 1
    assert grouped[0]["evidence"] == ["run-1", "run-2"]
    assert "paths" not in grouped[0]


def _qualified_finding(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "repository": "owner/repo",
        "owner": "issue-owner",
        "fix": "repair the missing route",
        "actionable": True,
        "occurrence_locations": [{"path": "tools/route.py", "locator": "route"}],
    }
    record.update(overrides)
    return record


def test_issue_worker_qualifies_flagless_user_owned_candidate() -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(finding_kind="recurrent-failure"), authenticated_repository="owner/repo"
    )
    assert handoff.status == "qualified"
    assert handoff.qualifies
    assert handoff.reason == "user-owned-candidate"
    assert handoff.occurrence_locations == ("tools/route.py::route",)
    assert handoff.source_finding_kind == "recurrent-failure"
    assert handoff.as_dict()["schema"] == issue_sync.ISSUE_WORKER_HANDOFF_SCHEMA


def test_issue_worker_preserves_no_issue_boundary_for_transient_observations() -> None:
    for finding in (
        _qualified_finding(finding_kind="count"),
        _qualified_finding(finding_kind="status"),
        _qualified_finding(finding_kind="selection-miss"),
        _qualified_finding(finding_kind="one-off"),
        _qualified_finding(current_scope_resolved=True),
        _qualified_finding(durable_follow_up=False),
    ):
        handoff = issue_sync.qualify_issue_worker_finding(
            finding, authenticated_repository="owner/repo"
        )
        assert handoff.status == "no-action"


def test_issue_worker_returns_no_mutation_handoff_for_other_or_missing_repo() -> None:
    other = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(repository="other/repo"), authenticated_repository="owner/repo"
    )
    missing = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(repository=""), authenticated_repository="owner/repo"
    )
    assert (other.status, other.reason) == ("handoff", "other-repository")
    assert (missing.status, missing.reason) == ("handoff", "repository-unresolved")


def test_issue_worker_plan_reorganizes_mixed_related_issues_without_mutation() -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    related = (
        issue_sync.GitHubIssueRecord(
            "owner/repo", "1", "old open", "## Finding\nrepair another route", "OPEN",
            "https://github.com/owner/repo/issues/1",
        ),
        issue_sync.GitHubIssueRecord(
            "owner/repo", "2", "old closed", "## Responsibility Boundary\nowner: issue-owner\n## Required Fix\nrepair the missing route\n## Finding\nrepair the missing route", "CLOSED",
            "https://github.com/owner/repo/issues/2",
        ),
    )
    plan = issue_sync.IssueWorker(None, "owner/repo").plan_publication(handoff, related)  # type: ignore[arg-type]
    assert plan.action == "reorganize"
    assert plan.destination_issue_ref.endswith("/2")
    assert plan.related_issue_refs == tuple(issue.url for issue in related)


def test_issue_worker_plan_rerun_is_noop_for_existing_destination() -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    issue = issue_sync.GitHubIssueRecord(
        "owner/repo", "2", "route", "## Responsibility Boundary\nowner: issue-owner\n## Required Fix\nrepair the missing route\n## Finding\nrepair the missing route", "OPEN",
        "https://github.com/owner/repo/issues/2",
    )
    plan = issue_sync.IssueWorker(None, "owner/repo").plan_publication(handoff, (issue,))  # type: ignore[arg-type]
    assert plan.action == "noop"


def test_publisher_projection_carries_checkout_identity_without_approval_gate() -> None:
    publisher = (
        Path(__file__).resolve().parents[2] / ".codex" / "agents" / "publisher.toml"
    ).read_text(encoding="utf-8")
    assert 'approval_policy = "never"' in publisher
    assert "checkout_identity" in publisher
    assert "cwd" in publisher and "branch" in publisher and "remote owner/repository" in publisher
    assert "extra approval" in publisher


def test_repository_normalization_matches_common_git_transports() -> None:
    assert issue_sync.normalize_repository("git@github.com:Owner/Repo.git") == "owner/repo"
    assert issue_sync.normalize_repository("https://github.com/Owner/Repo.git") == "owner/repo"
    assert issue_sync.normalize_repository("OWNER/REPO") == "owner/repo"


class _IssueWorkerClient:
    def __init__(self, records: tuple[issue_sync.GitHubIssueRecord, ...]) -> None:
        self.records = {record.number: record for record in records}
        self.calls: list[tuple[str, str]] = []

    def create(self, repository: str, title: str, body: str) -> issue_sync.GitHubIssueRecord:
        raise issue_sync.IssueSyncError("github_unavailable", "test client unavailable")

    def read(self, reference: issue_sync.GitHubIssueReference) -> issue_sync.GitHubIssueRecord:
        return self.records[reference.number]

    def edit(self, issue: issue_sync.GitHubIssueRecord, *, title: str, body: str) -> issue_sync.GitHubIssueRecord:
        self.calls.append(("edit", issue.number))
        updated = issue_sync.GitHubIssueRecord(
            issue.repository, issue.number, title, body, issue.state, issue.url
        )
        self.records[issue.number] = updated
        return updated

    def set_state(self, issue: issue_sync.GitHubIssueRecord, state: str) -> issue_sync.GitHubIssueRecord:
        self.calls.append(("state", issue.number))
        updated = issue_sync.GitHubIssueRecord(
            issue.repository, issue.number, issue.title, issue.body, state, issue.url
        )
        self.records[issue.number] = updated
        return updated


class _SuccessfulIssueWorkerClient(_IssueWorkerClient):
    def create(self, repository: str, title: str, body: str) -> issue_sync.GitHubIssueRecord:
        record = issue_sync.GitHubIssueRecord(
            repository,
            "42",
            title,
            body,
            "OPEN",
            f"https://github.com/{repository}/issues/42",
        )
        self.records[record.number] = record
        return record


class _SearchingIssueWorkerClient(_SuccessfulIssueWorkerClient):
    def __init__(self, records: tuple[issue_sync.GitHubIssueRecord, ...]) -> None:
        super().__init__(records)
        self.search_calls = 0
        self.create_calls = 0

    def search(
        self, repository: str, terms: tuple[str, ...]
    ) -> tuple[issue_sync.GitHubIssueRecord, ...]:
        self.search_calls += 1
        return tuple(self.records.values())

    def create(self, repository: str, title: str, body: str) -> issue_sync.GitHubIssueRecord:
        self.create_calls += 1
        return super().create(repository, title, body)


class _FakeReceiptStager:
    def __init__(self, callback: object = None, *, fail_preflight: bool = False) -> None:
        self.fail_preflight = fail_preflight
        self.callback = callback
        self.preflight_calls = 0
        self.receipts: list[tuple[str, str]] = []

    def preflight(self) -> None:
        self.preflight_calls += 1
        if self.fail_preflight:
            raise issue_sync.IssueSyncError(
                "issue_receipt_route_unavailable", "test route unavailable"
            )

    def __call__(
        self,
        record: issue_sync.GitHubIssueRecord,
        action: str,
        handoff: issue_sync.IssueWorkerHandoff,
    ) -> None:
        self.receipts.append((record.url, action))
        if callable(self.callback):
            self.callback(record, action, handoff)


def _spooling_stager(runtime: Path, *, source_finding_kind: str = "") -> _FakeReceiptStager:
    def callback(
        record: issue_sync.GitHubIssueRecord,
        action: str,
        handoff: issue_sync.IssueWorkerHandoff,
    ) -> None:
        issue_sync.stage_issue_publication_receipt(
            runtime,
            record,
            action=action,
            handoff=handoff,
            source_finding_kind=source_finding_kind,
        )

    return _FakeReceiptStager(callback)

def test_issue_worker_reorganization_removes_transferred_clause_and_adds_backlinks(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(
            responsibility={"owner": "issue-owner", "decision": "repair route"}
        ),
        authenticated_repository="owner/repo",
    )
    source = issue_sync.GitHubIssueRecord(
        "owner/repo", "1", "mixed", "## Finding\nrepair the missing route\n## Evidence\nrepair the missing route", "OPEN",
        "https://github.com/owner/repo/issues/1",
    )
    destination = issue_sync.GitHubIssueRecord(
        "owner/repo", "2", "closed", "## Responsibility Boundary\nowner: issue-owner\ndecision: repair route\n## Required Fix\nrepair the missing route\n## Finding\nrepair the missing route", "CLOSED",
        "https://github.com/owner/repo/issues/2",
    )
    client = _IssueWorkerClient((source, destination))
    result = issue_sync.IssueWorker(client, "owner/repo").publish(
        handoff,
        title="route",
        body=destination.body,
        related_issues=(source, destination),
        receipt_stager=_FakeReceiptStager(),
    )
    assert result.state == "OPEN"
    assert issue_sync.parse_sections(client.records["1"].body).get("finding", "") == ""
    assert "## Evidence\nrepair the missing route" in client.records["1"].body
    assert "clauses transferred to https://github.com/owner/repo/issues/2" in client.records["1"].body
    assert "transferred from https://github.com/owner/repo/issues/1" in result.body
    assert client.calls.count(("edit", "1")) == 1


def test_issue_worker_uses_injected_container_receipt_stager(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    client = _SuccessfulIssueWorkerClient(())
    stager = _FakeReceiptStager()
    result = issue_sync.IssueWorker(client, "owner/repo").publish(
        handoff,
        title="route",
        body="body",
        receipt_stager=stager,
    )
    assert result.number == "42"
    assert stager.preflight_calls == 1
    assert stager.receipts == [(result.url, "create")]


def test_issue_worker_stager_preflight_blocks_github_mutation() -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    client = _SuccessfulIssueWorkerClient(())
    stager = _FakeReceiptStager(fail_preflight=True)
    with pytest.raises(issue_sync.IssueSyncError, match="issue_receipt_route_unavailable"):
        issue_sync.IssueWorker(client, "owner/repo").publish(
            handoff,
            title="route",
            body="body",
            receipt_stager=stager,
        )
    assert client.records == {}
    assert stager.preflight_calls == 1


def test_retry_searches_existing_issue_before_create_and_records_noop(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    existing = issue_sync.GitHubIssueRecord(
        "owner/repo",
        "42",
        "route",
        "## Responsibility Boundary\nowner: issue-owner\n"
        "## Required Fix\nrepair the missing route\n"
        "## Finding\nrepair the missing route",
        "OPEN",
        "https://github.com/owner/repo/issues/42",
    )
    client = _SearchingIssueWorkerClient((existing,))
    body = tmp_path / "private-body.md"
    body.write_text(existing.body, encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="route",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
        route="issue-worker",
        handoff=handoff.as_dict(),
    )
    result = issue_sync.sync_pending_packet(
        packet,
        client,
        checkout_identity={"remote": "owner/repo"},
        runtime_root=tmp_path / "runtime",
        receipt_stager=_spooling_stager(tmp_path / "runtime"),
    )
    assert result.number == "42"
    assert client.search_calls == 1
    assert client.create_calls == 0
    receipt = issue_sync.read_issue_publication_receipt(
        tmp_path / "runtime" / "spool" / "private-feedback", "owner/repo", "42"
    )
    assert receipt is not None
    assert receipt["action"] == "noop"
    assert not packet.exists()


def test_retry_body_keyword_match_without_exact_content_stays_pending(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    existing = issue_sync.GitHubIssueRecord(
        "owner/repo", "51", "route", "canonical body", "OPEN",
        "https://github.com/owner/repo/issues/51",
    )
    body = tmp_path / "body.md"
    body.write_text("canonical body plus unrelated packet text", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log", repository="owner/repo", title="route",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
        route="issue-worker", handoff=handoff.as_dict(),
    )
    client = _SearchingIssueWorkerClient((existing,))
    with pytest.raises(issue_sync.IssueSyncError, match="exactly match"):
        issue_sync.sync_pending_packet(
            packet, client, checkout_identity={"remote": "owner/repo"},
            runtime_root=tmp_path / "runtime",
            receipt_stager=_FakeReceiptStager(),
        )
    assert packet.exists()
    assert client.create_calls == 0


def test_retry_multiple_exact_content_matches_stays_pending(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    body = tmp_path / "body.md"
    body.write_text("same body", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log", repository="owner/repo", title="same title",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
        route="issue-worker", handoff=handoff.as_dict(),
    )
    records = tuple(
        issue_sync.GitHubIssueRecord(
            "owner/repo", str(number), "same title", "same body", "OPEN",
            f"https://github.com/owner/repo/issues/{number}",
        )
        for number in (52, 53)
    )
    with pytest.raises(issue_sync.IssueSyncError, match="multiple exact"):
        issue_sync.sync_pending_packet(
            packet, _SearchingIssueWorkerClient(records),
            checkout_identity={"remote": "owner/repo"},
            runtime_root=tmp_path / "runtime",
            receipt_stager=_FakeReceiptStager(),
        )
    assert packet.exists()


def test_retry_search_error_stays_pending(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    body = tmp_path / "body.md"
    body.write_text("body", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log", repository="owner/repo", title="search error",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
        route="issue-worker", handoff=handoff.as_dict(),
    )

    class FailingSearchClient(_SearchingIssueWorkerClient):
        def search(self, repository: str, terms: tuple[str, ...]) -> tuple[issue_sync.GitHubIssueRecord, ...]:
            raise issue_sync.IssueSyncError("github_unavailable", "search unavailable")

    with pytest.raises(issue_sync.IssueSyncError, match="github_unavailable"):
        issue_sync.sync_pending_packet(
            packet, FailingSearchClient(()),
            checkout_identity={"remote": "owner/repo"},
            runtime_root=tmp_path / "runtime",
            receipt_stager=_FakeReceiptStager(),
        )
    assert packet.exists()


def test_retry_without_exact_search_result_remains_pending_without_create(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(finding_kind="recurrent-failure"),
        authenticated_repository="owner/repo",
    )
    body = tmp_path / "private-body.md"
    body.write_text("private body\n", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="unresolved retry",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
        route="issue-worker",
        handoff=handoff.as_dict(),
    )
    client = _SearchingIssueWorkerClient(())
    with pytest.raises(issue_sync.IssueSyncError, match="issue_worker_retry_unresolved"):
        issue_sync.sync_pending_packet(
            packet,
            client,
            checkout_identity={"remote": "owner/repo"},
            runtime_root=tmp_path / "runtime",
            receipt_stager=_FakeReceiptStager(),
        )
    assert packet.exists()
    assert client.calls == []


def test_initial_packet_retry_consumes_exact_receipt_without_duplicate_create(
    tmp_path: Path,
) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(finding_kind="recurrent-failure"),
        authenticated_repository="owner/repo",
    )
    body = tmp_path / "private-body.md"
    body.write_text("private body\n", encoding="utf-8")
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "log",
        repository="owner/repo",
        title="crashed initial",
        body_locator=str(body),
        body_digest="sha256:" + hashlib.sha256(body.read_bytes()).hexdigest(),
        input_mode="issue-publication-initial",
        route="issue-worker",
        handoff=handoff.as_dict(),
    )
    record = issue_sync.GitHubIssueRecord(
        "owner/repo", "50", "crashed initial", "private body", "OPEN",
        "https://github.com/owner/repo/issues/50",
    )
    runtime_archive = tmp_path / "runtime" / "spool" / "private-feedback"
    issue_sync.write_issue_publication_receipt(
        runtime_archive, record, action="create", handoff=handoff
    )
    client = _IssueWorkerClient((record,))
    result = issue_sync.sync_pending_packet(
        packet,
        client,
        checkout_identity={"remote": "owner/repo"},
        runtime_root=tmp_path / "runtime",
        receipt_stager=_FakeReceiptStager(),
    )
    assert result.number == "50"
    assert packet.exists() is False
    assert client.calls == []


def test_issue_worker_foreign_related_issue_is_handoff_relation_without_mutation(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    local = issue_sync.GitHubIssueRecord(
        "owner/repo", "2", "local", "## Responsibility Boundary\nowner: issue-owner\n## Required Fix\nrepair the missing route\n## Finding\nlocal clause", "OPEN",
        "https://github.com/owner/repo/issues/2",
    )
    foreign = issue_sync.GitHubIssueRecord(
        "other/repo", "8", "foreign", "owner: issue-owner\n## Finding\nforeign clause", "OPEN",
        "https://github.com/other/repo/issues/8",
    )
    client = _IssueWorkerClient((local, foreign))
    result = issue_sync.IssueWorker(client, "owner/repo").publish(
        handoff,
        title="route",
        body=local.body,
        related_issues=(local, foreign),
        receipt_stager=_FakeReceiptStager(),
    )
    assert result.number == "2"
    assert client.calls == [("edit", "2")]
    assert client.records["8"].body == foreign.body
    assert "handoff relation: foreign Issue https://github.com/other/repo/issues/8" in result.body


def test_issue_worker_changed_fix_clause_requires_update() -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(fix="new fix"), authenticated_repository="owner/repo"
    )
    old = issue_sync.GitHubIssueRecord(
        "owner/repo", "3", "old", "## Responsibility Boundary\nowner: issue-owner\n## Required Fix\nold fix", "OPEN",
        "https://github.com/owner/repo/issues/3",
    )
    plan = issue_sync.IssueWorker(None, "owner/repo").plan_publication(handoff, (old,))  # type: ignore[arg-type]
    assert plan.action == "update"


def test_issue_worker_requires_receipt_route_before_github_mutation() -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    client = _IssueWorkerClient(())
    with patch.dict(os.environ, {"AGENT_CANON_RUNTIME_ROOT": "", "AGENT_CANON_LOG_ROOT": ""}, clear=False), pytest.raises(issue_sync.IssueSyncError, match="issue_receipt_route_unavailable"):
        issue_sync.IssueWorker(client, "owner/repo").publish(
            handoff,
            title="route",
            body="body",
        )
    assert client.calls == []


def test_issue_worker_failure_writes_metadata_only_retry_packet(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    body = tmp_path / "private-body.md"
    body.write_text("private Issue body\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(body.read_bytes()).hexdigest()
    client = _IssueWorkerClient(())
    worker = issue_sync.IssueWorker(client, "owner/repo")
    with pytest.raises(issue_sync.IssueSyncError, match="github_unavailable"):
        worker.publish(
            handoff,
            title="retry me",
            body=body.read_text(encoding="utf-8"),
            defer_log_root=tmp_path / "agent-canon-log",
            body_locator=str(body),
            body_digest=digest,
            receipt_stager=_FakeReceiptStager(),
        )
    packets = tuple((tmp_path / "agent-canon-log" / "feedback/issue-packets/pending").glob("*.json"))
    assert len(packets) == 1
    packet = packets[0].read_text(encoding="utf-8")
    assert "github_unavailable" in packet
    assert "issue-worker" in packet
    assert "private Issue body" not in packet


def test_issue_worker_retry_packet_returns_through_issue_worker_route(tmp_path: Path) -> None:
    handoff = issue_sync.qualify_issue_worker_finding(
        _qualified_finding(), authenticated_repository="owner/repo"
    )
    existing = issue_sync.GitHubIssueRecord(
        "owner/repo",
        "42",
        "retry route",
        "## Responsibility Boundary\nowner: issue-owner\n"
        "## Required Fix\nrepair the missing route\n"
        "## Finding\nrepair the missing route",
        "OPEN",
        "https://github.com/owner/repo/issues/42",
    )
    body = tmp_path / "private-body.md"
    body.write_text(existing.body, encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(body.read_bytes()).hexdigest()
    packet = issue_sync.write_pending_packet(
        log_root=tmp_path / "agent-canon-log",
        repository="owner/repo",
        title="retry route",
        body_locator=str(body),
        body_digest=digest,
        route="issue-worker",
        handoff=handoff.as_dict(),
    )
    result = issue_sync.sync_pending_packet(
        packet,
        _SearchingIssueWorkerClient((existing,)),
        checkout_identity={"remote": "owner/repo"},
        runtime_root=tmp_path / "runtime",
        receipt_stager=_spooling_stager(tmp_path / "runtime"),
    )
    assert result.url.endswith("/42")
    assert not packet.exists()
