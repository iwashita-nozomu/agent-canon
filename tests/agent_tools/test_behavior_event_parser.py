"""Readback tests for canonical behavior event parsing."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from behavior_event_assembly import parse_behavior_events  # noqa: E402


class BehaviorEventParserTest(unittest.TestCase):
    def test_missing_file_is_read_only_missing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(parse_behavior_events(Path(temporary) / "behavior_events.jsonl").status, "missing")


if __name__ == "__main__":
    unittest.main()
