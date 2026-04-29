"""Tests for the refactor surface analyzer."""

# @dependency-start
# responsibility Tests test analyze refactor surface behavior.
# upstream implementation ../../tools/agent_tools/analyze_refactor_surface.py analyzer
# upstream design ../../agents/workflows/comprehensive-refactoring-workflow.md analyzer gate policy
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYZER = PROJECT_ROOT / "tools" / "agent_tools" / "analyze_refactor_surface.py"


class AnalyzeRefactorSurfaceTest(unittest.TestCase):
    """Verify analyzer scoring and finding output."""

    def test_small_file_passes(self) -> None:
        """A small function-only module should pass the default score gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "small.py"
            source.write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(ANALYZER), "--root", str(root), str(source)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REFACTOR_SURFACE_FILES=1", result.stdout)
            self.assertIn("REFACTOR_SURFACE_VIOLATIONS=0", result.stdout)
            self.assertIn("REFACTOR_SURFACE=pass", result.stdout)

    def test_long_function_can_fail_score_gate(self) -> None:
        """A long function is reported and can fail a high score gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            body = "\n".join(f"    value += {index}" for index in range(12))
            source = root / "long_function.py"
            source.write_text(
                f"def too_long() -> int:\n    value = 0\n{body}\n    return value\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ANALYZER),
                    "--root",
                    str(root),
                    "--max-function-lines",
                    "5",
                    "--min-score",
                    "100",
                    str(source),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("VIOLATION=long_function.py:1:function_lines:too_long:", result.stdout)
            self.assertIn("REFACTOR_SURFACE=fail", result.stdout)

    def test_public_method_count_is_reported(self) -> None:
        """A class with too many public methods should be flagged."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            methods = "\n".join(
                f"    def method_{index}(self) -> None:\n        return None"
                for index in range(4)
            )
            source = root / "class_surface.py"
            source.write_text(f"class TooWide:\n{methods}\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ANALYZER),
                    "--root",
                    str(root),
                    "--max-public-methods",
                    "2",
                    str(source),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("VIOLATION=class_surface.py:1:public_methods:TooWide:4>2", result.stdout)
            self.assertIn("REFACTOR_SURFACE_SCORE=95", result.stdout)
