# @dependency-start
# contract test
# responsibility Tests orchestration materialization of the IssueWorker publisher route.
# upstream implementation ../../tools/agent_tools/issue_worker_dispatch.py materializes route and ToolCall
# upstream implementation ../../tools/agent_tools/agent_team.py exposes orchestration facade
# @dependency-end
"""Focused IssueWorker orchestration tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import issue_worker_dispatch  # noqa: E402
from checkout_identity import CheckoutIdentity  # noqa: E402
from implementation_dispatch import (  # noqa: E402
    recommended_initial_subagent_wave,
    workflow_spawn_budget,
)
from team_config import (  # noqa: E402
    load_task_catalog,
    load_team_config,
    select_roles,
)


def _candidate(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "repository": "iwashita-nozomu/agent-canon",
        "owner": "issue-worker",
        "fix": "connect explicit candidates to publisher",
        "decision": "route durable feedback",
    }
    value.update(overrides)
    return value


def test_same_repository_candidate_materializes_publisher_tool_call() -> None:
    calls: list[tuple[str, str]] = []

    def spawn(agent_type: str, prompt: str) -> str:
        calls.append((agent_type, prompt))
        return "publisher-1"

    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(),
        "publish explicit feedback",
        spawn,
        workspace_root=PROJECT_ROOT,
        source_root=PROJECT_ROOT,
        request_clause_ids=("feedback-routing",),
    )

    assert result.status == "spawned"
    assert result.handoff.qualifies
    assert result.publisher_agent_id == "publisher-1"
    assert result.tool_call is not None
    assert result.tool_call["tool_id"] == "issue-worker"
    assert result.tool_call["arguments"]["publisher_agent_id"] == "publisher-1"
    assert result.tool_call["arguments"]["checkout_repository"] == "iwashita-nozomu/agent-canon"
    assert calls and calls[0][0] == "publisher"
    assert "checkout_identity" in calls[0][1]
    assert "remote" in calls[0][1]

    config = load_team_config(PROJECT_ROOT / "agents" / "agents_config.json")
    catalog = load_task_catalog(config, PROJECT_ROOT)
    roles = select_roles(
        config,
        [],
        full_team=False,
        catalog=catalog,
        workflow_family_id="issue_worker_publication",
        issue_worker_candidate=_candidate(),
    )
    active_subagents, _ = workflow_spawn_budget(catalog, "issue_worker_publication")
    assert tuple(role.id for role in roles) == ("publisher",)
    assert recommended_initial_subagent_wave(
        roles,
        active_subagents,
        catalog,
        agent_root=PROJECT_ROOT / ".codex" / "agents",
        workflow_family_id="issue_worker_publication",
        issue_worker_candidate=_candidate(),
    ) == ("worker",)


def test_t15_without_explicit_candidate_has_no_initial_publisher() -> None:
    config = load_team_config(PROJECT_ROOT / "agents" / "agents_config.json")
    catalog = load_task_catalog(config, PROJECT_ROOT)
    roles = select_roles(
        config,
        [],
        full_team=False,
        catalog=catalog,
        workflow_family_id="issue_worker_publication",
    )
    active_subagents, _ = workflow_spawn_budget(catalog, "issue_worker_publication")

    assert roles == ()
    assert recommended_initial_subagent_wave(
        roles,
        active_subagents,
        catalog,
        agent_root=PROJECT_ROOT / ".codex" / "agents",
        workflow_family_id="issue_worker_publication",
    ) == ()


def test_explicit_issue_worker_candidate_does_not_change_generic_intake() -> None:
    config = load_team_config(PROJECT_ROOT / "agents" / "agents_config.json")
    catalog = load_task_catalog(config, PROJECT_ROOT)
    roles = select_roles(
        config,
        [],
        full_team=False,
        catalog=catalog,
        workflow_family_id="comprehensive_development",
        issue_worker_candidate=_candidate(),
    )
    active_subagents, _ = workflow_spawn_budget(catalog, "comprehensive_development")

    assert all(role.id != "publisher" for role in roles)
    assert recommended_initial_subagent_wave(
        roles,
        active_subagents,
        catalog,
        agent_root=PROJECT_ROOT / ".codex" / "agents",
        workflow_family_id="comprehensive_development",
        issue_worker_candidate=_candidate(),
    ) == ("requirements_organizer",)


def test_other_repository_candidate_is_no_mutation_handoff() -> None:
    calls: list[str] = []

    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(repository="other/repository"),
        "publish explicit feedback",
        lambda agent_type, prompt: calls.append(agent_type) or "publisher-1",
        workspace_root=PROJECT_ROOT,
        source_root=PROJECT_ROOT,
    )

    assert result.status == "deferred"
    assert result.handoff.reason == "other-repository"
    assert result.tool_call is None
    assert calls == []


def test_same_repository_evidence_gap_still_reaches_publisher_investigation() -> None:
    calls: list[str] = []
    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(owner=""),
        "investigate explicit feedback",
        lambda agent_type, prompt: calls.append(agent_type) or "publisher-1",
        workspace_root=PROJECT_ROOT,
        source_root=PROJECT_ROOT,
    )

    assert result.status == "spawned"
    assert not result.handoff.qualifies
    assert result.handoff.reason == "owner-unresolved"
    assert calls == ["publisher"]


def test_missing_checkout_identity_is_deferred_without_spawn(monkeypatch) -> None:
    monkeypatch.setattr(
        issue_worker_dispatch,
        "resolve_checkout_identity",
        lambda workspace: CheckoutIdentity(
            cwd=str(workspace),
            git_root="unknown",
            branch="detached",
            head="unknown",
            remote="unknown",
        ),
    )
    calls: list[str] = []
    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(),
        "publish explicit feedback",
        lambda agent_type, prompt: calls.append(agent_type) or "publisher-1",
        workspace_root=PROJECT_ROOT,
        source_root=PROJECT_ROOT,
    )

    assert result.status == "deferred"
    assert result.handoff.reason == "checkout-identity-unresolved"
    assert calls == []
