#!/usr/bin/env python3
# @dependency-start
# contract implementation
# responsibility Owns provider-independent GPU admission, immutable direct-command plans, exact GPU environments, and descendant-safe lock release.
# upstream implementation ./execution_resource_plan.py owns strict NVIDIA evidence, BUSY/UNKNOWN/FREE classification, UUID reservation, and admission receipts
# upstream design ../../documents/experiments/gpu-direct-command.md direct versus managed execution boundary
# upstream design ../../agents/skills/gpu-execution.md route selection and no-fallback policy
# downstream implementation ./run_gpu_command.py shell-free command-line adapter
# downstream implementation ../../tests/tools/test_run_gpu_command.py fake-probe, race, environment, lifecycle, and provider-independence tests
# @dependency-end

"""Provider-independent GPU admission for arbitrary shell-free commands.

The module deliberately composes the existing R5 evidence owners instead of
implementing a second scheduler.  A command can start only after a strict
NVIDIA observation, BUSY/UNKNOWN exclusion, a per-UUID lock, a distinct fresh
post-lock observation, and an immutable plan.  The selected UUID environment
is materialized only after that plan is durably written.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Literal, Mapping, Protocol, Sequence, cast

from tools.experiments.execution_resource_plan import (
    ConcurrentRunEvidence,
    DescendantRetentionEvidence,
    EvidenceFd,
    FdReleaseEvidence,
    GpuProcessOccupancyProbe,
    GpuReservationTransaction,
    HOST_RUNTIME_ROOT,
    LOCK_ROOT,
    MigEvidence,
    NvidiaInventory,
    NvidiaListEvidence,
    NvidiaSMIResourceProbe,
    ProcessOccupancyEvidence,
    ResourceObservation,
    ReservationEvidence,
    RunGpuAdmissionReceipt,
    TypedPreflightFailure,
    UuidVisibilityEvidence,
    build_lock_bound_admission_receipt,
    parse_nvidia_smi_list,
    validate_absolute_posix_path,
)

DIRECT_PLAN_SCHEMA = "agentcanon-gpu-command-plan/v1"
DIRECT_ENVIRONMENT_SCHEMA = "agentcanon-gpu-command-environment/v1"
DIRECT_RESULT_SCHEMA = "agentcanon-gpu-command-result/v1"
DIRECT_FAILURE_SCHEMA = "agentcanon-gpu-command-failure/v1"
GPU_VISIBLE_KEYS = ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES")
JAX_GPU_ENVIRONMENT = MappingProxyType(
    {
        "JAX_PLATFORMS": "cuda",
        "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
        "XLA_PYTHON_CLIENT_ALLOCATOR": "platform",
        "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR": "false",
    }
)
_FULL_NVIDIA_UUID = re.compile(r"^(?:GPU|MIG)-[A-Za-z0-9-]+$")
_SENSITIVE_ENV_PARTS = (
    "API_KEY",
    "AUTH",
    "CREDENTIAL",
    "KEY",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)
_PR_SET_CHILD_SUBREAPER = 36
_PR_GET_CHILD_SUBREAPER = 37


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _environment_contract_items(
    environment: Mapping[str, str],
) -> tuple[tuple[str, object], ...]:
    return tuple(
        (
            key,
            {
                "present": True,
                "redacted": True,
                "sha256": hashlib.sha256(
                    environment[key].encode("utf-8")
                ).hexdigest(),
                "byte_count": len(environment[key].encode("utf-8")),
            }
            if _is_sensitive_environment_key(key)
            else environment[key],
        )
        for key in sorted(environment)
    )


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("write made no progress")
        offset += written


def _write_json_once(path: Path, value: Mapping[str, object]) -> None:
    payload = (_canonical_json(dict(value)) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise TypedPreflightFailure(
            "gpu_command_evidence_collision",
            "direct GPU command evidence paths must be created exactly once",
            path=str(path),
        ) from exc
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _is_sensitive_environment_key(key: str) -> bool:
    upper = key.upper()
    return any(part in upper for part in _SENSITIVE_ENV_PARTS)


def _environment_key_witness(environment: Mapping[str, str]) -> Mapping[str, object]:
    return MappingProxyType(
        {
            key: (
                {"present": True, "redacted": True}
                if _is_sensitive_environment_key(key)
                else {"present": True, "redacted": False}
            )
            for key in sorted(environment)
        }
    )


def _validate_string_mapping(environment: Mapping[str, str]) -> None:
    for key, value in environment.items():
        if (
            not isinstance(key, str)
            or not key
            or "\x00" in key
            or "=" in key
            or not isinstance(value, str)
            or "\x00" in value
        ):
            raise TypedPreflightFailure(
                "gpu_command_environment_invalid",
                "direct command environment keys and values must be NUL-free strings",
            )


def _validate_full_uuid(uuid: str) -> None:
    if _FULL_NVIDIA_UUID.fullmatch(uuid) is None:
        raise TypedPreflightFailure(
            "gpu_candidate_uuid_invalid",
            "GPU candidates must use complete opaque physical or MIG UUIDs",
            candidate=uuid,
        )


@dataclass(frozen=True)
class CandidateAllocation:
    """Strict candidate leaf set before resource observation."""

    candidate_ids: tuple[str, ...]
    source: Literal["cli", "scheduler_environment", "strict_nvidia_inventory"]
    inventory_fingerprint: str
    physical_uuids: tuple[str, ...]
    mig_uuids: tuple[str, ...]
    mig_parent_by_uuid: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.candidate_ids:
            raise TypedPreflightFailure(
                "gpu_candidate_set_empty",
                "direct GPU command admission requires a non-empty candidate set",
            )
        if not self.inventory_fingerprint:
            raise ValueError("candidate inventory fingerprint is required")
        if self.candidate_ids != tuple(sorted(self.candidate_ids)):
            raise ValueError("candidate IDs must use stable lexical UUID order")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("candidate IDs must be unique")
        if self.physical_uuids != tuple(sorted(self.physical_uuids)):
            raise ValueError("physical UUIDs must use stable lexical order")
        if self.mig_uuids != tuple(sorted(self.mig_uuids)):
            raise ValueError("MIG UUIDs must use stable lexical order")
        parent_by_uuid = dict(self.mig_parent_by_uuid)
        if set(parent_by_uuid) != set(self.mig_uuids):
            raise ValueError("MIG parent mapping must cover exactly every MIG UUID")
        if any(
            parent not in self.physical_uuids
            for parent in parent_by_uuid.values()
        ):
            raise ValueError("MIG parent mapping must reference known physical UUIDs")
        for uuid in (*self.physical_uuids, *self.mig_uuids, *self.candidate_ids):
            _validate_full_uuid(uuid)
        object.__setattr__(
            self,
            "mig_parent_by_uuid",
            MappingProxyType(parent_by_uuid),
        )


class NvidiaListCommand(Protocol):
    def __call__(
        self,
        argv: Sequence[str],
        *,
        check: bool,
        capture_output: bool,
        timeout: float,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]: ...


def read_strict_nvidia_list(
    nvidia_smi: str,
    *,
    command: NvidiaListCommand = subprocess.run,
) -> NvidiaListEvidence:
    """Capture and parse ``nvidia-smi -L`` through the canonical fd parser."""
    if not nvidia_smi:
        raise TypedPreflightFailure(
            "gpu_structured_probe_unavailable",
            "nvidia-smi is required to resolve direct-command GPU candidates",
        )
    try:
        completed = command(
            (nvidia_smi, "-L"),
            check=False,
            capture_output=True,
            timeout=30.0,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TypedPreflightFailure(
            "gpu_list_probe_failed",
            "nvidia-smi -L could not be executed",
            executable=nvidia_smi,
        ) from exc
    if completed.returncode != 0:
        raise TypedPreflightFailure(
            "gpu_list_probe_failed",
            "nvidia-smi -L returned a failure",
            executable=nvidia_smi,
            returncode=completed.returncode,
        )
    payload = bytes(completed.stdout)
    memfd_create = getattr(os, "memfd_create", None)
    if not callable(memfd_create):
        raise TypedPreflightFailure(
            "gpu_evidence_fd_unavailable",
            "strict candidate discovery requires memfd_create support",
        )
    descriptor = int(memfd_create("agent-canon-direct-nvidia-list", os.MFD_CLOEXEC))
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        identity = os.fstat(descriptor)
        evidence = EvidenceFd(
            fd=descriptor,
            source_name="direct_nvidia_smi_list",
            st_dev=identity.st_dev,
            st_ino=identity.st_ino,
            byte_count=identity.st_size,
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        return parse_nvidia_smi_list(evidence)
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            raise TypedPreflightFailure(
                "gpu_evidence_fd_close_ambiguous",
                "strict candidate evidence fd close was ambiguous",
                fd=descriptor,
                errno=exc.errno,
            ) from exc


def _visible_environment_restriction(
    environment: Mapping[str, str],
) -> tuple[str, ...] | None:
    exact_values: list[tuple[str, ...]] = []
    for key in GPU_VISIBLE_KEYS:
        raw = environment.get(key)
        if raw is None:
            continue
        normalized = raw.strip()
        if normalized.lower() in {"all", ""}:
            continue
        if normalized.lower() in {"none", "void"}:
            raise TypedPreflightFailure(
                "gpu_scheduler_uuid_visibility_unproven",
                "direct GPU execution cannot widen an explicitly empty visibility set",
                environment_key=key,
                observed_value=raw,
            )
        tokens = tuple(token.strip() for token in normalized.split(","))
        if not tokens or any(not token for token in tokens):
            raise TypedPreflightFailure(
                "gpu_scheduler_uuid_visibility_unproven",
                "GPU visibility must be an exact comma-separated UUID set",
                environment_key=key,
                observed_value=raw,
            )
        for token in tokens:
            _validate_full_uuid(token)
        if len(tokens) != len(set(tokens)):
            raise TypedPreflightFailure(
                "gpu_scheduler_uuid_visibility_ambiguous",
                "GPU visibility must not repeat UUIDs",
                environment_key=key,
            )
        exact_values.append(tuple(sorted(tokens)))
    if not exact_values:
        return None
    if any(value != exact_values[0] for value in exact_values[1:]):
        raise TypedPreflightFailure(
            "gpu_scheduler_uuid_visibility_conflict",
            "CUDA and NVIDIA exact UUID visibility sets disagree",
            observed=exact_values,
        )
    return exact_values[0]


def resolve_candidate_allocation(
    environment: Mapping[str, str],
    *,
    explicit_candidates: Sequence[str] = (),
    nvidia_smi: str | None = None,
    command: NvidiaListCommand = subprocess.run,
) -> CandidateAllocation:
    """Resolve executable physical/MIG leaf UUIDs without integer or prefix IDs."""
    _validate_string_mapping(environment)
    executable = nvidia_smi or shutil.which("nvidia-smi") or ""
    inventory = read_strict_nvidia_list(executable, command=command)
    mig_parents = {join.parent_uuid for join in inventory.joins}
    executable_leaf_ids = (
        tuple(
            sorted(
                uuid
                for uuid in inventory.physical_uuids
                if uuid not in mig_parents
            )
        )
        + tuple(sorted(inventory.mig_uuids))
    )
    leaf_set = frozenset(executable_leaf_ids)
    scheduler_restriction = _visible_environment_restriction(environment)

    if explicit_candidates:
        requested = tuple(sorted(explicit_candidates))
        if len(requested) != len(set(requested)):
            raise TypedPreflightFailure(
                "gpu_candidate_uuid_duplicate",
                "explicit GPU candidates must be unique",
            )
        for uuid in requested:
            _validate_full_uuid(uuid)
        source: Literal["cli", "scheduler_environment", "strict_nvidia_inventory"] = "cli"
    elif scheduler_restriction is not None:
        requested = scheduler_restriction
        source = "scheduler_environment"
    else:
        requested = executable_leaf_ids
        source = "strict_nvidia_inventory"

    missing = tuple(sorted(set(requested).difference(leaf_set)))
    if missing:
        raise TypedPreflightFailure(
            "gpu_candidate_uuid_not_executable_leaf",
            "candidate UUIDs must be complete executable leaves in strict NVIDIA topology",
            missing=missing,
            executable_leaf_ids=executable_leaf_ids,
        )
    if scheduler_restriction is not None:
        escaped = tuple(
            sorted(set(requested).difference(scheduler_restriction))
        )
        if escaped:
            raise TypedPreflightFailure(
                "gpu_candidate_outside_scheduler_visibility",
                "explicit GPU candidates cannot widen the caller visibility set",
                escaped=escaped,
                scheduler_visible=scheduler_restriction,
            )
    return CandidateAllocation(
        candidate_ids=requested,
        source=source,
        inventory_fingerprint=inventory.evidence_fingerprint,
        physical_uuids=tuple(sorted(inventory.physical_uuids)),
        mig_uuids=tuple(sorted(inventory.mig_uuids)),
        mig_parent_by_uuid={
            join.mig_uuid: join.parent_uuid for join in inventory.joins
        },
    )


@dataclass(frozen=True)
class DirectGpuCommandRequest:
    """Complete direct-command request before GPU admission."""

    argv: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str]
    candidate_allocation: CandidateAllocation
    gpu_count: int
    minimum_free_memory_bytes: int
    output_dir: Path
    runtime_root: Path = Path(HOST_RUNTIME_ROOT)
    lock_root: Path = LOCK_ROOT
    descendant_poll_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not self.argv or any(
            not isinstance(token, str) or not token or "\x00" in token
            for token in self.argv
        ):
            raise TypedPreflightFailure(
                "gpu_command_argv_invalid",
                "direct GPU command argv must contain non-empty NUL-free strings",
            )
        if self.gpu_count <= 0:
            raise TypedPreflightFailure(
                "gpu_request_cardinality_invalid",
                "direct GPU command count must be positive",
                gpu_count=self.gpu_count,
            )
        if self.minimum_free_memory_bytes < 0:
            raise TypedPreflightFailure(
                "gpu_request_memory_invalid",
                "minimum free GPU memory cannot be negative",
                minimum_free_memory_bytes=self.minimum_free_memory_bytes,
            )
        if self.gpu_count > len(self.candidate_allocation.candidate_ids):
            raise TypedPreflightFailure(
                "gpu_candidate_cardinality_insufficient",
                "candidate set is smaller than the requested GPU count",
                requested=self.gpu_count,
                candidates=self.candidate_allocation.candidate_ids,
            )
        if self.descendant_poll_seconds <= 0:
            raise ValueError("descendant poll interval must be positive")
        _validate_string_mapping(self.environment)
        validate_absolute_posix_path(str(self.cwd))
        validate_absolute_posix_path(str(self.output_dir))
        validate_absolute_posix_path(str(self.runtime_root))
        validate_absolute_posix_path(str(self.lock_root))
        if self.runtime_root != Path(HOST_RUNTIME_ROOT) or self.lock_root != LOCK_ROOT:
            raise TypedPreflightFailure(
                "gpu_lock_namespace_not_canonical",
                "direct GPU commands must use the canonical shared AgentCanon runtime and lock root",
                runtime_root=str(self.runtime_root),
                lock_root=str(self.lock_root),
            )
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))


@dataclass(frozen=True)
class FrozenDirectGpuCommandPlan:
    """Immutable plan written before selected visibility is materialized."""

    schema_version: Literal["agentcanon-gpu-command-plan/v1"]
    plan_id: str
    plan_fingerprint: str
    argv: tuple[str, ...]
    cwd: str
    candidate_ids: tuple[str, ...]
    selected_ids: tuple[str, ...]
    candidate_source: str
    candidate_inventory_fingerprint: str
    candidate_mig_parent_by_uuid: Mapping[str, str]
    requested_gpu_count: int
    minimum_free_memory_bytes: int
    selected_free_memory_bytes: Mapping[str, int]
    initial_unit_states: Mapping[str, str]
    final_unit_states: Mapping[str, str]
    initial_observation_fingerprint: str
    final_observation_fingerprint: str
    initial_event_id: str
    final_event_id: str
    reservation_fingerprint: str
    reservation_ids: tuple[str, ...]
    lock_identities: tuple[tuple[int, int], ...]
    admission_fingerprint: str
    base_environment_fingerprint: str
    environment_key_witness: Mapping[str, object]
    output_dir: str
    unknown_initial_ids: tuple[str, ...]
    unknown_final_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != DIRECT_PLAN_SCHEMA:
            raise ValueError("invalid direct GPU plan schema")
        if not self.candidate_inventory_fingerprint:
            raise ValueError("candidate inventory fingerprint is required")
        if self.candidate_ids != tuple(sorted(self.candidate_ids)):
            raise ValueError("candidate UUIDs must use stable lexical order")
        if self.selected_ids != tuple(sorted(self.selected_ids)):
            raise ValueError("selected UUIDs must use stable lexical order")
        if not set(self.selected_ids).issubset(self.candidate_ids):
            raise ValueError("selected UUIDs must be a subset of candidates")
        if len(self.selected_ids) != self.requested_gpu_count:
            raise ValueError("selected UUID count must equal requested count")
        if len(self.reservation_ids) != len(self.selected_ids):
            raise ValueError("reservation identity count must equal selected count")
        if len(self.lock_identities) != len(self.selected_ids):
            raise ValueError("lock identity count must equal selected count")
        if len(set(self.reservation_ids)) != len(self.reservation_ids):
            raise ValueError("reservation identities must be unique")
        if len(set(self.lock_identities)) != len(self.lock_identities):
            raise ValueError("lock identities must be unique")
        if self.initial_event_id == self.final_event_id:
            raise ValueError("post-lock observation must use a fresh event ID")
        selected_memory = dict(self.selected_free_memory_bytes)
        if set(selected_memory) != set(self.selected_ids):
            raise ValueError("selected memory evidence must cover exactly selected UUIDs")
        if any(
            value < self.minimum_free_memory_bytes
            for value in selected_memory.values()
        ):
            raise ValueError("selected memory evidence violates the request threshold")
        final_states = dict(self.final_unit_states)
        if any(final_states.get(uuid) != "FREE" for uuid in self.selected_ids):
            raise ValueError("selected UUIDs must be FREE in the post-lock observation")
        if set(self.selected_ids) & (
            set(self.unknown_initial_ids) | set(self.unknown_final_ids)
        ):
            raise ValueError("selected UUIDs cannot be UNKNOWN")
        expected = _fingerprint(self.fingerprint_payload())
        if self.plan_fingerprint != expected:
            raise ValueError("direct GPU plan fingerprint mismatch")
        for name in (
            "candidate_mig_parent_by_uuid",
            "selected_free_memory_bytes",
            "initial_unit_states",
            "final_unit_states",
            "environment_key_witness",
        ):
            object.__setattr__(
                self,
                name,
                MappingProxyType(dict(getattr(self, name))),
            )

    def fingerprint_payload(self) -> Mapping[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "argv": self.argv,
            "cwd": self.cwd,
            "candidate_ids": self.candidate_ids,
            "selected_ids": self.selected_ids,
            "candidate_source": self.candidate_source,
            "candidate_inventory_fingerprint": self.candidate_inventory_fingerprint,
            "candidate_mig_parent_by_uuid": dict(self.candidate_mig_parent_by_uuid),
            "requested_gpu_count": self.requested_gpu_count,
            "minimum_free_memory_bytes": self.minimum_free_memory_bytes,
            "selected_free_memory_bytes": dict(self.selected_free_memory_bytes),
            "initial_unit_states": dict(self.initial_unit_states),
            "final_unit_states": dict(self.final_unit_states),
            "initial_observation_fingerprint": self.initial_observation_fingerprint,
            "final_observation_fingerprint": self.final_observation_fingerprint,
            "initial_event_id": self.initial_event_id,
            "final_event_id": self.final_event_id,
            "reservation_fingerprint": self.reservation_fingerprint,
            "reservation_ids": self.reservation_ids,
            "lock_identities": self.lock_identities,
            "admission_fingerprint": self.admission_fingerprint,
            "base_environment_fingerprint": self.base_environment_fingerprint,
            "environment_key_witness": dict(self.environment_key_witness),
            "output_dir": self.output_dir,
            "unknown_initial_ids": self.unknown_initial_ids,
            "unknown_final_ids": self.unknown_final_ids,
        }

    def record(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                **self.fingerprint_payload(),
                "plan_fingerprint": self.plan_fingerprint,
            }
        )


@dataclass(frozen=True)
class MaterializedDirectEnvironment:
    """Exact child environment derived only from a frozen plan."""

    schema_version: Literal["agentcanon-gpu-command-environment/v1"]
    plan_fingerprint: str
    environment_fingerprint: str
    exact_environment: Mapping[str, str] = field(repr=False, compare=False)
    selected_uuid_list: str
    canonical_jax_environment: Mapping[str, str]

    def __post_init__(self) -> None:
        expected = _fingerprint(_environment_contract_items(self.exact_environment))
        if self.environment_fingerprint != expected:
            raise ValueError("direct command environment fingerprint mismatch")
        object.__setattr__(
            self,
            "exact_environment",
            MappingProxyType(dict(self.exact_environment)),
        )
        object.__setattr__(
            self,
            "canonical_jax_environment",
            MappingProxyType(dict(self.canonical_jax_environment)),
        )

    def record(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "plan_fingerprint": self.plan_fingerprint,
                "environment_fingerprint": self.environment_fingerprint,
                "selected_uuid_list": self.selected_uuid_list,
                "cuda_visible_devices": self.exact_environment[
                    "CUDA_VISIBLE_DEVICES"
                ],
                "nvidia_visible_devices": self.exact_environment[
                    "NVIDIA_VISIBLE_DEVICES"
                ],
                "canonical_jax_environment": dict(self.canonical_jax_environment),
                "environment_key_witness": dict(
                    _environment_key_witness(self.exact_environment)
                ),
            }
        )


@dataclass(frozen=True)
class ProcRecord:
    pid: int
    parent_pid: int
    process_group_id: int
    session_id: int
    starttime: str
    state: str

    @property
    def identity(self) -> tuple[int, str]:
        return (self.pid, self.starttime)


@dataclass(frozen=True)
class DirectCommandLifecycle:
    child_pid: int
    child_starttime: str | None
    process_group_id: int
    session_id: int
    observed_descendant_identities: tuple[tuple[int, str], ...]
    descendant_quiescence: Literal["PROVEN"]
    subreaper_enabled: bool
    started_at_utc: str
    finished_at_utc: str
    started_at_monotonic: float
    finished_at_monotonic: float

    def record(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "child_pid": self.child_pid,
                "child_starttime": self.child_starttime,
                "process_group_id": self.process_group_id,
                "session_id": self.session_id,
                "observed_descendant_identities": self.observed_descendant_identities,
                "descendant_quiescence": self.descendant_quiescence,
                "subreaper_enabled": self.subreaper_enabled,
                "started_at": self.started_at_utc,
                "finished_at": self.finished_at_utc,
                "duration_seconds": max(
                    0.0,
                    self.finished_at_monotonic - self.started_at_monotonic,
                ),
                "signal_or_kill_sent": False,
            }
        )


@dataclass(frozen=True)
class DirectCommandExecution:
    returncode: int
    lifecycle: DirectCommandLifecycle
    stdout_path: Path
    stderr_path: Path


class DirectCommandPostLaunchFailure(RuntimeError):
    """An executor failure whose child tree is already proven quiescent."""

    def __init__(
        self,
        cause: BaseException,
        execution: DirectCommandExecution,
    ) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.execution = execution


class DirectCommandExecutor(Protocol):
    def execute(
        self,
        plan: FrozenDirectGpuCommandPlan,
        environment: Mapping[str, str],
        *,
        stdout_path: Path,
        stderr_path: Path,
        poll_seconds: float,
    ) -> DirectCommandExecution: ...


class ReservationTransaction(Protocol):
    @property
    def reservation_ids(self) -> tuple[str, ...]: ...

    def try_reserve(
        self,
        candidate_uuids: Sequence[str],
        *,
        occupied_uuids: Sequence[str] = (),
        requested_count: int = 1,
    ) -> ReservationEvidence: ...

    def close(self) -> tuple[FdReleaseEvidence, ...]: ...


class ObservationProbe(Protocol):
    def observe(self) -> ResourceObservation: ...


ProbeFactory = Callable[[Mapping[str, str], int, Path], ObservationProbe]
ReservationFactory = Callable[[Path], ReservationTransaction]


def _production_probe_factory(
    environment: Mapping[str, str],
    gpu_count: int,
    runtime_root: Path,
) -> ObservationProbe:
    return NvidiaSMIResourceProbe.discover(
        environment,
        gpu_requested_count=gpu_count,
        runtime_root=runtime_root,
    )


def _production_reservation_factory(lock_root: Path) -> ReservationTransaction:
    return GpuReservationTransaction(lock_root)


def _scan_proc_table(proc_root: Path = Path("/proc")) -> Mapping[int, ProcRecord]:
    records: dict[int, ProcRecord] = {}
    try:
        entries = tuple(proc_root.iterdir())
    except OSError as exc:
        raise TypedPreflightFailure(
            "gpu_command_proc_unavailable",
            "direct command lifecycle requires readable /proc",
            path=str(proc_root),
        ) from exc
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        try:
            raw = (entry / "stat").read_text(encoding="utf-8")
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
            continue
        suffix = raw.rsplit(")", 1)[-1].split()
        if len(suffix) <= 19:
            continue
        try:
            pid = int(entry.name)
            records[pid] = ProcRecord(
                pid=pid,
                parent_pid=int(suffix[1]),
                process_group_id=int(suffix[2]),
                session_id=int(suffix[3]),
                starttime=suffix[19],
                state=suffix[0],
            )
        except ValueError:
            continue
    return MappingProxyType(records)


def _set_child_subreaper(enabled: bool) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.restype = ctypes.c_int
    result = prctl(_PR_SET_CHILD_SUBREAPER, int(enabled), 0, 0, 0)
    if result != 0:
        errno_value = ctypes.get_errno()
        raise TypedPreflightFailure(
            "gpu_command_subreaper_unavailable",
            "direct command descendant retention requires PR_SET_CHILD_SUBREAPER",
            errno=errno_value,
        )


def _get_child_subreaper() -> bool:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.restype = ctypes.c_int
    value = ctypes.c_int(0)
    result = prctl(_PR_GET_CHILD_SUBREAPER, ctypes.byref(value), 0, 0, 0)
    if result != 0:
        errno_value = ctypes.get_errno()
        raise TypedPreflightFailure(
            "gpu_command_subreaper_unavailable",
            "direct command descendant retention requires PR_GET_CHILD_SUBREAPER",
            errno=errno_value,
        )
    return bool(value.value)


def _reap_scoped_zombies(
    records: Mapping[tuple[int, str], ProcRecord],
    *,
    runner_pid: int,
    root_pid: int,
) -> None:
    """Reap only command-owned adopted zombies, never unrelated children."""
    for record in records.values():
        if (
            record.pid == root_pid
            or record.parent_pid != runner_pid
            or record.state != "Z"
        ):
            continue
        while True:
            try:
                os.waitpid(record.pid, os.WNOHANG)
                break
            except ChildProcessError:
                break
            except InterruptedError:
                continue


def _descendant_scope(
    table: Mapping[int, ProcRecord],
    *,
    runner_pid: int,
    root_pid: int,
    tracked: Mapping[tuple[int, str], ProcRecord],
    baseline_runner_children: frozenset[tuple[int, str]],
) -> Mapping[tuple[int, str], ProcRecord]:
    """Close the process-tree set under ancestry, session, and adoption."""
    scoped: dict[tuple[int, str], ProcRecord] = {}
    tracked_pids = {record.pid for record in tracked.values()}
    frontier = {root_pid, *tracked_pids}
    changed = True
    while changed:
        changed = False
        for record in table.values():
            if record.pid == runner_pid:
                continue
            adopted_after_launch = (
                record.parent_pid == runner_pid
                and record.identity not in baseline_runner_children
            )
            in_scope = (
                record.pid == root_pid
                or record.identity in tracked
                or record.session_id == root_pid
                or record.process_group_id == root_pid
                or record.parent_pid in frontier
                or adopted_after_launch
            )
            if in_scope and record.pid not in frontier:
                frontier.add(record.pid)
                changed = True
            if in_scope:
                scoped[record.identity] = record
    return MappingProxyType(scoped)


class LinuxSubreaperCommandExecutor:
    """Launch once with shell=False and retain descendants until quiescence."""

    @staticmethod
    def _record_failure(
        current: BaseException | None,
        candidate: BaseException,
    ) -> BaseException:
        return current if current is not None else candidate

    def execute(
        self,
        plan: FrozenDirectGpuCommandPlan,
        environment: Mapping[str, str],
        *,
        stdout_path: Path,
        stderr_path: Path,
        poll_seconds: float,
    ) -> DirectCommandExecution:
        if sys.platform != "linux":
            raise TypedPreflightFailure(
                "gpu_command_lifecycle_unsupported",
                "direct GPU descendant retention requires Linux procfs and subreaper support",
                platform=sys.platform,
            )
        runner_pid = os.getpid()
        baseline_table = _scan_proc_table()
        baseline_runner_children = frozenset(
            record.identity
            for record in baseline_table.values()
            if record.parent_pid == runner_pid
        )
        prior_subreaper = _get_child_subreaper()
        if not prior_subreaper:
            _set_child_subreaper(True)
        started_at_utc = datetime.now(UTC).isoformat()
        started_at_monotonic = time.monotonic()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        try:
            stdout_fd = os.open(stdout_path, flags, 0o600)
        except BaseException:
            if not prior_subreaper:
                _set_child_subreaper(False)
            raise
        try:
            stderr_fd = os.open(stderr_path, flags, 0o600)
        except BaseException:
            os.close(stdout_fd)
            if not prior_subreaper:
                _set_child_subreaper(False)
            raise

        process: subprocess.Popen[bytes] | None = None
        pending_failure: BaseException | None = None
        execution: DirectCommandExecution | None = None
        try:
            try:
                process = subprocess.Popen(
                    list(plan.argv),
                    cwd=plan.cwd,
                    env=dict(environment),
                    stdin=None,
                    stdout=stdout_fd,
                    stderr=stderr_fd,
                    shell=False,
                    start_new_session=True,
                    close_fds=True,
                )
            except OSError as exc:
                raise TypedPreflightFailure(
                    "gpu_command_launch_failed",
                    "shell-free direct GPU command could not be launched",
                    executable=plan.argv[0],
                    errno=exc.errno,
                ) from exc

            root_pid = process.pid
            tracked: dict[tuple[int, str], ProcRecord] = {}
            child_starttime: str | None = None
            returncode: int | None = None

            # Once Popen succeeds, every failure is retained until the entire
            # process tree is proven quiescent. This prevents diagnostics,
            # procfs, fsync, or subreaper errors from releasing UUID locks
            # while an AgentCanon-started descendant can still execute.
            while returncode is None:
                try:
                    table = _scan_proc_table()
                    scoped = _descendant_scope(
                        table,
                        runner_pid=runner_pid,
                        root_pid=root_pid,
                        tracked=tracked,
                        baseline_runner_children=baseline_runner_children,
                    )
                    tracked.update(scoped)
                    root_record = table.get(root_pid)
                    if root_record is not None:
                        child_starttime = child_starttime or root_record.starttime
                    returncode = process.poll()
                except BaseException as exc:
                    pending_failure = self._record_failure(pending_failure, exc)
                    returncode = process.poll()
                if returncode is None:
                    time.sleep(poll_seconds)

            try:
                returncode = process.wait()
            except BaseException as exc:
                pending_failure = self._record_failure(pending_failure, exc)
                while returncode is None:
                    try:
                        returncode = process.poll()
                    except BaseException as poll_exc:
                        pending_failure = self._record_failure(
                            pending_failure,
                            poll_exc,
                        )
                    if returncode is None:
                        time.sleep(poll_seconds)

            while True:
                try:
                    table = _scan_proc_table()
                    scoped = _descendant_scope(
                        table,
                        runner_pid=runner_pid,
                        root_pid=root_pid,
                        tracked=tracked,
                        baseline_runner_children=baseline_runner_children,
                    )
                    tracked.update(scoped)
                    _reap_scoped_zombies(
                        scoped,
                        runner_pid=runner_pid,
                        root_pid=root_pid,
                    )
                    live = tuple(
                        record
                        for record in scoped.values()
                        if record.pid != root_pid and record.state != "Z"
                    )
                except BaseException as exc:
                    pending_failure = self._record_failure(pending_failure, exc)
                    time.sleep(poll_seconds)
                    continue
                if not live:
                    break
                time.sleep(poll_seconds)

            finished = time.monotonic()
            finished_at_utc = datetime.now(UTC).isoformat()
            descendants = tuple(
                sorted(
                    identity
                    for identity, record in tracked.items()
                    if record.pid != root_pid
                )
            )
            lifecycle = DirectCommandLifecycle(
                child_pid=root_pid,
                child_starttime=child_starttime,
                process_group_id=root_pid,
                session_id=root_pid,
                observed_descendant_identities=descendants,
                descendant_quiescence="PROVEN",
                subreaper_enabled=True,
                started_at_utc=started_at_utc,
                finished_at_utc=finished_at_utc,
                started_at_monotonic=started_at_monotonic,
                finished_at_monotonic=finished,
            )
            execution = DirectCommandExecution(
                returncode=cast(int, returncode),
                lifecycle=lifecycle,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
            for descriptor in (stdout_fd, stderr_fd):
                try:
                    os.fsync(descriptor)
                except BaseException as exc:
                    pending_failure = self._record_failure(pending_failure, exc)
        finally:
            for descriptor in (stderr_fd, stdout_fd):
                try:
                    os.close(descriptor)
                except BaseException as exc:
                    pending_failure = self._record_failure(pending_failure, exc)
            if not prior_subreaper:
                try:
                    _set_child_subreaper(False)
                except BaseException as exc:
                    pending_failure = self._record_failure(pending_failure, exc)

        if execution is None:
            # Only the pre-launch path can reach here. A post-launch path keeps
            # monitoring until it can construct quiescence evidence.
            if pending_failure is not None:
                raise pending_failure
            raise TypedPreflightFailure(
                "gpu_command_execution_state_invalid",
                "direct command executor produced no launch or lifecycle evidence",
            )
        if pending_failure is not None:
            raise DirectCommandPostLaunchFailure(pending_failure, execution)
        return execution


def _observe_occupancy(observation: ResourceObservation) -> ProcessOccupancyEvidence:
    inventory = observation.nvidia_inventory
    if inventory is None:
        raise TypedPreflightFailure(
            "gpu_inventory_unproven",
            "direct GPU admission requires strict NVIDIA inventory evidence",
        )
    try:
        namespace_inode = os.stat("/proc/self/ns/pid").st_ino
    except OSError as exc:
        raise TypedPreflightFailure(
            "gpu_namespace_identity_unproven",
            "direct GPU admission requires the local PID namespace identity",
        ) from exc
    return GpuProcessOccupancyProbe(
        inventory=inventory,
        namespace_inode=namespace_inode,
        processes=observation.process_identities,
        process_inventory_disposition=(
            "COMPLETE_EMPTY"
            if not observation.process_identities
            else "COMPLETE"
        ),
        unknown_gpu_ids=observation.unknown_gpu_ids,
    ).observe()


def _probe_environment(request: DirectGpuCommandRequest) -> Mapping[str, str]:
    environment = dict(request.environment)
    candidate_list = ",".join(request.candidate_allocation.candidate_ids)
    environment["CUDA_VISIBLE_DEVICES"] = candidate_list
    environment["NVIDIA_VISIBLE_DEVICES"] = candidate_list
    return MappingProxyType(environment)


def _eligible_ids(
    request: DirectGpuCommandRequest,
    observation: ResourceObservation,
    occupancy: ProcessOccupancyEvidence,
) -> tuple[str, ...]:
    return tuple(
        uuid
        for uuid in request.candidate_allocation.candidate_ids
        if occupancy.unit_states.get(uuid) == "FREE"
        and observation.free_memory_bytes.get(uuid, -1)
        >= request.minimum_free_memory_bytes
    )


def _validate_candidate_topology(
    request: DirectGpuCommandRequest,
    observation: ResourceObservation,
    *,
    phase: Literal["initial", "post_lock"],
) -> None:
    """Prove the strict list-derived executable-leaf topology did not drift."""
    inventory = observation.nvidia_inventory
    if inventory is None:
        raise TypedPreflightFailure(
            "gpu_inventory_unproven",
            "direct GPU admission requires strict NVIDIA inventory evidence",
            phase=phase,
        )
    expected_candidates = frozenset(request.candidate_allocation.candidate_ids)
    if observation.caller_allocated_ids != expected_candidates:
        raise TypedPreflightFailure(
            "gpu_candidate_visibility_raced",
            "resource observation caller visibility differs from the frozen candidate set",
            phase=phase,
            expected=tuple(sorted(expected_candidates)),
            observed=tuple(sorted(observation.caller_allocated_ids)),
        )
    observed_parent_by_uuid = {
        join.mig_uuid: join.parent_uuid for join in inventory.joins
    }
    expected = request.candidate_allocation
    topology_matches = (
        tuple(sorted(inventory.physical_uuids)) == expected.physical_uuids
        and tuple(sorted(inventory.mig_uuids)) == expected.mig_uuids
        and observed_parent_by_uuid == dict(expected.mig_parent_by_uuid)
    )
    mig_parents = frozenset(observed_parent_by_uuid.values())
    executable_leaves = frozenset(
        uuid for uuid in inventory.physical_uuids if uuid not in mig_parents
    ) | frozenset(inventory.mig_uuids)
    if not topology_matches or not expected_candidates.issubset(executable_leaves):
        raise TypedPreflightFailure(
            "gpu_candidate_topology_raced",
            "candidate UUIDs no longer match the strict executable-leaf topology",
            phase=phase,
            expected_physical_uuids=expected.physical_uuids,
            observed_physical_uuids=inventory.physical_uuids,
            expected_mig_uuids=expected.mig_uuids,
            observed_mig_uuids=inventory.mig_uuids,
            expected_mig_parent_by_uuid=dict(expected.mig_parent_by_uuid),
            observed_mig_parent_by_uuid=observed_parent_by_uuid,
            executable_leaf_ids=tuple(sorted(executable_leaves)),
        )


def _validate_fresh_post_lock_observation(
    request: DirectGpuCommandRequest,
    initial: ResourceObservation,
    final: ResourceObservation,
    final_occupancy: ProcessOccupancyEvidence,
    selected_ids: Sequence[str],
) -> None:
    if (
        not initial.observation_event_id
        or not final.observation_event_id
        or initial.observation_event_id == final.observation_event_id
    ):
        raise TypedPreflightFailure(
            "gpu_run_admission_raced",
            "post-lock GPU observation must have a distinct freshness event ID",
            initial_event_id=initial.observation_event_id,
            final_event_id=final.observation_event_id,
        )
    candidate_set = frozenset(request.candidate_allocation.candidate_ids)
    if not candidate_set.issubset(final.caller_allocated_ids):
        raise TypedPreflightFailure(
            "gpu_run_admission_raced",
            "post-lock caller-visible UUID set no longer contains every candidate",
            expected=tuple(sorted(candidate_set)),
            observed=tuple(sorted(final.caller_allocated_ids)),
        )
    violations = tuple(
        uuid
        for uuid in selected_ids
        if final_occupancy.unit_states.get(uuid) != "FREE"
        or final.free_memory_bytes.get(uuid, -1)
        < request.minimum_free_memory_bytes
    )
    if violations:
        raise TypedPreflightFailure(
            "gpu_run_admission_raced",
            "selected GPU became BUSY, UNKNOWN, or memory-insufficient after lock acquisition",
            selected_uuids=tuple(selected_ids),
            violated_uuids=violations,
            unit_states=dict(final_occupancy.unit_states),
            free_memory_bytes=dict(final.free_memory_bytes),
        )


def _host_runtime_identity_fingerprint(
    request: DirectGpuCommandRequest,
    final_observation: ResourceObservation,
) -> str:
    try:
        namespace_identity = os.readlink("/proc/self/ns/pid")
        lock_identity = os.stat(request.lock_root)
    except OSError as exc:
        raise TypedPreflightFailure(
            "gpu_runtime_identity_unproven",
            "direct GPU runtime identity or canonical lock root is unavailable",
        ) from exc
    return _fingerprint(
        {
            "schema_version": "host-direct-runtime-identity/v1",
            "runtime_root": str(request.runtime_root),
            "lock_root": str(request.lock_root),
            "lock_device": lock_identity.st_dev,
            "lock_inode": lock_identity.st_ino,
            "lock_mode": oct(lock_identity.st_mode & 0o7777),
            "pid_namespace": namespace_identity,
            "boot_id": final_observation.boot_id,
            "caller_allocated_ids": tuple(
                sorted(final_observation.caller_allocated_ids)
            ),
        }
    )


def _build_admission_receipt(
    request: DirectGpuCommandRequest,
    initial: ResourceObservation,
    final: ResourceObservation,
    initial_occupancy: ProcessOccupancyEvidence,
    final_occupancy: ProcessOccupancyEvidence,
    reservation: ReservationEvidence,
) -> RunGpuAdmissionReceipt:
    if not reservation.locks:
        raise TypedPreflightFailure(
            "gpu_lock_readback_missing",
            "acquired direct-command GPU reservation returned no lock readback",
        )
    inventory = cast(NvidiaInventory, final.nvidia_inventory)
    selected = reservation.selected_uuids
    concurrent = ConcurrentRunEvidence(
        initial_snapshot_fingerprint=initial.fingerprint,
        admission_snapshot_fingerprint=final.fingerprint,
        final_snapshot_fingerprint=final.fingerprint,
        initial_event_id=initial.observation_event_id,
        admission_event_id=final.observation_event_id,
        final_event_id=final.observation_event_id,
        fingerprint=_fingerprint(
            {
                "initial": initial.fingerprint,
                "admission": final.fingerprint,
                "initial_event_id": initial.observation_event_id,
                "admission_event_id": final.observation_event_id,
            }
        ),
    )
    mig = MigEvidence(
        parent_by_uuid={join.mig_uuid: join.parent_uuid for join in inventory.joins},
        executable_leaf_uuids=inventory.mig_uuids,
        selected_physical_uuids=tuple(
            uuid for uuid in selected if uuid in inventory.physical_uuids
        ),
        fingerprint=_fingerprint(
            {
                "joins": tuple(
                    (join.parent_uuid, join.ordinal, join.mig_uuid)
                    for join in inventory.joins
                ),
                "selected": selected,
            }
        ),
    )
    return build_lock_bound_admission_receipt(
        candidate_uuids=request.candidate_allocation.candidate_ids,
        occupied_uuids=final_occupancy.occupied_uuids,
        reserved_uuids=selected,
        selected_uuids=selected,
        inventory_fingerprint=inventory.evidence_fingerprint,
        occupancy_fingerprint=_fingerprint(
            {
                "initial": initial_occupancy.evidence_fingerprint,
                "final": final_occupancy.evidence_fingerprint,
            }
        ),
        reservation_fingerprint=reservation.evidence_fingerprint,
        runtime_identity_fingerprint=_host_runtime_identity_fingerprint(
            request,
            final,
        ),
        lock_readback=reservation.locks[0],
        actual_gpu_processes=(initial_occupancy, final_occupancy),
        concurrent_run_evidence=concurrent,
        mig_evidence=mig,
    )


def freeze_direct_gpu_command_plan(
    request: DirectGpuCommandRequest,
    *,
    initial: ResourceObservation,
    final: ResourceObservation,
    initial_occupancy: ProcessOccupancyEvidence,
    final_occupancy: ProcessOccupancyEvidence,
    reservation: ReservationEvidence,
    reservation_ids: Sequence[str],
    admission: RunGpuAdmissionReceipt,
) -> FrozenDirectGpuCommandPlan:
    """Freeze argv/cwd/resource identities before child visibility exists."""
    selected_ids = tuple(reservation.selected_uuids)
    if len(selected_ids) != request.gpu_count:
        raise TypedPreflightFailure(
            "gpu_allocation_contract_invalid",
            "direct command reservation cardinality differs from the request",
            requested=request.gpu_count,
            selected=selected_ids,
        )
    plan_id = (
        "gpu-command-"
        + hashlib.sha256(
            (
                "\0".join(request.argv)
                + str(request.cwd)
                + final.observation_event_id
            ).encode("utf-8")
        ).hexdigest()[:20]
    )
    base_environment_fingerprint = _fingerprint(
        _environment_contract_items(request.environment)
    )
    payload = {
        "schema_version": DIRECT_PLAN_SCHEMA,
        "plan_id": plan_id,
        "argv": request.argv,
        "cwd": str(request.cwd),
        "candidate_ids": request.candidate_allocation.candidate_ids,
        "selected_ids": selected_ids,
        "candidate_source": request.candidate_allocation.source,
        "candidate_inventory_fingerprint": request.candidate_allocation.inventory_fingerprint,
        "candidate_mig_parent_by_uuid": dict(
            request.candidate_allocation.mig_parent_by_uuid
        ),
        "requested_gpu_count": request.gpu_count,
        "minimum_free_memory_bytes": request.minimum_free_memory_bytes,
        "selected_free_memory_bytes": {
            uuid: final.free_memory_bytes[uuid] for uuid in selected_ids
        },
        "initial_unit_states": {
            uuid: initial_occupancy.unit_states.get(uuid, "UNKNOWN")
            for uuid in request.candidate_allocation.candidate_ids
        },
        "final_unit_states": {
            uuid: final_occupancy.unit_states.get(uuid, "UNKNOWN")
            for uuid in request.candidate_allocation.candidate_ids
        },
        "initial_observation_fingerprint": initial.fingerprint,
        "final_observation_fingerprint": final.fingerprint,
        "initial_event_id": initial.observation_event_id,
        "final_event_id": final.observation_event_id,
        "reservation_fingerprint": reservation.evidence_fingerprint,
        "reservation_ids": tuple(reservation_ids),
        "lock_identities": tuple(
            (lock.device, lock.inode) for lock in reservation.locks
        ),
        "admission_fingerprint": admission.admission_fingerprint,
        "base_environment_fingerprint": base_environment_fingerprint,
        "environment_key_witness": dict(
            _environment_key_witness(request.environment)
        ),
        "output_dir": str(request.output_dir),
        "unknown_initial_ids": initial_occupancy.unknown_uuids,
        "unknown_final_ids": final_occupancy.unknown_uuids,
    }
    return FrozenDirectGpuCommandPlan(
        **payload,
        plan_fingerprint=_fingerprint(payload),
    )


def materialize_direct_environment(
    plan: FrozenDirectGpuCommandPlan,
    base_environment: Mapping[str, str],
) -> MaterializedDirectEnvironment:
    """Derive exact full-UUID/JAX values from an already-frozen plan."""
    _validate_string_mapping(base_environment)
    selected_uuid_list = ",".join(plan.selected_ids)
    if not selected_uuid_list or any(
        _FULL_NVIDIA_UUID.fullmatch(uuid) is None for uuid in plan.selected_ids
    ):
        raise TypedPreflightFailure(
            "gpu_visibility_materialization_invalid",
            "selected visibility requires non-empty complete UUIDs",
            selected_ids=plan.selected_ids,
        )
    environment = dict(base_environment)
    environment["CUDA_VISIBLE_DEVICES"] = selected_uuid_list
    environment["NVIDIA_VISIBLE_DEVICES"] = selected_uuid_list
    environment.update(JAX_GPU_ENVIRONMENT)
    return MaterializedDirectEnvironment(
        schema_version=DIRECT_ENVIRONMENT_SCHEMA,
        plan_fingerprint=plan.plan_fingerprint,
        environment_fingerprint=_fingerprint(_environment_contract_items(environment)),
        exact_environment=environment,
        selected_uuid_list=selected_uuid_list,
        canonical_jax_environment=JAX_GPU_ENVIRONMENT,
    )


def _prepare_output_directory(request: DirectGpuCommandRequest) -> None:
    output_dir = request.output_dir
    try:
        output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise TypedPreflightFailure(
            "gpu_command_output_unavailable",
            "direct GPU command output directory could not be created",
            output_dir=str(output_dir),
            errno=exc.errno,
        ) from exc
    try:
        identity = os.lstat(output_dir)
    except OSError as exc:
        raise TypedPreflightFailure(
            "gpu_command_output_unavailable",
            "direct GPU command output directory identity is unavailable",
            output_dir=str(output_dir),
        ) from exc
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise TypedPreflightFailure(
            "gpu_command_output_invalid",
            "direct GPU command output must be a non-symlink directory",
            output_dir=str(output_dir),
            mode=identity.st_mode,
        )
    for filename in (
        "gpu_command_plan.json",
        "gpu_command_environment.json",
        "gpu_command_result.json",
        "gpu_command_failure.json",
        "stdout.log",
        "stderr.log",
    ):
        path = output_dir / filename
        if path.exists() or path.is_symlink():
            raise TypedPreflightFailure(
                "gpu_command_evidence_collision",
                "direct GPU command output files must not already exist",
                path=str(path),
            )


def _attempt_reservation_release(
    transaction: ReservationTransaction,
) -> tuple[tuple[FdReleaseEvidence, ...], BaseException | None]:
    """Call the transaction close path exactly once and retain any failure."""
    try:
        return tuple(transaction.close()), None
    except BaseException as exc:
        return (), exc


def _release_dispositions_complete(
    dispositions: Sequence[FdReleaseEvidence],
) -> bool:
    return bool(dispositions) and all(
        item.error_kind is None
        and item.disposition in {
            "busy_candidate",
            "released",
            "rolled_back",
        }
        for item in dispositions
    )


def _release_failure(
    *,
    primary_failure: BaseException | None,
    close_failure: BaseException | None,
    dispositions: Sequence[FdReleaseEvidence],
) -> TypedPreflightFailure:
    primary_code = (
        primary_failure.code
        if isinstance(primary_failure, TypedPreflightFailure)
        else type(primary_failure).__name__
        if primary_failure is not None
        else None
    )
    return TypedPreflightFailure(
        "gpu_reservation_release_failed",
        "direct command GPU reservation release was incomplete",
        primary_failure=primary_code,
        close_failure=(
            type(close_failure).__name__ if close_failure is not None else None
        ),
        close_failure_message=(
            str(close_failure) if close_failure is not None else None
        ),
        release_dispositions=tuple(
            {
                "uuid": item.uuid,
                "disposition": item.disposition,
                "error_kind": item.error_kind,
            }
            for item in dispositions
        ),
    )


def _release_record(
    dispositions: Sequence[FdReleaseEvidence],
) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {
            "component": item.component,
            "uuid": item.uuid,
            "disposition": item.disposition,
            "close_attempts": item.close_attempts,
            "error_kind": item.error_kind,
            "fingerprint": item.fingerprint,
        }
        for item in dispositions
    )


@dataclass(frozen=True)
class DirectGpuCommandResult:
    schema_version: Literal["agentcanon-gpu-command-result/v1"]
    plan: FrozenDirectGpuCommandPlan
    environment: MaterializedDirectEnvironment
    admission: RunGpuAdmissionReceipt
    execution: DirectCommandExecution
    release_dispositions: tuple[Mapping[str, object], ...]
    stdout_sha256: str
    stdout_bytes: int
    stderr_sha256: str
    stderr_bytes: int
    result_path: Path

    @property
    def returncode(self) -> int:
        return self.execution.returncode

    def record(self) -> Mapping[str, object]:
        lifecycle = self.execution.lifecycle.record()
        visibility = UuidVisibilityEvidence(
            cuda_visible_devices=self.environment.selected_uuid_list,
            nvidia_visible_devices=self.environment.selected_uuid_list,
            disposition="explicit",
            visible_uuids=self.plan.selected_ids,
            namespace_id=f"pid-session:{self.execution.lifecycle.session_id}",
            provision_receipt_fingerprint=self.admission.runtime_identity_fingerprint,
            fingerprint=_fingerprint(
                {
                    "plan_fingerprint": self.plan.plan_fingerprint,
                    "selected_ids": self.plan.selected_ids,
                    "session_id": self.execution.lifecycle.session_id,
                }
            ),
        )
        descendant = DescendantRetentionEvidence(
            child_process_ids=(self.execution.lifecycle.child_pid,),
            process_group_ids=(self.execution.lifecycle.process_group_id,),
            descendant_quiescence="PROVEN",
            retained_gpu_process_uuids=(),
            release_blocked=False,
            fingerprint=_fingerprint(dict(lifecycle)),
        )
        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "plan_id": self.plan.plan_id,
                "plan_fingerprint": self.plan.plan_fingerprint,
                "admission_fingerprint": self.admission.admission_fingerprint,
                "environment_fingerprint": self.environment.environment_fingerprint,
                "argv": self.plan.argv,
                "cwd": self.plan.cwd,
                "candidate_gpu_ids": self.plan.candidate_ids,
                "selected_gpu_ids": self.plan.selected_ids,
                "selected_free_memory_bytes": dict(
                    self.plan.selected_free_memory_bytes
                ),
                "reservation_ids": self.plan.reservation_ids,
                "lock_identities": self.plan.lock_identities,
                "raw_returncode": self.execution.returncode,
                "process_exit_code": (
                    self.execution.returncode
                    if self.execution.returncode >= 0
                    else 128 + abs(self.execution.returncode)
                ),
                "stdout": {
                    "path": str(self.execution.stdout_path),
                    "sha256": self.stdout_sha256,
                    "bytes": self.stdout_bytes,
                },
                "stderr": {
                    "path": str(self.execution.stderr_path),
                    "sha256": self.stderr_sha256,
                    "bytes": self.stderr_bytes,
                },
                "lifecycle": dict(lifecycle),
                "container_visible_uuid_mapping": {
                    "cuda_visible_devices": visibility.cuda_visible_devices,
                    "nvidia_visible_devices": visibility.nvidia_visible_devices,
                    "visible_uuids": visibility.visible_uuids,
                    "namespace_id": visibility.namespace_id,
                    "fingerprint": visibility.fingerprint,
                },
                "descendant_retention_evidence": {
                    "child_process_ids": descendant.child_process_ids,
                    "process_group_ids": descendant.process_group_ids,
                    "descendant_quiescence": descendant.descendant_quiescence,
                    "release_blocked": descendant.release_blocked,
                    "fingerprint": descendant.fingerprint,
                },
                "release_dispositions": self.release_dispositions,
                "managed_provider_required": False,
                "shell": False,
                "signal_or_kill_sent": False,
            }
        )


class DirectGpuCommandRunner:
    """Compose admission, freeze, exact environment, execution, and release."""

    def __init__(
        self,
        *,
        probe_factory: ProbeFactory = _production_probe_factory,
        reservation_factory: ReservationFactory = _production_reservation_factory,
        executor: DirectCommandExecutor | None = None,
    ) -> None:
        self._probe_factory = probe_factory
        self._reservation_factory = reservation_factory
        self._executor = executor or LinuxSubreaperCommandExecutor()

    def run(self, request: DirectGpuCommandRequest) -> DirectGpuCommandResult:
        _prepare_output_directory(request)
        transaction: ReservationTransaction | None = None
        release_dispositions: tuple[FdReleaseEvidence, ...] = ()
        release_close_failure: BaseException | None = None
        child_started = False
        descendant_quiescence_proven = False
        execution: DirectCommandExecution | None = None
        plan: FrozenDirectGpuCommandPlan | None = None
        materialized: MaterializedDirectEnvironment | None = None
        admission: RunGpuAdmissionReceipt | None = None
        try:
            probe_environment = _probe_environment(request)
            initial = self._probe_factory(
                probe_environment,
                request.gpu_count,
                request.runtime_root,
            ).observe()
            _validate_candidate_topology(request, initial, phase="initial")
            initial_occupancy = _observe_occupancy(initial)
            eligible = _eligible_ids(request, initial, initial_occupancy)
            if len(eligible) < request.gpu_count:
                raise TypedPreflightFailure(
                    "gpu_candidate_unavailable",
                    "FREE, memory-qualified GPU candidates cannot satisfy the request",
                    candidate_uuids=request.candidate_allocation.candidate_ids,
                    eligible_uuids=eligible,
                    occupied_uuids=initial_occupancy.occupied_uuids,
                    unknown_uuids=initial_occupancy.unknown_uuids,
                    unit_states=dict(initial_occupancy.unit_states),
                )
            transaction = self._reservation_factory(request.lock_root)
            reservation = transaction.try_reserve(
                eligible,
                occupied_uuids=tuple(
                    sorted(
                        set(initial_occupancy.occupied_uuids)
                        | set(initial_occupancy.unknown_uuids)
                    )
                ),
                requested_count=request.gpu_count,
            )
            if (
                reservation.disposition != "ACQUIRED"
                or len(reservation.selected_uuids) != request.gpu_count
            ):
                raise TypedPreflightFailure(
                    "gpu_candidate_unavailable",
                    "UUID lock acquisition could not satisfy the direct command request",
                    eligible_uuids=eligible,
                    selected_uuids=reservation.selected_uuids,
                    disposition=reservation.disposition,
                )
            final = self._probe_factory(
                probe_environment,
                request.gpu_count,
                request.runtime_root,
            ).observe()
            _validate_candidate_topology(request, final, phase="post_lock")
            final_occupancy = _observe_occupancy(final)
            _validate_fresh_post_lock_observation(
                request,
                initial,
                final,
                final_occupancy,
                reservation.selected_uuids,
            )
            admission = _build_admission_receipt(
                request,
                initial,
                final,
                initial_occupancy,
                final_occupancy,
                reservation,
            )
            plan = freeze_direct_gpu_command_plan(
                request,
                initial=initial,
                final=final,
                initial_occupancy=initial_occupancy,
                final_occupancy=final_occupancy,
                reservation=reservation,
                reservation_ids=transaction.reservation_ids,
                admission=admission,
            )
            _write_json_once(
                request.output_dir / "gpu_command_plan.json",
                plan.record(),
            )
            materialized = materialize_direct_environment(
                plan,
                request.environment,
            )
            _write_json_once(
                request.output_dir / "gpu_command_environment.json",
                materialized.record(),
            )
            execution = self._executor.execute(
                plan,
                materialized.exact_environment,
                stdout_path=request.output_dir / "stdout.log",
                stderr_path=request.output_dir / "stderr.log",
                poll_seconds=request.descendant_poll_seconds,
            )
            child_started = True
            if execution.lifecycle.descendant_quiescence != "PROVEN":
                raise TypedPreflightFailure(
                    "gpu_reservation_release_blocked",
                    "direct command GPU reservation cannot release before descendant quiescence",
                )
            descendant_quiescence_proven = True
            assert transaction is not None
            owned_transaction = transaction
            transaction = None
            release_dispositions, release_close_failure = (
                _attempt_reservation_release(owned_transaction)
            )
            if (
                release_close_failure is not None
                or not _release_dispositions_complete(release_dispositions)
            ):
                raise _release_failure(
                    primary_failure=None,
                    close_failure=release_close_failure,
                    dispositions=release_dispositions,
                )
            stdout_sha256, stdout_bytes = _hash_file(execution.stdout_path)
            stderr_sha256, stderr_bytes = _hash_file(execution.stderr_path)
            result_path = request.output_dir / "gpu_command_result.json"
            result = DirectGpuCommandResult(
                schema_version=DIRECT_RESULT_SCHEMA,
                plan=plan,
                environment=materialized,
                admission=admission,
                execution=execution,
                release_dispositions=_release_record(release_dispositions),
                stdout_sha256=stdout_sha256,
                stdout_bytes=stdout_bytes,
                stderr_sha256=stderr_sha256,
                stderr_bytes=stderr_bytes,
                result_path=result_path,
            )
            _write_json_once(result_path, result.record())
            return result
        except BaseException as exc:
            effective_failure = exc
            if isinstance(exc, DirectCommandPostLaunchFailure):
                execution = exc.execution
                child_started = True
                descendant_quiescence_proven = (
                    execution.lifecycle.descendant_quiescence == "PROVEN"
                )
                effective_failure = exc.cause
            if transaction is not None and (
                not child_started or descendant_quiescence_proven
            ):
                owned_transaction = transaction
                transaction = None
                release_dispositions, release_close_failure = (
                    _attempt_reservation_release(owned_transaction)
                )
                if (
                    release_close_failure is not None
                    or not _release_dispositions_complete(release_dispositions)
                ):
                    effective_failure = _release_failure(
                        primary_failure=effective_failure,
                        close_failure=release_close_failure,
                        dispositions=release_dispositions,
                    )
            failure_code = (
                effective_failure.code
                if isinstance(effective_failure, TypedPreflightFailure)
                else type(effective_failure).__name__
            )
            evidence = (
                dict(effective_failure.evidence)
                if isinstance(effective_failure, TypedPreflightFailure)
                else {}
            )
            lifecycle = (
                dict(execution.lifecycle.record())
                if execution is not None
                else None
            )
            failure_record = {
                "schema_version": DIRECT_FAILURE_SCHEMA,
                "failure_code": failure_code,
                "message": str(effective_failure),
                "evidence": evidence,
                "plan_fingerprint": (
                    plan.plan_fingerprint if plan is not None else None
                ),
                "environment_fingerprint": (
                    materialized.environment_fingerprint
                    if materialized is not None
                    else None
                ),
                "admission_fingerprint": (
                    admission.admission_fingerprint
                    if admission is not None
                    else None
                ),
                "release_dispositions": _release_record(release_dispositions),
                "release_close_failure": (
                    {
                        "type": type(release_close_failure).__name__,
                        "message": str(release_close_failure),
                    }
                    if release_close_failure is not None
                    else None
                ),
                "managed_provider_required": False,
                "child_started": child_started,
                "descendant_quiescence_proven": descendant_quiescence_proven,
                "release_blocked": transaction is not None,
                "lifecycle": lifecycle,
            }
            failure_path = request.output_dir / "gpu_command_failure.json"
            if not failure_path.exists():
                _write_json_once(failure_path, failure_record)
            if effective_failure is exc:
                raise
            raise effective_failure from exc


def forward_command_output(result: DirectGpuCommandResult) -> None:
    """Copy captured child bytes to this process without tool-owned decoration."""
    for path, stream in (
        (result.execution.stdout_path, sys.stdout.buffer),
        (result.execution.stderr_path, sys.stderr.buffer),
    ):
        with path.open("rb") as source:
            shutil.copyfileobj(source, stream, length=1024 * 1024)
        stream.flush()


def process_exit_code(raw_returncode: int) -> int:
    """Map subprocess signal returns to the conventional process exit domain."""
    return raw_returncode if raw_returncode >= 0 else 128 + abs(raw_returncode)
