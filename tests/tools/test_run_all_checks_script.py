"""Tests for the integrated CI shell entrypoint."""

# @dependency-start
# responsibility Tests integrated CI shell wiring that is too expensive to execute wholesale.
# upstream implementation ../../tools/ci/run_all_checks.sh runs repository and AgentCanon CI gates
# upstream implementation ../../tools/agent_tools/run_accumulated_agent_evals.py writes accumulated eval reports
# upstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates accumulated eval reports
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves mounted log archive paths
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_all_checks.sh"


class RunAllChecksScriptTest(unittest.TestCase):
    """Validate static CI entrypoint contracts."""

    def test_eval_accumulation_has_archive_before_producers(self) -> None:
        """Accumulated eval producers need a writable AgentCanon log archive."""
        text = SCRIPT.read_text(encoding="utf-8")

        archive_marker = (
            'AGENT_CANON_CI_HOOK_ARCHIVE_DIR="${AGENT_CANON_HOOK_ARCHIVE_DIR:-'
            '${AGENT_CANON_SOURCE_ROOT}/.agent-canon/log-archive}"'
        )
        mkdir_marker = 'mkdir -p "${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"'
        producer_marker = 'tools/agent_tools/run_accumulated_agent_evals.py "${accumulated_eval_args[@]}"'
        checker_marker = "tools/agent_tools/eval_accumulation_check.py"
        command_env_marker = 'AGENT_CANON_HOOK_ARCHIVE_DIR="${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"'

        self.assertIn(archive_marker, text)
        self.assertIn(mkdir_marker, text)
        self.assertIn(command_env_marker, text)
        self.assertLess(text.index(archive_marker), text.index(producer_marker))
        self.assertLess(text.index(mkdir_marker), text.index(producer_marker))
        self.assertLess(text.index(producer_marker), text.index(checker_marker))
        self.assertNotIn("export AGENT_CANON_HOOK_ARCHIVE_DIR", text)


if __name__ == "__main__":
    unittest.main()
