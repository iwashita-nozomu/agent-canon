"""Focused regression tests for staged GPU build capability receipts."""

# @dependency-start
# contract test
# responsibility Verifies fail-closed GPU build admission, WSL thunk diagnosis, and runtime/build separation.
# upstream design ../../documents/design/environment-resolution-gpu-build-capability.md staged GPU build capability contract
# upstream implementation ../../tools/agent_tools/gpu_build_capability.py typed receipt and decision model
# upstream data ../fixtures/environment_resolution/wsl2_rootless_nvml_failed.json sanitized WSL2 failure readback
# upstream data ../fixtures/environment_resolution/wsl2_rootless_cuda_build_repaired.json sanitized WSL2 repaired readback
# @dependency-end

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent_tools.gpu_build_capability import (  # noqa: E402
    BuildCapability,
    BuilderDriver,
    DaemonMode,
    FINDING_GPU_BUILD_ENVIRONMENT_UNAVAILABLE,
    GpuBuildCapabilityReceipt,
    HANDOFF_OWNER,
    HANDOFF_REQUIREMENTS,
    ReceiptError,
    State,
    Stage,
    load_gpu_build_capability_receipt,
)

FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "environment_resolution"
FAILED_FIXTURE = FIXTURE_ROOT / "wsl2_rootless_nvml_failed.json"
REPAIRED_FIXTURE = FIXTURE_ROOT / "wsl2_rootless_cuda_build_repaired.json"


class GpuBuildCapabilityReceiptTest(unittest.TestCase):
    """Keep build capability as a conjunction of build-only stage receipts."""

    def setUp(self) -> None:
        self.failed_raw = json.loads(FAILED_FIXTURE.read_text(encoding="utf-8"))

    def test_wsl2_failure_preserves_lower_stages_and_finds_missing_thunk(self) -> None:
        receipt = load_gpu_build_capability_receipt(FAILED_FIXTURE)
        decision = receipt.decide()

        self.assertEqual(receipt.builder.builder_name, "rootless")
        self.assertEqual(receipt.builder.daemon_mode, DaemonMode.ROOTLESS)
        self.assertEqual(receipt.builder.builder_driver, BuilderDriver.DOCKER)
        self.assertEqual(receipt.state(Stage.DEVICE_ENTITLEMENT), State.SUPPORTED)
        self.assertEqual(receipt.state(Stage.CDI_INVENTORY), State.MATCHED)
        self.assertEqual(receipt.state(Stage.RUN_DEVICE_REQUEST), State.ACCEPTED)
        self.assertEqual(receipt.state(Stage.DEVICE_NODES), State.PRESENT)
        self.assertEqual(receipt.state(Stage.DRIVER_LOADER), State.PARTIAL)
        self.assertEqual(
            receipt.state(Stage.CUDA_DRIVER_API), State.FAILED_INITIALIZATION
        )
        self.assertEqual(decision.capability, BuildCapability.UNAVAILABLE)
        self.assertEqual(decision.blocking_stage, Stage.DRIVER_LOADER)
        self.assertEqual(decision.blocking_state, State.PARTIAL)
        self.assertEqual(
            decision.incomplete_stages,
            (
                Stage.DRIVER_LOADER,
                Stage.CUDA_DRIVER_API,
                Stage.CUDA_COMPILE_RUN,
            ),
        )

    def test_runtime_cdi_pass_cannot_promote_build_time_failure(self) -> None:
        receipt = GpuBuildCapabilityReceipt.from_mapping(self.failed_raw)
        decision = receipt.decide()

        self.assertEqual(receipt.state(Stage.RUNTIME_CDI), State.PASSED)
        self.assertEqual(decision.runtime_cdi, State.PASSED)
        self.assertEqual(decision.capability, BuildCapability.UNAVAILABLE)
        self.assertEqual(decision.finding, FINDING_GPU_BUILD_ENVIRONMENT_UNAVAILABLE)
        self.assertEqual(decision.handoff_owner, HANDOFF_OWNER)
        self.assertEqual(decision.handoff_requirements, HANDOFF_REQUIREMENTS)

    def test_repaired_wsl_builder_is_ready_with_exact_two_device_identity(self) -> None:
        receipt = load_gpu_build_capability_receipt(REPAIRED_FIXTURE)
        decision = receipt.decide()

        self.assertEqual(decision.capability, BuildCapability.READY)
        self.assertEqual(decision.incomplete_stages, ())
        self.assertIsNone(decision.finding)
        self.assertEqual(
            receipt.builder.requested_devices,
            ("nvidia.com/gpu=all", "local.wsl/cuda-build=all"),
        )
        self.assertEqual(receipt.state(Stage.DRIVER_LOADER), State.COMPLETE)
        self.assertEqual(receipt.state(Stage.CUDA_DRIVER_API), State.READY)
        self.assertEqual(receipt.state(Stage.CUDA_COMPILE_RUN), State.PASSED)
        self.assertIn(
            "RTX 2080 capability=7.5",
            receipt.evidence[Stage.CUDA_DRIVER_API].observations,
        )
        self.assertEqual(decision.handoff_owner, HANDOFF_OWNER)
        self.assertEqual(decision.handoff_requirements, HANDOFF_REQUIREMENTS)

    def test_runtime_state_is_independent_even_when_build_is_ready(self) -> None:
        raw = json.loads(REPAIRED_FIXTURE.read_text(encoding="utf-8"))
        raw["stages"]["runtime_cdi"] = "unverified"
        decision = GpuBuildCapabilityReceipt.from_mapping(raw).decide()

        self.assertEqual(decision.capability, BuildCapability.READY)
        self.assertEqual(decision.runtime_cdi, State.UNVERIFIED)
        self.assertIsNone(decision.blocking_stage)

    def test_independent_stage_observations_fail_closed_at_first_gap(self) -> None:
        raw = copy.deepcopy(self.failed_raw)
        raw["stages"].update(
            {
                "run_device_request": "rejected",
                "device_nodes": "present",
                "driver_loader": "complete",
                "cuda_driver_api": "unverified",
                "cuda_compile_run": "not_attempted",
            }
        )
        raw["evidence"]["run_device_request"]["exit_code"] = 1
        decision = GpuBuildCapabilityReceipt.from_mapping(raw).decide()

        self.assertEqual(decision.blocking_stage, Stage.RUN_DEVICE_REQUEST)
        self.assertEqual(decision.blocking_state, State.REJECTED)
        self.assertEqual(
            decision.incomplete_stages,
            (
                Stage.RUN_DEVICE_REQUEST,
                Stage.CUDA_DRIVER_API,
                Stage.CUDA_COMPILE_RUN,
            ),
        )

    def test_cdi_inventory_state_matches_every_requested_identity(self) -> None:
        missing = copy.deepcopy(self.failed_raw)
        missing["builder"]["cdi_devices"] = []
        missing["stages"]["cdi_inventory"] = "missing"
        decision = GpuBuildCapabilityReceipt.from_mapping(missing).decide()
        self.assertEqual(decision.blocking_stage, Stage.CDI_INVENTORY)

        inconsistent = json.loads(REPAIRED_FIXTURE.read_text(encoding="utf-8"))
        inconsistent["builder"]["cdi_devices"] = ["nvidia.com/gpu=all"]
        with self.assertRaisesRegex(ReceiptError, "every requested device"):
            GpuBuildCapabilityReceipt.from_mapping(inconsistent)

        unresolved = copy.deepcopy(inconsistent)
        unresolved["stages"]["cdi_inventory"] = "unresolved"
        receipt = GpuBuildCapabilityReceipt.from_mapping(unresolved)
        self.assertEqual(receipt.state(Stage.CDI_INVENTORY), State.UNRESOLVED)

    def test_builder_mode_driver_and_evidence_exit_are_typed(self) -> None:
        unknown_driver = copy.deepcopy(self.failed_raw)
        unknown_driver["builder"]["builder_driver"] = "dockerish"
        with self.assertRaisesRegex(ReceiptError, "unknown value"):
            GpuBuildCapabilityReceipt.from_mapping(unknown_driver)

        impossible_success = copy.deepcopy(self.failed_raw)
        impossible_success["stages"]["driver_loader"] = "complete"
        impossible_success["evidence"]["driver_loader"]["exit_code"] = 1
        with self.assertRaisesRegex(ReceiptError, "requires evidence.exit_code=0"):
            GpuBuildCapabilityReceipt.from_mapping(impossible_success)

        impossible_failure = copy.deepcopy(self.failed_raw)
        impossible_failure["evidence"]["cuda_driver_api"]["exit_code"] = 0
        with self.assertRaisesRegex(ReceiptError, "requires non-zero"):
            GpuBuildCapabilityReceipt.from_mapping(impossible_failure)

    def test_unknown_stage_state_is_rejected_instead_of_inferred(self) -> None:
        raw = copy.deepcopy(self.failed_raw)
        raw["stages"]["cuda_driver_api"] = "probably_ready"

        with self.assertRaisesRegex(ReceiptError, "unknown state"):
            GpuBuildCapabilityReceipt.from_mapping(raw)

    def test_missing_stage_and_unbounded_summary_are_rejected(self) -> None:
        missing = copy.deepcopy(self.failed_raw)
        del missing["stages"]["cdi_inventory"]
        with self.assertRaisesRegex(ReceiptError, "keys mismatch"):
            GpuBuildCapabilityReceipt.from_mapping(missing)

        unbounded = copy.deepcopy(self.failed_raw)
        unbounded["evidence"]["cuda_driver_api"]["summary"] = "x" * 241
        with self.assertRaisesRegex(ReceiptError, "exceeds 240"):
            GpuBuildCapabilityReceipt.from_mapping(unbounded)

    def test_exact_failure_evidence_is_retained_without_path_or_runtime_inference(self) -> None:
        receipt = GpuBuildCapabilityReceipt.from_mapping(self.failed_raw)

        self.assertEqual(receipt.builder.requested_devices, ("nvidia.com/gpu=all",))
        self.assertEqual(receipt.builder.cdi_devices, ("nvidia.com/gpu=all",))
        self.assertIn("/dev/dxg", receipt.evidence[Stage.DEVICE_NODES].observations)
        self.assertIn(
            "BuildKit CDI: WSL thunk libcuda.so.1 absent",
            receipt.evidence[Stage.DRIVER_LOADER].observations,
        )
        self.assertIn(
            "cudaGetDeviceCount: status 35",
            receipt.evidence[Stage.CUDA_DRIVER_API].observations,
        )
        self.assertEqual(
            receipt.evidence[Stage.RUNTIME_CDI].observations,
            ("NVIDIA GeForce RTX 2080", "NVIDIA GeForce RTX 2080"),
        )


if __name__ == "__main__":
    unittest.main()
