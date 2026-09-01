from __future__ import annotations

from dataclasses import replace
import json

import pytest

from tools.agent.orchestration.direct_luna_dispatch import (
    LUNA_MODEL,
    DirectLunaBlocker,
    build_direct_luna_packet,
    build_reuse_decision,
    build_reuse_survey,
    verify_direct_luna_runtime,
)


def _decision(**overrides):
    values = {
        "asset_path": "tools/agent/orchestration/direct_luna_dispatch.py",
        "asset_origin": "current",
        "capability": "build and validate the existing handoff packet",
        "disposition": "extend",
        "reason": "the existing serializer is the single write-handoff owner",
        "test_paths": ("tests/tools/test_direct_luna_dispatch.py",),
    }
    values.update(overrides)
    return build_reuse_decision(**values)


def _survey(**overrides):
    values = {
        "scope": "current_and_history",
        "universe_status": "complete",
        "surface_admission": "existing_asset",
        "decisions": (_decision(),),
        "current_refs": (
            "current:direct_luna_dispatch.py and its focused packet tests",
        ),
        "history_refs": (
            "history:git log and deleted-path search for the handoff owner",
        ),
        "prior_work_refs": ("prior_work:Issue #1033 and PR #1035",),
        "design_refs": (
            "design:agents/skills/direct-luna-communication.md",
        ),
        "bounded_omissions": (),
        "reason": "establish one current+historical universe before slicing",
    }
    values.update(overrides)
    return build_reuse_survey(**values)


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
        "context": "Issue #1033 candidate epoch 1",
        "request_clause_ids": ("REQ-1033-1",),
    }
    values.update(overrides)
    return build_direct_luna_packet(**values)


def _workspace_packet(**overrides):
    values = {
        "logical_role_id": "implementer",
        "skill_ids": ("code-cleanup", "refactor-loop"),
        "reasoning_effort": "xhigh",
        "authority": "workspace-write",
        "allowed_paths": ("tools/agent/orchestration", "tests/tools"),
        "do_not_read": ("reports/private",),
        "expected_output": "bounded implementation and focused regressions",
        "validation_route": "pytest -q tests/tools/test_direct_luna_dispatch.py",
        "objective": "implement Issue #1033 reuse admission",
        "context": "Issue #1033 current-main packet",
        "reuse_survey": _survey(),
        "request_clause_ids": ("REQ-1033-1", "REQ-1033-2"),
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
    assert serialized["reuse_survey"] is None


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
        _workspace_packet(allowed_paths=())
    with pytest.raises(ValueError, match="repository-relative"):
        _workspace_packet(allowed_paths=("../outside",))


def test_workspace_write_rejects_missing_reuse_survey() -> None:
    with pytest.raises(ValueError, match="requires a structured reuse_survey"):
        _workspace_packet(reuse_survey=None)


def test_bounded_non_split_write_requires_explicit_not_applicable_reason() -> None:
    not_applicable = build_reuse_survey(
        scope="not_applicable",
        universe_status="not_applicable",
        surface_admission="not_applicable",
        reason="bounded typo-only edit with no asset choice or worker split",
    )
    packet = _workspace_packet(reuse_survey=not_applicable)
    assert packet.reuse_survey == not_applicable

    with pytest.raises(ValueError, match="reuse_survey reason must be non-empty"):
        build_reuse_survey(
            scope="not_applicable",
            universe_status="not_applicable",
            surface_admission="not_applicable",
            reason=" ",
        )


def test_all_supported_dispositions_are_serialized_with_test_evidence() -> None:
    dispositions = (
        "reuse",
        "extend",
        "restore",
        "consolidate",
        "replace",
        "delete",
        "reject",
    )
    decisions = tuple(
        _decision(
            asset_path=f"tools/agent/orchestration/candidate_{index}.py",
            asset_origin="history" if disposition == "restore" else "current",
            disposition=disposition,
            capability=f"candidate capability {index}",
            reason=f"evidence-backed {disposition} decision",
            test_paths=(f"tests/tools/test_candidate_{index}.py",),
        )
        for index, disposition in enumerate(dispositions)
    )
    survey = _survey(decisions=decisions)
    serialized = json.loads(_workspace_packet(reuse_survey=survey).to_json())
    serialized_decisions = serialized["reuse_survey"]["decisions"]

    assert [decision["disposition"] for decision in serialized_decisions] == list(
        dispositions
    )
    assert all(decision["test_paths"] for decision in serialized_decisions)


def test_incomplete_decision_is_rejected() -> None:
    with pytest.raises(ValueError, match="reason must be non-empty"):
        _decision(reason="")
    with pytest.raises(ValueError, match="test_paths must contain at least one entry"):
        _decision(test_paths=())


def test_candidate_asset_paths_must_be_unique() -> None:
    duplicate = _decision(disposition="reuse")
    with pytest.raises(ValueError, match="must not duplicate asset_path"):
        _survey(decisions=(_decision(), duplicate))


def test_current_and_history_scope_requires_each_evidence_dimension_or_omission() -> None:
    with pytest.raises(ValueError, match="requires history_refs"):
        _survey(history_refs=())

    bounded = _survey(
        universe_status="bounded_omission",
        history_refs=(),
        bounded_omissions=(
            "history: repository has no deleted or predecessor path for this owner",
        ),
    )
    assert bounded.universe_status == "bounded_omission"


def test_new_surface_requires_evidence_backed_rejection_of_every_candidate() -> None:
    with pytest.raises(ValueError, match="every candidate disposition to be reject"):
        _survey(surface_admission="new_surface")

    rejected = _decision(
        asset_path="tools/legacy/candidate.py",
        disposition="reject",
        reason="the candidate owns a different lifecycle and cannot satisfy this contract",
        test_paths=("tests/legacy/test_candidate.py",),
    )
    survey = _survey(
        surface_admission="new_surface",
        decisions=(rejected,),
    )
    packet = _workspace_packet(
        allowed_paths=("tools/new_surface", "tests/new_surface"),
        reuse_survey=survey,
    )
    assert packet.reuse_survey == survey


def test_rejected_foreign_asset_does_not_expand_write_scope() -> None:
    selected = _decision()
    foreign = _decision(
        asset_path="vendor/foreign_helper.py",
        disposition="reject",
        capability="unrelated vendor helper",
        reason="different repository responsibility and lifecycle",
        test_paths=("vendor/tests/test_foreign_helper.py",),
    )
    packet = _workspace_packet(reuse_survey=_survey(decisions=(selected, foreign)))

    assert packet.allowed_paths == (
        "tools/agent/orchestration",
        "tests/tools",
    )
    assert packet.reuse_survey is not None
    assert packet.reuse_survey.decisions[-1].asset_path == "vendor/foreign_helper.py"


def test_write_disposition_must_remain_inside_parent_scope() -> None:
    outside = _decision(asset_path="tools/other_owner.py")
    with pytest.raises(ValueError, match="must be covered by allowed_paths"):
        _workspace_packet(reuse_survey=_survey(decisions=(outside,)))


def test_reuse_evidence_must_not_cross_do_not_read() -> None:
    forbidden = _decision(
        asset_path="reports/private/hidden.py",
        disposition="reject",
        test_paths=("tests/tools/test_hidden.py",),
    )
    with pytest.raises(ValueError, match="overlaps do_not_read"):
        _workspace_packet(
            reuse_survey=_survey(decisions=(_decision(), forbidden))
        )


def test_worker_and_reviewer_prompts_consume_the_exact_same_reuse_survey() -> None:
    survey = _survey()
    worker = _workspace_packet(reuse_survey=survey)
    reviewer = _packet(reuse_survey=survey)

    worker_payload = json.loads(worker.to_json())
    reviewer_payload = json.loads(reviewer.to_json())
    assert worker_payload["reuse_survey"] == reviewer_payload["reuse_survey"]
    assert worker_payload["reuse_survey"]["decisions"][0] == {
        "asset_origin": "current",
        "asset_path": "tools/agent/orchestration/direct_luna_dispatch.py",
        "capability": "build and validate the existing handoff packet",
        "disposition": "extend",
        "reason": "the existing serializer is the single write-handoff owner",
        "test_paths": ["tests/tools/test_direct_luna_dispatch.py"],
    }


def test_reuse_v0_code_split_history_contract_replay() -> None:
    current = _decision(
        asset_path="tools/cleanup/monolith.py",
        disposition="consolidate",
        capability="current owner for the behavior being split",
        reason="keep one responsibility owner instead of duplicating helpers",
        test_paths=("tests/cleanup/test_monolith.py",),
    )
    historical = _decision(
        asset_path="tools/cleanup/deleted_helper.py",
        asset_origin="history",
        disposition="restore",
        capability="previously validated helper for the extracted behavior",
        reason="history proves the predecessor should be restored, not reimplemented",
        test_paths=("tests/cleanup/test_deleted_helper.py",),
    )
    survey = _survey(
        decisions=(current, historical),
        current_refs=("current:module/helper/type/test inventory",),
        history_refs=("history:git log -S plus deleted-path scan",),
        prior_work_refs=("prior_work:PR #700 and Issue #699",),
        design_refs=("design:documents/design/cleanup-owner.md",),
    )
    worker = _workspace_packet(
        allowed_paths=("tools/cleanup", "tests/cleanup"),
        reuse_survey=survey,
    )
    reviewer = _packet(
        allowed_paths=("tools/cleanup", "tests/cleanup"),
        reuse_survey=survey,
    )

    worker_survey = json.loads(worker.to_json())["reuse_survey"]
    reviewer_survey = json.loads(reviewer.to_json())["reuse_survey"]
    assert worker_survey == reviewer_survey
    assert worker_survey["scope"] == "current_and_history"
    assert [item["asset_origin"] for item in worker_survey["decisions"]] == [
        "current",
        "history",
    ]
    assert [item["disposition"] for item in worker_survey["decisions"]] == [
        "consolidate",
        "restore",
    ]
    assert all(item["test_paths"] for item in worker_survey["decisions"])


def test_direct_dataclass_mutation_cannot_bypass_admission_validation() -> None:
    valid = _survey()
    invalid = replace(valid, history_refs=())
    with pytest.raises(ValueError, match="requires history_refs"):
        _workspace_packet(reuse_survey=invalid)


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
