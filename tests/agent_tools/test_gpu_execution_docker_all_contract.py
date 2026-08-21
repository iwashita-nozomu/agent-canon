"""Regression tests for the single Docker GPU entrypoint and internal routing."""

# @dependency-start
# contract test
# responsibility Tests one public Docker GPU entrypoint, internal CDI/all selection, and environment-skill alignment.
# upstream design ../../agents/skills/gpu-execution.md canonical Docker GPU child wiring
# upstream design ../../agents/skills/environment-maintenance.md canonical image validation boundary
# upstream design ../../documents/experiments/gpu-direct-command.md injection selection contract
# upstream design ../../tools/README.md public Docker GPU invocation documentation
# upstream implementation ../../tools/ci/run_gpu_container.sh route-selecting shell adapter
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GPU_SKILL = PROJECT_ROOT / "agents" / "skills" / "gpu-execution.md"
ENVIRONMENT_SKILL = PROJECT_ROOT / "agents" / "skills" / "environment-maintenance.md"
DESIGN = PROJECT_ROOT / "documents" / "experiments" / "gpu-direct-command.md"
TOOLS_README = PROJECT_ROOT / "tools" / "README.md"
WRAPPER = PROJECT_ROOT / "tools" / "ci" / "run_gpu_container.sh"
GPU_ENVIRONMENT_NAMES = (
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "JAX_PLATFORMS",
    "XLA_PYTHON_CLIENT_PREALLOCATE",
    "XLA_PYTHON_CLIENT_ALLOCATOR",
    "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR",
)


class GpuExecutionDockerRoutingContractTest(unittest.TestCase):
    """Keep one caller contract while the adapter chooses one injection route."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.gpu_text = GPU_SKILL.read_text(encoding="utf-8")
        cls.environment_text = ENVIRONMENT_SKILL.read_text(encoding="utf-8")
        cls.design_text = DESIGN.read_text(encoding="utf-8")
        cls.tools_readme_text = TOOLS_README.read_text(encoding="utf-8")
        cls.wrapper_text = WRAPPER.read_text(encoding="utf-8")
        cls.combined = cls.gpu_text + cls.environment_text + cls.design_text

    def test_public_invocation_has_no_runtime_mode_argument(self) -> None:
        self.assertIn("run_gpu_container.sh", self.gpu_text)
        self.assertIn("--image <canonical-image> -- <argv...>", self.gpu_text)
        self.assertIn("--image <image> [--name <name>] -- <argv...>", self.design_text)
        self.assertNotIn("--image <canonical-image> --gpus", self.gpu_text)
        self.assertNotIn("--image <image> --gpus", self.design_text)
        self.assertIn(
            "run_gpu_container.sh --image <image> -- <argv...>",
            self.tools_readme_text,
        )
        self.assertNotIn(
            "run_gpu_container.sh --image <image> --gpus all",
            self.tools_readme_text,
        )
        self.assertIn(
            "usage: run_gpu_container.sh --image IMAGE [--name NAME] -- COMMAND",
            self.wrapper_text,
        )
        self.assertNotIn("--gpus)\n", self.wrapper_text)
        self.assertNotIn("--device)\n", self.wrapper_text)

    def test_adapter_owns_one_exclusive_capability_branch(self) -> None:
        self.assertIn("DiscoveredDevices", self.combined)
        self.assertIn("individual-cdi", self.combined)
        self.assertIn("gpus-all", self.combined)
        self.assertIn("nvidia.com/gpu=<full UUID/MIG>", self.gpu_text)
        self.assertIn("docker info --format", self.wrapper_text)
        self.assertIn("docker_command+=(--device", self.wrapper_text)
        self.assertIn("docker_command+=(--gpus all)", self.wrapper_text)
        self.assertIn("exact_uuid_devices_discovered", self.wrapper_text)
        self.assertIn("exact_uuid_devices_not_discovered", self.wrapper_text)

    def test_both_routes_keep_exact_full_uuid_environment(self) -> None:
        self.assertIn("full UUID", self.combined)
        self.assertIn("integer index", self.combined)
        self.assertIn("-e NAME=VALUE", self.gpu_text)
        for name in GPU_ENVIRONMENT_NAMES:
            with self.subTest(name=name):
                self.assertIn(name, self.gpu_text)
                self.assertIn(name, self.wrapper_text)

    def test_contract_rejects_alternate_legacy_runtime_mechanisms(self) -> None:
        self.assertNotIn("no-cgroups=true", self.combined)
        self.assertNotIn("nvidia-container-runtime", self.combined)
        self.assertNotIn("--runtime=nvidia", self.combined)
        self.assertNotIn("nvidia-ctk cdi generate", self.combined)

    def test_environment_owner_delegates_gpu_wiring_to_single_entrypoint(self) -> None:
        self.assertIn("agents/skills/gpu-execution.md", self.environment_text)
        self.assertIn(
            "run_gpu_container.sh --image <image> -- <command...>",
            self.environment_text,
        )
        self.assertIn("container内のfresh JAX import", self.environment_text)


if __name__ == "__main__":
    unittest.main()
