# @dependency-start
# responsibility Tests test log agent learning behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for the agent learning logging tool."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "log_agent_learning.py"


class LogAgentLearningTest(unittest.TestCase):
    """Verify agent philosophy note updates."""

    def test_creates_note_and_appends_interaction_observation(self) -> None:
        """The tool should create the note and write an interaction observation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            note_path = Path(tmp_dir) / "AGENT_PHILOSOPHY.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--kind",
                    "interaction-observation",
                    "--statement",
                    "対話から agent-side learning を抽出する",
                    "--source",
                    "chat",
                    "--evidence",
                    "user requested agent personality formation",
                    "--scope",
                    "repo-wide",
                    "--confidence",
                    "tentative",
                    "--observed-on",
                    "2026-04-10",
                    "--note-path",
                    str(note_path),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            note_text = note_path.read_text(encoding="utf-8")
            self.assertIn("## Interaction Observations", note_text)
            self.assertIn("2026-04-10 | interaction-observation", note_text)
            self.assertIn("対話から agent-side learning を抽出する", note_text)
            self.assertIn("source: chat", note_text)
            self.assertIn("scope: repo-wide", note_text)
            self.assertIn("confidence: tentative", note_text)
            self.assertIn("evidence: user requested agent personality formation", note_text)

    def test_failure_avoidance_goes_to_promotion_candidates(self) -> None:
        """Failure-avoidance observations should be promotion candidates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            note_path = Path(tmp_dir) / "AGENT_PHILOSOPHY.md"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--kind",
                    "failure-avoidance",
                    "--statement",
                    "raw chat をそのまま memory にしない",
                    "--observed-on",
                    "2026-04-10",
                    "--note-path",
                    str(note_path),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            note_text = note_path.read_text(encoding="utf-8")
            promotion_section = note_text.split("## Promotion Candidates", 1)[1]
            self.assertIn("failure-avoidance", promotion_section)
            self.assertIn("raw chat をそのまま memory にしない", promotion_section)


if __name__ == "__main__":
    unittest.main()
