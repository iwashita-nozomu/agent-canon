#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the immutable ExecutionResourcePlan transaction, canonical GPU allocation, ExperimentRunner handoff, and completion coverage.
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md approved AgentCanon GPU admission R5 U-18 implementation frame and exact packet identity
# upstream design ../../documents/design/experiment_runner.md ExperimentRunner lifecycle and scheduler boundary
# upstream design ../../agents/skills/gpu-execution.md UUID GPU and readback contract
# upstream design ../../documents/structure/repo-structure-contract.toml tree capability authority
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json validation failure taxonomy authority
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md validation failure reader projection
# upstream design ../../documents/experiments/gpu-admission-r5-nvidia-visibility.md official nvidia-smi C/G/M/O/C+G/M+C process visibility, PID/start/container mapping, MIG UUID mapping
# downstream implementation ./run_managed_experiment.py managed experiment adapter
# downstream implementation ../agent_tools/jit_canonical_ir.py GPU requests must route here or fail typed preflight
# downstream implementation ../../experiments/_template/run.py direct GPU launch is statically prohibited
# downstream environment ../../.devcontainer/bootstrap-shared-runtime.sh publishes the provision receipt through this owner
# downstream environment ../../.devcontainer/finalize-shared-runtime.sh parses and publishes runtime receipts through this owner
# @dependency-end

# Static consumer closure: run_managed_experiment.py is the only managed-run
# consumer; generic lifecycle remains in the fixed ff97 ExperimentRunner source.

"""Canonical execution resource planning for managed ExperimentRunner runs.

This module deliberately owns the complete resource transaction.  Callers may
provide observations and an ExperimentRunner transport, but they cannot add a
second GPU policy, mutate a frozen plan, or fall back to a different execution
mode when the requested allocation is unavailable.
"""

from __future__ import annotations

import hashlib
import errno
import ctypes
import json
import os
import re
import secrets
import stat
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Literal, Mapping, Protocol, Sequence, TypeAlias, cast

if TYPE_CHECKING:
    from experiment_runner import RunnerLifecycleEvidence

try:
    import fcntl
except ImportError:  # pragma: no cover - this owner is Unix/container-only.
    fcntl = None  # type: ignore[assignment]


PLAN_SCHEMA_VERSION = "execution-resource-plan/v1"
ENVIRONMENT_CERTIFICATE_SCHEMA_VERSION = "environment-certificate/v1"
COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION = "completion-coverage/v2"
HOST_RUNTIME_ROOT = "/var/lib/agent-canon/runtime"
CONTAINER_RUNTIME_ROOT = "/var/lib/agent-canon/runtime"
RUNTIME_ROOT = Path(HOST_RUNTIME_ROOT)
LOCK_ROOT = RUNTIME_ROOT / "locks"
SOURCE_PROJECTION_TEMPLATE = "/workspace/reports/agents/{run_id}/runtime"
STRUCTURE_CONTRACT_REF = "documents/structure/repo-structure-contract.toml"
VALIDATION_TAXONOMY_REF = "documents/runtime/runtime-profiles-and-check-matrix.json"
VALIDATION_TAXONOMY_READER_REF = "documents/runtime/runtime-profiles-and-check-matrix.md"
DESIGN_MANAGER_ARTIFACT = "reports/agents/w1-tool-env-routing-20260716/design_partition.json"
DESIGN_AUTHORITY_ARTIFACT = "reports/agents/w1-tool-env-routing-20260716/design_brief.md"
DESIGN_REVIEW_AUTHORITY_ARTIFACT = "reports/agents/w1-tool-env-routing-20260716/design_review.md"
APPROVED_DESIGN_BRIEF_SHA256 = "c103be1a2c37a150465194e00770548680c624eed6e0ed0e41b83e3151307305"
APPROVED_DESIGN_PARTITION_SHA256 = "4719b6da8d96811fec132e9b5e166785ae272fc45d9af480d7c6869ab2da0cca"
APPROVED_DESIGN_REVISION = "W1-DESIGN-20260716-R3-GPU-COMPLETIONCOVERAGE-REPAIR"
ORGANIZER_CONTEXT_ID = "019f6480-0e7d-73a2-9838-e343adc44457"
MANAGED_RUN_ADAPTER_PATH = "tools/experiments/run_managed_experiment.py"
PARENT_LINEAGE_ARTIFACT = "reports/agents/w1-tool-env-routing-20260716/control_topology_ledger.md"
ALTERNATE_GPU_ROUTE_STATIC_CONTRACT = (
    "tools/agent_tools/jit_canonical_ir.py",
    "experiments/_template/run.py",
    MANAGED_RUN_ADAPTER_PATH,
)
CALLER_ALLOCATION_PROVENANCE = "caller_scheduler_allocated_uuid_set"
COMPLETION_COVERAGE_FILENAME = "completion_coverage.json"
ENVIRONMENT_CERTIFICATE_FILENAME = "environment_certificate.json"
SIDE_EFFECT_INVENTORY_FILENAME = "os_side_effect_inventory.json"
TERMINAL_EVIDENCE_FILENAME = "terminal_evidence.json"
PARTIAL_EVIDENCE_FILENAME = "partial_evidence.json"
CLEANUP_EVIDENCE_FILENAME = "cleanup_evidence.json"
CLOSEOUT_INTENT_FILENAME = "closeout_intent.json"
CLOSEOUT_EVIDENCE_FILENAME = "closeout_evidence.json"
_PLANNER_PROVENANCE = object()
_MANAGED_RUN_INTEGRATION_PROVENANCE = object()

GPU_ENVIRONMENT_KEYS = frozenset(
    {
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "JAX_PLATFORMS",
        "XLA_PYTHON_CLIENT_PREALLOCATE",
        "XLA_PYTHON_CLIENT_ALLOCATOR",
        "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR",
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


class _PlannerAttemptFailure(ResourcePlanError):
    def __init__(self, cause: Exception, leases: Sequence[ReservationLease]) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.leases = tuple(leases)


RuntimeRoute: TypeAlias = Literal["MANAGED_CONTAINER", "HOST_DIRECT"]
VisibilityDisposition: TypeAlias = Literal["explicit", "all", "unset"]
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
Sha256Hex: TypeAlias = str
AbsolutePosixPath: TypeAlias = str
RelativePosixPath: TypeAlias = str
FullGpuUuid: TypeAlias = str
FullMigUuid: TypeAlias = str
EvidenceAbsenceField: TypeAlias = Literal[
    "source_freeze_evidence",
    "lock_readback",
    "effective_environment",
    "actual_gpu_processes",
    "concurrent_run_evidence",
    "mig_evidence",
    "container_visible_uuid_mapping",
    "os_safe_lock_placement",
    "descendant_retention_evidence",
]
EvidenceDisposition: TypeAlias = Literal["not_reached", "failed"]
_EVIDENCE_ABSENCE_FIELD_ORDER = (
    "source_freeze_evidence",
    "lock_readback",
    "effective_environment",
    "actual_gpu_processes",
    "concurrent_run_evidence",
    "mig_evidence",
    "container_visible_uuid_mapping",
    "os_safe_lock_placement",
    "descendant_retention_evidence",
)

SOURCE_FREEZE_SCHEMA_VERSION = "source-freeze/v2"
RUNTIME_IDENTITY_SCHEMA_VERSION = "runtime-identity/v1"
SHARED_RUNTIME_PROVISION_SCHEMA_VERSION = "shared-runtime-provision/v1"
SHARED_RUNTIME_READBACK_SCHEMA_VERSION = "shared-runtime-readback/v1"
PROCESS_UMASK = 0o0007
_AT_EMPTY_PATH = 0x1000


@dataclass(frozen=True)
class EvidenceAbsence:
    """Typed absence for one pre-active coverage evidence field."""

    field_name: EvidenceAbsenceField
    disposition: EvidenceDisposition
    failure_kind: str | None
    fingerprint: Sha256Hex


def validate_absolute_posix_path(raw: str) -> AbsolutePosixPath:
    """Validate an absolute path without following any symlink component."""
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise TypedPreflightFailure(
            "runtime_path_invalid",
            "runtime paths must be non-empty NUL-free strings",
        )
    if not raw.startswith("/") or raw == "/":
        raise TypedPreflightFailure(
            "runtime_path_invalid",
            "runtime paths must be absolute POSIX paths with components",
            path=raw,
        )
    components = raw.split("/")[1:]
    if any(component in {"", ".", ".."} for component in components):
        raise TypedPreflightFailure(
            "runtime_path_invalid",
            "runtime paths must not contain empty, dot, or traversal components",
            path=raw,
        )
    current = Path("/")
    for component in components:
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            raise TypedPreflightFailure(
                "runtime_path_unreadable",
                "runtime path component could not be inspected",
                path=raw,
                component=str(current),
                errno=exc.errno,
            ) from exc
        if stat.S_ISLNK(mode):
            raise TypedPreflightFailure(
                "runtime_path_symlink",
                "runtime paths must not contain symlink components",
                path=raw,
                component=str(current),
            )
    return raw


def _canonical_fingerprint(payload: Mapping[str, object], field_name: str) -> Sha256Hex:
    without_fingerprint = {
        key: value for key, value in payload.items() if key != field_name
    }
    return hashlib.sha256(
        (_canonical_json(_json_safe(without_fingerprint))).encode("utf-8")
    ).hexdigest()


def _strict_json_object(raw: bytes, *, path: str) -> dict[str, JsonValue]:
    """Decode one canonical JSON object while rejecting duplicate keys."""
    duplicate = object()

    def pairs(items: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in items:
            if key in result:
                raise TypedPreflightFailure(
                    "runtime_receipt_invalid",
                    "runtime receipts must not contain duplicate JSON keys",
                    path=path,
                    key=key,
                )
            result[key] = value
        return result

    del duplicate
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime receipts must be UTF-8 JSON",
            path=path,
        ) from exc
    if not isinstance(decoded, dict):
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime receipts must contain one JSON object",
            path=path,
        )
    return decoded


def _read_runtime_receipt(
    path: AbsolutePosixPath,
) -> tuple[dict[str, JsonValue], os.stat_result]:
    validate_absolute_posix_path(path)
    parent = os.path.dirname(path)
    name = os.path.basename(path)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    directory = -1
    descriptor = -1
    try:
        directory = os.open(parent, directory_flags)
        descriptor = os.open(name, flags, dir_fd=directory)
    except OSError as exc:
        if directory >= 0:
            os.close(directory)
        raise TypedPreflightFailure(
            "runtime_receipt_unavailable",
            "runtime receipt could not be opened with no-follow flags",
            path=path,
            errno=exc.errno,
        ) from exc
    try:
        parent_stat = os.fstat(directory)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_dev != parent_stat.st_dev
            or stat.S_IMODE(before.st_mode) != 0o660
            or before.st_uid != parent_stat.st_uid
            or before.st_gid != parent_stat.st_gid
            or before.st_size <= 0
            or before.st_size > 65536
        ):
            raise TypedPreflightFailure(
                "runtime_receipt_invalid",
                "runtime receipt fd identity, mode, owner, group, or size is invalid",
                path=path,
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mode,
            before.st_uid,
            before.st_gid,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise TypedPreflightFailure(
                "runtime_receipt_raced",
                "runtime receipt identity changed while reading",
                path=path,
            )
        return _strict_json_object(b"".join(chunks), path=path), before
    finally:
        os.close(descriptor)
        os.close(directory)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except InterruptedError:
            raise TypedPreflightFailure(
                "runtime_receipt_write_ambiguous",
                "receipt write was interrupted and is not retried",
            )
        if written <= 0:
            raise TypedPreflightFailure(
                "runtime_receipt_write_failed",
                "receipt write made no progress",
            )
        offset += written


def _link_tmpfile(descriptor: int, directory: int, name: bytes) -> None:
    libc = __import__("ctypes").CDLL(None, use_errno=True)
    linkat = libc.linkat
    linkat.argtypes = [
        __import__("ctypes").c_int,
        __import__("ctypes").c_char_p,
        __import__("ctypes").c_int,
        __import__("ctypes").c_char_p,
        __import__("ctypes").c_int,
    ]
    linkat.restype = __import__("ctypes").c_int
    if linkat(descriptor, b"", directory, name, _AT_EMPTY_PATH) != 0:
        error_number = __import__("ctypes").get_errno()
        raise TypedPreflightFailure(
            "runtime_receipt_publish_failed",
            "temporary runtime receipt could not be linked atomically",
            errno=error_number,
        )


def write_runtime_receipt_atomic(
    path: AbsolutePosixPath,
    payload: Mapping[str, JsonValue],
) -> None:
    """Publish one canonical receipt atomically under the runtime receipt lock."""
    validate_absolute_posix_path(path)
    if fcntl is None:
        raise TypedPreflightFailure(
            "runtime_receipt_lock_unavailable",
            "runtime receipt publication requires POSIX flock",
            path=path,
        )
    parent = os.path.dirname(path)
    name = os.path.basename(path).encode("utf-8")
    lock_path = os.path.join(parent, "locks", "shared-runtime-receipt.lock")
    validate_absolute_posix_path(lock_path)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    temporary_flags = os.O_WRONLY | os.O_TMPFILE | os.O_CLOEXEC
    directory = os.open(parent, directory_flags)
    lock_descriptor = -1
    descriptor = -1
    staging_name: bytes | None = None
    try:
        parent_stat = os.fstat(directory)
        try:
            lock_descriptor = os.open(
                lock_path,
                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o660,
            )
        except OSError as exc:
            raise TypedPreflightFailure(
                "runtime_receipt_lock_unavailable",
                "runtime receipt publication lock could not be opened",
                path=lock_path,
                errno=exc.errno,
            ) from exc
        lock_stat = os.fstat(lock_descriptor)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_dev != parent_stat.st_dev
            or stat.S_IMODE(lock_stat.st_mode) != 0o660
            or lock_stat.st_uid != parent_stat.st_uid
            or lock_stat.st_gid != parent_stat.st_gid
        ):
            raise TypedPreflightFailure(
                "runtime_receipt_lock_tampered",
                "runtime receipt publication lock identity is not exact",
                path=lock_path,
            )
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)

        descriptor = os.open(".", temporary_flags, 0o660, dir_fd=directory)
        os.fchmod(descriptor, 0o660)
        encoded = (_canonical_json(_json_safe(payload)) + "\n").encode("utf-8")
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        try:
            existing = os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is None:
            _link_tmpfile(descriptor, directory, name)
        else:
            if (
                not stat.S_ISREG(existing.st_mode)
                or existing.st_dev != parent_stat.st_dev
                or stat.S_IMODE(existing.st_mode) != 0o660
                or existing.st_uid != parent_stat.st_uid
                or existing.st_gid != parent_stat.st_gid
            ):
                raise TypedPreflightFailure(
                    "runtime_receipt_target_tampered",
                    "runtime receipt target identity is not replaceable",
                    path=path,
                )
            staging_name = (
                f".{os.path.basename(path)}.{secrets.token_hex(16)}.tmp".encode("utf-8")
            )
            _link_tmpfile(descriptor, directory, staging_name)
            os.replace(
                staging_name,
                name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
            )
            staging_name = None
        os.fsync(directory)
    finally:
        if staging_name is not None:
            try:
                os.unlink(staging_name, dir_fd=directory)
            except FileNotFoundError:
                pass
        if descriptor >= 0:
            os.close(descriptor)
        if lock_descriptor >= 0:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            finally:
                os.close(lock_descriptor)
        os.close(directory)


@dataclass(frozen=True)
class GpuRunRequest:
    gpu_count: int
    minimum_memory_bytes_per_unit: int
    max_workers: int
    host_memory_bytes: int
    cuda_runtime_library_path: str | None
    environment: Mapping[str, str]
    source_root: AbsolutePosixPath
    runtime_route: RuntimeRoute
    source_paths: tuple[RelativePosixPath, ...]
    planned_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class SharedRuntimeProvisionReceipt:
    schema_version: Literal["shared-runtime-provision/v1"]
    runtime_route: RuntimeRoute
    host_uid: int
    host_gid: int
    host_supplementary_gids: tuple[int, ...]
    host_umask: int
    bind_source_path: AbsolutePosixPath
    bind_source_dev: int
    bind_source_ino: int
    provision_fingerprint: Sha256Hex


@dataclass(frozen=True)
class SourceFileRecord:
    relative_path: RelativePosixPath
    source_kind: Literal["tracked", "dirty", "untracked"]
    st_dev: int
    st_ino: int
    st_mode: int
    st_size: int
    st_mtime_ns: int
    st_ctime_ns: int
    sha256: Sha256Hex
    byte_count: int


@dataclass(frozen=True)
class SourceSnapshotRecord:
    relative_path: RelativePosixPath
    source_dev: int
    source_ino: int
    source_byte_count: int
    source_sha256: Sha256Hex
    snapshot_relative_path: RelativePosixPath
    snapshot_dev: int
    snapshot_ino: int
    snapshot_byte_count: int
    snapshot_sha256: Sha256Hex


@dataclass(frozen=True)
class SourceSnapshotManifest:
    schema_version: Literal["source-snapshot/v2"]
    source_root_dev: int
    source_root_ino: int
    source_commit: str
    source_tree: str
    records: tuple[SourceSnapshotRecord, ...]
    manifest_fingerprint: Sha256Hex


@dataclass(frozen=True)
class SourceFreezeReceipt:
    schema_version: Literal["source-freeze/v2"]
    runtime_route: RuntimeRoute
    source_root_path: AbsolutePosixPath
    source_root_dev: int
    source_root_ino: int
    source_commit: str
    source_tree: str
    files: tuple[SourceFileRecord, ...]
    source_paths: tuple[RelativePosixPath, ...]
    snapshot_root_relative_path: RelativePosixPath
    snapshot_relative_path: RelativePosixPath
    snapshot_manifest_fingerprint: Sha256Hex
    receipt_fingerprint: Sha256Hex


@dataclass(frozen=True)
class SharedRuntimeReadbackReceipt:
    schema_version: Literal["shared-runtime-readback/v1"]
    runtime_route: RuntimeRoute
    container_uid: int
    container_gid: int
    container_supplementary_gids: tuple[int, ...]
    container_umask: int
    bind_target_path: AbsolutePosixPath
    bind_target_dev: int
    bind_target_ino: int
    namespace_inode: int
    mount_id: int
    mount_parent_id: int
    mount_root: str
    probe_fd_disposition: Literal["closed"]
    readback_fingerprint: Sha256Hex


@dataclass(frozen=True)
class RuntimeIdentityReceipt:
    schema_version: Literal["runtime-identity/v1"]
    runtime_route: RuntimeRoute
    namespace_inode: int
    uid: int
    gid: int
    supplementary_gids: tuple[int, ...]
    umask: int
    bind_source_dev: int
    bind_source_ino: int
    bind_target_dev: int
    bind_target_ino: int
    provision_fingerprint: Sha256Hex
    readback_fingerprint: Sha256Hex
    receipt_fingerprint: Sha256Hex


@dataclass(frozen=True)
class CudaRuntimeCapabilityReceipt:
    """The capability obtained from one exact configured CUDA library fd."""

    schema_version: Literal["cuda-runtime-capability/v1"]
    library_realpath: str
    library_sha256: Sha256Hex
    cuda_runtime_get_version_raw: int
    cuda_runtime_major: int
    cuda_runtime_minor: int
    receipt_fingerprint: Sha256Hex


def _receipt_field(
    payload: Mapping[str, JsonValue],
    name: str,
    expected_type: type[object],
    *,
    path: str,
) -> object:
    value = payload.get(name)
    if expected_type is int:
        valid = type(value) is int
    else:
        valid = isinstance(value, expected_type)
    if not valid:
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime receipt field has the wrong type",
            path=path,
            field=name,
        )
    return value


def _receipt_gids(
    payload: Mapping[str, JsonValue],
    name: str,
    *,
    path: str,
) -> tuple[int, ...]:
    value = _receipt_field(payload, name, list, path=path)
    if any(type(item) is not int or item < 0 for item in cast(list[object], value)):
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime supplementary groups must be non-negative integers",
            path=path,
            field=name,
        )
    groups = tuple(cast(list[int], value))
    if groups != tuple(sorted(set(groups))):
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime supplementary groups must be sorted and unique",
            path=path,
            field=name,
        )
    return groups


def _require_receipt_shape(
    payload: Mapping[str, JsonValue],
    fields: frozenset[str],
    *,
    path: str,
) -> None:
    if set(payload) != fields:
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime receipt schema contains missing or extra fields",
            path=path,
            expected_fields=tuple(sorted(fields)),
            observed_fields=tuple(sorted(payload)),
        )


def read_shared_runtime_provision(
    path: AbsolutePosixPath,
) -> SharedRuntimeProvisionReceipt:
    payload, receipt_stat = _read_runtime_receipt(path)
    _require_receipt_shape(
        payload,
        frozenset(
            {
                "schema_version",
                "runtime_route",
                "host_uid",
                "host_gid",
                "host_supplementary_gids",
                "host_umask",
                "bind_source_path",
                "bind_source_dev",
                "bind_source_ino",
                "provision_fingerprint",
            }
        ),
        path=path,
    )
    schema_version = _receipt_field(payload, "schema_version", str, path=path)
    route = _receipt_field(payload, "runtime_route", str, path=path)
    bind_source_path = _receipt_field(payload, "bind_source_path", str, path=path)
    if schema_version != SHARED_RUNTIME_PROVISION_SCHEMA_VERSION:
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime provision receipt schema version is unsupported",
            path=path,
        )
    if route not in {"MANAGED_CONTAINER", "HOST_DIRECT"}:
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime provision receipt route is unsupported",
            path=path,
        )
    validate_absolute_posix_path(cast(str, bind_source_path))
    typed_payload = {
        "schema_version": schema_version,
        "runtime_route": route,
        "host_uid": _receipt_field(payload, "host_uid", int, path=path),
        "host_gid": _receipt_field(payload, "host_gid", int, path=path),
        "host_supplementary_gids": _receipt_gids(
            payload,
            "host_supplementary_gids",
            path=path,
        ),
        "host_umask": _receipt_field(payload, "host_umask", int, path=path),
        "bind_source_path": bind_source_path,
        "bind_source_dev": _receipt_field(payload, "bind_source_dev", int, path=path),
        "bind_source_ino": _receipt_field(payload, "bind_source_ino", int, path=path),
        "provision_fingerprint": _receipt_field(
            payload,
            "provision_fingerprint",
            str,
            path=path,
        ),
    }
    expected = _canonical_fingerprint(typed_payload, "provision_fingerprint")
    if typed_payload["provision_fingerprint"] != expected:
        raise TypedPreflightFailure(
            "runtime_receipt_fingerprint_mismatch",
            "runtime provision receipt fingerprint does not match its payload",
            path=path,
        )
    if receipt_stat.st_uid != typed_payload["host_uid"]:
        raise TypedPreflightFailure(
            "runtime_receipt_identity_mismatch",
            "runtime provision receipt fd owner differs from its host identity",
            path=path,
        )
    return SharedRuntimeProvisionReceipt(
        schema_version=cast(
            Literal["shared-runtime-provision/v1"],
            typed_payload["schema_version"],
        ),
        runtime_route=cast(RuntimeRoute, typed_payload["runtime_route"]),
        host_uid=cast(int, typed_payload["host_uid"]),
        host_gid=cast(int, typed_payload["host_gid"]),
        host_supplementary_gids=cast(
            tuple[int, ...],
            typed_payload["host_supplementary_gids"],
        ),
        host_umask=cast(int, typed_payload["host_umask"]),
        bind_source_path=cast(
            AbsolutePosixPath,
            typed_payload["bind_source_path"],
        ),
        bind_source_dev=cast(int, typed_payload["bind_source_dev"]),
        bind_source_ino=cast(int, typed_payload["bind_source_ino"]),
        provision_fingerprint=cast(
            Sha256Hex,
            typed_payload["provision_fingerprint"],
        ),
    )


def read_shared_runtime_readback(
    path: AbsolutePosixPath,
) -> SharedRuntimeReadbackReceipt:
    payload, receipt_stat = _read_runtime_receipt(path)
    _require_receipt_shape(
        payload,
        frozenset(
            {
                "schema_version",
                "runtime_route",
                "container_uid",
                "container_gid",
                "container_supplementary_gids",
                "container_umask",
                "bind_target_path",
                "bind_target_dev",
                "bind_target_ino",
                "namespace_inode",
                "mount_id",
                "mount_parent_id",
                "mount_root",
                "probe_fd_disposition",
                "readback_fingerprint",
            }
        ),
        path=path,
    )
    schema_version = _receipt_field(payload, "schema_version", str, path=path)
    route = _receipt_field(payload, "runtime_route", str, path=path)
    bind_target_path = _receipt_field(payload, "bind_target_path", str, path=path)
    mount_root = _receipt_field(payload, "mount_root", str, path=path)
    probe_disposition = _receipt_field(
        payload,
        "probe_fd_disposition",
        str,
        path=path,
    )
    if schema_version != SHARED_RUNTIME_READBACK_SCHEMA_VERSION:
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime readback receipt schema version is unsupported",
            path=path,
        )
    if route not in {"MANAGED_CONTAINER", "HOST_DIRECT"}:
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime readback receipt route is unsupported",
            path=path,
        )
    if probe_disposition != "closed":
        raise TypedPreflightFailure(
            "runtime_receipt_invalid",
            "runtime readback receipt must report a closed probe",
            path=path,
        )
    validate_absolute_posix_path(cast(str, bind_target_path))
    typed_payload = {
        "schema_version": schema_version,
        "runtime_route": route,
        "container_uid": _receipt_field(payload, "container_uid", int, path=path),
        "container_gid": _receipt_field(payload, "container_gid", int, path=path),
        "container_supplementary_gids": _receipt_gids(
            payload,
            "container_supplementary_gids",
            path=path,
        ),
        "container_umask": _receipt_field(payload, "container_umask", int, path=path),
        "bind_target_path": bind_target_path,
        "bind_target_dev": _receipt_field(payload, "bind_target_dev", int, path=path),
        "bind_target_ino": _receipt_field(payload, "bind_target_ino", int, path=path),
        "namespace_inode": _receipt_field(payload, "namespace_inode", int, path=path),
        "mount_id": _receipt_field(payload, "mount_id", int, path=path),
        "mount_parent_id": _receipt_field(payload, "mount_parent_id", int, path=path),
        "mount_root": mount_root,
        "probe_fd_disposition": probe_disposition,
        "readback_fingerprint": _receipt_field(
            payload,
            "readback_fingerprint",
            str,
            path=path,
        ),
    }
    expected = _canonical_fingerprint(typed_payload, "readback_fingerprint")
    if typed_payload["readback_fingerprint"] != expected:
        raise TypedPreflightFailure(
            "runtime_receipt_fingerprint_mismatch",
            "runtime readback receipt fingerprint does not match its payload",
            path=path,
        )
    if receipt_stat.st_uid != typed_payload["container_uid"]:
        raise TypedPreflightFailure(
            "runtime_receipt_identity_mismatch",
            "runtime readback receipt fd owner differs from its container identity",
            path=path,
        )
    return SharedRuntimeReadbackReceipt(
        schema_version=cast(
            Literal["shared-runtime-readback/v1"],
            typed_payload["schema_version"],
        ),
        runtime_route=cast(RuntimeRoute, typed_payload["runtime_route"]),
        container_uid=cast(int, typed_payload["container_uid"]),
        container_gid=cast(int, typed_payload["container_gid"]),
        container_supplementary_gids=cast(
            tuple[int, ...],
            typed_payload["container_supplementary_gids"],
        ),
        container_umask=cast(int, typed_payload["container_umask"]),
        bind_target_path=cast(
            AbsolutePosixPath,
            typed_payload["bind_target_path"],
        ),
        bind_target_dev=cast(int, typed_payload["bind_target_dev"]),
        bind_target_ino=cast(int, typed_payload["bind_target_ino"]),
        namespace_inode=cast(int, typed_payload["namespace_inode"]),
        mount_id=cast(int, typed_payload["mount_id"]),
        mount_parent_id=cast(int, typed_payload["mount_parent_id"]),
        mount_root=cast(str, typed_payload["mount_root"]),
        probe_fd_disposition=cast(
            Literal["closed"],
            typed_payload["probe_fd_disposition"],
        ),
        readback_fingerprint=cast(
            Sha256Hex,
            typed_payload["readback_fingerprint"],
        ),
    )


class RuntimeIdentityReader:
    """Validate script-owned runtime receipts without mutating runtime state."""

    def read(
        self,
        provision: SharedRuntimeProvisionReceipt,
        readback: SharedRuntimeReadbackReceipt,
    ) -> RuntimeIdentityReceipt:
        if provision.runtime_route != readback.runtime_route:
            raise TypedPreflightFailure(
                "runtime_identity_mismatch",
                "provision and readback routes differ",
            )
        if (
            provision.host_uid != readback.container_uid
            or provision.host_gid != readback.container_gid
            or provision.host_supplementary_gids
            != readback.container_supplementary_gids
            or provision.host_umask != readback.container_umask
            or provision.bind_source_dev != readback.bind_target_dev
            or provision.bind_source_ino != readback.bind_target_ino
            or readback.probe_fd_disposition != "closed"
            or readback.namespace_inode <= 0
            or readback.mount_id <= 0
            or readback.mount_parent_id < 0
        ):
            raise TypedPreflightFailure(
                "runtime_identity_mismatch",
                "runtime provision/readback identity is not exact",
            )
        if provision.host_uid == 0:
            raise TypedPreflightFailure(
                "runtime_identity_invalid",
                "UID 0 is not a valid managed runtime identity",
            )
        receipt_payload = {
            "schema_version": RUNTIME_IDENTITY_SCHEMA_VERSION,
            "runtime_route": provision.runtime_route,
            "namespace_inode": readback.namespace_inode,
            "uid": provision.host_uid,
            "gid": provision.host_gid,
            "supplementary_gids": provision.host_supplementary_gids,
            "umask": provision.host_umask,
            "bind_source_dev": provision.bind_source_dev,
            "bind_source_ino": provision.bind_source_ino,
            "bind_target_dev": readback.bind_target_dev,
            "bind_target_ino": readback.bind_target_ino,
            "provision_fingerprint": provision.provision_fingerprint,
            "readback_fingerprint": readback.readback_fingerprint,
        }
        receipt_fingerprint = _canonical_fingerprint(
            receipt_payload,
            "receipt_fingerprint",
        )
        return RuntimeIdentityReceipt(
            schema_version=cast(
                Literal["runtime-identity/v1"],
                receipt_payload["schema_version"],
            ),
            runtime_route=cast(RuntimeRoute, receipt_payload["runtime_route"]),
            namespace_inode=cast(int, receipt_payload["namespace_inode"]),
            uid=cast(int, receipt_payload["uid"]),
            gid=cast(int, receipt_payload["gid"]),
            supplementary_gids=cast(
                tuple[int, ...],
                receipt_payload["supplementary_gids"],
            ),
            umask=cast(int, receipt_payload["umask"]),
            bind_source_dev=cast(int, receipt_payload["bind_source_dev"]),
            bind_source_ino=cast(int, receipt_payload["bind_source_ino"]),
            bind_target_dev=cast(int, receipt_payload["bind_target_dev"]),
            bind_target_ino=cast(int, receipt_payload["bind_target_ino"]),
            provision_fingerprint=cast(
                Sha256Hex,
                receipt_payload["provision_fingerprint"],
            ),
            readback_fingerprint=cast(
                Sha256Hex,
                receipt_payload["readback_fingerprint"],
            ),
            receipt_fingerprint=receipt_fingerprint,
        )


def capture_cuda_runtime_capability(
    path: str,
) -> CudaRuntimeCapabilityReceipt:
    """Read CUDA runtime capability from one exact configured library path."""
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise TypedPreflightFailure(
            "cuda_runtime_library_path_invalid",
            "CUDA runtime capability requires one absolute configured library path",
        )
    descriptor = -1
    library: object | None = None
    library_handle = 0
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise TypedPreflightFailure(
                "cuda_runtime_library_invalid",
                "configured CUDA runtime path is not a regular file",
            )
        content, before_hash = _pread_hash_all(descriptor)
        after = os.fstat(descriptor)
        if _source_stat_changed(before, after, len(content)):
            raise TypedPreflightFailure(
                "cuda_runtime_library_raced",
                "configured CUDA runtime changed during fd-bound hashing",
            )
        realpath = os.path.realpath(path)
        try:
            library = ctypes.CDLL(
                realpath,
                mode=ctypes.RTLD_LOCAL | ctypes.RTLD_NOW,
            )
            library_handle = int(getattr(library, "_handle", 0))
            if library_handle <= 0:
                raise AttributeError("CUDA runtime handle is missing")
            function = getattr(library, "cudaRuntimeGetVersion")
            function.argtypes = [ctypes.POINTER(ctypes.c_int)]
            function.restype = ctypes.c_int
            raw_version = ctypes.c_int(0)
            status = int(function(ctypes.byref(raw_version)))
            if status != 0 or raw_version.value <= 0:
                raise TypedPreflightFailure(
                    "cuda_runtime_capability_unproven",
                    "cudaRuntimeGetVersion did not return a positive successful value",
                    status=status,
                    raw_version=raw_version.value,
                )
            content_after, after_hash = _pread_hash_all(descriptor)
            final = os.fstat(descriptor)
            if (
                content_after != content
                or after_hash != before_hash
                or _source_stat_changed(after, final, len(content_after))
            ):
                raise TypedPreflightFailure(
                    "cuda_runtime_library_raced",
                    "configured CUDA runtime changed during capability lookup",
                )
            payload = {
                "schema_version": "cuda-runtime-capability/v1",
                "library_realpath": realpath,
                "library_sha256": before_hash,
                "cuda_runtime_get_version_raw": raw_version.value,
                "cuda_runtime_major": raw_version.value // 1000,
                "cuda_runtime_minor": (raw_version.value % 1000) // 10,
            }
            return CudaRuntimeCapabilityReceipt(
                schema_version="cuda-runtime-capability/v1",
                library_realpath=realpath,
                library_sha256=before_hash,
                cuda_runtime_get_version_raw=raw_version.value,
                cuda_runtime_major=raw_version.value // 1000,
                cuda_runtime_minor=(raw_version.value % 1000) // 10,
                receipt_fingerprint=_canonical_fingerprint(
                    payload,
                    "receipt_fingerprint",
                ),
            )
        except (AttributeError, OSError) as exc:
            raise TypedPreflightFailure(
                "cuda_runtime_capability_unproven",
                "configured CUDA runtime could not be loaded exactly",
            ) from exc
    finally:
        if library_handle:
            dlclose = getattr(ctypes, "_dlclose", None)
            if not callable(dlclose):
                raise TypedPreflightFailure(
                    "cuda_runtime_dlclose_unavailable",
                    "exact CUDA runtime handle closure is unavailable",
                )
            try:
                dlclose(library_handle)
                if library is not None:
                    setattr(library, "_handle", 0)
            except OSError as exc:
                raise TypedPreflightFailure(
                    "cuda_runtime_dlclose_failed",
                    "CUDA runtime handle closure failed",
                ) from exc
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                raise TypedPreflightFailure(
                    "cuda_runtime_library_close_ambiguous",
                    "CUDA runtime library fd close was ambiguous",
                ) from exc


class SourceFreezeOwner:
    """Own one fd-bound source freeze and its retained evidence descriptors."""

    def __init__(self, snapshot_result_root: AbsolutePosixPath) -> None:
        self._snapshot_result_root = validate_absolute_posix_path(snapshot_result_root)
        self._owned_fds: list[int] = []
        self._source_root_fd: int | None = None
        self._source_root_stat: tuple[int, int] | None = None
        self._source_root_path: AbsolutePosixPath | None = None
        self._closed = False
        self._frozen = False

    @staticmethod
    def fingerprint(record: Mapping[str, object]) -> Sha256Hex:
        return _canonical_fingerprint(record, "fingerprint")

    def freeze(self, request: GpuRunRequest) -> SourceFreezeReceipt:
        """Freeze exactly ``request.source_paths`` through retained source fds."""
        if self._closed:
            raise TypedPreflightFailure(
                "gpu_source_freeze_closed",
                "a closed source-freeze owner cannot be reused",
            )
        if self._frozen:
            raise TypedPreflightFailure(
                "gpu_source_freeze_repeated",
                "a source-freeze owner accepts exactly one freeze operation",
            )
        source_root = validate_absolute_posix_path(request.source_root)
        if request.runtime_route not in {"MANAGED_CONTAINER", "HOST_DIRECT"}:
            raise TypedPreflightFailure(
                "gpu_source_freeze_route_invalid",
                "source freeze runtime route is unsupported",
            )
        source_paths = _normalize_source_paths(request.source_paths)
        root_fd = self._register_fd(
            _open_source_root(source_root),
        )
        self._source_root_fd = root_fd
        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise TypedPreflightFailure(
                "gpu_source_freeze_root_invalid",
                "source root must be a directory",
                source_root=source_root,
            )
        self._source_root_stat = (root_stat.st_dev, root_stat.st_ino)
        self._source_root_path = source_root
        identity_fd = -1
        try:
            identity_fd = os.dup(root_fd)
            os.set_inheritable(identity_fd, True)
            source_commit, source_tree = _read_git_identity(identity_fd)
            result_dir_fd = self._open_destination_chain(self._snapshot_result_root)
            snapshot_dir_fd = self._open_or_create_directory(
                result_dir_fd,
                "source_snapshot",
            )
            records: list[SourceSnapshotRecord] = []
            files: list[SourceFileRecord] = []
            for relative_path in source_paths:
                source_fd = self._open_source_file(root_fd, relative_path)
                source_before = os.fstat(source_fd)
                if not stat.S_ISREG(source_before.st_mode):
                    raise TypedPreflightFailure(
                        "gpu_source_freeze_non_regular",
                        "source freeze accepts regular files only",
                        relative_path=relative_path,
                    )
                source_bytes, source_sha256 = _pread_hash_all(source_fd)
                source_after = os.fstat(source_fd)
                if _source_stat_changed(
                    source_before,
                    source_after,
                    len(source_bytes),
                ):
                    raise TypedPreflightFailure(
                        "gpu_source_freeze_raced",
                        "source identity changed during fd-bound read",
                        relative_path=relative_path,
                    )
                source_kind = _git_source_kind(identity_fd, relative_path)
                snapshot_relative_path = f"source_snapshot/{relative_path}"
                snapshot_fd, snapshot_stat = self._copy_to_snapshot(
                    snapshot_dir_fd,
                    relative_path,
                    source_bytes,
                )
                try:
                    snapshot_bytes, snapshot_sha256 = _pread_hash_all(snapshot_fd)
                finally:
                    os.close(snapshot_fd)
                if (
                    len(snapshot_bytes) != len(source_bytes)
                    or snapshot_sha256 != source_sha256
                ):
                    raise TypedPreflightFailure(
                        "gpu_source_snapshot_mismatch",
                        "snapshot bytes do not match the retained source fd",
                        relative_path=relative_path,
                    )
                records.append(
                    SourceSnapshotRecord(
                        relative_path=relative_path,
                        source_dev=source_before.st_dev,
                        source_ino=source_before.st_ino,
                        source_byte_count=len(source_bytes),
                        source_sha256=source_sha256,
                        snapshot_relative_path=snapshot_relative_path,
                        snapshot_dev=snapshot_stat.st_dev,
                        snapshot_ino=snapshot_stat.st_ino,
                        snapshot_byte_count=len(snapshot_bytes),
                        snapshot_sha256=snapshot_sha256,
                    )
                )
                files.append(
                    SourceFileRecord(
                        relative_path=relative_path,
                        source_kind=source_kind,
                        st_dev=source_before.st_dev,
                        st_ino=source_before.st_ino,
                        st_mode=source_before.st_mode,
                        st_size=source_before.st_size,
                        st_mtime_ns=source_before.st_mtime_ns,
                        st_ctime_ns=source_before.st_ctime_ns,
                        sha256=source_sha256,
                        byte_count=len(source_bytes),
                    )
                )
            manifest_payload: dict[str, object] = {
                "schema_version": "source-snapshot/v2",
                "source_root_dev": root_stat.st_dev,
                "source_root_ino": root_stat.st_ino,
                "source_commit": source_commit,
                "source_tree": source_tree,
                "records": tuple(
                    _source_snapshot_record_payload(record) for record in records
                ),
            }
            manifest_fingerprint = _canonical_fingerprint(
                manifest_payload,
                "manifest_fingerprint",
            )
            manifest = SourceSnapshotManifest(
                schema_version="source-snapshot/v2",
                source_root_dev=root_stat.st_dev,
                source_root_ino=root_stat.st_ino,
                source_commit=source_commit,
                source_tree=source_tree,
                records=tuple(records),
                manifest_fingerprint=manifest_fingerprint,
            )
            self._write_manifest(
                result_dir_fd,
                manifest,
            )
            os.fsync(snapshot_dir_fd)
            os.fsync(result_dir_fd)
            receipt_payload: dict[str, object] = {
                "schema_version": "source-freeze/v2",
                "runtime_route": request.runtime_route,
                "source_root_path": source_root,
                "source_root_dev": root_stat.st_dev,
                "source_root_ino": root_stat.st_ino,
                "source_commit": source_commit,
                "source_tree": source_tree,
                "files": tuple(
                    _source_file_record_payload(record) for record in files
                ),
                "source_paths": source_paths,
                "snapshot_root_relative_path": "source_snapshot",
                "snapshot_relative_path": "source_snapshot.json",
                "snapshot_manifest_fingerprint": manifest_fingerprint,
            }
            receipt_fingerprint = _canonical_fingerprint(
                receipt_payload,
                "receipt_fingerprint",
            )
            receipt = SourceFreezeReceipt(
                schema_version="source-freeze/v2",
                runtime_route=request.runtime_route,
                source_root_path=source_root,
                source_root_dev=root_stat.st_dev,
                source_root_ino=root_stat.st_ino,
                source_commit=source_commit,
                source_tree=source_tree,
                files=tuple(files),
                source_paths=source_paths,
                snapshot_root_relative_path="source_snapshot",
                snapshot_relative_path="source_snapshot.json",
                snapshot_manifest_fingerprint=manifest_fingerprint,
                receipt_fingerprint=receipt_fingerprint,
            )
            self._frozen = True
            return receipt
        except BaseException as primary:
            close_failure = self._close_owned_fds_without_revalidation()
            if close_failure is not None:
                raise primary from close_failure
            raise
        finally:
            if identity_fd >= 0:
                os.close(identity_fd)

    def revalidate(self) -> None:
        """Re-check the opened source-root identity without reopening source files."""
        if self._closed:
            raise TypedPreflightFailure(
                "gpu_source_freeze_closed",
                "a closed source-freeze owner cannot be revalidated",
            )
        if self._source_root_fd is None or self._source_root_stat is None:
            raise TypedPreflightFailure(
                "gpu_source_freeze_not_started",
                "source root is not retained for revalidation",
            )
        current_fd = -1
        try:
            current_fd = _open_source_root(cast(AbsolutePosixPath, self._source_root_path))
            current = os.fstat(current_fd)
            if (current.st_dev, current.st_ino) != self._source_root_stat:
                raise TypedPreflightFailure(
                    "gpu_source_freeze_raced",
                    "source-root identity changed before release",
                )
        except OSError as exc:
            raise TypedPreflightFailure(
                "gpu_source_freeze_raced",
                "source root could not be revalidated",
                errno=exc.errno,
            ) from exc
        finally:
            if current_fd >= 0:
                os.close(current_fd)

    def close(self) -> None:
        """Close retained source and snapshot fds once, in reverse order."""
        if self._closed:
            raise TypedPreflightFailure(
                "gpu_descriptor_double_close",
                "source-freeze descriptors were closed more than once",
            )
        race: TypedPreflightFailure | None = None
        try:
            self.revalidate()
        except TypedPreflightFailure as exc:
            race = exc
        close_failure = self._close_owned_fds_without_revalidation()
        if race is not None:
            if close_failure is not None:
                raise race from close_failure
            raise race
        if close_failure is not None:
            raise close_failure

    def _register_fd(self, descriptor: int) -> int:
        self._owned_fds.append(descriptor)
        return descriptor

    def _close_transient_fds(self, descriptors: Sequence[int]) -> None:
        for descriptor in reversed(tuple(descriptors)):
            try:
                self._owned_fds.remove(descriptor)
                os.close(descriptor)
            except OSError as exc:
                raise TypedPreflightFailure(
                    "gpu_descriptor_close_ambiguous",
                    "a transient source-freeze descriptor failed to close",
                    errno=exc.errno,
                ) from exc

    def _close_owned_fds_without_revalidation(
        self,
    ) -> TypedPreflightFailure | None:
        """Attempt every owned fd once and return typed ambiguity evidence."""
        self._closed = True
        dispositions: list[Mapping[str, object]] = []
        close_errors: list[OSError] = []
        for descriptor in reversed(self._owned_fds):
            try:
                os.close(descriptor)
            except OSError as exc:
                close_errors.append(exc)
                dispositions.append(
                    {
                        "fd": descriptor,
                        "disposition": "close_ambiguous",
                        "attempted_once": True,
                        "errno": exc.errno,
                    }
                )
            else:
                dispositions.append(
                    {
                        "fd": descriptor,
                        "disposition": "closed",
                        "attempted_once": True,
                    }
                )
        self._owned_fds.clear()
        if not close_errors:
            return None
        return TypedPreflightFailure(
            "gpu_descriptor_close_ambiguous",
            "one or more source-freeze descriptors failed to close",
            attempted_once=True,
            release_order="reverse_registration",
            release_dispositions=tuple(dispositions),
            errno=close_errors[0].errno,
        )

    def _open_source_file(self, root_fd: int, relative_path: RelativePosixPath) -> int:
        components = relative_path.split("/")
        parent_fds: list[int] = []
        parent_fd = root_fd
        try:
            for component in components[:-1]:
                parent_fd = self._register_fd(
                    os.open(
                        component,
                        os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                        dir_fd=parent_fd,
                    )
                )
                parent_fds.append(parent_fd)
            return self._register_fd(
                os.open(
                    components[-1],
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=parent_fd,
                )
            )
        finally:
            self._close_transient_fds(parent_fds)

    def _open_destination_chain(self, absolute_path: AbsolutePosixPath) -> int:
        current_fd = self._register_fd(
            os.open(
                "/",
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        )
        for component in absolute_path.split("/")[1:]:
            if not component:
                continue
            try:
                os.mkdir(component, 0o2770, dir_fd=current_fd)
            except FileExistsError:
                pass
            current_fd = self._register_fd(
                os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=current_fd,
                )
            )
        return current_fd

    def _open_or_create_directory(self, parent_fd: int, name: str) -> int:
        try:
            os.mkdir(name, 0o2770, dir_fd=parent_fd)
        except FileExistsError:
            pass
        return self._register_fd(
            os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        )

    def _copy_to_snapshot(
        self,
        snapshot_root_fd: int,
        relative_path: RelativePosixPath,
        source_bytes: bytes,
    ) -> tuple[int, os.stat_result]:
        components = relative_path.split("/")
        parent_fd = snapshot_root_fd
        parent_fds: list[int] = []
        try:
            for component in components[:-1]:
                parent_fd = self._open_or_create_directory(parent_fd, component)
                parent_fds.append(parent_fd)
            try:
                temporary_fd = self._register_fd(
                    os.open(
                        ".",
                        os.O_WRONLY | os.O_TMPFILE | os.O_CLOEXEC,
                        0o660,
                        dir_fd=parent_fd,
                    )
                )
            except OSError as exc:
                if exc.errno in {errno.EINVAL, errno.EOPNOTSUPP, errno.ENOTSUP}:
                    raise TypedPreflightFailure(
                        "gpu_source_snapshot_unsupported",
                        "the snapshot filesystem lacks O_TMPFILE support",
                        errno=exc.errno,
                    ) from exc
                raise TypedPreflightFailure(
                    "gpu_source_snapshot_open_failed",
                    "the snapshot temporary file could not be opened",
                    errno=exc.errno,
                ) from exc
            _write_all(temporary_fd, source_bytes)
            os.fsync(temporary_fd)
            _link_tmpfile(temporary_fd, parent_fd, components[-1].encode("utf-8"))
            os.fsync(parent_fd)
            snapshot_fd = os.open(
                components[-1],
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            snapshot_stat = os.fstat(snapshot_fd)
            if not stat.S_ISREG(snapshot_stat.st_mode):
                os.close(snapshot_fd)
                raise TypedPreflightFailure(
                    "gpu_source_snapshot_invalid",
                    "the linked snapshot is not a regular file",
                    relative_path=relative_path,
                )
            return snapshot_fd, snapshot_stat
        finally:
            self._close_transient_fds(parent_fds)

    def _write_manifest(
        self,
        result_dir_fd: int,
        manifest: SourceSnapshotManifest,
    ) -> None:
        payload = {
            "schema_version": manifest.schema_version,
            "source_root_dev": manifest.source_root_dev,
            "source_root_ino": manifest.source_root_ino,
            "source_commit": manifest.source_commit,
            "source_tree": manifest.source_tree,
            "records": tuple(
                _source_snapshot_record_payload(record)
                for record in manifest.records
            ),
            "manifest_fingerprint": manifest.manifest_fingerprint,
        }
        try:
            temporary_fd = self._register_fd(
                os.open(
                    ".",
                    os.O_WRONLY | os.O_TMPFILE | os.O_CLOEXEC,
                    0o660,
                    dir_fd=result_dir_fd,
                )
            )
        except OSError as exc:
            if exc.errno in {errno.EINVAL, errno.EOPNOTSUPP, errno.ENOTSUP}:
                raise TypedPreflightFailure(
                    "gpu_source_snapshot_unsupported",
                    "the manifest filesystem lacks O_TMPFILE support",
                    errno=exc.errno,
                ) from exc
            raise TypedPreflightFailure(
                "gpu_source_snapshot_open_failed",
                "the manifest temporary file could not be opened",
                errno=exc.errno,
            ) from exc
        _write_all(
            temporary_fd,
            (_canonical_json(_json_safe(payload)) + "\n").encode("utf-8"),
        )
        os.fsync(temporary_fd)
        _link_tmpfile(temporary_fd, result_dir_fd, b"source_snapshot.json")
        os.fsync(result_dir_fd)


def freeze_source_tree(request: GpuRunRequest) -> SourceFreezeReceipt:
    """Execute one standalone source freeze through the canonical owner."""
    snapshot_root = os.environ.get("AGENT_CANON_SOURCE_SNAPSHOT_ROOT")
    if snapshot_root is None:
        raise TypedPreflightFailure(
            "gpu_source_snapshot_root_missing",
            "AGENT_CANON_SOURCE_SNAPSHOT_ROOT is required for source freeze",
        )
    owner = SourceFreezeOwner(validate_absolute_posix_path(snapshot_root))
    try:
        receipt = owner.freeze(request)
        owner.close()
        return receipt
    except BaseException as primary:
        if not owner._closed:
            close_failure = owner._close_owned_fds_without_revalidation()
            if close_failure is not None:
                raise primary from close_failure
        raise


def _open_source_root(source_root: AbsolutePosixPath) -> int:
    try:
        return os.open(
            source_root,
            os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
    except OSError as exc:
        raise TypedPreflightFailure(
            "gpu_source_freeze_root_open_failed",
            "source root could not be opened with fd-bound no-follow flags",
            source_root=source_root,
            errno=exc.errno,
        ) from exc


def _normalize_source_paths(
    source_paths: Sequence[RelativePosixPath],
) -> tuple[RelativePosixPath, ...]:
    normalized: list[RelativePosixPath] = []
    seen: set[str] = set()
    for raw in source_paths:
        if (
            not isinstance(raw, str)
            or not raw
            or raw.startswith("/")
            or "\x00" in raw
            or any(component in {"", ".", ".."} for component in raw.split("/"))
        ):
            raise TypedPreflightFailure(
                "gpu_source_freeze_path_invalid",
                "source paths must be relative, normalized POSIX paths",
                source_path=raw,
            )
        if raw in seen:
            raise TypedPreflightFailure(
                "gpu_source_freeze_path_duplicate",
                "source paths must be unique",
                source_path=raw,
            )
        seen.add(raw)
        normalized.append(raw)
    return tuple(sorted(normalized, key=lambda value: value.encode("utf-8")))


def _read_git_identity(identity_fd: int) -> tuple[str, str]:
    commit = _run_git_identity_command(identity_fd, "HEAD")
    tree = _run_git_identity_command(identity_fd, "HEAD^{tree}")
    if len(commit) != 40 or len(tree) != 40:
        raise TypedPreflightFailure(
            "gpu_source_freeze_git_identity_invalid",
            "Git source identity must contain exact commit and tree hashes",
        )
    return commit, tree


def _run_git_identity_command(identity_fd: int, revision: str) -> str:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                f"/proc/self/fd/{identity_fd}",
                "rev-parse",
                "--verify",
                revision,
            ],
            check=False,
            capture_output=True,
            close_fds=True,
            pass_fds=(identity_fd,),
            text=True,
            encoding="utf-8",
        )
    except (OSError, UnicodeError) as exc:
        raise TypedPreflightFailure(
            "gpu_source_freeze_git_identity_failed",
            "Git identity could not be read through the retained root identity fd",
        ) from exc
    if result.returncode != 0:
        raise TypedPreflightFailure(
            "gpu_source_freeze_git_identity_failed",
            "Git identity command failed",
            stderr=result.stderr.strip(),
        )
    return result.stdout.strip()


def _git_source_kind(identity_fd: int, relative_path: RelativePosixPath) -> Literal[
    "tracked", "dirty", "untracked"
]:
    tracked = _run_git_path_command(
        identity_fd,
        ("ls-files", "--error-unmatch", "--", relative_path),
    )
    if tracked:
        status = _run_git_path_command(
            identity_fd,
            ("status", "--porcelain=v1", "--untracked-files=all", "--", relative_path),
        )
        return "dirty" if status else "tracked"
    untracked = _run_git_path_command(
        identity_fd,
        ("ls-files", "--others", "--exclude-standard", "--", relative_path),
    )
    if untracked:
        return "untracked"
    raise TypedPreflightFailure(
        "gpu_source_freeze_unlisted_path",
        "source path is neither tracked nor non-ignored untracked content",
        relative_path=relative_path,
    )


def _run_git_path_command(
    identity_fd: int,
    arguments: Sequence[str],
) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", f"/proc/self/fd/{identity_fd}", *arguments],
            check=False,
            capture_output=True,
            close_fds=True,
            pass_fds=(identity_fd,),
            text=True,
            encoding="utf-8",
        )
    except (OSError, UnicodeError) as exc:
        raise TypedPreflightFailure(
            "gpu_source_freeze_git_membership_failed",
            "Git source membership could not be read through the identity fd",
        ) from exc
    if result.returncode not in {0, 1}:
        raise TypedPreflightFailure(
            "gpu_source_freeze_git_membership_failed",
            "Git source membership command failed",
            stderr=result.stderr.strip(),
        )
    return result.stdout.strip()


def _pread_hash_all(descriptor: int) -> tuple[bytes, Sha256Hex]:
    chunks: list[bytes] = []
    digest = hashlib.sha256()
    offset = 0
    while True:
        try:
            chunk = os.pread(descriptor, 1024 * 1024, offset)
        except OSError as exc:
            raise TypedPreflightFailure(
                "gpu_source_freeze_read_failed",
                "source bytes could not be read through the retained fd",
                errno=exc.errno,
            ) from exc
        if not chunk:
            break
        chunks.append(chunk)
        digest.update(chunk)
        offset += len(chunk)
    return b"".join(chunks), digest.hexdigest()


def _source_stat_changed(
    before: os.stat_result,
    after: os.stat_result,
    byte_count: int,
) -> bool:
    return (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mode != after.st_mode
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or byte_count != before.st_size
    )


def _source_snapshot_record_payload(
    record: SourceSnapshotRecord,
) -> Mapping[str, object]:
    return {
        "relative_path": record.relative_path,
        "source_dev": record.source_dev,
        "source_ino": record.source_ino,
        "source_byte_count": record.source_byte_count,
        "source_sha256": record.source_sha256,
        "snapshot_relative_path": record.snapshot_relative_path,
        "snapshot_dev": record.snapshot_dev,
        "snapshot_ino": record.snapshot_ino,
        "snapshot_byte_count": record.snapshot_byte_count,
        "snapshot_sha256": record.snapshot_sha256,
    }


def _source_file_record_payload(
    record: SourceFileRecord,
) -> Mapping[str, object]:
    return {
        "relative_path": record.relative_path,
        "source_kind": record.source_kind,
        "st_dev": record.st_dev,
        "st_ino": record.st_ino,
        "st_mode": record.st_mode,
        "st_size": record.st_size,
        "st_mtime_ns": record.st_mtime_ns,
        "st_ctime_ns": record.st_ctime_ns,
        "sha256": record.sha256,
        "byte_count": record.byte_count,
    }


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


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


def _write_json_once(
    path: Path,
    payload: Mapping[str, object],
    *,
    allow_identical: bool = True,
) -> Mapping[str, object]:
    """Durably create one immutable JSON evidence record without replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (_canonical_json(_json_safe(payload)) + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = path.read_bytes()
        if not allow_identical or existing != encoded:
            raise ResourcePlanError(f"immutable evidence collision: {path}")
        return MappingProxyType(
            {
                "path": str(path),
                "sha256": hashlib.sha256(existing).hexdigest(),
                "bytes": len(existing),
                "disposition": "existing_identical",
            }
        )
    try:
        written = 0
        while written < len(encoded):
            written += os.write(descriptor, encoded[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return MappingProxyType(
        {
            "path": str(path),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "bytes": len(encoded),
            "disposition": "created",
        }
    )


@dataclass(frozen=True)
class ProcessIdentity:
    """GPU process identity including PID and process-start identity."""

    pid: int
    process_start_identity: str
    gpu_uuid: str
    kind: str = "compute"
    parent_pid: int | None = None
    relationship: str = "unknown"
    observation_timestamp: str = ""
    observation_fingerprint: str = ""
    container_namespace_identity: str = ""

    def __post_init__(self) -> None:
        if (
            self.pid <= 0
            or not self.process_start_identity
            or not self.gpu_uuid
            or not self.relationship
            or (self.parent_pid is not None and self.parent_pid <= 0)
        ):
            raise ValueError("process identity requires PID, process-start identity, and GPU UUID")


@dataclass(frozen=True)
class GPUDevice:
    uuid: str
    free_memory_bytes: int
    memory_bytes: int = 0
    mig_parent_uuid: str | None = None


@dataclass(frozen=True)
class ResourceObservation:
    """One coherent A/O/device/memory/boot observation from a resource probe."""

    caller_allocated_ids: frozenset[str]
    process_identities: tuple[ProcessIdentity, ...]
    gpu_devices: tuple[GPUDevice, ...]
    free_memory_bytes: Mapping[str, int]
    boot_id: str
    container_visible_ids: frozenset[str]
    observed_at: str
    fingerprint: str = ""
    observation_event_id: str = ""
    cpu_available_set: tuple[int, ...] = ()
    host_memory_bytes: int = 0
    temp_bytes: int = 0
    structure_tool: Mapping[str, str] = field(default_factory=dict)
    tool_availability: Mapping[str, object] = field(default_factory=dict)
    container_id: str = ""
    nvidia_inventory: "NvidiaInventory | None" = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "caller_allocated_ids", frozenset(self.caller_allocated_ids))
        object.__setattr__(self, "process_identities", tuple(self.process_identities))
        object.__setattr__(self, "gpu_devices", tuple(sorted(self.gpu_devices, key=lambda device: device.uuid)))
        object.__setattr__(self, "free_memory_bytes", _freeze_mapping(self.free_memory_bytes))
        object.__setattr__(self, "container_visible_ids", frozenset(self.container_visible_ids))
        object.__setattr__(self, "cpu_available_set", tuple(sorted(self.cpu_available_set)))
        object.__setattr__(self, "structure_tool", _freeze_mapping(self.structure_tool))
        object.__setattr__(self, "tool_availability", _freeze_mapping(self.tool_availability))
        if not self.observation_event_id:
            object.__setattr__(
                self,
                "observation_event_id",
                f"observation-{secrets.token_hex(12)}",
            )
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                hashlib.sha256(
                    _canonical_json(
                        {
                            "caller_allocated_ids": tuple(sorted(self.caller_allocated_ids)),
                            "process_identities": tuple(
                                _process_record(process) for process in self.process_identities
                            ),
                            "gpu_devices": tuple(
                                {
                                    "uuid": device.uuid,
                                    "free_memory_bytes": device.free_memory_bytes,
                                    "memory_bytes": device.memory_bytes,
                                    "mig_parent_uuid": device.mig_parent_uuid,
                                }
                                for device in self.gpu_devices
                            ),
                            "free_memory_bytes": dict(self.free_memory_bytes),
                            "boot_id": self.boot_id,
                            "container_visible_ids": tuple(sorted(self.container_visible_ids)),
                            "observed_at": self.observed_at,
                            "observation_event_id": self.observation_event_id,
                        }
                    ).encode("utf-8")
                ).hexdigest(),
            )


class ResourceProbe(Protocol):
    """Read-only coherent observations used for atomic planner rereads."""

    def observe(self) -> ResourceObservation: ...


def _xml_text(element: ET.Element | None, field_name: str) -> str:
    value = element.text.strip() if element is not None and element.text else ""
    if not value:
        raise TypedPreflightFailure(
            "gpu_structured_observation_incomplete",
            "nvidia-smi XML omitted a required field",
            field=field_name,
        )
    return value


def _xml_memory_bytes(element: ET.Element | None, field_name: str) -> int:
    raw = _xml_text(element, field_name)
    parts = raw.split()
    if len(parts) != 2:
        raise TypedPreflightFailure(
            "gpu_structured_observation_malformed",
            "nvidia-smi XML memory field is not a value/unit pair",
            field=field_name,
            value=raw,
        )
    try:
        value = float(parts[0])
    except ValueError as exc:
        raise TypedPreflightFailure(
            "gpu_structured_observation_malformed",
            "nvidia-smi XML memory value is not numeric",
            field=field_name,
            value=raw,
        ) from exc
    multipliers = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    if parts[1] not in multipliers:
        raise TypedPreflightFailure(
            "gpu_structured_observation_malformed",
            "nvidia-smi XML memory unit is unsupported",
            field=field_name,
            unit=parts[1],
        )
    return int(value * multipliers[parts[1]])


def _scheduler_uuid_set(environment: Mapping[str, str]) -> frozenset[str]:
    observed: dict[str, tuple[str, ...]] = {}
    for key in ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"):
        raw = environment.get(key)
        if raw is None:
            continue
        tokens = tuple(token.strip() for token in raw.split(",") if token.strip())
        if not tokens or any(
            token.lower() in {"all", "none", "void"} or _is_gpu_index(token)
            for token in tokens
        ):
            raise TypedPreflightFailure(
                "gpu_scheduler_uuid_visibility_unproven",
                "GPU scheduler visibility must be a non-empty UUID/MIG UUID set",
                environment_key=key,
                observed_value=raw,
            )
        observed[key] = tokens
    if not observed:
        raise TypedPreflightFailure(
            "gpu_scheduler_uuid_visibility_unproven",
            "GPU request has no caller/scheduler UUID visibility",
        )
    values = tuple(observed.values())
    if len(values) == 2 and values[0] != values[1]:
        raise TypedPreflightFailure(
            "gpu_scheduler_uuid_visibility_conflict",
            "CUDA and NVIDIA scheduler UUID sets disagree",
            observed=observed,
        )
    return frozenset(values[0])


def _proc_start_and_parent(pid: int) -> tuple[str, int | None]:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise TypedPreflightFailure(
            "gpu_process_identity_unproven",
            "GPU process PID is not visible in the current process namespace",
            pid=pid,
        ) from exc
    fields = stat.rsplit(")", 1)[-1].split()
    if len(fields) <= 19:
        raise TypedPreflightFailure(
            "gpu_process_identity_unproven",
            "GPU process start identity is not available",
            pid=pid,
        )
    try:
        parent_pid = int(fields[1])
    except ValueError as exc:
        raise TypedPreflightFailure(
            "gpu_process_identity_unproven",
            "GPU process parent PID is not available",
            pid=pid,
        ) from exc
    start_identity = fields[19]
    if not start_identity or start_identity in {"unknown", "dead"}:
        raise TypedPreflightFailure(
            "gpu_process_identity_unproven",
            "GPU process start identity is not authoritative",
            pid=pid,
            process_start_identity=start_identity,
        )
    return start_identity, parent_pid


def _process_relationship(pid: int, parent_pid: int | None) -> str:
    current_pid = os.getpid()
    if pid == current_pid:
        return "planner_process"
    if parent_pid == current_pid:
        return "child"
    cursor = parent_pid
    for _ in range(64):
        if cursor in (None, 0, 1):
            break
        if cursor == current_pid:
            return "descendant"
        _start, cursor = _proc_start_and_parent(cursor)
    return "external"


def _xml_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {
        child: parent
        for parent in root.iter()
        for child in list(parent)
    }


def _nearest_xml_ancestor(
    element: ET.Element,
    parent_map: Mapping[ET.Element, ET.Element],
    tags: frozenset[str],
) -> ET.Element | None:
    cursor: ET.Element | None = element
    while cursor is not None:
        if cursor.tag.rsplit("}", 1)[-1] in tags:
            return cursor
        cursor = parent_map.get(cursor)
    return None


def _structured_unit_uuid(
    element: ET.Element,
    parent_map: Mapping[ET.Element, ET.Element],
) -> str:
    explicit_uuid = element.find("uuid")
    if explicit_uuid is not None and explicit_uuid.text:
        return explicit_uuid.text.strip()
    physical = _nearest_xml_ancestor(element, parent_map, frozenset({"gpu"}))
    if physical is None:
        return ""
    parent_uuid = physical.find("uuid")
    if parent_uuid is None or not parent_uuid.text:
        return ""
    identifiers: list[str] = []
    for ancestor in (element, parent_map.get(element), parent_map.get(parent_map.get(element))):
        if ancestor is None:
            continue
        for tag in ("gpu_instance_id", "compute_instance_id"):
            value = ancestor.find(tag)
            if value is not None and value.text:
                identifiers.append(value.text.strip())
    if not identifiers:
        return parent_uuid.text.strip()
    return "MIG-" + parent_uuid.text.strip() + "/" + "/".join(identifiers)


_PROCESS_INVENTORY_TAGS = frozenset(
    {"processes", "compute_processes", "graphics_processes"}
)


def _xml_local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _process_inventory_containers(element: ET.Element) -> tuple[ET.Element, ...]:
    return tuple(
        candidate
        for candidate in element.iter()
        if _xml_local_name(candidate) in _PROCESS_INVENTORY_TAGS
    )


def _prove_allocated_process_inventory_visibility(
    root: ET.Element,
    allocated_ids: frozenset[str],
    parent_map: Mapping[ET.Element, ET.Element],
) -> Mapping[str, object]:
    """Prove a structured process table covers every allocated physical/MIG unit."""
    element_by_uuid: dict[str, ET.Element] = {}
    for gpu in root.findall(".//gpu"):
        uuid_element = gpu.find("uuid")
        if uuid_element is None or not uuid_element.text:
            continue
        uuid = uuid_element.text.strip()
        element_by_uuid[uuid] = gpu
    for element in root.iter():
        if _xml_local_name(element) not in {
            "mig_device",
            "gpu_instance",
            "compute_instance",
        }:
            continue
        uuid = _structured_unit_uuid(element, parent_map)
        if uuid:
            element_by_uuid[uuid] = element

    unit_witnesses: dict[str, object] = {}
    hidden_markers = (
        "insufficient permission",
        "permission denied",
        "not supported",
        "unknown error",
    )
    for uuid in sorted(allocated_ids):
        unit = element_by_uuid.get(uuid)
        if unit is None:
            raise TypedPreflightFailure(
                "gpu_process_identity_unproven",
                "allocated GPU/MIG UUID has no structured process-inventory scope",
                gpu_uuid=uuid,
            )
        containers = _process_inventory_containers(unit)
        coverage_source = "allocated_unit_process_table"
        if not containers:
            physical = _nearest_xml_ancestor(unit, parent_map, frozenset({"gpu"}))
            if physical is not None:
                containers = _process_inventory_containers(physical)
                coverage_source = "physical_parent_process_table"
        if not containers:
            raise TypedPreflightFailure(
                "gpu_process_identity_unproven",
                "structured GPU XML omitted the process inventory for an allocated unit",
                gpu_uuid=uuid,
            )
        inventory_text = " ".join(
            text.strip().lower()
            for container in containers
            for text in container.itertext()
            if text.strip()
        )
        hidden_marker = next(
            (marker for marker in hidden_markers if marker in inventory_text),
            None,
        )
        if hidden_marker is not None:
            raise TypedPreflightFailure(
                "gpu_process_identity_unproven",
                "structured GPU process inventory is unsupported or permission-hidden",
                gpu_uuid=uuid,
                visibility_failure=hidden_marker,
            )
        process_count = sum(
            1
            for container in containers
            for candidate in container.iter()
            if _xml_local_name(candidate) == "process_info"
        )
        unit_witnesses[uuid] = {
            "visible": True,
            "coverage_source": coverage_source,
            "container_tags": tuple(
                sorted({_xml_local_name(container) for container in containers})
            ),
            "process_count": process_count,
            "explicit_empty": process_count == 0,
        }
    return MappingProxyType(
        {
            "schema_version": "gpu-process-inventory-visibility/v1",
            "allocated_ids": tuple(sorted(allocated_ids)),
            "all_allocated_units_visible": True,
            "units": MappingProxyType(unit_witnesses),
        }
    )


def _parse_structured_gpu_processes(
    root: ET.Element,
    device_by_uuid: Mapping[str, GPUDevice],
    parent_map: Mapping[ET.Element, ET.Element],
) -> tuple[ProcessIdentity, ...]:
    processes: list[ProcessIdentity] = []
    for process_info in root.findall(".//process_info"):
        pid_text = _xml_text(process_info.find("pid"), "process_info.pid")
        try:
            pid = int(pid_text)
        except ValueError as exc:
            raise TypedPreflightFailure(
                "gpu_process_identity_unproven",
                "nvidia-smi XML process PID is not numeric",
                pid=pid_text,
            ) from exc
        if pid <= 0:
            raise TypedPreflightFailure(
                "gpu_process_identity_unproven",
                "nvidia-smi XML process PID is not positive",
                pid=pid,
            )
        ancestor: ET.Element | None = process_info
        bound_uuid = _structured_unit_uuid(process_info, parent_map)
        raw_process_kind = process_info.findtext("type", default="").strip().upper()
        process_kind_tokens = frozenset(
            token.strip() for token in raw_process_kind.split("+") if token.strip()
        )
        if not process_kind_tokens or not process_kind_tokens.issubset(
            {"C", "G", "M", "O"}
        ):
            raise TypedPreflightFailure(
                "gpu_process_kind_visibility_unproven",
                "GPU process context is not classified by the structured inventory",
                pid=pid,
                observed_type=raw_process_kind,
            )
        if {"G", "C"}.issubset(process_kind_tokens):
            process_kind = "compute_graphics"
        elif "G" in process_kind_tokens:
            process_kind = "graphics"
        elif "M" in process_kind_tokens:
            process_kind = "mps_compute"
        elif "O" in process_kind_tokens:
            process_kind = "other_gpu_context"
        else:
            process_kind = "compute"
        graphics_ancestor = False
        while ancestor is not None:
            tag = ancestor.tag.rsplit("}", 1)[-1]
            if tag == "graphics_processes":
                process_kind = "graphics"
                graphics_ancestor = True
            if bound_uuid in device_by_uuid:
                break
            if tag in {"compute_instance", "gpu_instance", "mig_device", "gpu"}:
                bound_uuid = _structured_unit_uuid(ancestor, parent_map)
                if bound_uuid in device_by_uuid:
                    break
            ancestor = parent_map.get(ancestor)
        if graphics_ancestor:
            process_kind = "graphics"
        if not bound_uuid or bound_uuid not in device_by_uuid:
            raise TypedPreflightFailure(
                "gpu_process_uuid_visibility_unproven",
                "GPU process context cannot be bound to an observed GPU/MIG UUID",
                pid=pid,
                observed_uuid=bound_uuid,
                process_kind=process_kind,
            )
        start_identity, parent_pid = _proc_start_and_parent(pid)
        try:
            container_namespace_identity = str(Path(f"/proc/{pid}/ns/pid").readlink())
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise TypedPreflightFailure(
                "gpu_process_identity_unproven",
                "GPU process PID/container namespace mapping is unavailable",
                pid=pid,
            ) from exc
        if not container_namespace_identity:
            raise TypedPreflightFailure(
                "gpu_process_identity_unproven",
                "GPU process container namespace identity is empty",
                pid=pid,
            )
        relationship = _process_relationship(pid, parent_pid)
        processes.append(
            ProcessIdentity(
                pid=pid,
                process_start_identity=start_identity,
                gpu_uuid=bound_uuid,
                kind=process_kind,
                parent_pid=parent_pid,
                relationship=relationship,
                container_namespace_identity=container_namespace_identity,
            )
        )
    return tuple(
        sorted(
            processes,
            key=lambda process: (
                process.gpu_uuid,
                process.kind,
                process.pid,
                process.process_start_identity,
            ),
        )
    )


@dataclass(frozen=True)
class EvidenceFd:
    """Retained fd identity used by one strict NVIDIA evidence parser."""

    fd: int
    source_name: str
    st_dev: int
    st_ino: int
    byte_count: int
    sha256: Sha256Hex


_CLOSED_EVIDENCE_FDS: set[int] = set()
_EVIDENCE_FD_CLOSE_LOCK = threading.Lock()


def _capture_evidence_fd(
    command: Sequence[str],
    source_name: str,
) -> EvidenceFd:
    """Capture one parser producer into a retained, hashed evidence fd."""
    if not command or not source_name or any(
        not isinstance(item, str) or not item for item in command
    ):
        raise TypedPreflightFailure(
            "gpu_evidence_command_invalid",
            "structured evidence capture requires a non-empty string command",
        )
    memfd_create = getattr(os, "memfd_create", None)
    if not callable(memfd_create):
        raise TypedPreflightFailure(
            "gpu_evidence_fd_unavailable",
            "structured evidence requires memfd_create support",
            source_name=source_name,
        )
    try:
        result = subprocess.run(
            tuple(command),
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TypedPreflightFailure(
            "gpu_evidence_capture_failed",
            "structured evidence producer could not be executed",
            source_name=source_name,
        ) from exc
    if result.returncode != 0:
        raise TypedPreflightFailure(
            "gpu_evidence_capture_failed",
            "structured evidence producer returned a failure",
            source_name=source_name,
            returncode=result.returncode,
        )
    payload = bytes(result.stdout)
    try:
        descriptor = int(memfd_create(f"agent-canon-{source_name}", os.MFD_CLOEXEC))
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        identity = os.fstat(descriptor)
    except OSError as exc:
        if "descriptor" in locals():
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise TypedPreflightFailure(
            "gpu_evidence_fd_unavailable",
            "structured evidence could not be retained in a memfd",
            source_name=source_name,
        ) from exc
    return EvidenceFd(
        fd=descriptor,
        source_name=source_name,
        st_dev=identity.st_dev,
        st_ino=identity.st_ino,
        byte_count=identity.st_size,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _close_evidence_fd(evidence: EvidenceFd) -> FdDisposition:
    """Close one parser input exactly once; never retry an ambiguous close."""
    with _EVIDENCE_FD_CLOSE_LOCK:
        if evidence.fd in _CLOSED_EVIDENCE_FDS:
            raise TypedPreflightFailure(
                "gpu_evidence_fd_closed_twice",
                "structured evidence fd close was attempted twice",
                fd=evidence.fd,
                source_name=evidence.source_name,
            )
        _CLOSED_EVIDENCE_FDS.add(evidence.fd)
    try:
        os.close(evidence.fd)
    except OSError as exc:
        raise TypedPreflightFailure(
            "gpu_evidence_fd_close_ambiguous",
            "structured evidence fd close was ambiguous",
            fd=evidence.fd,
            source_name=evidence.source_name,
            errno=exc.errno,
        ) from exc
    return "released"


def build_source_path_set(
    root: AbsolutePosixPath,
    topic_name: str,
    command_argv: Sequence[str],
) -> tuple[RelativePosixPath, ...]:
    """Build the deterministic, bounded source membership for one topic run."""
    source_root = Path(validate_absolute_posix_path(root))
    if not topic_name or "/" in topic_name or "\\" in topic_name:
        raise TypedPreflightFailure(
            "gpu_source_path_topic_invalid",
            "source path selection requires one simple topic name",
        )
    fixed_core = (
        "tools/experiments/execution_resource_plan.py",
        "tools/experiments/run_managed_experiment.py",
        "tools/experiments/registry_lib.py",
        "tools/agent_tools/jit_canonical_ir.py",
    )
    result: list[str] = []
    for relative_path in fixed_core:
        candidate = source_root / relative_path
        if not candidate.is_file():
            raise TypedPreflightFailure(
                "gpu_source_path_missing",
                "a fixed managed source path is missing",
                relative_path=relative_path,
            )
        result.append(relative_path)
    registry_path = source_root / "experiments/registry.toml"
    if not registry_path.is_file():
        raise TypedPreflightFailure(
            "gpu_source_path_registry_missing",
            "the canonical experiments/registry.toml source edge is missing",
            relative_path="experiments/registry.toml",
        )
    result.append("experiments/registry.toml")
    try:
        listed = subprocess.run(
            [
                "git",
                "-C",
                str(source_root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                f"experiments/{topic_name}/**",
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TypedPreflightFailure(
            "gpu_source_path_membership_failed",
            "git source membership could not be captured",
        ) from exc
    if listed.returncode != 0:
        raise TypedPreflightFailure(
            "gpu_source_path_membership_failed",
            "git source membership command failed",
            returncode=listed.returncode,
        )
    excluded_parts = {"result", ".venv", "__pycache__", ".cache", "runtime"}
    for raw_path in bytes(listed.stdout).split(b"\0"):
        if not raw_path:
            continue
        try:
            relative_path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TypedPreflightFailure(
                "gpu_source_path_membership_failed",
                "git source membership was not UTF-8",
            ) from exc
        if any(part in excluded_parts for part in Path(relative_path).parts):
            continue
        if (source_root / relative_path).is_symlink():
            raise TypedPreflightFailure(
                "gpu_source_path_symlink",
                "source membership cannot include a symlink",
                relative_path=relative_path,
            )
        result.append(relative_path)
    supported_extensions = {".py", ".pyi", ".toml", ".yaml", ".yml", ".json"}
    command_paths: list[str] = []
    for token in command_argv:
        if not isinstance(token, str) or token.startswith("-"):
            continue
        candidate = Path(token)
        if candidate.is_absolute():
            try:
                relative = candidate.relative_to(source_root)
            except ValueError:
                continue
        else:
            relative = candidate
        if any(part in {"", ".", ".."} for part in relative.parts):
            continue
        relative_text = relative.as_posix()
        if Path(relative_text).suffix not in supported_extensions:
            continue
        if (source_root / relative).is_file():
            command_paths.append(relative_text)
    result.extend(command_paths)
    ordered: list[str] = []
    seen: set[str] = set()
    for path in result:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return tuple(ordered)


@dataclass(frozen=True)
class NvidiaDriverVersion:
    """The only accepted NVIDIA driver-version representation."""

    major: int
    minor: int
    patch: int | None
    raw: str


@dataclass(frozen=True)
class NvidiaTopologyJoin:
    """One exact full-UUID physical-to-MIG topology join."""

    parent_uuid: FullGpuUuid
    ordinal: int
    mig_uuid: FullMigUuid


@dataclass(frozen=True)
class NvidiaListEvidence:
    """Strict, fd-backed physical and MIG records from ``nvidia-smi -L``."""

    schema_version: Literal["nvidia-list/v1"]
    physical_uuids: tuple[FullGpuUuid, ...]
    mig_uuids: tuple[FullMigUuid, ...]
    joins: tuple[NvidiaTopologyJoin, ...]
    evidence_fingerprint: Sha256Hex


@dataclass(frozen=True)
class ParsedNvidiaXml:
    """Strict XML topology plus process-container completeness witness.

    Process identity and occupancy are deliberately not represented here; the
    separate occupancy owner consumes the completeness witness in its slice.
    """

    schema_version: Literal["nvidia-xml/v1"]
    physical_uuids: tuple[FullGpuUuid, ...]
    mig_uuids: tuple[FullMigUuid, ...]
    joins: tuple[NvidiaTopologyJoin, ...]
    processing_instructions: tuple[str, ...]
    comments: tuple[str, ...]
    process_inventory_disposition: Literal["COMPLETE", "COMPLETE_EMPTY"]
    evidence_fingerprint: Sha256Hex


@dataclass(frozen=True)
class _ParsedNvidiaXmlDocument:
    """Canonical fd-bound XML parse plus its parser-owned element graph."""

    parsed: ParsedNvidiaXml
    root: ET.Element
    parent_map: Mapping[ET.Element, ET.Element]


@dataclass(frozen=True)
class NvidiaInventory:
    """Candidate topology produced only by the NVIDIA evidence owner."""

    schema_version: Literal["nvidia-inventory/v1"]
    physical_uuids: tuple[FullGpuUuid, ...]
    mig_uuids: tuple[FullMigUuid, ...]
    joins: tuple[NvidiaTopologyJoin, ...]
    driver_version: NvidiaDriverVersion | None
    evidence_fingerprint: Sha256Hex


@dataclass(frozen=True)
class NvidiaStructuredObservation:
    """One canonical fd-bound topology/process observation for admission."""

    inventory: NvidiaInventory
    devices: tuple[GPUDevice, ...]
    processes: tuple[ProcessIdentity, ...]
    process_inventory_visibility: Mapping[str, object]


_NVIDIA_DRIVER_VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.([0-9]+)(?:\.([0-9]+))?$"
)
_NVIDIA_PHYSICAL_LINE_RE = re.compile(
    r"^GPU ([0-9]+): ([^\n]+) \(UUID: (GPU-[A-Za-z0-9-]+)\)$"
)
_NVIDIA_MIG_LINE_RE = re.compile(
    r"^[ ]{2,}MIG ([0-9]+c\.)?[0-9]+g\.[0-9]+gb[ ]{2,}Device[ ]{2}([0-9]+): \(UUID: (MIG-[A-Za-z0-9-]+)\)$"
)
_NVIDIA_UUID_RE = re.compile(r"^(GPU|MIG)-[A-Za-z0-9-]+$")
_NVIDIA_UNSAFE_XML_RE = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_NVIDIA_PROCESS_CONTAINER_TAGS = frozenset(
    {"processes", "compute_processes", "graphics_processes"}
)
_NVIDIA_PROCESS_RECORD_TAGS = frozenset(
    {"process_info", "pid", "process_name", "used_memory", "type"}
)


def _nvidia_parser_failure(
    code: str,
    message: str,
    *,
    evidence: EvidenceFd | None = None,
    **details: object,
) -> TypedPreflightFailure:
    if evidence is not None:
        details.update({"source_name": evidence.source_name, "fd": evidence.fd})
    return TypedPreflightFailure(code, message, **details)


def _read_evidence_fd(evidence: EvidenceFd) -> bytes:
    """Load one retained evidence fd and revalidate it before returning bytes."""
    try:
        before = os.fstat(evidence.fd)
    except OSError as exc:
        raise _nvidia_parser_failure(
            "gpu_evidence_unreadable",
            "NVIDIA evidence fd could not be inspected",
            evidence=evidence,
            errno=exc.errno,
        ) from exc
    if not stat.S_ISREG(before.st_mode):
        raise _nvidia_parser_failure(
            "gpu_evidence_not_regular",
            "NVIDIA evidence fd must reference a regular file",
            evidence=evidence,
        )
    if (
        before.st_dev != evidence.st_dev
        or before.st_ino != evidence.st_ino
        or before.st_size != evidence.byte_count
    ):
        raise _nvidia_parser_failure(
            "gpu_evidence_raced",
            "NVIDIA evidence identity or length changed before parsing",
            evidence=evidence,
            before_dev=before.st_dev,
            before_ino=before.st_ino,
            before_size=before.st_size,
        )
    chunks: list[bytes] = []
    offset = 0
    while offset < before.st_size:
        try:
            chunk = os.pread(evidence.fd, min(1024 * 1024, before.st_size - offset), offset)
        except OSError as exc:
            raise _nvidia_parser_failure(
                "gpu_evidence_unreadable",
                "NVIDIA evidence fd could not be read",
                evidence=evidence,
                errno=exc.errno,
            ) from exc
        if not chunk:
            raise _nvidia_parser_failure(
                "gpu_evidence_raced",
                "NVIDIA evidence fd ended before its captured length",
                evidence=evidence,
                offset=offset,
            )
        chunks.append(chunk)
        offset += len(chunk)
    data = b"".join(chunks)
    try:
        after = os.fstat(evidence.fd)
    except OSError as exc:
        raise _nvidia_parser_failure(
            "gpu_evidence_unreadable",
            "NVIDIA evidence fd could not be revalidated",
            evidence=evidence,
            errno=exc.errno,
        ) from exc
    if (
        not stat.S_ISREG(after.st_mode)
        or after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_size != before.st_size
        or after.st_mode != before.st_mode
        or len(data) != after.st_size
        or hashlib.sha256(data).hexdigest() != evidence.sha256
    ):
        raise _nvidia_parser_failure(
            "gpu_evidence_raced",
            "NVIDIA evidence identity, mode, length, or hash changed during parsing",
            evidence=evidence,
            before_mode=before.st_mode,
            after_mode=after.st_mode,
            after_dev=after.st_dev,
            after_ino=after.st_ino,
            after_size=after.st_size,
        )
    return data


def _evidence_fingerprint(
    evidence: EvidenceFd,
    *,
    payload: Mapping[str, object],
) -> Sha256Hex:
    return hashlib.sha256(
        _canonical_json(
            {
                "source_name": evidence.source_name,
                "st_dev": evidence.st_dev,
                "st_ino": evidence.st_ino,
                "byte_count": evidence.byte_count,
                "sha256": evidence.sha256,
                "payload": payload,
            }
        ).encode("utf-8")
    ).hexdigest()


def _nvidia_join_payload(join: NvidiaTopologyJoin) -> Mapping[str, object]:
    return {
        "parent_uuid": join.parent_uuid,
        "ordinal": join.ordinal,
        "mig_uuid": join.mig_uuid,
    }


def _nvidia_driver_payload(driver: NvidiaDriverVersion | None) -> object:
    if driver is None:
        return None
    return {
        "major": driver.major,
        "minor": driver.minor,
        "patch": driver.patch,
        "raw": driver.raw,
    }


def _decode_nvidia_utf8(data: bytes, evidence: EvidenceFd) -> str:
    if data.startswith(b"\xef\xbb\xbf") or b"\x00" in data:
        raise _nvidia_parser_failure(
            "gpu_structured_probe_malformed",
            "NVIDIA evidence must be UTF-8 without BOM or NUL bytes",
            evidence=evidence,
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _nvidia_parser_failure(
            "gpu_structured_probe_malformed",
            "NVIDIA evidence is not strict UTF-8",
            evidence=evidence,
        ) from exc


def _parse_driver_version(evidence: EvidenceFd) -> NvidiaDriverVersion:
    raw = _decode_nvidia_utf8(_read_evidence_fd(evidence), evidence)
    if not raw.endswith("\n") or raw.count("\n") != 1:
        raise _nvidia_parser_failure(
            "gpu_driver_version_malformed",
            "driver version evidence must contain one LF-terminated value",
            evidence=evidence,
        )
    value = raw[:-1]
    match = _NVIDIA_DRIVER_VERSION_RE.fullmatch(value)
    if match is None:
        raise _nvidia_parser_failure(
            "gpu_driver_version_malformed",
            "driver version does not match the approved grammar",
            evidence=evidence,
            value=value,
        )
    patch = match.group(3)
    return NvidiaDriverVersion(
        major=int(match.group(1)),
        minor=int(match.group(2)),
        patch=int(patch) if patch is not None else None,
        raw=value,
    )


def _parse_nvidia_smi_list(evidence: EvidenceFd) -> NvidiaListEvidence:
    data = _read_evidence_fd(evidence)
    text = _decode_nvidia_utf8(data, evidence)
    if not text.endswith("\n") or "\r" in text or "\t" in text:
        raise _nvidia_parser_failure(
            "gpu_list_probe_malformed",
            "nvidia-smi -L evidence must be strict LF output",
            evidence=evidence,
        )
    lines = text.split("\n")
    if lines[-1] != "" or any(not line for line in lines[:-1]):
        raise _nvidia_parser_failure(
            "gpu_list_probe_malformed",
            "nvidia-smi -L evidence must have one final LF and no empty lines",
            evidence=evidence,
        )
    physical: list[FullGpuUuid] = []
    mig: list[FullMigUuid] = []
    joins: list[NvidiaTopologyJoin] = []
    seen_physical: set[str] = set()
    seen_mig: set[str] = set()
    seen_joins: set[tuple[str, int]] = set()
    current_parent: FullGpuUuid | None = None
    for line in lines[:-1]:
        if line.endswith(" "):
            raise _nvidia_parser_failure(
                "gpu_list_probe_malformed",
                "nvidia-smi -L evidence must not contain trailing spaces",
                evidence=evidence,
                line=line,
            )
        physical_match = _NVIDIA_PHYSICAL_LINE_RE.fullmatch(line)
        if physical_match is not None:
            uuid = physical_match.group(3)
            if uuid in seen_physical:
                raise _nvidia_parser_failure(
                    "gpu_uuid_duplicate",
                    "nvidia-smi -L evidence repeats a physical UUID",
                    evidence=evidence,
                    gpu_uuid=uuid,
                )
            seen_physical.add(uuid)
            physical.append(uuid)
            current_parent = uuid
            continue
        mig_match = _NVIDIA_MIG_LINE_RE.fullmatch(line)
        if mig_match is None:
            raise _nvidia_parser_failure(
                "gpu_list_probe_malformed",
                "nvidia-smi -L evidence contains an unmatched line",
                evidence=evidence,
                line=line,
            )
        if current_parent is None:
            raise _nvidia_parser_failure(
                "gpu_mig_parent_missing",
                "MIG list evidence has no immediately preceding physical parent",
                evidence=evidence,
                line=line,
            )
        ordinal = int(mig_match.group(2))
        mig_uuid = mig_match.group(3)
        join_key = (current_parent, ordinal)
        if mig_uuid in seen_mig:
            raise _nvidia_parser_failure(
                "gpu_uuid_duplicate",
                "nvidia-smi -L evidence repeats a MIG UUID",
                evidence=evidence,
                mig_uuid=mig_uuid,
            )
        if join_key in seen_joins:
            raise _nvidia_parser_failure(
                "gpu_mig_parent_ordinal_duplicate",
                "nvidia-smi -L evidence repeats a parent/ordinal join",
                evidence=evidence,
                parent_uuid=current_parent,
                ordinal=ordinal,
            )
        seen_mig.add(mig_uuid)
        seen_joins.add(join_key)
        mig.append(mig_uuid)
        joins.append(NvidiaTopologyJoin(current_parent, ordinal, mig_uuid))
    return NvidiaListEvidence(
        schema_version="nvidia-list/v1",
        physical_uuids=tuple(physical),
        mig_uuids=tuple(mig),
        joins=tuple(joins),
        evidence_fingerprint=_evidence_fingerprint(
            evidence,
            payload={
                "physical_uuids": tuple(physical),
                "mig_uuids": tuple(mig),
                "joins": tuple(_nvidia_join_payload(join) for join in joins),
            },
        ),
    )


def _xml_local_name_strict(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def _xml_required_child_text(element: ET.Element, tag: str, evidence: EvidenceFd) -> str:
    child = next(
        (candidate for candidate in list(element) if _xml_local_name_strict(candidate) == tag),
        None,
    )
    value = child.text.strip() if child is not None and child.text else ""
    if not value:
        raise _nvidia_parser_failure(
            "gpu_structured_probe_malformed",
            "NVIDIA XML omitted a required topology field",
            evidence=evidence,
            field=tag,
        )
    return value


_NvidiaXmlEventName: TypeAlias = Literal["start", "end", "comment", "pi"]
_NvidiaXmlEvent: TypeAlias = tuple[_NvidiaXmlEventName, ET.Element]
_NVIDIA_XML_EVENT_NAMES = frozenset({"start", "end", "comment", "pi"})


def _typed_nvidia_xml_events(
    parser: ET.XMLPullParser,
    evidence: EvidenceFd,
) -> tuple[_NvidiaXmlEvent, ...]:
    """Validate and narrow ElementTree's heterogeneous pull-event boundary."""
    events: list[_NvidiaXmlEvent] = []
    raw_events = cast(Sequence[object], tuple(parser.read_events()))
    for raw_event in raw_events:
        if not isinstance(raw_event, tuple) or len(raw_event) != 2:
            raise _nvidia_parser_failure(
                "gpu_structured_probe_malformed",
                "NVIDIA XML parser returned an invalid event record",
                evidence=evidence,
            )
        raw_name, raw_element = raw_event
        if (
            not isinstance(raw_name, str)
            or raw_name not in _NVIDIA_XML_EVENT_NAMES
            or not isinstance(raw_element, ET.Element)
        ):
            raise _nvidia_parser_failure(
                "gpu_structured_probe_malformed",
                "NVIDIA XML parser returned an unsupported event payload",
                evidence=evidence,
            )
        events.append((cast(_NvidiaXmlEventName, raw_name), raw_element))
    return tuple(events)


def _parse_nvidia_smi_xml_document(evidence: EvidenceFd) -> _ParsedNvidiaXmlDocument:
    data = _read_evidence_fd(evidence)
    if _NVIDIA_UNSAFE_XML_RE.search(data.decode("ascii", errors="ignore")):
        raise _nvidia_parser_failure(
            "gpu_structured_probe_unsafe_xml",
            "NVIDIA XML must not contain DTD or entity declarations",
            evidence=evidence,
        )
    _decode_nvidia_utf8(data, evidence)
    try:
        parser = ET.XMLPullParser(events=("start", "end", "comment", "pi"))
        parser.feed(data)
        parser_events = _typed_nvidia_xml_events(parser, evidence)
        parser.close()
        root = next(
            (node for event, node in parser_events if event == "start"),
            None,
        )
    except ET.ParseError as exc:
        raise _nvidia_parser_failure(
            "gpu_structured_probe_malformed",
            "NVIDIA XML could not be parsed",
            evidence=evidence,
        ) from exc
    if root is None:
        raise _nvidia_parser_failure(
            "gpu_structured_probe_malformed",
            "NVIDIA XML contains no document root",
            evidence=evidence,
        )
    physical: list[FullGpuUuid] = []
    mig: list[FullMigUuid] = []
    joins: list[NvidiaTopologyJoin] = []
    seen_physical: set[str] = set()
    seen_mig: set[str] = set()
    seen_joins: set[tuple[str, int]] = set()
    for element in root.iter():
        if _xml_local_name_strict(element) != "gpu":
            continue
        uuid = _xml_required_child_text(element, "uuid", evidence)
        if _NVIDIA_UUID_RE.fullmatch(uuid) is None or not uuid.startswith("GPU-"):
            raise _nvidia_parser_failure(
                "gpu_structured_probe_malformed",
                "NVIDIA XML physical UUID is not full and opaque",
                evidence=evidence,
                gpu_uuid=uuid,
            )
        if uuid in seen_physical:
            raise _nvidia_parser_failure(
                "gpu_uuid_duplicate",
                "NVIDIA XML repeats a physical UUID",
                evidence=evidence,
                gpu_uuid=uuid,
            )
        seen_physical.add(uuid)
        physical.append(uuid)
        for child in element.iter():
            if child is element or _xml_local_name_strict(child) not in {"mig_device", "mig_instance"}:
                continue
            mig_uuid = _xml_required_child_text(child, "uuid", evidence)
            if _NVIDIA_UUID_RE.fullmatch(mig_uuid) is None or not mig_uuid.startswith("MIG-"):
                raise _nvidia_parser_failure(
                    "gpu_structured_probe_malformed",
                    "NVIDIA XML MIG UUID is not full and opaque",
                    evidence=evidence,
                    mig_uuid=mig_uuid,
                )
            ordinal_text = _xml_required_child_text(child, "device_ordinal", evidence)
            if not ordinal_text.isdecimal():
                raise _nvidia_parser_failure(
                    "gpu_mig_join_conflict",
                    "NVIDIA XML MIG device ordinal is not decimal",
                    evidence=evidence,
                    value=ordinal_text,
                )
            ordinal = int(ordinal_text)
            declared_parent = next(
                (
                    candidate.text.strip()
                    for candidate in list(child)
                    if _xml_local_name_strict(candidate) == "parent_uuid" and candidate.text
                ),
                uuid,
            )
            if declared_parent != uuid:
                raise _nvidia_parser_failure(
                    "gpu_mig_join_conflict",
                    "NVIDIA XML MIG topology parent does not match its physical GPU",
                    evidence=evidence,
                    parent_uuid=uuid,
                    declared_parent=declared_parent,
                    mig_uuid=mig_uuid,
                )
            join_key = (uuid, ordinal)
            if mig_uuid in seen_mig or join_key in seen_joins:
                raise _nvidia_parser_failure(
                    "gpu_mig_join_conflict",
                    "NVIDIA XML repeats a MIG UUID or parent/ordinal join",
                    evidence=evidence,
                    parent_uuid=uuid,
                    ordinal=ordinal,
                    mig_uuid=mig_uuid,
                )
            seen_mig.add(mig_uuid)
            seen_joins.add(join_key)
            mig.append(mig_uuid)
            joins.append(NvidiaTopologyJoin(uuid, ordinal, mig_uuid))
    if not physical:
        raise _nvidia_parser_failure(
            "gpu_structured_probe_malformed",
            "NVIDIA XML contains no physical GPU topology",
            evidence=evidence,
        )
    containers = tuple(
        element
        for element in root.iter()
        if _xml_local_name_strict(element) in _NVIDIA_PROCESS_CONTAINER_TAGS
    )
    for element in root.iter():
        tag = _xml_local_name_strict(element)
        if "process" in tag and tag not in _NVIDIA_PROCESS_CONTAINER_TAGS | _NVIDIA_PROCESS_RECORD_TAGS:
            raise _nvidia_parser_failure(
                "gpu_process_scope_unproven",
                "NVIDIA XML contains an unsupported process scope",
                evidence=evidence,
                tag=tag,
            )
    if not containers:
        raise _nvidia_parser_failure(
            "gpu_process_inventory_unproven",
            "NVIDIA XML omitted supported process inventory containers",
            evidence=evidence,
        )
    inventory_text = " ".join(
        text_value.strip().lower()
        for container in containers
        for text_value in container.itertext()
        if text_value.strip()
    )
    hidden_marker = next(
        (
            marker
            for marker in ("permission denied", "insufficient permission", "not supported", "unknown error")
            if marker in inventory_text
        ),
        None,
    )
    if hidden_marker is not None:
        raise _nvidia_parser_failure(
            "gpu_process_inventory_unproven",
            "NVIDIA XML process inventory is hidden or unsupported",
            evidence=evidence,
            marker=hidden_marker,
        )
    process_records = tuple(
        element
        for container in containers
        for element in container.iter()
        if _xml_local_name_strict(element) == "process_info"
    )
    disposition: Literal["COMPLETE", "COMPLETE_EMPTY"] = (
        "COMPLETE_EMPTY" if not process_records else "COMPLETE"
    )
    processing_instructions = tuple(
        str(element.text or "") for event, element in parser_events if event == "pi"
    )
    comments = tuple(
        str(element.text or "") for event, element in parser_events if event == "comment"
    )
    parsed = ParsedNvidiaXml(
        schema_version="nvidia-xml/v1",
        physical_uuids=tuple(physical),
        mig_uuids=tuple(mig),
        joins=tuple(joins),
        processing_instructions=processing_instructions,
        comments=comments,
        process_inventory_disposition=disposition,
        evidence_fingerprint=_evidence_fingerprint(
            evidence,
            payload={
                "physical_uuids": tuple(physical),
                "mig_uuids": tuple(mig),
                "joins": tuple(_nvidia_join_payload(join) for join in joins),
                "processing_instructions": processing_instructions,
                "comments": comments,
                "process_inventory_disposition": disposition,
            },
        ),
    )
    return _ParsedNvidiaXmlDocument(
        parsed=parsed,
        root=root,
        parent_map=_xml_parent_map(root),
    )


def _parse_nvidia_smi_xml(evidence: EvidenceFd) -> ParsedNvidiaXml:
    """Parse XML once through the canonical retained-fd parser."""
    return _parse_nvidia_smi_xml_document(evidence).parsed


def _structured_gpu_devices(
    document: _ParsedNvidiaXmlDocument,
    inventory: NvidiaInventory,
    allocated: frozenset[str],
) -> dict[str, GPUDevice]:
    """Materialize memory-bearing devices from the canonical parsed XML graph."""
    root = document.root
    parent_map = document.parent_map
    parsed_devices: dict[str, GPUDevice] = {}
    for gpu in root.iter():
        if _xml_local_name(gpu) != "gpu":
            continue
        uuid = _xml_text(gpu.find("uuid"), "gpu.uuid")
        memory = gpu.find("fb_memory_usage")
        if memory is None:
            continue
        parsed_devices[uuid] = GPUDevice(
            uuid=uuid,
            free_memory_bytes=_xml_memory_bytes(
                memory.find("free"), "gpu.fb_memory_usage.free"
            ),
            memory_bytes=_xml_memory_bytes(
                memory.find("total"), "gpu.fb_memory_usage.total"
            ),
        )
    for element in root.iter():
        if _xml_local_name(element) not in {
            "mig_device",
            "gpu_instance",
            "compute_instance",
        }:
            continue
        uuid = _structured_unit_uuid(element, parent_map)
        if not uuid or uuid in parsed_devices:
            continue
        parent_element = _nearest_xml_ancestor(element, parent_map, frozenset({"gpu"}))
        parent_value = parent_element.find("uuid") if parent_element is not None else None
        parent = parent_value.text.strip() if parent_value is not None and parent_value.text else None
        memory = element.find("fb_memory_usage")
        if memory is None:
            continue
        parsed_devices[uuid] = GPUDevice(
            uuid=uuid,
            free_memory_bytes=_xml_memory_bytes(
                memory.find("free"), "mig.fb_memory_usage.free"
            ),
            memory_bytes=_xml_memory_bytes(
                memory.find("total"), "mig.fb_memory_usage.total"
            ),
            mig_parent_uuid=parent,
        )
    if not parsed_devices or not allocated.issubset(parsed_devices):
        raise TypedPreflightFailure(
            "gpu_structured_discovery_cardinality_incomplete",
            "structured GPU observation does not cover every allocated UUID/MIG UUID",
            allocated=tuple(sorted(allocated)),
            observed=tuple(sorted(parsed_devices)),
        )
    if set(inventory.physical_uuids).difference(parsed_devices) or set(
        inventory.mig_uuids
    ).difference(parsed_devices):
        raise TypedPreflightFailure(
            "gpu_structured_discovery_cardinality_incomplete",
            "strict NVIDIA inventory and memory observation disagree",
        )
    return parsed_devices


class NvidiaInventoryProbe:
    """Own only fd-backed NVIDIA driver, list, and topology evidence."""

    def __init__(
        self,
        list_evidence: EvidenceFd,
        xml_evidence: EvidenceFd,
        driver_evidence: EvidenceFd | None = None,
    ) -> None:
        self._list_evidence = list_evidence
        self._xml_evidence = xml_evidence
        self._driver_evidence = driver_evidence

    @staticmethod
    def parse_nvidia_driver_version(evidence: EvidenceFd) -> NvidiaDriverVersion:
        return _parse_driver_version(evidence)

    @staticmethod
    def parse_nvidia_smi_list(evidence: EvidenceFd) -> NvidiaListEvidence:
        return _parse_nvidia_smi_list(evidence)

    @staticmethod
    def parse_nvidia_smi_xml(evidence: EvidenceFd) -> ParsedNvidiaXml:
        return _parse_nvidia_smi_xml(evidence)

    def observe(self) -> NvidiaInventory:
        list_evidence = self.parse_nvidia_smi_list(self._list_evidence)
        xml_evidence = self.parse_nvidia_smi_xml(self._xml_evidence)
        if (
            list_evidence.physical_uuids != xml_evidence.physical_uuids
            or list_evidence.mig_uuids != xml_evidence.mig_uuids
            or list_evidence.joins != xml_evidence.joins
        ):
            raise TypedPreflightFailure(
                "gpu_mig_join_conflict",
                "NVIDIA list and XML topology evidence disagree",
                list_source=self._list_evidence.source_name,
                xml_source=self._xml_evidence.source_name,
            )
        driver = (
            self.parse_nvidia_driver_version(self._driver_evidence)
            if self._driver_evidence is not None
            else None
        )
        return NvidiaInventory(
            schema_version="nvidia-inventory/v1",
            physical_uuids=list_evidence.physical_uuids,
            mig_uuids=list_evidence.mig_uuids,
            joins=list_evidence.joins,
            driver_version=driver,
            evidence_fingerprint=hashlib.sha256(
                _canonical_json(
                    {
                        "list": list_evidence.evidence_fingerprint,
                        "xml": xml_evidence.evidence_fingerprint,
                        "driver": _nvidia_driver_payload(driver),
                    }
                ).encode("utf-8")
            ).hexdigest(),
        )

    def observe_structured(
        self,
        allocated: frozenset[str],
    ) -> NvidiaStructuredObservation:
        """Return all admission values from one retained-fd XML parse."""
        list_evidence = self.parse_nvidia_smi_list(self._list_evidence)
        xml_document = _parse_nvidia_smi_xml_document(self._xml_evidence)
        xml_evidence = xml_document.parsed
        if (
            list_evidence.physical_uuids != xml_evidence.physical_uuids
            or list_evidence.mig_uuids != xml_evidence.mig_uuids
            or list_evidence.joins != xml_evidence.joins
        ):
            raise TypedPreflightFailure(
                "gpu_mig_join_conflict",
                "NVIDIA list and XML topology evidence disagree",
                list_source=self._list_evidence.source_name,
                xml_source=self._xml_evidence.source_name,
            )
        driver = (
            self.parse_nvidia_driver_version(self._driver_evidence)
            if self._driver_evidence is not None
            else None
        )
        inventory = NvidiaInventory(
            schema_version="nvidia-inventory/v1",
            physical_uuids=list_evidence.physical_uuids,
            mig_uuids=list_evidence.mig_uuids,
            joins=list_evidence.joins,
            driver_version=driver,
            evidence_fingerprint=hashlib.sha256(
                _canonical_json(
                    {
                        "list": list_evidence.evidence_fingerprint,
                        "xml": xml_evidence.evidence_fingerprint,
                        "driver": _nvidia_driver_payload(driver),
                    }
                ).encode("utf-8")
            ).hexdigest(),
        )
        parsed_devices = _structured_gpu_devices(xml_document, inventory, allocated)
        process_visibility = _prove_allocated_process_inventory_visibility(
            xml_document.root,
            allocated,
            xml_document.parent_map,
        )
        processes = _parse_structured_gpu_processes(
            xml_document.root,
            parsed_devices,
            xml_document.parent_map,
        )
        return NvidiaStructuredObservation(
            inventory=inventory,
            devices=tuple(sorted(parsed_devices.values(), key=lambda device: device.uuid)),
            processes=processes,
            process_inventory_visibility=process_visibility,
        )


def parse_nvidia_driver_version(evidence: EvidenceFd) -> NvidiaDriverVersion:
    """Parse driver evidence through the sole NVIDIA inventory owner."""
    return NvidiaInventoryProbe.parse_nvidia_driver_version(evidence)


def parse_nvidia_smi_list(evidence: EvidenceFd) -> NvidiaListEvidence:
    """Parse strict list evidence through the sole NVIDIA inventory owner."""
    return NvidiaInventoryProbe.parse_nvidia_smi_list(evidence)


def parse_nvidia_smi_xml(evidence: EvidenceFd) -> ParsedNvidiaXml:
    """Parse strict XML evidence through the sole NVIDIA inventory owner."""
    return NvidiaInventoryProbe.parse_nvidia_smi_xml(evidence)


@dataclass(frozen=True)
class ProcessOccupancyEvidence:
    """Conservative process occupancy for one proven local namespace."""

    schema_version: Literal["gpu-process-occupancy/v1"]
    namespace_inode: int
    processes: tuple[ProcessIdentity, ...]
    occupied_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    inventory_scope: Literal["local-namespace-complete"]
    evidence_fingerprint: Sha256Hex


class GpuProcessOccupancyProbe:
    """Own process/namespace occupancy, separate from topology and locks."""

    def __init__(
        self,
        *,
        inventory: NvidiaInventory,
        namespace_inode: int,
        processes: Sequence[ProcessIdentity],
        process_inventory_disposition: str,
    ) -> None:
        self._inventory = inventory
        self._namespace_inode = namespace_inode
        self._processes = tuple(processes)
        self._process_inventory_disposition = process_inventory_disposition
        self._state: Literal["UNPROVEN", "OBSERVING", "PROVEN", "FAILED"] = "UNPROVEN"

    def observe(self) -> ProcessOccupancyEvidence:
        """Prove one complete process inventory and close its occupied UUID set."""
        if self._state != "UNPROVEN":
            raise TypedPreflightFailure(
                "gpu_process_observation_repeated",
                "GPU process occupancy is a one-shot observation",
                state=self._state,
            )
        self._state = "OBSERVING"
        try:
            evidence = self._observe_once()
        except TypedPreflightFailure:
            self._state = "FAILED"
            raise
        self._state = "PROVEN"
        return evidence

    def _observe_once(self) -> ProcessOccupancyEvidence:
        if self._namespace_inode <= 0:
            raise TypedPreflightFailure(
                "gpu_namespace_identity_unproven",
                "GPU process occupancy requires a positive local namespace inode",
                namespace_inode=self._namespace_inode,
            )
        if self._process_inventory_disposition not in {"COMPLETE", "COMPLETE_EMPTY"}:
            raise TypedPreflightFailure(
                "gpu_process_inventory_unproven",
                "GPU process inventory is not proven complete",
                disposition=self._process_inventory_disposition,
            )
        if self._process_inventory_disposition == "COMPLETE_EMPTY" and self._processes:
            raise TypedPreflightFailure(
                "gpu_process_inventory_conflict",
                "complete-empty process evidence contains process identities",
                process_count=len(self._processes),
            )
        physical_uuids = tuple(self._inventory.physical_uuids)
        mig_uuids = tuple(self._inventory.mig_uuids)
        physical_set = set(physical_uuids)
        mig_set = set(mig_uuids)
        if (
            len(physical_set) != len(physical_uuids)
            or len(mig_set) != len(mig_uuids)
            or physical_set & mig_set
            or any(
                _NVIDIA_UUID_RE.fullmatch(uuid) is None or not uuid.startswith("GPU-")
                for uuid in physical_uuids
            )
            or any(
                _NVIDIA_UUID_RE.fullmatch(uuid) is None or not uuid.startswith("MIG-")
                for uuid in mig_uuids
            )
        ):
            raise TypedPreflightFailure(
                "gpu_process_topology_unproven",
                "GPU process occupancy received duplicate or non-opaque inventory UUIDs",
            )
        known_uuids = physical_set | mig_set
        children_by_parent: dict[str, tuple[str, ...]] = {}
        parent_by_child: dict[str, str] = {}
        seen_join_keys: set[tuple[str, int]] = set()
        seen_join_mig_uuids: set[str] = set()
        for join in self._inventory.joins:
            join_key = (join.parent_uuid, join.ordinal)
            if (
                join.parent_uuid not in physical_set
                or join.mig_uuid not in mig_set
                or join.ordinal < 0
                or join_key in seen_join_keys
                or join.mig_uuid in seen_join_mig_uuids
            ):
                raise TypedPreflightFailure(
                    "gpu_process_topology_unproven",
                    "GPU process occupancy received a topology join outside inventory",
                    parent_uuid=join.parent_uuid,
                    mig_uuid=join.mig_uuid,
                )
            seen_join_keys.add(join_key)
            seen_join_mig_uuids.add(join.mig_uuid)
            parent_by_child[join.mig_uuid] = join.parent_uuid
            children_by_parent[join.parent_uuid] = tuple(
                sorted((*children_by_parent.get(join.parent_uuid, ()), join.mig_uuid))
            )
        ordered_processes = tuple(
            sorted(
                self._processes,
                key=lambda process: (
                    process.gpu_uuid,
                    process.kind,
                    process.pid,
                    process.process_start_identity,
                ),
            )
        )
        seen_processes: set[tuple[int, str, str, str]] = set()
        seen_pid_starts: dict[int, str] = {}
        occupied: set[str] = set()
        expected_namespace = f"pid:[{self._namespace_inode}]"
        for process in ordered_processes:
            identity_key = (
                process.pid,
                process.process_start_identity,
                process.gpu_uuid,
                process.kind,
            )
            if identity_key in seen_processes:
                raise TypedPreflightFailure(
                    "gpu_process_identity_ambiguous",
                    "GPU process inventory repeats one process identity",
                    pid=process.pid,
                    gpu_uuid=process.gpu_uuid,
                )
            seen_processes.add(identity_key)
            previous_start = seen_pid_starts.setdefault(process.pid, process.process_start_identity)
            if previous_start != process.process_start_identity:
                raise TypedPreflightFailure(
                    "gpu_process_identity_ambiguous",
                    "GPU process PID has conflicting process-start identities",
                    pid=process.pid,
                    first_start_identity=previous_start,
                    second_start_identity=process.process_start_identity,
                )
            if not process.kind:
                raise TypedPreflightFailure(
                    "gpu_process_identity_unproven",
                    "GPU process identity has no conservative process kind",
                    pid=process.pid,
                )
            if process.container_namespace_identity != expected_namespace:
                raise TypedPreflightFailure(
                    "gpu_process_namespace_mismatch",
                    "GPU process identity is not proven in the local namespace",
                    pid=process.pid,
                    observed_namespace=process.container_namespace_identity,
                    expected_namespace=expected_namespace,
                )
            if process.gpu_uuid not in known_uuids or _NVIDIA_UUID_RE.fullmatch(process.gpu_uuid) is None:
                raise TypedPreflightFailure(
                    "gpu_process_uuid_visibility_unproven",
                    "GPU process identity is not bound to an observed full UUID",
                    pid=process.pid,
                    gpu_uuid=process.gpu_uuid,
                )
            if process.gpu_uuid in physical_set:
                occupied.add(process.gpu_uuid)
                occupied.update(children_by_parent.get(process.gpu_uuid, ()))
            else:
                occupied.add(process.gpu_uuid)
                parent_uuid = parent_by_child.get(process.gpu_uuid)
                if parent_uuid is not None:
                    occupied.add(parent_uuid)
        occupied_uuids = tuple(sorted(occupied))
        fingerprint = hashlib.sha256(
            _canonical_json(
                _json_safe(
                    {
                        "schema_version": "gpu-process-occupancy/v1",
                        "namespace_inode": self._namespace_inode,
                        "processes": tuple(_process_record(process) for process in ordered_processes),
                        "occupied_uuids": occupied_uuids,
                        "inventory_scope": "local-namespace-complete",
                    }
                )
            ).encode("utf-8")
        ).hexdigest()
        return ProcessOccupancyEvidence(
            schema_version="gpu-process-occupancy/v1",
            namespace_inode=self._namespace_inode,
            processes=ordered_processes,
            occupied_uuids=occupied_uuids,
            inventory_scope="local-namespace-complete",
            evidence_fingerprint=fingerprint,
        )


FdDisposition: TypeAlias = Literal[
    "busy_candidate",
    "reserved",
    "released",
    "rolled_back",
    "close_ambiguous",
]
DescendantQuiescenceStatus: TypeAlias = Literal["PROVEN", "UNPROVEN"]


@dataclass(frozen=True)
class LockReadback:
    """One fd-bound lock identity readback owned by the reservation transaction."""

    runtime_root: Literal["/var/lib/agent-canon/runtime"]
    filesystem_type: Literal["btrfs", "ext4", "xfs"]
    device: int
    inode: int
    selected: tuple["ReservationEvidence", ...]
    fingerprint: Sha256Hex


@dataclass(frozen=True)
class ReservationEvidence:
    """The immutable result of one candidate-local admission attempt."""

    schema_version: Literal["gpu-reservation/v1"]
    selected_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    locks: tuple[LockReadback, ...]
    disposition: Literal["ACQUIRED", "BUSY_CANDIDATE", "ROLLED_BACK"]
    evidence_fingerprint: Sha256Hex


@dataclass(frozen=True)
class ConcurrentRunEvidence:
    initial_snapshot_fingerprint: Sha256Hex
    admission_snapshot_fingerprint: Sha256Hex
    final_snapshot_fingerprint: Sha256Hex
    initial_event_id: str
    admission_event_id: str
    final_event_id: str
    fingerprint: Sha256Hex


@dataclass(frozen=True)
class MigEvidence:
    parent_by_uuid: Mapping[FullMigUuid, FullGpuUuid]
    executable_leaf_uuids: tuple[FullMigUuid, ...]
    selected_physical_uuids: tuple[FullGpuUuid, ...]
    fingerprint: Sha256Hex

    def __post_init__(self) -> None:
        object.__setattr__(self, "parent_by_uuid", _freeze_mapping(self.parent_by_uuid))
        object.__setattr__(self, "executable_leaf_uuids", tuple(self.executable_leaf_uuids))
        object.__setattr__(self, "selected_physical_uuids", tuple(self.selected_physical_uuids))


@dataclass(frozen=True)
class UuidVisibilityEvidence:
    cuda_visible_devices: str | None
    nvidia_visible_devices: str | None
    disposition: VisibilityDisposition
    visible_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    namespace_id: str
    provision_receipt_fingerprint: Sha256Hex
    fingerprint: Sha256Hex


@dataclass(frozen=True)
class LockPlacementEvidence:
    runtime_root: Literal["/var/lib/agent-canon/runtime"]
    filesystem_type: Literal["btrfs", "ext4", "xfs"]
    filesystem_source: str
    device: int
    inode: int
    group_name: Literal["agent-canon-runtime"]
    mode: Literal["02770", "0660"]
    local_flock_filesystem: Literal[True]
    fingerprint: Sha256Hex


@dataclass(frozen=True)
class DescendantRetentionEvidence:
    child_process_ids: tuple[int, ...]
    process_group_ids: tuple[int, ...]
    descendant_quiescence: DescendantQuiescenceStatus
    retained_gpu_process_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    release_blocked: bool
    fingerprint: Sha256Hex


@dataclass(frozen=True)
class RunGpuAdmissionReceipt:
    """The immutable join of independent discovery, occupancy, and lock owners."""

    schema_version: Literal["gpu-admission/v1"]
    candidate_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    occupied_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    reserved_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    selected_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    inventory_fingerprint: Sha256Hex
    occupancy_fingerprint: Sha256Hex
    reservation_fingerprint: Sha256Hex
    runtime_identity_fingerprint: Sha256Hex
    plan_fingerprint: Sha256Hex | None
    admission_fingerprint: Sha256Hex
    lock_readback: LockReadback | None = None
    effective_environment: Mapping[str, str] | None = None
    actual_gpu_processes: tuple[ProcessOccupancyEvidence, ...] | None = None
    concurrent_run_evidence: ConcurrentRunEvidence | None = None
    mig_evidence: MigEvidence | None = None
    container_visible_uuid_mapping: UuidVisibilityEvidence | None = None
    os_safe_lock_placement: LockPlacementEvidence | None = None
    descendant_retention_evidence: DescendantRetentionEvidence | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "candidate_uuids",
            "occupied_uuids",
            "reserved_uuids",
            "selected_uuids",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        if self.effective_environment is not None:
            object.__setattr__(
                self,
                "effective_environment",
                _freeze_mapping(self.effective_environment),
            )
        if self.actual_gpu_processes is not None:
            object.__setattr__(
                self,
                "actual_gpu_processes",
                tuple(self.actual_gpu_processes),
            )
        supplied_fingerprint = self.admission_fingerprint
        computed_fingerprint = hashlib.sha256(
            _canonical_json(_admission_receipt_payload(self)).encode("utf-8")
        ).hexdigest()
        if supplied_fingerprint and not secrets.compare_digest(
            supplied_fingerprint,
            computed_fingerprint,
        ):
            raise TypedPreflightFailure(
                "gpu_admission_fingerprint_mismatch",
                "GPU admission fingerprint does not match the complete receipt preimage",
                supplied_fingerprint=supplied_fingerprint,
            )
        object.__setattr__(self, "admission_fingerprint", computed_fingerprint)


def _admission_receipt_payload(value: RunGpuAdmissionReceipt) -> dict[str, object]:
    def full_lock_readback(lock: LockReadback) -> dict[str, object]:
        payload = _lock_readback_payload(lock)
        payload["fingerprint"] = lock.fingerprint
        payload["selected"] = tuple(
            full_reservation_evidence(item) for item in lock.selected
        )
        return payload

    def full_reservation_evidence(
        reservation: ReservationEvidence,
    ) -> dict[str, object]:
        payload = _reservation_evidence_payload(reservation)
        payload["evidence_fingerprint"] = reservation.evidence_fingerprint
        payload["locks"] = tuple(
            full_lock_readback(item) for item in reservation.locks
        )
        return payload

    return {
        "schema_version": value.schema_version,
        "candidate_uuids": value.candidate_uuids,
        "occupied_uuids": value.occupied_uuids,
        "reserved_uuids": value.reserved_uuids,
        "selected_uuids": value.selected_uuids,
        "inventory_fingerprint": value.inventory_fingerprint,
        "occupancy_fingerprint": value.occupancy_fingerprint,
        "reservation_fingerprint": value.reservation_fingerprint,
        "runtime_identity_fingerprint": value.runtime_identity_fingerprint,
        "plan_fingerprint": value.plan_fingerprint,
        "lock_readback": (
            full_lock_readback(value.lock_readback)
            if value.lock_readback is not None
            else None
        ),
        "effective_environment": value.effective_environment,
        "actual_gpu_processes": (
            tuple(
                {
                    "schema_version": item.schema_version,
                    "namespace_inode": item.namespace_inode,
                    "processes": tuple(
                        _process_record(process) for process in item.processes
                    ),
                    "occupied_uuids": item.occupied_uuids,
                    "inventory_scope": item.inventory_scope,
                    "evidence_fingerprint": item.evidence_fingerprint,
                }
                for item in value.actual_gpu_processes
            )
            if value.actual_gpu_processes is not None
            else None
        ),
        "concurrent_run_evidence": (
            {
                "initial_snapshot_fingerprint": value.concurrent_run_evidence.initial_snapshot_fingerprint,
                "admission_snapshot_fingerprint": value.concurrent_run_evidence.admission_snapshot_fingerprint,
                "final_snapshot_fingerprint": value.concurrent_run_evidence.final_snapshot_fingerprint,
                "initial_event_id": value.concurrent_run_evidence.initial_event_id,
                "admission_event_id": value.concurrent_run_evidence.admission_event_id,
                "final_event_id": value.concurrent_run_evidence.final_event_id,
                "fingerprint": value.concurrent_run_evidence.fingerprint,
            }
            if value.concurrent_run_evidence is not None
            else None
        ),
        "mig_evidence": (
            {
                "parent_by_uuid": value.mig_evidence.parent_by_uuid,
                "executable_leaf_uuids": value.mig_evidence.executable_leaf_uuids,
                "selected_physical_uuids": value.mig_evidence.selected_physical_uuids,
                "fingerprint": value.mig_evidence.fingerprint,
            }
            if value.mig_evidence is not None
            else None
        ),
        "container_visible_uuid_mapping": (
            {
                "cuda_visible_devices": value.container_visible_uuid_mapping.cuda_visible_devices,
                "nvidia_visible_devices": value.container_visible_uuid_mapping.nvidia_visible_devices,
                "disposition": value.container_visible_uuid_mapping.disposition,
                "visible_uuids": value.container_visible_uuid_mapping.visible_uuids,
                "namespace_id": value.container_visible_uuid_mapping.namespace_id,
                "provision_receipt_fingerprint": value.container_visible_uuid_mapping.provision_receipt_fingerprint,
                "fingerprint": value.container_visible_uuid_mapping.fingerprint,
            }
            if value.container_visible_uuid_mapping is not None
            else None
        ),
        "os_safe_lock_placement": (
            {
                "runtime_root": value.os_safe_lock_placement.runtime_root,
                "filesystem_type": value.os_safe_lock_placement.filesystem_type,
                "filesystem_source": value.os_safe_lock_placement.filesystem_source,
                "device": value.os_safe_lock_placement.device,
                "inode": value.os_safe_lock_placement.inode,
                "group_name": value.os_safe_lock_placement.group_name,
                "mode": value.os_safe_lock_placement.mode,
                "local_flock_filesystem": value.os_safe_lock_placement.local_flock_filesystem,
                "fingerprint": value.os_safe_lock_placement.fingerprint,
            }
            if value.os_safe_lock_placement is not None
            else None
        ),
        "descendant_retention_evidence": (
            {
                "child_process_ids": value.descendant_retention_evidence.child_process_ids,
                "process_group_ids": value.descendant_retention_evidence.process_group_ids,
                "descendant_quiescence": value.descendant_retention_evidence.descendant_quiescence,
                "retained_gpu_process_uuids": value.descendant_retention_evidence.retained_gpu_process_uuids,
                "release_blocked": value.descendant_retention_evidence.release_blocked,
                "fingerprint": value.descendant_retention_evidence.fingerprint,
            }
            if value.descendant_retention_evidence is not None
            else None
        ),
    }


@dataclass(frozen=True)
class FdReleaseEvidence:
    """Exactly-one-attempt release evidence for one transaction-owned fd."""

    component: str
    uuid: FullGpuUuid | FullMigUuid | None
    disposition: FdDisposition
    close_attempts: Literal[1]
    error_kind: str | None
    fingerprint: Sha256Hex


def _reservation_evidence_payload(value: ReservationEvidence) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "selected_uuids": value.selected_uuids,
        "locks": tuple(_lock_readback_payload(lock) for lock in value.locks),
        "disposition": value.disposition,
    }


def _lock_readback_payload(value: LockReadback) -> dict[str, object]:
    return {
        "runtime_root": value.runtime_root,
        "filesystem_type": value.filesystem_type,
        "device": value.device,
        "inode": value.inode,
        "selected": tuple(_reservation_evidence_payload(item) for item in value.selected),
    }


def _fd_release_payload(value: FdReleaseEvidence) -> dict[str, object]:
    return {
        "component": value.component,
        "uuid": value.uuid,
        "disposition": value.disposition,
        "close_attempts": value.close_attempts,
        "error_kind": value.error_kind,
    }


class GpuReservationTransaction:
    """Own atomic candidate locks, readback, and total reverse rollback."""

    def __init__(
        self,
        lock_root: AbsolutePosixPath | Path = LOCK_ROOT,
        *,
        runtime_root: AbsolutePosixPath = HOST_RUNTIME_ROOT,
    ) -> None:
        if fcntl is None:
            raise TypedPreflightFailure(
                "gpu_reservation_unavailable",
                "GPU reservation requires the Unix flock interface",
            )
        if runtime_root != HOST_RUNTIME_ROOT:
            raise TypedPreflightFailure(
                "gpu_lock_namespace_not_canonical",
                "GPU reservation must use the canonical shared runtime root",
                runtime_root=runtime_root,
            )
        self._lock_root = Path(validate_absolute_posix_path(str(lock_root)))
        self._runtime_root: Literal["/var/lib/agent-canon/runtime"] = HOST_RUNTIME_ROOT
        try:
            self._root_fd = os.open(
                self._lock_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            root_stat = os.fstat(self._root_fd)
        except OSError as exc:
            raise TypedPreflightFailure(
                "gpu_lock_namespace_unavailable",
                "GPU lock namespace could not be opened with fd-bound no-follow flags",
                lock_root=str(self._lock_root),
                errno=exc.errno,
            ) from exc
        if not stat.S_ISDIR(root_stat.st_mode):
            os.close(self._root_fd)
            raise TypedPreflightFailure(
                "gpu_lock_namespace_invalid",
                "GPU lock namespace is not a directory",
                lock_root=str(self._lock_root),
            )
        self._root_device = root_stat.st_dev
        self._root_uid = root_stat.st_uid
        self._root_gid = root_stat.st_gid
        self._filesystem_type: Literal["btrfs", "ext4", "xfs"] = (
            self._read_filesystem_type(self._lock_root)
        )
        self._held: list[tuple[str, int, os.stat_result]] = []
        self._reservation_ids: dict[str, str] = {}
        self._release_dispositions: list[FdReleaseEvidence] = []
        self._state: Literal["CREATED", "ACQUIRING", "HELD", "ROLLING_BACK", "CLOSED"] = "CREATED"

    @staticmethod
    def _read_filesystem_type(path: Path) -> Literal["btrfs", "ext4", "xfs"]:
        try:
            result = subprocess.run(
                ["stat", "-f", "-c", "%T", str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise TypedPreflightFailure(
                "gpu_lock_filesystem_unavailable",
                "lock filesystem type could not be read",
                path=str(path),
            ) from exc
        filesystem_type = result.stdout.strip()
        if result.returncode != 0 or filesystem_type not in {"btrfs", "ext4", "xfs"}:
            raise TypedPreflightFailure(
                "gpu_lock_filesystem_unproved",
                "GPU lock filesystem must be btrfs, ext4, or xfs",
                path=str(path),
                filesystem_type=filesystem_type,
                returncode=result.returncode,
            )
        return cast(Literal["btrfs", "ext4", "xfs"], filesystem_type)

    def try_reserve(
        self,
        candidate_uuids: Sequence[FullGpuUuid | FullMigUuid],
        *,
        occupied_uuids: Sequence[FullGpuUuid | FullMigUuid] = (),
        requested_count: int = 1,
    ) -> ReservationEvidence:
        """Scan candidates; busy closes only its fd, infrastructure rolls back all."""
        if self._state != "CREATED":
            raise TypedPreflightFailure(
                "gpu_reservation_transaction_repeated",
                "GPU reservation transaction is one-shot",
                state=self._state,
            )
        if requested_count <= 0:
            raise TypedPreflightFailure(
                "gpu_reservation_cardinality_invalid",
                "GPU reservation requested count must be positive",
                requested_count=requested_count,
            )
        candidates = tuple(candidate_uuids)
        if len(set(candidates)) != len(candidates):
            raise TypedPreflightFailure(
                "gpu_reservation_candidate_ambiguous",
                "GPU reservation candidates must be unique",
            )
        occupied = frozenset(occupied_uuids)
        if any(_NVIDIA_UUID_RE.fullmatch(uuid) is None for uuid in candidates):
            raise TypedPreflightFailure(
                "gpu_reservation_uuid_unproven",
                "GPU reservation requires complete opaque UUIDs",
            )
        self._state = "ACQUIRING"
        busy_count = 0
        try:
            for uuid in candidates:
                if uuid in occupied:
                    busy_count += 1
                    continue
                descriptor, lock_stat = self._open_candidate(uuid)
                try:
                    if not self._try_lock(descriptor):
                        busy_evidence = self._close_busy_candidate(descriptor, uuid)
                        if busy_evidence.error_kind is not None:
                            raise TypedPreflightFailure(
                                "gpu_busy_candidate_close_ambiguous",
                                "busy GPU candidate lock close was ambiguous",
                                attempted_once=True,
                                close_error_kind=busy_evidence.error_kind,
                            )
                        busy_count += 1
                        continue
                    self._verify_candidate_identity(uuid, descriptor, lock_stat)
                    previous = os.pread(descriptor, 65536, 0)
                    if previous:
                        record = _strict_json_object(
                            previous,
                            path=str(self._lock_root / f"gpu-{_safe_uuid_filename(uuid)}.lock"),
                        )
                        if record.get("schema_version") not in {
                            "gpu-reservation-released/v1",
                            "gpu-reservation-reclaimed/v1",
                        }:
                            raise TypedPreflightFailure(
                                "gpu_lock_record_tampered",
                                "an acquired lock contains a non-released record",
                                uuid=uuid,
                            )
                    self._write_active_record(descriptor, uuid)
                    self._held.append((uuid, descriptor, lock_stat))
                except BaseException:
                    if descriptor not in {held[1] for held in self._held}:
                        self._close_descriptor_once(descriptor, uuid, "rolled_back")
                    raise
                if len(self._held) >= requested_count:
                    self._state = "HELD"
                    return self._evidence("ACQUIRED")
            self._state = "ROLLING_BACK"
            dispositions = self.close()
            if any(item.disposition == "close_ambiguous" for item in dispositions):
                raise TypedPreflightFailure(
                    "gpu_reservation_rollback_ambiguous",
                    "partial GPU reservation rollback had an ambiguous close",
                    primary_failure="candidate_exhaustion",
                    release_dispositions=tuple(
                        _fd_release_payload(item) for item in dispositions
                    ),
                )
            if any(item.error_kind is not None for item in dispositions):
                raise TypedPreflightFailure(
                    "gpu_reservation_rollback_failed",
                    "partial GPU reservation rollback recorded a release failure",
                    primary_failure="candidate_exhaustion",
                    release_dispositions=tuple(
                        _fd_release_payload(item) for item in dispositions
                    ),
                )
            return self._evidence("BUSY_CANDIDATE")
        except BaseException as primary:
            self._state = "ROLLING_BACK"
            dispositions = self.close()
            if any(item.disposition == "close_ambiguous" for item in dispositions):
                raise TypedPreflightFailure(
                    "gpu_reservation_rollback_ambiguous",
                    "GPU reservation rollback had an ambiguous close",
                    primary_failure=type(primary).__name__,
                    release_dispositions=tuple(_fd_release_payload(item) for item in dispositions),
                ) from primary
            if any(item.error_kind is not None for item in dispositions):
                raise TypedPreflightFailure(
                    "gpu_reservation_rollback_failed",
                    "GPU reservation rollback recorded a release failure",
                    primary_failure=type(primary).__name__,
                    release_dispositions=tuple(_fd_release_payload(item) for item in dispositions),
                ) from primary
            if isinstance(primary, TypedPreflightFailure):
                raise
            raise TypedPreflightFailure(
                "gpu_reservation_infrastructure_failed",
                "GPU reservation infrastructure failed",
                failure=type(primary).__name__,
            ) from primary

    @property
    def reservation_ids(self) -> tuple[str, ...]:
        """Return reservation identities in the stable selected-UUID order."""
        return tuple(
            self._reservation_ids[uuid]
            for uuid, _, _ in self._held
            if uuid in self._reservation_ids
        )

    def _open_candidate(self, uuid: str) -> tuple[int, os.stat_result]:
        name = f"gpu-{_safe_uuid_filename(uuid)}.lock"
        try:
            descriptor = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o660,
                dir_fd=self._root_fd,
            )
        except OSError as exc:
            raise TypedPreflightFailure(
                "gpu_lock_open_failed",
                "GPU candidate lock could not be opened",
                uuid=uuid,
                errno=exc.errno,
            ) from exc
        try:
            lock_stat = os.fstat(descriptor)
            path_stat = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
        except OSError as exc:
            self._close_descriptor_once(descriptor, uuid, "rolled_back")
            raise TypedPreflightFailure(
                "gpu_lock_open_failed",
                "GPU candidate lock identity could not be read",
                uuid=uuid,
                errno=exc.errno,
            ) from exc
        if not stat.S_ISREG(lock_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            self._close_descriptor_once(descriptor, uuid, "rolled_back")
            raise TypedPreflightFailure(
                "gpu_lock_not_regular",
                "GPU candidate lock must be a regular file",
                uuid=uuid,
            )
        if (lock_stat.st_dev, lock_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
            self._close_descriptor_once(descriptor, uuid, "rolled_back")
            raise TypedPreflightFailure(
                "gpu_lock_identity_changed",
                "GPU candidate lock path identity differs from its fd",
                uuid=uuid,
            )
        if lock_stat.st_dev != self._root_device:
            self._close_descriptor_once(descriptor, uuid, "rolled_back")
            raise TypedPreflightFailure(
                "gpu_lock_device_changed",
                "GPU candidate lock is outside the shared lock filesystem",
                uuid=uuid,
            )
        return descriptor, lock_stat

    @staticmethod
    def _try_lock(descriptor: int) -> bool:
        try:
            assert fcntl is not None
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                return False
            raise TypedPreflightFailure(
                "gpu_lock_acquire_failed",
                "GPU candidate flock failed",
                errno=exc.errno,
            ) from exc
        return True

    def _verify_candidate_identity(
        self,
        uuid: str,
        descriptor: int,
        initial_stat: os.stat_result,
    ) -> None:
        name = f"gpu-{_safe_uuid_filename(uuid)}.lock"
        final_stat = os.fstat(descriptor)
        path_stat = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
        if (initial_stat.st_dev, initial_stat.st_ino) != (
            final_stat.st_dev,
            final_stat.st_ino,
        ) or (final_stat.st_dev, final_stat.st_ino) != (
            path_stat.st_dev,
            path_stat.st_ino,
        ):
            raise TypedPreflightFailure(
                "gpu_lock_readback_tampered",
                "GPU candidate lock identity changed during admission",
                uuid=uuid,
            )
        if (
            not stat.S_ISREG(final_stat.st_mode)
            or stat.S_IMODE(final_stat.st_mode) != 0o660
            or final_stat.st_uid != self._root_uid
            or final_stat.st_gid != self._root_gid
            or path_stat.st_uid != self._root_uid
            or path_stat.st_gid != self._root_gid
        ):
            raise TypedPreflightFailure(
                "gpu_lock_readback_invalid",
                "GPU candidate lock type, mode, or ownership is invalid",
                uuid=uuid,
            )

    def _write_active_record(self, descriptor: int, uuid: str) -> None:
        reservation_id = f"reservation-{secrets.token_hex(12)}"
        record = {
            "schema_version": "gpu-reservation/v1",
            "reservation_id": reservation_id,
            "uuid": uuid,
            "owner_pid": os.getpid(),
            "owner_process_start_identity": _process_start_identity(os.getpid()),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip(),
            "lock_namespace": str(self._lock_root),
        }
        payload = (_canonical_json(record) + "\n").encode("utf-8")
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise TypedPreflightFailure(
                    "gpu_lock_record_write_failed",
                    "GPU candidate lock record write made no progress",
                    uuid=uuid,
                )
            offset += written
        os.fsync(descriptor)
        self._reservation_ids[uuid] = reservation_id

    def _evidence(
        self,
        disposition: Literal["ACQUIRED", "BUSY_CANDIDATE", "ROLLED_BACK"],
    ) -> ReservationEvidence:
        locks = tuple(
            LockReadback(
                runtime_root=self._runtime_root,
                filesystem_type=self._filesystem_type,
                device=lock_stat.st_dev,
                inode=lock_stat.st_ino,
                selected=(),
                fingerprint="",
            )
            for _, _, lock_stat in self._held
        )
        locks = tuple(
            replace(
                lock,
                fingerprint=hashlib.sha256(
                    _canonical_json(_lock_readback_payload(lock)).encode("utf-8")
                ).hexdigest(),
            )
            for lock in locks
        )
        evidence = ReservationEvidence(
            schema_version="gpu-reservation/v1",
            selected_uuids=tuple(uuid for uuid, _, _ in self._held),
            locks=locks,
            disposition=disposition,
            evidence_fingerprint="",
        )
        return replace(
            evidence,
            evidence_fingerprint=hashlib.sha256(
                _canonical_json(_reservation_evidence_payload(evidence)).encode("utf-8")
            ).hexdigest(),
        )

    def _close_busy_candidate(
        self,
        descriptor: int,
        uuid: str,
    ) -> FdReleaseEvidence:
        return self._close_descriptor_once(descriptor, uuid, "busy_candidate")

    def _close_descriptor_once(
        self,
        descriptor: int,
        uuid: str | None,
        disposition: FdDisposition,
    ) -> FdReleaseEvidence:
        error_kind: str | None = None
        try:
            os.close(descriptor)
        except OSError as exc:
            error_kind = error_kind or "close_ambiguous"
            del exc
        if error_kind is not None:
            disposition = "close_ambiguous"
        evidence = FdReleaseEvidence(
            component="gpu-reservation-lock",
            uuid=uuid,
            disposition=disposition,
            close_attempts=1,
            error_kind=error_kind,
            fingerprint="",
        )
        evidence = replace(
            evidence,
            fingerprint=hashlib.sha256(
                _canonical_json(_fd_release_payload(evidence)).encode("utf-8")
            ).hexdigest(),
        )
        self._release_dispositions.append(evidence)
        return evidence

    def _write_release_record(self, descriptor: int, uuid: str) -> None:
        record = {
            "schema_version": "gpu-reservation-released/v1",
            "uuid": uuid,
            "released_at": utc_now(),
        }
        payload = (_canonical_json(record) + "\n").encode("utf-8")
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise TypedPreflightFailure(
                    "gpu_lock_release_record_failed",
                    "GPU release record write made no progress",
                    uuid=uuid,
                )
            offset += written
        os.fsync(descriptor)

    def close(self) -> tuple[FdReleaseEvidence, ...]:
        """Release all transaction-owned descriptors once, in reverse order."""
        if self._state == "CLOSED":
            return tuple(self._release_dispositions)
        self._state = "ROLLING_BACK"
        for uuid, descriptor, _ in reversed(self._held):
            release_error: str | None = None
            try:
                self._write_release_record(descriptor, uuid)
            except BaseException as exc:
                release_error = type(exc).__name__
            evidence = self._close_descriptor_once(descriptor, uuid, "released")
            if release_error is not None:
                evidence = replace(
                    evidence,
                    error_kind=release_error,
                    fingerprint="",
                )
                evidence = replace(
                    evidence,
                    fingerprint=hashlib.sha256(
                        _canonical_json(_fd_release_payload(evidence)).encode("utf-8")
                    ).hexdigest(),
                )
                self._release_dispositions[-1] = evidence
        self._held.clear()
        self._close_root()
        self._state = "CLOSED"
        return tuple(self._release_dispositions)

    def _close_root(self) -> None:
        root_fd = getattr(self, "_root_fd", -1)
        if root_fd == -1:
            return
        self._root_fd = -1
        try:
            os.close(root_fd)
        except OSError as exc:
            raise TypedPreflightFailure(
                "gpu_lock_root_close_ambiguous",
                "GPU lock namespace close was ambiguous",
                attempted_once=True,
                errno=exc.errno,
            ) from exc


@dataclass(frozen=True)
class _NvidiaSMIObservation:
    """Read-only transport observation returned by the NVIDIA resource probe."""

    allocated: frozenset[str]
    processes: tuple[ProcessIdentity, ...]
    devices: tuple[GPUDevice, ...]
    current_boot_id: str
    visible: frozenset[str]
    observed_at: str
    observation_event_id: str
    fingerprint: str
    cpu_set: tuple[int, ...]
    host_memory: int
    temp_capacity: int
    structure_capability: Mapping[str, str]
    tool_capability: Mapping[str, object]
    container_identity: str
    inventory: NvidiaInventory | None = None

    @classmethod
    def discover(
        cls,
        environment: Mapping[str, str],
        *,
        gpu_requested_count: int,
        runtime_root: Path,
    ) -> "_NvidiaSMIObservation":
        observed_at = utc_now()
        try:
            cpu_set = tuple(sorted(os.sched_getaffinity(0)))
        except (AttributeError, OSError) as exc:
            raise TypedPreflightFailure(
                "cpu_capability_discovery_unavailable",
                "authoritative CPU affinity discovery is unavailable",
            ) from exc
        boot_path = Path("/proc/sys/kernel/random/boot_id")
        try:
            boot_id = boot_path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise TypedPreflightFailure(
                "boot_identity_unavailable",
                "authoritative host boot identity is unavailable",
                path=str(boot_path),
            ) from exc
        if not boot_id:
            raise TypedPreflightFailure("boot_identity_unavailable", "boot identity is empty")
        allocated = frozenset()
        devices: tuple[GPUDevice, ...] = ()
        processes: tuple[ProcessIdentity, ...] = ()
        inventory: NvidiaInventory | None = None
        process_inventory_visibility: Mapping[str, object] | None = None
        tool_capability: dict[str, object] = {
            "tree": {
                "available": shutil.which("tree") is not None,
                "path": shutil.which("tree") or "",
            }
        }
        if gpu_requested_count:
            allocated = _scheduler_uuid_set(environment)
            nvidia_smi = shutil.which("nvidia-smi")
            if not nvidia_smi:
                raise TypedPreflightFailure(
                    "gpu_structured_probe_unavailable",
                    "GPU request requires the structured nvidia-smi XML probe",
                )
            list_evidence = _capture_evidence_fd(
                (nvidia_smi, "-L"),
                "nvidia_smi_list",
            )
            xml_evidence = _capture_evidence_fd(
                (nvidia_smi, "-q", "-x"),
                "nvidia_smi_xml",
            )
            driver_evidence = _capture_evidence_fd(
                (
                    nvidia_smi,
                    "--id=0",
                    "--query-gpu=driver_version",
                    "--format=csv,noheader,nounits",
                ),
                "nvidia_driver_version",
            )
            try:
                structured = NvidiaInventoryProbe(
                    list_evidence,
                    xml_evidence,
                    driver_evidence,
                ).observe_structured(allocated)
                inventory = structured.inventory
                devices = structured.devices
                processes = structured.processes
                process_inventory_visibility = structured.process_inventory_visibility
            finally:
                for evidence in (driver_evidence, xml_evidence, list_evidence):
                    _close_evidence_fd(evidence)
            tool_capability["nvidia-smi"] = {
                "available": True,
                "path": nvidia_smi,
                "query": "-q -x",
                "structured": True,
                "process_type_taxonomy": ("C", "G", "M", "O", "C+G", "M+C"),
                "pid_identity": "authoritative_proc_pid_stat_and_pid_namespace",
                "uuid_identity": "full_gpu_or_mig_uuid",
                "narrower_sources_rejected": ("pmon", "query-compute-apps"),
                "process_inventory_visibility": process_inventory_visibility,
            }
        else:
            tool_capability["nvidia-smi"] = {
                "available": shutil.which("nvidia-smi") is not None,
                "path": shutil.which("nvidia-smi") or "",
                "structured": True,
                "required": False,
            }
        structure_capability = {
            "available": "true" if tool_capability["tree"]["available"] else "false",
            "command": "tree",
            "structure_contract_ref": STRUCTURE_CONTRACT_REF,
        }
        try:
            host_memory = sum(
                int(line.split()[1]) * 1024
                for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
                if line.startswith("MemTotal:")
            )
            temp_capacity = shutil.disk_usage(Path("/")).free
        except (OSError, ValueError, IndexError) as exc:
            raise TypedPreflightFailure(
                "host_capability_discovery_unavailable",
                "authoritative host/temp capability discovery is unavailable",
            ) from exc
        try:
            container_identity = Path("/etc/hostname").read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise TypedPreflightFailure(
                "container_identity_unavailable",
                "container identity is unavailable",
            ) from exc
        observation_event_id = f"nvidia-smi-{secrets.token_hex(12)}"
        fingerprint = hashlib.sha256(
            _canonical_json(
                {
                    "allocated": tuple(sorted(allocated)),
                    "devices": tuple(
                        {
                            "uuid": device.uuid,
                            "free_memory_bytes": device.free_memory_bytes,
                            "memory_bytes": device.memory_bytes,
                            "mig_parent_uuid": device.mig_parent_uuid,
                        }
                        for device in devices
                    ),
                    "processes": tuple(_process_record(process) for process in processes),
                    "boot_id": boot_id,
                    "visible": tuple(sorted(allocated)),
                    "observed_at": observed_at,
                    "observation_event_id": observation_event_id,
                }
            ).encode("utf-8")
        ).hexdigest()
        processes = tuple(
            replace(
                process,
                observation_timestamp=observed_at,
                observation_fingerprint=fingerprint,
            )
            for process in processes
        )
        return cls(
            allocated=allocated,
            processes=processes,
            devices=devices,
            current_boot_id=boot_id,
            visible=allocated,
            observed_at=observed_at,
            observation_event_id=observation_event_id,
            fingerprint=fingerprint,
            cpu_set=cpu_set,
            host_memory=host_memory,
            temp_capacity=temp_capacity,
            structure_capability=structure_capability,
            tool_capability=tool_capability,
            container_identity=container_identity,
            inventory=inventory if gpu_requested_count else None,
        )

@dataclass(frozen=True)
class NvidiaSMIResourceProbe:
    """Production probe that performs a fresh structured observation per call."""

    environment: Mapping[str, str]
    gpu_requested_count: int
    runtime_root: Path

    @classmethod
    def discover(
        cls,
        environment: Mapping[str, str],
        *,
        gpu_requested_count: int,
        runtime_root: Path,
    ) -> "NvidiaSMIResourceProbe":
        return cls(
            environment=_freeze_mapping(environment),
            gpu_requested_count=gpu_requested_count,
            runtime_root=runtime_root,
        )

    def observe(self) -> ResourceObservation:
        snapshot = _NvidiaSMIObservation.discover(
            self.environment,
            gpu_requested_count=self.gpu_requested_count,
            runtime_root=self.runtime_root,
        )
        return ResourceObservation(
            caller_allocated_ids=snapshot.allocated,
            process_identities=snapshot.processes,
            gpu_devices=snapshot.devices,
            free_memory_bytes={
                device.uuid: device.free_memory_bytes for device in snapshot.devices
            },
            boot_id=snapshot.current_boot_id,
            container_visible_ids=snapshot.visible,
            observed_at=snapshot.observed_at,
            fingerprint=snapshot.fingerprint,
            observation_event_id=snapshot.observation_event_id,
            cpu_available_set=snapshot.cpu_set,
            host_memory_bytes=snapshot.host_memory,
            temp_bytes=snapshot.temp_capacity,
            structure_tool=snapshot.structure_capability,
            tool_availability=snapshot.tool_capability,
            container_id=snapshot.container_identity,
            nvidia_inventory=snapshot.inventory,
        )


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
    _released: threading.Event = field(
        default_factory=threading.Event,
        repr=False,
        compare=False,
    )

    @property
    def active(self) -> bool:
        return not self._released.is_set()

    def release(
        self,
        *,
        observation_supplier: Callable[[], ResourceObservation],
    ) -> Mapping[str, object]:
        if self._released.is_set():
            return MappingProxyType(
                {
                    "uuid": self.uuid,
                    "reservation_id": self.reservation_id,
                    "result": "already_released",
                }
            )
        observation = observation_supplier()
        if not observation.gpu_devices:
            raise TypedPreflightFailure(
                "gpu_structured_probe_unavailable",
                "GPU lease release requires a coherent structured observation",
                uuid=self.uuid,
                observation_event_id=observation.observation_event_id,
                observation_fingerprint=observation.fingerprint,
            )
        observed_processes = observation.process_identities
        occupied_units = _occupied_gpu_units(
            observed_processes,
            observation.gpu_devices,
            (self.uuid,),
        )
        holders = tuple(
            process
            for process in observed_processes
            if self.uuid
            in _occupied_gpu_units((process,), observation.gpu_devices, (self.uuid,))
        )
        readback_at = observation.observed_at
        relationship_evidence = tuple(_process_record(process) for process in holders)
        if holders:
            return MappingProxyType(
                {
                    "uuid": self.uuid,
                    "reservation_id": self.reservation_id,
                    "result": "retained_live_gpu_holder",
                    "lock_held_during_readback": True,
                    "process_readback_at": readback_at,
                    "observation_event_id": observation.observation_event_id,
                    "observation_fingerprint": observation.fingerprint,
                    "occupied_gpu_units": occupied_units,
                    "holder_processes": relationship_evidence,
                    "force_kill": False,
                }
            )
        released_at = utc_now()
        release_record = {
            "schema_version": "gpu-reservation-released/v1",
            "uuid": self.uuid,
            "reservation_id": self.reservation_id,
            "owner_pid": self.owner_pid,
            "owner_process_start_identity": self.owner_process_start_identity,
            "boot_id": self.boot_id,
            "released_at": released_at,
            "result": "released",
            "lock_held_during_readback": True,
            "process_readback_at": readback_at,
            "observation_event_id": observation.observation_event_id,
            "observation_fingerprint": observation.fingerprint,
            "occupied_gpu_units": occupied_units,
            "holder_processes": relationship_evidence,
            "force_kill": False,
        }
        encoded = _canonical_json(release_record).encode("utf-8")
        os.ftruncate(self._descriptor, 0)
        os.lseek(self._descriptor, 0, os.SEEK_SET)
        os.write(self._descriptor, encoded)
        os.fsync(self._descriptor)
        os.close(self._descriptor)
        self._released.set()
        return MappingProxyType(dict(release_record))


@dataclass(frozen=True)
class StaleReclaimEvidence:
    uuid: str
    reservation_id: str | None
    reclaimed: bool
    prelock_proof: Mapping[str, object]
    under_lock_proof: Mapping[str, object]
    persistence_witness: Mapping[str, object]
    recorded_at: str

    def __post_init__(self) -> None:
        for name in ("prelock_proof", "under_lock_proof", "persistence_witness"):
            object.__setattr__(
                self,
                name,
                _freeze_mapping(cast(Mapping[str, object], getattr(self, name))),
            )


class UUIDReservationStore:
    """Host-safe, per-UUID flock lease store shared by the planner."""

    def __init__(
        self,
        root: Path = LOCK_ROOT,
        *,
        shared_across_schedulers: bool,
        host_safe: bool,
        visibility_witness: str,
    ) -> None:
        if fcntl is None:
            raise ResourcePlanError("per-UUID flock leases require a Unix runtime")
        if not root.is_absolute():
            raise TypedPreflightFailure(
                "gpu_lock_namespace_not_absolute",
                "GPU lock namespace must be an absolute path",
                lock_root=str(root),
            )
        if ".codex" in root.parts:
            raise TypedPreflightFailure(
                "gpu_lock_namespace_host_runtime",
                "GPU lock namespace cannot use a host Codex runtime path",
                lock_root=str(root),
            )
        if not shared_across_schedulers or not host_safe or not visibility_witness:
            raise TypedPreflightFailure(
                "gpu_lock_namespace_unproved",
                "GPU lock namespace requires host-safe shared-scheduler evidence",
                lock_root=str(root),
                shared_across_schedulers=shared_across_schedulers,
                host_safe=host_safe,
                visibility_witness=visibility_witness,
            )
        self.root = root
        self.shared_across_schedulers = shared_across_schedulers
        self.host_safe = host_safe
        self.visibility_witness = visibility_witness

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
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            prior_record = json.loads(os.read(descriptor, 1024 * 1024) or b"{}")
        except json.JSONDecodeError:
            prior_record = {"schema_version": "unreadable"}
        prior_schema = prior_record.get("schema_version")
        overwrite_allowed = prior_record == {} or prior_schema in {
            "gpu-reservation-released/v1",
            "gpu-reservation-reclaimed/v1",
        }
        if not overwrite_allowed:
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
            "lock_namespace": {
                "root": str(self.root),
                "shared_across_schedulers": self.shared_across_schedulers,
                "host_safe": self.host_safe,
                "visibility_witness": self.visibility_witness,
            },
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
        observation_supplier: Callable[[], ResourceObservation],
        process_start_identity: Callable[[int], str | None],
    ) -> StaleReclaimEvidence:
        """Repeat every stale proof under the UUID lock and persist the result."""
        def holds_uuid(
            processes: Sequence[ProcessIdentity],
            devices: Sequence[GPUDevice],
        ) -> bool:
            return uuid in _occupied_gpu_units(processes, devices, (uuid,))

        path = self.root / f"gpu-{_safe_uuid_filename(uuid)}.lock"
        recorded_at = utc_now()
        empty_proof: Mapping[str, object] = MappingProxyType({})
        if not path.is_file():
            return self._persist_reclaim_evidence(
                uuid=uuid,
                reservation_id=None,
                reclaimed=False,
                prelock_proof={"lock_file_present": False},
                under_lock_proof=empty_proof,
                recorded_at=recorded_at,
            )
        try:
            record = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return self._persist_reclaim_evidence(
                uuid=uuid,
                reservation_id=None,
                reclaimed=False,
                prelock_proof={"lock_record_readable": False},
                under_lock_proof=empty_proof,
                recorded_at=recorded_at,
            )
        reservation_id = record.get("reservation_id")
        owner_pid = record.get("owner_pid")
        owner_start = record.get("owner_process_start_identity")
        if not isinstance(owner_pid, int) or not isinstance(owner_start, str):
            return self._persist_reclaim_evidence(
                uuid=uuid,
                reservation_id=reservation_id if isinstance(reservation_id, str) else None,
                reclaimed=False,
                prelock_proof={"owner_identity_valid": False},
                under_lock_proof=empty_proof,
                recorded_at=recorded_at,
            )
        prelock_observation = observation_supplier()
        prelock_boot_id = prelock_observation.boot_id
        prelock_processes = prelock_observation.process_identities
        prelock_devices = prelock_observation.gpu_devices
        prelock_owner_start = process_start_identity(owner_pid)
        prelock_owner_dead_or_reused = prelock_owner_start in (None, "dead") or (
            prelock_owner_start not in (owner_start, "unknown")
        )
        prelock_boot_equal = record.get("boot_id") == prelock_boot_id
        prelock_boot_changed = record.get("boot_id") != prelock_boot_id
        prelock_stale_owner_proved = prelock_boot_changed or (
            prelock_boot_equal and prelock_owner_dead_or_reused
        )
        prelock_proof = {
            "lock_file_present": True,
            "uuid_matches": record.get("uuid") == uuid,
            "recorded_boot_id": record.get("boot_id"),
            "current_boot_id": prelock_boot_id,
            "boot_identity_present": isinstance(record.get("boot_id"), str)
            and bool(record.get("boot_id")),
            "boot_id_equal": prelock_boot_equal,
            "boot_id_changed": prelock_boot_changed,
            "owner_pid": owner_pid,
            "recorded_process_start_identity": owner_start,
            "observed_process_start_identity": prelock_owner_start,
            "owner_dead_or_pid_reused": prelock_owner_dead_or_reused,
            "stale_owner_proved": prelock_stale_owner_proved,
            "gpu_process_absent": not holds_uuid(prelock_processes, prelock_devices),
            "gpu_processes": tuple(_process_record(process) for process in prelock_processes),
            "observation_timestamp": prelock_observation.observed_at,
            "observation_event_id": prelock_observation.observation_event_id,
            "observation_fingerprint": prelock_observation.fingerprint,
        }
        if not all(
            bool(prelock_proof[key])
            for key in (
                "uuid_matches",
                "boot_identity_present",
                "stale_owner_proved",
                "gpu_process_absent",
            )
        ):
            return self._persist_reclaim_evidence(
                uuid=uuid,
                reservation_id=reservation_id if isinstance(reservation_id, str) else None,
                reclaimed=False,
                prelock_proof=prelock_proof,
                under_lock_proof=empty_proof,
                recorded_at=recorded_at,
            )
        descriptor = os.open(path, os.O_RDWR)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            os.close(descriptor)
            return self._persist_reclaim_evidence(
                uuid=uuid,
                reservation_id=reservation_id if isinstance(reservation_id, str) else None,
                reclaimed=False,
                prelock_proof=prelock_proof,
                under_lock_proof={"exclusive_lock_acquired": False},
                recorded_at=recorded_at,
            )
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            current = json.loads(os.read(descriptor, 1024 * 1024) or b"{}")
            current_owner_pid = current.get("owner_pid")
            current_owner_start = current.get("owner_process_start_identity")
            under_lock_observation = observation_supplier()
            under_lock_boot_id = under_lock_observation.boot_id
            under_lock_processes = under_lock_observation.process_identities
            under_lock_devices = under_lock_observation.gpu_devices
            observation_fresh = (
                bool(prelock_observation.observation_event_id)
                and bool(under_lock_observation.observation_event_id)
                and prelock_observation.observation_event_id
                != under_lock_observation.observation_event_id
                and bool(prelock_observation.fingerprint)
                and bool(under_lock_observation.fingerprint)
                and prelock_observation.fingerprint
                != under_lock_observation.fingerprint
            )
            under_lock_owner_start = (
                process_start_identity(current_owner_pid)
                if isinstance(current_owner_pid, int)
                else None
            )
            under_lock_owner_dead_or_reused = (
                isinstance(current_owner_start, str)
                and (
                    under_lock_owner_start in (None, "dead")
                    or under_lock_owner_start not in (current_owner_start, "unknown")
                )
            )
            under_lock_boot_equal = current.get("boot_id") == under_lock_boot_id
            under_lock_boot_changed = current.get("boot_id") != under_lock_boot_id
            under_lock_stale_owner_proved = under_lock_boot_changed or (
                under_lock_boot_equal and under_lock_owner_dead_or_reused
            )
            under_lock_proof = {
                "exclusive_lock_acquired": True,
                "record_unchanged": current == record,
                "record_reread_under_lock": True,
                "uuid_matches": current.get("uuid") == uuid,
                "recorded_boot_id": current.get("boot_id"),
                "current_boot_id": under_lock_boot_id,
                "boot_identity_present": isinstance(current.get("boot_id"), str)
                and bool(current.get("boot_id")),
                "boot_id_equal": under_lock_boot_equal,
                "boot_id_changed": under_lock_boot_changed,
                "owner_pid": current_owner_pid,
                "recorded_process_start_identity": current_owner_start,
                "observed_process_start_identity": under_lock_owner_start,
                "owner_dead_or_pid_reused": under_lock_owner_dead_or_reused,
                "stale_owner_proved": under_lock_stale_owner_proved,
                "gpu_process_absent": not holds_uuid(
                    under_lock_processes,
                    under_lock_devices,
                ),
                "gpu_processes": tuple(
                    _process_record(process) for process in under_lock_processes
                ),
                "observation_timestamp": under_lock_observation.observed_at,
                "observation_event_id": under_lock_observation.observation_event_id,
                "observation_fingerprint": under_lock_observation.fingerprint,
                "fresh_from_prelock_observation": observation_fresh,
            }
            reclaimed = all(
                bool(under_lock_proof[key])
                for key in (
                    "record_unchanged",
                    "record_reread_under_lock",
                    "uuid_matches",
                    "boot_identity_present",
                    "stale_owner_proved",
                    "gpu_process_absent",
                    "fresh_from_prelock_observation",
                )
            )
            if reclaimed:
                tombstone = {
                    "schema_version": "gpu-reservation-reclaimed/v1",
                    "reservation_id": reservation_id,
                    "uuid": uuid,
                    "reclaimed_at": recorded_at,
                    "proof": under_lock_proof,
                }
                encoded = _canonical_json(_json_safe(tombstone)).encode("utf-8")
                os.ftruncate(descriptor, 0)
                os.lseek(descriptor, 0, os.SEEK_SET)
                os.write(descriptor, encoded)
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return self._persist_reclaim_evidence(
            uuid=uuid,
            reservation_id=reservation_id if isinstance(reservation_id, str) else None,
            reclaimed=reclaimed,
            prelock_proof=prelock_proof,
            under_lock_proof=under_lock_proof,
            recorded_at=recorded_at,
        )

    def _persist_reclaim_evidence(
        self,
        *,
        uuid: str,
        reservation_id: str | None,
        reclaimed: bool,
        prelock_proof: Mapping[str, object],
        under_lock_proof: Mapping[str, object],
        recorded_at: str,
    ) -> StaleReclaimEvidence:
        evidence_payload = {
            "schema_version": "gpu-stale-reclaim-evidence/v1",
            "uuid": uuid,
            "reservation_id": reservation_id,
            "reclaimed": reclaimed,
            "prelock_proof": prelock_proof,
            "under_lock_proof": under_lock_proof,
            "recorded_at": recorded_at,
        }
        evidence_id = (
            (reservation_id or "no-reservation")
            + "-"
            + hashlib.sha256(f"{uuid}:{recorded_at}".encode("utf-8")).hexdigest()[:12]
            + "-"
            + secrets.token_hex(4)
        )
        witness = _write_json_once(
            self.root / "reclaim-evidence" / f"{_safe_uuid_filename(uuid)}-{evidence_id}.json",
            evidence_payload,
        )
        return StaleReclaimEvidence(
            uuid=uuid,
            reservation_id=reservation_id,
            reclaimed=reclaimed,
            prelock_proof=prelock_proof,
            under_lock_proof=under_lock_proof,
            persistence_witness=witness,
            recorded_at=recorded_at,
        )


def _safe_uuid_filename(uuid: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in uuid)


def _is_gpu_index(value: str) -> bool:
    return value.isdecimal()


@dataclass(frozen=True)
class ManagedRunAdapterIntegrationContract:
    """Ordered W1 contract consumed by the tracked managed-run adapter."""

    manager_artifact_path: str = DESIGN_MANAGER_ARTIFACT
    design_authority_path: str = DESIGN_AUTHORITY_ARTIFACT
    approved_design_revision: str = APPROVED_DESIGN_REVISION
    design_review_authority_path: str = DESIGN_REVIEW_AUTHORITY_ARTIFACT
    approved_design_brief_sha256: str = APPROVED_DESIGN_BRIEF_SHA256
    approved_design_partition_sha256: str = APPROVED_DESIGN_PARTITION_SHA256
    organizer_context_id: str = ORGANIZER_CONTEXT_ID
    organizer_conclusion_prior_hash: str = "none"
    organizer_conclusion_hash_assigned: bool = False
    downstream_adapter_path: str = MANAGED_RUN_ADAPTER_PATH
    canonical_planner: str = "GpuReservationTransaction"
    composition_owner: str = "RunGpuAdmissionContext"
    scheduler_role: str = "transport_only_no_reselection_no_rewrite"
    alternate_gpu_routes: tuple[str, ...] = ALTERNATE_GPU_ROUTE_STATIC_CONTRACT
    alternate_gpu_route_policy: str = (
        "canonical_managed_transaction_or_typed_gpu_prohibition"
    )
    parent_lineage_artifact: str = PARENT_LINEAGE_ARTIFACT
    parent_lineage_status: str = "parent_certificate_required"
    bypass_forbidden: bool = True
    _provenance: object = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        expected = (
            DESIGN_MANAGER_ARTIFACT,
            DESIGN_AUTHORITY_ARTIFACT,
            APPROVED_DESIGN_REVISION,
            DESIGN_REVIEW_AUTHORITY_ARTIFACT,
            APPROVED_DESIGN_BRIEF_SHA256,
            APPROVED_DESIGN_PARTITION_SHA256,
            ORGANIZER_CONTEXT_ID,
            "none",
            False,
            MANAGED_RUN_ADAPTER_PATH,
            "GpuReservationTransaction",
            "RunGpuAdmissionContext",
            "transport_only_no_reselection_no_rewrite",
            ALTERNATE_GPU_ROUTE_STATIC_CONTRACT,
            "canonical_managed_transaction_or_typed_gpu_prohibition",
            PARENT_LINEAGE_ARTIFACT,
            "parent_certificate_required",
            True,
        )
        observed = (
            self.manager_artifact_path,
            self.design_authority_path,
            self.approved_design_revision,
            self.design_review_authority_path,
            self.approved_design_brief_sha256,
            self.approved_design_partition_sha256,
            self.organizer_context_id,
            self.organizer_conclusion_prior_hash,
            self.organizer_conclusion_hash_assigned,
            self.downstream_adapter_path,
            self.canonical_planner,
            self.composition_owner,
            self.scheduler_role,
            self.alternate_gpu_routes,
            self.alternate_gpu_route_policy,
            self.parent_lineage_artifact,
            self.parent_lineage_status,
            self.bypass_forbidden,
        )
        if observed != expected:
            raise PlanStateError("managed-run integration contract is not the approved W1 interface")

    def record(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "manager_artifact_path": self.manager_artifact_path,
                "design_authority_path": self.design_authority_path,
                "approved_design_revision": self.approved_design_revision,
                "design_review_authority_path": self.design_review_authority_path,
                "approved_design_brief_sha256": self.approved_design_brief_sha256,
                "approved_design_partition_sha256": self.approved_design_partition_sha256,
                "organizer_context_id": self.organizer_context_id,
                "organizer_conclusion_prior_hash": self.organizer_conclusion_prior_hash,
                "organizer_conclusion_hash_assigned": self.organizer_conclusion_hash_assigned,
                "downstream_adapter_path": self.downstream_adapter_path,
                "canonical_planner": self.canonical_planner,
                "composition_owner": self.composition_owner,
                "scheduler_role": self.scheduler_role,
                "alternate_gpu_routes": self.alternate_gpu_routes,
                "alternate_gpu_route_policy": self.alternate_gpu_route_policy,
                "parent_lineage_artifact": self.parent_lineage_artifact,
                "parent_lineage_status": self.parent_lineage_status,
                "bypass_forbidden": self.bypass_forbidden,
            }
        )


def managed_run_adapter_integration_contract() -> ManagedRunAdapterIntegrationContract:
    """Materialize the only approved W1-to-managed-run ordered interface."""
    contract = ManagedRunAdapterIntegrationContract()
    object.__setattr__(
        contract,
        "_provenance",
        _MANAGED_RUN_INTEGRATION_PROVENANCE,
    )
    return contract


@dataclass(frozen=True)
class ResourceRequest:
    owner_id: str
    parent_id: str
    context_id: str
    maximum_timeout_seconds: float
    argv: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str]
    integration_contract: ManagedRunAdapterIntegrationContract
    plan_id: str = ""
    cpu_requested_set: tuple[int, ...] = ()
    gpu_requested_count: int = 0
    gpu_requested_memory_bytes: int = 0
    gpu_allocation_provenance: str = ""
    host_memory_bytes: int = 0
    temp_bytes: int = 0
    ports: tuple[Mapping[str, object], ...] = ()
    xla_jax_preallocation_values: Mapping[str, str] = field(default_factory=dict)
    runtime_root: Path = RUNTIME_ROOT
    source_projection_root: Path | None = None
    run_id: str = ""
    requested_chunks: tuple[str, ...] = ()
    lock_root: Path = LOCK_ROOT
    lock_namespace_shared_across_schedulers: bool = False
    lock_namespace_host_safe: bool = False
    lock_namespace_visibility_witness: str = ""
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
    discovered_tool_availability: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.owner_id or not self.parent_id or not self.context_id:
            raise ValueError("owner_id, parent_id, and context_id are required")
        if self.maximum_timeout_seconds <= 0:
            raise ValueError("maximum_timeout_seconds must be positive")
        if self.gpu_requested_count < 0 or self.gpu_requested_memory_bytes < 0:
            raise ValueError("GPU requirements cannot be negative")
        if not self.argv:
            raise ValueError("argv must not be empty")
        if (
            self.integration_contract._provenance
            is not _MANAGED_RUN_INTEGRATION_PROVENANCE
        ):
            raise TypedPreflightFailure(
                "managed_run_adapter_bypass",
                "resource requests must enter through the approved managed-run adapter interface",
                required_adapter=MANAGED_RUN_ADAPTER_PATH,
                manager_artifact=DESIGN_MANAGER_ARTIFACT,
                approved_design_revision=APPROVED_DESIGN_REVISION,
            )
        if not self.cwd.is_absolute():
            raise ValueError("cwd must be absolute")
        if self.gpu_requested_count and self.gpu_allocation_provenance != CALLER_ALLOCATION_PROVENANCE:
            raise TypedPreflightFailure(
                "gpu_allocation_provenance_missing",
                "GPU planning requires caller/scheduler UUID-set provenance",
                required_provenance=CALLER_ALLOCATION_PROVENANCE,
                observed_provenance=self.gpu_allocation_provenance,
            )
        object.__setattr__(self, "environment", _freeze_mapping(self.environment))
        object.__setattr__(
            self,
            "xla_jax_preallocation_values",
            _freeze_mapping(self.xla_jax_preallocation_values),
        )
        object.__setattr__(
            self,
            "discovered_structure_tool",
            _freeze_mapping(self.discovered_structure_tool),
        )
        object.__setattr__(
            self,
            "discovered_tool_availability",
            _freeze_mapping(self.discovered_tool_availability),
        )
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
    observation: ResourceObservation
    reservation_store: UUIDReservationStore | None
    tool_availability: Mapping[str, object] = field(default_factory=dict)
    allocation_provenance: str = ""
    observed_at: str = field(default_factory=utc_now)
    observation_fingerprint: str = ""
    state: PlanState = PlanState.RESOURCE_DISCOVERED
    state_history: tuple[PlanState, ...] = (PlanState.RESOURCE_DISCOVERED,)

    def __post_init__(self) -> None:
        object.__setattr__(self, "structure_tool", _freeze_mapping(self.structure_tool))
        object.__setattr__(self, "tool_availability", _freeze_mapping(self.tool_availability))
        object.__setattr__(
            self,
            "ports",
            tuple(cast(Mapping[str, object], _freeze_value(port)) for port in self.ports),
        )


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
    occupied_process_identities: tuple[ProcessIdentity, ...]
    process_identities: tuple[ProcessIdentity, ...]
    allocation_id: str
    lock_root: Path
    selection_order: tuple[str, ...]
    memory_bytes: Mapping[str, int]
    slot_id: str | None
    requested_count: int
    requested_memory_bytes: int
    readback_fingerprint: str
    lock_readback: Mapping[str, object]
    allocation_provenance: str
    leases: tuple[ReservationLease, ...] = field(repr=False, compare=False)
    _planner_provenance: object = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "caller_allocated_ids",
            "candidate_ids",
            "occupied_ids",
            "reserved_ids",
            "eligible_ids",
            "selected_ids",
            "reservation_ids",
            "occupied_process_identities",
            "process_identities",
            "selection_order",
            "leases",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "free_memory_bytes", _freeze_mapping(self.free_memory_bytes))
        object.__setattr__(self, "memory_bytes", _freeze_mapping(self.memory_bytes))
        object.__setattr__(self, "lock_readback", _freeze_mapping(self.lock_readback))
        if tuple(self.selected_ids) != tuple(sorted(self.selected_ids)):
            raise PlanStateError("selected GPU UUIDs must use stable UUID order")
        if self.candidate_ids != tuple(sorted(self.caller_allocated_ids)):
            raise PlanStateError("candidate GPU set must be the stable caller allocation A")
        if any(
            len(values) != len(set(values))
            for values in (
                self.caller_allocated_ids,
                self.occupied_ids,
                self.reserved_ids,
                self.eligible_ids,
                self.selected_ids,
            )
        ):
            raise PlanStateError("GPU A/O_t/R_t/E_t sets must not contain duplicates")
        expected_eligible = tuple(
            uuid
            for uuid in self.candidate_ids
            if uuid not in self.occupied_ids
            and uuid not in self.reserved_ids
            and self.free_memory_bytes.get(uuid, -1) >= self.requested_memory_bytes
        )
        if self.eligible_ids != expected_eligible:
            raise PlanStateError("eligible GPU set must equal hard-filtered A minus O_t/R_t")
        if self.selection_order != self.eligible_ids:
            raise PlanStateError("GPU selection order must equal stable E_t order")
        if not set(self.selected_ids).issubset(self.eligible_ids):
            raise PlanStateError("selected GPU UUIDs must be a subset of eligible UUIDs")
        if len(self.selected_ids) != self.requested_count:
            raise PlanStateError("GPU allocation cardinality does not match the request")
        if len(self.reservation_ids) != self.requested_count:
            raise PlanStateError("GPU reservation cardinality does not match the request")
        r5_transactional = (
            isinstance(self.lock_readback, Mapping)
            and self.lock_readback.get("reservation_owner")
            == "GpuReservationTransaction"
        )
        if not r5_transactional and len(self.leases) != self.requested_count:
            raise PlanStateError("GPU lease cardinality does not match the request")
        if any(
            self.free_memory_bytes.get(uuid, -1) < self.requested_memory_bytes
            for uuid in self.selected_ids
        ):
            raise PlanStateError("GPU allocation does not satisfy requested memory")


def _mark_canonical_planner_provenance(
    allocation: GPUAllocation,
) -> GPUAllocation:
    object.__setattr__(allocation, "_planner_provenance", _PLANNER_PROVENANCE)
    return allocation


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
        object.__setattr__(
            self,
            "side_effect_inventory",
            tuple(
                cast(Mapping[str, object], _freeze_value(side_effect))
                for side_effect in self.side_effect_inventory
            ),
        )

        object.__setattr__(self, "state_history", tuple(self.state_history))
        if not self.state_history or self.state_history[-1] != self.state:
            raise PlanStateError("state history must end at the current state")
        if self.state_history != STATE_SEQUENCE[: len(self.state_history)]:
            raise PlanStateError("state history must be an exact ordered prefix")
        if self.gpu_allocation.plan_fingerprint != self.plan_fingerprint:
            raise PlanStateError("GPU allocation fingerprint must match the immutable plan")
        tree_capability = self.container.get("tree_capability")
        if (
            self.container.get("structure_contract_ref") != STRUCTURE_CONTRACT_REF
            or not isinstance(tree_capability, Mapping)
            or tree_capability.get("structure_contract_ref")
            != STRUCTURE_CONTRACT_REF
        ):
            raise PlanStateError("plan cannot override the canonical structure contract")

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
    plan: ExecutionResourcePlan
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
        if self.plan.state != PlanState.ENV_MATERIALIZED:
            raise PlanStateError("materialized environment must carry the materialized plan")
        if self.plan_fingerprint != self.plan.plan_fingerprint:
            raise PlanStateError("materialized environment fingerprint mismatch")
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
    runtime_identity: str = ""
    allocation_id: str = ""
    caller_allocated_ids: tuple[str, ...] = ()
    reservation_ids: tuple[str, ...] = ()
    free_memory_bytes: Mapping[str, int] = field(default_factory=dict)
    process_identities: tuple[ProcessIdentity, ...] = ()
    requested_memory_bytes: int = 0
    probe_observation_timestamp: str = ""
    probe_observation_fingerprint: str = ""
    probe_observation_event_id: str = ""
    readback_fingerprint: str = ""
    readback_timestamp: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment", _freeze_mapping(self.environment))
        object.__setattr__(self, "free_memory_bytes", _freeze_mapping(self.free_memory_bytes))
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "visible_gpu_ids", tuple(self.visible_gpu_ids))
        object.__setattr__(self, "cpu_set", tuple(self.cpu_set))
        object.__setattr__(self, "caller_allocated_ids", tuple(self.caller_allocated_ids))
        object.__setattr__(self, "reservation_ids", tuple(self.reservation_ids))
        object.__setattr__(self, "process_identities", tuple(self.process_identities))


@dataclass(frozen=True)
class EnvironmentCertificate:
    plan: ExecutionResourcePlan = field(repr=False, compare=False)
    schema_version: str
    plan_fingerprint: str
    container_id: str
    runtime_identity: str
    cwd_equal: bool
    argv_equal: bool
    environment_key_set_equal: bool
    non_secret_env_equal: bool
    redacted_secret_witness: tuple[Mapping[str, object], ...]
    visible_gpu_ids_equal: bool
    cpu_set_equal: bool
    container_id_equal: bool
    runtime_identity_equal: bool
    allocation_id_equal: bool
    caller_allocation_equal: bool
    caller_allocation_probe_equal: bool
    reservation_ids_equal: bool
    reservation_leases_active: bool
    requested_memory_equal: bool
    free_memory_satisfies_request: bool
    free_memory_probe_equal: bool
    process_identities_equal: bool
    process_probe_equal: bool
    visible_gpu_probe_equal: bool
    readback_fingerprint_equal: bool
    runtime_root: Path
    source_projection_root: Path
    tree_capability: Mapping[str, str]
    tool_availability: Mapping[str, object]
    os_side_effect_inventory_ref: str
    certificate_persistence_witness: Mapping[str, object]
    inventory_persistence_witness: Mapping[str, object]
    readback_fingerprint: str
    all_witnesses_valid: bool
    readback_timestamp: str
    probe_observation_equal: bool = False
    state: PlanState = PlanState.EFFECTIVE_ENV_READBACK_VERIFIED

    def __post_init__(self) -> None:
        if self.plan.state != PlanState.EFFECTIVE_ENV_READBACK_VERIFIED:
            raise PlanStateError("certificate must carry the verified plan")
        if self.plan_fingerprint != self.plan.plan_fingerprint:
            raise PlanStateError("certificate fingerprint mismatch")
        if self.tree_capability.get("structure_contract_ref") != STRUCTURE_CONTRACT_REF:
            raise PlanStateError("certificate cannot override the canonical structure contract")
        for name in (
            "tree_capability",
            "tool_availability",
            "certificate_persistence_witness",
            "inventory_persistence_witness",
        ):
            object.__setattr__(
                self,
                name,
                _freeze_mapping(cast(Mapping[str, object], getattr(self, name))),
            )
        object.__setattr__(
            self,
            "redacted_secret_witness",
            tuple(
                cast(Mapping[str, object], _freeze_value(item))
                for item in self.redacted_secret_witness
            ),
        )


@dataclass(frozen=True)
class TerminalEvidence:
    plan: ExecutionResourcePlan = field(repr=False, compare=False)
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
    planned_chunk_ids: tuple[str, ...]
    terminal_chunk_ids: tuple[str, ...]
    terminal_chunk_records: tuple[Mapping[str, object], ...]
    partial: PartialEvidence
    persistence_witness: Mapping[str, object]
    terminal_timestamp: str
    state: PlanState = PlanState.TERMINAL

    def __post_init__(self) -> None:
        if self.plan.state != PlanState.TERMINAL:
            raise PlanStateError("terminal evidence must carry the terminal-state plan")
        if self.plan_fingerprint != self.plan.plan_fingerprint:
            raise PlanStateError("terminal fingerprint mismatch")
        object.__setattr__(self, "source_snapshot", _freeze_mapping(self.source_snapshot))
        object.__setattr__(self, "execution_result", _freeze_value(self.execution_result))
        if self.no_completion is not None:
            object.__setattr__(self, "no_completion", _freeze_mapping(self.no_completion))
        object.__setattr__(self, "planned_chunk_ids", tuple(self.planned_chunk_ids))
        object.__setattr__(self, "terminal_chunk_ids", tuple(self.terminal_chunk_ids))
        object.__setattr__(
            self,
            "terminal_chunk_records",
            tuple(
                cast(Mapping[str, object], _freeze_value(record))
                for record in self.terminal_chunk_records
            ),
        )
        object.__setattr__(
            self,
            "persistence_witness",
            _freeze_mapping(self.persistence_witness),
        )


@dataclass(frozen=True)
class CleanupEvidence:
    plan: ExecutionResourcePlan = field(repr=False, compare=False)
    plan_fingerprint: str
    side_effects: tuple[Mapping[str, object], ...]
    leak_or_unknown: tuple[Mapping[str, object], ...]
    descendant_retained_gpu_ids: tuple[str, ...]
    descendant_retained_processes: tuple[ProcessIdentity, ...]
    completion_coverage: CompletionCoverage
    closeout: CloseoutEvidence
    persistence_witness: Mapping[str, object]
    disposed_at: str
    state: PlanState = PlanState.CLEANUP_DISPOSED

    def __post_init__(self) -> None:
        if self.plan.state != PlanState.CLEANUP_DISPOSED:
            raise PlanStateError("cleanup evidence must carry the cleanup-state plan")
        if self.plan_fingerprint != self.plan.plan_fingerprint:
            raise PlanStateError("cleanup fingerprint mismatch")
        object.__setattr__(
            self,
            "side_effects",
            tuple(cast(Mapping[str, object], _freeze_value(item)) for item in self.side_effects),
        )
        object.__setattr__(
            self,
            "leak_or_unknown",
            tuple(cast(Mapping[str, object], _freeze_value(item)) for item in self.leak_or_unknown),
        )
        object.__setattr__(
            self,
            "persistence_witness",
            _freeze_mapping(self.persistence_witness),
        )


@dataclass(frozen=True)
class PreExecutionFailureTerminalEvidence:
    transaction_fingerprint: str
    failed_operation: str
    failure_code: str
    failure_message: str
    failure_evidence: Mapping[str, object]
    state_history: tuple[PlanState, ...]
    persistence_witness: Mapping[str, object]
    terminal_event_id: str
    state: PlanState = PlanState.TERMINAL

    def __post_init__(self) -> None:
        pre_terminal_history = self.state_history[:-1]
        if (
            self.state_history[-1:] != (PlanState.TERMINAL,)
            or not pre_terminal_history
            or pre_terminal_history
            != STATE_SEQUENCE[: len(pre_terminal_history)]
            or PlanState.EXECUTE in pre_terminal_history
        ):
            raise PlanStateError("pre-execution failure must terminate before cleanup")
        object.__setattr__(self, "failure_evidence", _freeze_mapping(self.failure_evidence))
        object.__setattr__(self, "state_history", tuple(self.state_history))
        object.__setattr__(self, "persistence_witness", _freeze_mapping(self.persistence_witness))


@dataclass(frozen=True)
class PreExecutionFailureCleanupEvidence:
    terminal: PreExecutionFailureTerminalEvidence
    lease_dispositions: tuple[Mapping[str, object], ...]
    leak_or_unknown: tuple[Mapping[str, object], ...]
    persistence_witness: Mapping[str, object]
    state_history: tuple[PlanState, ...]
    state: PlanState = PlanState.CLEANUP_DISPOSED

    def __post_init__(self) -> None:
        if self.state_history != (*self.terminal.state_history, PlanState.CLEANUP_DISPOSED):
            raise PlanStateError("pre-execution cleanup must follow its terminal edge")
        for name in ("lease_dispositions", "leak_or_unknown"):
            object.__setattr__(
                self,
                name,
                tuple(
                    cast(Mapping[str, object], _freeze_value(item))
                    for item in cast(Sequence[Mapping[str, object]], getattr(self, name))
                ),
            )
        object.__setattr__(self, "persistence_witness", _freeze_mapping(self.persistence_witness))
        object.__setattr__(self, "state_history", tuple(self.state_history))


@dataclass(frozen=True)
class PartialEvidence:
    plan_fingerprint: str
    last_exact_state: PlanState
    disposition: str
    stop_reason: str | None
    owner_maximum_timeout_seconds: float
    completed_chunk_ids: tuple[str, ...]
    in_flight_chunk_ids: tuple[str, ...]
    unstarted_chunk_ids: tuple[str, ...]
    diagnostics: Mapping[str, object]
    evidence_refs: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))
        object.__setattr__(self, "evidence_refs", _freeze_mapping(self.evidence_refs))


@dataclass(frozen=True)
class CloseoutEvidence:
    plan_fingerprint: str
    terminal_event_id: str
    terminal_evidence_present: bool
    partial_evidence_present: bool
    cleanup_evidence_present: bool
    closeout_evidence_present: bool
    effective_env_certificate_matches: bool
    required_review_gates_passed: bool
    validation_failures: tuple[Mapping[str, object], ...]
    unresolved_design_issue_blockers: tuple[str, ...]
    unresolved_validation_failures: tuple[Mapping[str, object], ...]
    all_planned_chunks_complete: bool
    overall_delivery_complete: bool
    completion_persistence_witness: Mapping[str, object]
    closeout_persistence_witness: Mapping[str, object]
    artifact_refs: Mapping[str, object]
    next_owner: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "validation_failures",
            tuple(
                cast(Mapping[str, object], _freeze_value(item))
                for item in self.validation_failures
            ),
        )
        object.__setattr__(
            self,
            "unresolved_validation_failures",
            tuple(
                cast(Mapping[str, object], _freeze_value(item))
                for item in self.unresolved_validation_failures
            ),
        )
        object.__setattr__(
            self,
            "completion_persistence_witness",
            _freeze_mapping(self.completion_persistence_witness),
        )
        object.__setattr__(
            self,
            "closeout_persistence_witness",
            _freeze_mapping(self.closeout_persistence_witness),
        )
        object.__setattr__(self, "artifact_refs", _freeze_mapping(self.artifact_refs))


@dataclass(frozen=True)
class FailureRecord:
    """Normalized terminal failure without traceback or secret-bearing reprs."""

    schema_version: Literal["gpu-failure/v1"]
    kind: str
    operation: str
    message: str
    evidence: Mapping[str, JsonValue]
    fingerprint: Sha256Hex

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence))


def _normalize_failure(exc: BaseException, operation: str) -> FailureRecord:
    """Normalize one terminal exception without moving authority to the caller."""
    kind = getattr(exc, "code", type(exc).__name__)
    message = str(exc)
    raw_evidence = getattr(exc, "evidence", {})
    evidence = (
        cast(Mapping[str, JsonValue], raw_evidence)
        if isinstance(raw_evidence, Mapping)
        else {}
    )
    payload = {
        "schema_version": "gpu-failure/v1",
        "kind": str(kind),
        "operation": operation,
        "message": message,
        "evidence": evidence,
    }
    return FailureRecord(
        schema_version="gpu-failure/v1",
        kind=str(kind),
        operation=operation,
        message=message,
        evidence=evidence,
        fingerprint=hashlib.sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest(),
    )


@dataclass(frozen=True)
class ManagedGpuOutcome:
    """Total terminal outcome produced after context state is closed."""

    schema_version: Literal["managed-gpu-outcome/v1"]
    run_id: str
    source_freeze_fingerprint: Sha256Hex | None
    plan_fingerprint: Sha256Hex | None
    admission_fingerprint: Sha256Hex | None
    planned_chunk_ids: tuple[str, ...]
    runner_lifecycle: RunnerLifecycleEvidence | None
    runner_lifecycle_fingerprint: Sha256Hex | None
    primary_failure: FailureRecord | None
    secondary_failures: tuple[FailureRecord, ...]
    release_disposition: tuple[FdReleaseEvidence, ...]
    context_state: Literal["closed"]
    exit_code: int
    outcome_fingerprint: Sha256Hex

    def __post_init__(self) -> None:
        object.__setattr__(self, "planned_chunk_ids", tuple(self.planned_chunk_ids))
        object.__setattr__(self, "secondary_failures", tuple(self.secondary_failures))
        object.__setattr__(self, "release_disposition", tuple(self.release_disposition))


@dataclass(frozen=True)
class AdmittedEnvironment:
    """Immutable exact UUID environment produced before generic runner creation."""

    schema_version: Literal["admitted-environment/v1"]
    exact_env_map: tuple[tuple[str, str], ...]
    cuda_visible_devices: str
    nvidia_visible_devices: str
    environment_fingerprint: Sha256Hex


def _failure_record_payload(value: FailureRecord) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "kind": value.kind,
        "operation": value.operation,
        "message": value.message,
        "evidence": value.evidence,
    }


def _outcome_payload(value: ManagedGpuOutcome) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "run_id": value.run_id,
        "source_freeze_fingerprint": value.source_freeze_fingerprint,
        "plan_fingerprint": value.plan_fingerprint,
        "admission_fingerprint": value.admission_fingerprint,
        "planned_chunk_ids": value.planned_chunk_ids,
        "runner_lifecycle_fingerprint": value.runner_lifecycle_fingerprint,
        "primary_failure": (
            _failure_record_payload(value.primary_failure)
            if value.primary_failure is not None
            else None
        ),
        "secondary_failures": tuple(
            _failure_record_payload(item) for item in value.secondary_failures
        ),
        "release_disposition": tuple(
            _fd_release_payload(item) for item in value.release_disposition
        ),
        "context_state": value.context_state,
        "exit_code": value.exit_code,
    }


class ManagedGpuOutcomeReducer:
    """Own terminal failure normalization and outcome fingerprints only."""

    def reduce_terminal(
        self,
        *,
        run_id: str,
        planned_chunk_ids: tuple[str, ...],
        admission: RunGpuAdmissionReceipt | None,
        source_freeze: SourceFreezeReceipt | None,
        runtime_identity: RuntimeIdentityReceipt | None,
        runner_lifecycle: RunnerLifecycleEvidence | None,
        primary_failure: FailureRecord | None,
        secondary_failures: tuple[FailureRecord, ...],
        release_disposition: tuple[FdReleaseEvidence, ...],
        context_state: Literal["closed"],
        exit_code: int,
    ) -> ManagedGpuOutcome:
        if context_state != "closed":
            raise TypedPreflightFailure(
                "gpu_outcome_context_not_closed",
                "terminal outcome requires closed composition context",
                context_state=context_state,
            )
        source_fingerprint = (
            source_freeze.receipt_fingerprint if source_freeze is not None else None
        )
        admission_fingerprint = (
            admission.admission_fingerprint if admission is not None else None
        )
        plan_fingerprint = (
            admission.plan_fingerprint if admission is not None else None
        )
        lifecycle_fingerprint = (
            hashlib.sha256(
                _canonical_json(_json_safe(runner_lifecycle.to_dict())).encode("utf-8")
            ).hexdigest()
            if runner_lifecycle is not None
            else None
        )
        outcome = ManagedGpuOutcome(
            schema_version="managed-gpu-outcome/v1",
            run_id=run_id,
            source_freeze_fingerprint=source_fingerprint,
            plan_fingerprint=plan_fingerprint,
            admission_fingerprint=admission_fingerprint,
            planned_chunk_ids=tuple(planned_chunk_ids),
            runner_lifecycle=runner_lifecycle,
            runner_lifecycle_fingerprint=lifecycle_fingerprint,
            primary_failure=primary_failure,
            secondary_failures=tuple(secondary_failures),
            release_disposition=tuple(release_disposition),
            context_state="closed",
            exit_code=exit_code,
            outcome_fingerprint="",
        )
        return replace(
            outcome,
            outcome_fingerprint=hashlib.sha256(
                _canonical_json(_outcome_payload(outcome)).encode("utf-8")
            ).hexdigest(),
        )


@dataclass(frozen=True)
class CompletionCoverageInput:
    schema_version: Literal["completion-coverage/v2"]
    outcome: ManagedGpuOutcome
    planned_chunk_ids: tuple[str, ...]
    candidate_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    occupied_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    reserved_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    selected_uuids: tuple[FullGpuUuid | FullMigUuid, ...]
    lock_readback: LockReadback | None
    effective_environment: Mapping[str, str] | None
    actual_gpu_processes: tuple[ProcessOccupancyEvidence, ...] | None
    concurrent_run_evidence: ConcurrentRunEvidence | None
    mig_evidence: MigEvidence | None
    container_visible_uuid_mapping: UuidVisibilityEvidence | None
    os_safe_lock_placement: LockPlacementEvidence | None
    descendant_retention_evidence: DescendantRetentionEvidence | None
    source_freeze_evidence: SourceFreezeReceipt | None
    absence_dispositions: tuple[EvidenceAbsence, ...]
    input_fingerprint: Sha256Hex = ""

    def __post_init__(self) -> None:
        if self.schema_version != COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported CompletionCoverageInput schema")
        object.__setattr__(self, "planned_chunk_ids", tuple(self.planned_chunk_ids))
        object.__setattr__(self, "candidate_uuids", tuple(self.candidate_uuids))
        object.__setattr__(self, "occupied_uuids", tuple(self.occupied_uuids))
        object.__setattr__(self, "reserved_uuids", tuple(self.reserved_uuids))
        object.__setattr__(self, "selected_uuids", tuple(self.selected_uuids))
        object.__setattr__(self, "absence_dispositions", tuple(self.absence_dispositions))
        optional_values: Mapping[str, object | None] = {
            "source_freeze_evidence": self.source_freeze_evidence,
            "lock_readback": self.lock_readback,
            "effective_environment": self.effective_environment,
            "actual_gpu_processes": self.actual_gpu_processes,
            "concurrent_run_evidence": self.concurrent_run_evidence,
            "mig_evidence": self.mig_evidence,
            "container_visible_uuid_mapping": self.container_visible_uuid_mapping,
            "os_safe_lock_placement": self.os_safe_lock_placement,
            "descendant_retention_evidence": self.descendant_retention_evidence,
        }
        absence_names = tuple(item.field_name for item in self.absence_dispositions)
        expected_absence_names = tuple(
            name for name in _EVIDENCE_ABSENCE_FIELD_ORDER if optional_values[name] is None
        )
        if absence_names != expected_absence_names:
            raise ValueError(
                "CompletionCoverageInput absence dispositions do not match optional evidence"
            )
        for item in self.absence_dispositions:
            if item.disposition == "not_reached" and item.failure_kind is not None:
                raise ValueError("not_reached evidence absence cannot carry a failure kind")
            if item.disposition == "failed" and not item.failure_kind:
                raise ValueError("failed evidence absence requires a failure kind")
            expected_fingerprint = hashlib.sha256(
                _canonical_json(
                    {
                        "field_name": item.field_name,
                        "disposition": item.disposition,
                        "failure_kind": item.failure_kind,
                    }
                ).encode("utf-8")
            ).hexdigest()
            if item.fingerprint != expected_fingerprint:
                raise ValueError("evidence absence fingerprint mismatch")
        if not self.input_fingerprint:
            payload = _completion_v2_input_payload(self)
            object.__setattr__(
                self,
                "input_fingerprint",
                hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest(),
            )


def build_completion_coverage_input(
    outcome: ManagedGpuOutcome,
    admission: RunGpuAdmissionReceipt | None,
    source_freeze: SourceFreezeReceipt | None,
    runtime_identity: RuntimeIdentityReceipt | None,
    evidence_absence: tuple[EvidenceAbsence, ...],
) -> CompletionCoverageInput:
    """Assemble one exact coverage input without becoming a second owner."""
    visibility = admission.container_visible_uuid_mapping if admission is not None else None
    if visibility is not None:
        if runtime_identity is None:
            raise CompletionCoverageFailure(
                "runtime identity is required for UUID visibility coverage"
            )
        visibility = replace(
            visibility,
            namespace_id=f"pid:[{runtime_identity.namespace_inode}]",
            provision_receipt_fingerprint=runtime_identity.provision_fingerprint,
        )
    return CompletionCoverageInput(
        schema_version=COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
        outcome=outcome,
        planned_chunk_ids=outcome.planned_chunk_ids,
        candidate_uuids=(admission.candidate_uuids if admission is not None else ()),
        occupied_uuids=(admission.occupied_uuids if admission is not None else ()),
        reserved_uuids=(admission.reserved_uuids if admission is not None else ()),
        selected_uuids=(admission.selected_uuids if admission is not None else ()),
        lock_readback=(admission.lock_readback if admission is not None else None),
        effective_environment=(
            admission.effective_environment if admission is not None else None
        ),
        actual_gpu_processes=(
            admission.actual_gpu_processes if admission is not None else None
        ),
        concurrent_run_evidence=(
            admission.concurrent_run_evidence if admission is not None else None
        ),
        mig_evidence=admission.mig_evidence if admission is not None else None,
        container_visible_uuid_mapping=visibility,
        os_safe_lock_placement=(
            admission.os_safe_lock_placement if admission is not None else None
        ),
        descendant_retention_evidence=(
            admission.descendant_retention_evidence if admission is not None else None
        ),
        source_freeze_evidence=source_freeze,
        absence_dispositions=evidence_absence,
    )


def _terminal_evidence_fingerprint(value: object | None) -> str | None:
    if value is None:
        return None
    for name in (
        "evidence_fingerprint",
        "receipt_fingerprint",
        "readback_fingerprint",
        "fingerprint",
    ):
        candidate = getattr(value, name, None)
        if isinstance(candidate, str):
            return candidate
    return hashlib.sha256(
        _canonical_json(_json_safe(getattr(value, "__dict__", value))).encode("utf-8")
    ).hexdigest()


def _completion_v2_input_payload(value: CompletionCoverageInput) -> dict[str, object]:
    return {
        "schema_version": "completion-coverage/v2",
        "outcome_fingerprint": (
            value.outcome.outcome_fingerprint if value.outcome is not None else None
        ),
        "planned_chunk_ids": value.planned_chunk_ids,
        "candidate_uuids": value.candidate_uuids,
        "occupied_uuids": value.occupied_uuids,
        "reserved_uuids": value.reserved_uuids,
        "selected_uuids": value.selected_uuids,
        "lock_readback": _terminal_evidence_fingerprint(value.lock_readback),
        "effective_environment": value.effective_environment,
        "actual_gpu_processes": tuple(
            _terminal_evidence_fingerprint(item)
            for item in (value.actual_gpu_processes or ())
        ),
        "concurrent_run_evidence": _terminal_evidence_fingerprint(value.concurrent_run_evidence),
        "mig_evidence": _terminal_evidence_fingerprint(value.mig_evidence),
        "container_visible_uuid_mapping": _terminal_evidence_fingerprint(
            value.container_visible_uuid_mapping
        ),
        "os_safe_lock_placement": _terminal_evidence_fingerprint(
            value.os_safe_lock_placement
        ),
        "descendant_retention_evidence": _terminal_evidence_fingerprint(
            value.descendant_retention_evidence
        ),
        "source_freeze_evidence": _terminal_evidence_fingerprint(value.source_freeze_evidence),
        "absence_dispositions": tuple(
            {
                "field_name": item.field_name,
                "disposition": item.disposition,
                "failure_kind": item.failure_kind,
                "fingerprint": item.fingerprint,
            }
            for item in value.absence_dispositions
        ),
    }


@dataclass(frozen=True)
class CompletionCoverage:
    schema_version: str
    plan_fingerprint: str
    terminal_event_id: str
    delivery_ordinal: int
    input_record: CompletionCoverageInput
    recorded_at: str
    all_planned_chunks_complete: bool
    overall_delivery_complete: bool
    unresolved_blockers: tuple[str, ...]
    persistence_witness: Mapping[str, object]
    input_fingerprint: Sha256Hex = ""
    terminal_complete: bool = False
    partial_complete: bool = False
    cleanup_complete: bool = False
    closeout_complete: bool = False
    failure_kind: str | None = None
    coverage_fingerprint: Sha256Hex = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "persistence_witness",
            _freeze_mapping(self.persistence_witness),
        )


@dataclass(frozen=True)
class _LegacyPlannerCoverageRecord:
    """Private historical planner record; never accepted by the R5 public gate."""

    schema_version: str = COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION
    plan_fingerprint: str = ""
    terminal_event_id: str = ""
    candidate_gpu_ids: tuple[str, ...] = ()
    occupied_gpu_ids: tuple[Mapping[str, object], ...] = ()
    reserved_gpu_ids: tuple[str, ...] = ()
    selected_gpu_ids: tuple[str, ...] = ()
    lock_readback: Mapping[str, object] = field(default_factory=dict)
    effective_env: Mapping[str, object] = field(default_factory=dict)
    actual_gpu_processes: tuple[Mapping[str, object], ...] = ()
    release_retention_disposition: Mapping[str, object] = field(default_factory=dict)
    concurrent_run_evidence: Mapping[str, object] = field(default_factory=dict)
    mig_evidence: Mapping[str, object] = field(default_factory=dict)
    container_visible_uuid_mapping: Mapping[str, object] = field(default_factory=dict)
    os_safe_lock_placement: Mapping[str, object] = field(default_factory=dict)
    descendant_retention_evidence: Mapping[str, object] = field(default_factory=dict)
    taxonomy_linked_validation_outcome: Mapping[str, object] = field(default_factory=dict)
    eligible_gpu_ids: tuple[str, ...] = ()
    planned_chunk_ids: tuple[str, ...] = ()
    terminal_chunk_ids: tuple[str, ...] = ()
    terminal_chunk_records: tuple[Mapping[str, object], ...] = ()
    required_evidence: Mapping[str, object] = field(default_factory=dict)
    effective_env_certificate_matches: bool = False
    cleanup_has_unresolved_leak_or_unknown: bool = True
    required_review_gates_passed: bool = False
    validation_failures: tuple[Mapping[str, object], ...] = ()
    unresolved_design_issue_blockers: tuple[str, ...] = ()
    unresolved_validation_failures: tuple[Mapping[str, object], ...] = ()


@dataclass
class CompletionCoverageAdapter:
    """Projection-only, exactly-once CompletionCoverage owner."""

    evidence_path: Path | None = None
    _records: dict[tuple[str, str], CompletionCoverage] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record_once(self, input: CompletionCoverageInput) -> CompletionCoverage:
        if input.outcome is not None:
            outcome = input.outcome
            key = (outcome.run_id, outcome.outcome_fingerprint)
            with self._lock:
                if key in self._records:
                    raise CompletionCoverageFailure(
                        "duplicate CompletionCoverage delivery",
                    )
                if self.evidence_path is None:
                    raise CompletionCoverageFailure(
                        "CompletionCoverage requires a durable evidence path",
                    )
                terminal_complete = outcome.context_state == "closed"
                cleanup_complete = (
                    outcome.context_state == "closed"
                    and all(
                        item.close_attempts == 1 and item.error_kind is None
                        for item in outcome.release_disposition
                    )
                )
                missing_evidence = tuple(
                    item.field_name for item in input.absence_dispositions
                )
                reached_evidence_complete = not missing_evidence
                all_planned_chunks_complete = (
                    reached_evidence_complete
                    and bool(input.planned_chunk_ids)
                    and outcome.primary_failure is None
                    and outcome.exit_code == 0
                )
                partial_complete = reached_evidence_complete
                closeout_complete = cleanup_complete and reached_evidence_complete
                overall_delivery_complete = (
                    terminal_complete
                    and partial_complete
                    and cleanup_complete
                    and all_planned_chunks_complete
                )
                failure_kind = (
                    outcome.primary_failure.kind
                    if outcome.primary_failure is not None
                    else None
                )
                unresolved_blockers = (
                    ((f"failure:{failure_kind}",) if failure_kind is not None else ())
                    + tuple(f"evidence_absent:{name}" for name in missing_evidence)
                )
                coverage_payload = {
                    "schema_version": "completion-coverage/v2",
                    "input_fingerprint": input.input_fingerprint,
                    "terminal_complete": terminal_complete,
                    "partial_complete": partial_complete,
                    "cleanup_complete": cleanup_complete,
                    "closeout_complete": closeout_complete,
                    "all_planned_chunks_complete": all_planned_chunks_complete,
                    "overall_delivery_complete": overall_delivery_complete,
                    "failure_kind": failure_kind,
                    "unresolved_blockers": unresolved_blockers,
                }
                coverage_fingerprint = hashlib.sha256(
                    _canonical_json(coverage_payload).encode("utf-8")
                ).hexdigest()
                recorded_at = utc_now()
                persistence_witness = _write_json_once(
                    self.evidence_path,
                    {**coverage_payload, "coverage_fingerprint": coverage_fingerprint},
                    allow_identical=False,
                )
                record = CompletionCoverage(
                    schema_version="completion-coverage/v2",
                    plan_fingerprint=outcome.plan_fingerprint or "",
                    terminal_event_id=outcome.outcome_fingerprint,
                    delivery_ordinal=1,
                    input_record=input,
                    recorded_at=recorded_at,
                    all_planned_chunks_complete=all_planned_chunks_complete,
                    overall_delivery_complete=overall_delivery_complete,
                    unresolved_blockers=unresolved_blockers,
                    persistence_witness=persistence_witness,
                    input_fingerprint=input.input_fingerprint,
                    terminal_complete=terminal_complete,
                    partial_complete=partial_complete,
                    cleanup_complete=cleanup_complete,
                    closeout_complete=closeout_complete,
                    failure_kind=failure_kind,
                    coverage_fingerprint=coverage_fingerprint,
                )
                self._records[key] = record
                return record
        raise CompletionCoverageFailure(
            "R5 CompletionCoverageAdapter.record_once accepts only the exact public input"
        )

    def _historical_planner_closeout_rejected(
        self,
        input: _LegacyPlannerCoverageRecord,
    ) -> CompletionCoverage:
        """Reject the superseded planner closeout instead of recording coverage."""
        raise CompletionCoverageFailure(
            "historical planner completion is not an authorized R5 route"
        )

        # The old validation body remains unreachable historical evidence only.
        key = (input.plan_fingerprint, input.terminal_event_id)
        with self._lock:
            if key in self._records:
                raise CompletionCoverageFailure(
                    "duplicate CompletionCoverage delivery",
                )
            if self.evidence_path is None:
                raise CompletionCoverageFailure(
                    "CompletionCoverage requires a durable evidence path"
                )
            candidate_ids = tuple(input.candidate_gpu_ids)
            eligible_ids = tuple(input.eligible_gpu_ids)
            reserved_ids = tuple(input.reserved_gpu_ids)
            selected_ids = tuple(input.selected_gpu_ids)
            occupied_process_ids = tuple(
                record.get("gpu_uuid") for record in input.occupied_gpu_ids
            )
            occupied_records_valid = all(
                isinstance(record.get("pid"), int)
                and cast(int, record.get("pid")) > 0
                and isinstance(record.get("process_start_identity"), str)
                and bool(record.get("process_start_identity"))
                and isinstance(record.get("gpu_uuid"), str)
                and bool(record.get("gpu_uuid"))
                and isinstance(record.get("observation_timestamp"), str)
                and bool(record.get("observation_timestamp"))
                and isinstance(record.get("observation_fingerprint"), str)
                and bool(record.get("observation_fingerprint"))
                for record in input.occupied_gpu_ids
            )
            if (
                len(set(candidate_ids)) != len(candidate_ids)
                or len(set(eligible_ids)) != len(eligible_ids)
                or len(set(reserved_ids)) != len(reserved_ids)
                or len(set(selected_ids)) != len(selected_ids)
                or not set(eligible_ids).issubset(candidate_ids)
                or not set(selected_ids).issubset(eligible_ids)
                or tuple(candidate_ids) != tuple(sorted(candidate_ids))
                or tuple(eligible_ids) != tuple(sorted(eligible_ids))
                or tuple(reserved_ids) != tuple(sorted(reserved_ids))
                or tuple(selected_ids) != tuple(sorted(selected_ids))
                or any(_is_gpu_index(uuid) for uuid in candidate_ids)
                or not occupied_records_valid
                or tuple(input.lock_readback.get("final_eligible_ids", eligible_ids))
                != eligible_ids
                or set(eligible_ids).intersection(reserved_ids)
                or set(eligible_ids).intersection(occupied_process_ids)
            ):
                raise CompletionCoverageFailure(
                    "CompletionCoverage GPU candidate/eligible/selected set is invalid"
                )
            terminal_record_ids = tuple(
                cast(str, record.get("chunk_id"))
                for record in input.terminal_chunk_records
                if record.get("terminal") is True
                and isinstance(record.get("chunk_id"), str)
            )
            all_planned_chunks_complete = (
                len(set(input.planned_chunk_ids)) == len(input.planned_chunk_ids)
                and len(terminal_record_ids) == len(input.terminal_chunk_records)
                and len(set(terminal_record_ids)) == len(terminal_record_ids)
                and tuple(sorted(terminal_record_ids))
                == tuple(sorted(input.planned_chunk_ids))
                and tuple(sorted(input.terminal_chunk_ids))
                == tuple(sorted(terminal_record_ids))
            )
            validation_history_complete = all(
                _validation_failure_has_resolved_taxonomy_outcome(failure)
                for failure in input.validation_failures
            )
            taxonomy_summary = input.taxonomy_linked_validation_outcome
            taxonomy_owner_values_valid = (
                taxonomy_summary.get("taxonomy_owner") == VALIDATION_TAXONOMY_REF
                and taxonomy_summary.get("taxonomy_reader_projection")
                == VALIDATION_TAXONOMY_READER_REF
            )
            taxonomy_summary_valid = taxonomy_owner_values_valid and (
                (
                    bool(input.validation_failures)
                    and _validation_failure_has_resolved_taxonomy_outcome(
                        taxonomy_summary
                    )
                )
                or (
                    not input.validation_failures
                    and taxonomy_summary.get("status") == "no_validation_failure"
                )
            )
            if not taxonomy_summary_valid or not validation_history_complete:
                raise CompletionCoverageFailure(
                    "validation history must use the owner-defined taxonomy fields and intent route"
                )
            validation_history_complete = (
                validation_history_complete and taxonomy_summary_valid
            )
            required_evidence_present = bool(input.required_evidence) and all(
                input.required_evidence.get(name) is True
                for name in ("terminal", "partial", "cleanup", "closeout_intent")
            ) and (
                input.required_evidence.get("terminal_records_complete") is True
                or input.required_evidence.get("explicit_partial_evidence") is True
            ) and all(
                _durable_dual_evidence_witness(
                    input.required_evidence.get(name)
                )
                for name in (
                    "terminal_ref",
                    "partial_ref",
                    "cleanup_ref",
                    "closeout_intent_ref",
                )
            )
            closeout_artifact_refs_present = all(
                input.required_evidence.get(name) not in (None, "", (), {})
                for name in (
                    "design_artifact",
                    "implementation_artifact",
                    "implementation_review_artifact",
                    "validation_artifacts",
                )
            )
            overall_delivery_complete = (
                all_planned_chunks_complete
                and required_evidence_present
                and closeout_artifact_refs_present
                and input.effective_env_certificate_matches
                and not input.cleanup_has_unresolved_leak_or_unknown
                and input.required_review_gates_passed
                and not input.unresolved_design_issue_blockers
                and not input.unresolved_validation_failures
                and validation_history_complete
            )
            unresolved_blockers = (
                tuple(input.unresolved_design_issue_blockers)
                + tuple(
                    f"validation_failure:{index}"
                    for index, _failure in enumerate(input.unresolved_validation_failures)
                )
                + (("cleanup_unresolved_leak_or_unknown",)
                   if input.cleanup_has_unresolved_leak_or_unknown else ())
                + (("validation_history_incomplete",)
                   if not validation_history_complete else ())
                + (("required_evidence_missing",)
                   if not required_evidence_present else ())
                + (("closeout_artifact_refs_missing",)
                   if not closeout_artifact_refs_present else ())
                + (("effective_environment_certificate_mismatch",)
                   if not input.effective_env_certificate_matches else ())
                + (("review_gate_unresolved",)
                   if not input.required_review_gates_passed else ())
            )
            recorded_at = utc_now()
            payload = {
                "schema_version": COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
                "plan_fingerprint": input.plan_fingerprint,
                "terminal_event_id": input.terminal_event_id,
                "delivery_ordinal": 1,
                "input": _completion_input_record(input),
                "recorded_at": recorded_at,
                "all_planned_chunks_complete": all_planned_chunks_complete,
                "overall_delivery_complete": overall_delivery_complete,
                "unresolved_blockers": unresolved_blockers,
            }
            try:
                persistence_witness = _write_json_once(
                    self.evidence_path,
                    payload,
                    allow_identical=False,
                )
            except ResourcePlanError as exc:
                raise CompletionCoverageFailure(
                    "duplicate or conflicting durable CompletionCoverage delivery"
                ) from exc
            record = CompletionCoverage(
                schema_version=COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
                plan_fingerprint=input.plan_fingerprint,
                terminal_event_id=input.terminal_event_id,
                delivery_ordinal=1,
                input_record=input,
                recorded_at=recorded_at,
                all_planned_chunks_complete=all_planned_chunks_complete,
                overall_delivery_complete=overall_delivery_complete,
                unresolved_blockers=unresolved_blockers,
                persistence_witness=persistence_witness,
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


class PostToolUseProjectionReducer:
    """Produce the exact nine-key projection; the Hook only validates it."""

    def project(self, outcome: ManagedGpuOutcome, coverage: CompletionCoverage) -> bytes:
        plan_fingerprint = outcome.plan_fingerprint or hashlib.sha256(
            outcome.outcome_fingerprint.encode("utf-8")
        ).hexdigest()
        exact_input = cast(CompletionCoverageInput, coverage.input_record)
        admission_source = exact_input.container_visible_uuid_mapping
        selected = tuple(exact_input.selected_uuids)
        admission = None
        if outcome.admission_fingerprint is not None:
            if not isinstance(admission_source, UuidVisibilityEvidence):
                raise CompletionCoverageFailure(
                    "GPU projection requires typed UUID visibility and runtime identity evidence"
                )
            if not admission_source.namespace_id or not admission_source.provision_receipt_fingerprint:
                raise CompletionCoverageFailure(
                    "GPU projection requires non-empty runtime namespace and provision fingerprints"
                )
            admission = {
                "admission_fingerprint": outcome.admission_fingerprint,
                "guarantee": "run-level-opaque-uuid-admission",
                "namespace_id": admission_source.namespace_id,
                "provision_receipt_fingerprint": admission_source.provision_receipt_fingerprint,
                "selected_uuids": selected,
            }
        error = None
        if outcome.primary_failure is not None:
            error = {
                "kind": outcome.primary_failure.kind,
                "message": outcome.primary_failure.message,
                "operation": outcome.primary_failure.operation,
            }
        projection = {
            "admission": admission,
            "completion_coverage_path": (
                f"reports/agents/{outcome.run_id}/runtime/completion_coverage.json"
            ),
            "error": error,
            "exit_code": outcome.exit_code,
            "plan_fingerprint": plan_fingerprint,
            "plan_path": f"reports/agents/{outcome.run_id}/runtime/execution_resource_plan.json",
            "projection": "post_tool_use",
            "run_id": outcome.run_id,
            "schema_version": "execution-resource-plan/v1",
        }
        return (_canonical_json(projection) + "\n").encode("utf-8")


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
            "parent_pid": value.parent_pid,
            "relationship": value.relationship,
            "container_namespace_identity": value.container_namespace_identity,
        }
    if isinstance(value, GPUDevice):
        return {
            "uuid": value.uuid,
            "free_memory_bytes": value.free_memory_bytes,
            "memory_bytes": value.memory_bytes,
            "mig_parent_uuid": value.mig_parent_uuid,
        }
    raise TypeError(f"value is not JSON serializable: {type(value)!r}")


def _process_record(process: ProcessIdentity) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "pid": process.pid,
            "process_start_identity": process.process_start_identity,
            "gpu_uuid": process.gpu_uuid,
            "kind": process.kind,
            "parent_pid": process.parent_pid,
            "relationship": process.relationship,
            "observation_timestamp": process.observation_timestamp,
            "observation_fingerprint": process.observation_fingerprint,
            "container_namespace_identity": process.container_namespace_identity,
        }
    )


def _execution_result_record(result: object | None) -> Mapping[str, object] | None:
    if result is None:
        return None
    if isinstance(result, Mapping):
        return _freeze_mapping(cast(Mapping[str, object], result))
    fields = (
        "status",
        "failure_kind",
        "message",
        "raw_exit_code",
        "signal_name",
        "stdout",
        "stderr",
        "traceback",
        "source",
    )
    record = {
        field_name: getattr(result, field_name)
        for field_name in fields
        if hasattr(result, field_name)
    }
    if not record:
        raise ResourcePlanError(
            "ExecutionResult must expose the canonical diagnostic fields"
        )
    return _freeze_mapping(record)


def _validation_failure_has_resolved_taxonomy_outcome(
    failure: Mapping[str, object],
) -> bool:
    required_fields = (
        "failing_contract",
        "observation_level",
        "cause_classification",
        "intent_preservation",
        "evidence",
    )
    owner_cause_classes = {
        "implementation_bug",
        "test_oracle_spec_mismatch",
        "fixture_environment_issue",
        "stale_generated_artifact",
        "pre_existing_unrelated_failure",
        "approved_design_user_request_conflict",
    }
    owner_intent_routes = {
        "repair_same_intent",
        "redesign_same_intent",
        "escalate_design_conflict",
    }
    return (
        all(failure.get(field) not in (None, "", (), {}) for field in required_fields)
        and failure.get("taxonomy_owner") == VALIDATION_TAXONOMY_REF
        and failure.get("taxonomy_reader_projection")
        == VALIDATION_TAXONOMY_READER_REF
        and failure.get("cause_classification") in owner_cause_classes
        and failure.get("intent_preservation") in owner_intent_routes
    )


def _durable_dual_evidence_witness(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    for location in ("runtime", "projection"):
        witness = value.get(location)
        if not isinstance(witness, Mapping):
            return False
        if (
            not isinstance(witness.get("path"), str)
            or not isinstance(witness.get("sha256"), str)
            or not isinstance(witness.get("bytes"), int)
            or witness.get("disposition") not in {"created", "existing_identical"}
        ):
            return False
        path = Path(cast(str, witness["path"]))
        try:
            encoded = path.read_bytes()
        except OSError:
            return False
        if (
            len(encoded) != witness["bytes"]
            or hashlib.sha256(encoded).hexdigest() != witness["sha256"]
        ):
            return False
    return True


def _completion_input_record(
    input: _LegacyPlannerCoverageRecord,
) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "schema_version": input.schema_version,
            "plan_fingerprint": input.plan_fingerprint,
            "terminal_event_id": input.terminal_event_id,
            "candidate_gpu_ids": input.candidate_gpu_ids,
            "occupied_gpu_ids": input.occupied_gpu_ids,
            "reserved_gpu_ids": input.reserved_gpu_ids,
            "eligible_gpu_ids": input.eligible_gpu_ids,
            "selected_gpu_ids": input.selected_gpu_ids,
            "lock_readback": input.lock_readback,
            "effective_env": input.effective_env,
            "actual_gpu_processes": input.actual_gpu_processes,
            "release_retention_disposition": input.release_retention_disposition,
            "concurrent_run_evidence": input.concurrent_run_evidence,
            "mig_evidence": input.mig_evidence,
            "container_visible_uuid_mapping": input.container_visible_uuid_mapping,
            "os_safe_lock_placement": input.os_safe_lock_placement,
            "descendant_retention_evidence": input.descendant_retention_evidence,
            "taxonomy_linked_validation_outcome": input.taxonomy_linked_validation_outcome,
            "planned_chunk_ids": input.planned_chunk_ids,
            "terminal_chunk_ids": input.terminal_chunk_ids,
            "terminal_chunk_records": input.terminal_chunk_records,
            "required_evidence": input.required_evidence,
            "effective_env_certificate_matches": input.effective_env_certificate_matches,
            "cleanup_has_unresolved_leak_or_unknown": input.cleanup_has_unresolved_leak_or_unknown,
            "required_review_gates_passed": input.required_review_gates_passed,
            "validation_failures": input.validation_failures,
            "unresolved_design_issue_blockers": input.unresolved_design_issue_blockers,
            "unresolved_validation_failures": input.unresolved_validation_failures,
        }
    )


def _persist_runtime_and_projection_once(
    plan: ExecutionResourcePlan,
    filename: str,
    payload: Mapping[str, object],
    *,
    allow_identical: bool = False,
) -> Mapping[str, object]:
    run_root = Path(cast(str, plan.resources["temp"]["run_root"]))
    projection_root = Path(cast(str, plan.container["source_projection_root"]))
    runtime_witness = _write_json_once(
        run_root / filename,
        payload,
        allow_identical=allow_identical,
    )
    projection_witness = _write_json_once(
        projection_root / filename,
        payload,
        allow_identical=allow_identical,
    )
    return MappingProxyType(
        {
            "runtime": runtime_witness,
            "projection": projection_witness,
        }
    )


def _pre_execution_failure_roots(
    *,
    request: ResourceRequest | None,
    plan: ExecutionResourcePlan | None,
    transaction_id: str,
) -> tuple[Path, Path]:
    if plan is not None:
        return (
            Path(cast(str, plan.resources["temp"]["run_root"])),
            Path(cast(str, plan.container["source_projection_root"])),
        )
    if request is None:
        raise PlanStateError("pre-execution failure requires request or plan roots")
    return (
        request.runtime_root / "runs" / transaction_id,
        cast(Path, request.source_projection_root),
    )


def _persist_pre_execution_failure_record(
    runtime_root: Path,
    projection_root: Path,
    filename: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "runtime": _write_json_once(
                runtime_root / filename,
                payload,
                allow_identical=False,
            ),
            "projection": _write_json_once(
                projection_root / filename,
                payload,
                allow_identical=False,
            ),
        }
    )


def _dispose_pre_execution_leases(
    leases: Sequence[ReservationLease],
    observation_probe: Callable[[], ResourceObservation] | None,
) -> tuple[tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...]]:
    dispositions: list[Mapping[str, object]] = []
    leaks: list[Mapping[str, object]] = []
    for lease in leases:
        if observation_probe is None:
            disposition: Mapping[str, object] = {
                "uuid": lease.uuid,
                "reservation_id": lease.reservation_id,
                "result": "retained_missing_process_probe",
                "force_kill": False,
            }
        else:
            try:
                disposition = _release_lease_with_observation(
                    lease,
                    observation_probe,
                )
            except Exception as exc:
                disposition = {
                    "uuid": lease.uuid,
                    "reservation_id": lease.reservation_id,
                    "result": "release_failed",
                    "failure_type": type(exc).__name__,
                    "failure_message": str(exc),
                    "force_kill": False,
                }
        dispositions.append(disposition)
        if disposition.get("result") not in {"released", "already_released"}:
            leaks.append(disposition)
    return tuple(dispositions), tuple(leaks)


def handle_pre_execution_failure(
    failure: Exception,
    *,
    failed_operation: str,
    source_state: PlanState,
    request: ResourceRequest | None = None,
    plan: ExecutionResourcePlan | None = None,
    discovered: DiscoveredResources | None = None,
    acquired_leases: Sequence[ReservationLease] = (),
) -> PreExecutionFailureCleanupEvidence:
    """Persist a terminal failure edge and race-safe cleanup without fallback."""
    if source_state not in STATE_SEQUENCE[:4]:
        raise PlanStateError("pre-execution failure source must precede execute")
    if plan is not None:
        transaction_id = plan.plan_id
    elif request is not None:
        transaction_id = (
            request.plan_id
            or request.run_id
            or f"preflight-{secrets.token_hex(12)}"
        )
    else:
        raise PlanStateError("pre-execution failure without plan requires request")
    if plan is not None:
        if plan.state != source_state:
            raise PlanStateError("pre-execution failure source does not match plan state")
        transaction_fingerprint = plan.plan_fingerprint
        source_history = plan.state_history
    else:
        if request is None:
            raise PlanStateError("pre-execution failure without plan requires request")
        failure_spec = {
            "schema_version": "pre-execution-failure-transaction/v1",
            "transaction_id": transaction_id,
            "owner": {
                "owner_id": request.owner_id,
                "parent_id": request.parent_id,
                "context_id": request.context_id,
            },
            "request": {
                "cwd": str(request.cwd),
                "argv": request.argv,
                "cpu_requested_set": request.cpu_requested_set,
                "gpu_requested_count": request.gpu_requested_count,
                "gpu_requested_memory_bytes": request.gpu_requested_memory_bytes,
                "managed_run_integration": request.integration_contract.record(),
            },
        }
        transaction_fingerprint = hashlib.sha256(
            _canonical_json(_json_safe(failure_spec)).encode("utf-8")
        ).hexdigest()
        source_history = (source_state,)
    terminal_event_id = f"pre-execution-terminal-{secrets.token_hex(12)}"
    failure_code = (
        failure.code
        if isinstance(failure, TypedPreflightFailure)
        else f"{failed_operation}_failed"
    )
    failure_evidence = (
        dict(failure.evidence)
        if isinstance(failure, TypedPreflightFailure)
        else {"failure_type": type(failure).__name__}
    )
    runtime_root, projection_root = _pre_execution_failure_roots(
        request=request,
        plan=plan,
        transaction_id=transaction_id,
    )
    leases_by_reservation = {
        lease.reservation_id: lease
        for lease in (
            *acquired_leases,
            *(plan.gpu_allocation.leases if plan is not None else ()),
        )
    }
    if plan is not None:
        observation_probe: Callable[[], ResourceObservation] | None = (
            plan.resource_probe.observe
        )
    elif discovered is not None:
        observation_probe = discovered.probe.observe
    elif request is not None and isinstance(request.resource_probe, NvidiaSMIResourceProbe):
        observation_probe = request.resource_probe.observe
    else:
        observation_probe = None
    partial_payload = {
        "schema_version": "partial-evidence/v1",
        "plan_fingerprint": transaction_fingerprint,
        "terminal_event_id": terminal_event_id,
        "last_exact_state": source_state,
        "disposition": "explicit_pre_execution_partial_not_completion",
        "stop_reason": failure_code,
        "failed_operation": failed_operation,
        "failure_evidence": failure_evidence,
        "partial_is_completion": False,
        "fallback_attempted": False,
    }
    terminal_history = (*source_history, PlanState.TERMINAL)
    try:
        partial_witness = _persist_pre_execution_failure_record(
            runtime_root,
            projection_root,
            PARTIAL_EVIDENCE_FILENAME,
            partial_payload,
        )
        terminal_payload = {
            "schema_version": "terminal-evidence/v1",
            "plan_fingerprint": transaction_fingerprint,
            "terminal_event_id": terminal_event_id,
            "failed_operation": failed_operation,
            "failure_code": failure_code,
            "failure_message": str(failure),
            "failure_evidence": failure_evidence,
            "state_history": terminal_history,
            "partial_evidence": partial_witness,
            "fallback_attempted": False,
            "terminal_timestamp": utc_now(),
        }
        terminal_witness = _persist_pre_execution_failure_record(
            runtime_root,
            projection_root,
            TERMINAL_EVIDENCE_FILENAME,
            terminal_payload,
        )
    except Exception as persistence_failure:
        lease_dispositions, leaks = _dispose_pre_execution_leases(
            tuple(leases_by_reservation.values()),
            observation_probe,
        )
        raise TypedPreflightFailure(
            "pre_execution_failure_evidence_persistence_failed",
            "pre-execution evidence persistence failed after race-safe lease cleanup",
            original_failure_code=failure_code,
            failed_operation=failed_operation,
            lease_dispositions=lease_dispositions,
            leak_or_unknown=leaks,
            fallback_attempted=False,
        ) from persistence_failure
    terminal = PreExecutionFailureTerminalEvidence(
        transaction_fingerprint=transaction_fingerprint,
        failed_operation=failed_operation,
        failure_code=failure_code,
        failure_message=str(failure),
        failure_evidence=failure_evidence,
        state_history=terminal_history,
        persistence_witness={
            "terminal": terminal_witness,
            "partial": partial_witness,
        },
        terminal_event_id=terminal_event_id,
    )
    lease_dispositions, leaks = _dispose_pre_execution_leases(
        tuple(leases_by_reservation.values()),
        observation_probe,
    )
    cleanup_history = (*terminal_history, PlanState.CLEANUP_DISPOSED)
    cleanup_payload = {
        "schema_version": "cleanup-evidence/v1",
        "plan_fingerprint": transaction_fingerprint,
        "terminal_event_id": terminal_event_id,
        "failed_operation": failed_operation,
        "state_history": cleanup_history,
        "lease_dispositions": tuple(lease_dispositions),
        "leak_or_unknown": tuple(leaks),
        "fallback_attempted": False,
        "force_kill": False,
        "disposed_at": utc_now(),
    }
    cleanup_witness = _persist_pre_execution_failure_record(
        runtime_root,
        projection_root,
        CLEANUP_EVIDENCE_FILENAME,
        cleanup_payload,
    )
    persistence: dict[str, object] = {"cleanup": cleanup_witness}
    if plan is not None:
        completion_path = projection_root / COMPLETION_COVERAGE_FILENAME
        closeout_intent_witness = _persist_pre_execution_failure_record(
            runtime_root,
            projection_root,
            CLOSEOUT_INTENT_FILENAME,
            {
                "schema_version": "closeout-intent/v1",
                "plan_fingerprint": transaction_fingerprint,
                "terminal_event_id": terminal_event_id,
                "terminal_evidence": terminal_witness,
                "partial_evidence": partial_witness,
                "cleanup_evidence": cleanup_witness,
                "completion_coverage_path": str(completion_path),
                "next_owner": "CompletionCoverage",
            },
        )
        allocation = plan.gpu_allocation
        required_evidence = {
            "terminal": True,
            "partial": True,
            "cleanup": True,
            "closeout_intent": True,
            "terminal_records_complete": False,
            "explicit_partial_evidence": True,
            "terminal_ref": terminal_witness,
            "partial_ref": partial_witness,
            "cleanup_ref": cleanup_witness,
            "closeout_intent_ref": closeout_intent_witness,
            "design_artifact": DESIGN_AUTHORITY_ARTIFACT,
            "design_manager_artifact": DESIGN_MANAGER_ARTIFACT,
            "design_review_authority_artifact": DESIGN_REVIEW_AUTHORITY_ARTIFACT,
            "approved_design_brief_sha256": APPROVED_DESIGN_BRIEF_SHA256,
            "approved_design_partition_sha256": APPROVED_DESIGN_PARTITION_SHA256,
            "organizer_conclusion_prior_hash": "none",
            "organizer_conclusion_hash_assigned": False,
            "implementation_artifact": "tools/experiments/execution_resource_plan.py",
            "implementation_review_artifact": (
                "reports/agents/w1-tool-env-routing-20260716/implementation_review.md"
            ),
            "validation_artifacts": "pre_execution_failure_evidence_only",
        }
        failure_coverage_input = _LegacyPlannerCoverageRecord(
            schema_version=COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
            plan_fingerprint=transaction_fingerprint,
            terminal_event_id=terminal_event_id,
            candidate_gpu_ids=allocation.candidate_ids,
            occupied_gpu_ids=tuple(
                _process_record(process)
                for process in allocation.occupied_process_identities
            ),
            reserved_gpu_ids=allocation.reserved_ids,
            selected_gpu_ids=allocation.selected_ids,
            lock_readback=allocation.lock_readback,
            effective_env=cast(
                Mapping[str, object],
                plan.readback.get("effective_environment", {}),
            ),
            actual_gpu_processes=tuple(
                _process_record(process)
                for process in plan.resource_probe.observe().process_identities
            ),
            release_retention_disposition={
                "lease_dispositions": tuple(lease_dispositions),
            },
            concurrent_run_evidence={
                "planner_lock_attempts": allocation.lock_readback.get("attempts", ()),
            },
            mig_evidence={
                "candidate_mig_mapping": plan.resources["gpu"].get("mig_mapping", {}),
            },
            container_visible_uuid_mapping={
                "selected_ids": allocation.selected_ids,
                "effective_visible_ids": plan.readback.get(
                    "effective_environment", {}
                ).get("visible_gpu_ids", ()),
            },
            os_safe_lock_placement={
                "lock_root": str(allocation.lock_root),
                "shared_across_schedulers": allocation.lock_readback.get(
                    "shared_across_schedulers"
                ),
                "host_safe": allocation.lock_readback.get("host_safe"),
                "visibility_witness": allocation.lock_readback.get(
                    "visibility_witness"
                ),
            },
            descendant_retention_evidence={
                "lease_dispositions": tuple(lease_dispositions),
                "force_kill": False,
            },
            taxonomy_linked_validation_outcome={
                "taxonomy_owner": VALIDATION_TAXONOMY_REF,
                "taxonomy_reader_projection": VALIDATION_TAXONOMY_READER_REF,
                "status": "no_validation_failure",
            },
            eligible_gpu_ids=allocation.eligible_ids,
            planned_chunk_ids=tuple(
                cast(Sequence[str], plan.execution.get("requested_chunks", ()))
            ),
            terminal_chunk_ids=(),
            terminal_chunk_records=(),
            required_evidence=required_evidence,
            effective_env_certificate_matches=False,
            cleanup_has_unresolved_leak_or_unknown=bool(leaks),
            required_review_gates_passed=False,
            unresolved_design_issue_blockers=(
                f"pre_execution_failure:{failure_code}",
            ),
        )
        completion_coverage = CompletionCoverageAdapter(
            evidence_path=completion_path
        )._historical_planner_closeout_rejected(failure_coverage_input)
        closeout_witness = _persist_pre_execution_failure_record(
            runtime_root,
            projection_root,
            CLOSEOUT_EVIDENCE_FILENAME,
            {
                "schema_version": "closeout-evidence/v1",
                "plan_fingerprint": transaction_fingerprint,
                "terminal_event_id": terminal_event_id,
                "terminal_evidence": terminal_witness,
                "partial_evidence": partial_witness,
                "cleanup_evidence": cleanup_witness,
                "closeout_intent": closeout_intent_witness,
                "completion_coverage": completion_coverage.persistence_witness,
                "completion_claim_status": (
                    "persisted_exactly_once_before_final_closeout"
                ),
                "all_planned_chunks_complete": (
                    completion_coverage.all_planned_chunks_complete
                ),
                "overall_delivery_complete": (
                    completion_coverage.overall_delivery_complete
                ),
                "unresolved_blockers": completion_coverage.unresolved_blockers,
                "next_owner": "CompletionCoverage",
            },
        )
        persistence.update(
            {
                "closeout_intent": closeout_intent_witness,
                "closeout": closeout_witness,
                "completion_coverage": completion_coverage.persistence_witness,
            }
        )
    return PreExecutionFailureCleanupEvidence(
        terminal=terminal,
        lease_dispositions=tuple(lease_dispositions),
        leak_or_unknown=tuple(leaks),
        persistence_witness=persistence,
        state_history=cleanup_history,
    )


def failure_after_durable_cleanup(
    failure: Exception,
    cleanup: PreExecutionFailureCleanupEvidence,
) -> TypedPreflightFailure:
    code = failure.code if isinstance(failure, TypedPreflightFailure) else cleanup.terminal.failure_code
    return TypedPreflightFailure(
        code,
        str(failure),
        original_evidence=(
            dict(failure.evidence)
            if isinstance(failure, TypedPreflightFailure)
            else {"failure_type": type(failure).__name__}
        ),
        pre_execution_terminal=cleanup.terminal.persistence_witness,
        pre_execution_cleanup=cleanup.persistence_witness,
        state_history=cleanup.state_history,
        fallback_attempted=False,
    )


def _transition_plan(
    plan: ExecutionResourcePlan,
    expected: PlanState,
    next_state: PlanState,
    *,
    readback: Mapping[str, object] | None = None,
    evidence: Mapping[str, object] | None = None,
) -> ExecutionResourcePlan:
    _require_state(plan, expected)
    expected_index = STATE_SEQUENCE.index(expected)
    if expected_index + 1 >= len(STATE_SEQUENCE) or STATE_SEQUENCE[expected_index + 1] != next_state:
        raise PlanStateError(f"invalid transition {expected} -> {next_state}")
    next_readback = dict(plan.readback)
    if readback:
        next_readback.update(readback)
    next_evidence = dict(plan.evidence)
    if evidence:
        next_evidence.update(evidence)
    return replace(
        plan,
        readback=next_readback,
        evidence=next_evidence,
        state=next_state,
        state_history=(*plan.state_history, next_state),
    )


def _process_start_identity(pid: int) -> str:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return "dead"
    except OSError:
        return "unknown"
    fields = stat.rsplit(")", 1)[-1].split()
    return fields[19] if len(fields) > 19 else "unknown"


def discover_resources(request: ResourceRequest) -> DiscoveredResources:
    """Capture the declared capability boundary before the plan is frozen."""
    try:
        return _discover_resources_impl(request)
    except Exception as exc:
        cleanup = handle_pre_execution_failure(
            exc,
            failed_operation="resource_discovery",
            source_state=PlanState.RESOURCE_DISCOVERED,
            request=request,
        )
        raise failure_after_durable_cleanup(exc, cleanup) from exc


def _discover_resources_impl(request: ResourceRequest) -> DiscoveredResources:
    if request.resource_probe is None:
        probe: ResourceProbe = NvidiaSMIResourceProbe.discover(
            request.environment,
            gpu_requested_count=request.gpu_requested_count,
            runtime_root=request.runtime_root,
        )
    elif not isinstance(request.resource_probe, NvidiaSMIResourceProbe):
        raise TypedPreflightFailure(
            "noncanonical_resource_probe",
            "public production discovery requires NvidiaSMIResourceProbe",
            observed_probe=type(request.resource_probe).__name__,
        )
    else:
        probe = request.resource_probe
    observation = probe.observe()
    if request.gpu_requested_count:
        structured_probe = observation.tool_availability.get("nvidia-smi")
        if not isinstance(structured_probe, Mapping) or structured_probe.get(
            "structured"
        ) is not True:
            raise TypedPreflightFailure(
                "gpu_structured_readback_capability_unproven",
                "GPU execution requires NVIDIA runtime-projected structured probe capability",
                tool_capability=structured_probe,
            )
        visibility = structured_probe.get("process_inventory_visibility")
        visible_units = (
            visibility.get("allocated_ids")
            if isinstance(visibility, Mapping)
            else None
        )
        if (
            not isinstance(visibility, Mapping)
            or visibility.get("all_allocated_units_visible") is not True
            or tuple(visible_units or ())
            != tuple(sorted(observation.caller_allocated_ids))
        ):
            raise TypedPreflightFailure(
                "gpu_process_identity_unproven",
                "GPU execution requires an explicit process-table visibility witness for every allocated UUID/MIG UUID",
                allocated_ids=tuple(sorted(observation.caller_allocated_ids)),
                process_inventory_visibility=visibility,
            )
    return _discover_resources_from_probe_impl(
        request,
        probe,
        observation,
        cpu_available_set=observation.cpu_available_set,
        gpu_devices=observation.gpu_devices,
        reserved_ids=request.discovered_reserved_ids,
        host_memory_bytes=observation.host_memory_bytes,
        temp_bytes=observation.temp_bytes,
        ports=request.discovered_ports,
        container_id=observation.container_id,
        structure_tool=observation.structure_tool,
        tool_availability=observation.tool_availability,
    )


def _discover_resources_from_probe_impl(
    request: ResourceRequest,
    probe: ResourceProbe,
    observation: ResourceObservation,
    *,
    cpu_available_set: Sequence[int] = (),
    gpu_devices: Sequence[GPUDevice] = (),
    reserved_ids: frozenset[str] = frozenset(),
    host_memory_bytes: int = 0,
    temp_bytes: int = 0,
    ports: Sequence[Mapping[str, object]] = (),
    container_id: str = "",
    structure_tool: Mapping[str, str] | None = None,
    tool_availability: Mapping[str, object] | None = None,
) -> DiscoveredResources:
    """Materialize one explicit discovery snapshot without fallback probing."""
    if request.gpu_requested_count and (
        not request.lock_namespace_shared_across_schedulers
        or not request.lock_namespace_host_safe
        or not request.lock_namespace_visibility_witness
    ):
        raise TypedPreflightFailure(
            "gpu_lock_namespace_unproved",
            "GPU planning requires a declared host-safe shared lock namespace",
            lock_root=str(request.lock_root),
            shared_across_schedulers=request.lock_namespace_shared_across_schedulers,
            host_safe=request.lock_namespace_host_safe,
            visibility_witness=request.lock_namespace_visibility_witness,
        )
    return DiscoveredResources(
        cpu_available_set=tuple(sorted(cpu_available_set)),
        gpu_devices=tuple(sorted(gpu_devices, key=lambda device: device.uuid)),
        caller_allocated_ids=observation.caller_allocated_ids,
        occupied_processes=observation.process_identities,
        reserved_ids=frozenset(reserved_ids),
        host_memory_bytes=host_memory_bytes,
        temp_bytes=temp_bytes,
        ports=tuple(ports),
        container_id=container_id,
        structure_tool=MappingProxyType(dict(structure_tool or {})),
        boot_id=observation.boot_id,
        probe=probe,
        observation=observation,
        reservation_store=(
            None
            if isinstance(probe, NvidiaSMIResourceProbe)
            else UUIDReservationStore(
                request.lock_root,
                shared_across_schedulers=(
                    request.lock_namespace_shared_across_schedulers
                    or not request.gpu_requested_count
                ),
                host_safe=request.lock_namespace_host_safe or not request.gpu_requested_count,
                visibility_witness=(
                    request.lock_namespace_visibility_witness
                    or "not-applicable-no-gpu"
                    if not request.gpu_requested_count
                    else request.lock_namespace_visibility_witness
                ),
            )
        ),
        tool_availability=MappingProxyType(dict(tool_availability or {})),
        allocation_provenance=request.gpu_allocation_provenance,
        observed_at=observation.observed_at,
        observation_fingerprint=observation.fingerprint,
    )


def _gpu_preflight(code: str, message: str, **evidence: object) -> TypedPreflightFailure:
    return TypedPreflightFailure(code, message, **evidence)


def _occupied_gpu_units(
    processes: Sequence[ProcessIdentity],
    devices: Sequence[GPUDevice],
    candidate_ids: Sequence[str],
) -> tuple[str, ...]:
    """Conservatively map physical/MIG process contexts to eligible units."""
    parent_by_uuid = {
        device.uuid: device.mig_parent_uuid
        for device in devices
        if device.mig_parent_uuid is not None
    }
    children_by_parent: dict[str, set[str]] = {}
    for child, parent in parent_by_uuid.items():
        children_by_parent.setdefault(parent, set()).add(child)
    occupied: set[str] = set()
    candidate_set = set(candidate_ids)
    for process in processes:
        occupied.add(process.gpu_uuid)
        parent = parent_by_uuid.get(process.gpu_uuid)
        if parent:
            occupied.add(parent)
        if process.gpu_uuid in children_by_parent:
            occupied.update(children_by_parent[process.gpu_uuid])
    return tuple(sorted(occupied.intersection(candidate_set)))


def _release_lease_with_observation(
    lease: ReservationLease,
    observation_supplier: Callable[[], ResourceObservation],
) -> Mapping[str, object]:
    """Release against one coherent live-holder observation and frozen mapping."""
    return lease.release(observation_supplier=observation_supplier)


def plan_gpu_allocation(
    request: ResourceRequest,
    discovered: DiscoveredResources,
) -> GPUAllocation:
    """Run the sole planner and durably terminalize every preflight failure."""
    try:
        return _plan_gpu_allocation_impl(request, discovered)
    except _PlannerAttemptFailure as attempt:
        cleanup = handle_pre_execution_failure(
            attempt.cause,
            failed_operation="gpu_preflight",
            source_state=PlanState.RESOURCE_DISCOVERED,
            request=request,
            discovered=discovered,
            acquired_leases=attempt.leases,
        )
        raise failure_after_durable_cleanup(attempt.cause, cleanup) from attempt.cause
    except Exception as exc:
        cleanup = handle_pre_execution_failure(
            exc,
            failed_operation="gpu_preflight",
            source_state=PlanState.RESOURCE_DISCOVERED,
            request=request,
            discovered=discovered,
        )
        raise failure_after_durable_cleanup(exc, cleanup) from exc


def _plan_gpu_allocation_impl(
    request: ResourceRequest,
    discovered: DiscoveredResources,
) -> GPUAllocation:
    """Select and reserve only eligible caller-allocated UUIDs.

    The algorithm is intentionally stable and unweighted: A is the caller
    allocation, O_t is the live GPU process set, R_t is the reservation set,
    and E_t is the hard-memory-filtered remainder.  Every selected UUID is
    locked and reread before it is accepted.
    """
    if discovered.state != PlanState.RESOURCE_DISCOVERED:
        raise PlanStateError("GPU planning requires resource_discovered state")
    if discovered.reservation_store is None:
        raise TypedPreflightFailure(
            "legacy_gpu_planner_unavailable",
            "the legacy lease planner is not an admission route",
        )
    requested = request.gpu_requested_count
    provenance = discovered.allocation_provenance
    observation_s0 = discovered.observation
    observation_events = {observation_s0.observation_event_id}
    observation_fingerprints = {observation_s0.fingerprint}

    def fresh_observation(event: str) -> ResourceObservation:
        observation = discovered.probe.observe()
        if observation.observation_event_id in observation_events:
            raise _gpu_preflight(
                "gpu_observation_event_reused",
                "resource probe returned an observation event more than once",
                event=event,
                observation_event_id=observation.observation_event_id,
            )
        if not observation.fingerprint or observation.fingerprint in observation_fingerprints:
            raise _gpu_preflight(
                "gpu_observation_fingerprint_reused",
                "resource probe returned a repeated or empty observation fingerprint",
                event=event,
                observation_event_id=observation.observation_event_id,
                observation_fingerprint=observation.fingerprint,
            )
        observation_events.add(observation.observation_event_id)
        observation_fingerprints.add(observation.fingerprint)
        return observation
    if requested == 0:
        lock_readback = {
            "gpu_requested": False,
            "lock_root": str(request.lock_root),
            "attempts": (),
        }
        readback_fingerprint = hashlib.sha256(
            _canonical_json(_json_safe(lock_readback)).encode("utf-8")
        ).hexdigest()
        return _mark_canonical_planner_provenance(GPUAllocation(
            plan_fingerprint="pending",
            caller_allocated_ids=(),
            candidate_ids=(),
            occupied_ids=(),
            reserved_ids=(),
            eligible_ids=(),
            selected_ids=(),
            reservation_ids=(),
            free_memory_bytes={},
            occupied_process_identities=(),
            process_identities=(),
            allocation_id="none",
            lock_root=request.lock_root,
            selection_order=(),
            memory_bytes={},
            slot_id=None,
            requested_count=0,
            requested_memory_bytes=0,
            readback_fingerprint=readback_fingerprint,
            lock_readback=lock_readback,
            allocation_provenance=provenance or "not_applicable",
            leases=(),
        ))
    if provenance != CALLER_ALLOCATION_PROVENANCE:
        raise _gpu_preflight(
            "gpu_allocation_provenance_missing",
            "planner provenance is not the caller/scheduler allocated UUID set",
            required_provenance=CALLER_ALLOCATION_PROVENANCE,
            observed_provenance=provenance,
        )
    caller_ids = tuple(sorted(observation_s0.caller_allocated_ids))
    if any(_is_gpu_index(uuid) for uuid in caller_ids):
        raise _gpu_preflight(
            "gpu_uuid_required",
            "GPU allocation must use UUIDs rather than device indices",
            caller_allocated_ids=caller_ids,
        )
    if len(caller_ids) < requested:
        raise _gpu_preflight(
            "gpu_cardinality_unavailable",
            "caller allocation cannot satisfy requested GPU cardinality",
            requested_count=requested,
            caller_allocated_ids=caller_ids,
        )
    device_by_id = {device.uuid: device for device in observation_s0.gpu_devices}
    missing_device_ids = tuple(uuid for uuid in caller_ids if uuid not in device_by_id)
    if missing_device_ids:
        raise _gpu_preflight(
            "gpu_discovery_cardinality_incomplete",
            "every caller-allocated UUID requires a device capability record",
            caller_allocated_ids=caller_ids,
            missing_device_ids=missing_device_ids,
        )
    candidate_ids = caller_ids
    occupied_ids = _occupied_gpu_units(
        observation_s0.process_identities,
        observation_s0.gpu_devices,
        candidate_ids,
    )
    reserved_ids_seen = set(discovered.reserved_ids)
    reserved_ids = tuple(sorted(reserved_ids_seen))
    free_memory = dict(observation_s0.free_memory_bytes)
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
    reread_processes: tuple[ProcessIdentity, ...] = observation_s0.process_identities
    readback_attempts: list[Mapping[str, object]] = []
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
                boot_id=observation_s0.boot_id,
            )
            if lease is None:
                reclaim = discovered.reservation_store.reclaim_stale(
                    uuid,
                    observation_supplier=lambda: fresh_observation("stale_reclaim"),
                    process_start_identity=_process_start_identity,
                )
                if reclaim.reclaimed:
                    lease = discovered.reservation_store.acquire(
                        uuid,
                        owner_pid=os.getpid(),
                        owner_process_start_identity=(
                            request.owner_process_start_identity
                            if request.owner_process_start_identity != "unknown"
                            else _process_start_identity(os.getpid())
                        ),
                        boot_id=observation_s0.boot_id,
                    )
                if lease is None:
                    reserved_ids_seen.add(uuid)
                    readback_attempts.append(
                        {
                            "uuid": uuid,
                            "lock_acquired": False,
                            "result": "active_reservation_or_lock_race",
                            "stale_reclaim": {
                                "reclaimed": reclaim.reclaimed,
                                "prelock_proof": reclaim.prelock_proof,
                                "under_lock_proof": reclaim.under_lock_proof,
                                "persistence_witness": reclaim.persistence_witness,
                            },
                        }
                    )
                    continue
                readback_attempts.append(
                    {
                        "uuid": uuid,
                        "lock_acquired_after_stale_reclaim": True,
                        "stale_reclaim": {
                            "reclaimed": True,
                            "prelock_proof": reclaim.prelock_proof,
                            "under_lock_proof": reclaim.under_lock_proof,
                            "persistence_witness": reclaim.persistence_witness,
                        },
                    }
                )
            leases.append(lease)
            observation_s_lock = fresh_observation(f"S_lock:{uuid}")
            reread_allocated = observation_s_lock.caller_allocated_ids
            reread_processes = observation_s_lock.process_identities
            reread_memory = observation_s_lock.free_memory_bytes
            selected_under_lock = (*selected, uuid)
            occupied_under_lock = _occupied_gpu_units(
                reread_processes,
                observation_s_lock.gpu_devices,
                selected_under_lock,
            )
            raced_selected = tuple(
                selected_uuid
                for selected_uuid in selected_under_lock
                if selected_uuid not in reread_allocated
                or selected_uuid in occupied_under_lock
                or reread_memory.get(selected_uuid, 0)
                < request.gpu_requested_memory_bytes
            )
            readback_attempts.append(
                {
                    "uuid": uuid,
                    "lock_acquired": True,
                    "caller_allocated_ids": tuple(sorted(reread_allocated)),
                    "process_identities": tuple(
                        _process_record(process) for process in reread_processes
                    ),
                    "free_memory_bytes": reread_memory.get(uuid, 0),
                    "requested_memory_bytes": request.gpu_requested_memory_bytes,
                    "observation_timestamp": observation_s_lock.observed_at,
                    "observation_fingerprint": observation_s_lock.fingerprint,
                    "observation_event": "S_lock",
                    "observation_event_id": observation_s_lock.observation_event_id,
                    "selected_ids_under_lock": selected_under_lock,
                    "occupied_ids_under_lock": occupied_under_lock,
                    "raced_selected_ids": raced_selected,
                    "raced": bool(raced_selected),
                }
            )
            if raced_selected:
                retained_leases: list[ReservationLease] = []
                for selected_lease in leases:
                    if selected_lease.uuid not in raced_selected:
                        retained_leases.append(selected_lease)
                        continue
                    release_witness = _release_lease_with_observation(
                        selected_lease,
                        lambda selected_uuid=selected_lease.uuid: fresh_observation(
                            f"release_race:{selected_uuid}"
                        ),
                    )
                    if release_witness.get("result") != "released":
                        raise _gpu_preflight(
                            "gpu_race_release_retained",
                            "raced GPU lease retained because a live holder appeared",
                            release_witness=release_witness,
                        )
                    if selected_lease.uuid in selected:
                        selected.remove(selected_lease.uuid)
                leases = retained_leases
                continue
            selected.append(uuid)
            free_memory[uuid] = reread_memory.get(uuid, free_memory.get(uuid, 0))
            for selected_uuid in selected:
                free_memory[selected_uuid] = reread_memory[selected_uuid]
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
    except Exception as exc:
        raise _PlannerAttemptFailure(exc, tuple(leases)) from exc
    try:
        observation_s_final = fresh_observation("S_final")
    except Exception as exc:
        raise _PlannerAttemptFailure(exc, tuple(leases)) from exc
    final_allocated = observation_s_final.caller_allocated_ids
    final_processes = observation_s_final.process_identities
    final_memory = observation_s_final.free_memory_bytes
    final_device_by_id = {device.uuid: device for device in observation_s_final.gpu_devices}
    final_occupied_ids = _occupied_gpu_units(
        final_processes,
        observation_s_final.gpu_devices,
        candidate_ids,
    )
    final_valid = (
        len(selected) == requested
        and all(uuid in final_allocated for uuid in selected)
        and not set(selected).intersection(final_occupied_ids)
        and all(
            final_memory.get(uuid, 0) >= request.gpu_requested_memory_bytes
            for uuid in selected
        )
        and len(leases) == requested
        and all(uuid in final_device_by_id for uuid in selected)
    )
    if not final_valid:
        failure = _gpu_preflight(
            "gpu_final_readback_failed",
            "final allocation/process/memory reread did not preserve the request",
            selected_ids=tuple(selected),
            requested_count=requested,
            requested_memory_bytes=request.gpu_requested_memory_bytes,
        )
        raise _PlannerAttemptFailure(failure, tuple(leases)) from failure
    final_eligible_ids = tuple(
        uuid
        for uuid in candidate_ids
        if uuid not in final_occupied_ids
        and uuid not in reserved_ids_seen
        and final_memory.get(uuid, 0) >= request.gpu_requested_memory_bytes
    )
    if not set(selected).issubset(final_eligible_ids):
        failure = _gpu_preflight(
            "gpu_final_eligible_set_failed",
            "selected UUIDs are not members of the final hard-filtered E_t set",
            selected_ids=tuple(selected),
            final_eligible_ids=final_eligible_ids,
        )
        raise _PlannerAttemptFailure(failure, tuple(leases)) from failure
    allocation_id = f"allocation-{secrets.token_hex(12)}"
    lock_readback = {
        "lock_root": str(request.lock_root),
        "shared_across_schedulers": request.lock_namespace_shared_across_schedulers,
        "host_safe": request.lock_namespace_host_safe,
        "visibility_witness": request.lock_namespace_visibility_witness,
        "attempts": tuple(readback_attempts),
        "final_caller_allocated_ids": tuple(sorted(final_allocated)),
        "final_process_identities": tuple(
            _process_record(process) for process in final_processes
        ),
        "final_occupied_ids": final_occupied_ids,
        "final_free_memory_bytes": {
            uuid: final_memory.get(uuid, 0) for uuid in candidate_ids
        },
        "initial_observation": {
            "timestamp": observation_s0.observed_at,
            "fingerprint": observation_s0.fingerprint,
            "event": "S0",
            "event_id": observation_s0.observation_event_id,
        },
        "final_observation": {
            "timestamp": observation_s_final.observed_at,
            "fingerprint": observation_s_final.fingerprint,
            "event": "S_final",
            "event_id": observation_s_final.observation_event_id,
        },
        "final_eligible_ids": final_eligible_ids,
        "reservation_ids": tuple(lease.reservation_id for lease in leases),
        "readback_timestamp": observation_s_final.observed_at,
        "provenance": provenance,
        "candidate_cardinality": len(candidate_ids),
        "eligible_cardinality": len(final_eligible_ids),
        "selected_cardinality": len(selected),
        "requested_cardinality": requested,
        "stable_uuid_order": tuple(selected) == tuple(sorted(selected)),
    }
    readback_fingerprint = hashlib.sha256(
        _canonical_json(_json_safe(lock_readback)).encode("utf-8")
    ).hexdigest()
    return _mark_canonical_planner_provenance(GPUAllocation(
        plan_fingerprint="pending",
        caller_allocated_ids=caller_ids,
        candidate_ids=candidate_ids,
        occupied_ids=final_occupied_ids,
        reserved_ids=tuple(sorted(reserved_ids_seen)),
        eligible_ids=final_eligible_ids,
        selected_ids=tuple(selected),
        reservation_ids=tuple(lease.reservation_id for lease in leases),
        free_memory_bytes={uuid: final_memory.get(uuid, 0) for uuid in candidate_ids},
        occupied_process_identities=final_processes,
        process_identities=final_processes,
        allocation_id=allocation_id,
        lock_root=request.lock_root,
        selection_order=final_eligible_ids,
        memory_bytes={uuid: final_device_by_id[uuid].memory_bytes for uuid in selected},
        slot_id=None,
        requested_count=requested,
        requested_memory_bytes=request.gpu_requested_memory_bytes,
        readback_fingerprint=readback_fingerprint,
        lock_readback=lock_readback,
        allocation_provenance=provenance,
        leases=tuple(leases),
    ))


def _allocation_with_fingerprint(allocation: GPUAllocation, fingerprint: str) -> GPUAllocation:
    fingerprinted = GPUAllocation(
        plan_fingerprint=fingerprint,
        caller_allocated_ids=allocation.caller_allocated_ids,
        candidate_ids=allocation.candidate_ids,
        occupied_ids=allocation.occupied_ids,
        reserved_ids=allocation.reserved_ids,
        eligible_ids=allocation.eligible_ids,
        selected_ids=allocation.selected_ids,
        reservation_ids=allocation.reservation_ids,
        free_memory_bytes=allocation.free_memory_bytes,
        occupied_process_identities=allocation.occupied_process_identities,
        process_identities=allocation.process_identities,
        allocation_id=allocation.allocation_id,
        lock_root=allocation.lock_root,
        selection_order=allocation.selection_order,
        memory_bytes=allocation.memory_bytes,
        slot_id=allocation.slot_id,
        requested_count=allocation.requested_count,
        requested_memory_bytes=allocation.requested_memory_bytes,
        readback_fingerprint=allocation.readback_fingerprint,
        lock_readback=allocation.lock_readback,
        allocation_provenance=allocation.allocation_provenance,
        leases=allocation.leases,
    )
    if allocation._planner_provenance is _PLANNER_PROVENANCE:
        return _mark_canonical_planner_provenance(fingerprinted)
    return fingerprinted


def freeze_resource_plan(
    request: ResourceRequest,
    discovered: DiscoveredResources,
    gpu_allocation: GPUAllocation,
) -> ExecutionResourcePlan:
    """Freeze the plan or durably terminalize and clean the failed transaction."""
    try:
        return _freeze_resource_plan_impl(request, discovered, gpu_allocation)
    except Exception as exc:
        cleanup = handle_pre_execution_failure(
            exc,
            failed_operation="plan_freeze",
            source_state=PlanState.RESOURCE_DISCOVERED,
            request=request,
            discovered=discovered,
            acquired_leases=gpu_allocation.leases,
        )
        raise failure_after_durable_cleanup(exc, cleanup) from exc


def _freeze_resource_plan_impl(
    request: ResourceRequest,
    discovered: DiscoveredResources,
    gpu_allocation: GPUAllocation,
) -> ExecutionResourcePlan:
    """Seal the immutable resource/environment/argv/cwd contract."""
    if discovered.state != PlanState.RESOURCE_DISCOVERED:
        raise PlanStateError("freeze requires resource_discovered state")
    if gpu_allocation.plan_fingerprint not in ("", "pending"):
        raise PlanStateError("GPU allocation is already bound to another plan")
    if gpu_allocation.requested_count != request.gpu_requested_count:
        raise PlanStateError("GPU allocation cardinality does not match the request")
    if not set(request.cpu_requested_set).issubset(
        discovered.cpu_available_set
    ):
        raise TypedPreflightFailure(
            "cpu_cardinality_unavailable",
            "requested CPU set is not contained in the discovered allocation",
            requested_cpu_set=request.cpu_requested_set,
            discovered_cpu_set=discovered.cpu_available_set,
        )
    r5_transactional = (
        isinstance(gpu_allocation.lock_readback, Mapping)
        and gpu_allocation.lock_readback.get("reservation_owner")
        == "GpuReservationTransaction"
    )
    if (
        gpu_allocation._planner_provenance is not _PLANNER_PROVENANCE
        and not r5_transactional
    ):
        raise TypedPreflightFailure(
            "gpu_planner_provenance_invalid",
            "GPUAllocation was not produced by canonical plan_gpu_allocation",
        )
    if (
        request.gpu_requested_count
        and gpu_allocation.allocation_provenance
        != CALLER_ALLOCATION_PROVENANCE
    ):
        raise TypedPreflightFailure(
            "gpu_caller_allocation_provenance_invalid",
            "GPUAllocation is not bound to the caller/scheduler UUID set",
        )
    if (
        gpu_allocation.requested_count != request.gpu_requested_count
        or gpu_allocation.requested_memory_bytes
        != request.gpu_requested_memory_bytes
    ):
        raise TypedPreflightFailure(
            "gpu_request_provenance_mismatch",
            "GPUAllocation request provenance differs from ResourceRequest",
        )
    if request.gpu_requested_count:
        allocation_valid = (
            len(gpu_allocation.selected_ids) == request.gpu_requested_count
            and len(gpu_allocation.reservation_ids) == request.gpu_requested_count
            and (
                len(gpu_allocation.leases) == request.gpu_requested_count
                or r5_transactional
            )
            and set(gpu_allocation.selected_ids).issubset(
                gpu_allocation.caller_allocated_ids
            )
            and set(gpu_allocation.selected_ids).issubset(
                gpu_allocation.eligible_ids
            )
            and not set(gpu_allocation.selected_ids).intersection(
                gpu_allocation.occupied_ids
            )
            and not set(gpu_allocation.selected_ids).intersection(
                gpu_allocation.reserved_ids
            )
            and all(
                gpu_allocation.free_memory_bytes.get(uuid, 0)
                >= request.gpu_requested_memory_bytes
                for uuid in gpu_allocation.selected_ids
            )
            and all(not _is_gpu_index(uuid) for uuid in gpu_allocation.selected_ids)
            and bool(gpu_allocation.readback_fingerprint)
        )
        if not allocation_valid:
            raise TypedPreflightFailure(
                "gpu_allocation_contract_invalid",
                "GPUAllocation does not prove cardinality, memory, UUID, or lease invariants",
                requested_count=request.gpu_requested_count,
                requested_memory_bytes=request.gpu_requested_memory_bytes,
                selected_ids=gpu_allocation.selected_ids,
            )
    elif (
        gpu_allocation.selected_ids
        or gpu_allocation.reservation_ids
        or gpu_allocation.leases
    ):
        raise TypedPreflightFailure(
            "gpu_allocation_without_request",
            "GPU-unrequested plan cannot carry allocation or reservation state",
        )
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
    if request.gpu_requested_count:
        preallocate = exact_environment.get("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
        if preallocate.lower() != "false":
            raise TypedPreflightFailure(
                "xla_preallocation_must_be_disabled",
                "GPU execution requires canonical preallocation-disabled XLA environment",
            )
        exact_environment["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
        exact_environment.setdefault("XLA_PYTHON_CLIENT_ALLOCATOR", "platform")
        exact_environment.setdefault(
            "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR",
            "false",
        )
    if request.gpu_requested_count and not selected_ids:
        raise _gpu_preflight("gpu_selection_empty", "GPU request has no selected UUIDs")
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
            "occupied_process_identities": gpu_allocation.occupied_process_identities,
            "process_identities": gpu_allocation.process_identities,
            "lock_root": str(gpu_allocation.lock_root),
            "selection_order": gpu_allocation.selection_order,
            "memory_bytes": gpu_allocation.memory_bytes,
            "mig_mapping": {
                device.uuid: device.mig_parent_uuid
                for device in discovered.gpu_devices
                if device.uuid in gpu_allocation.candidate_ids
            },
            "slot_id": gpu_allocation.slot_id,
            "readback_fingerprint": gpu_allocation.readback_fingerprint,
            "allocation_provenance": discovered.allocation_provenance,
            "lock_readback": gpu_allocation.lock_readback,
            "planner_provenance": "canonical_plan_gpu_allocation",
            "observation_timestamp": discovered.observed_at,
            "observation_fingerprint": discovered.observation_fingerprint,
            "mig_parent_by_uuid": {
                device.uuid: device.mig_parent_uuid
                for device in discovered.gpu_devices
                if device.mig_parent_uuid is not None
            },
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
        "managed_run_integration": request.integration_contract.record(),
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
    discovered_structure_ref = discovered.structure_tool.get(
        "structure_contract_ref"
    )
    if discovered_structure_ref not in (None, STRUCTURE_CONTRACT_REF):
        raise TypedPreflightFailure(
            "structure_contract_authority_mismatch",
            "tree capability cannot override the canonical structure contract",
            expected=STRUCTURE_CONTRACT_REF,
            observed=discovered_structure_ref,
        )
    tree_capability = dict(discovered.structure_tool)
    tree_capability["structure_contract_ref"] = STRUCTURE_CONTRACT_REF
    container = {
        "runtime_root": str(runtime_root),
        "source_projection_root": str(source_projection),
        "structure_tool": "tree",
        "tree_version": str(discovered.structure_tool.get("version", "unknown")),
        "tree_capability": tree_capability,
        "structure_contract_ref": STRUCTURE_CONTRACT_REF,
        "tool_availability": dict(discovered.tool_availability),
        "container_id": discovered.container_id,
        "boot_id": discovered.boot_id,
    }
    side_effects = (
        {
            "id": "workspace-bind",
            "owner": "container-runtime",
            "target": "/workspace",
            "policy": "allowed_source_bound_readback",
            "disposal": "record_only",
        },
        {"id": "runtime-root", "owner": "ExecutionResourcePlan", "target": str(runtime_root), "policy": "container-local", "disposal": "record_only"},
        {"id": "run-root", "owner": "ExecutionResourcePlan", "target": str(run_root), "policy": "container-local", "disposal": "record_only"},
        {"id": "log-root", "owner": "ExecutionResourcePlan", "target": str(log_root), "policy": "container-local", "disposal": "record_only"},
        {"id": "source-projection", "owner": "ExecutionResourcePlan", "target": str(source_projection), "policy": "controlled_source_bound", "disposal": "record_only"},
        {"id": "runner-process-tree", "owner": "ExperimentRunner", "target": plan_id, "policy": "runner_owned_descendant_lifecycle", "disposal": "dispose_after_terminal"},
        {"id": "gpu-leases", "owner": "GpuReservationTransaction", "target": str(request.lock_root), "policy": "shared_scheduler_visibility", "disposal": "owner_callback_after_runner_join"},
        {"id": "cpu-affinity", "owner": "ExperimentRunner", "target": request.cpu_requested_set, "policy": "runner_owned", "disposal": "dispose_if_applied"},
        {"id": "gpu-slot", "owner": "ExperimentRunner", "target": gpu_allocation.slot_id, "policy": "runner_owned", "disposal": "dispose_if_allocated"},
        {"id": "temp-handle", "owner": "ExperimentRunner", "target": str(run_root), "policy": "retain_evidence_remove_transient", "disposal": "owner_callback"},
        *tuple(
            {
                "id": f"port:{port.get('name', index)}",
                "owner": "ExperimentRunner",
                "target": port,
                "policy": "runner_owned",
                "disposal": "release_if_allocated",
            }
            for index, port in enumerate(discovered.ports)
        ),
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
        evidence={
            "terminal": None,
            "partial": None,
            "cleanup": None,
            "closeout": None,
        },
        state=PlanState.PLAN_FROZEN,
        state_history=(*discovered.state_history, PlanState.PLAN_FROZEN),
        gpu_allocation=allocation,
        resource_probe=discovered.probe,
    )


def materialize_environment(plan: ExecutionResourcePlan) -> MaterializedEnvironment:
    """Materialize or durably terminalize and clean a failed frozen plan."""
    try:
        return _materialize_environment_impl(plan)
    except Exception as exc:
        cleanup = handle_pre_execution_failure(
            exc,
            failed_operation="environment_materialization",
            source_state=PlanState.PLAN_FROZEN,
            plan=plan,
        )
        raise failure_after_durable_cleanup(exc, cleanup) from exc


def _materialize_environment_impl(plan: ExecutionResourcePlan) -> MaterializedEnvironment:
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
    environment_witness = _write_json_once(
        environment_path,
        {
            "schema_version": 1,
            "plan_fingerprint": plan.plan_fingerprint,
            "environment": _redacted_environment(env),
            "cwd": str(plan.execution["cwd"]),
            "argv": plan.execution["argv"],
            "cuda_visible_devices_uuid_list": plan.gpu_allocation.selected_ids,
            "xla_jax_preallocation_values": {
                key: value
                for key, value in env.items()
                if key.startswith(("JAX_", "XLA_"))
            },
        },
    )
    _write_json_once(
        source_projection / "environment.json",
        {
            "schema_version": 1,
            "plan_fingerprint": plan.plan_fingerprint,
            "environment": _redacted_environment(env),
            "cwd": str(plan.execution["cwd"]),
            "argv": plan.execution["argv"],
            "cuda_visible_devices_uuid_list": plan.gpu_allocation.selected_ids,
            "runtime_root": str(runtime_root),
            "tool_availability": plan.container.get("tool_availability", {}),
        },
    )
    materialized_plan = _transition_plan(
        plan,
        PlanState.PLAN_FROZEN,
        PlanState.ENV_MATERIALIZED,
        evidence={"environment_materialization": environment_witness},
    )
    return MaterializedEnvironment(
        plan=materialized_plan,
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
    """Verify readback or durably terminalize and clean the failed plan."""
    try:
        return _verify_effective_environment_impl(plan, readback)
    except Exception as exc:
        cleanup = handle_pre_execution_failure(
            exc,
            failed_operation="effective_environment_readback",
            source_state=PlanState.ENV_MATERIALIZED,
            plan=plan,
        )
        raise failure_after_durable_cleanup(exc, cleanup) from exc


def _verify_effective_environment_impl(
    plan: ExecutionResourcePlan,
    readback: EffectiveEnvironmentReadback,
    *,
    probe_observation: ResourceObservation | None = None,
) -> EnvironmentCertificate:
    """Prove effective env/cwd/argv/UUID equality before runner execution."""
    _require_state(plan, PlanState.ENV_MATERIALIZED)
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
    environment_key_set_equal = set(observed) == set(expected)
    non_secret_equal = all(
        key in observed and observed[key] == value
        for key, value in expected.items()
        if not _is_sensitive_env_key(key)
    )
    secret_equal = all(bool(item["equality"]) for item in secret_witness)
    cwd_equal = readback.cwd == Path(cast(str, plan.execution["cwd"]))
    argv_equal = tuple(readback.argv) == tuple(cast(Sequence[str], plan.execution["argv"]))
    visible_expected = tuple(plan.gpu_allocation.selected_ids)
    visible_equal = tuple(readback.visible_gpu_ids) == visible_expected
    cpu_set_equal = readback.cpu_set == tuple(cast(Sequence[int], plan.resources["cpu"]["allocated_set"]))
    container_id_equal = readback.container_id == str(plan.container.get("container_id", ""))
    runtime_identity_equal = readback.runtime_identity == str(
        plan.container.get("container_id", "")
    )
    allocation_id_equal = readback.allocation_id == plan.gpu_allocation.allocation_id
    if probe_observation is None:
        probe_observation = plan.resource_probe.observe()
    caller_allocation_equal = tuple(readback.caller_allocated_ids) == tuple(
        plan.gpu_allocation.caller_allocated_ids
    )
    caller_allocation_probe_equal = frozenset(readback.caller_allocated_ids) == (
        probe_observation.caller_allocated_ids
    )
    reservation_ids_equal = tuple(readback.reservation_ids) == tuple(
        plan.gpu_allocation.reservation_ids
    )
    reservation_leases_active = (
        len(plan.gpu_allocation.leases) == len(plan.gpu_allocation.reservation_ids)
        and all(lease.active for lease in plan.gpu_allocation.leases)
    )
    requested_memory_equal = (
        readback.requested_memory_bytes
        == plan.gpu_allocation.requested_memory_bytes
    )
    free_memory_satisfies_request = all(
        readback.free_memory_bytes.get(uuid, 0)
        >= plan.gpu_allocation.requested_memory_bytes
        for uuid in plan.gpu_allocation.selected_ids
    )
    probe_memory = probe_observation.free_memory_bytes
    free_memory_probe_equal = all(
        readback.free_memory_bytes.get(uuid, -1) == probe_memory.get(uuid, -2)
        for uuid in plan.gpu_allocation.selected_ids
    )
    process_identities_equal = tuple(readback.process_identities) == tuple(
        plan.gpu_allocation.process_identities
    )
    process_probe_equal = tuple(readback.process_identities) == tuple(
        probe_observation.process_identities
    )
    probe_observation_equal = (
        bool(readback.probe_observation_timestamp)
        and bool(readback.probe_observation_fingerprint)
        and bool(readback.probe_observation_event_id)
        and readback.probe_observation_timestamp == probe_observation.observed_at
        and readback.probe_observation_fingerprint == probe_observation.fingerprint
        and readback.probe_observation_event_id == probe_observation.observation_event_id
    )
    visible_gpu_probe_equal = tuple(readback.visible_gpu_ids) == tuple(
        sorted(probe_observation.container_visible_ids)
    )
    tree_capability = cast(Mapping[str, object], plan.container.get("tree_capability", {}))
    tool_availability = cast(Mapping[str, object], plan.container.get("tool_availability", {}))
    tree_capability_valid = bool(tree_capability) and tree_capability.get("available") in {
        True,
        "true",
        "available",
    } and tree_capability.get("structure_contract_ref") == STRUCTURE_CONTRACT_REF
    structured_probe = tool_availability.get("nvidia-smi")
    process_inventory_visibility = (
        structured_probe.get("process_inventory_visibility")
        if isinstance(structured_probe, Mapping)
        else None
    )
    process_inventory_visibility_valid = (
        not plan.gpu_allocation.selected_ids
        or (
            isinstance(process_inventory_visibility, Mapping)
            and process_inventory_visibility.get("all_allocated_units_visible") is True
            and tuple(process_inventory_visibility.get("allocated_ids", ()))
            == tuple(plan.gpu_allocation.caller_allocated_ids)
        )
    )
    structured_probe_valid = (
        not plan.gpu_allocation.selected_ids
        or (
            isinstance(structured_probe, Mapping)
            and structured_probe.get("available") is True
            and structured_probe.get("structured") is True
            and process_inventory_visibility_valid
        )
    )
    tool_availability_valid = bool(tool_availability) and structured_probe_valid
    all_witnesses_valid = (
        environment_key_set_equal
        and non_secret_equal
        and secret_equal
        and cwd_equal
        and argv_equal
        and visible_equal
        and cpu_set_equal
        and container_id_equal
        and runtime_identity_equal
        and allocation_id_equal
        and caller_allocation_equal
        and caller_allocation_probe_equal
        and reservation_ids_equal
        and reservation_leases_active
        and requested_memory_equal
        and free_memory_satisfies_request
        and free_memory_probe_equal
        and process_identities_equal
        and process_probe_equal
        and probe_observation_equal
        and visible_gpu_probe_equal
        and tree_capability_valid
        and tool_availability_valid
    )
    readback_packet = _effective_readback_packet(readback)
    readback_fingerprint = _effective_readback_fingerprint(readback)
    readback_fingerprint_equal = readback.readback_fingerprint == readback_fingerprint
    all_witnesses_valid = all_witnesses_valid and readback_fingerprint_equal
    run_root = Path(cast(str, plan.resources["temp"]["run_root"]))
    source_projection_root = Path(
        cast(str, plan.container["source_projection_root"])
    )
    inventory_payload = {
        "schema_version": "os-side-effect-inventory/v1",
        "plan_fingerprint": plan.plan_fingerprint,
        "structure_contract_ref": STRUCTURE_CONTRACT_REF,
        "side_effects": plan.side_effect_inventory,
    }
    inventory_runtime_witness = _write_json_once(
        run_root / SIDE_EFFECT_INVENTORY_FILENAME,
        inventory_payload,
    )
    inventory_projection_witness = _write_json_once(
        source_projection_root / SIDE_EFFECT_INVENTORY_FILENAME,
        inventory_payload,
    )
    certificate_payload = {
        "schema_version": ENVIRONMENT_CERTIFICATE_SCHEMA_VERSION,
        "plan_fingerprint": plan.plan_fingerprint,
        "container_id": readback.container_id,
        "runtime_identity": readback.runtime_identity,
        "witnesses": {
            "environment_key_set_equal": environment_key_set_equal,
            "non_secret_env_equal": non_secret_equal,
            "redacted_secret_witness": secret_witness,
            "cwd_equal": cwd_equal,
            "argv_equal": argv_equal,
            "visible_gpu_ids_equal": visible_equal,
            "cpu_set_equal": cpu_set_equal,
            "container_id_equal": container_id_equal,
            "runtime_identity_equal": runtime_identity_equal,
            "allocation_id_equal": allocation_id_equal,
            "caller_allocation_equal": caller_allocation_equal,
            "caller_allocation_probe_equal": caller_allocation_probe_equal,
            "reservation_ids_equal": reservation_ids_equal,
            "reservation_leases_active": reservation_leases_active,
            "requested_memory_equal": requested_memory_equal,
            "free_memory_satisfies_request": free_memory_satisfies_request,
            "free_memory_probe_equal": free_memory_probe_equal,
            "process_identities_equal": process_identities_equal,
            "process_probe_equal": process_probe_equal,
            "probe_observation_equal": probe_observation_equal,
            "probe_observation_timestamp": readback.probe_observation_timestamp,
            "probe_observation_fingerprint": readback.probe_observation_fingerprint,
            "probe_observation_event_id": readback.probe_observation_event_id,
            "visible_gpu_probe_equal": visible_gpu_probe_equal,
            "readback_fingerprint_equal": readback_fingerprint_equal,
            "tree_capability_valid": tree_capability_valid,
            "tool_availability_valid": tool_availability_valid,
            "structured_probe_valid": structured_probe_valid,
            "process_inventory_visibility_valid": (
                process_inventory_visibility_valid
            ),
        },
        "redacted_environment": _redacted_environment(observed),
        "readback_fingerprint": readback_fingerprint,
        "readback_timestamp": readback.readback_timestamp,
        "probe_observation": {
            "timestamp": readback.probe_observation_timestamp,
            "fingerprint": readback.probe_observation_fingerprint,
            "event_id": readback.probe_observation_event_id,
        },
        "all_witnesses_valid": all_witnesses_valid,
        "structure_contract_ref": STRUCTURE_CONTRACT_REF,
        "tree_capability": plan.container.get("tree_capability", {}),
        "tool_availability": plan.container.get("tool_availability", {}),
        "runtime_root": plan.container["runtime_root"],
        "source_projection_root": plan.container["source_projection_root"],
        "os_side_effect_inventory_ref": str(
            source_projection_root / SIDE_EFFECT_INVENTORY_FILENAME
        ),
    }
    certificate_runtime_witness = _write_json_once(
        run_root / ENVIRONMENT_CERTIFICATE_FILENAME,
        certificate_payload,
    )
    certificate_projection_witness = _write_json_once(
        source_projection_root / ENVIRONMENT_CERTIFICATE_FILENAME,
        certificate_payload,
    )
    if not all_witnesses_valid:
        raise EnvironmentReadbackMismatch(
            "effective environment/allocation readback does not match the immutable plan; "
            f"certificate={certificate_runtime_witness['path']}"
        )
    verified_plan = _transition_plan(
        plan,
        PlanState.ENV_MATERIALIZED,
        PlanState.EFFECTIVE_ENV_READBACK_VERIFIED,
        readback={
            "effective_environment": readback_packet,
            "readback_fingerprint": readback_fingerprint,
            "all_witnesses_valid": True,
        },
        evidence={
            "environment_certificate": certificate_runtime_witness,
            "environment_certificate_projection": certificate_projection_witness,
            "os_side_effect_inventory": inventory_runtime_witness,
            "os_side_effect_inventory_projection": inventory_projection_witness,
        },
    )
    return EnvironmentCertificate(
        plan=verified_plan,
        schema_version=ENVIRONMENT_CERTIFICATE_SCHEMA_VERSION,
        plan_fingerprint=plan.plan_fingerprint,
        container_id=readback.container_id,
        runtime_identity=readback.runtime_identity,
        cwd_equal=cwd_equal,
        argv_equal=argv_equal,
        environment_key_set_equal=environment_key_set_equal,
        non_secret_env_equal=non_secret_equal,
        redacted_secret_witness=secret_witness,
        visible_gpu_ids_equal=visible_equal,
        cpu_set_equal=cpu_set_equal,
        container_id_equal=container_id_equal,
        runtime_identity_equal=runtime_identity_equal,
        allocation_id_equal=allocation_id_equal,
        caller_allocation_equal=caller_allocation_equal,
        caller_allocation_probe_equal=caller_allocation_probe_equal,
        reservation_ids_equal=reservation_ids_equal,
        reservation_leases_active=reservation_leases_active,
        requested_memory_equal=requested_memory_equal,
        free_memory_satisfies_request=free_memory_satisfies_request,
        free_memory_probe_equal=free_memory_probe_equal,
        process_identities_equal=process_identities_equal,
        process_probe_equal=process_probe_equal,
        visible_gpu_probe_equal=visible_gpu_probe_equal,
        readback_fingerprint_equal=readback_fingerprint_equal,
        runtime_root=Path(cast(str, plan.container["runtime_root"])),
        source_projection_root=Path(cast(str, plan.container["source_projection_root"])),
        tree_capability={
            "command": "tree",
            "version": str(plan.container.get("tree_version", "unknown")),
            **cast(Mapping[str, str], plan.container.get("tree_capability", {})),
            "structure_contract_ref": STRUCTURE_CONTRACT_REF,
        },
        tool_availability=tool_availability,
        os_side_effect_inventory_ref=str(
            source_projection_root / SIDE_EFFECT_INVENTORY_FILENAME
        ),
        certificate_persistence_witness={
            "runtime": certificate_runtime_witness,
            "projection": certificate_projection_witness,
        },
        inventory_persistence_witness={
            "runtime": inventory_runtime_witness,
            "projection": inventory_projection_witness,
        },
        readback_fingerprint=readback_fingerprint,
        all_witnesses_valid=all_witnesses_valid,
        readback_timestamp=readback.readback_timestamp,
        probe_observation_equal=probe_observation_equal,
    )


def _effective_readback_packet(
    readback: EffectiveEnvironmentReadback,
) -> Mapping[str, object]:
    return {
        "environment": dict(readback.environment),
        "cwd": str(readback.cwd),
        "argv": readback.argv,
        "visible_gpu_ids": readback.visible_gpu_ids,
        "cpu_set": readback.cpu_set,
        "container_id": readback.container_id,
        "runtime_identity": readback.runtime_identity,
        "allocation_id": readback.allocation_id,
        "caller_allocated_ids": readback.caller_allocated_ids,
        "reservation_ids": readback.reservation_ids,
        "free_memory_bytes": readback.free_memory_bytes,
        "process_identities": tuple(
            _process_record(process) for process in readback.process_identities
        ),
        "requested_memory_bytes": readback.requested_memory_bytes,
        "probe_observation_timestamp": readback.probe_observation_timestamp,
        "probe_observation_fingerprint": readback.probe_observation_fingerprint,
        "probe_observation_event_id": readback.probe_observation_event_id,
        "readback_timestamp": readback.readback_timestamp,
    }


def _effective_readback_fingerprint(readback: EffectiveEnvironmentReadback) -> str:
    return hashlib.sha256(
        _canonical_json(_json_safe(_effective_readback_packet(readback))).encode("utf-8")
    ).hexdigest()


def _environment_readback_fingerprint(environment: MaterializedEnvironment, allocation: GPUAllocation) -> str:
    packet = {
        "environment": dict(environment.exact_env_map),
        "cwd": str(environment.cwd),
        "argv": environment.argv,
        "caller_allocated_ids": allocation.caller_allocated_ids,
        "candidate_ids": allocation.candidate_ids,
        "occupied_ids": allocation.occupied_ids,
        "reserved_ids": allocation.reserved_ids,
        "eligible_ids": allocation.eligible_ids,
        "selected_ids": allocation.selected_ids,
        "allocation_id": allocation.allocation_id,
        "reservation_ids": allocation.reservation_ids,
        "free_memory_bytes": allocation.free_memory_bytes,
        "memory_bytes": allocation.memory_bytes,
        "occupied_process_identities": tuple(
            _process_record(process)
            for process in allocation.occupied_process_identities
        ),
        "process_identities": tuple(
            _process_record(process) for process in allocation.process_identities
        ),
        "requested_count": allocation.requested_count,
        "requested_memory_bytes": allocation.requested_memory_bytes,
        "planner_readback_fingerprint": allocation.readback_fingerprint,
        "lock_readback": allocation.lock_readback,
    }
    return hashlib.sha256(_canonical_json(_json_safe(packet)).encode("utf-8")).hexdigest()


def _readback_processes(raw: object) -> tuple[ProcessIdentity, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise EnvironmentReadbackMismatch("runner process readback must be a sequence")
    processes: list[ProcessIdentity] = []
    for item in raw:
        if isinstance(item, ProcessIdentity):
            processes.append(item)
            continue
        if not isinstance(item, Mapping):
            raise EnvironmentReadbackMismatch("runner process identity is malformed")
        pid = item.get("pid")
        process_start = item.get("process_start_identity")
        gpu_uuid = item.get("gpu_uuid")
        kind = item.get("kind", "compute")
        parent_pid = item.get("parent_pid")
        relationship = item.get("relationship", "unknown")
        observation_timestamp = item.get("observation_timestamp", "")
        observation_fingerprint = item.get("observation_fingerprint", "")
        if (
            not isinstance(pid, int)
            or not isinstance(process_start, str)
            or not isinstance(gpu_uuid, str)
            or not isinstance(kind, str)
            or (parent_pid is not None and not isinstance(parent_pid, int))
            or not isinstance(relationship, str)
            or not isinstance(observation_timestamp, str)
            or not isinstance(observation_fingerprint, str)
        ):
            raise EnvironmentReadbackMismatch("runner process identity fields are malformed")
        processes.append(
            ProcessIdentity(
                pid=pid,
                process_start_identity=process_start,
                gpu_uuid=gpu_uuid,
                kind=kind,
                parent_pid=cast(int | None, parent_pid),
                relationship=relationship,
                observation_timestamp=observation_timestamp,
                observation_fingerprint=observation_fingerprint,
            )
        )
    return tuple(processes)


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
    terminal_chunk_ids: Sequence[str] = (),
    completed_chunk_ids: Sequence[str] | None = None,
    in_flight_chunk_ids: Sequence[str] = (),
    unstarted_chunk_ids: Sequence[str] = (),
    stop_reason: str | None = None,
    disposition: str | None = None,
    diagnostics: Mapping[str, object] | None = None,
    evidence_refs: Mapping[str, object] | None = None,
) -> TerminalEvidence:
    """Record terminal or structured no-completion evidence without success inference."""
    _require_state(plan, PlanState.EXECUTE)
    if execution_result is None and no_completion is None:
        raise ResourcePlanError("terminal evidence requires ExecutionResult or no-completion")
    if not terminal_event_id:
        raise ResourcePlanError("terminal_event_id is required")
    planned_chunk_ids = tuple(cast(Sequence[str], plan.execution.get("requested_chunks", ())))
    terminal_ids = tuple(terminal_chunk_ids)
    if len(set(planned_chunk_ids)) != len(planned_chunk_ids):
        raise ResourcePlanError("requested chunk identifiers must be unique")
    if (
        len(set(terminal_ids)) != len(terminal_ids)
        or not set(terminal_ids).issubset(planned_chunk_ids)
    ):
        raise ResourcePlanError(
            "terminal chunk identifiers must be unique members of the frozen plan"
        )
    completed_ids = tuple(
        completed_chunk_ids if completed_chunk_ids is not None else terminal_ids
    )
    in_flight_ids = tuple(in_flight_chunk_ids)
    derived_unstarted = tuple(
        chunk_id
        for chunk_id in planned_chunk_ids
        if chunk_id not in set(completed_ids) | set(in_flight_ids)
    )
    unstarted_ids = tuple(unstarted_chunk_ids) or derived_unstarted
    partition_sets = (set(completed_ids), set(in_flight_ids), set(unstarted_ids))
    if (
        any(len(values) != len(set(values)) for values in (completed_ids, in_flight_ids, unstarted_ids))
        or any(not values.issubset(planned_chunk_ids) for values in partition_sets)
        or partition_sets[0].intersection(partition_sets[1])
        or partition_sets[0].intersection(partition_sets[2])
        or partition_sets[1].intersection(partition_sets[2])
        or set().union(*partition_sets) != set(planned_chunk_ids)
    ):
        raise ResourcePlanError(
            "completed/in-flight/unstarted chunk sets must partition the frozen plan"
        )
    all_chunks_terminal = set(terminal_ids) == set(planned_chunk_ids)
    if not all_chunks_terminal and not stop_reason:
        raise ResourcePlanError("partial terminal evidence requires a stop reason")
    result_record = _execution_result_record(execution_result)
    partial = PartialEvidence(
        plan_fingerprint=plan.plan_fingerprint,
        last_exact_state=PlanState.TERMINAL,
        disposition=(
            "not_applicable_all_planned_chunks_terminal"
            if all_chunks_terminal
            else disposition or "partial_not_completion"
        ),
        stop_reason=stop_reason,
        owner_maximum_timeout_seconds=float(plan.owner["maximum_timeout_seconds"]),
        completed_chunk_ids=completed_ids,
        in_flight_chunk_ids=in_flight_ids,
        unstarted_chunk_ids=unstarted_ids,
        diagnostics={
            "execution_result": result_record,
            "no_completion": no_completion,
            **dict(diagnostics or {}),
        },
        evidence_refs={
            "stdout": stdout_path,
            "stderr": stderr_path,
            "startup_log": startup_log_path,
            "run_log": run_log_path,
            "artifact_manifest": artifact_manifest_path,
            "source_snapshot": source_snapshot or {},
            "environment_certificate": plan.evidence.get("environment_certificate"),
            "cleanup_disposition_ref": {
                "runtime": str(
                    Path(cast(str, plan.resources["temp"]["run_root"]))
                    / CLEANUP_EVIDENCE_FILENAME
                ),
                "projection": str(
                    Path(cast(str, plan.container["source_projection_root"]))
                    / CLEANUP_EVIDENCE_FILENAME
                ),
                "status": "required_after_terminal",
            },
            **dict(evidence_refs or {}),
        },
    )
    partial_payload = {
        "schema_version": "partial-evidence/v1",
        "plan_fingerprint": plan.plan_fingerprint,
        "terminal_event_id": terminal_event_id,
        "last_exact_state": partial.last_exact_state,
        "disposition": partial.disposition,
        "stop_reason": partial.stop_reason,
        "owner_maximum_timeout_seconds": partial.owner_maximum_timeout_seconds,
        "completed_chunk_ids": partial.completed_chunk_ids,
        "in_flight_chunk_ids": partial.in_flight_chunk_ids,
        "unstarted_chunk_ids": partial.unstarted_chunk_ids,
        "diagnostics": partial.diagnostics,
        "evidence_refs": partial.evidence_refs,
        "partial_is_completion": False,
    }
    partial_witness = _persist_runtime_and_projection_once(
        plan,
        PARTIAL_EVIDENCE_FILENAME,
        partial_payload,
    )
    terminal_chunk_records = tuple(
        {
            "chunk_id": chunk_id,
            "terminal": True,
            "terminal_event_id": terminal_event_id,
            "execution_result": result_record,
            "no_completion": no_completion,
        }
        for chunk_id in terminal_ids
    )
    terminal_timestamp = utc_now()
    terminal_payload = {
        "schema_version": "terminal-evidence/v1",
        "plan_fingerprint": plan.plan_fingerprint,
        "terminal_event_id": terminal_event_id,
        "execution_result": result_record,
        "no_completion": no_completion,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "startup_log_path": startup_log_path,
        "run_log_path": run_log_path,
        "artifact_manifest_path": artifact_manifest_path,
        "source_snapshot": source_snapshot or {},
        "planned_chunk_ids": planned_chunk_ids,
        "terminal_chunk_records": terminal_chunk_records,
        "partial_evidence": partial_witness,
        "terminal_timestamp": terminal_timestamp,
    }
    terminal_witness = _persist_runtime_and_projection_once(
        plan,
        TERMINAL_EVIDENCE_FILENAME,
        terminal_payload,
    )
    terminal_plan = _transition_plan(
        plan,
        PlanState.EXECUTE,
        PlanState.TERMINAL,
        evidence={
            "terminal": terminal_witness,
            "partial": partial_witness,
            "terminal_event": {
                "terminal_event_id": terminal_event_id,
                "terminal_chunk_records": terminal_chunk_records,
                "stop_reason": stop_reason,
            },
        },
    )
    return TerminalEvidence(
        plan=terminal_plan,
        plan_fingerprint=plan.plan_fingerprint,
        terminal_event_id=terminal_event_id,
        execution_result=result_record,
        no_completion=no_completion,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        startup_log_path=startup_log_path,
        run_log_path=run_log_path,
        artifact_manifest_path=artifact_manifest_path,
        source_snapshot=source_snapshot or {},
        planned_chunk_ids=planned_chunk_ids,
        terminal_chunk_ids=terminal_ids,
        terminal_chunk_records=terminal_chunk_records,
        partial=partial,
        persistence_witness={
            "terminal": terminal_witness,
            "partial": partial_witness,
        },
        terminal_timestamp=terminal_timestamp,
    )


def release_runner_owned_gpu_leases(
    plan: ExecutionResourcePlan,
    *,
    runner_quiescence_evidence: Mapping[str, object],
) -> Mapping[str, object]:
    """Dispose GPU leases from the W1 runner adapter's terminal boundary.

    This is intentionally a separate owner call from ``StandardRunner`` callbacks:
    its caller is responsible for invoking it from an adapter ``finally``/side-effect
    disposer after the external runner has joined all descendants.  A failed or
    incomplete quiescence proof retains every lease and never force-kills a process.
    """
    if plan.state not in {
        PlanState.ENV_MATERIALIZED,
        PlanState.EXECUTE,
        PlanState.TERMINAL,
    }:
        raise PlanStateError("runner-owned lease disposal requires a materialized or terminal plan")
    plan_fingerprint = plan.plan_fingerprint
    quiescent = (
        runner_quiescence_evidence.get("plan_fingerprint") == plan_fingerprint
        and runner_quiescence_evidence.get("quiescent") is True
        and runner_quiescence_evidence.get("process_tree_terminal") is True
        and runner_quiescence_evidence.get("can_create_gpu_context") is False
    )
    dispositions: list[Mapping[str, object]] = []
    released: list[str] = []
    retained: list[str] = []
    for lease in plan.gpu_allocation.leases:
        if not quiescent:
            disposition = {
                "uuid": lease.uuid,
                "reservation_id": lease.reservation_id,
                "result": "retained_runner_quiescence_unproved",
                "force_kill": False,
                "runner_quiescence_evidence": runner_quiescence_evidence,
            }
            retained.append(lease.uuid)
            dispositions.append(disposition)
            continue
        try:
            witness = _release_lease_with_observation(
                lease,
                plan.resource_probe.observe,
            )
            result = str(witness.get("result", "unknown"))
            if result in {"released", "already_released"}:
                released.append(lease.uuid)
            else:
                retained.append(lease.uuid)
            dispositions.append(witness)
        except Exception as exc:
            retained.append(lease.uuid)
            dispositions.append(
                {
                    "uuid": lease.uuid,
                    "reservation_id": lease.reservation_id,
                    "result": "retained_release_observation_failed",
                    "failure_type": type(exc).__name__,
                    "failure_message": str(exc),
                    "force_kill": False,
                }
            )
    return {
        "owner": "GpuReservationTransaction",
        "plan_fingerprint": plan_fingerprint,
        "runner_quiescence_evidence": runner_quiescence_evidence,
        "released_gpu_ids": tuple(sorted(released)),
        "retained_gpu_ids": tuple(sorted(retained)),
        "dispositions": tuple(dispositions),
        "force_kill": False,
        "cleanup_complete": not retained,
    }


def dispose_resources(
    plan: ExecutionResourcePlan,
    terminal: TerminalEvidence,
    *,
    completion_coverage_adapter: CompletionCoverageAdapter,
    completion_coverage_input: _LegacyPlannerCoverageRecord,
    runner_quiescence_evidence: Mapping[str, object],
    side_effect_disposers: Mapping[str, object] | None = None,
    next_owner: str = "CompletionCoverage",
) -> CleanupEvidence:
    """Release only resources proven free; retain descendants without force-kill."""
    _require_state(plan, PlanState.TERMINAL)
    if terminal.plan_fingerprint != plan.plan_fingerprint:
        raise PlanStateError("terminal evidence does not belong to the terminal plan")
    if terminal.plan != plan:
        raise PlanStateError("terminal evidence is not the current terminal snapshot")
    projection_root = Path(cast(str, plan.container["source_projection_root"]))
    expected_completion_path = projection_root / COMPLETION_COVERAGE_FILENAME
    if (
        completion_coverage_adapter.evidence_path is None
        or completion_coverage_adapter.evidence_path.absolute()
        != expected_completion_path.absolute()
    ):
        raise CompletionCoverageFailure(
            "CompletionCoverage must use the canonical source projection path"
        )
    if (
        completion_coverage_input.plan_fingerprint != plan.plan_fingerprint
        or completion_coverage_input.terminal_event_id != terminal.terminal_event_id
    ):
        raise CompletionCoverageFailure("cleanup and CompletionCoverage keys do not match")
    quiescence_processes = runner_quiescence_evidence.get("process_identities")
    quiescence_processes_valid = isinstance(quiescence_processes, (tuple, list)) and all(
        isinstance(process, Mapping)
        and isinstance(process.get("pid"), int)
        and cast(int, process.get("pid")) > 0
        and isinstance(process.get("process_start_identity"), str)
        and bool(process.get("process_start_identity"))
        and isinstance(process.get("relationship"), str)
        and bool(process.get("relationship"))
        and isinstance(process.get("observation_timestamp"), str)
        and bool(process.get("observation_timestamp"))
        and isinstance(process.get("observation_fingerprint"), str)
        and bool(process.get("observation_fingerprint"))
        for process in cast(Sequence[object], quiescence_processes or ())
    )
    quiescence_valid = (
        runner_quiescence_evidence.get("plan_fingerprint")
        == plan.plan_fingerprint
        and runner_quiescence_evidence.get("quiescent") is True
        and runner_quiescence_evidence.get("process_tree_terminal") is True
        and runner_quiescence_evidence.get("can_create_gpu_context") is False
        and isinstance(runner_quiescence_evidence.get("observed_at"), str)
        and bool(runner_quiescence_evidence.get("observed_at"))
        and isinstance(runner_quiescence_evidence.get("observation_fingerprint"), str)
        and bool(runner_quiescence_evidence.get("observation_fingerprint"))
        and runner_quiescence_evidence.get("creation_barrier")
        == "runner_process_tree_joined"
        and isinstance(runner_quiescence_evidence.get("runner_root_pid"), int)
        and cast(int, runner_quiescence_evidence.get("runner_root_pid")) > 0
        and isinstance(
            runner_quiescence_evidence.get("runner_root_process_start_identity"),
            str,
        )
        and bool(
            runner_quiescence_evidence.get("runner_root_process_start_identity")
        )
        and quiescence_processes_valid
    )
    retained_process_list: list[ProcessIdentity] = []
    retained_gpu_ids: set[str] = set()
    side_effects: list[Mapping[str, object]] = []
    leaks: list[Mapping[str, object]] = []
    released_gpu_ids: list[str] = []
    disposer_by_id = dict(side_effect_disposers or {})
    runner_lease_disposition: Mapping[str, object] | None = None
    runner_lease_disposer = disposer_by_id.get("gpu-leases")
    if runner_lease_disposer is not None:
        try:
            candidate_disposition = runner_lease_disposer(
                {
                    "plan": plan,
                    "terminal": terminal,
                    "runner_quiescence_evidence": runner_quiescence_evidence,
                }
            )
            if not isinstance(candidate_disposition, Mapping):
                raise TypeError("gpu-leases disposer must return a mapping")
            runner_lease_disposition = candidate_disposition
            released_gpu_ids.extend(
                str(uuid)
                for uuid in cast(
                    Sequence[object], candidate_disposition.get("released_gpu_ids", ())
                )
            )
            retained_gpu_ids.update(
                str(uuid)
                for uuid in cast(
                    Sequence[object], candidate_disposition.get("retained_gpu_ids", ())
                )
            )
            raw_dispositions = candidate_disposition.get("dispositions", ())
            if isinstance(raw_dispositions, (tuple, list)):
                side_effects.extend(
                    cast(Mapping[str, object], disposition)
                    for disposition in raw_dispositions
                    if isinstance(disposition, Mapping)
                )
            if retained_gpu_ids:
                leaks.append(candidate_disposition)
        except Exception as exc:
            runner_lease_disposition = {
                "owner": "GpuReservationTransaction",
                "released_gpu_ids": (),
                "retained_gpu_ids": tuple(
                    sorted(lease.uuid for lease in plan.gpu_allocation.leases)
                ),
                "cleanup_complete": False,
                "failure_type": type(exc).__name__,
                "failure_message": str(exc),
                "force_kill": False,
            }
            retained_gpu_ids.update(
                cast(Sequence[str], runner_lease_disposition["retained_gpu_ids"])
            )
            leaks.append(runner_lease_disposition)
    for lease in plan.gpu_allocation.leases:
        if runner_lease_disposition is not None:
            continue
        if not quiescence_valid:
            disposition = {
                "uuid": lease.uuid,
                "action": "retained",
                "reservation_id": lease.reservation_id,
                "reason": "runner_process_tree_quiescence_unproved",
                "runner_quiescence_evidence": runner_quiescence_evidence,
                "force_kill": False,
            }
            retained_gpu_ids.add(lease.uuid)
            side_effects.append(disposition)
            leaks.append(disposition)
            continue
        try:
            release_witness = _release_lease_with_observation(
                lease,
                plan.resource_probe.observe,
            )
            if release_witness.get("result") == "released":
                released_gpu_ids.append(lease.uuid)
                disposition = {
                    "uuid": lease.uuid,
                    "action": "released",
                    "reservation_id": lease.reservation_id,
                    "release_witness": release_witness,
                }
            else:
                under_lock_holders = _readback_processes(
                    release_witness.get("holder_processes", ())
                )
                retained_process_list.extend(under_lock_holders)
                retained_gpu_ids.add(lease.uuid)
                disposition = {
                    "uuid": lease.uuid,
                    "action": "retained",
                    "reservation_id": lease.reservation_id,
                    "reason": "live_gpu_holder_reread_under_uuid_lock",
                    "release_witness": release_witness,
                    "holder_processes": tuple(
                        _process_record(process) for process in under_lock_holders
                    ),
                    "force_kill": False,
                }
                leaks.append(disposition)
        except Exception as exc:
            disposition = {
                "uuid": lease.uuid,
                "action": "release_failed",
                "reservation_id": lease.reservation_id,
                "failure_type": type(exc).__name__,
                "failure_message": str(exc),
                "force_kill": False,
            }
            leaks.append(disposition)
        side_effects.append(disposition)
    retained_processes = tuple(retained_process_list)
    retained = tuple(sorted(retained_gpu_ids))
    try:
        final_process_observation = plan.resource_probe.observe()
        current_processes = final_process_observation.process_identities
        final_process_observation_evidence: Mapping[str, object] = {
            "available": True,
            "timestamp": final_process_observation.observed_at,
            "fingerprint": final_process_observation.fingerprint,
            "event_id": final_process_observation.observation_event_id,
        }
    except Exception as exc:
        current_processes = ()
        final_process_observation_evidence = {
            "available": False,
            "failure_type": type(exc).__name__,
            "failure_message": str(exc),
            "disposition": "retained_or_unknown_without_fresh_observation",
        }
        leaks.append(
            {
                "action": "retained_or_unknown",
                "reason": "final_live_process_observation_failed",
                "observation_failure": final_process_observation_evidence,
                "force_kill": False,
            }
        )
    for side_effect in plan.side_effect_inventory:
        side_effect_id = cast(str, side_effect["id"])
        disposal = str(side_effect.get("disposal", "record_only"))
        if side_effect_id == "gpu-leases":
            outcome = {
                "id": side_effect_id,
                "owner": side_effect.get("owner", "ExecutionResourcePlan"),
                "declared": side_effect,
                "disposal_attempted": True,
                "disposal_result": (
                    "runner_owned_disposer"
                    if runner_lease_disposition is not None
                    else "retained_or_released_from_live_process_readback"
                ),
                "retained_gpu_ids": retained,
                "released_gpu_ids": tuple(released_gpu_ids),
                "runner_owned_disposition": runner_lease_disposition,
                "timestamp": utc_now(),
            }
            side_effects.append(outcome)
            continue
        if disposal == "record_only":
            outcome = {
                "id": side_effect_id,
                "owner": side_effect.get("owner", "ExecutionResourcePlan"),
                "declared": side_effect,
                "disposal_attempted": False,
                "disposal_result": "recorded_no_disposal_declared",
                "readback": {"present": True, "target": side_effect.get("target")},
                "timestamp": utc_now(),
            }
            side_effects.append(outcome)
            continue
        disposer = disposer_by_id.get(side_effect_id)
        if disposer is None:
            outcome = {
                "id": side_effect_id,
                "owner": side_effect.get("owner", "ExperimentRunner"),
                "declared": side_effect,
                "disposal_attempted": False,
                "disposal_result": "unknown_missing_owner_disposer",
                "timestamp": utc_now(),
            }
            side_effects.append(outcome)
            leaks.append(outcome)
            continue
        try:
            callback_result = disposer(side_effect)
            result = callback_result.get("result")
            outcome = {
                "id": side_effect_id,
                "owner": side_effect.get("owner", "ExperimentRunner"),
                "declared": side_effect,
                "disposal_attempted": True,
                "disposal_result": result,
                "owner_readback": callback_result,
                "timestamp": utc_now(),
            }
            if result not in {
                "disposed",
                "released",
                "not_allocated",
                "not_applied",
                "retained_for_durable_evidence",
            }:
                leaks.append(outcome)
        except Exception as exc:
            outcome = {
                "id": side_effect_id,
                "owner": side_effect.get("owner", "ExperimentRunner"),
                "declared": side_effect,
                "disposal_attempted": True,
                "disposal_result": "failed",
                "failure_type": type(exc).__name__,
                "failure_message": str(exc),
                "timestamp": utc_now(),
            }
            side_effects.append(outcome)
            leaks.append(outcome)
            continue
        side_effects.append(outcome)
    cleanup_timestamp = utc_now()
    cleanup_payload = {
        "schema_version": "cleanup-evidence/v1",
        "plan_fingerprint": plan.plan_fingerprint,
        "terminal_event_id": terminal.terminal_event_id,
        "side_effects": tuple(side_effects),
        "leak_or_unknown": tuple(leaks),
        "descendant_retained_gpu_ids": retained,
        "descendant_retained_processes": tuple(
            _process_record(process) for process in retained_processes
        ),
        "force_kill": False,
        "runner_quiescence_evidence": runner_quiescence_evidence,
        "runner_quiescence_valid": quiescence_valid,
        "final_process_observation": final_process_observation_evidence,
        "completion_coverage_pending_exactly_once": True,
        "disposed_at": cleanup_timestamp,
    }
    cleanup_witness = _persist_runtime_and_projection_once(
        plan,
        CLEANUP_EVIDENCE_FILENAME,
        cleanup_payload,
    )
    cleanup_plan = _transition_plan(
        plan,
        PlanState.TERMINAL,
        PlanState.CLEANUP_DISPOSED,
        evidence={
            "cleanup": cleanup_witness,
            "cleanup_disposition": {
                "side_effects": tuple(side_effects),
                "retained_processes": tuple(
                    _process_record(process) for process in retained_processes
                ),
                "force_kill": False,
            },
        },
    )
    closeout_intent_payload = {
        "schema_version": "closeout-intent/v1",
        "plan_fingerprint": plan.plan_fingerprint,
        "terminal_event_id": terminal.terminal_event_id,
        "terminal_evidence": terminal.persistence_witness,
        "partial_evidence": terminal.persistence_witness.get("partial"),
        "cleanup_evidence": cleanup_witness,
        "completion_coverage_path": str(expected_completion_path),
        "validation_artifacts": completion_coverage_input.required_evidence,
        "unresolved_design_issue_blockers": (
            completion_coverage_input.unresolved_design_issue_blockers
        ),
        "unresolved_validation_failures": (
            completion_coverage_input.unresolved_validation_failures
        ),
        "next_owner": next_owner,
    }
    closeout_intent_witness = _persist_runtime_and_projection_once(
        cleanup_plan,
        CLOSEOUT_INTENT_FILENAME,
        closeout_intent_payload,
    )
    closeout_artifact_refs = dict(completion_coverage_input.required_evidence)
    closeout_artifact_refs.update(
        {
            "design_artifact": DESIGN_AUTHORITY_ARTIFACT,
            "design_manager_artifact": DESIGN_MANAGER_ARTIFACT,
            "design_review_authority_artifact": DESIGN_REVIEW_AUTHORITY_ARTIFACT,
            "approved_design_brief_sha256": APPROVED_DESIGN_BRIEF_SHA256,
            "approved_design_partition_sha256": APPROVED_DESIGN_PARTITION_SHA256,
            "organizer_conclusion_prior_hash": "none",
            "organizer_conclusion_hash_assigned": False,
            "approved_design_revision": APPROVED_DESIGN_REVISION,
            "organizer_context_id": ORGANIZER_CONTEXT_ID,
            "implementation_artifact": "tools/experiments/execution_resource_plan.py",
            "implementation_review_artifact": (
                "reports/agents/w1-tool-env-routing-20260716/implementation_review.md"
            ),
        }
    )
    terminal_records_complete = (
        set(terminal.terminal_chunk_ids) == set(terminal.planned_chunk_ids)
        and len(terminal.terminal_chunk_records) == len(terminal.planned_chunk_ids)
    )
    explicit_partial_evidence = (
        not terminal_records_complete
        and terminal.partial.disposition == "partial_not_completion"
        and bool(terminal.partial.stop_reason)
    )
    required_evidence = dict(closeout_artifact_refs)
    required_evidence.update(
        {
            "terminal": bool(terminal.persistence_witness.get("terminal")),
            "partial": bool(terminal.persistence_witness.get("partial")),
            "cleanup": bool(cleanup_witness),
            "closeout_intent": bool(closeout_intent_witness),
            "terminal_records_complete": terminal_records_complete,
            "explicit_partial_evidence": explicit_partial_evidence,
            "terminal_ref": terminal.persistence_witness.get("terminal"),
            "partial_ref": terminal.persistence_witness.get("partial"),
            "cleanup_ref": cleanup_witness,
            "closeout_intent_ref": closeout_intent_witness,
            "design_artifact": DESIGN_AUTHORITY_ARTIFACT,
            "design_manager_artifact": DESIGN_MANAGER_ARTIFACT,
            "design_review_authority_artifact": DESIGN_REVIEW_AUTHORITY_ARTIFACT,
            "approved_design_brief_sha256": APPROVED_DESIGN_BRIEF_SHA256,
            "approved_design_partition_sha256": APPROVED_DESIGN_PARTITION_SHA256,
            "organizer_conclusion_prior_hash": "none",
            "organizer_conclusion_hash_assigned": False,
            "approved_design_revision": APPROVED_DESIGN_REVISION,
            "organizer_context_id": ORGANIZER_CONTEXT_ID,
            "implementation_artifact": "tools/experiments/execution_resource_plan.py",
            "implementation_review_artifact": (
                "reports/agents/w1-tool-env-routing-20260716/implementation_review.md"
            ),
        }
    )
    allocation = cleanup_plan.gpu_allocation
    occupied_processes = tuple(
        _process_record(process)
        for process in allocation.occupied_process_identities
    )
    certificate_matches = (
        completion_coverage_input.effective_env_certificate_matches
        and cleanup_plan.readback.get("all_witnesses_valid") is True
        and bool(cleanup_plan.evidence.get("environment_certificate"))
    )
    final_coverage_input = replace(
        completion_coverage_input,
        candidate_gpu_ids=tuple(allocation.candidate_ids),
        occupied_gpu_ids=occupied_processes,
        eligible_gpu_ids=tuple(allocation.eligible_ids),
        reserved_gpu_ids=tuple(allocation.reserved_ids),
        selected_gpu_ids=tuple(allocation.selected_ids),
        lock_readback=allocation.lock_readback,
        effective_env=cast(
            Mapping[str, object],
            cleanup_plan.readback.get("effective_environment", {}),
        ),
        actual_gpu_processes=tuple(
            _process_record(process) for process in current_processes
        ),
        release_retention_disposition={
            "side_effects": tuple(side_effects),
            "retained_gpu_ids": retained,
            "released_gpu_ids": tuple(released_gpu_ids),
        },
        concurrent_run_evidence={
            **dict(completion_coverage_input.concurrent_run_evidence),
            "planner_lock_attempts": allocation.lock_readback.get("attempts", ()),
            "final_process_observation": final_process_observation_evidence,
        },
        mig_evidence={
            "candidate_mig_mapping": cleanup_plan.resources["gpu"].get(
                "mig_mapping", {}
            ),
            **dict(completion_coverage_input.mig_evidence),
        },
        container_visible_uuid_mapping={
            "selected_ids": allocation.selected_ids,
            "effective_visible_ids": cleanup_plan.readback.get(
                "effective_environment", {}
            ).get("visible_gpu_ids", ()),
            **dict(completion_coverage_input.container_visible_uuid_mapping),
        },
        os_safe_lock_placement={
            "lock_root": str(allocation.lock_root),
            "shared_across_schedulers": allocation.lock_readback.get(
                "shared_across_schedulers"
            ),
            "host_safe": allocation.lock_readback.get("host_safe"),
            "visibility_witness": allocation.lock_readback.get(
                "visibility_witness"
            ),
        },
        descendant_retention_evidence={
            "retained_gpu_ids": retained,
            "retained_processes": tuple(
                _process_record(process) for process in retained_processes
            ),
            "runner_quiescence_evidence": runner_quiescence_evidence,
            "runner_quiescence_valid": quiescence_valid,
            "lease_release_requires_under_lock_process_reread": True,
            "force_kill": False,
        },
        planned_chunk_ids=terminal.planned_chunk_ids,
        terminal_chunk_ids=terminal.terminal_chunk_ids,
        terminal_chunk_records=terminal.terminal_chunk_records,
        required_evidence=required_evidence,
        effective_env_certificate_matches=certificate_matches,
        cleanup_has_unresolved_leak_or_unknown=bool(leaks),
    )
    completion_coverage = completion_coverage_adapter._historical_planner_closeout_rejected(
        final_coverage_input
    )
    closeout_payload = {
        "schema_version": "closeout-evidence/v1",
        "plan_fingerprint": plan.plan_fingerprint,
        "terminal_event_id": terminal.terminal_event_id,
        "terminal_evidence": terminal.persistence_witness,
        "partial_evidence": terminal.persistence_witness.get("partial"),
        "cleanup_evidence": cleanup_witness,
        "closeout_intent": closeout_intent_witness,
        "completion_coverage": completion_coverage.persistence_witness,
        "completion_claim_owner": "CompletionCoverageAdapter.record_once",
        "completion_claim_status": "persisted_exactly_once_before_final_closeout",
        "all_planned_chunks_complete": completion_coverage.all_planned_chunks_complete,
        "overall_delivery_complete": completion_coverage.overall_delivery_complete,
        "unresolved_blockers": completion_coverage.unresolved_blockers,
        "artifact_refs": required_evidence,
        "next_owner": next_owner,
    }
    closeout_witness = _persist_runtime_and_projection_once(
        cleanup_plan,
        CLOSEOUT_EVIDENCE_FILENAME,
        closeout_payload,
    )
    closeout = CloseoutEvidence(
        plan_fingerprint=plan.plan_fingerprint,
        terminal_event_id=terminal.terminal_event_id,
        terminal_evidence_present=True,
        partial_evidence_present=True,
        cleanup_evidence_present=True,
        closeout_evidence_present=True,
        effective_env_certificate_matches=certificate_matches,
        required_review_gates_passed=final_coverage_input.required_review_gates_passed,
        validation_failures=final_coverage_input.validation_failures,
        unresolved_design_issue_blockers=final_coverage_input.unresolved_design_issue_blockers,
        unresolved_validation_failures=final_coverage_input.unresolved_validation_failures,
        all_planned_chunks_complete=completion_coverage.all_planned_chunks_complete,
        overall_delivery_complete=completion_coverage.overall_delivery_complete,
        completion_persistence_witness=completion_coverage.persistence_witness,
        closeout_persistence_witness=closeout_witness,
        artifact_refs=required_evidence,
        next_owner=next_owner,
    )
    final_cleanup_evidence = dict(cleanup_plan.evidence)
    final_cleanup_evidence.update(
        {
            "completion_coverage": completion_coverage.persistence_witness,
            "closeout_intent": closeout_intent_witness,
            "closeout": closeout_witness,
        }
    )
    final_cleanup_plan = replace(
        cleanup_plan,
        evidence=final_cleanup_evidence,
    )
    return CleanupEvidence(
        plan=final_cleanup_plan,
        plan_fingerprint=plan.plan_fingerprint,
        side_effects=tuple(side_effects),
        leak_or_unknown=tuple(leaks),
        descendant_retained_gpu_ids=retained,
        descendant_retained_processes=retained_processes,
        completion_coverage=completion_coverage,
        closeout=closeout,
        persistence_witness={
            "cleanup": cleanup_witness,
            "closeout_intent": closeout_intent_witness,
            "completion_coverage": completion_coverage.persistence_witness,
            "closeout": closeout_witness,
        },
        disposed_at=cleanup_timestamp,
    )


def _require_state(plan: ExecutionResourcePlan, state: PlanState) -> None:
    if plan.state != state:
        raise PlanStateError(f"expected plan state {state}, got {plan.state}")


__all__ = [
    "AbsolutePosixPath",
    "ALTERNATE_GPU_ROUTE_STATIC_CONTRACT",
    "AdmittedEnvironment",
    "CALLER_ALLOCATION_PROVENANCE",
    "COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION",
    "CONTAINER_RUNTIME_ROOT",
    "CleanupEvidence",
    "CloseoutEvidence",
    "CompletionCoverage",
    "CompletionCoverageAdapter",
    "CompletionCoverageFailure",
    "CompletionCoverageInput",
    "ConcurrentRunEvidence",
    "CudaRuntimeCapabilityReceipt",
    "DiscoveredResources",
    "EffectiveEnvironmentReadback",
    "EnvironmentCertificate",
    "EnvironmentReadbackMismatch",
    "EvidenceAbsence",
    "EvidenceAbsenceField",
    "EvidenceDisposition",
    "EvidenceFd",
    "FailureRecord",
    "ExecutionResourcePlan",
    "FdDisposition",
    "FdReleaseEvidence",
    "GPUAllocation",
    "GPUDevice",
    "GpuProcessOccupancyProbe",
    "GpuReservationTransaction",
    "GpuRunRequest",
    "HOST_RUNTIME_ROOT",
    "JsonScalar",
    "JsonValue",
    "ManagedRunAdapterIntegrationContract",
    "ManagedGpuOutcome",
    "ManagedGpuOutcomeReducer",
    "MaterializedEnvironment",
    "NvidiaDriverVersion",
    "NvidiaInventory",
    "NvidiaInventoryProbe",
    "NvidiaListEvidence",
    "NvidiaSMIResourceProbe",
    "NvidiaTopologyJoin",
    "ParsedNvidiaXml",
    "PlanState",
    "PlanStateError",
    "PartialEvidence",
    "PreExecutionFailureCleanupEvidence",
    "PreExecutionFailureTerminalEvidence",
    "ProcessOccupancyEvidence",
    "ProcessIdentity",
    "PostToolUseProjectionReducer",
    "ResourcePlanError",
    "ResourceObservation",
    "ResourceProbe",
    "ResourceRequest",
    "ReservationEvidence",
    "RunGpuAdmissionReceipt",
    "RuntimeIdentityReader",
    "RuntimeIdentityReceipt",
    "RuntimeRoute",
    "DescendantRetentionEvidence",
    "MigEvidence",
    "UuidVisibilityEvidence",
    "LockPlacementEvidence",
    "SharedRuntimeProvisionReceipt",
    "SharedRuntimeReadbackReceipt",
    "Sha256Hex",
    "LockReadback",
    "SourceFileRecord",
    "SourceFreezeOwner",
    "SourceFreezeReceipt",
    "SourceSnapshotManifest",
    "SourceSnapshotRecord",
    "StaleReclaimEvidence",
    "TerminalEvidence",
    "TypedPreflightFailure",
    "UUIDReservationStore",
    "discover_resources",
    "build_completion_coverage_input",
    "build_source_path_set",
    "capture_cuda_runtime_capability",
    "dispose_resources",
    "failure_after_durable_cleanup",
    "freeze_source_tree",
    "freeze_resource_plan",
    "handle_pre_execution_failure",
    "materialize_environment",
    "managed_run_adapter_integration_contract",
    "plan_gpu_allocation",
    "parse_nvidia_driver_version",
    "parse_nvidia_smi_list",
    "parse_nvidia_smi_xml",
    "record_terminal",
    "read_shared_runtime_provision",
    "read_shared_runtime_readback",
    "release_runner_owned_gpu_leases",
    "validate_absolute_posix_path",
    "verify_effective_environment",
    "write_runtime_receipt_atomic",
]
