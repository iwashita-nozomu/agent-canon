"""Tests for the IssueWorker receipt-stage ToolCall command."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.agent_tools.tool_calls import (
    build_issue_receipt_stage_command,
    materialize_issue_worker_tool_call,
)


def test_issue_worker_tool_call_contains_post_publication_container_command() -> None:
    token = materialize_issue_worker_tool_call(
        handoff={"repository": "owner/repo", "fix": "repair route"},
        publisher_agent_id="publisher-1",
        checkout_repository="owner/repo",
        checkout_identity={
            "cwd": str(PROJECT_ROOT),
            "git_root": str(PROJECT_ROOT),
            "branch": "main",
            "head": "a" * 40,
            "remote": "owner/repo",
        },
        control_parent_root="/var/lib/agent-canon",
        runtime_root="/var/lib/agent-canon/runtime",
        source_root=str(PROJECT_ROOT),
    )
    command = token["arguments"]["receipt_stage_command"]
    assert tuple(command[:8]) == (
        str(PROJECT_ROOT / "bootstrap.sh"),
        "--control-parent-root",
        "/var/lib/agent-canon",
        "--runtime-root",
        "/var/lib/agent-canon/runtime",
        "tool",
        "run",
        "--root",
    )
    assert "issue_sync" in command
    assert "--stage-publication-receipt" in command
    assert "--checkout-head" in command
    assert "--checkout-repository" in command
    assert "repair route" not in command


def test_receipt_stage_command_contains_readback_metadata_without_body() -> None:
    command = build_issue_receipt_stage_command(
        repository="owner/repo",
        runtime_root="/runtime",
        source_root="/project",
        control_parent_root="/control",
        checkout_identity={"head": "b" * 40, "remote": "owner/repo"},
        number="42",
        url="https://github.com/owner/repo/issues/42",
        state="open",
        action="update",
        responsibility=("owner", "repair route"),
        occurrence_locations=("tools/route.py::route",),
        source_finding_kind="recurrent-failure",
        execution="exec",
    )
    assert command[0:10] == (
        "./bootstrap.sh",
        "--control-parent-root",
        "/control",
        "--runtime-root",
        "/runtime",
        "tool",
        "exec",
        "--root",
        "/project",
        "issue_sync",
    )
    assert "--receipt-number" in command
    assert "42" in command
    assert "--receipt-url" in command
    assert "private body" not in " ".join(command)


def test_receipt_stage_command_rejects_non_github_issue_state() -> None:
    with pytest.raises(ValueError, match="state"):
        build_issue_receipt_stage_command(
            repository="owner/repo",
            state="pending",
            action="create",
        )
