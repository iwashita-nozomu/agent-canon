"""Focused tests for the typed retirement guard."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from check_hook_retirement import check_payload, contract_payload  # noqa: E402
from hook_retirement import MOVED_SOURCE_ABSENCES, RETIRED_CHILD_TOMBSTONES, source_digest  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class HookRetirementTest(unittest.TestCase):
    def test_manifest_counts_and_digest(self) -> None:
        self.assertEqual(len(RETIRED_CHILD_TOMBSTONES), 23)
        self.assertEqual(len(MOVED_SOURCE_ABSENCES), 1)
        self.assertRegex(source_digest(), r"^[0-9a-f]{64}$")

    def test_actual_tree_distinguishes_moved_safety_source_from_retired_children(self) -> None:
        """The moved safety owner is allowed while its old hook path remains absent."""
        payload = contract_payload(PROJECT_ROOT)
        caller_audit = payload["caller_audit"]

        self.assertEqual(check_payload(payload), [])
        self.assertFalse((PROJECT_ROOT / ".codex" / "hooks" / "hook_safety.py").exists())
        self.assertTrue((PROJECT_ROOT / "tools" / "agent_tools" / "hook_safety.py").is_file())
        self.assertEqual(caller_audit["moved_source_old_paths"], [".codex/hooks/hook_safety.py"])
        self.assertNotIn("hook_safety.py", caller_audit["retired_child_basenames"])
        self.assertNotIn(
            "tools/agent_tools/hook_safety.py",
            payload["generated_inventory_paths"],
        )


if __name__ == "__main__":
    unittest.main()
