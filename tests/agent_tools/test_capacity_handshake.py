# @dependency-start
# contract test
# responsibility Tests typed capacity derivation, successful-spawn reservations, queue retention, and lifecycle CAS.
# upstream implementation ../../agents/capacity_policy.toml declares capacity policy
# upstream implementation ../../tools/agent_tools/capacity_handshake.py implements the provider contract
# downstream implementation ../../tools/agent_tools/agent_team.py consumes spawn reservation behavior
# @dependency-end

from __future__ import annotations

from pathlib import Path

import pytest

from tools.agent_tools.capacity_handshake import (
    CapacityLedger,
    DeclaredFamilyCapacity,
    DeclaredTeamTopologyDerivation,
    DescendantTopologyReadback,
    LifecycleStatus,
    ReadyWorkItem,
    TopologyCapacityNode,
    TopologyCapacityWitness,
    load_startup_contract,
    main,
    make_session_snapshot,
    materialize_closeout_packet,
    record_lifecycle_transition,
    record_successful_spawn,
    request_slot,
)


def _derivation() -> DeclaredTeamTopologyDerivation:
    return DeclaredTeamTopologyDerivation(
        1,
        "agents/task_catalog.yaml",
        "agents/task_catalog.yaml",
        "reviewer",
        "producer",
        "final",
        (),
        (),
        (
            DeclaredFamilyCapacity(
                "research",
                tuple(f"direct-{index}" for index in range(20)),
                tuple(f"nested-{index}" for index in range(6)),
                ("final",),
                20,
                6,
                1,
            ),
        ),
    )


def _witness() -> TopologyCapacityWitness:
    derivation = _derivation()
    parent = TopologyCapacityNode("parent", "workflow", (), None, 1, 0, (), ())
    children = tuple(
        TopologyCapacityNode(f"child-{index}", "descendant", ("parent",), "parent", 1, 1, (f"p{index}",), ())
        for index in range(6)
    )
    return TopologyCapacityWitness(
        declared_team_topology_sha256="a" * 64,
        node_records=(parent, *children),
        legal_frontier_ids=tuple(node.node_id for node in (parent, *children)),
        peak_frontier_node_ids=tuple(f"direct-{index}" for index in range(20)),
        peak_write_frontier_node_ids=tuple(node.node_id for node in children),
        requested_total_capacity=26,
        workflow_dag_peak_demand=20,
        nested_reservation_count=6,
        workflow_dag_budget=26,
        write_scope_cap=6,
        derivation=derivation,
    )


def _contract(tmp_path: Path, configured: int = 26):
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(f"[agents]\nmax_threads = {configured}\n", encoding="utf-8")
    return load_startup_contract(_derivation(), _witness(), str(config))


def test_requested_capacity_is_direct_frontier_plus_nested_once() -> None:
    derivation = _derivation()
    assert derivation.peak_family.direct_frontier_count == 20
    assert derivation.peak_family.nested_reservation_count == 6
    assert derivation.requested_max_threads() == 26


def test_snapshot_separates_requested_effective_available_and_write(tmp_path: Path) -> None:
    snapshot = make_session_snapshot(
        _contract(tmp_path, 22),
        platform_advertised_effective_cap=21,
        currently_available_runtime_slots=9,
        workflow_dag_demand=20,
        nested_capacity_reservation=6,
        write_scope_cap=4,
        requested_write_capacity=4,
        currently_available_write_slots=2,
    )
    assert snapshot.requested_total_capacity == 26
    assert snapshot.effective_total_capacity == 21
    assert snapshot.available_total_capacity == 9
    assert snapshot.effective_write_capacity == 4
    assert snapshot.available_write_capacity == 2
    assert snapshot.reserved_total_capacity == 0
    assert {item.input_id for item in snapshot.input_provenance} >= {
        "requested_total_capacity",
        "configured_total_capacity",
        "platform_effective_total_capacity",
        "current_available_total_capacity",
        "workflow_dag_direct_demand",
        "nested_reservation_count",
        "write_scope_cap",
    }
    assert all(item.readback_value == item.value for item in snapshot.input_provenance)


def test_nested_reservation_cannot_be_counted_twice(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="counted_once"):
        make_session_snapshot(
            _contract(tmp_path),
            workflow_dag_demand=26,
            nested_capacity_reservation=6,
        )


def test_reservation_is_created_only_after_successful_spawn(tmp_path: Path) -> None:
    snapshot = make_session_snapshot(_contract(tmp_path), workflow_dag_demand=20, nested_capacity_reservation=6, write_scope_cap=2)
    ledger = CapacityLedger(DescendantTopologyReadback("parent"))
    item = ReadyWorkItem("child", "b" * 64, "spark_implementation_low", required_write_slots=1)
    assert request_slot(snapshot, ledger, item).status == "ready"
    assert ledger.open_records == {}
    assert record_successful_spawn(snapshot, ledger, item, spawn_succeeded=False).status == "queued"
    assert ledger.open_records == {}
    ledger.ready_queue.clear()
    assert record_successful_spawn(snapshot, ledger, item, spawn_succeeded=True).status == "granted"
    assert set(ledger.open_records) == {"child"}
    assert set(ledger.reservations) == {"child"}


def _advance_to_readback(ledger: CapacityLedger, work_id: str) -> None:
    sequence = (
        (LifecycleStatus.SPAWNED, LifecycleStatus.ACTIVE, None),
        (LifecycleStatus.ACTIVE, LifecycleStatus.DURABLE_RESULT_EVIDENCE, "result://durable"),
        (LifecycleStatus.DURABLE_RESULT_EVIDENCE, LifecycleStatus.HANDED_BACK, "handback://ok"),
        (LifecycleStatus.HANDED_BACK, LifecycleStatus.DESCENDANTS_CLOSURE_VERIFIED, "descendants://closed"),
        (LifecycleStatus.DESCENDANTS_CLOSURE_VERIFIED, LifecycleStatus.CLOSED, "close://accepted"),
        (LifecycleStatus.CLOSED, LifecycleStatus.READBACK_VERIFIED, "readback://ok"),
    )
    for generation, (old, new, evidence) in enumerate(sequence):
        record_lifecycle_transition(
            ledger,
            work_id,
            new,
            expected_status=old,
            expected_generation=generation,
            evidence_ref=evidence,
        )


def test_lifecycle_is_closed_compare_and_swap_and_release_retains_record(tmp_path: Path) -> None:
    snapshot = make_session_snapshot(_contract(tmp_path), workflow_dag_demand=20, nested_capacity_reservation=6)
    ledger = CapacityLedger(DescendantTopologyReadback("parent"))
    item = ReadyWorkItem("child", "c" * 64, "spark_implementation_low")
    record_successful_spawn(snapshot, ledger, item, spawn_succeeded=True)
    with pytest.raises(ValueError, match="out_of_order"):
        record_lifecycle_transition(
            ledger,
            "child",
            LifecycleStatus.CLOSED,
            expected_status=LifecycleStatus.SPAWNED,
            expected_generation=0,
        )
    _advance_to_readback(ledger, "child")
    token = {"tool_id": "close_agent", "arguments": {"terminal_agent_id": "child"}}
    packet = materialize_closeout_packet("parent", ledger, (ledger.topology,), {"child": token})
    assert packet.status == "closed"
    assert packet.close_agent_calls[0].close_agent_call_token == token
    assert ledger.open_records["child"].status == LifecycleStatus.RESERVATION_RELEASED
    assert "child" not in ledger.reservations


def test_closeout_never_reclaims_open_record(tmp_path: Path) -> None:
    snapshot = make_session_snapshot(_contract(tmp_path), workflow_dag_demand=20, nested_capacity_reservation=6)
    ledger = CapacityLedger(DescendantTopologyReadback("parent"))
    item = ReadyWorkItem("child", "d" * 64, "spark_implementation_low")
    record_successful_spawn(snapshot, ledger, item, spawn_succeeded=True)
    packet = materialize_closeout_packet("parent", ledger, (ledger.topology,), {})
    assert packet.status == "failed"
    assert "child" in ledger.open_records
    assert "child" in ledger.reservations


def _projection_root(tmp_path: Path, configured: int) -> Path:
    (tmp_path / "agents").mkdir(parents=True)
    (tmp_path / ".codex").mkdir(parents=True)
    (tmp_path / "agents" / "capacity_policy.toml").write_text(
        '''policy_id = "topology_derived_v1"
[topology_derivation]
direct_frontier_count = 20
nested_reservation_count = 6
nested_reservation_accounting = "count_once"
[runtime_config_change_policy]
target_value_derivation = "declared_team_peak_plus_nested_reservations_v1"
target_value = 26
required_predicates = ["generated_value_matches_topology_witness"]
[generated_manifest_policy]
numeric_family_default = false
''',
        encoding="utf-8",
    )
    (tmp_path / ".codex" / "config.toml").write_text(f"[agents]\nmax_threads = {configured}\n", encoding="utf-8")
    return tmp_path


def test_capacity_config_generator_and_readback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _projection_root(tmp_path, 18)
    assert main(("--root", str(root), "--write-config-projection")) == 0
    assert capsys.readouterr().out == "CAPACITY_CONFIG_PROJECTION=written\n"
    assert main(("--root", str(root), "--check-config-projection", "--expected-max-threads", "26")) == 0
    assert capsys.readouterr().out == "CAPACITY_CONFIG_PROJECTION=pass\n"
