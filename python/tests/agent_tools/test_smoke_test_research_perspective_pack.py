"""Smoke-test coverage for the research perspective pack helper."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts" / "agent_tools" / "smoke_test_research_perspective_pack.py"
)


class ResearchPerspectivePackSmokeTest(unittest.TestCase):
    """Verify that the smoke-test helper exits successfully."""

    def test_smoke_script_passes(self) -> None:
        """The helper should report a passing smoke test on the checked-in config."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SMOKE_TEST=pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
