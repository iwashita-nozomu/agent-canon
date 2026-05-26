# @dependency-start
# responsibility Tests AgentCanon improvement guide generation.
# upstream implementation ../../tools/agent_tools/generate_agent_improvement_guide.py generates guide reports
# @dependency-end

"""Tests for generated AgentCanon improvement guides."""

from __future__ import annotations

import json
import os
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
        self.assertNotIn("- `latest`: `1`", guide)
        self.assertNotIn("- `skill-name`: `1`", guide)
        self.assertNotIn("skill:latest", guide)
        self.assertNotIn("skill:skill-name", guide)
        self.assertIn("tool_input_skill_usage_ignored", guide)
        self.assertIn("noncanonical_skill_usage_ignored", guide)
        self.assertIn("agent-orchestration@UserPromptSubmit", guide)
        self.assertIn("hook_tool_counts:", guide)
        self.assertIn("apply_patch", guide)
        self.assertIn("hook_namespace_counts:", guide)
        self.assertIn("test-container", guide)
        self.assertIn("skill_source_counts:", guide)
        self.assertIn("prompt", guide)
        self.assertIn("prompt_candidate_skill_counts:", guide)
        self.assertIn("result-artifact-writeout", guide)
        self.assertIn("Skill Routing Gaps", guide)
        self.assertIn("`result-artifact-writeout`: gap=`2` selected=`0` candidate=`1` feedback=`1`", guide)
        self.assertIn("prompt_candidate_workflow_counts:", guide)
        self.assertIn("codex-task-workflow", guide)
        self.assertIn("prompt_candidate_tool_counts:", guide)
        self.assertIn("workflow_monitor.py", guide)
        self.assertIn("human_feedback_label_counts:", guide)
        self.assertIn("quality_gap", guide)
        self.assertIn("human_feedback_target_counts:", guide)
        self.assertIn("skill:result-artifact-writeout", guide)
        self.assertIn("human_feedback_action_counts:", guide)
        self.assertIn("prompt_repair", guide)
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
        self.assertIn("hook_status_counts: `{'fail': 1, 'pass': 4}`", guide)

    def test_skill_routing_gap_ignores_pre_cutover_skill_logs(self) -> None:
        """Skill source updates should archive older routing signals from gap math."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_cutover_fixture(root)
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
        self.assertNotIn("`agent-orchestration`: gap=", guide)
        self.assertIn("skill_routing_signal_before_cutover_ignored", guide)
        self.assertIn(
            "skill_routing_signal_before_cutover_ignored:agent-orchestration",
            guide,
        )

    def test_skill_routing_gap_keeps_post_cutover_skill_logs(self) -> None:
        """Skill source cutover should not hide current routing pressure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_cutover_fixture(root, include_post_cutover=True)
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
        self.assertIn(
            "`agent-orchestration`: gap=`1` selected=`1` candidate=`1` feedback=`1`",
            guide,
        )
        self.assertNotIn(
            "`agent-orchestration`: gap=`3` selected=`1` candidate=`2` feedback=`2`",
            guide,
        )

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
        for skill in ("agent-orchestration", "codex-task-workflow", "result-artifact-writeout"):
            skill_path = root / ".agents" / "skills" / skill / "SKILL.md"
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(
                f"---\nname: {skill}\ndescription: test skill\n---\n\n# {skill}\n",
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
                    "candidate_skills": ["result-artifact-writeout"],
                    "candidate_workflows": ["codex-task-workflow"],
                    "candidate_tools": ["workflow_monitor.py"],
                    "prompt_feedback_detected": True,
                    "feedback_labels": ["quality_gap", "repair_request"],
                    "feedback_targets": ["skill:result-artifact-writeout", "tool:workflow_monitor.py"],
                    "feedback_action": "prompt_repair",
                    "skill_source_fields": ["prompt"],
                    "observed_text_field_count": 1,
                    "observed_text_value_count": 1,
                    "workflow_monitor_event_count": 0,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "skill-hook-shell-vars",
                    "event": "PostToolUse",
                    "status": "pass",
                    "payload_fingerprint": "payload-shell-vars",
                    "hook_log_namespace": "test-container",
                    "skills": ["latest"],
                    "skill_count": 1,
                    "feedback_targets": ["skill:latest"],
                    "skill_source_fields": ["tool_input"],
                    "observed_text_field_count": 1,
                    "observed_text_value_count": 1,
                    "tool_name": "Bash",
                    "tool_command_verb": "latest=$(ls",
                    "workflow_monitor_event_count": 0,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "skill-hook-placeholder",
                    "event": "Stop",
                    "status": "pass",
                    "payload_fingerprint": "payload-placeholder",
                    "hook_log_namespace": "test-container",
                    "skills": ["skill-name"],
                    "skill_count": 1,
                    "feedback_targets": ["skill:skill-name"],
                    "skill_source_fields": ["last_assistant_message"],
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

    def write_cutover_fixture(
        self,
        root: Path,
        *,
        include_post_cutover: bool = False,
    ) -> None:
        """Write a Git-backed fixture with hook evidence older than skill source."""
        root.mkdir(parents=True, exist_ok=True)
        skill_path = root / ".agents" / "skills" / "agent-orchestration" / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(
            "---\nname: agent-orchestration\ndescription: test skill\n---\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "add", ".agents/skills/agent-orchestration/SKILL.md"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        commit_env = os.environ.copy()
        commit_env.update(
            {
                "GIT_AUTHOR_DATE": "2026-05-21T10:00:00+00:00",
                "GIT_COMMITTER_DATE": "2026-05-21T10:00:00+00:00",
            }
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=AgentCanon Test",
                "-c",
                "user.email=agentcanon-test@example.invalid",
                "commit",
                "-m",
                "update agent orchestration skill",
            ],
            cwd=root,
            env=commit_env,
            check=True,
            capture_output=True,
            text=True,
        )
        hook_results = root / "agents" / "evals" / "results" / "hook-runs" / "test-container"
        hook_results.mkdir(parents=True)
        entries: list[dict[str, object]] = [
            {
                "hook_run_id": "skill-hook-before-cutover",
                "event": "UserPromptSubmit",
                "timestamp": "2026-05-20T10:00:00Z",
                "status": "pass",
                "payload_fingerprint": "payload-before-cutover",
                "hook_log_namespace": "test-container",
                "candidate_skills": ["agent-orchestration"],
                "feedback_targets": ["skill:agent-orchestration"],
                "feedback_labels": ["repair_request"],
                "skill_source_fields": ["prompt"],
                "observed_text_field_count": 1,
                "observed_text_value_count": 1,
                "workflow_monitor_event_count": 1,
                "workflow_monitor_report_dir": "reports/agents/test",
            }
        ]
        if include_post_cutover:
            entries.append(
                {
                    "hook_run_id": "skill-hook-after-cutover",
                    "event": "UserPromptSubmit",
                    "timestamp": "2026-05-22T10:00:00Z",
                    "status": "pass",
                    "payload_fingerprint": "payload-after-cutover",
                    "hook_log_namespace": "test-container",
                    "skills": ["agent-orchestration"],
                    "skill_count": 1,
                    "candidate_skills": ["agent-orchestration"],
                    "feedback_targets": ["skill:agent-orchestration"],
                    "feedback_labels": ["repair_request"],
                    "skill_source_fields": ["prompt"],
                    "observed_text_field_count": 1,
                    "observed_text_value_count": 1,
                    "workflow_monitor_event_count": 1,
                    "workflow_monitor_report_dir": "reports/agents/test",
                }
            )
        (hook_results / "skill_usage.jsonl").write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
