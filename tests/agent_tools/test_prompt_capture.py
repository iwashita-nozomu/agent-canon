"""Focused tests for pure, redacted prompt capture."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from prompt_capture import capture_prompt  # noqa: E402


class PromptCaptureTest(unittest.TestCase):
    def test_capture_is_redacted_and_bounded(self) -> None:
        result = capture_prompt({"prompt": "token sk-abcdefghijklmnopqrstuvwxyz1234567890"})
        self.assertEqual(result.status, "present")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", result.excerpt_redacted)
        self.assertTrue(result.fingerprint)


if __name__ == "__main__":
    unittest.main()
