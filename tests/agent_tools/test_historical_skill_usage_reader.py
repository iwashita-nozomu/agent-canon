"""Focused tests for historical-only skill usage parsing."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from historical_skill_usage_reader import read_skill_usage_history  # noqa: E402


class HistoricalSkillUsageReaderTest(unittest.TestCase):
    def test_reads_valid_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "skill_usage.jsonl"
            path.write_text('{"skills":["task-routing"]}\n', encoding="utf-8")
            self.assertEqual(len(read_skill_usage_history(path).records), 1)


if __name__ == "__main__":
    unittest.main()
