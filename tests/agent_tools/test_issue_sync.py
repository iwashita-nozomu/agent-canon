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
    )
    record = issue_sync.GitHubIssueRecord(
        repository="owner/repo", number="42", title="Online packet",
        body="Issue body\n", state="OPEN",
        url="https://github.com/owner/repo/issues/42",
    )
    client = issue_sync.GitHubIssueClient("owner/repo")
    with patch.object(client, "create", return_value=record) as create:
        result = issue_sync.sync_pending_packet(packet, client)
    assert result.url.endswith("/42")
    create.assert_called_once_with("owner/repo", "Online packet", "Issue body\n")
    assert not packet.exists()


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
        issue_sync.sync_pending_packet(packet, issue_sync.GitHubIssueClient("owner/repo"))
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
