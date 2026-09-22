"""Execute the documented ordinary GPU command with recording native-tool fakes."""

# @dependency-start
# contract test
# responsibility Checks native Docker device selection, argument preservation, and exit behavior without GPU admission prerequisites.
# upstream design ../../agents/skills/gpu-execution.md ordinary GPU command under test
# upstream design ../../agents/skills/environment-maintenance.md image execution guidance
# upstream design ../../documents/experiments/gpu-direct-command.md optional admission boundary
# upstream design ../../tools/README.md project GPU execution guidance
# @dependency-end

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GPU_SKILL = PROJECT_ROOT / "agents/skills/gpu-execution.md"
GPU_ENVIRONMENT_NAMES = (
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "JAX_PLATFORMS",
    "XLA_PYTHON_CLIENT_PREALLOCATE",
    "XLA_PYTHON_CLIENT_ALLOCATOR",
    "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR",
)


class GpuExecutionDockerRoutingContractTest(unittest.TestCase):
    """Test the shell example itself, not a second implementation of its argv."""

    def test_native_device_selection_without_admission_environment(self) -> None:
        text = GPU_SKILL.read_text(encoding="utf-8")
        command = text.split("```bash\n", 1)[1].split("```", 1)[0]
        payload = ["python3", "script with spaces.py", "literal; echo not-a-command"]
        for gpu in ("1", "GPU-01234567-89ab-cdef-0123-456789abcdef"):
            for exit_code in (0, 23, 125):
                with self.subTest(gpu=gpu, exit_code=exit_code):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        calls_path = root / "calls.jsonl"
                        fake = (
                            f"#!{sys.executable}\n"
                            "import json, os, pathlib, sys\n"
                            "name = pathlib.Path(sys.argv[0]).name\n"
                            "with open(os.environ['GPU_TEST_CALLS'], 'a') as output:\n"
                            "    output.write(json.dumps([name, *sys.argv[1:]]) + '\\n')\n"
                            "sys.exit(int(os.environ['GPU_TEST_EXIT']) if name == 'docker' else 0)\n"
                        )
                        for name in ("nvidia-smi", "docker"):
                            executable = root / name
                            executable.write_text(fake, encoding="utf-8")
                            executable.chmod(0o755)
                        environment = {
                            key: value for key, value in os.environ.items()
                            if key not in GPU_ENVIRONMENT_NAMES
                        }
                        environment.update(
                            PATH=f"{root}{os.pathsep}{os.defpath}",
                            GPU=gpu,
                            IMAGE="project:test",
                            GPU_TEST_CALLS=str(calls_path),
                            GPU_TEST_EXIT=str(exit_code),
                        )
                        result = subprocess.run(
                            ["bash", "-c", command, "gpu-example", *payload],
                            env=environment,
                            capture_output=True,
                            text=True,
                            timeout=10,
                            check=False,
                        )
                        self.assertEqual(result.returncode, exit_code, result.stderr)
                        calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
                        self.assertEqual(calls, [
                            ["docker", "run", "--rm", "--gpus", f"device={gpu}",
                             "project:test", *payload],
                        ])

    def test_environment_and_tool_guidance_use_the_canonical_skill(self) -> None:
        for relative in ("agents/skills/environment-maintenance.md", "tools/README.md"):
            with self.subTest(path=relative):
                text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("gpu-execution.md", text)
                self.assertNotIn("run_gpu_container.sh --image", text)

    def test_admission_contract_is_explicitly_optional(self) -> None:
        text = (PROJECT_ROOT / "documents/experiments/gpu-direct-command.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Applicability", text)
        self.assertIn("only when reservation is explicitly required", text)
        self.assertNotIn("Use the direct route by default", text)
        self.assertIn("## Admission state machine", text)
        self.assertIn("## Child lifecycle and lock retention", text)


if __name__ == "__main__":
    unittest.main()
