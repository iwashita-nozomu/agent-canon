#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Exercises public ExecutionResourcePlan resource, environment, certificate, lock, readback, terminal, cleanup, and completion observables.
# upstream implementation ../../tools/experiments/execution_resource_plan.py canonical resource-plan owner
# upstream design ../../reports/agents/w1-tool-env-routing-20260716/design_brief.md approved W1-DESIGN-20260716-R3-GPU-COMPLETIONCOVERAGE-REPAIR
# upstream design ../../documents/experiment_runner.md ExperimentRunner lifecycle and scheduler boundary
# downstream integration ../../reports/agents/w1-tool-env-routing-20260716/integration_bundle_selector.json selects this contract source without executing it
# @dependency-end
"""Public contract-source selectors for the canonical resource plan."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.experiments.execution_resource_plan import (
    CALLER_ALLOCATION_PROVENANCE,
    COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
    CompletionCoverageAdapter,
    CompletionCoverageFailure,
    CompletionCoverageInput,
    EffectiveEnvironmentReadback,
    ExperimentRunnerPreLaunchAdapter,
    GPUDevice,
    managed_run_adapter_integration_contract,
    PlanState,
    ProcessIdentity,
    ResourceRequest,
    SnapshotResourceProbe,
    TypedPreflightFailure,
    UUIDReservationStore,
    discover_injected_test_resources,
    dispose_resources,
    freeze_resource_plan,
    materialize_environment,
    plan_gpu_allocation,
    record_terminal,
)


class ExecutionResourcePlanContractTest(unittest.TestCase):
    """Describe public resource-plan invariants without private-detail coupling."""

    def make_request(self, root: Path) -> ResourceRequest:
        """Build a declared caller/scheduler resource request."""
        return ResourceRequest(
            owner_id="worker-luna",
            parent_id="parent-sol",
            context_id="context-continuation",
            maximum_timeout_seconds=3600,
            argv=("/workspace/experiment", "--run", "chunk-1"),
            cwd=Path("/workspace"),
            environment={"RUN_MODE": "managed"},
            integration_contract=managed_run_adapter_integration_contract(),
            run_id="resource-plan-contract",
            requested_chunks=("chunk-1",),
            cpu_requested_set=(0,),
            gpu_requested_count=1,
            gpu_requested_memory_bytes=1024,
            gpu_allocation_provenance=CALLER_ALLOCATION_PROVENANCE,
            runtime_root=root / "runtime",
            source_projection_root=root / "projection",
            lock_root=root / "locks",
            lock_namespace_shared_across_schedulers=True,
            lock_namespace_host_safe=True,
            lock_namespace_visibility_witness="container-local-shared-lock",
            resource_probe=SnapshotResourceProbe(
                allocated=frozenset({"GPU-0001"}),
                processes=(),
                memory={"GPU-0001": 4096},
                current_boot_id="boot-1",
                visible=frozenset({"GPU-0001"}),
            ),
            discovered_cpu_available_set=(0,),
            discovered_gpu_devices=(GPUDevice("GPU-0001", 4096, 8192),),
            discovered_container_id="container-1",
            discovered_structure_tool={"available": "true", "version": "tree-1"},
            discovered_tool_availability={
                "tree": {"available": True},
                "nvidia-smi": {"available": True, "structured": True},
            },
        )

    def build_plan(self, root: Path):
        """Build the public discovery and frozen-plan stages."""
        request = self.make_request(root)
        discovered = discover_injected_test_resources(
            request,
            request.resource_probe,
            cpu_available_set=request.discovered_cpu_available_set,
            gpu_devices=request.discovered_gpu_devices,
            container_id=request.discovered_container_id,
            structure_tool=request.discovered_structure_tool,
            tool_availability=request.discovered_tool_availability,
        )
        allocation = plan_gpu_allocation(request, discovered)
        plan = freeze_resource_plan(request, discovered, allocation)
        return request, plan

    def test_state_and_immutable_nested_plan_are_public(self) -> None:
        """Materialization exposes the next frozen state and rejects nested mutation."""
        with tempfile.TemporaryDirectory() as temporary:
            _, plan = self.build_plan(Path(temporary))
            self.assertEqual(plan.state, PlanState.PLAN_FROZEN)
            materialized = materialize_environment(plan)
            self.assertEqual(materialized.plan.state, PlanState.ENV_MATERIALIZED)
            with self.assertRaises(TypeError):
                materialized.plan.side_effect_inventory[0]["target"] = "/changed"  # type: ignore[index]

    def test_gpu_plan_exposes_eligible_set_provenance_and_cardinality(self) -> None:
        """The allocation exposes candidate, eligible, selected, and reread evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            request, plan = self.build_plan(Path(temporary))
            allocation = plan.gpu_allocation
            self.assertEqual(
                allocation.lock_readback["provenance"],
                request.gpu_allocation_provenance,
            )
            self.assertEqual(len(allocation.selected_ids), request.gpu_requested_count)
            self.assertTrue(set(allocation.selected_ids).issubset(allocation.eligible_ids))
            self.assertEqual(tuple(allocation.selected_ids), tuple(sorted(allocation.selected_ids)))
            self.assertEqual(allocation.lock_readback["selected_cardinality"], 1)
            self.assertEqual(
                allocation.lock_readback["initial_observation"]["event"],
                "S0",
            )
            self.assertEqual(
                allocation.lock_readback["final_observation"]["event"],
                "S_final",
            )
            self.assertEqual(
                allocation.lock_readback["attempts"][0]["observation_event"],
                "S_lock",
            )
            self.assertNotEqual(
                allocation.lock_readback["initial_observation"]["fingerprint"],
                allocation.lock_readback["final_observation"]["fingerprint"],
            )

    def test_wrong_gpu_provenance_fails_before_planning(self) -> None:
        """A GPU request cannot enter the planner without caller/scheduler provenance."""
        with self.assertRaises(TypedPreflightFailure):
            ResourceRequest(
                owner_id="worker",
                parent_id="parent",
                context_id="context",
                maximum_timeout_seconds=60,
                argv=("/bin/true",),
                cwd=Path("/workspace"),
                environment={},
                integration_contract=managed_run_adapter_integration_contract(),
                gpu_requested_count=1,
            )

    def test_certificate_readback_prelaunch_terminal_cleanup_and_exact_once(self) -> None:
        """The public route preserves readback, packet, terminal, cleanup, and coverage evidence."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, frozen = self.build_plan(root)
            materialized = materialize_environment(frozen)
            allocation = frozen.gpu_allocation
            readback = EffectiveEnvironmentReadback(
                environment=materialized.exact_env_map,
                cwd=materialized.cwd,
                argv=materialized.argv,
                visible_gpu_ids=allocation.selected_ids,
                cpu_set=(0,),
                container_id="container-1",
                runtime_identity="container-1",
                allocation_id=allocation.allocation_id,
                reservation_ids=allocation.reservation_ids,
                free_memory_bytes={"GPU-0001": 4096},
                process_identities=(),
                requested_memory_bytes=1024,
            )
            adapter = ExperimentRunnerPreLaunchAdapter(
                managed_run_adapter_integration_contract()
            )

            def transport(payload):
                return {
                    "accepted": True,
                    "canonical_environment": payload["canonical_environment"],
                    "gpu_allocation": payload["gpu_allocation"],
                    "scheduler_policy": payload["scheduler_policy"],
                    "plan_fingerprint": payload["handoff_metadata"]["plan_fingerprint"],
                    "readback_fingerprint": payload["handoff_metadata"]["readback_fingerprint"],
                    "effective_environment": materialized.exact_env_map,
                    "cwd": materialized.cwd,
                    "argv": materialized.argv,
                    "visible_gpu_ids": allocation.selected_ids,
                    "cpu_set": (0,),
                    "container_id": "container-1",
                    "runtime_identity": "container-1",
                    "allocation_id": allocation.allocation_id,
                    "caller_allocated_ids": allocation.caller_allocated_ids,
                    "reservation_ids": allocation.reservation_ids,
                    "free_memory_bytes": {"GPU-0001": 4096},
                    "process_identities": (),
                    "requested_memory_bytes": 1024,
                    "readback_timestamp": payload["prelaunch_observation"][
                        "observation_timestamp"
                    ],
                    "probe_observation_timestamp": payload["prelaunch_observation"][
                        "observation_timestamp"
                    ],
                    "probe_observation_fingerprint": payload["prelaunch_observation"][
                        "observation_fingerprint"
                    ],
                    "probe_observation_event_id": payload["prelaunch_observation"][
                        "observation_event_id"
                    ],
                }

            prelaunch = adapter.pre_launch(
                materialized.plan,
                materialized,
                allocation,
                transport,
            )
            certificate = prelaunch.certificate
            self.assertTrue(certificate.all_witnesses_valid)
            self.assertEqual(prelaunch.plan.state, PlanState.EXECUTE)
            terminal = record_terminal(
                prelaunch.plan,
                {"status": "ok"},
                terminal_event_id="terminal-1",
                terminal_chunk_ids=request.requested_chunks,
            )
            coverage_input = CompletionCoverageInput(
                schema_version=COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
                plan_fingerprint=terminal.plan_fingerprint,
                terminal_event_id=terminal.terminal_event_id,
                candidate_gpu_ids=allocation.candidate_ids,
                occupied_gpu_ids=(),
                reserved_gpu_ids=allocation.reserved_ids,
                selected_gpu_ids=allocation.selected_ids,
                lock_readback=allocation.lock_readback,
                effective_env={"certificate": certificate.readback_fingerprint},
                actual_gpu_processes=(),
                release_retention_disposition={},
                concurrent_run_evidence={"observed": True},
                mig_evidence={"observed": True},
                container_visible_uuid_mapping={"GPU-0001": "GPU-0001"},
                os_safe_lock_placement={"lock_root": str(request.lock_root)},
                descendant_retention_evidence={"force_kill": False},
                taxonomy_linked_validation_outcome={"status": "not_applicable"},
                planned_chunk_ids=terminal.planned_chunk_ids,
                terminal_chunk_ids=terminal.terminal_chunk_ids,
                required_evidence={"terminal": True, "partial": True},
                effective_env_certificate_matches=True,
                cleanup_has_unresolved_leak_or_unknown=False,
                required_review_gates_passed=True,
            )
            coverage_adapter = CompletionCoverageAdapter(root / "completion_coverage.json")
            cleanup = dispose_resources(
                terminal.plan,
                terminal,
                completion_coverage_adapter=coverage_adapter,
                completion_coverage_input=coverage_input,
                runner_quiescence_evidence={
                    "plan_fingerprint": terminal.plan_fingerprint,
                    "quiescent": True,
                    "process_tree_terminal": True,
                    "can_create_gpu_context": False,
                    "creation_barrier": "runner_process_tree_joined",
                    "runner_root_pid": 1,
                    "runner_root_process_start_identity": "test",
                    "observed_at": "2026-07-16T00:00:00Z",
                    "observation_fingerprint": "test-observation",
                    "process_identities": (),
                },
            )
            self.assertEqual(cleanup.plan.state, PlanState.CLEANUP_DISPOSED)
            self.assertEqual(cleanup.completion_coverage.delivery_ordinal, 1)
            with self.assertRaises(CompletionCoverageFailure):
                coverage_adapter.record_once(cleanup.completion_coverage.input_record)

    def test_stale_reclaim_requires_lock_reread_and_persists_proof(self) -> None:
        """Stale reclaim is observable only after dead-owner and under-lock rereads."""
        with tempfile.TemporaryDirectory() as temporary:
            store = UUIDReservationStore(
                Path(temporary),
                shared_across_schedulers=True,
                host_safe=True,
                visibility_witness="container-local-shared-lock",
            )
            lease = store.acquire(
                "GPU-0001",
                owner_pid=999999,
                owner_process_start_identity="start-1",
                boot_id="boot-1",
            )
            self.assertIsNotNone(lease)
            lease.release(
                gpu_processes=lambda: (),
                occupied_gpu_units=lambda _processes: (),
            )
            evidence = store.reclaim_stale(
                "GPU-0001",
                current_boot_id=lambda: "boot-1",
                gpu_processes=lambda: (),
                process_start_identity=lambda _pid: None,
                occupied_gpu_units=lambda _processes: (),
            )
            self.assertTrue(evidence.reclaimed)
            self.assertTrue(evidence.under_lock_proof["record_reread_under_lock"])
            self.assertTrue(evidence.persistence_witness["path"])


if __name__ == "__main__":
    unittest.main()
