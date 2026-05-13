# @dependency-start
# responsibility Tests AgentCanon improvement guide generation.
# upstream implementation ../../tools/agent_tools/generate_agent_improvement_guide.py generates guide reports
# @dependency-end

"""Tests for generated AgentCanon improvement guides."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "generate_agent_improvement_guide.py"


class GenerateAgentImprovementGuideTest(unittest.TestCase):
    """Verify deterministic guide output from accumulated evidence."""

    def test_generates_guidance_from_issues_eval_memory_and_hook_logs(self) -> None:
        """The guide should summarize every evidence family."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            output = root / "reports" / "guide.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            guide = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("AGENT_IMPROVEMENT_GUIDE=", result.stdout)
        self.assertIn("open_issues: `1`", guide)
        self.assertIn("closed_issues: `1`", guide)
        self.assertIn("failed_skill_eval_reports: `1`", guide)
        self.assertIn("failure-a", guide)
        self.assertIn("memory/AGENT_PHILOSOPHY.md", guide)
        self.assertIn("Local Agent or Copilot PR", guide)

    def write_fixture(self, root: Path) -> None:
        """Write a small AgentCanon-like evidence tree."""
        (root / "issues" / "open").mkdir(parents=True)
        (root / "issues" / "closed").mkdir(parents=True)
        (root / "memory").mkdir()
        skill_results = root / "agents" / "evals" / "results" / "skill-workflow-prompt"
        hook_results = root / "agents" / "evals" / "results" / "hook-runs"
        skill_results.mkdir(parents=True)
        hook_results.mkdir(parents=True)
        (root / "issues" / "open" / "AC-20260513-open.md").write_text(
            "issue_id: AC-20260513-open\nstatus: open\n",
            encoding="utf-8",
        )
        (root / "issues" / "closed" / "AC-20260513-closed.md").write_text(
            "issue_id: AC-20260513-closed\nstatus: resolved\n",
            encoding="utf-8",
        )
        (root / "memory" / "AGENT_PHILOSOPHY.md").write_text(
            "# Agent Philosophy\n\n- durable learning\n",
            encoding="utf-8",
        )
        (root / "memory" / "USER_PREFERENCES.md").write_text(
            "# User Preferences\n\n- durable preference\n",
            encoding="utf-8",
        )
        (skill_results / "skill-eval-test-fail-agent-orchestration.md").write_text(
            "EVAL_STATUS=fail\n",
            encoding="utf-8",
        )
        (hook_results / "oop_readability_guard.jsonl").write_text(
            json.dumps(
                {
                    "hook_run_id": "hook-test",
                    "status": "fail",
                    "failure_fingerprint": "failure-a",
                }
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
