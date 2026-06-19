"""Tests for single-file local LLM responsibility review."""

# @dependency-start
# contract test
# responsibility Tests single-file local LLM responsibility review.
# upstream implementation ../../tools/agent_tools/file_responsibility_llm.py renders local LLM prompts
# upstream design ../../documents/local-llm-responsibility-analysis.md single-file scope policy
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "file_responsibility_llm.py"


class FileResponsibilityLlmTest(unittest.TestCase):
    """Exercise local LLM prompt rendering without requiring llama.cpp."""

    def test_print_prompt_for_single_file(self) -> None:
        """Prompt mode should expose single-file scope and deterministic metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "tools" / "example.py"
            target.parent.mkdir(parents=True)
            target.write_text("# @dependency-start\n# responsibility Example.\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--print-prompt",
                    "tools/example.py",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FILE_RESP_LLM_SCOPE=single_file", result.stdout)
        self.assertIn("FILE_RESP_LLM_FILE=tools/example.py", result.stdout)
        self.assertIn("FILE_RESP_LLM_MODEL=ggml-org/SmolLM3-3B-GGUF:Q4_K_M", result.stdout)
        self.assertIn("Do not infer repo-wide ownership.", result.stdout)
        self.assertIn("Responsibility Summary", result.stdout)

    def test_directory_target_fails(self) -> None:
        """The tool must reject directory or repo-wide targets."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "tools").mkdir()

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--print-prompt",
                    "tools",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("single-file target is required", result.stderr)

    def test_llama_invocation_hides_accelerator_devices(self) -> None:
        """The local LLM subprocess should inherit normal env while hiding accelerators."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "tools" / "example.py"
            fake_llama = root / "llama-cli"
            target.parent.mkdir(parents=True)
            target.write_text("# @dependency-start\n# responsibility Example.\n", encoding="utf-8")
            fake_llama.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'CUDA_VISIBLE_DEVICES=%s\\n' \"${CUDA_VISIBLE_DEVICES-unset}\"\n"
                "printf 'NVIDIA_VISIBLE_DEVICES=%s\\n' \"${NVIDIA_VISIBLE_DEVICES-unset}\"\n"
                "printf 'HIP_VISIBLE_DEVICES=%s\\n' \"${HIP_VISIBLE_DEVICES-unset}\"\n"
                "printf 'ROCR_VISIBLE_DEVICES=%s\\n' \"${ROCR_VISIBLE_DEVICES-unset}\"\n"
                "printf 'AGENT_CANON_TEST_MARKER=%s\\n' \"${AGENT_CANON_TEST_MARKER-unset}\"\n",
                encoding="utf-8",
            )
            fake_llama.chmod(0o755)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--llama-cli",
                    str(fake_llama),
                    "tools/example.py",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "CUDA_VISIBLE_DEVICES": "0",
                    "NVIDIA_VISIBLE_DEVICES": "0",
                    "HIP_VISIBLE_DEVICES": "0",
                    "ROCR_VISIBLE_DEVICES": "0",
                    "AGENT_CANON_TEST_MARKER": "kept",
                },
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FILE_RESP_LLM=pass", result.stdout)
        self.assertIn("CUDA_VISIBLE_DEVICES=\n", result.stdout)
        self.assertIn("NVIDIA_VISIBLE_DEVICES=void", result.stdout)
        self.assertIn("HIP_VISIBLE_DEVICES=\n", result.stdout)
        self.assertIn("ROCR_VISIBLE_DEVICES=\n", result.stdout)
        self.assertIn("AGENT_CANON_TEST_MARKER=kept", result.stdout)


if __name__ == "__main__":
    unittest.main()
