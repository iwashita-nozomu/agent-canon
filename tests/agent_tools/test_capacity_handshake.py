from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.agent_tools.capacity_handshake import (
    DeclaredFamilyCapacity,
    DeclaredTeamTopologyDerivation,
    LifecycleStatus,
    ReadyWorkItem,
    TopologyCapacityNode,
    TopologyCapacityWitness,
    CapacityLedger,
    DescendantLifecycleRecord,
    DescendantTopologyReadback,
    ThreadSaturationEvent,
    ModelCapacityEvent,
    load_startup_contract,
    main,
    make_session_snapshot,
    materialize_closeout_packet,
    queue_ready_work,
    queued_reclaim,
    record_lifecycle_transition,
    request_slot,
)


def _sample_derivation() -> DeclaredTeamTopologyDerivation:
    return DeclaredTeamTopologyDerivation(
        derivation_version=1,
        topology_source="agents/task_catalog.yaml::role_topology_defaults",
        workflow_role_source="agents/task_catalog.yaml::workflow_families[].roles",
        direct_frontier_stage_class="reviewer",
        nested_owner_stage_class="producer",
        final_stage_class="final",
        excluded_nested_role_ids=("skill_evaluator",),
        isolated_direct_role_ids=("skill_evaluator",),
        family_records=(
            DeclaredFamilyCapacity(
                workflow_family_id="research_driven_change",
                direct_frontier_role_ids=tuple("f" for _ in range(20)),
                nested_owner_role_ids=tuple("r" for _ in range(6)),
                final_frontier_role_ids=tuple("x" for _ in range(3)),
                direct_frontier_count=20,
                nested_reservation_count=6,
                final_frontier_count=3,
            ),
        ),
    )


def _sample_witness() -> TopologyCapacityWitness:
    derivation = _sample_derivation()
    return TopologyCapacityWitness(
        target_state_contract_sha256="",
        declared_team_topology_ref="agents/task_catalog.yaml",
        declared_team_topology_sha256="sha",
        node_records=(
            TopologyCapacityNode(
                node_id="parent",
                node_kind="parent",
                predecessor_ids=(),
                descendant_parent_id=None,
                total_slot_weight=1,
                write_slot_weight=0,
                allowed_write_paths=("agents.task",),
                exclusion_ids=(),
            ),
            TopologyCapacityNode(
                node_id="child",
                node_kind="descendant",
                predecessor_ids=("parent",),
                descendant_parent_id="parent",
                total_slot_weight=1,
                write_slot_weight=0,
                allowed_write_paths=("agents.child",),
                exclusion_ids=(),
            ),
        ),
        legal_frontier_ids=("parent", "child"),
        peak_frontier_node_ids=("parent",),
        peak_write_frontier_node_ids=(),
        requested_total_capacity=26,
        workflow_dag_peak_demand=20,
        nested_reservation_count=6,
        workflow_dag_budget=20,
        write_scope_cap=2,
        status="approved",
        derivation=derivation,
    )


def _write_config(path: Path, value: int) -> str:
    cfg = path / ".codex"
    cfg.mkdir(parents=True, exist_ok=True)
    file = cfg / "config.toml"
    file.write_text(f"[agents]\nmax_threads = {value}\n", encoding="utf-8")
    return str(file)


def _write_capacity_cli_policy(path: Path, value: int = 26, raw: str | None = None) -> None:
    policy_dir = path / "agents"
    policy_dir.mkdir(parents=True, exist_ok=True)
    if raw is None:
        raw = f'''policy_version = 1
policy_id = "topology_derived_v1"

[topology_derivation]
total_slot_derivation = "max_legal_concurrent_open_frontier"

[runtime_config_change_policy]
target_value_derivation = "declared_team_peak_plus_nested_reservations"
target_value = {value}
required_predicates = ["generated_value_matches_topology_witness"]

[generated_manifest_policy]
numeric_family_default = false
'''
    (policy_dir / "capacity_policy.toml").write_text(raw, encoding="utf-8")


@pytest.fixture
def capacity_projection_root_26(tmp_path: Path) -> Path:
    _write_capacity_cli_policy(tmp_path, 26)
    _write_config(tmp_path, 26)
    return tmp_path


def test_requested_capacity_is_derived_from_topology():
    derivation = _sample_derivation()
    assert derivation.requested_max_threads() == 26


def test_restart_required_evidence_on_unreadable_config(tmp_path):
    witness = _sample_witness()
    with pytest.raises(RuntimeError):
        load_startup_contract(_sample_derivation(), witness, config_path=str(tmp_path / "missing" / "config.toml"))


def test_requested_and_configured_inputs_remain_distinct_and_bootstrap_contract_uses_topology_value(tmp_path):
    witness = _sample_witness()
    cfg = _write_config(tmp_path, 24)
    contract = load_startup_contract(_sample_derivation(), witness, config_path=cfg)
    assert contract.input_evidence.requested_capacity_loader.requested_total_capacity == 26
    assert contract.input_evidence.max_threads_loader.configured_max_threads == 24

    snapshot = make_session_snapshot(contract)
    assert snapshot.effective_total_capacity == 26
    assert snapshot.configured_max_threads == 24


def test_thread_and_model_capacity_events_are_distinct(tmp_path):
    cfg = _write_config(tmp_path, 24)
    contract = load_startup_contract(_sample_derivation(), _sample_witness(), config_path=cfg)
    snapshot = make_session_snapshot(contract, currently_available_runtime_slots=1, write_scope_cap=0)
    ledger = CapacityLedger(topology=DescendantTopologyReadback(parent_work_id="root"))

    thread_result = request_slot(
        snapshot,
        ledger,
        ReadyWorkItem(work_id="w-thread", packet_sha256="sha1", profile_id="agent", required_slots=2),
    )
    assert thread_result.status == "queued"
    assert isinstance(thread_result.events[0], ThreadSaturationEvent)

    model_result = request_slot(
        snapshot,
        ledger,
        ReadyWorkItem(work_id="w-model", packet_sha256="sha2", profile_id="agent"),
        model_capacity_denied=True,
    )
    assert model_result.status == "queued"
    assert isinstance(model_result.events[0], ModelCapacityEvent)


def test_queue_reclaim_after_close_releases_slots(tmp_path):
    cfg = _write_config(tmp_path, 2)
    contract = load_startup_contract(_sample_derivation(), _sample_witness(), config_path=cfg)
    snapshot = make_session_snapshot(contract, requested_capacity=2, currently_available_runtime_slots=2, write_scope_cap=2)
    ledger = CapacityLedger(topology=DescendantTopologyReadback(parent_work_id="root"))

    first = request_slot(snapshot, ledger, ReadyWorkItem(work_id="running", packet_sha256="a", profile_id="agent", required_slots=2))
    assert first.status == "granted"
    queue_item = ReadyWorkItem(work_id="queued", packet_sha256="b", profile_id="agent", required_slots=1)
    queue_ready_work(queue_item, ledger.ready_queue)

    record_lifecycle_transition(ledger, "running", LifecycleStatus.CLOSED)
    reclaim = queued_reclaim(snapshot, ledger, "running")
    assert reclaim.status in {"reclaimed", "unchanged"}


def test_closeout_fails_on_terminal_open_and_unknown_descendant(tmp_path):
    cfg = _write_config(tmp_path, 24)
    contract = load_startup_contract(_sample_derivation(), _sample_witness(), config_path=cfg)
    _ = make_session_snapshot(contract)
    closeout = materialize_closeout_packet(
        parent_work_id="parent",
        ledger=CapacityLedger(topology=DescendantTopologyReadback(parent_work_id="parent")),
        descendants=(
            DescendantTopologyReadback(
                parent_work_id="parent",
                descendants=(
                    DescendantLifecycleRecord(
                        work_id="child-a",
                        parent_work_id="parent",
                        status=LifecycleStatus.DURABLE_RESULT,
                        durable_handback=False,
                        close_readback=True,
                    ),
                    DescendantLifecycleRecord(
                        work_id="child-b",
                        parent_work_id="parent",
                        status=LifecycleStatus.CLOSED,
                        durable_handback=True,
                        close_readback=False,
                    ),
                ),
            ),
        ),
    )
    assert closeout.status == "failed"
    assert any("terminal_but_open" in f.detail for f in closeout.failures)
    assert any("missing_close_readback" in f.detail for f in closeout.failures)


def test_closeout_packet_includes_machine_readable_close_agent_calls():
    closeout = materialize_closeout_packet(
        parent_work_id="parent",
        ledger=CapacityLedger(topology=DescendantTopologyReadback(parent_work_id="parent")),
        descendants=(
            DescendantTopologyReadback(
                parent_work_id="parent",
                descendants=(
                    DescendantLifecycleRecord(
                        work_id="child-c",
                        parent_work_id="parent",
                        status=LifecycleStatus.CLOSED,
                        durable_handback=True,
                        close_readback=True,
                    ),
                ),
            ),
        ),
    )
    assert closeout.status == "closed"
    assert closeout.close_agent_calls
    assert closeout.close_agent_calls[0].close_agent_call_token == "close_agent:child-c"


def test_capacity_handshake_cli_v1_accepts_matching_26_projection(capacity_projection_root_26, capsys):
    result = main(
        (
            "--root",
            str(capacity_projection_root_26),
            "--check-config-projection",
            "--expected-max-threads",
            "26",
        )
    )

    assert result == 0
    assert capsys.readouterr().out == "CAPACITY_CONFIG_PROJECTION=pass\n"


@pytest.mark.parametrize(
    ("policy_value", "configured_value", "expected_value"),
    (
        (25, 26, 26),
        (26, 25, 26),
        (26, 26, 25),
    ),
)
def test_capacity_handshake_cli_v1_rejects_projection_mismatch(
    tmp_path,
    capsys,
    policy_value,
    configured_value,
    expected_value,
):
    _write_capacity_cli_policy(tmp_path, policy_value)
    _write_config(tmp_path, configured_value)

    result = main(
        (
            "--root",
            str(tmp_path),
            "--check-config-projection",
            "--expected-max-threads",
            str(expected_value),
        )
    )

    evidence = json.loads(capsys.readouterr().out)
    assert result == 1
    assert evidence == {
        "configured_max_threads": configured_value,
        "configured_source_ref": str(tmp_path / ".codex" / "config.toml"),
        "derived_requested_capacity": policy_value,
        "evidence_type": "CapacityInputEvidence",
        "expected_max_threads": expected_value,
        "policy_source_ref": str(tmp_path / "agents" / "capacity_policy.toml"),
        "reason": "capacity_config_projection_mismatch",
        "schema_id": "capacity_handshake_cli_v1",
        "status": "fail",
    }


@pytest.mark.parametrize(
    ("policy_raw", "config_raw", "reason"),
    (
        ('policy_id = "topology_derived_v1"\n[', "[agents]\nmax_threads = 26\n", "capacity_policy_malformed"),
        ('policy_id = "wrong"\n', "[agents]\nmax_threads = 26\n", "capacity_policy_schema_invalid"),
        (None, "[agents\nmax_threads = 26\n", "max_threads_loader_unreadable"),
        (None, '[agents]\nmax_threads = "26"\n', "max_threads_loader_unreadable"),
    ),
)
def test_capacity_handshake_cli_v1_rejects_malformed_loader_input(tmp_path, capsys, policy_raw, config_raw, reason):
    _write_capacity_cli_policy(tmp_path, raw=policy_raw)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(config_raw, encoding="utf-8")

    result = main(
        (
            "--root",
            str(tmp_path),
            "--check-config-projection",
            "--expected-max-threads",
            "26",
        )
    )

    evidence = json.loads(capsys.readouterr().out)
    assert result == 1
    assert evidence["schema_id"] == "capacity_handshake_cli_v1"
    assert evidence["evidence_type"] == "CapacityInputEvidence"
    assert evidence["status"] == "fail"
    assert evidence["reason"] == reason
