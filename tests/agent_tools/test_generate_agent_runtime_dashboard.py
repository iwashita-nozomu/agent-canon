# @dependency-start
# responsibility Tests AgentCanon runtime dashboard generation.
# upstream implementation ../../tools/agent_tools/generate_agent_runtime_dashboard.py generates dashboard reports
# downstream design ../../agents/evals/results/README.md documents result families shown by dashboard
# @dependency-end

"""Tests for generated AgentCanon runtime dashboards."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "generate_agent_runtime_dashboard.py"


class GenerateAgentRuntimeDashboardTest(unittest.TestCase):
    """Verify dashboard output from accumulated runtime evidence."""

    def test_generates_log_location_dashboard(self) -> None:
        """The dashboard should show canonical paths and accumulated counts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            output = root / "reports" / "dashboard.md"

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
            dashboard = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_STATUS=pass", result.stdout)
        self.assertIn("## Where Logs Accumulate", dashboard)
        self.assertIn("## Visual Evidence Map", dashboard)
        self.assertIn("```mermaid", dashboard)
        self.assertIn("flowchart LR", dashboard)
        self.assertIn("## Action Map", dashboard)
        self.assertIn("| hook evidence | `healthy` | `2` |", dashboard)
        self.assertIn("| report quality eval | `missing` | `0` |", dashboard)
        self.assertIn("## Issue Routing", dashboard)
        self.assertIn("AC-20260517-mcp-inventory-preflight-cache.md", dashboard)
        self.assertIn("AC-20260517-eval-accumulation-gaps.md", dashboard)
        self.assertIn("AC-20260517-github-folder-issue-sync.md", dashboard)
        self.assertIn("## Skill Eval Failure Analysis", dashboard)
        self.assertIn("| `agent-orchestration` | `1` | `1` | `100.0%` |", dashboard)
        self.assertIn("## Hook Workflow Attribution", dashboard)
        self.assertIn("| `environment-maintenance@UserPromptSubmit` | `1` |", dashboard)
        self.assertIn("hook_entries_missing_workflow_attribution: `3`", dashboard)
        self.assertIn("## Token Consumption Evidence", dashboard)
        self.assertIn("token_comparison_status: `present`", dashboard)
        self.assertIn("average_token_ratio: `0.500`", dashboard)
        self.assertIn("## Prompt And Tool Selection Evidence", dashboard)
        self.assertIn("prompt_entries: `1`", dashboard)
        self.assertIn("tool_selection_entries: `2`", dashboard)
        self.assertIn("| `Bash` | `2` |", dashboard)
        self.assertIn("| `python3` | `1` |", dashboard)
        self.assertIn("## Markdown Docs Hook Signals", dashboard)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_MARKDOWN_EVAL_REPORTS=1", dashboard)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_MARKDOWN_EVAL_FAILURES=1", dashboard)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_MARKDOWN_HOOK_SIGNALS=2", dashboard)
        self.assertIn("markdown_hook_signal_status: `present`", dashboard)
        self.assertIn("| `run_docs_checks.sh` | `1` |", dashboard)
        self.assertIn("agents/evals/results/hook-runs/<runtime-namespace>/<hook-name>.jsonl", dashboard)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_HOOK_FILES=2", dashboard)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES=4", dashboard)
        self.assertIn("skill-workflow-prompt", dashboard)
        self.assertIn("local-llm-responsibility", dashboard)
        self.assertIn("workflow-selection", dashboard)
        self.assertIn("test-container", dashboard)
        self.assertIn("environment-maintenance", dashboard)
        self.assertIn("quality_gap", dashboard)
        self.assertIn("skill-eval-test-fail-agent-orchestration.md", dashboard)

    def test_resolves_parent_repo_vendored_agentcanon_logs(self) -> None:
        """Parent-root invocation should read vendored AgentCanon evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            canon_root = parent / "vendor" / "agent-canon"
            self.write_fixture(canon_root)
            output = parent / "reports" / "dashboard.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(parent),
                    "--out",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            dashboard = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={canon_root.resolve().as_posix()}", dashboard)
        self.assertIn("hook_jsonl_files: `2`", dashboard)

    def write_fixture(self, root: Path) -> None:
        """Write a small AgentCanon-like evidence tree."""
        hook_dir = root / "agents" / "evals" / "results" / "hook-runs" / "test-container"
        skill_dir = root / "agents" / "evals" / "results" / "skill-workflow-prompt"
        local_llm_dir = root / "agents" / "evals" / "results" / "local-llm-responsibility"
        workflow_dir = root / "agents" / "evals" / "results" / "workflow-selection"
        hook_dir.mkdir(parents=True)
        skill_dir.mkdir(parents=True)
        local_llm_dir.mkdir(parents=True)
        workflow_dir.mkdir(parents=True)
        (root / "issues" / "open").mkdir(parents=True)
        (root / "issues" / "closed").mkdir(parents=True)
        (root / "memory").mkdir()
        (root / "issues" / "open" / "AC-20260517-open.md").write_text(
            "issue_id: AC-20260517-open\nstatus: open\n",
            encoding="utf-8",
        )
        for slug in (
            "mcp-inventory-preflight-cache",
            "eval-accumulation-gaps",
            "github-folder-issue-sync",
        ):
            (root / "issues" / "open" / f"AC-20260517-{slug}.md").write_text(
                f"issue_id: AC-20260517-{slug}\nstatus: open\n",
                encoding="utf-8",
            )
        (root / "issues" / "closed" / "AC-20260517-closed.md").write_text(
            "issue_id: AC-20260517-closed\nstatus: resolved\n",
            encoding="utf-8",
        )
        (root / "memory" / "USER_PREFERENCES.md").write_text("- preference\n", encoding="utf-8")
        (root / "memory" / "AGENT_PHILOSOPHY.md").write_text("- learning\n", encoding="utf-8")
        (skill_dir / "skill-eval-test-fail-agent-orchestration.md").write_text(
            "- used_skills: `agent-orchestration`\nEVAL_STATUS=fail\n",
            encoding="utf-8",
        )
        (skill_dir / "skill-eval-test-fail-md-style-check.md").write_text(
            "- used_skills: `md-style-check`\nEVAL_STATUS=fail\n",
            encoding="utf-8",
        )
        (local_llm_dir / "local-llm-eval-20260517T010203040506Z-1234567890-pass.md").write_text(
            "LOCAL_LLM_EVAL_STATUS=pass\n",
            encoding="utf-8",
        )
        (workflow_dir / "workflow-selection-eval-20260517T010203040506Z-1234567890-pass.md").write_text(
            "WORKFLOW_SELECTION_EVAL_STATUS=pass\n",
            encoding="utf-8",
        )
        (hook_dir / "oop_readability_guard.jsonl").write_text(
            json.dumps(
                {
                    "hook_run_id": "hook-test-1",
                    "hook_log_namespace": "test-container",
                    "event": "PostToolUse",
                    "status": "pass",
                    "payload_fingerprint": "payload-a",
                    "tool_name": "Bash",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (hook_dir / "skill_usage.jsonl").write_text(
            json.dumps(
                {
                    "hook_run_id": "hook-skill-1",
                    "hook_log_namespace": "test-container",
                    "event": "UserPromptSubmit",
                    "status": "pass",
                    "payload_fingerprint": "payload-b",
                    "skills": ["agent-orchestration"],
                    "candidate_workflows": ["environment-maintenance"],
                    "candidate_skills": ["md-style-check"],
                    "candidate_tools": ["run_docs_checks.sh"],
                    "feedback_labels": ["quality_gap"],
                    "prompt_capture_status": "present",
                    "prompt_excerpt_redacted": "Use environment maintenance",
                    "prompt_char_count": 27,
                    "tool_name": "",
                    "tool_command_verb": "",
                    "skill_source_fields": ["prompt"],
                    "observed_text_field_count": 1,
                    "workflow_monitor_event_count": 1,
                    "workflow_monitor_report_dir": "reports/agents/test",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "hook-skill-2",
                    "hook_log_namespace": "test-container",
                    "event": "Stop",
                    "status": "pass",
                    "payload_fingerprint": "payload-c",
                    "skills": [],
                    "skill_source_fields": ["last_assistant_message"],
                    "observed_text_field_count": 1,
                    "workflow_monitor_event_count": 1,
                    "workflow_monitor_report_dir": "reports/agents/test",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "hook-skill-3",
                    "hook_log_namespace": "test-container",
                    "event": "PostToolUse",
                    "status": "pass",
                    "payload_fingerprint": "payload-d",
                    "tool_name": "Bash",
                    "tool_selection_kind": "executed_tool",
                    "tool_command_verb": "python3",
                    "tool_input_key_count": 1,
                    "tool_input_keys": ["cmd"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        workflow_report = root / "reports" / "agents" / "test" / "workflow_monitoring.md"
        workflow_report.parent.mkdir(parents=True)
        workflow_report.write_text(
            "token_efficiency_protocol=active token_footprint_comparison=pass "
            "baseline_total=200 candidate_total=100 token_ratio=0.500 target_ratio=0.500\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
