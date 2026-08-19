#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides run managed experiment experiment workflow tooling.
# upstream design ../README.md shared automation index
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md approved AgentCanon GPU admission R5 composition and terminal frame
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md external admitted CLI ownership and task boundary
# upstream implementation ./execution_resource_plan.py canonical admission planning and terminal owner
# upstream implementation ../../documents/experiments/experiment-runner-ff97-lifecycle.md fixed generic runner lifecycle and scheduler source identity
# downstream implementation ../../documents/experiments/gpu-admission-r5-ordered-integration-interface.json ordered W2-W4 interface
# downstream implementation ../../templates/experiments/_template/run.py exposes the topic main adapted from the frozen snapshot
# downstream implementation ../../tests/tools/test_run_managed_experiment.py validates the sole composition and frozen topic adapter
# upstream design ../../documents/experiments/gpu-admission-r5-nvidia-visibility.md NVIDIA process/PID/MIG/UUID visibility gate
# upstream environment ../../agent-canon-environment.toml audited ExperimentRunner provider identity and runtime item
# @dependency-end

# Static route evidence: run_cli -> execute_managed_run ->
# experiment-runner-admitted --request ... --result ... -> terminal reducers ->
# cleanup. Alternate managed GPU launch routes: none; the fixed opaque-UUID
# composition is the only managed route.

"""Run one experiment while recording canonical server-side run metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

if __package__:
    from tools.experiments.execution_resource_plan import (
        CALLER_ALLOCATION_PROVENANCE,
        COMPLETION_COVERAGE_FILENAME,
        HOST_RUNTIME_ROOT,
        AdmittedEnvironment,
        CompletionCoverageAdapter,
        ConcurrentRunEvidence,
        DescendantRetentionEvidence,
        DiscoveredResources,
        EvidenceAbsence,
        EvidenceAbsenceField,
        EvidenceDisposition,
        ExecutionResourcePlan,
        FailureRecord,
        FdReleaseEvidence,
        GPUAllocation,
        GpuProcessOccupancyProbe,
        GpuReservationTransaction,
        GpuRunRequest,
        LockPlacementEvidence,
        LockReadback,
        ManagedGpuOutcomeReducer,
        MigEvidence,
        NvidiaSMIResourceProbe,
        PostToolUseProjectionReducer,
        ProcessOccupancyEvidence,
        ResourcePlanError,
        ResourceRequest,
        RunGpuAdmissionReceipt,
        RuntimeIdentityReader,
        RuntimeIdentityReceipt,
        SourceFreezeOwner,
        TypedPreflightFailure,
        UuidVisibilityEvidence,
        _normalize_failure,
        build_completion_coverage_input,
        build_lock_bound_admission_receipt,
        build_source_path_set,
        freeze_resource_plan,
        managed_run_adapter_integration_contract,
        read_shared_runtime_provision,
        read_shared_runtime_readback,
    )
    from tools.experiments.experiment_identity import (
        ExperimentIdentity,
        ExperimentIdentityError,
        contained_path,
        identity_from_manifest,
        load_json_file,
        load_json_text,
        raw_relative_path,
        report_relative_path,
        result_relative_path,
        validate_segment,
    )
else:
    from execution_resource_plan import (  # type: ignore[no-redef]
        CALLER_ALLOCATION_PROVENANCE,
        COMPLETION_COVERAGE_FILENAME,
        HOST_RUNTIME_ROOT,
        AdmittedEnvironment,
        CompletionCoverageAdapter,
        ConcurrentRunEvidence,
        DescendantRetentionEvidence,
        DiscoveredResources,
        EvidenceAbsence,
        EvidenceAbsenceField,
        EvidenceDisposition,
        ExecutionResourcePlan,
        FailureRecord,
        FdReleaseEvidence,
        GPUAllocation,
        GpuProcessOccupancyProbe,
        GpuReservationTransaction,
        GpuRunRequest,
        LockPlacementEvidence,
        LockReadback,
        ManagedGpuOutcomeReducer,
        MigEvidence,
        NvidiaSMIResourceProbe,
        PostToolUseProjectionReducer,
        ProcessOccupancyEvidence,
        ResourcePlanError,
        ResourceRequest,
        RunGpuAdmissionReceipt,
        RuntimeIdentityReader,
        RuntimeIdentityReceipt,
        SourceFreezeOwner,
        TypedPreflightFailure,
        UuidVisibilityEvidence,
        _normalize_failure,
        build_completion_coverage_input,
        build_lock_bound_admission_receipt,
        build_source_path_set,
        freeze_resource_plan,
        managed_run_adapter_integration_contract,
        read_shared_runtime_provision,
        read_shared_runtime_readback,
    )
    from experiment_identity import (  # type: ignore[no-redef]
        ExperimentIdentity,
        ExperimentIdentityError,
        contained_path,
        identity_from_manifest,
        load_json_file,
        load_json_text,
        raw_relative_path,
        report_relative_path,
        result_relative_path,
        validate_segment,
    )

DEFAULT_REQUIRED_EVAL_ARTIFACTS = ("summary.json", "cases.jsonl", "config.json")
CONFIG_SOURCE_SNAPSHOT_NAME = "config_source.yaml"
COMMAND_MANIFEST_NAME = "command.json"
ENVIRONMENT_MANIFEST_NAME = "environment.json"
SOURCE_SNAPSHOT_NAME = "source_snapshot.json"
ARTIFACT_MANIFEST_NAME = "artifact_manifest.json"
STARTUP_LOG_NAME = "startup.jsonl"
STDOUT_LOG_NAME = "stdout.log"
STDERR_LOG_NAME = "stderr.log"
MANAGED_RUN_EXECUTABLE = "experiment-runner-admitted"
MANAGED_RUN_REQUEST_SCHEMA = "agentcanon-managed-run/v1"
MANAGED_RUN_RESULT_SCHEMA = "agentcanon-managed-run-result/v1"
MANAGED_RUN_PROVIDER_REPOSITORY = "https://github.com/iwashita-nozomu/experiment-runner"
MANAGED_RUN_PROVIDER_COMMIT = "71b3630266151703bdf88b11741b7492eca92fb4"
MANAGED_RUN_PROVIDER_CONTRACT_PATH = "documents/experiment-runner-admission.md"
MANAGED_RUN_PROVIDER_CONTRACT_SHA256 = (
    "2de2b63aac3076e6aacdf1ff10b2c35a0235e835504aeff2db92a7750a720d85"
)
MANAGED_RUN_PROVIDER_INVOCATION = (
    "experiment-runner-admitted --request <path> --result <path>"
)
MANAGED_RUN_REQUEST_FILENAME = "managed-run-request.json"
MANAGED_RUN_RESULT_FILENAME = "managed-run-result.json"
MANAGED_RUN_RECEIPT_FILENAME = "managed-run-receipt.json"
MANAGED_RUN_LIFECYCLE_FILENAME = "managed-run-lifecycle.json"
MANAGED_RUN_ARTIFACTS = frozenset(
    {
        "run_manifest.json",
        "eval_manifest.json",
        "run.log",
        CONFIG_SOURCE_SNAPSHOT_NAME,
        COMMAND_MANIFEST_NAME,
        ENVIRONMENT_MANIFEST_NAME,
        SOURCE_SNAPSHOT_NAME,
        ARTIFACT_MANIFEST_NAME,
        f"logs/{STARTUP_LOG_NAME}",
        f"logs/{STDOUT_LOG_NAME}",
        f"logs/{STDERR_LOG_NAME}",
    }
)
RESERVATION_MARKER_NAME = ".agentcanon-reservation.json"
RESERVATION_MARKER_SCHEMA = "agentcanon.experiment-reservation/v1"
FILE_READ_CHUNK_BYTES = 1024 * 1024
PREFLIGHT_FAILURE_EXIT_CODE = 2
DURATION_ROUND_DIGITS = 3
REGISTERED_COMMAND_KINDS = ("default", "formal")
REVIEWED_W1_LINEAGE_ARTIFACT = (
    "W1-IMPLEMENTATION-RECHECK-EF2DE34A-20260716-READONLY"
)
REVIEWED_W1_LINEAGE_COMMIT = "b829286c6a1c9de15f260199a44556e4f90be459"
REVIEWED_W1_LINEAGE_TREE = "551abfa0a6e89f4a9218fc4fc0706b3addd2a84e"
REVIEWED_W1_SOURCE_BLOBS = {
    "tools/experiments/execution_resource_plan.py": (
        "0a767491176530ecfe68a18e6b198de5d45f47fe"
    ),
    "tools/experiments/run_managed_experiment.py": (
        "4de18aeb418423ac36152d6e8501b11c16e82e18"
    ),
}
LEGACY_REGISTERED_COMMAND_ALIASES = {"smoke": "default"}
SENSITIVE_ENV_KEY_PARTS = (
    "API_KEY",
    "AUTH",
    "CREDENTIAL",
    "KEY",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)
EXCLUDED_SOURCE_SNAPSHOT_DIRS = frozenset(
    {
        ".git",
        "raw",
        "result",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


@dataclass(frozen=True)
class RegistryContext:
    """Loaded experiment registry data for one topic."""

    path: Path
    entry: dict[str, object]
    defaults: dict[str, object]
    available: bool


# Compatibility name for imports in downstream adapters.  The canonical owner
# is ExperimentIdentity; no second identity schema is maintained here.
if TYPE_CHECKING:
    RunIdentity: TypeAlias = ExperimentIdentity
else:
    RunIdentity = ExperimentIdentity


@dataclass(frozen=True)
class RunPaths:
    """Filesystem paths owned by one managed run identity."""

    result_dir: Path
    raw_dir: Path
    log_dir: Path
    report_path: Path
    manifest_path: Path
    eval_manifest_path: Path
    artifact_manifest_path: Path
    command_manifest_path: Path
    environment_manifest_path: Path
    source_snapshot_path: Path
    config_source_path: Path
    config_path: Path
    log_path: Path
    startup_log_path: Path
    stdout_log_path: Path
    stderr_log_path: Path


@dataclass(frozen=True)
class CommandSelection:
    """Selected inner command and its provenance."""

    command: list[str]
    source: str
    registered_match: str | None


@dataclass(frozen=True)
class GitSnapshot:
    """Git state captured for one run manifest."""

    branch: str | None
    commit: str | None
    status_short: list[str]


@dataclass(frozen=True)
class EvalArtifactPatterns:
    """Validated eval artifact patterns for one run."""

    required: list[str]
    optional: list[str]


@dataclass(frozen=True)
class RunContext:
    """Complete immutable setup context for one managed run."""

    repo_root: Path
    identity: RunIdentity
    topic_dir: Path
    paths: RunPaths
    registry: RegistryContext
    command: CommandSelection
    created_at: str
    git: GitSnapshot


@dataclass(frozen=True)
class ReservationReceipt:
    """Record the exact empty paths reserved by one runner invocation."""

    result_dir: Path
    raw_dir: Path
    report_path: Path
    report_content: str | None
    result_parent: Path
    result_parent_preexisted: bool
    raw_parent: Path
    raw_parent_preexisted: bool
    report_parent: Path
    report_parent_preexisted: bool
    token: str
    marker_path: Path
    result_inode: int
    raw_inode: int
    marker_inode: int
    report_reserved: bool
    report_inode: int | None
    result_parent_inode: int
    raw_parent_inode: int
    report_parent_inode: int | None
    identity: ExperimentIdentity


@dataclass(frozen=True)
class ManagedRunExecutionResult:
    """Result projected from the external admitted-runner protocol."""

    status: Literal["ok", "failed"]
    raw_exit_code: int
    failure_kind: str | None = None
    message: str | None = None
    source: str = MANAGED_RUN_EXECUTABLE

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "raw_exit_code": self.raw_exit_code,
            "failure_kind": self.failure_kind,
            "message": self.message,
            "source": self.source,
        }


@dataclass(frozen=True)
class ManagedRunLifecycleEvidence:
    """Provider lifecycle evidence returned by the admitted-run CLI."""

    run_id: str
    terminal_event_id: str
    observed_at_ns: int
    terminal_status: str
    total_case_count_at_start: int
    completion_count_before: int
    completion_count_after: int
    scheduler_completed: bool
    admitted_case_count: int
    terminal_notification_count: int
    child_process_ids: tuple[int, ...]
    process_group_ids: tuple[int, ...]
    direct_children_quiescent: bool
    descendant_quiescence: Literal["proved", "no_child", "unproven"]
    cleanup_failures: tuple[str, ...]
    terminal_coverage_complete: bool
    requested_case_coverage_complete: bool
    quiescence_complete: bool
    completion_coverage_complete: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "terminal_event_id": self.terminal_event_id,
            "observed_at_ns": self.observed_at_ns,
            "terminal_status": self.terminal_status,
            "total_case_count_at_start": self.total_case_count_at_start,
            "completion_count_before": self.completion_count_before,
            "completion_count_after": self.completion_count_after,
            "scheduler_completed": self.scheduler_completed,
            "admitted_case_count": self.admitted_case_count,
            "terminal_notification_count": self.terminal_notification_count,
            "child_process_ids": self.child_process_ids,
            "process_group_ids": self.process_group_ids,
            "direct_children_quiescent": self.direct_children_quiescent,
            "descendant_quiescence": self.descendant_quiescence,
            "cleanup_failures": self.cleanup_failures,
            "terminal_coverage_complete": self.terminal_coverage_complete,
            "requested_case_coverage_complete": self.requested_case_coverage_complete,
            "quiescence_complete": self.quiescence_complete,
            "completion_coverage_complete": self.completion_coverage_complete,
        }


def _lifecycle_quiescence_is_proven(
    lifecycle: ManagedRunLifecycleEvidence | None,
) -> bool:
    """Return the provider-backed lock-release predicate without defaults."""
    return bool(
        lifecycle is not None
        and lifecycle.quiescence_complete
        and lifecycle.direct_children_quiescent
        and lifecycle.descendant_quiescence in {"proved", "no_child"}
        and not lifecycle.cleanup_failures
        and lifecycle.completion_coverage_complete
    )


def build_admitted_environment(
    plan: ExecutionResourcePlan,
    runtime_identity: RuntimeIdentityReceipt,
    *,
    admission_fingerprint: str | None,
) -> AdmittedEnvironment:
    """Build the exact UUID environment only after plan freeze and admission."""
    if runtime_identity.runtime_route != "MANAGED_CONTAINER":
        raise TypedPreflightFailure(
            "runtime_identity_route_invalid",
            "managed admission requires the managed-container runtime identity",
            runtime_route=runtime_identity.runtime_route,
        )
    selected = tuple(plan.gpu_allocation.selected_ids)
    bound_fingerprint = admission_fingerprint
    if selected and (not isinstance(bound_fingerprint, str) or not bound_fingerprint):
        raise TypedPreflightFailure(
            "admission_fingerprint_missing",
            "admitted environment requires the lock-held composite admission fingerprint",
        )
    raw_gpu_resources = plan.resources.get("gpu", {})
    plan_bound_fingerprint = (
        raw_gpu_resources.get("admission_fingerprint")
        if isinstance(raw_gpu_resources, Mapping)
        else None
    )
    allocation_bound_fingerprint = getattr(
        plan.gpu_allocation,
        "admission_fingerprint",
        None,
    )
    if selected and (
        allocation_bound_fingerprint != bound_fingerprint
        or plan_bound_fingerprint != bound_fingerprint
    ):
        raise TypedPreflightFailure(
            "admission_fingerprint_mismatch",
            "plan and admitted environment do not reference the same composite admission fingerprint",
        )
    raw_environment = plan.execution.get("env")
    if not isinstance(raw_environment, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in raw_environment.items()
    ):
        raise TypedPreflightFailure(
            "admitted_environment_invalid",
            "frozen execution environment must be a string mapping",
        )
    environment = {str(key): str(value) for key, value in raw_environment.items()}
    expected = ",".join(selected)
    if selected and any(
        name in environment
        for name in ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES")
    ):
        raise TypedPreflightFailure(
            "gpu_visibility_before_plan_freeze",
            "GPU visibility must be absent from the pre-freeze environment",
            selected_uuids=selected,
        )
    if selected:
        environment["CUDA_VISIBLE_DEVICES"] = expected
        environment["NVIDIA_VISIBLE_DEVICES"] = expected
    for name in ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"):
        value = environment.get(name)
        if value is not None and any(item.isdecimal() for item in value.split(",")):
            raise TypedPreflightFailure(
                "admitted_environment_integer_route_forbidden",
                "GPU environment must contain opaque UUIDs, not indices",
                variable=name,
            )
    exact_map = tuple(sorted(environment.items()))
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "schema_version": "admitted-environment/v1",
                "exact_env_map": exact_map,
                "cuda_visible_devices": expected,
                "nvidia_visible_devices": expected,
                "admission_fingerprint": bound_fingerprint,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return AdmittedEnvironment(
        schema_version="admitted-environment/v1",
        exact_env_map=exact_map,
        cuda_visible_devices=expected,
        nvidia_visible_devices=expected,
        environment_fingerprint=fingerprint,
        admission_fingerprint=bound_fingerprint,
    )


class RunGpuAdmissionContext(AbstractContextManager[GpuRunRequest]):
    """Composition-only ordering and reverse-release context."""

    @classmethod
    def create(cls, request: GpuRunRequest) -> "RunGpuAdmissionContext":
        return cls(request)

    def __init__(self, request: GpuRunRequest) -> None:
        self.request = request
        self.state: str = "CREATED"
        self._release_callbacks: list[Callable[[], object]] = []
        self._release_failure_sink: Callable[[FailureRecord], None] | None = None

    def register_release(self, callback: Callable[[], object]) -> None:
        if self.state not in {"CREATED", "ENTERING", "ACTIVE"}:
            raise TypedPreflightFailure(
                "gpu_context_release_registration_closed",
                "context release registration occurred after close",
                state=self.state,
            )
        self._release_callbacks.append(callback)

    def register_release_failure_sink(
        self,
        sink: Callable[[FailureRecord], None],
    ) -> None:
        """Register only the root-owned sink for typed release failures."""
        if self.state not in {"CREATED", "ENTERING", "ACTIVE"}:
            raise TypedPreflightFailure(
                "gpu_context_release_registration_closed",
                "context release failure sink was registered after close",
                state=self.state,
            )
        self._release_failure_sink = sink

    def __enter__(self) -> GpuRunRequest:
        if self.state != "CREATED":
            raise TypedPreflightFailure(
                "gpu_context_reentered",
                "GPU admission context is one-shot",
                state=self.state,
            )
        self.state = "ENTERING"
        self.state = "ACTIVE"
        return self.request

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        if self.state not in {"ACTIVE", "ENTERING"}:
            raise TypedPreflightFailure(
                "gpu_context_exit_invalid",
                "GPU admission context exit occurred outside an active state",
                state=self.state,
            )
        self.state = "RELEASING"
        for callback in reversed(self._release_callbacks):
            try:
                callback()
            except BaseException as failure:
                if self._release_failure_sink is not None:
                    self._release_failure_sink(
                        _normalize_failure(failure, "context_release")
                    )
        self.state = "CLOSED"
        return False


def _provider_gpu_ids(selected_uuids: tuple[str, ...]) -> tuple[str, ...]:
    """Forward validated admission identifiers without changing their identity."""
    if any(
        not isinstance(value, str) or not value or value != value.strip()
        for value in selected_uuids
    ):
        raise TypedPreflightFailure(
            "admitted_runner_provider_gpu_identifier_invalid",
            "selected GPU identifiers must be non-empty, trimmed strings",
            selected_uuids=selected_uuids,
            provider_field="selected_gpu_ids",
        )
    if len(set(selected_uuids)) != len(selected_uuids):
        raise TypedPreflightFailure(
            "admitted_runner_provider_gpu_identifier_duplicate",
            "selected GPU identifiers must preserve the admission uniqueness contract",
            selected_uuids=selected_uuids,
            provider_field="selected_gpu_ids",
        )
    return tuple(selected_uuids)


def _provider_contract_identity() -> dict[str, str]:
    """Return the merged provider identity bound into each managed request."""
    return {
        "repository": MANAGED_RUN_PROVIDER_REPOSITORY,
        "commit": MANAGED_RUN_PROVIDER_COMMIT,
        "contract_path": MANAGED_RUN_PROVIDER_CONTRACT_PATH,
        "contract_sha256": MANAGED_RUN_PROVIDER_CONTRACT_SHA256,
        "invocation": MANAGED_RUN_PROVIDER_INVOCATION,
    }


def _build_managed_run_request(
    context: RunContext,
    request: GpuRunRequest,
    plan: ExecutionResourcePlan,
    admitted_environment: AdmittedEnvironment,
    source_paths: tuple[str, ...],
) -> tuple[Path, Path, Path, Mapping[str, object]]:
    """Serialize the schema-owned request without importing topic code."""
    expected_relative = f"experiments/{context.identity.topic}/run.py"
    try:
        topic_relative = context.topic_dir.resolve().relative_to(
            context.repo_root.resolve()
        )
    except ValueError as exc:
        raise TypedPreflightFailure(
            "experiment_runner_topic_identity_mismatch",
            "managed topic directory must be inside the repository root",
            topic=context.identity.topic,
        ) from exc
    if topic_relative.as_posix() != f"experiments/{context.identity.topic}":
        raise TypedPreflightFailure(
            "experiment_runner_topic_identity_mismatch",
            "managed topic directory is not the canonical experiments/<topic> path",
            topic_relative_path=topic_relative.as_posix(),
        )
    if expected_relative not in source_paths:
        raise TypedPreflightFailure(
            "gpu_source_freeze_manifest_incomplete",
            "the canonical topic entrypoint is absent from source membership",
            entrypoint_relative_path=expected_relative,
        )

    command = tuple(context.command.command)
    source_entrypoint = str(context.repo_root.resolve() / expected_relative)
    matches = tuple(
        index
        for index, token in enumerate(command)
        if token in {expected_relative, source_entrypoint}
    )
    interpreter_name = Path(command[0]).name if command else ""
    python_interpreter = interpreter_name in {"python", "python3"} or (
        interpreter_name.startswith("python3.")
        and interpreter_name.removeprefix("python3.").isdigit()
    )
    if matches != (1,) or not python_interpreter:
        raise TypedPreflightFailure(
            "managed_command_entrypoint_mismatch",
            "selected managed command must invoke the exact topic run.py with Python",
            expected_entrypoint=expected_relative,
            selected_command=command,
        )

    request_path = context.paths.result_dir / "runtime" / MANAGED_RUN_REQUEST_FILENAME
    result_path = context.paths.result_dir / "runtime" / MANAGED_RUN_RESULT_FILENAME
    lifecycle_path = context.paths.result_dir / "runtime" / MANAGED_RUN_LIFECYCLE_FILENAME
    selected_uuids = tuple(plan.gpu_allocation.selected_ids)
    selected_gpu_ids = _provider_gpu_ids(selected_uuids)
    payload: dict[str, object] = {
        **context.identity.to_dict(),
        "schema": MANAGED_RUN_REQUEST_SCHEMA,
        "run_id": context.identity.run_name,
        "task": {
            "module": f"experiments.{context.identity.topic}.run",
            "callable": "main",
        },
        "cases": [
            {
                "argv": command[2:],
                "entrypoint_relative_path": expected_relative,
            }
        ],
        "environment": dict(admitted_environment.exact_env_map),
        "capacity": {
            "max_workers": 1,
            "host_memory_bytes": request.host_memory_bytes,
            "gpu_devices": [
                {
                    "gpu_id": gpu_id,
                    "memory_bytes": plan.gpu_allocation.memory_bytes.get(uuid, 0),
                    "max_slots": 1,
                }
                for uuid, gpu_id in zip(selected_uuids, selected_gpu_ids)
            ],
        },
        "resource_estimate": {
            "host_memory_bytes": request.host_memory_bytes,
            "gpu_count": request.gpu_requested_count,
            "gpu_memory_bytes": request.gpu_requested_memory_bytes,
            "gpu_slots": 1,
        },
        "selected_gpu_ids": selected_gpu_ids,
        "metadata": {
            "agentcanon_provider_contract": _provider_contract_identity(),
            "agentcanon_admission_fingerprint": admitted_environment.admission_fingerprint,
            "agentcanon_plan_fingerprint": plan.plan_fingerprint,
            "agentcanon_source_paths": source_paths,
            "agentcanon_source_snapshot_root": str(
                context.paths.result_dir / "source_snapshot"
            ),
            "agentcanon_working_directory": str(
                context.paths.result_dir / "source_snapshot"
            ),
            "agentcanon_output_directory": str(context.paths.result_dir),
            "agentcanon_lifecycle_artifact_path": str(
                context.paths.result_dir
                / "runtime"
                / MANAGED_RUN_LIFECYCLE_FILENAME
            ),
            "agentcanon_selected_uuids": selected_uuids,
        },
    }
    payload["fingerprint"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return request_path, result_path, lifecycle_path, payload


def _resolve_admitted_runner() -> str:
    configured = os.environ.get(
        "AGENT_CANON_EXPERIMENT_RUNNER_ADMITTED",
        MANAGED_RUN_EXECUTABLE,
    )
    resolved = shutil.which(configured)
    if resolved is None and Path(configured).is_file() and os.access(configured, os.X_OK):
        resolved = str(Path(configured).resolve())
    if resolved is None:
        raise TypedPreflightFailure(
            "admitted_runner_cli_missing",
            "experiment-runner-admitted CLI is unavailable",
            executable=MANAGED_RUN_EXECUTABLE,
        )
    return resolved


def _validate_admitted_result(
    result_path: Path,
    request_payload: Mapping[str, object],
    process_returncode: int,
) -> tuple[ManagedRunExecutionResult, ManagedRunLifecycleEvidence, Mapping[str, object]]:
    try:
        result = load_json_file(result_path)
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "experiment-runner-admitted result artifact is missing or invalid JSON",
        ) from exc
    if not isinstance(result, Mapping):
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "experiment-runner-admitted result artifact must be a JSON object",
        )
    if result.get("schema") != MANAGED_RUN_RESULT_SCHEMA:
        raise TypedPreflightFailure(
            "admitted_runner_result_schema_mismatch",
            "experiment-runner-admitted result schema is not the reviewed version",
            observed_schema=result.get("schema"),
        )
    try:
        request_identity = identity_from_manifest(request_payload)
        result_identity = identity_from_manifest(result)
    except (ExperimentIdentityError, TypeError) as exc:
        raise TypedPreflightFailure(
            "admitted_runner_result_identity_invalid",
            "request and result must contain the canonical nested experiment identity",
        ) from exc
    if result_identity != request_identity:
        raise TypedPreflightFailure(
            "admitted_runner_result_identity_mismatch",
            "provider result identity does not match the managed request identity",
        )
    request_fingerprint = request_payload.get("fingerprint")
    if result.get("request_fingerprint") != request_fingerprint:
        raise TypedPreflightFailure(
            "admitted_runner_result_fingerprint_mismatch",
            "result does not reference the request fingerprint",
        )
    if result.get("run_id") != request_payload.get("run_id"):
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "result does not reference the request run identity",
        )
    status = result.get("status")
    if status not in {"ok", "failed", "rejected"}:
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "result status is not part of the provider schema",
            observed_status=status,
        )
    worker_pids_raw = result.get("worker_pids")
    if not isinstance(worker_pids_raw, list):
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "result worker_pids must be an array",
        )
    worker_pids = tuple(worker_pids_raw)
    if any(
        isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0
        for pid in worker_pids
    ) or len(set(worker_pids)) != len(worker_pids):
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "result worker_pids must contain unique positive process IDs",
        )
    worker_pid = result.get("worker_pid")
    if worker_pids:
        if (
            isinstance(worker_pid, bool)
            or not isinstance(worker_pid, int)
            or worker_pid != worker_pids[0]
        ):
            raise TypedPreflightFailure(
                "admitted_runner_result_corrupt",
                "result worker_pid must be the first provider worker PID",
            )
    elif worker_pid is not None:
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "result worker_pid must be null when worker_pids is empty",
        )
    lifecycle = result.get("lifecycle")
    quiescence = result.get("quiescence")
    exit_record = result.get("exit")
    completions = result.get("completions")
    if not isinstance(lifecycle, Mapping) or not isinstance(quiescence, Mapping) or not isinstance(exit_record, Mapping):
        raise TypedPreflightFailure(
            "admitted_runner_descendant_quiescence_unproven",
            "result must contain provider lifecycle and quiescence objects",
        )

    def required_int(mapping: Mapping[str, object], name: str) -> int:
        value = mapping.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise TypedPreflightFailure(
                "admitted_runner_result_corrupt",
                f"provider lifecycle field {name} is invalid",
            )
        return value

    def required_bool(mapping: Mapping[str, object], name: str) -> bool:
        value = mapping.get(name)
        if not isinstance(value, bool):
            raise TypedPreflightFailure(
                "admitted_runner_result_corrupt",
                f"provider lifecycle field {name} is invalid",
            )
        return value

    def required_pid_sequence(mapping: Mapping[str, object], name: str) -> tuple[int, ...]:
        value = mapping.get(name)
        if not isinstance(value, list):
            raise TypedPreflightFailure(
                "admitted_runner_result_corrupt",
                f"provider lifecycle field {name} is invalid",
            )
        pids = tuple(value)
        if any(
            isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0
            for pid in pids
        ) or len(set(pids)) != len(pids):
            raise TypedPreflightFailure(
                "admitted_runner_result_corrupt",
                f"provider lifecycle field {name} contains invalid process IDs",
            )
        return pids

    lifecycle_run_id = lifecycle.get("run_id")
    terminal_event_id = lifecycle.get("terminal_event_id")
    terminal_status = lifecycle.get("terminal_status")
    descendant_status = lifecycle.get("descendant_quiescence")
    lifecycle_child_pids = required_pid_sequence(lifecycle, "child_process_ids")
    lifecycle_group_pids = required_pid_sequence(lifecycle, "process_group_ids")
    if (
        lifecycle_run_id != request_payload.get("run_id")
        or not isinstance(terminal_event_id, str)
        or not terminal_event_id
        or terminal_status not in {"finished", "failed", "interrupted"}
        or descendant_status not in {"proved", "no_child", "unproven"}
        or tuple(worker_pids) != lifecycle_child_pids
    ):
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "provider lifecycle identity or status fields are invalid",
        )
    cleanup_failures_raw = lifecycle.get("cleanup_failures")
    if not isinstance(cleanup_failures_raw, list) or any(
        not isinstance(item, str) or not item for item in cleanup_failures_raw
    ):
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "provider lifecycle cleanup_failures must be an array of strings",
        )
    cleanup_failures = tuple(cleanup_failures_raw)
    direct_children_quiescent = required_bool(quiescence, "direct_children_quiescent")
    result_descendant_status = quiescence.get("descendant_quiescence")
    quiescence_cleanup_failures = quiescence.get("cleanup_failures")
    if (
        result.get("descendant_quiescence") != descendant_status
        or result_descendant_status != descendant_status
        or not isinstance(quiescence_cleanup_failures, list)
        or tuple(quiescence_cleanup_failures) != cleanup_failures
    ):
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "provider result and lifecycle quiescence statuses disagree",
        )
    quiescence_complete = required_bool(quiescence, "complete")
    lifecycle_quiescence_complete = required_bool(lifecycle, "quiescence_complete")
    terminal_coverage_complete = required_bool(lifecycle, "terminal_coverage_complete")
    requested_case_coverage_complete = required_bool(
        lifecycle,
        "requested_case_coverage_complete",
    )
    completion_coverage_complete = required_bool(
        lifecycle,
        "completion_coverage_complete",
    )
    scheduler_completed = required_bool(lifecycle, "scheduler_completed")
    if not isinstance(completions, list):
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "provider result completions must be an array",
        )
    admitted_case_count = required_int(lifecycle, "admitted_case_count")
    if len(completions) != admitted_case_count:
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "provider completion count does not match admitted case count",
        )
    if not (
        quiescence_complete
        and lifecycle_quiescence_complete
        and direct_children_quiescent
        and descendant_status in {"proved", "no_child"}
        and not cleanup_failures
        and terminal_coverage_complete
        and requested_case_coverage_complete
        and completion_coverage_complete
        and scheduler_completed
    ):
        raise TypedPreflightFailure(
            "admitted_runner_descendant_quiescence_unproven",
            "provider terminal result does not prove complete quiescence and completion coverage",
            quiescence_complete=quiescence_complete,
            lifecycle_quiescence_complete=lifecycle_quiescence_complete,
            direct_children_quiescent=direct_children_quiescent,
            descendant_quiescence=descendant_status,
            terminal_coverage_complete=terminal_coverage_complete,
            requested_case_coverage_complete=requested_case_coverage_complete,
            completion_coverage_complete=completion_coverage_complete,
        )
    exit_code = exit_record.get("code")
    error = exit_record.get("error")
    if (
        isinstance(exit_code, bool)
        or not isinstance(exit_code, int)
        or exit_code != process_returncode
    ):
        raise TypedPreflightFailure(
            "admitted_runner_exit_mismatch",
            "result exit code does not match the admitted CLI process",
            process_returncode=process_returncode,
            result_exit_code=exit_code,
        )
    if result.get("exit_code") != exit_code or result.get("error") != error:
        raise TypedPreflightFailure(
            "admitted_runner_result_corrupt",
            "provider result exit projection disagrees with its exit record",
        )
    if (status == "ok") != (exit_code == 0):
        raise TypedPreflightFailure(
            "admitted_runner_exit_mismatch",
            "provider result status disagrees with its exit code",
        )
    if exit_code != 0 and error in (None, ""):
        raise TypedPreflightFailure(
            "admitted_runner_error_missing",
            "nonzero admitted-runner exit requires typed error evidence",
        )

    lifecycle_evidence = ManagedRunLifecycleEvidence(
        run_id=str(lifecycle_run_id),
        terminal_event_id=cast(str, terminal_event_id),
        observed_at_ns=required_int(lifecycle, "observed_at_ns"),
        terminal_status=cast(str, terminal_status),
        total_case_count_at_start=required_int(lifecycle, "total_case_count_at_start"),
        completion_count_before=required_int(lifecycle, "completion_count_before"),
        completion_count_after=required_int(lifecycle, "completion_count_after"),
        scheduler_completed=scheduler_completed,
        admitted_case_count=admitted_case_count,
        terminal_notification_count=required_int(
            lifecycle,
            "terminal_notification_count",
        ),
        child_process_ids=lifecycle_child_pids,
        process_group_ids=lifecycle_group_pids,
        direct_children_quiescent=direct_children_quiescent,
        descendant_quiescence=cast(
            Literal["proved", "no_child", "unproven"],
            descendant_status,
        ),
        cleanup_failures=cleanup_failures,
        terminal_coverage_complete=terminal_coverage_complete,
        requested_case_coverage_complete=requested_case_coverage_complete,
        quiescence_complete=lifecycle_quiescence_complete,
        completion_coverage_complete=completion_coverage_complete,
    )
    execution = ManagedRunExecutionResult(
        status="ok" if exit_code == 0 else "failed",
        raw_exit_code=exit_code,
        failure_kind=(
            str(error.get("kind"))
            if isinstance(error, Mapping) and error.get("kind")
            else "admitted_runner_failed"
            if exit_code
            else None
        ),
        message=(
            str(error.get("message"))
            if isinstance(error, Mapping) and error.get("message")
            else str(error)
            if error not in (None, "")
            else None
        ),
    )
    return execution, lifecycle_evidence, result


def _run_admitted_runner(
    *,
    context: RunContext,
    request_path: Path,
    result_path: Path,
    lifecycle_path: Path,
    request_payload: Mapping[str, object],
    environment: Mapping[str, str],
) -> tuple[ManagedRunExecutionResult, ManagedRunLifecycleEvidence, Mapping[str, object]]:
    """Invoke the fixed shell-free admitted-runner handshake."""
    executable = _resolve_admitted_runner()
    argv = [executable, "--request", str(request_path), "--result", str(result_path)]
    try:
        with context.paths.stdout_log_path.open("ab") as stdout, context.paths.stderr_log_path.open("ab") as stderr:
            process = subprocess.Popen(
                argv,
                cwd=str(context.paths.result_dir / "source_snapshot"),
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
            )
            process_returncode = process.wait()
    except (OSError, subprocess.SubprocessError) as exc:
        raise TypedPreflightFailure(
            "admitted_runner_launch_failed",
            "experiment-runner-admitted could not be launched",
            executable=MANAGED_RUN_EXECUTABLE,
        ) from exc
    execution, lifecycle, result = _validate_admitted_result(
        result_path,
        request_payload,
        process_returncode,
    )
    lifecycle_path.parent.mkdir(parents=True, exist_ok=True)
    lifecycle_payload = lifecycle.to_dict()
    context_identity = cast(
        ExperimentIdentity | None,
        getattr(context, "identity", None),
    )
    if context_identity is None:
        context_identity = identity_from_manifest(request_payload)
    if isinstance(context_identity, ExperimentIdentity):
        lifecycle_payload.update(context_identity.to_dict())
    lifecycle_path.write_text(
        json.dumps(lifecycle_payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    receipt = {
        "schema_version": "agentcanon-managed-run-receipt/v1",
        "provider_contract": _provider_contract_identity(),
        "executable": MANAGED_RUN_EXECUTABLE,
        "resolved_executable": executable,
        "argv": argv,
        "request_fingerprint": request_payload["fingerprint"],
        "result_content_fingerprint": hashlib.sha256(
            json.dumps(
                result,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "process_returncode": process_returncode,
        "worker_pid": lifecycle.child_process_ids[0] if lifecycle.child_process_ids else None,
    }
    if isinstance(context_identity, ExperimentIdentity):
        receipt.update(context_identity.to_dict())
    receipt_path = context.paths.result_dir.joinpath("runtime", MANAGED_RUN_RECEIPT_FILENAME)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return execution, lifecycle, result


def repo_root_from_script() -> Path:
    """Return the repository root from this script location."""
    return Path(__file__).absolute().parents[2]


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_timestamp() -> str:
    """Return the compact timestamp used for run names."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create one managed experiment run directory with manifests, "
            "source/config snapshots, split logs, and an optional report stub."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=str(repo_root_from_script()),
        help="Repository root. Defaults to the path inferred from this script.",
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="Experiment topic name under experiments/.",
    )
    parser.add_argument(
        "--run-name",
        help="Explicit run name. Defaults to <topic>_<variant>_<timestamp>.",
    )
    parser.add_argument(
        "--variant",
        required=True,
        help="Required variant label used in the result/report/branch identity.",
    )
    parser.add_argument(
        "--registry",
        help=(
            "Optional registry path. Defaults to <repo-root>/experiments/registry.toml "
            "when present."
        ),
    )
    parser.add_argument(
        "--use-registered-command",
        help="Execute a registered inner command from experiments/registry.toml for this topic.",
    )
    parser.add_argument(
        "--report-path",
        help="Optional report path. Defaults to experiments/report/<topic>/<variant>/<run_name>.md.",
    )
    parser.add_argument(
        "--skip-report-init",
        action="store_true",
        help="Do not create a report stub when the report file is absent.",
    )
    parser.add_argument(
        "--config-json",
        help=(
            "Optional JSON object file to merge into result/<variant>/<run_name>/config.json. "
            "The file must decode to a dictionary."
        ),
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help=(
            "Add one JSON-encoded config value to result/<variant>/<run_name>/config.json. "
            "Example: --config seed=0 --config enabled=true."
        ),
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help=(
            "Command to run. Tokens may use {run_dir}, {raw_dir}, {run_name}, "
            "{report_path}, {topic}, {variant}, "
            "{manifest_path}, {eval_manifest_path}, {config_path}, "
            "{config_source_path}, {startup_log_path}, {stdout_log_path}, "
            "or {stderr_log_path}."
        ),
    )
    return parser.parse_args()


def load_registry(path: Path) -> dict[str, object]:
    """Load one experiment registry TOML file."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError("experiment registry TOML root must be a table")
    return data


def string_list(raw_value: object, key: str) -> list[str]:
    """Return one normalized non-empty string list."""
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise ValueError(f"{key} must be an array of strings")
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key}[{index}] must be a non-empty string")
    return [item.strip() for item in raw_value]


def find_registry_topic(
    registry: dict[str, object], topic_name: str
) -> dict[str, object] | None:
    """Return one topic entry from the registry."""
    raw_topics = registry.get("topics", [])
    if not isinstance(raw_topics, list):
        raise ValueError("experiment registry must contain [[topics]]")
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            continue
        name = raw_topic.get("name")
        if name == topic_name:
            return raw_topic
    return None


def resolve_registry_path(repo_root: Path, registry_arg: str) -> Path:
    """Resolve the registry path requested by the CLI."""
    if registry_arg:
        return Path(registry_arg).resolve()
    return repo_root / "experiments" / "registry.toml"


def load_registry_context(registry_path: Path, topic_name: str) -> RegistryContext:
    """Load one topic registry context when the registry exists."""
    if not registry_path.is_file():
        return RegistryContext(
            path=registry_path,
            entry={},
            defaults={},
            available=False,
        )
    registry = load_registry(registry_path)
    entry = find_registry_topic(registry, topic_name)
    if entry is None:
        raise ValueError(f"topic {topic_name!r} is missing from {registry_path}")
    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("experiment registry defaults must be a table")
    return RegistryContext(
        path=registry_path,
        entry=entry,
        defaults=defaults,
        available=True,
    )


def load_command_version(name: str) -> str | None:
    """Return one-line version text for a command when available."""
    if shutil.which(name) is None:
        return None
    result = subprocess.run(
        [name, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if not output:
        return None
    return output.splitlines()[0]


def load_config_json(path: Path) -> dict[str, object]:
    """Load one experiment config JSON object."""
    data = load_json_file(path)
    if not isinstance(data, dict):
        raise ValueError(f"--config-json must decode to a JSON object: {path}")
    config: dict[str, object] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"--config-json contains an invalid key: {key!r}")
        config[key] = value
    return config


def parse_config_pairs(pairs: list[str]) -> dict[str, object]:
    """Parse repeated KEY=JSON config arguments."""
    config: dict[str, object] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--config must use KEY=JSON form: {pair}")
        key, raw_value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--config has an empty key: {pair}")
        try:
            config[key] = load_json_text(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"--config value for {key!r} is not valid JSON: {exc}"
            ) from exc
    return config


def build_registry_config_snapshot(registry: RegistryContext) -> dict[str, object]:
    """Build the registry fragment embedded in run config."""
    if not registry.available:
        return {}
    return {
        "name": registry.entry.get("name"),
        "canonical_entrypoint": registry.entry.get("canonical_entrypoint"),
        "default_variant": registry.entry.get("default_variant"),
        "default_inner_command": registry.entry.get("default_inner_command")
        or registry.entry.get("smoke_inner_command"),
        "formal_inner_command": registry.entry.get("formal_inner_command"),
    }


def build_run_config(
    context: RunContext, explicit_config: dict[str, object]
) -> dict[str, object]:
    """Build one JSON-serializable experiment run configuration dictionary."""
    run_config: dict[str, object] = {
        **context.identity.to_dict(),
        "paths": {
            "result_dir": str(context.paths.result_dir),
            "raw_dir": str(context.paths.raw_dir),
            "log_dir": str(context.paths.log_dir),
            "report_path": str(context.paths.report_path),
            "run_manifest": str(context.paths.manifest_path),
            "eval_manifest": str(context.paths.eval_manifest_path),
            "artifact_manifest": str(context.paths.artifact_manifest_path),
            "command_manifest": str(context.paths.command_manifest_path),
            "environment_manifest": str(context.paths.environment_manifest_path),
            "source_snapshot": str(context.paths.source_snapshot_path),
            "source_config": str(context.paths.config_source_path),
            "config": str(context.paths.config_path),
            "startup_log": str(context.paths.startup_log_path),
            "stdout_log": str(context.paths.stdout_log_path),
            "stderr_log": str(context.paths.stderr_log_path),
        },
        "command": context.command.command,
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "config": explicit_config,
    }
    registry_config = build_registry_config_snapshot(context.registry)
    if registry_config:
        run_config["registry"] = registry_config
    return run_config


def git_value(repo_root: Path, *args: str) -> str | None:
    """Return one git value or None when unavailable."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def load_git_snapshot(repo_root: Path) -> GitSnapshot:
    """Load the git state recorded in run artifacts."""
    git_dirty = git_value(repo_root, "status", "--short")
    return GitSnapshot(
        branch=git_value(repo_root, "branch", "--show-current"),
        commit=git_value(repo_root, "rev-parse", "HEAD"),
        status_short=git_dirty.splitlines() if git_dirty else [],
    )


def registry_path_text(registry: RegistryContext) -> str:
    """Return the display registry path for reports."""
    if registry.available:
        return str(registry.path)
    return "(none)"


def render_report_stub(context: RunContext) -> str:
    """Render one initial run report."""
    command_text = (
        shlex.join(context.command.command)
        if context.command.command
        else "(no command)"
    )
    branch_text = context.git.branch or "(unknown)"
    commit_text = context.git.commit or "(unknown)"
    return f"""# {context.identity.run_name}

- Topic: {context.identity.topic}
- Variant: {context.identity.variant}
- Created At (UTC): {context.created_at}
- Result Dir: {context.paths.result_dir}
- Raw Dir: {context.paths.raw_dir}
- Log Dir: {context.paths.log_dir}
- Run Manifest: {context.paths.manifest_path}
- Eval Manifest: {context.paths.eval_manifest_path}
- Artifact Manifest: {context.paths.artifact_manifest_path}
- Config: {context.paths.config_path}
- Source Config Snapshot: {context.paths.config_source_path}
- Registry: {registry_path_text(context.registry)}
- Branch: {branch_text}
- Commit: {commit_text}

## Question

<!-- What empirical question does this run answer? -->

## Comparison Target

<!-- main, baseline, previous run, or external reference. -->

## Protocol

- Command: `{command_text}`
- Report Path: `{context.paths.report_path}`

## Results

<!-- Fill in summary.json, cases.jsonl, and the main observations after the run. -->

## Reproducibility Record

- `run_manifest.json`
- `config.json`
- `config_source.yaml`
- `eval_manifest.json`
- `artifact_manifest.json`
- `command.json`
- `environment.json`
- `source_snapshot.json`
- `run.log`
- `logs/`
- `logs/startup.jsonl`
- `logs/stdout.log`
- `logs/stderr.log`
- `summary.json`
- `cases.jsonl`

## Critical Review Notes

<!-- What this run still does not justify. -->
"""


def build_manifest(context: RunContext, status: str) -> dict[str, object]:
    """Build one manifest dictionary."""
    manifest: dict[str, object] = {
        **context.identity.to_dict(),
        "status": status,
        "created_at_utc": context.created_at,
        "repo_root": str(context.repo_root),
        "topic_dir": str(context.topic_dir),
        "result_dir": str(context.paths.result_dir),
        "raw_dir": str(context.paths.raw_dir),
        "raw_artifacts": {
            "path": raw_relative_path(context.identity).as_posix(),
            "retention": {"state": "unarchived"},
        },
        "log_dir": str(context.paths.log_dir),
        "report_path": str(context.paths.report_path),
        "manifest_path": str(context.paths.manifest_path),
        "eval_manifest_path": str(context.paths.eval_manifest_path),
        "artifact_manifest_path": str(context.paths.artifact_manifest_path),
        "command_manifest_path": str(context.paths.command_manifest_path),
        "environment_manifest_path": str(context.paths.environment_manifest_path),
        "source_snapshot_path": str(context.paths.source_snapshot_path),
        "config_source_path": str(context.paths.config_source_path),
        "startup_log_path": str(context.paths.startup_log_path),
        "stdout_log_path": str(context.paths.stdout_log_path),
        "stderr_log_path": str(context.paths.stderr_log_path),
        "command": context.command.command,
        "server_context": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "user": os.environ.get("USER") or os.environ.get("USERNAME") or "(unknown)",
        },
        "tool_versions": {
            "python": platform.python_version(),
            "codex": load_command_version("codex"),
            "docker": load_command_version("docker"),
        },
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "git": {
            "branch": context.git.branch,
            "commit": context.git.commit,
            "dirty": bool(context.git.status_short),
            "status_short": context.git.status_short,
        },
    }
    if context.registry.available:
        registry_snapshot = dict(context.registry.entry)
        registry_snapshot["registry_path"] = str(context.registry.path)
        manifest["registry"] = registry_snapshot
    return manifest


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write one JSON object with canonical formatting."""
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    """Write one manifest JSON file."""
    write_json(path, manifest)


def env_key_is_sensitive(key: str) -> bool:
    """Return whether an environment variable name likely contains a secret."""
    key_upper = key.upper()
    return any(part in key_upper for part in SENSITIVE_ENV_KEY_PARTS)


def captured_environment(env: dict[str, str]) -> dict[str, object]:
    """Return a redacted environment snapshot for reproducibility."""
    values: dict[str, object] = {}
    redacted_keys: list[str] = []
    for key in sorted(env):
        if env_key_is_sensitive(key):
            values[key] = {"present": True, "redacted": True}
            redacted_keys.append(key)
        else:
            values[key] = env[key]
    return {
        "captured_at_utc": utc_now(),
        "policy": "full_environment_with_key_secret_redaction",
        "key_count": len(values),
        "redacted_keys": redacted_keys,
        "values": values,
    }


def file_record(path: Path, base: Path) -> dict[str, object]:
    """Return stable metadata for one file."""
    relative_path = str(path.relative_to(base))
    return {
        "relative_path": relative_path,
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
    }


def path_is_relative_to(path: Path, base: Path) -> bool:
    """Return whether path is inside base."""
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def external_file_record(path: Path) -> dict[str, object]:
    """Return stable metadata for one source file outside the repo root."""
    return {
        "absolute_path": str(path),
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
    }


def source_snapshot_candidate_files(path: Path) -> list[Path]:
    """Return source snapshot files under one path."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    files: list[Path] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        relative_parts = child.relative_to(path).parts
        if any(part in EXCLUDED_SOURCE_SNAPSHOT_DIRS for part in relative_parts):
            continue
        files.append(child)
    return files


def git_status_path_text(status_line: str) -> str:
    """Return the path portion from one git status --short line."""
    raw_path = status_line[3:].strip()
    if " -> " in raw_path:
        raw_path = raw_path.rsplit(" -> ", 1)[1]
    return raw_path.strip('"')


def dirty_source_files(repo_root: Path, status_short: list[str]) -> tuple[list[Path], list[str]]:
    """Return existing dirty files plus dirty entries without a readable file."""
    files: list[Path] = []
    missing_paths: list[str] = []
    for status_line in status_short:
        path_text = git_status_path_text(status_line)
        if not path_text:
            continue
        candidate = repo_root / path_text
        candidate_files = source_snapshot_candidate_files(candidate)
        if candidate_files:
            files.extend(candidate_files)
        else:
            missing_paths.append(path_text)
    return files, missing_paths


def command_source_files(command: list[str], repo_root: Path) -> list[Path]:
    """Return local source files referenced directly by a command."""
    files: list[Path] = []
    for token in command:
        candidate = Path(token)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.is_file():
            files.append(candidate.resolve())
    return files


def unique_paths(paths: list[Path]) -> list[Path]:
    """Return stable unique paths."""
    return sorted(dict.fromkeys(path.resolve() for path in paths), key=lambda path: str(path))


def build_source_snapshot(context: RunContext) -> dict[str, object]:
    """Build the source-file digest snapshot for one managed run."""
    files = source_snapshot_candidate_files(context.topic_dir)
    if context.registry.available and context.registry.path.is_file():
        files.append(context.registry.path)
    files.extend(command_source_files(context.command.command, context.repo_root))
    dirty_files, missing_dirty_paths = dirty_source_files(
        context.repo_root,
        context.git.status_short,
    )
    files.extend(dirty_files)
    runner_path = Path(__file__).resolve()
    if path_is_relative_to(runner_path, context.repo_root):
        files.append(runner_path)
        external_files: list[Path] = []
    else:
        external_files = [runner_path]
    unique_files = unique_paths(files)
    repo_files = [
        path for path in unique_files if path_is_relative_to(path, context.repo_root)
    ]
    external_records = [
        external_file_record(path) for path in unique_paths(external_files)
    ]
    return {
        **context.identity.to_dict(),
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "base_dir": str(context.repo_root),
        "excluded_topic_dirs": sorted(EXCLUDED_SOURCE_SNAPSHOT_DIRS),
        "git": {
            "branch": context.git.branch,
            "commit": context.git.commit,
            "dirty": bool(context.git.status_short),
            "status_short": context.git.status_short,
            "missing_dirty_paths": missing_dirty_paths,
        },
        "command_source_files": [
            str(path.relative_to(context.repo_root))
            for path in command_source_files(context.command.command, context.repo_root)
            if path_is_relative_to(path, context.repo_root)
        ],
        "dirty_file_count": len(dirty_files),
        "file_count": len(repo_files),
        "external_file_count": len(external_records),
        "files": [file_record(path, context.repo_root) for path in repo_files],
        "external_files": external_records,
    }


def copy_source_config_snapshot(context: RunContext) -> dict[str, object]:
    """Copy the checked-in topic config into the run directory."""
    source_config = context.topic_dir / "config.yaml"
    if not source_config.is_file():
        return {
            "status": "missing",
            "source_path": str(source_config),
            "snapshot_path": str(context.paths.config_source_path),
        }
    shutil.copy2(source_config, context.paths.config_source_path)
    return {
        "status": "copied",
        "source_path": str(source_config),
        "snapshot_path": str(context.paths.config_source_path),
        "sha256": load_file_sha256(context.paths.config_source_path),
        "bytes": context.paths.config_source_path.stat().st_size,
    }


def build_command_manifest(context: RunContext) -> dict[str, object]:
    """Build the resolved-command manifest for one run."""
    return {
        **context.identity.to_dict(),
        "schema_version": 1,
        "created_at_utc": utc_now(),
        "command": context.command.command,
        "command_text": shlex.join(context.command.command),
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "cwd": str(context.repo_root),
        "paths": {
            "result_dir": str(context.paths.result_dir),
            "raw_dir": str(context.paths.raw_dir),
            "log_dir": str(context.paths.log_dir),
            "run_log": str(context.paths.log_path),
            "stdout_log": str(context.paths.stdout_log_path),
            "stderr_log": str(context.paths.stderr_log_path),
            "startup_log": str(context.paths.startup_log_path),
        },
    }


def append_startup_event(
    context: RunContext,
    event: str,
    payload: dict[str, object],
) -> None:
    """Append one startup chronology event."""
    context.paths.startup_log_path.parent.mkdir(parents=True, exist_ok=True)
    entry: dict[str, object] = {
        **context.identity.to_dict(),
        "timestamp_utc": utc_now(),
        "event": event,
    }
    entry.update(payload)
    with context.paths.startup_log_path.open("a", encoding="utf-8") as handle:
        json.dump(entry, handle, sort_keys=True, ensure_ascii=True)
        handle.write("\n")


def build_artifact_manifest(context: RunContext) -> dict[str, object]:
    """Build a digest inventory for all current run artifacts."""
    files = [
        path
        for path in sorted(context.paths.result_dir.rglob("*"))
        if path.is_file() and path != context.paths.artifact_manifest_path
    ]
    return {
        **context.identity.to_dict(),
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "result_dir": str(context.paths.result_dir),
        "self_excluded": str(context.paths.artifact_manifest_path),
        "artifact_count": len(files),
        "artifacts": [file_record(path, context.paths.result_dir) for path in files],
    }


def merge_unique_strings(*groups: list[str]) -> list[str]:
    """Return one deduplicated list preserving first appearance order."""
    return list(dict.fromkeys(value for group in groups for value in group))


def validate_eval_artifact_patterns(patterns: list[str], key: str) -> list[str]:
    """Validate one eval artifact pattern list."""
    for pattern in patterns:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute():
            raise ValueError(
                f"{key} must stay relative to result/<variant>/<run_name>: {pattern}"
            )
        if ".." in pattern_path.parts:
            raise ValueError(f"{key} must not escape result/<variant>/<run_name>: {pattern}")
    return patterns


def resolve_eval_artifact_patterns(
    registry_defaults: dict[str, object],
    registry_entry: dict[str, object],
) -> EvalArtifactPatterns:
    """Return required and optional eval artifact patterns for one run."""
    default_required = string_list(
        registry_defaults.get("required_eval_artifacts"),
        "defaults.required_eval_artifacts",
    )
    default_optional = string_list(
        registry_defaults.get("optional_eval_artifacts"),
        "defaults.optional_eval_artifacts",
    )
    entry_required = string_list(
        registry_entry.get("required_eval_artifacts"),
        "topics.required_eval_artifacts",
    )
    entry_optional = string_list(
        registry_entry.get("optional_eval_artifacts"),
        "topics.optional_eval_artifacts",
    )
    required = merge_unique_strings(
        list(DEFAULT_REQUIRED_EVAL_ARTIFACTS),
        default_required,
        entry_required,
    )
    optional = merge_unique_strings(default_optional, entry_optional)
    optional = [pattern for pattern in optional if pattern not in required]
    return EvalArtifactPatterns(
        required=validate_eval_artifact_patterns(required, "required_eval_artifacts"),
        optional=validate_eval_artifact_patterns(optional, "optional_eval_artifacts"),
    )


def load_file_sha256(path: Path) -> str:
    """Return the sha256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(FILE_READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def artifact_kind(path: Path) -> str:
    """Infer one artifact kind from the file suffix."""
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    if suffix in {".txt", ".log", ".md"}:
        return "text"
    if suffix in {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".html"}:
        return "rendered"
    return "file"


def load_line_count(path: Path) -> int:
    """Return the number of lines in one file without assuming UTF-8 text."""
    count = 0
    saw_bytes = False
    last_byte = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(FILE_READ_CHUNK_BYTES)
            if not chunk:
                break
            saw_bytes = True
            last_byte = chunk[-1:]
            count += chunk.count(b"\n")
    if saw_bytes and last_byte != b"\n":
        count += 1
    return count


def is_managed_run_artifact(path: Path, result_dir: Path) -> bool:
    """Return whether one path is a reserved managed artifact."""
    return str(path.relative_to(result_dir)) in MANAGED_RUN_ARTIFACTS


def load_eval_artifact(
    path: Path, result_dir: Path, patterns: list[str]
) -> dict[str, object]:
    """Load eval artifact metadata for one collected file."""
    artifact: dict[str, object] = {
        "relative_path": str(path.relative_to(result_dir)),
        "kind": artifact_kind(path),
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
        "matched_patterns": patterns,
    }
    if artifact["kind"] in {"jsonl", "text", "csv"}:
        artifact["line_count"] = load_line_count(path)
    return artifact


def load_eval_artifacts(
    result_dir: Path,
    *,
    topic: str,
    variant: str,
    run_name: str,
    patterns: EvalArtifactPatterns,
) -> dict[str, object]:
    """Collect eval artifact metadata from one result directory."""
    matched_patterns_by_path: dict[Path, list[str]] = {}
    missing_required_patterns: list[str] = []

    for pattern in patterns.required:
        matches = sorted(
            path
            for path in result_dir.glob(pattern)
            if path.is_file() and not is_managed_run_artifact(path, result_dir)
        )
        if not matches:
            missing_required_patterns.append(pattern)
            continue
        for match in matches:
            matched_patterns_by_path.setdefault(match, []).append(pattern)

    for pattern in patterns.optional:
        for match in sorted(
            path
            for path in result_dir.glob(pattern)
            if path.is_file() and not is_managed_run_artifact(path, result_dir)
        ):
            matched_patterns_by_path.setdefault(match, []).append(pattern)

    artifacts: list[dict[str, object]] = []
    for path in sorted(
        matched_patterns_by_path,
        key=lambda item: str(item.relative_to(result_dir)),
    ):
        artifacts.append(
            load_eval_artifact(path, result_dir, matched_patterns_by_path[path])
        )

    return {
        **ExperimentIdentity(topic=topic, variant=variant, run_name=run_name).to_dict(),
        "result_dir": str(result_dir),
        "collected_at_utc": utc_now(),
        "required_patterns": patterns.required,
        "optional_patterns": patterns.optional,
        "missing_required_patterns": missing_required_patterns,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def format_command(command: list[str], placeholders: dict[str, str]) -> list[str]:
    """Format command tokens with run placeholders."""
    if command and command[0] == "--":
        command = command[1:]
    return [token.format(**placeholders) for token in command]


def normalize_registered_command_kind(command_kind: str) -> str:
    """Return the canonical registered command kind."""
    normalized = LEGACY_REGISTERED_COMMAND_ALIASES.get(command_kind, command_kind)
    if normalized not in REGISTERED_COMMAND_KINDS:
        allowed = ", ".join(REGISTERED_COMMAND_KINDS)
        raise ValueError(f"unsupported registered command {command_kind!r}; expected {allowed}")
    return normalized


def registered_command_keys(command_kind: str) -> tuple[str, ...]:
    """Return preferred registry keys for one command kind."""
    normalized = normalize_registered_command_kind(command_kind)
    keys = [f"{normalized}_inner_command"]
    if normalized == "default":
        keys.append("smoke_inner_command")
    return tuple(keys)


def command_from_registry(
    registry_entry: dict[str, object],
    command_kind: str,
    placeholders: dict[str, str],
) -> list[str]:
    """Return one formatted command from the registry."""
    checked_keys = registered_command_keys(command_kind)
    raw_command: str | None = None
    for command_key in checked_keys:
        raw_value = registry_entry.get(command_key)
        if isinstance(raw_value, str) and raw_value.strip():
            raw_command = raw_value
            break
    else:
        raise ValueError(f"registry entry is missing one of {', '.join(checked_keys)}")
    assert raw_command is not None
    return [token.format(**placeholders) for token in shlex.split(raw_command)]


def resolve_registered_command_match(
    registry: RegistryContext, command: list[str], placeholders: dict[str, str]
) -> str | None:
    """Return the matching registered command kind when one exists."""
    if not registry.available:
        return None
    for command_kind in REGISTERED_COMMAND_KINDS:
        try:
            registered_command = command_from_registry(
                registry.entry, command_kind, placeholders
            )
        except ValueError:
            continue
        if registered_command == command:
            return command_kind
    return None


def resolve_topic_dir(
    repo_root: Path, identity: RunIdentity, registry: RegistryContext
) -> Path:
    """Resolve the experiment topic directory."""
    if registry.available:
        topic_dir_raw = registry.entry.get("topic_dir")
        if not isinstance(topic_dir_raw, str):
            raise ValueError(
                f"registry entry for {identity.topic!r} is missing topic_dir"
            )
        return repo_root / topic_dir_raw
    return repo_root / "experiments" / identity.topic


def resolve_report_path(
    repo_root: Path,
    registry: RegistryContext,
    identity: RunIdentity,
    report_arg: str,
) -> Path:
    """Resolve the report path for one run."""
    if report_arg:
        candidate = Path(report_arg)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        return contained_path(repo_root, candidate)
    if registry.available:
        registry_report_root = registry.entry.get(
            "report_root"
        ) or registry.defaults.get("report_root")
        if isinstance(registry_report_root, str):
            return contained_path(
                repo_root,
                repo_root
                / registry_report_root
                / identity.topic
                / identity.variant
                / f"{identity.run_name}.md",
            )
    return contained_path(repo_root, repo_root / report_relative_path(identity))


def build_run_paths(
    topic_dir: Path, identity: RunIdentity, report_path: Path
) -> RunPaths:
    """Derive result and raw paths from the canonical complete identity."""
    topic_dir = topic_dir.absolute()
    repo_root = topic_dir.parent.parent
    expected_topic_dir = (repo_root / "experiments" / identity.topic).absolute()
    if topic_dir != expected_topic_dir:
        raise ExperimentIdentityError(
            "topic directory must be experiments/<topic> for the identity"
        )
    if topic_dir.is_symlink() or topic_dir.resolve() != topic_dir:
        raise ExperimentIdentityError(
            f"topic directory must not escape by symlink: {topic_dir}"
        )
    if not topic_dir.is_dir():
        raise ExperimentIdentityError(f"topic directory does not exist: {topic_dir}")

    result_dir = (repo_root / result_relative_path(identity)).absolute()
    raw_dir = (repo_root / raw_relative_path(identity)).absolute()
    for kind, run_dir in (("result", result_dir), ("raw", raw_dir)):
        root = topic_dir / kind
        variant_root = root / identity.variant
        for label, directory in (
            (f"{kind} root", root),
            (f"variant {kind} root", variant_root),
            (f"{kind} directory", run_dir),
        ):
            if directory.is_symlink() or directory.resolve() != directory:
                raise ExperimentIdentityError(
                    f"{label} must not escape by symlink: {directory}"
                )
            if directory.exists() and not directory.is_dir():
                raise ExperimentIdentityError(f"{label} must be a directory: {directory}")

    expected_report_path = (repo_root / report_relative_path(identity)).absolute()
    report_path = report_path.absolute()
    if report_path != expected_report_path:
        raise ExperimentIdentityError(
            "report path must match complete identity: "
            f"expected {expected_report_path}, got {report_path}"
        )
    if report_path.is_symlink() or report_path.resolve() != report_path:
        raise ExperimentIdentityError(
            f"report path must not escape by symlink: {report_path}"
        )

    log_dir = result_dir / "logs"
    return RunPaths(
        result_dir=result_dir,
        raw_dir=raw_dir,
        log_dir=log_dir,
        report_path=report_path,
        manifest_path=result_dir / "run_manifest.json",
        eval_manifest_path=result_dir / "eval_manifest.json",
        artifact_manifest_path=result_dir / ARTIFACT_MANIFEST_NAME,
        command_manifest_path=result_dir / COMMAND_MANIFEST_NAME,
        environment_manifest_path=result_dir / ENVIRONMENT_MANIFEST_NAME,
        source_snapshot_path=result_dir / SOURCE_SNAPSHOT_NAME,
        config_source_path=result_dir / CONFIG_SOURCE_SNAPSHOT_NAME,
        config_path=result_dir / "config.json",
        log_path=result_dir / "run.log",
        startup_log_path=log_dir / STARTUP_LOG_NAME,
        stdout_log_path=log_dir / STDOUT_LOG_NAME,
        stderr_log_path=log_dir / STDERR_LOG_NAME,
    )


def build_placeholders(
    repo_root: Path, identity: RunIdentity, topic_dir: Path, paths: RunPaths
) -> dict[str, str]:
    """Build command placeholder values for one run."""
    return {
        "repo_root": str(repo_root),
        "topic_dir": str(topic_dir),
        "variant": identity.variant,
        "run_name": identity.run_name,
        "run_dir": str(paths.result_dir),
        "raw_dir": str(paths.raw_dir),
        "log_dir": str(paths.log_dir),
        "report_path": str(paths.report_path),
        "manifest_path": str(paths.manifest_path),
        "eval_manifest_path": str(paths.eval_manifest_path),
        "artifact_manifest_path": str(paths.artifact_manifest_path),
        "command_manifest_path": str(paths.command_manifest_path),
        "environment_manifest_path": str(paths.environment_manifest_path),
        "source_snapshot_path": str(paths.source_snapshot_path),
        "config_source_path": str(paths.config_source_path),
        "config_path": str(paths.config_path),
        "log_path": str(paths.log_path),
        "startup_log_path": str(paths.startup_log_path),
        "stdout_log_path": str(paths.stdout_log_path),
        "stderr_log_path": str(paths.stderr_log_path),
    }


def load_explicit_config(
    config_json_path: str, config_pairs: list[str]
) -> dict[str, object]:
    """Load explicit CLI config values."""
    explicit_config: dict[str, object] = {}
    if config_json_path:
        explicit_config.update(load_config_json(Path(config_json_path).resolve()))
    explicit_config.update(parse_config_pairs(config_pairs))
    return explicit_config


def select_command(
    use_registered_command: str,
    manual_command: list[str],
    registry: RegistryContext,
    placeholders: dict[str, str],
) -> CommandSelection:
    """Select the inner command for one managed run."""
    if use_registered_command and manual_command:
        raise ValueError(
            "do not pass both a manual command and --use-registered-command"
        )
    if use_registered_command:
        if not registry.available:
            raise ValueError(
                "--use-registered-command requires experiments/registry.toml"
            )
        registered_kind = normalize_registered_command_kind(use_registered_command)
        command = command_from_registry(
            registry.entry, registered_kind, placeholders
        )
        return CommandSelection(
            command=command,
            source=f"registered:{registered_kind}",
            registered_match=registered_kind,
        )
    command = format_command(manual_command, placeholders)
    return CommandSelection(
        command=command,
        source="manual",
        registered_match=resolve_registered_command_match(
            registry, command, placeholders
        ),
    )


def build_run_context(args: argparse.Namespace) -> RunContext:
    """Build setup context for one managed run."""
    repo_root = Path(args.repo_root).resolve()
    topic = validate_segment(args.topic, "topic")
    variant = validate_segment(args.variant, "variant")
    run_name = validate_segment(
        args.run_name or f"{topic}_{variant}_{compact_timestamp()}", "run_name"
    )
    identity = RunIdentity(topic=topic, variant=variant, run_name=run_name)
    registry = load_registry_context(
        resolve_registry_path(repo_root, args.registry or ""),
        identity.topic,
    )
    topic_dir = resolve_topic_dir(repo_root, identity, registry)
    topic_dir = contained_path(repo_root, topic_dir)
    canonical_topic_dir = contained_path(
        repo_root, repo_root / "experiments" / identity.topic
    )
    if topic_dir != canonical_topic_dir:
        raise ValueError(
            "topic directory must match canonical identity path: "
            f"expected {canonical_topic_dir}, got {topic_dir}"
        )
    if not topic_dir.is_dir():
        raise ValueError(f"topic directory does not exist: {topic_dir}")
    report_path = resolve_report_path(
        repo_root,
        registry,
        identity,
        args.report_path or "",
    )
    expected_report_path = contained_path(repo_root, repo_root / report_relative_path(identity))
    if report_path != expected_report_path:
        raise ValueError(
            "report path must match complete identity: "
            f"expected {expected_report_path}, got {report_path}"
        )
    paths = build_run_paths(topic_dir, identity, report_path)
    placeholders = build_placeholders(repo_root, identity, topic_dir, paths)
    command = select_command(
        args.use_registered_command or "",
        args.command,
        registry,
        placeholders,
    )
    return RunContext(
        repo_root=repo_root,
        identity=identity,
        topic_dir=topic_dir,
        paths=paths,
        registry=registry,
        command=command,
        created_at=utc_now(),
        git=load_git_snapshot(repo_root),
    )


def write_initial_artifacts(
    context: RunContext,
    manifest: dict[str, object],
    run_config: dict[str, object],
    skip_report_init: bool,
) -> dict[str, object]:
    """Write run directories, initial JSON files, and optional report stub."""
    context.paths.log_dir.mkdir(parents=True, exist_ok=True)
    source_config = copy_source_config_snapshot(context)
    run_config["source_config"] = source_config
    manifest["source_config"] = source_config
    write_json(context.paths.config_path, run_config)
    write_json(context.paths.command_manifest_path, build_command_manifest(context))
    write_json(
        context.paths.environment_manifest_path,
        captured_environment(build_run_environment(context)),
    )
    write_json(context.paths.source_snapshot_path, build_source_snapshot(context))
    write_manifest(context.paths.manifest_path, manifest)
    append_startup_event(
        context,
        "initialized",
        {
            "result_dir": str(context.paths.result_dir),
            "raw_dir": str(context.paths.raw_dir),
            "command_manifest": str(context.paths.command_manifest_path),
            "environment_manifest": str(context.paths.environment_manifest_path),
            "source_snapshot": str(context.paths.source_snapshot_path),
        },
    )

    return source_config


def reserve_run_paths(
    context: RunContext, skip_report_init: bool
) -> ReservationReceipt:
    """Reserve result, raw, and optional report as one complete identity."""
    if context.paths.report_path.exists():
        raise ValueError(
            f"report already exists for identity: {context.paths.report_path}"
        )
    result_parent = context.paths.result_dir.parent
    raw_parent = context.paths.raw_dir.parent
    result_parent_existed = result_parent.exists()
    raw_parent_existed = raw_parent.exists()
    result_parent.mkdir(parents=True, exist_ok=True)
    result_parent_inode = result_parent.stat().st_ino
    try:
        context.paths.result_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        if not result_parent_existed:
            _remove_owned_empty_dir(result_parent, result_parent_inode)
        raise ValueError(
            f"result directory already exists for identity: {context.paths.result_dir}"
        ) from exc
    result_inode = context.paths.result_dir.stat().st_ino

    try:
        raw_parent.mkdir(parents=True, exist_ok=True)
        raw_parent_inode = raw_parent.stat().st_ino
        context.paths.raw_dir.mkdir(exist_ok=False)
    except BaseException as exc:
        _remove_owned_empty_dir(context.paths.result_dir, result_inode)
        if not result_parent_existed:
            _remove_owned_empty_dir(result_parent, result_parent_inode)
        if raw_parent.exists() and not raw_parent_existed:
            _remove_owned_empty_dir(raw_parent, raw_parent.stat().st_ino)
        if isinstance(exc, FileExistsError):
            raise ValueError(
                f"raw directory already exists for identity: {context.paths.raw_dir}"
            ) from exc
        raise
    raw_inode = context.paths.raw_dir.stat().st_ino

    token = secrets.token_hex(24)
    marker_path = context.paths.result_dir / RESERVATION_MARKER_NAME
    marker_payload = {
        "schema": RESERVATION_MARKER_SCHEMA,
        "state": "reserved",
        "token": token,
        "result_inode": result_inode,
        "raw_inode": raw_inode,
        **context.identity.to_dict(),
    }
    try:
        with marker_path.open("x", encoding="utf-8") as marker_file:
            marker_file.write(json.dumps(marker_payload, sort_keys=True))
            marker_file.write("\n")
            marker_file.flush()
            os.fsync(marker_file.fileno())
        marker_inode = marker_path.stat().st_ino
    except BaseException:
        _remove_owned_empty_dir(context.paths.raw_dir, raw_inode)
        _remove_owned_empty_dir(context.paths.result_dir, result_inode)
        if not raw_parent_existed:
            _remove_owned_empty_dir(raw_parent, raw_parent_inode)
        if not result_parent_existed:
            _remove_owned_empty_dir(result_parent, result_parent_inode)
        raise

    report_parent = context.paths.report_path.parent
    report_parent_existed = report_parent.exists()
    receipt = ReservationReceipt(
        result_dir=context.paths.result_dir,
        raw_dir=context.paths.raw_dir,
        report_path=context.paths.report_path,
        report_content=None,
        result_parent=result_parent,
        result_parent_preexisted=result_parent_existed,
        raw_parent=raw_parent,
        raw_parent_preexisted=raw_parent_existed,
        report_parent=report_parent,
        report_parent_preexisted=report_parent_existed,
        token=token,
        marker_path=marker_path,
        result_inode=result_inode,
        raw_inode=raw_inode,
        marker_inode=marker_inode,
        report_reserved=False,
        report_inode=None,
        result_parent_inode=result_parent_inode,
        raw_parent_inode=raw_parent_inode,
        report_parent_inode=None,
        identity=context.identity,
    )
    try:
        if not skip_report_init:
            report_parent.mkdir(parents=True, exist_ok=True)
            report_parent_inode = report_parent.stat().st_ino
            receipt = replace(receipt, report_parent_inode=report_parent_inode)
            report_content = render_report_stub(context)
            with context.paths.report_path.open("x", encoding="utf-8") as handle:
                report_inode = os.fstat(handle.fileno()).st_ino
                receipt = replace(
                    receipt,
                    report_content=report_content,
                    report_reserved=True,
                    report_inode=report_inode,
                    report_parent_inode=report_parent_inode,
                )
                handle.write(report_content)
                handle.flush()
                os.fsync(handle.fileno())
    except BaseException:
        rollback_empty_reservation(receipt)
        raise
    return receipt


def _remove_owned_empty_dir(path: Path, inode: int) -> bool:
    """Remove a directory only when its current inode is the recorded one."""
    try:
        stat_result = path.stat()
        if path.is_symlink() or stat_result.st_ino != inode:
            return False
        if any(path.iterdir()):
            return False
        path.rmdir()
        return True
    except OSError:
        return False


def _reservation_parent_matches(
    path: Path, preexisted: bool, inode: int | None
) -> bool:
    """Prove ownership of an observed parent before attempting cleanup."""
    if preexisted or inode is None:
        return True
    try:
        stat_result = path.stat()
    except OSError:
        return False
    return path.is_dir() and not path.is_symlink() and stat_result.st_ino == inode


def _reservation_owner_matches(receipt: ReservationReceipt) -> bool:
    """Verify token, identity, and result/raw inode ownership before cleanup."""
    try:
        result_stat = receipt.result_dir.stat()
        raw_stat = receipt.raw_dir.stat()
        marker_stat = receipt.marker_path.stat()
        if (
            receipt.result_dir.is_symlink()
            or receipt.raw_dir.is_symlink()
            or receipt.marker_path.is_symlink()
        ):
            return False
        if result_stat.st_ino != receipt.result_inode:
            return False
        if raw_stat.st_ino != receipt.raw_inode:
            return False
        if marker_stat.st_ino != receipt.marker_inode:
            return False
        marker = load_json_file(receipt.marker_path)
        if not isinstance(marker, Mapping):
            return False
        if set(marker) != {
            "schema",
            "state",
            "token",
            "result_inode",
            "raw_inode",
            "identity",
        }:
            return False
        if marker.get("schema") != RESERVATION_MARKER_SCHEMA:
            return False
        if marker.get("state") != "reserved":
            return False
        if marker.get("token") != receipt.token:
            return False
        if marker.get("result_inode") != receipt.result_inode:
            return False
        if marker.get("raw_inode") != receipt.raw_inode:
            return False
        if identity_from_manifest(marker) != receipt.identity:
            return False
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return True


def rollback_empty_reservation(receipt: ReservationReceipt) -> bool:
    """Remove only a receipt-owned empty result/raw/report reservation."""
    if not _reservation_owner_matches(receipt):
        return False
    for path, preexisted, inode in (
        (
            receipt.result_parent,
            receipt.result_parent_preexisted,
            receipt.result_parent_inode,
        ),
        (receipt.raw_parent, receipt.raw_parent_preexisted, receipt.raw_parent_inode),
        (
            receipt.report_parent,
            receipt.report_parent_preexisted,
            receipt.report_parent_inode,
        ),
    ):
        if not _reservation_parent_matches(path, preexisted, inode):
            return False
    try:
        result_children = list(receipt.result_dir.iterdir())
        raw_children = list(receipt.raw_dir.iterdir())
    except OSError:
        return False
    if result_children != [receipt.marker_path] or raw_children:
        return False

    if receipt.report_reserved:
        if receipt.report_inode is None or receipt.report_parent_inode is None:
            return False
        try:
            report_stat = receipt.report_path.stat()
            report_parent_stat = receipt.report_parent.stat()
        except OSError:
            return False
        if (
            receipt.report_path.is_symlink()
            or report_stat.st_ino != receipt.report_inode
            or report_parent_stat.st_ino != receipt.report_parent_inode
        ):
            return False
    try:
        receipt.raw_dir.rmdir()
        receipt.marker_path.unlink()
        receipt.result_dir.rmdir()
        if receipt.report_reserved:
            receipt.report_path.unlink()
    except OSError:
        return False
    for parent, preexisted, inode in (
        (
            receipt.report_parent,
            receipt.report_parent_preexisted,
            receipt.report_parent_inode,
        ),
        (receipt.raw_parent, receipt.raw_parent_preexisted, receipt.raw_parent_inode),
        (
            receipt.result_parent,
            receipt.result_parent_preexisted,
            receipt.result_parent_inode,
        ),
    ):
        if not preexisted and inode is not None:
            _remove_owned_empty_dir(parent, inode)
    return True


def release_reservation_marker(receipt: ReservationReceipt) -> bool:
    """Remove a receipt-owned marker after initial artifacts are durable."""
    if not _reservation_owner_matches(receipt):
        return False
    try:
        receipt.marker_path.unlink()
    except OSError:
        return False
    return True


def source_config_error(source_config: dict[str, object]) -> str | None:
    """Return a preflight error when the checked-in config snapshot is missing."""
    if source_config.get("status") == "copied":
        return None
    return (
        "missing required source config.yaml: "
        f"{source_config.get('source_path')}; create the checked-in topic config "
        "before running a managed experiment"
    )


def build_run_environment(context: RunContext) -> dict[str, str]:
    """Build the environment for the inner experiment command."""
    env = dict(os.environ)
    env.update(
        {
            "EXPERIMENT_RUN_NAME": context.identity.run_name,
            "EXPERIMENT_TOPIC": context.identity.topic,
            "EXPERIMENT_VARIANT": context.identity.variant,
            "EXPERIMENT_RUN_DIR": str(context.paths.result_dir),
            "EXPERIMENT_RAW_DIR": str(context.paths.raw_dir),
            "EXPERIMENT_LOG_DIR": str(context.paths.log_dir),
            "EXPERIMENT_REPORT_PATH": str(context.paths.report_path),
            "EXPERIMENT_RUN_MANIFEST": str(context.paths.manifest_path),
            "EXPERIMENT_EVAL_MANIFEST": str(context.paths.eval_manifest_path),
            "EXPERIMENT_ARTIFACT_MANIFEST": str(context.paths.artifact_manifest_path),
            "EXPERIMENT_COMMAND_MANIFEST": str(context.paths.command_manifest_path),
            "EXPERIMENT_CONFIG_PATH": str(context.paths.config_path),
            "EXPERIMENT_SOURCE_CONFIG_PATH": str(context.paths.config_source_path),
            "EXPERIMENT_SOURCE_SNAPSHOT": str(context.paths.source_snapshot_path),
            "EXPERIMENT_RUN_LOG": str(context.paths.log_path),
            "EXPERIMENT_STARTUP_LOG": str(context.paths.startup_log_path),
            "EXPERIMENT_STDOUT_LOG": str(context.paths.stdout_log_path),
            "EXPERIMENT_STDERR_LOG": str(context.paths.stderr_log_path),
        }
    )
    return env


def finalize_run_manifest(
    context: RunContext,
    manifest: dict[str, object],
    start_monotonic: float,
    exit_code: int,
    patterns: EvalArtifactPatterns,
) -> None:
    """Collect eval artifacts and write the final run manifest."""
    eval_collection = load_eval_artifacts(
        context.paths.result_dir,
        topic=context.identity.topic,
        variant=context.identity.variant,
        run_name=context.identity.run_name,
        patterns=patterns,
    )
    write_json(context.paths.eval_manifest_path, eval_collection)
    manifest["finished_at_utc"] = utc_now()
    manifest["duration_seconds"] = round(
        time.monotonic() - start_monotonic, DURATION_ROUND_DIGITS
    )
    manifest["exit_code"] = exit_code
    manifest["status"] = "completed" if exit_code == 0 else "failed"
    manifest["eval_artifacts"] = {
        "eval_manifest_path": str(context.paths.eval_manifest_path),
        "required_patterns": patterns.required,
        "optional_patterns": patterns.optional,
        "collected_artifact_count": eval_collection["artifact_count"],
        "missing_required_patterns": eval_collection["missing_required_patterns"],
    }
    manifest["artifact_manifest"] = {
        "artifact_manifest_path": str(context.paths.artifact_manifest_path),
        "self_excluded": True,
    }
    write_manifest(context.paths.manifest_path, manifest)
    write_json(context.paths.artifact_manifest_path, build_artifact_manifest(context))


def _config_int(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _config_bool(config: Mapping[str, object], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _config_chunks(config: Mapping[str, object], run_name: str) -> tuple[str, ...]:
    value = config.get("requested_chunks", [run_name])
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError("requested_chunks must be a non-empty array of strings")
    return tuple(value)


def _resource_request_for_managed_run(
    context: RunContext,
    run_config: Mapping[str, object],
) -> ResourceRequest:
    """Translate CLI/config metadata into the one canonical resource request."""
    raw_config = run_config.get("config", {})
    if not isinstance(raw_config, Mapping):
        raise ValueError("managed run config must remain a mapping")
    config = cast(Mapping[str, object], raw_config)
    try:
        cpu_requested_set = tuple(
            sorted(
                os.sched_getaffinity(0)
                if "cpu_requested_set" not in config
                else cast(list[int], config["cpu_requested_set"])
            )
        )
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise TypedPreflightFailure(
            "cpu_capability_discovery_unavailable",
            "managed run cannot declare an authoritative CPU set",
        ) from exc
    if any(isinstance(cpu, bool) or not isinstance(cpu, int) for cpu in cpu_requested_set):
        raise ValueError("cpu_requested_set must contain integers")
    environment = build_run_environment(context)
    gpu_requested_count = _config_int(config, "gpu_requested_count", 0)
    configured_provenance = str(config.get("gpu_allocation_provenance", ""))
    if gpu_requested_count and configured_provenance not in {
        "",
        CALLER_ALLOCATION_PROVENANCE,
    }:
        raise TypedPreflightFailure(
            "gpu_allocation_provenance_conflict",
            "managed GPU execution cannot override canonical scheduler UUID provenance",
            observed_provenance=configured_provenance,
        )
    lock_root_value = "/var/lib/agent-canon/runtime/locks"
    timeout_value = config.get("maximum_timeout_seconds", 3600.0)
    if isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float)):
        raise ValueError("maximum_timeout_seconds must be a positive number")
    return ResourceRequest(
        owner_id=str(config.get("owner_id", "worker-luna")),
        parent_id=str(config.get("parent_id", "parent-sol")),
        context_id=str(config.get("context_id", "context-continuation")),
        maximum_timeout_seconds=float(timeout_value),
        argv=tuple(context.command.command),
        cwd=context.repo_root,
        environment=environment,
        integration_contract=managed_run_adapter_integration_contract(),
        plan_id=context.identity.run_name,
        run_id=context.identity.run_name,
        cpu_requested_set=cpu_requested_set,
        gpu_requested_count=gpu_requested_count,
        gpu_requested_memory_bytes=_config_int(
            config, "gpu_requested_memory_bytes", 0
        ),
        gpu_allocation_provenance=(
            CALLER_ALLOCATION_PROVENANCE if gpu_requested_count else ""
        ),
        temp_bytes=_config_int(config, "temp_bytes", 0),
        runtime_root=Path("/var/lib/agent-canon/runtime"),
        source_projection_root=Path(
            f"/workspace/reports/agents/{context.identity.run_name}/runtime"
        ),
        requested_chunks=_config_chunks(config, context.identity.run_name),
        lock_root=Path(lock_root_value),
        lock_namespace_shared_across_schedulers=True,
        lock_namespace_host_safe=True,
        lock_namespace_visibility_witness="shared-runtime-receipt",
    )


def _r5_absence(
    field_name: EvidenceAbsenceField,
    disposition: EvidenceDisposition,
    failure_kind: str | None,
) -> EvidenceAbsence:
    """Build one exact fingerprint for a missing typed evidence field."""
    payload = {
        "field_name": field_name,
        "disposition": disposition,
        "failure_kind": failure_kind,
    }
    return EvidenceAbsence(
        field_name=field_name,
        disposition=disposition,
        failure_kind=failure_kind,
        fingerprint=hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    )


def _r5_evidence_fingerprint(payload: Mapping[str, object]) -> str:
    """Fingerprint a composition-assembled typed evidence value."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def execute_managed_run(
    context: RunContext,
    run_config: Mapping[str, object],
) -> ManagedRunExecutionResult:
    """Compose the fixed owners around one admitted-runner CLI invocation."""
    request = _resource_request_for_managed_run(context, run_config)
    raw_config = run_config.get("config", {})
    config = cast(Mapping[str, object], raw_config) if isinstance(raw_config, Mapping) else {}
    source_paths = build_source_path_set(
        str(context.repo_root),
        context.identity.topic,
        context.command.command,
    )
    source_request = GpuRunRequest(
        gpu_count=request.gpu_requested_count,
        minimum_memory_bytes_per_unit=request.gpu_requested_memory_bytes,
        max_workers=1,
        host_memory_bytes=request.host_memory_bytes,
        cuda_runtime_library_path=(
            str(config["cuda_runtime_library_path"])
            if isinstance(config.get("cuda_runtime_library_path"), str)
            else None
        ),
        environment=dict(request.environment),
        source_root=str(context.repo_root),
        runtime_route="MANAGED_CONTAINER",
        source_paths=source_paths,
        planned_chunk_ids=request.requested_chunks,
    )
    admission_context = RunGpuAdmissionContext.create(source_request)
    source_freeze = None
    runtime_identity = None
    admission: RunGpuAdmissionReceipt | None = None
    frozen_plan = None
    admitted_environment = None
    reservation_transaction: GpuReservationTransaction | None = None
    final_probe = None
    reservation_dispositions: list[FdReleaseEvidence] = []
    release_failures: list[FailureRecord] = []
    coverage_lock_readback: LockReadback | None = None
    coverage_environment: Mapping[str, str] | None = None
    coverage_processes: tuple[ProcessOccupancyEvidence, ...] | None = None
    coverage_concurrent: ConcurrentRunEvidence | None = None
    coverage_mig: MigEvidence | None = None
    coverage_visibility: UuidVisibilityEvidence | None = None
    coverage_lock_placement: LockPlacementEvidence | None = None
    coverage_descendants: DescendantRetentionEvidence | None = None
    coverage_attempted: set[EvidenceAbsenceField] = set()
    primary_exception: BaseException | None = None
    lifecycle_failure: FailureRecord | None = None
    execution_result: ManagedRunExecutionResult | None = None
    runner_lifecycle: ManagedRunLifecycleEvidence | None = None
    runner_invoked = False
    admission_context.register_release_failure_sink(release_failures.append)
    with admission_context:
        try:
            source_owner = SourceFreezeOwner(str(context.paths.result_dir))
            coverage_attempted.add("source_freeze_evidence")
            source_freeze = source_owner.freeze(source_request)
            admission_context.register_release(source_owner.close)

            runtime_root = os.environ.get(
                "AGENT_CANON_SHARED_RUNTIME_SOURCE",
                HOST_RUNTIME_ROOT,
            )
            if runtime_root != HOST_RUNTIME_ROOT:
                raise TypedPreflightFailure(
                    "runtime_identity_path_mismatch",
                    "managed execution requires the exact shared runtime root",
                    runtime_root=runtime_root,
                )
            expected_provision_path = (
                f"{HOST_RUNTIME_ROOT}/shared-runtime-provision.json"
            )
            provision_path = os.environ.get(
                "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT",
                expected_provision_path,
            )
            if provision_path != expected_provision_path:
                raise TypedPreflightFailure(
                    "runtime_identity_path_mismatch",
                    "managed execution requires the exact provision receipt path",
                    provision_path=provision_path,
                )
            provision = read_shared_runtime_provision(provision_path)
            readback = read_shared_runtime_readback(
                f"{HOST_RUNTIME_ROOT}/shared-runtime-readback.json"
            )
            runtime_identity = RuntimeIdentityReader().read(provision, readback)

            probe = NvidiaSMIResourceProbe.discover(
                request.environment,
                gpu_requested_count=request.gpu_requested_count,
                runtime_root=request.runtime_root,
            )
            initial_observation = probe.observe()
            inventory = initial_observation.nvidia_inventory
            occupied_initial = ()
            if request.gpu_requested_count:
                if inventory is None:
                    raise TypedPreflightFailure(
                        "gpu_inventory_unproven",
                        "GPU admission requires the strict NVIDIA inventory owner output",
                    )
                namespace_inode = os.stat("/proc/self/ns/pid").st_ino
                occupancy_initial = GpuProcessOccupancyProbe(
                    inventory=inventory,
                    namespace_inode=namespace_inode,
                    processes=initial_observation.process_identities,
                    process_inventory_disposition=(
                        "COMPLETE_EMPTY"
                        if not initial_observation.process_identities
                        else "COMPLETE"
                    ),
                    unknown_gpu_ids=initial_observation.unknown_gpu_ids,
                ).observe()
                occupied_initial = occupancy_initial.occupied_uuids
                unknown_initial = occupancy_initial.unknown_uuids
                candidates = tuple(sorted(initial_observation.caller_allocated_ids))
                eligible = tuple(
                    uuid
                    for uuid in candidates
                    if uuid not in occupied_initial
                    and uuid not in unknown_initial
                    and initial_observation.free_memory_bytes.get(uuid, 0)
                    >= request.gpu_requested_memory_bytes
                )
                reservation_transaction = GpuReservationTransaction(request.lock_root)

                def release_reservation() -> None:
                    if runner_invoked and not _lifecycle_quiescence_is_proven(
                        runner_lifecycle
                    ):
                        raise TypedPreflightFailure(
                            "gpu_reservation_release_blocked",
                            "GPU reservation remains held until admitted-runner descendant quiescence is proven",
                        )
                    reservation_dispositions.extend(reservation_transaction.close())

                coverage_attempted.add("lock_readback")
                reservation = reservation_transaction.try_reserve(
                    eligible,
                    occupied_uuids=occupied_initial,
                    requested_count=request.gpu_requested_count,
                )
                admission_context.register_release(release_reservation)
                if (
                    reservation.disposition != "ACQUIRED"
                    or len(reservation.selected_uuids) != request.gpu_requested_count
                ):
                    raise TypedPreflightFailure(
                        "gpu_candidate_unavailable",
                        "the exact UUID candidate frontier could not satisfy the request",
                        candidate_uuids=candidates,
                        eligible_uuids=eligible,
                        selected_uuids=reservation.selected_uuids,
                    )
                final_probe = NvidiaSMIResourceProbe.discover(
                    request.environment,
                    gpu_requested_count=request.gpu_requested_count,
                    runtime_root=request.runtime_root,
                )
                final_observation = final_probe.observe()
                final_inventory = final_observation.nvidia_inventory
                if (
                    final_inventory is None
                    or final_observation.observation_event_id
                    == initial_observation.observation_event_id
                ):
                    raise TypedPreflightFailure(
                        "gpu_run_admission_raced",
                        "final NVIDIA evidence did not provide a new admission snapshot",
                    )
                coverage_attempted.add("actual_gpu_processes")
                final_occupancy = GpuProcessOccupancyProbe(
                    inventory=final_inventory,
                    namespace_inode=namespace_inode,
                    processes=final_observation.process_identities,
                    process_inventory_disposition=(
                        "COMPLETE_EMPTY"
                        if not final_observation.process_identities
                        else "COMPLETE"
                    ),
                    unknown_gpu_ids=final_observation.unknown_gpu_ids,
                ).observe()
                selected = reservation.selected_uuids
                occupied_final = final_occupancy.occupied_uuids
                unknown_final = final_occupancy.unknown_uuids
                coverage_processes = (occupancy_initial, final_occupancy)
                coverage_attempted.add("concurrent_run_evidence")
                coverage_attempted.add("mig_evidence")
                coverage_concurrent = ConcurrentRunEvidence(
                    initial_snapshot_fingerprint=initial_observation.fingerprint,
                    admission_snapshot_fingerprint=final_observation.fingerprint,
                    final_snapshot_fingerprint=final_observation.fingerprint,
                    initial_event_id=initial_observation.observation_event_id,
                    admission_event_id=final_observation.observation_event_id,
                    final_event_id=final_observation.observation_event_id,
                    fingerprint=_r5_evidence_fingerprint(
                        {
                            "initial": initial_observation.fingerprint,
                            "admission": final_observation.fingerprint,
                            "final": final_observation.fingerprint,
                        }
                    ),
                )
                coverage_mig = MigEvidence(
                    parent_by_uuid={
                        join.mig_uuid: join.parent_uuid for join in final_inventory.joins
                    },
                    executable_leaf_uuids=final_inventory.mig_uuids,
                    selected_physical_uuids=tuple(
                        uuid
                        for uuid in selected
                        if uuid in final_inventory.physical_uuids
                    ),
                    fingerprint=_r5_evidence_fingerprint(
                        {
                            "parents": tuple(
                                (join.mig_uuid, join.parent_uuid)
                                for join in final_inventory.joins
                            ),
                            "leaves": final_inventory.mig_uuids,
                        }
                    ),
                )
                coverage_lock_readback = (
                    reservation.locks[0] if reservation.locks else None
                )
                if coverage_lock_readback is None:
                    raise TypedPreflightFailure(
                        "gpu_lock_readback_missing",
                        "GPU reservation returned no lock readback for an acquired reservation",
                    )
                coverage_lock_placement = LockPlacementEvidence(
                    runtime_root="/var/lib/agent-canon/runtime",
                    filesystem_type=coverage_lock_readback.filesystem_type,
                    filesystem_source=str(request.lock_root),
                    device=coverage_lock_readback.device,
                    inode=coverage_lock_readback.inode,
                    group_name="agent-canon-runtime",
                    mode="0660",
                    local_flock_filesystem=True,
                    fingerprint=_r5_evidence_fingerprint(
                        {
                            "runtime_root": "/var/lib/agent-canon/runtime",
                            "filesystem_type": coverage_lock_readback.filesystem_type,
                            "filesystem_source": str(request.lock_root),
                            "device": coverage_lock_readback.device,
                            "inode": coverage_lock_readback.inode,
                            "mode": "0660",
                        }
                    ),
                )
                coverage_attempted.add("os_safe_lock_placement")
                if any(
                    uuid not in final_observation.caller_allocated_ids
                    or uuid in occupied_final
                    or uuid in unknown_final
                    or final_observation.free_memory_bytes.get(uuid, 0)
                    < request.gpu_requested_memory_bytes
                    for uuid in selected
                ):
                    raise TypedPreflightFailure(
                        "gpu_run_admission_raced",
                        "final UUID, occupancy, or memory evidence changed after reservation",
                        selected_uuids=selected,
                    )
                lock_readback = {
                    "reservation_owner": "GpuReservationTransaction",
                    "reservation_evidence_fingerprint": reservation.evidence_fingerprint,
                    "initial_observation_fingerprint": initial_observation.fingerprint,
                    "admission_observation_fingerprint": final_observation.fingerprint,
                    "final_eligible_ids": tuple(
                        uuid
                        for uuid in sorted(final_observation.caller_allocated_ids)
                        if uuid not in occupied_final
                        and uuid not in unknown_final
                        and final_observation.free_memory_bytes.get(uuid, 0)
                        >= request.gpu_requested_memory_bytes
                    ),
                }
                selected_memory = {
                    uuid: final_observation.free_memory_bytes.get(uuid, 0)
                    for uuid in selected
                }
                allocation = GPUAllocation(
                    plan_fingerprint="pending",
                    caller_allocated_ids=candidates,
                    candidate_ids=candidates,
                    occupied_ids=tuple(sorted(set(occupied_final) | set(unknown_final))),
                    reserved_ids=(),
                    eligible_ids=tuple(cast(tuple[str, ...], lock_readback["final_eligible_ids"])),
                    selected_ids=selected,
                    reservation_ids=reservation_transaction.reservation_ids,
                    free_memory_bytes=dict(final_observation.free_memory_bytes),
                    occupied_process_identities=final_observation.process_identities,
                    process_identities=final_observation.process_identities,
                    allocation_id=reservation.evidence_fingerprint,
                    lock_root=request.lock_root,
                    selection_order=tuple(cast(tuple[str, ...], lock_readback["final_eligible_ids"])),
                    memory_bytes={
                        device.uuid: device.memory_bytes
                        for device in final_observation.gpu_devices
                        if device.uuid in selected_memory
                    },
                    slot_id=None,
                    requested_count=request.gpu_requested_count,
                    requested_memory_bytes=request.gpu_requested_memory_bytes,
                    readback_fingerprint=hashlib.sha256(
                        json.dumps(lock_readback, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    lock_readback=lock_readback,
                    allocation_provenance=request.gpu_allocation_provenance,
                    leases=(),
                )
            else:
                final_observation = initial_observation
                allocation = GPUAllocation(
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
                    readback_fingerprint=hashlib.sha256(b"gpu-unrequested").hexdigest(),
                    lock_readback={
                        "reservation_owner": "GpuReservationTransaction",
                        "gpu_requested": False,
                    },
                    allocation_provenance="not_applicable",
                    leases=(),
                )
            if request.gpu_requested_count:
                admission = build_lock_bound_admission_receipt(
                    candidate_uuids=allocation.candidate_ids,
                    occupied_uuids=tuple(sorted(occupied_final)),
                    reserved_uuids=allocation.reserved_ids,
                    selected_uuids=allocation.selected_ids,
                    inventory_fingerprint=(
                        final_inventory.evidence_fingerprint
                        if final_inventory is not None
                        else ""
                    ),
                    occupancy_fingerprint=hashlib.sha256(
                        "|".join(
                            (
                                initial_observation.fingerprint,
                                final_observation.fingerprint,
                            )
                        ).encode("utf-8")
                    ).hexdigest(),
                    reservation_fingerprint=allocation.readback_fingerprint,
                    runtime_identity_fingerprint=runtime_identity.readback_fingerprint,
                    lock_readback=coverage_lock_readback,
                    actual_gpu_processes=coverage_processes,
                    concurrent_run_evidence=coverage_concurrent,
                    mig_evidence=coverage_mig,
                    os_safe_lock_placement=coverage_lock_placement,
                )
                allocation = replace(
                    allocation,
                    admission_fingerprint=admission.admission_fingerprint,
                )
            if request.gpu_requested_count:
                if final_probe is None:
                    raise TypedPreflightFailure(
                        "gpu_final_probe_missing",
                        "GPU admission completed without a final NVIDIA probe",
                    )
                discovered_probe = final_probe
            else:
                discovered_probe = probe
            discovered = DiscoveredResources(
                cpu_available_set=final_observation.cpu_available_set,
                gpu_devices=final_observation.gpu_devices,
                caller_allocated_ids=final_observation.caller_allocated_ids,
                occupied_processes=final_observation.process_identities,
                reserved_ids=frozenset(),
                host_memory_bytes=final_observation.host_memory_bytes,
                temp_bytes=final_observation.temp_bytes,
                ports=(),
                container_id=final_observation.container_id,
                structure_tool=final_observation.structure_tool,
                boot_id=final_observation.boot_id,
                probe=discovered_probe,
                observation=final_observation,
                reservation_store=None,
                tool_availability=final_observation.tool_availability,
                allocation_provenance=request.gpu_allocation_provenance,
                observed_at=final_observation.observed_at,
                observation_fingerprint=final_observation.fingerprint,
            )
            plan_request = replace(
                request,
                cwd=context.paths.result_dir / "source_snapshot",
            )
            frozen_plan = freeze_resource_plan(
                plan_request,
                discovered,
                allocation,
            )
            plan_fingerprint = frozen_plan.plan_fingerprint
            if admission is not None:
                admission = replace(
                    admission,
                    plan_fingerprint=plan_fingerprint,
                )
            coverage_attempted.add("effective_environment")
            admitted_environment = build_admitted_environment(
                frozen_plan,
                runtime_identity,
                admission_fingerprint=(
                    admission.admission_fingerprint if admission is not None else None
                ),
            )
            coverage_environment = dict(admitted_environment.exact_env_map)
            if request.gpu_requested_count:
                exact_visible = admitted_environment.cuda_visible_devices
                coverage_attempted.add("container_visible_uuid_mapping")
                coverage_visibility = UuidVisibilityEvidence(
                    cuda_visible_devices=admitted_environment.cuda_visible_devices,
                    nvidia_visible_devices=admitted_environment.nvidia_visible_devices,
                    disposition="explicit",
                    visible_uuids=tuple(allocation.selected_ids),
                    namespace_id=f"pid:[{runtime_identity.namespace_inode}]",
                    provision_receipt_fingerprint=runtime_identity.provision_fingerprint,
                    fingerprint=_r5_evidence_fingerprint(
                        {
                            "cuda": exact_visible,
                            "nvidia": admitted_environment.nvidia_visible_devices,
                            "visible_uuids": allocation.selected_ids,
                            "namespace_id": f"pid:[{runtime_identity.namespace_inode}]",
                            "provision_receipt_fingerprint": runtime_identity.provision_fingerprint,
                        }
                    ),
                )
            if admission is not None:
                admission = replace(
                    admission,
                    effective_environment=coverage_environment,
                    container_visible_uuid_mapping=coverage_visibility,
                )
            request_path, result_path, lifecycle_path, request_payload = (
                _build_managed_run_request(
                    context,
                    source_request,
                    frozen_plan,
                    admitted_environment,
                    source_paths,
                )
            )
            runner_invoked = True
            runner_exception: BaseException | None = None
            try:
                execution_result, runner_lifecycle, _ = _run_admitted_runner(
                    context=context,
                    request_path=request_path,
                    result_path=result_path,
                    lifecycle_path=lifecycle_path,
                    request_payload=request_payload,
                    environment=dict(admitted_environment.exact_env_map),
                )
            except BaseException as exc:
                runner_exception = exc
            if runner_lifecycle is None:
                missing_lifecycle = TypedPreflightFailure(
                    "experiment_runner_lifecycle_missing",
                    "admitted runner completed without typed lifecycle evidence",
                )
                if runner_exception is None:
                    raise missing_lifecycle
                lifecycle_failure = _normalize_failure(
                    missing_lifecycle,
                    "runner_lifecycle",
                )
            if runner_exception is not None:
                raise runner_exception
        except BaseException as exc:
            primary_exception = exc

    primary_failure = (
        _normalize_failure(primary_exception, "managed_admission")
        if primary_exception is not None
        else (release_failures[0] if release_failures else None)
    )
    if primary_failure is not None:
        outcome_exit_code = 1
    else:
        if execution_result is None:
            raise ResourcePlanError(
                "ExperimentRunner returned no typed result for a successful managed run"
            )
        outcome_exit_code = _execution_exit_code(execution_result)
    secondary_failures = tuple(
        ([lifecycle_failure] if lifecycle_failure is not None else [])
        + (
            release_failures
            if primary_exception is not None
            else release_failures[1:]
        )
    )
    if runner_invoked:
        lifecycle = runner_lifecycle
        lifecycle_quiescent = _lifecycle_quiescence_is_proven(lifecycle)
        coverage_descendants = DescendantRetentionEvidence(
            child_process_ids=(lifecycle.child_process_ids if lifecycle is not None else ()),
            process_group_ids=(lifecycle.process_group_ids if lifecycle is not None else ()),
            descendant_quiescence="PROVEN" if lifecycle_quiescent else "UNPROVEN",
            retained_gpu_process_uuids=(),
            release_blocked=not lifecycle_quiescent,
            fingerprint=_r5_evidence_fingerprint(
                {
                    "runner_lifecycle": repr(lifecycle),
                    "descendant_quiescence": "PROVEN" if lifecycle_quiescent else "UNPROVEN",
                    "release_blocked": not lifecycle_quiescent,
                }
            ),
        )
        coverage_attempted.add("descendant_retention_evidence")
        if admission is not None:
            admission = replace(
                admission,
                descendant_retention_evidence=coverage_descendants,
            )
    outcome = ManagedGpuOutcomeReducer().reduce_terminal(
        run_id=request.run_id or request.plan_id or context.identity.run_name,
        planned_chunk_ids=request.requested_chunks,
        admission=admission,
        source_freeze=source_freeze,
        runtime_identity=runtime_identity,
        runner_lifecycle=runner_lifecycle,
        primary_failure=primary_failure,
        secondary_failures=secondary_failures,
        release_disposition=tuple(reservation_dispositions),
        context_state="closed",
        exit_code=outcome_exit_code,
    )
    optional_fields = (
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
    evidence_values: Mapping[EvidenceAbsenceField, object | None] = {
        "source_freeze_evidence": source_freeze,
        "lock_readback": coverage_lock_readback,
        "effective_environment": coverage_environment,
        "actual_gpu_processes": coverage_processes,
        "concurrent_run_evidence": coverage_concurrent,
        "mig_evidence": coverage_mig,
        "container_visible_uuid_mapping": coverage_visibility,
        "os_safe_lock_placement": coverage_lock_placement,
        "descendant_retention_evidence": coverage_descendants,
    }
    failure_kind = primary_failure.kind if primary_failure is not None else None
    absence_dispositions = tuple(
        _r5_absence(
            field_name,
            "failed" if field_name in coverage_attempted else "not_reached",
            failure_kind if field_name in coverage_attempted else None,
        )
        for field_name in optional_fields
        if evidence_values[field_name] is None
    )
    coverage_path = context.paths.result_dir / "runtime" / COMPLETION_COVERAGE_FILENAME
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage = CompletionCoverageAdapter(coverage_path).record_once(
        build_completion_coverage_input(
            outcome,
            admission,
            source_freeze,
            runtime_identity,
            absence_dispositions,
        )
    )
    projection = PostToolUseProjectionReducer().project(outcome, coverage)
    projection_path = coverage_path.parent / "post_tool_use_projection.json"
    try:
        with projection_path.open("xb") as projection_file:
            projection_file.write(projection)
    except FileExistsError as exc:
        raise ResourcePlanError(
            "post-tool-use projection was delivered more than once"
        ) from exc
    if primary_exception is not None:
        raise primary_exception
    if execution_result is None:
        raise ResourcePlanError("admitted runner returned no execution result")
    return execution_result


def _execution_exit_code(execution_result: ManagedRunExecutionResult) -> int:
    raw_exit_code = execution_result.raw_exit_code
    if raw_exit_code is None:
        raise ResourcePlanError(
            "admitted runner returned an execution result without a raw exit code"
        )
    return raw_exit_code


def run_cli(
    args: argparse.Namespace,
) -> int:
    """Run one managed experiment through the canonical frozen topic adapter."""
    context = build_run_context(args)
    patterns = resolve_eval_artifact_patterns(
        context.registry.defaults,
        context.registry.entry,
    )
    explicit_config = load_explicit_config(args.config_json or "", args.config)

    if not context.command.command:
        raise ValueError("a command is required")

    reservation = reserve_run_paths(context, args.skip_report_init)
    manifest = build_manifest(context, "running")
    run_config = build_run_config(context, explicit_config)
    manifest["config_path"] = str(context.paths.config_path)
    manifest["config"] = run_config
    start_monotonic = time.monotonic()
    try:
        source_config = write_initial_artifacts(
            context,
            manifest,
            run_config,
            args.skip_report_init,
        )
        if not release_reservation_marker(reservation):
            raise ResourcePlanError(
                "reservation marker ownership changed before initial artifacts completed"
            )
    except BaseException:
        # A setup failure before any artifact exists may clean only the
        # receipt-owned empty reservation.  Once an artifact is present, the
        # failed run remains available for diagnosis and operator cleanup.
        rollback_empty_reservation(reservation)
        raise
    preflight_error = source_config_error(source_config)
    if preflight_error:
        print(preflight_error, file=sys.stderr)
        manifest["preflight_error"] = {
            "kind": "missing_source_config",
            "message": preflight_error,
        }
        append_startup_event(
            context,
            "preflight_failed",
            {
                "exit_code": PREFLIGHT_FAILURE_EXIT_CODE,
                "message": preflight_error,
            },
        )
        finalize_run_manifest(
            context,
            manifest,
            start_monotonic,
            PREFLIGHT_FAILURE_EXIT_CODE,
            patterns,
        )
        return PREFLIGHT_FAILURE_EXIT_CODE

    append_startup_event(
        context,
        "command_start",
        {
            "command": context.command.command,
            "command_source": context.command.source,
        },
    )
    execution_result = execute_managed_run(
        context,
        run_config,
    )
    exit_code = _execution_exit_code(execution_result)
    append_startup_event(context, "command_exit", {"exit_code": exit_code})
    finalize_run_manifest(context, manifest, start_monotonic, exit_code, patterns)
    return exit_code


def main() -> int:
    """Run the CLI."""
    try:
        return run_cli(parse_args())
    except (OSError, ValueError, ResourcePlanError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
