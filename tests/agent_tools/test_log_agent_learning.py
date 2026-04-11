"""Tests for the agent learning logging tool."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "log_agent_learning.py"


class LogAgentLearningTest(unittest.TestCase):
    """Verify agent philosophy note updates."""

    @staticmethod
    def write_loadout(tmp_dir: Path) -> Path:
        """Create a minimal fixed-routing config for role-aware tests."""
        config: dict[str, object] = {
            "global_read_files": [],
            "method_files": {
                "implementation": str((tmp_dir / "implementation.md").resolve()),
                "review": str((tmp_dir / "review.md").resolve()),
            },
            "candidate_files": {
                "implementation": str((tmp_dir / "implementation_candidates.md").resolve()),
                "review": str((tmp_dir / "review_candidates.md").resolve()),
            },
            "role_loadouts": {
                "implementer": {
                    "method_reads": ["implementation"],
                    "candidate_file": "implementation",
                    "allow_method_write": True,
                    "allow_global_write": True,
                },
                "manager_reviewer": {
                    "method_reads": ["review"],
                    "candidate_file": "review",
                    "allow_method_write": False,
                    "allow_global_write": False,
                },
            },
        }
        path = tmp_dir / "subagent_loadouts.yaml"
        path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        return path

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

    def test_role_defaults_to_candidate_route(self) -> None:
        """A role-aware log should write to the fixed candidate path by default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            loadout_path = self.write_loadout(tmp_path)
            candidate_path = tmp_path / "review_candidates.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--role",
                    "manager_reviewer",
                    "--loadout-path",
                    str(loadout_path),
                    "--kind",
                    "interaction-observation",
                    "--statement",
                    "review role は candidate までで止める",
                    "--observed-on",
                    "2026-04-11",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(candidate_path.is_file())
            note_text = candidate_path.read_text(encoding="utf-8")
            self.assertIn("review role は candidate までで止める", note_text)
            self.assertIn("AGENT_LEARNING_LAYER=candidate", result.stdout)
            self.assertIn("AGENT_LEARNING_ROLE=manager_reviewer", result.stdout)

    def test_reviewer_role_cannot_write_global_directly(self) -> None:
        """Reviewer roles should be blocked from direct global-memory writes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            loadout_path = self.write_loadout(tmp_path)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--role",
                    "manager_reviewer",
                    "--loadout-path",
                    str(loadout_path),
                    "--target-layer",
                    "global",
                    "--kind",
                    "interaction-observation",
                    "--statement",
                    "review role が global を直書きしない",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("may not write global memory directly", result.stderr)


if __name__ == "__main__":
    unittest.main()
