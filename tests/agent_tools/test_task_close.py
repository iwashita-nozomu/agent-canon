# @dependency-start
# contract test
# responsibility Tests exact postorder close tokens and lifecycle reservation release.
# upstream implementation ../../tools/agent_tools/task_close.py consumes the provider ledger
# upstream implementation ../../tools/agent_tools/capacity_handshake.py owns lifecycle state
# @dependency-end

"""Task-close tests for AgentCanon parent sync gating and lifecycle closeout."""

from __future__ import annotations

from tools.agent_tools import capacity_handshake
from tools.agent_tools.task_close import validate_capacity_lifecycle_closeout


def _readback_record(work_id: str, parent: str) -> capacity_handshake.DescendantLifecycleRecord:
    return capacity_handshake.DescendantLifecycleRecord(
        work_id=work_id,
        parent_work_id=parent,
        status=capacity_handshake.LifecycleStatus.READBACK_VERIFIED,
        durable_result_evidence_ref=f"result://{work_id}",
        durable_handback=True,
        descendants_closed=True,
        close_readback=True,
        transition_generation=6,
    )


def _close_call(work_id: str) -> dict[str, object]:
    return {
        "agent_id": work_id,
        "tool_call_token": {
            "tool_id": "close_agent",
            "arguments": {"terminal_agent_id": work_id},
        },
    }


def _ledger() -> capacity_handshake.CapacityLedger:
    child = _readback_record("child", "parent-agent")
    parent = _readback_record("parent-agent", "root")
    return capacity_handshake.CapacityLedger(
        topology=capacity_handshake.DescendantTopologyReadback(
            parent_work_id="root",
            descendants=(parent, child),
        ),
        open_records={"parent-agent": parent, "child": child},
        reservations={
            "parent-agent": capacity_handshake.ParentChildEdge("root", "parent-agent"),
            "child": capacity_handshake.ParentChildEdge("parent-agent", "child"),
        },
    )


def test_closeout_requires_exactly_one_schema_valid_postorder_token() -> None:
    """Closeout requires valid single postorder close token chain."""
    ledger = _ledger()
    ready, failures = validate_capacity_lifecycle_closeout(
        ledger,
        (_close_call("child"), _close_call("parent-agent")),
    )
    assert ready
    assert failures == ()
    assert ledger.reservations == {}
    assert set(ledger.open_records) == {"parent-agent", "child"}
    assert all(
        record.status == capacity_handshake.LifecycleStatus.RESERVATION_RELEASED
        for record in ledger.open_records.values()
    )


def test_closeout_rejects_duplicate_reverse_and_metadata_tokens() -> None:
    """Closeout rejects duplicate close tokens and metadata-enriched tokens."""
    reverse = validate_capacity_lifecycle_closeout(
        _ledger(),
        (_close_call("parent-agent"), _close_call("child")),
    )
    assert not reverse[0]
    assert "close_agent_tool_calls_not_postorder" in reverse[1]

    duplicate = validate_capacity_lifecycle_closeout(
        _ledger(),
        (_close_call("child"), _close_call("child"), _close_call("parent-agent")),
    )
    assert not duplicate[0]
    assert "child:duplicate_close_agent_tool_call" in duplicate[1]

    metadata_call = _close_call("child")
    token = metadata_call["tool_call_token"]
    assert isinstance(token, dict)
    token["metadata"] = {"reason": "arbitrary"}
    invalid = validate_capacity_lifecycle_closeout(
        _ledger(),
        (metadata_call, _close_call("parent-agent")),
    )
    assert not invalid[0]
    assert "child:close_agent_token_fields_invalid" in invalid[1]


def test_closeout_rejects_open_and_unknown_descendants_without_reclaim() -> None:
    """Closeout must reject open and unknown descendants with reclaim leaks."""
    record = capacity_handshake.DescendantLifecycleRecord(
        work_id="open",
        parent_work_id="root",
        status=capacity_handshake.LifecycleStatus.ACTIVE,
    )
    ledger = capacity_handshake.CapacityLedger(
        topology=capacity_handshake.DescendantTopologyReadback("root", (record,)),
        open_records={"open": record, "unknown": record},
        reservations={"open": capacity_handshake.ParentChildEdge("root", "open")},
    )
    ready, failures = validate_capacity_lifecycle_closeout(ledger)
    assert not ready
    assert "open:open_descendant" in failures
    assert "unknown:unknown_descendant" in failures
    assert "open" in ledger.open_records
    assert "open" in ledger.reservations
