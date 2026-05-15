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
        self.assertIn("skill_usage_counts:", guide)
        self.assertIn("agent-orchestration", guide)
        self.assertIn("agent-orchestration@UserPromptSubmit", guide)
        self.assertIn("hook_tool_counts:", guide)
        self.assertIn("apply_patch", guide)
        self.assertIn("hook_namespace_counts:", guide)
        self.assertIn("test-container", guide)
        self.assertIn("skill_source_counts:", guide)
        self.assertIn("prompt", guide)
        self.assertIn("Top Failure Repair Targets", guide)
        self.assertIn("tools/agent_tools/task_start.py", guide)
        self.assertIn("hook_quality_counts:", guide)
        self.assertIn("unknown_event", guide)
        self.assertIn("Hook Quality Findings", guide)
        self.assertIn("Protocol Feedback Coverage", guide)
        self.assertIn("hook_tool_feedback=reviewed", guide)
        self.assertIn("failure-a", guide)
        self.assertIn("memory/AGENT_PHILOSOPHY.md", guide)
        self.assertIn("Local Agent or Copilot PR", guide)

    def test_resolves_vendored_agentcanon_root_from_parent_repo(self) -> None:
        """Parent-root invocation should use vendored AgentCanon evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent_root = Path(temp_dir)
            canon_root = parent_root / "vendor" / "agent-canon"
            self.write_fixture(canon_root)
            output = parent_root / "reports" / "guide.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(parent_root),
                    "--out",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            guide = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"evidence_root: `{canon_root.resolve().as_posix()}`", guide)
        self.assertIn("open_issues: `1`", guide)
        self.assertIn("hook_status_counts: `{'fail': 1, 'pass': 2}`", guide)

    def write_fixture(self, root: Path) -> None:
        """Write a small AgentCanon-like evidence tree."""
        root.mkdir(parents=True, exist_ok=True)
        (root / "issues" / "open").mkdir(parents=True)
        (root / "issues" / "closed").mkdir(parents=True)
        (root / "memory").mkdir()
        skill_results = root / "agents" / "evals" / "results" / "skill-workflow-prompt"
        hook_results = root / "agents" / "evals" / "results" / "hook-runs" / "test-container"
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
                    "hook_log_namespace": "test-container",
                    "event": "PostToolUse",
                    "status": "fail",
                    "payload_fingerprint": "payload-a",
                    "failure_fingerprint": "failure-a",
                    "tool_name": "apply_patch",
                    "commands": [
                        {
                            "command": [
                                "python3",
                                "tools/oop/python/readability.py",
                                "--root",
                                str(root),
                                "--min-score",
                                "95",
                                "tools/agent_tools/task_start.py",
                            ],
                            "returncode": 1,
                            "output_snippet": "OOP_READABILITY_FINDING=tools/agent_tools/task_start.py:1",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (hook_results / "skill_usage.jsonl").write_text(
            json.dumps(
                {
                    "hook_run_id": "skill-hook-test",
                    "event": "UserPromptSubmit",
                    "status": "pass",
                    "payload_fingerprint": "payload-skill-a",
                    "hook_log_namespace": "test-container",
                    "skills": ["agent-orchestration", "codex-task-workflow"],
                    "skill_count": 2,
                    "skill_source_fields": ["prompt"],
                    "observed_text_field_count": 1,
                    "observed_text_value_count": 1,
                    "workflow_monitor_event_count": 0,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "skill-hook-empty",
                    "event": "UnknownHookEvent",
                    "status": "pass",
                    "payload_fingerprint": "payload-skill-empty",
                    "hook_log_namespace": "test-container",
                    "skills": [],
                    "skill_count": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
