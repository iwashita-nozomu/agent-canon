# @dependency-start
# contract test-only-evidence
# responsibility Provides deterministic injected observations for public contract selectors.
# upstream implementation ../../tools/experiments/execution_resource_plan.py owns production discovery and planning.
# downstream implementation ./test_execution_resource_plan.py public resource-plan observables.
# downstream implementation ./test_run_managed_experiment.py public managed-run observables.
# @dependency-end
"""Test-only deterministic evidence boundary for resource-plan selectors."""

from __future__ import annotations

from typing import Mapping, Sequence

from tools.experiments.execution_resource_plan import (
    DiscoveredResources,
    GPUDevice,
    ResourceObservation,
    ResourceRequest,
    SnapshotResourceProbe,
    UUIDReservationStore,
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
