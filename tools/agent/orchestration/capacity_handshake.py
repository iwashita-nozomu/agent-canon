#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns typed capacity derivation, spawn reservations, saturation queues, and descendant lifecycle CAS.
# upstream implementation ../../../agents/capacity_policy.toml declares topology and projection policy
# upstream implementation ../../../.codex/config.toml provides configured capacity loader readback
# downstream implementation ./implementation_dispatch.py consumes capacity and records successful spawns
# downstream implementation ./implementation_route.py consumes availability for Spark routing
# downstream implementation ../../runtime/lifecycle/task_close.py validates postorder close tokens and release state
# downstream implementation ../../../tests/agent_tools/test_capacity_handshake.py tests capacity and lifecycle behavior
# @dependency-end
"""Typed capacity handshake, queue, reservation, and lifecycle owner."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Mapping, Optional, Sequence, Tuple

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

Ref = str
Id = str
Sha256 = str
ShapeId = str


def _shape_id(name: str) -> ShapeId:
    return name


def _sha256_text(value: str) -> Sha256:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class LifecycleStatus(str, Enum):
    SPAWNED = "spawned"
    ACTIVE = "active"
    DURABLE_RESULT_EVIDENCE = "durable_result_evidence"
    HANDED_BACK = "handed_back"
    DESCENDANTS_CLOSURE_VERIFIED = "descendants_closure_verified"
    CLOSED = "closed"
    READBACK_VERIFIED = "readback_verified"
    RESERVATION_RELEASED = "reservation_released"


_NEXT_LIFECYCLE_STATUS = {
    LifecycleStatus.SPAWNED: LifecycleStatus.ACTIVE,
    LifecycleStatus.ACTIVE: LifecycleStatus.DURABLE_RESULT_EVIDENCE,
    LifecycleStatus.DURABLE_RESULT_EVIDENCE: LifecycleStatus.HANDED_BACK,
    LifecycleStatus.HANDED_BACK: LifecycleStatus.DESCENDANTS_CLOSURE_VERIFIED,
    LifecycleStatus.DESCENDANTS_CLOSURE_VERIFIED: LifecycleStatus.CLOSED,
    LifecycleStatus.CLOSED: LifecycleStatus.READBACK_VERIFIED,
    LifecycleStatus.READBACK_VERIFIED: LifecycleStatus.RESERVATION_RELEASED,
}


@dataclass(frozen=True)
class CapacityPolicy:
    policy_version: int
    policy_id: str
    topology_proof_ref: Ref
    topology_proof_sha256: Sha256
    requested_total_capacity: int
    workflow_budget_derivation: str = "direct_frontier_plus_nested_reservations_once"
    write_slot_derivation: str = "max_pairwise_disjoint_write_frontier"
    source_ref: Ref = "agents/capacity_policy.toml"
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_policy_v1"), init=False)


@dataclass(frozen=True)
class DeclaredFamilyCapacity:
    workflow_family_id: Id
    direct_frontier_role_ids: Sequence[Id]
    nested_owner_role_ids: Sequence[Id]
    final_frontier_role_ids: Sequence[Id]
    direct_frontier_count: int
    nested_reservation_count: int
    final_frontier_count: int

    @property
    def requested_thread_count(self) -> int:
        return self.direct_frontier_count + self.nested_reservation_count

    @property
    def workflow_thread_request(self) -> int:
        return max(self.requested_thread_count, self.final_frontier_count)


@dataclass(frozen=True)
class DeclaredTeamTopologyDerivation:
    derivation_version: int
    topology_source: Ref
    workflow_role_source: Ref
    direct_frontier_stage_class: str
    nested_owner_stage_class: str
    final_stage_class: str
    excluded_nested_role_ids: Sequence[Id]
    isolated_direct_role_ids: Sequence[Id]
    family_records: Sequence[DeclaredFamilyCapacity]

    @property
    def peak_family(self) -> DeclaredFamilyCapacity:
        if not self.family_records:
            raise ValueError("topology:no_family_records")
        return max(self.family_records, key=lambda item: item.workflow_thread_request)

    def requested_max_threads(self) -> int:
        return self.peak_family.workflow_thread_request


@dataclass(frozen=True)
class TopologyCapacityNode:
    node_id: Id
    node_kind: str
    predecessor_ids: Sequence[Id]
    descendant_parent_id: Optional[Id]
    total_slot_weight: int
    write_slot_weight: int
    allowed_write_paths: Sequence[Ref]
    exclusion_ids: Sequence[Id]


@dataclass(frozen=True)
class TopologyCapacityWitness:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("topology_capacity_witness_v1"), init=False)
    witness_version: int = 1
    target_state_contract_sha256: Sha256 = ""
    declared_team_topology_ref: Ref = "agents/task_catalog.yaml"
    declared_team_topology_sha256: Sha256 = ""
    node_records: Sequence[TopologyCapacityNode] = ()
    legal_frontier_ids: Sequence[Id] = ()
    peak_frontier_node_ids: Sequence[Id] = ()
    peak_write_frontier_node_ids: Sequence[Id] = ()
    requested_total_capacity: int = 0
    workflow_dag_peak_demand: int = 0
    nested_reservation_count: int = 0
    workflow_dag_budget: int = 0
    write_scope_cap: int = 0
    status: str = "approved"
    derivation: Optional[DeclaredTeamTopologyDerivation] = None

    def assert_legal_topology(self) -> None:
        if self.status != "approved" or not self.node_records:
            raise ValueError("topology_witness:not_approved_or_empty")
        node_ids = {node.node_id for node in self.node_records}
        if len(node_ids) != len(self.node_records):
            raise ValueError("topology_witness:duplicate_node")
        for node in self.node_records:
            if node.node_id in node.predecessor_ids:
                raise ValueError(f"topology_witness:self_predecessor:{node.node_id}")
            if any(predecessor not in node_ids for predecessor in node.predecessor_ids):
                raise ValueError(f"topology_witness:unknown_predecessor:{node.node_id}")
            if node.node_kind == "descendant" and node.descendant_parent_id not in node_ids:
                raise ValueError(f"topology_witness:descendant_parent_missing:{node.node_id}")


@dataclass(frozen=True)
class MaxThreadsLoaderEvidence:
    loaded: bool
    configured_max_threads: Optional[int]
    raw_text: Optional[str] = None
    evidence_ref: Ref = ".codex/config.toml"
    message: Optional[str] = None
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("max_threads_loader_evidence_v1"), init=False)

    @property
    def success(self) -> bool:
        return self.loaded and isinstance(self.configured_max_threads, int) and self.configured_max_threads > 0


@dataclass(frozen=True)
class RequestedCapacityLoaderEvidence:
    requested_total_capacity: Optional[int]
    topology_proof_ref: Ref
    topology_proof_sha256: Sha256
    derived_from_topology: bool
    direct_frontier_count: int
    nested_reservation_count: int
    message: Optional[str] = None
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("requested_capacity_loader_evidence_v1"), init=False)

    @property
    def success(self) -> bool:
        return bool(
            self.requested_total_capacity
            and self.derived_from_topology
            and self.requested_total_capacity == self.direct_frontier_count + self.nested_reservation_count
        )


@dataclass(frozen=True)
class CapacityInputProvenance:
    input_id: str
    value: Optional[int]
    source_ref: Ref
    loader_id: str
    readback_value: Optional[int]
    status: str
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_input_provenance_v1"), init=False)


@dataclass(frozen=True)
class CapacityInputEvidence:
    max_threads_loader: MaxThreadsLoaderEvidence
    requested_capacity_loader: RequestedCapacityLoaderEvidence
    provenance: tuple[CapacityInputProvenance, ...]
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_input_evidence_v1"), init=False)


@dataclass(frozen=True)
class SessionCapacityContract:
    contract_id: str
    generation: int
    capacity_policy: CapacityPolicy
    input_evidence: CapacityInputEvidence
    generation_active: bool = True
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("session_capacity_contract_v1"), init=False)


@dataclass(frozen=True)
class CapacitySnapshot:
    contract: SessionCapacityContract
    requested_capacity: int
    configured_max_threads: int
    platform_advertised_effective_cap: Optional[int]
    currently_available_runtime_slots: Optional[int]
    workflow_dag_demand: int
    nested_capacity_reservation: int
    session_reload_generation: int
    write_scope_cap: int
    workflow_dag_budget: Optional[int] = None
    requested_write_capacity: int = 0
    platform_advertised_effective_write_cap: Optional[int] = None
    currently_available_write_slots: Optional[int] = None
    workflow_dag_write_demand: int = 0
    input_provenance: tuple[CapacityInputProvenance, ...] = ()
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_snapshot_v1"), init=False)

    @property
    def requested_total_capacity(self) -> int:
        return self.requested_capacity

    @property
    def workflow_total_demand(self) -> int:
        return self.workflow_dag_demand + self.nested_capacity_reservation

    @property
    def effective_total_capacity(self) -> int:
        values = [self.requested_capacity, self.configured_max_threads, self.workflow_total_demand]
        if self.workflow_dag_budget is not None:
            values.append(self.workflow_dag_budget)
        if self.platform_advertised_effective_cap is not None:
            values.append(self.platform_advertised_effective_cap)
        return max(min(values), 0)

    @property
    def available_total_capacity(self) -> int:
        if self.currently_available_runtime_slots is None:
            return self.effective_total_capacity
        return max(min(self.effective_total_capacity, self.currently_available_runtime_slots), 0)

    @property
    def reserved_total_capacity(self) -> int:
        """Topology nested reservations are already included in requested total."""
        return 0

    @property
    def remaining_total_slots(self) -> int:
        return self.available_total_capacity

    @property
    def effective_write_capacity(self) -> int:
        requested = self.requested_write_capacity or self.write_scope_cap
        demand = self.workflow_dag_write_demand or requested
        values = [requested, self.write_scope_cap, demand]
        if self.platform_advertised_effective_write_cap is not None:
            values.append(self.platform_advertised_effective_write_cap)
        return max(min(values), 0)

    @property
    def available_write_capacity(self) -> int:
        if self.currently_available_write_slots is None:
            return self.effective_write_capacity
        return max(min(self.effective_write_capacity, self.currently_available_write_slots), 0)

    @property
    def remaining_write_slots(self) -> int:
        return self.available_write_capacity

    @property
    def workflow_dag_budget_value(self) -> int:
        return self.effective_total_capacity


@dataclass(frozen=True)
class DescendantTopologyReadback:
    parent_work_id: Id
    descendants: Sequence["DescendantLifecycleRecord"] = ()
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("descendant_topology_readback_v1"), init=False)


@dataclass
class DescendantLifecycleRecord:
    work_id: Id = ""
    parent_work_id: Optional[Id] = None
    profile_id: str = ""
    status: LifecycleStatus = LifecycleStatus.SPAWNED
    durable_result_evidence_ref: Optional[Ref] = None
    durable_handback: bool = False
    descendants_closed: bool = False
    close_readback: bool = False
    reserved_slots: int = 1
    reserved_write_slots: int = 0
    transition_generation: int = 0
    transition_history: list["LifecycleTransitionRecord"] = field(default_factory=list)
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("descendant_lifecycle_record_v1"), init=False)


@dataclass(frozen=True)
class LifecycleTransitionRecord:
    work_id: Id
    previous_status: LifecycleStatus
    next_status: LifecycleStatus
    expected_generation: int
    resulting_generation: int
    evidence_ref: Optional[Ref] = None
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("lifecycle_transition_record_v1"), init=False)


@dataclass(frozen=True)
class ParentChildEdge:
    parent_work_id: Id
    child_work_id: Id


@dataclass
class CapacityLedger:
    topology: DescendantTopologyReadback = field(default_factory=lambda: DescendantTopologyReadback(parent_work_id=""))
    open_records: dict[Id, DescendantLifecycleRecord] = field(default_factory=dict)
    ready_queue: List["ReadyWorkItem"] = field(default_factory=list)
    reservations: dict[Id, ParentChildEdge] = field(default_factory=dict)
    transitions: list[LifecycleTransitionRecord] = field(default_factory=list)
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_ledger_v1"), init=False)


@dataclass(frozen=True)
class ThreadSaturationEvent:
    work_id: Id
    reason: str
    available_slots: int
    required_slots: int
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("thread_saturation_event_v1"), init=False)


@dataclass(frozen=True)
class ModelCapacityEvent:
    work_id: Id
    model: str
    reason: str
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("model_capacity_event_v1"), init=False)


@dataclass(frozen=True)
class ReadyWorkItem:
    work_id: Id
    packet_sha256: str
    profile_id: Id
    required_slots: int = 1
    required_write_slots: int = 0
    model: str = "default"


@dataclass(frozen=True)
class ReservationResult:
    status: str
    item: ReadyWorkItem
    slot_allocation: int
    write_slot_allocation: int
    events: Tuple[object, ...] = ()
    queue_ref: Optional[Ref] = None


@dataclass(frozen=True)
class QueueResult:
    status: str
    queued: Tuple[ReadyWorkItem, ...]
    queue_depth: int
    saturation_events: Tuple[ThreadSaturationEvent, ...] = ()
    model_events: Tuple[ModelCapacityEvent, ...] = ()


@dataclass(frozen=True)
class RestartRequiredEvidence:
    reason: str
    old_configured: Optional[int]
    new_requested: Optional[int] = None
    evidence_ref: Ref = "runtime://current-spawn/P2_capacity_handshake"


@dataclass(frozen=True)
class LedgerWriteResult:
    write_success: bool
    errors: Tuple[str, ...] = ()
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("ledger_write_result_v1"), init=False)


@dataclass(frozen=True)
class CloseAgentCallRecord:
    close_agent_call_token: Mapping[str, object]
    work_id: Id


@dataclass(frozen=True)
class LifecycleCloseoutFailure:
    work_id: Id
    detail: str


@dataclass(frozen=True)
class CloseoutPacket:
    parent_work_id: Id
    close_agent_calls: Sequence[CloseAgentCallRecord]
    failures: Sequence[LifecycleCloseoutFailure]
    status: str
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("closeout_packet_v1"), init=False)


def capacity_from_topology_derivation(evidence: DeclaredTeamTopologyDerivation) -> int:
    return evidence.requested_max_threads()


def load_max_threads_loader(path: str = ".codex/config.toml") -> MaxThreadsLoaderEvidence:
    config_path = Path(path)
    try:
        raw = config_path.read_text(encoding="utf-8")
        parsed = tomllib.loads(raw)
        configured = parsed.get("agents", {}).get("max_threads")
    except (OSError, tomllib.TOMLDecodeError, AttributeError) as exc:
        return MaxThreadsLoaderEvidence(False, None, evidence_ref=path, message=f"unreadable_config:{exc}")
    if not isinstance(configured, int) or configured <= 0:
        return MaxThreadsLoaderEvidence(False, None, raw, path, "configured_max_threads_not_positive_int")
    return MaxThreadsLoaderEvidence(True, configured, raw, path)


def load_requested_capacity(evidence: DeclaredTeamTopologyDerivation) -> RequestedCapacityLoaderEvidence:
    peak = evidence.peak_family
    requested = peak.direct_frontier_count + peak.nested_reservation_count
    proof = {
        "topology_source": evidence.topology_source,
        "family": peak.workflow_family_id,
        "direct_frontier_count": peak.direct_frontier_count,
        "nested_reservation_count": peak.nested_reservation_count,
        "requested_total_capacity": requested,
    }
    return RequestedCapacityLoaderEvidence(
        requested,
        evidence.topology_source,
        _sha256_text(json.dumps(proof, sort_keys=True, separators=(",", ":"))),
        True,
        peak.direct_frontier_count,
        peak.nested_reservation_count,
    )


def build_capacity_policy(witness: TopologyCapacityWitness) -> CapacityPolicy:
    validate_topology_inputs(witness)
    return CapacityPolicy(
        1,
        "topology_derived_v1",
        witness.declared_team_topology_ref,
        witness.declared_team_topology_sha256,
        witness.requested_total_capacity,
    )


def validate_topology_inputs(evidence: TopologyCapacityWitness) -> None:
    evidence.assert_legal_topology()
    if evidence.requested_total_capacity <= 0:
        raise ValueError("requested_total_capacity:must_be_positive")
    if evidence.workflow_dag_peak_demand + evidence.nested_reservation_count != evidence.requested_total_capacity:
        raise ValueError("requested_total_capacity:must_equal_direct_plus_nested_once")
    if evidence.derivation is not None and evidence.derivation.requested_max_threads() != evidence.requested_total_capacity:
        raise ValueError("requested_total_capacity:derivation_mismatch")


def load_startup_contract(
    derivation: DeclaredTeamTopologyDerivation,
    witness: TopologyCapacityWitness,
    config_path: str = ".codex/config.toml",
    contract_id: str = "handshake-contract",
) -> SessionCapacityContract:
    validate_topology_inputs(witness)
    max_threads = load_max_threads_loader(config_path)
    requested = load_requested_capacity(derivation)
    if not max_threads.success or not requested.success:
        raise RuntimeError(
            str(RestartRequiredEvidence("capacity_loader_failed", max_threads.configured_max_threads, requested.requested_total_capacity))
        )
    provenance = (
        CapacityInputProvenance(
            "requested_total_capacity",
            requested.requested_total_capacity,
            requested.topology_proof_ref,
            "declared_team_topology_loader_v1",
            requested.requested_total_capacity,
            "readback_verified",
        ),
        CapacityInputProvenance(
            "configured_total_capacity",
            max_threads.configured_max_threads,
            max_threads.evidence_ref,
            "max_threads_loader_v1",
            max_threads.configured_max_threads,
            "readback_verified",
        ),
    )
    return SessionCapacityContract(
        contract_id,
        1,
        build_capacity_policy(witness),
        CapacityInputEvidence(max_threads, requested, provenance),
    )


def _provenance(
    input_id: str,
    value: Optional[int],
    source_ref: str,
    loader_id: str,
) -> CapacityInputProvenance:
    return CapacityInputProvenance(
        input_id,
        value,
        source_ref,
        loader_id,
        value,
        "readback_verified" if value is not None else "not_advertised",
    )


def make_session_snapshot(
    contract: SessionCapacityContract,
    requested_capacity: Optional[int] = None,
    configured_max_threads: Optional[int] = None,
    platform_advertised_effective_cap: Optional[int] = None,
    currently_available_runtime_slots: Optional[int] = None,
    workflow_dag_demand: Optional[int] = None,
    nested_capacity_reservation: int = 0,
    write_scope_cap: int = 0,
    session_reload_generation: int = 1,
    *,
    requested_write_capacity: Optional[int] = None,
    platform_advertised_effective_write_cap: Optional[int] = None,
    currently_available_write_slots: Optional[int] = None,
    workflow_dag_write_demand: Optional[int] = None,
    workflow_dag_budget: Optional[int] = None,
) -> CapacitySnapshot:
    requested = requested_capacity or contract.capacity_policy.requested_total_capacity
    configured = configured_max_threads or contract.input_evidence.max_threads_loader.configured_max_threads
    if configured is None or configured <= 0 or requested <= 0:
        raise ValueError("capacity_snapshot:requested_and_configured_required")
    direct_demand = workflow_dag_demand if workflow_dag_demand is not None else requested - nested_capacity_reservation
    if direct_demand < 0 or direct_demand + nested_capacity_reservation != requested:
        raise ValueError("capacity_snapshot:nested_reservation_must_be_counted_once")
    write_cap = write_scope_cap or requested
    requested_write = requested_write_capacity if requested_write_capacity is not None else write_cap
    write_demand = workflow_dag_write_demand if workflow_dag_write_demand is not None else requested_write
    budget = workflow_dag_budget if workflow_dag_budget is not None else requested
    provenance = contract.input_evidence.provenance + (
        _provenance("platform_effective_total_capacity", platform_advertised_effective_cap, "runtime://platform/effective-total", "platform_capacity_loader_v1"),
        _provenance("current_available_total_capacity", currently_available_runtime_slots, "runtime://current/available-total", "current_capacity_loader_v1"),
        _provenance("workflow_dag_direct_demand", direct_demand, "agents/task_catalog.yaml", "workflow_dag_loader_v1"),
        _provenance("nested_reservation_count", nested_capacity_reservation, "agents/task_catalog.yaml", "nested_reservation_loader_v1"),
        _provenance("write_scope_cap", write_cap, "team_manifest.run.write_scopes", "write_scope_loader_v1"),
        _provenance("current_available_write_capacity", currently_available_write_slots, "runtime://current/available-write", "current_write_capacity_loader_v1"),
    )
    return CapacitySnapshot(
        contract=contract,
        requested_capacity=requested,
        configured_max_threads=configured,
        platform_advertised_effective_cap=platform_advertised_effective_cap,
        currently_available_runtime_slots=currently_available_runtime_slots,
        workflow_dag_demand=direct_demand,
        nested_capacity_reservation=nested_capacity_reservation,
        session_reload_generation=session_reload_generation,
        write_scope_cap=write_cap,
        workflow_dag_budget=budget,
        requested_write_capacity=requested_write,
        platform_advertised_effective_write_cap=platform_advertised_effective_write_cap,
        currently_available_write_slots=currently_available_write_slots,
        workflow_dag_write_demand=write_demand,
        input_provenance=provenance,
    )


def queue_ready_work(item: ReadyWorkItem, queue: List[ReadyWorkItem]) -> QueueResult:
    if not any(existing.work_id == item.work_id for existing in queue):
        queue.append(item)
    return QueueResult("queued", tuple(queue), len(queue))


def _reserved_capacity(ledger: CapacityLedger) -> tuple[int, int]:
    records = [ledger.open_records[work_id] for work_id in ledger.reservations if work_id in ledger.open_records]
    return (
        sum(record.reserved_slots for record in records),
        sum(record.reserved_write_slots for record in records),
    )


def _can_grant(snapshot: CapacitySnapshot, ledger: CapacityLedger, item: ReadyWorkItem) -> bool:
    total_reserved, write_reserved = _reserved_capacity(ledger)
    return (
        snapshot.remaining_total_slots - total_reserved >= item.required_slots
        and snapshot.remaining_write_slots - write_reserved >= item.required_write_slots
    )


def request_slot(
    snapshot: CapacitySnapshot,
    ledger: CapacityLedger,
    item: ReadyWorkItem,
    model_capacity_denied: bool = False,
    model_name: Optional[str] = None,
) -> ReservationResult:
    """Return spawn readiness without creating a reservation."""
    if model_capacity_denied:
        event = ModelCapacityEvent(item.work_id, model_name or item.model, "model_service_overload")
        queue_ready_work(item, ledger.ready_queue)
        return ReservationResult("queued", item, 0, 0, (event,), "runtime://capacity/ready-queue")
    if _can_grant(snapshot, ledger, item):
        return ReservationResult("ready", item, item.required_slots, item.required_write_slots)
    total_reserved, _ = _reserved_capacity(ledger)
    event = ThreadSaturationEvent(
        item.work_id,
        "thread_or_write_limit_reached",
        max(snapshot.remaining_total_slots - total_reserved, 0),
        item.required_slots,
    )
    queue_ready_work(item, ledger.ready_queue)
    return ReservationResult("queued", item, 0, 0, (event,), "runtime://capacity/ready-queue")


def record_successful_spawn(
    snapshot: CapacitySnapshot,
    ledger: CapacityLedger,
    item: ReadyWorkItem,
    *,
    spawn_succeeded: bool,
    parent_work_id: str | None = None,
) -> ReservationResult:
    """Create exactly one reservation only after an actual successful spawn."""
    if item.work_id in ledger.open_records or item.work_id in ledger.reservations:
        raise ValueError(f"spawn_reservation:duplicate:{item.work_id}")
    readiness = request_slot(snapshot, ledger, item)
    if readiness.status != "ready":
        return readiness
    if not spawn_succeeded:
        queue_ready_work(item, ledger.ready_queue)
        return ReservationResult("queued", item, 0, 0, queue_ref="runtime://capacity/ready-queue")
    parent = parent_work_id or ledger.topology.parent_work_id
    record = DescendantLifecycleRecord(
        work_id=item.work_id,
        parent_work_id=parent,
        profile_id=item.profile_id,
        reserved_slots=item.required_slots,
        reserved_write_slots=item.required_write_slots,
    )
    ledger.open_records[item.work_id] = record
    ledger.reservations[item.work_id] = ParentChildEdge(parent, item.work_id)
    ledger.topology = DescendantTopologyReadback(
        ledger.topology.parent_work_id,
        tuple((*ledger.topology.descendants, record)),
    )
    ledger.ready_queue[:] = [queued for queued in ledger.ready_queue if queued.work_id != item.work_id]
    return ReservationResult("granted", item, item.required_slots, item.required_write_slots)


def record_lifecycle_transition(
    ledger: CapacityLedger,
    item_id: Id,
    new_status: LifecycleStatus,
    *,
    expected_status: LifecycleStatus,
    expected_generation: int,
    evidence_ref: Optional[Ref] = None,
) -> DescendantLifecycleRecord:
    current = ledger.open_records.get(item_id)
    if current is None:
        raise ValueError(f"lifecycle:unknown_record:{item_id}")
    if current.status != expected_status or current.transition_generation != expected_generation:
        raise ValueError(f"lifecycle:compare_and_swap_failed:{item_id}")
    required_next = _NEXT_LIFECYCLE_STATUS.get(expected_status)
    if required_next != new_status:
        raise ValueError(f"lifecycle:out_of_order:{expected_status.value}->{new_status.value}")
    if new_status == LifecycleStatus.DURABLE_RESULT_EVIDENCE and not evidence_ref:
        raise ValueError("lifecycle:durable_result_evidence_ref_required")
    if new_status == LifecycleStatus.DESCENDANTS_CLOSURE_VERIFIED:
        children = [
            record
            for record in ledger.open_records.values()
            if record.parent_work_id == item_id
        ]
        if any(child.status != LifecycleStatus.RESERVATION_RELEASED for child in children):
            raise ValueError("lifecycle:descendants_not_closed_postorder")
    if new_status == LifecycleStatus.RESERVATION_RELEASED:
        if not (current.durable_handback and current.descendants_closed and current.close_readback):
            raise ValueError("lifecycle:release_preconditions_missing")
        if item_id not in ledger.reservations:
            raise ValueError("lifecycle:reservation_missing_before_release")
    transition = LifecycleTransitionRecord(
        item_id,
        expected_status,
        new_status,
        expected_generation,
        expected_generation + 1,
        evidence_ref,
    )
    current.status = new_status
    current.transition_generation += 1
    current.transition_history.append(transition)
    if new_status == LifecycleStatus.DURABLE_RESULT_EVIDENCE:
        current.durable_result_evidence_ref = evidence_ref
    elif new_status == LifecycleStatus.HANDED_BACK:
        current.durable_handback = True
    elif new_status == LifecycleStatus.DESCENDANTS_CLOSURE_VERIFIED:
        current.descendants_closed = True
    elif new_status == LifecycleStatus.READBACK_VERIFIED:
        current.close_readback = True
    elif new_status == LifecycleStatus.RESERVATION_RELEASED:
        ledger.reservations.pop(item_id)
    ledger.transitions.append(transition)
    return current


def _postorder_records(records: Sequence[DescendantLifecycleRecord]) -> tuple[DescendantLifecycleRecord, ...]:
    by_parent: dict[str | None, list[DescendantLifecycleRecord]] = {}
    for record in records:
        by_parent.setdefault(record.parent_work_id, []).append(record)
    result: list[DescendantLifecycleRecord] = []
    visiting: set[str] = set()

    def visit(record: DescendantLifecycleRecord) -> None:
        if record.work_id in visiting:
            raise ValueError("lifecycle:descendant_cycle")
        visiting.add(record.work_id)
        for child in sorted(by_parent.get(record.work_id, []), key=lambda value: value.work_id):
            visit(child)
        visiting.remove(record.work_id)
        result.append(record)

    all_ids = {record.work_id for record in records}
    roots = [record for record in records if record.parent_work_id not in all_ids]
    for root in sorted(roots, key=lambda value: value.work_id):
        visit(root)
    if len(result) != len(records):
        raise ValueError("lifecycle:unreachable_descendant")
    return tuple(result)


def materialize_closeout_packet(
    parent_work_id: Id,
    ledger: CapacityLedger,
    descendants: Sequence[DescendantTopologyReadback],
    close_agent_tokens: Mapping[str, Mapping[str, object]] | None = None,
) -> CloseoutPacket:
    failures: list[LifecycleCloseoutFailure] = []
    calls: list[CloseAgentCallRecord] = []
    tokens = close_agent_tokens or {}
    records = tuple(record for topology in descendants for record in topology.descendants)
    provided_ids = {record.work_id for record in records}
    try:
        postorder = _postorder_records(records)
    except ValueError as exc:
        return CloseoutPacket(parent_work_id, (), (LifecycleCloseoutFailure(parent_work_id, str(exc)),), "failed")
    for known_id, record in ledger.open_records.items():
        if record.parent_work_id == parent_work_id and known_id not in provided_ids:
            failures.append(LifecycleCloseoutFailure(known_id, "unknown_descendant"))
    for record in postorder:
        if record.status not in {LifecycleStatus.READBACK_VERIFIED, LifecycleStatus.RESERVATION_RELEASED}:
            failures.append(LifecycleCloseoutFailure(record.work_id, "lifecycle_not_readback_verified"))
            continue
        token = tokens.get(record.work_id)
        if not isinstance(token, Mapping):
            failures.append(LifecycleCloseoutFailure(record.work_id, "close_agent_token_missing"))
            continue
        calls.append(CloseAgentCallRecord(dict(token), record.work_id))
        if record.status == LifecycleStatus.READBACK_VERIFIED:
            try:
                record_lifecycle_transition(
                    ledger,
                    record.work_id,
                    LifecycleStatus.RESERVATION_RELEASED,
                    expected_status=LifecycleStatus.READBACK_VERIFIED,
                    expected_generation=record.transition_generation,
                    evidence_ref="closeout://reservation-release",
                )
            except ValueError as exc:
                failures.append(LifecycleCloseoutFailure(record.work_id, str(exc)))
    return CloseoutPacket(parent_work_id, tuple(calls), tuple(failures), "closed" if not failures else "failed")


def queued_reclaim(snapshot: CapacitySnapshot, ledger: CapacityLedger, closed_work_id: Id) -> QueueResult:
    record = ledger.open_records.get(closed_work_id)
    if record is None or record.status != LifecycleStatus.RESERVATION_RELEASED:
        return QueueResult("unchanged", tuple(ledger.ready_queue), len(ledger.ready_queue))
    ready = tuple(item for item in ledger.ready_queue if _can_grant(snapshot, ledger, item))
    return QueueResult("capacity_available" if ready else "unchanged", tuple(ledger.ready_queue), len(ledger.ready_queue))


_CAPACITY_HANDSHAKE_CLI_SCHEMA_ID = "capacity_handshake_cli_v1"
_TOPOLOGY_TARGET_DERIVATION = "declared_team_peak_plus_nested_reservations_v1"
_TOPOLOGY_WITNESS_PREDICATE = "generated_value_matches_topology_witness"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _load_policy_topology_request(root: Path) -> tuple[Optional[int], str, dict[str, int]]:
    path = root / "agents" / "capacity_policy.toml"
    try:
        with path.open("rb") as handle:
            policy = tomllib.load(handle)
    except FileNotFoundError:
        return None, "capacity_policy_missing", {}
    except tomllib.TOMLDecodeError:
        return None, "capacity_policy_malformed", {}
    if policy.get("policy_id") != "topology_derived_v1":
        return None, "capacity_policy_schema_invalid", {}
    topology = policy.get("topology_derivation")
    projection = policy.get("runtime_config_change_policy")
    manifest = policy.get("generated_manifest_policy")
    if not isinstance(topology, dict) or not isinstance(projection, dict) or not isinstance(manifest, dict):
        return None, "capacity_policy_schema_invalid", {}
    direct = topology.get("direct_frontier_count")
    nested = topology.get("nested_reservation_count")
    requested = projection.get("target_value")
    if (
        topology.get("nested_reservation_accounting") != "count_once"
        or projection.get("target_value_derivation") != _TOPOLOGY_TARGET_DERIVATION
        or not isinstance(direct, int)
        or not isinstance(nested, int)
        or not isinstance(requested, int)
        or direct + nested != requested
    ):
        return None, "capacity_policy_topology_invalid", {}
    predicates = projection.get("required_predicates")
    if not isinstance(predicates, list) or _TOPOLOGY_WITNESS_PREDICATE not in predicates:
        return None, "capacity_policy_schema_invalid", {}
    return requested, "ok", {"direct_frontier_count": direct, "nested_reservation_count": nested}


def _print_projection_failure(
    *,
    reason: str,
    root: Path,
    expected: Optional[int],
    derived: Optional[int],
    configured: Optional[int],
    counts: Mapping[str, int] | None = None,
) -> None:
    print(
        json.dumps(
            {
                "schema_id": _CAPACITY_HANDSHAKE_CLI_SCHEMA_ID,
                "evidence_type": "CapacityInputEvidence",
                "status": "fail",
                "reason": reason,
                "expected_max_threads": expected,
                "derived_requested_capacity": derived,
                "configured_max_threads": configured,
                "direct_frontier_count": (counts or {}).get("direct_frontier_count"),
                "nested_reservation_count": (counts or {}).get("nested_reservation_count"),
                "policy_source_ref": str(root / "agents" / "capacity_policy.toml"),
                "configured_source_ref": str(root / ".codex" / "config.toml"),
            },
            sort_keys=True,
        )
    )


def _write_config_projection(root: Path, value: int) -> None:
    path = root / ".codex" / "config.toml"
    raw = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?m)^(max_threads\s*=\s*)\d+\s*$")
    if len(pattern.findall(raw)) != 1:
        raise ValueError("max_threads_projection_target_not_unique")
    path.write_text(pattern.sub(rf"\g<1>{value}", raw), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="capacity_handshake.py")
    parser.add_argument("--root", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-config-projection", action="store_true")
    mode.add_argument("--write-config-projection", action="store_true")
    parser.add_argument("--expected-max-threads", type=_positive_int)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    derived, status, counts = _load_policy_topology_request(root)
    if status != "ok" or derived is None:
        _print_projection_failure(reason=status, root=root, expected=args.expected_max_threads, derived=derived, configured=None, counts=counts)
        return 1
    expected = args.expected_max_threads if args.expected_max_threads is not None else derived
    if args.write_config_projection:
        try:
            _write_config_projection(root, derived)
        except (OSError, ValueError) as exc:
            _print_projection_failure(reason=str(exc), root=root, expected=expected, derived=derived, configured=None, counts=counts)
            return 1
    configured_evidence = load_max_threads_loader(str(root / ".codex" / "config.toml"))
    configured = configured_evidence.configured_max_threads
    if not configured_evidence.success:
        _print_projection_failure(reason="max_threads_loader_unreadable", root=root, expected=expected, derived=derived, configured=configured, counts=counts)
        return 1
    if configured != derived or derived != expected:
        _print_projection_failure(reason="capacity_config_projection_mismatch", root=root, expected=expected, derived=derived, configured=configured, counts=counts)
        return 1
    print("CAPACITY_CONFIG_PROJECTION=written" if args.write_config_projection else "CAPACITY_CONFIG_PROJECTION=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
