from __future__ import annotations

import json

import pytest

from tools.agent_tools.direct_luna_dispatch import (
    LUNA_MODEL,
    DirectLunaBlocker,
    build_direct_luna_packet,
    verify_direct_luna_runtime,
)


def _packet(**overrides):
    values = {
        "logical_role_id": "change_reviewer",
        "skill_ids": ("change-review", "subagent-bootstrap"),
        "reasoning_effort": "high",
        "authority": "read-only",
        "allowed_paths": ("tools/agent_tools",),
        "do_not_read": ("reports/private",),
        "expected_output": "stable blocker list and evidence",
        "validation_route": "focused static tests selected by the parent",
        "objective": "review the bounded implementation diff",
        "context": "Issue #775 candidate epoch 1",
        "request_clause_ids": ("REQ-775-1",),
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
    assert serialized["model"] == "gpt-5.6-luna"


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


def test_workspace_write_requires_bounded_allowed_paths() -> None:
    with pytest.raises(ValueError, match="requires at least one allowed path"):
        _packet(authority="workspace-write", allowed_paths=())
    with pytest.raises(ValueError, match="repository-relative"):
        _packet(authority="workspace-write", allowed_paths=("../outside",))


def test_effective_runtime_readback_is_required() -> None:
    packet = _packet()
    with pytest.raises(DirectLunaBlocker) as captured:
        verify_direct_luna_runtime(
            packet,
            override_available=True,
            effective_model=None,
            effective_reasoning_effort=None,
        )
    assert captured.value.code == "direct_luna_unverified"


def test_model_mismatch_is_not_silently_fallbacked() -> None:
    packet = _packet()
    with pytest.raises(DirectLunaBlocker) as captured:
        verify_direct_luna_runtime(
            packet,
            override_available=True,
            effective_model="gpt-5.6-sol",
            effective_reasoning_effort="high",
        )
    assert captured.value.code == "direct_luna_unverified"


def test_unavailable_override_is_a_distinct_blocker() -> None:
    packet = _packet()
    with pytest.raises(DirectLunaBlocker) as captured:
        verify_direct_luna_runtime(
            packet,
            override_available=False,
            effective_model=None,
            effective_reasoning_effort=None,
        )
    assert captured.value.code == "direct_luna_unavailable"


def test_matching_effective_runtime_returns_evidence() -> None:
    packet = _packet(reasoning_effort="xhigh")
    evidence = verify_direct_luna_runtime(
        packet,
        override_available=True,
        effective_model=LUNA_MODEL,
        effective_reasoning_effort="xhigh",
    )
    assert evidence.requested_model == evidence.effective_model == LUNA_MODEL
    assert evidence.requested_reasoning_effort == evidence.effective_reasoning_effort == "xhigh"
