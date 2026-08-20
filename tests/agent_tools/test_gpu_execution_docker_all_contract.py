"""Regression tests for the sole Docker --gpus all route."""

# @dependency-start
# contract test
# responsibility Tests all-only Docker injection, exact environment forwarding, and environment-skill alignment for GPU containers.
# upstream design ../../agents/skills/gpu-execution.md canonical Docker GPU child wiring
# upstream design ../../agents/skills/environment-maintenance.md canonical image validation boundary
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GPU_SKILL = PROJECT_ROOT / "agents" / "skills" / "gpu-execution.md"
ENVIRONMENT_SKILL = PROJECT_ROOT / "agents" / "skills" / "environment-maintenance.md"
GPU_ENVIRONMENT_NAMES = (
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "JAX_PLATFORMS",
    "XLA_PYTHON_CLIENT_PREALLOCATE",
    "XLA_PYTHON_CLIENT_ALLOCATOR",
    "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR",
)


class GpuExecutionDockerAllContractTest(unittest.TestCase):
    """Keep Docker GPU execution on one all-injection/full-UUID contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.gpu_text = GPU_SKILL.read_text(encoding="utf-8")
        cls.environment_text = ENVIRONMENT_SKILL.read_text(encoding="utf-8")

    def test_gpu_skill_declares_all_injection_and_exact_environment(self) -> None:
        self.assertIn("run_gpu_container.sh", self.gpu_text)
        self.assertIn("--gpus all", self.gpu_text)
        self.assertIn("selected full UUID", self.gpu_text)
        for name in GPU_ENVIRONMENT_NAMES:
            with self.subTest(name=name):
                self.assertIn(name, self.gpu_text)

    def test_all_injection_keeps_compute_visibility_on_full_uuid(self) -> None:
        self.assertIn("full UUID", self.gpu_text)
        self.assertIn("integer index", self.gpu_text)

    def test_contract_does_not_restore_legacy_or_cgroup_bypass_examples(self) -> None:
        combined = self.gpu_text + self.environment_text
        self.assertNotIn("--device nvidia.com/gpu=", combined)
        self.assertNotIn("no-cgroups=true", combined)
        self.assertNotIn("nvidia-container-runtime", combined)

    def test_environment_owner_delegates_gpu_wiring_to_gpu_execution(self) -> None:
        self.assertIn("agents/skills/gpu-execution.md", self.environment_text)
        self.assertIn(
            "run_gpu_container.sh --gpus all",
            self.environment_text,
        )
        self.assertIn("container内のfresh JAX import", self.environment_text)


if __name__ == "__main__":
    unittest.main()
