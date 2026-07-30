"""Focused tests for the typed retirement guard."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from hook_retirement import MOVED_SOURCE_ABSENCES, RETIRED_CHILD_TOMBSTONES, source_digest  # noqa: E402


class HookRetirementTest(unittest.TestCase):
    def test_manifest_counts_and_digest(self) -> None:
        self.assertEqual(len(RETIRED_CHILD_TOMBSTONES), 23)
        self.assertEqual(len(MOVED_SOURCE_ABSENCES), 1)
        self.assertRegex(source_digest(), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
