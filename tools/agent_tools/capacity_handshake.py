from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

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
    DURABLE_RESULT = "durable_result"
    ERROR = "error"
    HANDED_BACK = "handed_back"
    DESCENDANTS_VERIFIED = "descendants_verified"
    CLOSED = "closed"


@dataclass(frozen=True)
class CapacityPolicy:
    policy_version: int
    policy_id: str
    topology_proof_ref: Ref
    topology_proof_sha256: Sha256
    requested_total_capacity: int
    workflow_budget_derivation: str = "requested_total_capacity"
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
        return max(self.family_records, key=lambda item: item.workflow_thread_request)

    def requested_max_threads(self) -> int:
        if not self.family_records:
            raise ValueError("no family records")
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
        if self.status != "approved":
            raise ValueError("topology witness rejected")
        node_ids = {node.node_id for node in self.node_records}
        if not node_ids:
            raise ValueError("no topology nodes")
        for node in self.node_records:
            if node.node_id in node.predecessor_ids:
                raise ValueError(f"self predecessor detected: {node.node_id}")
            unknown_pred = [pred for pred in node.predecessor_ids if pred not in node_ids]
            if unknown_pred:
                raise ValueError(f"unknown predecessor in {node.node_id}: {unknown_pred}")
            if node.node_kind == "descendant" and node.descendant_parent_id is None:
                raise ValueError(f"descendant missing parent {node.node_id}")


@dataclass(frozen=True)
class MaxThreadsLoaderEvidence:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("session_capacity_contract_v1"), init=False)
    loaded: bool
    configured_max_threads: Optional[int]
    raw_text: Optional[str] = None
    evidence_ref: Ref = ".codex/config.toml"
    message: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.loaded and isinstance(self.configured_max_threads, int)


@dataclass(frozen=True)
class RequestedCapacityLoaderEvidence:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("session_capacity_contract_v1"), init=False)
    requested_total_capacity: Optional[int]
    topology_proof_ref: Ref
    topology_proof_sha256: Sha256
    derived_from_topology: bool
    message: Optional[str] = None

    @property
    def success(self) -> bool:
        return bool(self.requested_total_capacity is not None and self.derived_from_topology)


@dataclass(frozen=True)
class CapacityInputEvidence:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("session_capacity_contract_v1"), init=False)
    max_threads_loader: MaxThreadsLoaderEvidence
    requested_capacity_loader: RequestedCapacityLoaderEvidence


@dataclass(frozen=True)
class SessionCapacityContract:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("session_capacity_contract_v1"), init=False)
    contract_id: str
    generation: int
    capacity_policy: CapacityPolicy
    input_evidence: CapacityInputEvidence
    generation_active: bool = True


@dataclass(frozen=True)
class CapacitySnapshot:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_snapshot_v1"), init=False)
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

    @property
    def effective_total_capacity(self) -> int:
        return self.requested_capacity

    @property
    def workflow_dag_budget_value(self) -> int:
        if self.workflow_dag_budget is None:
            return min(self.effective_total_capacity, self.workflow_dag_demand)
        return min(self.effective_total_capacity, self.workflow_dag_demand, self.workflow_dag_budget)

    @property
    def reserved_total_capacity(self) -> int:
        return self.nested_capacity_reservation

    @property
    def available_total_capacity(self) -> int:
        effective = min(self.effective_total_capacity, self.configured_max_threads)
        if self.platform_advertised_effective_cap is not None:
            effective = min(effective, self.platform_advertised_effective_cap)
        if self.currently_available_runtime_slots is not None:
            effective = min(effective, self.currently_available_runtime_slots)
        return max(effective - self.reserved_total_capacity, 0)

    @property
    def remaining_total_slots(self) -> int:
        return self.available_total_capacity

    @property
    def remaining_write_slots(self) -> int:
        return max(self.write_scope_cap, 0)


@dataclass(frozen=True)
class DescendantTopologyReadback:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("descendant_topology_readback_v1"), init=False)
    parent_work_id: Id
    descendants: Sequence["DescendantLifecycleRecord"] = ()


@dataclass
class DescendantLifecycleRecord:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("descendant_lifecycle_record_v1"), init=False)
    work_id: Id = ""
    parent_work_id: Optional[Id] = None
    status: LifecycleStatus = LifecycleStatus.SPAWNED
    durable_handback: bool = False
    descendants_closed: bool = False
    close_readback: bool = False
    reserved_slots: int = 1
    reserved_write_slots: int = 0


@dataclass(frozen=True)
class LifecycleTransitionRecord:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("lifecycle_transition_record_v1"), init=False)
    work_id: Id
    previous_status: LifecycleStatus
    next_status: LifecycleStatus
    reason: Optional[str] = None


@dataclass(frozen=True)
class ParentChildEdge:
    parent_work_id: Id
    child_work_id: Id


@dataclass
class CapacityLedger:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_ledger_v1"), init=False)
    topology: DescendantTopologyReadback = field(default_factory=lambda: DescendantTopologyReadback(parent_work_id=""))
    open_records: dict[Id, DescendantLifecycleRecord] = field(default_factory=dict)
    ready_queue: List["ReadyWorkItem"] = field(default_factory=list)
    reservations: dict[Id, ParentChildEdge] = field(default_factory=dict)


@dataclass(frozen=True)
class ThreadSaturationEvent:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_snapshot_v1"), init=False)
    work_id: Id
    reason: str
    available_slots: int
    required_slots: int


@dataclass(frozen=True)
class ModelCapacityEvent:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("capacity_snapshot_v1"), init=False)
    work_id: Id
    model: str
    reason: str


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
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("ledger_write_result_v1"), init=False)
    write_success: bool
    errors: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CloseAgentCallRecord:
    close_agent_call_token: Ref
    work_id: Id


@dataclass(frozen=True)
class LifecycleCloseoutFailure:
    work_id: Id
    detail: str


@dataclass(frozen=True)
class CloseoutPacket:
    shape_id: ShapeId = field(default_factory=lambda: _shape_id("closeout_packet_v1"), init=False)
    parent_work_id: Id
    close_agent_calls: Sequence[CloseAgentCallRecord]
    failures: Sequence[LifecycleCloseoutFailure]
    status: str


def capacity_from_topology_derivation(evidence: DeclaredTeamTopologyDerivation) -> int:
    return evidence.requested_max_threads()


def load_max_threads_loader(path: str = ".codex/config.toml") -> MaxThreadsLoaderEvidence:
    config_path = Path(path)
    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as error:
        return MaxThreadsLoaderEvidence(
            loaded=False,
            configured_max_threads=None,
            evidence_ref=path,
            raw_text=None,
            message=f"unreadable_config: {error}",
        )

    try:
        parsed = tomllib.loads(raw)
    except Exception as error:  # pragma: no cover
        return MaxThreadsLoaderEvidence(
            loaded=False,
            configured_max_threads=None,
            raw_text=raw,
            evidence_ref=path,
            message=f"parse_failure: {error}",
        )

    agents_section = parsed.get("agents", {})
    configured = agents_section.get("max_threads")
    if not isinstance(configured, int):
        return MaxThreadsLoaderEvidence(
            loaded=False,
            configured_max_threads=None,
            raw_text=raw,
            evidence_ref=path,
            message="configured_max_threads_not_int",
        )

    return MaxThreadsLoaderEvidence(loaded=True, configured_max_threads=configured, raw_text=raw, evidence_ref=path)


def load_requested_capacity(evidence: DeclaredTeamTopologyDerivation) -> RequestedCapacityLoaderEvidence:
    requested = evidence.requested_max_threads()
    return RequestedCapacityLoaderEvidence(
        requested_total_capacity=requested,
        topology_proof_ref="agents/task_catalog.yaml",
        topology_proof_sha256=_sha256_text(f"{requested}|{len(evidence.family_records)}"),
        derived_from_topology=True,
    )


def build_capacity_policy(witness: TopologyCapacityWitness) -> CapacityPolicy:
    if witness.requested_total_capacity <= 0:
        raise ValueError("invalid requested_total_capacity")
    if witness.derivation is not None and witness.derivation.requested_max_threads() != witness.requested_total_capacity:
        raise ValueError("witness request mismatch")
    return CapacityPolicy(
        policy_version=1,
        policy_id="topology_derived_v1",
        topology_proof_ref=witness.declared_team_topology_ref,
        topology_proof_sha256=witness.declared_team_topology_sha256,
        requested_total_capacity=witness.requested_total_capacity,
    )


def validate_topology_inputs(evidence: TopologyCapacityWitness) -> None:
    evidence.assert_legal_topology()
    if evidence.requested_total_capacity <= 0:
        raise ValueError("requested_total_capacity must be > 0")


def load_startup_contract(
    derivation: DeclaredTeamTopologyDerivation,
    witness: TopologyCapacityWitness,
    config_path: str = ".codex/config.toml",
    contract_id: str = "handshake-contract",
) -> SessionCapacityContract:
    validate_topology_inputs(witness)
    policy = build_capacity_policy(witness)

    max_threads_evidence = load_max_threads_loader(config_path)
    requested_evidence = load_requested_capacity(derivation)

    if not max_threads_evidence.success:
        raise RuntimeError(
            str(
                RestartRequiredEvidence(
                    reason="max_threads_unreadable",
                    old_configured=witness.requested_total_capacity,
                    new_requested=requested_evidence.requested_total_capacity,
                )
            )
        )

    return SessionCapacityContract(
        contract_id=contract_id,
        generation=1,
        capacity_policy=policy,
        input_evidence=CapacityInputEvidence(
            max_threads_loader=max_threads_evidence,
            requested_capacity_loader=requested_evidence,
        ),
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
) -> CapacitySnapshot:
    if requested_capacity is None:
        requested_capacity = contract.capacity_policy.requested_total_capacity
    if configured_max_threads is None:
        configured_max_threads = contract.input_evidence.max_threads_loader.configured_max_threads
    if configured_max_threads is None:
        raise ValueError("configured_max_threads missing")
    if workflow_dag_demand is None:
        workflow_dag_demand = requested_capacity
    if write_scope_cap == 0:
        write_scope_cap = requested_capacity
    return CapacitySnapshot(
        contract=contract,
        requested_capacity=requested_capacity,
        configured_max_threads=configured_max_threads,
        platform_advertised_effective_cap=platform_advertised_effective_cap,
        currently_available_runtime_slots=currently_available_runtime_slots,
        workflow_dag_demand=workflow_dag_demand,
        nested_capacity_reservation=nested_capacity_reservation,
        session_reload_generation=session_reload_generation,
        write_scope_cap=write_scope_cap,
        workflow_dag_budget=requested_capacity,
    )


def queue_ready_work(item: ReadyWorkItem, queue: List[ReadyWorkItem]) -> QueueResult:
    if item not in queue:
        queue.append(item)
    return QueueResult(status="queued", queued=tuple(queue), queue_depth=len(queue))


def _can_grant(snapshot: CapacitySnapshot, ledger: CapacityLedger, item: ReadyWorkItem) -> bool:
    reserved = sum(record.reserved_slots for record in ledger.open_records.values())
    write_reserved = sum(record.reserved_write_slots for record in ledger.open_records.values())
    available = max(snapshot.remaining_total_slots - reserved, 0)
    write_available = max(snapshot.write_scope_cap - write_reserved, 0)
    return available >= item.required_slots and write_available >= item.required_write_slots


def request_slot(
    snapshot: CapacitySnapshot,
    ledger: CapacityLedger,
    item: ReadyWorkItem,
    model_capacity_denied: bool = False,
    model_name: Optional[str] = None,
) -> ReservationResult:
    if model_capacity_denied:
        event = ModelCapacityEvent(work_id=item.work_id, model=model_name or item.model, reason="model_service_overload")
        queue_ready_work(item, ledger.ready_queue)
        return ReservationResult(
            status="queued",
            item=item,
            slot_allocation=0,
            write_slot_allocation=0,
            events=(event,),
            queue_ref="runtime://current-spawn/P2_capacity_handshake",
        )

    if _can_grant(snapshot, ledger, item):
        ledger.open_records[item.work_id] = DescendantLifecycleRecord(
            work_id=item.work_id,
            parent_work_id=ledger.topology.parent_work_id,
            status=LifecycleStatus.SPAWNED,
            reserved_slots=item.required_slots,
            reserved_write_slots=item.required_write_slots,
        )
        return ReservationResult(
            status="granted",
            item=item,
            slot_allocation=item.required_slots,
            write_slot_allocation=item.required_write_slots,
            events=(),
        )

    event = ThreadSaturationEvent(
        work_id=item.work_id,
        reason="thread_limit_reached",
        available_slots=snapshot.remaining_total_slots,
        required_slots=item.required_slots,
    )
    queue_ready_work(item, ledger.ready_queue)
    return ReservationResult(
        status="queued",
        item=item,
        slot_allocation=0,
        write_slot_allocation=0,
        events=(event,),
        queue_ref="runtime://current-spawn/P2_capacity_handshake",
    )


def record_lifecycle_transition(ledger: CapacityLedger, item_id: Id, new_status: LifecycleStatus) -> DescendantLifecycleRecord:
    current = ledger.open_records.get(item_id)
    if current is None:
        current = DescendantLifecycleRecord(work_id=item_id)
    transition = LifecycleTransitionRecord(work_id=item_id, previous_status=current.status, next_status=new_status)
    del transition
    current.status = new_status
    ledger.open_records[item_id] = current
    return current


def _require_closed_descendant(record: DescendantLifecycleRecord, parent_work_id: Id, failures: List[LifecycleCloseoutFailure]) -> None:
    if record.parent_work_id != parent_work_id:
        return
    if record.status in {LifecycleStatus.DURABLE_RESULT, LifecycleStatus.ERROR}:
        failures.append(LifecycleCloseoutFailure(work_id=record.work_id, detail="terminal_but_open"))
    elif record.status == LifecycleStatus.SPAWNED:
        failures.append(LifecycleCloseoutFailure(work_id=record.work_id, detail="missing_durable_handback"))


def materialize_closeout_packet(
    parent_work_id: Id,
    ledger: CapacityLedger,
    descendants: Sequence[DescendantTopologyReadback],
) -> CloseoutPacket:
    failures: List[LifecycleCloseoutFailure] = []
    calls: List[CloseAgentCallRecord] = []

    provided_ids = {record.work_id for topology in descendants for record in topology.descendants}

    for topology in descendants:
        for record in topology.descendants:
            if record.parent_work_id == parent_work_id and not record.close_readback:
                failures.append(LifecycleCloseoutFailure(work_id=record.work_id, detail="missing_close_readback"))
            if record.status == LifecycleStatus.CLOSED and record.close_readback and record.parent_work_id == parent_work_id:
                calls.append(CloseAgentCallRecord(close_agent_call_token=f"close_agent:{record.work_id}", work_id=record.work_id))
                ledger.open_records.pop(record.work_id, None)
                ledger.reservations.pop(record.work_id, None)
            else:
                _require_closed_descendant(record, parent_work_id, failures)
            if record.parent_work_id == parent_work_id and record.status in {
                LifecycleStatus.DURABLE_RESULT,
                LifecycleStatus.ERROR,
            } and not record.durable_handback:
                failures.append(LifecycleCloseoutFailure(work_id=record.work_id, detail="missing_durable_handback"))

    for known_id, rec in list(ledger.open_records.items()):
        if rec.parent_work_id == parent_work_id and known_id not in provided_ids:
            failures.append(LifecycleCloseoutFailure(work_id=known_id, detail="unknown_descendant"))

    if any(True for _ in ledger.reservations):
        for work_id in ledger.reservations:
            if work_id not in provided_ids:
                failures.append(LifecycleCloseoutFailure(work_id=work_id, detail="reservation_leak"))

    status = "closed" if not failures else "failed"
    return CloseoutPacket(parent_work_id=parent_work_id, close_agent_calls=tuple(calls), failures=tuple(failures), status=status)


def queued_reclaim(snapshot: CapacitySnapshot, ledger: CapacityLedger, closed_work_id: Id) -> QueueResult:
    if closed_work_id not in ledger.open_records:
        return QueueResult(status="unchanged", queued=tuple(ledger.ready_queue), queue_depth=len(ledger.ready_queue))
    ledger.open_records.pop(closed_work_id, None)

    while ledger.ready_queue and _can_grant(snapshot, ledger, ledger.ready_queue[0]):
        item = ledger.ready_queue.pop(0)
        result = request_slot(snapshot, ledger, item)
        if result.status != "granted":
            break

    return QueueResult(status="reclaimed", queued=tuple(ledger.ready_queue), queue_depth=len(ledger.ready_queue))


_CAPACITY_HANDSHAKE_CLI_SCHEMA_ID = "capacity_handshake_cli_v1"
_TOPOLOGY_TARGET_DERIVATION = "declared_team_peak_plus_nested_reservations"
_TOPOLOGY_WITNESS_PREDICATE = "generated_value_matches_topology_witness"


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _load_policy_topology_request(root: Path) -> tuple[Optional[int], str]:
    policy_path = root / "agents" / "capacity_policy.toml"
    try:
        raw = policy_path.read_text(encoding="utf-8")
    except OSError:
        return None, "capacity_policy_unreadable"

    try:
        policy = tomllib.loads(raw)
    except Exception:
        return None, "capacity_policy_malformed"

    topology = policy.get("topology_derivation")
    projection = policy.get("runtime_config_change_policy")
    manifest = policy.get("generated_manifest_policy")
    if not isinstance(topology, dict) or not isinstance(projection, dict) or not isinstance(manifest, dict):
        return None, "capacity_policy_schema_invalid"
    if policy.get("policy_id") != "topology_derived_v1":
        return None, "capacity_policy_schema_invalid"
    if projection.get("target_value_derivation") != _TOPOLOGY_TARGET_DERIVATION:
        return None, "capacity_policy_schema_invalid"
    predicates = projection.get("required_predicates")
    if not isinstance(predicates, list) or _TOPOLOGY_WITNESS_PREDICATE not in predicates:
        return None, "capacity_policy_schema_invalid"
    if manifest.get("numeric_family_default") is not False:
        return None, "capacity_policy_schema_invalid"

    requested = projection.get("target_value")
    if isinstance(requested, bool) or not isinstance(requested, int) or requested <= 0:
        return None, "capacity_policy_schema_invalid"
    return requested, "loaded"


def _print_projection_failure(
    *,
    reason: str,
    root: Path,
    derived: Optional[int],
    configured: Optional[int],
    expected: int,
) -> None:
    evidence = {
        "configured_max_threads": configured,
        "configured_source_ref": str(root / ".codex" / "config.toml"),
        "derived_requested_capacity": derived,
        "evidence_type": "CapacityInputEvidence",
        "expected_max_threads": expected,
        "policy_source_ref": str(root / "agents" / "capacity_policy.toml"),
        "reason": reason,
        "schema_id": _CAPACITY_HANDSHAKE_CLI_SCHEMA_ID,
        "status": "fail",
    }
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="capacity_handshake.py")
    parser.add_argument("--root", required=True, type=Path, metavar="PATH")
    parser.add_argument("--check-config-projection", required=True, action="store_true")
    parser.add_argument("--expected-max-threads", required=True, type=_positive_int, metavar="POSITIVE_INT")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    derived, policy_status = _load_policy_topology_request(root)
    if policy_status != "loaded":
        _print_projection_failure(
            reason=policy_status,
            root=root,
            derived=derived,
            configured=None,
            expected=args.expected_max_threads,
        )
        return 1

    config_evidence = load_max_threads_loader(str(root / ".codex" / "config.toml"))
    if not config_evidence.success:
        _print_projection_failure(
            reason="max_threads_loader_unreadable",
            root=root,
            derived=derived,
            configured=config_evidence.configured_max_threads,
            expected=args.expected_max_threads,
        )
        return 1

    configured = config_evidence.configured_max_threads
    if derived != configured or derived != args.expected_max_threads:
        _print_projection_failure(
            reason="capacity_config_projection_mismatch",
            root=root,
            derived=derived,
            configured=configured,
            expected=args.expected_max_threads,
        )
        return 1

    print("CAPACITY_CONFIG_PROJECTION=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
