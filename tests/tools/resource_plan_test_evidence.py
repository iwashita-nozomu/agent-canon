# @dependency-start
# contract test
# responsibility Provides deterministic injected observations for public contract selectors.
# upstream implementation ../../tools/experiments/execution/execution_resource_plan.py owns production discovery and planning.
# downstream implementation ./test_execution_resource_plan.py public resource-plan observables.
# downstream implementation ./test_run_managed_experiment.py public managed-run observables.
# @dependency-end
"""Test-only deterministic evidence boundary for resource-plan selectors."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from tools.experiments.execution.execution_resource_plan import (
    DiscoveredResources,
    GPUDevice,
    ProcessIdentity,
    ResourceObservation,
    ResourceRequest,
    UUIDReservationStore,
)


@dataclass(frozen=True)
class SnapshotResourceProbe:
    """Deterministic observation source confined to the test evidence boundary."""

    allocated: frozenset[str]
    processes: tuple[ProcessIdentity, ...]
    memory: Mapping[str, int]
    current_boot_id: str
    visible: frozenset[str] = frozenset()
    observation_sequence: tuple[ResourceObservation, ...] = ()
    _observation_index: int = field(default=0, init=False, repr=False, compare=False)
    _observation_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
        compare=False,
    )

    def observe(self) -> ResourceObservation:
        if self.observation_sequence:
            with self._observation_lock:
                index = self._observation_index
                object.__setattr__(self, "_observation_index", index + 1)
            if index >= len(self.observation_sequence):
                raise RuntimeError("deterministic observation sequence exhausted")
            return self.observation_sequence[index]
        return ResourceObservation(
            caller_allocated_ids=self.allocated,
            process_identities=self.processes,
            gpu_devices=tuple(
                GPUDevice(uuid=uuid, free_memory_bytes=free_memory)
                for uuid, free_memory in sorted(self.memory.items())
            ),
            free_memory_bytes=self.memory,
            boot_id=self.current_boot_id,
            container_visible_ids=self.visible,
            observed_at="injected-test-observation",
        )


def discover_test_resources(
    request: ResourceRequest,
    probe: SnapshotResourceProbe,
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
    """Construct the observable discovery state without entering production CLI discovery."""
    observation: ResourceObservation = probe.observe()
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
        structure_tool=dict(structure_tool or {}),
        boot_id=observation.boot_id,
        probe=probe,
        observation=observation,
        reservation_store=UUIDReservationStore(
            request.lock_root,
            shared_across_schedulers=request.lock_namespace_shared_across_schedulers,
            host_safe=request.lock_namespace_host_safe,
            visibility_witness=request.lock_namespace_visibility_witness,
        ),
        tool_availability=dict(tool_availability or {}),
        allocation_provenance=request.gpu_allocation_provenance,
        observed_at=observation.observed_at,
        observation_fingerprint=observation.fingerprint,
    )
