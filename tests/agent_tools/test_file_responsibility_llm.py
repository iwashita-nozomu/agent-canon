"""Tests for single-file local LLM responsibility review."""

# @dependency-start
# responsibility Tests single-file local LLM responsibility review.
# upstream implementation ../../tools/agent_tools/file_responsibility_llm.py renders local LLM prompts
# upstream design ../../documents/local-llm-responsibility-analysis.md single-file scope policy
# @dependency-end

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
