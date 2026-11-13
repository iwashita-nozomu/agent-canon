# @dependency-start
# contract test
# responsibility Tests the native AgentCanon runtime dashboard CLI and API.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs owns dashboard collection
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/dashboard_render.rs owns full and compact Markdown output
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/dashboard_token_usage.rs owns token evidence scanning
# @dependency-end

"""Black-box tests for AgentCanon runtime dashboards."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = "generate-agent-runtime-dashboard"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from tools.runtime.archive.runtime_log_paths import (
    HOOK_ARCHIVE_DIR_ENV,
    mounted_log_archive_root,
    repo_log_key,
)

DASHBOARD_PROMPT_CHAR_COUNT = 27


class GenerateAgentRuntimeDashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._runtime_temp = tempfile.TemporaryDirectory()
        self._previous_runtime = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
        self._previous_archive_dir = os.environ.pop(HOOK_ARCHIVE_DIR_ENV, None)
        self._previous_log_root = os.environ.pop("AGENT_CANON_LOG_ROOT", None)
        self.runtime_root = Path(self._runtime_temp.name) / "runtime"
        self.runtime_root.mkdir()
        os.environ["AGENT_CANON_RUNTIME_ROOT"] = str(self.runtime_root)

    def tearDown(self) -> None:
        if self._previous_runtime is None:
            os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
        else:
            os.environ["AGENT_CANON_RUNTIME_ROOT"] = self._previous_runtime
        if self._previous_archive_dir is None:
            os.environ.pop(HOOK_ARCHIVE_DIR_ENV, None)
        else:
            os.environ[HOOK_ARCHIVE_DIR_ENV] = self._previous_archive_dir
        if self._previous_log_root is None:
            os.environ.pop("AGENT_CANON_LOG_ROOT", None)
        else:
            os.environ["AGENT_CANON_LOG_ROOT"] = self._previous_log_root
        self._runtime_temp.cleanup()

    def run_cli(
        self, command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        """Translate the old producer-shaped test argv to the native selector."""
        command = list(command)
        if command[:2] == [sys.executable, SCRIPT]:
            native = os.environ.get("AGENT_CANON_NATIVE_BIN") or os.environ.get(
                "AGENT_CANON_CLI"
            )
            if not native:
                self.fail(
                    "AGENT_CANON_NATIVE_BIN or AGENT_CANON_CLI must select the native executable"
                )
            command = [native, SCRIPT, *command[2:]]
            if "--runtime-root" not in command:
                command.extend(["--runtime-root", str(self.runtime_root)])
            environment = os.environ.copy()
            environment["AGENT_CANON_RUNTIME_ROOT"] = str(self.runtime_root)
            environment.setdefault(
                "AGENT_CANON_LOG_ROOT", str(self.runtime_root / "agent-canon-log")
            )
            kwargs["env"] = environment
            kwargs.setdefault("check", False)
            kwargs.setdefault("capture_output", True)
            kwargs.setdefault("text", True)
        return subprocess.run(command, check=kwargs.pop("check", False), **kwargs)

    def write_hook(
        self, root: Path, name: str, records: list[dict[str, object]]
    ) -> Path:
        """Write JSONL fixture rows through the mounted archive layout."""
        path = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / "legacy-import"
            / "test-container"
            / name
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8"
        )
        return path

    def run_dashboard(
        self,
        root: Path,
        *,
        out: Path | None = None,
        compact: Path | None = None,
        api: Path | None = None,
        extra: tuple[str, ...] = (),
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Invoke the native dashboard against an isolated source and runtime root."""
        out = out or self.runtime_root / "reports" / "dashboard.md"
        command = [
            sys.executable,
            SCRIPT,
            "--root",
            str(root),
            "--runtime-root",
            str(self.runtime_root),
            "--out",
            str(out),
        ]
        if compact is not None:
            command.extend(["--compact-out", str(compact)])
        if api is not None:
            command.extend(["--api-out", str(api)])
        command.extend(extra)
        return self.run_cli(
            command, cwd=cwd, check=False, capture_output=True, text=True
        )

    def test_dashboard_api_schema_and_no_candidate_inference(self) -> None:
        """Counts and selection misses alone do not create IssueWorker candidates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_hook(
                root,
                "skill_usage.jsonl",
                [
                    {
                        "hook_run_id": "counts-only",
                        "hook_log_namespace": "test-container",
                        "event": "UserPromptSubmit",
                        "status": "pass",
                        "candidate_skills": ["agent-log-analysis"],
                    }
                ],
            )
            output = self.runtime_root / "reports" / "candidate-api.json"
            result = self.run_dashboard(root, api=output)
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["schema"], "agent_runtime_dashboard.v1")
        self.assertEqual(payload["issue_worker"]["qualified"], 0)
        self.assertEqual(payload["issue_worker"]["handoff"], 0)

    def test_issue_candidate_uses_checkout_identity_and_creates_read_only_action(
        self,
    ) -> None:
        """Only explicit candidates qualify, and the dashboard only recommends publication."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_hook(
                root,
                "behavior_events.jsonl",
                [
                    {
                        "hook_run_id": "candidate",
                        "hook_log_namespace": "test-container",
                        "event": "PostToolUse",
                        "status": "pass",
                        "checkout_identity": {
                            "remote": "git@github.com:owner/repo.git"
                        },
                        "issue_worker_candidate": {
                            "repository": "owner/repo",
                            "owner": "issue-owner",
                            "fix": "repair the route",
                            "status": "open",
                            "finding_kind": "recurrent-failure",
                            "durable_follow_up": True,
                            "occurrence_locations": ["src/module.rs::route"],
                        },
                    }
                ],
            )
            output = self.runtime_root / "reports" / "candidate-api.json"
            full = self.runtime_root / "reports" / "candidate.md"
            result = self.run_dashboard(root, api=output, out=full)
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["issue_worker"]["qualified"], 1)
        self.assertEqual(payload["issue_worker"]["routeable"], 1)
        self.assertEqual(payload["issue_worker"]["handoff"], 0)
        issue_action = next(
            action
            for action in payload["priority_next_actions"]
            if action["action"] == "publish explicit IssueWorker candidates"
        )
        self.assertIn("dashboard remains read-only", issue_action["command"])
        self.assertIn("owner/repo", full.read_text(encoding="utf-8"))

    def test_candidate_without_checkout_identity_is_handoff_not_authenticated_fallback(
        self,
    ) -> None:
        """A self-claimed repository cannot substitute for checkout identity."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_hook(
                root,
                "behavior_events.jsonl",
                [
                    {
                        "hook_run_id": "candidate",
                        "hook_log_namespace": "test-container",
                        "event": "PostToolUse",
                        "status": "pass",
                        "authenticated_repository": "owner/repo",
                        "issue_worker_candidate": {
                            "repository": "owner/repo",
                            "owner": "issue-owner",
                            "fix": "repair route",
                        },
                    }
                ],
            )
            output = self.runtime_root / "reports" / "candidate-api.json"
            result = self.run_dashboard(root, api=output)
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["issue_worker"]["handoff"], 1)
        self.assertEqual(payload["issue_worker"]["routeable"], 0)
        self.assertEqual(
            payload["issue_worker"]["reasons"], {"checkout-identity-unresolved": 1}
        )

    def test_published_receipts_are_identity_checked_and_separate_from_candidates(
        self,
    ) -> None:
        """Receipt path and body identity must agree before refs/actions are counted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_hook(
                root,
                "behavior_events.jsonl",
                [
                    {
                        "hook_run_id": "candidate",
                        "hook_log_namespace": "test-container",
                        "event": "PostToolUse",
                        "status": "pass",
                        "checkout_identity": {"remote": "owner/repo"},
                        "issue_worker_candidate": {
                            "repository": "owner/repo",
                            "owner": "issue-owner",
                            "fix": "repair route",
                        },
                    }
                ],
            )
            published = (
                mounted_log_archive_root(root)
                / "feedback"
                / "issue-packets"
                / "published"
            )
            valid_dir = published / "owner" / "repo"
            invalid_dir = published / "other" / "repo"
            valid_dir.mkdir(parents=True)
            invalid_dir.mkdir(parents=True)
            receipt = {
                "repository": "owner/repo",
                "number": "42",
                "url": "https://github.com/owner/repo/issues/42",
                "state": "OPEN",
                "action": "update",
                "responsibility": ["issue-owner"],
                "occurrence_locations": ["src/module.rs::route"],
                "source_finding_kind": "recurrent-failure",
                "timestamp": "2026-11-12T10:00:00Z",
            }
            (valid_dir / "42.json").write_text(
                json.dumps(receipt) + "\n", encoding="utf-8"
            )
            (invalid_dir / "43.json").write_text(
                json.dumps(
                    {
                        **receipt,
                        "number": "43",
                        "url": "https://github.com/owner/repo/issues/43",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            external_receipt = root / "external-receipt.json"
            external_receipt.write_text(
                json.dumps(
                    {
                        **receipt,
                        "number": "44",
                        "url": "https://github.com/owner/repo/issues/44",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (valid_dir / "44.json").symlink_to(external_receipt)
            (published / "linked-owner").symlink_to(valid_dir.parent)
            output = self.runtime_root / "reports" / "receipt-api.json"
            compact = self.runtime_root / "reports" / "receipt-compact.md"
            result = self.run_dashboard(root, api=output, compact=compact)
            payload = json.loads(output.read_text(encoding="utf-8"))
            compact_text = compact.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["github_issue_refs"], [receipt["url"]])
        self.assertEqual(payload["issue_publication_action_counts"], {"update": 1})
        self.assertEqual(payload["issue_worker"]["qualified"], 1)
        self.assertEqual(payload["issue_worker"]["published_receipts"], 1)
        self.assertIn(
            "AGENT_RUNTIME_DASHBOARD_ISSUE_PUBLICATION_RECEIPTS=1", compact_text
        )

    def test_candidate_only_workflow_stays_unattributed(self) -> None:
        """Candidate workflow suggestions do not become observed attribution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_hook(
                root,
                "skill_usage.jsonl",
                [
                    {
                        "hook_run_id": "candidate-only",
                        "hook_log_namespace": "test-container",
                        "event": "UserPromptSubmit",
                        "status": "pass",
                        "candidate_workflows": ["environment-maintenance"],
                    }
                ],
            )
            output = self.runtime_root / "reports" / "workflow.md"
            compact = self.runtime_root / "reports" / "workflow-compact.md"
            result = self.run_dashboard(root, out=output, compact=compact)
            full_text = output.read_text(encoding="utf-8")
            compact_text = compact.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("hook_entries_missing_workflow_attribution: `1`", full_text)
        self.assertIn("entries_missing_workflow", compact_text)
        self.assertNotIn(
            "| `workflow` | `environment-maintenance` | `1` | `1` | `0`", full_text
        )

    def test_token_objective_requires_evidence_and_explicit_opt_out_has_no_token_action(
        self,
    ) -> None:
        """Token evidence is required only when a token-reduction objective was selected."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            monitor = (
                self.runtime_root
                / "reports"
                / "agents"
                / "run"
                / "workflow_monitoring.md"
            )
            monitor.parent.mkdir(parents=True)
            output = self.runtime_root / "reports" / "token.md"
            api = self.runtime_root / "reports" / "token-api.json"
            monitor.write_text("token_reduction_objective=selected\n", encoding="utf-8")
            result = self.run_dashboard(root, out=output, api=api)
            selected = json.loads(api.read_text(encoding="utf-8"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "token_comparison_status: `missing`", output.read_text(encoding="utf-8")
            )
            self.assertTrue(
                any(
                    action["action"] == "add token consumption moving-average evidence"
                    for action in selected["priority_next_actions"]
                )
            )
            monitor.write_text(
                "token_efficiency_not_required reason=single-route\n", encoding="utf-8"
            )
            result = self.run_dashboard(root, out=output, api=api)
            opted_out = json.loads(api.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "token_comparison_status: `not-selected`",
            output.read_text(encoding="utf-8"),
        )
        self.assertFalse(
            any(
                action["action"] == "add token consumption moving-average evidence"
                for action in opted_out["priority_next_actions"]
            )
        )

    def test_recent_cutoff_filters_hook_rows_and_writes_all_outputs_externally(
        self,
    ) -> None:
        """Recent mode filters timestamps and all artifacts stay in the external runtime."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recent = (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            self.write_hook(
                root,
                "skill_usage.jsonl",
                [
                    {
                        "hook_run_id": "old",
                        "hook_log_namespace": "old",
                        "event": "UserPromptSubmit",
                        "status": "pass",
                        "timestamp": "2000-01-01T00:00:00Z",
                        "skills": ["old-skill"],
                    },
                    {
                        "hook_run_id": "recent",
                        "hook_log_namespace": "recent",
                        "event": "UserPromptSubmit",
                        "status": "pass",
                        "timestamp": recent,
                        "skills": ["agent-log-analysis"],
                        "prompt_capture_status": "present",
                        "prompt_char_count": 10,
                        "prompt_excerpt_redacted": "current",
                    },
                ],
            )
            out = self.runtime_root / "reports" / "dashboard.md"
            compact = self.runtime_root / "reports" / "compact.md"
            api = self.runtime_root / "reports" / "dashboard.json"
            result = self.run_dashboard(
                root, out=out, compact=compact, api=api, extra=("--recent-days", "5")
            )
            full_text = out.read_text(encoding="utf-8")
            compact_text = compact.read_text(encoding="utf-8")
            payload = json.loads(api.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["hook_entries"], 1)
        self.assertEqual(payload["hook_files"], 1)
        self.assertIn("AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES=1", compact_text)
        self.assertNotIn("old-skill", full_text)
        self.assertNotIn("old-skill", compact_text)
        self.assertFalse((root / "reports").exists())

    def test_issue_worker_candidate_has_no_authentication_fallback(self) -> None:
        """Candidate authentication uses only checkout readback, not a self-claimed field."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_hook(
                root,
                "behavior_events.jsonl",
                [
                    {
                        "hook_run_id": "candidate",
                        "hook_log_namespace": "test-container",
                        "event": "PostToolUse",
                        "status": "pass",
                        "authenticated_repository": "owner/repo",
                        "issue_worker_candidate": {
                            "repository": "owner/repo",
                            "owner": "issue-owner",
                            "fix": "repair route",
                        },
                    }
                ],
            )
            api = self.runtime_root / "reports" / "issue-api.json"
            result = self.run_dashboard(root, api=api)
            payload = json.loads(api.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            payload["issue_worker"]["reasons"], {"checkout-identity-unresolved": 1}
        )
        self.assertEqual(payload["issue_worker"]["routeable"], 0)

    def test_dashboard_source_sync_projection_is_part_of_api(self) -> None:
        """The API always includes the host-owned source-sync projection slot."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            api = self.runtime_root / "reports" / "source-sync-api.json"
            result = self.run_dashboard(root, api=api)
            payload = json.loads(api.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("source_sync_state", payload)
        self.assertEqual(payload["schema"], "agent_runtime_dashboard.v1")

    def test_generates_log_location_dashboard(self) -> None:
        """The dashboard should show canonical paths and accumulated counts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            output = self.runtime_root / "reports" / "dashboard.md"
            compact_output = self.runtime_root / "reports" / "compact-dashboard.md"

            result = self.run_cli(
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
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
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

    def test_live_like_api_and_compact_route_writes_only_external_runtime(self) -> None:
        """Container-style relative outputs stay outside the analyzed checkout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            private_log = self.runtime_root.parent / "private-log"
            private_log.mkdir()
            output_dir = self.runtime_root / "reports" / "agent-runtime-dashboard"
            output = output_dir / "dashboard.md"
            compact_output = output_dir / "agent-log-analysis-compact.md"
            api_output = output_dir / "agent-log-analysis-api.json"

            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(private_log),
                    "AGENT_CANON_LOG_ROOT": str(private_log),
                },
            ):
                self.write_fixture(root)
                result = self.run_cli(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--root",
                        ".",
                        "--out",
                        "reports/agent-runtime-dashboard/dashboard.md",
                        "--compact-out",
                        "reports/agent-runtime-dashboard/agent-log-analysis-compact.md",
                        "--api-out",
                        "reports/agent-runtime-dashboard/agent-log-analysis-api.json",
                    ],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                payload = json.loads(api_output.read_text(encoding="utf-8"))
                compact_dashboard = compact_output.read_text(encoding="utf-8")
                dashboard = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(output.is_file())
        self.assertTrue(compact_output.is_file())
        self.assertTrue(api_output.is_file())
        self.assertTrue(private_log.is_dir())
        self.assertIn(private_log.as_posix(), dashboard)
        self.assertFalse((root / "reports").exists())
        self.assertEqual(payload["schema"], "agent_runtime_dashboard.v1")
        for field in (
            "unknown_event_count",
            "status_by_hook_family",
            "failure_by_hook_family",
            "skip_by_hook_family",
            "namespace_debt_by_hook_family",
            "oop_applicability",
        ):
            self.assertIn(field, payload)
        self.assertIn("# Agent Runtime Compact Summary", compact_dashboard)
        self.assertIn("## Evidence Drilldown", compact_dashboard)
        self.assertNotIn(
            "eval/producers/",
            compact_dashboard,
        )

    def assert_compact_dashboard(self, dashboard: str) -> None:
        """Verify the token-light summary omits full dashboard-only sections."""
        required = (
            "# Agent Runtime Compact Summary",
            "## Machine Summary",
            "AGENT_RUNTIME_DASHBOARD_STATUS=pass",
            "## Priority Problems",
            "## Priority Next Actions",
            "## Selection Misses",
            "| `skill` | `md-style-check` | `0` | `1` | `1` | `100.0%` |",
            "## Evidence Drilldown",
            "### Hook Failure Drilldown",
            "### Selection Evidence Drilldown",
            "### Prompt Token Trend Drilldown",
            "### Token Consumption Drilldown",
            "| `rolling_window_observations` | `8` |",
            "| `prompt_chars_per_call_recent` | `27` |",
            "| `token_ratio_recent` | `0.500` |",
            "| `candidate_tokens_per_comparison_recent` | `100` |",
            "| `joint_trend_status` | `limited_joint_window` |",
            "| `comparison_count` | `1` |",
            "| `missing_namespaces` | `test-container=6` |",
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
            "AGENT_RUNTIME_DASHBOARD_PROBLEM_COMPONENTS=4",
            (
                "| `workflow` | `_unattributed_hook_entries` | `attention` | "
                "`6 hook entries lack workflow attribution` | "
                "`compact report Workflow Attribution Drilldown` | "
                "`repair workflow attribution logging` |"
            ),
            (
                "| `hook` | `reference_capture_guard` | `attention` | "
                "`1 referenced URLs are unregistered` | "
                "`compact report Reference Capture Drilldown` | "
                "`materialize references or repair hook logging` |"
            ),
        )
        for expected in required:
            self.assertIn(expected, dashboard)

    def assert_next_action_section(self, dashboard: str) -> None:
        """Verify concrete dashboard-generated next actions."""
        required = (
            "## Next Actions",
            "AGENT_RUNTIME_DASHBOARD_NEXT_ACTIONS=",
            "AGENT_RUNTIME_DASHBOARD_BLOCKING_NEXT_ACTIONS=3",
            "`materialize missing consulted source URLs`",
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
            "## Issue Routing",
            "missing-local-issue",
            "## Hook Workflow Attribution",
            "| `_none` | `0` |",
            "hook_entries_missing_workflow_attribution: `6`",
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
            "| `tools/bin/agent-canon` | `1` |",
            "### Selected Repo Tools",
            "| `agent-canon-cli` | `1` |",
            "## Markdown Docs Hook Signals",
            "AGENT_RUNTIME_DASHBOARD_MARKDOWN_HOOK_SIGNALS=2",
            "markdown_hook_signal_status: `present`",
            "| `agent-canon-cli` | `1` |",
        )
        for expected in required:
            self.assertIn(expected, dashboard)
        self.assert_selection_rows(dashboard)

    def assert_selection_rows(self, dashboard: str) -> None:
        """Verify selection table rows for each responsibility."""
        rows = (
            (
                "| `skill` | `md-style-check` | `0` | `1` | `1` | "
                "`100.0%` | `untracked-or-unknown` |"
            ),
            (
                "| `skill` | `oop-readability-check` | `1` | `1` | `0` | "
                "`0.0%` | `untracked-or-unknown` |"
            ),
            (
                "| `workflow` | `environment-maintenance` | `0` | `1` | `1` | "
                "`100.0%` | `untracked-or-unknown` |"
            ),
            (
                "| `tool` | `agent-canon-cli` | `1` | `1` | `0` | "
                "`0.0%` | `untracked-or-unknown` |"
            ),
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
            ".agent-canon/log-archive/agent-reports/<repo-key>/index.jsonl",
            "archive-agent-report --report-dir reports/agents/<run-id>",
            "AGENT_RUNTIME_DASHBOARD_HOOK_FILES=3",
            "AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES=6",
            "workflow-selection",
            "test-container",
            "environment-maintenance",
            "quality_gap",
        )
        for expected in required:
            self.assertIn(expected, dashboard)

    def test_reads_external_runtime_evidence_for_standalone_source(self) -> None:
        """Standalone source invocation reads the explicit external archive."""
        with tempfile.TemporaryDirectory() as temp_dir:
            canon_root = Path(temp_dir)
            self.write_fixture(canon_root)
            output = self.runtime_root / "reports" / "dashboard.md"

            result = self.run_cli(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(canon_root),
                    "--out",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            dashboard = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            f"AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={canon_root.resolve().as_posix()}",
            dashboard,
        )
        self.assertIn("hook_jsonl_files: `3`", dashboard)

    def test_prompt_token_trend_uses_chronological_recent_window(self) -> None:
        """Recent prompt/token trend rows should use timestamps, not file order."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_out_of_order_trend_fixture(root)
            compact_output = self.runtime_root / "reports" / "compact-dashboard.md"

            result = self.run_cli(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(self.runtime_root / "reports" / "dashboard.md"),
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
        self.assertIn(
            "| `candidate_tokens_per_comparison_recent` | `100` |", compact_dashboard
        )
        self.assertIn("| `joint_trend_status` | `ready` |", compact_dashboard)

    def test_recent_days_filters_hook_and_token_evidence(self) -> None:
        """Recent dashboard mode should not mix old JSONL rows into reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_recent_filter_fixture(root)
            compact_output = self.runtime_root / "reports" / "compact-dashboard.md"

            result = self.run_cli(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(self.runtime_root / "reports" / "dashboard.md"),
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

    def test_api_out_exposes_log_repair_schema(self) -> None:
        """The dashboard API should expose routing repair fields without raw JSONL."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.append_dashboard_schema_fixture(root)
            api_output = self.runtime_root / "reports" / "dashboard-api.json"
            compact_output = self.runtime_root / "reports" / "compact-dashboard.md"

            result = self.run_cli(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(self.runtime_root / "reports" / "dashboard.md"),
                    "--compact-out",
                    str(compact_output),
                    "--api-out",
                    str(api_output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            payload = json.loads(api_output.read_text(encoding="utf-8"))
            compact_dashboard = compact_output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["schema"], "agent_runtime_dashboard.v1")
        for key in (
            "unknown_event_count",
            "unknown_events_by_file",
            "status_by_hook_family",
            "failure_by_hook_family",
            "skip_by_hook_family",
            "namespace_debt_by_hook_family",
            "oop_applicability",
            "priority_problems",
            "priority_next_actions",
            "selection_misses",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["unknown_event_count"], 1)
        self.assertEqual(sum(payload["unknown_events_by_file"].values()), 1)
        self.assertEqual(payload["status_by_hook_family"]["skill_usage"]["fail"], 1)
        self.assertEqual(
            payload["failure_by_hook_family"]["skill_usage"]["schema-fixture"], 1
        )
        self.assertEqual(payload["namespace_debt_by_hook_family"]["skill_usage"], 1)
        self.assertEqual(
            payload["skip_by_hook_family"]["oop_readability_guard"][
                "no_changed_source_files"
            ],
            1,
        )
        self.assertEqual(payload["oop_applicability"]["applicable_count"], 1)
        self.assertEqual(payload["oop_applicability"]["not_applicable_count"], 1)
        self.assertEqual(payload["oop_applicability"]["missing_reason_count"], 0)
        self.assertIn(
            {
                "responsibility": "skill",
                "name": "md-style-check",
                "selected": 0,
                "candidate": 1,
                "missed": 1,
                "miss_rate": "100.0%",
                "reset_basis": "untracked-or-unknown",
            },
            payload["selection_misses"],
        )
        self.assertIn(
            "| `namespace_debt_by_hook_family` | `skill_usage=1` |", compact_dashboard
        )
        self.assertIn("oop_applicability", compact_dashboard)

    def test_api_and_compact_include_published_issue_refs_separate_from_candidates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            published = (
                mounted_log_archive_root(root)
                / "feedback"
                / "issue-packets"
                / "published"
                / "owner"
                / "repo"
            )
            published.mkdir(parents=True)
            (published / "42.json").write_text(
                json.dumps(
                    {
                        "repository": "owner/repo",
                        "number": "42",
                        "url": "https://github.com/owner/repo/issues/42",
                        "state": "OPEN",
                        "action": "update",
                        "responsibility": ["issue-owner"],
                        "occurrence_locations": ["tools/route.py::route"],
                        "source_finding_kind": "recurrent-failure",
                        "timestamp": "2026-08-27T00:00:00Z",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            api_output = self.runtime_root / "reports" / "dashboard-api.json"
            compact_output = self.runtime_root / "reports" / "compact-dashboard.md"
            result = self.run_cli(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(self.runtime_root / "reports" / "dashboard.md"),
                    "--compact-out",
                    str(compact_output),
                    "--api-out",
                    str(api_output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            payload = json.loads(api_output.read_text(encoding="utf-8"))
            compact = compact_output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "https://github.com/owner/repo/issues/42", payload["github_issue_refs"]
        )
        self.assertEqual(payload["issue_publication_action_counts"], {"update": 1})
        self.assertEqual(payload["issue_worker"]["published_receipts"], 1)
        self.assertEqual(
            payload["issue_worker"]["issue_publication_action_counts"], {"update": 1}
        )
        self.assertIn("AGENT_RUNTIME_DASHBOARD_ISSUE_PUBLICATION_RECEIPTS=1", compact)
        self.assertIn("update=1", compact)
        self.assertIn("published_receipts", compact)

    def test_selection_metrics_normalize_workflows_and_known_skills(self) -> None:
        """Selection metrics should compare canonical workflow names only."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.append_selection_normalization_fixture(root)
            output = self.runtime_root / "reports" / "dashboard.md"

            result = self.run_cli(
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
        self.assertIn(
            "| `workflow` | `platform-and-environment` | `1` | `1` | `0` | `0.0%` |",
            dashboard,
        )
        self.assertNotIn("| `skill` | `pid` |", dashboard)

    def test_selection_metrics_use_run_bundle_workflow_selection(self) -> None:
        """Run-bundle workflow declarations should confirm workflow candidates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_workflow_catalog_fixture(root)
            self.append_run_bundle_workflow_selection_fixture(root)
            output = self.runtime_root / "reports" / "dashboard.md"

            result = self.run_cli(
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
        self.assertIn(
            "| `workflow` | `platform-and-environment` | `1` | `1` | `0` | `0.0%` |",
            dashboard,
        )
        self.assertNotIn("| `workflow` | `agent-canon-update-route` |", dashboard)

    def test_selection_metrics_alias_legacy_docs_tool(self) -> None:
        """Legacy docs tool names should be counted under the canonical CLI."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.append_tool_alias_fixture(root)
            output = self.runtime_root / "reports" / "dashboard.md"

            result = self.run_cli(
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
        self.assertIn(
            "| `tool` | `agent-canon-cli` | `2` | `2` | `0` | `0.0%` |",
            dashboard,
        )
        self.assertNotIn("| `tool` | `docs check` |", dashboard)
        self.assertNotIn("| `tool` | `docs format` |", dashboard)

    def test_invalid_tool_selection_label_does_not_abort_dashboard(self) -> None:
        """Regex-like tool labels stay aggregate evidence without a reset path."""
        invalid_tool = "pattern='INVALID_TOOL_LABEL|...'"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            hook_dir = (
                mounted_log_archive_root(root)
                / "hook-runs"
                / repo_log_key(root)
                / "test-container"
            )
            with (hook_dir / "skill_usage.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "hook_run_id": "hook-invalid-tool-label",
                            "hook_log_namespace": "test-container",
                            "event": "UserPromptSubmit",
                            "status": "pass",
                            "payload_fingerprint": "payload-invalid-tool-label",
                            "timestamp": "2026-05-17T01:02:07Z",
                            "candidate_tools": [invalid_tool],
                        }
                    )
                    + "\n"
                )
            output = self.runtime_root / "reports" / "dashboard.md"

            result = self.run_cli(
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
        self.assertIn(
            "| `tool` | `pattern='INVALID_TOOL_LABEL/...'` | `0` | `1` | `1` |",
            dashboard,
        )

    def test_selection_metrics_ignore_related_only_skill_candidates(self) -> None:
        """Related skill hints should not inflate missed skill selections."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            hook_dir = (
                mounted_log_archive_root(root)
                / "hook-runs"
                / repo_log_key(root)
                / "test-container"
            )
            with (hook_dir / "skill_usage.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "hook_run_id": "hook-related-skill",
                            "hook_log_namespace": "test-container",
                            "event": "UserPromptSubmit",
                            "status": "pass",
                            "timestamp": "2026-05-17T01:02:05Z",
                            "candidate_skills": ["report-writing"],
                            "candidate_skill_reasons": [
                                "report-writing:related_to=agent-log-analysis"
                            ],
                        }
                    )
                    + "\n"
                )
            output = self.runtime_root / "reports" / "dashboard.md"

            result = self.run_cli(
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
        self.assertNotIn("| `skill` | `report-writing` |", dashboard)

    def test_selection_metrics_ignore_legacy_unattributed_skill_candidates(
        self,
    ) -> None:
        """Legacy candidate-only hook entries should not become skill misses."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            hook_dir = (
                mounted_log_archive_root(root)
                / "hook-runs"
                / repo_log_key(root)
                / "test-container"
            )
            with (hook_dir / "skill_usage.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "hook_run_id": "hook-legacy-skill",
                            "hook_log_namespace": "test-container",
                            "event": "UnknownHookEvent",
                            "status": "pass",
                            "timestamp": "2026-05-17T01:02:06Z",
                            "candidate_skills": ["report-writing"],
                        }
                    )
                    + "\n"
                )
            output = self.runtime_root / "reports" / "dashboard.md"

            result = self.run_cli(
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
        self.assertNotIn("| `skill` | `report-writing` |", dashboard)

    def write_fixture(self, root: Path, *, source_root: Path | None = None) -> None:
        """Write a small AgentCanon-like evidence tree."""
        source = source_root or root
        archive = mounted_log_archive_root(root)
        hook_dir = archive / "hook-runs" / repo_log_key(source) / "test-container"
        workflow_dir = archive / "eval-results" / "workflow-selection"
        evals_dir = root / "agents" / "evals"
        evals_dir.mkdir(parents=True)
        (evals_dir / "README.md").write_text("# Eval Fixture\n", encoding="utf-8")
        self.create_fixture_dirs(root, hook_dir, workflow_dir)
        self.write_issue_knowledge_fixture(root)
        self.write_eval_report_fixture(workflow_dir)
        self.write_hook_fixture(hook_dir)
        self.write_workflow_monitor_fixture(root)

    def create_fixture_dirs(
        self,
        root: Path,
        hook_dir: Path,
        workflow_dir: Path,
    ) -> None:
        """Create fixture directories."""
        for directory in (hook_dir, workflow_dir):
            directory.mkdir(parents=True)
        (root / "issues" / "open").mkdir(parents=True)
        (root / "issues" / "closed").mkdir(parents=True)

    def write_issue_knowledge_fixture(self, root: Path) -> None:
        """Write issue and private knowledge fixture files."""
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

    def write_eval_report_fixture(
        self,
        workflow_dir: Path,
    ) -> None:
        """Write eval report fixture files."""
        (
            workflow_dir
            / "workflow-selection-eval-20260517T010203040506Z-1234567890-pass.md"
        ).write_text(
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
                    "candidate_tools": ["agent-canon-cli"],
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
                    "tool_command_verb": "tools/bin/agent-canon",
                    "selected_tools": ["agent-canon-cli"],
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

    def append_selection_normalization_fixture(self, root: Path) -> None:
        """Add workflow display-name and stale selected-skill evidence."""
        skill_dir = root / "agents" / "skills"
        skill_dir.mkdir(parents=True)
        (skill_dir / "agent-orchestration.md").write_text(
            "# agent-orchestration\n", encoding="utf-8"
        )
        hook_dir = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / repo_log_key(root)
            / "test-container"
        )
        with (hook_dir / "skill_usage.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "hook_run_id": "hook-normalization",
                        "hook_log_namespace": "test-container",
                        "event": "UserPromptSubmit",
                        "status": "pass",
                        "payload_fingerprint": "payload-normalization",
                        "timestamp": "2026-05-17T01:02:04Z",
                        "skills": ["agent-orchestration", "pid"],
                        "selected_workflows": ["Platform And Environment"],
                        "workflow": ["Platform And Environment"],
                        "candidate_workflows": ["platform-and-environment"],
                    }
                )
                + "\n"
            )

    def append_run_bundle_workflow_selection_fixture(self, root: Path) -> None:
        """Add a workflow candidate confirmed only by run-bundle monitoring."""
        hook_dir = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / repo_log_key(root)
            / "test-container"
        )
        with (hook_dir / "skill_usage.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "hook_run_id": "hook-workflow-candidate",
                        "hook_log_namespace": "test-container",
                        "event": "UserPromptSubmit",
                        "status": "pass",
                        "payload_fingerprint": "payload-workflow-candidate",
                        "timestamp": "2026-05-17T01:02:04Z",
                        "candidate_workflows": [
                            "platform-and-environment",
                            "agent-canon-update-route",
                        ],
                    }
                )
                + "\n"
            )
        workflow_report = (
            self.runtime_root / "reports" / "agents" / "test" / "workflow_monitoring.md"
        )
        workflow_report.write_text(
            workflow_report.read_text(encoding="utf-8")
            + "- `2026-05-17 10:02 JST` workflow=Platform And Environment, "
            + "skills=$agent-orchestration, review=local\n",
            encoding="utf-8",
        )

    def append_tool_alias_fixture(self, root: Path) -> None:
        """Add a legacy docs-tool candidate and canonical tool selection."""
        hook_dir = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / repo_log_key(root)
            / "test-container"
        )
        with (hook_dir / "skill_usage.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "hook_run_id": "hook-tool-alias-candidate",
                        "hook_log_namespace": "test-container",
                        "event": "UserPromptSubmit",
                        "status": "pass",
                        "payload_fingerprint": "payload-tool-alias-candidate",
                        "timestamp": "2026-05-17T01:02:04Z",
                        "candidate_tools": ["docs check", "docs format"],
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "hook_run_id": "hook-tool-alias-selected",
                        "hook_log_namespace": "test-container",
                        "event": "PostToolUse",
                        "status": "pass",
                        "payload_fingerprint": "payload-tool-alias-selected",
                        "timestamp": "2026-05-17T01:02:05Z",
                        "selected_tools": ["agent-canon-cli"],
                    }
                )
                + "\n"
            )

    def write_workflow_catalog_fixture(self, root: Path) -> None:
        """Write a minimal workflow family catalog."""
        catalog = root / "agents" / "task_catalog.yaml"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text(
            "workflow_families:\n"
            "  - id: platform_and_environment\n"
            "    name: Platform And Environment\n"
            "tasks:\n"
            "  - id: T1\n"
            "    family: platform_and_environment\n",
            encoding="utf-8",
        )

    def append_dashboard_schema_fixture(self, root: Path) -> None:
        """Add focused hook entries for dashboard API schema assertions."""
        hook_dir = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / repo_log_key(root)
            / "test-container"
        )
        with (hook_dir / "skill_usage.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "hook_run_id": "hook-schema-unknown",
                        "event": "UnknownHookEvent",
                        "status": "fail",
                        "failure_fingerprint": "schema-fixture",
                        "payload_fingerprint": "payload-schema",
                    }
                )
                + "\n"
            )
        with (hook_dir / "oop_readability_guard.jsonl").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write(
                json.dumps(
                    {
                        "hook_run_id": "hook-schema-oop-skip",
                        "hook_log_namespace": "test-container",
                        "event": "PostToolUse",
                        "status": "skipped",
                        "payload_fingerprint": "payload-oop-skip",
                        "checked": False,
                        "skip_reason": "no_changed_source_files",
                    }
                )
                + "\n"
            )

    def write_workflow_monitor_fixture(self, root: Path) -> None:
        """Write token comparison fixture files."""
        report_dir = self.runtime_root / "reports" / "agents" / "test"
        report_dir.mkdir(parents=True, exist_ok=True)
        workflow_report = report_dir / "workflow_monitoring.md"
        workflow_report.write_text(
            "timestamp=2026-05-17T01:02:03Z "
            "token_efficiency_protocol=active token_footprint_comparison=pass "
            "baseline_total=200 candidate_total=100 token_ratio=0.500 target_ratio=0.500\n",
            encoding="utf-8",
        )

    def write_recent_filter_fixture(self, root: Path) -> None:
        """Write mixed old and recent evidence for recent-mode assertions."""
        hook_dir = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / repo_log_key(root)
            / "test-container"
        )
        hook_dir.mkdir(parents=True)
        recent_timestamp = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
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
        hook_dir = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / repo_log_key(root)
            / "test-container"
        )
        (
            self.runtime_root / "reports" / "agents" / "test" / "workflow_monitoring.md"
        ).unlink()
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

    def write_token_report(
        self,
        root: Path,
        name: str,
        timestamp: str,
        baseline: int,
        candidate: int,
        ratio: float,
    ) -> None:
        """Write one token comparison report."""
        report = (
            self.runtime_root / "reports" / "agents" / name / "workflow_monitoring.md"
        )
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            f"timestamp={timestamp} baseline_total={baseline} "
            f"candidate_total={candidate} token_ratio={ratio:.3f}\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
