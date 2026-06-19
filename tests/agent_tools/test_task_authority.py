"""Tests for request-local task authority lookup."""

# @dependency-start
# contract test
# responsibility Tests request-local task authority lookup behavior.
# upstream implementation ../../tools/agent_tools/task_authority.py locates active task authority files.
# downstream implementation ../../.codex/hooks/task_authority_schema_guard.py consumes active task authority.
# downstream implementation ../../.codex/hooks/role_write_policy_guard.py consumes active task authority.
# downstream implementation ../../.codex/hooks/first_party_library_guard.py consumes active task authority.
# @dependency-end

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tools.agent_tools.task_authority import (
    AUTHORITY_ENV,
    AUTHORITY_FILE_NAME,
    find_authority_path,
)


class TaskAuthorityTest(unittest.TestCase):
    """Validate task authority lookup stays request-local."""

    def test_find_authority_path_does_not_guess_latest_report_authority(self) -> None:
        """A stale report bundle must not become authority for a new request."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stale = root / "reports" / "agents" / "old-run" / AUTHORITY_FILE_NAME
            stale.parent.mkdir(parents=True)
            stale.write_text("version: 1\nrun_id: old-run\n", encoding="utf-8")

            old_override = os.environ.pop(AUTHORITY_ENV, None)
            try:
                self.assertIsNone(find_authority_path(root))
            finally:
                if old_override is not None:
                    os.environ[AUTHORITY_ENV] = old_override

    def test_find_authority_path_uses_active_run_pointer(self) -> None:
        """The active run pointer can select the current request authority."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active = root / "reports" / "agents" / "run-1" / AUTHORITY_FILE_NAME
            active.parent.mkdir(parents=True)
            active.write_text("version: 1\nrun_id: run-1\n", encoding="utf-8")
            pointer = root / "reports" / "agents" / ".active_run"
            pointer.write_text("reports/agents/run-1\n", encoding="utf-8")

            old_override = os.environ.pop(AUTHORITY_ENV, None)
            try:
                self.assertEqual(find_authority_path(root), active)
            finally:
                if old_override is not None:
                    os.environ[AUTHORITY_ENV] = old_override


if __name__ == "__main__":
    unittest.main()
