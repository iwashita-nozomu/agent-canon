# @dependency-start
# responsibility Tests AgentCanon memory persistence behavior.
# upstream implementation ../../tools/agent_tools/persist_agent_memory.py persists memory notes.
# @dependency-end

"""Tests for AgentCanon memory persistence."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "persist_agent_memory.py"


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one command for a test fixture."""
    return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)


class PersistAgentMemoryTest(unittest.TestCase):
    """Verify memory note persistence into AgentCanon commits."""

    def test_check_reports_dirty_memory(self) -> None:
        """The check mode should fail when memory files have pending changes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._make_agent_canon_repo(Path(tmp_dir))
            note = repo / "memory" / "AGENT_PHILOSOPHY.md"
            note.write_text(note.read_text(encoding="utf-8") + "\n- pending\n", encoding="utf-8")

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workspace-root",
                    str(repo),
                    "--check",
                ],
                cwd=PROJECT_ROOT,
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("AGENT_MEMORY_STATUS=dirty", result.stdout)
            self.assertIn("AGENT_MEMORY_PATH=memory/AGENT_PHILOSOPHY.md", result.stdout)

    def test_commit_persists_memory_changes(self) -> None:
        """The commit mode should create an AgentCanon commit and clean memory status."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._make_agent_canon_repo(Path(tmp_dir))
            note = repo / "memory" / "USER_PREFERENCES.md"
            note.write_text(note.read_text(encoding="utf-8") + "\n- durable\n", encoding="utf-8")

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workspace-root",
                    str(repo),
                    "--commit",
                    "--message",
                    "Record test memory",
                ],
                cwd=PROJECT_ROOT,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGENT_MEMORY_COMMIT=created", result.stdout)
            status = run(["git", "status", "--short", "--", "memory"], repo)
            self.assertEqual(status.stdout.strip(), "")
            log = run(["git", "log", "--oneline", "-1"], repo)
            self.assertIn("Record test memory", log.stdout)

    def _make_agent_canon_repo(self, root: Path) -> Path:
        """Create a minimal AgentCanon-like Git repo."""
        repo = root / "agent-canon"
        memory = repo / "memory"
        memory.mkdir(parents=True)
        (memory / "AGENT_PHILOSOPHY.md").write_text("# Agent Philosophy\n", encoding="utf-8")
        (memory / "USER_PREFERENCES.md").write_text("# User Preferences\n", encoding="utf-8")
        run(["git", "init", "-b", "main"], repo)
        run(["git", "config", "user.email", "test@example.invalid"], repo)
        run(["git", "config", "user.name", "Test User"], repo)
        run(["git", "add", "memory"], repo)
        commit = run(["git", "commit", "-m", "Initial memory"], repo)
        self.assertEqual(commit.returncode, 0, commit.stderr)
        return repo


if __name__ == "__main__":
    unittest.main()
