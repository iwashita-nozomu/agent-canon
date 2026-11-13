"""Tests for the IssueWorker receipt-stage ToolCall command."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.agent.orchestration.tool_calls import build_issue_receipt_stage_command


def test_receipt_stage_command_contains_readback_metadata_without_body() -> None:
    command = build_issue_receipt_stage_command(
        repository="owner/repo",
        runtime_root="/runtime",
        agentcanon_source_root="/agent-canon",
        target_root="/project",
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
        "/agent-canon/bootstrap.sh",
        "--control-parent-root",
        "/control",
        "--runtime-root",
        "/runtime",
        "tool",
        "exec",
        "--root",
        "/project",
        "issue-sync",
    )
    assert "--receipt-number" in command
    assert "42" in command
    assert "--receipt-url" in command
    assert "private body" not in " ".join(command)
    child_args = command[command.index("--") + 1 :]
    assert "/runtime" not in child_args
    assert "/project" not in child_args


def test_receipt_stage_command_rejects_non_github_issue_state() -> None:
    with pytest.raises(ValueError, match="state"):
        build_issue_receipt_stage_command(
            repository="owner/repo",
            state="pending",
            action="create",
        )
