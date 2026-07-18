#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Exercises public ExecutionResourcePlan resource, environment, certificate, lock, readback, terminal, cleanup, and completion observables.
# upstream implementation ../../tools/experiments/execution_resource_plan.py canonical resource-plan owner
# upstream design ../../documents/gpu-admission-r5-source-packet.md approved AgentCanon GPU admission R5 test frame
# upstream design ../../documents/experiment_runner.md ExperimentRunner lifecycle and scheduler boundary
# downstream implementation ../../documents/gpu-admission-r5-ordered-integration-interface.json selects this contract source without executing it
# @dependency-end
"""Public contract-source selectors for the canonical resource plan."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tests.tools.resource_plan_test_evidence import (
    SnapshotResourceProbe,
    discover_test_resources,
)

from tools.experiments.execution_resource_plan import (
    CALLER_ALLOCATION_PROVENANCE,
    COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
    CompletionCoverageAdapter,
    CompletionCoverageFailure,
    CompletionCoverageInput,
    ConcurrentRunEvidence,
    DescendantRetentionEvidence,
    EvidenceFd,
    EvidenceAbsence,
    GPUDevice,
    GpuProcessOccupancyProbe,
    GpuReservationTransaction,
    GpuRunRequest,
    LockPlacementEvidence,
    LockReadback,
    MigEvidence,
    RunGpuAdmissionReceipt,
    ManagedGpuOutcomeReducer,
    PostToolUseProjectionReducer,
    ReservationEvidence,
    NvidiaInventoryProbe,
    managed_run_adapter_integration_contract,
    PlanState,
    ProcessIdentity,
    ProcessOccupancyEvidence,
    ResourceRequest,
    ResourceObservation,
    SourceFreezeOwner,
    TypedPreflightFailure,
    UUIDReservationStore,
    UuidVisibilityEvidence,
    build_source_path_set,
    freeze_resource_plan,
    materialize_environment,
    parse_nvidia_driver_version,
    parse_nvidia_smi_list,
    parse_nvidia_smi_xml,
    plan_gpu_allocation,
)


class ExecutionResourcePlanContractTest(unittest.TestCase):
    """Describe public resource-plan invariants without private-detail coupling."""

    def test_r5_terminal_coverage_projection_is_exact_and_hook_validated(self) -> None:
        """Terminal outcome, exactly-once coverage, and Hook bytes share one receipt."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            uuid = "GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            visibility = UuidVisibilityEvidence(
                cuda_visible_devices=uuid,
                nvidia_visible_devices=uuid,
                disposition="explicit",
                visible_uuids=(uuid,),
                namespace_id="pid:[4026531836]",
                provision_receipt_fingerprint="c" * 64,
                fingerprint="d" * 64,
            )
            admission = RunGpuAdmissionReceipt(
                schema_version="gpu-admission/v1",
                candidate_uuids=(uuid,),
                occupied_uuids=(),
                reserved_uuids=(),
                selected_uuids=(uuid,),
                inventory_fingerprint="e" * 64,
                occupancy_fingerprint="f" * 64,
                reservation_fingerprint="g" * 64,
                runtime_identity_fingerprint="h" * 64,
                plan_fingerprint="b" * 64,
                admission_fingerprint="a" * 64,
                container_visible_uuid_mapping=visibility,
            )
            outcome = ManagedGpuOutcomeReducer().reduce_terminal(
                run_id="r5-terminal",
                planned_chunk_ids=("chunk-1",),
                admission=admission,
                source_freeze=None,
                runtime_identity=None,
                runner_lifecycle=None,
                primary_failure=None,
                secondary_failures=(),
                release_disposition=(),
                context_state="closed",
                exit_code=0,
            )
            absence_fields = (
                "source_freeze_evidence",
                "lock_readback",
                "effective_environment",
                "actual_gpu_processes",
                "concurrent_run_evidence",
                "mig_evidence",
                "os_safe_lock_placement",
                "descendant_retention_evidence",
            )
            absence = tuple(
                EvidenceAbsence(
                    field_name=field_name,
                    disposition="not_reached",
                    failure_kind=None,
                    fingerprint=hashlib.sha256(
                        json.dumps(
                            {
                                "field_name": field_name,
                                "disposition": "not_reached",
                                "failure_kind": None,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                )
                for field_name in absence_fields
            )
            coverage_input = CompletionCoverageInput(
                schema_version=COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
                outcome=outcome,
                planned_chunk_ids=("chunk-1",),
                candidate_uuids=(uuid,),
                occupied_uuids=(),
                reserved_uuids=(),
                selected_uuids=(uuid,),
                lock_readback=None,
                effective_environment=None,
                actual_gpu_processes=None,
                concurrent_run_evidence=None,
                mig_evidence=None,
                container_visible_uuid_mapping=visibility,
                os_safe_lock_placement=None,
                descendant_retention_evidence=None,
                source_freeze_evidence=None,
                absence_dispositions=absence,
            )
            coverage_adapter = CompletionCoverageAdapter(
                root / "completion_coverage.json"
            )
            coverage = coverage_adapter.record_once(coverage_input)
            self.assertFalse(coverage.partial_complete)
            self.assertFalse(coverage.all_planned_chunks_complete)
            self.assertFalse(coverage.overall_delivery_complete)
            projection = PostToolUseProjectionReducer().project(outcome, coverage)
            hook = (
                Path(__file__).resolve().parents[2]
                / ".codex"
                / "hooks"
                / "execution_resource_plan_projection_guard.py"
            )
            hook_input = json.dumps(
                {
                    "hook_event_name": "PostToolUse",
                    "schema_version": "agent-canon-post-tool-use-input/v1",
                    "tool_input_fingerprint": hashlib.sha256(
                        json.dumps(
                            {"command": "managed-run"},
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                    "tool_name": "Bash",
                    "tool_input": {"command": "managed-run"},
                    "tool_response": {
                        "exit_code": 0,
                        "stderr": "",
                        "stdout": projection.decode("utf-8"),
                    },
                }
            )
            hook_result = subprocess.run(
                [sys.executable, str(hook)],
                input=hook_input,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(hook_result.returncode, 0, hook_result.stderr)
            with self.assertRaises(CompletionCoverageFailure):
                coverage_adapter.record_once(coverage_input)

    def test_r5_admission_fingerprint_covers_every_nested_evidence_owner(self) -> None:
        """One receipt oracle proves every U-06 nested owner enters the preimage."""
        physical_uuid = "GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        mig_uuid = "MIG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        nested_lock = LockReadback(
            runtime_root="/var/lib/agent-canon/runtime",
            filesystem_type="ext4",
            device=7,
            inode=11,
            selected=(),
            fingerprint="1" * 64,
        )
        reservation = ReservationEvidence(
            schema_version="gpu-reservation/v1",
            selected_uuids=(mig_uuid,),
            locks=(nested_lock,),
            disposition="ACQUIRED",
            evidence_fingerprint="2" * 64,
        )
        lock_readback = replace(nested_lock, selected=(reservation,))
        process = ProcessIdentity(
            pid=401,
            process_start_identity="401:17",
            gpu_uuid=mig_uuid,
            relationship="direct",
            observation_timestamp="2026-07-18T00:00:00Z",
            observation_fingerprint="3" * 64,
            container_namespace_identity="pid:[4026531836]",
        )
        occupancy = ProcessOccupancyEvidence(
            schema_version="gpu-process-occupancy/v1",
            namespace_inode=4026531836,
            processes=(process,),
            occupied_uuids=(physical_uuid, mig_uuid),
            inventory_scope="local-namespace-complete",
            evidence_fingerprint="4" * 64,
        )
        concurrent = ConcurrentRunEvidence(
            initial_snapshot_fingerprint="5" * 64,
            admission_snapshot_fingerprint="6" * 64,
            final_snapshot_fingerprint="7" * 64,
            initial_event_id="S0",
            admission_event_id="S-lock",
            final_event_id="S-final",
            fingerprint="8" * 64,
        )
        mig = MigEvidence(
            parent_by_uuid={mig_uuid: physical_uuid},
            executable_leaf_uuids=(mig_uuid,),
            selected_physical_uuids=(),
            fingerprint="9" * 64,
        )
        visibility = UuidVisibilityEvidence(
            cuda_visible_devices=mig_uuid,
            nvidia_visible_devices=mig_uuid,
            disposition="explicit",
            visible_uuids=(mig_uuid,),
            namespace_id="pid:[4026531836]",
            provision_receipt_fingerprint="a" * 64,
            fingerprint="b" * 64,
        )
        placement = LockPlacementEvidence(
            runtime_root="/var/lib/agent-canon/runtime",
            filesystem_type="ext4",
            filesystem_source="/dev/nvme0n1p1",
            device=7,
            inode=13,
            group_name="agent-canon-runtime",
            mode="0660",
            local_flock_filesystem=True,
            fingerprint="c" * 64,
        )
        descendants = DescendantRetentionEvidence(
            child_process_ids=(401,),
            process_group_ids=(401,),
            descendant_quiescence="PROVEN",
            retained_gpu_process_uuids=(),
            release_blocked=False,
            fingerprint="d" * 64,
        )
        base = RunGpuAdmissionReceipt(
            schema_version="gpu-admission/v1",
            candidate_uuids=(mig_uuid,),
            occupied_uuids=(),
            reserved_uuids=(),
            selected_uuids=(mig_uuid,),
            inventory_fingerprint="e" * 64,
            occupancy_fingerprint="f" * 64,
            reservation_fingerprint="0" * 64,
            runtime_identity_fingerprint="1" * 64,
            plan_fingerprint="2" * 64,
            admission_fingerprint="",
            lock_readback=lock_readback,
            effective_environment={"CUDA_VISIBLE_DEVICES": mig_uuid},
            actual_gpu_processes=(occupancy,),
            concurrent_run_evidence=concurrent,
            mig_evidence=mig,
            container_visible_uuid_mapping=visibility,
            os_safe_lock_placement=placement,
            descendant_retention_evidence=descendants,
        )
        variants = {
            "lock": replace(
                base,
                lock_readback=replace(lock_readback, fingerprint="e" * 64),
                admission_fingerprint="",
            ),
            "environment": replace(
                base,
                effective_environment={"CUDA_VISIBLE_DEVICES": physical_uuid},
                admission_fingerprint="",
            ),
            "process": replace(
                base,
                actual_gpu_processes=(
                    replace(occupancy, evidence_fingerprint="f" * 64),
                ),
                admission_fingerprint="",
            ),
            "concurrent": replace(
                base,
                concurrent_run_evidence=replace(concurrent, final_event_id="S-final-2"),
                admission_fingerprint="",
            ),
            "mig": replace(
                base,
                mig_evidence=replace(mig, selected_physical_uuids=(physical_uuid,)),
                admission_fingerprint="",
            ),
            "visibility": replace(
                base,
                container_visible_uuid_mapping=replace(
                    visibility,
                    namespace_id="pid:[4026531837]",
                ),
                admission_fingerprint="",
            ),
            "placement": replace(
                base,
                os_safe_lock_placement=replace(placement, inode=14),
                admission_fingerprint="",
            ),
            "descendant": replace(
                base,
                descendant_retention_evidence=replace(
                    descendants,
                    retained_gpu_process_uuids=(mig_uuid,),
                ),
                admission_fingerprint="",
            ),
        }
        for owner, variant in variants.items():
            with self.subTest(owner=owner):
                self.assertNotEqual(
                    base.admission_fingerprint,
                    variant.admission_fingerprint,
                )
        assert base.effective_environment is not None
        with self.assertRaises(TypeError):
            base.effective_environment["CUDA_VISIBLE_DEVICES"] = physical_uuid  # type: ignore[index]

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

    def _fixture_evidence(self, record_id: str) -> tuple[EvidenceFd, dict[str, object]]:
        """Open one manifest-named raw fixture and verify its captured hash."""
        fixture_root = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "nvidia"
        manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
        record = next(item for item in manifest["records"] if item["id"] == record_id)
        path = fixture_root / record["raw_file"]
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            raw = os.pread(descriptor, metadata.st_size, 0)
            self.assertEqual(metadata.st_size, record.get("byte_count", metadata.st_size))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["raw_sha256"])
            expected = dict(record["expected"])
            expected["parser"] = record["parser"]
            return (
                EvidenceFd(
                    fd=descriptor,
                    source_name=record["raw_file"],
                    st_dev=metadata.st_dev,
                    st_ino=metadata.st_ino,
                    byte_count=metadata.st_size,
                    sha256=hashlib.sha256(raw).hexdigest(),
                ),
                expected,
            )
        except BaseException:
            os.close(descriptor)
            raise

    def _assert_fixture_failure(self, record_id: str) -> None:
        evidence, expected = self._fixture_evidence(record_id)
        try:
            with self.assertRaises(TypedPreflightFailure) as raised:
                if expected["parser"] == "nvidia_smi_list":
                    parse_nvidia_smi_list(evidence)
                else:
                    parse_nvidia_smi_xml(evidence)
            self.assertEqual(raised.exception.code, expected["failure_code"])
        finally:
            os.close(evidence.fd)

    def _fixture_nvidia_inventory(self):
        list_evidence, _ = self._fixture_evidence("list.valid.physical_mig")
        xml_evidence, _ = self._fixture_evidence("xml.valid.pi_comment")
        parsed_xml = parse_nvidia_smi_xml(xml_evidence)
        inventory = NvidiaInventoryProbe(
            list_evidence=list_evidence,
            xml_evidence=xml_evidence,
        ).observe()
        return inventory, parsed_xml.process_inventory_disposition, (list_evidence, xml_evidence)

    @staticmethod
    def _fixture_process(gpu_uuid: str, pid: int, kind: str = "other_gpu_context") -> ProcessIdentity:
        return ProcessIdentity(
            pid=pid,
            process_start_identity=f"start-{pid}",
            gpu_uuid=gpu_uuid,
            kind=kind,
            relationship="external",
            container_namespace_identity="pid:[4026531836]",
        )

    def test_nvidia_driver_list_xml_fixture_public_parser_family(self) -> None:
        """The public parser family retains one exact full-UUID topology."""
        driver, driver_expected = self._fixture_evidence("driver.valid")
        list_evidence, list_expected = self._fixture_evidence("list.valid.physical_mig")
        xml_evidence, xml_expected = self._fixture_evidence("xml.valid.pi_comment")
        try:
            parsed_driver = parse_nvidia_driver_version(driver)
            parsed_list = parse_nvidia_smi_list(list_evidence)
            parsed_xml = parse_nvidia_smi_xml(xml_evidence)
            inventory = NvidiaInventoryProbe(
                list_evidence=list_evidence,
                xml_evidence=xml_evidence,
                driver_evidence=driver,
            ).observe()
            self.assertEqual(
                (parsed_driver.major, parsed_driver.minor, parsed_driver.patch, parsed_driver.raw),
                (
                    driver_expected["major"],
                    driver_expected["minor"],
                    driver_expected["patch"],
                    driver_expected["raw"],
                ),
            )
            self.assertEqual(parsed_list.physical_uuids, tuple(list_expected["physical_uuids"]))
            self.assertEqual(parsed_list.mig_uuids, tuple(list_expected["mig_uuids"]))
            self.assertEqual(parsed_xml.process_inventory_disposition, xml_expected["disposition"])
            self.assertEqual(parsed_xml.processing_instructions, ("fixture nvidia-smi",))
            self.assertEqual(parsed_xml.comments, (" fixture topology ",))
            self.assertEqual(inventory.joins, parsed_list.joins)
            self.assertEqual(inventory.driver_version, parsed_driver)
            self.assertNotIn("processes", inventory.__dict__)
        finally:
            for evidence in (driver, list_evidence, xml_evidence):
                os.close(evidence.fd)

    def test_nvidia_fixture_list_reject_duplicate_parent_ordinal(self) -> None:
        self._assert_fixture_failure("list.reject.duplicate_parent_ordinal")

    def test_nvidia_fixture_list_reject_duplicate_uuid(self) -> None:
        self._assert_fixture_failure("list.reject.duplicate_uuid")

    def test_nvidia_fixture_list_reject_missing_topology_parent(self) -> None:
        self._assert_fixture_failure("list.reject.missing_topology_parent")

    def test_nvidia_fixture_list_reject_ambiguous_whitespace(self) -> None:
        for record_id in (
            "list.reject.single_space_before_device",
            "list.reject.single_space_after_device",
            "list.reject.tab_before_device",
            "list.reject.cr",
            "list.reject.trailing_space",
            "list.reject.unmatched",
        ):
            with self.subTest(record_id=record_id):
                self._assert_fixture_failure(record_id)

    def test_nvidia_fixture_xml_reject_conflicting_join(self) -> None:
        self._assert_fixture_failure("xml.reject.conflicting_join")

    def test_nvidia_fixture_xml_reject_unsafe_or_unproven_inventory(self) -> None:
        for record_id in (
            "xml.reject.dtd",
            "xml.reject.entity",
            "xml.reject.hidden_process_inventory",
            "xml.reject.ambiguous_scope",
        ):
            with self.subTest(record_id=record_id):
                self._assert_fixture_failure(record_id)

    def test_nvidia_fixture_xml_accept_complete_empty(self) -> None:
        evidence, expected = self._fixture_evidence("xml.valid.complete_empty")
        try:
            parsed = parse_nvidia_smi_xml(evidence)
            self.assertEqual(parsed.process_inventory_disposition, expected["disposition"])
        finally:
            os.close(evidence.fd)

    def test_gpu_process_occupancy_closes_physical_to_full_mig_scope(self) -> None:
        """Any physical holder conservatively occupies its physical and MIG units."""
        inventory, disposition, descriptors = self._fixture_nvidia_inventory()
        try:
            probe = GpuProcessOccupancyProbe(
                inventory=inventory,
                namespace_inode=4026531836,
                processes=(self._fixture_process(inventory.physical_uuids[0], 123),),
                process_inventory_disposition=disposition,
            )
            evidence = probe.observe()
            self.assertIsInstance(evidence, ProcessOccupancyEvidence)
            self.assertEqual(evidence.schema_version, "gpu-process-occupancy/v1")
            self.assertEqual(evidence.inventory_scope, "local-namespace-complete")
            self.assertEqual(
                evidence.occupied_uuids,
                (
                    "GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "MIG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                ),
            )
            self.assertEqual(len(evidence.processes), 1)
            self.assertNotIn("reservation", probe.__dict__)
        finally:
            for descriptor in descriptors:
                os.close(descriptor.fd)

    def test_gpu_process_occupancy_excludes_mig_leaf_and_physical_parent(self) -> None:
        """A MIG holder conservatively excludes its leaf and physical parent."""
        inventory, disposition, descriptors = self._fixture_nvidia_inventory()
        try:
            evidence = GpuProcessOccupancyProbe(
                inventory=inventory,
                namespace_inode=4026531836,
                processes=(self._fixture_process(inventory.mig_uuids[0], 124, "graphics"),),
                process_inventory_disposition=disposition,
            ).observe()
            self.assertEqual(
                evidence.occupied_uuids,
                (
                    "GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "MIG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                ),
            )
        finally:
            for descriptor in descriptors:
                os.close(descriptor.fd)

    def test_gpu_process_occupancy_fails_closed_without_complete_scope(self) -> None:
        inventory, _, descriptors = self._fixture_nvidia_inventory()
        try:
            with self.assertRaises(TypedPreflightFailure) as raised:
                GpuProcessOccupancyProbe(
                    inventory=inventory,
                    namespace_inode=4026531836,
                    processes=(),
                    process_inventory_disposition="UNPROVEN",
                ).observe()
            self.assertEqual(raised.exception.code, "gpu_process_inventory_unproven")
        finally:
            for descriptor in descriptors:
                os.close(descriptor.fd)

    def test_gpu_process_occupancy_rejects_unknown_full_uuid(self) -> None:
        inventory, disposition, descriptors = self._fixture_nvidia_inventory()
        try:
            with self.assertRaises(TypedPreflightFailure) as raised:
                GpuProcessOccupancyProbe(
                    inventory=inventory,
                    namespace_inode=4026531836,
                    processes=(self._fixture_process("GPU-ffffffffffffffffffffffffffffffff", 125),),
                    process_inventory_disposition=disposition,
                ).observe()
            self.assertEqual(raised.exception.code, "gpu_process_uuid_visibility_unproven")
        finally:
            for descriptor in descriptors:
                os.close(descriptor.fd)

    def test_gpu_process_occupancy_is_one_shot(self) -> None:
        inventory, disposition, descriptors = self._fixture_nvidia_inventory()
        try:
            probe = GpuProcessOccupancyProbe(
                inventory=inventory,
                namespace_inode=4026531836,
                processes=(self._fixture_process(inventory.mig_uuids[0], 126),),
                process_inventory_disposition=disposition,
            )
            probe.observe()
            with self.assertRaises(TypedPreflightFailure) as raised:
                probe.observe()
            self.assertEqual(raised.exception.code, "gpu_process_observation_repeated")
        finally:
            for descriptor in descriptors:
                os.close(descriptor.fd)

    def test_gpu_process_occupancy_rejects_ambiguous_namespace_and_pid(self) -> None:
        inventory, disposition, descriptors = self._fixture_nvidia_inventory()
        try:
            with self.assertRaises(TypedPreflightFailure) as raised_namespace:
                GpuProcessOccupancyProbe(
                    inventory=inventory,
                    namespace_inode=4026531836,
                    processes=(
                        ProcessIdentity(
                            pid=127,
                            process_start_identity="start-127",
                            gpu_uuid=inventory.mig_uuids[0],
                            relationship="external",
                            container_namespace_identity="",
                        ),
                    ),
                    process_inventory_disposition=disposition,
                ).observe()
            self.assertEqual(raised_namespace.exception.code, "gpu_process_namespace_mismatch")
            with self.assertRaises(TypedPreflightFailure) as raised_pid:
                GpuProcessOccupancyProbe(
                    inventory=inventory,
                    namespace_inode=4026531836,
                    processes=(
                        self._fixture_process(inventory.mig_uuids[0], 128),
                        ProcessIdentity(
                            pid=128,
                            process_start_identity="different-start-128",
                            gpu_uuid=inventory.mig_uuids[0],
                            relationship="external",
                            container_namespace_identity="pid:[4026531836]",
                        ),
                    ),
                    process_inventory_disposition=disposition,
                ).observe()
            self.assertEqual(raised_pid.exception.code, "gpu_process_identity_ambiguous")
        finally:
            for descriptor in descriptors:
                os.close(descriptor.fd)

    def test_gpu_reservation_busy_candidate_continues_and_releases_once(self) -> None:
        """A busy candidate closes locally and does not block the next candidate."""
        first = "GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        second = "GPU-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        with tempfile.TemporaryDirectory() as temporary:
            previous_umask = os.umask(0o0007)
            try:
                with patch.object(
                    GpuReservationTransaction,
                    "_read_filesystem_type",
                    return_value="ext4",
                ):
                    first_transaction = GpuReservationTransaction(temporary)
                    first_evidence = first_transaction.try_reserve((first,))
                    self.assertIsInstance(first_evidence, ReservationEvidence)
                    second_transaction = GpuReservationTransaction(temporary)
                    second_evidence = second_transaction.try_reserve((first, second))
                    self.assertEqual(second_evidence.disposition, "ACQUIRED")
                    self.assertEqual(second_evidence.selected_uuids, (second,))
                    self.assertEqual(
                        second_transaction.close()[0].close_attempts,
                        1,
                    )
                    self.assertEqual(
                        first_transaction.close()[0].close_attempts,
                        1,
                    )
            finally:
                os.umask(previous_umask)

    def test_gpu_reservation_tamper_fails_closed_and_rolls_back_all(self) -> None:
        """A tampered record is infrastructure failure, never a candidate-local busy."""
        first = "GPU-cccccccccccccccccccccccccccccccc"
        tampered = "GPU-dddddddddddddddddddddddddddddddd"
        with tempfile.TemporaryDirectory() as temporary:
            previous_umask = os.umask(0o0007)
            try:
                tampered_path = Path(temporary) / f"gpu-{tampered}.lock"
                tampered_path.write_text('{"schema_version":"tampered"}\n', encoding="utf-8")
                tampered_path.chmod(0o660)
                with patch.object(
                    GpuReservationTransaction,
                    "_read_filesystem_type",
                    return_value="ext4",
                ):
                    transaction = GpuReservationTransaction(temporary)
                    with self.assertRaises(TypedPreflightFailure) as raised:
                        transaction.try_reserve((first, tampered), requested_count=2)
                    self.assertEqual(raised.exception.code, "gpu_lock_record_tampered")
                    rollback = transaction.close()
                    self.assertEqual(len(rollback), 2)
                    self.assertTrue(all(item.close_attempts == 1 for item in rollback))
                    retry = GpuReservationTransaction(temporary)
                    retry_evidence = retry.try_reserve((first,))
                    self.assertEqual(retry_evidence.disposition, "ACQUIRED")
                    self.assertEqual(retry.close()[0].close_attempts, 1)
            finally:
                os.umask(previous_umask)

    def test_gpu_reservation_infrastructure_failure_rolls_back_every_held_fd(self) -> None:
        """A later candidate infrastructure failure releases all earlier locks."""
        first = "GPU-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        second = "GPU-ffffffffffffffffffffffffffffffff"
        with tempfile.TemporaryDirectory() as temporary:
            previous_umask = os.umask(0o0007)
            try:
                (Path(temporary) / f"gpu-{second}.lock").symlink_to("missing-target")
                with patch.object(
                    GpuReservationTransaction,
                    "_read_filesystem_type",
                    return_value="ext4",
                ):
                    transaction = GpuReservationTransaction(temporary)
                    with self.assertRaises(TypedPreflightFailure) as raised:
                        transaction.try_reserve((first, second), requested_count=2)
                    self.assertEqual(raised.exception.code, "gpu_lock_open_failed")
                    retry = GpuReservationTransaction(temporary)
                    retry_evidence = retry.try_reserve((first,))
                    self.assertEqual(retry_evidence.disposition, "ACQUIRED")
                    self.assertEqual(retry.close()[0].close_attempts, 1)
            finally:
                os.umask(previous_umask)

    def test_gpu_reservation_partial_exhaustion_rolls_back_every_held_fd(self) -> None:
        """A short candidate list releases partial locks before reporting busy."""
        first = "GPU-11111111111111111111111111111111"
        with tempfile.TemporaryDirectory() as temporary:
            previous_umask = os.umask(0o0007)
            try:
                with patch.object(
                    GpuReservationTransaction,
                    "_read_filesystem_type",
                    return_value="ext4",
                ):
                    transaction = GpuReservationTransaction(temporary)
                    evidence = transaction.try_reserve((first,), requested_count=2)
                    self.assertEqual(evidence.disposition, "BUSY_CANDIDATE")
                    release = transaction.close()
                    self.assertEqual(len(release), 1)
                    self.assertEqual(release[0].close_attempts, 1)
                    retry = GpuReservationTransaction(temporary)
                    retry_evidence = retry.try_reserve((first,))
                    self.assertEqual(retry_evidence.disposition, "ACQUIRED")
                    self.assertEqual(retry.close()[0].close_attempts, 1)
            finally:
                os.umask(previous_umask)

    def build_plan(self, root: Path):
        """Build the public discovery and frozen-plan stages."""
        request = self.make_request(root)
        discovered = discover_test_resources(
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

    def test_source_freeze_fd_snapshot_lineage_and_reverse_release(self) -> None:
        """Source bytes, manifest records, and receipt lineage share one fd freeze."""
        source_root = Path(__file__).resolve().parents[2]
        source_path = "tools/experiments/execution_resource_plan.py"
        with tempfile.TemporaryDirectory() as temporary:
            request = GpuRunRequest(
                gpu_count=0,
                minimum_memory_bytes_per_unit=0,
                max_workers=1,
                host_memory_bytes=1,
                cuda_runtime_library_path=None,
                environment={},
                source_root=str(source_root),
                runtime_route="HOST_DIRECT",
                source_paths=(source_path,),
                planned_chunk_ids=(),
            )
            owner = SourceFreezeOwner(temporary)
            receipt = owner.freeze(request)
            self.assertTrue(owner._owned_fds)
            manifest_path = Path(temporary) / "source_snapshot.json"
            snapshot_path = (
                Path(temporary)
                / "source_snapshot"
                / source_path
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "source-snapshot/v2")
            self.assertEqual(
                manifest["manifest_fingerprint"],
                receipt.snapshot_manifest_fingerprint,
            )
            self.assertEqual(receipt.source_paths, (source_path,))
            self.assertEqual(receipt.snapshot_root_relative_path, "source_snapshot")
            self.assertEqual(receipt.snapshot_relative_path, "source_snapshot.json")
            self.assertEqual(
                snapshot_path.read_bytes(),
                (source_root / source_path).read_bytes(),
            )
            owner.close()
            self.assertEqual(owner._owned_fds, [])

    def test_source_path_set_includes_nonignored_untracked_topic_and_exact_registry(self) -> None:
        """Source membership includes untracked topic files and only the canonical registry edge."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            for relative_path in (
                "tools/experiments/execution_resource_plan.py",
                "tools/experiments/run_managed_experiment.py",
                "tools/experiments/registry_lib.py",
                "tools/agent_tools/jit_canonical_ir.py",
                "experiments/registry.toml",
                "experiments/topic/cases.py",
            ):
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("source\n", encoding="utf-8")
            source_paths = build_source_path_set(str(root), "topic", ())
            self.assertIn("experiments/registry.toml", source_paths)
            self.assertIn("experiments/topic/cases.py", source_paths)
            self.assertNotIn("tools/experiments/experiments_registry.toml", source_paths)

    def test_source_path_set_fails_closed_when_exact_registry_is_missing(self) -> None:
        """The fixed registry closure is required and has no alternate spelling."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            for relative_path in (
                "tools/experiments/execution_resource_plan.py",
                "tools/experiments/run_managed_experiment.py",
                "tools/experiments/registry_lib.py",
                "tools/agent_tools/jit_canonical_ir.py",
                "experiments/topic/run.py",
            ):
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("source\n", encoding="utf-8")

            with self.assertRaises(TypedPreflightFailure) as raised:
                build_source_path_set(str(root), "topic", ())

            self.assertEqual(
                raised.exception.code,
                "gpu_source_path_registry_missing",
            )

    def test_source_freeze_failure_preserves_primary_and_typed_close_secondary(self) -> None:
        """Failure cleanup keeps the primary and exposes one attempted close ambiguity."""
        source_root = Path(__file__).resolve().parents[2]
        request = GpuRunRequest(
            gpu_count=0,
            minimum_memory_bytes_per_unit=0,
            max_workers=1,
            host_memory_bytes=1,
            cuda_runtime_library_path=None,
            environment={},
            source_root=str(source_root),
            runtime_route="HOST_DIRECT",
            source_paths=("tools/experiments/execution_resource_plan.py",),
            planned_chunk_ids=(),
        )
        primary = TypedPreflightFailure(
            "gpu_source_freeze_primary",
            "injected primary source-freeze failure",
        )
        with tempfile.TemporaryDirectory() as temporary:
            owner = SourceFreezeOwner(temporary)
            root_fd: list[int] = []
            close_calls: list[int] = []
            real_close = os.close

            def fail_identity(_identity_fd: int) -> tuple[str, str]:
                assert owner._source_root_fd is not None
                root_fd.append(owner._source_root_fd)
                raise primary

            def close_once_with_ambiguity(descriptor: int) -> None:
                close_calls.append(descriptor)
                if root_fd and descriptor == root_fd[0]:
                    raise OSError(5, "injected close ambiguity")
                real_close(descriptor)

            with patch(
                "tools.experiments.execution_resource_plan._read_git_identity",
                side_effect=fail_identity,
            ), patch(
                "tools.experiments.execution_resource_plan.os.close",
                side_effect=close_once_with_ambiguity,
            ):
                with self.assertRaises(TypedPreflightFailure) as raised:
                    owner.freeze(request)

            self.assertIs(raised.exception, primary)
            self.assertIsNotNone(raised.exception.__cause__)
            assert raised.exception.__cause__ is not None
            close_failure = raised.exception.__cause__
            assert isinstance(close_failure, TypedPreflightFailure)
            self.assertEqual(close_failure.code, "gpu_descriptor_close_ambiguous")
            self.assertTrue(close_failure.evidence["attempted_once"])
            self.assertEqual(close_calls.count(root_fd[0]), 1)
            self.assertEqual(owner._owned_fds, [])
            real_close(root_fd[0])

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
            release_observation = ResourceObservation(
                caller_allocated_ids=frozenset({"GPU-0001"}),
                process_identities=(),
                gpu_devices=(GPUDevice("GPU-0001", 4096, 8192),),
                free_memory_bytes={"GPU-0001": 4096},
                boot_id="boot-1",
                container_visible_ids=frozenset({"GPU-0001"}),
                observed_at="release-observation",
            )
            lease.release(
                observation_supplier=lambda: release_observation,
            )
            reclaim_observations = iter(
                (
                    ResourceObservation(
                        caller_allocated_ids=frozenset({"GPU-0001"}),
                        process_identities=(),
                        gpu_devices=(GPUDevice("GPU-0001", 4096, 8192),),
                        free_memory_bytes={"GPU-0001": 4096},
                        boot_id="boot-1",
                        container_visible_ids=frozenset({"GPU-0001"}),
                        observed_at="reclaim-prelock-observation",
                    ),
                    ResourceObservation(
                        caller_allocated_ids=frozenset({"GPU-0001"}),
                        process_identities=(),
                        gpu_devices=(GPUDevice("GPU-0001", 4096, 8192),),
                        free_memory_bytes={"GPU-0001": 4096},
                        boot_id="boot-1",
                        container_visible_ids=frozenset({"GPU-0001"}),
                        observed_at="reclaim-under-lock-observation",
                    ),
                )
            )
            evidence = store.reclaim_stale(
                "GPU-0001",
                observation_supplier=lambda: next(reclaim_observations),
                process_start_identity=lambda _pid: None,
            )
            self.assertTrue(evidence.reclaimed)
            self.assertTrue(evidence.under_lock_proof["record_reread_under_lock"])
            self.assertTrue(evidence.persistence_witness["path"])


if __name__ == "__main__":
    unittest.main()
