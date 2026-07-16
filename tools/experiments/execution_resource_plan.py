#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the immutable ExecutionResourcePlan transaction, canonical GPU allocation, ExperimentRunner handoff, and completion coverage.
# upstream design ../../reports/agents/w1-tool-env-routing-20260716/design_brief.md approved W1-DESIGN-20260716-R3-GPU-COMPLETIONCOVERAGE-REPAIR
# upstream design ../../documents/experiment_runner.md ExperimentRunner lifecycle and scheduler boundary
# upstream design ../../agents/skills/gpu-execution.md UUID GPU and readback contract
# downstream implementation ./run_managed_experiment.py managed experiment adapter
# @dependency-end

"""Canonical execution resource planning for managed ExperimentRunner runs.

This module deliberately owns the complete resource transaction.  Callers may
provide observations and an ExperimentRunner transport, but they cannot add a
second GPU policy, mutate a frozen plan, or fall back to a different execution
mode when the requested allocation is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence, cast

try:
    import fcntl
except ImportError:  # pragma: no cover - this owner is Unix/container-only.
    fcntl = None  # type: ignore[assignment]


PLAN_SCHEMA_VERSION = "execution-resource-plan/v1"
ENVIRONMENT_CERTIFICATE_SCHEMA_VERSION = "environment-certificate/v1"
COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION = "completion-coverage-input/v1"
RUNTIME_ROOT = Path("/var/lib/agent-canon/runtime")
LOCK_ROOT = RUNTIME_ROOT / "locks"
SOURCE_PROJECTION_TEMPLATE = "/workspace/reports/agents/{run_id}/runtime"

GPU_ENVIRONMENT_KEYS = frozenset(
    {
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "JAX_PLATFORMS",
        "XLA_PYTHON_CLIENT_PREALLOCATE",
        "XLA_PYTHON_CLIENT_MEM_FRACTION",
        "XLA_FLAGS",
    }
)
SENSITIVE_ENV_PARTS = (
    "API_KEY",
    "AUTH",
    "CREDENTIAL",
    "KEY",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)


class PlanState(StrEnum):
    RESOURCE_DISCOVERED = "resource_discovered"
    PLAN_FROZEN = "plan_frozen"
    ENV_MATERIALIZED = "env_materialized"
    EFFECTIVE_ENV_READBACK_VERIFIED = "effective_env_readback_verified"
    EXECUTE = "ExperimentRunner execute"
    TERMINAL = "terminal"
    CLEANUP_DISPOSED = "cleanup_disposed"


STATE_SEQUENCE = (
    PlanState.RESOURCE_DISCOVERED,
    PlanState.PLAN_FROZEN,
    PlanState.ENV_MATERIALIZED,
    PlanState.EFFECTIVE_ENV_READBACK_VERIFIED,
    PlanState.EXECUTE,
    PlanState.TERMINAL,
    PlanState.CLEANUP_DISPOSED,
)


class ResourcePlanError(RuntimeError):
    """Base class for typed resource-plan failures."""


class TypedPreflightFailure(ResourcePlanError):
    """A typed failure that must stop before ExperimentRunner execution."""

    def __init__(self, code: str, message: str, **evidence: object) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.evidence = MappingProxyType(dict(evidence))


class EnvironmentReadbackMismatch(ResourcePlanError):
    """The effective runner environment does not equal the frozen plan."""


class CompletionCoverageFailure(ResourcePlanError):
    """Completion coverage was absent or delivered more than once."""


class PlanStateError(ResourcePlanError):
    """A caller attempted to skip or repeat a fixed transaction state."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return cast(Mapping[str, object], _freeze_value(value))


def _is_sensitive_env_key(key: str) -> bool:
    upper = key.upper()
    return any(part in upper for part in SENSITIVE_ENV_PARTS)


def _redacted_environment(env: Mapping[str, str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in sorted(env):
        if _is_sensitive_env_key(key):
            result[key] = {"present": True, "redacted": True}
        else:
            result[key] = env[key]
    return result


@dataclass(frozen=True)
class ProcessIdentity:
    """GPU process identity including PID and process-start identity."""

    pid: int
    process_start_identity: str
    gpu_uuid: str
    kind: str = "compute"


@dataclass(frozen=True)
class GPUDevice:
    uuid: str
    free_memory_bytes: int
    memory_bytes: int = 0
    mig_parent_uuid: str | None = None


class ResourceProbe(Protocol):
    """Read-only runtime observations used for atomic planner rereads."""

    def caller_allocated_ids(self) -> frozenset[str]: ...

    def process_identities(self) -> tuple[ProcessIdentity, ...]: ...

    def free_memory_bytes(self) -> Mapping[str, int]: ...

    def boot_id(self) -> str: ...

    def container_visible_ids(self) -> frozenset[str]: ...


@dataclass(frozen=True)
class SnapshotResourceProbe:
    """Deterministic probe adapter for a scheduler/NVML observation source."""

    allocated: frozenset[str]
    processes: tuple[ProcessIdentity, ...]
    memory: Mapping[str, int]
    current_boot_id: str
    visible: frozenset[str] = frozenset()

    def caller_allocated_ids(self) -> frozenset[str]:
        return self.allocated

    def process_identities(self) -> tuple[ProcessIdentity, ...]:
        return self.processes

    def free_memory_bytes(self) -> Mapping[str, int]:
        return self.memory

    def boot_id(self) -> str:
        return self.current_boot_id

    def container_visible_ids(self) -> frozenset[str]:
        return self.visible


@dataclass(frozen=True)
class ReservationLease:
    """An acquired UUID lease; the open descriptor retains the OS lock."""

    uuid: str
    reservation_id: str
    path: Path
    owner_pid: int
    owner_process_start_identity: str
    boot_id: str
    _descriptor: int = field(repr=False, compare=False)

    def release(self) -> None:
        if self._descriptor < 0:
            return
        if fcntl is not None:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        os.close(self._descriptor)


class UUIDReservationStore:
    """Host-safe, per-UUID flock lease store shared by the planner."""

    def __init__(self, root: Path = LOCK_ROOT) -> None:
        if fcntl is None:
            raise ResourcePlanError("per-UUID flock leases require a Unix runtime")
        self.root = root

    def acquire(
        self,
        uuid: str,
        *,
        owner_pid: int,
        owner_process_start_identity: str,
        boot_id: str,
    ) -> ReservationLease | None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"gpu-{_safe_uuid_filename(uuid)}.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            os.close(descriptor)
            return None
        reservation_id = f"reservation-{secrets.token_hex(12)}"
        record = {
            "schema_version": "gpu-reservation/v1",
            "reservation_id": reservation_id,
            "uuid": uuid,
            "owner_pid": owner_pid,
            "owner_process_start_identity": owner_process_start_identity,
            "boot_id": boot_id,
            "acquired_at": utc_now(),
        }
        os.ftruncate(descriptor, 0)
        os.write(descriptor, _canonical_json(record).encode("utf-8"))
        os.fsync(descriptor)
        return ReservationLease(
            uuid=uuid,
            reservation_id=reservation_id,
            path=path,
            owner_pid=owner_pid,
            owner_process_start_identity=owner_process_start_identity,
            boot_id=boot_id,
            _descriptor=descriptor,
        )

    def reclaim_stale(
        self,
        uuid: str,
        *,
        current_boot_id: str,
        gpu_processes: Sequence[ProcessIdentity],
        process_start_identity: Callable[[int], str | None],
    ) -> bool:
        """Reclaim only after boot, dead-owner, and no-GPU-process proof."""
        path = self.root / f"gpu-{_safe_uuid_filename(uuid)}.lock"
        if not path.is_file():
            return False
        try:
            record = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return False
        if record.get("boot_id") != current_boot_id:
            return False
        owner_pid = record.get("owner_pid")
        owner_start = record.get("owner_process_start_identity")
        if not isinstance(owner_pid, int) or not isinstance(owner_start, str):
            return False
        if process_start_identity(owner_pid) == owner_start:
            return False
        if any(process.gpu_uuid == uuid for process in gpu_processes):
            return False
        descriptor = os.open(path, os.O_RDWR)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            os.close(descriptor)
            return False
        try:
            current = json.loads(os.read(descriptor, 1024 * 1024) or b"{}")
            if current != record:
                return False
            os.ftruncate(descriptor, 0)
            os.fsync(descriptor)
            return True
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _safe_uuid_filename(uuid: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in uuid)


def _is_gpu_index(value: str) -> bool:
    return value.isdecimal()


@dataclass(frozen=True)
class ResourceRequest:
    owner_id: str
    parent_id: str
    context_id: str
    maximum_timeout_seconds: float
    argv: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str]
    plan_id: str = ""
    cpu_requested_set: tuple[int, ...] = ()
    gpu_requested_count: int = 0
    gpu_requested_memory_bytes: int = 0
    host_memory_bytes: int = 0
    temp_bytes: int = 0
    ports: tuple[Mapping[str, object], ...] = ()
    xla_jax_preallocation_values: Mapping[str, str] = field(default_factory=dict)
    runtime_root: Path = RUNTIME_ROOT
    source_projection_root: Path | None = None
    run_id: str = ""
    requested_chunks: tuple[str, ...] = ()
    lock_root: Path = LOCK_ROOT
    owner_process_start_identity: str = "unknown"
    resource_probe: ResourceProbe | None = field(default=None, repr=False, compare=False)
    discovered_cpu_available_set: tuple[int, ...] = ()
    discovered_gpu_devices: tuple[GPUDevice, ...] = ()
    discovered_reserved_ids: frozenset[str] = frozenset()
    discovered_host_memory_bytes: int = 0
    discovered_temp_bytes: int = 0
    discovered_ports: tuple[Mapping[str, object], ...] = ()
    discovered_container_id: str = ""
    discovered_structure_tool: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.maximum_timeout_seconds <= 0:
            raise ValueError("maximum_timeout_seconds must be positive")
        if self.gpu_requested_count < 0 or self.gpu_requested_memory_bytes < 0:
            raise ValueError("GPU requirements cannot be negative")
        if not self.argv:
            raise ValueError("argv must not be empty")
        if self.source_projection_root is None:
            run_id = self.run_id or self.plan_id or "unassigned"
            object.__setattr__(
                self,
                "source_projection_root",
                Path(SOURCE_PROJECTION_TEMPLATE.format(run_id=run_id)),
            )


@dataclass(frozen=True)
class DiscoveredResources:
    cpu_available_set: tuple[int, ...]
    gpu_devices: tuple[GPUDevice, ...]
    caller_allocated_ids: frozenset[str]
    occupied_processes: tuple[ProcessIdentity, ...]
    reserved_ids: frozenset[str]
    host_memory_bytes: int
    temp_bytes: int
    ports: tuple[Mapping[str, object], ...]
    container_id: str
    structure_tool: Mapping[str, str]
    boot_id: str
    probe: ResourceProbe
    reservation_store: UUIDReservationStore
    observed_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class GPUAllocation:
    plan_fingerprint: str
    caller_allocated_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    occupied_ids: tuple[str, ...]
    reserved_ids: tuple[str, ...]
    eligible_ids: tuple[str, ...]
    selected_ids: tuple[str, ...]
    reservation_ids: tuple[str, ...]
    free_memory_bytes: Mapping[str, int]
    process_identities: tuple[ProcessIdentity, ...]
    allocation_id: str
    lock_root: Path
    selection_order: tuple[str, ...]
    memory_bytes: Mapping[str, int]
    slot_id: str | None
    leases: tuple[ReservationLease, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "free_memory_bytes", _freeze_mapping(self.free_memory_bytes))
        object.__setattr__(self, "memory_bytes", _freeze_mapping(self.memory_bytes))


@dataclass(frozen=True)
class ExecutionResourcePlan:
    schema_version: str
    plan_id: str
    plan_fingerprint: str
    owner: Mapping[str, object]
    resources: Mapping[str, object]
    execution: Mapping[str, object]
    container: Mapping[str, object]
    side_effect_inventory: tuple[Mapping[str, object], ...]
    readback: Mapping[str, object]
    evidence: Mapping[str, object]
    state: PlanState
    state_history: tuple[PlanState, ...]
    gpu_allocation: GPUAllocation
    resource_probe: ResourceProbe = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("owner", "resources", "execution", "container", "readback", "evidence"):
            object.__setattr__(self, name, _freeze_mapping(cast(Mapping[str, object], getattr(self, name))))

    def json_spec(self) -> dict[str, object]:
        """Return the immutable, non-secret-safe spec used by the fingerprint."""
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "owner": dict(self.owner),
            "resources": _json_safe(self.resources),
            "execution": _json_safe(self.execution),
            "container": _json_safe(self.container),
            "side_effect_inventory": _json_safe(self.side_effect_inventory),
        }


@dataclass(frozen=True)
class MaterializedEnvironment:
    plan_fingerprint: str
    exact_env_map: Mapping[str, str]
    persisted_env_map: Mapping[str, object]
    cuda_visible_devices_uuid_list: tuple[str, ...]
    xla_jax_preallocation_values: Mapping[str, str]
    cwd: Path
    argv: tuple[str, ...]
    runtime_root: Path
    run_root: Path
    log_root: Path
    source_projection_root: Path
    state: PlanState = PlanState.ENV_MATERIALIZED

    def __post_init__(self) -> None:
        object.__setattr__(self, "exact_env_map", _freeze_mapping(self.exact_env_map))
        object.__setattr__(self, "persisted_env_map", _freeze_mapping(self.persisted_env_map))
        object.__setattr__(self, "xla_jax_preallocation_values", _freeze_mapping(self.xla_jax_preallocation_values))


@dataclass(frozen=True)
class EffectiveEnvironmentReadback:
    environment: Mapping[str, str]
    cwd: Path
    argv: tuple[str, ...]
    visible_gpu_ids: tuple[str, ...] = ()
    cpu_set: tuple[int, ...] = ()
    container_id: str = ""
    readback_timestamp: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class EnvironmentCertificate:
    schema_version: str
    plan_fingerprint: str
    container_id: str
    runtime_identity: str
    cwd_equal: bool
    argv_equal: bool
    non_secret_env_equal: bool
    redacted_secret_witness: tuple[Mapping[str, object], ...]
    visible_gpu_ids_equal: bool
    cpu_set_equal: bool
    runtime_root: Path
    source_projection_root: Path
    tree_capability: Mapping[str, str]
    os_side_effect_inventory_ref: str
    readback_timestamp: str
    state: PlanState = PlanState.EFFECTIVE_ENV_READBACK_VERIFIED


@dataclass(frozen=True)
class PreLaunchContext:
    plan_fingerprint: str
    transport_payload: Mapping[str, object]
    readback_fingerprint: str
    state: PlanState = PlanState.EFFECTIVE_ENV_READBACK_VERIFIED


class ExperimentRunnerExecutionPort(Protocol):
    def execute(
        self,
        *,
        plan: ExecutionResourcePlan,
        task: Callable[..., object],
        cases: list[object],
        context_builder: Callable[..., object],
        initializer: Callable[..., object],
        resource_estimator: Callable[..., object],
        skip_controller: object | None,
    ) -> object: ...


class RunnerTransport(Protocol):
    def __call__(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class TerminalEvidence:
    plan_fingerprint: str
    terminal_event_id: str
    execution_result: object | None
    no_completion: Mapping[str, object] | None
    stdout_path: str | None
    stderr_path: str | None
    startup_log_path: str | None
    run_log_path: str | None
    artifact_manifest_path: str | None
    source_snapshot: Mapping[str, object]
    terminal_timestamp: str
    state: PlanState = PlanState.TERMINAL


@dataclass(frozen=True)
class CleanupEvidence:
    plan_fingerprint: str
    side_effects: tuple[Mapping[str, object], ...]
    leak_or_unknown: tuple[Mapping[str, object], ...]
    descendant_retained_gpu_ids: tuple[str, ...]
    disposed_at: str
    state: PlanState = PlanState.CLEANUP_DISPOSED


@dataclass(frozen=True)
class CompletionCoverageInput:
    schema_version: str
    plan_fingerprint: str
    terminal_event_id: str
    candidate_gpu_ids: tuple[str, ...]
    occupied_gpu_ids: tuple[Mapping[str, object], ...]
    reserved_gpu_ids: tuple[str, ...]
    selected_gpu_ids: tuple[str, ...]
    lock_readback: Mapping[str, object]
    effective_env: Mapping[str, object]
    actual_gpu_processes: tuple[Mapping[str, object], ...]
    release_retention_disposition: Mapping[str, object]
    concurrent_run_evidence: Mapping[str, object]
    mig_evidence: Mapping[str, object]
    container_visible_uuid_mapping: Mapping[str, object]
    os_safe_lock_placement: Mapping[str, object]
    descendant_retention_evidence: Mapping[str, object]
    taxonomy_linked_validation_outcome: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.schema_version != COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported CompletionCoverageInput schema")
        for name in (
            "lock_readback",
            "effective_env",
            "release_retention_disposition",
            "concurrent_run_evidence",
            "mig_evidence",
            "container_visible_uuid_mapping",
            "os_safe_lock_placement",
            "descendant_retention_evidence",
            "taxonomy_linked_validation_outcome",
        ):
            object.__setattr__(self, name, _freeze_mapping(cast(Mapping[str, object], getattr(self, name))))


@dataclass(frozen=True)
class CompletionCoverage:
    schema_version: str
    plan_fingerprint: str
    terminal_event_id: str
    delivery_ordinal: int
    input_record: CompletionCoverageInput
    recorded_at: str


@dataclass
class CompletionCoverageAdapter:
    """Projection-only, exactly-once CompletionCoverage owner."""

    _records: dict[tuple[str, str], CompletionCoverage] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record_once(self, input: CompletionCoverageInput) -> CompletionCoverage:
        key = (input.plan_fingerprint, input.terminal_event_id)
        with self._lock:
            if key in self._records:
                raise CompletionCoverageFailure(
                    "duplicate CompletionCoverage delivery",
                )
            record = CompletionCoverage(
                schema_version=COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
                plan_fingerprint=input.plan_fingerprint,
                terminal_event_id=input.terminal_event_id,
                delivery_ordinal=1,
                input_record=input,
                recorded_at=utc_now(),
            )
            self._records[key] = record
            return record

    def require_record(self, plan_fingerprint: str, terminal_event_id: str) -> CompletionCoverage:
        try:
            return self._records[(plan_fingerprint, terminal_event_id)]
        except KeyError as exc:
            raise CompletionCoverageFailure(
                "missing CompletionCoverage delivery",
            ) from exc


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, ProcessIdentity):
        return {
            "pid": value.pid,
            "process_start_identity": value.process_start_identity,
            "gpu_uuid": value.gpu_uuid,
            "kind": value.kind,
        }
    if isinstance(value, GPUDevice):
        return {
            "uuid": value.uuid,
            "free_memory_bytes": value.free_memory_bytes,
            "memory_bytes": value.memory_bytes,
            "mig_parent_uuid": value.mig_parent_uuid,
        }
    raise TypeError(f"value is not JSON serializable: {type(value)!r}")


def _process_start_identity(pid: int) -> str:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    fields = stat.rsplit(")", 1)[-1].split()
    return fields[19] if len(fields) > 19 else "unknown"


def discover_resources(request: ResourceRequest) -> DiscoveredResources:
    """Capture the declared capability boundary before the plan is frozen."""
    if request.resource_probe is None:
        raise TypedPreflightFailure(
            "resource_probe_unavailable",
            "resource discovery requires the declared scheduler/NVML probe",
        )
    return discover_resources_from_probe(
        request,
        request.resource_probe,
        cpu_available_set=request.discovered_cpu_available_set,
        gpu_devices=request.discovered_gpu_devices,
        reserved_ids=request.discovered_reserved_ids,
        host_memory_bytes=request.discovered_host_memory_bytes,
        temp_bytes=request.discovered_temp_bytes,
        ports=request.discovered_ports,
        container_id=request.discovered_container_id,
        structure_tool=request.discovered_structure_tool,
    )


def discover_resources_from_probe(
    request: ResourceRequest,
    probe: ResourceProbe,
    *,
    cpu_available_set: Sequence[int] = (),
    gpu_devices: Sequence[GPUDevice] = (),
    reserved_ids: frozenset[str] = frozenset(),
    host_memory_bytes: int = 0,
    temp_bytes: int = 0,
    ports: Sequence[Mapping[str, object]] = (),
    container_id: str = "",
    structure_tool: Mapping[str, str] | None = None,
) -> DiscoveredResources:
    """Materialize one explicit discovery snapshot without fallback probing."""
    return DiscoveredResources(
        cpu_available_set=tuple(sorted(cpu_available_set)),
        gpu_devices=tuple(sorted(gpu_devices, key=lambda device: device.uuid)),
        caller_allocated_ids=frozenset(probe.caller_allocated_ids()),
        occupied_processes=tuple(probe.process_identities()),
        reserved_ids=frozenset(reserved_ids),
        host_memory_bytes=host_memory_bytes,
        temp_bytes=temp_bytes,
        ports=tuple(ports),
        container_id=container_id,
        structure_tool=MappingProxyType(dict(structure_tool or {})),
        boot_id=probe.boot_id(),
        probe=probe,
        reservation_store=UUIDReservationStore(request.lock_root),
    )


def _gpu_preflight(code: str, message: str, **evidence: object) -> TypedPreflightFailure:
    return TypedPreflightFailure(code, message, **evidence)


def plan_gpu_allocation(
    request: ResourceRequest,
    discovered: DiscoveredResources,
) -> GPUAllocation:
    """Select and reserve only eligible caller-allocated UUIDs.

    The algorithm is intentionally stable and unweighted: A is the caller
    allocation, O_t is the live GPU process set, R_t is the reservation set,
    and E_t is the hard-memory-filtered remainder.  Every selected UUID is
    locked and reread before it is accepted.
    """
    requested = request.gpu_requested_count
    if requested == 0:
        return GPUAllocation(
            plan_fingerprint="pending",
            caller_allocated_ids=(),
            candidate_ids=(),
            occupied_ids=(),
            reserved_ids=(),
            eligible_ids=(),
            selected_ids=(),
            reservation_ids=(),
            free_memory_bytes={},
            process_identities=(),
            allocation_id="none",
            lock_root=request.lock_root,
            selection_order=(),
            memory_bytes={},
            slot_id=None,
            leases=(),
        )
    caller_ids = tuple(sorted(discovered.caller_allocated_ids))
    if len(caller_ids) < requested:
        raise _gpu_preflight(
            "gpu_cardinality_unavailable",
            "caller allocation cannot satisfy requested GPU cardinality",
            requested_count=requested,
            caller_allocated_ids=caller_ids,
        )
    device_by_id = {device.uuid: device for device in discovered.gpu_devices}
    candidate_ids = tuple(uuid for uuid in caller_ids if uuid in device_by_id)
    if any(_is_gpu_index(uuid) for uuid in candidate_ids):
        raise _gpu_preflight(
            "gpu_uuid_required",
            "GPU allocation must use UUIDs rather than device indices",
            candidate_ids=candidate_ids,
        )
    occupied_ids = tuple(sorted({process.gpu_uuid for process in discovered.occupied_processes}))
    reserved_ids_seen = set(discovered.reserved_ids)
    reserved_ids = tuple(sorted(reserved_ids_seen))
    free_memory = dict(discovered.probe.free_memory_bytes())
    eligible_ids = tuple(
        uuid
        for uuid in candidate_ids
        if uuid not in occupied_ids
        and uuid not in reserved_ids
        and free_memory.get(uuid, device_by_id[uuid].free_memory_bytes)
        >= request.gpu_requested_memory_bytes
    )
    leases: list[ReservationLease] = []
    selected: list[str] = []
    reread_processes: tuple[ProcessIdentity, ...] = discovered.occupied_processes
    try:
        for uuid in eligible_ids:
            if len(selected) == requested:
                break
            lease = discovered.reservation_store.acquire(
                uuid,
                owner_pid=os.getpid(),
                owner_process_start_identity=request.owner_process_start_identity
                if request.owner_process_start_identity != "unknown"
                else _process_start_identity(os.getpid()),
                boot_id=discovered.probe.boot_id(),
            )
            if lease is None:
                reserved_ids_seen.add(uuid)
                continue
            reread_allocated = discovered.probe.caller_allocated_ids()
            reread_processes = tuple(discovered.probe.process_identities())
            reread_memory = discovered.probe.free_memory_bytes()
            raced = (
                uuid not in reread_allocated
                or any(process.gpu_uuid == uuid for process in reread_processes)
                or uuid in reserved_ids_seen
                or reread_memory.get(uuid, 0) < request.gpu_requested_memory_bytes
            )
            if raced:
                lease.release()
                continue
            leases.append(lease)
            selected.append(uuid)
            free_memory[uuid] = reread_memory.get(uuid, free_memory.get(uuid, 0))
        if len(selected) != requested:
            raise _gpu_preflight(
                "gpu_memory_or_lease_unavailable",
                "eligible UUID cardinality was lost during atomic lease/readback",
                requested_count=requested,
                candidate_ids=candidate_ids,
                occupied_ids=occupied_ids,
                reserved_ids=tuple(sorted(reserved_ids_seen)),
                eligible_ids=eligible_ids,
                selected_ids=tuple(selected),
                requested_memory_bytes=request.gpu_requested_memory_bytes,
            )
    except Exception:
        for lease in leases:
            lease.release()
        raise
    allocation_id = f"allocation-{secrets.token_hex(12)}"
    return GPUAllocation(
        plan_fingerprint="pending",
        caller_allocated_ids=caller_ids,
        candidate_ids=candidate_ids,
        occupied_ids=occupied_ids,
        reserved_ids=tuple(sorted(reserved_ids_seen)),
        eligible_ids=eligible_ids,
        selected_ids=tuple(selected),
        reservation_ids=tuple(lease.reservation_id for lease in leases),
        free_memory_bytes={uuid: free_memory[uuid] for uuid in selected},
        process_identities=reread_processes,
        allocation_id=allocation_id,
        lock_root=request.lock_root,
        selection_order=eligible_ids,
        memory_bytes={uuid: device_by_id[uuid].memory_bytes for uuid in selected},
        slot_id=None,
        leases=tuple(leases),
    )


def _allocation_with_fingerprint(allocation: GPUAllocation, fingerprint: str) -> GPUAllocation:
    return GPUAllocation(
        plan_fingerprint=fingerprint,
        caller_allocated_ids=allocation.caller_allocated_ids,
        candidate_ids=allocation.candidate_ids,
        occupied_ids=allocation.occupied_ids,
        reserved_ids=allocation.reserved_ids,
        eligible_ids=allocation.eligible_ids,
        selected_ids=allocation.selected_ids,
        reservation_ids=allocation.reservation_ids,
        free_memory_bytes=allocation.free_memory_bytes,
        process_identities=allocation.process_identities,
        allocation_id=allocation.allocation_id,
        lock_root=allocation.lock_root,
        selection_order=allocation.selection_order,
        memory_bytes=allocation.memory_bytes,
        slot_id=allocation.slot_id,
        leases=allocation.leases,
    )


def freeze_resource_plan(
    request: ResourceRequest,
    discovered: DiscoveredResources,
    gpu_allocation: GPUAllocation,
) -> ExecutionResourcePlan:
    """Seal the immutable resource/environment/argv/cwd contract."""
    if gpu_allocation.plan_fingerprint not in ("", "pending"):
        raise PlanStateError("GPU allocation is already bound to another plan")
    plan_id = request.plan_id or request.run_id or f"plan-{secrets.token_hex(12)}"
    selected_ids = tuple(gpu_allocation.selected_ids)
    exact_environment = dict(request.environment)
    if request.gpu_requested_count:
        exact_environment["CUDA_VISIBLE_DEVICES"] = ",".join(selected_ids)
        exact_environment["NVIDIA_VISIBLE_DEVICES"] = ",".join(selected_ids)
    elif any(key in exact_environment for key in GPU_ENVIRONMENT_KEYS) or request.xla_jax_preallocation_values:
        raise _gpu_preflight(
            "gpu_environment_without_request",
            "GPU environment cannot be injected for a GPU-unrequested plan",
            keys=tuple(sorted(set(key for key in exact_environment if key in GPU_ENVIRONMENT_KEYS) | set(request.xla_jax_preallocation_values))),
        )
    for key, value in request.xla_jax_preallocation_values.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypedPreflightFailure("invalid_environment_packet", "environment values must be strings")
        exact_environment[key] = value
    if request.gpu_requested_count and not selected_ids:
        raise _gpu_preflight("gpu_selection_empty", "GPU request has no selected UUIDs")
    allocation = _allocation_with_fingerprint(gpu_allocation, "pending")
    runtime_root = request.runtime_root
    run_root = runtime_root / "runs" / plan_id
    log_root = run_root / "logs"
    source_projection = cast(Path, request.source_projection_root)
    resources = {
        "cpu": {"requested_set": request.cpu_requested_set, "allocated_set": discovered.cpu_available_set, "affinity_id": None},
        "gpu": {
            "requested_count": request.gpu_requested_count,
            "requested_memory_bytes": request.gpu_requested_memory_bytes,
            "caller_allocated_ids": gpu_allocation.caller_allocated_ids,
            "candidate_ids": gpu_allocation.candidate_ids,
            "occupied_ids": gpu_allocation.occupied_ids,
            "reserved_ids": gpu_allocation.reserved_ids,
            "eligible_ids": gpu_allocation.eligible_ids,
            "selected_ids": gpu_allocation.selected_ids,
            "visible_ids": gpu_allocation.selected_ids,
            "allocation_id": gpu_allocation.allocation_id,
            "reservation_ids": gpu_allocation.reservation_ids,
            "free_memory_bytes": gpu_allocation.free_memory_bytes,
            "process_identities": gpu_allocation.process_identities,
            "lock_root": str(gpu_allocation.lock_root),
            "selection_order": gpu_allocation.selection_order,
            "memory_bytes": gpu_allocation.memory_bytes,
            "slot_id": gpu_allocation.slot_id,
        },
        "memory": {
            "host_bytes": discovered.host_memory_bytes,
            "gpu_bytes": gpu_allocation.memory_bytes,
            "temp_bytes": discovered.temp_bytes,
            "enforcement_mode": "hard_preflight",
        },
        "temp": {
            "runtime_root": str(runtime_root),
            "run_root": str(run_root),
            "log_root": str(log_root),
            "quota_bytes": request.temp_bytes,
            "disposal_policy": "record_every_side_effect",
        },
        "ports": discovered.ports,
    }
    owner = {
        "owner_id": request.owner_id,
        "parent_id": request.parent_id,
        "context_id": request.context_id,
        "maximum_timeout_seconds": request.maximum_timeout_seconds,
    }
    execution = {
        "cwd": str(request.cwd.absolute()),
        "argv": request.argv,
        "env": exact_environment,
        "owner_maximum_timeout_seconds": request.maximum_timeout_seconds,
        "idle_policy": "observe_and_wait",
        "force_stop_policy": "no_idle_force_stop; runner_deadline_owner_only",
        "gpu_force_kill_policy": "never",
        "requested_chunks": request.requested_chunks,
    }
    container = {
        "runtime_root": str(runtime_root),
        "source_projection_root": str(source_projection),
        "structure_tool": "tree",
        "container_id": discovered.container_id,
        "boot_id": discovered.boot_id,
    }
    side_effects = (
        {"id": "workspace-bind", "target": "/workspace", "policy": "allowed_source_bound_readback"},
        {"id": "runtime-root", "target": str(runtime_root), "policy": "container-local"},
        {"id": "run-root", "target": str(run_root), "policy": "container-local"},
        {"id": "log-root", "target": str(log_root), "policy": "container-local"},
        {"id": "source-projection", "target": str(source_projection), "policy": "controlled_source_bound"},
        {"id": "gpu-leases", "target": str(request.lock_root), "policy": "shared_scheduler_visibility"},
    )
    spec = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": plan_id,
        "owner": owner,
        "resources": resources,
        "execution": execution,
        "container": container,
        "side_effect_inventory": side_effects,
    }
    fingerprint = hashlib.sha256(_canonical_json(_json_safe(spec)).encode("utf-8")).hexdigest()
    allocation = _allocation_with_fingerprint(gpu_allocation, fingerprint)
    return ExecutionResourcePlan(
        schema_version=PLAN_SCHEMA_VERSION,
        plan_id=plan_id,
        plan_fingerprint=fingerprint,
        owner=owner,
        resources=resources,
        execution=execution,
        container=container,
        side_effect_inventory=side_effects,
        readback={"non_secret_equal": False, "secret_witness": (), "observed_cwd": None, "observed_argv": ()},
        evidence={"terminal": None, "partial": None, "cleanup": None},
        state=PlanState.PLAN_FROZEN,
        state_history=(PlanState.RESOURCE_DISCOVERED, PlanState.PLAN_FROZEN),
        gpu_allocation=allocation,
        resource_probe=discovered.probe,
    )


def materialize_environment(plan: ExecutionResourcePlan) -> MaterializedEnvironment:
    """Materialize exactly the sealed packet and container-local side effects."""
    _require_state(plan, PlanState.PLAN_FROZEN)
    env = dict(cast(Mapping[str, str], plan.execution["env"]))
    run_root = Path(cast(str, plan.resources["temp"]["run_root"]))
    log_root = Path(cast(str, plan.resources["temp"]["log_root"]))
    runtime_root = Path(cast(str, plan.resources["temp"]["runtime_root"]))
    source_projection = Path(cast(str, plan.container["source_projection_root"]))
    run_root.mkdir(parents=True, exist_ok=True)
    log_root.mkdir(parents=True, exist_ok=True)
    source_projection.mkdir(parents=True, exist_ok=True)
    environment_path = run_root / "environment.json"
    environment_path.write_text(
        _canonical_json(
            {
                "schema_version": 1,
                "plan_fingerprint": plan.plan_fingerprint,
                "environment": _redacted_environment(env),
                "cwd": str(plan.execution["cwd"]),
                "argv": plan.execution["argv"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return MaterializedEnvironment(
        plan_fingerprint=plan.plan_fingerprint,
        exact_env_map=env,
        persisted_env_map=_redacted_environment(env),
        cuda_visible_devices_uuid_list=plan.gpu_allocation.selected_ids,
        xla_jax_preallocation_values={
            key: value
            for key, value in env.items()
            if key.startswith(("JAX_", "XLA_"))
        },
        cwd=Path(cast(str, plan.execution["cwd"])),
        argv=tuple(cast(Sequence[str], plan.execution["argv"])),
        runtime_root=runtime_root,
        run_root=run_root,
        log_root=log_root,
        source_projection_root=source_projection,
    )


def verify_effective_environment(
    plan: ExecutionResourcePlan,
    readback: EffectiveEnvironmentReadback,
) -> EnvironmentCertificate:
    """Prove effective env/cwd/argv/UUID equality before runner execution."""
    _require_state(plan, PlanState.PLAN_FROZEN)
    expected = cast(Mapping[str, str], plan.execution["env"])
    observed = readback.environment
    secret_witness = tuple(
        {
            "key": key,
            "present": key in observed,
            "redacted": True,
            "equality": key in observed and observed[key] == expected[key],
        }
        for key in sorted(expected)
        if _is_sensitive_env_key(key)
    )
    non_secret_equal = all(
        key in observed and observed[key] == value
        for key, value in expected.items()
        if not _is_sensitive_env_key(key)
    ) and all(key in expected for key in observed if not _is_sensitive_env_key(key))
    secret_equal = all(bool(item["equality"]) for item in secret_witness)
    cwd_equal = readback.cwd == Path(cast(str, plan.execution["cwd"]))
    argv_equal = tuple(readback.argv) == tuple(cast(Sequence[str], plan.execution["argv"]))
    visible_expected = tuple(plan.gpu_allocation.selected_ids)
    visible_equal = tuple(readback.visible_gpu_ids) == visible_expected
    if not (non_secret_equal and secret_equal and cwd_equal and argv_equal and visible_equal):
        raise EnvironmentReadbackMismatch(
            "effective environment readback does not match the immutable plan"
        )
    return EnvironmentCertificate(
        schema_version=ENVIRONMENT_CERTIFICATE_SCHEMA_VERSION,
        plan_fingerprint=plan.plan_fingerprint,
        container_id=readback.container_id,
        runtime_identity=str(plan.container.get("container_id", "")),
        cwd_equal=cwd_equal,
        argv_equal=argv_equal,
        non_secret_env_equal=non_secret_equal,
        redacted_secret_witness=secret_witness,
        visible_gpu_ids_equal=visible_equal,
        cpu_set_equal=readback.cpu_set == tuple(cast(Sequence[int], plan.resources["cpu"]["allocated_set"])),
        runtime_root=Path(cast(str, plan.container["runtime_root"])),
        source_projection_root=Path(cast(str, plan.container["source_projection_root"])),
        tree_capability={"command": "tree", "version": str(plan.container.get("tree_version", "unknown")), "structure_contract_ref": "documents/repo-structure-contract.toml"},
        os_side_effect_inventory_ref=f"{plan.plan_fingerprint}:side_effect_inventory",
        readback_timestamp=readback.readback_timestamp,
    )


def _environment_readback_fingerprint(environment: MaterializedEnvironment, allocation: GPUAllocation) -> str:
    packet = {
        "environment": dict(environment.exact_env_map),
        "cwd": str(environment.cwd),
        "argv": environment.argv,
        "selected_ids": allocation.selected_ids,
        "allocation_id": allocation.allocation_id,
        "reservation_ids": allocation.reservation_ids,
    }
    return hashlib.sha256(_canonical_json(_json_safe(packet)).encode("utf-8")).hexdigest()


@dataclass
class ExperimentRunnerPreLaunchAdapter:
    """The sole pre-launch transport adapter; it never selects or rewrites GPUs."""

    _transported_plan_fingerprints: set[str] = field(default_factory=set)

    def pre_launch(
        self,
        plan: ExecutionResourcePlan,
        canonical_environment: MaterializedEnvironment,
        gpu_allocation: GPUAllocation,
        runner_transport: RunnerTransport,
    ) -> PreLaunchContext:
        _require_state(plan, PlanState.PLAN_FROZEN)
        if canonical_environment.plan_fingerprint != plan.plan_fingerprint:
            raise EnvironmentReadbackMismatch("environment packet fingerprint mismatch")
        if gpu_allocation != plan.gpu_allocation:
            raise PlanStateError("pre-launch allocation is not the frozen allocation")
        if plan.plan_fingerprint in self._transported_plan_fingerprints:
            raise PlanStateError("ExperimentRunner pre-launch adapter called twice")
        readback_fingerprint = _environment_readback_fingerprint(canonical_environment, gpu_allocation)
        payload = {
            "canonical_environment": {
                "plan_fingerprint": plan.plan_fingerprint,
                "exact_env_map": dict(canonical_environment.exact_env_map),
                "cuda_visible_devices_uuid_list": canonical_environment.cuda_visible_devices_uuid_list,
                "xla_jax_preallocation_values": dict(canonical_environment.xla_jax_preallocation_values),
                "cwd": str(canonical_environment.cwd),
                "argv": canonical_environment.argv,
            },
            "gpu_allocation": {
                "plan_fingerprint": plan.plan_fingerprint,
                "selected_ids": gpu_allocation.selected_ids,
                "caller_allocated_ids": gpu_allocation.caller_allocated_ids,
                "reservation_ids": gpu_allocation.reservation_ids,
                "allocation_id": gpu_allocation.allocation_id,
            },
            "handoff_metadata": {
                "plan_fingerprint": plan.plan_fingerprint,
                "allocation_id": gpu_allocation.allocation_id,
                "reservation_ids": gpu_allocation.reservation_ids,
                "readback_fingerprint": readback_fingerprint,
            },
        }
        acknowledgement = runner_transport(payload)
        if acknowledgement.get("plan_fingerprint", plan.plan_fingerprint) != plan.plan_fingerprint:
            raise EnvironmentReadbackMismatch("runner transport changed the plan fingerprint")
        if acknowledgement.get("readback_fingerprint", readback_fingerprint) != readback_fingerprint:
            raise EnvironmentReadbackMismatch("runner transport changed the environment packet")
        self._transported_plan_fingerprints.add(plan.plan_fingerprint)
        return PreLaunchContext(
            plan_fingerprint=plan.plan_fingerprint,
            transport_payload=payload,
            readback_fingerprint=readback_fingerprint,
        )


def execute_with_experiment_runner(
    plan: ExecutionResourcePlan,
    pre_launch_context: PreLaunchContext,
    runner_port: ExperimentRunnerExecutionPort,
    *,
    task: Callable[..., object],
    cases: list[object],
    context_builder: Callable[..., object],
    initializer: Callable[..., object],
    resource_estimator: Callable[..., object],
    skip_controller: object | None = None,
) -> object:
    """Execute through the external ExperimentRunner port only."""
    if pre_launch_context.plan_fingerprint != plan.plan_fingerprint:
        raise PlanStateError("runner context does not belong to the frozen plan")
    return runner_port.execute(
        plan=plan,
        task=task,
        cases=cases,
        context_builder=context_builder,
        initializer=initializer,
        resource_estimator=resource_estimator,
        skip_controller=skip_controller,
    )


def record_terminal(
    plan: ExecutionResourcePlan,
    execution_result: object | None,
    *,
    terminal_event_id: str,
    no_completion: Mapping[str, object] | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
    startup_log_path: str | None = None,
    run_log_path: str | None = None,
    artifact_manifest_path: str | None = None,
    source_snapshot: Mapping[str, object] | None = None,
) -> TerminalEvidence:
    """Record terminal or structured no-completion evidence without success inference."""
    _require_state(plan, PlanState.PLAN_FROZEN)
    if execution_result is None and no_completion is None:
        raise ResourcePlanError("terminal evidence requires ExecutionResult or no-completion")
    return TerminalEvidence(
        plan_fingerprint=plan.plan_fingerprint,
        terminal_event_id=terminal_event_id,
        execution_result=execution_result,
        no_completion=no_completion,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        startup_log_path=startup_log_path,
        run_log_path=run_log_path,
        artifact_manifest_path=artifact_manifest_path,
        source_snapshot=source_snapshot or {},
        terminal_timestamp=utc_now(),
    )


def dispose_resources(
    plan: ExecutionResourcePlan,
    terminal: TerminalEvidence,
) -> CleanupEvidence:
    """Release only resources proven free; retain descendants without force-kill."""
    if terminal.plan_fingerprint != plan.plan_fingerprint:
        raise PlanStateError("terminal evidence does not belong to the frozen plan")
    current_processes = tuple(plan.resource_probe.process_identities())
    retained = tuple(
        uuid
        for uuid in plan.gpu_allocation.selected_ids
        if any(process.gpu_uuid == uuid for process in current_processes)
    )
    side_effects: list[Mapping[str, object]] = []
    leaks: list[Mapping[str, object]] = []
    for lease in plan.gpu_allocation.leases:
        if lease.uuid in retained:
            disposition = {"uuid": lease.uuid, "action": "retained", "reason": "descendant_gpu_process_present"}
            leaks.append(disposition)
        else:
            lease.release()
            disposition = {"uuid": lease.uuid, "action": "released", "reservation_id": lease.reservation_id}
        side_effects.append(disposition)
    for side_effect in plan.side_effect_inventory:
        side_effects.append({"id": side_effect["id"], "action": "disposed_or_recorded", "timestamp": utc_now()})
    return CleanupEvidence(
        plan_fingerprint=plan.plan_fingerprint,
        side_effects=tuple(side_effects),
        leak_or_unknown=tuple(leaks),
        descendant_retained_gpu_ids=retained,
        disposed_at=utc_now(),
    )


def _require_state(plan: ExecutionResourcePlan, state: PlanState) -> None:
    if plan.state != state:
        raise PlanStateError(f"expected plan state {state}, got {plan.state}")


__all__ = [
    "CleanupEvidence",
    "CompletionCoverage",
    "CompletionCoverageAdapter",
    "CompletionCoverageFailure",
    "CompletionCoverageInput",
    "DiscoveredResources",
    "EffectiveEnvironmentReadback",
    "EnvironmentCertificate",
    "EnvironmentReadbackMismatch",
    "ExecutionResourcePlan",
    "ExperimentRunnerExecutionPort",
    "ExperimentRunnerPreLaunchAdapter",
    "GPUAllocation",
    "GPUDevice",
    "MaterializedEnvironment",
    "PlanState",
    "PlanStateError",
    "PreLaunchContext",
    "ProcessIdentity",
    "ResourcePlanError",
    "ResourceProbe",
    "ResourceRequest",
    "SnapshotResourceProbe",
    "TerminalEvidence",
    "TypedPreflightFailure",
    "UUIDReservationStore",
    "discover_resources",
    "discover_resources_from_probe",
    "dispose_resources",
    "execute_with_experiment_runner",
    "freeze_resource_plan",
    "materialize_environment",
    "plan_gpu_allocation",
    "record_terminal",
    "verify_effective_environment",
]
