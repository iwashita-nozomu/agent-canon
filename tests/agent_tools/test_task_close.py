# @dependency-start
# contract test
# responsibility Tests typed lifecycle closeout and reservation release.
# upstream implementation ../../tools/agent_tools/task_close.py consumes the provider ledger
# downstream implementation ../../tools/agent_tools/capacity_handshake.py owns lifecycle state
# @dependency-end

from __future__ import annotations

from tools.agent_tools import capacity_handshake
from tools.agent_tools.task_close import validate_capacity_lifecycle_closeout


def _closed_record(work_id: str) -> capacity_handshake.DescendantLifecycleRecord:
    return capacity_handshake.DescendantLifecycleRecord(
        work_id=work_id,
        parent_work_id="parent",
        status=capacity_handshake.LifecycleStatus.CLOSED,
        durable_handback=True,
        descendants_closed=True,
        close_readback=True,
    )


def _close_call(work_id: str) -> dict[str, object]:
    return {
        "agent_id": work_id,
        "tool_call_token": {
            "schema_id": "tool_call_token_v1",
            "skill_id": "subagent-bootstrap",
            "tool_id": "close_agent",
            "arguments": {"terminal_agent_id": work_id},
            "argument_schema_id": "close_agent_args_v1",
            "failure_schema_id": "close_agent_failure_v1",
            "target": "terminal_agent_id",
        },
    }


def test_closeout_releases_reservations() -> None:
    record = _closed_record("child")
    ledger = capacity_handshake.CapacityLedger(
        topology=capacity_handshake.DescendantTopologyReadback(
            parent_work_id="parent", descendants=(record,)
        ),
        open_records={"child": record},
        reservations={
            "child": capacity_handshake.ParentChildEdge(
                parent_work_id="parent", child_work_id="child"
            )
        },
    )
    ready, failures = validate_capacity_lifecycle_closeout(
        ledger, (_close_call("child"),)
    )
    assert ready
    assert failures == ()
    assert ledger.open_records == {}
    assert ledger.reservations == {}


def test_closeout_rejects_open_and_unknown_descendants() -> None:
    open_record = capacity_handshake.DescendantLifecycleRecord(
        work_id="open",
        parent_work_id="parent",
        status=capacity_handshake.LifecycleStatus.ACTIVE,
    )
    ledger = capacity_handshake.CapacityLedger(
        topology=capacity_handshake.DescendantTopologyReadback(
            parent_work_id="parent", descendants=(open_record,)
        ),
        open_records={"open": open_record, "unknown": open_record},
    )
    ready, failures = validate_capacity_lifecycle_closeout(ledger)
    assert not ready
    assert "open:open_descendant" in failures
    assert "unknown:unknown_descendant" in failures
