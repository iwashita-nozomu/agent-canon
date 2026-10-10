from __future__ import annotations

import json

import pytest

from tools.agent.orchestration.direct_luna_dispatch import (
    LUNA_MODEL,
    build_direct_luna_packet,
)


def _packet(**overrides):
    values = {
        "logical_role_id": "change_reviewer",
        "skill_ids": ("change-review", "subagent-bootstrap"),
        "reasoning_effort": "high",
        "authority": "read-only",
        "allowed_paths": ("tools/agent/orchestration", "tests/tools"),
        "do_not_read": ("reports/private",),
        "expected_output": "stable blocker list and evidence",
        "validation_route": "focused static tests selected by the parent",
        "objective": "review the bounded implementation diff",
        "context": "Issue #1232: reuse the existing dispatch owner and its tests; remove only survey grammar.",
        "request_clause_ids": ("REQ-1232-1",),
    }
    values.update(overrides)
    return build_direct_luna_packet(**values)


def test_packet_keeps_role_skill_profile_and_authority_independent() -> None:
    packet = _packet()
    assert packet.logical_role_id == "change_reviewer"
    assert packet.skill_ids == ("change-review", "subagent-bootstrap")
    assert packet.model == LUNA_MODEL
    assert packet.authority == "read-only"
    assert packet.fork_turns == "none"
    serialized = json.loads(packet.to_json())
    assert serialized["model"] == "gpt-6-luna"
    assert serialized["reasoning_effort"] == "high"
    assert "effective_model" not in serialized
    assert "effective_reasoning_effort" not in serialized
    assert "reuse_survey" not in serialized


def test_logical_role_changes_do_not_create_a_new_physical_profile() -> None:
    reviewer = _packet(logical_role_id="reviewer", skill_ids=("change-review",))
    researcher = _packet(
        logical_role_id="researcher",
        skill_ids=("research-workflow",),
        expected_output="claim/evidence research notes",
    )
    assert reviewer.model == researcher.model == LUNA_MODEL
    assert reviewer.logical_role_id != researcher.logical_role_id
    assert reviewer.skill_ids != researcher.skill_ids


@pytest.mark.parametrize(
    "context",
    (
        "Use the existing serializer in tools/agent/orchestration/direct_luna_dispatch.py. Issue #1232 explains the redundant admission; preserve path and authority checks.",
        "Follow the reviewed design and Issue #1232. This spelling-only edit does not choose a new asset or require a new test.",
        "The existing owner covers serialization; extend it for the missing case described in the Issue. The rejected vendor implementation has a different lifecycle.",
    ),
)
def test_write_accepts_existing_evidence_without_reuse_grammar(context: str) -> None:
    worker = _packet(
        authority="workspace-write", logical_role_id="implementer", context=context
    )
    reviewer = _packet(context=context)
    worker_payload = json.loads(worker.to_json())
    reviewer_payload = json.loads(reviewer.to_json())
    assert worker_payload["context"] == reviewer_payload["context"] == context
    assert worker_payload["allowed_paths"] == [
        "tools/agent/orchestration",
        "tests/tools",
    ]
    assert worker_payload["do_not_read"] == ["reports/private"]
    assert worker_payload["authority"] == "workspace-write"
    assert reviewer_payload["authority"] == "read-only"
    assert "reuse_survey" not in worker_payload


def test_missing_handoff_context_is_not_replaced_with_synthetic_evidence() -> None:
    with pytest.raises(ValueError, match="context must be non-empty"):
        _packet(authority="workspace-write", context=" ")


@pytest.mark.parametrize("paths", ((), ("../outside",), ("/outside",), (".",)))
def test_workspace_write_requires_bounded_allowed_paths(paths) -> None:
    with pytest.raises(ValueError):
        _packet(authority="workspace-write", allowed_paths=paths)


@pytest.mark.parametrize(
    ("allowed_paths", "do_not_read"),
    (
        (("tools/agent/orchestration",), ("tools/agent/orchestration/private",)),
        (("tools/agent/orchestration/private",), ("tools/agent/orchestration",)),
        (("tools/agent/orchestration",), ("tools/agent/orchestration",)),
    ),
)
def test_evidence_cannot_override_forbidden_paths(allowed_paths, do_not_read) -> None:
    with pytest.raises(ValueError, match="allowed_paths and do_not_read overlap"):
        _packet(
            authority="workspace-write",
            allowed_paths=allowed_paths,
            do_not_read=do_not_read,
            context="The referenced asset is useful; this text does not grant access.",
        )


def test_context_does_not_grant_write_access_or_add_paths() -> None:
    packet = _packet(
        context="A candidate outside scope was considered. Write access is not granted by this context."
    )
    assert packet.authority == "read-only"
    assert packet.allowed_paths == ("tools/agent/orchestration", "tests/tools")
    assert packet.do_not_read == ("reports/private",)


@pytest.mark.parametrize("authority", ("full-access", "", "write"))
def test_unsupported_authority_is_rejected(authority: str) -> None:
    with pytest.raises(ValueError, match="unsupported authority"):
        _packet(authority=authority)
