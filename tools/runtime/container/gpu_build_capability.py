#!/usr/bin/env python3
# @dependency-start
# contract implementation
# responsibility Validates staged GPU build receipts without owning Dockerfiles, BuildKit mutation, or CUDA provider materialization.
# upstream design ../../documents/design/environment-resolution-gpu-build-capability.md GPU build admission contract
# downstream implementation ../../tests/agent_tools/test_gpu_build_capability.py focused receipt regression
# downstream implementation ../../tests/fixtures/environment_resolution/wsl2_rootless_nvml_failed.json sanitized WSL2 failure receipt
# downstream implementation ../../tests/fixtures/environment_resolution/wsl2_rootless_cuda_build_repaired.json sanitized WSL2 repaired receipt
# @dependency-end
"""Typed, fail-closed classification for GPU capability inside image builds."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

SCHEMA = "agent-canon.environment-resolution.gpu-build-capability"
SCHEMA_VERSION = 2
FINDING_GPU_BUILD_ENVIRONMENT_UNAVAILABLE = "gpu_build_environment_unavailable"
HANDOFF_OWNER = "project-environment-or-cppdev-provider"
HANDOFF_REQUIREMENTS = (
    "provider_artifact_identity",
    "detected_compute_capability",
)
MAX_TEXT = 240
MAX_ITEMS = 32
EnumT = TypeVar("EnumT", bound=Enum)


class ReceiptError(ValueError):
    """Raised when a receipt violates the closed schema."""


class Stage(str, Enum):  # noqa: UP042
    """Independent build observations plus separate runtime evidence."""

    DEVICE_ENTITLEMENT = "device_entitlement"
    CDI_INVENTORY = "cdi_inventory"
    RUN_DEVICE_REQUEST = "run_device_request"
    DEVICE_NODES = "device_nodes"
    DRIVER_LOADER = "driver_loader"
    CUDA_DRIVER_API = "cuda_driver_api"
    CUDA_COMPILE_RUN = "cuda_compile_run"
    RUNTIME_CDI = "runtime_cdi"


class State(str, Enum):  # noqa: UP042
    """Closed state vocabulary used by the staged receipt."""

    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    SUPPORTED = "supported"
    MISSING = "missing"
    UNRESOLVED = "unresolved"
    MATCHED = "matched"
    NOT_ATTEMPTED = "not_attempted"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    PRESENT = "present"
    COMPLETE = "complete"
    UNVERIFIED = "unverified"
    FAILED_INITIALIZATION = "failed_initialization"
    READY = "ready"
    COMPILE_FAILED = "compile_failed"
    RUN_FAILED = "run_failed"
    FAILED = "failed"
    PASSED = "passed"


class ProbeKind(str, Enum):  # noqa: UP042
    """Stage-owned probe identity; free-form text cannot promote a stage."""

    DEVICE_ENTITLEMENT = "device_entitlement"
    CDI_INVENTORY = "cdi_inventory"
    RUN_DEVICE_REQUEST = "run_device_request"
    DEVICE_NODES = "device_nodes"
    DRIVER_LOADER = "driver_loader"
    CUDA_DRIVER_API = "cuda_driver_api"
    CUDA_RUNTIME_API = "cuda_runtime_api"
    CUDA_COMPILE_RUN = "cuda_compile_run"
    NVML = "nvml"
    RUNTIME_CDI = "runtime_cdi"


class DaemonMode(str, Enum):  # noqa: UP042
    """Docker daemon ownership mode retained in the builder identity."""

    ROOTLESS = "rootless"
    ROOTFUL = "rootful"
    DESKTOP = "desktop"


class BuilderDriver(str, Enum):  # noqa: UP042
    """Buildx driver identity; distinct drivers are never inferred as equivalent."""

    DOCKER = "docker"
    DOCKER_CONTAINER = "docker-container"
    KUBERNETES = "kubernetes"
    REMOTE = "remote"


class BuildCapability(str, Enum):  # noqa: UP042
    """Final build-worker capability classification."""

    UNAVAILABLE = "unavailable"
    READY = "ready"


BUILD_STAGES = (
    Stage.DEVICE_ENTITLEMENT,
    Stage.CDI_INVENTORY,
    Stage.RUN_DEVICE_REQUEST,
    Stage.DEVICE_NODES,
    Stage.DRIVER_LOADER,
    Stage.CUDA_DRIVER_API,
    Stage.CUDA_COMPILE_RUN,
)
ALL_STAGES = (*BUILD_STAGES, Stage.RUNTIME_CDI)
ALLOWED_STATES = {
    Stage.DEVICE_ENTITLEMENT: {
        State.UNAVAILABLE,
        State.UNSUPPORTED,
        State.SUPPORTED,
    },
    Stage.CDI_INVENTORY: {State.MISSING, State.UNRESOLVED, State.MATCHED},
    Stage.RUN_DEVICE_REQUEST: {
        State.NOT_ATTEMPTED,
        State.REJECTED,
        State.ACCEPTED,
    },
    Stage.DEVICE_NODES: {State.MISSING, State.PARTIAL, State.PRESENT},
    Stage.DRIVER_LOADER: {State.MISSING, State.PARTIAL, State.COMPLETE},
    Stage.CUDA_DRIVER_API: {
        State.UNVERIFIED,
        State.FAILED_INITIALIZATION,
        State.READY,
    },
    Stage.CUDA_COMPILE_RUN: {
        State.NOT_ATTEMPTED,
        State.COMPILE_FAILED,
        State.RUN_FAILED,
        State.PASSED,
    },
    Stage.RUNTIME_CDI: {State.UNVERIFIED, State.FAILED, State.PASSED},
}
SUCCESS_STATE = {
    Stage.DEVICE_ENTITLEMENT: State.SUPPORTED,
    Stage.CDI_INVENTORY: State.MATCHED,
    Stage.RUN_DEVICE_REQUEST: State.ACCEPTED,
    Stage.DEVICE_NODES: State.PRESENT,
    Stage.DRIVER_LOADER: State.COMPLETE,
    Stage.CUDA_DRIVER_API: State.READY,
    Stage.CUDA_COMPILE_RUN: State.PASSED,
}


@dataclass(frozen=True)
class BuilderIdentity:
    """Exact builder surface that produced one receipt."""

    platform: str
    builder_name: str
    daemon_mode: DaemonMode
    builder_driver: BuilderDriver
    docker_version: str
    buildx_version: str
    buildkit_version: str
    requested_devices: tuple[str, ...]
    cdi_devices: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> BuilderIdentity:
        """Parse the closed builder identity without alias inference."""
        _exact_keys(
            raw,
            {
                "platform",
                "builder_name",
                "daemon_mode",
                "builder_driver",
                "docker_version",
                "buildx_version",
                "buildkit_version",
                "requested_devices",
                "cdi_devices",
            },
            "builder",
        )
        return cls(
            platform=_text(raw["platform"], "builder.platform"),
            builder_name=_text(raw["builder_name"], "builder.builder_name"),
            daemon_mode=_enum_value(
                DaemonMode, raw["daemon_mode"], "builder.daemon_mode"
            ),
            builder_driver=_enum_value(
                BuilderDriver, raw["builder_driver"], "builder.builder_driver"
            ),
            docker_version=_text(raw["docker_version"], "builder.docker_version"),
            buildx_version=_text(raw["buildx_version"], "builder.buildx_version"),
            buildkit_version=_text(raw["buildkit_version"], "builder.buildkit_version"),
            requested_devices=_strings(
                raw["requested_devices"],
                "builder.requested_devices",
                allow_empty=False,
                unique=True,
            ),
            cdi_devices=_strings(
                raw["cdi_devices"],
                "builder.cdi_devices",
                allow_empty=True,
                unique=True,
            ),
        )


@dataclass(frozen=True)
class StageEvidence:
    """Bounded evidence for one explicitly named stage."""

    summary: str
    probe_kind: ProbeKind
    command: tuple[str, ...]
    exit_code: int | None
    observations: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Mapping[str, Any], stage: Stage) -> StageEvidence:
        """Parse one bounded evidence record."""
        field = f"evidence.{stage.value}"
        _exact_keys(
            raw,
            {"summary", "probe_kind", "command", "exit_code", "observations"},
            field,
        )
        exit_code = raw["exit_code"]
        if exit_code is not None and (
            isinstance(exit_code, bool) or not isinstance(exit_code, int)
        ):
            raise ReceiptError(f"{field}.exit_code must be an integer or null")
        return cls(
            summary=_text(raw["summary"], f"{field}.summary"),
            probe_kind=_probe_kind(stage, raw["probe_kind"], field),
            command=_strings(
                raw["command"], f"{field}.command", allow_empty=True, unique=False
            ),
            exit_code=exit_code,
            observations=_strings(
                raw["observations"],
                f"{field}.observations",
                allow_empty=True,
                unique=False,
            ),
        )


@dataclass(frozen=True)
class GpuBuildCapabilityDecision:
    """Fail-closed decision derived only from build-time stages."""

    capability: BuildCapability
    blocking_stage: Stage | None
    blocking_state: State | None
    incomplete_stages: tuple[Stage, ...]
    runtime_cdi: State
    finding: str | None
    handoff_owner: str
    handoff_requirements: tuple[str, ...]


@dataclass(frozen=True)
class GpuBuildCapabilityReceipt:
    """Typed observation of one builder; runtime CDI never promotes build state."""

    builder: BuilderIdentity
    states: Mapping[Stage, State]
    evidence: Mapping[Stage, StageEvidence]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> GpuBuildCapabilityReceipt:
        """Parse exact schema, stage identities, states, and evidence."""
        _exact_keys(
            raw,
            {"schema", "version", "builder", "stages", "evidence"},
            "receipt",
        )
        if raw["schema"] != SCHEMA:
            raise ReceiptError(f"unsupported schema: {raw['schema']!r}")
        version = raw["version"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise ReceiptError("schema version must be an integer")
        if version != SCHEMA_VERSION:
            raise ReceiptError(f"unsupported schema version: {version!r}")

        builder = BuilderIdentity.parse(_mapping(raw["builder"], "builder"))
        stage_values = _mapping(raw["stages"], "stages")
        evidence_values = _mapping(raw["evidence"], "evidence")
        names = {stage.value for stage in ALL_STAGES}
        _exact_keys(stage_values, names, "stages")
        _exact_keys(evidence_values, names, "evidence")

        states = MappingProxyType(
            {
                stage: _state(stage, stage_values[stage.value])
                for stage in ALL_STAGES
            }
        )
        evidence = MappingProxyType(
            {
                stage: StageEvidence.parse(
                    _mapping(evidence_values[stage.value], f"evidence.{stage.value}"),
                    stage,
                )
                for stage in ALL_STAGES
            }
        )
        _validate_cdi_identity(builder, states[Stage.CDI_INVENTORY])
        _validate_evidence_consistency(states, evidence)
        return cls(builder=builder, states=states, evidence=evidence)

    def state(self, stage: Stage) -> State:
        """Return one exact stage state."""
        return self.states[stage]

    def decide(self) -> GpuBuildCapabilityDecision:
        """Classify readiness as the conjunction of build-only success states."""
        incomplete = tuple(
            stage
            for stage in BUILD_STAGES
            if self.state(stage) != SUCCESS_STATE[stage]
        )
        runtime = self.state(Stage.RUNTIME_CDI)
        if not incomplete:
            return GpuBuildCapabilityDecision(
                capability=BuildCapability.READY,
                blocking_stage=None,
                blocking_state=None,
                incomplete_stages=(),
                runtime_cdi=runtime,
                finding=None,
                handoff_owner=HANDOFF_OWNER,
                handoff_requirements=HANDOFF_REQUIREMENTS,
            )
        blocking = incomplete[0]
        return GpuBuildCapabilityDecision(
            capability=BuildCapability.UNAVAILABLE,
            blocking_stage=blocking,
            blocking_state=self.state(blocking),
            incomplete_stages=incomplete,
            runtime_cdi=runtime,
            finding=FINDING_GPU_BUILD_ENVIRONMENT_UNAVAILABLE,
            handoff_owner=HANDOFF_OWNER,
            handoff_requirements=HANDOFF_REQUIREMENTS,
        )


def load_gpu_build_capability_receipt(path: Path) -> GpuBuildCapabilityReceipt:
    """Load one UTF-8 JSON receipt and reject non-object roots."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReceiptError(f"cannot load receipt {path}: {error}") from error
    return GpuBuildCapabilityReceipt.from_mapping(_mapping(raw, "receipt"))


def _state(stage: Stage, value: Any) -> State:
    if not isinstance(value, str):
        raise ReceiptError(f"stages.{stage.value} must be a string")
    try:
        state = State(value)
    except ValueError as error:
        allowed = sorted(item.value for item in ALLOWED_STATES[stage])
        raise ReceiptError(
            f"stages.{stage.value} has unknown state {value!r}; "
            f"expected one of {allowed}"
        ) from error
    if state not in ALLOWED_STATES[stage]:
        allowed = sorted(item.value for item in ALLOWED_STATES[stage])
        raise ReceiptError(
            f"stages.{stage.value} rejects state {value!r}; "
            f"expected one of {allowed}"
        )
    return state


def _enum_value(enum_type: type[EnumT], value: Any, field: str) -> EnumT:
    if not isinstance(value, str):
        raise ReceiptError(f"{field} must be a string")
    try:
        return enum_type(value)
    except ValueError as error:
        allowed = sorted(item.value for item in enum_type)
        raise ReceiptError(
            f"{field} has unknown value {value!r}; expected one of {allowed}"
        ) from error


def _validate_evidence_consistency(
    states: Mapping[Stage, State],
    evidence: Mapping[Stage, StageEvidence],
) -> None:
    _validate_evidence_presence(states, evidence)
    success_states = {**SUCCESS_STATE, Stage.RUNTIME_CDI: State.PASSED}
    for stage, success in success_states.items():
        if states[stage] is success and evidence[stage].exit_code != 0:
            raise ReceiptError(
                f"{stage.value}={success.value} requires evidence.exit_code=0"
            )

    executed_failures = {
        Stage.RUN_DEVICE_REQUEST: {State.REJECTED},
        Stage.CUDA_DRIVER_API: {State.FAILED_INITIALIZATION},
        Stage.CUDA_COMPILE_RUN: {State.COMPILE_FAILED, State.RUN_FAILED},
        Stage.RUNTIME_CDI: {State.FAILED},
    }
    for stage, failures in executed_failures.items():
        if states[stage] in failures and evidence[stage].exit_code in (None, 0):
            raise ReceiptError(
                f"{stage.value}={states[stage].value} requires non-zero evidence.exit_code"
            )

    _validate_cuda_driver_api_evidence(states, evidence)


_EMPTY_EVIDENCE_STATES = {
    (Stage.RUN_DEVICE_REQUEST, State.NOT_ATTEMPTED),
    (Stage.CUDA_DRIVER_API, State.UNVERIFIED),
    (Stage.CUDA_COMPILE_RUN, State.NOT_ATTEMPTED),
    (Stage.RUNTIME_CDI, State.UNVERIFIED),
}


def _validate_evidence_presence(
    states: Mapping[Stage, State],
    evidence: Mapping[Stage, StageEvidence],
) -> None:
    """Require an executable argv and observations for every attempted stage."""
    for stage, item in evidence.items():
        empty_allowed = (stage, states[stage]) in _EMPTY_EVIDENCE_STATES
        if not item.command or not item.observations:
            if empty_allowed and not item.command and not item.observations:
                if item.exit_code is not None:
                    raise ReceiptError(
                        f"{stage.value}={states[stage].value} may be empty only with "
                        "exit_code=null"
                    )
                continue
            if not empty_allowed:
                raise ReceiptError(
                    f"{stage.value}={states[stage].value} requires non-empty "
                    "executable command and observations"
                )
            raise ReceiptError(
                f"{stage.value} evidence requires command and observations together"
            )
        if item.command and item.command[0].startswith("<"):
            raise ReceiptError(
                f"{stage.value}.command must start with an executable, not a placeholder"
            )


def _validate_cuda_driver_api_evidence(
    states: Mapping[Stage, State],
    evidence: Mapping[Stage, StageEvidence],
) -> None:
    """Require a typed direct-driver/NVML witness before declaring API readiness."""
    stage = Stage.CUDA_DRIVER_API
    item = evidence[stage]
    if states[stage] is not State.READY:
        return
    if item.probe_kind is ProbeKind.CUDA_DRIVER_API:
        required = (
            re.compile(r"\bcuInit\s+status=0\b"),
            re.compile(r"\bcuDeviceGetCount\s+status=0\s+count=\d+\b"),
        )
    elif item.probe_kind is ProbeKind.NVML:
        required = (
            re.compile(r"\bnvmlInit(?:_v2)?\s+status=0\b"),
            re.compile(
                r"\bnvmlDeviceGetCount\s+status=0\s+count=\d+\b"
            ),
        )
    else:
        raise ReceiptError(
            "cuda_driver_api=ready requires probe_kind=cuda_driver_api or nvml"
        )
    observations = "\n".join(item.observations)
    missing = [pattern.pattern for pattern in required if not pattern.search(observations)]
    if missing:
        raise ReceiptError(
            "cuda_driver_api=ready evidence is missing typed success observations: "
            + ", ".join(missing)
        )


def _validate_cdi_identity(builder: BuilderIdentity, state: State) -> None:
    missing = tuple(
        device for device in builder.requested_devices if device not in builder.cdi_devices
    )
    if state is State.MATCHED and missing:
        raise ReceiptError(
            "cdi_inventory=matched requires every requested device in "
            f"builder.cdi_devices; missing={list(missing)}"
        )
    if state is State.MISSING and builder.cdi_devices:
        raise ReceiptError(
            "cdi_inventory=missing requires an empty builder.cdi_devices inventory"
        )
    if state is State.UNRESOLVED and not missing:
        raise ReceiptError(
            "cdi_inventory=unresolved requires at least one requested device to be absent"
        )


def _probe_kind(stage: Stage, value: Any, field: str) -> ProbeKind:
    if not isinstance(value, str):
        raise ReceiptError(f"{field}.probe_kind must be a string")
    try:
        kind = ProbeKind(value)
    except ValueError as error:
        allowed = sorted(item.value for item in _allowed_probe_kinds(stage))
        raise ReceiptError(
            f"{field}.probe_kind has unknown value {value!r}; expected one of {allowed}"
        ) from error
    if kind not in _allowed_probe_kinds(stage):
        allowed = sorted(item.value for item in _allowed_probe_kinds(stage))
        raise ReceiptError(
            f"{field}.probe_kind={value!r} is not accepted for {stage.value}; "
            f"expected one of {allowed}"
        )
    return kind


def _allowed_probe_kinds(stage: Stage) -> frozenset[ProbeKind]:
    if stage is Stage.CUDA_DRIVER_API:
        return frozenset(
            {
                ProbeKind.CUDA_DRIVER_API,
                ProbeKind.CUDA_RUNTIME_API,
                ProbeKind.NVML,
            }
        )
    return frozenset({ProbeKind(stage.value)})


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReceiptError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ReceiptError(f"{field} keys must be strings")
    return value


def _exact_keys(raw: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(raw)
    if actual != expected:
        raise ReceiptError(
            f"{field} keys mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReceiptError(f"{field} must be a non-empty string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ReceiptError(f"{field} must not contain control characters")
    if len(value) > MAX_TEXT:
        raise ReceiptError(f"{field} exceeds {MAX_TEXT} characters")
    return value


def _strings(
    value: Any,
    field: str,
    *,
    allow_empty: bool,
    unique: bool,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ReceiptError(f"{field} must be an array of strings")
    if not allow_empty and not value:
        raise ReceiptError(f"{field} must not be empty")
    if len(value) > MAX_ITEMS:
        raise ReceiptError(f"{field} exceeds {MAX_ITEMS} items")
    result = tuple(_text(item, f"{field}[{index}]") for index, item in enumerate(value))
    if unique and len(set(result)) != len(result):
        raise ReceiptError(f"{field} must not contain duplicate values")
    return result
