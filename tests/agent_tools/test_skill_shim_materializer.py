"""Focused tests for the canonical skill runtime shim materializer."""

# @dependency-start
# contract test
# responsibility Verifies 60-row materializer fixed-point and readback evidence.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md approved materializer contract
# upstream implementation ../../tools/agent_tools/skill_shim_materializer.py single shim writer
# downstream implementation ../../tests/fixtures/skill-runtime-shim/fixed-point/expected.json fixed-point oracle
# @dependency-end

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS_ROOT))

from skill_shim_materializer import fixed_point_acceptance  # noqa: E402


class SkillShimMaterializerTest(unittest.TestCase):
    """Verify materialization converges without a second writer."""

    def test_materialize_fixed_point(self) -> None:
        """Two runs preserve all records/projections and the second run is empty."""
        actual = fixed_point_acceptance(PROJECT_ROOT)
        expected = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/skill-runtime-shim/fixed-point/expected.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(actual, expected)
        self.assertEqual(actual["second_run"]["content_delta_count"], 0)
        self.assertEqual(len(actual["first_run"]["record_digests"]), 60)
        self.assertEqual(len(actual["first_run"]["projection_digests"]), 60)
        self.assertEqual(actual["status"], "pass")


if __name__ == "__main__":
    unittest.main()
