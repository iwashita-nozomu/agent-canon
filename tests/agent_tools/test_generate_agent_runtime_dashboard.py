# @dependency-start
# responsibility Tests AgentCanon runtime dashboard generation.
# upstream implementation ../../tools/agent_tools/generate_agent_runtime_dashboard.py generates dashboard reports
# upstream design ../../documents/runtime-log-archive.md documents result families shown by dashboard
# @dependency-end

"""Tests for generated AgentCanon runtime dashboards."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "generate_agent_runtime_dashboard.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from runtime_log_paths import mounted_log_archive_root, repo_log_key  # noqa: E402

DASHBOARD_PROMPT_CHAR_COUNT = 27


class GenerateAgentRuntimeDashboardTest(unittest.TestCase):
    """Verify dashboard output from accumulated runtime evidence."""

    def test_generates_log_location_dashboard(self) -> None:
        """The dashboard should show canonical paths and accumulated counts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            output = root / "reports" / "dashboard.md"
            compact_output = root / "reports" / "compact-dashboard.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(output),
                    "--compact-out",
                    str(compact_output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            dashboard = output.read_text(encoding="utf-8")
            compact_dashboard = compact_output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_STATUS=pass", result.stdout)
        self.assert_compact_dashboard(compact_dashboard)
        self.assert_problem_component_section(dashboard)
        self.assert_next_action_section(dashboard)
        self.assert_overview_sections(dashboard)
        self.assert_selection_and_prompt_sections(dashboard)
        self.assert_reference_and_log_sections(dashboard)

    def assert_compact_dashboard(self, dashboard: str) -> None:
        """Verify the token-light summary omits full dashboard-only sections."""
        required = (
            "# Agent Runtime Compact Summary",
            "## Machine Summary",
            "AGENT_RUNTIME_DASHBOARD_STATUS=pass",
            "## Priority Problems",
            "| `skill` | `agent-orchestration` | `fail` | `1 failed eval report(s)` |",
            "## Priority Next Actions",
            "`repair failed skill eval for agent-orchestration`",
            "## Selection Misses",
            "| `skill` | `md-style-check` | `0` | `1` | `1` | `100.0%` |",
            "## Evidence Drilldown",
            "### Hook Failure Drilldown",
            "### Skill Eval Failure Drilldown",
            "### Selection Evidence Drilldown",
            "### Prompt Token Trend Drilldown",
            "### Token Consumption Drilldown",
            "| `agent-orchestration` | `1` | `1` | `100.0%` |",
            "| `rolling_window_observations` | `8` |",
            "| `prompt_chars_per_call_recent` | `27` |",
            "| `token_ratio_recent` | `0.500` |",
            "| `candidate_tokens_per_comparison_recent` | `100` |",
            "| `joint_trend_status` | `limited_joint_window` |",
            "| `comparison_count` | `1` |",
            "| `missing_namespaces` | `test-container=5` |",
            "| `missing_urls` | `https://example.com/paper.pdf=1` |",
            "| `registered_urls` | `https://example.com/reference.html=1` |",
            "Do not read raw JSONL during normal agent log analysis.",
            "extend or rerun the dashboard tool",
        )
        for expected in required:
            self.assertIn(expected, dashboard)
        self.assertNotIn("## Where Logs Accumulate", dashboard)
        self.assertNotIn("```mermaid", dashboard)
        self.assertNotIn("reference_capture_guard.jsonl", dashboard)
        self.assertNotIn("skill_usage.jsonl", dashboard)
        self.assertNotIn("reports/agents/**", dashboard)

    def assert_problem_component_section(self, dashboard: str) -> None:
        """Verify glanceable problem component rows."""
        required = (
            "## Problem Components",
            "AGENT_RUNTIME_DASHBOARD_PROBLEM_COMPONENTS=6",
            "| `workflow` | `_unattributed_hook_entries` | `attention` | "
            "`5 hook entries lack workflow attribution` | "
            "`compact report Workflow Attribution Drilldown` | "
            "`repair workflow attribution logging` |",
            "| `hook` | `reference_capture_guard` | `attention` | "
            "`1 referenced URLs are unregistered` | "
            "`compact report Reference Capture Drilldown` | "
            "`materialize references or repair hook logging` |",
        )
        for expected in required:
            self.assertIn(expected, dashboard)
        self.assertIn(
            "| `skill` | `agent-orchestration` | `fail` | `1 failed eval report(s)` | "
            "`compact report Skill Eval Failure Drilldown skill=agent-orchestration` | "
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
            "hook_entries_context_attributed: `0`",
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
            "AGENT_RUNTIME_DASHBOARD_SELECTION_ITEMS=7",
            "AGENT_RUNTIME_DASHBOARD_SELECTION_SELECTED=6",
            "AGENT_RUNTIME_DASHBOARD_SELECTION_CANDIDATES=4",
            "AGENT_RUNTIME_DASHBOARD_SELECTION_MISSES=2",
            "AGENT_RUNTIME_DASHBOARD_SKILL_SELECTION_MISS_RATE=50.0%",
            "## Prompt And Tool Selection Evidence",
            "prompt_entries: `1`",
            "tool_selection_entries: `2`",
            "| `Bash` | `2` |",
            "| `python3` | `1` |",
            "### Selected Repo Tools",
            "| `run_docs_checks.sh` | `1` |",
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
            "| `skill` | `oop-readability-check` | `1` | `1` | `0` | "
            "`0.0%` | `untracked-or-unknown` |",
            "| `workflow` | `environment-maintenance` | `0` | `1` | `1` | "
            "`100.0%` | `untracked-or-unknown` |",
            "| `tool` | `run_docs_checks.sh` | `1` | `1` | `0` | "
            "`0.0%` | `untracked-or-unknown` |",
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
            ".agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>.jsonl",
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
            self.write_fixture(canon_root, source_root=parent)
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

    def test_prompt_token_trend_uses_chronological_recent_window(self) -> None:
        """Recent prompt/token trend rows should use timestamps, not file order."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_out_of_order_trend_fixture(root)
            compact_output = root / "reports" / "compact-dashboard.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(root / "reports" / "dashboard.md"),
                    "--compact-out",
                    str(compact_output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            compact_dashboard = compact_output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("| `prompt_chars_per_call_recent` | `10` |", compact_dashboard)
        self.assertIn("| `token_ratio_recent` | `0.100` |", compact_dashboard)
        self.assertIn("| `candidate_tokens_per_comparison_recent` | `100` |", compact_dashboard)
        self.assertIn("| `joint_trend_status` | `ready` |", compact_dashboard)

    def test_recent_days_filters_hook_and_token_evidence(self) -> None:
        """Recent dashboard mode should not mix old JSONL rows into reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_recent_filter_fixture(root)
            compact_output = root / "reports" / "compact-dashboard.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(root / "reports" / "dashboard.md"),
                    "--compact-out",
                    str(compact_output),
                    "--recent-days",
                    "5",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            compact_dashboard = compact_output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_RECENT_DAYS=5", compact_dashboard)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES=1", compact_dashboard)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_PROMPT_ENTRIES=1", compact_dashboard)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_TOKEN_COMPARISONS=1", compact_dashboard)
        self.assertIn("| `prompt_chars_per_call_recent` | `10` |", compact_dashboard)
        self.assertIn("| `token_ratio_recent` | `0.100` |", compact_dashboard)
        self.assertNotIn("legacy-skill", compact_dashboard)

    def write_fixture(self, root: Path, *, source_root: Path | None = None) -> None:
        """Write a small AgentCanon-like evidence tree."""
        source = source_root or root
        archive = mounted_log_archive_root(root)
        hook_dir = archive / "hook-runs" / repo_log_key(source) / "test-container"
        skill_dir = archive / "eval-results" / "skill-workflow-prompt"
        local_llm_dir = archive / "eval-results" / "local-llm-responsibility"
        workflow_dir = archive / "eval-results" / "workflow-selection"
        evals_dir = root / "agents" / "evals"
        evals_dir.mkdir(parents=True)
        (evals_dir / "README.md").write_text("# Eval Fixture\n", encoding="utf-8")
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
                    "candidate_skills": ["md-style-check", "oop-readability-check"],
                    "candidate_tools": ["run_docs_checks.sh"],
                    "feedback_labels": ["quality_gap"],
                    "prompt_capture_status": "present",
                    "prompt_excerpt_redacted": "Use environment maintenance",
                    "timestamp": "2026-05-17T01:02:02Z",
                    "prompt_char_count": DASHBOARD_PROMPT_CHAR_COUNT,
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
                    "selected_tools": ["run_docs_checks.sh"],
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
                    "urls": ["https://example.com/paper.pdf"],
                    "registered_urls": [],
                    "missing_urls": ["https://example.com/paper.pdf"],
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
                    "urls": ["https://example.com/reference.html"],
                    "registered_urls": ["https://example.com/reference.html"],
                    "missing_urls": [],
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
            "timestamp=2026-05-17T01:02:03Z "
            "token_efficiency_protocol=active token_footprint_comparison=pass "
            "baseline_total=200 candidate_total=100 token_ratio=0.500 target_ratio=0.500\n",
            encoding="utf-8",
        )

    def write_recent_filter_fixture(self, root: Path) -> None:
        """Write mixed old and recent evidence for recent-mode assertions."""
        hook_dir = mounted_log_archive_root(root) / "hook-runs" / repo_log_key(root) / "test-container"
        hook_dir.mkdir(parents=True)
        recent_timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        (hook_dir / "skill_usage.jsonl").write_text(
            json.dumps(
                {
                    "hook_run_id": "old-hook",
                    "hook_log_namespace": "test-container",
                    "event": "UserPromptSubmit",
                    "status": "pass",
                    "payload_fingerprint": "old",
                    "skills": ["legacy-skill"],
                    "prompt_capture_status": "present",
                    "prompt_excerpt_redacted": "old prompt",
                    "timestamp": "2000-01-01T00:00:00Z",
                    "prompt_char_count": 900,
                    "skill_source_fields": ["prompt"],
                    "observed_text_field_count": 1,
                    "workflow_monitor_event_count": 1,
                    "workflow_monitor_report_dir": "reports/agents/old",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "recent-hook",
                    "hook_log_namespace": "test-container",
                    "event": "UserPromptSubmit",
                    "status": "pass",
                    "payload_fingerprint": "recent",
                    "skills": ["md-style-check"],
                    "prompt_capture_status": "present",
                    "prompt_excerpt_redacted": "recent",
                    "timestamp": recent_timestamp,
                    "prompt_char_count": 10,
                    "skill_source_fields": ["prompt"],
                    "observed_text_field_count": 1,
                    "workflow_monitor_event_count": 1,
                    "workflow_monitor_report_dir": "reports/agents/recent",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.write_token_report(root, "old", "2000-01-01T00:00:00Z", 1000, 900, 0.900)
        self.write_token_report(root, "recent", recent_timestamp, 1000, 100, 0.100)

    def write_out_of_order_trend_fixture(self, root: Path) -> None:
        """Write trend evidence where lexical and chronological order disagree."""
        hook_dir = mounted_log_archive_root(root) / "hook-runs" / repo_log_key(root) / "test-container"
        (root / "reports" / "agents" / "test" / "workflow_monitoring.md").unlink()
        new_entries = [
            self.prompt_entry(f"2026-05-{day:02d}T00:00:00Z", 10)
            for day in range(2, 10)
        ]
        old_entry = self.prompt_entry("2026-05-01T00:00:00Z", 900)
        (hook_dir / "skill_usage.jsonl").write_text(
            "\n".join(json.dumps(entry) for entry in (*new_entries, old_entry)) + "\n",
            encoding="utf-8",
        )
        self.write_token_report(root, "z-old", "2026-05-01T00:00:00Z", 1000, 900, 0.900)
        for day in range(2, 10):
            self.write_token_report(
                root,
                f"a-new-{day}",
                f"2026-05-{day:02d}T00:00:00Z",
                1000,
                100,
                0.100,
            )

    @staticmethod
    def prompt_entry(timestamp: str, prompt_chars: int) -> dict[str, object]:
        """Return one prompt-capture hook entry."""
        return {
            "hook_run_id": f"hook-{timestamp}",
            "hook_log_namespace": "test-container",
            "event": "UserPromptSubmit",
            "status": "pass",
            "payload_fingerprint": timestamp,
            "prompt_capture_status": "present",
            "prompt_excerpt_redacted": "trend",
            "prompt_char_count": prompt_chars,
            "timestamp": timestamp,
        }

    @staticmethod
    def write_token_report(
        root: Path,
        name: str,
        timestamp: str,
        baseline: int,
        candidate: int,
        ratio: float,
    ) -> None:
        """Write one token comparison report."""
        report = root / "reports" / "agents" / name / "workflow_monitoring.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            f"timestamp={timestamp} baseline_total={baseline} "
            f"candidate_total={candidate} token_ratio={ratio:.3f}\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
