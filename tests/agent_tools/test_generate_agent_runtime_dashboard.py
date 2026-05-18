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
        self.assert_problem_component_section(dashboard)
        self.assert_next_action_section(dashboard)
        self.assert_overview_sections(dashboard)
        self.assert_selection_and_prompt_sections(dashboard)
        self.assert_reference_and_log_sections(dashboard)

    def assert_problem_component_section(self, dashboard: str) -> None:
        """Verify glanceable problem component rows."""
        required = (
            "## Problem Components",
            "AGENT_RUNTIME_DASHBOARD_PROBLEM_COMPONENTS=7",
            "| `workflow` | `_unattributed_hook_entries` | `attention` | "
            "`5 hook entries lack workflow attribution` | `reference_capture_guard.jsonl` | "
            "`repair workflow attribution logging` |",
            "| `tool` | `run_docs_checks.sh` | `attention` | "
            "`1 candidate miss(es); miss rate 100.0%` | "
            "`## Selection Accuracy By Responsibility` | `repair tool selection or logging` |",
            "| `hook` | `reference_capture_guard` | `attention` | "
            "`1 referenced URLs are unregistered` | "
            "`agents/evals/results/hook-runs/*/reference_capture_guard.jsonl` | "
            "`materialize references or repair hook logging` |",
        )
        for expected in required:
            self.assertIn(expected, dashboard)
        self.assertIn(
            "| `skill` | `agent-orchestration` | `fail` | `1 failed eval report(s)` | "
            "`agents/evals/results/skill-workflow-prompt/"
            "skill-eval-test-fail-agent-orchestration.md` | "
            "`repair failed skill eval for agent-orchestration` |",
            dashboard,
        )

    def assert_next_action_section(self, dashboard: str) -> None:
        """Verify concrete dashboard-generated next actions."""
        required = (
            "## Next Actions",
            "AGENT_RUNTIME_DASHBOARD_NEXT_ACTIONS=6",
            "AGENT_RUNTIME_DASHBOARD_BLOCKING_NEXT_ACTIONS=5",
            "`materialize missing consulted source URLs`",
            "`repair failed skill eval for agent-orchestration`",
            "`repair skill selection for md-style-check`",
            "`repair workflow attribution logging`",
        )
        for expected in required:
            self.assertIn(expected, dashboard)

    def assert_overview_sections(self, dashboard: str) -> None:
        """Verify overview, visual, and issue-routing sections."""
        required = (
            "## Where Logs Accumulate",
            "## Visual Evidence Map",
            "```mermaid",
            "flowchart LR",
            "## Action Map",
            "| hook evidence | `healthy` | `3` |",
            "| report quality eval | `missing` | `0` |",
            "## Issue Routing",
            "AC-20260517-mcp-inventory-preflight-cache.md",
            "AC-20260517-eval-accumulation-gaps.md",
            "AC-20260517-github-folder-issue-sync.md",
            "## Skill Eval Failure Analysis",
            "| `agent-orchestration` | `1` | `1` | `100.0%` |",
            "## Hook Workflow Attribution",
            "| `environment-maintenance@UserPromptSubmit` | `1` |",
            "hook_entries_missing_workflow_attribution: `5`",
            "## Token Consumption Evidence",
            "token_comparison_status: `present`",
            "average_token_ratio: `0.500`",
        )
        for expected in required:
            self.assertIn(expected, dashboard)

    def assert_selection_and_prompt_sections(self, dashboard: str) -> None:
        """Verify routing selection, prompt, and Markdown evidence sections."""
        required = (
            "## Selection Accuracy By Responsibility",
            "AGENT_RUNTIME_DASHBOARD_SELECTION_ITEMS=6",
            "AGENT_RUNTIME_DASHBOARD_SELECTION_SELECTED=4",
            "AGENT_RUNTIME_DASHBOARD_SELECTION_CANDIDATES=3",
            "AGENT_RUNTIME_DASHBOARD_SELECTION_MISSES=3",
            "AGENT_RUNTIME_DASHBOARD_SKILL_SELECTION_MISS_RATE=100.0%",
            "## Prompt And Tool Selection Evidence",
            "prompt_entries: `1`",
            "tool_selection_entries: `2`",
            "| `Bash` | `2` |",
            "| `python3` | `1` |",
            "## Markdown Docs Hook Signals",
            "AGENT_RUNTIME_DASHBOARD_MARKDOWN_EVAL_REPORTS=1",
            "AGENT_RUNTIME_DASHBOARD_MARKDOWN_EVAL_FAILURES=1",
            "AGENT_RUNTIME_DASHBOARD_MARKDOWN_HOOK_SIGNALS=2",
            "markdown_hook_signal_status: `present`",
            "| `run_docs_checks.sh` | `1` |",
        )
        for expected in required:
            self.assertIn(expected, dashboard)
        self.assert_selection_rows(dashboard)

    def assert_selection_rows(self, dashboard: str) -> None:
        """Verify selection table rows for each responsibility."""
        rows = (
            "| `skill` | `md-style-check` | `0` | `1` | `1` | "
            "`100.0%` | `untracked-or-unknown` |",
            "| `workflow` | `environment-maintenance` | `0` | `1` | `1` | "
            "`100.0%` | `untracked-or-unknown` |",
            "| `tool` | `run_docs_checks.sh` | `0` | `1` | `1` | "
            "`100.0%` | `untracked-or-unknown` |",
        )
        for row in rows:
            self.assertIn(row, dashboard)

    def assert_reference_and_log_sections(self, dashboard: str) -> None:
        """Verify reference-capture and accumulated log summary sections."""
        required = (
            "## Reference Capture Signals",
            "AGENT_RUNTIME_DASHBOARD_REFERENCE_CAPTURE_ENTRIES=2",
            "AGENT_RUNTIME_DASHBOARD_REFERENCE_URL_OBSERVATIONS=2",
            "AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS=1",
            "AGENT_RUNTIME_DASHBOARD_REFERENCE_BLOCKED_ENTRIES=0",
            "| `UserPromptSubmit` | `1` |",
            "| `last_assistant_message` | `1` |",
            "agents/evals/results/hook-runs/<runtime-namespace>/<hook-name>.jsonl",
            "AGENT_RUNTIME_DASHBOARD_HOOK_FILES=3",
            "AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES=6",
            "skill-workflow-prompt",
            "local-llm-responsibility",
            "workflow-selection",
            "test-container",
            "environment-maintenance",
            "quality_gap",
            "skill-eval-test-fail-agent-orchestration.md",
        )
        for expected in required:
            self.assertIn(expected, dashboard)

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
        self.assertIn("hook_jsonl_files: `3`", dashboard)

    def write_fixture(self, root: Path) -> None:
        """Write a small AgentCanon-like evidence tree."""
        hook_dir = root / "agents" / "evals" / "results" / "hook-runs" / "test-container"
        skill_dir = root / "agents" / "evals" / "results" / "skill-workflow-prompt"
        local_llm_dir = root / "agents" / "evals" / "results" / "local-llm-responsibility"
        workflow_dir = root / "agents" / "evals" / "results" / "workflow-selection"
        self.create_fixture_dirs(root, hook_dir, skill_dir, local_llm_dir, workflow_dir)
        self.write_issue_memory_fixture(root)
        self.write_eval_report_fixture(skill_dir, local_llm_dir, workflow_dir)
        self.write_hook_fixture(hook_dir)
        self.write_workflow_monitor_fixture(root)

    def create_fixture_dirs(
        self,
        root: Path,
        hook_dir: Path,
        skill_dir: Path,
        local_llm_dir: Path,
        workflow_dir: Path,
    ) -> None:
        """Create fixture directories."""
        for directory in (hook_dir, skill_dir, local_llm_dir, workflow_dir):
            directory.mkdir(parents=True)
        (root / "issues" / "open").mkdir(parents=True)
        (root / "issues" / "closed").mkdir(parents=True)
        (root / "memory").mkdir()

    def write_issue_memory_fixture(self, root: Path) -> None:
        """Write issue and memory fixture files."""
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

    def write_eval_report_fixture(
        self,
        skill_dir: Path,
        local_llm_dir: Path,
        workflow_dir: Path,
    ) -> None:
        """Write eval report fixture files."""
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

    def write_hook_fixture(self, hook_dir: Path) -> None:
        """Write hook JSONL fixture files."""
        self.write_oop_hook_fixture(hook_dir)
        self.write_skill_usage_hook_fixture(hook_dir)
        self.write_reference_capture_hook_fixture(hook_dir)

    def write_oop_hook_fixture(self, hook_dir: Path) -> None:
        """Write OOP hook fixture files."""
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

    def write_skill_usage_hook_fixture(self, hook_dir: Path) -> None:
        """Write skill-usage hook fixture files."""
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

    def write_reference_capture_hook_fixture(self, hook_dir: Path) -> None:
        """Write reference-capture hook fixture files."""
        (hook_dir / "reference_capture_guard.jsonl").write_text(
            json.dumps(
                {
                    "hook_run_id": "hook-reference-1",
                    "hook_log_namespace": "test-container",
                    "event": "UserPromptSubmit",
                    "status": "pass",
                    "payload_fingerprint": "payload-e",
                    "url_count": 1,
                    "registered_count": 0,
                    "missing_count": 1,
                    "decision": "pass",
                    "source_fields": ["prompt"],
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "hook-reference-2",
                    "hook_log_namespace": "test-container",
                    "event": "Stop",
                    "status": "pass",
                    "payload_fingerprint": "payload-f",
                    "url_count": 1,
                    "registered_count": 1,
                    "missing_count": 0,
                    "decision": "pass",
                    "source_fields": ["last_assistant_message"],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def write_workflow_monitor_fixture(self, root: Path) -> None:
        """Write token comparison fixture files."""
        workflow_report = root / "reports" / "agents" / "test" / "workflow_monitoring.md"
        workflow_report.parent.mkdir(parents=True)
        workflow_report.write_text(
            "token_efficiency_protocol=active token_footprint_comparison=pass "
            "baseline_total=200 candidate_total=100 token_ratio=0.500 target_ratio=0.500\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
