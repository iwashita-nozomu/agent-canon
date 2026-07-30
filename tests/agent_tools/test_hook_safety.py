"""Focused tests for the sole pure hook safety owner."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from hook_safety import secret_kind  # noqa: E402


class HookSafetyTest(unittest.TestCase):
    def test_secret_kind_detects_api_key(self) -> None:
        self.assertIsNotNone(secret_kind("sk-abcdefghijklmnopqrstuvwxyz1234567890"))


if __name__ == "__main__":
    unittest.main()
