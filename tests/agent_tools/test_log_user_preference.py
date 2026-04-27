# @dependency-start
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for the user preference logging tool."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "log_user_preference.py"


class LogUserPreferenceTest(unittest.TestCase):
    """Verify user preference note updates."""

    def test_creates_note_and_appends_to_provisional_section(self) -> None:
        """The tool should create the note and write one entry."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            note_path = Path(tmp_dir) / "USER_PREFERENCES.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--preference",
                    "workflow は機械化を優先する",
                    "--kind",
                    "provisional",
                    "--source",
                    "chat",
                    "--rationale",
                    "rule は prose より tool に落とす",
                    "--observed-on",
                    "2026-04-09",
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
            self.assertIn("## Provisional Preferences", note_text)
            self.assertIn("2026-04-09 | workflow は機械化を優先する", note_text)
            self.assertIn("source: chat", note_text)
            self.assertIn("rationale: rule は prose より tool に落とす", note_text)

    def test_appends_to_recent_observations(self) -> None:
        """The recent bucket should also accept entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            note_path = Path(tmp_dir) / "USER_PREFERENCES.md"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--preference",
                    "header-only C++ を使う",
                    "--kind",
                    "recent",
                    "--observed-on",
                    "2026-04-09",
                    "--note-path",
                    str(note_path),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            note_text = note_path.read_text(encoding="utf-8")
            self.assertIn("## Recent Observations", note_text)
            self.assertIn("2026-04-09 | header-only C++ を使う", note_text)


if __name__ == "__main__":
    unittest.main()
